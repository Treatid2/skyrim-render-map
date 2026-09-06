#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Treatid2 and contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Compile immutable submissions into a deterministic semantic snapshot."""

from __future__ import annotations

import argparse
import decimal
import hashlib
import json
import pathlib
import sys
from typing import Any

import validate_repository as validator


TOOL_VERSION = "1.3.0"


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


def performance_ref(submission_id: str, observation_id: str) -> str:
    return (
        "urn:skyrim-render-map:submission:"
        f"{submission_id}#{observation_id}"
    )


def optimization_ref(submission_id: str, experiment_id: str) -> str:
    return (
        "urn:skyrim-render-map:submission:"
        f"{submission_id}#{experiment_id}"
    )


def candidate_ref(experiment_reference: str, candidate_id: str) -> str:
    return f"{experiment_reference}/{candidate_id}"


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


def _lower_digest(value: str | None) -> str | None:
    return value.lower() if value is not None else None


def normalize_performance_context(record: dict, *, include_installation: bool) -> dict:
    environment = record["environment"]
    render_context = environment["renderContext"]
    normalized_environment = {
        "cpuModel": environment["cpuModel"],
        "gpuModel": environment["gpuModel"],
        "gpuDriverVersion": environment["gpuDriverVersion"],
        "renderContext": {
            **render_context,
            "refreshRateHz": _decimal_string(
                decimal.Decimal(render_context["refreshRateHz"])
            ),
            "renderScale": _decimal_string(
                decimal.Decimal(render_context["renderScale"])
            ),
            "targetFrameRate": (
                _decimal_string(decimal.Decimal(render_context["targetFrameRate"]))
                if render_context["targetFrameRate"] is not None
                else None
            ),
        },
    }
    if include_installation:
        normalized_environment["installationId"] = environment["installationId"]
    runtime = record["runtime"]
    return {
        "map": {
            "mapSnapshotId": record["map"]["mapSnapshotId"],
            "nodeRefs": sorted(record["map"]["nodeRefs"]),
        },
        "runtime": {
            "engine": {
                "runtime": runtime["engine"]["runtime"],
                "executableSha256": runtime["engine"]["executableSha256"].lower(),
                "moduleSha256": _lower_digest(runtime["engine"]["moduleSha256"]),
            },
            "extensions": sorted(
                (
                    {
                        "namespace": item["namespace"],
                        "sourceCommit": _lower_digest(item["sourceCommit"]),
                        "buildId": item["buildId"],
                        "artifactSha256": item["artifactSha256"].lower(),
                    }
                    for item in runtime["extensions"]
                ),
                key=lambda item: item["namespace"],
            ),
            "runtimeRoute": runtime["runtimeRoute"],
        },
        "environment": normalized_environment,
        "protocol": {
            **record["protocol"],
            "artifactSha256": record["protocol"]["artifactSha256"].lower(),
            "tools": sorted(
                (
                    {
                        **item,
                        "artifactSha256": item["artifactSha256"].lower(),
                    }
                    for item in record["protocol"]["tools"]
                ),
                key=lambda item: item["name"],
            ),
        },
        "scenario": {
            "scenarioSha256": record["scenario"]["scenarioSha256"].lower(),
            "configurationSha256": record["scenario"]["configurationSha256"].lower(),
            "cacheSha256": record["scenario"]["cacheSha256"].lower(),
        },
        "measurement": {
            "metric": record["measurement"]["metric"],
            "unit": record["measurement"]["unit"],
            "scope": record["measurement"]["scope"],
            "scopeRefs": sorted(record["measurement"]["scopeRefs"]),
        },
    }


