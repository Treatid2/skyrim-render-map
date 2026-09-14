# Repository working agreements

- Map any Skyrim engine domain and evidenced relationships across domains;
  rendering is one domain. Follow `docs/engine-map.md` for scope and provenance.
- Preserve the existing repository, schema, URN, and content identity contracts
  when changing display names or organizing maps. Never broaden old claims.
- Keep scope examples and synthetic test fixtures outside the evidence ledger.
- Treat accepted submissions as immutable evidence.
- Data PRs add one new `submissions/YYYY/MM/<submission-id>` directory only.
- Corrections are new amendment or resolution records; never rewrite history.
- Do not assign greater authority to Treatid2 or the bootstrap imports.
- Keep mechanical validation deterministic and non-LLM.
- Never execute contributor-controlled files during validation.
- Keep producer observations separate from derived map conclusions.
- Record exact schema, source, build, artifact, and applicability identities.
- Use the path-specific licences documented in `LICENSE.md`.
- Commit with a concise Conventional Commit subject and a body containing
  `Rationale:` and `Implementation:` sections.
