import { useEffect, useMemo, useRef, useState } from "react";
import { call, STATUS_COLOR, STATUS_LABEL } from "../marketingApi";

// Etapas 2 (Aprovar) e 3 (Enviar) de um post, mostradas dentro do card do ativo.
// O servidor decide tudo (aprovação, modo simulação, aviso legal); aqui é só a interface.

const T = {
    caption: "Legenda do post",
    captionHint: "Precisa conter: Conteúdo educacional. Sem recomendação de investimento.",
    save: "Salvar legenda",
    saveFirst: "Salve a legenda antes de aprovar.",
    approve: "Aprovar e ir para Enviar →",
    reject: "Rejeitar",
    back: "← Voltar ao card",
    approveNote: "Aprovar não publica.",
    alreadyApproved: "Este post já está aprovado. Se editar a legenda, salve e confira de novo.",
    saved: "Salvo.",
    mode: "Modo",
    modeDry: "Simulação",
    modeLive: "Real",
    ready: "Pronto para enviar",
    publishing: "Publicando…",
    done: "Publicado",
    failed: "Falhou",
    format: "Formato",
    formatValue: "Feed · imagem 1080×1350",
    metaId: "ID do post na Meta",
    publishedAt: "Publicado em",
    noValue: "—",
    testAccount: "Testar conta",
    checkOk: "Conta lida com sucesso",
    publish: "Publicar no Instagram…",
    confirmTitle: "Confirmar envio",
    confirmDry: "Modo Simulação: nada vai ao Instagram, só registramos o que seria enviado.",
    confirmLive: "Modo Real: isto publica de verdade no Instagram e só se apaga pelo app do Instagram.",
    confirmYes: "Confirmar e publicar",
    cancel: "Voltar",
    retry: "Voltar para rascunho",
    withdraw: "Cancelar aprovação",
    channelMissing: "Canal do Instagram não configurado no servidor.",
    disabled: "As publicações estão desligadas. Ligue no topo da página para enviar.",
    xTitle: "X (Twitter)",
    xSoon: "em breve",
    xBody: "Mesmo fluxo de aprovação. Aparece aqui quando o canal for ligado.",
    history: "Histórico do post",
    error: "Erro",
    dryRunDone: "Simulação registrada. Nada foi publicado.",
    publishStarted: "Publicação iniciada.",
};

const field = {
    width: "100%",
    background: "var(--mw-bg)",
    color: "var(--mw-text-1)",
    border: "1px solid var(--mw-hairline-strong)",
    borderRadius: 6,
    padding: "8px 10px",
    fontSize: 13,
    fontFamily: "var(--mono, ui-monospace, monospace)",
    boxSizing: "border-box",
    lineHeight: 1.5,
};
const label = { display: "block", fontSize: 12, color: "var(--mw-text-2)", marginBottom: 4 };
const box = { border: "1px solid var(--mw-hairline-strong)", borderRadius: 10, padding: 12, background: "var(--mw-raised)" };

export function StatusPill({ status, testId }) {
    const color = STATUS_COLOR[status] || "var(--mw-text-2)";
    return (
        <span data-testid={testId || "status-badge"} style={{ fontSize: 12, padding: "2px 9px", borderRadius: 999, border: `1px solid ${color}`, color, whiteSpace: "nowrap" }}>
            {STATUS_LABEL[status] || status}
        </span>
    );
}

