import { chromium } from 'playwright';
import { join } from 'node:path';

const SCREENSHOTS = 'demo/screenshots';

async function shot(page, name) {
  await page.screenshot({ path: join(SCREENSHOTS, `${name}.png`), fullPage: false });
  console.log(`  [shot] ${name}.png`);
}

async function main() {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  await page.goto('http://127.0.0.1:9090/', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);

  // Login as the certs intake mailbox
  await page.locator('#rcmloginuser, input[name="_user"]').first().fill('certs@ci.laredo.tx.us');
  await page.locator('#rcmloginpwd, input[name="_pass"]').first().fill('any');
  await page.locator('button[type="submit"], #rcmloginsubmit').first().click();
  await page.waitForTimeout(3500);
  await shot(page, '00b_roundcube_certs_inbox_after_intake');

  // Try clicking the Processed folder if visible
  const processed = page.getByText(/Processed/i).first();
  if (await processed.count() > 0) {
    await processed.click();
    await page.waitForTimeout(2500);
    await shot(page, '00c_roundcube_processed_folder');

    // Click first row in Processed
    const firstRow = page.locator('tr.message, tr[id^="rcmrow"]').first();
    if (await firstRow.count() > 0) {
      await firstRow.click();
      await page.waitForTimeout(2000);
      await shot(page, '00d_roundcube_email_open');
    }
  }

  await context.close();
  await browser.close();
}

main().catch(err => { console.error('FAILED:', err); process.exit(1); });
