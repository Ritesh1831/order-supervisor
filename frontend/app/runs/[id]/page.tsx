"use client";

import { use, useEffect, useState } from "react";
import { api, Activity, EVENT_TYPES, Run, Supervisor } from "@/lib/api";
import { StatusBadge } from "@/components/Badge";

const TYPE_STYLE: Record<string, string> = {
  event: "border-blue-300 bg-blue-50",
  action: "border-emerald-300 bg-emerald-50",
  wake_decision: "border-violet-300 bg-violet-50",
  reasoning: "border-slate-300 bg-slate-50",
  memory_update: "border-amber-300 bg-amber-50",
  instruction: "border-cyan-300 bg-cyan-50",
  sleep: "border-indigo-200 bg-indigo-50",
  lifecycle: "border-slate-400 bg-white",
  final: "border-slate-900 bg-slate-100",
};

// Human-readable labels for the raw activity types.
const TYPE_LABEL: Record<string, string> = {
  event: "Event",
  action: "Action",
  wake_decision: "Wake decision",
  reasoning: "Reasoning",
  memory_update: "Memory",
  instruction: "Instruction",
  sleep: "Sleep",
  lifecycle: "Lifecycle",
  final: "Final report",
};

// Sensible starting payloads so injected events carry real detail for the agent.
const DEFAULT_PAYLOADS: Record<string, any> = {
  order_created: { items: 1, total: 49 },
  payment_confirmed: { amount: 49 },
  payment_failed: { reason: "card declined" },
  shipment_created: { carrier: "UPS", eta_days: 3 },
  shipment_delayed: { reason: "weather", extra_days: 2 },
  delivered: {},
  cancelled: { reason: "customer request" },
};

const payloadFor = (t: string) => JSON.stringify(DEFAULT_PAYLOADS[t] ?? {}, null, 2);

