/**
 * Configuration page — tabbed container for cert type and alert rule management.
 *
 * Coordinator-only. Tabs:
 *  1. Certificate Types — manage cert types and periodicity
 *  2. Alert Rules — manage reminder day-offsets and overdue behavior
 */

import { useState } from 'react';
import { Header } from '../components/Header';
import { CertTypeTab } from '../components/CertTypeTab';
import { AlertRulesTab } from '../components/AlertRulesTab';
import './ConfigurationPage.css';

type Tab = 'cert-types' | 'alert-rules';

export function ConfigurationPage() {
  const [activeTab, setActiveTab] = useState<Tab>('cert-types');

  return (
    <div className="configuration-page">
      <Header
        title="Configuration"
        showBackLink
        backTo="/"
        backLabel="Dashboard"
      />

      <main className="page-main">
        <div className="config-tabs">
          <button
            className={`config-tab${activeTab === 'cert-types' ? ' config-tab--active' : ''}`}
            onClick={() => setActiveTab('cert-types')}
          >
            Certificate Types
          </button>
          <button
            className={`config-tab${activeTab === 'alert-rules' ? ' config-tab--active' : ''}`}
            onClick={() => setActiveTab('alert-rules')}
          >
            Alert Rules
          </button>
        </div>

        <div className="config-tab-content">
          {activeTab === 'cert-types' && <CertTypeTab />}
          {activeTab === 'alert-rules' && <AlertRulesTab />}
        </div>
      </main>
    </div>
  );
}

export default ConfigurationPage;
