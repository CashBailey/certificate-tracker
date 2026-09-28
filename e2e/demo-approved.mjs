import { chromium } from 'playwright';
import { join } from 'node:path';

const SCREENSHOTS = 'demo/screenshots';
const BASE = 'https://localhost';
const COORD = { email: 'cashbailey@ci.laredo.tx.us', password: process.env.E2E_COORDINATOR_PASSWORD ?? '' };

async function loginAs(page, creds) {
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.getByLabel('Email').fill(creds.email);
  await page.getByLabel('Password').fill(creds.password);
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.waitForFunction(() => window.location.pathname !== '/login', null, { timeout: 30000 });
}

async function shot(page, name) {
  await page.screenshot({ path: join(SCREENSHOTS, `${name}.png`), fullPage: false });
  console.log(`  [shot] ${name}.png`);
}

async function main() {
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
  await loginAs(page, COORD);

  // Approved record id — there are 4550 approved per the queue counter, so
  // any small id from the early ones should exist. 24400 was Approved per
  // the queue screenshot.
  await page.goto(`${BASE}/review/24400`, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(2500);
  await shot(page, '03g_review_detail_approved_24400');

  // Reports redirect: /reports should redirect to /compliance
  await page.goto(`${BASE}/reports`, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(1500);
  await shot(page, '04b_reports_redirect_to_compliance');

  // Configuration Alert Rules tab
  await page.goto(`${BASE}/configuration`, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(1200);
  const alertRulesTab = page.getByRole('button', { name: /alert rules/i }).first();
  if (await alertRulesTab.count() > 0) {
    await alertRulesTab.click();
    await page.waitForTimeout(1200);
    await shot(page, '06b_configuration_alert_rules_tab');
  }

  await context.close();
  await browser.close();
}

main().catch(err => { console.error('FAILED:', err); process.exit(1); });
