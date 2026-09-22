import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Camera } from "@/types";

export interface SampleVideo {
  filename: string;
  description: string;
}

export function useSampleVideos() {
  return useQuery<SampleVideo[]>({
    queryKey: ["demo", "sample-videos"],
    queryFn: () => api.get<SampleVideo[]>("/api/demo/sample-videos"),
  });
}

export function useLaunchDemo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { filename: string; camera_name: string }) =>
      api.post<Camera>("/api/demo", input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cameras"] }),
  });
}
