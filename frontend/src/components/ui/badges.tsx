import { cn } from "@/lib/utils";
import type { CameraStatus, IncidentSeverity, IncidentStatus } from "@/types";

const severityStyles: Record<IncidentSeverity, string> = {
  low: "bg-severity-low/15 text-severity-low border-severity-low/30",
  medium: "bg-severity-medium/15 text-severity-medium border-severity-medium/30",
  high: "bg-severity-high/15 text-severity-high border-severity-high/30",
  critical: "bg-severity-critical/15 text-severity-critical border-severity-critical/30",
};

export function SeverityBadge({ severity }: { severity: IncidentSeverity }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium capitalize",
        severityStyles[severity],
      )}
    >
      {severity}
    </span>
  );
}

const statusStyles: Record<IncidentStatus, string> = {
  new: "bg-cyan/15 text-cyan border-cyan/30",
  acknowledged: "bg-severity-medium/15 text-severity-medium border-severity-medium/30",
  investigating: "bg-severity-medium/15 text-severity-medium border-severity-medium/30",
  resolved: "bg-teal/15 text-teal border-teal/30",
  false_positive: "bg-text-faint/15 text-text-muted border-text-faint/30",
};

export function IncidentStatusBadge({ status }: { status: IncidentStatus }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium capitalize",
        statusStyles[status],
        status === "new" && "pulse-new",
      )}
    >
      {status.replace("_", " ")}
    </span>
  );
}

const cameraStatusDot: Record<CameraStatus, string> = {
  online: "bg-status-online",
  offline: "bg-status-offline",
  error: "bg-status-error",
  disabled: "bg-text-faint",
};

export function CameraStatusDot({ status }: { status: CameraStatus }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-text-muted capitalize">
      <span className={cn("h-1.5 w-1.5 rounded-full", cameraStatusDot[status])} />
      {status}
    </span>
  );
}
