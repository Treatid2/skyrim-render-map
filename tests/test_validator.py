# SPDX-FileCopyrightText: 2026 Treatid2 and contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_repository", ROOT / "tools" / "validate_repository.py"
)
VALIDATOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = VALIDATOR
SPEC.loader.exec_module(VALIDATOR)


class ValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.base = self.root / "base"
        self.candidate = self.root / "candidate"
        self._make_repository(self.base, "sub-existing-example")
        shutil.copytree(self.base, self.candidate)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _make_repository(self, root: pathlib.Path, submission_id: str) -> None:
        directory = root / "submissions" / "2026" / "09" / submission_id
        content = directory / "content"
        content.mkdir(parents=True)
        (content / "observation.json").write_text(
            '{"observation":"example"}\n', encoding="utf-8"
        )
        self._write_manifest(directory, submission_id)
        (root / "schemas").mkdir()
        (root / "schemas" / "example.json").write_text("{}\n", encoding="utf-8")

    def _write_manifest(self, directory: pathlib.Path, submission_id: str) -> None:
        summary = VALIDATOR.summarize_tree(directory / "content")
        manifest = {
            "schema": {
                "name": "skyrim-render-map.submission",
                "major": 1,
                "minor": 0,
            },
            "submissionId": submission_id,
            "submissionClass": "observation",
            "namespace": "example",
            "createdAt": "2026-09-05T12:00:00+01:00",
            "status": "candidate-unreviewed",
            "contributor": {
                "displayName": "Example",
                "github": "example-contributor",
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

    def _add_submission(self, submission_id: str = "sub-new-example") -> pathlib.Path:
        directory = self.candidate / "submissions" / "2026" / "09" / submission_id
        content = directory / "content"
        content.mkdir(parents=True)
        (content / "observation.json").write_text(
            '{"observation":"new"}\n', encoding="utf-8"
        )
        self._write_manifest(directory, submission_id)
        return directory

    def test_accepts_one_append_only_submission(self) -> None:
        self._add_submission()
        self.assertEqual(
            VALIDATOR.validate_candidate(self.base, self.candidate),
            "Accepted for map review",
        )

    def test_rejects_self_declared_accepted_submission(self) -> None:
        directory = self._add_submission()
        manifest_path = directory / "submission.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "accepted"
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(
            VALIDATOR.ValidationError, "candidate-unreviewed"
        ):
            VALIDATOR.validate_candidate(self.base, self.candidate)

    def test_rejects_missing_github_contributor(self) -> None:
        directory = self._add_submission()
        manifest_path = directory / "submission.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["contributor"]["github"] = None
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(
            VALIDATOR.ValidationError, "GitHub contributor"
        ):
            VALIDATOR.validate_candidate(self.base, self.candidate)

    def test_rejects_existing_submission_change(self) -> None:
        existing = next(self.candidate.glob("submissions/*/*/*/content/*.json"))
        existing.write_text("{}\n", encoding="utf-8")
        with self.assertRaises(VALIDATOR.ValidationError):
            VALIDATOR.validate_candidate(self.base, self.candidate)

    def test_rejects_mixed_submission_and_governance_change(self) -> None:
        self._add_submission()
        (self.candidate / "schemas" / "example.json").write_text(
            '{"changed":true}\n', encoding="utf-8"
        )
        with self.assertRaises(VALIDATOR.ValidationError):
            VALIDATOR.validate_candidate(self.base, self.candidate)

    def test_rejects_stale_content_digest(self) -> None:
        directory = self._add_submission()
        (directory / "content" / "observation.json").write_text(
            '{"observation":"tampered"}\n', encoding="utf-8"
        )
        with self.assertRaises(VALIDATOR.ValidationError):
            VALIDATOR.validate_candidate(self.base, self.candidate)

    def test_rejects_absolute_path(self) -> None:
        directory = self._add_submission()
        (directory / "content" / "observation.json").write_text(
            '{"path":"C:\\\\Users\\\\Example\\\\capture.json"}\n',
            encoding="utf-8",
        )
        self._write_manifest(directory, directory.name)
        with self.assertRaises(VALIDATOR.ValidationError):
            VALIDATOR.validate_candidate(self.base, self.candidate)

    def test_rejects_noncanonical_assertion_jsonl(self) -> None:
        directory = self._add_submission()
        manifest = json.loads((directory / "submission.json").read_text(encoding="utf-8"))
        manifest["submissionClass"] = "assertion"
        (directory / "content" / "assertions.jsonl").write_text(
            '{"schema": {"name": "skyrim-render-map.assertion"}}\n',
            encoding="utf-8",
        )
        self._write_manifest(directory, directory.name)
        manifest = json.loads((directory / "submission.json").read_text(encoding="utf-8"))
        manifest["submissionClass"] = "assertion"
        (directory / "submission.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        with self.assertRaises(VALIDATOR.ValidationError):
            VALIDATOR.validate_candidate(self.base, self.candidate)

    def test_rejects_assertion_class_without_ledger(self) -> None:
        directory = self._add_submission()
        manifest = json.loads((directory / "submission.json").read_text(encoding="utf-8"))
        manifest["submissionClass"] = "assertion"
        (directory / "submission.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        with self.assertRaises(VALIDATOR.ValidationError):
            VALIDATOR.validate_candidate(self.base, self.candidate)

    def test_rejects_duplicate_json_keys(self) -> None:
        directory = self._add_submission()
        path = directory / "content" / "observation.json"
        path.write_text('{"value":1,"value":2}\n', encoding="utf-8")
        self._write_manifest(directory, directory.name)
        with self.assertRaises(VALIDATOR.ValidationError):
            VALIDATOR.validate_candidate(self.base, self.candidate)

    def test_rejects_nonfinite_json_numbers(self) -> None:
        directory = self._add_submission()
        path = directory / "content" / "observation.json"
        path.write_text('{"value":NaN}\n', encoding="utf-8")
        self._write_manifest(directory, directory.name)
        with self.assertRaises(VALIDATOR.ValidationError):
            VALIDATOR.validate_candidate(self.base, self.candidate)

    def test_rejects_crlf_jsonl(self) -> None:
        path = self.root / "records.jsonl"
        path.write_bytes(b'{"value":1}\r\n')
        with self.assertRaises(VALIDATOR.ValidationError):
            VALIDATOR.load_jsonl(path)


if __name__ == "__main__":
    unittest.main()