def _decimal_string(value: decimal.Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _median(values: list[decimal.Decimal]) -> decimal.Decimal:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / decimal.Decimal(2)


def performance_summary(record: dict) -> dict:
    values = [decimal.Decimal(item["value"]) for item in record["measurement"]["samples"]]
    with decimal.localcontext() as context:
        context.prec = 64
        mean = sum(values, decimal.Decimal(0)) / decimal.Decimal(len(values))
        mean = mean.quantize(
            decimal.Decimal("0.000000001"), rounding=decimal.ROUND_HALF_EVEN
        )
    return {
        "sampleCount": len(values),
        "minimum": _decimal_string(min(values)),
        "maximum": _decimal_string(max(values)),
        "median": _decimal_string(_median(values)),
        "arithmeticMean": _decimal_string(mean),
    }


def _compile_performance_groups(
    observations: list[dict],
) -> tuple[list[dict], list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for observation in observations:
        if observation["aggregateEligible"]:
            grouped.setdefault(observation["aggregateKey"], []).append(observation)

    groups: list[dict] = []
    signals: list[dict] = []
    for aggregate_key, members in sorted(grouped.items()):
        ordered = sorted(members, key=lambda item: item["ref"])
        medians = [decimal.Decimal(item["summary"]["median"]) for item in ordered]
        installations = {
            item["record"]["environment"]["installationId"] for item in ordered
        }
        evaluation = "insufficient-sample"
        lower_fence: decimal.Decimal | None = None
        upper_fence: decimal.Decimal | None = None
        if len(ordered) >= 5 and len(installations) >= 3:
            sorted_medians = sorted(medians)
            midpoint = len(sorted_medians) // 2
            lower_half = sorted_medians[:midpoint]
            upper_half = sorted_medians[midpoint + (len(sorted_medians) % 2) :]
            first_quartile = _median(lower_half)
            third_quartile = _median(upper_half)
            interquartile_range = third_quartile - first_quartile
            if interquartile_range == 0:
                evaluation = "insufficient-dispersion"
            else:
                evaluation = "evaluated"
                lower_fence = max(
                    decimal.Decimal(0),
                    first_quartile - decimal.Decimal(3) * interquartile_range,
                )
                upper_fence = third_quartile + decimal.Decimal(3) * interquartile_range
                for observation, observation_median in zip(ordered, medians):
                    if observation_median < lower_fence or observation_median > upper_fence:
                        identity = {
                            "kind": "measurement-outlier",
                            "aggregateKey": aggregate_key,
                            "observationRef": observation["ref"],
                        }
                        signals.append(
                            {
                                "signalId": content_id("signal", identity),
                                **identity,
                                "observedMedian": _decimal_string(observation_median),
                                "lowerFence": _decimal_string(lower_fence),
                                "upperFence": _decimal_string(upper_fence),
                                "state": "open",
                            }
                        )
        groups.append(
            {
                "aggregateKey": aggregate_key,
                "observationRefs": [item["ref"] for item in ordered],
                "observationCount": len(ordered),
                "installationCount": len(installations),
                "medianOfObservationMedians": _decimal_string(_median(medians)),
                "outlierEvaluation": evaluation,
                "lowerFence": (
                    _decimal_string(lower_fence) if lower_fence is not None else None
                ),
                "upperFence": (
                    _decimal_string(upper_fence) if upper_fence is not None else None
                ),
            }
        )
    return groups, sorted(signals, key=lambda item: item["signalId"])


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
) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict], list[dict]]:
    submissions: list[dict] = []
    entities: list[dict] = []
    assertions: list[dict] = []
    resolutions: list[dict] = []
    performance_observations: list[dict] = []
    optimization_experiments: list[dict] = []
    for directory in validator.submission_directories(repository):
        manifest = validator.load_json_document(directory / "submission.json")
        if not isinstance(manifest, dict):
            raise CompileError(f"submission manifest is not an object: {directory}")
        submission_id = manifest["submissionId"]
        (
            entity_records,
            assertion_records,
            resolution_records,
            performance_records,
            optimization_records,
        ) = validator.load_submission_records(directory, manifest["submissionClass"])
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
                "performanceObservationCount": len(performance_records),
                "optimizationExperimentCount": len(optimization_records),
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
        for record in performance_records:
            reference = performance_ref(submission_id, record["observationId"])
            comparison_context = normalize_performance_context(
                record, include_installation=True
            )
            aggregate_context = normalize_performance_context(
                record, include_installation=False
            )
            performance_observations.append(
                {
                    "ref": reference,
                    "submissionId": submission_id,
                    "comparisonKey": content_id("comparison-key", comparison_context),
                    "aggregateKey": content_id(
                        "aggregate-key",
                        {
                            **aggregate_context,
                            "treatmentSha256": record["treatment"][
                                "treatmentSha256"
                            ].lower(),
                        },
                    ),
                    "aggregateEligible": record["validity"]["state"] == "valid",
                    "summary": performance_summary(record),
                    "record": record,
                }
            )
        for record in optimization_records:
            optimization_experiments.append(
                {
                    "ref": optimization_ref(submission_id, record["experimentId"]),
                    "submissionId": submission_id,
                    "record": record,
                }
            )
    return (
        submissions,
        entities,
        assertions,
        resolutions,
        performance_observations,
        optimization_experiments,
    )


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


