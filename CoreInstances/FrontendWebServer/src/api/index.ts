/**
 * API functions for all endpoints.
 */

import { API_URL, apiFetch, fetchWithAuthRetry } from './client';

export { tokenStorage } from './client';

// ==================== TYPES ====================

export interface User {
  id: number;
  employee_number: string;
  first_name: string;
  last_name: string;
  email: string;
  role: string;
  is_active: boolean;
}

export interface Requirement {
  id: number;
  employee_id: number;
  employee_name: string | null;
  certificate_type_id: number;
  due_date: string;
  status: string;
  satisfied_by_id: number | null;
  expiration_date: string | null;
  waived_at: string | null;
  waived_by_id: number | null;
  waiver_reason: string | null;
  waiver_expiration: string | null;
  created_at: string;
  updated_at: string;
}

export interface Document {
  id: number;
  employee_id: number;
  file_name: string;
  file_type: string;
  file_size_bytes: number;
  uploaded_by_id: number;
  acting_as: string;
  created_at: string;
}

export interface ExtractionField {
  value: string | null;
  confidence: {
    zone: number;
    ocr: number;
    parse: number;
    validate: number;
    overall: number;
  };
  extraction_source: string;
  needs_review: boolean;
  bbox_norm?: [number, number, number, number]; // [x1, y1, x2, y2] normalized 0-1
  page?: number;
}

