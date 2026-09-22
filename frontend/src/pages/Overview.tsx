import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, Camera, ShieldCheck } from "lucide-react";

import { PageHeader } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { IncidentStatusBadge, SeverityBadge } from "@/components/ui/badges";
import { useCameras } from "@/hooks/useCameras";
import { useIncidents } from "@/hooks/useIncidents";
import { api } from "@/lib/api";
import type { HealthStatus } from "@/types";

function StatCard({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: typeof Activity;
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <Card>
      <CardContent className="flex items-start justify-between">
        <div>
          <p className="text-xs text-text-muted">{label}</p>
          <p className="mt-1 text-2xl font-semibold text-text">{value}</p>
          {hint && <p className="mt-1 text-xs text-text-faint">{hint}</p>}
        </div>
        <div className="rounded-md border border-border bg-surface-raised p-2 text-text-muted">
          <Icon className="h-4 w-4" />
        </div>
      </CardContent>
    </Card>
  );
}

export function OverviewPage() {
  const { data: health, isLoading, isError } = useQuery<HealthStatus>({
    queryKey: ["health"],
    queryFn: () => api.get<HealthStatus>("/api/health"),
    refetchInterval: 15_000,
  });
  const { data: cameras } = useCameras();
  const { data: allIncidents } = useIncidents();
  const { data: resolvedIncidents } = useIncidents({ status: "resolved" });

  const cameraCount = cameras?.length ?? 0;
  const onlineCount = cameras?.filter((c) => c.status === "online").length ?? 0;
  const unresolvedCount =
    allIncidents?.filter((i) => i.status === "new" || i.status === "acknowledged" || i.status === "investigating")
      .length ?? 0;
  const resolvedCount = resolvedIncidents?.length ?? 0;
  const recentIncidents = allIncidents?.slice(0, 5) ?? [];

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Overview"
        description="System status, camera health, and incident summary."
      />

      <div className="flex-1 space-y-6 p-6">
        <Card>
          <CardHeader>
            <CardTitle>System health</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading && <p className="text-sm text-text-muted">Checking backend…</p>}
            {isError && (
              <p className="text-sm text-severity-critical">
                Could not reach the API. Is the backend running?
              </p>
            )}
            {health && (
              <div className="flex items-center gap-6 text-sm">
                <span className="flex items-center gap-2">
                  <span
                    className={`h-2 w-2 rounded-full ${
                      health.status === "ok" ? "bg-status-online" : "bg-severity-medium"
                    }`}
                  />
                  API: <span className="font-medium text-text">{health.status}</span>
                </span>
                <span className="flex items-center gap-2">
                  <span
                    className={`h-2 w-2 rounded-full ${
                      health.database.connected ? "bg-status-online" : "bg-status-error"
                    }`}
                  />
                  Database:{" "}
                  <span className="font-medium text-text">
                    {health.database.connected ? "connected" : "disconnected"}
                  </span>
                </span>
                <span className="text-text-faint">
                  Uptime: {Math.floor(health.uptime_seconds)}s
                </span>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard icon={Camera} label="Cameras configured" value={String(cameraCount)} />
          <StatCard icon={Activity} label="Cameras online" value={String(onlineCount)} />
          <StatCard icon={AlertTriangle} label="Unresolved incidents" value={String(unresolvedCount)} />
          <StatCard icon={ShieldCheck} label="Resolved" value={String(resolvedCount)} />
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Recent incidents</CardTitle>
          </CardHeader>
          <CardContent>
            {recentIncidents.length === 0 ? (
              <p className="text-sm text-text-muted">
                No incidents recorded yet. Once a camera detects a zone intrusion or an
                unattended object, it will appear here.
              </p>
            ) : (
              <div className="divide-y divide-border">
                {recentIncidents.map((incident) => (
                  <div key={incident.id} className="flex items-center justify-between py-2">
                    <div className="flex items-center gap-3">
                      <SeverityBadge severity={incident.severity} />
                      <span className="text-sm capitalize text-text">
                        {incident.category.replace("_", " ")}
                      </span>
                      <span className="text-xs text-text-faint">
                        {new Date(incident.created_at).toLocaleString()}
                      </span>
                    </div>
                    <IncidentStatusBadge status={incident.status} />
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
