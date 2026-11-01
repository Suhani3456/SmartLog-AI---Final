/**
 * Upload page: drag-and-drop (input fallback), preview, progress bar and a
 * results summary linking to Incidents. Feature 2 adds a "From URL" tab:
 * paste a URL, fetch it and classify the log-like lines exactly like a file
 * upload (same progress bar, same results summary).
 */

import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/primitives";
import { useScrapeUrl, useUpload } from "../hooks/useApi";
import { cn } from "../lib/utils";
import type { UploadProgress } from "../hooks/useApi";

type Tab = "file" | "url";

/** The shared progress + results summary card both ingest paths render. */
function ProgressSummary({
  progress,
  failedLabel,
  label,
}: {
  progress: UploadProgress;
  failedLabel: string;
  label: string;
}) {
  return (
    <Card>
      <CardContent className="p-4 space-y-2">
        <div className="flex justify-between text-[13px]">
          <span className="font-mono truncate" title={progress.filename || label}>
            {progress.filename || label}
          </span>
          {progress.total > 0 && (
            <span className="font-mono text-muted">{progress.processed}/{progress.total}</span>
          )}
        </div>
        <div className="h-2 rounded bg-border overflow-hidden">
          <div
            className="h-full bg-teal-700 transition-all"
            style={{ width: `${progress.total ? (progress.processed / progress.total) * 100 : 0}%` }}
          />
        </div>
        <p className="text-[13px] text-muted">
          {progress.status === "uploading" && "Fetching…"}
          {progress.status === "processing" && `Classifying… ${progress.processed} of ${progress.total} lines.`}
          {progress.status === "done" && (
            <span>
              Done. {progress.incidentsCreated} incidents created.{" "}
              <Link to="/incidents" className="text-teal-700 underline">View them in Incidents</Link>.
            </span>
          )}
          {progress.status === "failed" && <span className="text-red-700">{failedLabel}</span>}
        </p>
      </CardContent>
    </Card>
  );
}

export default function UploadPage() {
  const [tab, setTab] = useState<Tab>("file");
  const [url, setUrl] = useState("");
  const [urlError, setUrlError] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const { upload, uploading, progress: uploadProgress } = useUpload();
  const { scrape, scraping, progress: scrapeProgress, error: scrapeError } = useScrapeUrl();

  const accept = (f: File) => {
    if (/\.(log|txt|csv)$/i.test(f.name)) setFile(f);
  };

  const progress = tab === "url" && (scrapeProgress.status !== "idle") ? scrapeProgress : uploadProgress;

  const submitUrl = () => {
    if (!/^https?:\/\//.test(url.trim())) {
      // Client-side validation mirrors the backend's 400 contract; the
      // backend also validates, we only avoid the obvious mistakes early.
      setUrlError("That URL must start with http:// or https://.");
      return;
    }
    setUrlError(null);
    scrape(url.trim());
  };

  return (
    <div className="max-w-2xl space-y-4">
      {/* Tab strip, styled with the existing Button variants. The default tab
          keeps the file flow exactly as it was. */}
      <div className="flex gap-2">
        <Button
          size="sm"
          variant={tab === "file" ? "primary" : "secondary"}
          onClick={() => setTab("file")}
        >
          Upload file
        </Button>
        <Button
          size="sm"
          variant={tab === "url" ? "primary" : "secondary"}
          onClick={() => setTab("url")}
        >
          From URL
        </Button>
      </div>

      {tab === "file" ? (
        <>
          <div
            className={cn(
              "flex flex-col items-center justify-center rounded-md border border-dashed p-8 text-center text-[13px] text-muted",
              dragging && "border-teal-600 bg-teal-50",
            )}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); accept(e.dataTransfer.files[0]); }}
          >
            <p>Drop a .log, .txt or .csv file here (~500 lines work well).</p>
            <Button size="sm" variant="outline" className="mt-2" onClick={() => inputRef.current?.click()}>
              Choose file
            </Button>
            <input
              ref={inputRef}
              type="file"
              accept=".log,.txt,.csv"
              hidden
              onChange={(e) => e.target.files?.[0] && accept(e.target.files[0])}
            />
          </div>

          {file && (
            <Card>
              <CardContent className="p-4 space-y-2">
                <div className="flex items-center justify-between text-[13px]">
                  <span className="font-mono">{file.name}</span>
                  <span className="text-muted">{(file.size / 1024).toFixed(1)} KB</span>
                </div>
                <Button size="sm" disabled={uploading} onClick={() => upload(file)}>
                  {uploading ? "Uploading…" : "Start classification"}
                </Button>
              </CardContent>
            </Card>
          )}
        </>
      ) : (
        <>
          <Card>
            <CardContent className="p-4 space-y-2">
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  className="h-9 w-full rounded-md border bg-surface px-3 text-[13px] font-mono outline-none focus:ring-2"
                  placeholder="http://localhost:9000/logs.html"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") submitUrl(); }}
                />
                <Button size="sm" disabled={scraping || !url.trim()} onClick={submitUrl}>
                  {scraping ? "Fetching…" : "Fetch and classify"}
                </Button>
              </div>
              <p className="text-[12px] text-muted">
                Static pages only (plain text, JSON, or HTML that shows its logs server-side).
                The extracted lines are classified exactly like a file upload.
              </p>
            </CardContent>
          </Card>
          {urlError && (
            <p className="text-[13px] text-red-700">{urlError}</p>
          )}
        </>
      )}

      {progress.status !== "idle" && (
        <ProgressSummary
          progress={progress}
          label={tab === "url" ? url : (file?.name ?? "")}
          failedLabel={
            scrapeError instanceof Error && scrapeError.message
              ? scrapeError.message
              : "The backend couldn't process this request."
          }
        />
      )}
    </div>
  );
}
