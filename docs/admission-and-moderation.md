# Ledger admission and moderation policy

## 1. Admission is not endorsement

Merging a data pull request admits an immutable contribution to the canonical
evidence ledger. It does not certify that every assertion is true, reproduce
the contributor's work, or make the contributor authoritative.

The generated map is an evidence projection. It must expose the provenance and
evidence state of a claim rather than turn repository membership into a claim
of certainty.

## 2. Admission criteria

A data contribution is eligible for admission when all of the following are
true:

1. The trusted structural validator accepts the exact candidate tree against
   the current canonical tree.
2. The trusted compiler produces a deterministic snapshot and semantic-impact
   report.
3. The submission is append-only, contains one coherent contribution, and
   does not alter accepted ledger records, schemas, tools, or generated output.
4. Its applicability, provenance, evidence references, limitations, licensing,
   privacy declaration, and DCO sign-off satisfy the published contracts.
5. Every referenced artifact is either public and immutable or represented by
   a content-addressed index that explains its availability restrictions.
6. A maintainer performs the bounded moderation review in section 3.
7. The exact queued tree passes the required checks against current `main`.

A semantic conflict is not an admission failure. The compiler must expose it,
and the pull request must acknowledge it, but compatible and incompatible
evidence may coexist in the ledger.

Canonical admission is established by presence on protected `main`, not by a
contributor setting `submission.json.status` to `accepted`. An ordinary new
submission declares `candidate-unreviewed`; that immutable field records its
state when packaged. Merge metadata and the canonical tree establish the later
admission decision without rewriting the submission.

## 3. Bounded moderation review

The maintainer's admission decision asks whether the contribution is genuine,
reviewable map evidence—not whether the maintainer has independently proved its
technical conclusion.

The reviewer confirms that the submission:

- is relevant to the Skyrim, Skyrim VR, shader, render, or performance map;
- is intelligible enough for another person to inspect or attempt to reproduce;
- does not make claims materially broader than its declared evidence and
  applicability;
- discloses known conflicts, transformations, uncertainty, and unavailable raw
  evidence;
- is not obvious spam, fabrication, abusive duplication, or repository-flooding;
- does not contain prohibited private, dangerous, or copyrighted material; and
- does not attempt to gain authority by naming a contributor, organization, or
  tool as inherently trusted.

Reproducing a reverse-engineering result, capture, or benchmark is welcome but
is not required for admission. A reviewer must not imply that admission
constitutes reproduction or technical endorsement.

An admissible submission may be rejected or held when the reviewer records one
of these bounded reasons:

- structural or deterministic-validation failure;
- insufficient or unverifiable provenance;
- applicability too vague for the claim made;
- prohibited material, privacy, licensing, or security concern;
- unrelated or incoherent scope;
- obvious fabrication, spam, abusive duplication, or volume abuse; or
- a conflict or limitation that the submission conceals rather than records.

Disagreement with a plausible, properly scoped conclusion is not by itself a
reason to erase or reject it. Submit competing evidence or a resolution record.

## 4. Evidence states

Published projections should use the following meanings:

- `provisional`: one admissible evidence lineage supports the assertion and no
  applicable incompatible assertion is known.
- `supported`: compatible evidence from at least two independent lineages
  supports the assertion and no applicable incompatible assertion is known.
- `contested`: applicable assertions make mutually incompatible claims.
- `resolved`: an immutable resolution record interprets a formerly contested
  set for a stated applicability domain.
- `superseded`: a later record replaces the assertion for a bounded domain
  without deleting its historical applicability.
- `retracted`: the contributor or an evidentiary resolution records that the
  assertion should no longer inform the current projection.
- `moderation-excluded`: a maintainer moderation record excludes abusive or
  fraudulent material from ordinary projections while retaining an audit trail.

Absence of conflict is not corroboration. An assertion about an unexplored area
remains `provisional` until independent support or a resolution justifies a
stronger state.

### Independent evidence

Independence is a property of evidence lineage, not a count of pull requests,
GitHub accounts, files, or repeated assertions. Evidence is not independent
when it derives from the same capture, binary analysis, imported map, producer
run, or copied source—even if it is repackaged by another contributor.

Hardware and installation fingerprints may distinguish performance runs, but
they do not alone prove methodological independence. The compiler must not
infer `supported` merely from equal values until the contribution contract can
represent and validate evidence lineage.

## 5. Conflict and resolution

The canonical ledger preserves every admitted participant in a conflict. A
resolution is a new immutable record that identifies the participants,
applicability, evidence considered, decision, and adjudicator. It may narrow
applicability, select effective assertions, retain an unresolved conflict, or
record that evidence is unsupported.

A resolution changes the generated interpretation, never the original bytes.
Later evidence may supersede a resolution through another reviewed record.

## 6. Abuse and exceptional removal

Maintainers may close submissions, limit submission rate, or restrict
contributors who spam, fabricate provenance, coordinate abusive duplicates, or
attempt to overwhelm review. Those actions are repository moderation, not
technical adjudication.

After merge, discovered bad-faith material should normally receive an immutable
`moderation-excluded` record. History may be removed only when necessary for a
legal, privacy, credential, malware, or security emergency. The reason and
scope should be documented whenever disclosure is safe.

## 7. Automation boundary

Fully unattended admission is limited to conflict-free observations produced
by explicitly allowlisted, signed producer versions under bounded submission
and rate limits. Assertions, amendments, resolutions, unknown producers,
performance outliers, and moderation signals require human review.

Automation may validate, compile, classify, and report. It must not silently
rank contributors, discard conflicts, infer independent corroboration, or turn
an admitted claim into an endorsed fact.

## 8. Current compiler limitation

Dataset compiler v1.1 uses `supported` to mean only that an assertion has no
detected incompatible-value conflict. That label does **not** establish the
independent corroboration required by this policy. Consumers must treat v1.1
`supported` assertions as `provisional` unless they inspect the evidence
lineage themselves.

A future compiler contract should represent evidence lineage explicitly,
derive the states above, and preserve a compatibility mapping for v1.1
snapshots. That change requires a separately reviewed tooling and schema pull
request. The current schema also lacks a standalone moderation-exclusion
record; until that contract exists, maintainers must stop ordinary publication,
record the incident publicly when safe, and add the exclusion through that
reviewed schema extension rather than rewriting the original submission.
