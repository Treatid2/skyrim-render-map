# Optimization experiments and Pareto surfaces

Optimization experiments connect automated preset searches to the structural
render map and its performance evidence. They preserve the explored parameter
space and every candidate outcome. The dataset compiler derives Pareto
frontiers; contributors do not submit a preferred winner as map truth.

## 1. Submission shape

An optimization experiment is part of an `observation` submission:

```text
submissions/YYYY/MM/<submission-id>/
  submission.json
  content/
    performance-observations.jsonl
    optimization-experiments.jsonl
    method.md                         # optional
```

The performance observations may instead come from earlier accepted
submissions. Every experiment conforms to
[`optimization-experiment-v1`](../schemas/contribution/optimization-experiment-v1.schema.json).
The [worked example](../examples/optimization-experiment-v1.json) illustrates
the record shape but is not evidence.

The ordinary append-only, licensing, DCO, privacy, size, and validation rules
still apply. An experiment submission cannot add structural map entities.

## 2. Evidence boundary

An experiment record is an index over evidence, not a measurement container.
It records:

- the exact structural map snapshot and relevant render/shader nodes;
- the exact search producer binary and algorithm version;
- the requested search budget and optional hashed random seed;
- every varied setting axis and its allowed domain;
- every objective, direction, scope, reducer, and dominance tolerance;
- explicit feasibility constraints;
- every attempted candidate, including failures and rejections; and
- references from candidate objectives to raw performance observations.

The linked performance records remain authoritative for runtime, hardware,
driver, protocol, scenario, configuration, cache, samples, validity, and
privacy. Do not duplicate those fields in the experiment or replace the raw
sample history with a score.

## 3. Mapping shader settings

Each axis identifies one stable CSX or engine map node and one setting path.
The experiment declares all referenced nodes in `map.nodeRefs`. This lets a
candidate vary settings across several shader families while retaining an
explicit relationship to the render graph.

Supported axis domains are:

- `boolean`;
- non-negative stepped `integer`;
- canonical non-negative stepped `decimal`; and
- `categorical`, with an explicit list of allowed strings.

Minimum, maximum, and step must form a closed domain. Every candidate supplies
exactly one in-domain value for every axis. The compiler sorts and normalizes
those parameters and derives `parameterVectorSha256`; contributors do not
choose that identity.

The treatment hash on a candidate covers the complete deliberately changed
state, not only the displayed axes. It must match every performance observation
linked to that candidate. This detects hidden or accidentally omitted changes.

## 4. Objectives and repeat measurements

An experiment has at least two objectives. Each objective declares:

- a metric and unit matching its performance observations;
- `minimize` or `maximize`;
- a map-aware measurement scope;
- `median-of-observation-medians` as the v1 reducer; and
- a non-negative `dominanceEpsilon` in the objective's unit.

One candidate may reference repeated observations for an objective. The
compiler first uses each observation's median and then takes the median of
those medians. The same performance observation cannot be reused elsewhere in
the experiment.

For a given objective, all candidates must reference the same comparison
context. The compiler therefore rejects mixtures of installations, runtime
builds, drivers, render contexts, protocols, scenarios, caches, metrics, or
scopes. Treatment is deliberately excluded from that comparison identity.
Different objectives may use different measurement protocols.

## 5. Candidate outcomes and validity

Candidate outcomes are:

- `completed` — all objectives were measured;
- `failed` — execution failed, including a crash, timeout, or rendering fault;
- `incomplete` — execution returned but the objective set is incomplete; or
- `rejected` — a declared screening rule prevented execution.

Completed candidates declare no failure kind and must reference every
objective. Other outcomes retain a specific failure kind and may retain any
measurements completed before termination.

A completed candidate becomes Pareto-eligible only when every linked
observation is `valid`. Contaminated and inconclusive measurements remain in
the dataset but exclude that candidate from the derived surface. Outlier
signals remain advisory and do not silently remove a candidate.

## 6. Constraints and Pareto dominance

Constraints apply `at-most` or `at-least` thresholds to derived objective
values. A candidate with complete valid measurements may be evidence-eligible
but infeasible. Infeasible candidates remain visible and are excluded from the
frontier.

For two feasible candidates `A` and `B`, `A` dominates `B` when:

1. `A` is no worse than `B` beyond each objective's epsilon; and
2. `A` is better than `B` by more than epsilon on at least one objective.

For a minimized objective, no worse means `A <= B + epsilon` and strictly
better means `A < B - epsilon`. The inequalities reverse for maximized
objectives. Equal candidates do not dominate each other.

The generated surface contains every candidate, its normalized parameter hash,
derived objective values, eligibility, constraint violations, and `dominatedBy`
references. The frontier is the feasible set with no dominator. If no candidate
qualifies, the surface reports `insufficient-evidence` rather than inventing a
winner.

## 7. Reproducibility and privacy

The producer artifact digest and algorithm version make search behavior
auditable. Hash a random seed before publication when exact replay requires it;
use `null` for deterministic searches without a seed. Never publish raw seeds
that embed usernames, timestamps, paths, or other local information.

Optimization records do not add a second installation fingerprint. Their
linked performance observations carry the random, resettable installation ID
and publication consent under the
[performance contribution contract](performance-contributions.md). Preview the
entire combined submission before opening a PR.

## 8. Producer integration

An auto-preset producer should:

1. pin the structural map snapshot and resolve each setting to a stable node;
2. define the complete domains, objectives, tolerances, and constraints before
   running the search;
3. hash the common configuration separately from each candidate treatment;
4. publish bounded raw observations for every measured objective;
5. retain failed, incomplete, screened, and dominated candidates;
6. emit one canonical experiment record referencing those observations; and
7. run repository validation and deterministic compilation locally.

The producer may maintain an internal live frontier to schedule work, but that
frontier is not authoritative. The public frontier is recomputed from admitted
evidence so corrections, contamination findings, or added candidates can
change it without rewriting the source ledger.

The map-side [optimization run exporter](producer-export.md) implements this
handoff for CSX profiler schema-v3 captures and normalized inline samples. It
verifies the capture identity and emits reviewable neutral records; it does not
implement the search or operate the game.

Blinded ordinal judgments use the separate
[visual evaluation contract](visual-evaluation.md). Visual comparisons do not
become percentage objectives automatically; any scalar aggregation must be an
explicit, versioned future policy with the source trials retained.
