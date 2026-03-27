import api from "./index";

export interface ReportSummary {
  ok_rate: number;
  total_orders: number;
  done_orders: number;
  ng_count: number;
  ok_count: number;
  alert_count: number;
  days: number;
}

export interface DailyTrend {
  dates: string[];
  ok: number[];
  ng: number[];
  skip: number[];
  override: number[];
}

export interface AlertDistribution {
  items: { name: string; value: number }[];
}

export interface StationComparison {
  stations: string[];
  alert_counts: number[];
}

export const reportApi = {
  summary: (days?: number) =>
    api.get<ReportSummary>("/report/summary", { params: days ? { days } : {} }),

  dailyTrend: (days?: number) =>
    api.get<DailyTrend>("/report/daily-trend", { params: days ? { days } : {} }),

  alertDistribution: (days?: number) =>
    api.get<AlertDistribution>("/report/alert-distribution", { params: days ? { days } : {} }),

  stationComparison: (days?: number) =>
    api.get<StationComparison>("/report/station-comparison", { params: days ? { days } : {} }),
};
