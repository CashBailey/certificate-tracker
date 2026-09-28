import assert from 'node:assert/strict';
import test from 'node:test';

import { canApproveReview } from '../src/utils/reviewWorkflow.ts';

test('approval stays blocked until the document is reviewable', () => {
  assert.equal(canApproveReview('loading', false), false);
  assert.equal(canApproveReview('error', false), false);
  assert.equal(canApproveReview('ready', false), true);
});

test('approval stays blocked while a prior submission is in flight', () => {
  assert.equal(canApproveReview('ready', true), false);
});
