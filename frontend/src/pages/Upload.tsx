/**
 * Upload page: drag-and-drop (input fallback), preview, progress bar and a
 * results summary linking to Incidents.
 */

import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/primitives";
import { useUpload } from "../hooks/useApi";
import { cn } from "../lib/utils";

export default function UploadPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const { upload, uploading, progress } = useUpload();

  const accept = (f: File) => {
    if (/\.(log|txt|csv)$/i.test(f.name)) setFile(f);
  };

  return (
    <div className="max-w-2xl space-y-4">
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

      {progress.status !== "idle" && (
        <Card>
          <CardContent className="p-4 space-y-2">
            <div className="flex justify-between text-[13px]">
              <span className="font-mono">{progress.filename || file?.name}</span>
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
              {progress.status === "processing" && `Classifying… ${progress.processed} of ${progress.total} lines.`}
              {progress.status === "done" && (
                <span>
                  Done. {progress.incidentsCreated} incidents created.{" "}
                  <Link to="/incidents" className="text-teal-700 underline">View them in Incidents</Link>.
                </span>
              )}
              {progress.status === "failed" && <span className="text-red-700">The backend couldn't process this file.</span>}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
