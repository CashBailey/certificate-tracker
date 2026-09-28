/**
 * Upload page - Upload certificate documents with drag-and-drop.
 */

import React, { useState, useCallback, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Header } from '../components/Header';
import { uploadDocument, getEmployee } from '../api';
import './UploadPage.css';

export function UploadPage() {
  const [searchParams] = useSearchParams();
  // Guard against non-numeric and non-integer employee_id values (e.g.
  // ?employee_id=abc, ?employee_id=1.5, ?employee_id=-5, ?employee_id=).
  // Number("") === 0 is finite; Number("1.5") === 1.5 is also finite.
  // Only positive integers are valid employee ids.
  const rawEmployeeId = searchParams.get('employee_id');
  const parsedEmployeeId = rawEmployeeId !== null && rawEmployeeId !== '' ? Number(rawEmployeeId) : NaN;
  const employeeId = Number.isInteger(parsedEmployeeId) && parsedEmployeeId > 0 ? parsedEmployeeId : undefined;
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<{ documentId: number; extractionId: number } | null>(null);
  const [employeeLabel, setEmployeeLabel] = useState<string | null>(null);

  // Look up the employee name so the Coordinator sees who they're uploading for.
  // If the lookup fails (employee deleted/inactive), we still let the upload
  // attempt — the backend will reject if the id is invalid.
  useEffect(() => {
    if (employeeId === undefined) {
      setEmployeeLabel(null);
      return;
    }
    let cancelled = false;
    getEmployee(employeeId)
      .then(emp => {
        if (!cancelled) {
          setEmployeeLabel(`${emp.first_name} ${emp.last_name} (${emp.employee_number})`);
        }
      })
      .catch(() => {
        if (!cancelled) setEmployeeLabel(`Employee #${employeeId}`);
      });
    return () => { cancelled = true; };
  }, [employeeId]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      validateAndSetFile(droppedFile);
    }
  }, []);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      validateAndSetFile(selectedFile);
    }
  }, []);

  const validateAndSetFile = (file: File) => {
    setError(null);

    // Validate file type
    const allowedTypes = ['application/pdf', 'image/jpeg', 'image/png', 'image/tiff'];
    if (!allowedTypes.includes(file.type)) {
      setError('Invalid file type. Please upload a PDF, JPEG, PNG, or TIFF file.');
      return;
    }

    // Validate file size (max 20MB)
    const maxSize = 20 * 1024 * 1024;
    if (file.size > maxSize) {
      setError('File is too large. Maximum size is 20MB.');
      return;
    }

    setFile(file);
  };

  const handleUpload = async () => {
    if (!file) return;

    setUploading(true);
    setError(null);

    try {
      const result = await uploadDocument(file, employeeId);
      setSuccess({
        documentId: result.document_id,
        extractionId: result.extraction_id,
      });
      setFile(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="upload-page">
      <Header
        title="Upload Certificate"
        showBackLink
        backTo="/"
        backLabel="Dashboard"
      />

      <main className="page-main">
        {success ? (
          <div className="success-card">
            <div className="success-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </div>
            <h2>Upload Successful!</h2>
            <p>Your document has been uploaded and is being processed.</p>
            <div className="success-details">
              <div className="success-detail-row">
                <span className="detail-label">Document ID:</span>
                <span className="detail-value">{success.documentId}</span>
              </div>
              <div className="success-detail-row">
                <span className="detail-label">Extraction ID:</span>
                <span className="detail-value">{success.extractionId}</span>
              </div>
            </div>
            <div className="success-actions">
              <button onClick={() => setSuccess(null)} className="btn btn--secondary">
                Upload Another
              </button>
              <Link to="/review" className="btn btn--primary">
                Review Queue
              </Link>
            </div>
          </div>
        ) : employeeId === undefined ? (
          <div className="upload-card">
            <div className="empty-state">
              <h2>Pick an employee first</h2>
              <p>
                Certificate uploads must be attributed to a specific employee.
                Open the <Link to="/requirements">Requirements page</Link> and use the per-row <strong>Upload</strong> action,
                or open <Link to="/employees">Employees</Link> to find the right person.
              </p>
            </div>
          </div>
        ) : (
          <div className="upload-card">
            {employeeLabel && (
              <div className="upload-target-banner">
                Uploading certificate for: <strong>{employeeLabel}</strong>
              </div>
            )}
            <div
              className={`drop-zone ${isDragging ? 'drop-zone--active' : ''} ${file ? 'drop-zone--has-file' : ''}`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              {file ? (
                <div className="file-preview">
                  <div className="file-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <polyline points="14 2 14 8 20 8" />
                    </svg>
                  </div>
                  <div className="file-info">
                    <span className="file-name">{file.name}</span>
                    <span className="file-size">{formatFileSize(file.size)}</span>
                  </div>
                  <button
                    onClick={() => setFile(null)}
                    className="remove-file"
                    type="button"
                    aria-label="Remove file"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <line x1="18" y1="6" x2="6" y2="18" />
                      <line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                </div>
              ) : (
                <>
                  <div className="drop-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="17 8 12 3 7 8" />
                      <line x1="12" y1="3" x2="12" y2="15" />
                    </svg>
                  </div>
                  <p className="drop-text">
                    Drag and drop your certificate here, or{' '}
                    <label className="browse-link">
                      browse
                      <input
                        type="file"
                        onChange={handleFileSelect}
                        accept=".pdf,.jpg,.jpeg,.png,.tiff,.tif"
                        hidden
                      />
                    </label>
                  </p>
                  <p className="drop-hint">
                    Supported formats: PDF, JPEG, PNG, TIFF (max 20MB)
                  </p>
                </>
              )}
            </div>

            {error && <div className="error-message">{error}</div>}

            <button
              onClick={handleUpload}
              disabled={!file || uploading}
              className="btn btn--primary btn--large btn--full upload-button"
            >
              {uploading ? 'Uploading...' : 'Upload Document'}
            </button>
          </div>
        )}
      </main>
    </div>
  );
}

export default UploadPage;
