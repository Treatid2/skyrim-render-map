# SPDX-FileCopyrightText: 2026 Treatid2 and contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import binascii
import copy
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import struct
import sys
import tempfile
import unittest
import zipfile
import zlib
from unittest import mock


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


def _indexed_png(bit_depth: int = 1) -> bytes:
    rows = b"\x00\x00"
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(
            b"IHDR", struct.pack(">IIBBBBB", 1, 1, bit_depth, 3, 0, 0, 0)
        )
        + _png_chunk(b"PLTE", b"\x00\x00\x00\xff\xff\xff")
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

    def _replace_artifact_bytes(self, artifact: dict, data: bytes) -> None:
        name = pathlib.Path(artifact["path"]).name
        (self.source / name).write_bytes(data)
        artifact["bytes"] = len(data)
        artifact["sha256"] = hashlib.sha256(data).hexdigest()

    def _rename_artifact(self, artifact: dict, new_name: str) -> None:
        old_name = pathlib.Path(artifact["path"]).name
        (self.source / old_name).replace(self.source / new_name)
        artifact["path"] = f"D:/expired/capture/{new_name}"

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
            original_name = pathlib.Path(artifact["path"]).name
            combined_name = original_name.replace("_left.png", "_combined.png")
            (self.source / original_name).replace(self.source / combined_name)
            artifact["path"] = f"D:/expired/capture/{combined_name}"
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

    def test_fallback_requires_an_explicit_actual_source(self) -> None:
        manifest = self._manifest()
        for child in manifest["children"]:
            child["actual"] = {"source": {"fallbackApplied": True}}
        self._write_inputs(manifest)
        with self.assertRaisesRegex(EXPORTER.ExportError, "fallback without an actual"):
            EXPORTER.export_plan(self.plan_path, self.root / "unknown-fallback")

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

    def test_png_structure_is_validated_and_private_chunks_are_removed(self) -> None:
        manifest = self._manifest()
        artifact = manifest["children"][0]["artifacts"][0]
        png = _png(value=7)
        private_chunk = _png_chunk(b"tEXt", b"private-path\x00C:/Users/Example")
        png = png[:33] + private_chunk + png[33:]
        self._replace_artifact_bytes(artifact, png)
        self._write_inputs(manifest)
        output = self.root / "sanitized"
        receipt = EXPORTER.export_plan(self.plan_path, output)
        with zipfile.ZipFile(output / receipt["artifactFile"]) as archive:
            exported = archive.read("frames/000000/left.png")
            bundle = json.loads(archive.read("bundle-manifest.json"))
        self.assertNotIn(b"private-path", exported)
        metadata = bundle["frames"][0]["artifacts"][0]
        self.assertEqual(metadata["sourceSha256"], hashlib.sha256(png).hexdigest())
        self.assertEqual(metadata["sha256"], hashlib.sha256(exported).hexdigest())

        for label, invalid in {
            "truncated": _png()[:-8],
            "bad-crc": _png()[:-1] + bytes((_png()[-1] ^ 1,)),
            "unknown-ancillary": _png()[:33]
            + _png_chunk(b"vpAg", b"opaque")
            + _png()[33:],
            "indexed": _indexed_png(),
            "invalid-sbit": _png()[:33]
            + _png_chunk(b"sBIT", b"\x00\x08\x08\x08")
            + _png()[33:],
        }.items():
            manifest = self._manifest()
            self._replace_artifact_bytes(
                manifest["children"][0]["artifacts"][0], invalid
            )
            self._write_inputs(manifest)
            with self.subTest(label=label), self.assertRaises(EXPORTER.ExportError):
                EXPORTER.export_plan(self.plan_path, self.root / f"invalid-{label}")

    def test_single_eye_and_invalid_or_ambiguous_views_are_rejected(self) -> None:
        manifest = self._manifest()
        for child in manifest["children"]:
            child["artifacts"] = child["artifacts"][:1]
        self._write_inputs(manifest)
        with self.assertRaisesRegex(EXPORTER.ExportError, "complete output declaration"):
            EXPORTER.export_plan(self.plan_path, self.root / "single-eye")

        manifest = self._manifest()
        manifest["children"][0]["artifacts"][0]["view"] = "future-eye"
        self._write_inputs(manifest)
        with self.assertRaisesRegex(EXPORTER.ExportError, "unsupported view"):
            EXPORTER.export_plan(self.plan_path, self.root / "invalid-view")

        manifest = self._manifest()
        manifest["capture"]["outputs"].append(
            copy.deepcopy(manifest["capture"]["outputs"][0])
        )
        self._write_inputs(manifest)
        with self.assertRaisesRegex(EXPORTER.ExportError, "repeats an output view"):
            EXPORTER.export_plan(self.plan_path, self.root / "ambiguous-view")

    def test_output_declarations_must_agree_and_be_complete(self) -> None:
        manifest = self._manifest()
        manifest["capture"]["outputs"][0]["nameSuffix"] = "combined"
        self._write_inputs(manifest)
        with self.assertRaisesRegex(EXPORTER.ExportError, "conflicting view and suffix"):
            EXPORTER.export_plan(self.plan_path, self.root / "conflicting-output")

        manifest = self._manifest()
        manifest["capture"]["outputs"].append(
            {
                "view": "combined",
                "nameSuffix": "combined",
                "encoding": {"format": "png", "colourContract": "sdr_srgb"},
            }
        )
        self._write_inputs(manifest)
        with self.assertRaisesRegex(EXPORTER.ExportError, "complete output declaration"):
            EXPORTER.export_plan(self.plan_path, self.root / "missing-output")

        manifest = self._manifest()
        manifest["children"][0]["artifacts"][0]["actual"] = {
            "format": "jpeg",
            "colourContract": "display-p3",
        }
        self._write_inputs(manifest)
        with self.assertRaisesRegex(EXPORTER.ExportError, "conflicting format"):
            EXPORTER.export_plan(self.plan_path, self.root / "conflicting-encoding")

        manifest = self._manifest()
        manifest["children"][0]["artifacts"][0]["actual"] = {
            "format": "png",
            "colourContract": "display-p3",
        }
        self._write_inputs(manifest)
        with self.assertRaisesRegex(EXPORTER.ExportError, "conflicting colour"):
            EXPORTER.export_plan(self.plan_path, self.root / "conflicting-colour")

        manifest = self._manifest()
        manifest["children"][0]["artifacts"][0]["actual"] = {
            "view": "right_eye"
        }
        self._write_inputs(manifest)
        with self.assertRaisesRegex(EXPORTER.ExportError, "conflicting view"):
            EXPORTER.export_plan(self.plan_path, self.root / "conflicting-artifact-view")

    def test_explicit_views_do_not_require_filename_inference(self) -> None:
        manifest = self._manifest()
        manifest["capture"]["outputs"] = []
        for child in manifest["children"]:
            for index, artifact in enumerate(child["artifacts"]):
                artifact["actual"] = {
                    "view": "left_eye" if index == 0 else "right_eye",
                    "format": "png",
                    "colourContract": "sdr_srgb",
                }
                self._rename_artifact(
                    artifact, f"frame_{child['ordinal']:06d}_camera{index}.png"
                )
        self._write_inputs(manifest)
        receipt = EXPORTER.export_plan(self.plan_path, self.root / "explicit-view")
        self.assertEqual(receipt["retainedFrameCount"], 2)

        manifest = self._manifest()
        for output in manifest["capture"]["outputs"]:
            output["nameSuffix"] = output["view"]
        for child in manifest["children"]:
            for artifact, suffix in zip(child["artifacts"], ("left_eye", "right_eye")):
                old_name = pathlib.Path(artifact["path"]).name
                base = old_name.rsplit("_", 1)[0]
                self._rename_artifact(artifact, f"{base}_{suffix}.png")
        self._write_inputs(manifest)
        receipt = EXPORTER.export_plan(self.plan_path, self.root / "alias-view")
        self.assertEqual(receipt["retainedFrameCount"], 2)

        manifest = self._manifest()
        manifest["capture"] = None
        for child in manifest["children"]:
            child["artifacts"] = child["artifacts"][:1]
            artifact = child["artifacts"][0]
            artifact["actual"] = {
                "view": "source_native",
                "format": "png",
                "colourContract": "sdr_srgb",
            }
            self._rename_artifact(
                artifact, f"frame_{child['ordinal']:06d}_camera.png"
            )
            child["requested"] = {"source": {"kind": "desktop_mirror"}}
            child["effective"] = {"source": {"kind": "desktop_mirror"}}
            child["actual"] = {
                "source": {"kind": "desktop_mirror", "fallbackApplied": False}
            }
        self._write_inputs(manifest)
        receipt = EXPORTER.export_plan(self.plan_path, self.root / "explicit-mono")
        self.assertEqual(receipt["retainedFrameCount"], 2)

    def test_warning_state_and_terminal_code_allowlist_contaminate_safely(self) -> None:
        manifest = self._manifest()
        manifest["children"][0]["state"] = "completed_with_warnings"
        manifest["children"][0]["warnings"] = []
        child = manifest["children"][1]
        child["state"] = "dropped"
        child["artifacts"] = []
        child["error"] = "opaque-but-syntactically-valid"
        manifest["counts"]["written"] = 1
        manifest["counts"]["dropped"] = 1
        self._write_inputs(manifest)
        output = self.root / "warning-state"
        receipt = EXPORTER.export_plan(self.plan_path, output)
        capture = self._read_jsonl(output / "content" / "visual-captures.jsonl")
        self.assertEqual(capture["validity"]["state"], "contaminated")
        self.assertIn("child warnings", capture["validity"]["notes"])
        with zipfile.ZipFile(output / receipt["artifactFile"]) as archive:
            bundle = json.loads(archive.read("bundle-manifest.json"))
        self.assertEqual(bundle["omissions"][0]["terminalCode"], "unspecified")

    def test_plan_identity_is_validated_before_source_media(self) -> None:
        for label, mutate in {
            "submission": lambda plan: plan.update(submissionId="sub-short"),
            "collision": lambda plan: plan.update(captureId=plan["artifactId"]),
        }.items():
            plan = self._plan()
            mutate(plan)
            plan["source"]["manifestPath"] = str(self.root / "does-not-exist.json")
            self.plan_path.write_text(json.dumps(plan), encoding="utf-8")
            with self.subTest(label=label), self.assertRaises(EXPORTER.ExportError):
                EXPORTER.export_plan(self.plan_path, self.root / f"identity-{label}")

        plan = self._plan()
        plan["treatment"]["baselineObservationRef"] = EXPORTER.compiler.visual_capture_ref(
            plan["submissionId"], plan["captureId"]
        )
        plan["source"]["manifestPath"] = str(self.root / "does-not-exist.json")
        self.plan_path.write_text(json.dumps(plan), encoding="utf-8")
        with self.assertRaisesRegex(EXPORTER.ExportError, "generated capture or artifact"):
            EXPORTER.export_plan(self.plan_path, self.root / "identity-self-baseline")

        plan = self._plan()
        plan["treatment"]["baselineObservationRef"] = EXPORTER.compiler.artifact_ref(
            plan["submissionId"], plan["artifactId"]
        )
        plan["source"]["manifestPath"] = str(self.root / "does-not-exist.json")
        self.plan_path.write_text(json.dumps(plan), encoding="utf-8")
        with self.assertRaisesRegex(EXPORTER.ExportError, "generated capture or artifact"):
            EXPORTER.export_plan(self.plan_path, self.root / "identity-artifact-baseline")

    def test_producer_retention_classes_match_the_plan_schema(self) -> None:
        for retention in sorted(EXPORTER.PRODUCER_RETENTION_CLASSES):
            with self.subTest(retention=retention):
                plan = self._plan()
                plan["artifact"]["retentionClass"] = retention
                self._write_inputs(self._manifest(), plan)
                receipt = EXPORTER.export_plan(
                    self.plan_path, self.root / f"retention-{retention}"
                )
                self.assertEqual(receipt["retainedFrameCount"], 2)

        plan = self._plan()
        plan["artifact"]["retentionClass"] = "repository-inline"
        plan["source"]["manifestPath"] = str(self.root / "does-not-exist.json")
        self.plan_path.write_text(json.dumps(plan), encoding="utf-8")
        with self.assertRaisesRegex(EXPORTER.ExportError, "retentionClass is unsupported"):
            EXPORTER.export_plan(self.plan_path, self.root / "retention-neutral-only")

    def test_staged_frame_mutation_is_detected_before_publication(self) -> None:
        self._write_inputs()
        original = EXPORTER._write_bundle

        def mutate_then_write(path: pathlib.Path, inspected: dict) -> tuple[int, int, dict]:
            inspected["frames"][0]["_sourcePaths"][0].write_bytes(_png(value=99))
            return original(path, inspected)

        with mock.patch.object(EXPORTER, "_write_bundle", side_effect=mutate_then_write):
            with self.assertRaisesRegex(EXPORTER.ExportError, "staged frame changed"):
                EXPORTER.export_plan(self.plan_path, self.root / "mutated-stage")

    def test_manifest_bytes_and_digest_are_bound_to_one_read(self) -> None:
        manifest = self._manifest()
        self._write_inputs(manifest)
        expected_digest = hashlib.sha256(self.manifest_path.read_bytes()).hexdigest()
        original = EXPORTER._load_json_document

        def load_then_replace(path: pathlib.Path, context: str) -> tuple[dict, str]:
            value, digest = original(path, context)
            if context == "CSX sequence manifest":
                path.write_text('{"state":"replaced"}', encoding="utf-8")
            return value, digest

        output = self.root / "manifest-bound"
        with mock.patch.object(
            EXPORTER, "_load_json_document", side_effect=load_then_replace
        ):
            receipt = EXPORTER.export_plan(self.plan_path, output)
        self.assertEqual(receipt["sourceManifestSha256"], expected_digest)
        with zipfile.ZipFile(output / receipt["artifactFile"]) as archive:
            bundle = json.loads(archive.read("bundle-manifest.json"))
        self.assertEqual(bundle["source"]["manifestSha256"], expected_digest)
        self.assertEqual(len(bundle["frames"]), 2)

    def test_concurrent_destination_is_not_replaced(self) -> None:
        self._write_inputs()
        output = self.root / "raced-output"
        original = EXPORTER._publish_no_clobber

        def create_destination(
            staging: pathlib.Path,
            destination: pathlib.Path,
            expected: dict,
            expected_identity: tuple[int, int],
        ) -> None:
            destination.mkdir()
            (destination / "owner.txt").write_text("other producer", encoding="utf-8")
            original(staging, destination, expected, expected_identity)

        with mock.patch.object(
            EXPORTER, "_publish_no_clobber", side_effect=create_destination
        ):
            with self.assertRaisesRegex(EXPORTER.ExportError, "already exists"):
                EXPORTER.export_plan(self.plan_path, output)
        self.assertEqual((output / "owner.txt").read_text(), "other producer")

    def test_bundle_and_stage_identity_are_bound_through_publication(self) -> None:
        self._write_inputs()
        original_build = EXPORTER._build_records

        def replace_bundle(*args):
            result = original_build(*args)
            pathlib.Path(args[3]).write_bytes(b"replacement")
            return result

        with mock.patch.object(EXPORTER, "_build_records", side_effect=replace_bundle):
            with self.assertRaisesRegex(EXPORTER.ExportError, "bundle identity changed"):
                EXPORTER.export_plan(self.plan_path, self.root / "replaced-bundle")

        self._write_inputs()
        original_hash = EXPORTER._hash_stream
        hash_calls = 0

        def mutate_before_second_hash(stream) -> tuple[int, str]:
            nonlocal hash_calls
            hash_calls += 1
            if hash_calls == 2:
                stream.seek(0)
                first = stream.read(1)
                stream.seek(0)
                stream.write(bytes((first[0] ^ 1,)))
                stream.flush()
                os.fsync(stream.fileno())
            return original_hash(stream)

        with mock.patch.object(
            EXPORTER, "_hash_stream", side_effect=mutate_before_second_hash
        ):
            with self.assertRaisesRegex(EXPORTER.ExportError, "coherent verification"):
                EXPORTER.export_plan(self.plan_path, self.root / "changed-during-verify")

        original_publish = EXPORTER._publish_no_clobber

        def add_member(
            staging: pathlib.Path,
            destination: pathlib.Path,
            expected: dict,
            expected_identity: tuple[int, int],
        ):
            (staging / "unlisted.json").write_text("{}", encoding="utf-8")
            original_publish(staging, destination, expected, expected_identity)

        with mock.patch.object(EXPORTER, "_publish_no_clobber", side_effect=add_member):
            with self.assertRaisesRegex(EXPORTER.ExportError, "changed after validation"):
                EXPORTER.export_plan(self.plan_path, self.root / "mutated-public-stage")
        self.assertFalse((self.root / "mutated-public-stage").exists())

        def mutate_after_publish(
            staging: pathlib.Path,
            destination: pathlib.Path,
            expected: dict,
            expected_identity: tuple[int, int],
        ):
            original_snapshot = EXPORTER._snapshot_stage

            def snapshot(root: pathlib.Path, scan_public: bool = False):
                if root == destination and destination.exists():
                    (destination / "late-member.json").write_text("{}", encoding="utf-8")
                return original_snapshot(root, scan_public=scan_public)

            with mock.patch.object(EXPORTER, "_snapshot_stage", side_effect=snapshot):
                original_publish(staging, destination, expected, expected_identity)

        with mock.patch.object(
            EXPORTER, "_publish_no_clobber", side_effect=mutate_after_publish
        ):
            with self.assertRaisesRegex(EXPORTER.ExportError, "published output differs"):
                EXPORTER.export_plan(self.plan_path, self.root / "mutated-after-publish")
        self.assertFalse((self.root / "mutated-after-publish").exists())

    def test_bundle_rejects_ungenerated_zip_envelope_content(self) -> None:
        cases = (
            "extra-entry",
            "duplicate-entry",
            "archive-comment",
            "trailing-data",
        )
        for case in cases:
            with self.subTest(case=case):
                self._write_inputs()
                original_hash = EXPORTER._hash_stream
                injected = False

                def inject_before_first_seal(stream):
                    nonlocal injected
                    if not injected:
                        injected = True
                        stream.seek(0)
                        if case == "trailing-data":
                            stream.seek(0, os.SEEK_END)
                            stream.write(b"not generated")
                        else:
                            with zipfile.ZipFile(stream, "a") as archive:
                                if case == "extra-entry":
                                    archive.writestr(
                                        "unlisted-private.txt", b"not generated"
                                    )
                                elif case == "duplicate-entry":
                                    with self.assertWarns(UserWarning):
                                        archive.writestr(
                                            "bundle-manifest.json",
                                            b'{"replacement":true}',
                                        )
                                else:
                                    archive.comment = b"not generated"
                        stream.flush()
                        os.fsync(stream.fileno())
                    return original_hash(stream)

                with mock.patch.object(
                    EXPORTER, "_hash_stream", side_effect=inject_before_first_seal
                ):
                    with self.assertRaisesRegex(
                        EXPORTER.ExportError,
                        "bundle (member|inventory|envelope) verification failed",
                    ):
                        EXPORTER.export_plan(
                            self.plan_path, self.root / f"unexpected-zip-{case}"
                        )
                self.assertFalse((self.root / f"unexpected-zip-{case}").exists())

    def test_first_stage_seal_binds_generated_bytes_and_directories(self) -> None:
        original = EXPORTER._seal_public_stage

        for index, relative_path in enumerate(
            (
                "content/artifacts.jsonl",
                "content/visual-captures.jsonl",
                "public-preview.json",
                "export-receipt.json",
            )
        ):
            self._write_inputs()

            def replace_record(staging: pathlib.Path, *args, target=relative_path):
                path = staging / target
                path.write_bytes(path.read_bytes() + b" ")
                return original(staging, *args)

            with self.subTest(relative_path=relative_path), mock.patch.object(
                EXPORTER, "_seal_public_stage", side_effect=replace_record
            ):
                with self.assertRaisesRegex(
                    EXPORTER.ExportError, "generated public record"
                ):
                    EXPORTER.export_plan(
                        self.plan_path, self.root / f"changed-public-record-{index}"
                    )

        self._write_inputs()

        def replace_with_valid_record(staging: pathlib.Path, *args):
            path = staging / "content" / "artifacts.jsonl"
            artifact = json.loads(path.read_text(encoding="utf-8"))
            artifact["notes"] = "Individually valid but unrelated producer output."
            EXPORTER.validator.validate_artifact(artifact, "fixture replacement")
            path.write_bytes(EXPORTER._jsonl_bytes([artifact]))
            return original(staging, *args)

        with mock.patch.object(
            EXPORTER, "_seal_public_stage", side_effect=replace_with_valid_record
        ):
            with self.assertRaisesRegex(EXPORTER.ExportError, "generated public record"):
                EXPORTER.export_plan(
                    self.plan_path, self.root / "valid-but-wrong-public-record"
                )

        self._write_inputs()

        def add_directory(staging: pathlib.Path, *args):
            (staging / "unexpected-empty-directory").mkdir()
            return original(staging, *args)

        with mock.patch.object(EXPORTER, "_seal_public_stage", side_effect=add_directory):
            with self.assertRaisesRegex(EXPORTER.ExportError, "unexpected directory set"):
                EXPORTER.export_plan(self.plan_path, self.root / "extra-directory")

    def test_stage_snapshot_detects_change_to_an_already_read_member(self) -> None:
        stage = self.root / "coherent-stage"
        stage.mkdir()
        (stage / "a.txt").write_text("first", encoding="utf-8")
        (stage / "b.txt").write_text("second", encoding="utf-8")
        original = EXPORTER._read_sealed_stream
        changed = False

        def mutate_after_read(stream, path: pathlib.Path, retain_bytes: bool = False):
            nonlocal changed
            result = original(stream, path, retain_bytes=retain_bytes)
            if not changed:
                changed = True
                stream.seek(0, os.SEEK_END)
                stream.write(b"!")
                stream.flush()
                os.fsync(stream.fileno())
            return result

        with mock.patch.object(
            EXPORTER, "_read_sealed_stream", side_effect=mutate_after_read
        ):
            with self.assertRaisesRegex(EXPORTER.ExportError, "coherent verification"):
                EXPORTER._snapshot_stage(stage)

    def test_inventory_detects_members_added_during_its_walk(self) -> None:
        for member_kind in ("file", "directory"):
            with self.subTest(member_kind=member_kind):
                stage = self.root / f"membership-{member_kind}"
                earlier = stage / "earlier"
                later = stage / "later"
                earlier.mkdir(parents=True)
                later.mkdir()
                (earlier / "known.txt").write_text("known", encoding="utf-8")
                original_walk = os.walk
                changed = False

                def mutating_walk(*args, **kwargs):
                    nonlocal changed
                    for current, names, filenames in original_walk(*args, **kwargs):
                        yield current, names, filenames
                        if pathlib.Path(current) == earlier and not changed:
                            changed = True
                            if member_kind == "file":
                                (earlier / "late.txt").write_text(
                                    "late", encoding="utf-8"
                                )
                            else:
                                (earlier / "late-directory").mkdir()

                with mock.patch.object(EXPORTER.os, "walk", side_effect=mutating_walk):
                    with self.assertRaisesRegex(
                        EXPORTER.ExportError, "membership changed during enumeration"
                    ):
                        EXPORTER._inventory_stage(stage)

    def test_post_publication_verification_failure_withdraws_owned_output(self) -> None:
        self._write_inputs()
        output = self.root / "verification-error"
        original = EXPORTER._snapshot_stage

        def fail_published(root: pathlib.Path, scan_public: bool = False):
            if root == output:
                raise EXPORTER.ExportError("fixture final verification")
            return original(root, scan_public=scan_public)

        with mock.patch.object(EXPORTER, "_snapshot_stage", side_effect=fail_published):
            with self.assertRaisesRegex(EXPORTER.ExportError, "fixture final verification"):
                EXPORTER.export_plan(self.plan_path, output)
        self.assertFalse(output.exists())

        self._write_inputs()
        interrupted_output = self.root / "verification-interrupted"

        def interrupt_published(root: pathlib.Path, scan_public: bool = False):
            if root == interrupted_output:
                raise KeyboardInterrupt("fixture interruption")
            return original(root, scan_public=scan_public)

        with mock.patch.object(
            EXPORTER, "_snapshot_stage", side_effect=interrupt_published
        ):
            with self.assertRaisesRegex(KeyboardInterrupt, "fixture interruption"):
                EXPORTER.export_plan(self.plan_path, interrupted_output)
        self.assertFalse(interrupted_output.exists())

        self._write_inputs()
        uncertain_output = self.root / "verification-uncertain"

        def fail_uncertain(root: pathlib.Path, scan_public: bool = False):
            if root == uncertain_output:
                raise EXPORTER.ExportError("fixture final verification")
            return original(root, scan_public=scan_public)

        with mock.patch.object(
            EXPORTER, "_snapshot_stage", side_effect=fail_uncertain
        ), mock.patch.object(
            EXPORTER,
            "_withdraw_owned_publication",
            side_effect=EXPORTER.ExportError("fixture withdrawal uncertainty"),
        ):
            with self.assertRaisesRegex(EXPORTER.ExportError, "withdrawal failed"):
                EXPORTER.export_plan(self.plan_path, uncertain_output)
        self.assertTrue(uncertain_output.exists())

    def test_interruption_at_rename_completion_withdraws_owned_output(self) -> None:
        self._write_inputs()
        output = self.root / "rename-interrupted"
        original_rename = os.rename
        interrupted = False

        def rename_then_interrupt(source, destination):
            nonlocal interrupted
            original_rename(source, destination)
            if pathlib.Path(destination) == output and not interrupted:
                interrupted = True
                raise KeyboardInterrupt("fixture rename completion interruption")

        with mock.patch.object(EXPORTER.os, "rename", side_effect=rename_then_interrupt):
            with self.assertRaisesRegex(
                KeyboardInterrupt, "fixture rename completion interruption"
            ):
                EXPORTER.export_plan(self.plan_path, output)
        self.assertFalse(output.exists())

    def test_first_stage_seal_rejects_replacement_root(self) -> None:
        self._write_inputs()
        moved_original = self.root / "original-stage-owner"
        replacement_stage = None
        original_seal = EXPORTER._seal_public_stage

        def replace_root_before_seal(staging: pathlib.Path, *args):
            nonlocal replacement_stage
            os.rename(staging, moved_original)
            staging.mkdir()
            replacement_stage = staging
            for name in ("artifacts", "content"):
                shutil.move(str(moved_original / name), str(staging / name))
            for name in ("export-receipt.json", "public-preview.json"):
                shutil.move(str(moved_original / name), str(staging / name))
            return original_seal(staging, *args)

        with mock.patch.object(
            EXPORTER, "_seal_public_stage", side_effect=replace_root_before_seal
        ):
            with self.assertRaisesRegex(EXPORTER.ExportError, "cleanup failed"):
                EXPORTER.export_plan(self.plan_path, self.root / "replaced-first-seal")
        self.assertIsNotNone(replacement_stage)
        self.assertTrue(replacement_stage.exists())
        self.assertTrue(moved_original.exists())

    def test_cleanup_preserves_substituted_or_lost_owned_directories(self) -> None:
        self._write_inputs()
        moved_stage = self.root / "moved-owned-stage"
        foreign_stage = None

        def substitute_stage(
            staging: pathlib.Path,
            destination: pathlib.Path,
            expected: dict,
            expected_identity: tuple[int, int],
        ):
            nonlocal foreign_stage
            os.rename(staging, moved_stage)
            staging.mkdir()
            foreign_stage = staging
            (staging / "owner.txt").write_text("foreign", encoding="utf-8")
            raise EXPORTER.ExportError("fixture stage substitution")

        with mock.patch.object(
            EXPORTER, "_publish_no_clobber", side_effect=substitute_stage
        ):
            with self.assertRaisesRegex(EXPORTER.ExportError, "cleanup failed"):
                EXPORTER.export_plan(self.plan_path, self.root / "substituted-stage")
        self.assertIsNotNone(foreign_stage)
        self.assertEqual((foreign_stage / "owner.txt").read_text(), "foreign")
        self.assertTrue(moved_stage.exists())

        self._write_inputs()
        missing_stage = self.root / "missing-owned-stage"

        def remove_stage(
            staging: pathlib.Path,
            destination: pathlib.Path,
            expected: dict,
            expected_identity: tuple[int, int],
        ):
            os.rename(staging, missing_stage)
            raise EXPORTER.ExportError("fixture stage disappearance")

        with mock.patch.object(
            EXPORTER, "_publish_no_clobber", side_effect=remove_stage
        ):
            with self.assertRaisesRegex(EXPORTER.ExportError, "cleanup failed"):
                EXPORTER.export_plan(self.plan_path, self.root / "absent-stage")
        self.assertTrue(missing_stage.exists())

        self._write_inputs()
        moved_spool = self.root / "moved-owned-spool"
        foreign_spool = None
        original_build = EXPORTER._build_records

        def substitute_spool(*args):
            nonlocal foreign_spool
            result = original_build(*args)
            spool = pathlib.Path(args[4])
            os.rename(spool, moved_spool)
            spool.mkdir()
            foreign_spool = spool
            (spool / "owner.txt").write_text("foreign", encoding="utf-8")
            return result

        with mock.patch.object(EXPORTER, "_build_records", side_effect=substitute_spool):
            with self.assertRaisesRegex(EXPORTER.ExportError, "cleanup failed"):
                EXPORTER.export_plan(self.plan_path, self.root / "substituted-spool")
        self.assertIsNotNone(foreign_spool)
        self.assertEqual((foreign_spool / "owner.txt").read_text(), "foreign")
        self.assertTrue(moved_spool.exists())

    @unittest.skipUnless(os.name == "nt", "Windows handle-custody behavior")
    def test_cleanup_holds_root_identity_through_deletion(self) -> None:
        root = self.root / "owned-root"
        root.mkdir()
        (root / "owned.txt").write_text("owned", encoding="utf-8")
        expected_identity = EXPORTER._directory_identity(root, "fixture root")
        moved = self.root / "moved-root"
        original_open = EXPORTER._windows_open_path_handle
        attempted = False

        def attempt_substitution(path, *, delete, deny_delete_sharing):
            nonlocal attempted
            handle = original_open(
                path, delete=delete, deny_delete_sharing=deny_delete_sharing
            )
            if pathlib.Path(path) == root and delete and deny_delete_sharing:
                attempted = True
                with self.assertRaises(OSError):
                    os.rename(root, moved)
            return handle

        with mock.patch.object(
            EXPORTER,
            "_windows_open_path_handle",
            side_effect=attempt_substitution,
        ):
            EXPORTER._windows_delete_owned_tree(root, expected_identity, {})
        self.assertTrue(attempted)
        self.assertFalse(root.exists())
        self.assertFalse(moved.exists())

    @unittest.skipUnless(os.name == "nt", "Windows handle-custody behavior")
    def test_cleanup_preserves_child_substituted_during_deletion(self) -> None:
        root = self.root / "owned-parent"
        child = root / "active-child"
        child.mkdir(parents=True)
        (child / "owned.txt").write_text("owned", encoding="utf-8")
        root_identity = EXPORTER._directory_identity(root, "fixture root")
        child_identity = EXPORTER._directory_identity(child, "fixture child")
        moved_child = root / "moved-active-child"
        original_open = EXPORTER._windows_open_path_handle
        substituted = False

        def substitute_before_child_handle(path, *, delete, deny_delete_sharing):
            nonlocal substituted
            candidate = pathlib.Path(path)
            if candidate == child and delete and deny_delete_sharing and not substituted:
                substituted = True
                os.rename(child, moved_child)
                child.mkdir()
                (child / "foreign.txt").write_text("foreign", encoding="utf-8")
            return original_open(
                path, delete=delete, deny_delete_sharing=deny_delete_sharing
            )

        with mock.patch.object(
            EXPORTER,
            "_windows_open_path_handle",
            side_effect=substitute_before_child_handle,
        ):
            with self.assertRaisesRegex(EXPORTER.ExportError, "changed before deletion"):
                EXPORTER._windows_delete_owned_tree(
                    root, root_identity, {"active-child": child_identity}
                )
        self.assertTrue(substituted)
        self.assertEqual((child / "foreign.txt").read_text(), "foreign")
        self.assertEqual((moved_child / "owned.txt").read_text(), "owned")

    def test_unexpected_and_cleanup_errors_are_normalized(self) -> None:
        self._write_inputs()
        with mock.patch.object(
            EXPORTER, "_build_records", side_effect=AttributeError("fixture")
        ):
            with self.assertRaisesRegex(EXPORTER.ExportError, "capture export failed"):
                EXPORTER.export_plan(self.plan_path, self.root / "normalized")

        with mock.patch.object(
            EXPORTER, "_build_records", side_effect=AttributeError("fixture")
        ), mock.patch.object(
            EXPORTER,
            "_remove_private_staging",
            side_effect=EXPORTER.ExportError("fixture cleanup"),
        ):
            with self.assertRaisesRegex(EXPORTER.ExportError, "cleanup failed"):
                EXPORTER.export_plan(self.plan_path, self.root / "cleanup")


if __name__ == "__main__":
    unittest.main()
