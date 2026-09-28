/**
 * DocumentViewer component for displaying PDF documents with bounding box overlays.
 * Enables side-by-side review of documents with extracted field highlights.
 */

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.js?url';
import { DocumentLoadState } from '../utils/reviewWorkflow';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import './DocumentViewer.css';

// Keep the worker local so review works offline and does not depend on a CDN.
pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

export interface BoundingBoxHighlight {
  fieldName: string;
  bbox: [number, number, number, number]; // [x1, y1, x2, y2] normalized 0-1
  page: number;
  color?: string;
  isActive?: boolean;
}

interface DocumentViewerProps {
  documentUrl?: string;
  documentData?: Uint8Array;
  highlights?: BoundingBoxHighlight[];
  activeFieldName?: string | null;
  onHighlightClick?: (fieldName: string) => void;
  onPageChange?: (page: number) => void;
  onLoadStateChange?: (state: DocumentLoadState) => void;
}

type ZoomMode = 'fit-width' | 'fit-page' | 'custom';

const ZOOM_LEVELS = [0.5, 0.75, 1, 1.25, 1.5, 2];
// pdfjs-dist 3.x supports JavaScript evaluation for some font programs. The
// review viewer never needs it; keep untrusted certificate PDFs on the
// non-eval interpreter path until react-pdf's major upgrade is scheduled.
const PDF_OPTIONS = { isEvalSupported: false };
const DEFAULT_COLORS: Record<string, string> = {
  certificate_holder_name: '#3b82f6',
  certificate_type: '#8b5cf6',
  certificate_number: '#06b6d4',
  issuing_authority: '#10b981',
  issue_date: '#f59e0b',
  expiration_date: '#ef4444',
  training_hours: '#ec4899',
  license_class: '#6366f1',
  endorsements: '#14b8a6',
};

