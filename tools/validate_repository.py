#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Treatid2 and contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Deterministically validate the public render-map submission structure."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import stat
import sys
from dataclasses import dataclass


SUBMISSION_KEYS = {
    "schema",
    "submissionId",
    "submissionClass",
    "namespace",
    "createdAt",
    "status",
    "contributor",
    "provenance",
    "licensing",
    "content",
    "notes",
}
ALLOWED_CLASSES = {
    "legacy-import",
    "observation",
    "assertion",
    "amendment",
    "resolution",
}
ALLOWED_STATUS = {
    "candidate-unreviewed",
    "accepted",
    "contested",
    "superseded",
    "retracted",
}
ALLOWED_CONTENT_SUFFIXES = {".md", ".json", ".jsonl", ".csv"}
SUBMISSION_PATTERN = re.compile(r"^sub-[a-z0-9][a-z0-9.-]{7,127}$")
NAMESPACE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]{1,63}$")
SHA256_PATTERN = re.compile(r"^[A-Fa-f0-9]{64}$")
COMMIT_PATTERN = re.compile(r"^[A-Fa-f0-9]{40}$")
WINDOWS_USER_PATH = re.compile(rb"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s<>]+", re.I)
WINDOWS_ABSOLUTE_PATH = re.compile(rb"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/])")
UNIX_HOME_PATH = re.compile(rb"/home/[^/\s<>]+", re.I)
SECRET_MARKERS = (b"github_pat_", b"ghp_", b"-----BEGIN PRIVATE KEY-----")
MAX_FILES = 256
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024


class ValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class TreeSummary:
    file_count: int
    total_bytes: int
    sha256: str


def _regular_files(root: pathlib.Path) -> list[pathlib.Path]:
    if not root.is_dir():
        raise ValidationError(f"missing directory: {root}")
    result: list[pathlib.Path] = []
    for path in root.rglob("*"):
        relative_parts = path.relative_to(root).parts
        if ".git" in relative_parts or "__pycache__" in relative_parts:
            continue
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise ValidationError(f"symbolic links are not permitted: {path}")
        if path.is_dir():
            continue
        if not stat.S_ISREG(mode):
            raise ValidationError(f"special files are not permitted: {path}")
        result.append(path)
    return sorted(result, key=lambda item: item.relative_to(root).as_posix())


def summarize_tree(root: pathlib.Path) -> TreeSummary:
    digest = hashlib.sha256()
    files = _regular_files(root)
    total = 0
    for path in files:
        data = path.read_bytes()
        relative = path.relative_to(root).as_posix()
        file_digest = hashlib.sha256(data).hexdigest().upper()
        total += len(data)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(data)).encode("ascii"))
        digest.update(b"\0")
        digest.update(file_digest.encode("ascii"))
        digest.update(b"\n")
    return TreeSummary(len(files), total, digest.hexdigest().upper())


