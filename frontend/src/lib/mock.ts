/**
 * SmartLog AI — offline mock fallback (VITE_USE_MOCK=true).
 *
 * A thin stand-in for the backend so the UI can be demoed without it.
 * Shapes match the real API exactly; the data is small and believable but
 * NOT the real pipeline. Keep this only as a fallback.
 */

import type {
  ClassificationResult,
  ClustersResponse,
  DashboardStats,
  Incident,
  IncidentListResponse,
  IncidentStatus,
  MetricsResponse,
  TimeseriesResponse,
  UploadResponse,
  UploadStatus,
} from "../types";

const delay = (ms = 200) => new Promise((r) => setTimeout(r, ms));

const SAMPLE_ROWS: [string, string, string, string, string, number][] = [
  // source, level, raw, category, classifiedBy, detectionMs
  ["CRM", "ERROR", "2026-10-30 09:14:22 crm-app-03 db: connection timeout after 30s, req_id=a41f2c", "Database Error", "Regex", 4.1],
  ["Billing", "WARN", "2026-10-30 09:15:03 billing-api-02 payment: transaction declined, card token reused", "Payment Issue", "Regex", 3.6],
  ["HRMS", "INFO", "2026-10-30 09:16:41 hrms-web-01 user logged in, user_id=1042", "User Action", "Regex", 3.2],
  ["Cloud/Server", "ERROR", "2026-10-30 09:18:12 node-07 api: upstream timed out retrieving /v2/orders", "API Failure", "Regex", 4.4],
  ["CRM", "CRITICAL", "2026-10-30 09:21:57 crm-app-01 auth: brute force suspected from subnet 10.2.x, acl triggered", "Security Alert", "Regex", 3.9],
];

function makeIncident(i: number): Incident {
  const [source, level, raw, category, classifiedBy, detectionMs] = SAMPLE_ROWS[i % SAMPLE_ROWS.length];
  return {
    id: i,
    timestamp: new Date(Date.UTC(2026, 9, 30, 9, 14 + i * 3)).toISOString(),
    source,
    level,
    raw_text: raw,
    cleaned_text: "upstream orders endpoint returned status retry exhausted",
    category,
    severity: category === "Security Alert" ? "Critical" : category === "Database Error" ? "Critical" : "Medium",
    confidence: classifiedBy === "Regex" ? 0.97 : 0.75,
    classified_by: classifiedBy as Incident["classified_by"],
    regex_rule: classifiedBy === "Regex" ? "api_5xx_01" : null,
    is_known: true,
    pipeline_trace: [
      { stage: "Preprocess", matched: true, score: 1 },
      { stage: "Regex", matched: true, score: 0.97 },
    ],
    explanation: "Mock response matched a canned rule.",
    remediation: "Check the upstream service health endpoint.",
    detection_ms: detectionMs,
    status: i % 4 === 0 ? "Resolved" : i % 3 === 0 ? "Acknowledged" : "Open",
  };
}

const incidents: Incident[] = Array.from({ length: 23 }, (_, i) => makeIncident(i + 1));

