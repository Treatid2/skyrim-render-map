# Contributing

## Data contributions

Submit data through a pull request. A data PR must:

1. add exactly one new directory under `submissions/YYYY/MM/`;
2. include a valid `submission.json` and a `content/` directory;
3. leave every existing submission, schema, tool, and generated output
   unchanged;
4. contain only the bounded, declared file formats;
5. pass the deterministic structure check; and
6. declare `candidate-unreviewed` status and the contributor's GitHub identity;
   and
7. include a Developer Certificate of Origin sign-off in each commit.

Use `git commit -s` to add the sign-off.

The structure check is intentionally binary. A rejection means that the PR is
not yet eligible for substantive map review; consult this guide and validate
the package locally.

```console
python tools/validate_repository.py --repository .
```

Repository mode validates the complete tree, including historical submissions.
It does not compare a proposed contribution with `main` and therefore does not
exercise the candidate-only status and GitHub-attribution checks.

To reproduce the pull-request admission check, prepare separate clean checkouts
of current `main` and the candidate tree, then run the validator from the
trusted `main` checkout:

```console
python <main-tree>/tools/validate_repository.py --base-tree <main-tree> --candidate-tree <candidate-tree>
```

`<main-tree>` is the clean current canonical tree and `<candidate-tree>` is the
complete proposed tree. Always execute the validator supplied by `<main-tree>`;
candidate files are inert input and must not supply executable validation code.

Passing structural validation makes a submission eligible for admission
review. Merging admits its immutable evidence to the ledger; it does not
certify or endorse the conclusion. Maintainers apply the bounded criteria in
[the admission and moderation policy](docs/admission-and-moderation.md).

Assertion and amendment submissions place canonical records in
`content/assertions.jsonl` and declare new subjects in
`content/entities.jsonl`. Resolution submissions use
`content/resolutions.jsonl`. See [docs/semantic-ledger.md](docs/semantic-ledger.md)
and the schemas under `schemas/contribution/`.

Performance observations use `content/performance-observations.jsonl` and the
exact identity, sampling, contamination, privacy, grouping, and outlier
contracts in
[the performance contribution guide](docs/performance-contributions.md).

Before opening a PR, also run:

```console
python tools/compile_dataset.py --repository . --output .validation-output/snapshot.json
```

Do not commit generated snapshots; they are deterministic projections used
for review and publication.

## Corrections and disagreement

Do not edit or remove accepted information. Submit a new amendment, dispute,
or resolution record that identifies the earlier record. Contradictory but
well-formed evidence can coexist and will be signalled as contested until it
is resolved.

## Admission review

Before enabling merge, the maintainer records that:

- the trusted structure and deterministic compile checks passed against the
  current canonical tree;
- the contribution is relevant, coherent, inspectable, and no broader than its
  evidence and applicability;
- provenance, unavailable evidence, transformations, uncertainty, and known
  conflicts are disclosed;
- privacy, licensing, artifact, and DCO requirements are satisfied; and
- the contribution is not obvious fabrication, spam, abusive duplication, or
  volume abuse.

Technical reproduction is not required for admission. A reviewer must not
describe admission as proof. A previously unexplored assertion normally enters
the generated map as provisional; lack of disagreement is not corroboration.

Conflicts are review signals rather than automatic rejection. Reject or hold a
submission only for a reason enumerated in the admission policy, and record the
reason in the pull request.

## Tooling and governance

Changes to schemas, validators, CI, policy, or publishing tools are normal code
PRs. Do not mix them with a data submission. These changes require maintainer
review even when all automated tests pass.

## Material that is not accepted

Do not submit:

- Skyrim executables, assets, shader binaries, or substantial decompilation;
- crash or memory dumps through the ordinary contribution lane;
- usernames, machine names, account identifiers, serial numbers, IP or MAC
  addresses, except for the contributor-chosen public GitHub identity required
  in `submission.json`;
- credentials, tokens, private keys, or complete environment dumps;
- absolute local paths;
- executable files, symlinks, submodules, or nested archives.

Read [PRIVACY.md](PRIVACY.md) before publishing a capture.

## Licensing

By contributing map data or documentation, you agree to publish that material
under `CC-BY-SA-4.0`. Contribution schemas are dedicated under `CC0-1.0`, and
software contributions use `GPL-3.0-or-later`.
