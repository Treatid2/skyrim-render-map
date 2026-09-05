#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Treatid2 and contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Compile immutable submissions into a deterministic semantic snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from typing import Any

import validate_repository as validator


TOOL_VERSION = "1.1.0"


class CompileError(RuntimeError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_id(prefix: str, value: Any) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest}"


def assertion_ref(submission_id: str, assertion_id: str) -> str:
    return (
        "urn:skyrim-render-map:submission:"
        f"{submission_id}#{assertion_id}"
    )


def resolution_ref(submission_id: str, resolution_id: str) -> str:
    return (
        "urn:skyrim-render-map:submission:"
        f"{submission_id}#{resolution_id}"
    )


def entity_ref(submission_id: str, entity_id: str) -> str:
    return (
        "urn:skyrim-render-map:submission:"
        f"{submission_id}#{entity_id}"
    )


def normalize_applicability(applicability: dict) -> dict:
    engine = applicability["engine"]
    extension = applicability["extension"]

    def lower(value: str | None) -> str | None:
        return value.lower() if value is not None else None

    return {
        "engine": {
            "runtime": engine["runtime"],
            "executableSha256": lower(engine["executableSha256"]),
            "moduleSha256": lower(engine["moduleSha256"]),
        },
        "extension": {
            "namespace": extension["namespace"],
            "sourceCommit": lower(extension["sourceCommit"]),
            "buildId": extension["buildId"],
            "artifactSha256": lower(extension["artifactSha256"]),
        },
        "configurationSha256": lower(applicability["configurationSha256"]),
        "scenarioSha256": lower(applicability["scenarioSha256"]),
    }


def assertion_key(record: dict) -> str:
    return content_id(
        "assertion-key",
        {
            "subject": record["subject"],
            "predicate": record["predicate"],
            "applicability": normalize_applicability(record["applicability"]),
        },
    )


def topic_key(record: dict) -> str:
    return content_id(
        "topic-key",
        {"subject": record["subject"], "predicate": record["predicate"]},
    )


def _intersect_values(left: Any, right: Any) -> tuple[bool, Any]:
    if isinstance(left, dict) and isinstance(right, dict):
        result: dict[str, Any] = {}
        for key in sorted(left):
            overlaps, value = _intersect_values(left[key], right[key])
            if not overlaps:
                return False, None
            result[key] = value
        return True, result
    if left is None:
        return True, right
    if right is None:
        return True, left
    if left == right:
        return True, left
    return False, None


def applicability_intersection(left: dict, right: dict) -> dict | None:
    overlaps, intersection = _intersect_values(left, right)
    return intersection if overlaps else None


