import { useState } from "react";
import { PlayCircle } from "lucide-react";

import { PageHeader } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLaunchDemo, useSampleVideos } from "@/hooks/useDemo";
import { ApiError } from "@/lib/api";
import type { Camera } from "@/types";

export function DemoModePage() {
  const { data: videos, isLoading } = useSampleVideos();
  const launchDemo = useLaunchDemo();
  const [launchedCamera, setLaunchedCamera] = useState<Camera | null>(null);
  const [error, setError] = useState<string | null>(null);

  function handleLaunch(filename: string) {
    setError(null);
    launchDemo.mutate(
      { filename, camera_name: `Demo — ${filename}` },
      {
        onSuccess: (camera) => setLaunchedCamera(camera),
        onError: (err) =>
          setError(err instanceof ApiError ? err.message : "Failed to launch demo"),
      },
    );
  }

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Demo Mode"
        description="Present the full detection pipeline using a sample video — no physical camera required."
      />

      <div className="flex-1 space-y-4 p-6">
        <Card className="border-severity-medium/30 bg-severity-medium/5">
          <CardContent className="py-3 text-sm text-text-muted">
            <span className="font-medium text-severity-medium">Demo mode:</span> every camera
            launched from this page uses a labeled sample video file, never a real feed.
            Incidents and detections it produces are real (the same pipeline runs), but the
            source footage is not live CCTV.
          </CardContent>
        </Card>

        {error && <p className="text-sm text-severity-critical">{error}</p>}

        <Card>
          <CardHeader>
            <CardTitle>Available sample clips</CardTitle>
          </CardHeader>
          {isLoading && (
            <CardContent>
              <p className="text-sm text-text-muted">Loading…</p>
            </CardContent>
          )}
          <div className="divide-y divide-border">
            {videos?.map((video) => (
              <div key={video.filename} className="flex items-center justify-between px-4 py-3">
                <div className="max-w-lg">
                  <p className="text-sm text-text">{video.filename}</p>
                  <p className="text-xs text-text-faint">{video.description}</p>
                </div>
                <Button
                  size="sm"
                  onClick={() => handleLaunch(video.filename)}
                  disabled={launchDemo.isPending}
                >
                  <PlayCircle className="h-3.5 w-3.5" />
                  Launch demo
                </Button>
              </div>
            ))}
            {videos?.length === 0 && (
              <p className="px-4 py-6 text-center text-sm text-text-muted">
                No sample videos found under sample_data/.
              </p>
            )}
          </div>
        </Card>

        {launchedCamera && (
          <Card className="overflow-hidden">
            <CardHeader>
              <CardTitle>{launchedCamera.name}</CardTitle>
            </CardHeader>
            <div className="relative aspect-video bg-black">
              <img
                src={`/api/cameras/${launchedCamera.id}/stream.mjpg`}
                alt={`Demo feed: ${launchedCamera.name}`}
                className="h-full w-full object-contain"
              />
              <span className="absolute left-2 top-2 rounded-full bg-severity-medium/90 px-2 py-0.5 text-xs font-medium text-bg">
                DEMO
              </span>
            </div>
            <CardContent className="py-2 text-xs text-text-muted">
              Add a zone for this camera on the Zone Editor page to see live intrusion
              detection, or watch Incidents for real detections from this sample feed.
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
