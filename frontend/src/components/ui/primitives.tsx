/**
 * Small shadcn/ui-style primitives used across pages during Phase 2.
 * (button.tsx lives separately; these are the table/badge/skeleton basics.)
 * The Phase 5+ design passes restyle via CSS variables only — these file's
 * structure stays stable.
 */

import * as React from "react";
import { cn } from "../../lib/utils";

// --- Card -------------------------------------------------------------------

export const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("rounded-[6px] border border-border bg-surface", className)} {...props} />
  ),
);
Card.displayName = "Card";

export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-4 pb-2", className)} {...props} />;
}

export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-[16px] font-medium", className)} {...props} />;
}

export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-4 pt-2", className)} {...props} />;
}

// --- Table -------------------------------------------------------------------

export function Table({ className, ...props }: React.TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-auto border border-border rounded-[6px] bg-surface">
      <table className={cn("w-full caption-bottom text-[13px]", className)} {...props} />
    </div>
  );
}

export function THead({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn("[&_th]:py-2 [&_th]:border-b [&_th]:border-border bg-subtle/40", className)} {...props} />;
}

export function TBody({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("[&_td]:py-2 [&_td]:border-b [&_td]:border-border last:[&_tr]:border-0 [&_tr]:h-[36px] hover:[&_tr]:bg-subtle/30", className)} {...props} />;
}

export const Th = React.forwardRef<HTMLTableCellElement, React.ThHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <th ref={ref} className={cn("text-left font-medium text-muted text-[11px] uppercase tracking-wide", className)} {...props} />
  ),
);
Th.displayName = "Th";

export const Td = React.forwardRef<HTMLTableCellElement, React.TdHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <td ref={ref} className={cn("py-2 align-middle", className)} {...props} />
  ),
);
Td.displayName = "Td";

// --- Badge --------------------------------------------------------------------

const BADGE_TONES: Record<string, string> = {
  Critical: "border-[#B42318]/30 bg-[#B42318]/5 text-[#B42318] dark:text-[#f87171]",
  High: "border-[#C2410C]/30 bg-[#C2410C]/5 text-[#C2410C] dark:text-[#fb923c]",
  Medium: "border-[#A16207]/30 bg-[#A16207]/5 text-[#A16207] dark:text-[#fbbf24]",
  Low: "border-[#475569]/30 bg-[#475569]/5 text-[#475569] dark:text-[#94a3b8]",
  Unknown: "border-[#6D5BA8]/30 bg-[#6D5BA8]/5 text-[#6D5BA8] dark:text-[#a78bfa]",
  neutral: "border-border bg-subtle text-muted",
  accent: "border-accent/30 bg-accent/5 text-accent",
};

export function Badge({
  tone = "neutral",
  className,
  ...props
}: { tone?: string } & React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-[4px] border px-1.5 py-0.5 text-[11px] font-medium",
        BADGE_TONES[tone] ?? BADGE_TONES.neutral,
        className,
      )}
      {...props}
    />
  );
}

/** 6px severity dot, per the design brief. */
export function SeverityDot({ severity }: { severity: string }) {
  const color =
    severity === "Critical" ? "bg-sev-critical" :
    severity === "High" ? "bg-sev-high" :
    severity === "Medium" ? "bg-sev-medium" :
    severity === "Low" ? "bg-sev-low" :
    "bg-sev-unknown";
  return <span className={cn("inline-block h-1.5 w-1.5 rounded-full align-middle", color)} aria-label={severity} />;
}

// --- Inputs ---------------------------------------------------------------------

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn("h-9 rounded-md border bg-surface px-3 text-[13px] outline-none focus:ring-2", className)}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn("min-h-[120px] w-full rounded-md border bg-surface p-3 text-[13px] font-mono outline-none focus:ring-2", className)}
      {...props}
    />
  ),
);
Textarea.displayName = "Textarea";

export function Select({ className, children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn("h-9 rounded-md border bg-surface px-2 text-[13px] outline-none focus:ring-2", className)}
      {...props}
    >
      {children}
    </select>
  );
}

// --- Misc -------------------------------------------------------------------------

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded bg-slate-200/70", className)} />;
}

export function Progress({ value, className }: { value: number; className?: string }) {
  return (
    <div className={cn("h-2 w-full overflow-hidden rounded bg-border", className)}>
      <div className="h-full bg-teal-600 transition-all" style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
    </div>
  );
}

/** Right-side drawer, 480px, for incident details. */
export function Drawer({ open, onClose, title, children }: {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  children: React.ReactNode;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-black/20" onClick={onClose} />
      <aside className="absolute right-0 top-0 flex h-full w-[480px] max-w-full flex-col overflow-auto border-l bg-surface shadow-sm">
        <div className="flex items-center justify-between border-b p-4">
          <div className="font-medium">{title}</div>
          <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
        </div>
        <div className="p-4 space-y-4">{children}</div>
      </aside>
    </div>
  );
}

// Button is used inside the drawer; import kept at bottom for readability.
import { Button } from "./button";
