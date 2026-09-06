# Public Skyrim render-map repository architecture

Status: bootstrap implementation v1
Intended repository: `Treatid2/skyrim-render-map`

## 1. Purpose

The repository is the managed public knowledge base for versioned Skyrim,
Skyrim VR, and shader-extension render maps. It accepts evidence and map claims
from multiple producers without allowing a contribution to overwrite accepted
information.

The canonical source is an append-only evidence and assertion ledger. Human
readable maps, graph files, performance summaries, indexes, and the public web
site are deterministic projections of that ledger. Contributors do not edit
those projections directly.

The initial producer is CSX through DevBench and the Skyrim VR automation
tools. The contribution format is producer-neutral so Community Shaders Core,
Open Shaders, RenderDoc adapters, static-analysis tools, and manual research can
participate later without implementing the CSX API.

## 2. Trust boundaries

The system distinguishes three decisions which must never be collapsed:

1. **Structural validity** — a deterministic validator decides whether the PR
   obeys the submission contract. This is a binary required check and uses no
   LLM.
2. **Semantic state** — a deterministic compiler decides whether the new
   assertions are compatible, duplicate, contested, or unresolved relative to
   the current ledger. It never chooses which conflicting assertion is true.
3. **Admission** — an authorized maintainer decides whether valid evidence is
   worth admitting. GitHub auto-merge may perform the merge after approval and
   all current-head checks pass, but arbitrary public data is not admitted on
   schema validity alone. Admission is not technical endorsement.

A failed structural check returns only a standard rejection message and a link
to the submission guide. Detailed contributor diagnostics can be added later
without changing the contract.

## 3. Repository responsibilities

### CSX repository

- Runtime instrumentation and bounded capture implementation.
- DevBench service contracts.
- Runtime event and capture-manifest wire schemas.
- Deterministic CSX shader-manifest generation.
- Exact build provenance.

### Automation repository

- Capture orchestration.
- Local privacy redaction and contribution previews.
- Contribution bundle construction and validation.
- Optional PR or upload submission clients.

### Render-map repository

- Producer-neutral contribution envelope schemas.
- Versioned Skyrim engine-map facts.
- Versioned extension maps under separate namespaces.
- Accepted observations, claims, amendments, disputes, and resolutions.
- Offline graph compilation and conflict detection.
- Performance observation schemas and aggregate generation.
- Public documentation, releases, indexes, and web presentation.

The map repository references producer contracts by immutable version and
digest. It does not duplicate a producer's implementation history.

## 4. Proposed repository layout

```text
.github/
  CODEOWNERS
  pull_request_template.md
  workflows/
docs/
  contributing.md
  evidence-policy.md
  privacy.md
  conflict-resolution.md
schemas/
  contribution/
  assertion/
  observation/
  performance/
  resolution/
catalog/
  engine/
    skyrim-se/
    skyrim-ae/
    skyrim-vr/
  extensions/
    csx/
    community-shaders/
    open-shaders/
submissions/
  YYYY/
    MM/
      <submission-id>/
resolutions/
  YYYY/
    <resolution-id>.json
tools/
  validate_submission.py
  compile_dataset.py
  detect_conflicts.py
  publish_dataset.py
tests/
```

`catalog/` contains maintainer-managed stable identities and applicability
definitions. `submissions/` and `resolutions/` are immutable ledger entries.
Published maps are generated from them and should normally be release assets or
Pages artifacts rather than contributor-edited files on `main`.

## 5. Pull-request classes

Each PR declares exactly one class:

| Class | Permitted purpose | Review policy |
|---|---|---|
| `observation` | Add captured runtime or performance evidence | Structural checks plus maintainer acceptance |
| `assertion` | Add a static, reverse-engineered, correlated, or documented map claim | Structural checks plus subject review |
| `amendment` | Add information correcting or qualifying an earlier ledger entry | Must reference the earlier entry; does not modify it |
| `resolution` | Record an adjudication of a signalled conflict | Maintainer-only or explicitly authorized reviewer |
| `governance` | Change schemas, tools, policy, CI, or stable catalog identities | Normal code review; never mixed with data submission |

A capture run may contain several related observations in one submission. A PR
must not combine unrelated datasets, schema changes, and tooling changes.

Suggested titles:

```text
data(csx): add <submission-id>
data(skyrim-vr): add <submission-id>
resolve(map): record <resolution-id>
build(validation): update submission gate
```

## 6. Submission directory contract

A public data PR adds exactly one previously absent directory:

```text
submissions/2026/09/sub-0199.../
  submission.json
  assertions.jsonl       # optional by declared class
  observations.jsonl     # optional by declared class
  artifacts.json         # content-addressed external/raw evidence index
```

Contributors use submission-local identifiers such as `claim-0001`. They do
not allocate canonical catalog identifiers. A stable reference is therefore:

```text
urn:skyrim-render-map:submission:<submission-id>#claim-0001
```

