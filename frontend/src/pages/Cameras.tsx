import { type FormEvent, useState } from "react";
import { Camera as CameraIcon, Loader2, Plus, Trash2, Wifi } from "lucide-react";

import { PageHeader } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CameraStatusDot } from "@/components/ui/badges";
import { useSampleVideos } from "@/hooks/useDemo";
import {
  useCameras,
  useCreateCamera,
  useDeleteCamera,
  useModels,
  useTestCameraConnection,
  useUploadCameraVideo,
  useUpdateCamera,
  useUsbDevices,
} from "@/hooks/useCameras";
import { ApiError } from "@/lib/api";
import type { CameraSourceType } from "@/types";

function UsbDevicePicker({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const devices = useUsbDevices();
  if (devices.data && !devices.data.discovery_available) {
    return <input required type="number" min="0" value={value} placeholder="Device index"
      onChange={(event) => onChange(event.target.value)}
      className="w-full rounded-md border border-border-strong bg-surface-raised px-3 py-1.5 text-sm" />;
  }
  return <div className="space-y-2">
    <select required value={devices.data?.devices.some((device) => String(device.index) === value) ? value : ""}
      onChange={(event) => onChange(event.target.value)}
      aria-label="Connected USB camera"
      className="w-full rounded-md border border-border-strong bg-surface-raised px-3 py-1.5 text-sm">
      <option value="">{devices.isLoading ? "Finding cameras…" : "Select a camera by name"}</option>
      {devices.data?.devices.map((device) => <option key={device.index} value={String(device.index)}>
        {device.name} (device {device.index})
      </option>)}
    </select>
    {devices.error && <p className="text-xs text-severity-critical">{devices.error.message}</p>}
    {devices.data?.discovery_available && devices.data.devices.length === 0 &&
      <p className="text-xs text-text-muted">No cameras detected. Connect your USB camera and refresh.</p>}
    <Button type="button" variant="ghost" size="sm" disabled={devices.isFetching}
      onClick={() => void devices.refetch()}>Refresh devices</Button>
  </div>;
}

function ChangeUsbDevice({ cameraId }: { cameraId: string }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const update = useUpdateCamera();
  if (!editing) return <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>Change device</Button>;
  return <form className="space-y-2" onSubmit={(event) => {
    event.preventDefault();
    if (!value) return;
    update.mutate({ id: cameraId, usb_device_index: Number(value), enabled: true }, {
      onSuccess: () => { setEditing(false); setValue(""); },
    });
  }}>
    <UsbDevicePicker value={value} onChange={setValue} />
    {update.error && <p className="text-xs text-severity-critical">{update.error.message}</p>}
    <Button type="submit" size="sm" disabled={!value || update.isPending}>Use camera</Button>
    <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(false)}>Cancel</Button>
  </form>;
}

