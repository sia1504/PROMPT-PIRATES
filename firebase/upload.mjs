#!/usr/bin/env node
// Upload Stock Mover data + engine output to Firestore. Dry-run by default.
//   node upload.mjs                      dry run, everything
//   node upload.mjs --only=stores,runs   dry run, subset
//   node upload.mjs --commit             really write (needs credentials)
// Flags: --run=<date> --data=<dir> --out=<moves.json>
import { existsSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { readCsv } from './csv.mjs';
import { TABLES, MAX_DOC_BYTES } from './tables.mjs';

const PROJECT_ID = 'prompt-pirates';
const FREE_WRITES_PER_DAY = 20000;
const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');

const args = Object.fromEntries(
  process.argv.slice(2).map((a) => {
    const [k, v] = a.replace(/^--/, '').split('=');
    return [k, v ?? true];
  }),
);
const commit = args.commit === true;
const dataDir = resolve(root, args.data || 'data');
const outFile = resolve(root, args.out || 'out/moves.json');
const only = args.only ? String(args.only).split(',') : null;
const want = (c) => !only || only.includes(c);

// ---- Firestore stored-size estimate (documented formula), used for the 800 KB check ----
function size(v, path = '') {
  if (v === null || typeof v === 'boolean') return 1;
  if (typeof v === 'number') return 8;
  if (typeof v === 'string') return Buffer.byteLength(v) + 1;
  if (Array.isArray(v)) {
    return v.reduce((s, x) => {
      if (Array.isArray(x)) throw new Error(`nested array not allowed in Firestore at ${path}`);
      return s + size(x, path);
    }, 0);
  }
  if (typeof v === 'object') {
    return Object.entries(v).reduce((s, [k, x]) => s + Buffer.byteLength(k) + 1 + size(x, `${path}.${k}`), 0);
  }
  throw new Error(`unsupported value (${typeof v}) at ${path}`);
}
const docBytes = (path, data) => path.length + 17 + 32 + size(data, path);

// Replace undefined/NaN with null so Firestore accepts the doc.
const clean = (v) => {
  if (v === undefined || (typeof v === 'number' && !Number.isFinite(v))) return null;
  if (Array.isArray(v)) return v.map(clean);
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, clean(x)]));
  return v;
};

// ---- Build plan: Map<collectionLabel, [{path, data}]> ----
const plan = new Map();
const add = (label, path, data) => {
  if (!plan.has(label)) plan.set(label, []);
  plan.get(label).push({ path, data: clean(data) });
};
const typed = (row, num) => {
  const o = {};
  for (const [c, v] of Object.entries(row)) {
    const t = v.trim();
    o[c] = t === '' ? null : num.includes(c) ? Number(t) : t;
    if (num.includes(c) && t !== '' && Number.isNaN(o[c])) throw new Error(`non-numeric ${c}="${t}"`);
  }
  return o;
};

for (const [name, spec] of Object.entries(TABLES)) {
  if (!want(name)) continue;
  const file = join(dataDir, `${name}.csv`);
  if (!existsSync(file)) { console.warn(`! missing ${file}, skipped`); continue; }
  const rows = readCsv(file).map((r) => typed(r, spec.num));
  if (spec.kind === 'doc') {
    const seen = new Set();
    rows.forEach((r, i) => {
      const id = spec.id(r, i).replaceAll('/', '-'); // '/' is illegal in a doc id (e.g. "Accessories (Safa/Mala/Stole)")
      if (seen.has(id)) throw new Error(`${name}: duplicate doc id "${id}"`);
      seen.add(id);
      add(name, `${name}/${id}`, { ...r, ...(spec.extra ? spec.extra(r) : {}) });
    });
  } else {
    for (let i = 0, c = 1; i < rows.length; i += spec.per, c++) {
      const part = rows.slice(i, i + spec.per);
      add(name, `${name}/chunk_${String(c).padStart(4, '0')}`, { chunk: c, rows: part, count: part.length, table: name });
    }
  }
}

