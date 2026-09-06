#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Treatid2 and contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Export a private optimization run plan into public map records."""

from __future__ import annotations

import argparse
import datetime as dt
import decimal
import hashlib
import json
import math
import pathlib
import shutil
import sys
import tempfile
from typing import Any

import compile_dataset as compiler
import validate_repository as validator


TOOL_VERSION = "1.0.0"
PLAN_SCHEMA = {
    "name": "skyrim-render-map.csx-optimization-export-plan",
    "major": 1,
    "minor": 0,
}
PLAN_KEYS = {
    "schema",
    "submissionId",
    "map",
    "runtime",
    "environment",
    "scenario",
    "privacy",
    "experiment",
    "candidates",
}
EXPERIMENT_KEYS = {
    "experimentId",
    "recordedAt",
    "producer",
    "search",
    "axes",
    "objectives",
    "constraints",
    "notes",
}
OBJECTIVE_PLAN_KEYS = {
    "objectiveId",
    "label",
    "metric",
    "unit",
    "direction",
    "scope",
    "scopeRefs",
    "reducer",
    "dominanceEpsilon",
    "collection",
}
COLLECTION_KEYS = {"sourceKind", "metricSource", "timerName", "protocol"}
CANDIDATE_PLAN_KEYS = {
    "candidateId",
    "label",
    "treatmentSha256",
    "baselineObservationRef",
    "outcome",
    "failureKind",
    "parameters",
    "objectiveRuns",
    "notes",
}
OBJECTIVE_RUN_KEYS = {"objectiveId", "runs"}
RUN_KEYS = {"observationId", "recordedAt", "source", "validity", "notes"}
PROFILER_SOURCE_KEYS = {"kind", "rawPath", "summaryPath"}
INLINE_SOURCE_KEYS = {"kind", "samples"}
PROFILER_METRICS = {
    "resolved-gpu-total": ("resolvedTotalMs", None, "gpu"),
    "resolved-cpu-total": ("resolvedCpuTotalMs", None, "cpu"),
    "timer-gpu": ("gpuMs", "timers", "gpu"),
    "timer-cpu": ("cpuMs", "timers", "cpu"),
    "timer-top-level": ("topLevelMs", "timers", "gpu"),
}


class ExportError(RuntimeError):
    pass


def _strict_keys(value: Any, expected: set[str], context: str) -> dict:
    if not isinstance(value, dict):
        raise ExportError(f"{context} must be an object")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ExportError(f"{context} keys mismatch; missing={missing}, extra={extra}")
    return value


def _load_json(path: pathlib.Path, context: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ExportError(f"cannot read {context}: {error}") from error


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: pathlib.Path) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError as error:
        raise ExportError(f"cannot hash source artifact: {error}") from error


