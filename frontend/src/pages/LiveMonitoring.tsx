import { useState } from "react";
import { Maximize2, X } from "lucide-react";

import { PageHeader } from "@/components/AppShell";
import { ComingSoon } from "@/components/ComingSoon";
import { Card } from "@/components/ui/card";
import { useCameraHealth, useCameras } from "@/hooks/useCameras";
import { Activity } from "lucide-react";

function CameraTile({
  cameraId,
  name,
  enabled,
  onExpand,
}: {
  cameraId: string;
  name: string;
  enabled: boolean;
  onExpand: () => void;
}) {
  const { data: health } = useCameraHealth(cameraId, enabled);

  return (
    <Card className="overflow-hidden">
      <div className="relative aspect-video bg-black">
        {enabled ? (
          <img
            src={`/api/cameras/${cameraId}/stream.mjpg`}
            alt={`Live feed: ${name}`}
            className="h-full w-full object-contain"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-text-faint">
            Camera disabled
          </div>
        )}
        <button
          onClick={onExpand}
          className="absolute right-2 top-2 rounded-md bg-black/50 p-1.5 text-white hover:bg-black/70"
          aria-label={`Expand ${name}`}
        >
          <Maximize2 className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="flex items-center justify-between px-3 py-2">
        <p className="text-sm text-text">{name}</p>
        <div className="flex items-center gap-2 text-xs text-text-muted">
          {health && (
            <>
              <span className={health.connected ? "text-status-online" : "text-status-offline"}>
                {health.connected ? "● live" : "● offline"}
              </span>
              {health.connected && (
                <span>{health.measured_inference_fps.toFixed(1)} fps (detection)</span>
              )}
              {health.active_track_count > 0 && <span>{health.active_track_count} tracked</span>}
            </>
          )}
        </div>
      </div>
    </Card>
  );
}

export function LiveMonitoringPage() {
  const { data: cameras, isLoading } = useCameras();
  const [expanded, setExpanded] = useState<{ id: string; name: string } | null>(null);

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Live Monitoring"
        description="Multi-camera grid with live annotated streams."
      />

      {isLoading && (
        <div className="p-6 text-sm text-text-muted">Loading cameras…</div>
      )}

      {cameras && cameras.length === 0 && (
        <ComingSoon
          icon={Activity}
          title="No cameras configured"
          milestone="right now — add one"
          description="Add a camera source on the Cameras page (a sample video file works for a demo) to see it here."
        />
      )}

      {cameras && cameras.length > 0 && (
        <div className="grid flex-1 auto-rows-min grid-cols-1 gap-4 p-6 sm:grid-cols-2 xl:grid-cols-3">
          {cameras.map((camera) => (
            <CameraTile
              key={camera.id}
              cameraId={camera.id}
              name={camera.name}
              enabled={camera.enabled}
              onExpand={() => setExpanded({ id: camera.id, name: camera.name })}
            />
          ))}
        </div>
      )}

      {expanded && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-8">
          <button
            onClick={() => setExpanded(null)}
            className="absolute right-6 top-6 rounded-md bg-white/10 p-2 text-white hover:bg-white/20"
            aria-label="Close fullscreen view"
          >
            <X className="h-5 w-5" />
          </button>
          <div className="flex max-h-full max-w-full flex-col items-center gap-3">
            <img
              src={`/api/cameras/${expanded.id}/stream.mjpg`}
              alt={`Live feed: ${expanded.name}`}
              className="max-h-[85vh] max-w-full rounded-lg object-contain"
            />
            <p className="text-sm text-white/80">{expanded.name}</p>
          </div>
        </div>
      )}
    </div>
  );
}
