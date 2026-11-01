/**
 * SmartLog AI — typed HTTP client for every backend call the UI makes.
 *
 * All data access in the app goes through this module. Env:
 *   VITE_API_URL   default http://localhost:8000
 *   VITE_USE_MOCK  default false ("true" serves the offline mock instead)
 */

import type {
  ClassificationResult,
  ClustersResponse,
  DashboardStats,
  HealthResponse,
  Incident,
  IncidentFilters,
  IncidentListResponse,
  IncidentStatus,
  MetricsResponse,
  TimeseriesResponse,
  UploadResponse,
  UploadStatus,
} from "../types";
import { mockApi } from "./mock";

export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
export const USE_MOCK = String(import.meta.env.VITE_USE_MOCK ?? "false") === "true";

export class ApiError extends Error {
  /** Thrown for any non-2xx response; status carries the HTTP code. */
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch (err) {
    throw new ApiError(0, `Couldn't reach the backend (${API_URL}).`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail ?? body);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

// --- Health ----------------------------------------------------------------

export const getHealth = (): Promise<HealthResponse> => request("/api/health");

// --- Dashboard -------------------------------------------------------------

export const getDashboardStats = (): Promise<DashboardStats> =>
  request("/api/dashboard/stats");

export const getTimeseries = (days = 7): Promise<TimeseriesResponse> =>
  request(`/api/incidents/timeseries?days=${days}`);

// --- Incidents -------------------------------------------------------------

export const getIncidents = (filters: IncidentFilters = {}): Promise<IncidentListResponse> => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  return request(`/api/incidents?${params.toString()}`);
};

export const getIncident = (id: number): Promise<Incident> =>
  request(`/api/incidents/${id}`);

export const updateIncidentStatus = (id: number, status: IncidentStatus): Promise<Incident> =>
  request(`/api/incidents/${id}/status`, { method: "PATCH", body: JSON.stringify({ status }) });

// --- Classify --------------------------------------------------------------

export const classifyText = (text: string): Promise<ClassificationResult> =>
  request("/api/classify", { method: "POST", body: JSON.stringify({ text }) });

// --- Upload ----------------------------------------------------------------

export const uploadLogs = (file: File): Promise<UploadResponse> => {
  const form = new FormData();
  form.append("file", file);
  return fetch(`${API_URL}/api/upload`, { method: "POST", body: form }).then(async (res) => {
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new ApiError(res.status, body?.detail ?? res.statusText);
    }
    return res.json() as Promise<UploadResponse>;
  });
};

export const getUploadStatus = (uploadId: number): Promise<UploadStatus> =>
  request(`/api/upload/${uploadId}/status`);

// --- Scrape (Feature 2) -------------------------------------------------------

/**
 * POST /api/scrape {url} — fetch a static page and ingest its log-like lines
 * exactly like a CSV upload. Reuses the UploadResponse contract; `filename`
 * carries the source URL. Mock mode needs the backend, so it throws.
 */
export const scrapeUrl = (
  url: string,
  onProgress?: (pct: number) => void,
): Promise<UploadResponse> => {
  if (USE_MOCK) {
    return Promise.reject(
      new Error("Fetching from a URL needs the backend. Set VITE_USE_MOCK=false."),
    );
  }
  onProgress?.(10);
  return request<UploadResponse>("/api/scrape", {
    method: "POST",
    body: JSON.stringify({ url }),
  }).then((res) => {
    // Extraction finished server-side; classification continues in the
    // background on /api/upload/{id}/status (the hook polls from here).
    onProgress?.(40);
    return res;
  });
};

// --- Anomalies -------------------------------------------------------------

export const getClusters = (): Promise<ClustersResponse> =>
  request("/api/anomalies/clusters");

export const labelCluster = (
  clusterId: number,
  category: string,
  notes = "",
): Promise<{ saved: boolean; training_example_id: number }> =>
  request(`/api/anomalies/clusters/${clusterId}/label`, {
    method: "POST",
    body: JSON.stringify({ category, notes }),
  });

// --- Metrics ---------------------------------------------------------------

export const getMetrics = (): Promise<MetricsResponse> => request("/api/metrics");

// --- Mock switch (VITE_USE_MOCK=true keeps the UI usable without a backend) --

const typedMock = mockApi as Record<string, (...args: any[]) => Promise<any>>;

type ApiFunction = (...args: any[]) => Promise<any>;

function withMock<T extends ApiFunction>(real: T, name: string): T {
  const mock = typedMock[name];
  if (USE_MOCK && mock) {
    return (async (...args: Parameters<T>) => mock(...args)) as T;
  }
  return real;
}

export const api = {
  getHealth: withMock(getHealth, "getHealth"),
  getDashboardStats: withMock(getDashboardStats, "getDashboardStats"),
  getTimeseries: withMock(getTimeseries, "getTimeseries"),
  getIncidents: withMock(getIncidents, "getIncidents"),
  getIncident: withMock(getIncident, "getIncident"),
  updateIncidentStatus: withMock(updateIncidentStatus, "updateIncidentStatus"),
  classifyText: withMock(classifyText, "classifyText"),
  uploadLogs: withMock(uploadLogs, "uploadLogs"),
  getUploadStatus: withMock(getUploadStatus, "getUploadStatus"),
  scrapeUrl, // handles mock mode itself (throws the guidance error)
  getClusters: withMock(getClusters, "getClusters"),
  labelCluster: withMock(labelCluster, "labelCluster"),
  getMetrics: withMock(getMetrics, "getMetrics"),
};
