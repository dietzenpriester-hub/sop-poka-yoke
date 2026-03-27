import api from "./index";

export interface DashboardOverview {
  active_orders: number;
  today_ok: number;
  today_ng: number;
  ok_rate: number;
  unacknowledged_alerts: number;
  today_alerts: number;
}

export interface StationStatusItem {
  id: number;
  name: string;
  line_id: string;
  active_orders: number;
  status: "busy" | "idle";
}

export interface RecentAlert {
  id: number;
  alert_type: string;
  severity: string;
  message: string;
  station_code: string;
  acknowledged: string;
  created_at: string;
}

export interface HourlyTrend {
  hours: string[];
  ok: number[];
  ng: number[];
}

export const dashboardApi = {
  overview: () => api.get<DashboardOverview>("/dashboard/overview"),
  stationStatus: () => api.get<StationStatusItem[]>("/dashboard/station-status"),
  recentAlerts: () => api.get<RecentAlert[]>("/dashboard/recent-alerts"),
  hourlyTrend: () => api.get<HourlyTrend>("/dashboard/hourly-trend"),
};
