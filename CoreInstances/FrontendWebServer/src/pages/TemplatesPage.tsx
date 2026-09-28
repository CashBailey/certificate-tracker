/**
 * Templates page - View template registry.
 */

import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '../components/Header';
import { getTemplates, Template } from '../api';
import './TemplatesPage.css';

export function TemplatesPage() {
  const navigate = useNavigate();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [registryHash, setRegistryHash] = useState<string>('');
  const [expandedTemplate, setExpandedTemplate] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchTemplates() {
      try {
        const data = await getTemplates();
        setTemplates(data.templates);
        setRegistryHash(data.registry_hash);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load templates');
      } finally {
        setLoading(false);
      }
    }
    fetchTemplates();
  }, []);

  const toggleExpanded = (templateId: string) => {
    setExpandedTemplate(prev => prev === templateId ? null : templateId);
  };

  if (loading) {
    return (
      <div className="loading-container">
        <span className="loading-spinner">Loading templates...</span>
      </div>
    );
  }

  return (
    <div className="templates-page">
      <Header
        title="Template Registry"
        showBackLink
        backTo="/"
        backLabel="Dashboard"
      />

      <main className="page-main">
        {error && <div className="error-message">{error}</div>}

        <div className="registry-info">
          <span className="registry-hash">
            Registry Hash: <code>{registryHash.substring(0, 16)}...</code>
          </span>
          <div className="registry-info__right">
            <span className="template-count">
              {templates.length} template{templates.length !== 1 ? 's' : ''}
            </span>
            <button
              className="btn btn--primary"
              onClick={() => navigate('/templates/new')}
            >
              + Add Template
            </button>
          </div>
        </div>

        {templates.length === 0 ? (
          <div className="empty-state">
            <h2>No Templates</h2>
            <p>No templates have been configured yet.</p>
          </div>
        ) : (
          <div className="templates-list">
            {templates.map(template => (
              <div key={template.template_id} className="template-card">
                <div
                  className="template-header"
                  onClick={() => toggleExpanded(template.template_id)}
                >
                  <div className="template-title">
                    <h3>{template.name}</h3>
                    <span className="template-id">{template.template_id}</span>
                  </div>
                  <div className="template-meta">
                    <span className="version-badge">v{template.version}</span>
                    <span className="expand-icon">
                      {expandedTemplate === template.template_id ? (
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polyline points="18 15 12 9 6 15" />
                        </svg>
                      ) : (
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polyline points="6 9 12 15 18 9" />
                        </svg>
                      )}
                    </span>
                  </div>
                </div>

                {expandedTemplate === template.template_id && (
                  <div className="template-details">
                    <p className="template-description">{template.description}</p>

                    <div className="template-section">
                      <h4>Zones ({template.zones.length})</h4>
                      <div className="zones-table-container">
                        <table className="zones-table">
                          <thead>
                            <tr>
                              <th>Field Name</th>
                              <th>Bounding Box</th>
                            </tr>
                          </thead>
                          <tbody>
                            {template.zones.map((zone, i) => (
                              <tr key={i}>
                                <td><code>{zone.field_name}</code></td>
                                <td className="bbox-cell">
                                  <code>
                                    [{zone.bbox_norm.map(v => v.toFixed(3)).join(', ')}]
                                  </code>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    <div className="template-timestamps">
                      <span>Created: {new Date(template.created_at).toLocaleString()}</span>
                      <span>Updated: {new Date(template.updated_at).toLocaleString()}</span>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

export default TemplatesPage;
