import { type MouseEvent, useRef, useState } from "react";
import { Save, Trash2, X } from "lucide-react";

import { PageHeader } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useCameras } from "@/hooks/useCameras";
import { useCreateZone, useDeleteZone, useZones } from "@/hooks/useZones";
import { ApiError } from "@/lib/api";

export function ZonesPage() {
  const { data: cameras } = useCameras();
  const [cameraId, setCameraId] = useState<string>("");
  const activeCameraId = cameraId || cameras?.[0]?.id || "";
  const { data: zones } = useZones(activeCameraId || undefined);
  const createZone = useCreateZone();
  const deleteZone = useDeleteZone();

  const [points, setPoints] = useState<[number, number][]>([]);
  const [zoneName, setZoneName] = useState("");
  const [dwellSeconds, setDwellSeconds] = useState(2);
  const [severity, setSeverity] = useState("medium");
  const [error, setError] = useState<string | null>(null);
  const imgRef = useRef<HTMLImageElement>(null);

  function handleImageClick(e: MouseEvent<HTMLImageElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    setPoints((prev) => [...prev, [Number(x.toFixed(4)), Number(y.toFixed(4))]]);
  }

  function handleSave() {
    if (points.length < 3 || !zoneName.trim() || !activeCameraId) return;
    setError(null);
    createZone.mutate(
      {
        camera_id: activeCameraId,
        name: zoneName,
        polygon: points,
        dwell_time_seconds: dwellSeconds,
        severity,
      },
      {
        onSuccess: () => {
          setPoints([]);
          setZoneName("");
        },
        onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to save zone"),
      },
    );
  }

  // Use an explicit SVG coordinate system: the `points` attribute expects
  // numeric coordinates, while CSS percentage strings are unreliable here.
  const polygonPointsAttr = points.map(([x, y]) => `${x * 1000},${y * 1000}`).join(" ");

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Zone Editor"
        description="Click on the live feed to draw a restricted-zone polygon."
      />

      <div className="flex-1 space-y-4 p-6">
        <div className="flex items-center gap-3">
          <label className="text-xs text-text-muted">Camera</label>
          <select
            value={activeCameraId}
            onChange={(e) => {
              setCameraId(e.target.value);
              setPoints([]);
            }}
            className="rounded-md border border-border-strong bg-surface-raised px-3 py-1.5 text-sm text-text outline-none"
          >
            {cameras?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        {!activeCameraId && (
          <p className="text-sm text-text-muted">Add a camera first on the Cameras page.</p>
        )}

        {activeCameraId && (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
            <Card className="overflow-hidden">
              <div className="relative">
                <img
                  ref={imgRef}
                  src={`/api/cameras/${activeCameraId}/stream.mjpg`}
                  alt="Camera feed for zone drawing"
                  onClick={handleImageClick}
                  className="w-full cursor-crosshair select-none"
                />
                <svg
                  aria-hidden="true"
                  viewBox="0 0 1000 1000"
                  preserveAspectRatio="none"
                  className="pointer-events-none absolute inset-0 h-full w-full"
                >
                  {points.length >= 3 && (
                    <polygon
                      points={polygonPointsAttr}
                      fill="rgba(45, 212, 191, 0.2)"
                      stroke="#2dd4bf"
                      strokeWidth={4}
                      strokeLinejoin="round"
                    />
                  )}
                  {points.length === 2 && (
                    <polyline
                      points={polygonPointsAttr}
                      fill="none"
                      stroke="#2dd4bf"
                      strokeWidth={4}
                      strokeLinejoin="round"
                      strokeLinecap="round"
                    />
                  )}
                  {points.map(([x, y], i) => (
                    <circle key={i} cx={x * 1000} cy={y * 1000} r={7} fill="#2dd4bf" stroke="#0f172a" strokeWidth={3} />
                  ))}
                </svg>
              </div>
              <CardContent className="flex items-center justify-between py-2">
                <p className="text-xs text-text-muted">
                  {points.length === 0
                    ? "Click at least 3 points on the image to draw a zone."
                    : `${points.length} point${points.length === 1 ? "" : "s"} placed.`}
                </p>
                {points.length > 0 && (
                  <Button variant="ghost" size="sm" onClick={() => setPoints([])}>
                    <X className="h-3.5 w-3.5" />
                    Clear
                  </Button>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardContent className="space-y-3">
                <div className="space-y-1">
                  <label className="text-xs text-text-muted">Zone name</label>
                  <input
                    value={zoneName}
                    onChange={(e) => setZoneName(e.target.value)}
                    placeholder="Loading Dock"
                    className="w-full rounded-md border border-border-strong bg-surface-raised px-3 py-1.5 text-sm text-text outline-none focus-visible:border-cyan"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-text-muted">Dwell time (seconds)</label>
                  <input
                    type="number"
                    min={0}
                    step={0.5}
                    value={dwellSeconds}
                    onChange={(e) => setDwellSeconds(Number(e.target.value))}
                    className="w-full rounded-md border border-border-strong bg-surface-raised px-3 py-1.5 text-sm text-text outline-none focus-visible:border-cyan"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-text-muted">Severity</label>
                  <select
                    value={severity}
                    onChange={(e) => setSeverity(e.target.value)}
                    className="w-full rounded-md border border-border-strong bg-surface-raised px-3 py-1.5 text-sm text-text outline-none"
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </select>
                </div>
                {error && <p className="text-sm text-severity-critical">{error}</p>}
                <Button
                  className="w-full"
                  disabled={points.length < 3 || !zoneName.trim() || createZone.isPending}
                  onClick={handleSave}
                >
                  <Save className="h-4 w-4" />
                  Save zone
                </Button>

                {zones && zones.length > 0 && (
                  <div className="space-y-2 border-t border-border pt-3">
                    <p className="text-xs font-medium text-text-muted">Existing zones</p>
                    {zones.map((zone) => (
                      <div
                        key={zone.id}
                        className="flex items-center justify-between rounded-md border border-border px-2 py-1.5 text-sm"
                      >
                        <span className="text-text">{zone.name}</span>
                        <button
                          onClick={() => deleteZone.mutate({ id: zone.id, cameraId: activeCameraId })}
                          className="text-text-muted hover:text-severity-critical"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
