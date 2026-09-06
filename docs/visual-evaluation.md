# Blinded visual evaluation

Visual evidence is kept separate from performance timing and from the
structural render map. A visual comparison pins an exact map/runtime context,
two content-addressed capture stimuli, a versioned rubric, and the raw trials
performed by human, multimodal-model, or algorithmic evaluators.

The compiler summarizes agreement. It does not declare that an evaluator is
correct, convert subjective preference into a technical fact, or assign an
overall quality score.

## Submission shape

Visual records belong to an `observation` submission:

```text
submissions/YYYY/MM/<submission-id>/
  submission.json
  content/
    visual-rubrics.jsonl
    artifacts.jsonl
    visual-captures.jsonl
    visual-comparisons.jsonl
    method.md                    # optional
```

Rubrics and comparisons may be submitted together. A comparison may also
reference a rubric from an earlier accepted submission. The schemas are:

- [`visual-rubric-v1`](../schemas/contribution/visual-rubric-v1.schema.json);
- [`artifact-v1`](../schemas/contribution/artifact-v1.schema.json);
- [`visual-capture-v1`](../schemas/contribution/visual-capture-v1.schema.json);
- [`visual-comparison-v1`](../schemas/contribution/visual-comparison-v1.schema.json).

The [rubric](../examples/visual-rubric-v1.json) and
[comparison](../examples/visual-comparison-v1.json) examples are illustrative
only and contain no evidence.

## Rubrics

A rubric defines stable dimensions and the meaning of the shared difference
magnitude scale. Every dimension is explicitly classified as:

- `correctness` — defects such as stereo mismatch, flicker, ghosting, or
  temporal instability;
- `visual-effect` — a directionally described rendering result such as shadow
  definition or indirect-light plausibility; or
- `preference` — an explicitly subjective aesthetic choice.

The description must state what “better” means for that dimension. Do not
collapse technical correctness, perceptible effect, and preference into one
dimension. Shader-family rubrics reference the relevant stable map nodes;
common rubrics may describe dimensions shared across the frame.

The canonical v1 magnitude scale is `imperceptible`, `slight`, `moderate`,
`large`, and `severe`. Magnitude describes the visible difference, not
confidence and not statistical significance.

## Capture stimuli and blinding

Stimuli `a` and `b` identify exact capture and treatment SHA-256 values. The
actual media remains in the repository's content-addressed evidence storage;
ordinary data PRs contain its digest, not game assets or large video files.

The protocol records whether the evaluator received a simultaneous or
sequential presentation, whether assignment was randomized, mono/stereo media,
frame count and rate, and the exact preprocessing digest. Each sequential trial
records `a-b` or `b-a` presentation order. Reversing order is strongly
recommended because order-sensitive answers remain visible as disagreement.

`sourceObservationRef` resolves each stimulus to an immutable capture
observation. The compiler verifies the capture and treatment digests, comparable
runtime context, media geometry and timing, capture validity, and the linked
artifact. See the [capture evidence contract](capture-evidence.md).

## Evaluators

Model and algorithm trials require an exact evaluator name and version plus
artifact and prompt SHA-256 values. The artifact identifies the evaluation
package or adapter; it does not imply that proprietary model weights are
available. Human evaluators may leave version, artifact, and prompt identities
null.

A dedicated multimodal evaluator can implement this contract, but its result
has ordinary evidence status. Preserve its model version, rubric, prompt,
preprocessing, presentation order, and repeated trials so later evaluators can
reassess the same content-addressed stimuli.

## Judgments and localized evidence

Every trial must judge every rubric dimension exactly once. An assessment is:

- `a-better`;
- `b-better`;
- `equivalent`; or
- `inconclusive`.

Confidence is a canonical decimal from zero to one. It is retained but does
not give one evaluator more votes than another. Evidence may identify a frame
range, view, optional normalized rectangular region, and notes. Regions must
remain inside the frame. This supports inspection without treating an
evaluator's prose as the evidence itself.

Contamination is comparison-specific and identifies trial ranges. A valid
comparison cannot declare contamination. Contaminated and inconclusive records
remain published but are not eligible for later optimization use.

## Deterministic summary

For each comparison and rubric dimension, the compiler emits exact assessment
counts and one conservative state:

- `unanimous-a-better`;
- `unanimous-b-better`;
- `unanimous-equivalent`;
- `contested`; or
- `insufficient`.

Any disagreement, including a mixture of a conclusive and inconclusive trial,
is contested. The compiler does not use confidence weighting, majority voting,
or model reputation. Raw trials remain authoritative and the derived summary
can be regenerated.

This first slice does not convert comparisons into scalar optimization
objectives. Connecting visual evidence to a Pareto experiment requires an
explicit, versioned aggregation policy rather than inventing a percentage from
ordinal judgments.
