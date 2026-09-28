/**
 * NotificationBell — header bell icon with unread badge and dropdown.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import {
  getNotifications,
  getUnreadCount,
  markNotificationRead,
  markAllNotificationsRead,
  Notification,
} from '../api';
import './NotificationBell.css';

function relativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffSec = Math.floor((now - then) / 1000);
  if (diffSec < 60) return 'just now';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return `${diffDay}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

function typeIcon(type: string): string {
  switch (type) {
    case 'RequirementDueSoon':
    case 'RequirementDueTomorrow': return '\u26A0';
    case 'RequirementOverdue':
    case 'RequirementEscalation':  return '\u2716';
    case 'CertificateExpiringSoon': return '\u23F3';
    case 'CertificateExpired':     return '\u2718';
    default:                       return '\u2709';
  }
}

function notificationRoute(type: string): string {
  switch (type) {
    case 'RequirementDueSoon':
    case 'RequirementDueTomorrow':
    case 'RequirementOverdue':
    case 'RequirementEscalation':
      return '/requirements';
    case 'CertificateExpiringSoon':
    case 'CertificateExpired':
      return '/compliance';
    default:
      return '/notifications';
  }
}

const POLL_INTERVAL = 60_000;

export function NotificationBell() {
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { user } = useAuth();

  const fetchCount = useCallback(async () => {
    try {
      const count = await getUnreadCount();
      setUnreadCount(count);
    } catch {
      // silently ignore polling errors
    }
  }, []);

  // Poll unread count
  useEffect(() => {
    fetchCount();
    const id = setInterval(fetchCount, POLL_INTERVAL);

    const handleVisibility = () => {
      if (!document.hidden) fetchCount();
    };
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [fetchCount]);

  // Fetch recent notifications when dropdown opens
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await getNotifications({ limit: 10 });
        if (!cancelled) {
          setNotifications(data.notifications);
          setUnreadCount(data.total_unread);
        }
      } catch {
        // ignore
      }
    })();
    return () => { cancelled = true; };
  }, [open]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  // Close on Escape key
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open]);

  const handleItemClick = async (n: Notification) => {
    if (!n.read) {
      try {
        const updated = await markNotificationRead(n.id);
        setNotifications(prev => prev.map(x => x.id === n.id ? updated : x));
        setUnreadCount(prev => Math.max(0, prev - 1));
      } catch {
        // ignore
      }
    }
    setOpen(false);
    // Only navigate to Coordinator-only routes if user is a Coordinator.
    // Admin should always go to /notifications (not /requirements or /compliance).
    const route = notificationRoute(n.notification_type);
    if (route === '/notifications' || user?.role === 'Coordinator') {
      navigate(route);
    } else {
      navigate('/notifications');
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsRead();
      setNotifications(prev => prev.map(n => ({ ...n, read: true, read_at: new Date().toISOString() })));
      setUnreadCount(0);
    } catch {
      // ignore
    }
  };

  return (
    <div className="notification-bell-container" ref={containerRef}>
      <button
        className="notification-bell-btn"
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
        aria-haspopup="true"
        aria-expanded={open}
        title="Notifications"
        onClick={() => setOpen(prev => !prev)}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unreadCount > 0 && (
          <span className="notification-badge">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="notification-dropdown" role="menu">
          <div className="notification-dropdown-header">
            <span className="notification-dropdown-title">Notifications</span>
            {unreadCount > 0 && (
              <button className="notification-mark-all" onClick={handleMarkAllRead}>
                Mark all read
              </button>
            )}
          </div>

          <div className="notification-dropdown-list">
            {notifications.length === 0 ? (
              <div className="notification-empty">No notifications</div>
            ) : (
              notifications.map(n => (
                <button
                  key={n.id}
                  className={`notification-item${n.read ? '' : ' notification-item--unread'}`}
                  role="menuitem"
                  onClick={() => handleItemClick(n)}
                >
                  <span className="notification-item-icon">{typeIcon(n.notification_type)}</span>
                  <div className="notification-item-content">
                    <span className="notification-item-subject">{n.subject}</span>
                    <span className="notification-item-body">{n.body}</span>
                    <span className="notification-item-time">{relativeTime(n.created_at)}</span>
                  </div>
                  {!n.read && <span className="notification-unread-dot" />}
                </button>
              ))
            )}
          </div>

          <div className="notification-dropdown-footer">
            <Link to="/notifications" className="notification-view-all" onClick={() => setOpen(false)}>
              View all notifications
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

export default NotificationBell;
