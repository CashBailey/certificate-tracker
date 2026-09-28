/**
 * Shared Header component with city logos and user info.
 */

import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import { NotificationBell } from './NotificationBell';
import './Header.css';

interface HeaderProps {
  title: string;
  showBackLink?: boolean;
  backTo?: string;
  backLabel?: string;
}

export function Header({ title, showBackLink = false, backTo = '/', backLabel = 'Dashboard' }: HeaderProps) {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const getInitials = (firstName?: string, lastName?: string): string => {
    const first = firstName?.charAt(0)?.toUpperCase() || '';
    const last = lastName?.charAt(0)?.toUpperCase() || '';
    return first + last || 'U';
  };

  const getRoleDisplay = (role?: string): string => {
    return role || 'User';
  };

  return (
    <header className="app-header">
      <div className="header-content">
        <div className="header-left">
          <div className="header-logo-wrapper">
            <img
              src="/logos/CityOfLaredoLogo.png"
              alt="City of Laredo"
              className="header-logo header-logo--city"
            />
          </div>
          <div className="header-logo-divider" />
          <div className="header-logo-wrapper">
            <img
              src="/logos/CityOfLaredoPublicHealthLogo.png"
              alt="City of Laredo Public Health"
              className="header-logo header-logo--health"
            />
          </div>
          <div className="header-title-group">
            {showBackLink && (
              <Link to={backTo} className="header-back-link">
                <span className="back-arrow">&larr;</span>
                <span className="back-text">{backLabel}</span>
              </Link>
            )}
            <h1 className="header-title">{title}</h1>
          </div>
        </div>

        <div className="header-right">
          <button
            onClick={toggleTheme}
            className="theme-toggle"
            aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
            title={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
          >
            {theme === 'light' ? (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="5" />
                <line x1="12" y1="1" x2="12" y2="3" />
                <line x1="12" y1="21" x2="12" y2="23" />
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                <line x1="1" y1="12" x2="3" y2="12" />
                <line x1="21" y1="12" x2="23" y2="12" />
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
              </svg>
            )}
          </button>
          <NotificationBell />
          <div className="header-user">
            <div className="user-avatar">
              {getInitials(user?.first_name, user?.last_name)}
            </div>
            <div className="user-details">
              <span className="user-name">
                {user?.first_name} {user?.last_name}
              </span>
              <span className="user-role-pill">
                {getRoleDisplay(user?.role)}
              </span>
            </div>
            <button onClick={handleLogout} className="header-signout">
              Sign Out
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}

export default Header;
