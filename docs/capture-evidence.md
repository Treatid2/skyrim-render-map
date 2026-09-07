# Visual capture evidence

Visual media is too large for the ordinary append-only Git ledger. The ledger
therefore stores two immutable records while the bytes remain in external,
content-addressed storage:

- `content/artifacts.jsonl` describes the exact bytes, license, size, media
  type, retention class, and one or more HTTPS retrieval locations;
- `content/visual-captures.jsonl` describes how those bytes were captured and
  binds them to an exact map, runtime, machine, scenario, treatment, and capture
  protocol.

The schemas are [artifact v1](../schemas/contribution/artifact-v1.schema.json)
and [visual capture v1](../schemas/contribution/visual-capture-v1.schema.json).
The [artifact](../examples/artifact-v1.json) and
[capture](../examples/visual-capture-v1.json) examples contain illustrative
identities only.

## Identity and storage

`artifactSha256` is the identity of the stored bytes. URLs are only locators:
an artifact may be mirrored or moved without changing its scientific identity.
Every available artifact must declare at least one absolute HTTPS location and
must be retrievable without embedding credentials in the record.

Accepted records remain immutable. A later submission may publish another
record for the same digest with additional locations; the compiler groups all
such records into `artifactIndex`. Metadata disagreement is retained there as
`contested` rather than silently selecting one description.

An artifact record covers one archive or media object. `byteLength` is the
stored length and `expandedByteLength` is the bounded expanded length. Producers
should prefer one sequence bundle over thousands of loose frame URLs. The
bundle should contain a deterministic manifest with per-file digests, frame
indices, eye identifiers, timestamps, dimensions, and encoding details. This
repository records the bundle digest; producer repositories own their detailed
wire manifests and creation code.

Artifact records are licensed independently because captured imagery may have
different reuse terms from schemas or tools. Do not publish Skyrim assets,
shader binaries, raw dumps, private paths, identifiers, or media for which the
contributor cannot grant the declared license.

## Capture validity

A capture records retained frame count and rate, actual source and fallback,
view count, dimensions, colour space, pixel format, timing mode, and exact
capture API provenance.
Dropped and duplicated frames are always declared. A capture may be `valid`
only when both counts are zero and no contamination is recorded. Contaminated
or inconclusive captures remain useful evidence but cannot serve as stimuli in
a valid visual comparison.

The random resettable installation identity supports within-machine grouping;
it is not a hardware fingerprint. Publication requires the same explicit
preview and opt-in declarations as performance observations.

## Comparison linkage

Each visual-comparison stimulus resolves `sourceObservationRef` to a visual
capture record. The compiler requires all of the following:

- the capture resolves to an artifact whose digest and media kind match;
- stimulus capture and treatment digests match the capture record;
- both captures have valid status;
- map, runtime, environment, scenario, media kind, frame count, frame rate,
  and view count are identical to the comparison context; and
- the two source capture protocols are byte-semantically identical, including
  dimensions, pixel format, timing mode, and capture API provenance.

This prevents a copied digest or stale label from silently joining unrelated
captures. Preprocessing remains separately identified by the comparison
protocol, so evaluators can repeat a presentation from the immutable sources.

This contract does not upload, download, execute, or inspect media. A later
producer adapter can normalize CSX screenshot-sequence manifests into these
records without changing the neutral ledger format.
