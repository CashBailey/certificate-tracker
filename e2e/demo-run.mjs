import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
import { writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

const SCREENSHOTS = 'demo/screenshots';
const BASE = 'https://localhost';
const ADMIN = { email: 'admin@ci.laredo.tx.us', password: process.env.E2E_ADMIN_PASSWORD ?? '' };
const COORD = { email: 'cashbailey@ci.laredo.tx.us', password: process.env.E2E_COORDINATOR_PASSWORD ?? '' };

let stepNum = 1;
async function shot(page, name, opts = {}) {
  const num = String(stepNum++).padStart(2, '0');
  const path = join(SCREENSHOTS, `${num}_${name}.png`);
  await page.screenshot({ path, fullPage: opts.fullPage ?? true, ...opts });
  console.log(`  [shot] ${num}_${name}.png`);
  return path;
}

async function loginAs(page, creds) {
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => {});
  if (new URL(page.url()).pathname !== '/login') return;
  await page.getByLabel('Email').fill(creds.email);
  await page.getByLabel('Password').fill(creds.password);
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.waitForFunction(() => window.location.pathname !== '/login', null, { timeout: 30000 });
  await page.getByText(/^Loading\.\.\.$/).waitFor({ state: 'hidden', timeout: 30000 }).catch(() => {});
}

async function logout(page) {
  await page.getByRole('button', { name: /sign out/i }).click().catch(() => {});
  await page.waitForFunction(() => window.location.pathname === '/login', null, { timeout: 30000 }).catch(() => {});
}

async function safeGoto(page, path) {
  await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(500);
}

async function main() {
  await mkdir(SCREENSHOTS, { recursive: true });
  const browser = await chromium.launch({
    channel: 'chrome',
    headless: true,
    args: ['--ignore-certificate-errors'],
  });
  const context = await browser.newContext({
    baseURL: BASE,
    ignoreHTTPSErrors: true,
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();

  // ===== Pre-act: login screen itself =====
  console.log('Pre-act: login screen');
  await safeGoto(page, '/login');
  await shot(page, 'login_page');

  // ===== Coordinator session =====
  console.log('Coordinator: login + dashboard');
  await loginAs(page, COORD);
  await shot(page, 'coordinator_dashboard');

  console.log('Coordinator: review queue');
  await safeGoto(page, '/review');
  await page.waitForTimeout(1000);
  await shot(page, 'review_queue');

  // Try to open the first review item if any
  console.log('Coordinator: review detail (best-effort)');
  const firstReviewLink = page.locator('a[href^="/review/"]').first();
  if (await firstReviewLink.count() > 0) {
    await firstReviewLink.click();
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1500);
    await shot(page, 'review_detail');
  } else {
    console.log('  no review items present, skipping detail screenshot');
  }

  console.log('Coordinator: compliance dashboard');
  await safeGoto(page, '/compliance');
  await page.waitForTimeout(1500);
  await shot(page, 'compliance_dashboard');

  console.log('Coordinator: requirements page');
  await safeGoto(page, '/requirements');
  await page.waitForTimeout(1500);
  await shot(page, 'requirements_page');

  console.log('Coordinator: configuration / alert rules');
  await safeGoto(page, '/configuration');
  await page.waitForTimeout(1500);
  await shot(page, 'configuration_alert_rules');

  console.log('Coordinator: templates');
  await safeGoto(page, '/templates');
  await page.waitForTimeout(1000);
  await shot(page, 'templates_list');

  console.log('Coordinator: upload page');
  await safeGoto(page, '/upload');
  await page.waitForTimeout(1000);
  await shot(page, 'upload_page');

  console.log('Coordinator: notifications');
  await safeGoto(page, '/notifications');
  await page.waitForTimeout(1000);
  await shot(page, 'notifications_coord');

  console.log('Coordinator: employees');
  await safeGoto(page, '/employees');
  await page.waitForTimeout(1000);
  await shot(page, 'employees_coord');

  // Coordinator tries /admin (should be rejected)
  console.log('Coordinator: tries /admin (should be blocked)');
  await safeGoto(page, '/admin');
  await page.waitForTimeout(1000);
  await shot(page, 'coordinator_blocked_from_admin');

  await logout(page);

  // ===== Admin session =====
  console.log('Admin: login');
  await loginAs(page, ADMIN);
  await shot(page, 'admin_dashboard');

  console.log('Admin: governance audit');
  await safeGoto(page, '/audit');
  await page.waitForTimeout(1500);
  await shot(page, 'admin_audit_log');

  console.log('Admin: /admin admin home');
  await safeGoto(page, '/admin');
  await page.waitForTimeout(1500);
  await shot(page, 'admin_admin_home');

  console.log('Admin: notifications');
  await safeGoto(page, '/notifications');
  await page.waitForTimeout(1000);
  await shot(page, 'admin_notifications');

  console.log('Admin: employees');
  await safeGoto(page, '/employees');
  await page.waitForTimeout(1000);
  await shot(page, 'admin_employees');

  await context.close();
  await browser.close();
  console.log('DONE.');
}

main().catch(async (err) => {
  console.error('FAILED:', err);
  process.exit(1);
});
