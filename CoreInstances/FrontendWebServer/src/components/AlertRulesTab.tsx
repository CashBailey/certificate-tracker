/**
 * AlertRulesTab — Manage notification reminder day-offsets, daily-overdue toggle,
 * and send time. Lives inside ConfigurationPage's "Alert Rules" tab.
 *
 * Backend contract (GET/PUT /api/alert-config):
 *   requirement_reminder_days: number[]   (sorted desc, 1-365)
 *   certificate_reminder_days: number[]   (sorted desc, 1-365)
 *   daily_overdue_enabled: boolean
 *   global_send_hour: number              (0-23)
 *   global_send_minute: number            (0-59)
 */

import { useState, useEffect, useCallback } from 'react';
import { getAlertConfig, updateAlertConfig, AlertConfig } from '../api';
import './AlertRulesTab.css';

function arraysEqual(a: number[], b: number[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

function toTimeString(hour: number, minute: number): string {
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

function parseTimeString(time: string): { hour: number; minute: number } {
  const [h, m] = time.split(':').map(Number);
  return { hour: h || 0, minute: m || 0 };
}

export function AlertRulesTab() {
  const [config, setConfig] = useState<AlertConfig | null>(null);
  const [serverConfig, setServerConfig] = useState<AlertConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveResult, setSaveResult] = useState<'success' | 'error' | null>(null);

  const [newRequirementDay, setNewRequirementDay] = useState('');
  const [newCertificateDay, setNewCertificateDay] = useState('');
  const [requirementDayError, setRequirementDayError] = useState<string | null>(null);
  const [certificateDayError, setCertificateDayError] = useState<string | null>(null);

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    setError(null);
    setConfig(null);
    setServerConfig(null);
    try {
      const data = await getAlertConfig();
      setConfig(data);
      setServerConfig(data);
    } catch {
      setError('Failed to load alert configuration.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchConfig(); }, [fetchConfig]);

  const isDirty = Boolean(config && serverConfig && (
    !arraysEqual(config.requirement_reminder_days, serverConfig.requirement_reminder_days) ||
    !arraysEqual(config.certificate_reminder_days, serverConfig.certificate_reminder_days) ||
    config.daily_overdue_enabled !== serverConfig.daily_overdue_enabled ||
    config.global_send_hour !== serverConfig.global_send_hour ||
    config.global_send_minute !== serverConfig.global_send_minute
  ));

  type ReminderField = 'requirement_reminder_days' | 'certificate_reminder_days';

  const handleRemoveDay = (field: ReminderField, day: number) => {
    setConfig(prev => {
      if (!prev || prev[field].length <= 1) return prev;
      return { ...prev, [field]: prev[field].filter((value: number) => value !== day) };
    });
  };

  const handleAddDay = (field: ReminderField, value: string) => {
    const setFieldError = field === 'requirement_reminder_days'
      ? setRequirementDayError
      : setCertificateDayError;
    setFieldError(null);
    const num = parseInt(value, 10);
    if (isNaN(num) || num < 1 || num > 365) {
      setFieldError('Enter a number between 1 and 365.');
      return;
    }
    if (!config || config[field].includes(num)) {
      setFieldError(`${num} is already in the list.`);
      return;
    }
    setConfig(prev => prev && ({
      ...prev,
      [field]: [...prev[field], num].sort((a, b) => b - a),
    }));
    if (field === 'requirement_reminder_days') setNewRequirementDay('');
    else setNewCertificateDay('');
  };

  const handleToggleOverdue = () => {
    setConfig(prev => prev && ({ ...prev, daily_overdue_enabled: !prev.daily_overdue_enabled }));
  };

  const handleSendTimeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { hour, minute } = parseTimeString(e.target.value);
    setConfig(prev => prev && ({ ...prev, global_send_hour: hour, global_send_minute: minute }));
  };

  const handleSave = async () => {
    if (!config || !serverConfig || config.requirement_reminder_days.length === 0 || config.certificate_reminder_days.length === 0) {
      setSaveResult('error');
      return;
    }
    setSaving(true);
    setSaveResult(null);
    try {
      const updated = await updateAlertConfig({
        requirement_reminder_days: config.requirement_reminder_days,
        certificate_reminder_days: config.certificate_reminder_days,
        daily_overdue_enabled: config.daily_overdue_enabled,
        global_send_hour: config.global_send_hour,
        global_send_minute: config.global_send_minute,
      });
      setConfig(updated);
      setServerConfig(updated);
      setSaveResult('success');
    } catch {
      setSaveResult('error');
    } finally {
      setSaving(false);
      setTimeout(() => setSaveResult(null), 3000);
    }
  };

  const handleReset = () => {
    if (!serverConfig) return;
    setConfig({ ...serverConfig });
    setRequirementDayError(null);
    setCertificateDayError(null);
    setSaveResult(null);
  };

  if (loading) return <div className="alert-rules-loading">Loading alert configuration...</div>;

  if (!config || !serverConfig) {
    return (
      <div className="alert-rules-error" role="alert">
        {error || 'Alert configuration is unavailable.'}
        <button type="button" className="alert-rules-retry-btn" onClick={fetchConfig}>Retry</button>
      </div>
    );
  }

  const reminderEditor = (
    field: ReminderField,
    title: string,
    description: string,
    newDay: string,
    setNewDay: (value: string) => void,
    fieldError: string | null,
    clearFieldError: () => void,
  ) => (
    <section className="alert-rules-section">
      <h3 className="alert-rules-section-title">{title}</h3>
      <p className="alert-rules-section-desc">{description}</p>
      <div className="alert-rules-chip-list">
        {config[field].map((day: number) => (
          <span key={day} className="alert-rules-chip">
            {day}d
            <button
              type="button"
              className="alert-rules-chip-remove"
              onClick={() => handleRemoveDay(field, day)}
              aria-label={`Remove ${day}-day ${title.toLowerCase()}`}
              disabled={config[field].length <= 1 || saving}
            >
              x
            </button>
          </span>
        ))}
      </div>
      <div className="alert-rules-add-row">
        <input
          type="number"
          className="alert-rules-add-input"
          placeholder="Days (1-365)"
          min={1}
          max={365}
          value={newDay}
          onChange={event => { setNewDay(event.target.value); clearFieldError(); }}
          onKeyDown={event => {
            if (event.key === 'Enter') {
              event.preventDefault();
              handleAddDay(field, newDay);
            }
          }}
          aria-label={`New ${title.toLowerCase()}`}
          aria-invalid={Boolean(fieldError)}
          disabled={saving}
        />
        <button type="button" className="alert-rules-add-btn" onClick={() => handleAddDay(field, newDay)} disabled={saving}>Add</button>
      </div>
      {fieldError && <p className="alert-rules-field-error" role="alert">{fieldError}</p>}
    </section>
  );

  return (
    <div className="alert-rules-tab">
      {reminderEditor(
        'requirement_reminder_days',
        'Requirement due-date reminder',
        'Notifications sent this many days before a requirement due date.',
        newRequirementDay,
        setNewRequirementDay,
        requirementDayError,
        () => setRequirementDayError(null),
      )}

      {reminderEditor(
        'certificate_reminder_days',
        'Certificate expiration reminder',
        'Notifications sent this many days before a certificate expiration date.',
        newCertificateDay,
        setNewCertificateDay,
        certificateDayError,
        () => setCertificateDayError(null),
      )}

      <section className="alert-rules-section">
        <h3 className="alert-rules-section-title">Daily Overdue Reminders</h3>
        <div className="alert-rules-toggle-row">
          <span className="alert-rules-toggle-label">Send daily reminders for overdue items</span>
          <button className={`alert-rules-toggle${config.daily_overdue_enabled ? ' alert-rules-toggle--on' : ''}`}
            type="button" role="switch" aria-checked={config.daily_overdue_enabled} onClick={handleToggleOverdue} disabled={saving}>
            <span className="alert-rules-toggle-knob" />
          </button>
        </div>
      </section>

      <section className="alert-rules-section">
        <h3 className="alert-rules-section-title">Daily Send Time</h3>
        <p className="alert-rules-section-desc">Notifications are generated and queued at this time each day.</p>
        <div className="alert-rules-time-row">
          <input type="time" className="alert-rules-time-input"
            value={toTimeString(config.global_send_hour, config.global_send_minute)}
            onChange={handleSendTimeChange} aria-label="Notification send time" disabled={saving} />
          <span className="alert-rules-time-hint">Server local time (CT)</span>
        </div>
      </section>

      <div className="alert-rules-footer">
        <button type="button" className="alert-rules-save-btn" onClick={handleSave} disabled={!isDirty || saving}>
          {saving ? 'Saving...' : 'Save Changes'}
        </button>
        <button type="button" className="alert-rules-reset-btn" onClick={handleReset} disabled={!isDirty || saving}>Reset</button>
        {saveResult === 'success' && <span className="alert-rules-save-msg alert-rules-save-msg--success" role="status">Configuration saved.</span>}
        {saveResult === 'error' && <span className="alert-rules-save-msg alert-rules-save-msg--error" role="alert">Failed to save. Please try again.</span>}
      </div>
    </div>
  );
}

export default AlertRulesTab;
