/**
 * FieldEditor component for reviewing and correcting extracted fields.
 *
 * Fields are always editable — no edit/confirm toggle. The reviewer corrects
 * values by typing directly into the input. Per INV-05, confidence scores are
 * not displayed; the reviewer relies on the document preview, bounding box
 * highlights, and candidate values.
 */

import type { FC } from 'react';
import './FieldEditor.css';

interface FieldEditorProps {
  fieldName: string;
  value: string;
  candidates?: Array<{ value: string }>;
  onChange: (value: string) => void;
  error?: string;
  readOnly?: boolean;
  required?: boolean;
}

const FIELD_LABELS: Record<string, string> = {
  certificate_holder_name: 'Certificate Holder Name',
  certificate_type: 'Certificate Type',
  certificate_number: 'Certificate Number',
  issuing_authority: 'Issuing Authority',
  issue_date: 'Issue Date',
  expiration_date: 'Expiration Date',
  training_hours: 'Training Hours',
  license_class: 'License Class',
  endorsements: 'Endorsements',
};

export const FieldEditor: FC<FieldEditorProps> = ({
  fieldName,
  value,
  candidates,
  onChange,
  error,
  readOnly = false,
  required = false,
}) => {
  const errorId = `field-error-${fieldName}`;
  const inputType = fieldName === 'issue_date' || fieldName === 'expiration_date'
    ? 'date'
    : 'text';

  return (
    <div className={`field-editor ${error ? 'field-editor--error' : ''}`}>
      <div className="field-editor__header">
        <label className="field-editor__label" htmlFor={`field-input-${fieldName}`}>
          {FIELD_LABELS[fieldName] || fieldName}
        </label>
      </div>

      <input
        id={`field-input-${fieldName}`}
        type={inputType}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="field-editor__input"
        placeholder="No value extracted"
        readOnly={readOnly}
        required={required}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? errorId : undefined}
      />

      {error && (
        <span id={errorId} className="field-editor__error" role="alert">
          {error}
        </span>
      )}

      {!readOnly && candidates && candidates.length > 1 && (
        <div className="field-editor__candidates">
          <span className="field-editor__candidates-label">Alternatives:</span>
          {candidates.slice(1, 4).map((c, i) => (
            <button
              key={i}
              type="button"
              onClick={() => onChange(c.value)}
              className="field-editor__candidate"
            >
              {c.value}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default FieldEditor;
