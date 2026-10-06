import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Camera, CameraHealth, CameraSourceType, ModelConfigInfo } from "@/types";

const CAMERAS_KEY = ["cameras"] as const;

export function useUsbDevices(enabled = true) {
  return useQuery({
    queryKey: ["usb-devices"],
    queryFn: () => api.get<{
      discovery_available: boolean;
      devices: { index: number; name: string }[];
    }>("/api/cameras/usb-devices"),
    enabled,
    refetchInterval: enabled ? 5_000 : false,
    retry: false,
  });
}

export function useCameras() {
  return useQuery<Camera[]>({
    queryKey: CAMERAS_KEY,
    queryFn: () => api.get<Camera[]>("/api/cameras"),
    refetchInterval: 10_000,
  });
}

export function useCameraHealth(cameraId: string, enabled: boolean) {
  return useQuery<CameraHealth>({
    queryKey: ["cameras", cameraId, "health"],
    queryFn: () => api.get<CameraHealth>(`/api/cameras/${cameraId}/health`),
    refetchInterval: 3_000,
    enabled,
  });
}

export function useModels() {
  return useQuery<ModelConfigInfo[]>({
    queryKey: ["models"],
    queryFn: () => api.get<ModelConfigInfo[]>("/api/models"),
  });
}

interface CreateCameraInput {
  name: string;
  source_type: CameraSourceType;
  source_uri: string;
  inference_fps?: number;
}

export function useCreateCamera() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateCameraInput) => api.post<Camera>("/api/cameras", input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: CAMERAS_KEY }),
  });
}

export function useUploadCameraVideo() {
  return useMutation({
    mutationFn: (video: File) => {
      const form = new FormData();
      form.append("video", video);
      return api.upload<{ source_uri: string; original_filename: string }>(
        "/api/cameras/upload-video",
        form,
      );
    },
  });
}

export function useUpdateCamera() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...changes }: { id: string; enabled?: boolean; usb_device_index?: number }) =>
      api.patch<Camera>(`/api/cameras/${id}`, changes),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: CAMERAS_KEY }),
  });
}

export function useDeleteCamera() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/api/cameras/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: CAMERAS_KEY }),
  });
}

export function useTestCameraConnection() {
  return useMutation({
    mutationFn: (id: string) =>
      api.post<{ ok: boolean; message: string }>(`/api/cameras/${id}/test-connection`),
  });
}
