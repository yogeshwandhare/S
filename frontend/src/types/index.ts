export type UserRole = "admin" | "operator" | "viewer";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface HealthStatus {
  status: "ok" | "degraded";
  uptime_seconds: number;
  database: {
    connected: boolean;
    error: string | null;
  };
}

export type IncidentCategory =
  | "intrusion"
  | "abandoned_object"
  | "aggressive_motion"
  | "fight"
  | "weapon";

export type IncidentSeverity = "low" | "medium" | "high" | "critical";

export type IncidentStatus =
  | "new"
  | "acknowledged"
  | "investigating"
  | "resolved"
  | "false_positive";

export type CameraStatus = "online" | "offline" | "error" | "disabled";
export type CameraSourceType = "rtsp" | "http" | "file" | "usb";

export interface Camera {
  id: string;
  name: string;
  source_type: CameraSourceType;
  status: CameraStatus;
  enabled: boolean;
  inference_fps: number;
  target_width: number;
  last_error: string | null;
  notes: string | null;
  created_at: string;
}

export interface CameraHealth {
  camera_id: string;
  connected: boolean;
  last_frame_at: string | null;
  last_error: string | null;
  measured_capture_fps: number;
  measured_inference_fps: number;
  consecutive_reconnect_attempts: number;
  active_track_count: number;
}

export interface ModelConfigInfo {
  id: string;
  task: string;
  name: string;
  license: string;
  is_available: boolean;
  enabled: boolean;
  confidence_threshold: number;
  notes: string | null;
  updated_at: string;
}

export interface Zone {
  id: string;
  camera_id: string;
  name: string;
  polygon: [number, number][];
  dwell_time_seconds: number;
  cooldown_seconds: number;
  severity: "low" | "medium" | "high" | "critical";
  enabled: boolean;
  created_at: string;
}

export interface ZoneCreateInput {
  camera_id: string;
  name: string;
  polygon: [number, number][];
  dwell_time_seconds?: number;
  cooldown_seconds?: number;
  severity?: string;
}

export interface ZoneUpdateInput {
  name?: string;
  polygon?: [number, number][];
  dwell_time_seconds?: number;
  cooldown_seconds?: number;
  severity?: string;
  enabled?: boolean;
}

export type IncidentSeverityLevel = IncidentSeverity;
export type IncidentStatusValue = IncidentStatus;

export interface Incident {
  id: string;
  camera_id: string;
  category: IncidentCategory;
  severity: IncidentSeverityLevel;
  status: IncidentStatusValue;
  model_name: string | null;
  ai_confidence: number | null;
  snapshot_path: string | null;
  assigned_operator_id: string | null;
  review_notes: string | null;
  acknowledged_at: string | null;
  resolved_at: string | null;
  human_confirmed: boolean | null;
  event_started_at: string;
  event_ended_at: string | null;
  created_at: string;
  evidence: Record<string, unknown>;
  track_ids: number[];
}

export interface IncidentTimelineEntry {
  id: string;
  event_type: string;
  detail: string | null;
  actor_user_id: string | null;
  created_at: string;
}
