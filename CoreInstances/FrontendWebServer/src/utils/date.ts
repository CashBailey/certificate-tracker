/**
 * Date helpers.
 *
 * A date-only string ("YYYY-MM-DD") passed to `new Date(...)` is parsed as UTC
 * midnight. In a negative-UTC timezone like Laredo (America/Chicago) that
 * renders as the *previous* day and shifts due/overdue boundaries a day early.
 * Parse those as local midnight instead. Full ISO timestamps (with a time or
 * zone) already carry their own offset and are passed through unchanged.
 */

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

export function parseLocalDate(value: string): Date {
  if (DATE_ONLY.test(value)) {
    const [year, month, day] = value.split('-').map(Number);
    return new Date(year, month - 1, day);
  }
  return new Date(value);
}
