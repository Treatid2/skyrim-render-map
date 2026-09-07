# CSX capture producer export

`tools/export_csx_capture.py` converts one finalized CSX screenshot-sequence
manifest into a deterministic evidence bundle and the neutral artifact and
visual-capture records used by this repository. It is an offline producer
adapter: it does not launch Skyrim, drive DevBench, upload media, or compose a
video.

The private input contract is
[`csx-capture-export-plan-v1`](../schemas/producer/csx-capture-export-plan-v1.schema.json).
The [example plan](../examples/csx-capture-export-plan-v1.json) contains
illustrative identities only. `source.manifestPath` may be absolute or relative
to the plan and is never copied into public output.

## Preconditions

The source must be a final `csx.screenshot` 1.0 sequence manifest with schema
revision 1 or later. The exporter rejects rather than guesses when:

- terminal child and summary counts do not reconcile;
- a retained artifact is absent, uncommitted, truncated, or has an invalid
  SHA-256;
- source, eye layout, dimensions, format, or colour metadata are ambiguous or
  inconsistent;
- the sequence contains no completed frame; or
- the producer plan cannot form valid neutral records.

Older promoted captures can be exported after their original scratch location
has expired. When a declared frame path is unavailable, the adapter accepts a
file with the same basename beside `sequence.json`. It still verifies the exact
declared length and SHA-256 before using that file.

## Export

Choose a protected working directory for unique capture data. In Codex
environments, use a managed `Kind=capture` scratch allocation and promote any
retained result to authoritative storage before releasing the allocation.

```console
python tools/export_csx_capture.py --plan private-plan.json --output review-bundle
```

The output directory must not already exist. A successful export contains:

```text
review-bundle/
  artifacts/<sha256>.zip
  content/artifacts.jsonl
  content/visual-captures.jsonl
  export-receipt.json
  public-preview.json
```

The ZIP uses stored entries, fixed timestamps and permissions, canonical JSON,
and stable frame names. Equal source bytes and manifests therefore produce
equal bundle bytes. `bundle-manifest.json` preserves the source-manifest digest,
source contract, original ordinals, engine-frame identifiers, timestamps,
per-file identities, and terminal omissions. It deliberately omits local paths,
request identifiers, session identifiers, capture tags, and other private
manifest fields.

The adapter writes atomically through a sibling staging directory. Any rejected
or interrupted export removes that staging directory and leaves no claimed
output.

## Actual capture semantics

The neutral record describes what CSX actually captured. `sourceKind` records
the actual source, and `sourceFallbackApplied` records whether CSX substituted
that source for the request. This prevents an HMD request that fell back to a
desktop mirror from being mislabelled as an HMD submission.

Dropped, failed, cancelled, duplicated, or warning-bearing frame slots are
retained in the bundle manifest and make the visual-capture record
`contaminated`. Such evidence can still be admitted and inspected, but the
visual comparison contract will not accept it as a valid comparison stimulus.
Unscheduled requested slots are not called dropped frames.

The producer supplies the orchestration protocol identity and intended frame
rate. The adapter derives the CSX capture API version from the source contract
and binds it to the exact CSX DLL hash declared in `runtime.extensions`.

## Publication

`artifact.locationTemplate` must be a stable credential-free HTTPS location
containing exactly one `{sha256}` placeholder. The exporter substitutes the
bundle digest but does not upload or test the URL. Upload the exact ZIP, verify
its SHA-256 at the public location, and preview every generated public field
before proposing a data PR.

Only publish media for which the declared license can be granted. The generated
`content/` files still require an ordinary append-only submission manifest and
the normal admission checks described in [CONTRIBUTING](../CONTRIBUTING.md).

This v1 adapter supports PNG mono or synchronized left/right sequences. It does
not transcode, resize, compress, repair, interpolate, or score frames.