References to existing map concepts use catalog URNs. New concepts may be
proposed through a submission-local entity declaration; their promotion to a
stable catalog identity is a separate maintainer action.

`submission.json` includes:

- contribution schema major/minor;
- globally unique UUIDv7 submission ID;
- PR class and namespace;
- creation time and producer identity;
- producer contract versions and immutable source/build digests;
- contributor and random installation identity disclosures;
- declared licenses and DCO acknowledgement;
- privacy-review confirmation;
- every included file's media type, size, and SHA-256;
- raw evidence locations, content digests, and retention class;
- prerequisite catalog/map/schema digests;
- assertion and observation counts;
- no absolute local paths or opaque undeclared extensions.

JSON schemas use `additionalProperties: false` at security and identity
boundaries. Optional extension namespaces remain bounded and versioned.

## 7. Append-only rules

For public contribution PRs the diff gate enforces:

- only additions under the one declared submission directory;
- no modified, deleted, renamed, or mode-changed tracked paths;
- no symlinks, submodules, executables, archives-within-archives, or special
  files;
- only allowlisted UTF-8 JSON, JSONL, Markdown, and small declared evidence
  formats;
- bounded file count, individual size, and total size;
- canonical line endings and serialization;
- no changes to schemas, tools, workflows, catalogs, resolutions, or generated
  products.

An accepted record is never silently corrected. A correction is a new
`amendment` record with one of these explicit relationships:

- `supplements`
- `qualifies`
- `disputes`
- `supersedes`
- `retracts`

The earlier record remains addressable. Physical removal is reserved for
privacy, legal, malicious-content, or repository-security incidents and
requires a documented maintainer procedure.

## 8. Deterministic first-level validation

The required `submission-structure` check runs a validator from the trusted
base branch or a pinned signed validator artifact. It never executes code,
workflows, scripts, binaries, or generated commands from the PR.

The binary gate performs, in order:

1. Validate base repository and supported PR class.
2. Inspect the Git diff and enforce the append-only path policy.
3. Reject unsafe file types, paths, links, modes, counts, and sizes.
4. Validate UTF-8 and canonical JSON/JSONL representation.
5. Validate every document against an accepted schema major.
6. Verify the manifest's file sizes and SHA-256 digests.
7. Verify submission ID, directory name, record IDs, and uniqueness.
8. Resolve every reference against current `main` plus the submitted records.
9. Reject an identity collision whose existing content digest differs.
10. Detect exact duplicate evidence and require an explicit duplicate
    relationship rather than silently adding it.
11. Enforce license, DCO, and privacy declarations.
12. Reject forbidden fields and likely secrets or private absolute paths.
13. Run the dataset compiler twice in isolated clean directories and require
    byte-identical output.
14. Emit a signed machine-readable validation receipt.

The public result is initially only:

```text
Accepted for map review
```

or:

```text
Submission structure rejected. See CONTRIBUTING.md.
```

The required-check status itself is the authoritative yes/no result. The
receipt is retained for maintainers and future diagnostics.

## 9. GitHub workflow security

Untrusted PR content must never run with a write-capable token.

- Use the `pull_request` event for validation with read-only permissions and no
  secrets.
- Pin third-party actions by full commit SHA.
- Check out PR data only as inert input to the trusted validator.
- Do not invoke scripts or workflow definitions from the PR branch.
- If labels or comments are later automated, use a separate trusted
  `workflow_run` or GitHub App that consumes only the signed validation receipt.
- Never use `pull_request_target` to check out and execute the contributor's
  head revision.

Branch protection requires the structure check, dataset compile check, current
head conflict check, and designated review. Force pushes and branch deletion
are disabled for the canonical branch.

## 10. Merge protocol

Structural acceptance does not grant merge authority. The initial
semi-automated protocol is:

1. The PR passes `submission-structure`.
2. The trusted compiler produces a semantic-impact and conflict report.
3. An authorized reviewer applies the bounded relevance, provenance, privacy,
   licensing, scope, and anti-abuse moderation criteria in
   [the admission policy](admission-and-moderation.md). Reproducing the
   technical conclusion is not required.
4. The reviewer enables GitHub auto-merge.
5. The merge queue reruns all checks against the latest `main`.
6. The merge occurs only if the exact queued tree still passes.
7. A post-merge job publishes a new content-addressed dataset snapshot and
   Pages build.

Generated outputs are not pushed directly to protected `main`. They are
published as Pages artifacts and immutable release assets. If a generated
snapshot must be retained in Git, a trusted bot opens a separate materializing
PR.

Later, conflict-free observations from allowlisted signed producer versions may
be eligible for fully automatic merge. Assertions, amendments, resolutions,
unknown producers, and performance outliers continue to require review.

Merge admits the exact contribution to the ledger; it does not certify its
conclusions. Semantic disagreement is retained as evidence and is not an
automatic merge failure. The authoritative criteria, evidence-state meanings,
and abuse response are defined in
[the admission and moderation policy](admission-and-moderation.md).

