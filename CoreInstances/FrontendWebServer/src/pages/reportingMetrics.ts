export interface DashboardRequirement {
  due_date: string;
  satisfied_by_id: number | null;
  expiration_date: string | null;
  waived_at: string | null;
}

export interface DashboardStats {
  pendingReviews: number;
  overdueRequirements: number;
  dueSoonRequirements: number;
  expiringCertificates: number;
}

type DateParser = (value: string) => Date;

export function calculateDashboardStats(
  pendingReviews: number,
  requirements: DashboardRequirement[],
  now: Date,
  parseDate: DateParser,
): DashboardStats {
  const thirtyDaysFromNow = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
  const expiringCertificateIds = new Set<number>();
  let overdueRequirements = 0;
  let dueSoonRequirements = 0;

  for (const requirement of requirements) {
    if (requirement.satisfied_by_id !== null) {
      if (requirement.expiration_date) {
        const expirationDate = parseDate(requirement.expiration_date);
        if (expirationDate >= now && expirationDate <= thirtyDaysFromNow) {
          expiringCertificateIds.add(requirement.satisfied_by_id);
        }
      }
      continue;
    }

    if (requirement.waived_at) continue;

    const dueDate = parseDate(requirement.due_date);
    if (dueDate < now) {
      overdueRequirements += 1;
    } else if (dueDate <= thirtyDaysFromNow) {
      dueSoonRequirements += 1;
    }
  }

  return {
    pendingReviews,
    overdueRequirements,
    dueSoonRequirements,
    expiringCertificates: expiringCertificateIds.size,
  };
}

export function hasNoUrgentTasks(stats: DashboardStats | null): boolean {
  return stats !== null
    && stats.pendingReviews === 0
    && stats.overdueRequirements === 0
    && stats.dueSoonRequirements === 0
    && stats.expiringCertificates === 0;
}

export function calculateComplianceRate(
  compliant: number,
  waived: number,
  total: number,
): number | null {
  if (total === 0) return null;
  return Math.round(((compliant + waived) / total) * 100);
}
