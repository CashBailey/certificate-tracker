import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';
import {
  ADMIN_EMAIL,
  ADMIN_PASSWORD,
  BASE_URL,
  COORDINATOR_EMAIL,
  COORDINATOR_PASSWORD,
  RESULTS_ROOT,
  writeResultFile,
} from './env.mjs';
import { join } from 'node:path';

export async function launchBrowser() {
  const headless = process.env.PW_HEADLESS !== 'false';
  const slowMo = Number(process.env.PW_SLOWMO ?? '0');
  return chromium.launch({
    channel: 'chrome',
    headless,
    slowMo: Number.isFinite(slowMo) ? slowMo : 0,
    args: ['--ignore-certificate-errors'],
  });
}

export async function newContext(browser, options = {}) {
  return browser.newContext({
    baseURL: BASE_URL,
    ignoreHTTPSErrors: true,
    acceptDownloads: true,
    viewport: { width: 1440, height: 900 },
    ...options,
  });
}

export async function loginViaUi(page, role = 'admin') {
  const creds =
    role === 'admin'
      ? { email: ADMIN_EMAIL, password: ADMIN_PASSWORD }
      : { email: COORDINATOR_EMAIL, password: COORDINATOR_PASSWORD };
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  if (new URL(page.url()).pathname !== '/login') {
    await page.getByText(/^Loading\.\.\.$/).waitFor({ state: 'hidden', timeout: 30000 }).catch(() => {});
    await page.getByRole('button', { name: /sign out/i }).waitFor({ timeout: 30000 });
    return;
  }
  await page.getByLabel('Email').fill(creds.email);
  await page.getByLabel('Password').fill(creds.password);
  await page.getByRole('button', { name: /sign in/i }).click();
  const outcome = await Promise.race([
    page.waitForFunction(() => window.location.pathname !== '/login', null, { timeout: 30000 }).then(() => 'navigated'),
    page.locator('.error-message').waitFor({ state: 'visible', timeout: 30000 }).then(() => 'error'),
  ]).catch(async () => {
    const message = await page.locator('.error-message').textContent().catch(() => null);
    throw new Error(
      message
        ? `Login failed for ${creds.email}: ${message.trim()}`
        : `Timed out waiting for ${creds.email} to leave /login.`,
    );
  });
  if (outcome === 'error') {
    const message = await page.locator('.error-message').textContent().catch(() => null);
    throw new Error(`Login failed for ${creds.email}: ${message?.trim() ?? 'unknown error'}`);
  }
  await page.waitForLoadState('domcontentloaded');
  await page.getByText(/^Loading\.\.\.$/).waitFor({ state: 'hidden', timeout: 30000 }).catch(() => {});
  await page.getByRole('button', { name: /sign out/i }).waitFor({ timeout: 30000 });
}

export async function requestPasswordReset(page, email) {
  await page.goto('/forgot-password');
  await page.getByLabel('Email').fill(email);
  await page.getByRole('button', { name: /send reset link/i }).click();
  await Promise.race([
    page.getByText(/if that address is registered/i).waitFor(),
    page.locator('.error-message').waitFor(),
  ]);
  const errorMessage = page.locator('.error-message');
  if (await errorMessage.isVisible()) {
    throw new Error(`Forgot-password UI failed: ${(await errorMessage.textContent())?.trim() ?? 'unknown error'}`);
  }
}

export async function resetPasswordWithLink(page, resetLink, newPassword) {
  await page.goto(resetLink);
  await page.locator('#new-password').fill(newPassword);
  await page.locator('#confirm-password').fill(newPassword);
  await page.getByRole('button', { name: /set new password/i }).click();
  await page.waitForURL((url) => url.pathname === '/login');
}

export async function logout(page) {
  await page.getByRole('button', { name: /sign out/i }).click();
  await page.waitForFunction(() => window.location.pathname === '/login', null, { timeout: 30000 });
  await page.getByRole('button', { name: /sign in/i }).waitFor({ timeout: 30000 });
}

export async function saveFailureArtifacts(page, id, errorText) {
  const safeId = id.toLowerCase();
  const imagePath = join(RESULTS_ROOT, `${safeId}.png`);
  await page.screenshot({ path: imagePath, fullPage: true });
  writeResultFile(`${safeId}.txt`, errorText);
  return imagePath;
}

export async function runAxe(page, id) {
  const results = await new AxeBuilder({ page }).analyze();
  return results.violations ?? [];
}
