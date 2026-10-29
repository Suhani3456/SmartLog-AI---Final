/**
 * Model performance page: metrics strip, confusion matrix (teal heatmap),
 * per-class table, baseline comparison and classifier usage bars.
 */

import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/primitives";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "../components/StateBlock";
import { useMetrics } from "../hooks/useApi";
import { StatStrip } from "../components/StatStrip";

export default function ModelPage() {
  const { data, isLoading, isError, error, refetch } = useMetrics();

  if (isLoading) return <LoadingBlock rows={6} />;
  if (isError) return <ErrorBlock error={error} retry={() => refetch()} />;
  if (!data) return <EmptyBlock message="No metrics saved yet. Run backend/train.py." />;

  const pct = (x: number) => `${(x * 100).toFixed(1)}%`;
  const maxCount = Math.max(1, ...data.confusion_matrix.matrix.flat());

  return (
    <div className="space-y-4">
      <StatStrip
        items={[
          { label: "Accuracy", value: pct(data.accuracy) },
          { label: "Macro F1", value: pct(data.f1_macro) },
          { label: "Trained", value: new Date(data.trained_at).toLocaleDateString() },
          { label: "Classes", value: String(data.per_class.length) },
        ]}
      />

      <Card>
        <CardHeader><CardTitle>Confusion matrix</CardTitle></CardHeader>
        <CardContent>
          <div className="overflow-auto">
            <table className="text-[11px] font-mono tabular-nums">
              <thead>
                <tr>
                  <th />
                  {data.confusion_matrix.labels.map((l) => (
                    <th key={l} className="px-1 pb-1 font-normal text-muted">
                      <span className="block w-16 truncate" title={l}>{l}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.confusion_matrix.matrix.map((row, i) => (
                  <tr key={i}>
                    <th className="pr-2 text-right font-normal text-muted max-w-[120px] truncate" title={data.confusion_matrix.labels[i]}>
                      {data.confusion_matrix.labels[i]}
                    </th>
                    {row.map((count, j) => {
                      const intensity = maxCount > 0 ? count / maxCount : 0;
                      return (
                        <td key={j} className="p-0">
                          <div
                            className="flex h-9 w-16 items-center justify-center border border-surface text-[11px]"
                            title={`${data.confusion_matrix.labels[i]} → ${data.confusion_matrix.labels[j]}: ${count}`}
                            style={{
                              background: `rgba(15, 118, 110, ${0.08 + 0.7 * intensity})`,
                              color: intensity > 0.5 ? "#fff" : "inherit",
                            }}
                          >
                            {count}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Per-class precision / recall / F1</CardTitle></CardHeader>
        <CardContent>
          <table className="w-full text-[13px]" style={{ fontVariantNumeric: "tabular-nums" }}>
            <thead>
              <tr className="text-[11px] uppercase text-muted border-b">
                <th className="py-1 text-left">Category</th>
                <th className="text-right">Precision</th>
                <th className="text-right">Recall</th>
                <th className="text-right">F1</th>
                <th className="text-right">Support</th>
              </tr>
            </thead>
            <tbody>
              {data.per_class.map((c) => (
                <tr key={c.category} className="border-b last:border-0">
                  <td className="py-1.5">{c.category}</td>
                  <td className="text-right font-mono">{c.precision.toFixed(3)}</td>
                  <td className="text-right font-mono">{c.recall.toFixed(3)}</td>
                  <td className="text-right font-mono">{c.f1.toFixed(3)}</td>
                  <td className="text-right font-mono">{c.support}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader><CardTitle>Rule-based vs ML vs Hybrid</CardTitle></CardHeader>
          <CardContent>
            <table className="w-full text-[13px]" style={{ fontVariantNumeric: "tabular-nums" }}>
              <thead>
                <tr className="text-[11px] uppercase text-muted border-b">
                  <th className="py-1 text-left">Approach</th><th className="text-right">F1</th><th className="text-right">False alert rate</th>
                </tr>
              </thead>
              <tbody>
                {data.baseline_comparison.map((b) => (
                  <tr key={b.approach} className="border-b last:border-0">
                    <td className="py-1.5">{b.approach}</td>
                    <td className="text-right font-mono">{b.f1.toFixed(3)}</td>
                    <td className="text-right font-mono">{pct(b.false_alert_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Classifier usage</CardTitle></CardHeader>
          <CardContent>
            <ul className="space-y-2 text-[13px]">
              {data.classifier_usage.map((u) => (
                <li key={u.classified_by} className="flex items-center gap-3">
                  <span className="w-28 text-muted">{u.classified_by}</span>
                  <div className="flex-1 h-1.5 rounded bg-border overflow-hidden">
                    <div className="h-full bg-teal-700" style={{ width: `${u.share * 100}%` }} />
                  </div>
                  <span className="font-mono w-12 text-right">{pct(u.share)}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
