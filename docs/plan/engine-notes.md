# Engine notes (plan vs data)
- 319 (store, sku) pairs sold 862 units in the 28-day window but have NO row in `stock_snapshot.csv` (zero-stock rows omitted). lld says `pos` = snapshot rows, so `build_position(inp, cfg)` still returns exactly 3,547 rows (T2 Accept). `run.py` calls it with `include_implied=True`, which adds those pairs as zero-stock rows: they are the real "selling with no stock" needs (F4) and their velocity belongs in `v_style` (validator R5 sums v over all sizes of a style, so omitting them made the engine pass moves the validator rejected).
- Quarantined units (KNP-03 SHW-02-L 300) count for capacity (A7) but not for style/category on-hand used by donor-cover and min-display. Otherwise KNP-03 looks like a rich SHW-02 donor.
- Validator R5 judges ALL outflow of a (store, style) once that style has any store->store move, so a later PULL_BACK of the same style is held to the 30-day style rule too (engine: `Ledger.s2s_styles`).
- `evidence.to_on_hand/to_in_transit/to_cover_before` are the pre-plan receiver position; `to_cover_after` includes all units allocated to that need so far.
- Added to contract: `validator.badge` (string), `Inputs.monthly`, `Inputs.row_counts`. Written header-only: `out/approved.csv`, `out/pick-list.csv`. `out/validation.json` is the validator's raw result.
- Exceptions are 232 of 960 moves (THIN_DATA 137, CROSS_ZONE 110, NEW_STORE 30); build-spec T10 target is ~40. Tuning left for T10.

## Consolidation + Sarvam (engine/consolidate.py, narrate.py)
- 38 actions (19 RESTOCK by destination, 19 CLEAR by source); every move carries `action_id`. Sort: needs_decision, urgency asc (null last), value desc.
- Facts sent to the model are counts/strings from code (donor list trimmed to 3 names + a count, value pre-formatted `Rs 8,38,425`). Verifier: digit-runs must be in facts (store-code digits and date parts count as allowed), store codes in facts or WH-KOL, JSON keys exact, limits headline 70 / summary 220 / Hindi 260, Devanagari present, finish_reason stop. Prompt asks 200/230 so answers fit.
- One re-ask is allowed when an answer is rejected (not only on 429/5xx) because the first pass accepted only 26 of 38. Cache key includes prompt version (v2) + facts.
- Template mode: narration `{source:'template', checked:false}`. `payload.narration` holds run stats. `demo/moves.js` is overwritten after a clean run unless --no-demo-copy; a `--no-llm` run also overwrites out/moves.js (use --no-demo-copy if needed). Narration run takes ~55 s cold (1.1 s spacing x 38 + retries), ~1 s warm, so NFR-1 (60 s) holds only warm or with --no-llm.
- Allowed-number check is lenient: a model could swap two numbers that both appear in the facts. Acceptable per brief (digit membership).