export interface Extraction {
  id: number;
  document_id: number;
  review_state: string;
  extracted_fields: Record<string, ExtractionField>;
  needs_review: boolean;
  needs_review_reasons: string[];
  template_id: string | null;
  template_version: number | null;
  review_assist: Record<string, { candidates: Array<{ value: string; confidence: number }> }> | null;
  reviewed_by_id: number | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

type ExtractionReviewState =
  | 'Processing'
  | 'PendingReview'
  | 'Approved'
  | 'Rejected';

const REVIEW_STATE_MAP: Record<string, ExtractionReviewState> = {
  Processing: 'Processing',
  PendingReview: 'PendingReview',
  Approved: 'Approved',
  Rejected: 'Rejected',
  processing: 'Processing',
  pending_review: 'PendingReview',
  approved: 'Approved',
  rejected: 'Rejected',
};

export function normalizeReviewState(state: string): string {
  return REVIEW_STATE_MAP[state] || state;
}

function normalizeExtraction(extraction: Extraction): Extraction {
  return {
    ...extraction,
    review_state: normalizeReviewState(extraction.review_state),
  };
}

interface VerifiedRecord {
  id: number;
  extraction_id: number;
  document_id: number;
  employee_id: number;
  certificate_holder_name: string | null;
  certificate_type: string | null;
  certificate_number: string | null;
  issuing_authority: string | null;
  issue_date: string | null;
  expiration_date: string | null;
  training_hours: number | null;
  license_class: string | null;
  endorsements: string | null;
  created_at: string;
}

export interface CertificateType {
  id: number;
  name: string;
  description: string;
  validity_period_days: number | null;
  created_at: string;
  updated_at: string;
}

export interface Template {
  template_id: string;
  version: number;
  name: string;
  description: string;
  zones: Array<{ field_name: string; bbox_norm: number[]; required: boolean }>;
  created_at: string;
  updated_at: string;
}

export interface ComplianceReport {
  total_employees: number;
  total_requirements: number;
  status_counts: {
    compliant: number;
    due_soon: number;
    overdue: number;
    waived: number;
  };
  by_certificate_type: Record<string, { compliant: number; due_soon: number; overdue: number; waived: number }>;
}

// ==================== REQUIREMENTS API ====================

interface RequirementsPage {
  total: number;
  page: number;
  page_size: number;
  items: Requirement[];
}

export async function getRequirements(employeeId?: number): Promise<Requirement[]> {
  const params = employeeId ? `?employee_id=${employeeId}` : '';
  return apiFetch<Requirement[]>(`/api/requirements${params}`);
}

export async function getRequirementsPaged(options: {
  page: number;
  pageSize: number;
  statusFilter?: string;
  search?: string;
}): Promise<RequirementsPage> {
  const params = new URLSearchParams({
    page: String(options.page),
    page_size: String(options.pageSize),
  });
  if (options.statusFilter) params.set('status_filter', options.statusFilter);
  if (options.search) params.set('search', options.search);
  return apiFetch<RequirementsPage>(`/api/requirements/paged?${params}`);
}

export async function createRequirement(data: {
  employee_id: number;
  certificate_type_id: number;
  due_date: string;
}): Promise<Requirement> {
  return apiFetch<Requirement>('/api/requirements', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function waiveRequirement(
  requirementId: number,
  reason: string,
  expiration?: string
): Promise<Requirement> {
  return apiFetch<Requirement>(`/api/requirements/${requirementId}/waive`, {
    method: 'POST',
    body: JSON.stringify({ reason, expiration }),
  });
}

export async function unwaiveRequirement(requirementId: number): Promise<Requirement> {
  return apiFetch<Requirement>(`/api/requirements/${requirementId}/unwaive`, {
    method: 'POST',
  });
}

// ==================== DOCUMENTS API ====================

export async function uploadDocument(file: File, employeeId?: number): Promise<{ document_id: number; extraction_id: number }> {
  const formData = new FormData();
  formData.append('file', file);
  if (employeeId) {
    formData.append('employee_id', employeeId.toString());
  }

  // Use fetchWithAuthRetry so a 401 during silent token refresh transparently
  // refreshes and retries instead of surfacing as a spurious "Upload failed".
  const response = await fetchWithAuthRetry('/api/documents', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Upload failed');
  }

  return response.json();
}

export async function getDocumentViewToken(documentId: number): Promise<string> {
  /**
   * Obtain a short-lived (60-second) document view token from the server.
   * This token is scoped to the specific documentId and is the only form
   * of credential accepted by GET /api/documents/{id}/content.
   * The full access token is sent in the Authorization header (via apiFetch)
   * and never appears in a URL.
   */
  const data = await apiFetch<{ view_token: string }>(
    `/api/documents/${documentId}/view-token`,
    { method: 'POST' }
  );
  return data.view_token;
}

export async function getDocumentContentUrl(documentId: number): Promise<string> {
  /**
   * Build the URL for viewing a document in the PDF viewer.
   * Obtains a short-lived view token first so the full JWT never appears in a URL.
   */
  const baseUrl = API_URL;
  const viewToken = await getDocumentViewToken(documentId);
  return `${baseUrl}/api/documents/${documentId}/content?token=${encodeURIComponent(viewToken)}`;
}

// ==================== EXTRACTIONS API ====================

export async function getExtractions(state?: string): Promise<Extraction[]> {
  const params = state ? `?state=${state}` : '';
  const response = await apiFetch<Extraction[]>(`/api/extractions${params}`);
  return response.map(normalizeExtraction);
}

export async function getExtraction(extractionId: number): Promise<Extraction> {
  const response = await apiFetch<Extraction>(`/api/extractions/${extractionId}`);
  return normalizeExtraction(response);
}

export async function approveExtraction(
  extractionId: number,
  corrections?: Record<string, string>,
  requirementId?: number
): Promise<VerifiedRecord> {
  return apiFetch<VerifiedRecord>(`/api/extractions/${extractionId}/approve`, {
    method: 'POST',
    body: JSON.stringify({ corrections, requirement_id: requirementId }),
  });
}

export async function rejectExtraction(extractionId: number, reason: string): Promise<void> {
  await apiFetch(`/api/extractions/${extractionId}/reject`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
}

// ==================== REPORTS API ====================

export async function getComplianceReport(): Promise<ComplianceReport> {
  return apiFetch<ComplianceReport>('/api/reports/requirements');
}

// Trigger a browser download of a Response body. Hoisted out so all three
// download fns share the same retry-on-401 path via fetchWithAuthRetry —
// previously each fn read tokenStorage synchronously, which raced with the
// silent-refresh window and produced spurious "Failed to download report".
async function _downloadResponseAs(response: Response, filename: string): Promise<void> {
  if (!response.ok) throw new Error('Failed to download report');
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

interface RequirementsExportOptions {
  status?: string;
  requirementStatus?: string;
  search?: string;
}

function _buildRequirementsExportQuery(format: 'csv' | 'xlsx', options?: RequirementsExportOptions): string {
  const params = new URLSearchParams({ format });
  if (options?.status) params.set('status', options.status);
  if (options?.requirementStatus) params.set('requirement_status', options.requirementStatus);
  if (options?.search) params.set('search', options.search);
  return `/api/reports/requirements?${params.toString()}`;
}

export async function downloadRequirementsXlsx(options?: RequirementsExportOptions): Promise<void> {
  const response = await fetchWithAuthRetry(_buildRequirementsExportQuery('xlsx', options));
  await _downloadResponseAs(
    response,
    `requirements_compliance_${new Date().toISOString().split('T')[0]}.xlsx`,
  );
}

export async function downloadRequirementsCsv(options?: RequirementsExportOptions): Promise<void> {
  const response = await fetchWithAuthRetry(_buildRequirementsExportQuery('csv', options));
  await _downloadResponseAs(
    response,
    `requirements_compliance_${new Date().toISOString().split('T')[0]}.csv`,
  );
}

// ==================== TEMPLATES API ====================

export async function getTemplates(): Promise<{ templates: Template[]; registry_hash: string }> {
  return apiFetch<{ templates: Template[]; registry_hash: string }>('/api/templates');
}

interface TemplateZoneCreate {
  field_name: string;
  bbox_norm: number[];
  required: boolean;
  hardcoded_value?: string;
  regex_pattern?: string;
  date_format?: string;
  allow_multiline: boolean;
  min_length?: number;
  max_length?: number;
}

interface TemplateCreateRequest {
  template_id: string;
  version: number;
  name: string;
  description?: string;
  anchor_keywords?: string[];
  anchor_regex?: string;
  min_keyword_matches: number;
  zones: TemplateZoneCreate[];
  always_review_fields?: string[];
  created_at: string;
  updated_at: string;
}

export async function createTemplate(data: TemplateCreateRequest): Promise<Template> {
  return apiFetch<Template>('/api/templates', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ==================== CERTIFICATE TYPES API ====================

export interface CertificateTypeCreate {
  name: string;
  description: string;
  validity_period_days?: number | null;
}

export interface CertificateTypeUpdate {
  name?: string;
  description?: string;
  validity_period_days?: number | null;
}

export async function getCertificateTypes(): Promise<CertificateType[]> {
  return apiFetch<CertificateType[]>('/api/certificate-types');
}

export async function createCertificateType(data: CertificateTypeCreate): Promise<CertificateType> {
  return apiFetch<CertificateType>('/api/certificate-types', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateCertificateType(id: number, data: CertificateTypeUpdate): Promise<CertificateType> {
  return apiFetch<CertificateType>(`/api/certificate-types/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deleteCertificateType(id: number): Promise<void> {
  return apiFetch<void>(`/api/certificate-types/${id}`, {
    method: 'DELETE',
  });
}

// ==================== EMPLOYEES API ====================

export interface EmployeeCreate {
  employee_number: string;
  first_name: string;
  last_name: string;
  email: string;
  role: string;
  manager_id?: number | null;
}

export interface EmployeeUpdate {
  employee_number?: string;
  first_name?: string;
  last_name?: string;
  email?: string;
  role?: string;
  manager_id?: number | null;
  is_active?: boolean;
}

interface EmployeeListResponse {
  employees: User[];
  total: number;
  skip: number;
  limit: number;
}

export async function getEmployees(params?: {
  skip?: number;
  limit?: number;
  role?: string;
  is_active?: boolean;
  search?: string;
}): Promise<EmployeeListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.skip !== undefined) searchParams.set('skip', params.skip.toString());
  if (params?.limit !== undefined) searchParams.set('limit', params.limit.toString());
  if (params?.role) searchParams.set('role', params.role);
  if (params?.is_active !== undefined) searchParams.set('is_active', params.is_active.toString());
  if (params?.search) searchParams.set('search', params.search);

  const query = searchParams.toString();
  return apiFetch<EmployeeListResponse>(`/api/employees${query ? `?${query}` : ''}`);
}

export async function getEmployee(employeeId: number): Promise<User> {
  return apiFetch<User>(`/api/employees/${employeeId}`);
}

export async function createEmployee(data: EmployeeCreate): Promise<User> {
  return apiFetch<User>('/api/employees', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateEmployee(employeeId: number, data: EmployeeUpdate): Promise<User> {
  return apiFetch<User>(`/api/employees/${employeeId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deactivateEmployee(employeeId: number): Promise<void> {
  await apiFetch(`/api/employees/${employeeId}`, {
    method: 'DELETE',
  });
}

export async function reactivateEmployee(employeeId: number): Promise<User> {
  return apiFetch<User>(`/api/employees/${employeeId}/reactivate`, {
    method: 'POST',
  });
}

export async function sendSetupEmail(employeeId: number): Promise<void> {
  await apiFetch(`/api/employees/${employeeId}/send-setup-email`, {
    method: 'POST',
  });
}

// ==================== NOTIFICATIONS API ====================

export interface Notification {
  id: number;
  notification_type: string;
  recipient_employee_id: number;
  subject: string;
  body: string;
  read: boolean;
  read_at: string | null;
  related_requirement_id: number | null;
  related_certificate_id: number | null;
  created_at: string;
}

interface NotificationListResponse {
  notifications: Notification[];
  total_unread: number;
}

export async function getNotifications(options?: {
  unreadOnly?: boolean;
  limit?: number;
}): Promise<NotificationListResponse> {
  const params = new URLSearchParams();
  if (options?.unreadOnly) params.set('unread_only', 'true');
  if (options?.limit) params.set('limit', String(options.limit));
  const query = params.toString();
  return apiFetch<NotificationListResponse>(
    `/api/notifications${query ? `?${query}` : ''}`
  );
}

export async function getUnreadCount(): Promise<number> {
  const data = await apiFetch<{ unread_count: number }>(
    '/api/notifications/unread-count'
  );
  return data.unread_count;
}

export async function markNotificationRead(id: number): Promise<Notification> {
  return apiFetch<Notification>(`/api/notifications/${id}/mark-read`, {
    method: 'POST',
  });
}

export async function markAllNotificationsRead(): Promise<{
  marked_count: number;
  message: string;
}> {
  return apiFetch('/api/notifications/mark-all-read', { method: 'POST' });
}

// ==================== AUDIT LOGS API ====================

export interface AuditLogEntry {
  id: number;
  actor_type: string;
  employee_id: number | null;
  actor_name: string | null;
  action: string;
  target_type: string;
  target_id: string;
  details: Record<string, unknown> | null;
  initiated_by_id: number | null;
  occurred_at_utc: string;
  recorded_at_utc: string;
  actor_role: string | null;
  source_service: string | null;
  outcome: string | null;
  ip_address: string | null;
  // Legacy alias — kept for components that reference created_at
  created_at: string;
}

interface AuditLogListResponse {
  total: number;
  skip: number;
  limit: number;
  items: AuditLogEntry[];
}

export async function getAuditLogs(params?: {
  action?: string;
  target_type?: string;
  target_id?: string;
  employee_id?: number;
  source_service?: string;
  outcome?: string;
  actor_role?: string;
  created_after?: string;
  created_before?: string;
  skip?: number;
  limit?: number;
}): Promise<AuditLogListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.action) searchParams.set('action', params.action);
  if (params?.target_type) searchParams.set('target_type', params.target_type);
  if (params?.target_id) searchParams.set('target_id', params.target_id);
  if (params?.employee_id !== undefined) searchParams.set('employee_id', params.employee_id.toString());
  if (params?.source_service) searchParams.set('source_service', params.source_service);
  if (params?.outcome) searchParams.set('outcome', params.outcome);
  if (params?.actor_role) searchParams.set('actor_role', params.actor_role);
  if (params?.created_after) searchParams.set('created_after', params.created_after);
  if (params?.created_before) searchParams.set('created_before', params.created_before);
  if (params?.skip !== undefined) searchParams.set('skip', params.skip.toString());
  if (params?.limit !== undefined) searchParams.set('limit', params.limit.toString());

  const query = searchParams.toString();
  return apiFetch<AuditLogListResponse>(`/api/audit-logs${query ? `?${query}` : ''}`);
}

// ==================== ALERT CONFIGURATION API ====================

export interface AlertConfig {
  requirement_reminder_days: number[];
  certificate_reminder_days: number[];
  daily_overdue_enabled: boolean;
  global_send_hour: number;
  global_send_minute: number;
  updated_at: string;
  updated_by_id: number | null;
}

export async function getAlertConfig(): Promise<AlertConfig> {
  return apiFetch<AlertConfig>('/api/alert-config');
}

export async function updateAlertConfig(
  config: Omit<AlertConfig, 'updated_at' | 'updated_by_id'>
): Promise<AlertConfig> {
  return apiFetch<AlertConfig>('/api/alert-config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
}