def _normalized_parameter_vector(record: dict, candidate: dict) -> list[dict]:
    axes = {item["axisId"]: item for item in record["axes"]}
    result = []
    for parameter in sorted(candidate["parameters"], key=lambda item: item["axisId"]):
        value = parameter["value"]
        if axes[parameter["axisId"]]["valueType"] == "decimal":
            value = _decimal_string(decimal.Decimal(value))
        result.append({"axisId": parameter["axisId"], "value": value})
    return result


def _observation_matches_objective(observation: dict, objective: dict) -> bool:
    measurement = observation["record"]["measurement"]
    return (
        measurement["metric"] == objective["metric"]
        and measurement["unit"] == objective["unit"]
        and measurement["scope"] == objective["scope"]
        and sorted(measurement["scopeRefs"]) == sorted(objective["scopeRefs"])
    )


def _dominates(left: dict, right: dict, objectives: dict[str, dict]) -> bool:
    left_values = {
        item["objectiveId"]: decimal.Decimal(item["value"])
        for item in left["objectiveValues"]
    }
    right_values = {
        item["objectiveId"]: decimal.Decimal(item["value"])
        for item in right["objectiveValues"]
    }
    strictly_better = False
    for objective_id, objective in objectives.items():
        left_value = left_values[objective_id]
        right_value = right_values[objective_id]
        epsilon = decimal.Decimal(objective["dominanceEpsilon"])
        if objective["direction"] == "minimize":
            if left_value > right_value + epsilon:
                return False
            strictly_better = strictly_better or left_value < right_value - epsilon
        else:
            if left_value < right_value - epsilon:
                return False
            strictly_better = strictly_better or left_value > right_value + epsilon
    return strictly_better


