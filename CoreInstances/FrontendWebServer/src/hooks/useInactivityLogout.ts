/**
 * Hook that tracks user activity and triggers a warning + logout after idle periods.
 *
 * Timers:
 *   - Warning fires at (timeoutMs - warningMs) of inactivity
 *   - Logout fires at timeoutMs of inactivity
 *
 * Any user activity event resets both timers.
 */

import { useEffect, useRef, useCallback } from 'react';

const ACTIVITY_EVENTS: (keyof WindowEventMap)[] = [
  'mousemove',
  'mousedown',
  'keydown',
  'scroll',
  'touchstart',
  'click',
];

interface UseInactivityLogoutOptions {
  /** Total idle duration before logout fires (ms) */
  timeoutMs: number;
  /** How early before logout to fire the warning (ms) */
  warningMs: number;
  /** Called when warning should appear; receives countdown seconds remaining */
  onWarning: (secondsRemaining: number) => void;
  /** Called when the user should be logged out */
  onLogout: () => void;
  /** Set to false to disable the hook (e.g. when not authenticated) */
  enabled?: boolean;
}

export function useInactivityLogout({
  timeoutMs,
  warningMs,
  onWarning,
  onLogout,
  enabled = true,
}: UseInactivityLogoutOptions): { resetTimer: () => void } {
  const warningTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const logoutTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countdownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Stable refs so timer callbacks don't capture stale closures
  const onWarningRef = useRef(onWarning);
  const onLogoutRef = useRef(onLogout);
  onWarningRef.current = onWarning;
  onLogoutRef.current = onLogout;

  const clearAllTimers = useCallback(() => {
    if (warningTimerRef.current !== null) {
      clearTimeout(warningTimerRef.current);
      warningTimerRef.current = null;
    }
    if (logoutTimerRef.current !== null) {
      clearTimeout(logoutTimerRef.current);
      logoutTimerRef.current = null;
    }
    if (countdownIntervalRef.current !== null) {
      clearInterval(countdownIntervalRef.current);
      countdownIntervalRef.current = null;
    }
  }, []);

  const startTimers = useCallback(() => {
    clearAllTimers();

    const warningDelay = timeoutMs - warningMs;

    warningTimerRef.current = setTimeout(() => {
      // Begin countdown
      const warningSeconds = Math.round(warningMs / 1000);
      onWarningRef.current(warningSeconds);

      let remaining = warningSeconds;
      countdownIntervalRef.current = setInterval(() => {
        remaining -= 1;
        onWarningRef.current(remaining);
      }, 1000);
    }, warningDelay);

    logoutTimerRef.current = setTimeout(() => {
      clearAllTimers();
      onLogoutRef.current();
    }, timeoutMs);
  }, [timeoutMs, warningMs, clearAllTimers]);

  const resetTimer = useCallback(() => {
    startTimers();
  }, [startTimers]);

  useEffect(() => {
    if (!enabled) {
      clearAllTimers();
      return;
    }

    startTimers();

    const handleActivity = () => startTimers();

    ACTIVITY_EVENTS.forEach((event) =>
      window.addEventListener(event, handleActivity, { passive: true }),
    );

    return () => {
      clearAllTimers();
      ACTIVITY_EVENTS.forEach((event) =>
        window.removeEventListener(event, handleActivity),
      );
    };
  }, [enabled, startTimers, clearAllTimers]);

  return { resetTimer };
}