export default function PostStages({ asset, post, versionLabel, textareaHeight, step, appState, busy, run, version, onBack }) {
    const [detail, setDetail] = useState(null);
    const [captionDraft, setCaptionDraft] = useState(post.caption || "");
    const touched = useRef(false); // true enquanto há edição à mão que um recarregamento não pode apagar
    const [confirmKey, setConfirmKey] = useState(""); // a confirmação só vale para este post, neste estado e etapa

    // Recarrega o detalhe (histórico) quando o post muda ou depois de qualquer ação.
    useEffect(() => {
        let alive = true;
        call(`/posts/${post.id}`)
            .then((d) => {
                if (!alive) return;
                setDetail(d);
                if (!touched.current) setCaptionDraft(d.post.caption || "");
            })
            .catch(() => {});
        return () => {
            alive = false;
        };
    }, [post.id, post.status, version]);

    useEffect(() => {
        touched.current = false;
    }, [post.id]);

    const stateKey = `${post.id}:${post.status}:${step}`;
    const confirming = confirmKey === stateKey;
    const setConfirming = (on) => setConfirmKey(on ? stateKey : "");

    const current = detail?.post && detail.post.id === post.id ? detail.post : post;
    const editable = ["draft", "approved", "rejected", "failed"].includes(current.status);
    const dirty = captionDraft !== (current.caption || "");
    const events = useMemo(() => [...(detail?.events || [])].reverse(), [detail]);
    const channelOk = appState?.channels?.instagram?.configured;
    const live = !!appState?.live;

    const act = (action, okMessage) => run(() => call(`/posts/${current.id}/${action}`, { method: "POST" }), okMessage);
    const saveCaption = () =>
        run(
            () => call(`/posts/${current.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ caption: captionDraft }) }),
            T.saved
        ).then((r) => {
            if (r) touched.current = false;
        });
    const doPublish = () =>
        run(
            () => call(`/posts/${current.id}/publish`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: true }) }),
            (r) => (r.dry_run ? T.dryRunDone : T.publishStarted)
        ).then(() => setConfirming(false));

    if (step === 2) {
        return (
            <div style={{ display: "grid", gap: 8 }} data-testid={`stage-approve-${asset}`}>
                <label style={label} htmlFor={`mk-edit-caption-${asset}`}>
                    {T.caption}
                    {versionLabel && (
                        <span data-testid={`version-label-${asset}`} style={{ marginLeft: 8, padding: "1px 8px", borderRadius: 999, fontSize: 11, fontWeight: 600, color: "var(--mw-pos)", background: "var(--mw-pos-bg)" }}>
                            versão {versionLabel}
                        </span>
                    )}
                </label>
                <textarea
                    id={`mk-edit-caption-${asset}`}
                    data-testid={`edit-caption-${asset}`}
                    rows={11}
                    style={textareaHeight ? { ...field, height: textareaHeight } : field}
                    value={captionDraft}
                    disabled={!editable}
                    onChange={(e) => {
                        touched.current = true;
                        setCaptionDraft(e.target.value);
                    }}
                />
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <span style={{ fontSize: 12, color: "var(--mw-text-3)", flex: 1 }}>
                        {T.captionHint} · {captionDraft.length}/2200
                    </span>
                    <button type="button" className="mw-btn mw-btn-secondary" data-testid="save-caption-btn" disabled={busy || !editable || !dirty} onClick={saveCaption}>
                        {T.save}
                    </button>
                </div>
                {current.status === "approved" && <div style={{ fontSize: 12, color: "var(--mw-accent-ink)" }}>{T.alreadyApproved}</div>}
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", borderTop: "1px solid var(--mw-hairline)", paddingTop: 12, marginTop: 4 }}>
                    {current.status === "draft" && (
                        <button
                            type="button"
                            className="mw-btn mw-btn-primary"
                            data-testid="approve-btn"
                            disabled={busy || dirty}
                            title={dirty ? T.saveFirst : undefined}
                            onClick={() => act("approve", T.saved)}
                        >
                            {T.approve}
                        </button>
                    )}
                    {["draft", "approved", "failed"].includes(current.status) && (
                        <button type="button" className="mw-btn mw-btn-secondary" data-testid="reject-btn" disabled={busy} onClick={() => act("reject", T.saved)}>
                            {T.reject}
                        </button>
                    )}
                    <button type="button" className="mw-btn mw-btn-secondary" data-testid={`back-card-${asset}`} onClick={onBack}>
                        {T.back}
                    </button>
                    {current.status === "draft" && <span style={{ fontSize: 12, color: "var(--mw-text-3)" }}>{T.approveNote}</span>}
                </div>
            </div>
        );
    }

    // etapa 3 · Enviar
    const stateLabel = current.status === "published" ? T.done : current.status === "publishing" ? T.publishing : current.status === "failed" ? T.failed : T.ready;
    return (
        <div style={{ display: "grid", gap: 10 }} data-testid={`stage-send-${asset}`}>
            <div style={box}>
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 8 }}>
                    <strong style={{ fontSize: 13 }}>Instagram</strong>
                    <span data-testid="send-mode" style={{ fontSize: 12, color: live ? "var(--mw-neg)" : "var(--mw-pos)" }}>
                        {T.mode}: {live ? T.modeLive : T.modeDry}
                    </span>
                    <span style={{ flex: 1 }} />
                    <StatusPill status={current.status} />
                    <span style={{ fontSize: 12, color: "var(--mw-text-2)" }}>{stateLabel}</span>
                </div>
                <dl style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: "3px 10px", fontSize: 12, margin: 0 }}>
                    <dt style={{ color: "var(--mw-text-3)" }}>{T.format}</dt>
                    <dd style={{ margin: 0 }}>{T.formatValue}</dd>
                    <dt style={{ color: "var(--mw-text-3)" }}>{T.metaId}</dt>
                    <dd style={{ margin: 0, fontFamily: "var(--mono, monospace)", wordBreak: "break-all" }} data-testid="meta-id">{current.external_id || T.noValue}</dd>
                    <dt style={{ color: "var(--mw-text-3)" }}>{T.publishedAt}</dt>
                    <dd style={{ margin: 0, fontFamily: "var(--mono, monospace)" }}>{current.published_at || T.noValue}</dd>
                </dl>
                {current.error && (
                    <div style={{ fontSize: 13, color: "var(--mw-neg)", marginTop: 8 }} data-testid="post-error">
                        {T.error}: {current.error}
                    </div>
                )}
                {!channelOk && <div style={{ fontSize: 12, color: "var(--mw-flip)", marginTop: 8 }}>{T.channelMissing}</div>}
                {!appState?.enabled && <div style={{ fontSize: 12, color: "var(--mw-flip)", marginTop: 8 }}>{T.disabled}</div>}

                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12, paddingTop: 10, borderTop: "1px solid var(--mw-hairline)" }}>
                    {current.status === "approved" && !confirming && (
                        <button type="button" className="mw-btn mw-btn-primary" data-testid="publish-btn" disabled={busy || !appState?.enabled} onClick={() => setConfirming(true)}>
                            {T.publish}
                        </button>
                    )}
                    <button
                        type="button"
                        className="mw-btn mw-btn-secondary"
                        data-testid="send-check-btn"
                        disabled={busy || !channelOk}
                        onClick={() => run(() => call("/channels/instagram/check"), T.checkOk)}
                    >
                        {T.testAccount}
                    </button>
                    {current.status === "failed" && (
                        <button type="button" className="mw-btn mw-btn-secondary" data-testid="retry-btn" disabled={busy} onClick={() => act("retry", T.saved)}>
                            {T.retry}
                        </button>
                    )}
                    {current.status === "approved" && (
                        <button type="button" className="mw-btn mw-btn-secondary" data-testid="reject-btn" disabled={busy} onClick={() => act("reject", T.saved)}>
                            {T.withdraw}
                        </button>
                    )}
                </div>

                {confirming && current.status === "approved" && (
                    <div role="alertdialog" aria-label={T.confirmTitle} data-testid="confirm-box" style={{ border: "1px solid var(--mw-flip)", borderRadius: 10, padding: 12, marginTop: 10 }}>
                        <strong>{T.confirmTitle}</strong>
                        <p style={{ margin: "6px 0 10px", fontSize: 13, color: live ? "var(--mw-neg)" : "var(--mw-pos)" }}>{live ? T.confirmLive : T.confirmDry}</p>
                        <div style={{ display: "flex", gap: 8 }}>
                            <button type="button" className="mw-btn mw-btn-primary" data-testid="confirm-publish-btn" disabled={busy} onClick={doPublish}>
                                {T.confirmYes}
                            </button>
                            <button type="button" className="mw-btn mw-btn-secondary" onClick={() => setConfirming(false)}>
                                {T.cancel}
                            </button>
                        </div>
                    </div>
                )}
            </div>

            <div style={{ ...box, opacity: 0.55 }}>
                <strong style={{ fontSize: 13 }}>{T.xTitle}</strong> <span style={{ fontSize: 12, color: "var(--mw-text-3)" }}>{T.xSoon}</span>
                <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--mw-text-3)" }}>{T.xBody}</p>
            </div>

            <div>
                <div style={{ ...label, marginBottom: 6 }}>{T.history}</div>
                <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 4, fontSize: 12, color: "var(--mw-text-2)" }} data-testid="event-list">
                    {events.map((ev) => (
                        <li key={ev.id}>
                            {ev.at.replace("T", " ").replace("+00:00", "Z")} · {ev.action} · {ev.actor}
                        </li>
                    ))}
                </ul>
            </div>
        </div>
    );
}
