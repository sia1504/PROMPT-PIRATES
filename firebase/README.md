# Firebase setup (Stock Mover)

Project id `prompt-pirates`. The web config in the page is public by design; access is controlled by `firestore.rules` and `users/*`. Never commit keys or `users.json`.

## One-time console steps
1. Firebase console > Build > Authentication > Get started > Sign-in method > enable **Google**.
2. Authentication > Settings > Authorized domains: make sure `localhost` is listed (and `prompt-pirates.firebaseapp.com`).
3. Build > Firestore Database > Create database > **Native mode** (not Datastore mode), pick a region near India (asia-south1), start in production mode.
4. Open the page at **http://localhost:8000** (`python3 -m http.server 8000` in the repo root), NOT `127.0.0.1` (not an authorized domain).
5. Service account for uploads: Project settings > Service accounts > Generate new private key. Save the JSON **outside the repo** (e.g. `~/secrets/prompt-pirates-sa.json`), `chmod 600` it. Never paste it in chat.

## Commands (run inside `firebase/`)
```bash
cd firebase && npm install
export GOOGLE_APPLICATION_CREDENTIALS=$HOME/secrets/prompt-pirates-sa.json

node upload.mjs                          # dry run: counts, sizes, quota verdict. touches nothing
node upload.mjs --commit                 # write everything (data/ + latest out/moves.json)
node upload.mjs --only=runs --run=2026-10-31 --commit   # just engine output for a run
node upload.mjs --only=stores,items --commit            # subset

cp users.template.json users.json        # edit with real emails (gitignored)
node seed-users.mjs                      # validate
node seed-users.mjs --commit             # write users/{lowercase email}

npx firebase-tools login
npx firebase-tools deploy --only firestore:rules --project prompt-pirates
```
Upload is idempotent (deterministic ids, `set` with merge): re-running overwrites the same docs. Full upload is about 8,500 writes (free quota 20,000/day); do not run it more than twice in a day. If a later run has fewer chunks than an earlier one, stale high-numbered `chunk_000n` docs stay; delete them in the console.
Use `--data=<dir>` / `--out=<file>` to point at other inputs.

## Rollback
- Rules: Firebase console > Firestore > Rules > History > restore the previous version (or redeploy an older `firestore.rules` from git).
- Data: collections are plain docs; delete a collection in the console (Firestore > the collection > Delete collection) and re-upload. A bad user: set `active:false` on its `users/` doc, or delete the doc.
- Engine run: delete `runs/{date}` and its subcollections (console, or `npx firebase-tools firestore:delete runs/<date> -r --project prompt-pirates`).

See `SCHEMA.md` (data model, user fields, required page queries) and `RULES_TEST_CASES.md`.
