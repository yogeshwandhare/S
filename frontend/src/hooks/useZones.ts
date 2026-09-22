import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Zone, ZoneCreateInput, ZoneUpdateInput } from "@/types";

export function useZones(cameraId: string | undefined) {
  return useQuery<Zone[]>({
    queryKey: ["zones", cameraId],
    queryFn: () => api.get<Zone[]>(`/api/zones?camera_id=${cameraId}`),
    enabled: !!cameraId,
  });
}

export function useCreateZone() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ZoneCreateInput) => api.post<Zone>("/api/zones", input),
    onSuccess: (zone) => queryClient.invalidateQueries({ queryKey: ["zones", zone.camera_id] }),
  });
}

export function useUpdateZone() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...changes }: { id: string } & ZoneUpdateInput) =>
      api.patch<Zone>(`/api/zones/${id}`, changes),
    onSuccess: (zone) => queryClient.invalidateQueries({ queryKey: ["zones", zone.camera_id] }),
  });
}

export function useDeleteZone() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: string; cameraId: string }) => api.delete<void>(`/api/zones/${id}`),
    onSuccess: (_data, variables) =>
      queryClient.invalidateQueries({ queryKey: ["zones", variables.cameraId] }),
  });
}
