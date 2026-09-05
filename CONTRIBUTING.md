# Contributing

## Data contributions

Submit data through a pull request. A data PR must:

1. add exactly one new directory under `submissions/YYYY/MM/`;
2. include a valid `submission.json` and a `content/` directory;
3. leave every existing submission, schema, tool, and generated output
   unchanged;
4. contain only the bounded, declared file formats;
5. pass the deterministic structure check; and
6. include a Developer Certificate of Origin sign-off in each commit.

Use `git commit -s` to add the sign-off.

The structure check is intentionally binary. A rejection means that the PR is
not yet eligible for substantive map review; consult this guide and validate
the package locally.

```console
python tools/validate_repository.py --repository .
```

Passing structural validation does not mean that a conclusion has been
accepted. Maintainers review provenance, applicability, evidence quality, and
conflicts separately.

## Corrections and disagreement

Do not edit or remove accepted information. Submit a new amendment, dispute,
or resolution record that identifies the earlier record. Contradictory but
well-formed evidence can coexist and will be signalled as contested until it
is resolved.

## Tooling and governance

Changes to schemas, validators, CI, policy, or publishing tools are normal code
PRs. Do not mix them with a data submission. These changes require maintainer
review even when all automated tests pass.

## Material that is not accepted

Do not submit:

- Skyrim executables, assets, shader binaries, or substantial decompilation;
- crash or memory dumps through the ordinary contribution lane;
- usernames, machine names, account identifiers, serial numbers, IP or MAC
  addresses;
- credentials, tokens, private keys, or complete environment dumps;
- absolute local paths;
- executable files, symlinks, submodules, or nested archives.

Read [PRIVACY.md](PRIVACY.md) before publishing a capture.

## Licensing

By contributing map data or documentation, you agree to publish that material
under `CC-BY-SA-4.0`. Contribution schemas are dedicated under `CC0-1.0`, and
software contributions use `GPL-3.0-or-later`.
