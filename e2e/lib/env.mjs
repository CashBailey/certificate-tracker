import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const REPO_ROOT = process.env.REPO_ROOT ?? join(dirname(fileURLToPath(import.meta.url)), '..', '..');
export const E2E_ROOT = join(REPO_ROOT, 'e2e');
export const TMP_ROOT = join(E2E_ROOT, 'tmp');
export const RESULTS_ROOT = join(E2E_ROOT, 'results');
export const BASE_URL = 'https://localhost';
export const ADMIN_EMAIL = 'admin@ci.laredo.tx.us';
export const COORDINATOR_EMAIL = 'cashbailey@ci.laredo.tx.us';
export const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? '';
export const COORDINATOR_PASSWORD = process.env.E2E_COORDINATOR_PASSWORD ?? '';

mkdirSync(TMP_ROOT, { recursive: true });
mkdirSync(RESULTS_ROOT, { recursive: true });

export function shell(command, options = {}) {
  return execFileSync('bash', ['-lc', command], {
    cwd: REPO_ROOT,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    ...options,
  }).trim();
}

export function dockerPsql(query, options = {}) {
  return shell(
    `docker exec -i -e PGPASSWORD=laredo_dev_password laredo-postgres ` +
      `psql -U laredo -d laredo_certificates -P footer=off -A -F $'\\t' <<'SQL'\n` +
      `${query}\n` +
      `SQL`,
    options,
  );
}

export function greenmailReset() {
  shell('curl -s -X POST http://127.0.0.1:8080/api/service/reset >/dev/null');
}

export function resetSlowApiLimits() {
  shell(
    `docker exec laredo-redis sh -lc '` +
      `redis-cli --tls --cert /tls/client.crt --key /tls/client.key --cacert /tls/ca.crt -p 6380 --scan ` +
      `| grep -E "^(LIMITS:LIMITER|login_failures:)" ` +
      `| xargs -r redis-cli --tls --cert /tls/client.crt --key /tls/client.key --cacert /tls/ca.crt -p 6380 del >/dev/null'`,
  );
}

function shellSingleQuote(value) {
  return `'${String(value).replace(/'/g, `'\"'\"'`)}'`;
}

export function setEmployeePassword(email, password) {
  const passwordHash = shell(
    `docker exec -i -e AUDIT_PASSWORD=${shellSingleQuote(password)} laredo-api python - <<'PY'\n` +
      `import os\n` +
      `from src.auth.security import hash_password\n` +
      `print(hash_password(os.environ["AUDIT_PASSWORD"]))\n` +
      `PY`,
  );
  const escapedHash = passwordHash.replace(/'/g, "''");
  const escapedEmail = email.replace(/'/g, "''");
  dockerPsql(
    `UPDATE certificates.employees ` +
      `SET password_hash = '${escapedHash}', is_active = TRUE ` +
      `WHERE email = '${escapedEmail}';`,
  );
}

export function greenmailLatest(email) {
  const encoded = encodeURIComponent(email);
  const raw = shell(`curl -s "http://127.0.0.1:8080/api/user/${encoded}/messages"`);
  const data = JSON.parse(raw);
  if (!Array.isArray(data) || data.length === 0) {
    return null;
  }
  return data[data.length - 1];
}

export function extractResetLink(message) {
  if (!message?.mimeMessage) return null;
  const match = message.mimeMessage.match(/https:\/\/localhost\/reset-password#token=[a-f0-9]+/i);
  return match?.[0] ?? null;
}

export function writeResultFile(name, content) {
  const path = join(RESULTS_ROOT, name);
  writeFileSync(path, content);
  return path;
}

export function readSamplePdfPath() {
  return join(REPO_ROOT, 'SampleDocs', 'lms_certificate', 'certificate_6275_preview.pdf');
}

export function readSampleImagePath() {
  return join(
    REPO_ROOT,
    'SimulationForTesting',
    'SampleDocs',
    'RachelSullivan_CPR-BLS_2026-02-03_CityOfLaredoPublicHealth.png',
  );
}

export function createOversizedFile() {
  const path = join(TMP_ROOT, 'oversized.pdf');
  const data = Buffer.alloc(21 * 1024 * 1024, 0x41);
  writeFileSync(path, data);
  return path;
}

export function createEmptyFile() {
  const path = join(TMP_ROOT, 'empty.pdf');
  writeFileSync(path, '');
  return path;
}

export function createCorruptPdf() {
  const path = join(TMP_ROOT, 'corrupt.pdf');
  writeFileSync(path, 'not-a-real-pdf');
  return path;
}

export function createFakePdf() {
  const path = join(TMP_ROOT, 'fake.pdf');
  writeFileSync(path, 'MZ executable bytes that are definitely not a pdf');
  return path;
}

export function parseTsvRows(tsv) {
  return tsv
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.split('\t'));
}
