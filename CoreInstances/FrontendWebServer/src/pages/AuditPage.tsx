/**
 * Audit Log page — read-only timeline of system audit events.
 *
 * Accessible to Coordinator and Admin roles.
 * Provides filtering by action, target type, date range, and per-entity drill-down.
 */

import { useState, useEffect, useCallback } from 'react';
import { Header } from '../components/Header';
import { getAuditLogs, AuditLogEntry } from '../api';
import './AuditPage.css';

const ACTION_LABELS: Record<string, string> = {
  extraction_approved: 'Approved extraction',
  extraction_rejected: 'Rejected extraction',
  requirement_created: 'Created requirement',
  requirement_waived: 'Waived requirement',
  employee_created: 'Created employee',
  employee_updated: 'Updated employee',
  employee_deactivated: 'Deactivated employee',
  employee_reactivated: 'Reactivated employee',
  login_success: 'Logged in',
  gal_import: 'Imported GAL directory',
  document_uploaded: 'Uploaded document',
  requirement_satisfied: 'Satisfied requirement',
};

const SOURCE_SERVICES = ['api', 'extraction-worker', 'scheduler-worker', 'email-intake'];
const OUTCOMES = ['success', 'failure', 'denied'];

const TARGET_TYPES = [
  'extraction',
  'requirement',
  'employee',
  'document',
  'auth',
  'gal_directory',
];

const SENSITIVE_KEYS = new Set([
  'password', 'token', 'secret', 'hash', 'password_hash', 'access_token',
  'refresh_token', 'api_key', 'credential',
]);

function formatActionLabel(action: string): string {
  return ACTION_LABELS[action] || action.replace(/_/g, ' ');
}

