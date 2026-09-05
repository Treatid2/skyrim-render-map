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


class DatasetCompilerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = pathlib.Path(self.temporary.name)
        self._add_legacy_submission()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _applicability(executable: str | None = None) -> dict:
        return {
            "engine": {
                "runtime": "skyrim-vr-1.4.15",
                "executableSha256": executable,
                "moduleSha256": None,
            },
            "extension": {
                "namespace": "csx",
                "sourceCommit": None,
                "buildId": None,
                "artifactSha256": None,
            },
            "configurationSha256": None,
            "scenarioSha256": None,
        }

    def _assertion(
        self,
        assertion_id: str,
        value: object,
        *,
        executable: str | None = None,
        policy: str = "single-valued",
    ) -> dict:
        return {
            "schema": {
                "name": "skyrim-render-map.assertion",
                "major": 1,
                "minor": 0,
            },
            "assertionId": assertion_id,
            "subject": "urn:test:render-target",
            "predicate": "engine.resource.format",
            "value": value,
            "conflictPolicy": policy,
            "applicability": self._applicability(executable),
            "evidence": {
                "class": "runtime-capture",
                "confidence": "high",
                "refs": ["evidence://fixture"],
            },
            "notes": "Fixture assertion",
        }

    def _write_manifest(
        self, directory: pathlib.Path, submission_id: str, submission_class: str
    ) -> None:
        summary = VALIDATOR.summarize_tree(directory / "content")
        manifest = {
            "schema": {
                "name": "skyrim-render-map.submission",
                "major": 1,
                "minor": 0,
            },
            "submissionId": submission_id,
            "submissionClass": submission_class,
            "namespace": "fixture",
            "createdAt": "2026-09-05T12:00:00+01:00",
            "status": "candidate-unreviewed",
            "contributor": {
                "displayName": "Fixture",
                "github": None,
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
                "importedAt": "2026-09-05T12:00:00+01:00",
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
            "notes": "Fixture",
        }
        (directory / "submission.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

    def _directory(self, submission_id: str) -> pathlib.Path:
        directory = self.repository / "submissions" / "2026" / "09" / submission_id
        (directory / "content").mkdir(parents=True)
        return directory

    def _add_legacy_submission(self) -> None:
        directory = self._directory("sub-fixture-legacy")
        (directory / "content" / "note.md").write_text("fixture\n", encoding="utf-8")
        self._write_manifest(directory, directory.name, "legacy-import")

    def _add_assertions(self, submission_id: str, records: list[dict]) -> None:
        directory = self._directory(submission_id)
        text = "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
            for record in records
        )
        (directory / "content" / "assertions.jsonl").write_text(
            text, encoding="utf-8", newline="\n"
        )
        self._write_manifest(directory, submission_id, "assertion")

    def _add_resolution(self, submission_id: str, record: dict) -> None:
        directory = self._directory(submission_id)
        text = json.dumps(
            record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ) + "\n"
        (directory / "content" / "resolutions.jsonl").write_text(
            text, encoding="utf-8", newline="\n"
        )
        self._write_manifest(directory, submission_id, "resolution")

    def test_equal_values_are_support_not_conflict(self) -> None:
        self._add_assertions("sub-fixture-first", [self._assertion("a-1", "RGBA8")])
        self._add_assertions("sub-fixture-second", [self._assertion("a-2", "RGBA8")])
        snapshot = COMPILER.compile_repository(self.repository)
        self.assertEqual(snapshot["statistics"]["conflictCount"], 0)
        self.assertEqual(
            {assertion["state"] for assertion in snapshot["assertions"]},
            {"supported"},
        )

    def test_overlapping_different_values_are_contested(self) -> None:
        self._add_assertions("sub-fixture-first", [self._assertion("a-1", "RGBA8")])
        self._add_assertions("sub-fixture-second", [self._assertion("a-2", "RGBA16")])
        snapshot = COMPILER.compile_repository(self.repository)
        self.assertEqual(snapshot["statistics"]["conflictCount"], 1)
        self.assertEqual(
            {assertion["state"] for assertion in snapshot["assertions"]},
            {"contested"},
        )

    def test_unknown_overlaps_specific_but_distinct_exact_values_do_not(self) -> None:
        self._add_assertions(
            "sub-fixture-general", [self._assertion("a-1", "general")]
        )
        self._add_assertions(
            "sub-fixture-specific",
            [self._assertion("a-2", "specific", executable="2" * 64)],
        )
        snapshot = COMPILER.compile_repository(self.repository)
        self.assertEqual(snapshot["statistics"]["conflictCount"], 1)

        self.temporary.cleanup()
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = pathlib.Path(self.temporary.name)
        self._add_legacy_submission()
        self._add_assertions(
            "sub-fixture-first",
            [self._assertion("a-1", "first", executable="2" * 64)],
        )
        self._add_assertions(
            "sub-fixture-second",
            [self._assertion("a-2", "second", executable="3" * 64)],
        )
        snapshot = COMPILER.compile_repository(self.repository)
        self.assertEqual(snapshot["statistics"]["conflictCount"], 0)

    def test_multi_valued_assertions_do_not_conflict(self) -> None:
        self._add_assertions(
            "sub-fixture-first",
            [self._assertion("a-1", "first", policy="multi-valued")],
        )
        self._add_assertions(
            "sub-fixture-second",
            [self._assertion("a-2", "second", policy="multi-valued")],
        )
        snapshot = COMPILER.compile_repository(self.repository)
        self.assertEqual(snapshot["statistics"]["conflictCount"], 0)

    def test_hex_identity_case_is_normalized(self) -> None:
        self._add_assertions(
            "sub-fixture-first",
            [self._assertion("a-1", "first", executable="A" * 64)],
        )
        self._add_assertions(
            "sub-fixture-second",
            [self._assertion("a-2", "second", executable="a" * 64)],
        )
        snapshot = COMPILER.compile_repository(self.repository)
        self.assertEqual(snapshot["statistics"]["conflictCount"], 1)
        self.assertEqual(
            {item["normalizedApplicability"]["engine"]["executableSha256"]
             for item in snapshot["assertions"]},
            {"a" * 64},
        )

    def test_resolution_preserves_assertions_and_resolves_conflict(self) -> None:
        self._add_assertions("sub-fixture-first", [self._assertion("a-1", "RGBA8")])
        self._add_assertions("sub-fixture-second", [self._assertion("a-2", "RGBA16")])
        initial = COMPILER.compile_repository(self.repository)
        conflict = initial["conflicts"][0]
        resolution = {
            "schema": {
                "name": "skyrim-render-map.resolution",
                "major": 1,
                "minor": 0,
            },
            "resolutionId": "resolution-1",
            "conflictId": conflict["conflictId"],
            "participantRefs": conflict["participants"],
            "outcome": "supersedes",
            "effectiveAssertionRefs": [conflict["participants"][1]],
            "evidenceRefs": ["evidence://review"],
            "rationale": "The later evidence is applicable.",
        }
        self._add_resolution("sub-fixture-resolution", resolution)
        snapshot = COMPILER.compile_repository(self.repository)
        self.assertEqual(len(snapshot["assertions"]), 2)
        self.assertEqual(snapshot["conflicts"][0]["state"], "resolved")
        self.assertEqual(
            {assertion["state"] for assertion in snapshot["assertions"]},
            {"resolved-contest"},
        )

    def test_resolution_must_match_exact_conflict(self) -> None:
        self._add_assertions("sub-fixture-first", [self._assertion("a-1", "RGBA8")])
        self._add_assertions("sub-fixture-second", [self._assertion("a-2", "RGBA16")])
        conflict = COMPILER.compile_repository(self.repository)["conflicts"][0]
        resolution = {
            "schema": {
                "name": "skyrim-render-map.resolution",
                "major": 1,
                "minor": 0,
            },
            "resolutionId": "resolution-1",
            "conflictId": conflict["conflictId"],
            "participantRefs": [conflict["participants"][0], "urn:invalid"],
            "outcome": "unresolved",
            "effectiveAssertionRefs": [],
            "evidenceRefs": ["evidence://review"],
            "rationale": "The conflict remains open.",
        }
        self._add_resolution("sub-fixture-resolution", resolution)
        with self.assertRaises(COMPILER.CompileError):
            COMPILER.compile_repository(self.repository)

    def test_snapshot_is_byte_deterministic(self) -> None:
        self._add_assertions("sub-fixture-first", [self._assertion("a-1", "RGBA8")])
        first = self.repository / "first.json"
        second = self.repository / "second.json"
        snapshot = COMPILER.compile_repository(self.repository)
        COMPILER.write_snapshot(snapshot, first)
        COMPILER.write_snapshot(COMPILER.compile_repository(self.repository), second)
        self.assertEqual(first.read_bytes(), second.read_bytes())


if __name__ == "__main__":
    unittest.main()
