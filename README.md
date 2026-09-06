# Skyrim render map

This repository is a public, versioned knowledge base for the rendering
systems of Skyrim SE, Skyrim AE, Skyrim VR, and compatible shader extensions.

It is evidence-led rather than authority-led. Treatid2 supplied the initial
material, but that material has no privileged evidentiary status. Every claim
is evaluated from its declared provenance, applicability, evidence class, and
supporting observations.

## Current status

The repository is in its bootstrap phase. It presently contains two imported
CSX-assisted research contributions:

- [Full Render Exploration snapshot](submissions/2026/08/sub-csx-full-render-exploration-9935c5210/submission.json),
  including a Skyrim VR 1.4.15 engine-map seed, CSX shader dependency data,
  schemas, bounded-capture findings, and derived graph examples.
- [Deferred command provenance correction](submissions/2026/09/sub-csx-command-provenance-a28e9e9f/submission.json),
  containing the later command-list and deferred G-buffer evidence slice.

Both are candidate contributions. Importing them preserves work and
provenance; it does not certify every conclusion.

The v1 [semantic ledger](docs/semantic-ledger.md) validates declared entities,
normalized assertions, and resolutions; detects overlapping incompatible
claims; and builds byte-reproducible dataset snapshots. The bootstrap imports
have not yet been normalized into assertions, so their knowledge remains
preserved source material rather than compiler-interpreted fact.

The long-term architecture is described in
[docs/architecture.md](docs/architecture.md).

## Contribution model

Accepted evidence is append-only. A public data PR adds one new submission
directory and cannot modify or delete an existing submission. Corrections and
disputes are new records that reference earlier material.

The first admission check is deliberately mechanical and does not use an LLM.
It answers only whether the submission obeys the repository contract. Passing
that check makes a contribution eligible for map review; it does not establish
that its conclusions are correct.

Merging a data PR means that its evidence has been admitted to the ledger. It
does not certify or endorse the conclusion. Uncorroborated assertions remain
provisional, and conflicting evidence remains visible until an immutable
resolution interprets it.

See [CONTRIBUTING.md](CONTRIBUTING.md),
[the admission and moderation policy](docs/admission-and-moderation.md), and
[PRIVACY.md](PRIVACY.md). Timing contributors should also read the
[performance contribution guide](docs/performance-contributions.md). Automated
preset searches use the
[optimization experiment contract](docs/optimization-experiments.md).

## Repository boundaries

- CSX owns its instrumentation, DevBench integration, and capture wire
  contracts.
- Automation tools own capture orchestration and local export/redaction.
- This repository owns the neutral contribution ledger and published map
  projections.

Other shader projects do not need to implement CSX or DevBench. They may
produce the neutral contribution format directly or through an adapter.

## Validation

The validator has no third-party Python dependencies:

```console
python tools/validate_repository.py --repository .
python tools/compile_dataset.py --repository . --output .validation-output/snapshot.json
python -m unittest discover -s tests -p "test_*.py"
```

## Licensing

This is a multi-licensed repository:

- tools, tests, and workflow code: `GPL-3.0-or-later`;
- maps, submissions, and documentation: `CC-BY-SA-4.0`;
- interoperability schemas: `CC0-1.0`.

See [LICENSE.md](LICENSE.md) and the complete texts in [LICENSES/](LICENSES/).

Skyrim and related names and assets belong to their respective owners. This
repository is not affiliated with or endorsed by Bethesda Softworks.
