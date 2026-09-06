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
    "compile_dataset_optimization", TOOLS / "compile_dataset.py"
)
COMPILER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = COMPILER
SPEC.loader.exec_module(COMPILER)
VALIDATOR = sys.modules["validate_repository"]


class OptimizationExperimentTest(unittest.TestCase):
    submission_id = "sub-optimization-fixture"
    frame_node = "urn:skyrim-render-map:catalog:engine:frame"
    shader_node = "urn:skyrim-render-map:catalog:csx:feature:ssgi"

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = pathlib.Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _observation(
        self,
        observation_id: str,
        treatment: str,
        metric: str,
        unit: str,
        scope: str,
        scope_refs: list[str],
        value: str,
        *,
        validity: str = "valid",
    ) -> dict:
        contamination = []
        validity_notes = "No known contamination."
        if validity != "valid":
            contamination = [
                {
                    "kind": "capture-overhead",
                    "firstSample": 0,
                    "lastSample": 0,
                    "notes": "Capture overlapped this sample.",
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
            "protocol": {
                "name": f"fixture-{metric}",
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
                "requestedSamples": 1,
                "sampleIntervalFrames": 1,
            },
            "scenario": {
                "label": "Fixture scene",
                "scenarioSha256": "2" * 64,
                "configurationSha256": "3" * 64,
                "cacheSha256": "4" * 64,
            },
            "treatment": {
                "label": observation_id,
                "treatmentSha256": treatment,
                "baselineObservationRef": None,
            },
            "measurement": {
                "metric": metric,
                "unit": unit,
                "scope": scope,
                "scopeRefs": scope_refs,
                "samples": [
                    {
                        "sequence": 0,
                        "value": value,
                        "frame": 1000,
                        "timestampOffsetMs": "0",
                    }
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
            "notes": "Optimization fixture observation.",
        }

    def _observation_ref(self, observation_id: str) -> str:
        return (
            "urn:skyrim-render-map:submission:"
            f"{self.submission_id}#{observation_id}"
        )

    def _experiment(self) -> dict:
        candidates = []
        for candidate_id, treatment, slices, steps in (
            ("candidate-a", "5" * 64, 2, 16),
            ("candidate-b", "6" * 64, 4, 24),
            ("candidate-c", "7" * 64, 6, 32),
        ):
            candidates.append(
                {
                    "candidateId": candidate_id,
                    "label": candidate_id,
                    "treatmentSha256": treatment,
                    "outcome": "completed",
                    "failureKind": None,
                    "parameters": [
                        {"axisId": "ssgi-slices", "value": slices},
                        {"axisId": "ssgi-steps", "value": steps},
                    ],
                    "objectiveObservations": [
                        {
                            "objectiveId": "frame-time",
                            "observationRefs": [
                                self._observation_ref(f"{candidate_id}-time")
                            ],
                        },
                        {
                            "objectiveId": "visual-quality",
                            "observationRefs": [
                                self._observation_ref(f"{candidate_id}-quality")
                            ],
                        },
                    ],
                    "notes": "Fixture candidate.",
                }
            )
        return {
            "schema": {
                "name": "skyrim-render-map.optimization-experiment",
                "major": 1,
                "minor": 0,
            },
            "experimentId": "optimization-fixture",
            "recordedAt": "2026-09-06T12:30:00Z",
            "map": {
                "mapSnapshotId": "map-snapshot-" + "a" * 64,
                "nodeRefs": [self.frame_node, self.shader_node],
            },
            "producer": {
                "name": "fixture-preset-search",
                "version": "1.0.0",
                "artifactSha256": "8" * 64,
            },
            "search": {
                "algorithm": "bounded-grid",
                "algorithmVersion": "1.0.0",
                "randomSeedSha256": None,
                "requestedCandidateCount": 3,
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
                        "maximum": 6,
                        "step": 2,
                    },
                },
                {
                    "axisId": "ssgi-steps",
                    "label": "SSGI steps",
                    "mapNodeRef": self.shader_node,
                    "settingPath": "ScreenSpaceGI.Steps",
                    "valueType": "integer",
                    "domain": {
                        "kind": "integer",
                        "minimum": 16,
                        "maximum": 32,
                        "step": 8,
                    },
                },
            ],
            "objectives": [
                {
                    "objectiveId": "frame-time",
                    "label": "GPU frame time",
                    "metric": "gpu-frame-duration",
                    "unit": "milliseconds",
                    "direction": "minimize",
                    "scope": "whole-frame",
                    "scopeRefs": [],
                    "reducer": "median-of-observation-medians",
                    "dominanceEpsilon": "0",
                },
                {
                    "objectiveId": "visual-quality",
                    "label": "Visual quality",
                    "metric": "visual-quality-score",
                    "unit": "percent",
                    "direction": "maximize",
                    "scope": "map-node",
                    "scopeRefs": [self.shader_node],
                    "reducer": "median-of-observation-medians",
                    "dominanceEpsilon": "0",
                },
            ],
            "constraints": [],
            "candidates": candidates,
            "notes": "Fixture multi-objective experiment.",
        }

    def _performance_records(self) -> list[dict]:
        records = []
        for candidate_id, treatment, time_value, quality_value in (
            ("candidate-a", "5" * 64, "10", "80"),
            ("candidate-b", "6" * 64, "12", "90"),
            ("candidate-c", "7" * 64, "14", "85"),
        ):
            records.append(
                self._observation(
                    f"{candidate_id}-time",
                    treatment,
                    "gpu-frame-duration",
                    "milliseconds",
                    "whole-frame",
                    [],
                    time_value,
                )
            )
            records.append(
                self._observation(
                    f"{candidate_id}-quality",
                    treatment,
                    "visual-quality-score",
                    "percent",
                    "map-node",
                    [self.shader_node],
                    quality_value,
                )
            )
        return records

    def _add_submission(
        self,
        submission_id: str,
        performance: list[dict],
        optimization: list[dict],
    ) -> None:
        directory = self.repository / "submissions" / "2026" / "09" / submission_id
        content = directory / "content"
        content.mkdir(parents=True)
        for name, records in (
            ("performance-observations.jsonl", performance),
            ("optimization-experiments.jsonl", optimization),
        ):
            if not records:
                continue
            text = "".join(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
                for record in records
            )
            (content / name).write_text(text, encoding="utf-8", newline="\n")
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
            "notes": "Optimization fixture.",
        }
        (directory / "submission.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

    def test_frontier_is_derived_without_discarding_dominated_candidates(self) -> None:
        self._add_submission(
            self.submission_id,
            self._performance_records(),
            [self._experiment()],
        )
        snapshot = COMPILER.compile_repository(self.repository)
        surface = snapshot["optimizationSurfaces"][0]
        self.assertEqual(surface["candidateCount"], 3)
        self.assertEqual(surface["eligibleCandidateCount"], 3)
        self.assertEqual(surface["feasibleCandidateCount"], 3)
        self.assertEqual(
            surface["frontierCandidateRefs"],
            [
                "urn:skyrim-render-map:submission:sub-optimization-fixture"
                "#optimization-fixture/candidate-a",
                "urn:skyrim-render-map:submission:sub-optimization-fixture"
                "#optimization-fixture/candidate-b",
            ],
        )
        candidate_c = next(
            item for item in surface["candidates"] if item["candidateId"] == "candidate-c"
        )
        self.assertEqual(candidate_c["dominatedBy"], [surface["frontierCandidateRefs"][1]])
        self.assertEqual(len(candidate_c["parameterVectorSha256"]), 64)

    def test_constraint_excludes_infeasible_candidates_from_frontier(self) -> None:
        experiment = self._experiment()
        experiment["constraints"] = [
            {
                "constraintId": "frame-budget",
                "objectiveId": "frame-time",
                "operator": "at-most",
                "threshold": "11",
            }
        ]
        self._add_submission(
            self.submission_id, self._performance_records(), [experiment]
        )
        surface = COMPILER.compile_repository(self.repository)[
            "optimizationSurfaces"
        ][0]
        self.assertEqual(surface["eligibleCandidateCount"], 3)
        self.assertEqual(surface["feasibleCandidateCount"], 1)
        self.assertEqual(len(surface["frontierCandidateRefs"]), 1)

    def test_contaminated_objective_excludes_candidate_but_preserves_it(self) -> None:
        observations = self._performance_records()
        contaminated = next(
            item for item in observations if item["observationId"] == "candidate-c-quality"
        )
        contaminated["validity"] = {
            "state": "contaminated",
            "contamination": [
                {
                    "kind": "capture-overhead",
                    "firstSample": 0,
                    "lastSample": 0,
                    "notes": "Capture overlapped this sample.",
                }
            ],
            "notes": "Retained as contaminated evidence.",
        }
        self._add_submission(self.submission_id, observations, [self._experiment()])
        surface = COMPILER.compile_repository(self.repository)[
            "optimizationSurfaces"
        ][0]
        candidate_c = next(
            item for item in surface["candidates"] if item["candidateId"] == "candidate-c"
        )
        self.assertEqual(candidate_c["eligibility"], "excluded")
        self.assertIn("non-valid-objective-visual-quality", candidate_c["exclusionReasons"])
        self.assertEqual(surface["candidateCount"], 3)

    def test_treatment_mismatch_fails_compilation(self) -> None:
        experiment = self._experiment()
        experiment["candidates"][0]["treatmentSha256"] = "9" * 64
        self._add_submission(
            self.submission_id, self._performance_records(), [experiment]
        )
        with self.assertRaises(COMPILER.CompileError):
            COMPILER.compile_repository(self.repository)

    def test_objective_cannot_mix_comparison_contexts(self) -> None:
        observations = self._performance_records()
        changed = next(
            item for item in observations if item["observationId"] == "candidate-c-time"
        )
        changed["environment"]["gpuDriverVersion"] = "different-driver"
        self._add_submission(self.submission_id, observations, [self._experiment()])
        with self.assertRaises(COMPILER.CompileError):
            COMPILER.compile_repository(self.repository)

    def test_axis_domain_fails_closed(self) -> None:
        experiment = self._experiment()
        experiment["candidates"][0]["parameters"][0]["value"] = 3
        with self.assertRaises(VALIDATOR.ValidationError):
            VALIDATOR.validate_optimization_experiment(experiment, "fixture")

    def test_completed_candidate_requires_every_objective(self) -> None:
        experiment = self._experiment()
        experiment["candidates"][1]["objectiveObservations"].pop()
        with self.assertRaises(VALIDATOR.ValidationError):
            VALIDATOR.validate_optimization_experiment(experiment, "fixture")

    def test_map_scoped_objective_requires_a_node_reference(self) -> None:
        experiment = self._experiment()
        experiment["objectives"][1]["scopeRefs"] = []
        with self.assertRaises(VALIDATOR.ValidationError):
            VALIDATOR.validate_optimization_experiment(experiment, "fixture")

    def test_differences_within_epsilon_do_not_create_a_dominator(self) -> None:
        experiment = self._experiment()
        experiment["objectives"][0]["dominanceEpsilon"] = "5"
        experiment["objectives"][1]["dominanceEpsilon"] = "15"
        self._add_submission(
            self.submission_id, self._performance_records(), [experiment]
        )
        surface = COMPILER.compile_repository(self.repository)[
            "optimizationSurfaces"
        ][0]
        self.assertEqual(surface["candidateCount"], 3)
        self.assertEqual(len(surface["frontierCandidateRefs"]), 3)
        self.assertTrue(
            all(not candidate["dominatedBy"] for candidate in surface["candidates"])
        )

    def test_optimization_only_addition_preserves_structural_map_identity(self) -> None:
        self._add_submission(self.submission_id, self._performance_records(), [])
        before = COMPILER.compile_repository(self.repository)
        self._add_submission(
            "sub-optimization-index",
            [],
            [self._experiment()],
        )
        after = COMPILER.compile_repository(self.repository)
        self.assertEqual(before["mapSnapshotId"], after["mapSnapshotId"])
        self.assertNotEqual(before["snapshotId"], after["snapshotId"])

    def test_published_example_matches_runtime_contract(self) -> None:
        example = VALIDATOR.load_json_document(
            ROOT / "examples" / "optimization-experiment-v1.json"
        )
        VALIDATOR.validate_optimization_experiment(example, "published-example")


if __name__ == "__main__":
    unittest.main()
