import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Incident, IncidentStatusValue, IncidentTimelineEntry } from "@/types";

export function useIncidents(filters: { status?: IncidentStatusValue; category?: string } = {}) {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.category) params.set("category", filters.category);
  const qs = params.toString();

  return useQuery<Incident[]>({
    queryKey: ["incidents", filters],
    queryFn: () => api.get<Incident[]>(`/api/incidents${qs ? `?${qs}` : ""}`),
    refetchInterval: 10_000,
  });
}

export function useIncident(incidentId: string | undefined) {
  return useQuery<Incident>({
    queryKey: ["incidents", incidentId],
    queryFn: () => api.get<Incident>(`/api/incidents/${incidentId}`),
    enabled: !!incidentId,
  });
}

export function useIncidentTimeline(incidentId: string | undefined) {
  return useQuery<IncidentTimelineEntry[]>({
    queryKey: ["incidents", incidentId, "timeline"],
    queryFn: () => api.get<IncidentTimelineEntry[]>(`/api/incidents/${incidentId}/timeline`),
    enabled: !!incidentId,
  });
}

interface ReviewInput {
  id: string;
  status?: IncidentStatusValue;
  review_notes?: string;
  human_confirmed?: boolean;
}

export function useReviewIncident() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...changes }: ReviewInput) =>
      api.patch<Incident>(`/api/incidents/${id}`, changes),
    onSuccess: (incident) => {
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      queryClient.invalidateQueries({ queryKey: ["incidents", incident.id, "timeline"] });
    },
  });
}
