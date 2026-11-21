# Firebase lane notes

Everything lives in `firebase/` (see its README.md, SCHEMA.md, RULES_TEST_CASES.md).
- Dry run on real data: 8,519 writes without scoped docs (42.6% of the 20k/day free quota), largest doc 497 KB (limit set at 800 KB).
- Deviation: findings/not_slow/self_audit/diff/narration go to `runs/{date}/audit/{part}` (not on the run doc) so rules can restrict them to merchandiser/head.
- Doc ids: `/` replaced by `-` (min_display "Safa/Mala/Stole", data_dictionary "city / state / zone").
- Rules were NOT tested in the emulator (brace balance + line review only). Open risk: list queries with `array-contains-any` proven against a `get()`-derived list; test on the real page.
- Nothing was uploaded; no credentials were used.
- Scoped per-scope action text goes to runs/{date}/actions/{id}/scoped/{scopeKey} (rule on doc id); stripped from the action doc. Writes grow by one per scope entry (a few hundred), still well under quota.
