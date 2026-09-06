# Exporting optimization runs

The optimization exporter converts private producer artifacts into public
performance observations and an optimization experiment. It is a boundary
adapter: it does not drive Skyrim, choose settings, run a search, or create a
final contribution manifest.

The input plan may contain local paths and therefore stays private. The output
contains only normalized map records, source-artifact hashes, and a review
preview. Source paths are never copied into the export.

## Supported inputs

`csx-profiler-v3` consumes the raw and summary JSON written by the CSX
profiler-control workflow. The exporter requires:

- the complete requested set of unique, fresh frames;
- a successfully restored profiler state;
- matching warm-up, requested-sample, and wall-clock cadence declarations;
- stable context and treatment fingerprints across the capture; and
- a runtime CSX artifact hash matching the plan.

The available profiler measurements are the resolved CSX GPU or CPU total and
one exact resolved timer's GPU, CPU, or top-level GPU duration. The resolved
CSX total is not whole-frame time and must not be labelled as such.

`inline-v1` accepts already normalized samples. It is useful for quality
scores and other producer measurements that do not originate in the CSX
profiler. The ordinary performance-observation validator remains authoritative
for the sample shape and validity declaration. Blinded ordinal comparisons are
not automatically quality scores; see the
[visual evaluation contract](visual-evaluation.md).

## Private plan

Create a plan conforming to
[`csx-optimization-export-plan-v1`](../schemas/producer/csx-optimization-export-plan-v1.schema.json).
The plan pins the map, runtime, environment, scenario, privacy choice, search
definition, setting axes, objectives, candidates, and every source artifact.
The [worked example](../examples/csx-optimization-export-plan-v1.json) uses
inline evidence only and contains no real measurements.

Every objective has its own collection declaration. A wall-clock profiler
capture uses, for example:

```json
{
  "sourceKind": "csx-profiler-v3",
  "metricSource": "timer-gpu",
  "timerName": "Screen Space GI",
  "protocol": {
    "name": "bounded-csx-profiler",
    "version": "1.0.0",
    "artifactSha256": "<sha256>",
    "tools": [
      {
        "name": "csx-profiler-control",
        "version": "<version>",
        "artifactSha256": "<sha256>"
      }
    ],
    "warmupSamples": 60,
    "requestedSamples": 120,
    "sampleCadence": {
      "mode": "wall-clock-ms",
      "value": "100"
    }
  }
}
```

Run the exporter with a Python 3 interpreter:

```console
python tools/export_optimization_run.py --plan private-plan.json --output review-bundle
```

The output directory must not already exist. This prevents a rerun from
silently replacing reviewed material.

## Review bundle

The exporter writes:

```text
review-bundle/
  content/
    performance-observations.jsonl
    optimization-experiments.jsonl
  public-preview.json
  export-receipt.json
```

The receipt records the plan hash, source-artifact hashes, record counts, and a
locally derived Pareto preview. The preview is advisory. The repository
compiler recomputes the authoritative surface after admission.

Review all public files before submission. In particular, confirm the hardware
description, random resettable installation identity, runtime and driver,
scenario/configuration/cache hashes, treatment hashes, contamination state,
and publication opt-in.

The review bundle is not yet a submission. Package its `content/` files under
one new append-only submission directory, create the ordinary
`submission.json`, then run repository validation and deterministic compilation
as described in [CONTRIBUTING.md](../CONTRIBUTING.md).

## Failure behavior

The exporter fails closed on incomplete captures, context drift, treatment or
runtime mismatch, unresolved or ambiguous timer names, non-finite measurements,
invalid public records, or an incomparable optimization surface. A rejected
export does not modify an existing destination. Failed and incomplete search
candidates may still be represented when the plan supplies their explicit
outcomes; they remain visible but are ineligible for the Pareto frontier.
