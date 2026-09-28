import { chromium } from 'playwright';
import { join } from 'node:path';

const SCREENSHOTS = 'demo/screenshots';

async function shot(page, name) {
  const path = join(SCREENSHOTS, `${name}.png`);
  await page.screenshot({ path, fullPage: false });
  console.log(`  [shot] ${name}.png`);
}

async function main() {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  // Greenmail web UI
  await page.goto('http://127.0.0.1:8080/', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);
  await shot(page, '00_greenmail_landing');

  // Try common Greenmail web paths
  for (const path of ['/api', '/swagger-ui/', '/swagger-ui/index.html']) {
    await page.goto(`http://127.0.0.1:8080${path}`, { waitUntil: 'domcontentloaded' }).catch(() => {});
    await page.waitForTimeout(1200);
    await shot(page, `00_greenmail_${path.replace(/[^a-z0-9]/gi, '_')}`);
  }

  // Roundcube login screen + inbox if creds work
  await page.goto('http://127.0.0.1:9090/', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);
  await shot(page, '00_roundcube_landing');

  // Try logging into Roundcube as ahmed.abdallah (the sender)
  const userInput = page.locator('#rcmloginuser, input[name="_user"]').first();
  if (await userInput.count() > 0) {
    await userInput.fill('ahmed.abdallah@ci.laredo.tx.us');
    const passInput = page.locator('#rcmloginpwd, input[name="_pass"]').first();
    await passInput.fill('any').catch(() => {});
    await page.locator('button[type="submit"], #rcmloginsubmit').first().click().catch(() => {});
    await page.waitForTimeout(2500);
    await shot(page, '00_roundcube_after_login_ahmed');
  }

  await context.close();
  await browser.close();
}

main().catch(err => { console.error('FAILED:', err); process.exit(1); });
