# Mapping the Skyrim engine

## Scope and implementation

Skyrim Engine Map accepts evidence about any subsystem of Skyrim SE, Skyrim
AE, and Skyrim VR, their extension interfaces, and relationships between those
subsystems. Rendering is a first-class domain within that scope. A claim need
not affect graphics to qualify for admission.

The implementation is the existing append-only entity/assertion ledger and
deterministic dataset compiler. `kind`, `predicate`, and JSON assertion values
already support non-render subjects. Generalising the scope requires no new
record format or retrospective edits to submissions. The compiler emits the
same records, applicability, evidence references, conflicts, and resolutions
for an actor claim as for a render-resource claim.

The following domain vocabulary is an organising convention, not a closed
schema enum, a declaration of Skyrim's internal architecture, or a report of
verified coverage. Evidence may cross several domains. Additional domains may
be proposed with their definitions and evidence; they do not require dummy
render entities.

| Domain | Subjects that may be investigated |
|---|---|
| `actors` | Player and other actor state, ownership, handles, lifecycle |
| `input` | Devices, action dispatch, controls, VR interaction |
| `camera` | Viewpoint state, transforms, camera transitions |
| `animation` | Graphs, events, skeletons, IK, pose updates |
| `physics` | Bodies, constraints, collisions, ragdolls, simulation steps |
| `ai` | Packages, detection, decisions, scheduling |
| `navigation` | Path requests, navmesh use, movement coordination |
| `combat` | Attacks, hit processing, damage, projectiles |
| `magic` | Casting, effects, effect lifetime, actor-value changes |
| `inventory` | Items, containers, equipment, ownership changes |
| `scripting` | Papyrus VM, native bindings, events, latent operations |
| `quests-dialogue` | Quest and dialogue state, conditions, transitions |
| `forms` | Records, references, resolution, identifiers, lifetime |
| `world-streaming` | Cells, worldspaces, loading, attachment, streaming |
| `persistence` | Saves, serialization, reconstruction, persistent state |
| `environment` | Time, weather, climate, interior/exterior influences |
| `audio` | Playback, emitters, state changes, spatialisation |
| `ui` | Menus, Scaleform interfaces, notifications, input routing |
| `rendering` | Passes, resources, shaders, composition, presentation |
| `infrastructure` | Memory, jobs, threads, resource lifetime, file I/O |
| `extension-interfaces` | Native/script hooks, callbacks, patches, ABI boundaries |

Suggested entity kinds include `engine-function`, `engine-type`,
`engine-field`, `engine-event`, `engine-state`, `engine-resource`, and
`extension-hook`. These describe the subject's form rather than confer truth
on its name. Reuse an existing entity reference where identity is established;
otherwise declare a submission-local entity and explain what is known about
its identity. Similar labels or offsets alone do not establish an alias.

## One ledger, several useful views

Structural, behavioural, lifecycle, hook, data-flow, rendering, and performance
views may all draw from this ledger. A future view should declare its source
snapshot and selection method, retain claim references and evidence states,
and expose links that cross its boundary. A filter must not silently hide a
conflicting participant, its applicability, or a relevant resolution. If a
view omits records, state that boundary and link to the source snapshot.

The current compiler produces a combined structural dataset and specialised
timing/optimization/visual outputs. It does not yet implement domain filters,
automatic domain classification, arbitrary graph traversal, a general event
timeline, or causal inference. This guide defines scope and contribution
practice; it does not claim those viewers exist.

Domain membership is interpretation. A future persisted classification must
have a versioned rule or its own evidence-backed assertion; old records must
not be rewritten to add labels. Leave unclassified material visible and report
coverage gaps explicitly. A long list of domain names is not mapped coverage.

## Choosing the record route

