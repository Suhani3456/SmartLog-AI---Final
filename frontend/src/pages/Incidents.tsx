/**
 * Incidents: filterable, sortable, paginated table with CSV export and the
 * detail drawer. Detail content (root-cause timeline etc.) is Phase 7 polish.
 */

import { useMemo, useState } from "react";
import { Button } from "../components/ui/button";
import { Badge, Input, Select, SeverityDot, Table, TBody, Td, THead, Th } from "../components/ui/primitives";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "../components/StateBlock";
import { useIncidents } from "../hooks/useApi";
import { IncidentDrawer } from "../components/IncidentDrawer";
import { CATEGORIES, SEVERITIES, STATUSES, type Incident } from "../types";

export default function IncidentsPage() {
  const [page, setPage] = useState(1);
  const [severity, setSeverity] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("timestamp");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [selected, setSelected] = useState<number | null>(null);

  const filters = useMemo(
    () => ({ page, page_size: 20, severity, category, status, search, sortBy, sortDir }),
    [page, severity, category, status, search, sortBy, sortDir],
  );
  const query = useIncidents(filters);

  function exportCsv() {
    const rows = query.data?.items ?? [];
    const header = ["id", "timestamp", "source", "level", "category", "severity", "confidence", "classified_by", "status", "raw_text"];
    const csv = [
      header.join(","),
      ...rows.map((r) =>
        [r.id, r.timestamp, r.source, r.level, r.category, r.severity, r.confidence, r.classified_by, r.status, `"${r.raw_text.replaceAll('"', '""')}"`].join(","),
      ),
    ].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "incidents.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          placeholder="Search raw text…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          className="w-56 h-8"
        />
        <Select value={severity} onChange={(e) => { setSeverity(e.target.value); setPage(1); }} className="h-8">
          <option value="">All severities</option>
          {SEVERITIES.map((s) => <option key={s}>{s}</option>)}
        </Select>
        <Select value={category} onChange={(e) => { setCategory(e.target.value); setPage(1); }} className="h-8">
          <option value="">All categories</option>
          {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
        </Select>
        <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="h-8">
          <option value="">All statuses</option>
          {STATUSES.map((s) => <option key={s}>{s}</option>)}
        </Select>
        <Button size="sm" variant="secondary" onClick={exportCsv}>Export CSV</Button>
      </div>

      {query.isLoading && <LoadingBlock rows={6} />}
      {query.isError && <ErrorBlock error={query.error} retry={() => query.refetch()} />}

      {query.data && query.data.items.length === 0 && (
        <EmptyBlock
          message="No incidents match these filters."
          action={<button className="text-teal-700 underline" onClick={() => { setSeverity(""); setCategory(""); setStatus(""); setSearch(""); }}>Clear filters</button>}
        />
      )}

      {query.data && query.data.items.length > 0 && (
        <Table>
          <THead>
            <tr>
              {([
                ["timestamp", "Time"], ["source", "Source"], ["category", "Category"],
                ["severity", "Severity"], ["confidence", "Conf"], ["detection_ms", "ms"], ["status", "Status"],
              ] as const).map(([key, label]) => (
                <Th
                  key={key}
                  className={`cursor-pointer select-none ${key === "confidence" || key === "detection_ms" ? "text-right" : ""}`}
                  onClick={() => {
                    if (sortBy === key) setSortDir(sortDir === "asc" ? "desc" : "asc");
                    else { setSortBy(key); setSortDir("desc"); }
                  }}
                >
                  {label}{sortBy === key ? (sortDir === "asc" ? " ↑" : " ↓") : ""}
                </Th>
              ))}
            </tr>
          </THead>
          <TBody>
            {query.data.items.map((it: Incident) => (
              <tr key={it.id} className="cursor-pointer hover:bg-slate-50" onClick={() => setSelected(it.id)}>
                <Td className="font-mono text-[12px] whitespace-nowrap">{new Date(it.timestamp).toLocaleString()}</Td>
                <Td>{it.source}</Td>
                <Td>{it.category}</Td>
                <Td>
                  <span className="flex items-center gap-1.5">
                    <SeverityDot severity={it.severity} /> {it.severity}
                  </span>
                </Td>
                <Td className="text-right font-mono">{it.confidence.toFixed(2)}</Td>
                <Td className="text-right font-mono">{it.detection_ms}</Td>
                <Td><Badge tone="neutral">{it.status}</Badge></Td>
              </tr>
            ))}
          </TBody>
        </Table>
      )}

      {query.data && query.data.total > 0 && (
        <div className="flex items-center justify-between text-[12px] text-muted">
          <span>Page {page} of {Math.max(1, Math.ceil(query.data.total / query.data.page_size))} · {query.data.total} total</span>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</Button>
            <Button size="sm" variant="secondary" disabled={page >= Math.ceil(query.data.total / query.data.page_size)} onClick={() => setPage(page + 1)}>Next</Button>
          </div>
        </div>
      )}

      <IncidentDrawer incidentId={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
