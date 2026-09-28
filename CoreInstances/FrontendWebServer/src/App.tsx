/**
 * Main application component with routing.
 */

import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { RequirementsPage } from './pages/RequirementsPage';
import { CompliancePage } from './pages/CompliancePage';
import { UploadPage } from './pages/UploadPage';
import { ConfigurationPage } from './pages/ConfigurationPage';
import { ReviewQueuePage } from './pages/ReviewQueuePage';

import { TemplatesPage } from './pages/TemplatesPage';
import { TemplateEditorPage } from './pages/TemplateEditorPage';
import { EmployeesPage } from './pages/EmployeesPage';
import { AuditPage } from './pages/AuditPage';
import { NotificationsPage } from './pages/NotificationsPage';
import { ForgotPasswordPage } from './pages/ForgotPasswordPage';
import { ResetPasswordPage } from './pages/ResetPasswordPage';
import { Header } from './components/Header';
import './App.css';

// PDF.js is the largest browser dependency and is only needed while reviewing
// a document. Keep it out of the initial dashboard/login bundle.
const ReviewDetailPage = lazy(() => import('./pages/ReviewDetailPage'));

function App() {
  return (
    <ThemeProvider>
    <BrowserRouter
      future={{
        v7_startTransition: true,
        v7_relativeSplatPath: true,
      }}
    >
      <AuthProvider>
        <a className="skip-link" href="#app-main-content">Skip to main content</a>
        <div id="app-main-content" tabIndex={-1}>
          <Suspense fallback={<div className="route-loading" role="status">Loading page...</div>}>
          <Routes>
            {/* Public routes */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />

            {/* Coordinator-only routes */}
            <Route
              path="/"
              element={
                <ProtectedRoute allowedRoles={['Coordinator', 'Admin']}>
                  <DashboardPage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/requirements"
              element={
                <ProtectedRoute allowedRoles={['Coordinator']}>
                  <RequirementsPage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/upload"
              element={
                <ProtectedRoute allowedRoles={['Coordinator']}>
                  <UploadPage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/review"
              element={
                <ProtectedRoute allowedRoles={['Coordinator']}>
                  <ReviewQueuePage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/review/:id"
              element={
                <ProtectedRoute allowedRoles={['Coordinator']}>
                  <ReviewDetailPage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/compliance"
              element={
                <ProtectedRoute allowedRoles={['Coordinator']}>
                  <CompliancePage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/configuration"
              element={
                <ProtectedRoute allowedRoles={['Coordinator']}>
                  <ConfigurationPage />
                </ProtectedRoute>
              }
            />

            {/* /reports redirects to compliance dashboard */}
            <Route path="/reports" element={<Navigate to="/compliance" replace />} />

            <Route
              path="/templates"
              element={
                <ProtectedRoute allowedRoles={['Coordinator']}>
                  <TemplatesPage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/templates/new"
              element={
                <ProtectedRoute allowedRoles={['Coordinator']}>
                  <TemplateEditorPage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/notifications"
              element={
                <ProtectedRoute allowedRoles={['Coordinator', 'Admin']}>
                  <NotificationsPage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/employees"
              element={
                <ProtectedRoute allowedRoles={['Coordinator', 'Admin']}>
                  <EmployeesPage />
                </ProtectedRoute>
              }
            />

            <Route
              path="/audit"
              element={
                <ProtectedRoute allowedRoles={['Admin']}>
                  <AuditPage />
                </ProtectedRoute>
              }
            />

            {/* /admin: admin-only gate — RBAC boundary; non-admins redirect to /unauthorized. */}
            <Route
              path="/admin"
              element={
                <ProtectedRoute allowedRoles={['Admin']}>
                  <Navigate to="/" replace />
                </ProtectedRoute>
              }
            />

            {/* Unauthorized page */}
            <Route
              path="/unauthorized"
              element={
                <div className="unauthorized-page">
                  <Header
                    title="Access Denied"
                    showBackLink
                    backTo="/"
                    backLabel="Dashboard"
                  />
                  <main className="page-main">
                    <p>You do not have permission to view this page.</p>
                  </main>
                </div>
              }
            />

            {/* Catch all - redirect to home */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </Suspense>
        </div>
      </AuthProvider>
    </BrowserRouter>
    </ThemeProvider>
  );
}

export default App;
