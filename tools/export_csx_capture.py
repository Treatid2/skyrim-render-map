#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Treatid2 and contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Export a finalized CSX screenshot sequence into neutral capture evidence."""

from __future__ import annotations

import argparse
import binascii
import datetime as dt
import decimal
import hashlib
import json
import pathlib
import re
import shutil
import struct
import sys
import tempfile
import zipfile
from typing import Any

import compile_dataset as compiler
import validate_repository as validator


TOOL_VERSION = "1.0.0"
PLAN_SCHEMA = {
    "name": "skyrim-render-map.csx-capture-export-plan",
    "major": 1,
    "minor": 0,
}
PLAN_KEYS = {
    "schema",
    "submissionId",
    "artifactId",
    "captureId",
    "recordedAt",
    "source",
    "artifact",
    "map",
    "runtime",
    "environment",
    "scenario",
    "treatment",
    "protocol",
    "privacy",
    "notes",
}
SOURCE_KEYS = {"kind", "manifestPath"}
ARTIFACT_PLAN_KEYS = {"locationTemplate", "license", "retentionClass"}
PROTOCOL_PLAN_KEYS = {
    "name",
    "version",
    "artifactSha256",
    "frameRateHz",
    "timingMode",
}
SUCCESS_STATES = {"completed", "completed_with_warnings"}
DROPPED_STATES = {"dropped"}
FAILED_STATES = {"failed", "failed_partial"}
CANCELLED_STATES = {"cancelled", "cancelled_partial"}
SHA256_PATTERN = re.compile(r"^[A-Fa-f0-9]{64}$")
TERMINAL_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
VIEW_ALIASES = {
    "left": "left",
    "left_eye": "left",
    "right": "right",
    "right_eye": "right",
    "combined": "mono",
    "desktop_mirror": "mono",
    "mirror": "mono",
    "source_native": "mono",
}
PNG_COLOUR_TYPES = {
    0: "grayscale",
    2: "rgb",
    3: "indexed",
    4: "grayscale-alpha",
    6: "rgba",
}
PNG_BIT_DEPTHS = {
    0: {1, 2, 4, 8, 16},
    2: {8, 16},
    3: {1, 2, 4, 8},
    4: {8, 16},
    6: {8, 16},
}


class ExportError(RuntimeError):
    pass


