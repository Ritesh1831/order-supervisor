"use client";

import { useEffect, useState } from "react";
import { api, Supervisor } from "@/lib/api";

const ALL_ACTIONS = [
  "send_customer_message",
  "create_internal_note",
  "escalate_issue",
  "mark_order_for_review",
  "request_human_review",
];

export default function Supervisors() {
  const [sups, setSups] = useState<Supervisor[]>([]);
  const [name, setName] = useState("");
  const [instruction, setInstruction] = useState("");
  const [actions, setActions] = useState<string[]>(ALL_ACTIONS);
  const [aggr, setAggr] = useState("medium");
  const [interval, setInterval] = useState(60);
  const [model, setModel] = useState("llama-3.3-70b-versatile");

  async function refresh() {
    setSups(await api.listSupervisors());
  }
  useEffect(() => {
    refresh();
  }, []);

  async function create() {
    if (!name.trim() || !instruction.trim()) return;
    await api.createSupervisor({
      name,
      base_instruction: instruction,
      enabled_actions: actions,
      wake_config: {
        default_interval_s: interval,
        max_sleep_s: Math.max(interval, 120),
        aggressiveness: aggr,
        max_age_s: 604800,
      },
      model,
    });
    setName("");
    setInstruction("");
    refresh();
  }

  function toggle(a: string) {
    setActions((cur) => (cur.includes(a) ? cur.filter((x) => x !== a) : [...cur, a]));
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <section>
        <h2 className="mb-3 font-semibold">Supervisor templates</h2>
        <div className="space-y-3">
          {sups.map((s) => (
            <div key={s.id} className="rounded-lg border bg-white p-4">
              <div className="flex items-center justify-between">
                <h3 className="font-medium">{s.name}</h3>
                <span className="text-xs text-slate-400">{s.id}</span>
              </div>
              <p className="mt-1 text-sm text-slate-600">{s.base_instruction}</p>
              <div className="mt-2 flex flex-wrap gap-1">
                {s.enabled_actions.map((a) => (
                  <span key={a} className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                    {a}
                  </span>
                ))}
              </div>
              <p className="mt-2 text-xs text-slate-400">
                wake: {s.wake_config?.aggressiveness ?? "medium"} · model: {s.model}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-3 font-semibold">New supervisor</h2>
        <div className="space-y-3 rounded-lg border bg-white p-4">
          <input
            className="w-full rounded border px-2 py-1.5 text-sm"
            placeholder="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <textarea
            className="w-full rounded border px-2 py-1.5 text-sm"
            rows={4}
            placeholder="Base instruction"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
          />
          <div>
            <div className="mb-1 text-sm text-slate-500">Enabled actions</div>
            <div className="flex flex-wrap gap-2">
              {ALL_ACTIONS.map((a) => (
                <label key={a} className="flex items-center gap-1 text-xs">
                  <input type="checkbox" checked={actions.includes(a)} onChange={() => toggle(a)} />
                  {a}
                </label>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap gap-4">
            <label className="block text-sm">
              <span className="text-slate-500">Wake aggressiveness</span>
              <select
                className="ml-2 rounded border px-2 py-1 text-sm"
                value={aggr}
                onChange={(e) => setAggr(e.target.value)}
              >
                <option value="low">low</option>
                <option value="medium">medium</option>
                <option value="high">high</option>
              </select>
            </label>
            <label className="block text-sm">
              <span className="text-slate-500">Wake interval (s)</span>
              <input
                type="number"
                min={10}
                className="ml-2 w-20 rounded border px-2 py-1 text-sm"
                value={interval}
                onChange={(e) => setInterval(Number(e.target.value) || 60)}
              />
            </label>
          </div>
          <label className="block text-sm">
            <span className="text-slate-500">Model</span>
            <input
              className="ml-2 w-64 rounded border px-2 py-1 text-sm"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            />
          </label>
          <button onClick={create} className="rounded bg-slate-900 px-4 py-2 text-sm text-white">
            Create supervisor
          </button>
        </div>
      </section>
    </div>
  );
}
