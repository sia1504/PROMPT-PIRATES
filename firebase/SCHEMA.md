# Firestore schema (project `prompt-pirates`)

Types: numbers are numbers, dates are ISO strings, ids are strings, empty CSV cells become `null`.
Doc ids replace `/` with `-` (illegal in ids), e.g. `min_display/S++_Accessories (Safa-Mala-Stole)`; the original text stays in the fields.

## Source tables (uploaded by `upload.mjs`, one collection per CSV, same name)

| Collection | Doc id | Docs |
|---|---|---|
| stores | `{store_id}` | 20 |
| area_managers | `{area_manager_id}` (+ `store_ids` array parsed from `stores`) | 6 |
| items | `{sku_id}` | 385 |
| salespeople | `{salesperson_id}` | 175 |
| calendar | `{date}_{state}` | 2,373 |
| rules | `{n}` (row number, 1-based) | 8 |
| min_display | `{tier}_{category}` | 24 |
| lead_times | `{n}` | 6 |
| flagship_protected | `{store_id}_{rank}` | 80 |
| warehouse_inbound | `{n}` | 768 |
| stock_snapshot | `{location_id}_{sku_id}` | 3,547 |
| data_dictionary | `{table}_{column}` | 36 |

Chunked tables: docs `chunk_0001`.. each `{chunk, rows:[...], count, table}`. Size is measured with Firestore's stored-size formula (field names + values + doc name + 32); every doc must stay under 800 KB (hard 1 MiB limit).

| Collection | Rows | Rows/chunk | Chunks | Max doc |
|---|---|---|---|---|
| stock_weekly | 61,416 | 5,000 | 13 | ~497 KB |
| bills | 90,805 | 5,000 | 19 | ~479 KB |
| bill_lines | 259,772 | 6,000 | 44 | ~464 KB |
| roster_daily | 23,569 | 5,000 | 5 | ~334 KB |
| footfall_daily | 13,892 | 8,000 | 2 | ~383 KB |

Rows/chunk are chosen so the largest chunk lands at 330-500 KB (about 40% headroom), while keeping total writes low: all tables = about 8,500 writes, 42% of the 20,000/day free quota. One chunk read = one read, so the page loads a whole table in a few dozen reads.

## Engine output (per run, `upload.mjs --run=<date>`)

```
runs/{date}                       run, summary, validator, assumptions, schema, has_actions   (any active user)
runs/{date}/audit/{part}          part in findings|not_slow|self_audit|diff|narration; {part, data}   (merchandiser, head)
runs/{date}/actions/{action_id}   engine action + stores:[...]            e.g. RESTOCK:LKO-04 (':' is legal)
runs/{date}/actions/{action_id}/scoped/{scopeKey}   per-scope text (headline, summary, summary_hi, counts, narration); scopeKey = AM-0n | STORE:<store_id> | WH-KOL
runs/{date}/moves/{move_id}       engine move + stores:[from,to] + action_id   e.g. LKO-02>BLR-01>IW-02-XXL
runs/{date}/blocked/chunk_000n    {chunk, rows, count, table:'blocked'}, 800 rows each   (merchandiser, head)
runs/{date}/decisions/{move_id}   written by the web page, never by upload.mjs
```
Deviation from the brief: findings/not_slow/self_audit/diff are NOT on `runs/{date}` itself. Firestore rules are per document, and the run doc must be readable by every active user, so audit data sits in `runs/{date}/audit/*`.
`stores` on an action = union of from/to of all its moves plus its `store`, so donors and receivers both see it. Every move_id and action_id was verified free of `/` (the uploader throws if one appears). The current out/moves.json already has `actions[]` and `action_id` on every move; if `actions` is missing the uploader just skips them (`has_actions:false`).

Decision doc `runs/{date}/decisions/{move_id}`: `{status, qty, skip_reason, by, at}`. `status` in Proposed|Approved|Skipped|Picking|Dispatched|Received; `qty` integer 1..move.qty; `skip_reason` string (<=200) or null (key must be present); `by` = signer email (must equal the auth email); `at` ISO string. Exactly these five keys.