def _strict_keys(value: Any, expected: set[str], context: str) -> dict:
    if not isinstance(value, dict):
        raise ExportError(f"{context} must be an object")
    actual = set(value)
    if actual != expected:
        raise ExportError(
            f"{context} keys mismatch; missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )
    return value


def _load_json(path: pathlib.Path, context: str) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
        return validator.parse_json(text, context)
    except (OSError, UnicodeError, validator.ValidationError) as error:
        raise ExportError(f"cannot read {context}: {error}") from error


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise ExportError(f"cannot hash {path.name!r}: {error}") from error
    return digest.hexdigest()


def _parse_time(value: Any, context: str) -> str:
    if not isinstance(value, str):
        raise ExportError(f"{context} must be an RFC 3339 timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ExportError(f"{context} must be an RFC 3339 timestamp") from error
    if parsed.tzinfo is None:
        raise ExportError(f"{context} must include a timezone")
    return parsed.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _resolve_plan_path(plan_path: pathlib.Path, value: Any) -> pathlib.Path:
    if not isinstance(value, str) or not value.strip():
        raise ExportError("source.manifestPath must be a non-empty path")
    candidate = pathlib.Path(value)
    if not candidate.is_absolute():
        candidate = plan_path.parent / candidate
    resolved = candidate.resolve()
    if not resolved.is_file():
        raise ExportError("source.manifestPath is not a file")
    return resolved


def _resolve_frame_path(manifest_path: pathlib.Path, value: Any) -> pathlib.Path:
    if not isinstance(value, str) or not value.strip():
        raise ExportError("frame artifact path must be non-empty")
    declared = pathlib.Path(value)
    if declared.is_absolute() and declared.is_file():
        return declared.resolve()
    if not declared.is_absolute():
        relative = (manifest_path.parent / declared).resolve()
        try:
            relative.relative_to(manifest_path.parent.resolve())
        except ValueError as error:
            raise ExportError("relative frame artifact escapes the manifest directory") from error
        if relative.is_file():
            return relative
    promoted = (manifest_path.parent / declared.name).resolve()
    if promoted.is_file():
        return promoted
    raise ExportError(f"frame artifact is unavailable: {declared.name!r}")


def _png_identity(path: pathlib.Path) -> tuple[int, int, str]:
    try:
        with path.open("rb") as stream:
            header = stream.read(33)
    except OSError as error:
        raise ExportError(f"cannot inspect {path.name!r}: {error}") from error
    if len(header) < 29 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ExportError(f"{path.name!r} is not a PNG")
    length = struct.unpack(">I", header[8:12])[0]
    if length != 13 or header[12:16] != b"IHDR":
        raise ExportError(f"{path.name!r} has no canonical PNG IHDR")
    width, height = struct.unpack(">II", header[16:24])
    bit_depth, colour_type = header[24], header[25]
    colour_name = PNG_COLOUR_TYPES.get(colour_type)
    expected_crc = struct.unpack(">I", header[29:33])[0]
    actual_crc = binascii.crc32(header[12:29]) & 0xFFFFFFFF
    if expected_crc != actual_crc:
        raise ExportError(f"{path.name!r} has an invalid PNG IHDR checksum")
    if (
        width == 0
        or height == 0
        or colour_name is None
        or bit_depth not in PNG_BIT_DEPTHS[colour_type]
    ):
        raise ExportError(f"{path.name!r} has unsupported PNG geometry")
    return width, height, f"png-{colour_name}-{bit_depth}bit"


def _normalize_view(value: Any, filename: str) -> str:
    if isinstance(value, str) and value.lower() in VIEW_ALIASES:
        return VIEW_ALIASES[value.lower()]
    stem = pathlib.Path(filename).stem.lower()
    for suffix, view in (("_left", "left"), ("_right", "right"), ("_combined", "mono")):
        if stem.endswith(suffix):
            return view
    raise ExportError(f"cannot identify view for frame artifact {filename!r}")


def _declared_output(capture: dict, filename: str, view: str) -> dict:
    outputs = capture.get("outputs", [])
    if not isinstance(outputs, list):
        raise ExportError("manifest capture.outputs must be an array")
    stem = pathlib.Path(filename).stem.lower()
    matches = []
    for output in outputs:
        if not isinstance(output, dict):
            continue
        raw_view = output.get("view")
        output_view = VIEW_ALIASES.get(raw_view.lower()) if isinstance(raw_view, str) else None
        suffix = output.get("nameSuffix")
        if output_view == view or (
            isinstance(suffix, str) and stem.endswith("_" + suffix.lower())
        ):
            matches.append(output)
    if len(matches) > 1:
        exact = [
            item
            for item in matches
            if isinstance(item.get("view"), str)
            and VIEW_ALIASES.get(item["view"].lower()) == view
        ]
        matches = exact
    return matches[0] if len(matches) == 1 else {}


def _artifact_metadata(
    manifest_path: pathlib.Path, capture: dict, artifact: dict, context: str
) -> tuple[pathlib.Path, dict]:
    if not isinstance(artifact, dict):
        raise ExportError(f"{context} must be an object")
    path = _resolve_frame_path(manifest_path, artifact.get("path"))
    size = path.stat().st_size
    if artifact.get("committed") is not True:
        raise ExportError(f"{context} is not committed")
    if artifact.get("bytes") != size:
        raise ExportError(f"{context} byte count differs from the file")
    digest = _sha256_file(path)
    declared_digest = artifact.get("sha256")
    if not isinstance(declared_digest, str) or not SHA256_PATTERN.fullmatch(declared_digest):
        raise ExportError(f"{context}.sha256 must be a complete SHA-256")
    if declared_digest.lower() != digest:
        raise ExportError(f"{context} SHA-256 differs from the file")
    actual = artifact.get("actual") if isinstance(artifact.get("actual"), dict) else {}
    view = _normalize_view(actual.get("view", artifact.get("view")), path.name)
    output = _declared_output(capture, path.name, view)
    encoding = output.get("encoding") if isinstance(output.get("encoding"), dict) else {}
    format_name = actual.get("format", encoding.get("format", path.suffix.lstrip(".")))
    if not isinstance(format_name, str):
        raise ExportError(f"{context} has no valid format declaration")
    format_name = format_name.lower()
    if format_name != "png":
        raise ExportError(f"{context} uses unsupported format {format_name!r}")
    width, height, pixel_format = _png_identity(path)
    if actual.get("width", width) != width or actual.get("height", height) != height:
        raise ExportError(f"{context} PNG dimensions differ from manifest metadata")
    colour = actual.get("colourContract", encoding.get("colourContract"))
    if not isinstance(colour, str) or not colour:
        raise ExportError(f"{context} has no colour contract")
    return path, {
        "view": view,
        "bytes": size,
        "sha256": digest,
        "width": width,
        "height": height,
        "format": "png",
        "colourContract": colour,
        "pixelFormat": pixel_format,
    }


def _validate_manifest_counts(counts: Any, child_count: int) -> dict[str, int]:
    if not isinstance(counts, dict):
        raise ExportError("manifest counts are required")
    normalized = {}
    for key in ("requested", "scheduled", "written", "dropped", "failed", "inFlight"):
        value = counts.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ExportError(f"manifest counts.{key} must be a non-negative integer")
        normalized[key] = value
    for key in ("cancelled", "acquired"):
        value = counts.get(key)
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            raise ExportError(f"manifest counts.{key} must be a non-negative integer")
        if value is not None:
            normalized[key] = value
    normalized.setdefault("cancelled", 0)
    if normalized["requested"] < normalized["scheduled"]:
        raise ExportError("manifest scheduled count exceeds requested count")
    if normalized["inFlight"] != 0 or normalized["scheduled"] != child_count:
        raise ExportError("final manifest count reconciliation failed")
    acquired = normalized.get("acquired")
    if acquired is not None and not (
        normalized["written"] <= acquired <= normalized["scheduled"]
    ):
        raise ExportError("manifest counts.acquired is inconsistent")
    return normalized


def _inspect_completed_child(
    manifest_path: pathlib.Path,
    capture: dict,
    child: dict,
    context: str,
) -> tuple[dict, str, bool, int]:
    artifacts = child.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ExportError(f"{context} has no committed artifacts")
    frame_artifacts = []
    source_paths = []
    for artifact_index, artifact in enumerate(artifacts):
        path, metadata = _artifact_metadata(
            manifest_path,
            capture,
            artifact,
            f"{context}.artifacts[{artifact_index}]",
        )
        source_paths.append(path)
        frame_artifacts.append(metadata)
    views = [item["view"] for item in frame_artifacts]
    if len(views) != len(set(views)):
        raise ExportError(f"{context} repeats an output view")
    engine_frame = child.get("scheduledEngineFrame")
    timestamp_us = child.get("scheduledTimestampUs")
    scheduled_values = (
        (engine_frame, "scheduledEngineFrame"),
        (timestamp_us, "scheduledTimestampUs"),
    )
    for value, name in scheduled_values:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ExportError(f"{context}.{name} must be non-negative")

    actual = child.get("actual") if isinstance(child.get("actual"), dict) else {}
    actual_source = actual.get("source") if isinstance(actual.get("source"), dict) else {}
    requested = child.get("requested") if isinstance(child.get("requested"), dict) else {}
    effective = child.get("effective") if isinstance(child.get("effective"), dict) else {}
    requested_source = capture.get("source") if isinstance(capture.get("source"), dict) else {}
    for descriptor in (requested, effective):
        source = descriptor.get("source")
        if not requested_source and isinstance(source, dict):
            requested_source = source
    source_kind = actual_source.get("kind", requested_source.get("kind"))
    if not isinstance(source_kind, str) or not source_kind:
        raise ExportError(f"{context} has no actual capture source")
    fallback_value = actual_source.get("fallbackApplied", False)
    if not isinstance(fallback_value, bool):
        raise ExportError(f"{context} has a non-boolean fallback declaration")
    if (
        actual_source.get("kind") is not None
        and requested_source.get("kind") is not None
        and actual_source["kind"] != requested_source["kind"]
        and not fallback_value
    ):
        raise ExportError(f"{context} changed capture source without declaring fallback")
    warnings = child.get("warnings", [])
    if warnings is not None and not isinstance(warnings, list):
        raise ExportError(f"{context}.warnings must be an array")
    return (
        {
            "scheduledEngineFrame": engine_frame,
            "scheduledTimestampUs": timestamp_us,
            "artifacts": frame_artifacts,
            "_sourcePaths": source_paths,
        },
        source_kind,
        fallback_value,
        len(warnings or []),
    )


def _inspect_manifest(manifest_path: pathlib.Path) -> dict:
    manifest = _load_json(manifest_path, "CSX sequence manifest")
    if not isinstance(manifest, dict):
        raise ExportError("CSX sequence manifest must be an object")
    contract = manifest.get("contract")
    if not isinstance(contract, dict) or contract.get("name") != "csx.screenshot":
        raise ExportError("source is not a CSX screenshot manifest")
    if contract.get("major") != 1 or contract.get("minor") != 0:
        raise ExportError("unsupported CSX screenshot contract; expected 1.0")
    revision = contract.get("schemaRevision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ExportError("unsupported CSX screenshot schema revision")
    if manifest.get("state") != "final":
        raise ExportError("CSX screenshot manifest is not final")
    children = manifest.get("children")
    capture = manifest.get("capture")
    if not isinstance(children, list):
        raise ExportError("manifest children are required")
    counts = _validate_manifest_counts(manifest.get("counts"), len(children))
    if capture is None:
        capture = {}
    if not isinstance(capture, dict):
        raise ExportError("manifest capture descriptor must be an object or null")
    frames = []
    omissions = []
    warning_count = 0
    source_kinds: set[str] = set()
    fallback_states: set[bool] = set()
    seen_ordinals: set[int] = set()
    seen_engine_frames: set[int] = set()
    duplicated_frames = 0
    for child_index, child in enumerate(children):
        context = f"children[{child_index}]"
        if not isinstance(child, dict):
            raise ExportError(f"{context} must be an object")
        ordinal = child.get("ordinal")
        if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 1:
            raise ExportError(f"{context}.ordinal must be positive")
        if ordinal in seen_ordinals:
            raise ExportError("manifest repeats a child ordinal")
        seen_ordinals.add(ordinal)
        state = child.get("state")
        if state not in SUCCESS_STATES:
            if state not in DROPPED_STATES | FAILED_STATES | CANCELLED_STATES:
                raise ExportError(f"{context} has unsupported terminal state {state!r}")
            omissions.append(
                {
                    "sourceOrdinal": ordinal,
                    "state": state,
                    "terminalCode": (
                        child["error"]
                        if isinstance(child.get("error"), str)
                        and TERMINAL_CODE_PATTERN.fullmatch(child["error"])
                        else "unspecified"
                    ),
                }
            )
            continue
        frame, source_kind, child_fallback, child_warning_count = (
            _inspect_completed_child(manifest_path, capture, child, context)
        )
        engine_frame = frame["scheduledEngineFrame"]
        if engine_frame in seen_engine_frames:
            duplicated_frames += 1
        seen_engine_frames.add(engine_frame)
        source_kinds.add(source_kind)
        fallback_states.add(child_fallback)
        warning_count += child_warning_count
        frame["sourceOrdinal"] = ordinal
        frames.append(frame)
    frames.sort(key=lambda item: item["sourceOrdinal"])
    if not frames:
        raise ExportError("manifest contains no completed frames")
    if counts["written"] != len(frames):
        raise ExportError("manifest counts.written differs from completed children")
    dropped = sum(item["state"] in DROPPED_STATES for item in omissions)
    failed = sum(item["state"] in FAILED_STATES for item in omissions)
    cancelled = sum(item["state"] in CANCELLED_STATES for item in omissions)
    if (
        counts["dropped"] != dropped
        or counts["failed"] != failed
        or counts["cancelled"] != cancelled
        or counts["written"] + dropped + failed + cancelled != counts["scheduled"]
    ):
        raise ExportError("manifest terminal counts do not reconcile")
    if len(source_kinds) != 1:
        raise ExportError("manifest mixes actual capture sources")
    if len(fallback_states) != 1:
        raise ExportError("manifest mixes fallback and non-fallback captures")
    view_sets = {tuple(sorted(item["view"] for item in frame["artifacts"])) for frame in frames}
    if len(view_sets) != 1:
        raise ExportError("manifest frames do not have a consistent view set")
    views = next(iter(view_sets))
    media_kind = "stereo-sequence" if views == ("left", "right") else "mono-sequence"
    if media_kind == "mono-sequence" and len(views) != 1:
        raise ExportError(f"unsupported capture view set: {views!r}")
    geometry = {
        (item["width"], item["height"], item["pixelFormat"], item["colourContract"])
        for frame in frames
        for item in frame["artifacts"]
    }
    if len(geometry) != 1:
        raise ExportError("manifest artifacts do not share geometry and encoding")
    width, height, pixel_format, colour_contract = next(iter(geometry))
    return {
        "manifest": manifest,
        "manifestSha256": _sha256_file(manifest_path),
        "contract": {
            "name": "csx.screenshot",
            "major": 1,
            "minor": 0,
            "schemaRevision": revision,
        },
        "counts": {
            "requested": counts["requested"],
            "scheduled": counts["scheduled"],
            "written": counts["written"],
            "dropped": dropped,
            "failed": failed,
            "cancelled": cancelled,
        },
        "frames": frames,
        "omissions": sorted(omissions, key=lambda item: item["sourceOrdinal"]),
        "dropped": dropped,
        "failed": failed,
        "cancelled": cancelled,
        "warningCount": warning_count,
        "duplicatedFrames": duplicated_frames,
        "sourceKind": next(iter(source_kinds)),
        "sourceFallbackApplied": next(iter(fallback_states)),
        "mediaKind": media_kind,
        "viewCount": len(views),
        "width": width,
        "height": height,
        "pixelFormat": pixel_format,
        "colourContract": colour_contract,
    }


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def _write_bundle(path: pathlib.Path, inspected: dict) -> tuple[int, int]:
    public_frames = []
    entries: list[tuple[str, pathlib.Path]] = []
    for index, frame in enumerate(inspected["frames"]):
        artifacts = []
        paired = sorted(
            zip(frame["artifacts"], frame["_sourcePaths"]),
            key=lambda item: item[0]["view"],
        )
        for metadata, source_path in paired:
            archive_path = f"frames/{index:06d}/{metadata['view']}.png"
            artifacts.append({"path": archive_path, **metadata})
            entries.append((archive_path, source_path))
        public_frames.append(
            {
                "index": index,
                "sourceOrdinal": frame["sourceOrdinal"],
                "scheduledEngineFrame": frame["scheduledEngineFrame"],
                "scheduledTimestampUs": frame["scheduledTimestampUs"],
                "artifacts": artifacts,
            }
        )
    bundle_manifest = {
        "schema": {
            "name": "skyrim-render-map.capture-bundle",
            "major": 1,
            "minor": 0,
        },
        "source": {
            "contract": inspected["contract"],
            "manifestSha256": inspected["manifestSha256"],
            "counts": inspected["counts"],
        },
        "frames": public_frames,
        "omissions": inspected["omissions"],
    }
    manifest_bytes = _canonical_json_bytes(bundle_manifest)
    try:
        validator.scan_public_content(pathlib.Path("bundle-manifest.json"), manifest_bytes)
    except validator.ValidationError as error:
        raise ExportError(f"capture bundle manifest is not publication-safe: {error}") from error
    expanded_bytes = len(manifest_bytes) + sum(source.stat().st_size for _, source in entries)
    try:
        with zipfile.ZipFile(path, "w", allowZip64=True) as archive:
            archive.writestr(_zip_info("bundle-manifest.json"), manifest_bytes)
            for archive_path, source in entries:
                with archive.open(_zip_info(archive_path), "w", force_zip64=True) as target:
                    with source.open("rb") as stream:
                        shutil.copyfileobj(stream, target, length=1024 * 1024)
    except OSError as error:
        raise ExportError(f"cannot write capture bundle: {error}") from error
    return path.stat().st_size, expanded_bytes


def _validate_plan(plan: Any) -> dict:
    plan = _strict_keys(plan, PLAN_KEYS, "plan")
    if plan["schema"] != PLAN_SCHEMA:
        raise ExportError("unsupported capture export plan schema")
    _strict_keys(plan["source"], SOURCE_KEYS, "plan.source")
    if plan["source"]["kind"] != "csx-screenshot-sequence-v1":
        raise ExportError("unsupported capture source kind")
    artifact = _strict_keys(plan["artifact"], ARTIFACT_PLAN_KEYS, "plan.artifact")
    template = artifact["locationTemplate"]
    if not isinstance(template, str) or template.count("{sha256}") != 1:
        raise ExportError("artifact.locationTemplate requires one {sha256} placeholder")
    protocol = _strict_keys(plan["protocol"], PROTOCOL_PLAN_KEYS, "plan.protocol")
    if protocol["timingMode"] not in validator.VISUAL_CAPTURE_TIMING_MODES:
        raise ExportError("plan.protocol.timingMode is unsupported")
    frame_rate = protocol["frameRateHz"]
    if not isinstance(frame_rate, str) or not validator.DECIMAL_PATTERN.fullmatch(frame_rate):
        raise ExportError("plan.protocol.frameRateHz must be a canonical decimal")
    try:
        parsed_frame_rate = decimal.Decimal(frame_rate)
    except decimal.InvalidOperation as error:
        raise ExportError("plan.protocol.frameRateHz must be a canonical decimal") from error
    if not parsed_frame_rate.is_finite() or parsed_frame_rate <= 0:
        raise ExportError("plan.protocol.frameRateHz must be positive")
    _parse_time(plan["recordedAt"], "plan.recordedAt")
    return plan


def _build_records(
    plan_path: pathlib.Path, plan: dict, bundle_path: pathlib.Path
) -> tuple[dict, dict, dict]:
    manifest_path = _resolve_plan_path(plan_path, plan["source"]["manifestPath"])
    inspected = _inspect_manifest(manifest_path)
    byte_length, expanded_length = _write_bundle(bundle_path, inspected)
    bundle_sha = _sha256_file(bundle_path)
    location = plan["artifact"]["locationTemplate"].replace("{sha256}", bundle_sha)
    csx_extensions = [
        item
        for item in plan["runtime"].get("extensions", [])
        if isinstance(item, dict) and item.get("namespace") == "csx"
    ]
    if len(csx_extensions) != 1:
        raise ExportError("plan.runtime requires exactly one CSX extension")
    csx_sha = csx_extensions[0].get("artifactSha256")
    artifact = {
        "schema": {"name": "skyrim-render-map.artifact", "major": 1, "minor": 0},
        "artifactId": plan["artifactId"],
        "artifactSha256": bundle_sha,
        "mediaType": "application/zip",
        "contentKind": inspected["mediaKind"],
        "encoding": "zip",
        "byteLength": byte_length,
        "expandedByteLength": expanded_length,
        "license": plan["artifact"]["license"],
        "retentionClass": plan["artifact"]["retentionClass"],
        "locations": [location],
        "notes": "Deterministic uncompressed capture bundle exported from CSX.",
    }
    issues = []
    if inspected["dropped"]:
        issues.append(f"{inspected['dropped']} scheduled frame slots were dropped")
    if inspected["failed"]:
        issues.append(f"{inspected['failed']} scheduled frame slots failed")
    if inspected["cancelled"]:
        issues.append(f"{inspected['cancelled']} scheduled frame slots were cancelled")
    if inspected["duplicatedFrames"]:
        issues.append(f"{inspected['duplicatedFrames']} engine frame identifiers repeat")
    if inspected["warningCount"]:
        issues.append(f"{inspected['warningCount']} child warnings were reported")
    validity_state = "contaminated" if issues else "valid"
    contamination = []
    full_range = {
        "firstFrame": 0,
        "lastFrame": len(inspected["frames"]) - 1,
    }
    missing_frames = inspected["dropped"] + inspected["failed"] + inspected["cancelled"]
    if missing_frames:
        contamination.append(
            {
                "kind": "dropped-frame",
                **full_range,
                "notes": f"{missing_frames} scheduled frame slots have no retained image.",
            }
        )
    if inspected["duplicatedFrames"]:
        contamination.append(
            {
                "kind": "duplicated-frame",
                **full_range,
                "notes": "At least one engine frame identifier was captured more than once.",
            }
        )
    if inspected["warningCount"]:
        contamination.append(
            {
                "kind": "unknown",
                **full_range,
                "notes": "The source manifest reported one or more child warnings.",
            }
        )
    capture = {
        "schema": {
            "name": "skyrim-render-map.visual-capture-observation",
            "major": 1,
            "minor": 0,
        },
        "captureId": plan["captureId"],
        "recordedAt": _parse_time(plan["recordedAt"], "plan.recordedAt"),
        "map": plan["map"],
        "runtime": plan["runtime"],
        "environment": plan["environment"],
        "scenario": plan["scenario"],
        "treatment": plan["treatment"],
        "protocol": {
            "name": plan["protocol"]["name"],
            "version": plan["protocol"]["version"],
            "artifactSha256": plan["protocol"]["artifactSha256"],
            "captureApi": {
                "name": "csx.screenshot",
                "version": (
                    f"{inspected['contract']['major']}.{inspected['contract']['minor']}"
                    f"-schema.{inspected['contract']['schemaRevision']}"
                ),
                "artifactSha256": csx_sha,
            },
            "sourceKind": inspected["sourceKind"],
            "sourceFallbackApplied": inspected["sourceFallbackApplied"],
            "mediaKind": inspected["mediaKind"],
            "frameCount": len(inspected["frames"]),
            "frameRateHz": plan["protocol"]["frameRateHz"],
            "viewCount": inspected["viewCount"],
            "width": inspected["width"],
            "height": inspected["height"],
            "colorSpace": inspected["colourContract"],
            "pixelFormat": inspected["pixelFormat"],
            "timingMode": plan["protocol"]["timingMode"],
            "droppedFrames": inspected["dropped"],
            "duplicatedFrames": inspected["duplicatedFrames"],
        },
        "captureSha256": bundle_sha,
        "artifactRef": compiler.artifact_ref(plan["submissionId"], plan["artifactId"]),
        "validity": {
            "state": validity_state,
            "contamination": contamination,
            "notes": "; ".join(issues) + ("." if issues else ""),
        },
        "privacy": plan["privacy"],
        "notes": plan["notes"],
    }
    try:
        validator.validate_artifact(artifact, "exported artifact")
        validator.validate_visual_capture(capture, "exported visual capture")
    except validator.ValidationError as error:
        raise ExportError(str(error)) from error
    receipt = {
        "schema": {
            "name": "skyrim-render-map.csx-capture-export-receipt",
            "major": 1,
            "minor": 0,
        },
        "generatedBy": {
            "name": "skyrim-render-map.export-csx-capture",
            "version": TOOL_VERSION,
        },
        "planSha256": _sha256_file(plan_path),
        "sourceManifestSha256": inspected["manifestSha256"],
        "artifactSha256": bundle_sha,
        "artifactFile": f"artifacts/{bundle_sha}.zip",
        "retainedFrameCount": len(inspected["frames"]),
        "droppedFrameCount": inspected["dropped"],
        "validityState": validity_state,
        "containsSourcePaths": False,
    }
    return artifact, capture, receipt


def _write_json(path: pathlib.Path, value: Any) -> None:
    path.write_bytes(_canonical_json_bytes(value))


def _write_jsonl(path: pathlib.Path, records: list[dict]) -> None:
    path.write_text(
        "".join(compiler.canonical_json(record) + "\n" for record in records),
        encoding="utf-8",
        newline="\n",
    )


def export_plan(plan_path: pathlib.Path, output: pathlib.Path) -> dict:
    plan_path = plan_path.resolve()
    plan = _validate_plan(_load_json(plan_path, "capture export plan"))
    output = output.resolve()
    if output.exists():
        raise ExportError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = pathlib.Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent))
    try:
        temporary_bundle = staging / "capture-bundle.zip"
        artifact, capture, receipt = _build_records(plan_path, plan, temporary_bundle)
        artifact_directory = staging / "artifacts"
        artifact_directory.mkdir()
        final_bundle = artifact_directory / f"{artifact['artifactSha256']}.zip"
        temporary_bundle.replace(final_bundle)
        content = staging / "content"
        content.mkdir()
        _write_jsonl(content / "artifacts.jsonl", [artifact])
        _write_jsonl(content / "visual-captures.jsonl", [capture])
        _write_json(
            staging / "public-preview.json",
            {"artifacts": [artifact], "visualCaptures": [capture]},
        )
        _write_json(staging / "export-receipt.json", receipt)
        public_files = (
            item
            for item in staging.rglob("*")
            if item.is_file() and item.suffix != ".zip"
        )
        for path in sorted(public_files):
            validator.scan_public_content(path, path.read_bytes())
        staging.replace(output)
    except OSError as error:
        shutil.rmtree(staging, ignore_errors=True)
        raise ExportError(f"cannot write export: {error}") from error
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = export_plan(args.plan, args.output)
    except (ExportError, validator.ValidationError) as error:
        print(f"export failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