| Evidence or claim | Current route | What the compiler can establish |
|---|---|---|
| Function/type/field identity, state or ownership claim | Entity declarations plus assertions | Subjects resolve; records and evidence refs are retained; incompatible single-valued assertions are signalled |
| Relation or sequence claim | Assertion with an explicitly described predicate and JSON value | Values are preserved; arbitrary embedded references and temporal/causal semantics are not interpreted |
| Captured events, state samples, bounded negative observations | `observation` submission with declared JSON/JSONL and a method record; add explicit assertions in a suitable assertion/amendment submission when interpreting it | Raw files are preserved and their manifest digests checked; arbitrary event files do not become inferred facts |
| Source/static analysis or documentation | `assertion` with the actual evidence class and immutable source locators | Same structural and conflict checks; source interpretation is a review responsibility |
| Engine-node or whole-frame timing | Performance observation, only when the full v1 contract fits | Existing controlled comparison, aggregation, and outlier rules |
| Images and visual judgments | Existing capture/artifact/visual contracts where applicable | Existing content identity and linkage checks; a screenshot alone does not establish internal cause |
| Correction or competing interpretation | Amendment or resolution under the ledger contract | Original records stay addressable; applicable conflicts and their resolutions remain visible |

Generic observations must still satisfy the submission envelope, file/type
limits, privacy/licensing rules, content digest, source provenance, and
ordinary admission review. They are not an unvalidated executable extension
mechanism. Large or restricted evidence needs an approved, content-addressed
artifact route; the visual-capture exporter is not a general trace uploader.

The envelope currently requires a source repository, source commit, and
source-content digest. A capture producer should identify the real committed
producer/export source and preserve the captured bytes' separate digests and
method. A manual investigation can use a real committed research package.
Do not put a guessed commit, all-zero hash, or an unrelated repository into a
required field. If the available evidence cannot truthfully satisfy the
envelope, preserve it outside the admitted ledger until a reviewed contract
extension supports its provenance.

These are contributor and admission-review obligations, not all mechanical
guarantees. The v1 validator requires the provenance fields and checks the
source commit and source-content digest formats. It does not establish that
the repository is relevant, that a commit exists, or that the declared
`provenance.sourceContentTreeSha256` matches an external source tree; even
all-zero source digests pass those format checks. Substantive review must
assess that evidence under the admission policy. The separately named
`content.treeSha256` is recomputed against the included submission bytes.
The original manifest retains the full provenance block; the compiled
submission summary projects only selected fields. Structural acceptance must
not be described as source authentication.

The timing schema requires render context and cache identity and has a finite
metric vocabulary. Do not encode Papyrus event counts as milliseconds, invent
render dimensions for offline analysis, or label an unrelated digest as a
shader cache. Retain such measurements as ordinary observation evidence, with
units and method, pending an appropriate specialised schema. They do not enter
timing aggregates through that fallback.

## Keeping claims traceable

Every claim needs its own bounded evidence trail. Retain the original source
identity and observation separately from the interpretation:

1. **Source and observation.** Record the exact executable/module digest and
   runtime when established; source repository/commit and source locations for
   source analysis; capture/artifact digest, producer version, run identity,
   and record/time interval for runtime observations. Distinguish virtual
   addresses, relative addresses, relocation IDs, record IDs, and offsets.
   Explain the address base and owning binary. A function label is not a
   substitute for identity.
2. **Method and transformation.** Retain the method and any extraction,
   symbolisation, normalization, correlation, redaction, or derivation steps.
   References should resolve to an immutable source or an indexed digest with
   an honest availability statement. Reference the original evidence as well
   as a derived table or report. The ledger checks reference shape/presence;
   it cannot establish that an arbitrary external reference supports a claim.
3. **Applicability.** Declare the exact engine/extension/configuration/scenario
   boundaries that the record format supports. Retain additional context in
   declared method/context evidence and link it from the assertion. Include
   actors, cell/interior/exterior state, exact time/weather, input route,
   save/load history, and scheduling state when they can affect the claim.
   Indoor evidence may depend on outdoor conditions. Do not invent conditions
   that were not measured.
4. **Interpretation.** Use the actual evidence class and confidence. Record
   what was observed, what was inferred, alternatives, missing coverage, and
   known conflicting evidence. Derived claims cite their inputs and method;
   they cannot gain independence by being copied into another domain.
5. **Amendment.** Add new qualification, dispute, or resolution records when
   evidence changes. Preserve old evidence, IDs, byte digests, and applicability.

The submission's producer namespace, the entity being mapped, and the
assertion's extension applicability answer different questions. A CSX-assisted
capture may investigate a base-engine actor function; this does not establish
that the function belongs to CSX or that every observation requires CSX.
Conversely, a plugin's behaviour does not become a vanilla-engine guarantee.

