# Performance contributions

Performance records preserve bounded measurements and the context required to
compare them. They are evidence, not universal performance claims. Admission
does not certify a result, and a statistical outlier is retained rather than
silently discarded.

## 1. Submission shape

A performance PR is an `observation` data contribution. It adds one immutable
submission directory containing:

```text
submissions/YYYY/MM/<submission-id>/
  submission.json
  content/
    performance-observations.jsonl
    method.md                         # optional
```

`performance-observations.jsonl` contains one compact canonical JSON object
per line conforming to
[`performance-observation-v1`](../schemas/contribution/performance-observation-v1.schema.json).
The [worked example](../examples/performance-observation-v1.json) illustrates
the record shape only; its identities and values are not real evidence.

The ordinary append-only, size, licensing, DCO, privacy, and candidate
validation rules in [CONTRIBUTING.md](../CONTRIBUTING.md) still apply.

## 2. Identity requirements

Every observation identifies:

- the exact published structural `mapSnapshotId` and stable node references
  being measured;
- the Skyrim runtime and executable digest;
- every relevant extension build and artifact digest;
- the physical-headset, null-HMD, or non-VR runtime route;
- CPU model, GPU model, driver, render dimensions, view count, refresh rate,
  render scale, limiter, target frame rate, and reprojection mode;
- the measurement protocol and every collection tool version and artifact
  digest;
- scenario, common configuration, shader-cache, and treatment digests; and
- a random, resettable repository-specific installation ID.

An unavailable source commit may be `null` when the exact extension binary
digest and build ID are present. The executable, extension artifacts, protocol,
tools, scenario, configuration, cache, and treatment identities are mandatory.
Labels aid people; hashes establish grouping identity.

The common `configurationSha256` excludes the deliberately varied treatment.
The complete changed state belongs in `treatmentSha256`. This lets controlled
A/B observations share a comparison key while retaining distinct treatments.

## 3. Measurement contract

Each record measures one metric, unit, and scope. Map-node scopes identify the
stable node or node set, and every measurement scope reference must also appear
in the record's map node references. Whole-frame and process scopes may have no
scope reference.

Values and timestamp offsets are canonical non-negative decimal strings with
at most 18 integer and nine fractional digits. Exponents, signs, trailing
decimal points, and binary floating-point values are not accepted. Samples
start at sequence zero and remain contiguous. A sample may also record its
source frame and relative timestamp.

Record the requested sample count even when fewer samples survive. Retained
samples must never exceed it. `sampleCadence` distinguishes a requested frame
stride from a wall-clock interval in milliseconds. Warm-up and cadence are part
of protocol identity; changing either creates a different comparison group.

Do not replace raw samples with an average. The compiler derives the sample
count, minimum, maximum, median, and arithmetic mean. The mean is rounded to
nine decimal places using round-half-even so output is deterministic.

## 4. Validity and contamination

Use `valid` only when no known contamination applies. A valid record must have
an empty contamination list. Use `contaminated` or `inconclusive` otherwise,
retain the samples, describe the limitation, and mark the affected inclusive
sample range for each known signal.

Recognized signals include shader compilation, loading transitions,
reprojection, frame limiting, thermal throttling, capture overhead, focus loss,
background activity, and driver resets. Use `unknown` with a specific note when
the cause has not been identified.

Contaminated and inconclusive records remain published evidence but do not
enter aggregate groups or outlier evaluation.

## 5. Comparison and aggregation

The compiler derives two content-addressed keys:

- `comparisonKey` includes the installation ID and every exact context field
  except treatment, samples, timestamp, validity, and notes. It joins controlled
  treatments from the same installation and environment.
- `aggregateKey` excludes the installation ID and includes the treatment. It
  joins repeated valid observations with equivalent hardware, software,
  protocol, scenario, configuration, cache, treatment, and measurement scope.

Array ordering for map nodes, extensions, tools, and scope references does not
change either key. Any identity or protocol difference that can materially
alter timing keeps records in separate groups. The structural map ID excludes
performance-only submissions, so adding timing records does not split later
cohorts. The full dataset `snapshotId` still changes because it covers the
complete compiled ledger. Future reviewed alias or migration records may
explicitly establish compatibility across structural map versions; the v1
compiler does not guess it.

## 6. Outlier signalling

Outlier detection is conservative and advisory. It runs only when an aggregate
group contains at least five valid observations from at least three installation
IDs.

The compiler compares each observation's median using Tukey's far-outlier
fences:

1. sort the observation medians;
2. exclude the middle value for an odd-sized cohort;
3. take the medians of the lower and upper halves as Q1 and Q3;
4. calculate IQR as Q3 minus Q1; and
5. signal values below `Q1 - 3 * IQR` or above `Q3 + 3 * IQR`.

The lower fence is clamped to zero. If the cohort is too small, lacks three
installation IDs, or has zero IQR, the compiler records why evaluation was not
performed. A `measurement-outlier` signal sends the record to review; it does
not reject, rank, modify, or delete the observation.

## 7. Privacy

Generate `installationId` from 128 random bits and encode it as `inst-` followed
by 32 lowercase hexadecimal characters. It must be repository-specific,
resettable, and unrelated to a Windows SID, username, machine name, Steam
account, serial number, MAC address, IP address, or hardware identifier.

CPU and GPU combinations may be identifying in a small population. Preview
every public field after collection and obtain a separate publication opt-in.
The four privacy declarations in every performance record must all be true.
Do not include local paths, unrestricted command lines, environment dumps,
credentials, screenshots, saves, crash dumps, or memory dumps in this lane.

## 8. Collection guidance

Prefer a fixed save, viewpoint, scene state, and cache state. Allow the declared
warm-up to finish. Preserve frame pacing and limiter state rather than assuming
that an observed FPS cap is GPU capability. Record shader compilation, loading,
reprojection, capture activity, focus changes, and driver events whenever they
occur.

For a comparison, change only the declared treatment. Repeat the baseline after
the treatment when practical to expose drift. Do not treat a disabled feature
as equivalent to an unloaded feature, or a component timer as additive
whole-frame savings, unless the protocol specifically establishes that claim.

Small bounded histories belong in Git. If the evidence exceeds the repository
limits, open a discussion before submitting it. The content-addressed external
artifact lane described by the architecture is not yet a general public upload
service.

Multi-objective searches should reference these observations through the
[optimization experiment contract](optimization-experiments.md). Search
metadata and derived Pareto membership do not belong in an individual
performance observation.