## 11. Structural and semantic conflict model

### Hard structural rejection

The PR cannot enter review when it has:

- an existing submission or record ID with different bytes;
- an invalid or unknown schema major;
- a dangling or type-invalid reference;
- a malformed applicability range;
- a claimed raw artifact whose digest or size does not match;
- an attempted modification or deletion of accepted data;
- non-deterministic derived output.

### Semantic conflict signal

A structurally valid contribution may conflict with accepted knowledge. The
compiler calculates an assertion key from:

```text
subject + predicate + applicability domain
```

Applicability includes the relevant Skyrim executable/module hash, runtime,
extension map/build digest, configuration domain, and scenario constraints.
Two assertions are contested when their applicability overlaps and their
objects are defined as mutually incompatible. Missing evidence is not a
conflict under the open-world model.

The initial compiler implements `incompatible-value`. Planned conflict types
include:

- `incompatible-value`
- `overlapping-applicability`
- `identity-alias`
- `ordering-contradiction`
- `resource-role-contradiction`
- `version-boundary-ambiguity`
- `evidence-provenance-mismatch`

Performance outliers are not structural map conflicts. They receive a separate
`measurement-outlier` review signal.

### Conflict artifact

The compiler emits a deterministic conflict record:

```json
{
  "conflictId": "conflict-<content-digest>",
  "kind": "incompatible-value",
  "assertionKey": "...",
  "participants": ["...claim-0001", "...claim-0004"],
  "applicabilityIntersection": {},
  "state": "open",
  "resolutionRefs": []
}
```

An open conflict is visible in the PR report and published map. The compiler
does not rank away or delete either participant. Map assertions may therefore
be `provisional`, `supported`, `contested`, `resolved`, `superseded`,
`retracted`, or `moderation-excluded`, with the meanings defined by the
admission policy. Compiler v1.1's broader use of `supported` is a documented
compatibility limitation, not a claim of independent corroboration.

## 12. Resolution protocol

A resolution is another immutable, reviewed record. It references every
participant, the evidence considered, the adjudicator, and one result:

- both valid under narrower applicability;
- one supersedes another for a stated version range;
- one is unsupported or invalid;
- the entities are aliases;
- conflict remains unresolved.

Resolutions cannot change original evidence. They alter the derived map's
interpretation for an explicitly bounded applicability domain. New evidence
can supersede a resolution through another reviewed resolution record.

## 13. Performance-record relationship

Performance observations are not facts embedded directly in the structural
map. Each measurement references:

- exact map snapshot digest and stable node IDs;
- Skyrim and extension build identities;
- measurement protocol and tool versions;
- scenario, settings, cache, and runtime-route digests;
- random repository-specific installation identity;
- CPU, GPU, driver, resolution, refresh, frame-pacing, and limiter context;
- raw bounded histories and validity/contamination state.

Aggregates are projections grouped by compatible identities. A new CSX map
does not rewrite old timing data; it either preserves stable node references or
publishes explicit alias/migration relations.

## 14. Evidence storage

The initial repository stores small manifests and normalized records in Git.
Raw captures are compressed, content-addressed evidence bundles outside normal
Git history. Their manifests record location, SHA-256, media type, compressed
and expanded size, retention class, and availability.

The preferred growth path is:

1. GitHub Releases or GHCR/OCI for early immutable reviewed bundles.
2. Object storage when volume justifies it.
3. Parquet and DuckDB/SQLite snapshots for analysis and public download.
4. GitHub Pages for browsing the current projection.

The storage backend is replaceable because map records reference content
digests rather than treating URLs as identities.

## 15. Licensing

Recommended licensing:

- tooling: `GPL-3.0-or-later`;
- authored maps and documentation: `CC-BY-SA-4.0`;
- interoperability schemas: `CC0-1.0`.

Use SPDX declarations and REUSE-compatible metadata. Each submission explicitly
acknowledges the applicable data license and certifies that the contributor may
publish the material. No game binaries, assets, raw decompilation, private
paths, credentials, crash dumps, or personal identifiers are accepted through
the ordinary contribution lane.

## 16. Implementation status

Completed bootstrap slices include repository governance, licensing, protected
branch policy, append-only submission validation, two provenance-preserving
legacy imports, entity/assertion/resolution schemas, deterministic semantic
compilation with subject resolution, pairwise incompatible-value conflict
signalling, and the unprivileged PR workflow.

The next data slice is a bounded normalization of selected legacy engine and
CSX claims into assertions. Observation, artifact-index, performance, and
applicability-range schemas; additional conflict classes; signed receipts;
immutable dataset releases; Pages; and producer export clients remain planned.

This sequence establishes the managed resource before inviting easy player
submissions and leaves storage, querying, and producer integration replaceable
as the corpus grows.
