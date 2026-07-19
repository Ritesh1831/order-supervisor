"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Run, Supervisor } from "@/lib/api";
import { StatusBadge } from "@/components/Badge";

export default function Home() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [sups, setSups] = useState<Supervisor[]>([]);
  const [supId, setSupId] = useState("");
  const [orderId, setOrderId] = useState("");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setRuns(await api.listRuns());
  }

  useEffect(() => {
    api.listSupervisors().then((s) => {
      setSups(s);
      if (s[0]) setSupId(s[0].id);
    });
    refresh();
    const t = setInterval(refresh, 2500);
    return () => clearInterval(t);
  }, []);

  async function start() {
    if (!supId) return;
    setBusy(true);
    try {
      const run = await api.createRun({
        supervisor_id: supId,
        order_id: orderId || undefined,
      });
      setOrderId("");
      await refresh();
      location.href = `/runs/${run.id}`;
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="rounded-lg border bg-white p-4">
        <h2 className="mb-3 font-semibold">Start an order run</h2>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <div className="mb-1 text-slate-500">Supervisor</div>
            <select
              className="w-56 rounded border px-2 py-1.5"
              value={supId}
              onChange={(e) => setSupId(e.target.value)}
            >
              {sups.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <div className="mb-1 text-slate-500">Order ID (optional)</div>
            <input
              className="w-48 rounded border px-2 py-1.5"
              placeholder="auto-generated"
              value={orderId}
              onChange={(e) => setOrderId(e.target.value)}
            />
          </label>
          <button
            onClick={start}
            disabled={busy}
            className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {busy ? "Starting…" : "Start run"}
          </button>
        </div>
      </section>

      <section>
        <h2 className="mb-3 font-semibold">Runs</h2>
        <div className="overflow-hidden rounded-lg border bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-4 py-2">Run</th>
                <th className="px-4 py-2">Supervisor</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Sleep state</th>
                <th className="px-4 py-2">Next wake-up</th>
                <th className="px-4 py-2">Updated</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="border-t hover:bg-slate-50">
                  <td className="px-4 py-2">
                    <Link href={`/runs/${r.id}`} className="font-medium text-slate-900 hover:underline">
                      {r.id}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-slate-600">
                    {sups.find((s) => s.id === r.supervisor_id)?.name ?? r.supervisor_id}
                  </td>
                  <td className="px-4 py-2">
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="px-4 py-2 text-slate-600">{r.sleep_state}</td>
                  <td className="px-4 py-2 text-slate-600">{fmt(r.next_wakeup)}</td>
                  <td className="px-4 py-2 text-slate-500">{fmt(r.updated_at)}</td>
                </tr>
              ))}
              {runs.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-slate-400">
                    No runs yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function fmt(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}
