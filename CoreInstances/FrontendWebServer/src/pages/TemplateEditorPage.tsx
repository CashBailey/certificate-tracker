/**
 * Template Editor Page - Visual zone annotator for defining template fields.
 *
 * Dr. Morgan uploads a sample document image, draws rectangles over each field,
 * assigns canonical field names, configures parsing/validation, and saves the
 * template to the registry.
 *
 * Features:
 *  - Drag to draw rectangles on the image
 *  - Click to select, drag to move, corner handles to resize
 *  - Undo/Redo (Ctrl+Z / Ctrl+Y)
 *  - Normalize/align zones (N key)
 *  - Per-field color coding
 *  - Saves directly to the Template Registry via API
 */

import { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '../components/Header';
import { createTemplate } from '../api';
import './TemplateEditorPage.css';

// ============================================================
// Constants
// ============================================================

const CANONICAL_FIELDS = [
  'certificate_holder_name',
  'certificate_type',
  'issuing_authority',
  'issue_date',
] as const;

const FIELD_LABELS: Record<string, string> = {
  certificate_holder_name: 'Certificate Holder Name',
  certificate_type: 'Certificate Type',
  issuing_authority: 'Issuing Authority',
  issue_date: 'Issue Date',
};

const FIELD_COLORS: Record<string, string> = {
  certificate_holder_name: '#3b82f6',
  certificate_type: '#22c55e',
  issuing_authority: '#ef4444',
  issue_date: '#8b5cf6',
};

const MIN_ZONE_SIZE = 0.01; // normalized

// ============================================================
// Types
// ============================================================

interface Zone {
  id: number;
  fieldName: string;
  bbox: [number, number, number, number]; // [x0, y0, x1, y1] normalized 0-1
  alwaysReview: boolean;
  hardcodedValue: string;
  regexPattern: string;
  dateFormat: string;
  allowMultiline: boolean;
  minLength: number;
  maxLength: number;
}

type Tool = 'select' | 'rect';
type DragMode = 'draw' | 'move' | 'resize' | null;
type HandleName = 'nw' | 'ne' | 'se' | 'sw';

interface UndoState {
  zones: Zone[];
  nextId: number;
}

// ============================================================
// Component
// ============================================================

export function TemplateEditorPage() {
  const navigate = useNavigate();

  // Image state
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [imageSize, setImageSize] = useState({ w: 0, h: 0 });
  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);

  // Tool state
  const [tool, setTool] = useState<Tool>('rect');
  const [selectedField, setSelectedField] = useState<string>(CANONICAL_FIELDS[0]);

  // Zones
  const [zones, setZones] = useState<Zone[]>([]);
  const [nextId, setNextId] = useState(1);
  const [selectedZoneId, setSelectedZoneId] = useState<number | null>(null);

  // Drag state
  const dragRef = useRef<{
    mode: DragMode;
    startNorm: [number, number];
    startBbox: [number, number, number, number];
    zoneId: number | null;
    handle: HandleName | null;
  }>({
    mode: null,
    startNorm: [0, 0],
    startBbox: [0, 0, 0, 0],
    zoneId: null,
    handle: null,
  });

  // Drawing temp rect
  const [tempRect, setTempRect] = useState<[number, number, number, number] | null>(null);

  // Undo/Redo
  const [undoStack, setUndoStack] = useState<UndoState[]>([]);
  const [redoStack, setRedoStack] = useState<UndoState[]>([]);

  // Template metadata
  const [templateId, setTemplateId] = useState('');
  const [templateName, setTemplateName] = useState('');
  const [templateVersion, setTemplateVersion] = useState(1);
  const [templateDesc, setTemplateDesc] = useState('');

  // Display options
  const [showLabels, setShowLabels] = useState(true);
  const [showFill, setShowFill] = useState(true);

  // Status
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState('Upload an image to begin defining template zones.');

  // --------------------------------------------------------
  // Undo/Redo helpers
  // --------------------------------------------------------

  const saveForUndo = useCallback(() => {
    setUndoStack(prev => [...prev.slice(-49), { zones: zones.map(z => ({ ...z })), nextId }]);
    setRedoStack([]);
  }, [zones, nextId]);

  const doUndo = useCallback(() => {
    if (undoStack.length === 0) return;
    const prev = undoStack[undoStack.length - 1];
    setRedoStack(rs => [...rs, { zones: zones.map(z => ({ ...z })), nextId }]);
    setUndoStack(us => us.slice(0, -1));
    setZones(prev.zones);
    setNextId(prev.nextId);
    setSelectedZoneId(null);
    setStatusMsg('Undo');
  }, [undoStack, zones, nextId]);

  const doRedo = useCallback(() => {
    if (redoStack.length === 0) return;
    const next = redoStack[redoStack.length - 1];
    setUndoStack(us => [...us, { zones: zones.map(z => ({ ...z })), nextId }]);
    setRedoStack(rs => rs.slice(0, -1));
    setZones(next.zones);
    setNextId(next.nextId);
    setSelectedZoneId(null);
    setStatusMsg('Redo');
  }, [redoStack, zones, nextId]);

  // --------------------------------------------------------
  // Coordinate helpers
  // --------------------------------------------------------

  const clientToNorm = useCallback((clientX: number, clientY: number): [number, number] => {
    const svg = containerRef.current?.querySelector('.zone-overlay') as SVGSVGElement | null;
    if (!svg) return [0, 0];
    const rect = svg.getBoundingClientRect();
    const x = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (clientY - rect.top) / rect.height));
    return [x, y];
  }, []);

  // --------------------------------------------------------
  // Image handling
  // --------------------------------------------------------

  const handleImageUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (ev) => {
      const src = ev.target?.result as string;
      setImageSrc(src);

      const img = new Image();
      img.onload = () => {
        setImageSize({ w: img.naturalWidth, h: img.naturalHeight });
        setStatusMsg(`Loaded: ${file.name} (${img.naturalWidth}x${img.naturalHeight}). Select Rectangle tool and draw zones.`);
      };
      img.src = src;

      // Reset zones
      setZones([]);
      setNextId(1);
      setSelectedZoneId(null);
      setUndoStack([]);
      setRedoStack([]);
    };
    reader.readAsDataURL(file);
  }, []);

  // --------------------------------------------------------
  // Hit testing
  // --------------------------------------------------------

  const hitHandle = useCallback((nx: number, ny: number): { zoneId: number; handle: HandleName } | null => {
    if (selectedZoneId === null) return null;
    const zone = zones.find(z => z.id === selectedZoneId);
    if (!zone) return null;

    const [x0, y0, x1, y1] = zone.bbox;
    const tol = 0.015;
    const handles: [HandleName, number, number][] = [
      ['nw', x0, y0], ['ne', x1, y0], ['se', x1, y1], ['sw', x0, y1],
    ];
    for (const [name, hx, hy] of handles) {
      if (Math.abs(nx - hx) < tol && Math.abs(ny - hy) < tol) {
        return { zoneId: selectedZoneId, handle: name };
      }
    }
    return null;
  }, [selectedZoneId, zones]);

  const hitZone = useCallback((nx: number, ny: number): number | null => {
    for (let i = zones.length - 1; i >= 0; i--) {
      const [x0, y0, x1, y1] = zones[i].bbox;
      if (nx >= x0 && nx <= x1 && ny >= y0 && ny <= y1) {
        return zones[i].id;
      }
    }
    return null;
  }, [zones]);

  // --------------------------------------------------------
  // Mouse handlers
  // --------------------------------------------------------

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (!imageSrc || e.button !== 0) return;
    e.preventDefault();

    const [nx, ny] = clientToNorm(e.clientX, e.clientY);

    // Check handle hit first
    const handleHit = hitHandle(nx, ny);
    if (handleHit) {
      const zone = zones.find(z => z.id === handleHit.zoneId)!;
      saveForUndo();
      dragRef.current = {
        mode: 'resize',
        startNorm: [nx, ny],
        startBbox: [...zone.bbox],
        zoneId: handleHit.zoneId,
        handle: handleHit.handle,
      };
      return;
    }

    // Check zone hit
    const zoneId = hitZone(nx, ny);
    if (zoneId !== null) {
      setSelectedZoneId(zoneId);
      const zone = zones.find(z => z.id === zoneId)!;
      saveForUndo();
      dragRef.current = {
        mode: 'move',
        startNorm: [nx, ny],
        startBbox: [...zone.bbox],
        zoneId,
        handle: null,
      };
      return;
    }

    // Empty space
    if (tool === 'select') {
      setSelectedZoneId(null);
      return;
    }

    // Draw new rect
    setSelectedZoneId(null);
    dragRef.current = {
      mode: 'draw',
      startNorm: [nx, ny],
      startBbox: [0, 0, 0, 0],
      zoneId: null,
      handle: null,
    };
    setTempRect([nx, ny, nx, ny]);
  }, [imageSrc, tool, clientToNorm, hitHandle, hitZone, zones, saveForUndo]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragRef.current.mode) return;
    e.preventDefault();

    const [nx, ny] = clientToNorm(e.clientX, e.clientY);
    const d = dragRef.current;

    if (d.mode === 'draw') {
      setTempRect([
        Math.min(d.startNorm[0], nx),
        Math.min(d.startNorm[1], ny),
        Math.max(d.startNorm[0], nx),
        Math.max(d.startNorm[1], ny),
      ]);
      return;
    }

    if (d.mode === 'move' && d.zoneId !== null) {
      const dx = nx - d.startNorm[0];
      const dy = ny - d.startNorm[1];
      setZones(prev => prev.map(z => {
        if (z.id !== d.zoneId) return z;
        return {
          ...z,
          bbox: [
            d.startBbox[0] + dx,
            d.startBbox[1] + dy,
            d.startBbox[2] + dx,
            d.startBbox[3] + dy,
          ],
        };
      }));
      return;
    }

    if (d.mode === 'resize' && d.zoneId !== null && d.handle) {
      setZones(prev => prev.map(z => {
        if (z.id !== d.zoneId) return z;
        const [ox0, oy0, ox1, oy1] = d.startBbox;
        let x0 = ox0, y0 = oy0, x1 = ox1, y1 = oy1;
        if (d.handle === 'nw') { x0 = nx; y0 = ny; }
        else if (d.handle === 'ne') { x1 = nx; y0 = ny; }
        else if (d.handle === 'se') { x1 = nx; y1 = ny; }
        else if (d.handle === 'sw') { x0 = nx; y1 = ny; }
        return {
          ...z,
          bbox: [Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1)],
        };
      }));
    }
  }, [clientToNorm]);

  const handleMouseUp = useCallback((e: React.MouseEvent) => {
    const d = dragRef.current;
    if (d.mode === 'draw') {
      const [nx, ny] = clientToNorm(e.clientX, e.clientY);
      const x0 = Math.min(d.startNorm[0], nx);
      const y0 = Math.min(d.startNorm[1], ny);
      const x1 = Math.max(d.startNorm[0], nx);
      const y1 = Math.max(d.startNorm[1], ny);

      if ((x1 - x0) >= MIN_ZONE_SIZE && (y1 - y0) >= MIN_ZONE_SIZE) {
        saveForUndo();
        const newZone: Zone = {
          id: nextId,
          fieldName: selectedField,
          bbox: [
            Math.round(x0 * 10000) / 10000,
            Math.round(y0 * 10000) / 10000,
            Math.round(x1 * 10000) / 10000,
            Math.round(y1 * 10000) / 10000,
          ],
          alwaysReview: false,
          hardcodedValue: '',
          regexPattern: '',
          dateFormat: '',
          allowMultiline: false,
          minLength: 0,
          maxLength: 0,
        };
        setZones(prev => [...prev, newZone]);
        setNextId(prev => prev + 1);
        setSelectedZoneId(newZone.id);
        setStatusMsg(`Created zone: ${FIELD_LABELS[selectedField]}`);
      }
      setTempRect(null);
    }

    dragRef.current = { mode: null, startNorm: [0, 0], startBbox: [0, 0, 0, 0], zoneId: null, handle: null };
  }, [clientToNorm, saveForUndo, nextId, selectedField]);

  // --------------------------------------------------------
  // Zone management
  // --------------------------------------------------------

  const deleteSelected = useCallback(() => {
    if (selectedZoneId === null) return;
    saveForUndo();
    setZones(prev => prev.filter(z => z.id !== selectedZoneId));
    setSelectedZoneId(null);
    setStatusMsg('Zone deleted');
  }, [selectedZoneId, saveForUndo]);

  const clearAll = useCallback(() => {
    if (zones.length === 0) return;
    if (!window.confirm('Delete all zones?')) return;
    saveForUndo();
    setZones([]);
    setNextId(1);
    setSelectedZoneId(null);
    setStatusMsg('All zones cleared');
  }, [zones, saveForUndo]);

  const updateSelectedZone = useCallback((updates: Partial<Zone>) => {
    if (selectedZoneId === null) return;
    setZones(prev => prev.map(z => z.id === selectedZoneId ? { ...z, ...updates } : z));
  }, [selectedZoneId]);

  // --------------------------------------------------------
  // Normalize/Align
  // --------------------------------------------------------

  const normalizeZones = useCallback(() => {
    if (zones.length < 2) return;
    saveForUndo();

    const mean = (vals: number[]) => vals.reduce((a, b) => a + b, 0) / vals.length;
    const tol = 0.02;

    // Cluster by left edge
    const sorted = [...zones].sort((a, b) => a.bbox[0] - b.bbox[0]);
    const clusters: Zone[][] = [];
    let cur: Zone[] = [];
    let curVals: number[] = [];

    for (const z of sorted) {
      const v = z.bbox[0];
      if (cur.length === 0) {
        cur = [z]; curVals = [v]; continue;
      }
      if (Math.abs(v - mean(curVals)) <= tol) {
        cur.push(z); curVals.push(v);
      } else {
        clusters.push(cur);
        cur = [z]; curVals = [v];
      }
    }
    if (cur.length > 0) clusters.push(cur);

    const updated = new Map<number, Zone>();
    zones.forEach(z => updated.set(z.id, { ...z }));

    for (const col of clusters) {
      if (col.length < 2) continue;
      const lefts = col.map(z => z.bbox[0]);
      const rights = col.map(z => z.bbox[2]);
      const L = mean(lefts);
      const alignRight = (Math.max(...rights) - Math.min(...rights)) <= tol;

      if (alignRight) {
        const R = mean(rights);
        for (const z of col) {
          const u = updated.get(z.id)!;
          u.bbox = [L, u.bbox[1], R, u.bbox[3]];
        }
      } else {
        for (const z of col) {
          const u = updated.get(z.id)!;
          const dx = L - u.bbox[0];
          u.bbox = [u.bbox[0] + dx, u.bbox[1], u.bbox[2] + dx, u.bbox[3]];
        }
      }
    }

    setZones(Array.from(updated.values()));
    setStatusMsg(`Normalized ${zones.length} zone(s)`);
  }, [zones, saveForUndo]);

  // --------------------------------------------------------
  // Keyboard shortcuts
  // --------------------------------------------------------

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't capture when typing in inputs
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

      if (e.key === 'v' || e.key === 'V') { setTool('select'); return; }
      if (e.key === 'r' || e.key === 'R') { setTool('rect'); return; }
      if (e.key === 'Delete' || e.key === 'Backspace') { deleteSelected(); return; }
      if (e.key === 'n' || e.key === 'N') { normalizeZones(); return; }
      if (e.ctrlKey && e.key === 'z') { e.preventDefault(); doUndo(); return; }
      if (e.ctrlKey && e.key === 'y') { e.preventDefault(); doRedo(); return; }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [deleteSelected, normalizeZones, doUndo, doRedo]);

  // --------------------------------------------------------
  // Save template
  // --------------------------------------------------------

  const handleSave = async () => {
    if (!templateId.trim()) {
      setStatusMsg('Error: Template ID is required');
      return;
    }
    if (!templateName.trim()) {
      setStatusMsg('Error: Template Name is required');
      return;
    }
    if (zones.length === 0) {
      setStatusMsg('Error: At least one zone must be defined');
      return;
    }
    if (!/^[a-z0-9_]+$/.test(templateId)) {
      setStatusMsg('Error: Template ID must be lowercase letters, numbers, and underscores only');
      return;
    }

    setSaving(true);
    setStatusMsg('Saving template...');

    try {
      const now = new Date().toISOString();

      await createTemplate({
        template_id: templateId,
        version: templateVersion,
        name: templateName,
        description: templateDesc || undefined,
        min_keyword_matches: 2,
        zones: zones.map(z => ({
          field_name: z.fieldName,
          bbox_norm: z.bbox,
          required: true,
          hardcoded_value: z.hardcodedValue || undefined,
          regex_pattern: z.regexPattern || undefined,
          date_format: z.dateFormat || undefined,
          allow_multiline: z.allowMultiline,
          min_length: z.minLength || undefined,
          max_length: z.maxLength || undefined,
        })),
        always_review_fields: zones.filter(z => z.alwaysReview).map(z => z.fieldName),
        created_at: now,
        updated_at: now,
      });

      setStatusMsg(`Template "${templateName}" saved successfully!`);
      setTimeout(() => navigate('/templates'), 1500);
    } catch (err) {
      setStatusMsg(`Error: ${err instanceof Error ? err.message : 'Failed to save template'}`);
    } finally {
      setSaving(false);
    }
  };

  // --------------------------------------------------------
  // Selected zone for properties panel
  // --------------------------------------------------------

  const selectedZone = useMemo(() => {
    return zones.find(z => z.id === selectedZoneId) ?? null;
  }, [zones, selectedZoneId]);

  // --------------------------------------------------------
  // Render
  // --------------------------------------------------------

  return (
    <div className="template-editor-page">
      <Header
        title="New Template"
        showBackLink
        backTo="/templates"
        backLabel="Templates"
      />

      <main className="editor-layout">
        {/* Left panel */}
        <div className="editor-panel">
          <div className="editor-panel__scroll">
            {/* Tools */}
            <section className="panel-section">
              <h3 className="panel-section__title">Tools</h3>
              <div className="tool-buttons">
                <button
                  className={`tool-btn ${tool === 'select' ? 'tool-btn--active' : ''}`}
                  onClick={() => setTool('select')}
                >
                  Select/Move (V)
                </button>
                <button
                  className={`tool-btn ${tool === 'rect' ? 'tool-btn--active' : ''}`}
                  onClick={() => setTool('rect')}
                >
                  Rectangle (R)
                </button>
              </div>
            </section>

            {/* Field to assign */}
            <section className="panel-section">
              <h3 className="panel-section__title">Field for New Zone</h3>
              <select
                className="panel-select"
                value={selectedField}
                onChange={e => setSelectedField(e.target.value)}
              >
                {CANONICAL_FIELDS.map(f => (
                  <option key={f} value={f}>{FIELD_LABELS[f]}</option>
                ))}
              </select>
              <div
                className="field-color-preview"
                style={{ backgroundColor: FIELD_COLORS[selectedField] }}
              />
            </section>

            {/* Template Info */}
            <section className="panel-section">
              <h3 className="panel-section__title">Template Info</h3>
              <label className="panel-label">
                ID <span className="panel-hint">(lowercase, underscores)</span>
                <input
                  className="panel-input"
                  value={templateId}
                  onChange={e => setTemplateId(e.target.value)}
                  placeholder="e.g. lms_certificate"
                />
              </label>
              <label className="panel-label">
                Name
                <input
                  className="panel-input"
                  value={templateName}
                  onChange={e => setTemplateName(e.target.value)}
                  placeholder="e.g. LMS Certificate"
                />
              </label>
              <label className="panel-label">
                Version
                <input
                  type="number"
                  className="panel-input panel-input--short"
                  value={templateVersion}
                  min={1}
                  onChange={e => setTemplateVersion(parseInt(e.target.value) || 1)}
                />
              </label>
              <label className="panel-label">
                Description
                <input
                  className="panel-input"
                  value={templateDesc}
                  onChange={e => setTemplateDesc(e.target.value)}
                  placeholder="Template description..."
                />
              </label>
            </section>

            {/* Zone Properties (selected zone) */}
            {selectedZone && (
              <section className="panel-section panel-section--highlight">
                <h3 className="panel-section__title">Zone Properties</h3>
                <label className="panel-label">
                  Field
                  <select
                    className="panel-select"
                    value={selectedZone.fieldName}
                    onChange={e => updateSelectedZone({ fieldName: e.target.value })}
                  >
                    {CANONICAL_FIELDS.map(f => (
                      <option key={f} value={f}>{FIELD_LABELS[f]}</option>
                    ))}
                  </select>
                </label>

                <div className="panel-checkboxes">
                  <label className="panel-checkbox">
                    <input
                      type="checkbox"
                      checked={selectedZone.alwaysReview}
                      onChange={e => updateSelectedZone({ alwaysReview: e.target.checked })}
                    />
                    Always Review
                  </label>
                  <label className="panel-checkbox">
                    <input
                      type="checkbox"
                      checked={selectedZone.allowMultiline}
                      onChange={e => updateSelectedZone({ allowMultiline: e.target.checked })}
                    />
                    Multiline
                  </label>
                </div>

                <label className="panel-label">
                  Hardcoded Value
                  <input
                    className="panel-input"
                    value={selectedZone.hardcodedValue}
                    onChange={e => updateSelectedZone({ hardcodedValue: e.target.value })}
                    placeholder="(leave empty for OCR)"
                  />
                </label>
                <label className="panel-label">
                  Regex Pattern
                  <input
                    className="panel-input"
                    value={selectedZone.regexPattern}
                    onChange={e => updateSelectedZone({ regexPattern: e.target.value })}
                    placeholder="parsing regex..."
                  />
                </label>
                <label className="panel-label">
                  Date Format
                  <input
                    className="panel-input"
                    value={selectedZone.dateFormat}
                    onChange={e => updateSelectedZone({ dateFormat: e.target.value })}
                    placeholder="%m/%d/%Y"
                  />
                </label>
                <div className="panel-row">
                  <label className="panel-label">
                    Min Length
                    <input
                      type="number"
                      className="panel-input panel-input--short"
                      value={selectedZone.minLength || ''}
                      min={0}
                      onChange={e => updateSelectedZone({ minLength: parseInt(e.target.value) || 0 })}
                    />
                  </label>
                  <label className="panel-label">
                    Max Length
                    <input
                      type="number"
                      className="panel-input panel-input--short"
                      value={selectedZone.maxLength || ''}
                      min={0}
                      onChange={e => updateSelectedZone({ maxLength: parseInt(e.target.value) || 0 })}
                    />
                  </label>
                </div>

                <div className="panel-bbox-info">
                  bbox: [{selectedZone.bbox.map(v => v.toFixed(4)).join(', ')}]
                </div>
              </section>
            )}

            {/* Display Options */}
            <section className="panel-section">
              <div className="panel-checkboxes">
                <label className="panel-checkbox">
                  <input type="checkbox" checked={showLabels} onChange={e => setShowLabels(e.target.checked)} />
                  Show Labels
                </label>
                <label className="panel-checkbox">
                  <input type="checkbox" checked={showFill} onChange={e => setShowFill(e.target.checked)} />
                  Show Fill
                </label>
              </div>
            </section>

            {/* Zones List */}
            <section className="panel-section panel-section--grow">
              <h3 className="panel-section__title">Zones ({zones.length})</h3>
              <div className="zones-list-panel">
                {zones.map(z => (
                  <div
                    key={z.id}
                    className={`zone-list-item ${z.id === selectedZoneId ? 'zone-list-item--selected' : ''}`}
                    onClick={() => setSelectedZoneId(z.id)}
                  >
                    <span
                      className="zone-list-item__color"
                      style={{ backgroundColor: FIELD_COLORS[z.fieldName] }}
                    />
                    <span className="zone-list-item__name">
                      {FIELD_LABELS[z.fieldName]}
                    </span>
                  </div>
                ))}
                {zones.length === 0 && (
                  <div className="zone-list-empty">No zones defined yet</div>
                )}
              </div>
            </section>

            {/* Actions */}
            <section className="panel-section">
              <div className="panel-actions">
                <button className="btn btn--secondary" onClick={normalizeZones} disabled={zones.length < 2} title="Align zones into neat columns (N)">
                  Normalize
                </button>
                <button className="btn btn--danger-outline" onClick={deleteSelected} disabled={!selectedZoneId}>
                  Delete
                </button>
                <button className="btn btn--secondary" onClick={clearAll} disabled={zones.length === 0}>
                  Clear All
                </button>
              </div>
              <button
                className="btn btn--primary panel-save-btn"
                onClick={handleSave}
                disabled={saving || zones.length === 0}
              >
                {saving ? 'Saving...' : 'Save Template'}
              </button>
            </section>
          </div>
        </div>

        {/* Canvas area */}
        <div className="editor-canvas">
          {!imageSrc ? (
            <div className="canvas-upload">
              <label className="canvas-upload__label">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <circle cx="8.5" cy="8.5" r="1.5" />
                  <path d="m21 15-5-5L5 21" />
                </svg>
                <span className="canvas-upload__text">
                  Upload a sample document image
                </span>
                <span className="canvas-upload__hint">
                  PNG, JPG, or BMP - this is the reference image for drawing zones
                </span>
                <input
                  type="file"
                  accept="image/*"
                  onChange={handleImageUpload}
                  className="canvas-upload__input"
                />
                <span className="btn btn--primary">Choose Image</span>
              </label>
            </div>
          ) : (
            <div
              className="canvas-container"
              ref={containerRef}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onMouseLeave={handleMouseUp}
              style={{ cursor: tool === 'rect' ? 'crosshair' : 'default' }}
            >
              <img
                ref={imgRef}
                src={imageSrc}
                alt="Template document"
                className="canvas-image"
                draggable={false}
              />

              {/* SVG overlay for zones */}
              <svg
                className="zone-overlay"
                viewBox="0 0 1 1"
                preserveAspectRatio="none"
              >
                {/* Existing zones */}
                {zones.map(z => {
                  const [x0, y0, x1, y1] = z.bbox;
                  const color = FIELD_COLORS[z.fieldName] || '#3b82f6';
                  const isSelected = z.id === selectedZoneId;

                  return (
                    <g key={z.id}>
                      <rect
                        x={x0} y={y0}
                        width={x1 - x0} height={y1 - y0}
                        fill={showFill ? color : 'none'}
                        fillOpacity={isSelected ? 0.35 : 0.15}
                        stroke={isSelected ? '#fff' : color}
                        strokeWidth={isSelected ? 0.004 : 0.002}
                        strokeDasharray={isSelected ? 'none' : 'none'}
                      />
                      {showLabels && (
                        <text
                          x={x0 + 0.005}
                          y={y0 + 0.025}
                          fontSize="0.018"
                          fill={isSelected ? '#fff' : color}
                          fontWeight={isSelected ? 'bold' : 'normal'}
                          style={{ pointerEvents: 'none' }}
                        >
                          {FIELD_LABELS[z.fieldName]}
                        </text>
                      )}
                      {/* Resize handles */}
                      {isSelected && (
                        <>
                          {[[x0, y0], [x1, y0], [x1, y1], [x0, y1]].map(([hx, hy], i) => (
                            <rect
                              key={i}
                              x={hx - 0.008} y={hy - 0.008}
                              width={0.016} height={0.016}
                              fill="#fff"
                              stroke="#333"
                              strokeWidth={0.002}
                              style={{ cursor: ['nw-resize', 'ne-resize', 'se-resize', 'sw-resize'][i] }}
                            />
                          ))}
                        </>
                      )}
                    </g>
                  );
                })}

                {/* Temp drawing rect */}
                {tempRect && (
                  <rect
                    x={tempRect[0]} y={tempRect[1]}
                    width={tempRect[2] - tempRect[0]}
                    height={tempRect[3] - tempRect[1]}
                    fill="none"
                    stroke="#22c55e"
                    strokeWidth={0.003}
                    strokeDasharray="0.01 0.005"
                  />
                )}
              </svg>

              {/* Change image button */}
              <label className="canvas-change-image">
                <input type="file" accept="image/*" onChange={handleImageUpload} style={{ display: 'none' }} />
                Change Image
              </label>
            </div>
          )}

          {/* Status bar */}
          <div className="editor-statusbar">
            <span className="editor-statusbar__msg">{statusMsg}</span>
            <span className="editor-statusbar__info">
              {imageSrc && `${imageSize.w}x${imageSize.h}`}
              {zones.length > 0 && ` | ${zones.length} zone${zones.length !== 1 ? 's' : ''}`}
            </span>
          </div>
        </div>
      </main>
    </div>
  );
}

export default TemplateEditorPage;
