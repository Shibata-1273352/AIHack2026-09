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
  /** 技術層（技術詳細モーダル側で表示。画面見出しには出さない） */
  current_activity_tech?: string;
  mode: string;
  route_label: string | null;
  route_detail?: string | null;
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
  /** 画面の平易層（null なら text を表示。LLM生成の仮説には無い） */
  text_plain?: string | null;
  evidence_ids: string[]; next_check: string;
}

export interface Plan {
  id: string; seq: number; at: string;
  version: number; hash: string; title: string;
  title_plain?: string;
  body: Record<string, string>;
  diff: string; impact: string; rollback: string;
  diff_plain?: string; impact_plain?: string; rollback_plain?: string;
  preconditions: string[];
  preconditions_plain?: string[];
  status: string;
  validation: null | {
    verified: boolean; clone_match?: boolean; reason?: string; message?: string;
    pre?: { business: boolean; forbidden: boolean };
    post?: { business: boolean; forbidden: boolean };
    /** 複製環境で実際に削除したルール（S6 の可視化で使う） */
    applied_in_verify?: { deleted_rule: string | null } | null;
    /** 検証用環境の変更前後ルールセット全文 */
    diff?: { pre: string; post: string } | null;
    /** 複製の実行手順 */
    clone_steps?: { step: string; rc?: number; stderr?: string }[] | null;
    evidence_id?: string;
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
  /** 平易層（画面に出す） */
  title: string; detail: string;
  /** 技術層（技術詳細モーダル側。null なら平易層へフォールバック） */
  tech_title?: string | null; tech_detail?: string | null;
}

// 引き継ぎレコード（M-12 / §14.3）。却下を起点に起票され、受領・保留が記録される。
export interface Handoff {
  id: string; seq: number; at: string;
  trigger: string;
  status: "open" | "accepted" | "held" | string;
  rejected_by: string | null;
  rejected_at: string | null;
  reason: string;
  plan_id: string | null;
  plan_version: number | null;
  plan_hash: string | null;
  plan_title: string | null;
  evidence_ids: string[];
  hypothesis_ids: string[];
  candidates: string[];
  residual: string;
  notes: { at: string; action: string; assignee: string; note: string }[];
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
  handoffs: Handoff[];
}

// シミュレータの軽量テレメトリ（SSE sim_pulse、2秒周期）。演出専用でエージェント不可視。
export interface SimPulse {
  business_ok: boolean;
  active_path: "r1" | "r2";
  primary_link_up: boolean | null;
  at: string;
}

// 冗長化制御デーモンの検知・切替履歴（SSE sim_failover / GET /api/demo/failover）。
// 時刻は sim コンテナ内の時計。案件側（サーバ時刻）と引き算してはいけない。
export interface SimFailoverEvent {
  at: string;       // "HH:MM:SS"（sim 時刻）
  event: "primary_link_down_detected" | "switch_to_backup" | "switch_to_primary" | string;
  reason: string;
}

export interface SimFailover {
  poll_sec?: number;
  threshold?: number;
  active_path?: "r1" | "r2";
  primary_link_up?: boolean | null;
  updated_at?: string | null;
  history: SimFailoverEvent[];
  log_tail?: string[];
  at?: string;
  error?: string;
}

export interface AppConfig {
  agent_mode: string;
  route_mode: string;
  has_api_key: boolean;
  token_required?: boolean;
  sim: {
    ok: boolean;
    netns?: string[];
    netns_count?: number;
    target_netns_count?: number;
    verify_netns_count?: number;
    error?: string;
  };
  approval_ttl_seconds: number;
}
