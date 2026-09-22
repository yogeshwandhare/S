import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface AppUser {
  id: string;
  email: string;
  full_name: string;
  role: "admin" | "operator" | "viewer";
  is_active: boolean;
  created_at: string;
}

export interface AuditLogEntry {
  id: string;
  actor_user_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  detail: string | null;
  ip_address: string | null;
  created_at: string;
}

export function useUsers() {
  return useQuery<AppUser[]>({
    queryKey: ["users"],
    queryFn: () => api.get<AppUser[]>("/api/users"),
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { email: string; full_name: string; password: string; role: string }) =>
      api.post<AppUser>("/api/users", input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useToggleUserActive() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, activate }: { id: string; activate: boolean }) =>
      api.patch<AppUser>(`/api/users/${id}/${activate ? "reactivate" : "deactivate"}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useAuditLogs() {
  return useQuery<AuditLogEntry[]>({
    queryKey: ["audit-logs"],
    queryFn: () => api.get<AuditLogEntry[]>("/api/audit-logs"),
  });
}
