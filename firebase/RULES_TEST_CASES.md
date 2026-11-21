# Rules Playground cases (manual; rules NOT emulator-tested)

Console > Firestore > Rules > Rules Playground. Set "Authenticated" with a provider of google.com, the email, and email_verified true (Firebase UID is arbitrary). Create the `users/*` docs from `users.template.json` first (or temporary copies), and one move doc `runs/2026-10-31/moves/WH-KOL>PAT-01>IW-02-L` with `stores:["WH-KOL","PAT-01"], from:"WH-KOL", to:"PAT-01", qty:7, value_mrp:50000, needs_approval:false`. The playground reads those docs, so they must exist.
Users: M=merch@example.com, H=head@example.com, A=am03 (PAT-01..04), W=wh@, S=a store manager for PAT-01 (change store_id/stores in a temp copy).
Decision body: `{status, qty, skip_reason:null, by:<email>, at:"2026-10-31T10:00:00Z"}`.

| # | Who | Path | Op | Expect |
|---|---|---|---|---|
| 1 | not signed in | /stores/LKO-01 | get | deny |
| 2 | email_verified false | /stores/LKO-01 | get | deny |
| 3 | verified email with no users doc | /stores/LKO-01 | get | deny |
| 4 | user with active:false | /stores/LKO-01 | get | deny |
| 5 | A | /stores/LKO-01 | get | allow |
| 6 | M | /stores/LKO-01 | update | deny |
| 7 | A | /users/am03@example.com | get | allow |
| 8 | A | /users/merch@example.com | get | deny |
| 9 | M | /users/merch@example.com | update | deny |
| 10 | A | /bills/chunk_0001 | get | deny |
| 11 | H | /bills/chunk_0001 | get | allow |
| 12 | S | /stock_snapshot/BLR-01_IW-01-L | get | deny |
| 13 | A | /runs/2026-10-31 | get | allow |
| 14 | A | /runs/2026-10-31/audit/findings | get | deny |
| 15 | M | /runs/2026-10-31/audit/findings | get | allow |
| 16 | A | /runs/2026-10-31/blocked/chunk_0001 | get | deny |
| 17 | A | the PAT-01 move | get | allow |
| 18 | A | a move with stores [BLR-01,WH-KOL] | get | deny |
| 19 | H | any move | get | allow |
| 20 | M | decisions/{move_id} create, status Approved, qty 7 | create | allow |
| 21 | M | same, qty 8 (move qty 7) | create | deny |
| 22 | M | same, qty 0 or 2.5 | create | deny |
| 23 | M | same, by = other email | create | deny |
| 24 | M | same, extra key `foo` | create | deny |
| 25 | A | decision on PAT-01 move above (needs_approval false, from WH-KOL) | create Approved | deny (WH-KOL not in A's stores) |
| 26 | A | decision on a move with from/to both in PAT-*, needs_approval false, value <= 100000 | create Approved | allow |
| 27 | A | same move but needs_approval true | create | deny |
| 28 | A | same move but value_mrp 150000 | create | deny |
| 29 | A | same move, status Picking | create | deny |
| 30 | H | any decision | create | deny |
| 31 | W | decision on the WH-KOL move, no prior decision, status Picking | create | deny |
| 32 | W | same, prior decision Approved, status Picking | update | allow |
| 33 | W | prior Picking, status Dispatched | update | allow |
| 34 | W | prior Proposed, status Dispatched | update | deny |
| 35 | W | status Approved | update | deny |
| 36 | W | move whose from is not WH-KOL | update | deny |
| 37 | S (PAT-01) | prior Dispatched, status Received, move to=PAT-01 | update | allow |
| 38 | S | prior Proposed, status Received | update | deny |
| 39 | S | move to=PAT-02 | update | deny |
| 40 | S | status Approved | update | deny |
| 41 | A | prior Dispatched (after W), status Approved | update | deny (cannot rewind) |
| 42 | M | any decision | delete | deny |
| 43 | anyone | /somethingelse/x | get | deny |
| 44 | S | decisions/{PAT-01 move} | get | allow |
| 45 | S | decisions/{move not touching PAT-01} | get | deny |

Scoped action text (create `runs/2026-10-31/actions/RESTOCK:PAT-01/scoped/AM-03`, `.../scoped/STORE:PAT-01`, `.../scoped/WH-KOL`, `.../scoped/AM-01` first):

| # | Who | Path (under runs/2026-10-31/actions/RESTOCK:PAT-01/scoped/) | Op | Expect |
|---|---|---|---|---|
| 46 | A (AM-03) | AM-03 | get | allow |
| 47 | A (AM-03) | AM-01 | get | deny |
| 48 | A | STORE:PAT-01 | get | deny |
| 49 | S (PAT-01) | STORE:PAT-01 | get | allow |
| 50 | S (PAT-01) | STORE:PAT-02 | get | deny |
| 51 | W | WH-KOL | get | allow |
| 52 | W | AM-03 | get | deny |
| 53 | M | any scoped doc | get | allow |
| 54 | H | any scoped doc | get | allow |
| 55 | M | any scoped doc | create/update | deny |
| 56 | user with active:false | own key | get | deny |
