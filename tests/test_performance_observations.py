# SPDX-FileCopyrightText: 2026 Treatid2 and contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location(
    "compile_dataset", TOOLS / "compile_dataset.py"
)
COMPILER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = COMPILER
SPEC.loader.exec_module(COMPILER)
VALIDATOR = sys.modules["validate_repository"]


class PerformanceObservationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = pathlib.Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _record(
        observation_id: str,
        *,
        installation: str = "0" * 32,
        treatment: str = "4" * 64,
        values: tuple[str, ...] = ("4.10", "4.20", "4.15"),
        validity: str = "valid",
    ) -> dict:
        contamination = []
        validity_notes = "No known contamination."
        if validity != "valid":
            contamination = [
                {
                    "kind": "shader-compilation",
                    "firstSample": 0,
                    "lastSample": 0,
                    "notes": "Compilation overlapped the first sample.",
                }
            ]
            validity_notes = "Retained as contaminated evidence."
        return {
            "schema": {
                "name": "skyrim-render-map.performance-observation",
                "major": 1,
                "minor": 0,
            },
            "observationId": observation_id,
            "recordedAt": "2026-09-06T12:00:00Z",
            "map": {
                "mapSnapshotId": "map-snapshot-" + "a" * 64,
                "nodeRefs": ["urn:skyrim-render-map:catalog:csx:pass:example"],
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
                "runtimeRoute": "steamvr-valve-null-hmd",
            },
            "environment": {
                "installationId": "inst-" + installation,
                "cpuModel": "Fixture CPU",
                "gpuModel": "Fixture GPU",
                "gpuDriverVersion": "fixture-driver",
                "renderContext": {
                    "renderWidth": 2000,
                    "renderHeight": 2200,
                    "viewCount": 2,
                    "refreshRateHz": "72",
                    "renderScale": "0.67",
                    "frameLimiter": "steamvr",
                    "targetFrameRate": "72",
                    "reprojectionMode": "disabled",
                },
            },
            "protocol": {
                "name": "fixture-protocol",
                "version": "1.0.0",
                "artifactSha256": "e" * 64,
                "tools": [
                    {
                        "name": "fixture-profiler",
                        "version": "1.0.0",
                        "artifactSha256": "f" * 64,
                    }
                ],
                "warmupSamples": 60,
                "requestedSamples": len(values),
                "sampleCadence": {"mode": "frame-stride", "value": 1},
            },
            "scenario": {
                "label": "Fixture scene",
                "scenarioSha256": "1" * 64,
                "configurationSha256": "2" * 64,
                "cacheSha256": "3" * 64,
            },
            "treatment": {
                "label": "Fixture treatment",
                "treatmentSha256": treatment,
                "baselineObservationRef": None,
            },
            "measurement": {
                "metric": "gpu-duration",
                "unit": "milliseconds",
                "scope": "map-node",
                "scopeRefs": ["urn:skyrim-render-map:catalog:csx:pass:example"],
                "samples": [
                    {
                        "sequence": index,
                        "value": value,
                        "frame": 1000 + index,
                        "timestampOffsetMs": str(index * 14),
                    }
                    for index, value in enumerate(values)
                ],
            },
            "validity": {
                "state": validity,
                "contamination": contamination,
                "notes": validity_notes,
            },
            "privacy": {
                "publicationOptIn": True,
                "fieldsPreviewed": True,
                "installationIdRandom": True,
                "installationIdResettable": True,
            },
            "notes": "Fixture performance observation.",
        }

    def _add_submission(self, submission_id: str, records: list[dict]) -> None:
        directory = self.repository / "submissions" / "2026" / "09" / submission_id
        content = directory / "content"
        content.mkdir(parents=True)
        text = "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
            for record in records
        )
        (content / "performance-observations.jsonl").write_text(
            text, encoding="utf-8", newline="\n"
        )
        summary = VALIDATOR.summarize_tree(content)
        manifest = {
            "schema": {
                "name": "skyrim-render-map.submission",
                "major": 1,
                "minor": 0,
            },
            "submissionId": submission_id,
            "submissionClass": "observation",
            "namespace": "fixture",
            "createdAt": "2026-09-06T12:00:00Z",
            "status": "candidate-unreviewed",
            "contributor": {
                "displayName": "Fixture",
                "github": "fixture-contributor",
                "standing": "ordinary-contributor",
            },
            "provenance": {
                "sourceRepository": "https://example.invalid/repository",
                "sourceCommit": "1" * 40,
                "sourceParentCommit": None,
                "sourceRef": None,
                "sourceState": "committed-local-preservation",
                "sourcePubliclyReachable": False,
                "sourceDirty": False,
                "importedAt": "2026-09-06T12:00:00Z",
                "sourceContentTreeSha256": summary.sha256,
                "transformations": [],
                "relatedUrls": [],
            },
            "licensing": {
                "content": "CC-BY-SA-4.0",
                "schemas": "CC0-1.0",
                "dcoAcknowledged": True,
            },
            "content": {
                "root": "content",
                "fileCount": summary.file_count,
                "totalBytes": summary.total_bytes,
                "treeSha256": summary.sha256,
            },
            "notes": "Performance fixture.",
        }
        (directory / "submission.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

    def test_published_example_matches_the_runtime_contract(self) -> None:
        example = VALIDATOR.load_json_document(
            ROOT / "examples" / "performance-observation-v1.json"
        )
        VALIDATOR.validate_performance_observation(example, "published-example")

    def test_valid_record_compiles_with_deterministic_summary(self) -> None:
        self._add_submission(
            "sub-performance-valid", [self._record("performance-valid")]
        )
        snapshot = COMPILER.compile_repository(self.repository)
        observation = snapshot["performanceObservations"][0]
        self.assertEqual(
            observation["summary"],
            {
                "sampleCount": 3,
                "minimum": "4.1",
                "maximum": "4.2",
                "median": "4.15",
                "arithmeticMean": "4.15",
            },
        )
        self.assertTrue(observation["aggregateEligible"])
        self.assertEqual(snapshot["statistics"]["performanceGroupCount"], 1)
        self.assertEqual(
            snapshot["performanceGroups"][0]["outlierEvaluation"],
            "insufficient-sample",
        )

    def test_keys_separate_treatment_from_installation(self) -> None:
        first = self._record("performance-first", installation="1" * 32)
        treatment = self._record(
            "performance-treatment",
            installation="1" * 32,
            treatment="5" * 64,
        )
        second_installation = self._record(
            "performance-second-installation", installation="2" * 32
        )
        self._add_submission("sub-performance-first", [first])
        self._add_submission("sub-performance-treatment", [treatment])
        self._add_submission("sub-performance-second", [second_installation])
        observations = {
            item["record"]["observationId"]: item
            for item in COMPILER.compile_repository(self.repository)[
                "performanceObservations"
            ]
        }
        self.assertEqual(
            observations["performance-first"]["comparisonKey"],
            observations["performance-treatment"]["comparisonKey"],
        )
        self.assertNotEqual(
            observations["performance-first"]["aggregateKey"],
            observations["performance-treatment"]["aggregateKey"],
        )
        self.assertNotEqual(
            observations["performance-first"]["comparisonKey"],
            observations["performance-second-installation"]["comparisonKey"],
        )
        self.assertEqual(
            observations["performance-first"]["aggregateKey"],
            observations["performance-second-installation"]["aggregateKey"],
        )

    def test_performance_only_addition_preserves_structural_map_identity(self) -> None:
        self._add_submission(
            "sub-performance-first", [self._record("performance-first")]
        )
        first = COMPILER.compile_repository(self.repository)
        self._add_submission(
            "sub-performance-second",
            [self._record("performance-second", installation="2" * 32)],
        )
        second = COMPILER.compile_repository(self.repository)
        self.assertEqual(first["mapSnapshotId"], second["mapSnapshotId"])
        self.assertNotEqual(first["snapshotId"], second["snapshotId"])

    def test_far_outlier_is_signalled_but_retained(self) -> None:
        medians = ("10", "10", "10.1", "10.2", "10.3", "10.4", "30")
        for index, value in enumerate(medians):
            record = self._record(
                f"performance-{index}",
                installation=f"{index % 3 + 1:032x}",
                values=(value,),
            )
            self._add_submission(f"sub-performance-{index}", [record])
        snapshot = COMPILER.compile_repository(self.repository)
        self.assertEqual(len(snapshot["performanceObservations"]), 7)
        self.assertEqual(snapshot["performanceGroups"][0]["outlierEvaluation"], "evaluated")
        self.assertEqual(len(snapshot["performanceSignals"]), 1)
        self.assertEqual(
            snapshot["performanceSignals"][0]["observationRef"],
            "urn:skyrim-render-map:submission:sub-performance-6#performance-6",
        )

    def test_contaminated_record_is_preserved_but_not_aggregated(self) -> None:
        record = self._record("performance-contaminated", validity="contaminated")
        self._add_submission("sub-performance-contaminated", [record])
        snapshot = COMPILER.compile_repository(self.repository)
        self.assertEqual(len(snapshot["performanceObservations"]), 1)
        self.assertFalse(snapshot["performanceObservations"][0]["aggregateEligible"])
        self.assertEqual(snapshot["performanceGroups"], [])

    def test_baseline_must_exist_and_share_comparison_context(self) -> None:
        baseline = self._record("performance-baseline")
        treatment = self._record(
            "performance-treatment",
            treatment="5" * 64,
        )
        treatment["treatment"]["baselineObservationRef"] = (
            "urn:skyrim-render-map:submission:sub-performance-baseline"
            "#performance-baseline"
        )
        self._add_submission("sub-performance-baseline", [baseline])
        self._add_submission("sub-performance-treatment", [treatment])
        COMPILER.compile_repository(self.repository)

        treatment["environment"]["installationId"] = "inst-" + "9" * 32
        self.temporary.cleanup()
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = pathlib.Path(self.temporary.name)
        self._add_submission("sub-performance-baseline", [baseline])
        self._add_submission("sub-performance-treatment", [treatment])
        with self.assertRaises(COMPILER.CompileError):
            COMPILER.compile_repository(self.repository)

    def test_invalid_sequence_fails_closed(self) -> None:
        record = self._record("performance-invalid")
        record["measurement"]["samples"][1]["sequence"] = 7
        self._add_submission("sub-performance-invalid", [record])
        with self.assertRaises(VALIDATOR.ValidationError):
            VALIDATOR.validate_repository(self.repository)

    def test_map_scope_must_reference_a_declared_map_node(self) -> None:
        record = self._record("performance-unbound-scope")
        record["measurement"]["scopeRefs"] = [
            "urn:skyrim-render-map:catalog:csx:pass:other"
        ]
        self._add_submission("sub-performance-unbound-scope", [record])
        with self.assertRaises(VALIDATOR.ValidationError):
            VALIDATOR.validate_repository(self.repository)

    def test_missing_publication_opt_in_fails_closed(self) -> None:
        record = self._record("performance-private")
        record["privacy"]["publicationOptIn"] = False
        self._add_submission("sub-performance-private", [record])
        with self.assertRaises(VALIDATOR.ValidationError):
            VALIDATOR.validate_repository(self.repository)

    def test_performance_ledger_requires_observation_class(self) -> None:
        record = self._record("performance-wrong-class")
        self._add_submission("sub-performance-wrong-class", [record])
        manifest_path = (
            self.repository
            / "submissions"
            / "2026"
            / "09"
            / "sub-performance-wrong-class"
            / "submission.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["submissionClass"] = "legacy-import"
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        with self.assertRaises(VALIDATOR.ValidationError):
            VALIDATOR.validate_repository(self.repository)


if __name__ == "__main__":
    unittest.main()
