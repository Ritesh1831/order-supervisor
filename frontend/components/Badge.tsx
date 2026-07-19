const COLORS: Record<string, string> = {
  running: "bg-emerald-100 text-emerald-700",
  paused: "bg-amber-100 text-amber-700",
  completed: "bg-slate-200 text-slate-600",
  terminated: "bg-rose-100 text-rose-700",
};

export function StatusBadge({ status }: { status: string }) {
  const cls = COLORS[status] ?? "bg-slate-100 text-slate-600";
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${cls}`}>{status}</span>;
}