def compile_optimization_surfaces(
    experiments: list[dict], performance_by_ref: dict[str, dict]
) -> tuple[list[dict], list[dict]]:
    compiled_experiments: list[dict] = []
    surfaces: list[dict] = []
    for experiment in sorted(experiments, key=lambda item: item["ref"]):
        record = experiment["record"]
        experiment_ref = experiment["ref"]
        objectives = {
            item["objectiveId"]: item for item in record["objectives"]
        }
        objective_contexts: dict[str, str] = {}
        used_observations: set[str] = set()
        compiled_candidates: list[dict] = []
        for candidate in sorted(
            record["candidates"], key=lambda item: item["candidateId"]
        ):
            reference = candidate_ref(experiment_ref, candidate["candidateId"])
            parameters = _normalized_parameter_vector(record, candidate)
            assignments = {
                item["objectiveId"]: item["observationRefs"]
                for item in candidate["objectiveObservations"]
            }
            objective_values: list[dict] = []
            exclusion_reasons: list[str] = []
            if candidate["outcome"] != "completed":
                exclusion_reasons.append(f"outcome-{candidate['outcome']}")
            for objective_id, objective in sorted(objectives.items()):
                observation_refs = assignments.get(objective_id, [])
                if not observation_refs:
                    exclusion_reasons.append(f"missing-objective-{objective_id}")
                    continue
                linked: list[dict] = []
                for observation_ref in observation_refs:
                    if observation_ref in used_observations:
                        raise CompileError(
                            f"optimization experiment {experiment_ref} reuses "
                            f"performance observation {observation_ref}"
                        )
                    used_observations.add(observation_ref)
                    observation = performance_by_ref.get(observation_ref)
                    if observation is None:
                        raise CompileError(
                            f"optimization experiment {experiment_ref} references "
                            f"unknown performance observation {observation_ref}"
                        )
                    observation_record = observation["record"]
                    if (
                        observation_record["map"]["mapSnapshotId"]
                        != record["map"]["mapSnapshotId"]
                        or not set(observation_record["map"]["nodeRefs"]).issubset(
                            record["map"]["nodeRefs"]
                        )
                    ):
                        raise CompileError(
                            f"optimization experiment {experiment_ref} has a map "
                            f"mismatch at {observation_ref}"
                        )
                    if (
                        observation_record["treatment"]["treatmentSha256"].lower()
                        != candidate["treatmentSha256"].lower()
                    ):
                        raise CompileError(
                            f"optimization candidate {reference} has a treatment "
                            f"mismatch at {observation_ref}"
                        )
                    if not _observation_matches_objective(observation, objective):
                        raise CompileError(
                            f"optimization objective {objective_id} does not match "
                            f"performance observation {observation_ref}"
                        )
                    context_key = observation["comparisonKey"]
                    prior_context = objective_contexts.setdefault(
                        objective_id, context_key
                    )
                    if prior_context != context_key:
                        raise CompileError(
                            f"optimization objective {objective_id} mixes "
                            "incomparable performance contexts"
                        )
                    linked.append(observation)
                if not all(item["aggregateEligible"] for item in linked):
                    exclusion_reasons.append(f"non-valid-objective-{objective_id}")
                    continue
                objective_value = _median(
                    [decimal.Decimal(item["summary"]["median"]) for item in linked]
                )
                objective_values.append(
                    {
                        "objectiveId": objective_id,
                        "value": _decimal_string(objective_value),
                        "observationRefs": sorted(observation_refs),
                    }
                )

            constraint_violations: list[str] = []
            feasible: bool | None = None
            if len(objective_values) == len(objectives):
                values = {
                    item["objectiveId"]: decimal.Decimal(item["value"])
                    for item in objective_values
                }
                for constraint in record["constraints"]:
                    value = values[constraint["objectiveId"]]
                    threshold = decimal.Decimal(constraint["threshold"])
                    violated = (
                        value > threshold
                        if constraint["operator"] == "at-most"
                        else value < threshold
                    )
                    if violated:
                        constraint_violations.append(constraint["constraintId"])
                feasible = not constraint_violations
            compiled_candidates.append(
                {
                    "ref": reference,
                    "candidateId": candidate["candidateId"],
                    "treatmentSha256": candidate["treatmentSha256"].lower(),
                    "parameterVectorSha256": hashlib.sha256(
                        canonical_json(parameters).encode("utf-8")
                    ).hexdigest(),
                    "parameters": parameters,
                    "objectiveValues": objective_values,
                    "eligibility": (
                        "eligible" if not exclusion_reasons else "excluded"
                    ),
                    "exclusionReasons": sorted(set(exclusion_reasons)),
                    "feasible": feasible,
                    "constraintViolations": sorted(constraint_violations),
                    "dominatedBy": [],
                }
            )

        eligible_candidates = [
            item
            for item in compiled_candidates
            if item["eligibility"] == "eligible"
        ]
        pareto_candidates = [
            item for item in eligible_candidates if item["feasible"] is True
        ]
        for candidate in pareto_candidates:
            candidate["dominatedBy"] = sorted(
                other["ref"]
                for other in pareto_candidates
                if other["ref"] != candidate["ref"]
                and _dominates(other, candidate, objectives)
            )
        frontier = sorted(
            item["ref"] for item in pareto_candidates if not item["dominatedBy"]
        )
        surface_identity = {
            "experimentRef": experiment_ref,
            "candidates": compiled_candidates,
        }
        surfaces.append(
            {
                "surfaceId": content_id("pareto-surface", surface_identity),
                "experimentRef": experiment_ref,
                "state": "derived" if frontier else "insufficient-evidence",
                "candidateCount": len(compiled_candidates),
                "eligibleCandidateCount": len(eligible_candidates),
                "feasibleCandidateCount": len(pareto_candidates),
                "frontierCandidateRefs": frontier,
                "candidates": compiled_candidates,
            }
        )
        compiled_experiments.append(experiment)
    return compiled_experiments, surfaces


def _structural_submission_projection(submission: dict) -> dict:
    fields = (
        "submissionId",
        "submissionClass",
        "namespace",
        "status",
        "createdAt",
        "sourceRepository",
        "sourceCommit",
        "contentTreeSha256",
        "entityCount",
        "assertionCount",
        "resolutionCount",
        "performanceObservationCount",
    )
    return {field: submission[field] for field in fields}


