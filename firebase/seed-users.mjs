#!/usr/bin/env node
// Write users/{lowercase email} from firebase/users.json (gitignored). Dry-run by default.
//   node seed-users.mjs            validate + print
//   node seed-users.mjs --commit   write (needs credentials, same as upload.mjs)
import { existsSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { readCsv } from './csv.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const commit = process.argv.includes('--commit');
const file = join(here, 'users.json');
if (!existsSync(file)) { console.error('firebase/users.json not found. Copy users.template.json to users.json and edit it.'); process.exit(1); }

const ROLES = ['merchandiser', 'head', 'area_manager', 'warehouse', 'store_manager'];
const LIMITS = { merchandiser: 100000000, area_manager: 100000, head: 0, warehouse: 0, store_manager: 0 };
const BASE = ['email', 'displayName', 'role', 'active', 'approval_limit_rs', 'language', 'createdAt', 'updatedBy', 'notes'];
const SCOPE = { area_manager: ['area_manager_id', 'stores'], store_manager: ['store_id', 'stores'], warehouse: ['location_id', 'stores'], merchandiser: [], head: [] };

const stores = new Set(['WH-KOL']);
const sf = resolve(here, '..', 'data', 'stores.csv');
if (existsSync(sf)) readCsv(sf).forEach((r) => stores.add(r.store_id));
const amf = resolve(here, '..', 'data', 'area_managers.csv');
const ams = existsSync(amf) ? new Set(readCsv(amf).map((r) => r.area_manager_id)) : null;

const list = JSON.parse(readFileSync(file, 'utf8'));
const docs = [], errs = [];
for (const [i, u] of list.entries()) {
  const e = (m) => errs.push(`#${i + 1} ${u.email ?? '?'}: ${m}`);
  const email = String(u.email ?? '').trim().toLowerCase();
  if (!/^[^@\s/]+@[^@\s/]+\.[^@\s/]+$/.test(email)) e('invalid email');
  if (!ROLES.includes(u.role)) { e(`role must be one of ${ROLES.join(', ')}`); continue; }
  if (typeof u.displayName !== 'string' || !u.displayName) e('displayName required (string)');
  if (typeof u.active !== 'boolean') e('active must be true/false');
  const lang = u.language ?? 'en';
  if (!['en', 'hi', 'kn'].includes(lang)) e('language must be en|hi|kn');
  const limit = u.approval_limit_rs ?? LIMITS[u.role];
  if (typeof limit !== 'number' || limit < 0) e('approval_limit_rs must be a number >= 0');
  const extra = Object.keys(u).filter((k) => !BASE.includes(k) && !SCOPE[u.role].includes(k));
  if (extra.length) e(`fields not allowed for role ${u.role}: ${extra.join(', ')}`);
  const need = SCOPE[u.role];
  for (const f of need) if (u[f] === undefined) e(`${f} required for ${u.role}`);
  const known = (s) => (stores.size > 1 && !stores.has(s) ? e(`unknown store/location "${s}"`) : 0);
  if (u.role === 'area_manager') {
    if (!/^AM-\d+$/.test(u.area_manager_id ?? '')) e('area_manager_id must look like AM-03');
    else if (ams && !ams.has(u.area_manager_id)) e(`unknown area_manager_id ${u.area_manager_id}`);
    if (!Array.isArray(u.stores) || !u.stores.length || !u.stores.every((s) => typeof s === 'string')) e('stores must be a non-empty array of store_ids');
    else u.stores.forEach(known);
  }
  if (u.role === 'store_manager') {
    if (typeof u.store_id !== 'string') e('store_id must be a string');
    else known(u.store_id);
    if (JSON.stringify(u.stores) !== JSON.stringify([u.store_id])) e('stores must equal [store_id]');
  }
  if (u.role === 'warehouse') {
    if (typeof u.location_id !== 'string') e('location_id must be a string');
    else known(u.location_id);
    if (JSON.stringify(u.stores) !== JSON.stringify([u.location_id])) e('stores must equal [location_id]');
  }
  docs.push({ id: email, data: { ...u, email, approval_limit_rs: limit, language: lang, createdAt: u.createdAt ?? new Date().toISOString(), updatedBy: 'seed-users.mjs' } });
}
const ids = docs.map((d) => d.id);
ids.filter((x, i) => ids.indexOf(x) !== i).forEach((x) => errs.push(`duplicate email ${x}`));
if (errs.length) { console.error('Validation failed:\n  ' + errs.join('\n  ')); process.exit(1); }

console.log(`${docs.length} valid user(s):`);
docs.forEach((d) => console.log(`  users/${d.id}  role=${d.data.role}  active=${d.data.active}`));
if (!commit) { console.log('\nDry run: nothing written. Use --commit.'); process.exit(0); }

const gac = process.env.GOOGLE_APPLICATION_CREDENTIALS;
if (!(gac && existsSync(gac)) && !existsSync(join(homedir(), '.config', 'gcloud', 'application_default_credentials.json'))) {
  console.error('No credentials: set GOOGLE_APPLICATION_CREDENTIALS to your service-account JSON path (outside the repo). See README.md.');
  process.exit(2);
}
const { initializeApp, applicationDefault } = await import('firebase-admin/app');
const { getFirestore } = await import('firebase-admin/firestore');
const db = getFirestore(initializeApp({ credential: applicationDefault(), projectId: 'prompt-pirates' }));
for (const d of docs) {
  // createdAt only set on first write
  const ref = db.doc(`users/${d.id}`);
  const snap = await ref.get();
  if (snap.exists) delete d.data.createdAt;
  await ref.set(d.data, { merge: true });
  console.log(`  wrote users/${d.id}`);
}
