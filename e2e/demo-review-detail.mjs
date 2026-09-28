import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';

const SCREENSHOTS = 'demo/screenshots';
const BASE = 'https://localhost';
const COORD = { email: 'cashbailey@ci.laredo.tx.us', password: process.env.E2E_COORDINATOR_PASSWORD ?? '' };
const EXTRACTION_ID = 24402;

async function loginAs(page, creds) {
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => {});
  if (new URL(page.url()).pathname !== '/login') return;
  await page.getByLabel('Email').fill(creds.email);
  await page.getByLabel('Password').fill(creds.password);
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.waitForFunction(() => window.location.pathname !== '/login', null, { timeout: 30000 });
}

async function shot(page, name) {
  const path = join(SCREENSHOTS, `${name}.png`);
  await page.screenshot({ path, fullPage: false });
  console.log(`  [shot] ${name}.png`);
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
  await loginAs(page, COORD);

  // Refresh queue first (now there's an extraction even if Rejected)
  await page.goto(`${BASE}/review?status=all`, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(1500);
  await shot(page, '03b_review_queue_with_status_filter');

  await page.goto(`${BASE}/review`, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(1500);
  await shot(page, '03c_review_queue_default');

  // Try filter buttons if any
  const allBtn = page.getByRole('button', { name: /^(all|show all|rejected)$/i }).first();
  if (await allBtn.count() > 0) {
    await allBtn.click().catch(() => {});
    await page.waitForTimeout(800);
    await shot(page, '03d_review_queue_all_clicked');
  }

  // Direct deep-link to extraction detail
  await page.goto(`${BASE}/review/${EXTRACTION_ID}`, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(2500);
  await shot(page, '03e_review_detail_extraction_24402');

  // Scroll to bottom to capture full side-by-side viewer
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(800);
  await shot(page, '03f_review_detail_bottom');

  await context.close();
  await browser.close();
  console.log('DONE.');
}

main().catch(err => { console.error('FAILED:', err); process.exit(1); });