def compile_repository(repository: pathlib.Path, source_revision: str | None = None) -> dict:
    validator.validate_repository(repository)
    (
        submissions,
        entities,
        assertions,
        resolutions,
        performance_observations,
        optimization_experiments,
    ) = _load_ledger(repository)
    refs = (
        [item["ref"] for item in entities]
        + [item["ref"] for item in assertions]
        + [item["ref"] for item in resolutions]
        + [item["ref"] for item in performance_observations]
        + [item["ref"] for item in optimization_experiments]
    )
    if len(refs) != len(set(refs)):
        raise CompileError("ledger record references must be globally unique")
    entity_refs = {item["ref"] for item in entities}
    for assertion in assertions:
        if assertion["record"]["subject"] not in entity_refs:
            raise CompileError(
                f"assertion {assertion['ref']} references an unknown subject"
            )
    performance_by_ref = {
        item["ref"]: item for item in performance_observations
    }
    for observation in performance_observations:
        baseline_ref = observation["record"]["treatment"]["baselineObservationRef"]
        if baseline_ref is None:
            continue
        baseline = performance_by_ref.get(baseline_ref)
        if baseline is None:
            raise CompileError(
                f"performance observation {observation['ref']} references an unknown baseline"
            )
        if baseline_ref == observation["ref"]:
            raise CompileError(
                f"performance observation {observation['ref']} references itself as baseline"
            )
        if baseline["comparisonKey"] != observation["comparisonKey"]:
            raise CompileError(
                f"performance observation {observation['ref']} baseline is not comparable"
            )
    compiled_optimization, optimization_surfaces = compile_optimization_surfaces(
        optimization_experiments, performance_by_ref
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
    compiled_performance = sorted(
        performance_observations, key=lambda item: item["ref"]
    )
    performance_groups, performance_signals = _compile_performance_groups(
        compiled_performance
    )
    structural_submission_ids = {
        item["submissionId"] for item in entities + assertions + resolutions
    }
    map_body = {
        "schema": {
            "name": "skyrim-render-map.structural-map-snapshot",
            "major": 1,
            "minor": 0,
        },
        "submissions": [
            _structural_submission_projection(item)
            for item in sorted(submissions, key=lambda item: item["submissionId"])
            if item["submissionId"] in structural_submission_ids
        ],
        "entities": sorted(entities, key=lambda item: item["ref"]),
        "assertions": compiled_assertions,
        "conflicts": conflicts,
        "resolutions": compiled_resolutions,
    }
    map_snapshot_id = content_id("map-snapshot", map_body)
    body = {
        "schema": {
            "name": "skyrim-render-map.dataset-snapshot",
            "major": 1,
            "minor": 3,
        },
        "generatedBy": {
            "name": "skyrim-render-map.compile-dataset",
            "version": TOOL_VERSION,
        },
        "mapSnapshotId": map_snapshot_id,
        "sourceRevision": source_revision,
        "submissions": sorted(submissions, key=lambda item: item["submissionId"]),
        "entities": sorted(entities, key=lambda item: item["ref"]),
        "assertions": compiled_assertions,
        "conflicts": conflicts,
        "resolutions": compiled_resolutions,
        "performanceObservations": compiled_performance,
        "performanceGroups": performance_groups,
        "performanceSignals": performance_signals,
        "optimizationExperiments": compiled_optimization,
        "optimizationSurfaces": optimization_surfaces,
        "statistics": {
            "submissionCount": len(submissions),
            "entityCount": len(entities),
            "assertionCount": len(assertions),
            "conflictCount": len(conflicts),
            "openConflictCount": sum(item["state"] == "open" for item in conflicts),
            "resolutionCount": len(resolutions),
            "performanceObservationCount": len(performance_observations),
            "aggregateEligiblePerformanceObservationCount": sum(
                item["aggregateEligible"] for item in performance_observations
            ),
            "performanceGroupCount": len(performance_groups),
            "performanceSignalCount": len(performance_signals),
            "optimizationExperimentCount": len(compiled_optimization),
            "optimizationSurfaceCount": len(optimization_surfaces),
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