export const mockApi = {
  async getHealth() {
    await delay();
    return { status: "ok", models_loaded: false, version: "0.1.0" };
  },

  async getDashboardStats(): Promise<DashboardStats> {
    await delay();
    return {
      total_logs: 18342,
      total_incidents: 23,
      critical_count: 3,
      unknown_anomalies: 47,
      avg_detection_ms: 3.8,
      false_alert_rate: 0.033,
      change_vs_prev_24h: { logs: 118, incidents: 2, critical: 0 },
      by_category: [
        { category: "API Failure", count: 7 },
        { category: "Database Error", count: 5 },
        { category: "User Action", count: 4 },
        { category: "Payment Issue", count: 3 },
        { category: "Security Alert", count: 2 },
        { category: "Resource Usage", count: 2 },
      ],
      by_source: [
        { source: "CRM", count: 9 },
        { source: "Billing", count: 6 },
        { source: "HRMS", count: 4 },
        { source: "Cloud/Server", count: 4 },
      ],
      by_severity: [
        { severity: "Critical", count: 3 },
        { severity: "High", count: 5 },
        { severity: "Medium", count: 9 },
        { severity: "Low", count: 6 },
      ],
    };
  },

  async getTimeseries(): Promise<TimeseriesResponse> {
    await delay();
    const points = Array.from({ length: 7 }, (_, i) => ({
      timestamp: new Date(Date.now() - (6 - i) * 86400000).toISOString().slice(0, 10),
      count: [3, 5, 2, 6, 4, 2, 1][i],
    }));
    return { points };
  },

  async getIncidents(filters: any = {}): Promise<IncidentListResponse> {
    await delay();
    let items = incidents;
    if (filters.severity) items = items.filter((i) => i.severity === filters.severity);
    if (filters.category) items = items.filter((i) => i.category === filters.category);
    if (filters.status) items = items.filter((i) => i.status === filters.status);
    if (filters.search) {
      const q = String(filters.search).toLowerCase();
      items = items.filter((i) => i.raw_text.toLowerCase().includes(q));
    }
    const page = Number(filters.page ?? 1);
    const pageSize = Number(filters.page_size ?? 20);
    return { items: items.slice((page - 1) * pageSize, page * pageSize), total: items.length, page, page_size: pageSize };
  },

  async getIncident(id: number): Promise<Incident> {
    await delay();
    const found = incidents.find((i) => i.id === id);
    if (!found) throw new Error("Incident not found");
    return found;
  },

  async updateIncidentStatus(id: number, status: IncidentStatus): Promise<Incident> {
    await delay();
    const found = incidents.find((i) => i.id === id);
    if (!found) throw new Error("Incident not found");
    found.status = status;
    return found;
  },

  async classifyText(text: string): Promise<ClassificationResult> {
    await delay(400);
    const known = /timeout|deadlock|declined|brute force/i.test(text);
    return {
      category: known ? "Database Error" : "Unknown",
      severity: known ? "Critical" : "Medium",
      confidence: known ? 0.97 : 0.15,
      classified_by: known ? "Regex" : "LLM",
      cleaned_text: text.toLowerCase().replace(/[^a-z0-9 ]/g, " ").slice(0, 120),
      is_known: known,
      pipeline_trace: [
        { stage: "Preprocess", matched: true, score: 1 },
        { stage: known ? "Regex" : "BERT+LogReg", matched: known, score: known ? 0.97 : 0.42 },
      ],
      explanation: "Mock backend response (VITE_USE_MOCK=true).",
      remediation: known ? "Check the DB connection pool and slow-query log." : "Forward to the on-call engineer for manual triage.",
    };
  },

  async uploadLogs(): Promise<UploadResponse> {
    await delay(300);
    return { upload_id: 1, filename: "mock-logs.log", total_lines: 12 };
  },

  async getUploadStatus(): Promise<UploadStatus> {
    await delay();
    return { upload_id: 1, filename: "mock-logs.log", status: "done", processed: 12, total: 12, incidents_created: 12 };
  },

  async getClusters(): Promise<ClustersResponse> {
    await delay();
    return {
      points: [
        { incident_id: 1, x: -1.2, y: 0.4, cluster_id: 0, noise: false },
        { incident_id: 2, x: -1.1, y: 0.6, cluster_id: 0, noise: false },
        { incident_id: 3, x: 1.4, y: -0.8, cluster_id: 1, noise: false },
        { incident_id: 4, x: 0.2, y: 2.0, cluster_id: -1, noise: true },
      ],
      clusters: [
        { cluster_id: 0, size: 2, is_noise: false, sample_logs: ["upstream crm-api timed out"], labeled_category: null },
        { cluster_id: 1, size: 1, is_noise: false, sample_logs: ["unlabeled task state"], labeled_category: null },
        { cluster_id: -1, size: 1, is_noise: true, sample_logs: ["no rulebook knows this"], labeled_category: null },
      ],
    };
  },

  async labelCluster(_clusterId: number, category: string) {
    await delay();
    return { saved: true, training_example_id: 1, category };
  },

  async getMetrics(): Promise<MetricsResponse> {
    await delay();
    const labels = ["Database Error", "API Failure", "Login Failure", "Payment Issue", "Security Alert", "Resource Usage", "Workflow Error", "User Action"];
    return {
      accuracy: 0.927,
      f1_macro: 0.927,
      trained_at: "2026-01-01T00:00:00Z",
      per_class: labels.map((c, i) => ({ category: c, precision: 0.9 + i * 0.01, recall: 0.88 + i * 0.01, f1: 0.89 + i * 0.01, support: 50 + i * 7 })),
      confusion_matrix: { labels, matrix: labels.map((_, i) => labels.map((_, j) => (i === j ? 60 : (i * 8 + j) % 3))) },
      baseline_comparison: [
        { approach: "Rule-based only", f1: 0.781, false_alert_rate: 0.089 },
        { approach: "ML only", f1: 0.908, false_alert_rate: 0.041 },
        { approach: "Hybrid", f1: 0.927, false_alert_rate: 0.033 },
      ],
      classifier_usage: [
        { classified_by: "Regex", share: 0.61 },
        { classified_by: "BERT+LogReg", share: 0.33 },
        { classified_by: "DBSCAN", share: 0.02 },
        { classified_by: "LLM", share: 0.04 },
      ],
    };
  },
};