def _require_keys(value: dict, expected: set[str], context: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValidationError(
            f"{context} fields differ; missing={missing}, unexpected={extra}"
        )


def _parse_time(value: object, context: str) -> None:
    if not isinstance(value, str):
        raise ValidationError(f"{context} must be an ISO-8601 string")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValidationError(f"invalid {context}: {value}") from error
    if parsed.tzinfo is None:
        raise ValidationError(f"{context} must include a timezone")


def _scan_public_content(path: pathlib.Path, data: bytes) -> None:
    if path.suffix.lower() not in ALLOWED_CONTENT_SUFFIXES:
        raise ValidationError(f"content type is not allowlisted: {path}")
    if len(data) > MAX_FILE_BYTES:
        raise ValidationError(f"content file exceeds {MAX_FILE_BYTES} bytes: {path}")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValidationError(f"content is not UTF-8: {path}") from error
    if WINDOWS_USER_PATH.search(data) or UNIX_HOME_PATH.search(data):
        raise ValidationError(f"personal home path detected: {path}")
    if WINDOWS_ABSOLUTE_PATH.search(data):
        raise ValidationError(f"absolute Windows path detected: {path}")
    if any(marker.lower() in data.lower() for marker in SECRET_MARKERS):
        raise ValidationError(f"credential-like material detected: {path}")


def validate_submission(directory: pathlib.Path) -> TreeSummary:
    manifest_path = directory / "submission.json"
    content_root = directory / "content"
    if not manifest_path.is_file():
        raise ValidationError(f"missing submission.json: {directory}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"invalid submission manifest: {manifest_path}") from error
    if not isinstance(manifest, dict):
        raise ValidationError(f"submission manifest must be an object: {manifest_path}")
    _require_keys(manifest, SUBMISSION_KEYS, "submission")

    schema = manifest["schema"]
    if schema != {"name": "skyrim-render-map.submission", "major": 1, "minor": 0}:
        raise ValidationError(f"unsupported submission schema: {schema!r}")
    submission_id = manifest["submissionId"]
    if not isinstance(submission_id, str) or not SUBMISSION_PATTERN.fullmatch(submission_id):
        raise ValidationError(f"invalid submissionId: {submission_id!r}")
    if directory.name != submission_id:
        raise ValidationError("submissionId must match its directory name")
    if manifest["submissionClass"] not in ALLOWED_CLASSES:
        raise ValidationError("unsupported submissionClass")
    namespace = manifest["namespace"]
    if not isinstance(namespace, str) or not NAMESPACE_PATTERN.fullmatch(namespace):
        raise ValidationError("invalid namespace")
    _parse_time(manifest["createdAt"], "createdAt")
    if manifest["status"] not in ALLOWED_STATUS:
        raise ValidationError("unsupported submission status")

    contributor = manifest["contributor"]
    if not isinstance(contributor, dict):
        raise ValidationError("contributor must be an object")
    _require_keys(contributor, {"displayName", "github", "standing"}, "contributor")
    if contributor["standing"] != "ordinary-contributor":
        raise ValidationError("all contributors have ordinary-contributor standing")

    provenance = manifest["provenance"]
    if not isinstance(provenance, dict):
        raise ValidationError("provenance must be an object")
    provenance_keys = {
        "sourceRepository",
        "sourceCommit",
        "sourceParentCommit",
        "sourceRef",
        "sourceState",
        "sourcePubliclyReachable",
        "sourceDirty",
        "importedAt",
        "sourceContentTreeSha256",
        "transformations",
        "relatedUrls",
    }
    _require_keys(provenance, provenance_keys, "provenance")
    if not COMMIT_PATTERN.fullmatch(provenance["sourceCommit"]):
        raise ValidationError("invalid sourceCommit")
    parent = provenance["sourceParentCommit"]
    if parent is not None and not COMMIT_PATTERN.fullmatch(parent):
        raise ValidationError("invalid sourceParentCommit")
    if not SHA256_PATTERN.fullmatch(provenance["sourceContentTreeSha256"]):
        raise ValidationError("invalid sourceContentTreeSha256")
    _parse_time(provenance["importedAt"], "provenance.importedAt")
    if not isinstance(provenance["transformations"], list):
        raise ValidationError("provenance.transformations must be an array")
    if not isinstance(provenance["relatedUrls"], list):
        raise ValidationError("provenance.relatedUrls must be an array")

    licensing = manifest["licensing"]
    expected_licensing = {
        "content": "CC-BY-SA-4.0",
        "schemas": "CC0-1.0",
        "dcoAcknowledged": True,
    }
    if licensing != expected_licensing:
        raise ValidationError("licensing declaration is incomplete")

    files = _regular_files(content_root)
    if not files:
        raise ValidationError("content directory must not be empty")
    if len(files) > MAX_FILES:
        raise ValidationError(f"submission exceeds {MAX_FILES} content files")
    for path in files:
        _scan_public_content(path, path.read_bytes())

    summary = summarize_tree(content_root)
    if summary.total_bytes > MAX_TOTAL_BYTES:
        raise ValidationError(f"submission exceeds {MAX_TOTAL_BYTES} total bytes")
    content = manifest["content"]
    expected_content = {
        "root": "content",
        "fileCount": summary.file_count,
        "totalBytes": summary.total_bytes,
        "treeSha256": summary.sha256,
    }
    if content != expected_content:
        raise ValidationError(
            f"content summary mismatch; expected {expected_content!r}"
        )
    return summary


def submission_directories(repository: pathlib.Path) -> list[pathlib.Path]:
    root = repository / "submissions"
    if not root.is_dir():
        raise ValidationError("missing submissions directory")
    result = []
    for manifest in root.glob("[0-9][0-9][0-9][0-9]/[0-1][0-9]/sub-*/submission.json"):
        result.append(manifest.parent)
    return sorted(result)


def validate_repository(repository: pathlib.Path) -> None:
    seen: set[str] = set()
    directories = submission_directories(repository)
    if not directories:
        raise ValidationError("repository contains no submissions")
    for directory in directories:
        if directory.name in seen:
            raise ValidationError(f"duplicate submission identity: {directory.name}")
        seen.add(directory.name)
        validate_submission(directory)

    for json_path in sorted(repository.rglob("*.json")):
        if ".git" in json_path.parts:
            continue
        try:
            json.loads(json_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValidationError(f"invalid JSON document: {json_path}") from error


def _tree_inventory(root: pathlib.Path) -> dict[str, tuple[int, str]]:
    result: dict[str, tuple[int, str]] = {}
    for path in _regular_files(root):
        relative = path.relative_to(root).as_posix()
        data = path.read_bytes()
        result[relative] = (len(data), hashlib.sha256(data).hexdigest())
    return result


def validate_candidate(base: pathlib.Path, candidate: pathlib.Path) -> str:
    base_files = _tree_inventory(base)
    candidate_files = _tree_inventory(candidate)
    removed = sorted(set(base_files) - set(candidate_files))
    modified = sorted(
        path for path in set(base_files) & set(candidate_files)
        if base_files[path] != candidate_files[path]
    )
    added = sorted(set(candidate_files) - set(base_files))

    submission_changes = [
        path for path in removed + modified if path.startswith("submissions/")
    ]
    if submission_changes:
        raise ValidationError("accepted submissions are immutable")

    new_submission_roots: set[str] = set()
    for path in added:
        parts = pathlib.PurePosixPath(path).parts
        if len(parts) >= 4 and parts[0] == "submissions":
            new_submission_roots.add("/".join(parts[:4]))

    if not new_submission_roots:
        validate_repository(candidate)
        return "Not a data submission; repository structure is valid"
    if len(new_submission_roots) != 1:
        raise ValidationError("a data PR must add exactly one submission directory")
    root = next(iter(new_submission_roots))
    unrelated = [path for path in added + modified + removed if not path.startswith(root + "/")]
    if unrelated:
        raise ValidationError("a data PR must not include unrelated changes")
    if root in {
        "/".join(pathlib.PurePosixPath(path).parts[:4])
        for path in base_files
        if path.startswith("submissions/")
    }:
        raise ValidationError("a data PR must create a new submission directory")
    validate_submission(candidate / pathlib.PurePosixPath(root))
    validate_repository(candidate)
    return "Accepted for map review"


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--repository", type=pathlib.Path)
    mode.add_argument("--tree-digest", type=pathlib.Path)
    mode.add_argument("--base-tree", type=pathlib.Path)
    parser.add_argument("--candidate-tree", type=pathlib.Path)
    args = parser.parse_args()
    try:
        if args.tree_digest is not None:
            print(json.dumps(summarize_tree(args.tree_digest).__dict__, sort_keys=True))
            return 0
        if args.base_tree is not None:
            if args.candidate_tree is None:
                raise ValidationError("--candidate-tree is required with --base-tree")
            message = validate_candidate(args.base_tree.resolve(), args.candidate_tree.resolve())
            print(message)
            return 0
        if args.candidate_tree is not None:
            raise ValidationError("--candidate-tree requires --base-tree")
        validate_repository(args.repository.resolve())
        print("Repository structure is valid")
        return 0
    except ValidationError:
        print(
            "Submission structure rejected. See CONTRIBUTING.md.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
