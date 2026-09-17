# SPDX-FileCopyrightText: 2026 Treatid2 and contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Synthetic engine-scope integration cases; none is a Skyrim finding."""

from __future__ import annotations

import copy
import json
import pathlib
import shutil
import unittest

import test_dataset_compiler as fixtures


COMPILER = fixtures.COMPILER
VALIDATOR = fixtures.VALIDATOR
DOMAINS = (
    "actors", "input", "camera", "animation", "physics", "ai", "navigation",
    "combat", "magic", "inventory", "scripting", "quests-dialogue", "forms",
    "world-streaming", "persistence", "environment", "audio", "ui",
    "rendering", "infrastructure", "extension-interfaces",
)
SUBMISSION_ID = "sub-fixture-engine"
PREFIX = f"urn:skyrim-render-map:submission:{SUBMISSION_ID}#"
ENTITY_PREFIX = PREFIX + "node-"


class EngineScopeTest(unittest.TestCase):
    def setUp(self) -> None:
        # Reuse the real submission builder, including its content digest.
        self.fixture = fixtures.DatasetCompilerTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.repository = self.fixture.repository

    @staticmethod
    def _write_jsonl(path: pathlib.Path, records: list[dict]) -> None:
        path.write_text(
            "".join(COMPILER.canonical_json(record) + "\n" for record in records),
            encoding="utf-8", newline="\n",
        )

    def _claim(self, domain: str = "actors", value: object = "fixture-state") -> dict:
        record = self.fixture._assertion(f"claim-{domain}", value)
        record["subject"] = ENTITY_PREFIX + domain
        record["predicate"] = "engine.fixture.observed-state"
        record["applicability"]["extension"] = {
            "namespace": None, "sourceCommit": None,
            "buildId": None, "artifactSha256": None,
        }
        record["evidence"] = {
            "class": "runtime-capture", "confidence": "unknown",
            "refs": ["evidence://synthetic-engine-fixture"],
        }
        record["notes"] = (
            "Synthetic contract test, not engine evidence. Extension state is "
            "unspecified; no vanilla or causal claim."
        )
        return record

    def _add_engine(self, records: list[dict] | None = None) -> pathlib.Path:
        directory = self.fixture._directory(SUBMISSION_ID)
        entities = [
            {
                "schema": {"name": "skyrim-render-map.entity", "major": 1, "minor": 0},
                "entityId": f"node-{domain}",
                "kind": f"{domain}.fixture",
                "label": f"Synthetic {domain} subject",
                "sourceRefs": ["evidence://synthetic-engine-fixture"],
                "notes": "Invented test entity, not a Skyrim fact.",
            }
            for domain in DOMAINS
        ]
        self._write_jsonl(directory / "content/entities.jsonl", entities)
        self._write_jsonl(
            directory / "content/assertions.jsonl",
            records if records is not None else [self._claim(d) for d in DOMAINS],
        )
        self.fixture._write_manifest(directory, SUBMISSION_ID, "assertion")
        manifest_path = directory / "submission.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["namespace"] = "engine-fixture"
        manifest["contributor"]["github"] = "synthetic-contributor"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return directory

    def test_every_domain_enters_through_ordinary_data_admission(self) -> None:
        # A coherent synthetic multi-subsystem run still adds one directory.
        candidate = self.repository / "candidate-copy"
        shutil.copytree(self.repository / "submissions", candidate / "submissions")
        original = self.fixture.repository
        self.fixture.repository = candidate
        try:
            self._add_engine()
        finally:
            self.fixture.repository = original
        base = self.repository / "base-copy"
        shutil.copytree(self.repository / "submissions", base / "submissions")
        self.assertEqual(
            VALIDATOR.validate_candidate(base, candidate), "Accepted for map review"
        )
        snapshot = COMPILER.compile_repository(candidate)
        self.assertEqual(len(snapshot["assertions"]), len(DOMAINS))
        self.assertEqual(
            {item["record"]["kind"] for item in snapshot["entities"]
             if item["submissionId"] == SUBMISSION_ID},
            {f"{domain}.fixture" for domain in DOMAINS},
        )

    def test_records_manifest_bytes_and_projected_source_identity_are_preserved(self) -> None:
        records = [self._claim(domain) for domain in DOMAINS]
        directory = self._add_engine(records)
        manifest_path = directory / "submission.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        # Source-tree identity is distinct from the included content digest.
        # This synthetic value tests retention, not external source verification.
        manifest["provenance"]["sourceContentTreeSha256"] = "f" * 64
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        before = {p.relative_to(directory): p.read_bytes()
                  for p in directory.rglob("*") if p.is_file()}
        snapshot = COMPILER.compile_repository(self.repository)
        by_id = {item["record"]["assertionId"]: item for item in snapshot["assertions"]}
        for record in records:
            with self.subTest(domain=record["subject"]):
                compiled = by_id[record["assertionId"]]
                self.assertEqual(compiled["record"], record)
                self.assertEqual(compiled["ref"], PREFIX + record["assertionId"])
                # Existing label means provisional, never independent corroboration.
                self.assertEqual(compiled["state"], "supported")
                self.assertNotIn("renderContext", record)
        manifest = json.loads(before[pathlib.Path("submission.json")])
        submission = next(s for s in snapshot["submissions"] if s["submissionId"] == SUBMISSION_ID)
        self.assertEqual(submission["sourceCommit"], manifest["provenance"]["sourceCommit"])
        self.assertEqual(submission["sourceRepository"], manifest["provenance"]["sourceRepository"])
        self.assertEqual(submission["contentTreeSha256"], manifest["content"]["treeSha256"].lower())
        retained_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(retained_manifest["provenance"], manifest["provenance"])
        self.assertEqual(retained_manifest["provenance"]["sourceContentTreeSha256"], "f" * 64)
        self.assertNotEqual(
            retained_manifest["provenance"]["sourceContentTreeSha256"],
            submission["contentTreeSha256"],
        )
        self.assertEqual(before, {p.relative_to(directory): p.read_bytes()
                                  for p in directory.rglob("*") if p.is_file()})

    def test_all_evidence_classes_remain_available_for_non_render_claims(self) -> None:
        records = []
        for evidence_class in sorted(VALIDATOR.EVIDENCE_CLASSES):
            record = self._claim("scripting")
            record["assertionId"] = f"claim-{evidence_class}"
            record["evidence"]["class"] = evidence_class
            records.append(record)
        self._add_engine(records)
        snapshot = COMPILER.compile_repository(self.repository)
        self.assertEqual(
            {item["record"]["evidence"]["class"] for item in snapshot["assertions"]},
            VALIDATOR.EVIDENCE_CLASSES,
        )
        self.assertEqual(snapshot["statistics"]["conflictCount"], 0)
        self.assertEqual(len(snapshot["assertions"]), len(records))

    def test_cross_submission_subject_keeps_its_original_identity(self) -> None:
        self._add_engine()
        record = self._claim("animation", {"target": ENTITY_PREFIX + "physics", "meaning": "synthetic relation"})
        record["assertionId"] = "cross-domain-claim"
        record["predicate"] = "engine.fixture.relation"
        # 'target' is an opaque JSON value; this test only proves subject resolution.
        self.fixture._add_assertions("sub-fixture-cross-domain", [record])
        snapshot = COMPILER.compile_repository(self.repository)
        compiled = next(a for a in snapshot["assertions"]
                        if a["submissionId"] == "sub-fixture-cross-domain")
        self.assertEqual(compiled["record"], record)
        self.assertEqual(compiled["record"]["subject"], ENTITY_PREFIX + "animation")

    def test_unknown_non_render_subject_is_rejected(self) -> None:
        record = self._claim()
        record["subject"] = PREFIX + "undeclared-actor"
        self._add_engine([record])
        with self.assertRaisesRegex(COMPILER.CompileError, "unknown subject"):
            COMPILER.compile_repository(self.repository)

    def test_non_render_claim_cannot_omit_evidence(self) -> None:
        record = self._claim("persistence")
        record["evidence"]["refs"] = []
        self._add_engine([record])
        with self.assertRaisesRegex(VALIDATOR.ValidationError, "evidence.refs"):
            COMPILER.compile_repository(self.repository)

    def test_source_provenance_requires_each_declared_field(self) -> None:
        directory = self._add_engine()
        path = directory / "submission.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for field in manifest["provenance"]:
            with self.subTest(missing_field=field):
                candidate = copy.deepcopy(manifest)
                del candidate["provenance"][field]
                path.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
                with self.assertRaisesRegex(
                    VALIDATOR.ValidationError,
                    rf"provenance fields differ; missing=\['{field}'\]",
                ):
                    COMPILER.compile_repository(self.repository)

    def test_source_commit_and_source_tree_digest_reject_malformed_strings(self) -> None:
        directory = self._add_engine()
        path = directory / "submission.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for field, width in (("sourceCommit", 40), ("sourceContentTreeSha256", 64)):
            for value in ("a" * (width - 1), "a" * (width + 1), "g" * width):
                with self.subTest(field=field, value=value):
                    candidate = copy.deepcopy(manifest)
                    candidate["provenance"][field] = value
                    path.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
                    with self.assertRaisesRegex(VALIDATOR.ValidationError, f"invalid {field}"):
                        COMPILER.compile_repository(self.repository)

    def test_source_format_validation_does_not_authenticate_provenance(self) -> None:
        directory = self._add_engine()
        path = directory / "submission.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["provenance"].update({
            "sourceRepository": "https://example.invalid/unrelated-synthetic-source",
            "sourceCommit": "0" * 40,
            "sourceContentTreeSha256": "0" * 64,
        })
        path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        # Document the current mechanical boundary. These invented identities
        # are prohibited by admission policy, but are syntactically valid.
        snapshot = COMPILER.compile_repository(self.repository)
        submission = next(s for s in snapshot["submissions"] if s["submissionId"] == SUBMISSION_ID)
        self.assertEqual(submission["sourceCommit"], "0" * 40)
        self.assertEqual(submission["sourceRepository"], manifest["provenance"]["sourceRepository"])
        self.assertEqual(submission["status"], "candidate-unreviewed")
        self.assertEqual(
            json.loads(path.read_text(encoding="utf-8"))["provenance"],
            manifest["provenance"],
        )

    def test_tampered_engine_evidence_is_rejected(self) -> None:
        directory = self._add_engine()
        records = [self._claim("actors", "changed-after-sealing")]
        self._write_jsonl(directory / "content/assertions.jsonl", records)
        with self.assertRaisesRegex(VALIDATOR.ValidationError, "content summary mismatch"):
            COMPILER.compile_repository(self.repository)

    def test_each_exact_applicability_dimension_keeps_conflicting_values_separate(self) -> None:
        paths = (
            ("engine", "runtime"), ("engine", "executableSha256"),
            ("engine", "moduleSha256"), ("extension", "namespace"),
            ("extension", "sourceCommit"), ("extension", "buildId"),
            ("extension", "artifactSha256"), ("configurationSha256",),
            ("scenarioSha256",),
        )
        self._add_engine([self._claim("ui")])
        for index, path in enumerate(paths):
            left = self._claim("actors", "first")
            right = copy.deepcopy(left)
            left["assertionId"] = f"left-{index}"
            right["assertionId"] = f"right-{index}"
            left["predicate"] = right["predicate"] = f"engine.fixture.boundary-{index}"
            right["value"] = "second"
            for record, digit in ((left, "a"), (right, "b")):
                target = record["applicability"]
                for part in path[:-1]:
                    target = target[part]
                size = 40 if path[-1] == "sourceCommit" else 64
                target[path[-1]] = digit * size if path[-1].endswith("Sha256") or path[-1] == "sourceCommit" else f"fixture-{digit}"
            self.fixture._add_assertions(f"sub-fixture-boundary-{index}", [left, right])
        snapshot = COMPILER.compile_repository(self.repository)
        self.assertEqual(len(snapshot["assertions"]), 1 + 2 * len(paths))
        self.assertEqual(snapshot["statistics"]["conflictCount"], 0)

    def test_unknown_applicability_does_not_certify_vanilla_or_hide_conflict(self) -> None:
        unknown = self._claim("physics", "first")
        exact = copy.deepcopy(unknown)
        exact["assertionId"] = "physics-extension-claim"
        exact["value"] = "second"
        exact["applicability"]["extension"] = {
            "namespace": "synthetic-plugin", "sourceCommit": "b" * 40,
            "buildId": "fixture-build", "artifactSha256": "b" * 64,
        }
        self._add_engine([unknown, exact])
        snapshot = COMPILER.compile_repository(self.repository)
        self.assertEqual(snapshot["statistics"]["conflictCount"], 1)
        self.assertEqual({a["state"] for a in snapshot["assertions"]}, {"contested"})
        retained = next(a for a in snapshot["assertions"] if a["record"]["assertionId"] == unknown["assertionId"])
        self.assertEqual(retained["record"]["applicability"], unknown["applicability"])

    def test_raw_engine_observation_is_retained_without_inventing_assertions(self) -> None:
        directory = self.fixture._directory("sub-fixture-events")
        self._write_jsonl(directory / "content/events.jsonl", [
            {"fixture": True, "ordinal": 1, "event": "synthetic-actor-update"},
        ])
        self.fixture._write_manifest(directory, directory.name, "observation")
        snapshot = COMPILER.compile_repository(self.repository)
        self.assertEqual(snapshot["statistics"]["assertionCount"], 0)
        self.assertEqual(snapshot["statistics"]["performanceObservationCount"], 0)
        submission = next(s for s in snapshot["submissions"] if s["submissionId"] == directory.name)
        self.assertEqual(submission["contentTreeSha256"], VALIDATOR.summarize_tree(directory / "content").sha256.lower())

    def test_scope_labels_do_not_change_existing_snapshot_identity(self) -> None:
        self._add_engine()
        before = COMPILER.compile_repository(self.repository)
        (self.repository / "README.md").write_text("# Skyrim Engine Map\n", encoding="utf-8")
        schema_dir = self.repository / "schemas"
        schema_dir.mkdir()
        (schema_dir / "scope.json").write_text('{"title":"Engine scope label"}\n', encoding="utf-8")
        after = COMPILER.compile_repository(self.repository)
        self.assertEqual(COMPILER.canonical_json(before), COMPILER.canonical_json(after))
        self.assertEqual(before["mapSnapshotId"], after["mapSnapshotId"])
        first, second = self.repository / "first.json", self.repository / "second.json"
        COMPILER.write_snapshot(before, first)
        COMPILER.write_snapshot(after, second)
        self.assertEqual(first.read_bytes(), second.read_bytes())


if __name__ == "__main__":
    unittest.main()
