/**
 * Classify demo page: textarea, example logs, pipeline stepper, result card.
 */

import { useState } from "react";
import { Button } from "../components/ui/button";
import { Badge, Card, CardContent, CardHeader, CardTitle, SeverityDot, Textarea } from "../components/ui/primitives";
import { ErrorBlock, LoadingBlock } from "../components/StateBlock";
import { useClassify } from "../hooks/useApi";
import { cn } from "../lib/utils";

const EXAMPLES = [
  "2026-10-30 09:14:22 crm-app-03 db: connection timeout after 30s, req_id=a41f2c Traceback (most recent call last): OperationalError",
  "2026-10-30 09:15:03 billing-api-02 payment: transaction declined, gateway returned code 05",
  "2026-10-30 09:16:41 hrms-web-01 user logged in, user_id=1042 session started",
  "2026-10-30 09:18:12 node-07 api: upstream timed out retrieving /v2/orders after 3 retries",
  "2026-10-30 09:21:57 crm-app-01 auth: brute force suspected from 10.2.44.9, acl triggered, 41 failed logins",
  "2026-10-30 09:25:10 node-02 jvm: heap usage 94% after full garbage collection, mem pool pressure high",
] as const;

export default function ClassifyPage() {
  const [text, setText] = useState("");
  const classify = useClassify();

  const trace = classify.data?.pipeline_trace || [];

  return (
    <div className="grid grid-cols-[1fr_380px] gap-4">
      <div className="space-y-3">
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste a raw log line here…"
          className="font-mono text-[12px] min-h-[140px]"
        />
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((ex, i) => (
            <Button key={i} size="sm" variant="secondary" onClick={() => setText(ex)}>
              Example {i + 1}
            </Button>
          ))}
          <Button size="sm" disabled={!text.trim() || classify.isPending} onClick={() => classify.mutate(text)}>
            Classify
          </Button>
        </div>

        {classify.isPending && <LoadingBlock rows={3} />}
        {classify.isError && <ErrorBlock error={classify.error} retry={() => classify.mutate(text)} />}
      </div>

      <Card>
        <CardHeader><CardTitle>Result</CardTitle></CardHeader>
        <CardContent>
          {!classify.data && !classify.isPending && (
            <p className="text-[13px] text-muted">Classify a log line to see the pipeline trace.</p>
          )}
          {classify.data && (
            <div className="space-y-4 text-[13px]">
              <div className="flex items-center gap-2">
                <SeverityDot severity={classify.data.severity} />
                <span className="font-medium">{classify.data.category}</span>
                <Badge tone={classify.data.is_known ? "neutral" : "Unknown"}>
                  {classify.data.is_known ? "known" : "unknown anomaly"}
                </Badge>
              </div>

              {/* Pipeline stepper */}
              <div>
                <div className="text-[11px] uppercase tracking-wide text-muted mb-2">Pipeline</div>
                <ol className="flex items-center gap-0">
                  {trace.map((stage, i) => {
                    const isDeciding = stage.matched && classify.data?.classified_by && 
                      ((stage.stage === "Regex" && classify.data.classified_by === "Regex") ||
                       (stage.stage === "BERT+LogReg" && classify.data.classified_by === "BERT+LogReg") ||
                       (stage.stage === "DBSCAN" && classify.data.classified_by === "DBSCAN") ||
                       (stage.stage === "LLM" && classify.data.classified_by === "LLM"));
                    const isSkipped = !stage.matched && i > 0 && trace.slice(0, i).some(s => s.matched);
                    return (
                      <li key={i} className="flex items-center flex-1">
                        <div className="flex flex-col items-center flex-1">
                          <div className="flex items-center w-full">
                            <div className={cn(
                              "h-5 w-5 rounded-full border flex items-center justify-center text-[11px]",
                              isDeciding ? "border-accent bg-accent text-accent-foreground" : 
                                stage.matched ? "border-accent/60 text-accent" :
                                isSkipped ? "border-border text-muted" : "border-border text-muted"
                            )}>
                              {i + 1}
                            </div>
                            {i < trace.length - 1 && <div className="flex-1 h-px bg-border" />}
                          </div>
                          <div className="mt-1 text-center">
                            <div className={cn("text-[11px]", isDeciding ? "text-accent" : isSkipped ? "text-muted" : "text-text")}>
                              {stage.stage}
                            </div>
                            {isSkipped ? (
                              <div className="text-[10px] text-muted">Skipped</div>
                            ) : stage.score > 0 ? (
                              <div className="text-[10px] font-mono text-muted">{stage.score.toFixed(2)}</div>
                            ) : null}
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ol>
              </div>

              <div>
                <div className="text-[11px] uppercase tracking-wide text-muted mb-1">Confidence</div>
                <div className="flex items-center gap-2">
                  <div className="h-1.5 flex-1 rounded-sm bg-border overflow-hidden">
                    <div className="h-full bg-accent" style={{ width: `${classify.data.confidence * 100}%` }} />
                  </div>
                  <span className="font-mono text-[12px] tabular-nums">{(classify.data.confidence * 100).toFixed(0)}%</span>
                </div>
              </div>

              <div>
                <div className="text-[11px] uppercase tracking-wide text-muted mb-1">Cleaned text</div>
                <p className="font-mono text-[11px] rounded-[4px] border border-border bg-subtle p-2 whitespace-pre-wrap break-words">
                  {classify.data.cleaned_text || "—"}
                </p>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wide text-muted mb-1">Explanation</div>
                <p className="text-[12px] leading-relaxed">{classify.data.explanation}</p>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wide text-muted mb-1">Remediation</div>
                <p className="text-[12px] leading-relaxed">{classify.data.remediation}</p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
