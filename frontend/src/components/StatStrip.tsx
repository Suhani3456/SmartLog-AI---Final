export function StatStrip({
  items,
}: {
  items: Array<{ label: string; value: string | number; delta?: string }>;
}) {
  return (
    <div className="flex border border-border rounded-[6px] bg-surface divide-x divide-border">
      {items.map((item, idx) => (
        <div key={idx} className="flex-1 px-4 py-3">
          <div className="text-[11px] uppercase tracking-wide text-muted">{item.label}</div>
          <div className="mt-1 text-[24px] tabular-nums leading-none">{item.value}</div>
          {item.delta && <div className="mt-1 text-[11px] text-muted">{item.delta}</div>}
        </div>
      ))}
    </div>
  );
}
