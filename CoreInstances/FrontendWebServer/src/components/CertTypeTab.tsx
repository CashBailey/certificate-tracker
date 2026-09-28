/**
 * CertTypeTab — certificate type management tab for ConfigurationPage.
 *
 * Lists all cert types in a table with search, and provides create/edit/delete
 * via a modal form. Follows EmployeesPage patterns.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  getCertificateTypes,
  createCertificateType,
  updateCertificateType,
  deleteCertificateType,
  CertificateType,
  CertificateTypeCreate,
  CertificateTypeUpdate,
} from '../api';
import './CertTypeTab.css';

type ModalMode = 'create' | 'edit' | null;

interface FormData {
  name: string;
  description: string;
  validity_period_days: string;
}

const EMPTY_FORM: FormData = {
  name: '',
  description: '',
  validity_period_days: '',
};

function sortCertTypes(items: CertificateType[]): CertificateType[] {
  return [...items].sort((a, b) => a.name.localeCompare(b.name));
}

export function CertTypeTab() {
  const [certTypes, setCertTypes] = useState<CertificateType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  // Modal state
  const [modalMode, setModalMode] = useState<ModalMode>(null);
  const [editingType, setEditingType] = useState<CertificateType | null>(null);
  const [formData, setFormData] = useState<FormData>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const fetchCertTypes = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getCertificateTypes();
      setCertTypes(sortCertTypes(data));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load certificate types');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCertTypes();
  }, [fetchCertTypes]);

  // Client-side search filter
  const filteredTypes = certTypes.filter(ct => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      ct.name.toLowerCase().includes(q) ||
      ct.description.toLowerCase().includes(q)
    );
  });

  const openCreateModal = () => {
    setFormData(EMPTY_FORM);
    setFormError(null);
    setEditingType(null);
    setModalMode('create');
  };

  const openEditModal = (ct: CertificateType) => {
    setFormData({
      name: ct.name,
      description: ct.description,
      validity_period_days: ct.validity_period_days !== null ? String(ct.validity_period_days) : '',
    });
    setFormError(null);
    setEditingType(ct);
    setModalMode('edit');
  };

  const closeModal = () => {
    setModalMode(null);
    setEditingType(null);
    setFormError(null);
  };

  const handleFormChange = (field: keyof FormData, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const validateForm = (): string | null => {
    if (!formData.name.trim()) {
      return 'Name is required.';
    }
    if (formData.name.trim().length > 200) {
      return 'Name must be 200 characters or less.';
    }
    if (!formData.description.trim()) {
      return 'Description is required.';
    }
    if (formData.validity_period_days.trim()) {
      const days = Number(formData.validity_period_days);
      if (!Number.isInteger(days) || days < 1) {
        return 'Validity period must be a positive whole number of days.';
      }
    }
    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    const validationError = validateForm();
    if (validationError) {
      setFormError(validationError);
      return;
    }

    setSubmitting(true);
    try {
      const validityDays = formData.validity_period_days.trim()
        ? Number(formData.validity_period_days)
        : null;

      if (modalMode === 'create') {
        const payload: CertificateTypeCreate = {
          name: formData.name.trim(),
          description: formData.description.trim(),
          validity_period_days: validityDays,
        };
        const created = await createCertificateType(payload);
        setCertTypes((current) => sortCertTypes([...current, created]));
      } else if (modalMode === 'edit' && editingType) {
        const payload: CertificateTypeUpdate = {
          name: formData.name.trim(),
          description: formData.description.trim(),
          validity_period_days: validityDays,
        };
        const updated = await updateCertificateType(editingType.id, payload);
        setCertTypes((current) =>
          sortCertTypes(current.map((item) => (item.id === updated.id ? updated : item)))
        );
      }
      closeModal();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Operation failed');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (ct: CertificateType) => {
    if (!confirm(`Are you sure you want to delete "${ct.name}"? This cannot be undone.`)) {
      return;
    }
    try {
      await deleteCertificateType(ct.id);
      setCertTypes((current) => current.filter((item) => item.id !== ct.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete certificate type');
    }
  };

  const formatValidityPeriod = (days: number | null): string => {
    if (days === null) return 'Non-expiring';
    if (days === 1) return '1 day';
    if (days < 365) return `${days} days`;
    const years = Math.floor(days / 365);
    const remaining = days % 365;
    if (remaining === 0) return years === 1 ? '1 year' : `${years} years`;
    return `${years}y ${remaining}d`;
  };

  return (
    <div className="certtype-tab">
      {error && <div className="error-message">{error}</div>}

      <div className="toolbar">
        <div className="search-form">
          <input
            type="text"
            placeholder="Search certificate types..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="search-input"
          />
        </div>
        <button onClick={openCreateModal} className="btn btn--success">
          + Add Certificate Type
        </button>
      </div>

      {loading ? (
        <div className="loading-container">
          <span className="loading-spinner">Loading certificate types...</span>
        </div>
      ) : filteredTypes.length === 0 ? (
        <div className="empty-state">
          <h2>No Certificate Types</h2>
          <p>
            {certTypes.length === 0
              ? 'No certificate types have been configured yet.'
              : 'No certificate types match your search.'}
          </p>
        </div>
      ) : (
        <div className="certtype-table-container">
          <table className="certtype-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Description</th>
                <th>Validity Period</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredTypes.map(ct => (
                <tr key={ct.id}>
                  <td className="cell-name">{ct.name}</td>
                  <td className="cell-description">{ct.description}</td>
                  <td className="cell-validity">
                    <span className={`validity-badge${ct.validity_period_days === null ? ' validity-badge--none' : ''}`}>
                      {formatValidityPeriod(ct.validity_period_days)}
                    </span>
                  </td>
                  <td className="cell-date">
                    {new Date(ct.created_at).toLocaleDateString()}
                  </td>
                  <td>
                    <div className="actions-cell">
                      <button
                        onClick={() => openEditModal(ct)}
                        className="btn btn--small btn--secondary"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleDelete(ct)}
                        className="btn btn--small btn--danger"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create/Edit Modal */}
      {modalMode && (
        <div className="modal-overlay" onClick={closeModal}>
          <div className="modal modal--large" onClick={e => e.stopPropagation()}>
            <h3>{modalMode === 'create' ? 'Add Certificate Type' : 'Edit Certificate Type'}</h3>

            {formError && <div className="error-message">{formError}</div>}

            <form onSubmit={handleSubmit} className="certtype-form">
              <div className="form-group">
                <label htmlFor="ct-name">Name *</label>
                <input
                  id="ct-name"
                  type="text"
                  value={formData.name}
                  onChange={(e) => handleFormChange('name', e.target.value)}
                  maxLength={200}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="ct-description">Description *</label>
                <textarea
                  id="ct-description"
                  value={formData.description}
                  onChange={(e) => handleFormChange('description', e.target.value)}
                  rows={3}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="ct-validity">Validity Period (days)</label>
                <input
                  id="ct-validity"
                  type="number"
                  value={formData.validity_period_days}
                  onChange={(e) => handleFormChange('validity_period_days', e.target.value)}
                  min={1}
                  placeholder="Leave empty for non-expiring"
                />
                <small className="form-hint">
                  How many days a certificate of this type remains valid. Leave empty if it does not expire.
                </small>
              </div>

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
                  {submitting ? 'Saving...' : modalMode === 'create' ? 'Create' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default CertTypeTab;
