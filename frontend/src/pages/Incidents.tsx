import { useState } from "react";
import { AlertTriangle, CheckCircle2, Clock, XCircle } from "lucide-react";

import { PageHeader } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { IncidentStatusBadge, SeverityBadge } from "@/components/ui/badges";
import { useIncident, useIncidentTimeline, useIncidents, useReviewIncident } from "@/hooks/useIncidents";
import type { IncidentStatusValue } from "@/types";

const STATUS_FILTERS: { label: string; value: IncidentStatusValue | undefined }[] = [
  { label: "All", value: undefined },
  { label: "New", value: "new" },
  { label: "Acknowledged", value: "acknowledged" },
  { label: "Investigating", value: "investigating" },
  { label: "Resolved", value: "resolved" },
  { label: "False positive", value: "false_positive" },
];

function CategoryLabel({ category }: { category: string }) {
  return <span className="capitalize">{category.replace("_", " ")}</span>;
}

function IncidentDetailPanel({ incidentId, onClose }: { incidentId: string; onClose: () => void }) {
  const { data: incident } = useIncident(incidentId);
  const { data: timeline } = useIncidentTimeline(incidentId);
  const review = useReviewIncident();
  const [notes, setNotes] = useState("");

  if (!incident) return null;

  return (
    <div className="w-96 shrink-0 border-l border-border bg-surface">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <p className="text-sm font-medium text-text">
          <CategoryLabel category={incident.category} />
        </p>
        <button onClick={onClose} className="text-text-muted hover:text-text">
          <XCircle className="h-4 w-4" />
        </button>
      </div>

      <div className="space-y-4 p-4">
        <div className="flex items-center gap-2">
          <SeverityBadge severity={incident.severity} />
          <IncidentStatusBadge status={incident.status} />
        </div>

        {incident.snapshot_path && (
          <img
            src={`/api/incidents/${incident.id}/snapshot`}
            alt="Evidence snapshot"
            className="w-full rounded-md border border-border"
          />
        )}

        <div className="space-y-1 text-sm">
          <p className="text-text-muted">
            Detected:{" "}
            <span className="text-text">{new Date(incident.event_started_at).toLocaleString()}</span>
          </p>
          {Object.entries(incident.evidence).map(([key, value]) => (
            <p key={key} className="text-text-muted">
              {key.replace(/_/g, " ")}: <span className="text-text">{String(value)}</span>
            </p>
          ))}
          {incident.track_ids.length > 0 && (
            <p className="text-text-muted">
              Track ID{incident.track_ids.length > 1 ? "s" : ""}:{" "}
              <span className="font-mono text-text">{incident.track_ids.join(", ")}</span>
            </p>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="secondary"
            disabled={review.isPending}
            onClick={() => review.mutate({ id: incident.id, status: "acknowledged" })}
          >
            <Clock className="h-3.5 w-3.5" />
            Acknowledge
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={review.isPending}
            onClick={() => review.mutate({ id: incident.id, status: "resolved" })}
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            Resolve
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={review.isPending}
            onClick={() =>
              review.mutate({ id: incident.id, status: "false_positive", human_confirmed: false })
            }
          >
            False positive
          </Button>
        </div>

        <div className="space-y-2">
          <label className="text-xs text-text-muted">Add a note</label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            className="w-full rounded-md border border-border-strong bg-surface-raised px-2 py-1.5 text-sm text-text outline-none focus-visible:border-cyan"
          />
          <Button
            size="sm"
            variant="secondary"
            disabled={!notes.trim() || review.isPending}
            onClick={() => {
              review.mutate({ id: incident.id, review_notes: notes });
              setNotes("");
            }}
          >
            Save note
          </Button>
        </div>

        {timeline && timeline.length > 0 && (
          <div className="space-y-1.5 border-t border-border pt-3">
            <p className="text-xs font-medium text-text-muted">Timeline</p>
            {timeline.map((t) => (
              <p key={t.id} className="text-xs text-text-faint">
                {new Date(t.created_at).toLocaleTimeString()} — {t.event_type}
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function IncidentsPage() {
  const [statusFilter, setStatusFilter] = useState<IncidentStatusValue | undefined>(undefined);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data: incidents, isLoading } = useIncidents({ status: statusFilter });

  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="flex flex-1 flex-col">
        <PageHeader title="Incidents" description="Searchable, filterable incident review queue." />

        <div className="flex gap-2 border-b border-border bg-surface px-6 py-3">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.label}
              onClick={() => setStatusFilter(f.value)}
              className={`rounded-full border px-3 py-1 text-xs ${
                statusFilter === f.value
                  ? "border-cyan/40 bg-cyan/10 text-cyan"
                  : "border-border-strong text-text-muted hover:text-text"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-auto p-6">
          {isLoading && <p className="text-sm text-text-muted">Loading…</p>}

          {incidents && incidents.length === 0 && (
            <div className="flex flex-col items-center gap-2 py-16 text-center">
              <AlertTriangle className="h-8 w-8 text-text-faint" />
              <p className="text-sm text-text-muted">No incidents match this filter.</p>
            </div>
          )}

          {incidents && incidents.length > 0 && (
            <Card>
              <div className="divide-y divide-border">
                {incidents.map((incident) => (
                  <button
                    key={incident.id}
                    onClick={() => setSelectedId(incident.id)}
                    className={`flex w-full items-center justify-between px-4 py-3 text-left hover:bg-surface-hover ${
                      selectedId === incident.id ? "bg-surface-hover" : ""
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <SeverityBadge severity={incident.severity} />
                      <div>
                        <p className="text-sm text-text">
                          <CategoryLabel category={incident.category} />
                        </p>
                        <p className="text-xs text-text-faint">
                          {new Date(incident.created_at).toLocaleString()}
                        </p>
                      </div>
                    </div>
                    <IncidentStatusBadge status={incident.status} />
                  </button>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>

      {selectedId && <IncidentDetailPanel incidentId={selectedId} onClose={() => setSelectedId(null)} />}
    </div>
  );
}