function AddCameraForm({ onDone }: { onDone: () => void }) {
  const createCamera = useCreateCamera();
  const uploadVideo = useUploadCameraVideo();
  const sampleVideos = useSampleVideos();
  const [name, setName] = useState("");
  const [sourceType, setSourceType] = useState<CameraSourceType>("file");
  const [sourceUri, setSourceUri] = useState("");
  const [manualFileEntry, setManualFileEntry] = useState(false);
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
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
          setUploadedFileName(null);
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
            onChange={(e) => {
              const nextType = e.target.value as CameraSourceType;
              setSourceType(nextType);
              setSourceUri("");
              setManualFileEntry(false);
              setUploadedFileName(null);
            }}
            className="w-full rounded-md border border-border-strong bg-surface-raised px-3 py-1.5 text-sm text-text outline-none focus-visible:border-cyan"
          >
            <option value="file">Video file (sample or upload)</option>
            <option value="rtsp">RTSP stream</option>
            <option value="http">HTTP / MJPEG stream</option>
            <option value="usb">USB webcam</option>
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-text-muted">
            {sourceType === "file" ? "Filename" : sourceType === "usb" ? "Connected camera" : sourceType === "http" ? "Video stream URL" : "RTSP URL"}
          </label>
          {sourceType === "usb" ? <UsbDevicePicker value={sourceUri} onChange={setSourceUri} /> : sourceType === "file" ? (
            <div className="space-y-2">
              {uploadedFileName ? (
                <div className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2 text-xs">
                  <span className="truncate text-text">Using {uploadedFileName}</span>
                  <Button type="button" variant="ghost" size="sm" onClick={() => { setUploadedFileName(null); setSourceUri(""); }}>
                    Choose another
                  </Button>
                </div>
              ) : !manualFileEntry && (
                <select
                  value={sourceUri}
                  onChange={(e) => {
                    if (e.target.value === "__manual__") {
                      setManualFileEntry(true);
                      setSourceUri("");
                    } else {
                      setSourceUri(e.target.value);
                    }
                  }}
                  required
                  aria-label="Sample video file"
                  className="w-full rounded-md border border-border-strong bg-surface-raised px-3 py-1.5 text-sm text-text outline-none"
                >
                  <option value="">{sampleVideos.isLoading ? "Loading sample videos…" : "Choose a sample video"}</option>
                  {sampleVideos.data?.map((video) => (
                    <option key={video.filename} value={video.filename}>{video.filename}</option>
                  ))}
                  <option value="__manual__">Enter filename manually…</option>
                </select>
              )}
              {!uploadedFileName && manualFileEntry && (
                <div className="space-y-1">
                  <input
                    required
                    value={sourceUri}
                    onChange={(e) => setSourceUri(e.target.value)}
                    placeholder="synthetic_pipeline_test.mp4"
                    aria-label="Video filename under sample_data"
                    className="w-full rounded-md border border-border-strong bg-surface-raised px-3 py-1.5 text-sm text-text outline-none focus-visible:border-cyan"
                  />
                  <Button type="button" variant="ghost" size="sm" onClick={() => { setManualFileEntry(false); setSourceUri(""); }}>
                    Choose from samples
                  </Button>
                </div>
              )}
              {!uploadedFileName && sampleVideos.error && <p className="text-xs text-severity-critical">Could not load sample videos. You can enter a filename manually.</p>}
              {!uploadedFileName && !sampleVideos.isLoading && sampleVideos.data?.length === 0 && !manualFileEntry && (
                <p className="text-xs text-text-muted">No sample videos found. Add an MP4 to sample_data/ or enter a filename manually.</p>
              )}
              {!uploadedFileName && !manualFileEntry && sourceUri && (
                <p className="text-xs text-text-muted">{sampleVideos.data?.find((video) => video.filename === sourceUri)?.description}</p>
              )}
              {!uploadedFileName && (
                <div className="space-y-1 border-t border-border pt-2">
                  <label className="text-xs text-text-muted" htmlFor="camera-video-upload">Or choose an MP4 from this device (up to 500 MB)</label>
                  <input
                    id="camera-video-upload"
                    type="file"
                    accept="video/mp4,.mp4"
                    disabled={uploadVideo.isPending}
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (!file) return;
                      uploadVideo.mutate(file, {
                        onSuccess: (uploaded) => {
                          setSourceUri(uploaded.source_uri);
                          setUploadedFileName(uploaded.original_filename);
                          setManualFileEntry(false);
                        },
                      });
                      event.target.value = "";
                    }}
                    className="block w-full text-xs text-text-muted file:mr-2 file:rounded-md file:border-0 file:bg-surface-raised file:px-2 file:py-1 file:text-xs file:text-text"
                  />
                  {uploadVideo.isPending && <p className="text-xs text-text-muted">Uploading video…</p>}
                  {uploadVideo.error && <p className="text-xs text-severity-critical">{uploadVideo.error.message}</p>}
                </div>
              )}
            </div>
          ) : <input
            required
            value={sourceUri}
            onChange={(e) => setSourceUri(e.target.value)}
            placeholder={sourceType === "http" ? "http://192.168.1.19:8080/video" : "rtsp://192.168.1.50:554/stream1"}
            className="w-full rounded-md border border-border-strong bg-surface-raised px-3 py-1.5 text-sm text-text outline-none focus-visible:border-cyan"
          />}
          {sourceType === "http" && <p className="text-xs text-text-muted">
            Use the direct video URL, not the camera's control page. For IP Webcam, append /video.
          </p>}
        </div>
      </div>
      {error && <p className="text-sm text-severity-critical">{error}</p>}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={createCamera.isPending || uploadVideo.isPending}>
          {createCamera.isPending ? "Adding…" : uploadVideo.isPending ? "Uploading video…" : "Add camera"}
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
                    {camera.source_type === "usb" && <ChangeUsbDevice cameraId={camera.id} />}
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
