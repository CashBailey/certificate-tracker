/**
 * StatusBadge component for displaying status with colored badges.
 */

import React from 'react';
import './StatusBadge.css';


interface StatusBadgeProps {
  status: string;
  size?: 'small' | 'medium' | 'large';
}

const statusColors: Record<string, string> = {
  // Requirements
  NotStarted: 'gray',
  InProgress: 'blue',
  Satisfied: 'green',
  Overdue: 'red',
  Waived: 'purple',
  // Extractions
  PendingReview: 'yellow',
  Approved: 'green',
  Rejected: 'red',
  // Certificates
  Valid: 'green',
  ExpiringSoon: 'yellow',
  Expired: 'red',
  // Compliance
  Compliant: 'green',
  DueSoon: 'yellow',
};

const statusLabels: Record<string, string> = {
  NotStarted: 'Not Started',
  InProgress: 'In Progress',
  Satisfied: 'Satisfied',
  Overdue: 'Overdue',
  Waived: 'Waived',
  PendingReview: 'Pending Review',
  Approved: 'Approved',
  Rejected: 'Rejected',
  Valid: 'Valid',
  ExpiringSoon: 'Expiring Soon',
  Expired: 'Expired',
  Compliant: 'Compliant',
  DueSoon: 'Due Soon',
};

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, size = 'medium' }) => {
  const color = statusColors[status] || 'gray';
  const label = statusLabels[status] || status;

  return (
    <span className={`status-badge status-badge--${color} status-badge--${size}`}>
      {label}
    </span>
  );
};

export default StatusBadge;
