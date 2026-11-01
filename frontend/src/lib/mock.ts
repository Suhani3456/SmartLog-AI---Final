/**
 * SmartLog AI — offline mock fallback (VITE_USE_MOCK=true).
 *
 * A thin stand-in for the backend so the UI can be demoed without it.
 * Shapes match the real API exactly; the data is small and believable but
 * NOT the real pipeline. Keep this only as a fallback.
 *
 * The store starts EMPTY, exactly like the real backend: every KPI is 0,
 * every list is empty, and data appears only when a file is uploaded
 * (baseLogsProcessed === 0 until then). No synthetic data feeds the UI.
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

// Template rows used ONLY when a real file is uploaded through the mock.
const SAMPLE_ROWS: [string, string, string, string, string, number][] = [
  // source, level, raw, category, classifiedBy, detectionMs
  ["CRM", "ERROR", "crm-app-03 db: connection timeout after 30s, req_id={id}", "Database Error", "Regex", 4.1],
  ["Billing", "WARN", "billing-api-02 payment: transaction declined, card token reused", "Payment Issue", "Regex", 3.6],
  ["HRMS", "INFO", "hrms-web-01 user logged in, user_id={id}", "User Action", "Regex", 3.2],
  ["Cloud/Server", "ERROR", "node-07 api: upstream timed out retrieving /v2/orders", "API Failure", "Regex", 4.4],
  ["CRM", "CRITICAL", "crm-app-01 auth: brute force suspected from subnet 10.2.x, acl triggered", "Security Alert", "Regex", 3.9],
  ["Cloud/Server", "INFO", "node-12 systemd service restart completed for api-gateway", "User Action", "Regex", 3.0],
];

// The mutable store — starts at the same zero state the backend has.
let incidents: Incident[] = [];
let nextId = 1;
let baseLogsProcessed = 0; // records added by ingest; 0 on a fresh start

function makeIncident(row: [string, string, string, string, string, number]): Incident {
  const [source, level, raw, category, classifiedBy, detectionMs] = row;
  return {
    id: nextId++,
    timestamp: new Date().toISOString(),
    source,
    level,
    raw_text: raw,
    cleaned_text: raw.toLowerCase().replace(/[^a-z0-9 ]/g, " ").slice(0, 120),
    category,
    severity:
      level === "CRITICAL" ? "Critical" : level === "ERROR" ? "High" : level === "WARN" ? "Medium" : "Low",
    confidence: classifiedBy === "Regex" ? 0.97 : 0.75,
    classified_by: classifiedBy as Incident["classified_by"],
    regex_rule: classifiedBy === "Regex" ? "api_5xx_01" : null,
    is_known: category !== "Unknown",
    pipeline_trace: [
      { stage: "Preprocess", matched: true, score: 1 },
      { stage: "Regex", matched: true, score: 0.97 },
    ],
    explanation: "Mock response matched a canned rule.",
    remediation: "Check the upstream service health endpoint.",
    detection_ms: detectionMs,
    status: "Open",
  };
}

/** Store the ingested lines (from upload; scrape needs the backend). */
function addIncidents(lines: string[]): void {
  for (const line of lines) {
    if (!line.trim()) continue;
    const lowered = line.toLowerCase();
    const level = lowered.includes("error") ? "ERROR"
      : lowered.includes("critical") ? "CRITICAL"
      : lowered.includes("warn") ? "WARN"
      : "INFO";
    const source = lowered.includes("crm") ? "CRM"
      : lowered.includes("hrms") || lowered.includes("employee") || lowered.includes("payroll") ? "HRMS"
      : lowered.includes("billing") || lowered.includes("payment") || lowered.includes("invoice") ? "Billing"
      : "Cloud/Server";
    const row = SAMPLE_ROWS[nextId % SAMPLE_ROWS.length];
    const incident = makeIncident([source, level, line, row[3], row[4], row[5]]);
    incidents.push(incident);
    baseLogsProcessed++;
  }
  incidents = incidents.slice(-500);
}

const EMPTY_TIMESERIES: TimeseriesResponse = {
  points: Array.from({ length: 7 }, (_, i) => ({
    timestamp: new Date(Date.now() - (6 - i) * 86400000).toISOString().slice(0, 10),
    count: 0,
  })),
};

