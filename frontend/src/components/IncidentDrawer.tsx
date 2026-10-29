/**
 * Shared incident detail drawer (raw + normalized log, trace, remediation
 * plus the status workflow). Used by the Live Monitor and Incidents pages.
 */

import { Badge, Drawer, SeverityDot } from "./ui/primitives";
import { Button } from "./ui/button";
import { useIncident, useUpdateIncidentStatus } from "../hooks/useApi";
import type { IncidentStatus } from "../types";

export function IncidentDrawer({ incidentId, onClose }: {
  incidentId: number | null;
  onClose: () => void;
}) {
  const { data: incident, isLoading, error } = useIncident(incidentId);
  const updateStatus = useUpdateIncidentStatus();

  const badgeTone = (s: string) =>
    ["Critical", "High", "Medium", "Low"].includes(s) ? s : "Unknown";

  return (
    <Drawer
      open={incidentId !== null}
      onClose={onClose}
      title={incident ? `Incident #${incident.id}` : "Incident"}
    >
      {isLoading && <p className="text-muted text-[13px]">Loading incident…</p>}
      {error && <p className="text-[13px] text-red-700">Couldn't load this incident. Try again.</p>}
      {incident && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <SeverityDot severity={incident.severity} />
            <span className="font-medium">{incident.category}</span>
            <Badge tone={badgeTone(incident.severity)}>{incident.severity}</Badge>
            <Badge tone="neutral">{incident.status}</Badge>
            <Badge tone={incident.is_known ? "neutral" : "Unknown"}>
              {incident.is_known ? "known" : "unknown anomaly"}
            </Badge>
          </div>

          <div className="grid grid-cols-2 gap-y-1 text-[12px] text-muted">
            <div>Source</div><div className="text-text">{incident.source} ({incident.level})</div>
            <div>Timestamp</div><div className="font-mono text-text">{incident.timestamp}</div>
            <div>Confidence</div><div className="font-mono text-text">{(incident.confidence * 100).toFixed(0)}%</div>
            <div>Classified by</div><div className="text-text">{incident.classified_by}</div>
            <div>Detection</div><div className="font-mono text-text">{incident.detection_ms} ms</div>
          </div>

          <div>
            <div className="text-xs text-muted mb-1">Raw log</div>
            <pre className="overflow-auto rounded-md border bg-bg p-3 font-mono text-[12px] whitespace-pre-wrap">
              {incident.raw_text}
            </pre>
          </div>

          <div>
            <div className="text-xs text-muted mb-1">Cleaned text</div>
            <p className="rounded-md border bg-bg p-3 font-mono text-[12px]">{incident.cleaned_text || "—"}</p>
          </div>

          <div>
            <div className="text-xs text-muted mb-1">Pipeline trace</div>
            <ul className="space-y-1 text-[12px]">
              {incident.pipeline_trace.map((s, i) => (
                <li key={i}>
                  <span className="font-mono">{s.stage}</span>{" "}
                  <span className={s.matched ? "text-teal-700" : "text-muted"}>
                    {s.matched ? `matched (${s.score.toFixed(2)})` : "no match"}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <div className="text-xs text-muted mb-1">Explanation</div>
            <p className="text-[13px]">{incident.explanation}</p>
          </div>
          <div>
            <div className="text-xs text-muted mb-1">Remediation</div>
            <p className="text-[13px]">{incident.remediation || "—"}</p>
          </div>

          <div className="border-t pt-3">
            <div className="text-xs text-muted mb-2">Status</div>
            <div className="flex gap-2">
              {(["Open", "Acknowledged", "Resolved"] as IncidentStatus[]).map((s) => (
                <Button
                  key={s}
                  size="sm"
                  variant={incident.status === s ? "default" : "outline"}
                  disabled={updateStatus.isPending || incident.status === s}
                  onClick={() => updateStatus.mutate({ id: incident.id, status: s })}
                >
                  {s}
                </Button>
              ))}
            </div>
          </div>
        </>
      )}
    </Drawer>
  );
}
