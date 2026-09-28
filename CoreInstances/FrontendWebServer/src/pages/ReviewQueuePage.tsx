/**
 * Review Queue page - List pending extractions for review.
 */

import { useState, useEffect, useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Header } from '../components/Header';
import { getExtractions, Extraction, normalizeReviewState } from '../api';
import { parseLocalDate } from '../utils/date';
import { StatusBadge } from '../components/StatusBadge';
import './ReviewQueuePage.css';

type AgeFilter = 'all' | 'today' | 'week' | 'older' | 'custom';
const REVIEW_STATUS_VALUES = new Set(['PendingReview', 'Approved', 'Rejected', 'all']);
const AGE_FILTER_VALUES = new Set<AgeFilter>(['all', 'today', 'week', 'older', 'custom']);

export function ReviewQueuePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [extractions, setExtractions] = useState<Extraction[]>([]);
  const [allExtractions, setAllExtractions] = useState<Extraction[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>(() => {
    const status = searchParams.get('status');
    return status && REVIEW_STATUS_VALUES.has(status) ? status : 'PendingReview';
  });
  const [ageFilter, setAgeFilter] = useState<AgeFilter>(() => {
    const age = searchParams.get('age');
    return age && AGE_FILTER_VALUES.has(age as AgeFilter) ? (age as AgeFilter) : 'all';
  });
  const [searchQuery, setSearchQuery] = useState(() => searchParams.get('search') ?? '');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [customFrom, setCustomFrom] = useState(() => searchParams.get('from') ?? '');
  const [customTo, setCustomTo] = useState(() => searchParams.get('to') ?? '');

  useEffect(() => {
    const next = new URLSearchParams();
    if (statusFilter !== 'PendingReview') {
      next.set('status', statusFilter);
    }
    if (ageFilter !== 'all') {
      next.set('age', ageFilter);
    }
    if (searchQuery) {
      next.set('search', searchQuery);
    }
    if (customFrom) {
      next.set('from', customFrom);
    }
    if (customTo) {
      next.set('to', customTo);
    }
    if (next.toString() !== searchParams.toString()) {
      setSearchParams(next, { replace: true });
    }
  }, [statusFilter, ageFilter, searchQuery, customFrom, customTo, searchParams, setSearchParams]);

  useEffect(() => {
    async function fetchExtractions() {
      setLoading(true);
      try {
        // Fetch all extractions for counts, and filtered for display
        const [all, filtered] = await Promise.all([
          getExtractions(),
          getExtractions(statusFilter === 'all' ? undefined : statusFilter),
        ]);
        setAllExtractions(all);
        setExtractions(filtered);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load extractions');
      } finally {
        setLoading(false);
      }
    }
    fetchExtractions();
  }, [statusFilter]);

  const getReviewStateDisplay = (state: string): string => {
    return normalizeReviewState(state);
  };

  const countNeedsReview = (extraction: Extraction): number => {
    return Object.values(extraction.extracted_fields).filter(f => f.needs_review).length;
  };

  const getAgeInDays = (createdAt: string): number => {
    const created = new Date(createdAt);
    const now = new Date();
    return Math.floor((now.getTime() - created.getTime()) / (1000 * 60 * 60 * 24));
  };

  // Summary counts
  const summaryCounts = useMemo(() => {
    const normalized = allExtractions.map((e) => normalizeReviewState(e.review_state));
    return {
      pending: normalized.filter((state) => state === 'PendingReview').length,
      approved: normalized.filter((state) => state === 'Approved').length,
      rejected: normalized.filter((state) => state === 'Rejected').length,
    };
  }, [allExtractions]);

  // Filtered extractions
  const filteredExtractions = useMemo(() => {
    return extractions.filter(extraction => {
      // Search filter
      if (searchQuery) {
        const searchLower = searchQuery.toLowerCase();
        const idMatch = extraction.id.toString().includes(searchLower);
        const templateMatch = extraction.template_id?.toLowerCase().includes(searchLower);
        if (!idMatch && !templateMatch) return false;
      }

      // Age filter
      if (ageFilter !== 'all') {
        if (ageFilter === 'custom') {
          if (customFrom || customTo) {
            const createdDate = new Date(extraction.created_at);
            createdDate.setHours(0, 0, 0, 0);
            if (customFrom) {
              // parseLocalDate gives local midnight of the selected day.
              const fromDate = parseLocalDate(customFrom);
              if (createdDate < fromDate) return false;
            }
            if (customTo) {
              const toDate = parseLocalDate(customTo);
              toDate.setHours(23, 59, 59, 999);
              if (createdDate > toDate) return false;
            }
          }
        } else {
          const ageDays = getAgeInDays(extraction.created_at);
          switch (ageFilter) {
            case 'today':
              if (ageDays > 0) return false;
              break;
            case 'week':
              if (ageDays > 7) return false;
              break;
            case 'older':
              if (ageDays <= 7) return false;
              break;
          }
        }
      }

      return true;
    });
  }, [extractions, searchQuery, ageFilter, customFrom, customTo]);

  // Queue IDs for next/prev navigation in ReviewDetailPage (C3)
  const queueIds = useMemo(() => filteredExtractions.map(e => e.id), [filteredExtractions]);

  if (loading) {
    return (
      <div className="loading-container">
        <span className="loading-spinner">Loading review queue...</span>
      </div>
    );
  }

  return (
    <div className="review-queue-page">
      <Header
        title="Review Queue"
        showBackLink
        backTo="/"
        backLabel="Dashboard"
      />

      <main className="page-main">
        {error && <div className="error-message">{error}</div>}

        {/* Summary Strip */}
        <div className="summary-strip">
          <button
            className={`summary-pill summary-pill--pending ${statusFilter === 'PendingReview' ? 'active' : ''}`}
            onClick={() => setStatusFilter('PendingReview')}
          >
            <span className="summary-pill__count">{summaryCounts.pending}</span>
            <span>Pending</span>
          </button>
          <button
            className={`summary-pill summary-pill--approved ${statusFilter === 'Approved' ? 'active' : ''}`}
            onClick={() => setStatusFilter('Approved')}
          >
            <span className="summary-pill__count">{summaryCounts.approved}</span>
            <span>Approved</span>
          </button>
          <button
            className={`summary-pill summary-pill--rejected ${statusFilter === 'Rejected' ? 'active' : ''}`}
            onClick={() => setStatusFilter('Rejected')}
          >
            <span className="summary-pill__count">{summaryCounts.rejected}</span>
            <span>Rejected</span>
          </button>
          <button
            className={`summary-pill ${statusFilter === 'all' ? 'active' : ''}`}
            onClick={() => setStatusFilter('all')}
          >
            <span>All</span>
          </button>
        </div>

        {/* Filter Bar */}
        <div className="filter-bar">
          <input
            type="text"
            placeholder="Search by ID or template..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="search-input"
          />
          <select
            value={ageFilter}
            onChange={(e) => {
              const newFilter = e.target.value as AgeFilter;
              setAgeFilter(newFilter);
              if (newFilter !== 'custom') {
                setCustomFrom('');
                setCustomTo('');
              }
            }}
            className="filter-select"
          >
            <option value="all">Any Age</option>
            <option value="today">Today</option>
            <option value="week">This Week</option>
            <option value="older">Older than 7 days</option>
            <option value="custom">Custom Range</option>
          </select>
          {ageFilter === 'custom' && (
            <div className="date-range-inputs">
              <label className="date-range-label">
                From
                <input
                  type="date"
                  value={customFrom}
                  onChange={(e) => setCustomFrom(e.target.value)}
                  className="date-input"
                />
              </label>
              <label className="date-range-label">
                To
                <input
                  type="date"
                  value={customTo}
                  onChange={(e) => setCustomTo(e.target.value)}
                  className="date-input"
                  min={customFrom || undefined}
                />
              </label>
            </div>
          )}
        </div>

        {filteredExtractions.length === 0 ? (
          <div className="empty-state">
            <h2>No Extractions</h2>
            <p>
              {extractions.length === 0
                ? statusFilter === 'PendingReview'
                  ? 'No documents are waiting for review.'
                  : 'No extractions match the selected status.'
                : 'No extractions match your current filters.'}
            </p>
          </div>
        ) : (
          <div className="extractions-grid">
            {filteredExtractions.map(extraction => {
              const needsReviewCount = countNeedsReview(extraction);
              const ageDays = getAgeInDays(extraction.created_at);

              return (
                <Link
                  key={extraction.id}
                  to={`/review/${extraction.id}`}
                  state={{ queueIds }}
                  className="extraction-card"
                >
                  <div className="extraction-card__header">
                    <span className="extraction-id">#{extraction.id}</span>
                    <StatusBadge status={getReviewStateDisplay(extraction.review_state)} size="small" />
                  </div>

                  <div className="extraction-card__body">
                    <div className="extraction-stat">
                      <span className="stat-label">Fields for Review</span>
                      <span className={`stat-value ${needsReviewCount > 0 ? 'needs-review' : ''}`}>
                        {needsReviewCount}
                      </span>
                    </div>

                    {extraction.template_id && (
                      <div className="extraction-stat">
                        <span className="stat-label">Template</span>
                        <span className="stat-value">{extraction.template_id}</span>
                      </div>
                    )}

                    <div className="extraction-stat">
                      <span className="stat-label">Age</span>
                      <span className="stat-value">
                        {ageDays === 0 ? 'Today' : ageDays === 1 ? '1 day' : `${ageDays} days`}
                      </span>
                    </div>
                  </div>

                  <div className="extraction-card__footer">
                    <span className="date">
                      Uploaded {new Date(extraction.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}

export default ReviewQueuePage;
