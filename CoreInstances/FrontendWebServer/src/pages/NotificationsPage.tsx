/**
 * Full notifications list page at /notifications.
 */

import { useState, useEffect, useCallback } from 'react';
import { Header } from '../components/Header';
import {
  getNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  Notification,
} from '../api';
import './NotificationsPage.css';

type Filter = 'all' | 'unread';

const TYPE_LABELS: Record<string, { label: string; className: string }> = {
  RequirementDueSoon:      { label: 'Due Soon',       className: 'notif-pill--warning' },
  RequirementDueTomorrow:  { label: 'Due Tomorrow',   className: 'notif-pill--warning' },
  RequirementOverdue:      { label: 'Overdue',        className: 'notif-pill--error' },
  RequirementEscalation:   { label: 'Escalation',     className: 'notif-pill--error' },
  CertificateExpiringSoon: { label: 'Expiring Soon',  className: 'notif-pill--warning' },
  CertificateExpired:      { label: 'Expired',        className: 'notif-pill--error' },
};

function getTypePill(type: string) {
  const config = TYPE_LABELS[type] || { label: type, className: 'notif-pill--default' };
  return config;
}

function formatTimestamp(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'Just now';
  if (diffMin < 60) return `${diffMin} min ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 7) return `${diffDay}d ago`;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

export function NotificationsPage() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [totalUnread, setTotalUnread] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>('all');
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const fetchNotifications = useCallback(async (f: Filter) => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await getNotifications({ unreadOnly: f === 'unread', limit: 200 });
      setNotifications(data.notifications);
      setTotalUnread(data.total_unread);
    } catch {
      setNotifications([]);
      setLoadError('Notifications could not be loaded. Please try again.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchNotifications(filter);
  }, [filter, fetchNotifications]);

  const handleMarkRead = async (id: number) => {
    setActionError(null);
    try {
      const updated = await markNotificationRead(id);
      setNotifications(prev => prev.map(n => n.id === id ? updated : n));
      setTotalUnread(prev => Math.max(0, prev - 1));
    } catch {
      setActionError('That notification could not be marked as read.');
    }
  };

  const handleMarkAllRead = async () => {
    setActionError(null);
    try {
      await markAllNotificationsRead();
      setNotifications(prev => prev.map(n => ({ ...n, read: true, read_at: new Date().toISOString() })));
      setTotalUnread(0);
    } catch {
      setActionError('Notifications could not be marked as read.');
    }
  };

  return (
    <div className="notifications-page">
      <Header title="Notifications" showBackLink backTo="/" backLabel="Dashboard" />

      <main className="notifications-content">
        <div className="notifications-toolbar">
          <div className="notifications-filter-group">
            <button
              type="button"
              className={`notifications-filter-btn${filter === 'all' ? ' notifications-filter-btn--active' : ''}`}
              onClick={() => setFilter('all')}
              aria-pressed={filter === 'all'}
            >
              All
            </button>
            <button
              type="button"
              className={`notifications-filter-btn${filter === 'unread' ? ' notifications-filter-btn--active' : ''}`}
              onClick={() => setFilter('unread')}
              aria-pressed={filter === 'unread'}
            >
              Unread{totalUnread > 0 ? ` (${totalUnread})` : ''}
            </button>
          </div>
          {totalUnread > 0 && (
            <button type="button" className="notifications-mark-all-btn" onClick={handleMarkAllRead}>
              Mark All Read
            </button>
          )}
        </div>

        {actionError && <div className="notifications-error" role="alert">{actionError}</div>}

        {loading ? (
          <div className="notifications-loading" role="status">Loading...</div>
        ) : loadError ? (
          <div className="notifications-error" role="alert">
            <span>{loadError}</span>
            <button type="button" onClick={() => fetchNotifications(filter)}>Retry</button>
          </div>
        ) : notifications.length === 0 ? (
          <div className="notifications-empty">
            <span className="notifications-empty-icon">{'\u2714'}</span>
            <p>You're all caught up!</p>
          </div>
        ) : (
          <div className="notifications-list" aria-label="Notifications">
            {filter === 'unread' && totalUnread > notifications.length && (
              <p className="notifications-limit-note" role="status">
                Showing the 200 most recent of {totalUnread} unread notifications.
              </p>
            )}
            {notifications.map(n => {
              const pill = getTypePill(n.notification_type);
              return (
                <div key={n.id} className={`notification-card${n.read ? '' : ' notification-card--unread'}`}>
                  <div className="notification-card-header">
                    <span className={`notif-pill ${pill.className}`}>{pill.label}</span>
                    <span className="notification-card-time">{formatTimestamp(n.created_at)}</span>
                  </div>
                  <h3 className="notification-card-subject">{n.subject}</h3>
                  <p className="notification-card-body">{n.body}</p>
                  {!n.read && (
                    <button type="button" className="notification-card-mark-btn" onClick={() => handleMarkRead(n.id)}>
                      Mark as read
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}

export default NotificationsPage;