def _decimal_string(value: Any, context: str) -> str:
    if isinstance(value, bool):
        raise ExportError(f"{context} must be a finite non-negative number")
    try:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("non-finite")
        parsed = decimal.Decimal(str(value))
    except (decimal.InvalidOperation, ValueError) as error:
        raise ExportError(f"{context} must be a finite non-negative number") from error
    if not parsed.is_finite() or parsed < 0:
        raise ExportError(f"{context} must be a finite non-negative number")
    with decimal.localcontext() as local:
        local.prec = 64
        parsed = parsed.quantize(
            decimal.Decimal("0.000000001"), rounding=decimal.ROUND_HALF_EVEN
        )
    if parsed == 0:
        return "0"
    text = format(parsed.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _parse_time(value: Any, context: str) -> dt.datetime:
    if not isinstance(value, str):
        raise ExportError(f"{context} must be an RFC 3339 timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ExportError(f"{context} must be an RFC 3339 timestamp") from error
    if parsed.tzinfo is None:
        raise ExportError(f"{context} must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def _resolve_source_path(
    plan_path: pathlib.Path, value: Any, context: str
) -> pathlib.Path:
    if not isinstance(value, str) or not value.strip():
        raise ExportError(f"{context} must be a non-empty path")
    candidate = pathlib.Path(value)
    if not candidate.is_absolute():
        candidate = plan_path.parent / candidate
    resolved = candidate.resolve()
    if not resolved.is_file():
        raise ExportError(f"{context} is not a file")
    return resolved


def _find_timer(record: dict, timer_name: str, context: str) -> dict:
    timers = record.get("timers")
    if not isinstance(timers, list):
        raise ExportError(f"{context}.timers must be an array")
    matches = [
        item
        for item in timers
        if isinstance(item, dict) and item.get("name") == timer_name
    ]
    if len(matches) != 1:
        raise ExportError(
            f"{context} must contain exactly one timer named {timer_name!r}"
        )
    return matches[0]


def _verify_profiler_summary(
    summary: dict,
    raw: list,
    candidate: dict,
    objective: dict,
    runtime: dict,
    context: str,
) -> None:
    if summary.get("schemaVersion") != 3:
        raise ExportError(f"{context} requires CSX profiler summary schemaVersion 3")
    if summary.get("profilerStateRestored") is not True:
        raise ExportError(f"{context} did not restore the profiler state")
    if not isinstance(raw, list) or not raw:
        raise ExportError(f"{context} raw capture must be a non-empty array")
    requested = summary.get("requestedSamples")
    collected = summary.get("collectedSamples")
    unique = summary.get("uniqueFreshFrames")
    if requested != len(raw) or collected != len(raw) or unique != len(raw):
        raise ExportError(f"{context} does not contain its complete fresh-frame set")
    protocol = objective["collection"]["protocol"]
    if protocol["requestedSamples"] != requested:
        raise ExportError(f"{context} requestedSamples differs from the export plan")
    if protocol["warmupSamples"] != summary.get("warmupSamples"):
        raise ExportError(f"{context} warmupSamples differs from the export plan")
    cadence = protocol["sampleCadence"]
    if cadence.get("mode") != "wall-clock-ms":
        raise ExportError(f"{context} profiler capture requires wall-clock-ms cadence")
    expected_interval = _decimal_string(
        summary.get("intervalMs"), f"{context}.intervalMs"
    )
    if cadence.get("value") != expected_interval:
        raise ExportError(f"{context} intervalMs differs from the export plan")

    context_fingerprint = summary.get("contextFingerprint")
    treatment_fingerprint = summary.get("treatmentFingerprint")
    if not isinstance(context_fingerprint, str) or not context_fingerprint:
        raise ExportError(f"{context} has no context fingerprint")
    expected_treatment = candidate["treatmentSha256"].lower()
    if (
        not isinstance(treatment_fingerprint, str)
        or treatment_fingerprint.lower() != expected_treatment
    ):
        raise ExportError(f"{context} treatment fingerprint differs from the candidate")
    frames: set[int] = set()
    for index, record in enumerate(raw):
        item_context = f"{context}.raw[{index}]"
        if not isinstance(record, dict):
            raise ExportError(f"{item_context} must be an object")
        if record.get("contextFingerprint") != context_fingerprint:
            raise ExportError(f"{item_context} context fingerprint changed")
        observed_treatment = record.get("treatmentFingerprint")
        if (
            not isinstance(observed_treatment, str)
            or observed_treatment.lower() != expected_treatment
        ):
            raise ExportError(f"{item_context} treatment fingerprint changed")
        frame = record.get("frame")
        if not isinstance(frame, int) or isinstance(frame, bool) or frame < 0:
            raise ExportError(f"{item_context}.frame must be a non-negative integer")
        if frame in frames:
            raise ExportError(f"{context} repeats frame {frame}")
        frames.add(frame)

    csx_extensions = [
        item for item in runtime["extensions"] if item["namespace"] == "csx"
    ]
    if len(csx_extensions) != 1:
        raise ExportError(f"{context} requires exactly one CSX runtime extension")
    runtime_identity = summary.get("runtimeIdentity")
    if not isinstance(runtime_identity, dict):
        raise ExportError(f"{context} has no runtime identity")
    artifact = runtime_identity.get("artifact")
    observed_artifact = artifact.get("sha256") if isinstance(artifact, dict) else None
    expected_artifact = csx_extensions[0]["artifactSha256"].lower()
    if (
        not isinstance(observed_artifact, str)
        or observed_artifact.lower() != expected_artifact
    ):
        raise ExportError(f"{context} CSX artifact differs from the export plan")


def _profiler_samples(
    raw: list,
    objective: dict,
    context: str,
) -> list[dict]:
    collection = objective["collection"]
    metric_source = collection["metricSource"]
    if metric_source not in PROFILER_METRICS:
        raise ExportError(f"{context} has unsupported profiler metricSource")
    if objective["unit"] != "milliseconds":
        raise ExportError(f"{context} profiler sources require milliseconds")
    field, container, activity = PROFILER_METRICS[metric_source]
    timer_name = collection["timerName"]
    if container is None and timer_name is not None:
        raise ExportError(f"{context} total metric cannot specify timerName")
    if container is not None and (not isinstance(timer_name, str) or not timer_name):
        raise ExportError(f"{context} timer metric requires timerName")

    timestamps = [
        _parse_time(record.get("timestampUtc"), f"{context}.raw[{index}].timestampUtc")
        for index, record in enumerate(raw)
    ]
    first_timestamp = timestamps[0]
    result = []
    for index, (record, timestamp) in enumerate(zip(raw, timestamps)):
        source = (
            record
            if container is None
            else _find_timer(record, timer_name, context)
        )
        if container is not None:
            active_key = "activeGpu" if activity == "gpu" else "activeCpu"
            present_key = "hasGpu" if activity == "gpu" else "hasCpu"
            if (
                source.get(active_key) is not True
                or source.get(present_key) is not True
            ):
                raise ExportError(
                    f"{context} timer {timer_name!r} is not active and resolved"
                )
        offset = (timestamp - first_timestamp).total_seconds() * 1000
        result.append(
            {
                "sequence": index,
                "value": _decimal_string(source.get(field), f"{context}.{field}"),
                "frame": record["frame"],
                "timestampOffsetMs": _decimal_string(
                    offset, f"{context}.timestampOffsetMs"
                ),
            }
        )
    return result


def _inline_samples(source: dict, context: str) -> list[dict]:
    samples = source["samples"]
    if not isinstance(samples, list) or not samples:
        raise ExportError(f"{context}.samples must be a non-empty array")
    result = json.loads(json.dumps(samples))
    return result


def _build_observation(
    plan_path: pathlib.Path,
    plan: dict,
    candidate: dict,
    objective: dict,
    run: dict,
    source_hashes: set[str],
    context_fingerprints: set[str],
) -> dict:
    context = f"candidate {candidate['candidateId']} observation {run['observationId']}"
    _strict_keys(run, RUN_KEYS, context)
    source = run["source"]
    if not isinstance(source, dict):
        raise ExportError(f"{context}.source must be an object")
    source_kind = objective["collection"]["sourceKind"]
    if source_kind == "csx-profiler-v3":
        _strict_keys(source, PROFILER_SOURCE_KEYS, f"{context}.source")
        if source["kind"] != source_kind:
            raise ExportError(
                f"{context}.source kind differs from the objective collection"
            )
        raw_path = _resolve_source_path(
            plan_path, source["rawPath"], f"{context}.rawPath"
        )
        summary_path = _resolve_source_path(
            plan_path, source["summaryPath"], f"{context}.summaryPath"
        )
        raw = _load_json(raw_path, f"{context} raw capture")
        summary = _load_json(summary_path, f"{context} summary")
        if not isinstance(summary, dict):
            raise ExportError(f"{context} summary must be an object")
        _verify_profiler_summary(
            summary, raw, candidate, objective, plan["runtime"], context
        )
        context_fingerprints.add(summary["contextFingerprint"])
        source_hashes.update({_sha256_file(raw_path), _sha256_file(summary_path)})
        samples = _profiler_samples(raw, objective, context)
        recorded_at = summary.get("startedUtc")
        if run["recordedAt"] is not None and run["recordedAt"] != recorded_at:
            raise ExportError(f"{context}.recordedAt differs from the profiler summary")
    elif source_kind == "inline-v1":
        _strict_keys(source, INLINE_SOURCE_KEYS, f"{context}.source")
        if source["kind"] != source_kind:
            raise ExportError(
                f"{context}.source kind differs from the objective collection"
            )
        samples = _inline_samples(source, context)
        recorded_at = run["recordedAt"]
        if recorded_at is None:
            raise ExportError(f"{context}.recordedAt is required for inline samples")
    else:
        raise ExportError(f"{context} has unsupported sourceKind")

    _parse_time(recorded_at, f"{context}.recordedAt")
    treatment = {
        "label": candidate["label"],
        "treatmentSha256": candidate["treatmentSha256"],
        "baselineObservationRef": candidate["baselineObservationRef"],
    }
    observation = {
        "schema": {
            "name": "skyrim-render-map.performance-observation",
            "major": 1,
            "minor": 0,
        },
        "observationId": run["observationId"],
        "recordedAt": recorded_at,
        "map": plan["map"],
        "runtime": plan["runtime"],
        "environment": plan["environment"],
        "protocol": objective["collection"]["protocol"],
        "scenario": plan["scenario"],
        "treatment": treatment,
        "measurement": {
            "metric": objective["metric"],
            "unit": objective["unit"],
            "scope": objective["scope"],
            "scopeRefs": objective["scopeRefs"],
            "samples": samples,
        },
        "validity": run["validity"],
        "privacy": plan["privacy"],
        "notes": run["notes"],
    }
    try:
        validator.validate_performance_observation(observation, context)
    except validator.ValidationError as error:
        raise ExportError(str(error)) from error
    return observation


def _build_records(
    plan_path: pathlib.Path, plan: dict
) -> tuple[list[dict], dict, dict]:
    _strict_keys(plan, PLAN_KEYS, "plan")
    if plan["schema"] != PLAN_SCHEMA:
        raise ExportError("unsupported optimization export plan schema")
    if (
        not isinstance(plan["submissionId"], str)
        or not validator.SUBMISSION_PATTERN.fullmatch(plan["submissionId"])
    ):
        raise ExportError("plan.submissionId is invalid")
    experiment_plan = _strict_keys(plan["experiment"], EXPERIMENT_KEYS, "experiment")
    if not isinstance(experiment_plan["objectives"], list) or not experiment_plan[
        "objectives"
    ]:
        raise ExportError("experiment.objectives must be a non-empty array")
    objectives: dict[str, dict] = {}
    public_objectives = []
    for index, objective in enumerate(experiment_plan["objectives"]):
        context = f"experiment.objectives[{index}]"
        _strict_keys(objective, OBJECTIVE_PLAN_KEYS, context)
        collection = _strict_keys(
            objective["collection"], COLLECTION_KEYS, f"{context}.collection"
        )
        if collection["sourceKind"] not in {"csx-profiler-v3", "inline-v1"}:
            raise ExportError(f"{context}.collection.sourceKind is unsupported")
        if collection["sourceKind"] == "inline-v1" and (
            collection["metricSource"] is not None
            or collection["timerName"] is not None
        ):
            raise ExportError(
                f"{context}.collection inline source cannot select a profiler metric"
            )
        if objective["objectiveId"] in objectives:
            raise ExportError(f"duplicate objectiveId {objective['objectiveId']!r}")
        objectives[objective["objectiveId"]] = objective
        public_objectives.append(
            {key: value for key, value in objective.items() if key != "collection"}
        )

    performance_records: list[dict] = []
    public_candidates: list[dict] = []
    observation_ids: set[str] = set()
    source_hashes: set[str] = set()
    context_fingerprints: set[str] = set()
    candidates = plan["candidates"]
    if not isinstance(candidates, list) or not candidates:
        raise ExportError("plan.candidates must be a non-empty array")
    for index, candidate in enumerate(candidates):
        context = f"candidates[{index}]"
        _strict_keys(candidate, CANDIDATE_PLAN_KEYS, context)
        if not isinstance(candidate["objectiveRuns"], list):
            raise ExportError(f"{context}.objectiveRuns must be an array")
        objective_refs = []
        objective_run_ids: set[str] = set()
        for run_group_index, run_group in enumerate(candidate["objectiveRuns"]):
            group_context = f"{context}.objectiveRuns[{run_group_index}]"
            _strict_keys(run_group, OBJECTIVE_RUN_KEYS, group_context)
            objective_id = run_group["objectiveId"]
            if objective_id not in objectives or objective_id in objective_run_ids:
                raise ExportError(
                    f"{group_context} has unknown or duplicate objectiveId"
                )
            objective_run_ids.add(objective_id)
            references = []
            runs = run_group["runs"]
            if not isinstance(runs, list) or not runs:
                raise ExportError(f"{group_context}.runs must be a non-empty array")
            for run in runs:
                observation = _build_observation(
                    plan_path,
                    plan,
                    candidate,
                    objectives[objective_id],
                    run,
                    source_hashes,
                    context_fingerprints,
                )
                observation_id = observation["observationId"]
                if observation_id in observation_ids:
                    raise ExportError(f"duplicate observationId {observation_id!r}")
                observation_ids.add(observation_id)
                performance_records.append(observation)
                references.append(
                    "urn:skyrim-render-map:submission:"
                    f"{plan['submissionId']}#{observation_id}"
                )
            objective_refs.append(
                {"objectiveId": objective_id, "observationRefs": references}
            )
        public_candidates.append(
            {
                "candidateId": candidate["candidateId"],
                "label": candidate["label"],
                "treatmentSha256": candidate["treatmentSha256"],
                "outcome": candidate["outcome"],
                "failureKind": candidate["failureKind"],
                "parameters": candidate["parameters"],
                "objectiveObservations": objective_refs,
                "notes": candidate["notes"],
            }
        )

    if len(context_fingerprints) > 1:
        raise ExportError(
            "profiler captures mix runtime/environment context fingerprints"
        )
    experiment = {
        "schema": {
            "name": "skyrim-render-map.optimization-experiment",
            "major": 1,
            "minor": 0,
        },
        "experimentId": experiment_plan["experimentId"],
        "recordedAt": experiment_plan["recordedAt"],
        "map": plan["map"],
        "producer": experiment_plan["producer"],
        "search": experiment_plan["search"],
        "axes": experiment_plan["axes"],
        "objectives": public_objectives,
        "constraints": experiment_plan["constraints"],
        "candidates": public_candidates,
        "notes": experiment_plan["notes"],
    }
    first_objective = objectives[next(iter(objectives))]
    first_candidate = candidates[0]
    common_probe = {
        "schema": {
            "name": "skyrim-render-map.performance-observation",
            "major": 1,
            "minor": 0,
        },
        "observationId": "export-plan-common-probe",
        "recordedAt": experiment_plan["recordedAt"],
        "map": plan["map"],
        "runtime": plan["runtime"],
        "environment": plan["environment"],
        "protocol": first_objective["collection"]["protocol"],
        "scenario": plan["scenario"],
        "treatment": {
            "label": first_candidate["label"],
            "treatmentSha256": first_candidate["treatmentSha256"],
            "baselineObservationRef": first_candidate["baselineObservationRef"],
        },
        "measurement": {
            "metric": first_objective["metric"],
            "unit": first_objective["unit"],
            "scope": first_objective["scope"],
            "scopeRefs": first_objective["scopeRefs"],
            "samples": [
                {"sequence": 0, "value": "0", "frame": None, "timestampOffsetMs": "0"}
            ],
        },
        "validity": {"state": "valid", "contamination": [], "notes": ""},
        "privacy": plan["privacy"],
        "notes": "Export-plan common-field validation probe.",
    }
    try:
        validator.validate_performance_observation(common_probe, "plan common fields")
        validator.validate_optimization_experiment(experiment, "experiment")
    except validator.ValidationError as error:
        raise ExportError(str(error)) from error

    wrapped_performance = []
    for record in performance_records:
        reference = compiler.performance_ref(
            plan["submissionId"], record["observationId"]
        )
        wrapped_performance.append(
            {
                "ref": reference,
                "submissionId": plan["submissionId"],
                "comparisonKey": compiler.content_id(
                    "comparison-key",
                    compiler.normalize_performance_context(
                        record, include_installation=True
                    ),
                ),
                "aggregateKey": "not-used-by-export-validation",
                "aggregateEligible": record["validity"]["state"] == "valid",
                "summary": compiler.performance_summary(record),
                "record": record,
            }
        )
    experiment_ref = compiler.optimization_ref(
        plan["submissionId"], experiment["experimentId"]
    )
    try:
        _, surfaces = compiler.compile_optimization_surfaces(
            [
                {
                    "ref": experiment_ref,
                    "submissionId": plan["submissionId"],
                    "record": experiment,
                }
            ],
            {item["ref"]: item for item in wrapped_performance},
        )
    except compiler.CompileError as error:
        raise ExportError(str(error)) from error
    receipt = {
        "schema": {
            "name": "skyrim-render-map.optimization-export-receipt",
            "major": 1,
            "minor": 0,
        },
        "generatedBy": {
            "name": "skyrim-render-map.export-optimization-run",
            "version": TOOL_VERSION,
        },
        "planSha256": _sha256_file(plan_path),
        "sourceArtifactSha256": sorted(source_hashes),
        "performanceObservationCount": len(performance_records),
        "optimizationExperimentCount": 1,
        "derivedPreview": surfaces[0],
        "containsSourcePaths": False,
    }
    return performance_records, experiment, receipt


def _write_json(path: pathlib.Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl(path: pathlib.Path, records: list[dict]) -> None:
    text = "".join(_canonical_json(record) + "\n" for record in records)
    path.write_text(text, encoding="utf-8", newline="\n")


def export_plan(plan_path: pathlib.Path, output: pathlib.Path) -> dict:
    plan_path = plan_path.resolve()
    plan = _load_json(plan_path, "optimization export plan")
    performance_records, experiment, receipt = _build_records(plan_path, plan)
    output = output.resolve()
    if output.exists():
        raise ExportError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = pathlib.Path(
        tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent)
    )
    try:
        content = staging / "content"
        content.mkdir(parents=True)
        _write_jsonl(content / "performance-observations.jsonl", performance_records)
        _write_jsonl(content / "optimization-experiments.jsonl", [experiment])
        _write_json(
            staging / "public-preview.json",
            {
                "performanceObservations": performance_records,
                "optimizationExperiments": [experiment],
            },
        )
        _write_json(staging / "export-receipt.json", receipt)
        for path in sorted(item for item in staging.rglob("*") if item.is_file()):
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
