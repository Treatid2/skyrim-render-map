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
import urllib.parse
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
    "sampleCadence",
}
PERFORMANCE_CADENCE_KEYS = {"mode", "value"}
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
OPTIMIZATION_KEYS = {
    "schema",
    "experimentId",
    "recordedAt",
    "map",
    "producer",
    "search",
    "axes",
    "objectives",
    "constraints",
    "candidates",
    "notes",
}
OPTIMIZATION_PRODUCER_KEYS = {"name", "version", "artifactSha256"}
OPTIMIZATION_SEARCH_KEYS = {
    "algorithm",
    "algorithmVersion",
    "randomSeedSha256",
    "requestedCandidateCount",
}
OPTIMIZATION_AXIS_KEYS = {
    "axisId",
    "label",
    "mapNodeRef",
    "settingPath",
    "valueType",
    "domain",
}
OPTIMIZATION_OBJECTIVE_KEYS = {
    "objectiveId",
    "label",
    "metric",
    "unit",
    "direction",
    "scope",
    "scopeRefs",
    "reducer",
    "dominanceEpsilon",
}
OPTIMIZATION_CONSTRAINT_KEYS = {
    "constraintId",
    "objectiveId",
    "operator",
    "threshold",
}
OPTIMIZATION_CANDIDATE_KEYS = {
    "candidateId",
    "label",
    "treatmentSha256",
    "outcome",
    "failureKind",
    "parameters",
    "objectiveObservations",
    "notes",
}
OPTIMIZATION_PARAMETER_KEYS = {"axisId", "value"}
OPTIMIZATION_OBJECTIVE_OBSERVATION_KEYS = {"objectiveId", "observationRefs"}
OPTIMIZATION_VALUE_TYPES = {"boolean", "integer", "decimal", "categorical"}
OPTIMIZATION_DIRECTIONS = {"minimize", "maximize"}
OPTIMIZATION_OPERATORS = {"at-most", "at-least"}
OPTIMIZATION_OUTCOMES = {"completed", "failed", "incomplete", "rejected"}
VISUAL_RUBRIC_KEYS = {
    "schema",
    "rubricId",
    "version",
    "label",
    "scope",
    "mapNodeRefs",
    "dimensions",
    "magnitudes",
    "notes",
}
VISUAL_DIMENSION_KEYS = {
    "dimensionId",
    "label",
    "description",
    "kind",
    "notes",
}
VISUAL_MAGNITUDE_KEYS = {
    "magnitudeId",
    "ordinal",
    "label",
    "description",
}
VISUAL_COMPARISON_KEYS = {
    "schema",
    "comparisonId",
    "recordedAt",
    "map",
    "runtime",
    "environment",
    "scenario",
    "rubricRef",
    "stimuli",
    "protocol",
    "trials",
    "validity",
    "privacy",
    "notes",
}
VISUAL_STIMULI_KEYS = {"a", "b"}
VISUAL_STIMULUS_KEYS = {
    "captureSha256",
    "treatmentSha256",
    "sourceObservationRef",
}
VISUAL_PROTOCOL_KEYS = {
    "name",
    "version",
    "artifactSha256",
    "evaluationMode",
    "presentation",
    "randomized",
    "mediaKind",
    "frameCount",
    "frameRateHz",
    "viewCount",
    "preprocessingSha256",
}
VISUAL_TRIAL_KEYS = {
    "trialId",
    "evaluator",
    "presentationOrder",
    "judgments",
    "notes",
}
VISUAL_EVALUATOR_KEYS = {
    "kind",
    "name",
    "version",
    "artifactSha256",
    "promptSha256",
}
VISUAL_JUDGMENT_KEYS = {
    "dimensionId",
    "assessment",
    "differenceMagnitude",
    "confidence",
    "evidence",
    "notes",
}
VISUAL_EVIDENCE_KEYS = {"firstFrame", "lastFrame", "view", "region", "notes"}
VISUAL_REGION_KEYS = {"x", "y", "width", "height"}
VISUAL_RUBRIC_SCOPES = {"common", "shader-family", "feature", "pass", "other"}
VISUAL_DIMENSION_KINDS = {"correctness", "visual-effect", "preference"}
VISUAL_MAGNITUDES = {
    "imperceptible": 0,
    "slight": 1,
    "moderate": 2,
    "large": 3,
    "severe": 4,
}
VISUAL_EVALUATOR_KINDS = {"human", "multimodal-model", "algorithm"}
VISUAL_PRESENTATIONS = {"simultaneous", "sequential"}
VISUAL_MEDIA_KINDS = {"stereo-sequence", "mono-sequence", "still-pair"}
VISUAL_PRESENTATION_ORDERS = {"a-b", "b-a", "simultaneous"}
VISUAL_ASSESSMENTS = {"a-better", "b-better", "equivalent", "inconclusive"}
VISUAL_VIEWS = {"left", "right", "both", "mono", "mirror"}
VISUAL_VALIDITY_KEYS = {"state", "contamination", "notes"}
VISUAL_CONTAMINATION_KEYS = {"kind", "firstTrial", "lastTrial", "notes"}
VISUAL_CONTAMINATION_KINDS = {
    "capture-overhead",
    "driver-reset",
    "evaluator-failure",
    "focus-loss",
    "loading-transition",
    "media-mismatch",
    "presentation-order",
    "shader-compilation",
    "unknown",
}
ARTIFACT_KEYS = {
    "schema",
    "artifactId",
    "artifactSha256",
    "mediaType",
    "contentKind",
    "encoding",
    "byteLength",
    "expandedByteLength",
    "license",
    "retentionClass",
    "locations",
    "notes",
}
ARTIFACT_CONTENT_KINDS = {
    "stereo-sequence",
    "mono-sequence",
    "still-pair",
    "capture-manifest",
    "other",
}
ARTIFACT_ENCODINGS = {"identity", "zip", "zstd"}
ARTIFACT_LICENSES = {"CC-BY-SA-4.0", "CC0-1.0"}
ARTIFACT_RETENTION_CLASSES = {
    "release-asset",
    "oci-artifact",
    "object-storage",
    "repository-inline",
    "external",
}
VISUAL_CAPTURE_KEYS = {
    "schema",
    "captureId",
    "recordedAt",
    "map",
    "runtime",
    "environment",
    "scenario",
    "treatment",
    "protocol",
    "captureSha256",
    "artifactRef",
    "validity",
    "privacy",
    "notes",
}
VISUAL_CAPTURE_PROTOCOL_KEYS = {
    "name",
    "version",
    "artifactSha256",
    "captureApi",
    "sourceKind",
    "sourceFallbackApplied",
    "mediaKind",
    "frameCount",
    "frameRateHz",
    "viewCount",
    "width",
    "height",
    "colorSpace",
    "pixelFormat",
    "timingMode",
    "droppedFrames",
    "duplicatedFrames",
}
VISUAL_CAPTURE_TIMING_MODES = {"fixed-step", "wall-clock", "unknown"}
VISUAL_CAPTURE_VALIDITY_KEYS = {"state", "contamination", "notes"}
VISUAL_CAPTURE_CONTAMINATION_KEYS = {
    "kind",
    "firstFrame",
    "lastFrame",
    "notes",
}
VISUAL_CAPTURE_CONTAMINATION_KINDS = {
    "capture-overhead",
    "driver-reset",
    "dropped-frame",
    "duplicated-frame",
    "focus-loss",
    "loading-transition",
    "shader-compilation",
    "timing-discontinuity",
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


def scan_public_content(path: pathlib.Path, data: bytes) -> None:
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
    for field in ("warmupSamples", "requestedSamples"):
        _require_nonnegative_integer(protocol[field], f"{context}.protocol.{field}")
    if protocol["requestedSamples"] == 0:
        raise ValidationError(f"{context}.protocol requestedSamples must be positive")
    cadence = protocol["sampleCadence"]
    if not isinstance(cadence, dict):
        raise ValidationError(f"{context}.protocol.sampleCadence must be an object")
    _require_keys(cadence, PERFORMANCE_CADENCE_KEYS, f"{context}.protocol.sampleCadence")
    if cadence["mode"] == "frame-stride":
        _require_nonnegative_integer(
            cadence["value"], f"{context}.protocol.sampleCadence.value"
        )
        if cadence["value"] == 0:
            raise ValidationError(f"{context}.protocol frame stride must be positive")
    elif cadence["mode"] == "wall-clock-ms":
        _require_canonical_decimal(
            cadence["value"], f"{context}.protocol.sampleCadence.value"
        )
        if decimal.Decimal(cadence["value"]) == 0:
            raise ValidationError(f"{context}.protocol wall-clock cadence must be positive")
    else:
        raise ValidationError(f"{context}.protocol.sampleCadence mode is unsupported")
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


def _validate_optimization_axis(axis: dict, context: str, map_nodes: set[str]) -> None:
    _require_keys(axis, OPTIMIZATION_AXIS_KEYS, context)
    axis_id = axis["axisId"]
    if not isinstance(axis_id, str) or not RECORD_ID_PATTERN.fullmatch(axis_id):
        raise ValidationError(f"invalid axisId at {context}")
    for field in ("label", "settingPath"):
        _require_nonempty_string(axis[field], f"{context}.{field}")
    if axis["mapNodeRef"] not in map_nodes:
        raise ValidationError(f"{context}.mapNodeRef is not declared by the experiment")
    value_type = axis["valueType"]
    if value_type not in OPTIMIZATION_VALUE_TYPES:
        raise ValidationError(f"invalid valueType at {context}")
    domain = axis["domain"]
    if not isinstance(domain, dict) or domain.get("kind") != value_type:
        raise ValidationError(f"{context}.domain must match valueType")
    if value_type == "boolean":
        _require_keys(domain, {"kind"}, f"{context}.domain")
        return
    if value_type == "categorical":
        _require_keys(domain, {"kind", "values"}, f"{context}.domain")
        _require_unique_strings(domain["values"], f"{context}.domain.values", minimum=2)
        return
    _require_keys(
        domain,
        {"kind", "minimum", "maximum", "step"},
        f"{context}.domain",
    )
    if value_type == "integer":
        for field in ("minimum", "maximum", "step"):
            _require_nonnegative_integer(domain[field], f"{context}.domain.{field}")
        if domain["step"] == 0 or domain["maximum"] < domain["minimum"]:
            raise ValidationError(f"invalid integer domain at {context}")
        if (domain["maximum"] - domain["minimum"]) % domain["step"]:
            raise ValidationError(f"integer domain does not end on a step at {context}")
        return
    for field in ("minimum", "maximum", "step"):
        _require_canonical_decimal(domain[field], f"{context}.domain.{field}")
    minimum = decimal.Decimal(domain["minimum"])
    maximum = decimal.Decimal(domain["maximum"])
    step = decimal.Decimal(domain["step"])
    if step == 0 or maximum < minimum or (maximum - minimum) % step:
        raise ValidationError(f"invalid decimal domain at {context}")


def _validate_optimization_value(value: object, axis: dict, context: str) -> None:
    value_type = axis["valueType"]
    domain = axis["domain"]
    if value_type == "boolean":
        if not isinstance(value, bool):
            raise ValidationError(f"{context} must be boolean")
        return
    if value_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValidationError(f"{context} must be an integer")
        if value < domain["minimum"] or value > domain["maximum"]:
            raise ValidationError(f"{context} is outside the axis domain")
        if (value - domain["minimum"]) % domain["step"]:
            raise ValidationError(f"{context} is not on an axis step")
        return
    if value_type == "decimal":
        _require_canonical_decimal(value, context)
        parsed = decimal.Decimal(value)
        minimum = decimal.Decimal(domain["minimum"])
        maximum = decimal.Decimal(domain["maximum"])
        step = decimal.Decimal(domain["step"])
        if parsed < minimum or parsed > maximum or (parsed - minimum) % step:
            raise ValidationError(f"{context} is outside the decimal axis domain")
        return
    if not isinstance(value, str) or value not in domain["values"]:
        raise ValidationError(f"{context} is not an allowed categorical value")


def validate_optimization_experiment(record: dict, context: str) -> None:
    if not isinstance(record, dict):
        raise ValidationError(f"{context} must be an object")
    _require_keys(record, OPTIMIZATION_KEYS, context)
    if record["schema"] != {
        "name": "skyrim-render-map.optimization-experiment",
        "major": 1,
        "minor": 0,
    }:
        raise ValidationError(f"unsupported optimization experiment schema at {context}")
    experiment_id = record["experimentId"]
    if not isinstance(experiment_id, str) or not RECORD_ID_PATTERN.fullmatch(
        experiment_id
    ):
        raise ValidationError(f"invalid experimentId at {context}")
    _parse_time(record["recordedAt"], f"{context}.recordedAt")

    map_identity = record["map"]
    if not isinstance(map_identity, dict):
        raise ValidationError(f"{context}.map must be an object")
    _require_keys(map_identity, PERFORMANCE_MAP_KEYS, f"{context}.map")
    if not isinstance(
        map_identity["mapSnapshotId"], str
    ) or not MAP_SNAPSHOT_ID_PATTERN.fullmatch(map_identity["mapSnapshotId"]):
        raise ValidationError(f"invalid mapSnapshotId at {context}")
    _require_unique_strings(map_identity["nodeRefs"], f"{context}.map.nodeRefs", minimum=1)
    map_nodes = set(map_identity["nodeRefs"])

    producer = record["producer"]
    if not isinstance(producer, dict):
        raise ValidationError(f"{context}.producer must be an object")
    _require_keys(producer, OPTIMIZATION_PRODUCER_KEYS, f"{context}.producer")
    for field in ("name", "version"):
        _require_nonempty_string(producer[field], f"{context}.producer.{field}")
    _require_optional_digest(
        producer["artifactSha256"], SHA256_PATTERN,
        f"{context}.producer.artifactSha256",
    )
    if producer["artifactSha256"] is None:
        raise ValidationError(f"{context}.producer.artifactSha256 is required")

    search = record["search"]
    if not isinstance(search, dict):
        raise ValidationError(f"{context}.search must be an object")
    _require_keys(search, OPTIMIZATION_SEARCH_KEYS, f"{context}.search")
    for field in ("algorithm", "algorithmVersion"):
        _require_nonempty_string(search[field], f"{context}.search.{field}")
    _require_optional_digest(
        search["randomSeedSha256"], SHA256_PATTERN,
        f"{context}.search.randomSeedSha256",
    )
    _require_nonnegative_integer(
        search["requestedCandidateCount"],
        f"{context}.search.requestedCandidateCount",
    )
    if search["requestedCandidateCount"] == 0:
        raise ValidationError(f"{context}.search.requestedCandidateCount must be positive")

    axes = record["axes"]
    if not isinstance(axes, list) or not axes:
        raise ValidationError(f"{context}.axes must be a non-empty array")
    axes_by_id: dict[str, dict] = {}
    for index, axis in enumerate(axes):
        item_context = f"{context}.axes[{index}]"
        if not isinstance(axis, dict):
            raise ValidationError(f"{item_context} must be an object")
        _validate_optimization_axis(axis, item_context, map_nodes)
        if axis["axisId"] in axes_by_id:
            raise ValidationError(f"duplicate axisId at {context}")
        axes_by_id[axis["axisId"]] = axis

    objectives = record["objectives"]
    if not isinstance(objectives, list) or len(objectives) < 2:
        raise ValidationError(f"{context}.objectives must contain at least two objectives")
    objectives_by_id: dict[str, dict] = {}
    for index, objective in enumerate(objectives):
        item_context = f"{context}.objectives[{index}]"
        if not isinstance(objective, dict):
            raise ValidationError(f"{item_context} must be an object")
        _require_keys(objective, OPTIMIZATION_OBJECTIVE_KEYS, item_context)
        objective_id = objective["objectiveId"]
        if not isinstance(objective_id, str) or not RECORD_ID_PATTERN.fullmatch(
            objective_id
        ):
            raise ValidationError(f"invalid objectiveId at {item_context}")
        if objective_id in objectives_by_id:
            raise ValidationError(f"duplicate objectiveId at {context}")
        objectives_by_id[objective_id] = objective
        for field in ("label", "metric"):
            _require_nonempty_string(objective[field], f"{item_context}.{field}")
        if objective["unit"] not in PERFORMANCE_UNITS:
            raise ValidationError(f"invalid objective unit at {item_context}")
        if objective["direction"] not in OPTIMIZATION_DIRECTIONS:
            raise ValidationError(f"invalid objective direction at {item_context}")
        if objective["scope"] not in PERFORMANCE_SCOPES:
            raise ValidationError(f"invalid objective scope at {item_context}")
        minimum_scope_refs = (
            1 if objective["scope"] in {"map-node", "map-node-set"} else 0
        )
        _require_unique_strings(
            objective["scopeRefs"],
            f"{item_context}.scopeRefs",
            minimum=minimum_scope_refs,
        )
        if not set(objective["scopeRefs"]).issubset(map_nodes):
            raise ValidationError(f"{item_context}.scopeRefs are not declared map nodes")
        if objective["reducer"] != "median-of-observation-medians":
            raise ValidationError(f"unsupported objective reducer at {item_context}")
        _require_canonical_decimal(
            objective["dominanceEpsilon"], f"{item_context}.dominanceEpsilon"
        )

    constraints = record["constraints"]
    if not isinstance(constraints, list):
        raise ValidationError(f"{context}.constraints must be an array")
    constraint_ids: set[str] = set()
    for index, constraint in enumerate(constraints):
        item_context = f"{context}.constraints[{index}]"
        if not isinstance(constraint, dict):
            raise ValidationError(f"{item_context} must be an object")
        _require_keys(constraint, OPTIMIZATION_CONSTRAINT_KEYS, item_context)
        constraint_id = constraint["constraintId"]
        if not isinstance(constraint_id, str) or not RECORD_ID_PATTERN.fullmatch(
            constraint_id
        ):
            raise ValidationError(f"invalid constraintId at {item_context}")
        if constraint_id in constraint_ids:
            raise ValidationError(f"duplicate constraintId at {context}")
        constraint_ids.add(constraint_id)
        if constraint["objectiveId"] not in objectives_by_id:
            raise ValidationError(f"unknown constraint objective at {item_context}")
        if constraint["operator"] not in OPTIMIZATION_OPERATORS:
            raise ValidationError(f"invalid constraint operator at {item_context}")
        _require_canonical_decimal(constraint["threshold"], f"{item_context}.threshold")

    candidates = record["candidates"]
    if not isinstance(candidates, list) or not candidates:
        raise ValidationError(f"{context}.candidates must be a non-empty array")
    if len(candidates) > search["requestedCandidateCount"]:
        raise ValidationError(f"candidate count exceeds requestedCandidateCount at {context}")
    candidate_ids: set[str] = set()
    for index, candidate in enumerate(candidates):
        item_context = f"{context}.candidates[{index}]"
        if not isinstance(candidate, dict):
            raise ValidationError(f"{item_context} must be an object")
        _require_keys(candidate, OPTIMIZATION_CANDIDATE_KEYS, item_context)
        candidate_id = candidate["candidateId"]
        if not isinstance(candidate_id, str) or not RECORD_ID_PATTERN.fullmatch(
            candidate_id
        ):
            raise ValidationError(f"invalid candidateId at {item_context}")
        if candidate_id in candidate_ids:
            raise ValidationError(f"duplicate candidateId at {context}")
        candidate_ids.add(candidate_id)
        _require_nonempty_string(candidate["label"], f"{item_context}.label")
        _require_optional_digest(
            candidate["treatmentSha256"], SHA256_PATTERN,
            f"{item_context}.treatmentSha256",
        )
        if candidate["treatmentSha256"] is None:
            raise ValidationError(f"{item_context}.treatmentSha256 is required")
        if candidate["outcome"] not in OPTIMIZATION_OUTCOMES:
            raise ValidationError(f"invalid candidate outcome at {item_context}")
        if candidate["outcome"] == "completed":
            if candidate["failureKind"] is not None:
                raise ValidationError(f"completed candidate has failureKind at {item_context}")
        else:
            _require_nonempty_string(
                candidate["failureKind"], f"{item_context}.failureKind"
            )
        if not isinstance(candidate["notes"], str):
            raise ValidationError(f"{item_context}.notes must be a string")

        parameters = candidate["parameters"]
        if not isinstance(parameters, list):
            raise ValidationError(f"{item_context}.parameters must be an array")
        parameter_ids: set[str] = set()
        for parameter_index, parameter in enumerate(parameters):
            parameter_context = f"{item_context}.parameters[{parameter_index}]"
            if not isinstance(parameter, dict):
                raise ValidationError(f"{parameter_context} must be an object")
            _require_keys(parameter, OPTIMIZATION_PARAMETER_KEYS, parameter_context)
            axis = axes_by_id.get(parameter["axisId"])
            if axis is None or parameter["axisId"] in parameter_ids:
                raise ValidationError(
                    f"invalid or duplicate parameter axis at {parameter_context}"
                )
            parameter_ids.add(parameter["axisId"])
            _validate_optimization_value(
                parameter["value"], axis, f"{parameter_context}.value"
            )
        if parameter_ids != set(axes_by_id):
            raise ValidationError(
                f"candidate parameters do not cover every axis at {item_context}"
            )

        assignments = candidate["objectiveObservations"]
        if not isinstance(assignments, list):
            raise ValidationError(f"{item_context}.objectiveObservations must be an array")
        assignment_ids: set[str] = set()
        for assignment_index, assignment in enumerate(assignments):
            assignment_context = (
                f"{item_context}.objectiveObservations[{assignment_index}]"
            )
            if not isinstance(assignment, dict):
                raise ValidationError(f"{assignment_context} must be an object")
            _require_keys(
                assignment, OPTIMIZATION_OBJECTIVE_OBSERVATION_KEYS,
                assignment_context,
            )
            objective_id = assignment["objectiveId"]
            if objective_id not in objectives_by_id or objective_id in assignment_ids:
                raise ValidationError(
                    f"invalid or duplicate objective assignment at {assignment_context}"
                )
            assignment_ids.add(objective_id)
            _require_unique_strings(
                assignment["observationRefs"],
                f"{assignment_context}.observationRefs",
                minimum=1,
            )
        if candidate["outcome"] == "completed" and assignment_ids != set(
            objectives_by_id
        ):
            raise ValidationError(
                f"completed candidate must cover every objective at {item_context}"
            )
    if not isinstance(record["notes"], str):
        raise ValidationError(f"{context}.notes must be a string")


def validate_visual_rubric(record: dict, context: str) -> None:
    if not isinstance(record, dict):
        raise ValidationError(f"{context} must be an object")
    _require_keys(record, VISUAL_RUBRIC_KEYS, context)
    if record["schema"] != {
        "name": "skyrim-render-map.visual-rubric",
        "major": 1,
        "minor": 0,
    }:
        raise ValidationError(f"unsupported visual rubric schema at {context}")
    _require_nonempty_string(record["rubricId"], f"{context}.rubricId")
    if not RECORD_ID_PATTERN.fullmatch(record["rubricId"]):
        raise ValidationError(f"{context}.rubricId is invalid")
    _require_nonempty_string(record["version"], f"{context}.version")
    _require_nonempty_string(record["label"], f"{context}.label")
    if record["scope"] not in VISUAL_RUBRIC_SCOPES:
        raise ValidationError(f"{context}.scope is unsupported")
    _require_unique_strings(record["mapNodeRefs"], f"{context}.mapNodeRefs")

    dimensions = record["dimensions"]
    if not isinstance(dimensions, list) or not dimensions:
        raise ValidationError(f"{context}.dimensions must be a non-empty array")
    dimension_ids: set[str] = set()
    for index, dimension in enumerate(dimensions):
        item_context = f"{context}.dimensions[{index}]"
        if not isinstance(dimension, dict):
            raise ValidationError(f"{item_context} must be an object")
        _require_keys(dimension, VISUAL_DIMENSION_KEYS, item_context)
        dimension_id = dimension["dimensionId"]
        _require_nonempty_string(dimension_id, f"{item_context}.dimensionId")
        if not RECORD_ID_PATTERN.fullmatch(dimension_id):
            raise ValidationError(f"{item_context}.dimensionId is invalid")
        if dimension_id in dimension_ids:
            raise ValidationError(f"duplicate visual dimensionId: {dimension_id}")
        dimension_ids.add(dimension_id)
        _require_nonempty_string(dimension["label"], f"{item_context}.label")
        _require_nonempty_string(
            dimension["description"], f"{item_context}.description"
        )
        if dimension["kind"] not in VISUAL_DIMENSION_KINDS:
            raise ValidationError(f"{item_context}.kind is unsupported")
        if not isinstance(dimension["notes"], str):
            raise ValidationError(f"{item_context}.notes must be a string")

    magnitudes = record["magnitudes"]
    if not isinstance(magnitudes, list):
        raise ValidationError(f"{context}.magnitudes must be an array")
    observed_magnitudes: dict[str, int] = {}
    for index, magnitude in enumerate(magnitudes):
        item_context = f"{context}.magnitudes[{index}]"
        if not isinstance(magnitude, dict):
            raise ValidationError(f"{item_context} must be an object")
        _require_keys(magnitude, VISUAL_MAGNITUDE_KEYS, item_context)
        magnitude_id = magnitude["magnitudeId"]
        if magnitude_id in observed_magnitudes:
            raise ValidationError(f"duplicate visual magnitudeId: {magnitude_id}")
        ordinal = magnitude["ordinal"]
        if not isinstance(ordinal, int) or isinstance(ordinal, bool):
            raise ValidationError(f"{item_context}.ordinal must be an integer")
        observed_magnitudes[magnitude_id] = ordinal
        _require_nonempty_string(magnitude["label"], f"{item_context}.label")
        _require_nonempty_string(
            magnitude["description"], f"{item_context}.description"
        )
    if observed_magnitudes != VISUAL_MAGNITUDES:
        raise ValidationError(
            f"{context}.magnitudes must define the canonical v1 magnitude scale"
        )
    if not isinstance(record["notes"], str):
        raise ValidationError(f"{context}.notes must be a string")


def _validate_visual_region(region: object, context: str) -> None:
    if region is None:
        return
    if not isinstance(region, dict):
        raise ValidationError(f"{context} must be null or an object")
    _require_keys(region, VISUAL_REGION_KEYS, context)
    values: dict[str, decimal.Decimal] = {}
    for key, value in region.items():
        _require_canonical_decimal(value, f"{context}.{key}")
        values[key] = decimal.Decimal(value)
        if values[key] > 1:
            raise ValidationError(f"{context}.{key} must not exceed 1")
    if values["width"] <= 0 or values["height"] <= 0:
        raise ValidationError(f"{context} width and height must be positive")
    if values["x"] + values["width"] > 1:
        raise ValidationError(f"{context} exceeds normalized horizontal bounds")
    if values["y"] + values["height"] > 1:
        raise ValidationError(f"{context} exceeds normalized vertical bounds")


def _validate_visual_validity(record: dict, context: str) -> None:
    validity = record["validity"]
    if not isinstance(validity, dict):
        raise ValidationError(f"{context}.validity must be an object")
    _require_keys(validity, VISUAL_VALIDITY_KEYS, f"{context}.validity")
    if validity["state"] not in PERFORMANCE_VALIDITY_STATES:
        raise ValidationError(f"invalid validity state at {context}")
    if not isinstance(validity["notes"], str):
        raise ValidationError(f"{context}.validity.notes must be a string")
    contamination = validity["contamination"]
    if not isinstance(contamination, list):
        raise ValidationError(f"{context}.validity.contamination must be an array")
    if validity["state"] == "valid" and contamination:
        raise ValidationError(f"valid visual comparisons cannot declare contamination")
    if validity["state"] != "valid" and not validity["notes"].strip():
        raise ValidationError(f"non-valid visual comparisons require validity notes")
    trial_count = len(record["trials"])
    for index, item in enumerate(contamination):
        item_context = f"{context}.validity.contamination[{index}]"
        if not isinstance(item, dict):
            raise ValidationError(f"{item_context} must be an object")
        _require_keys(item, VISUAL_CONTAMINATION_KEYS, item_context)
        if item["kind"] not in VISUAL_CONTAMINATION_KINDS:
            raise ValidationError(f"invalid contamination kind at {item_context}")
        for field in ("firstTrial", "lastTrial"):
            _require_nonnegative_integer(item[field], f"{item_context}.{field}")
        if (
            item["firstTrial"] > item["lastTrial"]
            or item["lastTrial"] >= trial_count
        ):
            raise ValidationError(f"invalid contamination trial range at {item_context}")
        _require_nonempty_string(item["notes"], f"{item_context}.notes")


def validate_artifact(record: dict, context: str) -> None:
    if not isinstance(record, dict):
        raise ValidationError(f"{context} must be an object")
    _require_keys(record, ARTIFACT_KEYS, context)
    if record["schema"] != {
        "name": "skyrim-render-map.artifact",
        "major": 1,
        "minor": 0,
    }:
        raise ValidationError(f"unsupported artifact schema at {context}")
    artifact_id = record["artifactId"]
    if not isinstance(artifact_id, str) or not RECORD_ID_PATTERN.fullmatch(artifact_id):
        raise ValidationError(f"invalid artifactId at {context}")
    _require_optional_digest(
        record["artifactSha256"], SHA256_PATTERN, f"{context}.artifactSha256"
    )
    if record["artifactSha256"] is None:
        raise ValidationError(f"{context}.artifactSha256 is required")
    _require_nonempty_string(record["mediaType"], f"{context}.mediaType")
    if record["contentKind"] not in ARTIFACT_CONTENT_KINDS:
        raise ValidationError(f"unsupported contentKind at {context}")
    if record["encoding"] not in ARTIFACT_ENCODINGS:
        raise ValidationError(f"unsupported encoding at {context}")
    if record["license"] not in ARTIFACT_LICENSES:
        raise ValidationError(f"unsupported artifact license at {context}")
    if record["retentionClass"] not in ARTIFACT_RETENTION_CLASSES:
        raise ValidationError(f"unsupported retentionClass at {context}")
    for field in ("byteLength", "expandedByteLength"):
        _require_nonnegative_integer(record[field], f"{context}.{field}")
        if record[field] == 0:
            raise ValidationError(f"{context}.{field} must be positive")
    locations = record["locations"]
    if not isinstance(locations, list) or not locations:
        raise ValidationError(f"{context}.locations must be a non-empty array")
    if not all(isinstance(location, str) for location in locations):
        raise ValidationError(f"{context}.locations must contain strings")
    if len(locations) != len(set(locations)):
        raise ValidationError(f"{context}.locations contains duplicates")
    for index, location in enumerate(locations):
        parsed = urllib.parse.urlsplit(location) if isinstance(location, str) else None
        if parsed is None or parsed.scheme != "https" or not parsed.netloc:
            raise ValidationError(
                f"{context}.locations[{index}] must be an absolute HTTPS URL"
            )
        if parsed.username or parsed.password:
            raise ValidationError(f"{context}.locations[{index}] must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValidationError(
                f"{context}.locations[{index}] must be a stable credential-free URL"
            )
    if not isinstance(record["notes"], str):
        raise ValidationError(f"{context}.notes must be a string")


def validate_visual_capture(record: dict, context: str) -> None:
    if not isinstance(record, dict):
        raise ValidationError(f"{context} must be an object")
    _require_keys(record, VISUAL_CAPTURE_KEYS, context)
    if record["schema"] != {
        "name": "skyrim-render-map.visual-capture-observation",
        "major": 1,
        "minor": 0,
    }:
        raise ValidationError(f"unsupported visual capture schema at {context}")
    capture_id = record["captureId"]
    if not isinstance(capture_id, str) or not RECORD_ID_PATTERN.fullmatch(capture_id):
        raise ValidationError(f"invalid captureId at {context}")
    _parse_time(record["recordedAt"], f"{context}.recordedAt")
    _validate_performance_identity(record, context)
    _validate_performance_environment(record, context)

    scenario = record["scenario"]
    if not isinstance(scenario, dict):
        raise ValidationError(f"{context}.scenario must be an object")
    _require_keys(scenario, PERFORMANCE_SCENARIO_KEYS, f"{context}.scenario")
    _require_nonempty_string(scenario["label"], f"{context}.scenario.label")
    for field in ("scenarioSha256", "configurationSha256", "cacheSha256"):
        _require_optional_digest(scenario[field], SHA256_PATTERN, f"{context}.scenario.{field}")
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

    protocol = record["protocol"]
    if not isinstance(protocol, dict):
        raise ValidationError(f"{context}.protocol must be an object")
    _require_keys(protocol, VISUAL_CAPTURE_PROTOCOL_KEYS, f"{context}.protocol")
    for field in ("name", "version", "colorSpace", "pixelFormat"):
        _require_nonempty_string(protocol[field], f"{context}.protocol.{field}")
    _require_optional_digest(
        protocol["artifactSha256"], SHA256_PATTERN,
        f"{context}.protocol.artifactSha256",
    )
    if protocol["artifactSha256"] is None:
        raise ValidationError(f"{context}.protocol.artifactSha256 is required")
    capture_api = protocol["captureApi"]
    if not isinstance(capture_api, dict):
        raise ValidationError(f"{context}.protocol.captureApi must be an object")
    _require_keys(capture_api, PERFORMANCE_TOOL_KEYS, f"{context}.protocol.captureApi")
    for field in ("name", "version"):
        _require_nonempty_string(capture_api[field], f"{context}.protocol.captureApi.{field}")
    _require_optional_digest(
        capture_api["artifactSha256"], SHA256_PATTERN,
        f"{context}.protocol.captureApi.artifactSha256",
    )
    if capture_api["artifactSha256"] is None:
        raise ValidationError(f"{context}.protocol.captureApi.artifactSha256 is required")
    if protocol["mediaKind"] not in VISUAL_MEDIA_KINDS:
        raise ValidationError(f"unsupported capture mediaKind at {context}")
    _require_nonempty_string(protocol["sourceKind"], f"{context}.protocol.sourceKind")
    if not isinstance(protocol["sourceFallbackApplied"], bool):
        raise ValidationError(f"{context}.protocol.sourceFallbackApplied must be boolean")
    for field in ("frameCount", "viewCount", "width", "height"):
        _require_nonnegative_integer(protocol[field], f"{context}.protocol.{field}")
        if protocol[field] == 0:
            raise ValidationError(f"{context}.protocol.{field} must be positive")
    for field in ("droppedFrames", "duplicatedFrames"):
        _require_nonnegative_integer(protocol[field], f"{context}.protocol.{field}")
    if protocol["timingMode"] not in VISUAL_CAPTURE_TIMING_MODES:
        raise ValidationError(f"unsupported capture timingMode at {context}")
    expected_views = 2 if protocol["mediaKind"] == "stereo-sequence" else 1
    if protocol["viewCount"] != expected_views:
        raise ValidationError(f"capture view count conflicts with media kind at {context}")
    if protocol["mediaKind"] == "still-pair":
        if protocol["frameCount"] != 1 or protocol["frameRateHz"] is not None:
            raise ValidationError(f"still-pair capture requires one frame and no rate at {context}")
    else:
        _require_canonical_decimal(protocol["frameRateHz"], f"{context}.protocol.frameRateHz")
        if decimal.Decimal(protocol["frameRateHz"]) == 0:
            raise ValidationError(f"capture frameRateHz must be positive at {context}")

    _require_optional_digest(record["captureSha256"], SHA256_PATTERN, f"{context}.captureSha256")
    if record["captureSha256"] is None:
        raise ValidationError(f"{context}.captureSha256 is required")
    _require_nonempty_string(record["artifactRef"], f"{context}.artifactRef")
    validity = record["validity"]
    if not isinstance(validity, dict):
        raise ValidationError(f"{context}.validity must be an object")
    _require_keys(validity, VISUAL_CAPTURE_VALIDITY_KEYS, f"{context}.validity")
    if validity["state"] not in PERFORMANCE_VALIDITY_STATES:
        raise ValidationError(f"invalid visual capture validity state at {context}")
    if not isinstance(validity["notes"], str):
        raise ValidationError(f"{context}.validity.notes must be a string")
    contamination = validity["contamination"]
    if not isinstance(contamination, list):
        raise ValidationError(f"{context}.validity.contamination must be an array")
    if validity["state"] == "valid":
        if contamination or protocol["droppedFrames"] or protocol["duplicatedFrames"]:
            raise ValidationError("valid visual captures must be complete and uncontaminated")
    elif not validity["notes"].strip():
        raise ValidationError(f"non-valid visual captures require validity notes at {context}")
    for index, item in enumerate(contamination):
        item_context = f"{context}.validity.contamination[{index}]"
        if not isinstance(item, dict):
            raise ValidationError(f"{item_context} must be an object")
        _require_keys(item, VISUAL_CAPTURE_CONTAMINATION_KEYS, item_context)
        if item["kind"] not in VISUAL_CAPTURE_CONTAMINATION_KINDS:
            raise ValidationError(f"unsupported contamination kind at {item_context}")
        for field in ("firstFrame", "lastFrame"):
            _require_nonnegative_integer(item[field], f"{item_context}.{field}")
        if item["firstFrame"] > item["lastFrame"] or item["lastFrame"] >= protocol["frameCount"]:
            raise ValidationError(f"invalid contamination frame range at {item_context}")
        _require_nonempty_string(item["notes"], f"{item_context}.notes")
    privacy = record["privacy"]
    if not isinstance(privacy, dict):
        raise ValidationError(f"{context}.privacy must be an object")
    _require_keys(privacy, PERFORMANCE_PRIVACY_KEYS, f"{context}.privacy")
    if any(privacy[field] is not True for field in PERFORMANCE_PRIVACY_KEYS):
        raise ValidationError(f"visual capture privacy declarations must all be true at {context}")
    if not isinstance(record["notes"], str):
        raise ValidationError(f"{context}.notes must be a string")


def validate_visual_comparison(record: dict, context: str) -> None:
    if not isinstance(record, dict):
        raise ValidationError(f"{context} must be an object")
    _require_keys(record, VISUAL_COMPARISON_KEYS, context)
    if record["schema"] != {
        "name": "skyrim-render-map.visual-comparison",
        "major": 1,
        "minor": 0,
    }:
        raise ValidationError(f"unsupported visual comparison schema at {context}")
    comparison_id = record["comparisonId"]
    _require_nonempty_string(comparison_id, f"{context}.comparisonId")
    if not RECORD_ID_PATTERN.fullmatch(comparison_id):
        raise ValidationError(f"{context}.comparisonId is invalid")
    _parse_time(record["recordedAt"], f"{context}.recordedAt")
    _validate_performance_identity(record, context)
    _validate_performance_environment(record, context)

    scenario = record["scenario"]
    if not isinstance(scenario, dict):
        raise ValidationError(f"{context}.scenario must be an object")
    _require_keys(scenario, PERFORMANCE_SCENARIO_KEYS, f"{context}.scenario")
    _require_nonempty_string(scenario["label"], f"{context}.scenario.label")
    for key in ("scenarioSha256", "configurationSha256", "cacheSha256"):
        _require_optional_digest(
            scenario[key], SHA256_PATTERN, f"{context}.scenario.{key}"
        )
    _require_nonempty_string(record["rubricRef"], f"{context}.rubricRef")

    stimuli = record["stimuli"]
    if not isinstance(stimuli, dict):
        raise ValidationError(f"{context}.stimuli must be an object")
    _require_keys(stimuli, VISUAL_STIMULI_KEYS, f"{context}.stimuli")
    for stimulus_id in ("a", "b"):
        stimulus = stimuli[stimulus_id]
        item_context = f"{context}.stimuli.{stimulus_id}"
        if not isinstance(stimulus, dict):
            raise ValidationError(f"{item_context} must be an object")
        _require_keys(stimulus, VISUAL_STIMULUS_KEYS, item_context)
        for key in ("captureSha256", "treatmentSha256"):
            _require_optional_digest(
                stimulus[key], SHA256_PATTERN, f"{item_context}.{key}"
            )
            if stimulus[key] is None:
                raise ValidationError(f"{item_context}.{key} must not be null")
        _require_nonempty_string(
            stimulus["sourceObservationRef"],
            f"{item_context}.sourceObservationRef",
        )
    if stimuli["a"]["captureSha256"].lower() == stimuli["b"]["captureSha256"].lower():
        raise ValidationError(f"{context}.stimuli must identify distinct captures")

    protocol = record["protocol"]
    if not isinstance(protocol, dict):
        raise ValidationError(f"{context}.protocol must be an object")
    _require_keys(protocol, VISUAL_PROTOCOL_KEYS, f"{context}.protocol")
    for key in ("name", "version"):
        _require_nonempty_string(protocol[key], f"{context}.protocol.{key}")
    for key in ("artifactSha256", "preprocessingSha256"):
        _require_optional_digest(
            protocol[key], SHA256_PATTERN, f"{context}.protocol.{key}"
        )
        if protocol[key] is None:
            raise ValidationError(f"{context}.protocol.{key} must not be null")
    if protocol["evaluationMode"] != "blinded-pairwise":
        raise ValidationError(f"{context}.protocol must use blinded-pairwise mode")
    if protocol["presentation"] not in VISUAL_PRESENTATIONS:
        raise ValidationError(f"{context}.protocol.presentation is unsupported")
    if not isinstance(protocol["randomized"], bool):
        raise ValidationError(f"{context}.protocol.randomized must be boolean")
    if protocol["mediaKind"] not in VISUAL_MEDIA_KINDS:
        raise ValidationError(f"{context}.protocol.mediaKind is unsupported")
    _require_nonnegative_integer(
        protocol["frameCount"], f"{context}.protocol.frameCount"
    )
    if protocol["frameCount"] < 1:
        raise ValidationError(f"{context}.protocol.frameCount must be positive")
    if protocol["frameRateHz"] is not None:
        _require_canonical_decimal(
            protocol["frameRateHz"], f"{context}.protocol.frameRateHz"
        )
        if decimal.Decimal(protocol["frameRateHz"]) <= 0:
            raise ValidationError(f"{context}.protocol.frameRateHz must be positive")
    view_count = protocol["viewCount"]
    if view_count not in {1, 2}:
        raise ValidationError(f"{context}.protocol.viewCount must be 1 or 2")
    expected_views = 2 if protocol["mediaKind"] == "stereo-sequence" else 1
    if view_count != expected_views:
        raise ValidationError(
            f"{context}.protocol view count conflicts with media kind"
        )
    if protocol["mediaKind"] == "still-pair":
        if protocol["frameCount"] != 1 or protocol["frameRateHz"] is not None:
            raise ValidationError(
                f"{context}.protocol still-pair requires one frame and no frame rate"
            )
    elif protocol["frameRateHz"] is None:
        raise ValidationError(f"{context}.protocol sequence requires a frame rate")

    trials = record["trials"]
    if not isinstance(trials, list) or not trials:
        raise ValidationError(f"{context}.trials must be a non-empty array")
    trial_ids: set[str] = set()
    for trial_index, trial in enumerate(trials):
        trial_context = f"{context}.trials[{trial_index}]"
        if not isinstance(trial, dict):
            raise ValidationError(f"{trial_context} must be an object")
        _require_keys(trial, VISUAL_TRIAL_KEYS, trial_context)
        trial_id = trial["trialId"]
        _require_nonempty_string(trial_id, f"{trial_context}.trialId")
        if not RECORD_ID_PATTERN.fullmatch(trial_id) or trial_id in trial_ids:
            raise ValidationError(f"{trial_context}.trialId is invalid or duplicate")
        trial_ids.add(trial_id)
        evaluator = trial["evaluator"]
        if not isinstance(evaluator, dict):
            raise ValidationError(f"{trial_context}.evaluator must be an object")
        _require_keys(evaluator, VISUAL_EVALUATOR_KEYS, f"{trial_context}.evaluator")
        if evaluator["kind"] not in VISUAL_EVALUATOR_KINDS:
            raise ValidationError(f"{trial_context}.evaluator.kind is unsupported")
        _require_nonempty_string(evaluator["name"], f"{trial_context}.evaluator.name")
        for key in ("version", "artifactSha256", "promptSha256"):
            if key == "version":
                _require_optional_string(
                    evaluator[key], f"{trial_context}.evaluator.{key}"
                )
            else:
                _require_optional_digest(
                    evaluator[key], SHA256_PATTERN, f"{trial_context}.evaluator.{key}"
                )
        if evaluator["kind"] != "human" and any(
            evaluator[key] is None
            for key in ("version", "artifactSha256", "promptSha256")
        ):
            raise ValidationError(
                f"{trial_context}.evaluator requires version and artifact provenance"
            )
        order = trial["presentationOrder"]
        if order not in VISUAL_PRESENTATION_ORDERS:
            raise ValidationError(f"{trial_context}.presentationOrder is unsupported")
        if protocol["presentation"] == "simultaneous" and order != "simultaneous":
            raise ValidationError(
                f"{trial_context} conflicts with simultaneous presentation"
            )
        if protocol["presentation"] == "sequential" and order == "simultaneous":
            raise ValidationError(
                f"{trial_context} conflicts with sequential presentation"
            )
        judgments = trial["judgments"]
        if not isinstance(judgments, list) or not judgments:
            raise ValidationError(f"{trial_context}.judgments must be non-empty")
        judgment_ids: set[str] = set()
        for judgment_index, judgment in enumerate(judgments):
            judgment_context = f"{trial_context}.judgments[{judgment_index}]"
            if not isinstance(judgment, dict):
                raise ValidationError(f"{judgment_context} must be an object")
            _require_keys(judgment, VISUAL_JUDGMENT_KEYS, judgment_context)
            dimension_id = judgment["dimensionId"]
            _require_nonempty_string(
                dimension_id, f"{judgment_context}.dimensionId"
            )
            if dimension_id in judgment_ids:
                raise ValidationError(
                    f"duplicate dimensionId within trial: {dimension_id}"
                )
            judgment_ids.add(dimension_id)
            if judgment["assessment"] not in VISUAL_ASSESSMENTS:
                raise ValidationError(f"{judgment_context}.assessment is unsupported")
            if judgment["differenceMagnitude"] not in VISUAL_MAGNITUDES:
                raise ValidationError(
                    f"{judgment_context}.differenceMagnitude is unsupported"
                )
            _require_canonical_decimal(
                judgment["confidence"], f"{judgment_context}.confidence"
            )
            if decimal.Decimal(judgment["confidence"]) > 1:
                raise ValidationError(
                    f"{judgment_context}.confidence must not exceed 1"
                )
            evidence = judgment["evidence"]
            if not isinstance(evidence, list):
                raise ValidationError(f"{judgment_context}.evidence must be an array")
            for evidence_index, item in enumerate(evidence):
                evidence_context = f"{judgment_context}.evidence[{evidence_index}]"
                if not isinstance(item, dict):
                    raise ValidationError(f"{evidence_context} must be an object")
                _require_keys(item, VISUAL_EVIDENCE_KEYS, evidence_context)
                for key in ("firstFrame", "lastFrame"):
                    _require_nonnegative_integer(item[key], f"{evidence_context}.{key}")
                    if item[key] >= protocol["frameCount"]:
                        raise ValidationError(
                            f"{evidence_context}.{key} is out of range"
                        )
                if item["firstFrame"] > item["lastFrame"]:
                    raise ValidationError(f"{evidence_context} frame range is reversed")
                if item["view"] not in VISUAL_VIEWS:
                    raise ValidationError(f"{evidence_context}.view is unsupported")
                _validate_visual_region(item["region"], f"{evidence_context}.region")
                if not isinstance(item["notes"], str):
                    raise ValidationError(f"{evidence_context}.notes must be a string")
            if not isinstance(judgment["notes"], str):
                raise ValidationError(f"{judgment_context}.notes must be a string")
        if not isinstance(trial["notes"], str):
            raise ValidationError(f"{trial_context}.notes must be a string")
    _validate_visual_validity(record, context)
    privacy = record["privacy"]
    if not isinstance(privacy, dict):
        raise ValidationError(f"{context}.privacy must be an object")
    _require_keys(privacy, PERFORMANCE_PRIVACY_KEYS, f"{context}.privacy")
    if any(privacy[field] is not True for field in PERFORMANCE_PRIVACY_KEYS):
        raise ValidationError(
            f"{context}.privacy requires explicit publication consent"
        )
    if not isinstance(record["notes"], str):
        raise ValidationError(f"{context}.notes must be a string")


def load_submission_records(
    directory: pathlib.Path, submission_class: str
) -> tuple[
    list[dict],
    list[dict],
    list[dict],
    list[dict],
    list[dict],
    list[dict],
    list[dict],
    list[dict],
    list[dict],
]:
    entities_path = directory / "content" / "entities.jsonl"
    assertions_path = directory / "content" / "assertions.jsonl"
    resolutions_path = directory / "content" / "resolutions.jsonl"
    performance_path = directory / "content" / "performance-observations.jsonl"
    optimization_path = directory / "content" / "optimization-experiments.jsonl"
    rubric_path = directory / "content" / "visual-rubrics.jsonl"
    comparison_path = directory / "content" / "visual-comparisons.jsonl"
    artifact_path = directory / "content" / "artifacts.jsonl"
    capture_path = directory / "content" / "visual-captures.jsonl"
    entities = load_jsonl(entities_path) if entities_path.is_file() else []
    assertions = load_jsonl(assertions_path) if assertions_path.is_file() else []
    resolutions = load_jsonl(resolutions_path) if resolutions_path.is_file() else []
    performance = load_jsonl(performance_path) if performance_path.is_file() else []
    optimization = load_jsonl(optimization_path) if optimization_path.is_file() else []
    rubrics = load_jsonl(rubric_path) if rubric_path.is_file() else []
    comparisons = load_jsonl(comparison_path) if comparison_path.is_file() else []
    artifacts = load_jsonl(artifact_path) if artifact_path.is_file() else []
    captures = load_jsonl(capture_path) if capture_path.is_file() else []

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
    if optimization and submission_class != "observation":
        raise ValidationError(
            "optimization-experiments.jsonl requires an observation submission"
        )
    if (rubrics or comparisons or artifacts or captures) and submission_class != "observation":
        raise ValidationError(
            "visual evidence files require an observation submission"
        )
    if (performance or optimization or rubrics or comparisons or artifacts or captures) and entities:
        raise ValidationError(
            "measurement submissions must not declare structural entities"
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
    optimization_ids: set[str] = set()
    for index, experiment in enumerate(optimization, start=1):
        validate_optimization_experiment(experiment, f"{optimization_path}:{index}")
        if experiment["experimentId"] in optimization_ids:
            raise ValidationError(
                f"duplicate optimization experimentId: {experiment['experimentId']}"
            )
        optimization_ids.add(experiment["experimentId"])
    rubric_ids: set[str] = set()
    for index, rubric in enumerate(rubrics, start=1):
        validate_visual_rubric(rubric, f"{rubric_path}:{index}")
        if rubric["rubricId"] in rubric_ids:
            raise ValidationError(f"duplicate visual rubricId: {rubric['rubricId']}")
        rubric_ids.add(rubric["rubricId"])
    comparison_ids: set[str] = set()
    for index, comparison in enumerate(comparisons, start=1):
        validate_visual_comparison(comparison, f"{comparison_path}:{index}")
        if comparison["comparisonId"] in comparison_ids:
            raise ValidationError(
                f"duplicate visual comparisonId: {comparison['comparisonId']}"
            )
        comparison_ids.add(comparison["comparisonId"])
    artifact_ids: set[str] = set()
    for index, artifact in enumerate(artifacts, start=1):
        validate_artifact(artifact, f"{artifact_path}:{index}")
        if artifact["artifactId"] in artifact_ids:
            raise ValidationError(f"duplicate artifactId: {artifact['artifactId']}")
        artifact_ids.add(artifact["artifactId"])
    capture_ids: set[str] = set()
    for index, capture in enumerate(captures, start=1):
        validate_visual_capture(capture, f"{capture_path}:{index}")
        if capture["captureId"] in capture_ids:
            raise ValidationError(f"duplicate visual captureId: {capture['captureId']}")
        capture_ids.add(capture["captureId"])
    record_ids = (
        list(entity_ids)
        + list(assertion_ids)
        + list(resolution_ids)
        + list(performance_ids)
        + list(optimization_ids)
        + list(rubric_ids)
        + list(comparison_ids)
        + list(artifact_ids)
        + list(capture_ids)
    )
    if len(record_ids) != len(set(record_ids)):
        raise ValidationError("submission-local record IDs must be unique across record types")
    return (
        entities,
        assertions,
        resolutions,
        performance,
        optimization,
        rubrics,
        comparisons,
        artifacts,
        captures,
    )


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
        scan_public_content(path, path.read_bytes())

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
