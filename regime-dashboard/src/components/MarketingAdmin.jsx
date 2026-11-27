import { useCallback, useEffect, useState } from "react";
import { call, STATUS_LABEL } from "../marketing/marketingApi";
import CardStudio from "../marketing/studio/CardStudio";
import { StatusPill } from "../marketing/studio/PostStages";

// Página administrativa de Marketing (somente plano admin). Abre em ?mode=marketing.
// Uma aba por ativo (WIN, WDO); em cada uma o post anda por Criar, Aprovar e Enviar dentro do próprio card.
// O servidor impõe as regras (aprovação, simulação, aviso fixo); aqui é só a interface.

const TEXT = {
    title: "Marketing",
    subtitle: "Criar, aprovar e enviar. Nada sai sem aprovação e confirmação.",
    back: "Voltar ao painel",
    loading: "Carregando…",
    loadError: "Não foi possível carregar. Tente de novo.",
    modeDryRun: "Simulação",
    modeDryRunHint: "Nada é publicado de verdade",
    modeLive: "Real",
    modeLiveHint: "Publica no Instagram",
    switchOn: "Publicações ligadas",
    switchOff: "Publicações desligadas",
    turnOff: "Desligar tudo",
    turnOn: "Ligar",
    channelOk: "Instagram conectado",
    channelMissing: "Instagram não configurado no servidor",
    kinds: { morning: "Manhã (marcações)", end_of_day: "Fim do dia", other: "Outro" },
    history: "Histórico",
    historyTitle: "Histórico de posts",
    historyHint: "Só consulta. Clicar abre o post na aba do ativo, na etapa em que ele está.",
    filterAll: "Todos",
    empty: "Nenhum post.",
    soon: "em breve",
    videoSoon: "O estúdio de vídeo chega depois.",
    saved: "Salvo.",
    studioSaved: "Rascunho criado com o card. Agora confira a legenda e aprove.",
    approvalReset: (assets) => `A aprovação do ${assets.join(" e ")} foi desfeita porque o card mudou: aprove de novo.`,
    studioBusy: "Já existe um post deste caso que não pode mais ser alterado",
    actionError: "A ação não foi concluída",
    themeLight: "Modo claro",
    themeDark: "Modo escuro",
    themeLabel: "Alternar entre modo claro e escuro",
};

const card = { background: "var(--mw-card)", border: "1px solid var(--mw-hairline)", borderRadius: 8, padding: 16 };
const THEME_KEY = "mw_marketing_theme";

function readTheme() {
    try {
        return localStorage.getItem(THEME_KEY) === "light" ? "light" : "dark";
    } catch {
        return "dark";
    }
}

function Pill({ children, tone, testId, title }) {
    const colors = {
        ok: ["var(--mw-pos)", "var(--mw-pos-bg)"],
        warn: ["var(--mw-flip)", "transparent"],
        neg: ["var(--mw-neg)", "var(--mw-neg-bg)"],
    }[tone] || ["var(--mw-text-2)", "var(--mw-raised)"];
    return (
        <span
            data-testid={testId}
            title={title}
            style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "3px 10px", borderRadius: 999, fontSize: 12, color: colors[0], background: colors[1], border: "1px solid var(--mw-hairline-strong)" }}
        >
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: "currentColor" }} />
            {children}
        </span>
    );
}

function MainTab({ id, selected, onClick, children, count, disabled }) {
    return (
        <button
            type="button"
            role="tab"
            aria-selected={selected}
            aria-disabled={disabled || undefined}
            data-testid={`main-tab-${id}`}
            onClick={disabled ? undefined : onClick}
            title={disabled ? TEXT.videoSoon : undefined}
            style={{
                background: "transparent",
                border: "none",
                borderBottom: selected ? "2px solid var(--mw-accent)" : "2px solid transparent",
                padding: "11px 14px",
                fontSize: 14,
                fontWeight: selected ? 700 : 500,
                color: selected ? "var(--mw-text-1)" : "var(--mw-text-2)",
                cursor: disabled ? "default" : "pointer",
                opacity: disabled ? 0.55 : 1,
                display: "flex",
                gap: 8,
                alignItems: "center",
            }}
        >
            {children}
            {count != null && (
                <span style={{ background: "var(--mw-accent)", color: "var(--mw-accent-on)", borderRadius: 999, fontSize: 11, fontWeight: 700, padding: "0 7px" }}>{count}</span>
            )}
        </button>
    );
}

