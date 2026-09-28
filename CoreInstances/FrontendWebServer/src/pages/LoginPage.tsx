/**
 * Login page component with city branding.
 */

import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { login, error, clearError, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // Show success notice after a completed password reset
  const resetSuccess = (location.state as { resetSuccess?: boolean } | null)?.resetSuccess ?? false;

  // Redirect if already authenticated
  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || '/';

  // Clear transient location state so the success banner doesn't survive a refresh
  useEffect(() => {
    if (resetSuccess) {
      navigate(location.pathname, { replace: true, state: {} });
    }
  }, [resetSuccess, navigate, location.pathname]);

  useEffect(() => {
    if (isAuthenticated) {
      navigate(from, { replace: true });
    }
  }, [isAuthenticated, navigate, from]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    clearError();

    try {
      await login({ email, password });
      navigate(from, { replace: true });
    } catch {
      // Error is already set in context
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="login-page" aria-labelledby="login-page-title">
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
          <h1 id="login-page-title">City of Laredo</h1>
          <h2>Certificate Management System</h2>
        </header>

        <form className="login-form" onSubmit={handleSubmit}>
          {resetSuccess && (
            <div className="success-message" role="status" aria-live="polite">
              Password reset successfully. Please sign in with your new password.
            </div>
          )}

          {error && (
            <div className="error-message" role="alert">
              {error}
            </div>
          )}

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

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              required
              autoComplete="current-password"
              disabled={isSubmitting}
            />
          </div>

          <button
            type="submit"
            className="login-button"
            disabled={isSubmitting}
          >
            {isSubmitting ? 'Signing in...' : 'Sign In'}
          </button>

          <div className="login-forgot">
            <a href="/forgot-password">Forgot your password?</a>
          </div>

          <p className="login-trust-note">
            Secure access for authorized City of Laredo employees only.
          </p>
        </form>
      </div>
    </main>
  );
}