function countsOf(
  rows: Incident[],
  keyName: "category" | "source" | "severity",
): { key: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const key = row[keyName] ?? "Unknown";
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([key, count]) => ({ key, count }))
    .sort((a, b) => b.count - a.count);
}

export const mockApi = {
  async getHealth() {
    await delay();
    return { status: "ok", models_loaded: false, version: "0.1.0" };
  },

  async getDashboardStats(): Promise<DashboardStats> {
    await delay();
    if (incidents.length === 0) {
      return {
        total_logs: 0,
        total_incidents: 0,
        critical_count: 0,
        unknown_anomalies: 0,
        avg_detection_ms: 0,
        false_alert_rate: 0,
        change_vs_prev_24h: { logs: 0, incidents: 0, critical: 0 },
        by_category: [],
        by_source: [],
        by_severity: [],
      };
    }
    const last24 = Date.now() - 86400000;
    const logsNow = incidents.filter((i) => new Date(i.timestamp).getTime() >= last24).length;
    const logsPrev = incidents.filter((i) => {
      const t = new Date(i.timestamp).getTime();
      return t >= last24 - 86400000 && t < last24;
    }).length;
    return {
      total_logs: incidents.length,
      total_incidents: incidents.length,
      critical_count: incidents.filter((i) => i.severity === "Critical").length,
      unknown_anomalies: incidents.filter((i) => !i.is_known).length,
      avg_detection_ms:
        incidents.length === 0
          ? 0
          : Math.round((incidents.reduce((s, i) => s + (i.detection_ms || 0), 0) / incidents.length) * 100) / 100,
      false_alert_rate: 0,
      change_vs_prev_24h: { logs: logsNow - logsPrev, incidents: logsNow - logsPrev, critical: 0 },
      by_category: countsOf(incidents, "category").map(({ key, count }) => ({ category: key, count })),
      by_source: countsOf(incidents, "source").map(({ key, count }) => ({ source: key, count })),
      by_severity: countsOf(incidents, "severity").map(({ key, count }) => ({ severity: key, count })),
    };
  },

  async getTimeseries(): Promise<TimeseriesResponse> {
    await delay();
    if (incidents.length === 0) return EMPTY_TIMESERIES;
    const counts = new Map<string, number>();
    for (const incident of incidents) {
      const key = incident.timestamp.slice(0, 10);
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    const points = Array.from({ length: 7 }, (_, i) => {
      const key = new Date(Date.now() - (6 - i) * 86400000).toISOString().slice(0, 10);
      return { timestamp: key, count: counts.get(key) ?? 0 };
    });
    return { points };
  },

  async getIncidents(filters: any = {}): Promise<IncidentListResponse> {
    await delay();
    let items = [...incidents].sort((a, b) => b.id - a.id);
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

  /**
   * Mock ingest: splits the file into lines and stores them through the same
   * store the stats read from — the dashboard fills only after a real upload.
   */
  async uploadLogs(file: File): Promise<UploadResponse> {
    await delay(300);
    const text = await file.text();
    const lines = text.split(/\r?\n/).filter((l) => l.trim() !== "");
    addIncidents(lines);
    return {
      upload_id: baseLogsProcessed,
      filename: file.name || "mock-logs.log",
      total_lines: lines.length,
    };
  },

  async getUploadStatus(): Promise<UploadStatus> {
    await delay();
    return {
      upload_id: baseLogsProcessed,
      filename: "mock-logs.log",
      status: "done",
      processed: baseLogsProcessed,
      total: baseLogsProcessed,
      incidents_created: baseLogsProcessed,
    };
  },

  async getClusters(): Promise<ClustersResponse> {
    await delay();
    if (incidents.filter((i) => !i.is_known).length === 0) {
      return { points: [], clusters: [] };
    }
    const unknowns = incidents.filter((i) => !i.is_known);
    return {
      points: unknowns.map((incident, i) => ({
        incident_id: incident.id,
        x: -0.5 + Math.sin(i) * 1.2,
        y: Math.cos(i) * 1.5,
        cluster_id: i % 2,
        noise: false,
      })),
      clusters: [
        {
          cluster_id: 0,
          size: unknowns.length,
          is_noise: false,
          sample_logs: unknowns.slice(0, 2).map((i) => i.raw_text),
          labeled_category: null,
        },
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
