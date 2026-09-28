/**
 * Dashboard page component with stats and navigation cards.
 */

import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Header } from '../components/Header';
import { getExtractions, getRequirements } from '../api';
import { parseLocalDate } from '../utils/date';
import {
  calculateDashboardStats,
  DashboardStats,
  hasNoUrgentTasks,
} from './reportingMetrics';
import './DashboardPage.css';

export function DashboardPage() {
  const { user } = useAuth();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [statsError, setStatsError] = useState<string | null>(null);
  const [statsRequest, setStatsRequest] = useState(0);

  const isCoordinator = user?.role === 'Coordinator';
  const isAdmin = user?.role === 'Admin';

  useEffect(() => {
    async function fetchStats() {
      if (!isCoordinator) {
        setLoading(false);
        return;
      }

      setLoading(true);
      setStats(null);
      setStatsError(null);

      try {
        const [extractions, requirements] = await Promise.all([
          getExtractions('PendingReview'),
          getRequirements(),
        ]);

        setStats(calculateDashboardStats(
          extractions.length,
          requirements,
          new Date(),
          parseLocalDate,
        ));
      } catch (error) {
        console.error('Failed to fetch dashboard stats:', error);
        setStats(null);
        setStatsError('Dashboard statistics could not be loaded. Please try again.');
      } finally {
        setLoading(false);
      }
    }

    fetchStats();
  }, [isCoordinator, statsRequest]);

  return (
    <div className="dashboard-page">
      <Header title="Certificate Management System" />

      <main className="dashboard-main">
        {/* Stats Section */}
        {isCoordinator && statsError && (
          <div className="error-message dashboard-stats-error" role="alert">
            <span>{statsError}</span>
            <button
              type="button"
              className="btn btn--secondary btn--small"
              onClick={() => setStatsRequest(request => request + 1)}
            >
              Retry
            </button>
          </div>
        )}

        {isCoordinator && (
          <div className="dashboard-stats-grid">
            <div className="dashboard-stat-card dashboard-stat-card--warning">
              <div className="dashboard-stat-value">{loading ? '...' : stats?.pendingReviews ?? '—'}</div>
              <div className="dashboard-stat-label">Pending Reviews</div>
            </div>
            <div className="dashboard-stat-card dashboard-stat-card--error">
              <div className="dashboard-stat-value">{loading ? '...' : stats?.overdueRequirements ?? '—'}</div>
              <div className="dashboard-stat-label">Requirements Overdue</div>
            </div>
            <div className="dashboard-stat-card dashboard-stat-card--info">
              <div className="dashboard-stat-value">{loading ? '...' : stats?.dueSoonRequirements ?? '—'}</div>
              <div className="dashboard-stat-label">Requirements Due Soon</div>
            </div>
            <div className="dashboard-stat-card dashboard-stat-card--info">
              <div className="dashboard-stat-value">{loading ? '...' : stats?.expiringCertificates ?? '—'}</div>
              <div className="dashboard-stat-label">Certificates Expiring</div>
            </div>
          </div>
        )}

        {/* Welcome Card */}
        <div className="welcome-card">
          <h2>Welcome, {user?.first_name}!</h2>
          <p>You are logged in as <strong>{user?.email}</strong></p>
          <p>Role: <strong>{user?.role}</strong></p>
          {user?.employee_number && (
            <p>Employee Number: <strong>{user.employee_number}</strong></p>
          )}
        </div>

        {/* Quick Actions - Coordinator only */}
        {isCoordinator && (
          <div className="tasks-card">
            <h3>Quick Actions</h3>
            <div className="tasks-list">
              {loading ? (
                <p className="tasks-empty">Loading urgent tasks...</p>
              ) : stats ? (
                <>
                  {stats.overdueRequirements > 0 && (
                    <Link to="/requirements" className="task-item task-item--urgent">
                      <span className="task-icon">!</span>
                      <span className="task-text">
                        You have {stats.overdueRequirements} overdue requirement{stats.overdueRequirements !== 1 ? 's' : ''}
                      </span>
                    </Link>
                  )}
                  {stats.dueSoonRequirements > 0 && (
                    <Link to="/requirements" className="task-item task-item--warning">
                      <span className="task-icon">i</span>
                      <span className="task-text">
                        {stats.dueSoonRequirements} requirement{stats.dueSoonRequirements !== 1 ? 's' : ''} due within 30 days
                      </span>
                    </Link>
                  )}
                  {stats.expiringCertificates > 0 && (
                    <Link to="/requirements" className="task-item task-item--warning">
                      <span className="task-icon">i</span>
                      <span className="task-text">
                        {stats.expiringCertificates} certificate{stats.expiringCertificates !== 1 ? 's' : ''} expiring within 30 days
                      </span>
                    </Link>
                  )}
                  {stats.pendingReviews > 0 && (
                    <Link to="/review" className="task-item task-item--info">
                      <span className="task-icon">R</span>
                      <span className="task-text">
                        {stats.pendingReviews} document{stats.pendingReviews !== 1 ? 's' : ''} awaiting review
                      </span>
                    </Link>
                  )}
                  {hasNoUrgentTasks(stats) && (
                    <p className="tasks-empty">All caught up! No urgent tasks.</p>
                  )}
                </>
              ) : (
                <p className="tasks-empty">Urgent-task status is unavailable.</p>
              )}
            </div>
          </div>
        )}

        {/* Navigation Cards */}
        <h3 className="section-title">Navigation</h3>
        <div className="dashboard-grid">
          {isCoordinator && (
            <Link to="/requirements" className="dashboard-card">
              <h3>Requirements</h3>
              <p>Track and manage employee certification requirements</p>
            </Link>
          )}

          {isCoordinator && (
            <Link to="/compliance" className="dashboard-card">
              <h3>Compliance</h3>
              <p>View overall compliance rates and status breakdown</p>
            </Link>
          )}

          {isCoordinator && (
            <Link to="/configuration" className="dashboard-card">
              <h3>Configuration</h3>
              <p>Manage certificate types, alert rules, and system settings</p>
            </Link>
          )}

          {isCoordinator && (
            <Link to="/review" className="dashboard-card">
              <h3>Review Queue</h3>
              <p>Review pending certificate submissions</p>
            </Link>
          )}

          {isCoordinator && (
            <Link to="/templates" className="dashboard-card">
              <h3>Templates</h3>
              <p>View and manage extraction templates</p>
            </Link>
          )}

          {(isCoordinator || isAdmin) && (
            <Link to="/employees" className="dashboard-card">
              <h3>Employees</h3>
              <p>Manage employee accounts and roles</p>
            </Link>
          )}

          {isAdmin && (
            <Link to="/audit" className="dashboard-card">
              <h3>Audit Log</h3>
              <p>View system activity timeline and audit trail</p>
            </Link>
          )}
        </div>
      </main>
    </div>
  );
}
