import assert from 'node:assert/strict';
import test from 'node:test';

import {
  calculateComplianceRate,
  calculateDashboardStats,
  hasNoUrgentTasks,
} from '../src/pages/reportingMetrics.ts';

const parseDateOnly = (value: string): Date => {
  const [year, month, day] = value.split('-').map(Number);
  return new Date(year, month - 1, day);
};

test('keeps requirement deadlines separate from certificate expirations', () => {
  const stats = calculateDashboardStats(
    2,
    [
      {
        due_date: '2026-07-20',
        satisfied_by_id: null,
        expiration_date: null,
        waived_at: null,
      },
      {
        due_date: '2026-06-01',
        satisfied_by_id: 99,
        expiration_date: '2026-07-22',
        waived_at: null,
      },
      {
        due_date: '2026-06-01',
        satisfied_by_id: 99,
        expiration_date: '2026-07-22',
        waived_at: null,
      },
      {
        due_date: '2026-07-10',
        satisfied_by_id: null,
        expiration_date: null,
        waived_at: null,
      },
      {
        due_date: '2026-07-10',
        satisfied_by_id: null,
        expiration_date: null,
        waived_at: '2026-07-01T12:00:00Z',
      },
    ],
    parseDateOnly('2026-07-12'),
    parseDateOnly,
  );

  assert.deepEqual(stats, {
    pendingReviews: 2,
    overdueRequirements: 1,
    dueSoonRequirements: 1,
    expiringCertificates: 1,
  });
});

test('does not treat unavailable dashboard statistics as an all-clear', () => {
  assert.equal(hasNoUrgentTasks(null), false);
  assert.equal(hasNoUrgentTasks({
    pendingReviews: 0,
    overdueRequirements: 0,
    dueSoonRequirements: 0,
    expiringCertificates: 0,
  }), true);
});

test('returns no rate for a zero-denominator compliance group', () => {
  assert.equal(calculateComplianceRate(0, 0, 0), null);
  assert.equal(calculateComplianceRate(6, 1, 10), 70);
});
