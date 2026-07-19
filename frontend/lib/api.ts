export type Supervisor = {
  id: string;
  name: string;
  base_instruction: string;
  enabled_actions: string[];
  wake_config: Record<string, any>;
  model: string;
};

export type Activity = {
  id: number;
  type: string;
  title: string;
  payload: Record<string, any>;
  created_at: string;
};

export type Run = {
  id: string;
  order_id: string;
  supervisor_id: string;
  workflow_id: string;
  status: string;
  memory_summary: string;
  next_wakeup: string | null;
  sleep_state: string;
  order_context: Record<string, any>;
  final_output: Record<string, any> | null;
  created_at: string;
  updated_at: string;
  activities?: Activity[];
};

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

const opts = { headers: { "Content-Type": "application/json" } };

export const api = {
  listSupervisors: () => fetch("/api/supervisors").then(j<Supervisor[]>),
  createSupervisor: (body: Partial<Supervisor>) =>
    fetch("/api/supervisors", { method: "POST", ...opts, body: JSON.stringify(body) }).then(
      j<Supervisor>,
    ),
  listRuns: () => fetch("/api/runs").then(j<Run[]>),
  getRun: (id: string) => fetch(`/api/runs/${id}`).then(j<Run>),
  createRun: (body: { supervisor_id: string; order_id?: string }) =>
    fetch("/api/runs", { method: "POST", ...opts, body: JSON.stringify(body) }).then(j<Run>),
  sendEvent: (id: string, type: string, payload: Record<string, any> = {}) =>
    fetch(`/api/runs/${id}/events`, { method: "POST", ...opts, body: JSON.stringify({ type, payload }) }),
  addInstruction: (id: string, text: string) =>
    fetch(`/api/runs/${id}/instructions`, { method: "POST", ...opts, body: JSON.stringify({ text }) }),
  control: (id: string, action: "interrupt" | "pause" | "resume") =>
    fetch(`/api/runs/${id}/${action}`, { method: "POST", ...opts }),
  terminate: (id: string, reason = "manual") =>
    fetch(`/api/runs/${id}/terminate`, { method: "POST", ...opts, body: JSON.stringify({ reason }) }),
};

export const EVENT_TYPES = [
  "order_created",
  "payment_confirmed",
  "payment_failed",
  "shipment_created",
  "shipment_delayed",
  "delivered",
  "cancelled",
];
