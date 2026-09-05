# Semantic ledger contract v1

The semantic ledger turns immutable contribution records into a reproducible
dataset snapshot. It detects disagreement without treating any contributor as
an authority and without editing accepted evidence.

## Structured records

An `assertion` or `amendment` submission contains a canonical
`content/assertions.jsonl` and may declare its subjects in
`content/entities.jsonl`. A `resolution` submission contains a canonical
`content/resolutions.jsonl`. Canonical JSONL means one compact JSON object per
line, keys sorted lexically, UTF-8 encoding, and a final newline.

Legacy imports remain valid without structured records. Their source files are
preserved evidence awaiting deliberate normalization; the compiler does not
infer assertions from prose.

Each assertion declares:

- a submission-local ID;
- a subject, predicate, and JSON value;
- whether the predicate is single-valued or multi-valued;
- exact or unknown engine, extension, configuration, and scenario identity;
- evidence class, confidence, and evidence references.

Every assertion subject must resolve to an entity declaration in the accepted
ledger or the same candidate submission. An entity has a submission-local ID,
kind, human-readable label, and one or more source references. This prevents a
misspelled subject from silently creating a disconnected identity. Stable
catalog promotion remains a separate reviewed operation.

`null` applicability values mean that the record does not establish a more
specific boundary. They are not wildcards chosen by the compiler and they are
not evidence that all versions behave identically.

## Stable identities

The globally stable entity, assertion, or resolution reference is:

```text
urn:skyrim-render-map:submission:<submission-id>#<record-id>
```

The compiler derives three content identities:

- `topicKey` from subject and predicate;
- `assertionKey` from subject, predicate, and exact applicability;
- `conflictId` from conflict kind, topic, sorted participant references, and
  their applicability intersection.

All content identities use SHA-256 over UTF-8 canonical JSON with sorted keys
and no insignificant whitespace. Hexadecimal applicability identities are
normalized to lowercase for comparison while the contributed record remains
unchanged in the snapshot.

## Applicability and conflicts

Applicability v1 uses exact values rather than version ranges. Two application
domains overlap unless at least one corresponding pair of non-null values is
different. Their intersection takes the known value when the other side is
null, retains equal known values, and remains null when both are null.

Two assertions create a pairwise `incompatible-value` conflict only when:

1. their topic keys match;
2. both declare `single-valued` conflict policy;
3. their canonical JSON values differ; and
4. their applicability domains overlap.

Equal values are independent support, not duplicates to discard.
`multi-valued` predicates may contain different values without conflict.
Pairwise records are intentional: a broad assertion may overlap two mutually
disjoint version-specific assertions without falsely making those two
specific assertions participants in the same conflict.

The open-world model applies. An absent claim, missing evidence, low
confidence, or an unstructured legacy import is not automatically a conflict.

## Resolutions

A resolution references one generated conflict and exactly its participant
set. It may record narrowed applicability, supersession, unsupported evidence,
aliases, or a deliberately unresolved outcome. Effective assertion references
must be members of that participant set.

Resolutions are immutable interpretation records. They do not rewrite source
assertions. A non-`unresolved` resolution changes the generated conflict state
to `resolved`; an `unresolved` record preserves the open state. Multiple
resolution records remain visible in the snapshot.

## Snapshot generation

Run:

```console
python tools/compile_dataset.py --repository . --output .validation-output/snapshot.json
```

The output contains no wall-clock generation time. It sorts all inputs and
derives `snapshotId` from the complete semantic body, including the optional
source revision. Running the compiler twice over identical repository content
must produce byte-identical output.

Snapshots are generated products. They are not committed by data contributors
and do not replace the append-only ledger.

## Deliberate v1 limits

This slice does not infer structured claims from imported Markdown or JSON,
resolve arbitrary objects embedded in legacy files, express version ranges,
detect ordering or identity-alias contradictions, rank evidence, or decide
which contested value is correct. Those extensions must preserve the v1
identities or publish explicit migration relations.
