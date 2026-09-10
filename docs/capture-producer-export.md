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

The v1 producer runs on Windows, where each private directory is atomically
created by the native file API with its original identity returned on the same
handle. The exporter retains the stage owner and creates every directory and
file relative to that held object, so a renamed or replaced stage pathname
cannot redirect generated writes into a foreign tree. Every created member is
recorded in an identity ledger. Later sealing, publication, and cleanup require
the observed tree to match that ledger exactly. Other platforms fail before the
plan, source media, output parent, or staging directory is read or changed.
Portable ledger validation and dataset compilation remain cross-platform; this
boundary applies only to capture production.

The source must be a final `csx.screenshot` 1.0 sequence manifest with schema
revision 1 or later. The exporter rejects rather than guesses when:

- terminal child and summary counts do not reconcile;
- a retained artifact is absent, uncommitted, truncated, or has an invalid
  SHA-256;
- a PNG is structurally invalid, undecodable, interlaced, indexed-colour,
  contains an unknown ancillary chunk, or declares an unsupported output view;
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
equal bundle bytes. The exporter reads each source once, validates its declared
size and digest, sanitizes that exact byte observation into private staging,
verifies every PNG chunk, decodes its image-data stream, and writes the bundle
from the corresponding sealed bytes. Text, EXIF,
and embedded-profile chunks are removed at that boundary; safe colour and
geometry chunks are retained. `bundle-manifest.json` preserves both source and
published frame identities, the source-manifest digest, source contract,
original ordinals, engine-frame identifiers, timestamps, and terminal
omissions. It deliberately omits local paths, request identifiers, session
identifiers, capture tags, and other private manifest fields.

The adapter admits only the exact generated public-record bytes and the expected
root, `artifacts`, and `content` directory layout. It holds exclusive file locks
while it validates and seals the complete member set, public-file scans, file
identities, modification times, lengths, and digests. The seal also requires
every file and directory identity to match its creation-time ownership ledger;
equal replacement bytes are not adopted. ZIP admission requires the exact
generated entry order and metadata, rejects duplicate or additional members and
archive comments, and covers generation through both whole-file hashes with one
lock. Directory identity and change metadata are sampled before and after
enumeration, and a recursive native change watch covers the sampling interval,
so a membership change during the observation fails. Watch setup and shutdown
account for every acquired handle independently. Every normal, failed, or
interrupted shutdown must establish terminal completion before releasing native
state. If it cannot, the exporter retains the handle, event, overlapped state,
and buffer instead of releasing memory still owned by pending I/O. It verifies
the same coherent tree after an operating-system no-replace rename of the sibling
staging directory. The post-rename comparison retains directory identities and
complete membership but excludes rename-volatile directory timestamps; each
pre- and post-rename inventory still checks those timestamps internally for
concurrent membership changes.

A concurrent creator of the destination wins without being overwritten. If
required verification fails or is interrupted after the rename, the exporter
reconciles the old and new names, then withdraws the output only while its
creation-time directory identity remains proven; otherwise it reports the
publication and custody uncertainty. Cleanup similarly removes only the
exact identity-ledger contents of the originally created stage or private spool.
An untracked, missing, or identity-replaced descendant rejects the whole cleanup
before deletion begins. On Windows the exporter retains native deletion handles
that exclude ordinary path replacement while removal is in progress, accounts
for each handle until release, and attempts all remaining releases after an
error. A substituted or missing pathname is preserved and reported as uncertain
rather than being treated as successful cleanup. CLI failures include exception
notes from unresolved handle release and custody operations instead of hiding
secondary cleanup uncertainty.

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

Only terminal error codes reserved by the CSX screenshot 1.0 contract are
copied. Unknown strings become `unspecified`, even when they happen to look like
opaque identifiers. A `completed_with_warnings` state contaminates the evidence
even if a malformed producer omitted the warning-detail array.

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
That submission manifest must use exactly the `submissionId` declared in the
private plan. Artifact and capture identifiers must be distinct because all
submission-local record types share one identifier namespace.

Producer plans may select `release-asset`, `oci-artifact`, `object-storage`, or
`external` retention. Repository-inline evidence is a later submission and
admission decision, not a producer-export retention class.

This v1 adapter supports non-interlaced grayscale, true-colour, grayscale-alpha,
and true-colour-alpha PNG mono or synchronized left/right sequences. Indexed
PNG is rejected rather than partially validated. A lone left or right eye is
rejected rather than relabelled as mono. The adapter does not transcode, resize,
compress, repair, interpolate, or score frames.
