/**
 * SmartLog AI — data hooks.
 *
 * Every read is a TanStack Query hook; every mutation invalidates the
 * affected queries. All call sites get loading/empty/error states for free.
 */

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../lib/api";
import { createStreamClient } from "../lib/ws";
import type {
  ClassificationResult,
  Incident,
  IncidentFilters,
  IncidentStatus,
  StreamFrame,
} from "../types";

// --- Reads -------------------------------------------------------------------

export const useStats = () =>
  useQuery({ queryKey: ["stats"], queryFn: api.getDashboardStats });

export const useTimeseries = (days = 7) =>
  useQuery({ queryKey: ["timeseries", days], queryFn: () => api.getTimeseries(days) });

export const useIncidents = (filters: IncidentFilters = {}) =>
  useQuery({
    queryKey: ["incidents", filters],
    queryFn: () => api.getIncidents(filters),
  });

export const useIncident = (id: number | null) =>
  useQuery({
    queryKey: ["incident", id],
    queryFn: () => api.getIncident(id as number),
    enabled: id !== null,
  });

export const useClusters = () =>
  useQuery({ queryKey: ["clusters"], queryFn: api.getClusters });

export const useMetrics = () =>
  useQuery({ queryKey: ["metrics"], queryFn: api.getMetrics });

// --- Mutations ----------------------------------------------------------------

export const useUpdateIncidentStatus = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: IncidentStatus }) =>
      api.updateIncidentStatus(id, status),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["incidents"] });
      void qc.invalidateQueries({ queryKey: ["incident"] });
      void qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });
};

export const useClassify = () =>
  useMutation({
    mutationFn: (text: string): Promise<ClassificationResult> => api.classifyText(text),
  });

export const useLabelCluster = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ clusterId, category, notes }: { clusterId: number; category: string; notes?: string }) =>
      api.labelCluster(clusterId, category, notes),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["clusters"] }),
  });
};

/**
 * Upload with progress: POST the file, then poll /api/upload/{id}/status.
 * Returns the increasing progress state for the progress bar.
 */
export interface UploadProgress {
  uploadId: number | null;
  status: "idle" | "uploading" | "processing" | "done" | "failed";
  processed: number;
  total: number;
  incidentsCreated: number;
  filename: string;
}

export const useUpload = () => {
  const qc = useQueryClient();
  const [progress, setProgress] = useState<UploadProgress>({
    uploadId: null,
    status: "idle",
    processed: 0,
    total: 0,
    incidentsCreated: 0,
    filename: "",
  });
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = null;
  };

  const startPolling = (uploadId: number) => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const status = await api.getUploadStatus(uploadId);
        setProgress((prev) => ({
          ...prev,
          status: status.status === "done" ? "done" : status.status === "failed" ? "failed" : "processing",
          processed: status.processed,
          total: status.total,
          incidentsCreated: status.incidents_created,
        }));
        if (status.status !== "processing") {
          stopPolling();
          if (status.status === "done") {
            void qc.invalidateQueries({ queryKey: ["incidents"] });
            void qc.invalidateQueries({ queryKey: ["stats"] });
          }
        }
      } catch {
        /* transient poll error: keep trying until the interval is cleared */
      }
    }, 500);
  };

  useEffect(() => stopPolling, []);

  const mutation = useMutation({
    mutationFn: (file: File) => {
      setProgress((prev) => ({ ...prev, status: "uploading", filename: file.name }));
      return api.uploadLogs(file);
    },
    onSuccess: (res) => {
      setProgress((prev) => ({
        ...prev,
        uploadId: res.upload_id,
        total: res.total_lines,
        status: "processing",
        filename: res.filename,
      }));
      startPolling(res.upload_id);
    },
    onError: () => setProgress((prev) => ({ ...prev, status: "failed" })),
  });

  return { upload: mutation.mutate, uploading: mutation.isPending, progress };
};

// --- Live stream ----------------------------------------------------------------

export const useStream = (paused = false) => {
  const [buffer, setBuffer] = useState<Incident[]>([]);
  const [connected, setConnected] = useState(false);
  const clientRef = useRef<ReturnType<typeof createStreamClient> | null>(null);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  useEffect(() => {
    const client = createStreamClient({
      onFrame: (frame: StreamFrame) => {
        if (frame.type === "incident" && !pausedRef.current) {
          // newest first, capped so the Live Monitor table stays bounded
          setBuffer((prev) => [frame.data, ...prev].slice(0, 200));
        }
      },
      onOpen: () => setConnected(true),
      onClose: () => setConnected(false),
    });
    clientRef.current = client;
    return () => {
      client.close();
      clientRef.current = null;
    };
  }, []);

  return { events: buffer, connected, clear: () => setBuffer([]) };
};
