import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface AnalyticsSummary {
  window_days: number;
  total_incidents: number;
  by_category: Record<string, number>;
  by_severity: Record<string, number>;
  by_status: Record<string, number>;
  by_camera: Record<string, number>;
  daily_trend: { date: string; count: number }[];
  avg_response_time_seconds: number | null;
  resolved_count: number;
  false_positive_count: number;
}

export function useAnalyticsSummary(days: number) {
  return useQuery<AnalyticsSummary>({
    queryKey: ["analytics", "summary", days],
    queryFn: () => api.get<AnalyticsSummary>(`/api/analytics/summary?days=${days}`),
  });
}