Null fields mean unspecified boundaries. They do not mean verified vanilla,
extension absent, all runtimes equivalent, or no configuration effect. Explain
unknown, verified-absent, and irrelevant-to-this-claim states in linked evidence
because v1 has no dedicated enum for those distinctions. Unknown applicability
still overlaps known values conservatively during conflict detection.

The v1 assertion has one extension identity slot. Preserve multiple relevant
components in a declared context artifact, bound the configuration digest to
that actual context, and disclose the compiler's inability to interpret the
component combination. Do not concatenate several builds into a fake single
identity. Multi-extension reasoning needs a future schema; this scope change
does not supply it.

## Relations, hooks, and negative results

Use separate assertions for separate propositions: a declaration exists, a
caller was observed, a callback executed, a field changed, and a change caused
a later effect are different claims. Each relation needs evidence even when
both endpoints are well supported. Temporal proximity is not causation; a
source-level call or hook registration is not proof of runtime execution.

For hook claims, identify the owning binary, target/offset or symbol, hook
implementation/build, original versus replaced behaviour, and the observation
conditions. Record ordering, thread, lifetime, and preconditions when known;
leave unknowns explicit. A declaration in a compatibility library establishes
what that library declares for that revision, not by itself the layout or
behaviour of every supported executable.

The current v1 compiler resolves assertion subjects. It does not resolve every
entity-like string or object inside `value`. Reserved top-level `entityRef`
validation is proposed separately in
[PR #8](https://github.com/Treatid2/skyrim-render-map/pull/8); it is not a
dependency or an implemented feature of this scope change. Until the running
validator/compiler explicitly supports that contract, embedded targets require
review and must not be presented as mechanically validated graph edges.
Nested values must not be assumed to receive the proposed top-level check.

For a negative observation, record the capture start/end, subscription time,
event filters, sampling/drop counts, and relevant transitions. "No event in
this interval" does not establish "the engine never emits the event". An event
before subscription is outside coverage. A callback that has already happened
cannot serve as a reliable future trigger; current state needs separate
evidence. This distinction applies equally to load, actor, animation, and
render events.

Similarly, selected, enabled, initialized, executed, and observed are distinct
states. Disabled, unloaded, absent, and a setting named "None" are not
interchangeable without evidence. Controlled trials should retain baseline,
treatment, and repeat observations and disclose changing conditions.

## Compatibility and evidence states

`Treatid2/skyrim-render-map`, `skyrim-render-map.*` schema names, and
`urn:skyrim-render-map:*` references remain compatibility identifiers for the
whole engine ledger. Do not rewrite them to match the display name. Existing
records, manifests, artifact digests, and source references remain unchanged.
Changing only the project scope does not change structural map identity.

Human-readable schema titles may change. Those files then have new byte
digests; retain the exact schema revision/digest used by a producer. Equal
validation semantics do not mean byte-identical schema files. This change
does not alter required fields, accepted values, or schema versions. If an
output's explicit `sourceRevision` changes, its full snapshot identity changes
as designed, even though its structural `mapSnapshotId` need not change.

The current compiler's `supported` state means no detected incompatible-value
conflict. Consumers must interpret it as provisional unless independence is
established under the [admission policy](admission-and-moderation.md). The same
limitations apply in every domain: no automatic causal reasoning, evidence
ranking, alias equivalence, transitive truth, or corroboration from repeated
copies. A new view may not upgrade those states through presentation.

The synthetic integration tests in
[`tests/test_engine_scope.py`](../tests/test_engine_scope.py) exercise every
domain above, cross-submission subjects, evidence preservation, applicability,
conflicts, required provenance fields, malformed source digest rejection, and
the boundary between format validation and source authentication. Their invented functions,
digests, and results are test data, never engine findings. No test fixture is
admitted under `submissions/`.

## Future modlist work

A later modlist project could reference these engine entities and evidence.
It would need its own composition identity: exact component versions and
artifacts, plugin and asset ordering, winning overrides, configuration,
generated outputs, runtime context, and save history where relevant. Effects
of a particular composition must not be promoted to unconditional base-engine
claims. Reusing immutable component evidence may reduce duplication, but it
does not establish the behaviour of combinations that were never examined.

This generalisation reserves no modlist schema, collector, automatic diagnosis,
compatibility solver, or new combinatorial dataset. Those require a separate
design and evidence contract once that project is chosen.
