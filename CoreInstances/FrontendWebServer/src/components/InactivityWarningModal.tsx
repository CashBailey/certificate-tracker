/**
 * Modal shown when the user is about to be automatically logged out due to inactivity.
 */

import React from 'react';

interface InactivityWarningModalProps {
  secondsRemaining: number;
  onStayLoggedIn: () => void;
}

export function InactivityWarningModal({
  secondsRemaining,
  onStayLoggedIn,
}: InactivityWarningModalProps) {
  return (
    <div style={styles.backdrop}>
      <div style={styles.modal} role="alertdialog" aria-modal="true" aria-labelledby="inactivity-title">
        <div style={styles.iconWrap}>
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
        </div>

        <h2 id="inactivity-title" style={styles.title}>Session Expiring Soon</h2>

        <p style={styles.body}>
          You will be automatically logged out due to inactivity in:
        </p>

        <div style={styles.countdown} aria-live="assertive" aria-atomic="true">
          {secondsRemaining}s
        </div>

        <button style={styles.button} onClick={onStayLoggedIn} autoFocus>
          Stay Logged In
        </button>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  backdrop: {
    position: 'fixed',
    inset: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.55)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 'var(--z-modal)' as unknown as number,
  },
  modal: {
    background: 'var(--bg-surface)',
    color: 'var(--ink-primary)',
    borderRadius: 'var(--radius-card)',
    boxShadow: 'var(--shadow-lg)',
    padding: 'var(--space-8)',
    maxWidth: '380px',
    width: '90%',
    textAlign: 'center',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 'var(--space-4)',
  },
  iconWrap: {
    color: 'var(--warning)',
  },
  title: {
    margin: 0,
    fontSize: 'var(--font-h2)',
    fontWeight: 'var(--font-weight-semibold)' as unknown as number,
    color: 'var(--ink-primary)',
  },
  body: {
    margin: 0,
    fontSize: 'var(--font-small)',
    color: 'var(--ink-secondary)',
    lineHeight: 'var(--line-height-normal)' as unknown as number,
  },
  countdown: {
    fontSize: '2.5rem',
    fontWeight: 'var(--font-weight-bold)' as unknown as number,
    color: 'var(--warning)',
    lineHeight: 1,
    minWidth: '4ch',
  },
  button: {
    marginTop: 'var(--space-2)',
    padding: 'var(--space-3) var(--space-6)',
    background: 'var(--gradient-start)',
    color: '#ffffff',
    border: 'none',
    borderRadius: 'var(--radius-button)',
    fontSize: 'var(--font-body)',
    fontWeight: 'var(--font-weight-medium)' as unknown as number,
    cursor: 'pointer',
    transition: 'var(--transition-fast)',
    width: '100%',
  },
};