export default function MarketingAdmin() {
    const [state, setState] = useState(null);
    const [posts, setPosts] = useState([]);
    const [version, setVersion] = useState(0); // sobe a cada ação: quem mostra detalhe de um post recarrega
    const [tab, setTab] = useState("WIN"); // WIN | WDO | HIST
    const [filter, setFilter] = useState("");
    const [focus, setFocus] = useState(null);
    const [message, setMessage] = useState("");
    const [busy, setBusy] = useState(false);
    const [loadError, setLoadError] = useState("");
    const [theme, setTheme] = useState(readTheme);

    const toggleTheme = () =>
        setTheme((t) => {
            const next = t === "dark" ? "light" : "dark";
            try {
                localStorage.setItem(THEME_KEY, next);
            } catch {
                /* sem armazenamento: o tema vale só nesta visita */
            }
            return next;
        });

    const refreshList = useCallback(async () => {
        const [st, list] = await Promise.all([call("/status"), call("/posts")]);
        setState(st);
        setPosts(list.posts || []);
    }, []);

    useEffect(() => {
        refreshList().then(() => setLoadError("")).catch(() => setLoadError(TEXT.loadError));
        const t = setInterval(() => refreshList().catch(() => {}), 15000);
        return () => clearInterval(t);
    }, [refreshList]);

    const run = useCallback(
        async (fn, okMessage) => {
            setBusy(true);
            setMessage("");
            try {
                const result = await fn();
                if (okMessage) setMessage(typeof okMessage === "function" ? okMessage(result) : okMessage);
                await refreshList();
                setVersion((v) => v + 1);
                return result;
            } catch (err) {
                setMessage(`${TEXT.actionError}: ${err.message}`);
                return null;
            } finally {
                setBusy(false);
            }
        },
        [refreshList]
    );

    // Recebe do estúdio os arquivos já gerados: cria o rascunho (ou atualiza o do mesmo caso) e anexa a mídia.
    const saveToQueue = (items) => {
        const reset = []; // ativos cuja aprovação o servidor desfaz ao trocar o conteúdo
        return run(async () => {
            let lastId = "";
            for (const it of items) {
                const all = await call("/posts");
                const existing = (all.posts || []).find(
                    (p) => p.kind === it.kind && p.asset === it.asset && p.ref_date === it.refDate && !["rejected", "failed"].includes(p.status)
                );
                let id;
                if (existing) {
                    if (!["draft", "approved"].includes(existing.status)) {
                        throw new Error(`${it.asset}: ${TEXT.studioBusy} (${STATUS_LABEL[existing.status] || existing.status}).`);
                    }
                    id = existing.id;
                    if (existing.status === "approved") reset.push(it.asset);
                    await call(`/posts/${id}`, {
                        method: "PATCH",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ caption: it.caption }),
                    });
                } else {
                    const r = await call("/posts", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ channel: "instagram", kind: it.kind, asset: it.asset, ref_date: it.refDate, caption: it.caption }),
                    });
                    id = r.post.id;
                }
                await call(`/posts/${id}/media`, { method: "POST", headers: { "Content-Type": it.mime }, body: it.blob });
                lastId = id;
            }
            return lastId;
        }, () => (reset.length ? `${TEXT.studioSaved} ${TEXT.approvalReset(reset)}` : TEXT.studioSaved));
    };

    const openFromHistory = (p) => {
        setFocus({ date: p.ref_date, key: `${p.id}:${Date.now()}` });
        setTab(p.asset);
        setMessage("");
    };

    const channelConfigured = state?.channels?.instagram?.configured;
    const shownPosts = filter ? posts.filter((p) => p.status === filter) : posts;
    const asset = tab === "HIST" ? null : tab;

    return (
        <div data-mw-theme={theme} style={{ minHeight: "100vh", background: "var(--mw-bg)", color: "var(--mw-text-1)", padding: "20px 16px", colorScheme: theme }}>
            <div style={{ maxWidth: 1180, margin: "0 auto", display: "grid", gap: 14 }}>
                <header style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                    <h1 style={{ fontSize: 22, margin: 0 }}>{TEXT.title}</h1>
                    <span style={{ color: "var(--mw-text-2)", fontSize: 13, flex: 1, minWidth: 200 }}>{TEXT.subtitle}</span>
                    <button type="button" className="mw-btn mw-btn-secondary" data-testid="theme-toggle" aria-label={TEXT.themeLabel} onClick={toggleTheme}>
                        {theme === "dark" ? `☀ ${TEXT.themeLight}` : `☾ ${TEXT.themeDark}`}
                    </button>
                    <a className="mw-btn mw-btn-secondary" href={window.location.pathname} data-testid="marketing-back">
                        {TEXT.back}
                    </a>
                </header>

                {loadError && <div style={{ ...card, color: "var(--mw-neg)" }}>{loadError}</div>}

                <section style={{ ...card, padding: "10px 14px", display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }} data-testid="marketing-status">
                    {!state ? (
                        <span>{TEXT.loading}</span>
                    ) : (
                        <>
                            <Pill tone={state.live ? "neg" : "ok"} testId="mode-label" title={state.live ? TEXT.modeLiveHint : TEXT.modeDryRunHint}>
                                {state.live ? TEXT.modeLive : TEXT.modeDryRun}
                            </Pill>
                            <Pill tone={channelConfigured ? "ok" : "warn"} testId="channel-state">
                                {channelConfigured ? TEXT.channelOk : TEXT.channelMissing}
                            </Pill>
                            <Pill tone={state.enabled ? "ok" : "warn"}>{state.enabled ? TEXT.switchOn : TEXT.switchOff}</Pill>
                            <span style={{ flex: 1 }} />
                            <button
                                type="button"
                                className="mw-btn mw-btn-secondary"
                                data-testid="switch-btn"
                                disabled={busy}
                                onClick={() =>
                                    run(
                                        () =>
                                            call("/switch", {
                                                method: "PUT",
                                                headers: { "Content-Type": "application/json" },
                                                body: JSON.stringify({ enabled: !state.enabled }),
                                            }),
                                        TEXT.saved
                                    )
                                }
                            >
                                {state.enabled ? TEXT.turnOff : TEXT.turnOn}
                            </button>
                        </>
                    )}
                </section>

                {message && (
                    <div role="status" data-testid="marketing-message" style={{ ...card, padding: 12, fontSize: 14 }}>
                        {message}
                    </div>
                )}

                <div role="tablist" aria-label="Seções" style={{ display: "flex", gap: 2, borderBottom: "1px solid var(--mw-hairline-strong)", alignItems: "flex-end" }}>
                    <MainTab id="WIN" selected={tab === "WIN"} onClick={() => setTab("WIN")}>WIN</MainTab>
                    <MainTab id="WDO" selected={tab === "WDO"} onClick={() => setTab("WDO")}>WDO</MainTab>
                    <MainTab id="VIDEO" selected={false} disabled>
                        Vídeo <span style={{ fontSize: 11, color: "var(--mw-text-3)", border: "1px solid var(--mw-hairline-strong)", borderRadius: 999, padding: "0 7px" }}>{TEXT.soon}</span>
                    </MainTab>
                    <span style={{ flex: 1 }} />
                    <MainTab id="HIST" selected={tab === "HIST"} onClick={() => setTab("HIST")} count={posts.length}>
                        {TEXT.history}
                    </MainTab>
                </div>

                {/* O estúdio fica sempre montado (só some da tela no Histórico) para não perder o que foi gerado. */}
                <div style={{ display: asset ? "block" : "none" }}>
                    <CardStudio onSave={saveToQueue} busy={busy} posts={posts} active={asset} focus={focus} appState={state} run={run} version={version} />
                </div>

                {tab === "HIST" && (
                    <section style={{ ...card, maxWidth: 760 }} data-testid="history-panel">
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                            <h2 style={{ fontSize: 15, margin: 0, flex: 1 }}>{TEXT.historyTitle}</h2>
                            <select
                                aria-label={TEXT.historyTitle}
                                value={filter}
                                onChange={(e) => setFilter(e.target.value)}
                                data-testid="filter-select"
                                style={{ background: "var(--mw-bg)", color: "var(--mw-text-1)", border: "1px solid var(--mw-hairline-strong)", borderRadius: 6, padding: "6px 8px" }}
                            >
                                <option value="">{TEXT.filterAll}</option>
                                {Object.entries(STATUS_LABEL).map(([k, v]) => (
                                    <option key={k} value={k}>{v}</option>
                                ))}
                            </select>
                        </div>
                        {shownPosts.length === 0 ? (
                            <div style={{ color: "var(--mw-text-3)", fontSize: 13 }}>{TEXT.empty}</div>
                        ) : (
                            <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 6 }} data-testid="post-list">
                                {shownPosts.map((p) => {
                                    const openable = p.kind === "end_of_day" && (p.asset === "WIN" || p.asset === "WDO");
                                    return (
                                        <li key={p.id}>
                                            <button
                                                type="button"
                                                data-testid="post-item"
                                                disabled={!openable}
                                                onClick={() => openFromHistory(p)}
                                                style={{
                                                    width: "100%",
                                                    textAlign: "left",
                                                    cursor: openable ? "pointer" : "default",
                                                    background: "var(--mw-raised)",
                                                    border: "1px solid var(--mw-hairline)",
                                                    borderRadius: 8,
                                                    padding: "8px 10px",
                                                    color: "var(--mw-text-1)",
                                                    display: "flex",
                                                    gap: 8,
                                                    alignItems: "center",
                                                    opacity: openable ? 1 : 0.6,
                                                }}
                                            >
                                                <span style={{ flex: 1, fontSize: 13 }}>
                                                    {TEXT.kinds[p.kind] || p.kind}
                                                    {p.asset ? ` · ${p.asset}` : ""}
                                                    {p.ref_date ? ` · ${p.ref_date}` : ""}
                                                </span>
                                                <StatusPill status={p.status} testId="status-badge" />
                                            </button>
                                        </li>
                                    );
                                })}
                            </ul>
                        )}
                        <p style={{ margin: "10px 0 0", fontSize: 12, color: "var(--mw-text-3)" }}>{TEXT.historyHint}</p>
                    </section>
                )}
            </div>
        </div>
    );
}
