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
    "export_optimization_run_test", TOOLS / "export_optimization_run.py"
)
EXPORTER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = EXPORTER
SPEC.loader.exec_module(EXPORTER)
VALIDATOR = sys.modules["validate_repository"]


class OptimizationExportTest(unittest.TestCase):
    frame_node = "urn:skyrim-render-map:catalog:engine:frame"
    shader_node = "urn:skyrim-render-map:catalog:csx:feature:ssgi"

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _protocol(
        self,
        name: str,
        requested: int,
        cadence: dict,
        *,
        warmup: int = 1,
    ) -> dict:
        return {
            "name": name,
            "version": "1.0.0",
            "artifactSha256": "e" * 64,
            "tools": [
                {
                    "name": "fixture-profiler",
                    "version": "3.0.0",
                    "artifactSha256": "f" * 64,
                }
            ],
            "warmupSamples": warmup,
            "requestedSamples": requested,
            "sampleCadence": cadence,
        }

    def _objective(
        self,
        objective_id: str,
        metric: str,
        unit: str,
        direction: str,
        scope: str,
        scope_refs: list[str],
        collection: dict,
    ) -> dict:
        return {
            "objectiveId": objective_id,
            "label": objective_id.replace("-", " ").title(),
            "metric": metric,
            "unit": unit,
            "direction": direction,
            "scope": scope,
            "scopeRefs": scope_refs,
            "reducer": "median-of-observation-medians",
            "dominanceEpsilon": "0",
            "collection": collection,
        }

    def _common_plan(self) -> dict:
        return {
            "schema": {
                "name": "skyrim-render-map.csx-optimization-export-plan",
                "major": 1,
                "minor": 0,
            },
            "submissionId": "sub-export-fixture",
            "map": {
                "mapSnapshotId": "map-snapshot-" + "a" * 64,
                "nodeRefs": [self.frame_node, self.shader_node],
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
                "installationId": "inst-" + "1" * 32,
                "cpuModel": "Fixture CPU",
                "gpuModel": "Fixture GPU",
                "gpuDriverVersion": "fixture-driver",
                "renderContext": {
                    "renderWidth": 2000,
                    "renderHeight": 2200,
                    "viewCount": 2,
                    "refreshRateHz": "72",
                    "renderScale": "0.67",
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
            "privacy": {
                "publicationOptIn": True,
                "fieldsPreviewed": True,
                "installationIdRandom": True,
                "installationIdResettable": True,
            },
            "experiment": {
                "experimentId": "optimization-export-fixture",
                "recordedAt": "2026-09-06T12:30:00Z",
                "producer": {
                    "name": "fixture-preset-search",
                    "version": "1.0.0",
                    "artifactSha256": "8" * 64,
                },
                "search": {
                    "algorithm": "bounded-grid",
                    "algorithmVersion": "1.0.0",
                    "randomSeedSha256": None,
                    "requestedCandidateCount": 1,
                },
                "axes": [
                    {
                        "axisId": "ssgi-slices",
                        "label": "SSGI slices",
                        "mapNodeRef": self.shader_node,
                        "settingPath": "ScreenSpaceGI.Slices",
                        "valueType": "integer",
                        "domain": {
                            "kind": "integer",
                            "minimum": 2,
                            "maximum": 8,
                            "step": 2,
                        },
                    }
                ],
                "objectives": [],
                "constraints": [],
                "notes": "Fixture producer run.",
            },
            "candidates": [],
        }

    def _inline_plan(self) -> dict:
        plan = self._common_plan()
        protocol = self._protocol(
            "inline-fixture", 3, {"mode": "frame-stride", "value": 1}
        )
        plan["experiment"]["objectives"] = [
            self._objective(
                "frame-time",
                "gpu-frame-duration",
                "milliseconds",
                "minimize",
                "whole-frame",
                [],
                {
                    "sourceKind": "inline-v1",
                    "metricSource": None,
                    "timerName": None,
                    "protocol": protocol,
                },
            ),
            self._objective(
                "visual-quality",
                "visual-quality-score",
                "percent",
                "maximize",
                "map-node",
                [self.shader_node],
                {
                    "sourceKind": "inline-v1",
                    "metricSource": None,
                    "timerName": None,
                    "protocol": protocol,
                },
            ),
        ]
        candidates = []
        for suffix, treatment, slices, frame_values, quality_values in (
            ("a", "5" * 64, 2, ["9", "10", "11"], ["78", "80", "82"]),
            ("b", "6" * 64, 4, ["11", "12", "13"], ["88", "90", "92"]),
        ):
            groups = []
            for objective_id, values in (
                ("frame-time", frame_values),
                ("visual-quality", quality_values),
            ):
                samples = [
                    {
                        "sequence": index,
                        "value": value,
                        "frame": 100 + index,
                        "timestampOffsetMs": str(index * 14),
                    }
                    for index, value in enumerate(values)
                ]
                groups.append(
                    {
                        "objectiveId": objective_id,
                        "runs": [
                            {
                                "observationId": f"candidate-{suffix}-{objective_id}",
                                "recordedAt": "2026-09-06T12:00:00Z",
                                "source": {
                                    "kind": "inline-v1",
                                    "samples": samples,
                                },
                                "validity": {
                                    "state": "valid",
                                    "contamination": [],
                                    "notes": "No known contamination.",
                                },
                                "notes": "Fixture inline observation.",
                            }
                        ],
                    }
                )
            candidates.append(
                {
                    "candidateId": f"candidate-{suffix}",
                    "label": f"Candidate {suffix.upper()}",
                    "treatmentSha256": treatment,
                    "baselineObservationRef": None,
                    "outcome": "completed",
                    "failureKind": None,
                    "parameters": [{"axisId": "ssgi-slices", "value": slices}],
                    "objectiveRuns": groups,
                    "notes": "Fixture candidate.",
                }
            )
        plan["experiment"]["search"]["requestedCandidateCount"] = 2
        plan["candidates"] = candidates
        return plan

    def _write_plan(self, plan: dict) -> pathlib.Path:
        path = self.root / "private-plan.json"
        path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        return path

    def _write_profiler_capture(
        self,
        treatment: str,
        *,
        restored: bool = True,
        interval_ms: int = 250,
    ) -> tuple[pathlib.Path, pathlib.Path]:
        raw = []
        for index, value in enumerate((2.5, 2.75, 3.0)):
            raw.append(
                {
                    "sample": index + 1,
                    "timestampUtc": f"2026-09-06T12:00:0{index}Z",
                    "frame": 100 + index,
                    "resolvedTotalMs": value,
                    "resolvedCpuTotalMs": 0.5,
                    "timers": [
                        {
                            "name": "SSGI",
                            "activeGpu": True,
                            "hasGpu": True,
                            "gpuMs": value - 1,
                            "topLevelMs": value - 1,
                            "activeCpu": True,
                            "hasCpu": True,
                            "cpuMs": 0.1,
                        }
                    ],
                    "contextFingerprint": "context-fixture",
                    "treatmentFingerprint": treatment,
                }
            )
        summary = {
            "schemaVersion": 3,
            "profilerStateRestored": restored,
            "requestedSamples": 3,
            "collectedSamples": 3,
            "uniqueFreshFrames": 3,
            "warmupSamples": 5,
            "intervalMs": interval_ms,
            "contextFingerprint": "context-fixture",
            "treatmentFingerprint": treatment,
            "startedUtc": "2026-09-06T12:00:00Z",
            "runtimeIdentity": {"artifact": {"sha256": "d" * 64}},
        }
        raw_path = self.root / "private-profiler-raw.json"
        summary_path = self.root / "private-profiler-summary.json"
        raw_path.write_text(json.dumps(raw), encoding="utf-8")
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        return raw_path, summary_path

    def _profiler_plan(self) -> dict:
        plan = self._common_plan()
        treatment = "5" * 64
        raw_path, summary_path = self._write_profiler_capture(treatment)
        plan["experiment"]["objectives"] = [
            self._objective(
                "frame-time",
                "csx-active-gpu-duration",
                "milliseconds",
                "minimize",
                "process",
                [],
                {
                    "sourceKind": "csx-profiler-v3",
                    "metricSource": "resolved-gpu-total",
                    "timerName": None,
                    "protocol": self._protocol(
                        "csx-profiler-fixture",
                        3,
                        {"mode": "wall-clock-ms", "value": "250"},
                        warmup=5,
                    ),
                },
            ),
            self._objective(
                "visual-quality",
                "visual-quality-score",
                "percent",
                "maximize",
                "map-node",
                [self.shader_node],
                {
                    "sourceKind": "inline-v1",
                    "metricSource": None,
                    "timerName": None,
                    "protocol": self._protocol(
                        "quality-fixture",
                        1,
                        {"mode": "frame-stride", "value": 1},
                    ),
                },
            ),
        ]
        plan["candidates"] = [
            {
                "candidateId": "candidate-a",
                "label": "Candidate A",
                "treatmentSha256": treatment,
                "baselineObservationRef": None,
                "outcome": "completed",
                "failureKind": None,
                "parameters": [{"axisId": "ssgi-slices", "value": 2}],
                "objectiveRuns": [
                    {
                        "objectiveId": "frame-time",
                        "runs": [
                            {
                                "observationId": "candidate-a-time",
                                "recordedAt": None,
                                "source": {
                                    "kind": "csx-profiler-v3",
                                    "rawPath": str(raw_path),
                                    "summaryPath": str(summary_path),
                                },
                                "validity": {
                                    "state": "valid",
                                    "contamination": [],
                                    "notes": "No known contamination.",
                                },
                                "notes": "Fixture profiler observation.",
                            }
                        ],
                    },
                    {
                        "objectiveId": "visual-quality",
                        "runs": [
                            {
                                "observationId": "candidate-a-quality",
                                "recordedAt": "2026-09-06T12:00:00Z",
                                "source": {
                                    "kind": "inline-v1",
                                    "samples": [
                                        {
                                            "sequence": 0,
                                            "value": "80",
                                            "frame": None,
                                            "timestampOffsetMs": "0",
                                        }
                                    ],
                                },
                                "validity": {
                                    "state": "valid",
                                    "contamination": [],
                                    "notes": "No known contamination.",
                                },
                                "notes": "Fixture quality observation.",
                            }
                        ],
                    },
                ],
                "notes": "Fixture candidate.",
            }
        ]
        return plan

    def test_inline_export_is_deterministic_and_path_free(self) -> None:
        plan_path = self._write_plan(self._inline_plan())
        first = self.root / "export-a"
        second = self.root / "export-b"
        first_receipt = EXPORTER.export_plan(plan_path, first)
        second_receipt = EXPORTER.export_plan(plan_path, second)
        self.assertEqual(first_receipt, second_receipt)
        for relative in (
            "content/performance-observations.jsonl",
            "content/optimization-experiments.jsonl",
            "public-preview.json",
            "export-receipt.json",
        ):
            self.assertEqual(
                (first / relative).read_bytes(), (second / relative).read_bytes()
            )
        public_text = "".join(
            path.read_text(encoding="utf-8")
            for path in first.rglob("*")
            if path.is_file()
        )
        self.assertNotIn(str(self.root), public_text)
        self.assertEqual(first_receipt["performanceObservationCount"], 4)
        self.assertEqual(
            len(first_receipt["derivedPreview"]["frontierCandidateRefs"]), 2
        )
        observations = VALIDATOR.load_jsonl(
            first / "content" / "performance-observations.jsonl"
        )
        for index, observation in enumerate(observations):
            VALIDATOR.validate_performance_observation(
                observation, f"exported observation {index}"
            )

    def test_profiler_v3_export_verifies_and_converts_capture(self) -> None:
        plan_path = self._write_plan(self._profiler_plan())
        receipt = EXPORTER.export_plan(plan_path, self.root / "export")
        self.assertEqual(len(receipt["sourceArtifactSha256"]), 2)
        observations = VALIDATOR.load_jsonl(
            self.root / "export" / "content" / "performance-observations.jsonl"
        )
        timing = next(
            item for item in observations if item["observationId"] == "candidate-a-time"
        )
        self.assertEqual(
            [sample["value"] for sample in timing["measurement"]["samples"]],
            ["2.5", "2.75", "3"],
        )
        self.assertEqual(
            [
                sample["timestampOffsetMs"]
                for sample in timing["measurement"]["samples"]
            ],
            ["0", "1000", "2000"],
        )
        public_text = (self.root / "export" / "public-preview.json").read_text()
        self.assertNotIn("private-profiler-raw.json", public_text)
        self.assertNotIn("private-profiler-summary.json", public_text)

    def test_profiler_v3_rejects_treatment_mismatch(self) -> None:
        plan = self._profiler_plan()
        plan["candidates"][0]["treatmentSha256"] = "6" * 64
        with self.assertRaisesRegex(EXPORTER.ExportError, "treatment fingerprint"):
            EXPORTER.export_plan(self._write_plan(plan), self.root / "export")

    def test_profiler_v3_rejects_unrestored_state(self) -> None:
        plan = self._profiler_plan()
        source = plan["candidates"][0]["objectiveRuns"][0]["runs"][0]["source"]
        summary_path = pathlib.Path(source["summaryPath"])
        summary = json.loads(summary_path.read_text())
        summary["profilerStateRestored"] = False
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        with self.assertRaisesRegex(EXPORTER.ExportError, "did not restore"):
            EXPORTER.export_plan(self._write_plan(plan), self.root / "export")

    def test_profiler_v3_rejects_cadence_mismatch(self) -> None:
        plan = self._profiler_plan()
        collection = plan["experiment"]["objectives"][0]["collection"]
        collection["protocol"]["sampleCadence"]["value"] = "100"
        with self.assertRaisesRegex(EXPORTER.ExportError, "intervalMs differs"):
            EXPORTER.export_plan(self._write_plan(plan), self.root / "export")

    def test_existing_output_is_never_overwritten(self) -> None:
        plan_path = self._write_plan(self._inline_plan())
        output = self.root / "export"
        output.mkdir()
        marker = output / "owned.txt"
        marker.write_text("preserve", encoding="utf-8")
        with self.assertRaisesRegex(EXPORTER.ExportError, "output already exists"):
            EXPORTER.export_plan(plan_path, output)
        self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")

    def test_private_path_in_public_field_is_rejected(self) -> None:
        plan = self._inline_plan()
        plan["candidates"][0]["notes"] = "Captured at C:\\Users\\Person\\run.json"
        output = self.root / "export"
        with self.assertRaisesRegex(VALIDATOR.ValidationError, "personal home path"):
            EXPORTER.export_plan(self._write_plan(plan), output)
        self.assertFalse(output.exists())

    def test_worked_example_exports(self) -> None:
        receipt = EXPORTER.export_plan(
            ROOT / "examples" / "csx-optimization-export-plan-v1.json",
            self.root / "example-export",
        )
        self.assertEqual(receipt["performanceObservationCount"], 2)
        self.assertEqual(receipt["optimizationExperimentCount"], 1)


if __name__ == "__main__":
    unittest.main()
