import { useEffect, useRef, useState } from "react";

export interface TopologyDocument {
  id: string; filename: string; status: "processing" | "ready" | "error";
  page_count: number; completed_pages: number; error?: string;
  result?: any;
}

export function TopologyUpload({ value, onChange }: {
  value: TopologyDocument | null; onChange: (doc: TopologyDocument | null) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [view, setView] = useState<"diagram" | "result">("diagram");
  const working = value?.status === "processing";
  useEffect(() => {
    if (!value?.id || !working) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const response = await fetch(`/api/topology-documents/${value.id}`, {signal:controller.signal});
        if (!response.ok) throw new Error("解析結果を取得できません。PDFを再選択してください。");
        const doc = await response.json();
        if (!controller.signal.aborted) onChange(doc);
        if (doc.status === "processing") timer = setTimeout(poll, 1500);
      } catch (e: any) {
        if (!controller.signal.aborted) onChange({...value,status:"error",error:e.message});
      }
    };
    timer = setTimeout(poll, 1000);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [value?.id, working]);

  const upload = async (file: File) => {
    if (working) return;
    setView("diagram");
    const pending: TopologyDocument = {id:"",filename:file.name,status:"processing",page_count:0,completed_pages:0};
    onChange(pending);
    try {
      if (!file.name.toLowerCase().endsWith(".pdf") || file.size > 10 * 1024 * 1024)
        throw new Error("10MB以下のPDFを選択してください。");
      const response = await fetch(`/api/topology-documents?filename=${encodeURIComponent(file.name)}`,
        {method:"POST",headers:{"Content-Type":"application/pdf"},body:file});
      const doc = await response.json();
      if (!response.ok) throw new Error(doc.detail || "アップロードに失敗しました");
      onChange(doc);
    } catch (e: any) { onChange({...pending,status:"error",error:e.message}); }
  };
  const demo = async () => {
    try {
      const response = await fetch("/api/assets/demo-topology.pdf");
      if (!response.ok) throw new Error("デモPDFを取得できません");
      await upload(new File([await response.blob()], "netwalker-demo-topology.pdf", {type:"application/pdf"}));
    } catch (e: any) { onChange({id:"",filename:"デモPDF",status:"error",page_count:0,completed_pages:0,error:e.message}); }
  };
  const r = value?.result;
  return <section className="card upload-card">
    <div className="upload-heading"><div><span className="eyebrow">構成理解 / PDF → VLM</span><h2>ネットワーク構成図を読み込む</h2></div><a href="/api/assets/demo-topology.pdf" download>デモPDFをダウンロード ↗</a></div>
    <input ref={input} type="file" accept="application/pdf,.pdf" aria-label="構成図PDF" disabled={working} onChange={e => { const f=e.target.files?.[0]; if(f) void upload(f); e.target.value=""; }} />
    {!value && <div className={`upload-drop ${drag ? "dragging" : ""}`}
      onDragOver={e => {e.preventDefault();setDrag(true);}} onDragLeave={() => setDrag(false)}
      onDrop={e => {e.preventDefault();setDrag(false);const f=e.dataTransfer.files[0];if(f) void upload(f);}}>
      <div className="upload-icon">↥</div><h3>構成図のPDFをここにドロップ</h3><p>画像とテキストから機器・接続を抽出し、登録構成と照合します。</p><small>PDF / 1〜3ページ / 最大10MB · OrcaRouterに送信して解析</small>
      <div className="upload-actions"><button className="btn-primary" onClick={() => input.current?.click()}>PDFを選択</button><button className="btn-outline" onClick={demo}>デモPDFで試す</button></div>
    </div>}
    {value && <>
      <div className="upload-filename"><b>{value.filename}</b><span>{working ? "解析中" : value.status === "error" ? "解析失敗" : r?.comparison?.ok ? "登録構成と一致" : "確認が必要"}</span></div>
      {working && <div className="upload-progress" role="status"><span className="spinner"/><h3>VLMが構成図を読み取っています</h3><p>{value.completed_pages} / {value.page_count || "?"} ページ完了。実際のモデル応答を待っています。</p></div>}
      {value.status === "error" && <div className="demo-notice error" role="alert">{value.error}</div>}
      {r && <>
        <div className="upload-stats"><div><strong>{r.mapped_nodes.length}</strong><span>抽出した機器</span></div><div><strong>{r.mapped_links.length}</strong><span>抽出した接続</span></div><div><b>{r.source.startsWith("golden") ? "記録再生" : "実推論"}</b><span>{r.model?.resolved_model || r.model?.route}</span></div></div>
        <div className="upload-tabs"><button className={`ptab ${view === "diagram" ? "on" : ""}`} onClick={() => setView("diagram")}>原図（1ページ目）</button><button className={`ptab ${view === "result" ? "on" : ""}`} onClick={() => setView("result")}>解析結果</button></div>
        {view === "diagram" ? <img className="upload-preview" src={`/api/topology-documents/${value.id}/preview`} alt="アップロードした構成図の1ページ目"/> : <div className="upload-results">
          {r.mapped_nodes.map((n:any,i:number)=><div key={i}><b>{n.label}</b><span>{n.role} / {n.zone}</span><span>{n.registered_id ? `✓ ${n.registered_id}` : "未登録・要確認"}</span></div>)}
          <details><summary>接続情報・ページ別の未修正出力</summary><pre>{JSON.stringify({links:r.mapped_links,pages:r.pages},null,2)}</pre></details>
        </div>}
        <div className={`upload-comparison ${r.comparison.ok ? "matched" : "unmatched"}`} role="status">{r.comparison.ok ? "✓ 機器と接続が登録構成に一致。この結果を調査へ引き継げます。" : "登録構成と不一致があります。この図での自動調査は開始できません。"}
          {!r.comparison.ok && <details><summary>確認が必要な項目</summary><pre>{JSON.stringify({comparison:r.comparison,conflicts:r.conflicts},null,2)}</pre></details>}
        </div>
      </>}
      {!working && <div className="upload-actions"><button className="btn-outline" onClick={() => input.current?.click()}>別のPDFを選択</button><button className="btn-outline" onClick={() => onChange(null)}>選択を解除</button></div>}
    </>}
  </section>;
}