function formatTimestamp(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function formatTargetType(type: string): string {
  return type.charAt(0).toUpperCase() + type.slice(1).replace(/_/g, ' ');
}

function renderDetails(details: Record<string, unknown>): JSX.Element {
  const entries = Object.entries(details).filter(
    ([key]) => !SENSITIVE_KEYS.has(key.toLowerCase())
  );

  if (entries.length === 0) {
    return <span className="audit-detail-empty">No details</span>;
  }

  return (
    <dl className="audit-detail-list">
      {entries.map(([key, value]) => (
        <div key={key} className="audit-detail-item">
          <dt>{key.replace(/_/g, ' ')}</dt>
          <dd>{typeof value === 'object' && value !== null
            ? JSON.stringify(value)
            : String(value ?? '')}</dd>
        </div>
      ))}
    </dl>
  );
}

export function AuditPage() {
  // Filter state
  const [actorIdFilter, setActorIdFilter] = useState('');
  const [actionFilter, setActionFilter] = useState('');
  const [targetTypeFilter, setTargetTypeFilter] = useState('');
  const [targetIdFilter, setTargetIdFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [sourceServiceFilter, setSourceServiceFilter] = useState('');
  const [outcomeFilter, setOutcomeFilter] = useState('');

  // Pagination
  const [page, setPage] = useState(0);
  const limit = 100;
  const [totalCount, setTotalCount] = useState(0);

  // Data
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Detail expansion
  const [expandedId, setExpandedId] = useState<number | null>(null);

  // Drill-down state
  const [drillTarget, setDrillTarget] = useState<{ type: string; id: string } | null>(null);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: {
        action?: string;
        target_type?: string;
        target_id?: string;
        employee_id?: number;
        source_service?: string;
        outcome?: string;
        created_after?: string;
        created_before?: string;
        skip: number;
        limit: number;
      } = {
        skip: page * limit,
        limit,
      };

      const activeTargetType = drillTarget?.type || targetTypeFilter;
      const activeTargetId = drillTarget?.id || targetIdFilter;

      if (actorIdFilter) {
        const parsed = parseInt(actorIdFilter, 10);
        if (!isNaN(parsed)) params.employee_id = parsed;
      }
      if (actionFilter) params.action = actionFilter;
      if (activeTargetType) params.target_type = activeTargetType;
      if (activeTargetId) params.target_id = activeTargetId;
      if (sourceServiceFilter) params.source_service = sourceServiceFilter;
      if (outcomeFilter) params.outcome = outcomeFilter;
      if (dateFrom) params.created_after = `${dateFrom}T00:00:00`;
      if (dateTo) params.created_before = `${dateTo}T23:59:59`;

      const response = await getAuditLogs(params);
      setLogs(response.items);
      setTotalCount(response.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load audit logs');
    } finally {
      setLoading(false);
    }
  }, [page, actorIdFilter, actionFilter, targetTypeFilter, targetIdFilter, dateFrom, dateTo, sourceServiceFilter, outcomeFilter, drillTarget]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const handleDrillDown = (type: string, id: string) => {
    setDrillTarget({ type, id });
    setPage(0);
    setExpandedId(null);
  };

  const clearDrillDown = () => {
    setDrillTarget(null);
    setPage(0);
  };

  const clearAllFilters = () => {
    setActorIdFilter('');
    setActionFilter('');
    setTargetTypeFilter('');
    setTargetIdFilter('');
    setDateFrom('');
    setDateTo('');
    setSourceServiceFilter('');
    setOutcomeFilter('');
    setDrillTarget(null);
    setPage(0);
    setExpandedId(null);
  };

  const hasActiveFilters = actorIdFilter || actionFilter || targetTypeFilter || targetIdFilter || dateFrom || dateTo || sourceServiceFilter || outcomeFilter || drillTarget;

  // Collect distinct actions from current results for the filter dropdown
  const distinctActions = Array.from(new Set(logs.map(l => l.action))).sort();

  const totalPages = Math.max(1, Math.ceil(totalCount / limit));

  return (
    <div className="audit-page">
      <Header
        title="Audit Log"
        showBackLink
        backTo="/"
        backLabel="Dashboard"
      />

      <main className="page-main">
        {error && <div className="error-message">{error}</div>}

        {/* Drill-down banner */}
        {drillTarget && (
          <div className="audit-drilldown-banner">
            <span>
              Showing events for: <strong>{formatTargetType(drillTarget.type)} #{drillTarget.id}</strong>
            </span>
            <button
              onClick={clearDrillDown}
              className="btn btn--small btn--secondary"
            >
              Clear
            </button>
          </div>
        )}

        {/* Filter Bar */}
        <div className="toolbar audit-filter-bar">
          <div className="filters">
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              placeholder="Actor Employee ID"
              value={actorIdFilter}
              onChange={(e) => { setActorIdFilter(e.target.value.replace(/\D/g, '')); setPage(0); }}
              className="filter-input filter-input--narrow"
            />

            <select
              value={actionFilter}
              onChange={(e) => { setActionFilter(e.target.value); setPage(0); }}
              className="filter-select"
            >
              <option value="">All Actions</option>
              {distinctActions.map(action => (
                <option key={action} value={action}>{formatActionLabel(action)}</option>
              ))}
            </select>

            <select
              value={drillTarget ? drillTarget.type : targetTypeFilter}
              onChange={(e) => {
                if (drillTarget) {
                  clearDrillDown();
                }
                setTargetTypeFilter(e.target.value);
                setPage(0);
              }}
              className="filter-select"
              disabled={!!drillTarget}
            >
              <option value="">All Target Types</option>
              {TARGET_TYPES.map(type => (
                <option key={type} value={type}>{formatTargetType(type)}</option>
              ))}
            </select>

            <select
              value={sourceServiceFilter}
              onChange={(e) => { setSourceServiceFilter(e.target.value); setPage(0); }}
              className="filter-select"
            >
              <option value="">All Services</option>
              {SOURCE_SERVICES.map(svc => (
                <option key={svc} value={svc}>{svc}</option>
              ))}
            </select>

            <select
              value={outcomeFilter}
              onChange={(e) => { setOutcomeFilter(e.target.value); setPage(0); }}
              className="filter-select"
            >
              <option value="">All Outcomes</option>
              {OUTCOMES.map(o => (
                <option key={o} value={o}>{o.charAt(0).toUpperCase() + o.slice(1)}</option>
              ))}
            </select>

            <div className="date-range-inputs">
              <label className="date-range-label">
                From
                <input
                  type="date"
                  value={dateFrom}
                  onChange={(e) => { setDateFrom(e.target.value); setPage(0); }}
                  className="date-input"
                />
              </label>
              <label className="date-range-label">
                To
                <input
                  type="date"
                  value={dateTo}
                  onChange={(e) => { setDateTo(e.target.value); setPage(0); }}
                  className="date-input"
                  min={dateFrom || undefined}
                />
              </label>
            </div>
          </div>

          {hasActiveFilters && (
            <button
              onClick={clearAllFilters}
              className="btn btn--small btn--secondary"
            >
              Clear Filters
            </button>
          )}
        </div>

        {/* Timeline Table */}
        {loading ? (
          <div className="loading-container">
            <span className="loading-spinner">Loading audit logs...</span>
          </div>
        ) : logs.length === 0 ? (
          <div className="empty-state">
            <h2>No Audit Events</h2>
            <p>
              {hasActiveFilters
                ? 'No events match your current filters.'
                : 'No audit events have been recorded yet.'}
            </p>
          </div>
        ) : (
          <>
            <div className="audit-table-container">
              <table className="audit-table">
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Actor</th>
                    <th>Action</th>
                    <th>Target</th>
                    <th className="th-details">Details</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map(log => (
                    <>
                      <tr key={log.id} className={expandedId === log.id ? 'audit-row--expanded' : ''}>
                        <td className="cell-timestamp">
                          {formatTimestamp(log.occurred_at_utc || log.created_at)}
                        </td>
                        <td className="cell-actor">
                          <span className={`actor-badge actor-badge--${log.actor_type.toLowerCase()}`}>
                            {log.actor_type}
                          </span>
                          {log.actor_name ? (
                            <span className="actor-name">{log.actor_name}</span>
                          ) : log.employee_id !== null ? (
                            <span className="actor-id">#{log.employee_id}</span>
                          ) : null}
                        </td>
                        <td className="cell-action">
                          {formatActionLabel(log.action)}
                        </td>
                        <td className="cell-target">
                          <button
                            className="target-link"
                            onClick={() => handleDrillDown(log.target_type, log.target_id)}
                            title={`Show all events for ${log.target_type} #${log.target_id}`}
                          >
                            {formatTargetType(log.target_type)} #{log.target_id}
                          </button>
                        </td>
                        <td className="cell-expand">
                          <button
                            className="expand-btn"
                            onClick={() => setExpandedId(expandedId === log.id ? null : log.id)}
                            aria-label={expandedId === log.id ? 'Collapse details' : 'Expand details'}
                            aria-expanded={expandedId === log.id}
                          >
                            <span className={`expand-chevron ${expandedId === log.id ? 'expand-chevron--open' : ''}`}>
                              &#9658;
                            </span>
                          </button>
                        </td>
                      </tr>
                      {expandedId === log.id && (
                        <tr key={`${log.id}-detail`} className="audit-detail-row">
                          <td colSpan={5}>
                            <div className="audit-detail-panel">
                              <div className="audit-detail-meta">
                                <span><strong>Event ID:</strong> {log.id}</span>
                                <span><strong>Actor Type:</strong> {log.actor_type}</span>
                                {log.actor_name && (
                                  <span><strong>Actor Name:</strong> {log.actor_name}</span>
                                )}
                                {log.employee_id !== null && (
                                  <span><strong>Employee ID:</strong> {log.employee_id}</span>
                                )}
                                {log.actor_role && (
                                  <span><strong>Actor Role:</strong> {log.actor_role}</span>
                                )}
                                {log.initiated_by_id !== null && log.initiated_by_id !== log.employee_id && (
                                  <span><strong>Initiated By:</strong> #{log.initiated_by_id}</span>
                                )}
                                <span><strong>Raw Action:</strong> <code>{log.action}</code></span>
                                <span><strong>Target:</strong> {log.target_type} / {log.target_id}</span>
                                {log.source_service && (
                                  <span><strong>Service:</strong> {log.source_service}</span>
                                )}
                                {log.outcome && (
                                  <span><strong>Outcome:</strong> <span className={`outcome-badge outcome-badge--${log.outcome}`}>{log.outcome}</span></span>
                                )}
                              </div>
                              {log.details && renderDetails(log.details)}
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="pagination">
              <span className="pagination-info">
                Showing {page * limit + 1} - {Math.min((page + 1) * limit, totalCount)} of {totalCount} events
              </span>
              <div className="pagination-buttons">
                <button
                  onClick={() => setPage(p => p - 1)}
                  disabled={page === 0}
                  className="btn btn--small btn--secondary"
                >
                  Previous
                </button>
                <span className="page-number">Page {page + 1} of {totalPages}</span>
                <button
                  onClick={() => setPage(p => p + 1)}
                  disabled={page >= totalPages - 1}
                  className="btn btn--small btn--secondary"
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

export default AuditPage;
