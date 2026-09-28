/**
 * Review Detail page - Review and approve/reject a single extraction.
 * Features side-by-side document preview with bounding box highlights.
 *
 * Fields are always editable — the reviewer corrects values by typing directly.
 * Submit Review finalizes the review and persists corrections in one action.
 *
 * Supports next/previous navigation when accessed from the review queue (C3).
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useParams, useNavigate, useLocation, Link } from 'react-router-dom';
import { Header } from '../components/Header';
import { getExtraction, approveExtraction, rejectExtraction, getDocumentContentUrl, Extraction, normalizeReviewState } from '../api';
import { StatusBadge } from '../components/StatusBadge';
import { FieldEditor } from '../components/FieldEditor';
import { DocumentViewer, BoundingBoxHighlight } from '../components/DocumentViewer';
import {
  canApproveReview,
  DocumentLoadState,
} from '../utils/reviewWorkflow';
import './ReviewDetailPage.css';

const REQUIRED_FIELDS = ['certificate_holder_name', 'certificate_type', 'issue_date'];

export function ReviewDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  // Queue navigation state (passed from ReviewQueuePage)
  const queueIds: number[] = (location.state as { queueIds?: number[] })?.queueIds ?? [];
  const currentIndex = queueIds.indexOf(parseInt(id ?? '0'));
  const prevId = currentIndex > 0 ? queueIds[currentIndex - 1] : null;
  const nextId = currentIndex < queueIds.length - 1 ? queueIds[currentIndex + 1] : null;

  const [extraction, setExtraction] = useState<Extraction | null>(null);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [documentLoadState, setDocumentLoadState] = useState<DocumentLoadState>('loading');
  const [error, setError] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [showRejectModal, setShowRejectModal] = useState(false);
  const rejectReasonRef = useRef<HTMLTextAreaElement>(null);

  // Document viewer state
  const [documentUrl, setDocumentUrl] = useState<string | null>(null);
  const [activeFieldName, setActiveFieldName] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchExtraction() {
      if (!id) return;
      setLoading(true);
      setError(null);
      setExtraction(null);
      setDocumentUrl(null);
      try {
        const data = await getExtraction(parseInt(id));
        if (cancelled) return;
        setExtraction(data);

        // Initialize field values from extracted data
        const initialValues = Object.fromEntries(
          REQUIRED_FIELDS.map((fieldName) => [fieldName, ''])
        );
        for (const [fieldName, field] of Object.entries(data.extracted_fields)) {
          initialValues[fieldName] = field.value ?? '';
        }
        setFieldValues(initialValues);

        // Build document URL for PDF viewer (uses short-lived view token, not access JWT)
        if (data.document_id) {
          try {
            const url = await getDocumentContentUrl(data.document_id);
            if (!cancelled) setDocumentUrl(url);
          } catch {
            if (!cancelled) setDocumentUrl(null);
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load extraction');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchExtraction();
    return () => {
      cancelled = true;
    };
  }, [id]);

  useEffect(() => {
    if (showRejectModal) rejectReasonRef.current?.focus();
  }, [showRejectModal]);

  const handleFieldChange = useCallback((fieldName: string, value: string) => {
    setFieldValues(prev => ({ ...prev, [fieldName]: value }));
    // Clear validation error when user types
    setValidationErrors(prev => {
      if (!prev[fieldName]) return prev;
      const next = { ...prev };
      delete next[fieldName];
      return next;
    });
  }, []);

  const validateFields = (): boolean => {
    const errors: Record<string, string> = {};
    for (const fieldName of REQUIRED_FIELDS) {
      if (!fieldValues[fieldName]?.trim()) {
        errors[fieldName] = 'This field is required';
      }
    }
    setValidationErrors(errors);

    if (Object.keys(errors).length > 0) {
      // Scroll to first error
      const firstErrorField = Object.keys(errors)[0];
      const el = document.getElementById(`field-${firstErrorField}`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
      return false;
    }
    return true;
  };

  // Navigate to next record after approve/reject, or back to queue if at end
  const navigateAfterAction = () => {
    const remainingIds = queueIds.filter(qid => qid !== parseInt(id ?? '0'));
    if (nextId !== null) {
      navigate(`/review/${nextId}`, { state: { queueIds: remainingIds }, replace: true });
    } else if (prevId !== null) {
      navigate(`/review/${prevId}`, { state: { queueIds: remainingIds }, replace: true });
    } else {
      navigate('/review', { replace: true });
    }
  };

  const handleSubmitReview = async () => {
    if (!extraction) return;
    if (!validateFields()) return;

    setSubmitting(true);
    setError(null);

    try {
      // Compute corrections: only fields that differ from original
      const corrections: Record<string, string> = {};
      for (const [fieldName, currentValue] of Object.entries(fieldValues)) {
        const originalValue = extraction.extracted_fields[fieldName]?.value ?? '';
        if (currentValue !== originalValue) {
          corrections[fieldName] = currentValue;
        }
      }

      await approveExtraction(
        extraction.id,
        Object.keys(corrections).length > 0 ? corrections : undefined
      );
      navigateAfterAction();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit review');
    } finally {
      setSubmitting(false);
    }
  };

  const handleReject = async () => {
    if (!extraction || rejectReason.trim().length < 10) return;

    setSubmitting(true);
    setError(null);

    try {
      await rejectExtraction(extraction.id, rejectReason);
      navigateAfterAction();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reject extraction');
    } finally {
      setSubmitting(false);
      setShowRejectModal(false);
    }
  };

  const handleNavigatePrev = () => {
    if (prevId !== null) {
      navigate(`/review/${prevId}`, { state: { queueIds } });
    }
  };

  const handleNavigateNext = () => {
    if (nextId !== null) {
      navigate(`/review/${nextId}`, { state: { queueIds } });
    }
  };

  const getReviewStateDisplay = (state: string): string => {
    return normalizeReviewState(state);
  };

  const normalizedReviewState = extraction ? normalizeReviewState(extraction.review_state) : null;
  const isProcessing = normalizedReviewState === 'Processing';
  const isEditable = normalizedReviewState === 'PendingReview';
  const displayedFieldNames = useMemo(() => {
    if (!extraction) return [];
    return Array.from(new Set([
      ...REQUIRED_FIELDS,
      ...Object.keys(extraction.extracted_fields),
    ]));
  }, [extraction]);

  // Handle field click from FieldEditor
  const handleFieldClick = useCallback((fieldName: string) => {
    setActiveFieldName(fieldName);
  }, []);

  // Handle highlight click from DocumentViewer
  const handleHighlightClick = useCallback((fieldName: string) => {
    setActiveFieldName(fieldName);
    // Scroll to field in the fields list
    const fieldElement = document.getElementById(`field-${fieldName}`);
    if (fieldElement) {
      fieldElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, []);

  // Build bounding box highlights from extraction data
  const highlights = useMemo((): BoundingBoxHighlight[] => {
    if (!extraction?.extracted_fields) return [];

    const result: BoundingBoxHighlight[] = [];

    for (const [fieldName, field] of Object.entries(extraction.extracted_fields)) {
      if (field.bbox_norm && field.bbox_norm.length === 4) {
        result.push({
          fieldName,
          bbox: field.bbox_norm,
          page: field.page || 1,
        });
      }
    }

    return result;
  }, [extraction?.extracted_fields]);

  if (loading) {
    return (
      <div className="loading-container">
        <span className="loading-spinner">Loading extraction...</span>
      </div>
    );
  }

  if (!extraction) {
    return (
      <div className="review-detail-page">
        <Header
          title="Extraction Not Found"
          showBackLink
          backTo="/review"
          backLabel="Review Queue"
        />
        <main className="page-main">
          <div className="error-message">The requested extraction could not be found.</div>
        </main>
      </div>
    );
  }

  return (
    <div className="review-detail-page">
      <Header
        title={`Review Extraction #${extraction.id}`}
        showBackLink
        backTo="/review"
        backLabel="Review Queue"
      />

      <main className="review-detail-main">
        {error && (
          <div className="error-message error-message--sticky" role="alert">
            {error}
          </div>
        )}

        <div className="review-layout-split">
          {/* Document Viewer Panel (Left) */}
          <div className="review-document-panel">
            {documentUrl ? (
              <DocumentViewer
                documentUrl={documentUrl}
                highlights={highlights}
                activeFieldName={activeFieldName}
                onHighlightClick={handleHighlightClick}
                onLoadStateChange={setDocumentLoadState}
              />
            ) : (
              <div className="document-unavailable">
                <p>Document preview unavailable</p>
              </div>
            )}
          </div>

          {/* Fields and Actions Panel (Right) */}
          <div className="review-fields-panel">
            {/* Record Navigation (C3) — only shown when navigated from queue */}
            {queueIds.length > 0 && (
              <div className="record-nav">
                <button
                  className="btn btn--secondary btn--small"
                  onClick={handleNavigatePrev}
                  disabled={prevId === null}
                >
                  &larr; Previous
                </button>
                <span className="record-nav__position">
                  {currentIndex + 1} of {queueIds.length}
                </span>
                <button
                  className="btn btn--secondary btn--small"
                  onClick={handleNavigateNext}
                  disabled={nextId === null}
                >
                  Next &rarr;
                </button>
              </div>
            )}

            <div className="info-bar">
              <StatusBadge status={getReviewStateDisplay(extraction.review_state)} />
              <span className="info-bar__item">Doc #{extraction.document_id}</span>
              {extraction.template_id && (
                <span className="info-bar__item">{extraction.template_id} v{extraction.template_version}</span>
              )}
              <span className="info-bar__item">{new Date(extraction.created_at).toLocaleDateString()}</span>
            </div>

            {isProcessing ? (
              <div className="review-main">
                <h2>Extraction In Progress</h2>
                <p className="fields-hint">
                  This document is still being processed by the extraction pipeline.
                  It will appear in the review queue once extraction is complete.
                </p>
                <Link to="/review" className="btn btn--secondary">
                  Back to Review Queue
                </Link>
              </div>
            ) : (
              <div className="review-main">
                <h2>Extracted Fields</h2>
                {isEditable ? (
                  <p className="fields-hint">Review values and correct any errors. Click a field to highlight it in the document.</p>
                ) : (
                  <p className="fields-hint">This extraction has been {extraction.review_state.toLowerCase()}. Fields are read-only.</p>
                )}
                <div className="fields-list">
                  {displayedFieldNames.map((fieldName) => {
                    const field = extraction.extracted_fields[fieldName];
                    return (
                      <div
                        key={fieldName}
                        id={`field-${fieldName}`}
                        className={`field-wrapper ${activeFieldName === fieldName ? 'field-wrapper--active' : ''}`}
                        onClick={() => handleFieldClick(fieldName)}
                      >
                        <FieldEditor
                          fieldName={fieldName}
                          value={fieldValues[fieldName] ?? field?.value ?? ''}
                          candidates={extraction.review_assist?.[fieldName]?.candidates}
                          onChange={(value) => handleFieldChange(fieldName, value)}
                          error={validationErrors[fieldName]}
                          readOnly={!isEditable}
                          required={REQUIRED_FIELDS.includes(fieldName)}
                        />
                      </div>
                    );
                  })}
                </div>

                {isEditable && (
                  <div className="review-actions">
                    {documentLoadState !== 'ready' && (
                      <p className="fields-hint" role="status">
                        Approval is available after the document preview loads successfully.
                      </p>
                    )}
                    <button
                      onClick={handleSubmitReview}
                      disabled={!canApproveReview(documentLoadState, submitting)}
                      className="btn btn--primary"
                    >
                      {submitting ? 'Submitting...' : 'Submit Review'}
                    </button>
                    <button
                      onClick={() => setShowRejectModal(true)}
                      disabled={submitting}
                      className="btn btn--danger"
                    >
                      Reject
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {showRejectModal && (
          <div className="modal-overlay" onClick={() => setShowRejectModal(false)}>
            <div
              className="modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="reject-dialog-title"
              onClick={e => e.stopPropagation()}
              onKeyDown={(e) => {
                if (e.key === 'Escape') setShowRejectModal(false);
              }}
            >
              <h3 id="reject-dialog-title">Reject Extraction</h3>
              <p>Please provide a reason for rejecting this extraction:</p>
              <textarea
                ref={rejectReasonRef}
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="Enter rejection reason..."
                className="reject-textarea"
                rows={4}
                minLength={10}
                maxLength={1000}
                required
                aria-describedby="reject-reason-help"
              />
              <p id="reject-reason-help" className="fields-hint">
                Enter at least 10 characters.
              </p>
              <div className="modal-actions">
                <button
                  onClick={() => setShowRejectModal(false)}
                  className="btn btn--secondary"
                >
                  Cancel
                </button>
                <button
                  onClick={handleReject}
                  disabled={rejectReason.trim().length < 10 || submitting}
                  className="btn btn--danger"
                >
                  {submitting ? 'Rejecting...' : 'Reject'}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default ReviewDetailPage;