// ---- Engine output ----
if (want('runs')) {
  if (!existsSync(outFile)) console.warn(`! ${outFile} not found, runs skipped`);
  else {
    const out = JSON.parse(readFileSync(outFile, 'utf8'));
    const date = out.run?.date;
    if (args.run && args.run !== date) {
      const alt = resolve(dirname(outFile), `moves-${args.run}.json`);
      if (!existsSync(alt)) throw new Error(`--run=${args.run} requested but ${outFile} is run ${date} and ${alt} does not exist`);
      Object.assign(out, JSON.parse(readFileSync(alt, 'utf8')));
    }
    const d = out.run.date;
    const base = `runs/${d}`;
    // Public-to-any-active-user run doc; audit material lives in runs/{d}/audit/* (merchandiser/head only).
    add('runs', base, {
      run: out.run, summary: out.summary, validator: out.validator, assumptions: out.assumptions ?? [],
      schema: out.schema ?? null, has_actions: Array.isArray(out.actions),
    });
    for (const part of ['findings', 'not_slow', 'self_audit', 'diff', 'narration']) {
      if (out[part] !== undefined) add('runs/audit', `${base}/audit/${part}`, { part, data: out[part] });
    }
    const moveById = new Map(out.moves.map((m) => [m.move_id, m]));
    const actionOf = new Map();
    for (const a of out.actions ?? []) {
      const stores = new Set();
      for (const mid of a.move_ids) {
        const m = moveById.get(mid);
        if (m) { stores.add(m.from); stores.add(m.to); actionOf.set(mid, a.action_id); }
      }
      if (a.store) stores.add(a.store);
      if (a.action_id.includes('/')) throw new Error(`action id with "/": ${a.action_id}`);
      const { scoped, ...pub } = a; // scoped text must never sit in the shared action doc
      add('runs/actions', `${base}/actions/${a.action_id}`, { ...pub, stores: [...stores].sort() });
      for (const [key, v] of Object.entries(scoped ?? {})) {
        if (key.includes('/')) throw new Error(`scope key with "/": ${key}`);
        add('runs/scoped', `${base}/actions/${a.action_id}/scoped/${key}`, { scope: key, action_id: a.action_id, ...v });
      }
    }
    for (const m of out.moves) {
      if (m.move_id.includes('/')) throw new Error(`move id with "/": ${m.move_id}`);
      add('runs/moves', `${base}/moves/${m.move_id}`, {
        ...m, stores: [...new Set([m.from, m.to])], action_id: m.action_id ?? actionOf.get(m.move_id) ?? null,
      });
    }
    const per = 800;
    for (let i = 0, c = 1; i < (out.blocked ?? []).length; i += per, c++) {
      const part = out.blocked.slice(i, i + per);
      add('runs/blocked', `${base}/blocked/chunk_${String(c).padStart(4, '0')}`, { chunk: c, rows: part, count: part.length, table: 'blocked' });
    }
  }
}

// ---- Report ----
const pad = (s, n) => String(s).padEnd(n);
let total = 0, maxBytes = 0, maxPath = '', bad = 0;
console.log(`\n${commit ? 'COMMIT' : 'DRY RUN'}  project=${PROJECT_ID}  data=${dataDir}\n`);
console.log(pad('collection', 20) + pad('docs', 8) + pad('chunk docs', 12) + pad('max doc KB', 12) + 'largest doc');
for (const [label, docs] of plan) {
  let mx = 0, mp = '';
  for (const d of docs) {
    const b = docBytes(d.path, d.data);
    if (b > mx) { mx = b; mp = d.path; }
  }
  if (mx > MAX_DOC_BYTES) bad++;
  if (mx > maxBytes) { maxBytes = mx; maxPath = mp; }
  const isChunk = /chunk_/.test(docs[0].path);
  total += docs.length;
  console.log(pad(label, 20) + pad(docs.length, 8) + pad(isChunk ? docs.length : '-', 12) + pad((mx / 1024).toFixed(1), 12) + mp);
}
console.log(`\nTotal writes: ${total}   largest doc: ${(maxBytes / 1024).toFixed(1)} KB (${maxPath})`);
console.log(`Free quota: ${total} of ${FREE_WRITES_PER_DAY} writes/day = ${((total / FREE_WRITES_PER_DAY) * 100).toFixed(1)}%  -> ${total <= FREE_WRITES_PER_DAY ? 'OK, fits free tier' : 'OVER the free tier, split with --only and run on different days'}`);
if (bad) { console.error(`\nERROR: ${bad} collection(s) have docs over ${MAX_DOC_BYTES / 1024} KB; lower rows-per-chunk in tables.mjs`); process.exit(1); }
if (!commit) { console.log('\nDry run only: nothing was sent. Re-run with --commit to write.'); process.exit(0); }

// ---- Commit ----
const gac = process.env.GOOGLE_APPLICATION_CREDENTIALS;
const adc = join(homedir(), '.config', 'gcloud', 'application_default_credentials.json');
if (!(gac && existsSync(gac)) && !existsSync(adc)) {
  console.error(
    '\nNo credentials found. Set GOOGLE_APPLICATION_CREDENTIALS to the path of your service-account JSON\n' +
    '(kept OUTSIDE this repo), e.g.\n  export GOOGLE_APPLICATION_CREDENTIALS=$HOME/secrets/prompt-pirates-sa.json\n' +
    'or run `gcloud auth application-default login`. See firebase/README.md.',
  );
  process.exit(2);
}
const { initializeApp, applicationDefault } = await import('firebase-admin/app');
const { getFirestore } = await import('firebase-admin/firestore');
const db = getFirestore(initializeApp({ credential: applicationDefault(), projectId: PROJECT_ID }));
const writer = db.bulkWriter();
let done = 0, failed = 0;
writer.onWriteError((e) => {
  if (e.failedAttempts < 5) return true; // BulkWriter backs off and retries
  failed++;
  console.error(`FAILED ${e.documentRef.path}: ${e.message}`);
  return false;
});
const t0 = Date.now();
for (const docs of plan.values()) {
  for (const d of docs) {
    writer.set(db.doc(d.path), d.data, { merge: true }).then(() => {
      if (++done % 500 === 0) console.log(`  ${done}/${total} written`);
    }, () => {});
  }
}
await writer.close();
console.log(`\nDone: ${done}/${total} written, ${failed} failed, ${((Date.now() - t0) / 1000).toFixed(1)}s`);
process.exit(failed ? 1 : 0);
