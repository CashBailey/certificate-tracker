/**
 * Employees page - Manage employees (Admin only).
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { Header } from '../components/Header';
import {
  getEmployees,
  createEmployee,
  updateEmployee,
  deactivateEmployee,
  reactivateEmployee,
  sendSetupEmail,
  User,
  EmployeeCreate,
  EmployeeUpdate,
} from '../api';
import { StatusBadge } from '../components/StatusBadge';
import './EmployeesPage.css';

type ModalMode = 'create' | 'edit' | null;

const ROLES = ['Coordinator', 'Admin', 'Employee'];
const ASSIGNABLE_ROLES = ['Coordinator', 'Employee'];

export function EmployeesPage() {
  const createEditModalRef = useRef<HTMLDivElement | null>(null);
  const deactivateModalRef = useRef<HTMLDivElement | null>(null);
  const { user } = useAuth();
  const [employees, setEmployees] = useState<User[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [activeFilter, setActiveFilter] = useState<string>('');
  const [page, setPage] = useState(0);
  const limit = 20;

  // Modal state
  const [modalMode, setModalMode] = useState<ModalMode>(null);
  const [editingEmployee, setEditingEmployee] = useState<User | null>(null);
  const [deactivateTarget, setDeactivateTarget] = useState<User | null>(null);
  const [formData, setFormData] = useState<EmployeeCreate>({
    employee_number: '',
    first_name: '',
    last_name: '',
    email: '',
    role: 'Employee',
    manager_id: null,
  });
  const [setupEmailStatus, setSetupEmailStatus] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle');
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [deactivateError, setDeactivateError] = useState<string | null>(null);
  const [deactivateSubmitting, setDeactivateSubmitting] = useState(false);

  const fetchEmployees = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: {
        skip: number;
        limit: number;
        role?: string;
        is_active?: boolean;
        search?: string;
      } = {
        skip: page * limit,
        limit,
      };

      if (roleFilter) params.role = roleFilter;
      if (activeFilter !== '') params.is_active = activeFilter === 'true';
      if (search.trim()) params.search = search.trim();

      const data = await getEmployees(params);
      setEmployees(data.employees);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load employees');
    } finally {
      setLoading(false);
    }
  }, [page, roleFilter, activeFilter, search]);

  useEffect(() => {
    fetchEmployees();
  }, [fetchEmployees]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(0);
    fetchEmployees();
  };

  const openCreateModal = () => {
    setFormData({
      employee_number: '',
      first_name: '',
      last_name: '',
      email: '',
      role: 'Employee',
      manager_id: null,
    });
    setFormError(null);
    setEditingEmployee(null);
    setModalMode('create');
  };

  const openEditModal = (emp: User) => {
    setFormData({
      employee_number: emp.employee_number,
      first_name: emp.first_name,
      last_name: emp.last_name,
      email: emp.email,
      role: emp.role,
      manager_id: null,
    });
    setSetupEmailStatus('idle');
    setFormError(null);
    setEditingEmployee(emp);
    setModalMode('edit');
  };

  const closeModal = () => {
    setModalMode(null);
    setEditingEmployee(null);
    setFormError(null);
    setSetupEmailStatus('idle');
  };

  const openDeactivateModal = (emp: User) => {
    setError(null);
    setDeactivateError(null);
    setDeactivateTarget(emp);
  };

  const closeDeactivateModal = useCallback(() => {
    if (deactivateSubmitting) return;
    setDeactivateError(null);
    setDeactivateTarget(null);
  }, [deactivateSubmitting]);

  const handleFormChange = (field: keyof EmployeeCreate, value: string | number | null) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setSubmitting(true);

    try {
      if (modalMode === 'create') {
        await createEmployee(formData);
      } else if (modalMode === 'edit' && editingEmployee) {
        const updateData: EmployeeUpdate = {
          employee_number: formData.employee_number,
          first_name: formData.first_name,
          last_name: formData.last_name,
          email: formData.email,
        };
        // The API only accepts Coordinator/Employee for role. Admin accounts
        // keep their role (sending 'Admin' would 422); non-Admins send it.
        if (editingEmployee.role !== 'Admin') {
          updateData.role = formData.role;
        }
        await updateEmployee(editingEmployee.id, updateData);
      }
      closeModal();
      fetchEmployees();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Operation failed');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSendSetupEmail = async () => {
    if (!editingEmployee) return;
    setSetupEmailStatus('sending');
    try {
      await sendSetupEmail(editingEmployee.id);
      setSetupEmailStatus('sent');
    } catch {
      setSetupEmailStatus('error');
    }
  };

  const handleDeactivate = async () => {
    if (!deactivateTarget) return;
    setDeactivateError(null);
    setDeactivateSubmitting(true);
    try {
      await deactivateEmployee(deactivateTarget.id);
      setDeactivateError(null);
      setDeactivateTarget(null);
      fetchEmployees();
    } catch (err) {
      setDeactivateError(err instanceof Error ? err.message : 'Failed to deactivate employee');
    } finally {
      setDeactivateSubmitting(false);
    }
  };

  const handleReactivate = async (emp: User) => {
    try {
      await reactivateEmployee(emp.id);
      fetchEmployees();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reactivate employee');
    }
  };

  useEffect(() => {
    const activeModal =
      modalMode !== null ? createEditModalRef.current
      : deactivateTarget ? deactivateModalRef.current
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

    const focusable = getFocusable();
    focusable[0]?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        if (modalMode !== null) {
          closeModal();
        } else {
          closeDeactivateModal();
        }
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
  }, [closeDeactivateModal, deactivateTarget, modalMode]);

  const totalPages = Math.ceil(total / limit);

  return (
    <div className="employees-page">
      <Header
        title="Employee Management"
        showBackLink
        backTo="/"
        backLabel="Dashboard"
      />

      <main className="page-main">
        {error && <div className="error-message">{error}</div>}

        <div className="toolbar">
          <form onSubmit={handleSearch} className="search-form">
            <input
              type="text"
              placeholder="Search by name, email, or employee number..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="search-input"
            />
            <button type="submit" className="btn btn--primary">Search</button>
          </form>

          <div className="filters">
            <select
              value={roleFilter}
              onChange={(e) => { setRoleFilter(e.target.value); setPage(0); }}
              className="filter-select"
            >
              <option value="">All Roles</option>
              {ROLES.map(role => (
                <option key={role} value={role}>{role}</option>
              ))}
            </select>

            <select
              value={activeFilter}
              onChange={(e) => { setActiveFilter(e.target.value); setPage(0); }}
              className="filter-select"
            >
              <option value="">All Status</option>
              <option value="true">Active Only</option>
              <option value="false">Inactive Only</option>
            </select>
          </div>

          <button onClick={openCreateModal} className="btn btn--success">
            + Add Employee
          </button>
        </div>

        {loading ? (
          <div className="loading-container">
            <span className="loading-spinner">Loading employees...</span>
          </div>
        ) : employees.length === 0 ? (
          <div className="empty-state">
            <h2>No Employees Found</h2>
            <p>No employees match your search criteria.</p>
            <p className="empty-state-hint">
              <em>Note: System Admin accounts are hidden from the default list. Use the Role filter and select <strong>Admin</strong> to view them.</em>
            </p>
          </div>
        ) : (
          <>
            <div className="employees-table-container">
              <table className="employees-table">
                <thead>
                  <tr>
                    <th>Employee #</th>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {employees.map(emp => (
                    <tr key={emp.id} className={!emp.is_active ? 'inactive-row' : ''}>
                      <td className="cell-emp-number">{emp.employee_number}</td>
                      <td className="cell-name">{emp.first_name} {emp.last_name}</td>
                      <td className="cell-email">{emp.email}</td>
                      <td>
                        <span className={`role-badge role-badge--${emp.role.toLowerCase()}`}>
                          {emp.role}
                        </span>
                      </td>
                      <td>
                        <StatusBadge
                          status={emp.is_active ? 'Valid' : 'Expired'}
                          size="small"
                        />
                      </td>
                      <td>
                        <div className="actions-cell">
                          <button
                            onClick={() => openEditModal(emp)}
                            className="btn btn--small btn--secondary"
                          >
                            Edit
                          </button>
                          {emp.is_active ? (
                            <button
                              onClick={() => openDeactivateModal(emp)}
                              className="btn btn--small btn--danger"
                              disabled={emp.id === user?.id}
                              title={emp.id === user?.id ? "Can't deactivate yourself" : ''}
                            >
                              Deactivate
                            </button>
                          ) : (
                            <button
                              onClick={() => handleReactivate(emp)}
                              className="btn btn--small btn--success"
                            >
                              Reactivate
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="pagination">
              <span className="pagination-info">
                Showing {page * limit + 1} - {Math.min((page + 1) * limit, total)} of {total}
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

        {/* Create/Edit Modal */}
        {modalMode && (
          <div className="modal-overlay" onClick={closeModal}>
            <div
              ref={createEditModalRef}
              className="modal modal--large"
              onClick={e => e.stopPropagation()}
              role="dialog"
              aria-modal="true"
            >
              <h3>{modalMode === 'create' ? 'Add New Employee' : 'Edit Employee'}</h3>

              {formError && <div className="error-message">{formError}</div>}

              <form onSubmit={handleSubmit} className="employee-form">
                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="employee_number">Employee Number *</label>
                    <input
                      id="employee_number"
                      type="text"
                      value={formData.employee_number}
                      onChange={(e) => handleFormChange('employee_number', e.target.value)}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="role">Role *</label>
                    {modalMode === 'edit' && editingEmployee?.role === 'Admin' ? (
                      // Admin role is not editable through this form; show it read-only.
                      <select id="role" value="Admin" disabled>
                        <option value="Admin">Admin</option>
                      </select>
                    ) : (
                      <select
                        id="role"
                        value={formData.role}
                        onChange={(e) => handleFormChange('role', e.target.value)}
                        required
                      >
                        {ASSIGNABLE_ROLES.map(role => (
                          <option key={role} value={role}>{role}</option>
                        ))}
                      </select>
                    )}
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="first_name">First Name *</label>
                    <input
                      id="first_name"
                      type="text"
                      value={formData.first_name}
                      onChange={(e) => handleFormChange('first_name', e.target.value)}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="last_name">Last Name *</label>
                    <input
                      id="last_name"
                      type="text"
                      value={formData.last_name}
                      onChange={(e) => handleFormChange('last_name', e.target.value)}
                      required
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label htmlFor="email">Email *</label>
                  <input
                    id="email"
                    type="email"
                    value={formData.email}
                    onChange={(e) => handleFormChange('email', e.target.value)}
                    required
                  />
                </div>

                {modalMode === 'create' && (
                  <p className="form-help-text">
                    A setup email will be sent to the employee so they can create their own password.
                  </p>
                )}

                {modalMode === 'edit' && (
                  <div className="form-group">
                    <label>Account Setup Email</label>
                    <div className="setup-email-row">
                      <button
                        type="button"
                        className="btn btn--secondary"
                        onClick={handleSendSetupEmail}
                        disabled={setupEmailStatus === 'sending'}
                      >
                        {setupEmailStatus === 'sending' ? 'Sending...' : 'Send Setup Email'}
                      </button>
                      {setupEmailStatus === 'sent' && (
                        <span className="setup-email-feedback setup-email-feedback--ok">
                          Email sent successfully.
                        </span>
                      )}
                      {setupEmailStatus === 'error' && (
                        <span className="setup-email-feedback setup-email-feedback--err">
                          Failed to send. Please try again.
                        </span>
                      )}
                    </div>
                    <small className="form-hint">
                      Sends a link for the employee to set or reset their password.
                    </small>
                  </div>
                )}

                <div className="modal-actions">
                  <button
                    type="button"
                    onClick={closeModal}
                    className="btn btn--secondary"
                    disabled={submitting}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn--primary"
                    disabled={submitting}
                  >
                    {submitting ? 'Saving...' : modalMode === 'create' ? 'Create Employee' : 'Save Changes'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {deactivateTarget && (
          <div className="modal-overlay" onClick={closeDeactivateModal}>
            <div
              ref={deactivateModalRef}
              className="modal"
              onClick={e => e.stopPropagation()}
              role="dialog"
              aria-modal="true"
            >
              <h3>Deactivate Employee</h3>
              <p>
                Deactivating <strong>{deactivateTarget.first_name} {deactivateTarget.last_name}</strong> will prevent
                them from signing in until the account is reactivated.
              </p>

              {deactivateError && <div className="error-message">{deactivateError}</div>}

              <div className="modal-actions">
                <button
                  type="button"
                  onClick={closeDeactivateModal}
                  className="btn btn--secondary"
                  disabled={deactivateSubmitting}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleDeactivate}
                  className="btn btn--danger"
                  disabled={deactivateSubmitting}
                >
                  {deactivateSubmitting ? 'Deactivating...' : 'Deactivate Employee'}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default EmployeesPage;
