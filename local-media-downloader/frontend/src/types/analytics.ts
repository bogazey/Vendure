export type AnalyticsRange = "today" | "7d" | "30d" | "90d";

export interface TrackEventPayload {
  event_type: "page_view";
  path: string;
  locale?: "en" | "ar";
  referrer?: string;
  utm_source?: string;
  utm_medium?: string;
  utm_campaign?: string;
}

export interface AnalyticsOverviewOut {
  range: AnalyticsRange;
  visitors: number;
  page_views: number;
  downloads_completed: number;
  new_users: number;
  paid_conversions: number;
  active_now: number;
  download_success_rate: number | null;
}

export interface TrafficPointOut {
  date: string;
  visitors: number;
  page_views: number;
}

export interface TrafficOut {
  range: AnalyticsRange;
  points: TrafficPointOut[];
}

export interface TopPageOut {
  path: string;
  views: number;
  visitors: number;
  pct_of_total: number;
}

export interface PagesOut {
  range: AnalyticsRange;
  pages: TopPageOut[];
}

export interface SourceRowOut {
  source: string;
  visitors: number;
  pct_of_total: number;
}

export interface SourcesOut {
  range: AnalyticsRange;
  sources: SourceRowOut[];
}

export interface CountryRowOut {
  country_code: string;
  visitors: number;
  page_views: number;
  downloads: number;
}

export interface GeographyOut {
  range: AnalyticsRange;
  available: boolean;
  countries: CountryRowOut[];
}

export interface BreakdownRowOut {
  key: string;
  count: number;
  pct: number;
}

export interface DevicesOut {
  range: AnalyticsRange;
  devices: BreakdownRowOut[];
  browsers: BreakdownRowOut[];
  os: BreakdownRowOut[];
  languages: BreakdownRowOut[];
}

export interface StageStatsOut {
  started: number;
  completed: number;
  failed: number;
  success_rate: number | null;
  avg_processing_seconds: number | null;
}

export interface PlatformRowOut {
  platform: string;
  analyses: number;
  downloads: number;
  successful: number;
  failed: number;
  success_rate: number | null;
}

export interface FailureRowOut {
  category: string;
  count: number;
}

export interface DownloadsOut {
  range: AnalyticsRange;
  analyze: StageStatsOut;
  downloads: StageStatsOut;
  platforms: PlatformRowOut[];
  failures: FailureRowOut[];
}

export interface FunnelStageOut {
  key: string;
  label: string;
  count: number;
  pct_of_previous: number | null;
}

export interface FunnelOut {
  range: AnalyticsRange;
  stages: FunnelStageOut[];
  methodology_note: string;
}

export interface PlanMovementRowOut {
  kind: string;
  count: number;
}

export interface RevenueOut {
  range: AnalyticsRange;
  active_paid_subscribers: number;
  new_paid_subscribers: number;
  cancellations: number;
  movements: PlanMovementRowOut[];
  mrr_available: boolean;
  mrr_note: string;
}
