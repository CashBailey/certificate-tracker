/**
 * E2E verification for the coordinator requirement actions added to /requirements:
 *   1. Assign Requirement modal creates a new assignment (appears in the table).
 *   2. Assigning a duplicate open requirement surfaces the API's 409 message.
 *   3. Waive captures a reason and flips the row to Waived.
 *   4. Unwaive restores the row to an active status.
 *
 * Test data is created against a real employee/cert type and deleted at the end.
 * Run: node e2e/verify-requirement-actions.mjs
 */

import { launchBrowser, newContext, loginViaUi } from './lib/browser.mjs';
import { dockerPsql } from './lib/env.mjs';

function fail(message) {
  console.error(`FAIL: ${message}`);
  process.exitCode = 1;
}

const cleanupIds = [];

function cleanup() {
  for (const id of cleanupIds) {
    try {
      dockerPsql(`DELETE FROM certificates.requirement_assignments WHERE id = ${Number(id)};`);
    } catch (error) {
      console.error(`cleanup failed for requirement ${id}: ${error.message}`);
    }
  }
}

// dockerPsql output includes a header line; data rows follow it.
const psqlRows = (query) => dockerPsql(query).split('\n').slice(1).filter(Boolean);

const [empRow] = psqlRows(
  `SELECT e.id, e.first_name, e.last_name
   FROM certificates.employees e
   WHERE e.role = 'Employee' AND e.is_active = true
     AND NOT EXISTS (
       SELECT 1 FROM certificates.requirement_assignments r
       WHERE r.employee_id = e.id
     )
   ORDER BY e.id LIMIT 1;`,
);
if (!empRow) {
  console.error('No requirement-free active employee found; aborting.');
  process.exit(1);
}
const [employeeId, firstName, lastName] = empRow.split('\t');
const [certTypeName] = psqlRows(
  `SELECT name FROM certificates.certificate_types ORDER BY id LIMIT 1;`,
);
console.log(`Using employee ${firstName} ${lastName} (#${employeeId}) and cert type "${certTypeName}"`);

const browser = await launchBrowser();
try {
  const context = await newContext(browser);
  const page = await context.newPage();
  await loginViaUi(page, 'coordinator');

  await page.goto('/requirements');
  await page.getByRole('button', { name: '+ Assign Requirement' }).waitFor({ timeout: 15000 });

  async function openAssignAndFill() {
    await page.getByRole('button', { name: '+ Assign Requirement' }).click();
    await page.getByLabel('Find Employee').fill(lastName);
    // Wait for the debounced search to populate the select with our employee
    await page.waitForFunction(
      (id) => {
        const select = document.getElementById('assign-employee');
        return select && [...select.options].some((o) => o.value === String(id));
      },
      employeeId,
      { timeout: 15000 },
    );
    await page.getByLabel('Employee *').selectOption(String(employeeId));
    await page.getByLabel('Certificate Type *').selectOption({ label: certTypeName });
    await page.getByLabel('Due Date *').fill('2027-03-15');
    await page.getByRole('button', { name: 'Assign Requirement', exact: true }).click();
  }

  // 1. Create
  await openAssignAndFill();
  await page.locator('.modal').waitFor({ state: 'hidden', timeout: 15000 });
  const [createdId] = psqlRows(
    `SELECT id FROM certificates.requirement_assignments
     WHERE employee_id = ${Number(employeeId)} ORDER BY id DESC LIMIT 1;`,
  );
  if (!createdId) {
    fail('requirement row was not created');
  } else {
    cleanupIds.push(createdId);
    console.log(`PASS: assignment created (requirement ${createdId})`);
  }

  // Row visible after search
  await page.getByPlaceholder('Search by employee or certificate type...').fill(lastName);
  const row = page.locator('tbody tr', { hasText: lastName });
  await row.first().waitFor({ timeout: 15000 });
  console.log('PASS: new assignment visible in requirements table');

  // 2. Duplicate rejected with a clear message
  await openAssignAndFill();
  const errorText = await page.locator('.modal .error-message').textContent({ timeout: 15000 });
  if (!/already has an open/i.test(errorText ?? '')) {
    fail(`expected duplicate 409 message, got: ${errorText}`);
  } else {
    console.log(`PASS: duplicate rejected ("${errorText.trim()}")`);
  }
  await page.getByRole('button', { name: 'Cancel' }).click();
  await page.locator('.modal').waitFor({ state: 'hidden', timeout: 15000 });

  // 3. Waive
  await row.first().getByRole('button', { name: 'Waive' }).click();
  await page.getByLabel(/Waiver Reason/).fill('Employee on approved extended leave.');
  await page.getByRole('button', { name: 'Waive Requirement' }).click();
  await page.locator('.modal').waitFor({ state: 'hidden', timeout: 15000 });
  await row.first().getByRole('button', { name: 'Unwaive' }).waitFor({ timeout: 15000 });
  const [waivedStatus] = psqlRows(
    `SELECT status, waiver_reason FROM certificates.requirement_assignments WHERE id = ${Number(createdId)};`,
  );
  if (!/Waived\t/.test(waivedStatus + '\t')) {
    fail(`expected Waived status in DB, got: ${waivedStatus}`);
  } else {
    console.log(`PASS: waive persisted (${waivedStatus})`);
  }

  // 4. Unwaive
  await row.first().getByRole('button', { name: 'Unwaive' }).click();
  await page.getByRole('button', { name: 'Remove Waiver' }).click();
  await page.locator('.modal').waitFor({ state: 'hidden', timeout: 15000 });
  await row.first().getByRole('button', { name: 'Waive' }).waitFor({ timeout: 15000 });
  const [restoredStatus] = psqlRows(
    `SELECT status FROM certificates.requirement_assignments WHERE id = ${Number(createdId)};`,
  );
  if (restoredStatus === 'Waived') {
    fail('requirement still Waived after unwaive');
  } else {
    console.log(`PASS: unwaive restored status to ${restoredStatus}`);
  }

  console.log(process.exitCode ? 'RESULT: FAIL' : 'RESULT: ALL CHECKS PASSED');
} finally {
  cleanup();
  await browser.close();
}
