import api from "./index";

export interface VideoClip {
  id: string;
  type: "step" | "alert";
  sn: string;
  station_code?: string;
  step_index?: number;
  step_name?: string;
  result?: string;
  alert_type?: string;
  severity?: string;
  message?: string;
  video_url: string | null;
  snapshot_url: string | null;
  created_at: string | null;
}

export const replayApi = {
  listClips: (params?: {
    sn?: string;
    station_code?: string;
    event_type?: string;
    date_from?: string;
    date_to?: string;
    skip?: number;
    limit?: number;
  }) => api.get<{ items: VideoClip[] }>("/replay/clips", { params }),

  getClipUrl: (objectName: string) =>
    api.get<{ url: string }>("/replay/clip-url", { params: { object_name: objectName } }),
};
