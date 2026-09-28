/**
 * Forgot password page — email input to trigger a reset link.
 */

import React, { useState } from 'react';
import { forgotPassword } from '../api/auth';

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);

    try {
      await forgotPassword(email.trim());
      setSubmitted(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : '';
      if (/rate limit|too many/i.test(message)) {
        setError('Too many reset requests from this browser. Please wait and try again.');
      } else if (message && !/^http error/i.test(message)) {
        setError(message);
      } else {
        setError('Something went wrong. Please try again.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="login-page" aria-labelledby="forgot-password-title">
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
          <h1 id="forgot-password-title">City of Laredo</h1>
          <h2>Reset Your Password</h2>
        </header>

        {submitted ? (
          <div className="login-form">
            <div className="success-message" role="status" aria-live="polite">
              If that address is registered, a reset link has been sent.
              Please check your inbox.
            </div>
            <div className="login-forgot">
              <a href="/login">Back to Sign In</a>
            </div>
          </div>
        ) : (
          <form className="login-form" onSubmit={handleSubmit}>
            {error && (
              <div className="error-message" role="alert">{error}</div>
            )}

            <p style={{ marginBottom: '1rem', color: 'var(--text-secondary, #666)' }}>
              Enter your work email address and we'll send you a link to reset
              your password.
            </p>

            <div className="form-group">
              <label htmlFor="email">Email</label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Enter your email"
                required
                autoComplete="email"
                disabled={isSubmitting}
              />
            </div>

            <button
              type="submit"
              className="login-button"
              disabled={isSubmitting}
            >
              {isSubmitting ? 'Sending...' : 'Send Reset Link'}
            </button>

            <div className="login-forgot">
              <a href="/login">Back to Sign In</a>
            </div>
          </form>
        )}
      </div>
    </main>
  );
}