## Users (`users/{lowercase google email}`), assigned by an admin before first login

Answer to "which fields to add to each user to assign roles":

| Field | Type | Notes |
|---|---|---|
| email | string | equals the doc id, lowercase |
| displayName | string | |
| role | string | `merchandiser` / `head` / `area_manager` / `warehouse` / `store_manager` |
| active | bool | false = locked out |
| approval_limit_rs | number | max move `value_mrp` the user may approve: merchandiser 100000000, area_manager 100000, others 0 |
| language | string | `en` / `hi` / `kn`, default `en` |
| area_manager_id | string | area_manager only, e.g. `AM-03` |
| stores | string[] | area_manager: their store_ids; store_manager: `[store_id]`; warehouse: `[location_id]`; none for merchandiser/head |
| store_id | string | store_manager only |
| location_id | string | warehouse only (`WH-KOL`) |
| createdAt | ISO string | set on first seed |
| updatedBy | string | who last changed it (seed script sets `seed-users.mjs`) |
| notes | string | optional |

Examples (see `users.template.json`, which `seed-users.mjs` validates against exactly these rules):
```json
{ "email": "merch@example.com", "displayName": "M", "role": "merchandiser", "active": true, "approval_limit_rs": 100000000, "language": "en" }
{ "email": "head@example.com", "displayName": "H", "role": "head", "active": true, "approval_limit_rs": 0, "language": "en" }
{ "email": "am03@example.com", "displayName": "A", "role": "area_manager", "active": true, "approval_limit_rs": 100000, "language": "hi", "area_manager_id": "AM-03", "stores": ["PAT-01","PAT-02","PAT-03","PAT-04"] }
{ "email": "wh@example.com", "displayName": "W", "role": "warehouse", "active": true, "approval_limit_rs": 0, "language": "en", "location_id": "WH-KOL", "stores": ["WH-KOL"] }
{ "email": "sm.lko01@example.com", "displayName": "S", "role": "store_manager", "active": true, "approval_limit_rs": 0, "language": "hi", "store_id": "LKO-01", "stores": ["LKO-01"] }
```

## Queries the page must run (rules are not filters)

Merchandiser/head: plain `collection(db,'runs',date,'moves')`.
Area manager / warehouse / store manager must constrain `stores` to values inside their own `users.stores`:
- several stores: `where('stores','array-contains-any', userDoc.stores)` (max 30 values)
- one store: `where('stores','array-contains', storeId)`
Same for `actions`. An unconstrained list query by a scoped role is rejected outright. Reading `decisions` by id (`getDoc`) is checked against the move's scope; for lists use the same query on `moves` and `getDoc` each decision.
Risk: see "By-id fallback" below.

## Scoped action text
`actions[].scoped` (map keyed by scope key) is stripped from the action doc and stored as `runs/{date}/actions/{action_id}/scoped/{scopeKey}` (fields: `scope`, `action_id`, plus the entry). The action doc is readable by everyone whose `stores` match, so scoped text must not live in it. Rule: merchandiser/head read all; area_manager reads only key == their `area_manager_id`; store_manager only `'STORE:'+store_id`; warehouse only `WH-KOL`; no client writes. The page fetches by id: `getDoc(doc(db,'runs',date,'actions',actionId,'scoped',ownKey))`; do not list the subcollection. If the engine output has no `scoped` key nothing is written for it.

## By-id fallback (if scoped list queries are denied)
Rules already allow `getDoc` on a move whose `stores` has any of the user's stores. If `array-contains(-any)` list queries on `actions`/`moves` return permission-denied, read `actions/{id}` by id and `getDoc` each id in its `move_ids`; ids the user may not see simply come back permission-denied and should be skipped (catch per read). Note the action doc's `move_ids` lists every move of that action, so scoped users can see ids of moves outside their scope (not their contents); drop `move_ids` from the action doc later if that matters. Costs one read per move.