def _load_ledger(
    repository: pathlib.Path,
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    submissions: list[dict] = []
    entities: list[dict] = []
    assertions: list[dict] = []
    resolutions: list[dict] = []
    for directory in validator.submission_directories(repository):
        manifest = validator.load_json_document(directory / "submission.json")
        if not isinstance(manifest, dict):
            raise CompileError(f"submission manifest is not an object: {directory}")
        submission_id = manifest["submissionId"]
        entity_records, assertion_records, resolution_records = (
            validator.load_submission_records(
                directory, manifest["submissionClass"]
            )
        )
        submissions.append(
            {
                "submissionId": submission_id,
                "submissionClass": manifest["submissionClass"],
                "namespace": manifest["namespace"],
                "status": manifest["status"],
                "createdAt": manifest["createdAt"],
                "sourceRepository": manifest["provenance"]["sourceRepository"],
                "sourceCommit": manifest["provenance"]["sourceCommit"].lower(),
                "contentTreeSha256": manifest["content"]["treeSha256"].lower(),
                "entityCount": len(entity_records),
                "assertionCount": len(assertion_records),
                "resolutionCount": len(resolution_records),
            }
        )
        for record in entity_records:
            entities.append(
                {
                    "ref": entity_ref(submission_id, record["entityId"]),
                    "submissionId": submission_id,
                    "record": record,
                }
            )
        for record in assertion_records:
            reference = assertion_ref(submission_id, record["assertionId"])
            assertions.append(
                {
                    "ref": reference,
                    "submissionId": submission_id,
                    "assertionKey": assertion_key(record),
                    "topicKey": topic_key(record),
                    "normalizedApplicability": normalize_applicability(
                        record["applicability"]
                    ),
                    "record": record,
                }
            )
        for record in resolution_records:
            resolutions.append(
                {
                    "ref": resolution_ref(submission_id, record["resolutionId"]),
                    "submissionId": submission_id,
                    "record": record,
                }
            )
    return submissions, entities, assertions, resolutions


def _detect_conflicts(assertions: list[dict]) -> list[dict]:
    conflicts: list[dict] = []
    ordered = sorted(assertions, key=lambda item: item["ref"])
    for index, left in enumerate(ordered):
        left_record = left["record"]
        if left_record["conflictPolicy"] != "single-valued":
            continue
        for right in ordered[index + 1 :]:
            right_record = right["record"]
            if right_record["conflictPolicy"] != "single-valued":
                continue
            if left["topicKey"] != right["topicKey"]:
                continue
            if canonical_json(left_record["value"]) == canonical_json(right_record["value"]):
                continue
            intersection = applicability_intersection(
                left["normalizedApplicability"],
                right["normalizedApplicability"],
            )
            if intersection is None:
                continue
            participants = sorted([left["ref"], right["ref"]])
            identity = {
                "kind": "incompatible-value",
                "topicKey": left["topicKey"],
                "participants": participants,
                "applicabilityIntersection": intersection,
            }
            conflicts.append(
                {
                    "conflictId": content_id("conflict", identity),
                    "kind": identity["kind"],
                    "topicKey": identity["topicKey"],
                    "assertionKeys": sorted(
                        [left["assertionKey"], right["assertionKey"]]
                    ),
                    "participants": participants,
                    "applicabilityIntersection": intersection,
                    "state": "open",
                    "resolutionRefs": [],
                }
            )
    return sorted(conflicts, key=lambda item: item["conflictId"])


def _apply_resolutions(
    assertions: list[dict], conflicts: list[dict], resolutions: list[dict]
) -> None:
    assertion_refs = {item["ref"] for item in assertions}
    conflicts_by_id = {item["conflictId"]: item for item in conflicts}
    for resolution in sorted(resolutions, key=lambda item: item["ref"]):
        record = resolution["record"]
        conflict = conflicts_by_id.get(record["conflictId"])
        if conflict is None:
            raise CompileError(
                f"resolution {resolution['ref']} references an unknown conflict"
            )
        participants = sorted(record["participantRefs"])
        if participants != conflict["participants"]:
            raise CompileError(
                f"resolution {resolution['ref']} participant set does not match conflict"
            )
        effective = set(record["effectiveAssertionRefs"])
        if not effective.issubset(assertion_refs) or not effective.issubset(participants):
            raise CompileError(
                f"resolution {resolution['ref']} has invalid effective assertions"
            )
        conflict["resolutionRefs"].append(resolution["ref"])
        if record["outcome"] != "unresolved":
            conflict["state"] = "resolved"


def compile_repository(repository: pathlib.Path, source_revision: str | None = None) -> dict:
    validator.validate_repository(repository)
    submissions, entities, assertions, resolutions = _load_ledger(repository)
    refs = (
        [item["ref"] for item in entities]
        + [item["ref"] for item in assertions]
        + [item["ref"] for item in resolutions]
    )
    if len(refs) != len(set(refs)):
        raise CompileError("ledger record references must be globally unique")
    entity_refs = {item["ref"] for item in entities}
    for assertion in assertions:
        if assertion["record"]["subject"] not in entity_refs:
            raise CompileError(
                f"assertion {assertion['ref']} references an unknown subject"
            )

    conflicts = _detect_conflicts(assertions)
    _apply_resolutions(assertions, conflicts, resolutions)
    conflict_refs_by_assertion: dict[str, list[str]] = {
        item["ref"]: [] for item in assertions
    }
    for conflict in conflicts:
        for reference in conflict["participants"]:
            conflict_refs_by_assertion[reference].append(conflict["conflictId"])

    compiled_assertions = []
    for assertion in sorted(assertions, key=lambda item: item["ref"]):
        conflict_refs = sorted(conflict_refs_by_assertion[assertion["ref"]])
        relevant = [
            conflict for conflict in conflicts if conflict["conflictId"] in conflict_refs
        ]
        if any(conflict["state"] == "open" for conflict in relevant):
            state = "contested"
        elif relevant:
            state = "resolved-contest"
        else:
            state = "supported"
        compiled_assertions.append(
            {
                **assertion,
                "state": state,
                "conflictRefs": conflict_refs,
            }
        )

    compiled_resolutions = sorted(resolutions, key=lambda item: item["ref"])
    body = {
        "schema": {
            "name": "skyrim-render-map.dataset-snapshot",
            "major": 1,
            "minor": 1,
        },
        "generatedBy": {
            "name": "skyrim-render-map.compile-dataset",
            "version": TOOL_VERSION,
        },
        "sourceRevision": source_revision,
        "submissions": sorted(submissions, key=lambda item: item["submissionId"]),
        "entities": sorted(entities, key=lambda item: item["ref"]),
        "assertions": compiled_assertions,
        "conflicts": conflicts,
        "resolutions": compiled_resolutions,
        "statistics": {
            "submissionCount": len(submissions),
            "entityCount": len(entities),
            "assertionCount": len(assertions),
            "conflictCount": len(conflicts),
            "openConflictCount": sum(item["state"] == "open" for item in conflicts),
            "resolutionCount": len(resolutions),
        },
    }
    return {"snapshotId": content_id("snapshot", body), **body}


def write_snapshot(snapshot: dict, output: pathlib.Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--source-revision")
    args = parser.parse_args()
    try:
        snapshot = compile_repository(
            args.repository.resolve(), source_revision=args.source_revision
        )
        write_snapshot(snapshot, args.output.resolve())
        print(snapshot["snapshotId"])
        return 0
    except (validator.ValidationError, CompileError) as error:
        print(f"Dataset compilation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
