/**
 * SmartLog AI — shared frontend types.
 *
 * These mirror the backend Pydantic schemas in `backend/schemas.py` EXACTLY
 * (same field names, same snake_case casing). Change both files together.
 */

export const CATEGORIES = [
  "Database Error",
  "API Failure",
  "Login Failure",
  "Payment Issue",
  "Security Alert",
  "Resource Usage",
  "Workflow Error",
  "User Action",
  "Unknown",
] as const;

export type Category = (typeof CATEGORIES)[number];

export const SEVERITIES = ["Critical", "High", "Medium", "Low"] as const;
export type Severity = (typeof SEVERITIES)[number];

export const STATUSES = ["Open", "Acknowledged", "Resolved"] as const;
export type IncidentStatus = (typeof STATUSES)[number];

export type ClassifiedBy = "Regex" | "BERT+LogReg" | "DBSCAN" | "LLM";

/** One row of the pipeline trace (stepper UI). */
export interface PipelineStage {
  stage: string;
  matched: boolean;
  score: number;
}

/** Result of POST /api/classify. */
export interface ClassificationResult {
  category: Category;
  severity: Severity;
  confidence: number;
  classified_by: ClassifiedBy;
  cleaned_text: string;
  is_known: boolean;
  pipeline_trace: PipelineStage[];
  explanation: string;
  remediation: string;
}

/** One classified log event. */
export interface Incident {
  id: number;
  timestamp: string;
  source: string;
  level: string;
  raw_text: string;
  cleaned_text: string;
  category: string;
  severity: Severity;
  confidence: number;
  classified_by: ClassifiedBy;
  regex_rule: string | null;
  is_known: boolean;
  pipeline_trace: PipelineStage[];
  explanation: string;
  remediation: string;
  detection_ms: number;
  status: IncidentStatus;
}

/** GET /api/incidents response. */
export interface IncidentListResponse {
  items: Incident[];
  total: number;
  page: number;
  page_size: number;
}

/** Query params for GET /api/incidents. */
export interface IncidentFilters {
  page?: number;
  page_size?: number;
  severity?: string;
  category?: string;
  source?: string;
  status?: string;
  search?: string;
  from?: string;
  to?: string;
  sortBy?: string;
  sortDir?: "asc" | "desc";
}

export interface ChangeDelta {
  logs: number;
  incidents: number;
  critical: number;
}

export interface CategoryCount {
  category: string;
  count: number;
}

export interface SourceCount {
  source: string;
  count: number;
}

export interface SeverityCount {
  severity: string;
  count: number;
}

/** GET /api/dashboard/stats response. */
export interface DashboardStats {
  total_logs: number;
  total_incidents: number;
  critical_count: number;
  unknown_anomalies: number;
  avg_detection_ms: number;
  false_alert_rate: number;
  change_vs_prev_24h: ChangeDelta;
  by_category: CategoryCount[];
  by_source: SourceCount[];
  by_severity: SeverityCount[];
}

export interface TimeseriesPoint {
  timestamp: string;
  count: number;
}

export interface TimeseriesResponse {
  points: TimeseriesPoint[];
}

export interface AnomalyPoint {
  incident_id: number;
  x: number;
  y: number;
  cluster_id: number; // -1 == noise
  noise: boolean;
}

export interface AnomalyCluster {
  cluster_id: number;
  size: number;
  is_noise: boolean;
  sample_logs: string[];
  labeled_category: string | null;
}

export interface ClustersResponse {
  points: AnomalyPoint[];
  clusters: AnomalyCluster[];
}

export interface PerClassMetric {
  category: string;
  precision: number;
  recall: number;
  f1: number;
  support: number;
}

export interface BaselineRow {
  approach: string;
  f1: number;
  false_alert_rate: number;
}

export interface ClassifierUsageRow {
  classified_by: string;
  share: number;
}

/** GET /api/metrics response (serves backend/models/metrics.json). */
export interface MetricsResponse {
  accuracy: number;
  f1_macro: number;
  trained_at: string;
  per_class: PerClassMetric[];
  confusion_matrix: { labels: string[]; matrix: number[][] };
  baseline_comparison: BaselineRow[];
  classifier_usage: ClassifierUsageRow[];
}

export interface UploadResponse {
  upload_id: number;
  filename: string;
  total_lines: number;
}

export interface UploadStatus {
  upload_id: number;
  filename: string;
  status: "processing" | "done" | "failed";
  processed: number;
  total: number;
  incidents_created: number;
}

export interface HealthResponse {
  status: "ok";
  models_loaded: boolean;
  version: string;
}

/** Frames received on WS /ws/stream. */
export type StreamFrame =
  | { type: "hello"; message: string }
  | { type: "incident"; data: Incident };
