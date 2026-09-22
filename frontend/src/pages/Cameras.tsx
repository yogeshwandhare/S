import { type FormEvent, useState } from "react";
import { Camera as CameraIcon, Loader2, Plus, Trash2, Wifi } from "lucide-react";

import { PageHeader } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CameraStatusDot } from "@/components/ui/badges";
import {
  useCameras,
  useCreateCamera,
  useDeleteCamera,
  useModels,
  useTestCameraConnection,
  useUpdateCamera,
} from "@/hooks/useCameras";
import { ApiError } from "@/lib/api";
import type { CameraSourceType } from "@/types";

function AddCameraForm({ onDone }: { onDone: () => void }) {
  const createCamera = useCreateCamera();
  const [name, setName] = useState("");
  const [sourceType, setSourceType] = useState<CameraSourceType>("file");
  const [sourceUri, setSourceUri] = useState("");
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    createCamera.mutate(
      { name, source_type: sourceType, source_uri: sourceUri },
      {
        onSuccess: () => {
          setName("");
          setSourceUri("");
          onDone();
        },
        onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to add camera"),
      },
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 border-t border-border p-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="space-y-1">
          <label className="text-xs text-text-muted">Name</label>
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Front Entrance"
            className="w-full rounded-md border border-border-strong bg-surface-raised px-3 py-1.5 text-sm text-text outline-none focus-visible:border-cyan"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-text-muted">Source type</label>
          <select
            value={sourceType}
            onChange={(e) => setSourceType(e.target.value as CameraSourceType)}
            className="w-full rounded-md border border-border-strong bg-surface-raised px-3 py-1.5 text-sm text-text outline-none focus-visible:border-cyan"
          >
            <option value="file">Video file (sample_data/)</option>
            <option value="rtsp">RTSP stream</option>
            <option value="usb">USB webcam</option>
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-text-muted">
            {sourceType === "file" ? "Filename" : sourceType === "usb" ? "Device index" : "RTSP URL"}
          </label>
          <input
            required
            value={sourceUri}
            onChange={(e) => setSourceUri(e.target.value)}
            placeholder={
              sourceType === "file"
                ? "synthetic_pipeline_test.mp4"
                : sourceType === "usb"
                  ? "0"
                  : "rtsp://192.168.1.50:554/stream1"
            }
            className="w-full rounded-md border border-border-strong bg-surface-raised px-3 py-1.5 text-sm text-text outline-none focus-visible:border-cyan"
          />
        </div>
      </div>
      {error && <p className="text-sm text-severity-critical">{error}</p>}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={createCamera.isPending}>
          {createCamera.isPending ? "Adding…" : "Add camera"}
        </Button>
      </div>
    </form>
  );
}

function TestConnectionButton({ cameraId }: { cameraId: string }) {
  const testConnection = useTestCameraConnection();
  return (
    <div className="flex items-center gap-2">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => testConnection.mutate(cameraId)}
        disabled={testConnection.isPending}
      >
        {testConnection.isPending ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Wifi className="h-3.5 w-3.5" />
        )}
        Test
      </Button>
      {testConnection.data && (
        <span
          className={`text-xs ${testConnection.data.ok ? "text-status-online" : "text-severity-critical"}`}
        >
          {testConnection.data.message}
        </span>
      )}
    </div>
  );
}

export function CamerasPage() {
  const { data: cameras, isLoading } = useCameras();
  const { data: models } = useModels();
  const updateCamera = useUpdateCamera();
  const deleteCamera = useDeleteCamera();
  const [showAddForm, setShowAddForm] = useState(false);

  const activeDetector = models?.find((m) => m.task === "object_detection" && m.enabled);

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Cameras"
        description="Add, configure, and monitor camera sources."
        actions={
          !showAddForm && (
            <Button size="sm" onClick={() => setShowAddForm(true)}>
              <Plus className="h-4 w-4" />
              Add camera
            </Button>
          )
        }
      />

      <div className="flex-1 space-y-4 p-6">
        <Card className="border-cyan/20 bg-cyan/5">
          <CardContent className="py-3 text-sm text-text-muted">
            Object detector:{" "}
            {activeDetector ? (
              <span className="text-text">
                {activeDetector.name} ({activeDetector.license})
              </span>
            ) : (
              <span className="text-severity-medium">
                not configured — cameras will show raw video with no detection overlay.
                Run <code className="rounded bg-surface-raised px-1">scripts/download_models.py</code>.
              </span>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Camera sources</CardTitle>
          </CardHeader>

          {isLoading && (
            <CardContent>
              <p className="text-sm text-text-muted">Loading…</p>
            </CardContent>
          )}

          {cameras && cameras.length === 0 && !showAddForm && (
            <CardContent>
              <div className="flex flex-col items-center gap-2 py-8 text-center">
                <CameraIcon className="h-8 w-8 text-text-faint" />
                <p className="text-sm text-text-muted">No cameras configured yet.</p>
              </div>
            </CardContent>
          )}

          {cameras && cameras.length > 0 && (
            <div className="divide-y divide-border">
              {cameras.map((camera) => (
                <div key={camera.id} className="flex items-center justify-between px-4 py-3">
                  <div className="flex items-center gap-3">
                    <CameraStatusDot status={camera.status} />
                    <div>
                      <p className="text-sm text-text">{camera.name}</p>
                      <p className="text-xs text-text-faint uppercase">
                        {camera.source_type} · {camera.inference_fps} fps
                      </p>
                      {camera.last_error && (
                        <p className="text-xs text-severity-critical">{camera.last_error}</p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <TestConnectionButton cameraId={camera.id} />
                    <label className="flex items-center gap-1.5 text-xs text-text-muted">
                      <input
                        type="checkbox"
                        checked={camera.enabled}
                        onChange={(e) =>
                          updateCamera.mutate({ id: camera.id, enabled: e.target.checked })
                        }
                      />
                      Enabled
                    </label>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => deleteCamera.mutate(camera.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {showAddForm && <AddCameraForm onDone={() => setShowAddForm(false)} />}
        </Card>
      </div>
    </div>
  );
}
