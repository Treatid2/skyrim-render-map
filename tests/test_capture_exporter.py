# SPDX-FileCopyrightText: 2026 Treatid2 and contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import binascii
import copy
import hashlib
import importlib.util
import json
import pathlib
import struct
import sys
import tempfile
import unittest
import zipfile
import zlib


ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location(
    "export_csx_capture_test", TOOLS / "export_csx_capture.py"
)
EXPORTER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = EXPORTER
SPEC.loader.exec_module(EXPORTER)
VALIDATOR = sys.modules["validate_repository"]


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
    )


def _png(width: int = 2, height: int = 1, value: int = 0) -> bytes:
    rows = b"".join(
        b"\x00" + bytes((value, 10, 20, 255)) * width for _ in range(height)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(
            b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
        )
        + _png_chunk(b"IDAT", zlib.compress(rows))
        + _png_chunk(b"IEND", b"")
    )


class CaptureExporterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.source = self.root / "private" / "CS_sequence_fixture"
        self.source.mkdir(parents=True)
        self.manifest_path = self.source / "sequence.json"
        self.plan_path = self.root / "plan.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _artifact(self, ordinal: int, view: str, value: int) -> dict:
        name = f"frame_{ordinal:06d}_{view}.png"
        data = _png(value=value)
        (self.source / name).write_bytes(data)
        return {
            "path": f"D:/expired/capture/{name}",
            "bytes": len(data),
            "committed": True,
            "sha256": hashlib.sha256(data).hexdigest(),
        }

    def _manifest(self) -> dict:
        children = []
        for ordinal in (1, 2):
            children.append(
                {
                    "ordinal": ordinal,
                    "requestId": f"fixture-{ordinal}",
                    "state": "completed",
                    "scheduledEngineFrame": 100 + ordinal,
                    "scheduledTimestampUs": 1_000_000 + ordinal * 500_000,
                    "artifacts": [
                        self._artifact(ordinal, "left", ordinal),
                        self._artifact(ordinal, "right", ordinal + 10),
                    ],
                    "error": None,
                }
            )
        return {
            "contract": {
                "name": "csx.screenshot",
                "major": 1,
                "minor": 0,
                "schemaRevision": 1,
            },
            "sessionId": "private-session-id",
            "requestId": "private-request-id",
            "state": "final",
            "capture": {
                "source": {"kind": "hmd_submission", "fallback": "reject"},
                "outputs": [
                    {
                        "view": "left_eye",
                        "nameSuffix": "left",
                        "encoding": {"format": "png", "colourContract": "sdr_srgb"},
                    },
                    {
                        "view": "right_eye",
                        "nameSuffix": "right",
                        "encoding": {"format": "png", "colourContract": "sdr_srgb"},
                    },
                ],
            },
            "counts": {
                "requested": 2,
                "scheduled": 2,
                "written": 2,
                "dropped": 0,
                "failed": 0,
                "inFlight": 0,
            },
            "children": children,
        }

    def _plan(self) -> dict:
        return {
            "schema": {
                "name": "skyrim-render-map.csx-capture-export-plan",
                "major": 1,
                "minor": 0,
            },
            "submissionId": "sub-capture-fixture",
            "artifactId": "capture-artifact-fixture",
            "captureId": "capture-observation-fixture",
            "recordedAt": "2026-09-07T01:00:00Z",
            "source": {
                "kind": "csx-screenshot-sequence-v1",
                "manifestPath": str(self.manifest_path),
            },
            "artifact": {
                "locationTemplate": "https://example.invalid/captures/{sha256}.zip",
                "license": "CC-BY-SA-4.0",
                "retentionClass": "object-storage",
            },
            "map": {
                "mapSnapshotId": "map-snapshot-" + "a" * 64,
                "nodeRefs": ["urn:skyrim-render-map:catalog:engine:frame"],
            },
            "runtime": {
                "engine": {
                    "runtime": "skyrim-vr-1.4.15",
                    "executableSha256": "b" * 64,
                    "moduleSha256": None,
                },
                "extensions": [
                    {
                        "namespace": "csx",
                        "sourceCommit": "c" * 40,
                        "buildId": "fixture-build",
                        "artifactSha256": "d" * 64,
                    }
                ],
                "runtimeRoute": "steamvr-physical-hmd",
            },
            "environment": {
                "installationId": "inst-" + "1" * 32,
                "cpuModel": "Fixture CPU",
                "gpuModel": "Fixture GPU",
                "gpuDriverVersion": "fixture-driver",
                "renderContext": {
                    "renderWidth": 2,
                    "renderHeight": 1,
                    "viewCount": 2,
                    "refreshRateHz": "72",
                    "renderScale": "1",
                    "frameLimiter": "disabled",
                    "targetFrameRate": "72",
                    "reprojectionMode": "disabled",
                },
            },
            "scenario": {
                "label": "Fixture scene",
                "scenarioSha256": "2" * 64,
                "configurationSha256": "3" * 64,
                "cacheSha256": "4" * 64,
            },
            "treatment": {
                "label": "Fixture treatment",
                "treatmentSha256": "5" * 64,
                "baselineObservationRef": None,
            },
            "protocol": {
                "name": "fixture-orchestrator",
                "version": "1.0.0",
                "artifactSha256": "e" * 64,
                "frameRateHz": "2",
                "timingMode": "wall-clock",
            },
            "privacy": {
                "publicationOptIn": True,
                "fieldsPreviewed": True,
                "installationIdRandom": True,
                "installationIdResettable": True,
            },
            "notes": "Fixture capture.",
        }

    def _write_inputs(self, manifest: dict | None = None, plan: dict | None = None) -> None:
        self.manifest_path.write_text(
            json.dumps(manifest or self._manifest()), encoding="utf-8"
        )
        self.plan_path.write_text(json.dumps(plan or self._plan()), encoding="utf-8")

    @staticmethod
    def _read_jsonl(path: pathlib.Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8").strip())

    def test_export_is_deterministic_and_redacts_source_paths(self) -> None:
        self._write_inputs()
        first = self.root / "first"
        second = self.root / "second"
        first_receipt = EXPORTER.export_plan(self.plan_path, first)
        second_receipt = EXPORTER.export_plan(self.plan_path, second)

        self.assertEqual(first_receipt["artifactSha256"], second_receipt["artifactSha256"])
        archive_name = first_receipt["artifactFile"].split("/")[-1]
        first_archive = first / "artifacts" / archive_name
        second_archive = second / "artifacts" / archive_name
        self.assertEqual(first_archive.read_bytes(), second_archive.read_bytes())

        artifact = self._read_jsonl(first / "content" / "artifacts.jsonl")
        capture = self._read_jsonl(first / "content" / "visual-captures.jsonl")
        VALIDATOR.validate_artifact(artifact, "artifact")
        VALIDATOR.validate_visual_capture(capture, "capture")
        self.assertEqual(capture["protocol"]["sourceKind"], "hmd_submission")
        self.assertFalse(capture["protocol"]["sourceFallbackApplied"])
        self.assertEqual(capture["validity"]["state"], "valid")

        public_text = "".join(
            path.read_text(encoding="utf-8")
            for path in first.rglob("*.json*")
        )
        self.assertNotIn(str(self.root), public_text)
        self.assertNotIn("D:/expired", public_text)
        self.assertNotIn("private-session-id", public_text)
        with zipfile.ZipFile(first_archive) as archive:
            self.assertEqual(
                archive.namelist(),
                [
                    "bundle-manifest.json",
                    "frames/000000/left.png",
                    "frames/000000/right.png",
                    "frames/000001/left.png",
                    "frames/000001/right.png",
                ],
            )
            bundle = json.loads(archive.read("bundle-manifest.json"))
        self.assertNotIn("sessionId", bundle["source"])
        self.assertNotIn("requestId", bundle["source"])

    def test_actual_fallback_source_is_preserved(self) -> None:
        manifest = self._manifest()
        manifest["capture"] = None
        for child in manifest["children"]:
            child["artifacts"] = child["artifacts"][:1]
            artifact = child["artifacts"][0]
            artifact["actual"] = {
                "view": "source_native",
                "width": 2,
                "height": 1,
                "format": "png",
                "colourContract": "sdr_srgb",
            }
            child["requested"] = {"source": {"kind": "hmd_submission"}}
            child["effective"] = {"source": {"kind": "hmd_submission"}}
            child["actual"] = {
                "source": {"kind": "desktop_mirror", "fallbackApplied": True}
            }
            child["state"] = "completed_with_warnings"
            child["warnings"] = [{"code": "source_fallback"}]
        self._write_inputs(manifest)

        output = self.root / "fallback"
        EXPORTER.export_plan(self.plan_path, output)
        capture = self._read_jsonl(output / "content" / "visual-captures.jsonl")
        self.assertEqual(capture["protocol"]["mediaKind"], "mono-sequence")
        self.assertEqual(capture["protocol"]["sourceKind"], "desktop_mirror")
        self.assertTrue(capture["protocol"]["sourceFallbackApplied"])
        self.assertEqual(capture["validity"]["state"], "contaminated")

    def test_dropped_frame_is_retained_as_contaminated_evidence(self) -> None:
        manifest = self._manifest()
        child = manifest["children"][1]
        child["state"] = "dropped"
        child["artifacts"] = []
        child["error"] = "C:/Users/Example/private-capture.png"
        manifest["counts"]["written"] = 1
        manifest["counts"]["dropped"] = 1
        self._write_inputs(manifest)

        output = self.root / "dropped"
        EXPORTER.export_plan(self.plan_path, output)
        capture = self._read_jsonl(output / "content" / "visual-captures.jsonl")
        self.assertEqual(capture["protocol"]["frameCount"], 1)
        self.assertEqual(capture["protocol"]["droppedFrames"], 1)
        self.assertEqual(capture["validity"]["state"], "contaminated")
        receipt = json.loads((output / "export-receipt.json").read_text(encoding="utf-8"))
        with zipfile.ZipFile(output / receipt["artifactFile"]) as archive:
            bundle = json.loads(archive.read("bundle-manifest.json"))
        self.assertEqual(bundle["omissions"][0]["terminalCode"], "unspecified")

    def test_invalid_frame_digest_fails_without_partial_output(self) -> None:
        manifest = self._manifest()
        manifest["children"][0]["artifacts"][0]["sha256"] = "0" * 64
        self._write_inputs(manifest)
        output = self.root / "invalid"
        with self.assertRaises(EXPORTER.ExportError):
            EXPORTER.export_plan(self.plan_path, output)
        self.assertFalse(output.exists())

    def test_nonfinal_manifest_and_zero_rate_are_rejected(self) -> None:
        manifest = self._manifest()
        manifest["state"] = "active"
        self._write_inputs(manifest)
        with self.assertRaisesRegex(EXPORTER.ExportError, "not final"):
            EXPORTER.export_plan(self.plan_path, self.root / "active")

        plan = copy.deepcopy(self._plan())
        plan["protocol"]["frameRateHz"] = "0.0"
        self._write_inputs(self._manifest(), plan)
        with self.assertRaisesRegex(EXPORTER.ExportError, "positive"):
            EXPORTER.export_plan(self.plan_path, self.root / "zero")


if __name__ == "__main__":
    unittest.main()
