/** Dashboard: stat strip, timeseries line chart, category bars, live feed. */

import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  useIncidents,
  useStats,
  useTimeseries,
} from "../hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle, SeverityDot } from "../components/ui/primitives";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "../components/StateBlock";
import { StatStrip } from "../components/StatStrip";

function formatDelta(v: number) {
  if (v === 0) return "0 since yesterday";
  const sign = v > 0 ? "▲" : "▼";
  return `${sign} ${Math.abs(v)} since yesterday`;
}

export default function DashboardPage() {
  const stats = useStats();
  const series = useTimeseries(7);
  const feed = useIncidents({ page: 1, page_size: 6, sortBy: "timestamp", sortDir: "desc" });

  if (stats.isLoading) return <LoadingBlock rows={5} />;
  if (stats.isError) return <ErrorBlock error={stats.error} retry={() => stats.refetch()} />;

  const s = stats.data!;

  return (
    <div className="space-y-4">
      <StatStrip
        items={[
          { label: "Logs", value: s.total_logs.toLocaleString(), delta: formatDelta(s.change_vs_prev_24h.logs) },
          { label: "Incidents", value: s.total_incidents, delta: formatDelta(s.change_vs_prev_24h.incidents) },
          { label: "Critical", value: s.critical_count, delta: formatDelta(s.change_vs_prev_24h.critical) },
          { label: "Unknown anomalies", value: s.unknown_anomalies },
          { label: "Avg detection", value: `${s.avg_detection_ms} ms` },
        ]}
      />

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader><CardTitle>Incidents over time</CardTitle></CardHeader>
          <CardContent>
            {series.isLoading ? (
              <LoadingBlock rows={3} />
            ) : series.isError ? (
              <ErrorBlock error={series.error} retry={() => series.refetch()} />
            ) : series.data!.points.every((p) => p.count === 0) ? (
              <EmptyBlock message="No data yet. Upload a log file on the Upload page." />
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={series.data!.points}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                  <XAxis dataKey="timestamp" tick={{ fontSize: 11 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11 }} width={30} />
                  <Tooltip />
                  <Line type="monotone" dataKey="count" stroke="#0f766e" strokeWidth={1.5} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>By category</CardTitle></CardHeader>
          <CardContent>
            {s.by_category.length === 0 ? (
              <EmptyBlock message="No data yet. Upload a log file on the Upload page." />
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={s.by_category} layout="vertical">
                  <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="category" width={100} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#5a8f89" radius={[0, 2, 2, 0]} barSize={10} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>By source</CardTitle></CardHeader>
          <CardContent>
            {s.by_source.length === 0 ? (
              <EmptyBlock message="No events by source yet." />
            ) : (
              <ul className="space-y-2 text-[13px]">
                {s.by_source.map((row) => (
                  <li key={row.source} className="flex items-center gap-3">
                    <span className="w-28 text-muted">{row.source}</span>
                    <div className="flex-1 h-1.5 rounded bg-border overflow-hidden">
                      <div
                        className="h-full bg-teal-700"
                        style={{ width: `${(row.count / Math.max(...s.by_source.map((x) => x.count))) * 100}%` }}
                      />
                    </div>
                    <span className="font-mono w-10 text-right">{row.count}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>By severity</CardTitle></CardHeader>
          <CardContent>
            {s.by_severity.length === 0 ? (
              <EmptyBlock message="No severity data yet." />
            ) : (
              <ul className="space-y-2 text-[13px]">
                {s.by_severity.map((row) => (
                  <li key={row.severity} className="flex items-center gap-2">
                    <SeverityDot severity={row.severity} />
                    <span className="w-16 text-muted">{row.severity}</span>
                    <span className="font-mono ml-auto">{row.count}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent incidents</CardTitle>
        </CardHeader>
        <CardContent>
          {feed.isLoading ? (
            <LoadingBlock rows={3} />
          ) : feed.isError ? (
            <ErrorBlock error={feed.error} retry={() => feed.refetch()} />
          ) : feed.data!.items.length === 0 ? (
            <EmptyBlock
              message="No data yet. Upload a log file on the Upload page."
              action={<Link to="/upload" className="text-teal-700 underline">Upload a log file</Link>}
            />
          ) : (
            <ul className="divide-y text-[13px]">
              {feed.data!.items.map((it) => (
                <li key={it.id} className="flex items-center gap-3 py-2">
                  <SeverityDot severity={it.severity} />
                  <span className="font-mono text-[12px] text-muted w-44 truncate">{it.timestamp}</span>
                  <span className="w-16 text-muted">{it.source}</span>
                  <span className="flex-1 font-mono truncate">{it.raw_text}</span>
                  <span className="text-muted">{it.category}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
