/**
 * Shared loading / error / empty state blocks.
 * Every API call site renders one of these while it waits or fails,
 * per the "every call has loading, empty and error states" requirement.
 */

import type { ReactNode } from "react";
import { Skeleton } from "./ui/primitives";

export function LoadingBlock({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-9 w-full" />
      ))}
    </div>
  );
}

export function ErrorBlock({ error, retry }: { error: unknown; retry?: () => void }) {
  const message =
    error instanceof Error ? error.message : "Something went wrong fetching data.";
  return (
    <div className="rounded-md border p-6 text-center text-[13px] space-y-2">
      <p className="text-red-700">{message}</p>
      {retry && (
        <button className="text-teal-700 underline" onClick={retry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyBlock({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div className="rounded-md border p-6 text-center text-[13px] text-muted space-y-1">
      <p>{message}</p>
      {action}
    </div>
  );
}
