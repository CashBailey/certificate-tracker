/**
 * Compliance page — dashboard view of overall compliance health.
 *
 * Shows compliance rate, status breakdown (Compliant / Due Soon / Overdue / Waived),
 * and a per-certificate-type breakdown table.
 */

import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Header } from '../components/Header';
import {
  getComplianceReport,
  ComplianceReport,
} from '../api';
import { calculateComplianceRate } from './reportingMetrics';
import './CompliancePage.css';

export function CompliancePage() {
  const [complianceReport, setComplianceReport] = useState<ComplianceReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        const report = await getComplianceReport();
        setComplianceReport(report);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load compliance report');
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  const overallComplianceRate = complianceReport
    ? calculateComplianceRate(
        complianceReport.status_counts.compliant,
        complianceReport.status_counts.waived,
        complianceReport.total_requirements,
      )
    : null;

  if (loading) {
    return (
      <div className="loading-container">
        <span className="loading-spinner">Loading compliance report...</span>
      </div>
    );
  }

  return (
    <div className="compliance-page">
      <Header
        title="Compliance"
        showBackLink
        backTo="/"
        backLabel="Dashboard"
      />

      <main className="page-main">
        {error && <div className="error-message">{error}</div>}

        <div className="compliance-actions">
          <Link to="/requirements" className="btn btn--secondary">
            View Requirements Table
          </Link>
        </div>

        {complianceReport && (
          <>
            {/* Summary Grid */}
            <div className="summary-grid">
              <div className="summary-card summary-card--highlight">
                <div className="summary-value">
                  {overallComplianceRate === null ? 'No data' : `${overallComplianceRate}%`}
                </div>
                <div className="summary-label">Overall Compliance</div>
              </div>
              <div className="summary-card">
                <div className="summary-value">{complianceReport.total_employees}</div>
                <div className="summary-label">Total Employees</div>
              </div>
              <div className="summary-card">
                <div className="summary-value">{complianceReport.total_requirements}</div>
                <div className="summary-label">Total Requirements</div>
              </div>
            </div>

            {/* Status Breakdown */}
            <div className="status-breakdown">
              <h2>Status Breakdown</h2>
              <div className="status-grid">
                <div className="status-card status-card--compliant">
                  <div className="status-count">{complianceReport.status_counts.compliant}</div>
                  <div className="status-label">Compliant</div>
                  <div className="status-bar">
                    <div
                      className="status-bar__fill"
                      style={{
                        width: `${complianceReport.total_requirements > 0
                          ? (complianceReport.status_counts.compliant / complianceReport.total_requirements) * 100
                          : 0}%`
                      }}
                    />
                  </div>
                </div>

                <div className="status-card status-card--due-soon">
                  <div className="status-count">{complianceReport.status_counts.due_soon}</div>
                  <div className="status-label">Due Soon</div>
                  <div className="status-bar">
                    <div
                      className="status-bar__fill"
                      style={{
                        width: `${complianceReport.total_requirements > 0
                          ? (complianceReport.status_counts.due_soon / complianceReport.total_requirements) * 100
                          : 0}%`
                      }}
                    />
                  </div>
                </div>

                <div className="status-card status-card--overdue">
                  <div className="status-count">{complianceReport.status_counts.overdue}</div>
                  <div className="status-label">Overdue</div>
                  <div className="status-bar">
                    <div
                      className="status-bar__fill"
                      style={{
                        width: `${complianceReport.total_requirements > 0
                          ? (complianceReport.status_counts.overdue / complianceReport.total_requirements) * 100
                          : 0}%`
                      }}
                    />
                  </div>
                </div>

                <div className="status-card status-card--waived">
                  <div className="status-count">{complianceReport.status_counts.waived}</div>
                  <div className="status-label">Waived</div>
                  <div className="status-bar">
                    <div
                      className="status-bar__fill"
                      style={{
                        width: `${complianceReport.total_requirements > 0
                          ? (complianceReport.status_counts.waived / complianceReport.total_requirements) * 100
                          : 0}%`
                      }}
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* By Certificate Type */}
            {Object.keys(complianceReport.by_certificate_type).length > 0 && (
              <div className="by-type-section">
                <h2>By Certificate Type</h2>
                <div className="type-table-container">
                  <table className="type-table">
                    <thead>
                      <tr>
                        <th>Certificate Type</th>
                        <th className="text-center">Compliant</th>
                        <th className="text-center">Due Soon</th>
                        <th className="text-center">Overdue</th>
                        <th className="text-center">Waived</th>
                        <th className="text-center">Compliance Rate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(complianceReport.by_certificate_type).map(([typeName, counts]) => {
                        const total = counts.compliant + counts.due_soon + counts.overdue + counts.waived;
                        const rate = calculateComplianceRate(counts.compliant, counts.waived, total);
                        const rateClass = rate === null
                          ? 'rate--none'
                          : rate >= 90
                            ? 'rate--high'
                            : rate >= 70
                              ? 'rate--medium'
                              : 'rate--low';
                        return (
                          <tr key={typeName}>
                            <td className="type-name">{typeName}</td>
                            <td className="text-center">{counts.compliant}</td>
                            <td className="text-center">{counts.due_soon}</td>
                            <td className="text-center">{counts.overdue}</td>
                            <td className="text-center">{counts.waived}</td>
                            <td className="text-center">
                              <span className={`rate-badge ${rateClass}`}>
                                {rate === null ? 'No data' : `${rate}%`}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

export default CompliancePage;
