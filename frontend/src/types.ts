// バックエンドの状態バンドル（/api/incidents/latest と SSE イベントの型）

export type IncidentStatus =
  | "RECEIVED" | "INVESTIGATING" | "VALIDATING_PLAN" | "AWAITING_APPROVAL"
  | "APPLYING" | "VERIFYING" | "SERVICE_RESTORED" | "RESOLVED"
  | "ROLLING_BACK" | "NEEDS_HUMAN" | "CANCELLED";

export interface GraphNodeStatus { status: string; label: string }

export interface Incident {
  id: string;
  created_at: string;
  symptom: string;
  site: string;
  business: string;
  reporter: string;
  status: IncidentStatus;
  status_label: string;
  status_history: { status: string; at: string; note?: string }[];
  current_activity: string;
  mode: string;
  route_label: string | null;
  residual_issues: { title: string; detail: string; assignee: string; action: string; at: string }[];
  graph_status: { nodes: Record<string, GraphNodeStatus>; links: Record<string, GraphNodeStatus> };
  success_criteria: string;
  allowed_scope: string;
  business_status: "unknown" | "ok" | "down";
  started_ms: number;
}

export interface Evidence {
  id: string; incident_id: string; seq: number; at: string;
  tool: string; params: Record<string, unknown>; summary: string;
  result: any; data_class: string;
}

export interface Hypothesis {
  id: string; seq: number; at: string;
  text: string; status: "open" | "supported" | "rejected";
  evidence_ids: string[]; next_check: string;
}

export interface Plan {
  id: string; seq: number; at: string;
  version: number; hash: string; title: string;
  body: Record<string, string>;
  diff: string; impact: string; rollback: string;
  preconditions: string[];
  status: string;
  validation: null | {
    verified: boolean; clone_match?: boolean; reason?: string; message?: string;
    pre?: { business: boolean; forbidden: boolean };
    post?: { business: boolean; forbidden: boolean };
  };
}

export interface Approval {
  id: string; seq: number; at: string;
  plan_id: string; plan_version: number; plan_hash: string;
  decision: "pending" | "approved" | "rejected" | "expired";
  approver: string | null; decided_at: string | null;
  expires_at: string; expires_epoch: number;
}

export interface Execution {
  id: string; seq: number; at: string;
  plan_id: string; execution_id: string; idempotency_key: string;
  deleted_rule: string | null; approver: string;
}

export interface Span {
  id: string; seq: number; at: string;
  name: string; kind: string;
  start_ms: number; end_ms: number; duration_ms: number;
  attrs: Record<string, unknown>; status: string;
}

export interface ModelRun {
  id: string; seq: number; at: string;
  key: string; profile: string; route: string | null;
  resolved_model: string | null;
  input_tokens: number | null; output_tokens: number | null;
  cost_usd: number | null; latency_ms: number | null;
  outcome: string; error: string | null;
}

export interface AgentStep {
  id: string; seq: number; at: string;
  title: string; detail: string;
}

export interface Bundle {
  incident: Incident | null;
  evidence: Evidence[];
  hypotheses: Hypothesis[];
  plans: Plan[];
  approvals: Approval[];
  executions: Execution[];
  spans: Span[];
  model_runs: ModelRun[];
  steps: AgentStep[];
}

// シミュレータの軽量テレメトリ（SSE sim_pulse、2秒周期）。演出専用でエージェント不可視。
export interface SimPulse {
  business_ok: boolean;
  active_path: "r1" | "r2";
  primary_link_up: boolean | null;
  at: string;
}

export interface AppConfig {
  agent_mode: string;
  route_mode: string;
  has_api_key: boolean;
  sim: { ok: boolean };
  approval_ttl_seconds: number;
}
