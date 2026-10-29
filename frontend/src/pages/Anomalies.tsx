/**
 * Anomaly Explorer: DBSCAN scatter (ScatterChart) + cluster side list with
 * the "Label cluster" flow.
 */

import { useState } from "react";
import {
  CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";
import { Button } from "../components/ui/button";
import { Badge, Card, CardContent, CardHeader, CardTitle, Select } from "../components/ui/primitives";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "../components/StateBlock";
import { useClusters, useLabelCluster } from "../hooks/useApi";
import { CATEGORIES } from "../types";

function ClusterDialog({ clusterId, onSubmit, busy }: {
  clusterId: number;
  onSubmit: (category: string) => void;
  busy: boolean;
}) {
  const [category, setCategory] = useState("");
  return (
    <div className="space-y-2 border rounded-md p-3">
      <div className="text-[13px] font-medium">Label cluster {clusterId}</div>
      <Select value={category} onChange={(e) => setCategory(e.target.value)}>
        <option value="">Choose a category…</option>
        {CATEGORIES.filter((c) => c !== "Unknown").map((c) => <option key={c}>{c}</option>)}
      </Select>
      <Button size="sm" disabled={!category || busy} onClick={() => onSubmit(category)}>
        Save label
      </Button>
    </div>
  );
}

export default function AnomaliesPage() {
  const { data, isLoading, isError, error, refetch } = useClusters();
  const label = useLabelCluster();
  const [labeled, setLabeled] = useState<number | null>(null);

  if (isLoading) return <LoadingBlock rows={5} />;
  if (isError) return <ErrorBlock error={error} retry={() => refetch()} />;
  if (!data || data.points.length === 0) {
    return <EmptyBlock message="No anomaly data yet. Run the pipeline on a batch of unknown logs." />;
  }

  const known = data.points.filter((p) => !p.noise);
  const noise = data.points.filter((p) => p.noise);

  return (
    <div className="grid grid-cols-[1fr_340px] gap-4">
      <Card>
        <CardHeader><CardTitle>DBSCAN scatter (2D PCA)</CardTitle></CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={420}>
            <ScatterChart>
              <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="2 2" />
              <XAxis dataKey="x" type="number" tick={{ fontSize: 11 }} stroke="hsl(var(--muted))" />
              <YAxis dataKey="y" type="number" tick={{ fontSize: 11 }} width={30} stroke="hsl(var(--muted))" />
              <ZAxis range={[20, 20]} />
              <Tooltip contentStyle={{ background: "hsl(var(--surface))", border: "1px solid hsl(var(--border))", fontSize: "12px" }} />
              <Scatter name="clustered" data={known} fill="hsl(var(--muted))" fillOpacity={0.8} />
              <Scatter name="noise" data={noise} fill="hsl(var(--sev-unknown))" fillOpacity={0.9} />
            </ScatterChart>
          </ResponsiveContainer>
          <p className="text-[12px] text-muted mt-1">
            Muted dots: clustered unknowns. Violet dots: noise (no cluster; flagged as true anomalies).
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Clusters</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {data.clusters.map((c) => (
            <div key={c.cluster_id} className="space-y-2 rounded-md border p-3">
              <div className="flex items-center gap-2 text-[13px]">
                <span className="font-mono">#{c.cluster_id}</span>
                <Badge tone={c.is_noise ? "Unknown" : "neutral"}>
                  {c.is_noise ? "noise" : `cluster · ${c.size}`}
                </Badge>
                {c.labeled_category && <Badge tone="accent">{c.labeled_category}</Badge>}
              </div>
              {c.sample_logs.slice(0, 2).map((log, i) => (
                <p key={i} className="font-mono text-[12px] text-muted truncate" title={log}>{log}</p>
              ))}
              {labeled === c.cluster_id ? (
                <ClusterDialog
                  clusterId={c.cluster_id}
                  busy={label.isPending}
                  onSubmit={(cat) =>
                    label.mutate(
                      { clusterId: c.cluster_id, category: cat },
                      { onSuccess: () => setLabeled(null) },
                    )
                  }
                />
              ) : (
                <Button size="sm" variant="secondary" onClick={() => setLabeled(c.cluster_id)}>
                  Label cluster
                </Button>
              )}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
