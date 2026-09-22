import type { LucideIcon } from "lucide-react";

export function ComingSoon({
  icon: Icon,
  title,
  milestone,
  description,
}: {
  icon: LucideIcon;
  title: string;
  milestone: string;
  description: string;
}) {
  return (
    <div className="flex flex-1 items-center justify-center p-8">
      <div className="max-w-md text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-lg border border-border bg-surface text-text-muted">
          <Icon className="h-5 w-5" />
        </div>
        <h2 className="text-sm font-medium text-text">{title}</h2>
        <p className="mt-2 text-sm text-text-muted">{description}</p>
        <span className="mt-4 inline-flex items-center rounded-full border border-border-strong bg-surface-raised px-2.5 py-1 text-xs text-text-faint">
          Planned for {milestone}
        </span>
      </div>
    </div>
  );
}
