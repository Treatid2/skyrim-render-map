# SPDX-FileCopyrightText: 2026 Treatid2 and contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import copy
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
    "compile_dataset_visual", TOOLS / "compile_dataset.py"
)
COMPILER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = COMPILER
SPEC.loader.exec_module(COMPILER)
VALIDATOR = sys.modules["validate_repository"]


class VisualComparisonTest(unittest.TestCase):
    submission_id = "sub-example-visual"

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = pathlib.Path(self.temporary.name)
        self.rubric = json.loads(
            (ROOT / "examples" / "visual-rubric-v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.comparison = json.loads(
            (ROOT / "examples" / "visual-comparison-v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.artifact_a = json.loads(
            (ROOT / "examples" / "artifact-v1.json").read_text(encoding="utf-8")
        )
        self.capture_a = json.loads(
            (ROOT / "examples" / "visual-capture-v1.json").read_text(encoding="utf-8")
        )
        self.artifact_b = copy.deepcopy(self.artifact_a)
        self.artifact_b["artifactId"] = "visual-artifact-b"
        self.artifact_b["artifactSha256"] = "6" * 64
        self.artifact_b["locations"] = [
            "https://example.invalid/artifacts/" + "6" * 64 + ".zip"
        ]
        self.capture_b = copy.deepcopy(self.capture_a)
        self.capture_b["captureId"] = "visual-capture-b"
        self.capture_b["captureSha256"] = "6" * 64
        self.capture_b["artifactRef"] = (
            "urn:skyrim-render-map:submission:sub-example-visual#visual-artifact-b"
        )
        self.capture_b["treatment"]["label"] = "Illustrative treatment B"
        self.capture_b["treatment"]["treatmentSha256"] = "7" * 64

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_records(
        self,
        rubrics: list[dict],
        comparisons: list[dict],
        artifacts: list[dict] | None = None,
        captures: list[dict] | None = None,
    ) -> None:
        directory = (
            self.repository
            / "submissions"
            / "2026"
            / "09"
            / self.submission_id
        )
        content = directory / "content"
        content.mkdir(parents=True)
        for name, records in (
            ("artifacts.jsonl", artifacts or [self.artifact_a, self.artifact_b]),
            ("visual-captures.jsonl", captures or [self.capture_a, self.capture_b]),
            ("visual-rubrics.jsonl", rubrics),
            ("visual-comparisons.jsonl", comparisons),
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
            "submissionId": self.submission_id,
            "submissionClass": "observation",
            "namespace": "fixture",
            "createdAt": "2026-09-06T20:00:00Z",
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
                "importedAt": "2026-09-06T20:00:00Z",
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
            "notes": "Visual comparison fixture.",
        }
        (directory / "submission.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

    def test_published_examples_validate(self) -> None:
        VALIDATOR.validate_visual_rubric(self.rubric, "rubric example")
        VALIDATOR.validate_artifact(self.artifact_a, "artifact example")
        VALIDATOR.validate_visual_capture(self.capture_a, "capture example")
        VALIDATOR.validate_visual_comparison(self.comparison, "comparison example")

    def test_compiler_preserves_unanimity_and_disagreement(self) -> None:
        self._write_records([self.rubric], [self.comparison])
        snapshot = COMPILER.compile_repository(self.repository)
        self.assertEqual(snapshot["statistics"]["visualRubricCount"], 1)
        self.assertEqual(snapshot["statistics"]["visualComparisonCount"], 1)
        self.assertEqual(snapshot["statistics"]["artifactCount"], 2)
        self.assertEqual(snapshot["statistics"]["artifactIdentityCount"], 2)
        self.assertEqual(snapshot["statistics"]["visualCaptureCount"], 2)
        summary = snapshot["visualComparisonSummaries"][0]
        states = {
            item["dimensionId"]: item["state"] for item in summary["dimensions"]
        }
        self.assertEqual(states["temporal-stability"], "unanimous-a-better")
        self.assertEqual(states["overall-preference"], "contested")
        self.assertTrue(summary["optimizationEligible"])
        self.assertEqual(len(snapshot["visualComparisons"][0]["record"]["trials"]), 2)

    def test_unknown_rubric_reference_fails_compilation(self) -> None:
        comparison = copy.deepcopy(self.comparison)
        comparison["rubricRef"] = "urn:skyrim-render-map:submission:missing#rubric"
        self._write_records([self.rubric], [comparison])
        with self.assertRaisesRegex(COMPILER.CompileError, "unknown rubric"):
            COMPILER.compile_repository(self.repository)

    def test_every_trial_must_cover_every_rubric_dimension(self) -> None:
        comparison = copy.deepcopy(self.comparison)
        comparison["trials"][0]["judgments"].pop()
        self._write_records([self.rubric], [comparison])
        with self.assertRaisesRegex(COMPILER.CompileError, "every rubric dimension"):
            COMPILER.compile_repository(self.repository)

    def test_region_must_remain_inside_normalized_frame(self) -> None:
        comparison = copy.deepcopy(self.comparison)
        region = comparison["trials"][0]["judgments"][0]["evidence"][0]["region"]
        region["x"] = "0.8"
        with self.assertRaisesRegex(VALIDATOR.ValidationError, "horizontal bounds"):
            VALIDATOR.validate_visual_comparison(comparison, "comparison")

    def test_model_evaluator_requires_exact_provenance(self) -> None:
        comparison = copy.deepcopy(self.comparison)
        comparison["trials"][0]["evaluator"]["promptSha256"] = None
        with self.assertRaisesRegex(VALIDATOR.ValidationError, "artifact provenance"):
            VALIDATOR.validate_visual_comparison(comparison, "comparison")

    def test_still_pair_requires_one_frame_without_rate(self) -> None:
        comparison = copy.deepcopy(self.comparison)
        protocol = comparison["protocol"]
        protocol["mediaKind"] = "still-pair"
        protocol["viewCount"] = 1
        protocol["frameCount"] = 1
        protocol["frameRateHz"] = None
        for trial in comparison["trials"]:
            for judgment in trial["judgments"]:
                judgment["evidence"] = []
        VALIDATOR.validate_visual_comparison(comparison, "comparison")
        protocol["frameRateHz"] = "72"
        with self.assertRaisesRegex(VALIDATOR.ValidationError, "still-pair"):
            VALIDATOR.validate_visual_comparison(comparison, "comparison")

    def test_source_observation_reference_must_resolve(self) -> None:
        comparison = copy.deepcopy(self.comparison)
        comparison["stimuli"]["a"]["sourceObservationRef"] = "urn:future"
        self._write_records([self.rubric], [comparison])
        with self.assertRaisesRegex(COMPILER.CompileError, "unknown visual capture"):
            COMPILER.compile_repository(self.repository)

    def test_capture_digest_must_match_artifact(self) -> None:
        capture = copy.deepcopy(self.capture_a)
        capture["captureSha256"] = "0" * 64
        self._write_records(
            [self.rubric], [self.comparison], captures=[capture, self.capture_b]
        )
        with self.assertRaisesRegex(COMPILER.CompileError, "digest does not match"):
            COMPILER.compile_repository(self.repository)

    def test_capture_artifact_reference_must_resolve(self) -> None:
        capture = copy.deepcopy(self.capture_a)
        capture["artifactRef"] = "urn:skyrim-render-map:submission:missing#artifact"
        self._write_records(
            [self.rubric], [self.comparison], captures=[capture, self.capture_b]
        )
        with self.assertRaisesRegex(COMPILER.CompileError, "unknown artifact"):
            COMPILER.compile_repository(self.repository)

    def test_artifact_locations_are_https_without_credentials(self) -> None:
        artifact = copy.deepcopy(self.artifact_a)
        artifact["locations"] = ["https://user:secret@example.invalid/capture.zip"]
        with self.assertRaisesRegex(VALIDATOR.ValidationError, "credentials"):
            VALIDATOR.validate_artifact(artifact, "artifact")

    def test_artifact_index_unions_mirrors_and_signals_metadata_conflict(self) -> None:
        mirror = copy.deepcopy(self.artifact_a)
        mirror["artifactId"] = "visual-artifact-a-mirror"
        mirror["mediaType"] = "application/octet-stream"
        mirror["locations"] = ["https://mirror.example.invalid/capture-a.zip"]
        self._write_records(
            [self.rubric],
            [self.comparison],
            artifacts=[self.artifact_a, mirror, self.artifact_b],
        )
        snapshot = COMPILER.compile_repository(self.repository)
        item = next(
            entry
            for entry in snapshot["artifactIndex"]
            if entry["artifactSha256"] == "4" * 64
        )
        self.assertEqual(item["metadataState"], "contested")
        self.assertEqual(len(item["recordRefs"]), 2)
        self.assertEqual(len(item["locations"]), 2)

    def test_stimulus_treatment_must_match_capture(self) -> None:
        comparison = copy.deepcopy(self.comparison)
        comparison["stimuli"]["a"]["treatmentSha256"] = "0" * 64
        self._write_records([self.rubric], [comparison])
        with self.assertRaisesRegex(COMPILER.CompileError, "treatment digest mismatch"):
            COMPILER.compile_repository(self.repository)

    def test_capture_protocols_must_match(self) -> None:
        capture_b = copy.deepcopy(self.capture_b)
        capture_b["protocol"]["width"] = 1920
        self._write_records(
            [self.rubric], [self.comparison], captures=[self.capture_a, capture_b]
        )
        with self.assertRaisesRegex(COMPILER.CompileError, "capture protocols differ"):
            COMPILER.compile_repository(self.repository)

    def test_capture_context_must_match_comparison(self) -> None:
        capture = copy.deepcopy(self.capture_a)
        capture["environment"]["gpuDriverVersion"] = "different-driver"
        self._write_records(
            [self.rubric], [self.comparison], captures=[capture, self.capture_b]
        )
        with self.assertRaisesRegex(COMPILER.CompileError, "not comparable"):
            COMPILER.compile_repository(self.repository)

    def test_valid_capture_rejects_dropped_frames(self) -> None:
        capture = copy.deepcopy(self.capture_a)
        capture["protocol"]["droppedFrames"] = 1
        with self.assertRaisesRegex(VALIDATOR.ValidationError, "complete and uncontaminated"):
            VALIDATOR.validate_visual_capture(capture, "capture")

    def test_rubric_requires_canonical_magnitude_scale(self) -> None:
        rubric = copy.deepcopy(self.rubric)
        rubric["magnitudes"][1]["ordinal"] = 4
        with self.assertRaisesRegex(VALIDATOR.ValidationError, "canonical v1"):
            VALIDATOR.validate_visual_rubric(rubric, "rubric")

    def test_non_valid_comparison_is_not_optimization_eligible(self) -> None:
        comparison = copy.deepcopy(self.comparison)
        comparison["validity"] = {
            "state": "inconclusive",
            "contamination": [],
            "notes": "The presentation order could not be verified.",
        }
        self._write_records([self.rubric], [comparison])
        summary = COMPILER.compile_repository(self.repository)[
            "visualComparisonSummaries"
        ][0]
        self.assertFalse(summary["optimizationEligible"])


if __name__ == "__main__":
    unittest.main()
