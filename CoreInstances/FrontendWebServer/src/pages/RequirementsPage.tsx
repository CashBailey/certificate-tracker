/**
 * Requirements page — operational table view of all employee requirements.
 *
 * Provides search, status filtering, Days Left tracking, and CSV/XLSX export.
 * Data is paginated server-side (25 per page) for fast load times.
 * For a compliance dashboard overview, see /compliance.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Header } from '../components/Header';
import {
  getRequirementsPaged,
  getCertificateTypes,
  getEmployees,
  createRequirement,
  waiveRequirement,
  unwaiveRequirement,
  downloadRequirementsXlsx,
  downloadRequirementsCsv,
  Requirement,
  CertificateType,
  User,
} from '../api';
import { useAuth } from '../contexts/AuthContext';
import { parseLocalDate } from '../utils/date';
import { StatusBadge } from '../components/StatusBadge';
import './RequirementsPage.css';

type StatusFilter = 'all' | 'overdue' | 'due-soon' | 'on-track' | 'satisfied' | 'waived';

const PAGE_SIZE = 25;

// Maps frontend filter labels to backend status_filter values (requirement statuses)
const STATUS_FILTER_MAP: Record<StatusFilter, string | undefined> = {
  all:       undefined,
  overdue:   'Overdue',
  'due-soon': 'DueSoon',
  'on-track': 'InProgress',
  satisfied: 'Satisfied',
  waived:    'Waived',
};

export function RequirementsPage() {
  const { user } = useAuth();
  const isCoordinator = user?.role === 'Coordinator';

  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [certificateTypes, setCertificateTypes] = useState<CertificateType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloadingXlsx, setDownloadingXlsx] = useState(false);
  const [downloadingCsv, setDownloadingCsv] = useState(false);

  // Assign-requirement modal (Coordinator only)
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignEmployeeSearch, setAssignEmployeeSearch] = useState('');
  const [assignEmployeeOptions, setAssignEmployeeOptions] = useState<User[]>([]);
  const [assignEmployeeId, setAssignEmployeeId] = useState<number | ''>('');
  const [assignCertTypeId, setAssignCertTypeId] = useState<number | ''>('');
  const [assignDueDate, setAssignDueDate] = useState('');
  const [assignError, setAssignError] = useState<string | null>(null);
  const [assignSubmitting, setAssignSubmitting] = useState(false);
  const assignModalRef = useRef<HTMLDivElement>(null);

  // Waive modal (Coordinator only)
  const [waiveTarget, setWaiveTarget] = useState<Requirement | null>(null);
  const [waiveReason, setWaiveReason] = useState('');
  const [waiveExpiration, setWaiveExpiration] = useState('');
  const [waiveError, setWaiveError] = useState<string | null>(null);
  const [waiveSubmitting, setWaiveSubmitting] = useState(false);
  const waiveModalRef = useRef<HTMLDivElement>(null);

  // Unwaive confirmation modal (Coordinator only)
  const [unwaiveTarget, setUnwaiveTarget] = useState<Requirement | null>(null);
  const [unwaiveError, setUnwaiveError] = useState<string | null>(null);
  const [unwaiveSubmitting, setUnwaiveSubmitting] = useState(false);
  const unwaiveModalRef = useRef<HTMLDivElement>(null);

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  // Filters — changes reset to page 1
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');

  // Debounced search value (avoids a request per keystroke)
  const [debouncedSearch, setDebouncedSearch] = useState('');
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchQuery), 400);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const fetchPage = useCallback(
    async (page: number, status: StatusFilter, search: string) => {
      setLoading(true);
      try {
        const result = await getRequirementsPaged({
          page,
          pageSize: PAGE_SIZE,
          statusFilter: STATUS_FILTER_MAP[status],
          search: search || undefined,
        });
        setRequirements(result.items);
        setTotalCount(result.total);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load requirements');
      } finally {
        setLoading(false);
      }
    },
    []
  );

  // Initial load of certificate types (needed for display names)
  useEffect(() => {
    getCertificateTypes().then(setCertificateTypes).catch(() => {});
  }, []);

  // Fetch when page, status filter, or search changes
  useEffect(() => {
    fetchPage(currentPage, statusFilter, debouncedSearch);
  }, [currentPage, statusFilter, debouncedSearch, fetchPage]);

  // Reset to page 1 when filters change
  const handleStatusChange = (newStatus: StatusFilter) => {
    setStatusFilter(newStatus);
    setCurrentPage(1);
  };

  const handleSearchChange = (value: string) => {
    setSearchQuery(value);
    setCurrentPage(1);
  };

  const getCertificateTypeName = (typeId: number) => {
    const type = certificateTypes.find(t => t.id === typeId);
    return type?.name || `Type ${typeId}`;
  };

  const getStatusFromRequirement = (req: Requirement): string => {
    if (req.waived_at) return 'Waived';
    if (req.satisfied_by_id) return 'Satisfied';
    const dueDate = parseLocalDate(req.due_date);
    const now = new Date();
    if (dueDate < now) return 'Overdue';
    const daysUntilDue = Math.ceil((dueDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
    if (daysUntilDue <= 30) return 'DueSoon';
    return 'InProgress';
  };

  const getDaysLeft = (req: Requirement): number | null => {
    if (req.waived_at) return null;
    const targetDate = req.satisfied_by_id && req.expiration_date
      ? parseLocalDate(req.expiration_date)
      : parseLocalDate(req.due_date);
    const now = new Date();
    return Math.ceil((targetDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
  };

  const refreshCurrentPage = useCallback(() => {
    fetchPage(currentPage, statusFilter, debouncedSearch);
  }, [fetchPage, currentPage, statusFilter, debouncedSearch]);

  // Employee search inside the assign modal (debounced, active employees only)
  useEffect(() => {
    if (!assignOpen) return;
    const timer = setTimeout(() => {
      getEmployees({ search: assignEmployeeSearch || undefined, is_active: true, limit: 20 })
        .then(result => setAssignEmployeeOptions(result.employees))
        .catch(() => setAssignEmployeeOptions([]));
    }, 300);
    return () => clearTimeout(timer);
  }, [assignOpen, assignEmployeeSearch]);

  const openAssignModal = () => {
    setAssignEmployeeSearch('');
    setAssignEmployeeId('');
    setAssignCertTypeId('');
    setAssignDueDate('');
    setAssignError(null);
    setAssignOpen(true);
  };

  const closeAssignModal = useCallback(() => {
    if (assignSubmitting) return;
    setAssignOpen(false);
  }, [assignSubmitting]);

  const handleAssignSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (assignEmployeeId === '' || assignCertTypeId === '' || !assignDueDate) {
      setAssignError('Select an employee, a certificate type, and a due date.');
      return;
    }
    setAssignError(null);
    setAssignSubmitting(true);
    try {
      await createRequirement({
        employee_id: assignEmployeeId,
        certificate_type_id: assignCertTypeId,
        due_date: assignDueDate,
      });
      setAssignOpen(false);
      refreshCurrentPage();
    } catch (err) {
      setAssignError(err instanceof Error ? err.message : 'Failed to create requirement');
    } finally {
      setAssignSubmitting(false);
    }
  };

  const openWaiveModal = (req: Requirement) => {
    setWaiveReason('');
    setWaiveExpiration('');
    setWaiveError(null);
    setWaiveTarget(req);
  };

  const closeWaiveModal = useCallback(() => {
    if (waiveSubmitting) return;
    setWaiveTarget(null);
  }, [waiveSubmitting]);

  const handleWaiveSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!waiveTarget) return;
    setWaiveError(null);
    setWaiveSubmitting(true);
    try {
      await waiveRequirement(waiveTarget.id, waiveReason.trim(), waiveExpiration || undefined);
      setWaiveTarget(null);
      refreshCurrentPage();
    } catch (err) {
      setWaiveError(err instanceof Error ? err.message : 'Failed to waive requirement');
    } finally {
      setWaiveSubmitting(false);
    }
  };

  const closeUnwaiveModal = useCallback(() => {
    if (unwaiveSubmitting) return;
    setUnwaiveTarget(null);
  }, [unwaiveSubmitting]);

  const handleUnwaive = async () => {
    if (!unwaiveTarget) return;
    setUnwaiveError(null);
    setUnwaiveSubmitting(true);
    try {
      await unwaiveRequirement(unwaiveTarget.id);
      setUnwaiveTarget(null);
      refreshCurrentPage();
    } catch (err) {
      setUnwaiveError(err instanceof Error ? err.message : 'Failed to remove waiver');
    } finally {
      setUnwaiveSubmitting(false);
    }
  };

  // Focus trap + Escape handling for whichever modal is open
  useEffect(() => {
    const activeModal =
      assignOpen ? assignModalRef.current
      : waiveTarget ? waiveModalRef.current
      : unwaiveTarget ? unwaiveModalRef.current
      : null;
    if (!activeModal) return;

    const focusableSelector = [
      'button:not([disabled])',
      '[href]',
      'input:not([disabled])',
      'select:not([disabled])',
      'textarea:not([disabled])',
      '[tabindex]:not([tabindex="-1"])',
    ].join(', ');

    const getFocusable = () =>
      Array.from(activeModal.querySelectorAll<HTMLElement>(focusableSelector)).filter(
        (element) => !element.hasAttribute('hidden') && element.getAttribute('aria-hidden') !== 'true'
      );

    getFocusable()[0]?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        if (assignOpen) closeAssignModal();
        else if (waiveTarget) closeWaiveModal();
        else closeUnwaiveModal();
        return;
      }

      if (event.key !== 'Tab') return;
      const focusableElements = getFocusable();
      if (focusableElements.length === 0) return;

      const currentIndex = focusableElements.indexOf(document.activeElement as HTMLElement);
      if (event.shiftKey) {
        if (currentIndex <= 0) {
          event.preventDefault();
          focusableElements[focusableElements.length - 1]?.focus();
        }
        return;
      }

      if (currentIndex === -1 || currentIndex === focusableElements.length - 1) {
        event.preventDefault();
        focusableElements[0]?.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [assignOpen, waiveTarget, unwaiveTarget, closeAssignModal, closeWaiveModal, closeUnwaiveModal]);

  const handleExportCSV = async () => {
    setDownloadingCsv(true);
    try {
      await downloadRequirementsCsv({
        requirementStatus: STATUS_FILTER_MAP[statusFilter],
        search: debouncedSearch || undefined,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to download CSV');
    } finally {
      setDownloadingCsv(false);
    }
  };

  const handleExportXLSX = async () => {
    setDownloadingXlsx(true);
    try {
      await downloadRequirementsXlsx({
        requirementStatus: STATUS_FILTER_MAP[statusFilter],
        search: debouncedSearch || undefined,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to download XLSX');
    } finally {
      setDownloadingXlsx(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  const pageStart = totalCount === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1;
  const pageEnd = Math.min(currentPage * PAGE_SIZE, totalCount);

  return (
    <div className="requirements-page">
      <Header
        title="Requirements"
        showBackLink
        backTo="/"
        backLabel="Dashboard"
      />

      <main className="page-main">
        {error && <div className="error-message">{error}</div>}

        {/* Status Legend */}
        <div className="status-legend">
          <div className="legend-title">Status Legend:</div>
          <div className="legend-items">
            <div className="legend-item">
              <span className="legend-dot legend-dot--overdue"></span>
              <span>Overdue</span>
            </div>
            <div className="legend-item">
              <span className="legend-dot legend-dot--due-soon"></span>
              <span>Due Soon</span>
            </div>
            <div className="legend-item">
              <span className="legend-dot legend-dot--on-track"></span>
              <span>On Track</span>
            </div>
            <div className="legend-item">
              <span className="legend-dot legend-dot--satisfied"></span>
              <span>Satisfied</span>
            </div>
            <div className="legend-item">
              <span className="legend-dot legend-dot--waived"></span>
              <span>Waived</span>
            </div>
            <div className="legend-item legend-item--link">
              <Link to="/compliance" className="compliance-link">
                View Compliance Report →
              </Link>
            </div>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="filter-bar">
          <input
            type="text"
            placeholder="Search by employee or certificate type..."
            value={searchQuery}
            onChange={(e) => handleSearchChange(e.target.value)}
            className="search-input"
          />
          <select
            value={statusFilter}
            onChange={(e) => handleStatusChange(e.target.value as StatusFilter)}
            className="filter-select"
          >
            <option value="all">All Status</option>
            <option value="overdue">Overdue</option>
            <option value="due-soon">Due Soon</option>
            <option value="on-track">On Track</option>
            <option value="satisfied">Satisfied</option>
            <option value="waived">Waived</option>
          </select>
          <button onClick={handleExportCSV} className="btn btn--secondary" disabled={downloadingCsv}>
            {downloadingCsv ? 'Downloading...' : 'Export CSV'}
          </button>
          <button onClick={handleExportXLSX} className="btn btn--secondary" disabled={downloadingXlsx}>
            {downloadingXlsx ? 'Downloading...' : 'Export XLSX'}
          </button>
          {isCoordinator && (
            <button onClick={openAssignModal} className="btn btn--success">
              + Assign Requirement
            </button>
          )}
        </div>

        {loading ? (
          <div className="loading-container">
            <span className="loading-spinner">Loading requirements...</span>
          </div>
        ) : requirements.length === 0 ? (
          <div className="empty-state">
            <h2>No Requirements</h2>
            <p>
              {totalCount === 0 && statusFilter === 'all' && !searchQuery
                ? 'No certification requirements have been assigned yet.'
                : 'No requirements match your current filters.'}
            </p>
          </div>
        ) : (
          <>
            <div className="requirements-table-container">
              <table className="requirements-table">
                <thead>
                  <tr>
                    <th>Employee</th>
                    <th>Certificate Type</th>
                    <th>Due Date</th>
                    <th>Days Left</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {requirements.map(req => {
                    const daysLeft = getDaysLeft(req);
                    const status = getStatusFromRequirement(req);

                    return (
                      <tr key={req.id}>
                        <td className="cell-employee">{req.employee_name || '-'}</td>
                        <td className="cell-type">{getCertificateTypeName(req.certificate_type_id)}</td>
                        <td className="cell-date">{parseLocalDate(req.due_date).toLocaleDateString()}</td>
                        <td className="cell-days">
                          {daysLeft !== null ? (
                            <span className={`days-badge ${daysLeft < 0 ? 'days-badge--overdue' : daysLeft <= 30 ? 'days-badge--soon' : 'days-badge--ok'}`}>
                              {daysLeft < 0
                                ? `${Math.abs(daysLeft)}d ${req.satisfied_by_id ? 'expired' : 'overdue'}`
                                : `${daysLeft}d`}
                            </span>
                          ) : (
                            <span className="text-muted">-</span>
                          )}
                        </td>
                        <td className="cell-status">
                          <StatusBadge status={status} size="small" />
                        </td>
                        <td className="cell-actions">
                          {!req.satisfied_by_id && !req.waived_at && (
                            <>
                              <Link to={`/upload?employee_id=${req.employee_id}`} className="btn btn--primary btn--small">
                                Upload
                              </Link>
                              {isCoordinator && (
                                <button
                                  onClick={() => openWaiveModal(req)}
                                  className="btn btn--secondary btn--small"
                                >
                                  Waive
                                </button>
                              )}
                            </>
                          )}
                          {req.satisfied_by_id && (
                            <span className="text-muted">Completed</span>
                          )}
                          {req.waived_at && (
                            isCoordinator ? (
                              <button
                                onClick={() => setUnwaiveTarget(req)}
                                className="btn btn--secondary btn--small"
                              >
                                Unwaive
                              </button>
                            ) : (
                              <span className="text-muted">Waived</span>
                            )
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination controls */}
            <div className="pagination-bar">
              <span className="pagination-info">
                {pageStart}–{pageEnd} of {totalCount}
              </span>
              <div className="pagination-controls">
                <button
                  className="btn btn--secondary btn--small"
                  onClick={() => setCurrentPage(1)}
                  disabled={currentPage === 1}
                >
                  «
                </button>
                <button
                  className="btn btn--secondary btn--small"
                  onClick={() => setCurrentPage(p => p - 1)}
                  disabled={currentPage === 1}
                >
                  ‹ Prev
                </button>
                <span className="pagination-page">
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  className="btn btn--secondary btn--small"
                  onClick={() => setCurrentPage(p => p + 1)}
                  disabled={currentPage === totalPages}
                >
                  Next ›
                </button>
                <button
                  className="btn btn--secondary btn--small"
                  onClick={() => setCurrentPage(totalPages)}
                  disabled={currentPage === totalPages}
                >
                  »
                </button>
              </div>
            </div>
          </>
        )}

        {assignOpen && (
          <div className="modal-overlay" onClick={closeAssignModal}>
            <div
              ref={assignModalRef}
              className="modal"
              onClick={e => e.stopPropagation()}
              role="dialog"
              aria-modal="true"
              aria-labelledby="assign-requirement-title"
            >
              <h3 id="assign-requirement-title">Assign Requirement</h3>

              {assignError && <div className="error-message">{assignError}</div>}

              <form onSubmit={handleAssignSubmit}>
                <div className="form-group">
                  <label htmlFor="assign-employee-search">Find Employee</label>
                  <input
                    id="assign-employee-search"
                    type="text"
                    placeholder="Search by name, email, or employee number..."
                    value={assignEmployeeSearch}
                    onChange={(e) => setAssignEmployeeSearch(e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="assign-employee">Employee *</label>
                  <select
                    id="assign-employee"
                    value={assignEmployeeId}
                    onChange={(e) => setAssignEmployeeId(e.target.value ? Number(e.target.value) : '')}
                    required
                  >
                    <option value="">Select an employee...</option>
                    {assignEmployeeOptions.map(emp => (
                      <option key={emp.id} value={emp.id}>
                        {emp.last_name}, {emp.first_name} ({emp.employee_number})
                      </option>
                    ))}
                  </select>
                  {assignEmployeeOptions.length === 20 && (
                    <small className="form-hint">Showing first 20 matches - refine the search to narrow down.</small>
                  )}
                </div>

                <div className="form-group">
                  <label htmlFor="assign-cert-type">Certificate Type *</label>
                  <select
                    id="assign-cert-type"
                    value={assignCertTypeId}
                    onChange={(e) => setAssignCertTypeId(e.target.value ? Number(e.target.value) : '')}
                    required
                  >
                    <option value="">Select a certificate type...</option>
                    {certificateTypes.map(type => (
                      <option key={type.id} value={type.id}>{type.name}</option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label htmlFor="assign-due-date">Due Date *</label>
                  <input
                    id="assign-due-date"
                    type="date"
                    value={assignDueDate}
                    onChange={(e) => setAssignDueDate(e.target.value)}
                    required
                  />
                </div>

                <div className="modal-actions">
                  <button
                    type="button"
                    onClick={closeAssignModal}
                    className="btn btn--secondary"
                    disabled={assignSubmitting}
                  >
                    Cancel
                  </button>
                  <button type="submit" className="btn btn--primary" disabled={assignSubmitting}>
                    {assignSubmitting ? 'Assigning...' : 'Assign Requirement'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {waiveTarget && (
          <div className="modal-overlay" onClick={closeWaiveModal}>
            <div
              ref={waiveModalRef}
              className="modal"
              onClick={e => e.stopPropagation()}
              role="dialog"
              aria-modal="true"
              aria-labelledby="waive-requirement-title"
            >
              <h3 id="waive-requirement-title">Waive Requirement</h3>
              <p>
                Waive the <strong>{getCertificateTypeName(waiveTarget.certificate_type_id)}</strong> requirement
                for <strong>{waiveTarget.employee_name || `employee #${waiveTarget.employee_id}`}</strong>?
              </p>

              {waiveError && <div className="error-message">{waiveError}</div>}

              <form onSubmit={handleWaiveSubmit}>
                <div className="form-group">
                  <label htmlFor="waive-reason">Waiver Reason * (minimum 10 characters)</label>
                  <textarea
                    id="waive-reason"
                    value={waiveReason}
                    onChange={(e) => setWaiveReason(e.target.value)}
                    minLength={10}
                    maxLength={1000}
                    rows={3}
                    required
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="waive-expiration">Waiver Expiration (optional)</label>
                  <input
                    id="waive-expiration"
                    type="date"
                    value={waiveExpiration}
                    onChange={(e) => setWaiveExpiration(e.target.value)}
                  />
                  <small className="form-hint">Leave blank for an indefinite waiver.</small>
                </div>

                <div className="modal-actions">
                  <button
                    type="button"
                    onClick={closeWaiveModal}
                    className="btn btn--secondary"
                    disabled={waiveSubmitting}
                  >
                    Cancel
                  </button>
                  <button type="submit" className="btn btn--primary" disabled={waiveSubmitting}>
                    {waiveSubmitting ? 'Waiving...' : 'Waive Requirement'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {unwaiveTarget && (
          <div className="modal-overlay" onClick={closeUnwaiveModal}>
            <div
              ref={unwaiveModalRef}
              className="modal"
              onClick={e => e.stopPropagation()}
              role="dialog"
              aria-modal="true"
              aria-labelledby="unwaive-requirement-title"
            >
              <h3 id="unwaive-requirement-title">Remove Waiver</h3>
              <p>
                Restore the <strong>{getCertificateTypeName(unwaiveTarget.certificate_type_id)}</strong> requirement
                for <strong>{unwaiveTarget.employee_name || `employee #${unwaiveTarget.employee_id}`}</strong> to
                active status?
              </p>
              {unwaiveTarget.waiver_reason && (
                <p className="text-muted">Current waiver reason: {unwaiveTarget.waiver_reason}</p>
              )}

              {unwaiveError && <div className="error-message">{unwaiveError}</div>}

              <div className="modal-actions">
                <button
                  type="button"
                  onClick={closeUnwaiveModal}
                  className="btn btn--secondary"
                  disabled={unwaiveSubmitting}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleUnwaive}
                  className="btn btn--primary"
                  disabled={unwaiveSubmitting}
                >
                  {unwaiveSubmitting ? 'Removing...' : 'Remove Waiver'}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default RequirementsPage;
