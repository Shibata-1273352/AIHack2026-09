// サーバ状態の購読。正本はサーバ側（§9）。
// 接続時に全量を取得し、SSE で増分反映。切断時は再接続して全量を再取得する（T-12）。

import { useEffect, useRef, useState } from "react";
import type { Bundle, AppConfig, SimPulse } from "./types";

const EMPTY: Bundle = {
  incident: null, evidence: [], hypotheses: [], plans: [], approvals: [],
  executions: [], spans: [], model_runs: [], steps: [],
};

function upsert<T extends { id: string }>(list: T[], item: T): T[] {
  const i = list.findIndex((x) => x.id === item.id);
  if (i === -1) return [...list, item];
  const next = list.slice();
  next[i] = item;
  return next;
}

export function useBundle(): {
  bundle: Bundle; connected: boolean; pulse: SimPulse | null; refresh: () => void;
} {
  const [bundle, setBundle] = useState<Bundle>(EMPTY);
  const [connected, setConnected] = useState(false);
  const [pulse, setPulse] = useState<SimPulse | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const generation = useRef(0);
  const [clock, setClock] = useState(Date.now());
  const lastPulse = useRef(0);

  const refresh = async () => {
    const version = ++generation.current;
    try {
      const r = await fetch("/api/incidents/latest");
      const data = await r.json();
      if (version !== generation.current) return;
      if (data.incident) setBundle(data);
      else setBundle(EMPTY);
    } catch { /* サーバ未起動時は次の再接続で回復 */ }
  };

  useEffect(() => {
    let stopped = false;
    const timer = setInterval(() => setClock(Date.now()), 1000);

    const connect = () => {
      if (stopped) return;
      const es = new EventSource("/api/events");
      esRef.current = es;
      es.onopen = () => { setConnected(true); refresh(); };
      es.onerror = () => {
        setConnected(false);
        es.close();
        setTimeout(connect, 2000); // 再接続 → onopen で全量再取得
      };
      es.onmessage = (msg) => {
        const ev = JSON.parse(msg.data);
        if (ev.type === "demo" && ev.reset) {
          generation.current++;
          setBundle(EMPTY);
          setPulse(null);
          return;
        }
        if (ev.type === "sim_pulse") {
          lastPulse.current = Date.now();
          setPulse(ev.pulse);
          return;
        }
        setBundle((b) => {
          switch (ev.type) {
            case "incident":
              return { ...(b.incident?.id === ev.incident.id ? b : EMPTY), incident: ev.incident };
            case "evidence":
              return { ...b, evidence: upsert(b.evidence, ev.evidence) };
            case "hypothesis":
              return { ...b, hypotheses: upsert(b.hypotheses, ev.hypothesis) };
            case "plan":
              return { ...b, plans: upsert(b.plans, ev.plan) };
            case "approval":
              return { ...b, approvals: upsert(b.approvals, ev.approval) };
            case "execution":
              return { ...b, executions: upsert(b.executions, ev.execution) };
            case "span":
              return { ...b, spans: upsert(b.spans, ev.span) };
            case "model_run":
              return { ...b, model_runs: upsert(b.model_runs, ev.model_run) };
            case "agent_step":
              return { ...b, steps: upsert(b.steps, ev.step) };
            case "node_status":
              if (!b.incident) return b;
              return {
                ...b,
                incident: {
                  ...b.incident,
                  graph_status: {
                    ...b.incident.graph_status,
                    nodes: {
                      ...b.incident.graph_status.nodes,
                      [ev.node]: { status: ev.status, label: ev.label },
                    },
                  },
                },
              };
            case "link_status":
              if (!b.incident) return b;
              return {
                ...b,
                incident: {
                  ...b.incident,
                  graph_status: {
                    ...b.incident.graph_status,
                    links: {
                      ...b.incident.graph_status.links,
                      [ev.link]: { status: ev.status, label: ev.label },
                    },
                  },
                },
              };
            default:
              return b;
          }
        });
      };
    };

    connect();
    return () => { stopped = true; clearInterval(timer); generation.current++; esRef.current?.close(); };
  }, []);

  return { bundle, connected, pulse: connected && clock - lastPulse.current < 6000 ? pulse : null, refresh };
}

export function useConfig(): AppConfig | null {
  const [cfg, setCfg] = useState<AppConfig | null>(null);
  useEffect(() => {
    fetch("/api/config").then((r) => r.json()).then(setCfg).catch(() => {});
  }, []);
  return cfg;
}

export async function post(path: string, body?: unknown): Promise<any> {
  const r = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: body === undefined ? "{}" : JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
}
