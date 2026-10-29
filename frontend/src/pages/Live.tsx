/**
 * Live Monitor: real log viewer per design brief.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "../components/ui/button";
import { Input, SeverityDot, Select } from "../components/ui/primitives";
import { EmptyBlock } from "../components/StateBlock";
import { useStream } from "../hooks/useApi";
import { IncidentDrawer } from "../components/IncidentDrawer";
import type { Incident } from "../types";
import { cn } from "../lib/utils";

export default function LivePage() {
  const [paused, setPaused] = useState(false);
  const { events, connected, clear } = useStream(paused);
  const [selected, setSelected] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [showJump, setShowJump] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const [atBottom, setAtBottom] = useState(true);

  const filtered = useMemo(
    () =>
      events.filter((e: Incident) => {
        if (category && e.category !== category) return false;
        if (search && !e.raw_text.toLowerCase().includes(search.toLowerCase())) return false;
        return true;
      }),
    [events, search, category],
  );

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onScroll = () => {
      const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
      setAtBottom(nearBottom);
      setShowJump(!nearBottom);
    };
    el.addEventListener("scroll", onScroll);
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (atBottom && !paused && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [filtered.length, atBottom, paused]);

  const jumpToLatest = () => {
    const el = containerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
      setAtBottom(true);
      setShowJump(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="flex items-center gap-1.5 text-[12px] text-muted">
          <span
            className={cn("inline-block h-1.5 w-1.5 rounded-full", connected ? "bg-emerald-500" : "bg-muted")}
          />
          {connected ? "Streaming" : "Disconnected"}
        </span>
        <Button size="sm" variant={paused ? "primary" : "secondary"} onClick={() => setPaused((p) => !p)}>
          {paused ? "Resume" : "Pause"}
        </Button>
        <Input
          placeholder="Search raw text…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-56 h-8"
        />
        <Select value={category} onChange={(e) => setCategory(e.target.value)} className="h-8">
          <option value="">All categories</option>
          {["Database Error", "API Failure", "Login Failure", "Payment Issue", "Security Alert", "Resource Usage", "Workflow Error", "User Action", "Unknown"].map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </Select>
        <Button size="sm" variant="ghost" onClick={clear}>Clear</Button>
      </div>

      {paused && events.length > 0 && (
        <p className="text-[12px] text-muted">Paused. {events.length} events waiting.</p>
      )}

      <div className="border border-border rounded-[6px] bg-surface overflow-hidden relative">
        <div ref={containerRef} className="max-h-[600px] overflow-auto">
          {filtered.length === 0 ? (
            <EmptyBlock message="Waiting for events from the stream… The backend replays sample logs every few seconds." />
          ) : (
            <table className="w-full text-[12px]">
              <thead className="sticky top-0 bg-subtle/40 border-b border-border">
                <tr className="text-[11px] uppercase tracking-wide text-muted">
                  <th className="px-3 py-1.5 text-left font-medium">Time</th>
                  <th className="px-3 py-1.5 text-left font-medium">Source</th>
                  <th className="px-3 py-1.5 text-left font-medium">Level</th>
                  <th className="px-3 py-1.5 text-left font-medium">Message</th>
                  <th className="px-3 py-1.5 text-left font-medium">Category</th>
                  <th className="px-3 py-1.5 text-left font-medium">Sev</th>
                  <th className="px-3 py-1.5 text-right font-medium">Conf</th>
                  <th className="px-3 py-1.5 text-right font-medium">By</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {filtered.map((e) => (
                  <tr
                    key={e.id}
                    className="cursor-pointer border-b border-border last:border-0 hover:bg-subtle/30 transition-opacity duration-150 animate-in fade-in"
                    onClick={() => setSelected(e.id)}
                  >
                    <td className="px-3 py-1.5 whitespace-nowrap text-[12px]">{new Date(e.timestamp).toLocaleTimeString()}</td>
                    <td className="px-3 py-1.5 text-[12px]">{e.source}</td>
                    <td className={cn("px-3 py-1.5 text-[12px]", e.level === "ERROR" || e.level === "CRITICAL" ? "text-sev-critical" : e.level === "WARN" ? "text-sev-high" : "")}>{e.level}</td>
                    <td className="px-3 py-1.5 max-w-[320px] truncate text-[12px]">{e.raw_text}</td>
                    <td className="px-3 py-1.5 text-[12px]">{e.category}</td>
                    <td className="px-3 py-1.5"><SeverityDot severity={e.severity} /></td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-[12px]">{e.confidence.toFixed(2)}</td>
                    <td className="px-3 py-1.5 text-right text-muted text-[12px]">{e.classified_by}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        {showJump && (
          <button
            onClick={jumpToLatest}
            className="absolute bottom-2 left-1/2 -translate-x-1/2 px-2 py-1 text-[11px] bg-surface border border-border rounded-sm shadow-sm"
          >
            Jump to latest
          </button>
        )}
      </div>

      <IncidentDrawer incidentId={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