export const DocumentViewer: React.FC<DocumentViewerProps> = ({
  documentUrl,
  documentData,
  highlights = [],
  activeFieldName,
  onHighlightClick,
  onPageChange,
  onLoadStateChange,
}) => {
  const [numPages, setNumPages] = useState<number>(0);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [zoomMode, setZoomMode] = useState<ZoomMode>('fit-page');
  const [zoomLevel, setZoomLevel] = useState<number>(1);
  const [containerWidth, setContainerWidth] = useState<number>(600);
  const [containerHeight, setContainerHeight] = useState<number>(800);
  const [pageAspectRatio, setPageAspectRatio] = useState<number | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const pageRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setNumPages(0);
    setCurrentPage(1);
    setLoading(true);
    setError(null);
    onLoadStateChange?.('loading');
  }, [documentUrl, documentData, onLoadStateChange]);

  // Measure container dimensions
  useEffect(() => {
    const updateDimensions = () => {
      const contentEl = contentRef.current;
      if (contentEl) {
        setContainerWidth(contentEl.clientWidth - 32);
        setContainerHeight(contentEl.clientHeight - 32);
      }
    };

    updateDimensions();
    window.addEventListener('resize', updateDimensions);
    return () => window.removeEventListener('resize', updateDimensions);
  }, []);

  const onDocumentLoadSuccess = useCallback(({ numPages }: { numPages: number }) => {
    setNumPages(numPages);
    setLoading(false);
    setError(null);
    onLoadStateChange?.('ready');
  }, [onLoadStateChange]);

  const onDocumentLoadError = useCallback((error: Error) => {
    setError(`Failed to load document: ${error.message}`);
    setLoading(false);
    onLoadStateChange?.('error');
  }, [onLoadStateChange]);

  const onPageLoadSuccess = useCallback((page: { width: number; height: number; originalWidth: number; originalHeight: number }) => {
    if (page.originalWidth && page.originalHeight) {
      setPageAspectRatio(page.originalWidth / page.originalHeight);
    } else if (page.width && page.height) {
      setPageAspectRatio(page.width / page.height);
    }
  }, []);

  const goToPage = useCallback((page: number) => {
    const newPage = Math.max(1, Math.min(page, numPages));
    setCurrentPage(newPage);
    onPageChange?.(newPage);
  }, [numPages, onPageChange]);

  const handlePageInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const page = parseInt(e.target.value, 10);
    if (!isNaN(page)) {
      goToPage(page);
    }
  };

  const handleZoomIn = () => {
    const currentIndex = ZOOM_LEVELS.findIndex(z => z >= zoomLevel);
    if (currentIndex < ZOOM_LEVELS.length - 1) {
      setZoomLevel(ZOOM_LEVELS[currentIndex + 1]);
      setZoomMode('custom');
    }
  };

  const handleZoomOut = () => {
    const currentIndex = ZOOM_LEVELS.findIndex(z => z >= zoomLevel);
    if (currentIndex > 0) {
      setZoomLevel(ZOOM_LEVELS[currentIndex - 1]);
      setZoomMode('custom');
    }
  };

  const handleZoomModeChange = (mode: ZoomMode) => {
    setZoomMode(mode);
    if (mode === 'custom') {
      setZoomLevel(1);
    }
  };

  // Calculate page width based on zoom mode
  const getPageWidth = (): number => {
    switch (zoomMode) {
      case 'fit-width':
        return containerWidth;
      case 'fit-page': {
        if (!pageAspectRatio) return containerWidth; // Fallback before page loads
        // Width that makes the page fit within both container width and height
        const widthFromHeight = containerHeight * pageAspectRatio;
        return Math.min(containerWidth, widthFromHeight);
      }
      case 'custom':
        return containerWidth * zoomLevel;
    }
  };

  // Get highlights for the current page
  const currentPageHighlights = highlights.filter(h => h.page === currentPage);

  // Navigate to page when activeFieldName changes
  useEffect(() => {
    if (activeFieldName) {
      const highlight = highlights.find(h => h.fieldName === activeFieldName);
      if (highlight && highlight.page !== currentPage) {
        goToPage(highlight.page);
      }
    }
  }, [activeFieldName, highlights, currentPage, goToPage]);

  const handleHighlightClick = (fieldName: string) => {
    onHighlightClick?.(fieldName);
  };

  const getHighlightColor = (highlight: BoundingBoxHighlight): string => {
    if (highlight.color) return highlight.color;
    return DEFAULT_COLORS[highlight.fieldName] || '#3b82f6';
  };

  const pageWidth = getPageWidth();

  return (
    <div className="document-viewer" ref={containerRef}>
      {/* Toolbar */}
      <div className="document-viewer__toolbar">
        <div className="document-viewer__nav">
          <button
            onClick={() => goToPage(currentPage - 1)}
            disabled={currentPage <= 1}
            className="document-viewer__btn"
            title="Previous page"
          >
            &larr;
          </button>
          <span className="document-viewer__page-info">
            <input
              type="number"
              value={currentPage}
              onChange={handlePageInputChange}
              min={1}
              max={numPages}
              className="document-viewer__page-input"
              aria-label="Page number"
            />
            <span>/ {numPages}</span>
          </span>
          <button
            onClick={() => goToPage(currentPage + 1)}
            disabled={currentPage >= numPages}
            className="document-viewer__btn"
            title="Next page"
          >
            &rarr;
          </button>
        </div>

        <div className="document-viewer__zoom">
          <button
            onClick={handleZoomOut}
            className="document-viewer__btn"
            title="Zoom out"
          >
            -
          </button>
          <select
            value={zoomMode}
            onChange={(e) => handleZoomModeChange(e.target.value as ZoomMode)}
            className="document-viewer__zoom-select"
            aria-label="Zoom level"
          >
            <option value="fit-width">Fit Width</option>
            <option value="fit-page">Fit Page</option>
            <option value="custom">{Math.round(zoomLevel * 100)}%</option>
          </select>
          <button
            onClick={handleZoomIn}
            className="document-viewer__btn"
            title="Zoom in"
          >
            +
          </button>
        </div>
      </div>

      {/* Document content */}
      <div className="document-viewer__content" ref={contentRef}>
        {loading && (
          <div className="document-viewer__loading">Loading document...</div>
        )}

        {error && (
          <div className="document-viewer__error">{error}</div>
        )}

        <Document
          file={documentData ? { data: documentData.slice() } : documentUrl}
          options={PDF_OPTIONS}
          onLoadSuccess={onDocumentLoadSuccess}
          onLoadError={onDocumentLoadError}
          loading=""
        >
          <div className="document-viewer__page-container" ref={pageRef}>
            <Page
              pageNumber={currentPage}
              width={pageWidth}
              onLoadSuccess={onPageLoadSuccess}
              renderTextLayer={true}
              renderAnnotationLayer={true}
            />

            {/* Bounding box overlay */}
            <svg
              className="document-viewer__overlay"
              style={{
                width: pageWidth,
                height: pageAspectRatio ? pageWidth / pageAspectRatio : 'auto',
              }}
              viewBox={`0 0 1 1`}
              preserveAspectRatio="none"
            >
              {currentPageHighlights.map((highlight) => {
                const [x1, y1, x2, y2] = highlight.bbox;
                const isActive = activeFieldName === highlight.fieldName;
                const color = getHighlightColor(highlight);

                return (
                  <g key={highlight.fieldName}>
                    <rect
                      x={x1}
                      y={y1}
                      width={x2 - x1}
                      height={y2 - y1}
                      fill={color}
                      fillOpacity={isActive ? 0.3 : 0.15}
                      stroke={color}
                      strokeWidth={isActive ? 0.004 : 0.002}
                      className="document-viewer__highlight"
                      onClick={() => handleHighlightClick(highlight.fieldName)}
                      style={{ cursor: 'pointer' }}
                    />
                    {isActive && (
                      <text
                        x={x1}
                        y={y1 - 0.01}
                        fontSize="0.02"
                        fill={color}
                        className="document-viewer__highlight-label"
                      >
                        {highlight.fieldName.replace(/_/g, ' ')}
                      </text>
                    )}
                  </g>
                );
              })}
            </svg>
          </div>
        </Document>
      </div>

      {/* Highlight legend */}
      {highlights.length > 0 && (
        <div className="document-viewer__legend">
          {[...new Set(highlights.map(h => h.fieldName))].map((fieldName) => {
            const highlight = highlights.find(h => h.fieldName === fieldName);
            const color = highlight ? getHighlightColor(highlight) : '#3b82f6';
            const isActive = activeFieldName === fieldName;

            return (
              <button
                key={fieldName}
                className={`document-viewer__legend-item ${isActive ? 'active' : ''}`}
                onClick={() => handleHighlightClick(fieldName)}
                style={{ borderColor: color }}
              >
                <span
                  className="document-viewer__legend-color"
                  style={{ backgroundColor: color }}
                />
                <span className="document-viewer__legend-label">
                  {fieldName.replace(/_/g, ' ')}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default DocumentViewer;