export default function RunDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [run, setRun] = useState<Run | null>(null);
  const [sups, setSups] = useState<Supervisor[]>([]);
  const [eventType, setEventType] = useState(EVENT_TYPES[1]);
  const [customType, setCustomType] = useState("");
  const [payloadText, setPayloadText] = useState(payloadFor(EVENT_TYPES[1]));
  const [instruction, setInstruction] = useState("");

  function pickEvent(t: string) {
    setEventType(t);
    setPayloadText(t === "custom" ? "{}" : payloadFor(t));
  }

  function sendEvent() {
    const type = eventType === "custom" ? customType.trim() : eventType;
    if (!type) return;
    let payload: any = {};
    try {
      payload = JSON.parse(payloadText || "{}");
    } catch {
      alert("Payload is not valid JSON");
      return;
    }
    api.sendEvent(id, type, payload).then(refresh);
  }

  function downloadTimeline() {
    if (!run) return;
    const data = {
      run_id: run.id,
      order_id: run.order_id,
      supervisor_id: run.supervisor_id,
      status: run.status,
      memory_summary: run.memory_summary,
      final_output: run.final_output,
      created_at: run.created_at,
      updated_at: run.updated_at,
      activities: run.activities ?? [],
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${run.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function refresh() {
    try {
      setRun(await api.getRun(id));
    } catch {
      /* run may not be visible yet */
    }
  }

  useEffect(() => {
    api.listSupervisors().then(setSups).catch(() => {});
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, [id]);

  if (!run) return <div className="text-slate-400">Loading…</div>;

  const done = run.status === "completed" || run.status === "terminated";
  const supName = sups.find((s) => s.id === run.supervisor_id)?.name ?? run.supervisor_id;
  const acts = run.activities ?? [];
  const instructions = acts
    .filter((a) => a.type === "instruction")
    .map((a) => a.payload?.text as string)
    .filter(Boolean);
  const asleep = !done && run.sleep_state === "sleeping";

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      {/* left: state + controls */}
      <div className="space-y-4">
        <div className="rounded-lg border bg-white p-4">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h2 className="font-semibold">{run.id}</h2>
            <div className="flex items-center gap-2">
              {!done && (
                <span
                  className={`rounded px-2 py-0.5 text-xs font-medium ${
                    asleep ? "bg-indigo-100 text-indigo-700" : "bg-emerald-100 text-emerald-700"
                  }`}
                >
                  {asleep ? "sleeping" : "awake"}
                </span>
              )}
              <StatusBadge status={run.status} />
            </div>
          </div>
          <dl className="space-y-1 text-sm text-slate-600">
            <Row k="Order" v={run.order_id} />
            <Row k="Next wake-up" v={fmt(run.next_wakeup)} />
            <Row k="Supervisor" v={supName} />
          </dl>
        </div>

        <StatsCard acts={acts} createdAt={run.created_at} updatedAt={run.updated_at} done={done} />

        <div className="rounded-lg border bg-white p-4">
          <h3 className="mb-2 text-sm font-semibold text-slate-700">Memory summary</h3>
          <p className="whitespace-pre-wrap text-sm text-slate-600">
            {run.memory_summary || "—"}
          </p>
        </div>

        {instructions.length > 0 && (
          <div className="rounded-lg border bg-white p-4">
            <h3 className="mb-2 text-sm font-semibold text-slate-700">Active instructions</h3>
            <ul className="list-disc space-y-1 pl-4 text-sm text-slate-600">
              {instructions.map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ul>
          </div>
        )}

        {!done && (
          <>
            <div className="rounded-lg border bg-white p-4">
              <h3 className="mb-2 text-sm font-semibold text-slate-700">Inject event</h3>
              <select
                className="mb-2 w-full rounded border px-2 py-1.5 text-sm"
                value={eventType}
                onChange={(e) => pickEvent(e.target.value)}
              >
                {EVENT_TYPES.map((t) => (
                  <option key={t}>{t}</option>
                ))}
                <option value="custom">Custom (With LLM)</option>
              </select>
              {eventType === "custom" && (
                <input
                  className="mb-2 w-full rounded border px-2 py-1.5 text-sm"
                  placeholder="event type, e.g. weather_alert"
                  value={customType}
                  onChange={(e) => setCustomType(e.target.value)}
                />
              )}
              <textarea
                className="mb-2 w-full rounded border px-2 py-1.5 font-mono text-xs"
                rows={3}
                value={payloadText}
                onChange={(e) => setPayloadText(e.target.value)}
              />
              <button
                onClick={sendEvent}
                className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white"
              >
                Send
              </button>
            </div>

            <div className="rounded-lg border bg-white p-4">
              <h3 className="mb-2 text-sm font-semibold text-slate-700">Add instruction</h3>
              <textarea
                className="mb-2 w-full rounded border px-2 py-1.5 text-sm"
                rows={2}
                placeholder="e.g. If shipment is delayed, escalate immediately."
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
              />
              <button
                onClick={() =>
                  instruction.trim() &&
                  api.addInstruction(id, instruction.trim()).then(() => {
                    setInstruction("");
                    refresh();
                  })
                }
                className="rounded bg-cyan-600 px-3 py-1.5 text-sm text-white"
              >
                Add
              </button>
            </div>

            <div className="rounded-lg border bg-white p-4">
              <h3 className="mb-2 text-sm font-semibold text-slate-700">Controls</h3>
              <div className="flex flex-wrap gap-2">
                <Ctrl label="Interrupt" onClick={() => api.control(id, "interrupt").then(refresh)} />
                <Ctrl label="Pause" onClick={() => api.control(id, "pause").then(refresh)} />
                <Ctrl label="Resume" onClick={() => api.control(id, "resume").then(refresh)} />
                <Ctrl
                  label="Terminate"
                  danger
                  onClick={() => api.terminate(id).then(refresh)}
                />
              </div>
            </div>
          </>
        )}

        {done && run.final_output && <FinalCard output={run.final_output} />}
      </div>

      {/* right: timeline */}
      <div className="lg:col-span-2">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-semibold">Timeline & activity</h3>
          <button
            onClick={downloadTimeline}
            disabled={acts.length === 0}
            className="rounded border px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-40"
          >
            Download (.json)
          </button>
        </div>
        <div className="space-y-2">
          {(run.activities ?? [])
            .slice()
            .reverse()
            .map((a) => (
              <ActivityRow key={a.id} a={a} />
            ))}
          {(run.activities ?? []).length === 0 && (
            <div className="text-sm text-slate-400">No activity yet.</div>
          )}
        </div>
      </div>
    </div>
  );
}

function ActivityRow({ a }: { a: Activity }) {
  const style = TYPE_STYLE[a.type] ?? "border-slate-200 bg-white";
  return (
    <div className={`rounded border-l-4 px-3 py-2 ${style}`}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          {TYPE_LABEL[a.type] ?? a.type}
        </span>
        <span className="text-xs text-slate-400">{new Date(a.created_at).toLocaleTimeString()}</span>
      </div>
      <div className="text-sm text-slate-800">{a.title}</div>
      {a.payload && Object.keys(a.payload).length > 0 && (
        <pre className="mt-1 overflow-x-auto whitespace-pre-wrap text-xs text-slate-500">
          {summarize(a.payload)}
        </pre>
      )}
    </div>
  );
}

function StatsCard({
  acts,
  createdAt,
  updatedAt,
  done,
}: {
  acts: Activity[];
  createdAt: string;
  updatedAt: string;
  done: boolean;
}) {
  const n = (t: string) => acts.filter((a) => a.type === t).length;
  const wakes = acts.filter((a) => a.type === "wake_decision" && a.payload?.important).length;
  const end = done ? new Date(updatedAt) : new Date();
  const mins = Math.max(0, Math.round((end.getTime() - new Date(createdAt).getTime()) / 60000));
  const stats: [string, number | string][] = [
    ["Events", n("event")],
    ["Actions", n("action")],
    ["Agent wakes", wakes],
    ["Scheduled wakes", acts.filter((a) => a.title === "scheduled wake-up").length],
    ["Sleeps", n("sleep")],
    ["Memory updates", n("memory_update")],
    ["Instructions", n("instruction")],
    [done ? "Duration" : "Age", `${mins}m`],
  ];
  return (
    <div className="rounded-lg border bg-white p-4">
      <h3 className="mb-2 text-sm font-semibold text-slate-700">Run analytics</h3>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        {stats.map(([k, v]) => (
          <div key={k} className="flex justify-between">
            <dt className="text-slate-400">{k}</dt>
            <dd className="font-medium text-slate-700">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function FinalCard({ output }: { output: Record<string, any> }) {
  const sections: [string, any][] = [
    ["Key actions", output.key_actions],
    ["Learnings", output.learnings],
    ["Recommendations", output.recommendations],
  ];
  return (
    <div className="rounded-lg border-2 border-slate-900 bg-slate-100 p-4">
      <h3 className="mb-2 text-sm font-semibold">Final report</h3>
      <p className="whitespace-pre-wrap text-sm text-slate-700">
        {output.summary || output.report}
      </p>
      {sections.map(([label, items]) =>
        Array.isArray(items) && items.length > 0 ? (
          <div key={label} className="mt-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              {label}
            </div>
            <ul className="list-disc pl-4 text-sm text-slate-700">
              {items.map((it: string, i: number) => (
                <li key={i}>{it}</li>
              ))}
            </ul>
          </div>
        ) : null,
      )}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-slate-400">{k}</dt>
      <dd className="text-right">{v}</dd>
    </div>
  );
}

function Ctrl({ label, onClick, danger }: { label: string; onClick: () => void; danger?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`rounded px-3 py-1.5 text-sm text-white ${danger ? "bg-rose-600" : "bg-slate-700"}`}
    >
      {label}
    </button>
  );
}

function summarize(p: Record<string, any>) {
  const s = JSON.stringify(p);
  return s.length > 300 ? s.slice(0, 300) + "…" : s;
}

function fmt(iso: string | null) {
  return iso ? new Date(iso).toLocaleString() : "—";
}
