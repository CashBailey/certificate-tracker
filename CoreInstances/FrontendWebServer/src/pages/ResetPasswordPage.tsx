/**
 * Reset password page — accepts a one-time token from the URL and sets a new password.
 */

import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { resetPassword } from '../api/auth';

const MIN_PASSWORD_LENGTH = 15; // MED-08: must match server-side enforcement (was 8, server enforces 15)
const SPECIAL_CHARACTER_PATTERN = /[!@#$%^&*()_+\-=[\]{}|;':",.<>?/`~\\]/;

function validatePassword(newPassword: string, confirmPassword: string): string | null {
  if (newPassword.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  }

  if (!/\d/.test(newPassword)) {
    return 'Password must contain at least one digit (0-9).';
  }

  if (!SPECIAL_CHARACTER_PATTERN.test(newPassword)) {
    return 'Password must contain at least one special character.';
  }

  if (newPassword !== confirmPassword) {
    return 'Passwords do not match.';
  }

  return null;
}

function formatResetError(message: string): string {
  if (!message || /^\[object Object\]$/i.test(message) || /^http error/i.test(message)) {
    return 'This reset link is invalid or has expired. Please request a new one.';
  }

  if (/invalid or expired reset token/i.test(message)) {
    return 'This reset link is invalid or has expired. Please request a new one.';
  }

  return message;
}

export function ResetPasswordPage() {
  const [token] = useState(() => {
    const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ''));
    const legacyQuery = new URLSearchParams(window.location.search);
    return fragment.get('token') ?? legacyQuery.get('token');
  });

  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const navigate = useNavigate();

  useEffect(() => {
    if (token && (window.location.hash || window.location.search)) {
      window.history.replaceState(
        window.history.state,
        '',
        window.location.pathname,
      );
    }
  }, [token]);

  // No token in URL — show a clear error
  if (!token) {
    return (
      <main className="login-page" aria-labelledby="invalid-reset-title">
        <div className="login-container">
          <header className="login-header">
            <h1 id="invalid-reset-title">City of Laredo</h1>
            <h2>Invalid Reset Link</h2>
          </header>
          <div className="login-form">
            <div className="error-message" role="alert">
              This password reset link is invalid or missing.
            </div>
            <div className="login-forgot">
              <a href="/forgot-password">Request a new reset link</a>
            </div>
          </div>
        </div>
      </main>
    );
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const validationError = validatePassword(newPassword, confirmPassword);
    if (validationError) {
      setError(validationError);
      return;
    }

    setIsSubmitting(true);

    try {
      await resetPassword(token, newPassword);
      navigate('/login', { state: { resetSuccess: true }, replace: true });
    } catch (err) {
      setError(formatResetError(err instanceof Error ? err.message : ''));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="login-page" aria-labelledby="reset-password-title">
      <div className="login-container">
        <header className="login-header">
          <div className="login-logos">
            <img
              src="/logos/CityOfLaredoLogo.png"
              alt="City of Laredo"
              className="login-logo login-logo--city"
            />
            <div className="login-logo-divider" />
            <img
              src="/logos/CityOfLaredoPublicHealthLogo.png"
              alt="City of Laredo Public Health"
              className="login-logo"
            />
          </div>
          <h1 id="reset-password-title">City of Laredo</h1>
          <h2>Set New Password</h2>
        </header>

        <form className="login-form" onSubmit={handleSubmit} noValidate>
          {error && (
            <div className="error-message" role="alert">
              {error}
              {error.includes('invalid or has expired') && (
                <span>
                  {' '}
                  <a href="/forgot-password">Request a new reset link.</a>
                </span>
              )}
            </div>
          )}

          <div className="form-group">
            <label htmlFor="new-password">New Password</label>
            <input
              id="new-password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder={`At least ${MIN_PASSWORD_LENGTH} characters`}
              required
              minLength={MIN_PASSWORD_LENGTH}
              maxLength={128}
              autoComplete="new-password"
              disabled={isSubmitting}
            />
          </div>

          <div className="form-group">
            <label htmlFor="confirm-password">Confirm New Password</label>
            <input
              id="confirm-password"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Re-enter your new password"
              required
              autoComplete="new-password"
              disabled={isSubmitting}
            />
          </div>

          <button
            type="submit"
            className="login-button"
            disabled={isSubmitting}
          >
            {isSubmitting ? 'Saving...' : 'Set New Password'}
          </button>

          <div className="login-forgot">
            <a href="/login">Back to Sign In</a>
          </div>
        </form>
      </div>
    </main>
  );
}
