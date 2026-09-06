#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Treatid2 and contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Deterministically validate the public render-map submission structure."""

from __future__ import annotations

import argparse
import datetime as dt
import decimal
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
RECORD_ID_PATTERN = re.compile(r"^[a-z][a-z0-9.-]{2,127}$")
WINDOWS_USER_PATH = re.compile(rb"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s<>]+", re.I)
WINDOWS_ABSOLUTE_PATH = re.compile(rb"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/])")
UNIX_HOME_PATH = re.compile(rb"/home/[^/\s<>]+", re.I)
SECRET_MARKERS = (b"github_pat_", b"ghp_", b"-----BEGIN PRIVATE KEY-----")
MAX_FILES = 256
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024

ASSERTION_KEYS = {
    "schema",
    "assertionId",
    "subject",
    "predicate",
    "value",
    "conflictPolicy",
    "applicability",
    "evidence",
    "notes",
}
ENTITY_KEYS = {"schema", "entityId", "kind", "label", "sourceRefs", "notes"}
APPLICABILITY_KEYS = {
    "engine",
    "extension",
    "configurationSha256",
    "scenarioSha256",
}
ENGINE_APPLICABILITY_KEYS = {"runtime", "executableSha256", "moduleSha256"}
EXTENSION_APPLICABILITY_KEYS = {
    "namespace",
    "sourceCommit",
    "buildId",
    "artifactSha256",
}
EVIDENCE_KEYS = {"class", "confidence", "refs"}
EVIDENCE_CLASSES = {
    "runtime-capture",
    "static-analysis",
    "reverse-engineering",
    "source-analysis",
    "documentation",
    "correlation",
    "manual-observation",
    "derived",
}
CONFIDENCE_LEVELS = {"high", "medium", "low", "unknown"}
RESOLUTION_KEYS = {
    "schema",
    "resolutionId",
    "conflictId",
    "participantRefs",
    "outcome",
    "effectiveAssertionRefs",
    "evidenceRefs",
    "rationale",
}
RESOLUTION_OUTCOMES = {
    "narrowed-applicability",
    "supersedes",
    "unsupported",
    "aliases",
    "unresolved",
}
PERFORMANCE_KEYS = {
    "schema",
    "observationId",
    "recordedAt",
    "map",
    "runtime",
    "environment",
    "protocol",
    "scenario",
    "treatment",
    "measurement",
    "validity",
    "privacy",
    "notes",
}
PERFORMANCE_MAP_KEYS = {"mapSnapshotId", "nodeRefs"}
PERFORMANCE_RUNTIME_KEYS = {"engine", "extensions", "runtimeRoute"}
PERFORMANCE_ENVIRONMENT_KEYS = {
    "installationId",
    "cpuModel",
    "gpuModel",
    "gpuDriverVersion",
    "renderContext",
}
PERFORMANCE_PROTOCOL_KEYS = {
    "name",
    "version",
    "artifactSha256",
    "tools",
    "warmupSamples",
    "requestedSamples",
    "sampleIntervalFrames",
}
PERFORMANCE_SCENARIO_KEYS = {
    "label",
    "scenarioSha256",
    "configurationSha256",
    "cacheSha256",
}
PERFORMANCE_TREATMENT_KEYS = {
    "label",
    "treatmentSha256",
    "baselineObservationRef",
}
PERFORMANCE_MEASUREMENT_KEYS = {"metric", "unit", "scope", "scopeRefs", "samples"}
PERFORMANCE_VALIDITY_KEYS = {"state", "contamination", "notes"}
PERFORMANCE_PRIVACY_KEYS = {
    "publicationOptIn",
    "fieldsPreviewed",
    "installationIdRandom",
    "installationIdResettable",
}
PERFORMANCE_RENDER_CONTEXT_KEYS = {
    "renderWidth",
    "renderHeight",
    "viewCount",
    "refreshRateHz",
    "renderScale",
    "frameLimiter",
    "targetFrameRate",
    "reprojectionMode",
}
PERFORMANCE_SAMPLE_KEYS = {"sequence", "value", "frame", "timestampOffsetMs"}
PERFORMANCE_CONTAMINATION_KEYS = {"kind", "firstSample", "lastSample", "notes"}
PERFORMANCE_TOOL_KEYS = {"name", "version", "artifactSha256"}
PERFORMANCE_UNITS = {
    "milliseconds",
    "microseconds",
    "frames-per-second",
    "percent",
    "count",
}
PERFORMANCE_SCOPES = {"whole-frame", "map-node", "map-node-set", "process", "other"}
PERFORMANCE_VALIDITY_STATES = {"valid", "contaminated", "inconclusive"}
PERFORMANCE_CONTAMINATION_KINDS = {
    "background-activity",
    "capture-overhead",
    "driver-reset",
    "focus-loss",
    "frame-limiter",
    "loading-transition",
    "reprojection",
    "shader-compilation",
    "thermal-throttling",
    "unknown",
}
INSTALLATION_ID_PATTERN = re.compile(r"^inst-[a-f0-9]{32}$")
MAP_SNAPSHOT_ID_PATTERN = re.compile(r"^map-snapshot-[a-f0-9]{64}$")
DECIMAL_PATTERN = re.compile(r"^(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,9})?$")


class ValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class TreeSummary:
    file_count: int
    total_bytes: int
    sha256: str


def _reject_json_constant(value: str) -> None:
    raise ValidationError(f"non-finite JSON number is not permitted: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def parse_json(text: str, context: str) -> object:
    try:
        value = json.loads(
            text,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return value
    except (json.JSONDecodeError, UnicodeEncodeError, ValueError) as error:
        raise ValidationError(f"invalid JSON document: {context}") from error


def load_json_document(path: pathlib.Path) -> object:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValidationError(f"JSON is not UTF-8: {path}") from error
    return parse_json(text, str(path))


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


def _require_optional_string(value: object, context: str) -> None:
    if value is not None and (not isinstance(value, str) or not value):
        raise ValidationError(f"{context} must be null or a non-empty string")


def _require_optional_digest(value: object, pattern: re.Pattern[str], context: str) -> None:
    if value is not None and (not isinstance(value, str) or not pattern.fullmatch(value)):
        raise ValidationError(f"{context} must be null or a valid digest")


def _require_unique_strings(value: object, context: str, *, minimum: int = 0) -> None:
    if not isinstance(value, list) or len(value) < minimum:
        raise ValidationError(f"{context} must be an array with at least {minimum} item(s)")
    if any(not isinstance(item, str) or not item for item in value):
        raise ValidationError(f"{context} must contain non-empty strings")
    if len(set(value)) != len(value):
        raise ValidationError(f"{context} must not contain duplicates")


def load_jsonl(path: pathlib.Path) -> list[dict]:
    """Load canonical JSON objects from a UTF-8 JSONL ledger file."""
    try:
        data = path.read_bytes()
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValidationError(f"JSONL is not UTF-8: {path}") from error
    if b"\r" in data:
        raise ValidationError(f"JSONL must use LF line endings: {path}")
    if not text or not text.endswith("\n"):
        raise ValidationError(f"JSONL must be non-empty and end with a newline: {path}")
    records: list[dict] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line:
            raise ValidationError(f"blank JSONL line at {path}:{line_number}")
        value = parse_json(line, f"{path}:{line_number}")
        if not isinstance(value, dict):
            raise ValidationError(f"JSONL record must be an object at {path}:{line_number}")
        canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if line != canonical:
            raise ValidationError(f"JSONL record is not canonical at {path}:{line_number}")
        records.append(value)
    return records


def validate_assertion(record: dict, context: str) -> None:
    _require_keys(record, ASSERTION_KEYS, context)
    if record["schema"] != {
        "name": "skyrim-render-map.assertion",
        "major": 1,
        "minor": 0,
    }:
        raise ValidationError(f"unsupported assertion schema at {context}")
    assertion_id = record["assertionId"]
    if not isinstance(assertion_id, str) or not RECORD_ID_PATTERN.fullmatch(assertion_id):
        raise ValidationError(f"invalid assertionId at {context}")
    for field in ("subject", "predicate"):
        if not isinstance(record[field], str) or not record[field]:
            raise ValidationError(f"{context}.{field} must be a non-empty string")
    if record["conflictPolicy"] not in {"single-valued", "multi-valued"}:
        raise ValidationError(f"invalid conflictPolicy at {context}")

    applicability = record["applicability"]
    if not isinstance(applicability, dict):
        raise ValidationError(f"{context}.applicability must be an object")
    _require_keys(applicability, APPLICABILITY_KEYS, f"{context}.applicability")
    engine = applicability["engine"]
    extension = applicability["extension"]
    if not isinstance(engine, dict) or not isinstance(extension, dict):
        raise ValidationError(f"{context}.applicability identities must be objects")
    _require_keys(engine, ENGINE_APPLICABILITY_KEYS, f"{context}.applicability.engine")
    _require_keys(
        extension,
        EXTENSION_APPLICABILITY_KEYS,
        f"{context}.applicability.extension",
    )
    _require_optional_string(engine["runtime"], f"{context}.applicability.engine.runtime")
    _require_optional_digest(
        engine["executableSha256"], SHA256_PATTERN,
        f"{context}.applicability.engine.executableSha256",
    )
    _require_optional_digest(
        engine["moduleSha256"], SHA256_PATTERN,
        f"{context}.applicability.engine.moduleSha256",
    )
    _require_optional_string(
        extension["namespace"], f"{context}.applicability.extension.namespace"
    )
    if extension["namespace"] is not None and not NAMESPACE_PATTERN.fullmatch(
        extension["namespace"]
    ):
        raise ValidationError(f"invalid extension namespace at {context}")
    _require_optional_digest(
        extension["sourceCommit"], COMMIT_PATTERN,
        f"{context}.applicability.extension.sourceCommit",
    )
    _require_optional_string(
        extension["buildId"], f"{context}.applicability.extension.buildId"
    )
    _require_optional_digest(
        extension["artifactSha256"], SHA256_PATTERN,
        f"{context}.applicability.extension.artifactSha256",
    )
    for field in ("configurationSha256", "scenarioSha256"):
        _require_optional_digest(
            applicability[field], SHA256_PATTERN, f"{context}.applicability.{field}"
        )

    evidence = record["evidence"]
    if not isinstance(evidence, dict):
        raise ValidationError(f"{context}.evidence must be an object")
    _require_keys(evidence, EVIDENCE_KEYS, f"{context}.evidence")
    if evidence["class"] not in EVIDENCE_CLASSES:
        raise ValidationError(f"invalid evidence class at {context}")
    if evidence["confidence"] not in CONFIDENCE_LEVELS:
        raise ValidationError(f"invalid confidence at {context}")
    _require_unique_strings(evidence["refs"], f"{context}.evidence.refs", minimum=1)
    if not isinstance(record["notes"], str):
        raise ValidationError(f"{context}.notes must be a string")


def validate_entity(record: dict, context: str) -> None:
    _require_keys(record, ENTITY_KEYS, context)
    if record["schema"] != {
        "name": "skyrim-render-map.entity",
        "major": 1,
        "minor": 0,
    }:
        raise ValidationError(f"unsupported entity schema at {context}")
    entity_id = record["entityId"]
    if not isinstance(entity_id, str) or not RECORD_ID_PATTERN.fullmatch(entity_id):
        raise ValidationError(f"invalid entityId at {context}")
    if not isinstance(record["kind"], str) or not NAMESPACE_PATTERN.fullmatch(
        record["kind"]
    ):
        raise ValidationError(f"invalid entity kind at {context}")
    if not isinstance(record["label"], str) or not record["label"]:
        raise ValidationError(f"{context}.label must be a non-empty string")
    _require_unique_strings(record["sourceRefs"], f"{context}.sourceRefs", minimum=1)
    if not isinstance(record["notes"], str):
        raise ValidationError(f"{context}.notes must be a string")


def validate_resolution(record: dict, context: str) -> None:
    _require_keys(record, RESOLUTION_KEYS, context)
    if record["schema"] != {
        "name": "skyrim-render-map.resolution",
        "major": 1,
        "minor": 0,
    }:
        raise ValidationError(f"unsupported resolution schema at {context}")
    resolution_id = record["resolutionId"]
    if not isinstance(resolution_id, str) or not RECORD_ID_PATTERN.fullmatch(resolution_id):
        raise ValidationError(f"invalid resolutionId at {context}")
    conflict_id = record["conflictId"]
    if not isinstance(conflict_id, str) or not re.fullmatch(r"conflict-[a-f0-9]{64}", conflict_id):
        raise ValidationError(f"invalid conflictId at {context}")
    _require_unique_strings(record["participantRefs"], f"{context}.participantRefs", minimum=2)
    if record["outcome"] not in RESOLUTION_OUTCOMES:
        raise ValidationError(f"invalid resolution outcome at {context}")
    _require_unique_strings(record["effectiveAssertionRefs"], f"{context}.effectiveAssertionRefs")
    _require_unique_strings(record["evidenceRefs"], f"{context}.evidenceRefs", minimum=1)
    if not isinstance(record["rationale"], str) or not record["rationale"]:
        raise ValidationError(f"{context}.rationale must be a non-empty string")


def _require_nonempty_string(value: object, context: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{context} must be a non-empty string")


def _require_nonnegative_integer(value: object, context: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValidationError(f"{context} must be a non-negative integer")


def _require_canonical_decimal(value: object, context: str) -> None:
    if not isinstance(value, str) or not DECIMAL_PATTERN.fullmatch(value):
        raise ValidationError(f"{context} must be a canonical non-negative decimal string")
    try:
        parsed = decimal.Decimal(value)
    except decimal.InvalidOperation as error:
        raise ValidationError(f"invalid decimal at {context}") from error
    if not parsed.is_finite() or parsed < 0:
        raise ValidationError(f"invalid decimal at {context}")


def _validate_performance_identity(record: dict, context: str) -> None:
    map_identity = record["map"]
    if not isinstance(map_identity, dict):
        raise ValidationError(f"{context}.map must be an object")
    _require_keys(map_identity, PERFORMANCE_MAP_KEYS, f"{context}.map")
    if not isinstance(
        map_identity["mapSnapshotId"], str
    ) or not MAP_SNAPSHOT_ID_PATTERN.fullmatch(
        map_identity["mapSnapshotId"]
    ):
        raise ValidationError(f"invalid mapSnapshotId at {context}")
    _require_unique_strings(map_identity["nodeRefs"], f"{context}.map.nodeRefs", minimum=1)

    runtime = record["runtime"]
    if not isinstance(runtime, dict):
        raise ValidationError(f"{context}.runtime must be an object")
    _require_keys(runtime, PERFORMANCE_RUNTIME_KEYS, f"{context}.runtime")
    engine = runtime["engine"]
    if not isinstance(engine, dict):
        raise ValidationError(f"{context}.runtime.engine must be an object")
    _require_keys(engine, ENGINE_APPLICABILITY_KEYS, f"{context}.runtime.engine")
    _require_nonempty_string(engine["runtime"], f"{context}.runtime.engine.runtime")
    _require_optional_digest(
        engine["executableSha256"], SHA256_PATTERN,
        f"{context}.runtime.engine.executableSha256",
    )
    if engine["executableSha256"] is None:
        raise ValidationError(f"{context}.runtime.engine.executableSha256 is required")
    _require_optional_digest(
        engine["moduleSha256"], SHA256_PATTERN,
        f"{context}.runtime.engine.moduleSha256",
    )
    _require_nonempty_string(runtime["runtimeRoute"], f"{context}.runtime.runtimeRoute")
    extensions = runtime["extensions"]
    if not isinstance(extensions, list):
        raise ValidationError(f"{context}.runtime.extensions must be an array")
    extension_names: set[str] = set()
    for index, extension in enumerate(extensions):
        item_context = f"{context}.runtime.extensions[{index}]"
        if not isinstance(extension, dict):
            raise ValidationError(f"{item_context} must be an object")
        _require_keys(extension, EXTENSION_APPLICABILITY_KEYS, item_context)
        namespace = extension["namespace"]
        if not isinstance(namespace, str) or not NAMESPACE_PATTERN.fullmatch(namespace):
            raise ValidationError(f"invalid extension namespace at {item_context}")
        if namespace in extension_names:
            raise ValidationError(f"duplicate extension namespace at {context}")
        extension_names.add(namespace)
        _require_optional_digest(
            extension["sourceCommit"], COMMIT_PATTERN,
            f"{item_context}.sourceCommit",
        )
        _require_nonempty_string(extension["buildId"], f"{item_context}.buildId")
        _require_optional_digest(
            extension["artifactSha256"], SHA256_PATTERN,
            f"{item_context}.artifactSha256",
        )
        if extension["artifactSha256"] is None:
            raise ValidationError(f"{item_context}.artifactSha256 is required")


def _validate_performance_environment(record: dict, context: str) -> None:
    environment = record["environment"]
    if not isinstance(environment, dict):
        raise ValidationError(f"{context}.environment must be an object")
    _require_keys(environment, PERFORMANCE_ENVIRONMENT_KEYS, f"{context}.environment")
    installation_id = environment["installationId"]
    if not isinstance(installation_id, str) or not INSTALLATION_ID_PATTERN.fullmatch(
        installation_id
    ):
        raise ValidationError(f"invalid installationId at {context}")
    for field in ("cpuModel", "gpuModel", "gpuDriverVersion"):
        _require_nonempty_string(environment[field], f"{context}.environment.{field}")
    render_context = environment["renderContext"]
    if not isinstance(render_context, dict):
        raise ValidationError(f"{context}.environment.renderContext must be an object")
    _require_keys(
        render_context,
        PERFORMANCE_RENDER_CONTEXT_KEYS,
        f"{context}.environment.renderContext",
    )
    for field in ("renderWidth", "renderHeight", "viewCount"):
        _require_nonnegative_integer(
            render_context[field], f"{context}.environment.renderContext.{field}"
        )
        if render_context[field] == 0:
            raise ValidationError(
                f"{context}.environment.renderContext.{field} must be positive"
            )
    for field in ("refreshRateHz", "renderScale"):
        _require_canonical_decimal(
            render_context[field], f"{context}.environment.renderContext.{field}"
        )
    for field in ("frameLimiter", "reprojectionMode"):
        _require_nonempty_string(
            render_context[field], f"{context}.environment.renderContext.{field}"
        )
    if render_context["targetFrameRate"] is not None:
        _require_canonical_decimal(
            render_context["targetFrameRate"],
            f"{context}.environment.renderContext.targetFrameRate",
        )


def _validate_performance_protocol(record: dict, context: str) -> None:
    protocol = record["protocol"]
    if not isinstance(protocol, dict):
        raise ValidationError(f"{context}.protocol must be an object")
    _require_keys(protocol, PERFORMANCE_PROTOCOL_KEYS, f"{context}.protocol")
    for field in ("name", "version"):
        _require_nonempty_string(protocol[field], f"{context}.protocol.{field}")
    _require_optional_digest(
        protocol["artifactSha256"], SHA256_PATTERN,
        f"{context}.protocol.artifactSha256",
    )
    if protocol["artifactSha256"] is None:
        raise ValidationError(f"{context}.protocol.artifactSha256 is required")
    for field in ("warmupSamples", "requestedSamples", "sampleIntervalFrames"):
        _require_nonnegative_integer(protocol[field], f"{context}.protocol.{field}")
    if protocol["requestedSamples"] == 0 or protocol["sampleIntervalFrames"] == 0:
        raise ValidationError(f"{context}.protocol sample counts must be positive")
    tools = protocol["tools"]
    if not isinstance(tools, list) or not tools:
        raise ValidationError(f"{context}.protocol.tools must be a non-empty array")
    tool_names: set[str] = set()
    for index, tool in enumerate(tools):
        item_context = f"{context}.protocol.tools[{index}]"
        if not isinstance(tool, dict):
            raise ValidationError(f"{item_context} must be an object")
        _require_keys(tool, PERFORMANCE_TOOL_KEYS, item_context)
        for field in ("name", "version"):
            _require_nonempty_string(tool[field], f"{item_context}.{field}")
        if tool["name"] in tool_names:
            raise ValidationError(f"duplicate protocol tool name at {context}")
        tool_names.add(tool["name"])
        _require_optional_digest(
            tool["artifactSha256"], SHA256_PATTERN,
            f"{item_context}.artifactSha256",
        )
        if tool["artifactSha256"] is None:
            raise ValidationError(f"{item_context}.artifactSha256 is required")


def _validate_performance_measurement(record: dict, context: str) -> None:
    measurement = record["measurement"]
    if not isinstance(measurement, dict):
        raise ValidationError(f"{context}.measurement must be an object")
    _require_keys(measurement, PERFORMANCE_MEASUREMENT_KEYS, f"{context}.measurement")
    _require_nonempty_string(measurement["metric"], f"{context}.measurement.metric")
    if measurement["unit"] not in PERFORMANCE_UNITS:
        raise ValidationError(f"invalid performance unit at {context}")
    if measurement["scope"] not in PERFORMANCE_SCOPES:
        raise ValidationError(f"invalid performance scope at {context}")
    _require_unique_strings(
        measurement["scopeRefs"], f"{context}.measurement.scopeRefs",
        minimum=1 if measurement["scope"] in {"map-node", "map-node-set"} else 0,
    )
    if measurement["scope"] in {"map-node", "map-node-set"} and not set(
        measurement["scopeRefs"]
    ).issubset(record["map"]["nodeRefs"]):
        raise ValidationError(
            f"map-node scopeRefs must also appear in map.nodeRefs at {context}"
        )
    samples = measurement["samples"]
    if not isinstance(samples, list) or not samples:
        raise ValidationError(f"{context}.measurement.samples must be a non-empty array")
    if len(samples) > record["protocol"]["requestedSamples"]:
        raise ValidationError(f"retained samples exceed requestedSamples at {context}")
    for index, sample in enumerate(samples):
        item_context = f"{context}.measurement.samples[{index}]"
        if not isinstance(sample, dict):
            raise ValidationError(f"{item_context} must be an object")
        _require_keys(sample, PERFORMANCE_SAMPLE_KEYS, item_context)
        if sample["sequence"] != index:
            raise ValidationError(f"sample sequence must be contiguous at {item_context}")
        _require_canonical_decimal(sample["value"], f"{item_context}.value")
        if sample["frame"] is not None:
            _require_nonnegative_integer(sample["frame"], f"{item_context}.frame")
        if sample["timestampOffsetMs"] is not None:
            _require_canonical_decimal(
                sample["timestampOffsetMs"], f"{item_context}.timestampOffsetMs"
            )


def _validate_performance_validity(record: dict, context: str) -> None:
    validity = record["validity"]
    if not isinstance(validity, dict):
        raise ValidationError(f"{context}.validity must be an object")
    _require_keys(validity, PERFORMANCE_VALIDITY_KEYS, f"{context}.validity")
    if validity["state"] not in PERFORMANCE_VALIDITY_STATES:
        raise ValidationError(f"invalid validity state at {context}")
    if not isinstance(validity["notes"], str):
        raise ValidationError(f"{context}.validity.notes must be a string")
    contamination = validity["contamination"]
    if not isinstance(contamination, list):
        raise ValidationError(f"{context}.validity.contamination must be an array")
    if validity["state"] == "valid" and contamination:
        raise ValidationError(f"valid performance observations cannot declare contamination")
    if validity["state"] != "valid" and not validity["notes"].strip():
        raise ValidationError(f"non-valid performance observations require validity notes")
    sample_count = len(record["measurement"]["samples"])
    for index, item in enumerate(contamination):
        item_context = f"{context}.validity.contamination[{index}]"
        if not isinstance(item, dict):
            raise ValidationError(f"{item_context} must be an object")
        _require_keys(item, PERFORMANCE_CONTAMINATION_KEYS, item_context)
        if item["kind"] not in PERFORMANCE_CONTAMINATION_KINDS:
            raise ValidationError(f"invalid contamination kind at {item_context}")
        for field in ("firstSample", "lastSample"):
            _require_nonnegative_integer(item[field], f"{item_context}.{field}")
        if item["firstSample"] > item["lastSample"] or item["lastSample"] >= sample_count:
            raise ValidationError(f"invalid contamination sample range at {item_context}")
        _require_nonempty_string(item["notes"], f"{item_context}.notes")


def validate_performance_observation(record: dict, context: str) -> None:
    if not isinstance(record, dict):
        raise ValidationError(f"{context} must be an object")
    _require_keys(record, PERFORMANCE_KEYS, context)
    if record["schema"] != {
        "name": "skyrim-render-map.performance-observation",
        "major": 1,
        "minor": 0,
    }:
        raise ValidationError(f"unsupported performance observation schema at {context}")
    observation_id = record["observationId"]
    if not isinstance(observation_id, str) or not RECORD_ID_PATTERN.fullmatch(observation_id):
        raise ValidationError(f"invalid observationId at {context}")
    _parse_time(record["recordedAt"], f"{context}.recordedAt")
    _validate_performance_identity(record, context)
    _validate_performance_environment(record, context)
    _validate_performance_protocol(record, context)

    scenario = record["scenario"]
    if not isinstance(scenario, dict):
        raise ValidationError(f"{context}.scenario must be an object")
    _require_keys(scenario, PERFORMANCE_SCENARIO_KEYS, f"{context}.scenario")
    _require_nonempty_string(scenario["label"], f"{context}.scenario.label")
    for field in ("scenarioSha256", "configurationSha256", "cacheSha256"):
        _require_optional_digest(
            scenario[field], SHA256_PATTERN, f"{context}.scenario.{field}"
        )
        if scenario[field] is None:
            raise ValidationError(f"{context}.scenario.{field} is required")

    treatment = record["treatment"]
    if not isinstance(treatment, dict):
        raise ValidationError(f"{context}.treatment must be an object")
    _require_keys(treatment, PERFORMANCE_TREATMENT_KEYS, f"{context}.treatment")
    _require_nonempty_string(treatment["label"], f"{context}.treatment.label")
    _require_optional_digest(
        treatment["treatmentSha256"], SHA256_PATTERN,
        f"{context}.treatment.treatmentSha256",
    )
    if treatment["treatmentSha256"] is None:
        raise ValidationError(f"{context}.treatment.treatmentSha256 is required")
    if treatment["baselineObservationRef"] is not None:
        _require_nonempty_string(
            treatment["baselineObservationRef"],
            f"{context}.treatment.baselineObservationRef",
        )

    _validate_performance_measurement(record, context)
    _validate_performance_validity(record, context)

    privacy = record["privacy"]
    if not isinstance(privacy, dict):
        raise ValidationError(f"{context}.privacy must be an object")
    _require_keys(privacy, PERFORMANCE_PRIVACY_KEYS, f"{context}.privacy")
    if any(privacy[field] is not True for field in PERFORMANCE_PRIVACY_KEYS):
        raise ValidationError(f"performance privacy declarations must all be true at {context}")
    if not isinstance(record["notes"], str):
        raise ValidationError(f"{context}.notes must be a string")


def load_submission_records(
    directory: pathlib.Path, submission_class: str
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    entities_path = directory / "content" / "entities.jsonl"
    assertions_path = directory / "content" / "assertions.jsonl"
    resolutions_path = directory / "content" / "resolutions.jsonl"
    performance_path = directory / "content" / "performance-observations.jsonl"
    entities = load_jsonl(entities_path) if entities_path.is_file() else []
    assertions = load_jsonl(assertions_path) if assertions_path.is_file() else []
    resolutions = load_jsonl(resolutions_path) if resolutions_path.is_file() else []
    performance = load_jsonl(performance_path) if performance_path.is_file() else []

    if submission_class in {"assertion", "amendment"} and not assertions:
        raise ValidationError(f"{submission_class} submissions require assertions.jsonl")
    if submission_class == "resolution" and not resolutions:
        raise ValidationError("resolution submissions require resolutions.jsonl")
    if assertions and submission_class not in {"legacy-import", "assertion", "amendment"}:
        raise ValidationError("assertions.jsonl is not valid for this submission class")
    if resolutions and submission_class != "resolution":
        raise ValidationError("resolutions.jsonl requires a resolution submission")
    if performance and submission_class != "observation":
        raise ValidationError(
            "performance-observations.jsonl requires an observation submission"
        )
    if performance and entities:
        raise ValidationError(
            "performance observation submissions must not declare structural entities"
        )
    if entities and submission_class == "resolution":
        raise ValidationError("resolution submissions must not declare entities")

    entity_ids: set[str] = set()
    for index, entity in enumerate(entities, start=1):
        validate_entity(entity, f"{entities_path}:{index}")
        if entity["entityId"] in entity_ids:
            raise ValidationError(f"duplicate entityId: {entity['entityId']}")
        entity_ids.add(entity["entityId"])
    assertion_ids: set[str] = set()
    for index, assertion in enumerate(assertions, start=1):
        validate_assertion(assertion, f"{assertions_path}:{index}")
        if assertion["assertionId"] in assertion_ids:
            raise ValidationError(f"duplicate assertionId: {assertion['assertionId']}")
        assertion_ids.add(assertion["assertionId"])
    resolution_ids: set[str] = set()
    for index, resolution in enumerate(resolutions, start=1):
        validate_resolution(resolution, f"{resolutions_path}:{index}")
        if resolution["resolutionId"] in resolution_ids:
            raise ValidationError(f"duplicate resolutionId: {resolution['resolutionId']}")
        resolution_ids.add(resolution["resolutionId"])
    performance_ids: set[str] = set()
    for index, observation in enumerate(performance, start=1):
        validate_performance_observation(observation, f"{performance_path}:{index}")
        if observation["observationId"] in performance_ids:
            raise ValidationError(
                f"duplicate performance observationId: {observation['observationId']}"
            )
        performance_ids.add(observation["observationId"])
    record_ids = (
        list(entity_ids)
        + list(assertion_ids)
        + list(resolution_ids)
        + list(performance_ids)
    )
    if len(record_ids) != len(set(record_ids)):
        raise ValidationError("submission-local record IDs must be unique across record types")
    return entities, assertions, resolutions, performance


def validate_submission(directory: pathlib.Path) -> TreeSummary:
    manifest_path = directory / "submission.json"
    content_root = directory / "content"
    if not manifest_path.is_file():
        raise ValidationError(f"missing submission.json: {directory}")
    manifest = load_json_document(manifest_path)
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

    load_submission_records(directory, manifest["submissionClass"])

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
        load_json_document(json_path)


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
    submission_directory = candidate / pathlib.PurePosixPath(root)
    validate_submission(submission_directory)
    manifest = load_json_document(submission_directory / "submission.json")
    if manifest["status"] != "candidate-unreviewed":
        raise ValidationError(
            "a new data submission must declare candidate-unreviewed status"
        )
    github = manifest["contributor"]["github"]
    if not isinstance(github, str) or not github.strip():
        raise ValidationError(
            "a new public data submission must identify its GitHub contributor"
        )
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
