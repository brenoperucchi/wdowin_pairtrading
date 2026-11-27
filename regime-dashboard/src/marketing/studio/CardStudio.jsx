import { useEffect, useMemo, useRef, useState } from "react";
import { API_BASE } from "../../apiBase";
import { authFetch } from "../../utils/saasAuth";
import {
    buildInstagramCaption,
    buildInstagramSignals,
    formatPtsLabel,
    formatSessionDateBr,
} from "../../utils/instagramSignalMetrics";
import { captionBody, finalCaption } from "../../utils/marketingCaption";
import {
    CARD_DIMENSIONS,
    DEFAULT_CARD_PREFS,
    InstagramCardSvg,
    loadPrefs,
    savePrefs,
    svgElementToPngBlob,
} from "../../components/instagramCard";
import { loadCardInputs } from "./cardInputs";
import { API, findStudioPost, stepOfPost } from "../marketingApi";
import PostStages, { StatusPill } from "./PostStages";

// Estúdio de card do Instagram dentro da tela de Marketing. Busca os dados do dia, calcula os sinais com a mesma
// regra do painel, mostra o card e entrega o PNG direto para a fila (sem baixar arquivo). Só formato Feed 1080×1350:
// é o que a API do Instagram aceita como imagem única.

// Dados do painel (etapa1 e motor). Em produção é a mesma API; em teste local pode apontar para outro endereço.
const COMPASS_BASE = import.meta.env.VITE_COMPASS_BASE ?? API_BASE;

// Ponte local de legendas com IA (scripts/caption_bridge.py). A chave do gateway fica na ponte, nunca no navegador.
const BRIDGE_BASE = import.meta.env.VITE_CAPTION_BRIDGE ?? "http://127.0.0.1:8095";

const T = {
    title: "Estúdio de card",
    hint: "Criar, aprovar e enviar acontecem neste card. Nada é publicado sem a sua confirmação.",
    steps: ["Criar", "Aprovar", "Enviar"],
    noDraft: "Sem rascunho",
    locked: "Imagem anexada ao rascunho. Para mudar o card, volte à etapa 1.",
    createNext: "Criar rascunho e ir para Aprovar →",
    updateNext: "Atualizar rascunho com este card →",
    attached: "Imagem anexada",
    date: "Data do pregão",
    assets: "Ativos",
    both: "WIN + WDO",
    loading: "Carregando o dia…",
    loadError: "Não foi possível carregar os dados deste dia.",
    noBars: "Sem dados de mercado para este dia.",
    engineError: "O motor de divergências não respondeu: o card sairia sem sinais. Tente de novo.",
    noSignals: "Nenhum sinal neste dia. O card sairia vazio.",
    layers: "Camadas do gráfico",
    ruler: "Régua de pontos",
    brand: "Título do card",
    handle: "Seu @instagram",
    filter: "Sinais incluídos",
    caption: "Legenda",
    regenCaption: "Regerar legenda",
    create: "Criar rascunho",
    creating: "Gerando o PNG…",
    generate: "Gerar versão",
    waiting: "Aguardando a outra versão terminar…",
    waitHint: "O Strata atende um pedido por vez. Clique em Gerar quando a outra terminar.",
    loadingHint: "Em geral leva 1 a 3 segundos.",
    regenerate: "Gerar de novo",
    suggesting: "Pedindo ao Strata…",
    useThis: "Usar esta legenda",
    inUse: "Em uso no rascunho",
    tabsLabel: "Versões da legenda",
    toneHint: {
        sobrio: "Só fatos do dia, sem emoji nem pergunta.",
        equilibrado: "Gancho com personalidade e fechamento leve.",
        chamativo: "Prende a atenção e leva ao painel, sem prometer resultado.",
    },
    toneNote: "A IA escreve só a primeira e a última linha; o resumo do meio fica intacto. Cada aba gera uma vez, ao ser aberta.",
    bridgeDown: "A ponte de IA não está ligada. Rode: python3 scripts/caption_bridge.py",
    revisit: "Os sinais vêm do motor com o dia completo e podem diferir do que apareceu ao vivo. Confira antes de aprovar.",
};

const TABS = [
    { id: "original", label: "Original" },
    { id: "sobrio", label: "Sóbrio" },
    { id: "equilibrado", label: "Equilibrado" },
    { id: "chamativo", label: "Chamativo" },
];

const LAYERS = [
    { key: "showFlow", label: "Fluxo Smart Money" },
    { key: "showGauss", label: "Canal Gauss" },
    { key: "showWalls", label: "Walls" },
    { key: "showMidWalls", label: "MidWalls" },
    { key: "showDivLines", label: "Linhas div." },
];
const RULERS = [
    { id: "BEST", label: "Melhor" },
    { id: "ALL", label: "Todos" },
    { id: "OFF", label: "Ocultar" },
];

const card = { background: "var(--mw-card)", border: "1px solid var(--mw-hairline)", borderRadius: 8, padding: 16 };
const field = {
    width: "100%",
    background: "var(--mw-bg)",
    color: "var(--mw-text-1)",
    border: "1px solid var(--mw-hairline-strong)",
    borderRadius: 6,
    padding: "8px 10px",
    fontSize: 14,
    fontFamily: "inherit",
    boxSizing: "border-box",
};
const label = { display: "block", fontSize: 12, color: "var(--mw-text-2)", marginBottom: 4 };
const CONTROL_H = 36;
const PILL_H = 28;
const control = { ...field, height: CONTROL_H, padding: "0 10px" };

function pill(active) {
    return {
        height: PILL_H,
        padding: "0 12px",
        borderRadius: 999,
        fontSize: 12,
        cursor: "pointer",
        color: active ? "var(--mw-accent-ink)" : "var(--mw-text-3)",
        background: active ? "var(--mw-accent-soft)" : "transparent",
        border: `1px solid ${active ? "var(--mw-accent-border)" : "var(--mw-hairline-strong)"}`,
    };
}

async function getJson(url, options) {
    const res = await authFetch(url, options);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

/** Baixa o etapa1 de uma data ("" = o mais recente). */
function useEtapa1(date) {
    const [state, setState] = useState({ status: "loading", data: null, requested: date });
    useEffect(() => {
        let cancelled = false;
        const q = date ? `?date_str=${encodeURIComponent(date)}` : "";
        getJson(`${COMPASS_BASE}/api/compass/etapa1${q}`)
            .then((data) => {
                if (!cancelled) setState({ status: "ok", data, requested: date });
            })
            .catch(() => {
                if (!cancelled) setState({ status: "erro", data: null, requested: date });
            });
        return () => {
            cancelled = true;
        };
    }, [date]);
    return state.requested === date ? state : { status: "loading", data: null, requested: date };
}

const fetchDivs = (body) =>
    getJson(`${COMPASS_BASE}/api/compass/divergencias_motor`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });

function StepBar({ asset, step, derived, onPick }) {
    return (
        <div style={{ display: "flex", alignItems: "center", gap: 0, width: "100%" }} role="tablist" aria-label="Etapas do post" data-testid={`stepper-${asset}`}>
            {T.steps.map((name, i) => {
                const n = i + 1;
                const done = n < derived;
                const now = n === step;
                const enabled = n <= derived;
                return (
                    <span key={name} style={{ display: "contents" }}>
                        {i > 0 && <span style={{ flex: "1 1 0", minWidth: 16, height: 1, background: n <= derived ? "var(--mw-pos)" : "var(--mw-hairline-strong)", margin: "0 10px" }} />}
                        <button
                            type="button"
                            role="tab"
                            aria-selected={now}
                            data-testid={`step-${asset}-${n}`}
                            disabled={!enabled}
                            onClick={() => onPick(n)}
                            style={{ display: "flex", alignItems: "center", gap: 8, background: "transparent", border: "none", padding: "4px 0", color: now ? "var(--mw-text-1)" : "var(--mw-text-3)", fontWeight: now ? 700 : 500, fontSize: 13, cursor: enabled ? "pointer" : "default" }}
                        >
                            <span
                                style={{
                                    width: 24,
                                    height: 24,
                                    borderRadius: "50%",
                                    display: "grid",
                                    placeItems: "center",
                                    fontSize: 12,
                                    fontWeight: 700,
                                    border: "1px solid var(--mw-hairline-strong)",
                                    background: now ? "var(--mw-accent)" : done ? "var(--mw-pos)" : "var(--mw-raised)",
                                    color: now ? "var(--mw-accent-on)" : done ? "#fff" : "var(--mw-text-3)",
                                    borderColor: now || done ? "transparent" : undefined,
                                }}
                            >
                                {done ? "✓" : n}
                            </span>
                            {name}
                        </button>
                    </span>
                );
            })}
        </div>
    );
}

/** A imagem que está de fato anexada ao rascunho (a que o Instagram vai receber). */
function PostMedia({ asset, post, version }) {
    const [url, setUrl] = useState("");
    const key = post?.has_media ? `${post.id}:${post.status}:${post.updated_at || ""}:${version}` : "";
    useEffect(() => {
        let alive = true;
        let objectUrl = "";
        if (!key) {
            setUrl("");
            return undefined;
        }
        authFetch(`${API}/posts/${post.id}/media`)
            .then((r) => (r.ok ? r.blob() : null))
            .then((blob) => {
                if (!alive || !blob) return;
                objectUrl = URL.createObjectURL(blob);
                setUrl(objectUrl);
            })
            .catch(() => {});
        return () => {
            alive = false;
            if (objectUrl) URL.revokeObjectURL(objectUrl);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [key]);
    return url ? (
        <img src={url} alt={`${T.attached} ${asset}`} style={{ width: "100%", borderRadius: 6, display: "block" }} data-testid={`media-preview-${asset}`} />
    ) : (
        <span style={{ color: "var(--mw-text-3)", fontSize: 13 }} data-testid={`media-empty-${asset}`}>{post?.has_media ? T.loading : "Sem mídia"}</span>
    );
}

const HOURGLASS_CSS = `@keyframes mw-hourglass{0%{transform:rotate(0)}45%{transform:rotate(0)}55%{transform:rotate(180deg)}100%{transform:rotate(180deg)}}
.mw-hourglass{display:inline-block;animation:mw-hourglass 1.4s ease-in-out infinite}
@media (prefers-reduced-motion:reduce){.mw-hourglass{animation:none}}`;

function Hourglass({ testId }) {
    return (
        <span className="mw-hourglass" role="img" aria-label="Gerando" data-testid={testId}>
            ⏳
        </span>
    );
}

function ToneTab({ asset, tone, state, valid, anyLoading, used, height, onGenerate, onEdit, onUse }) {
    const loading = state?.state === "loading";
    const ready = state?.state === "ready";
    return (
        <div role="tabpanel" style={{ display: "grid", gap: 8 }} data-testid={`tone-panel-${asset}-${tone}`}>
            <div style={{ fontSize: 12, color: "var(--mw-text-2)" }}>{T.toneHint[tone]}</div>
            {loading && (
                <div
                    style={{ display: "flex", alignItems: "center", gap: 10, padding: "18px 12px", border: "1px dashed var(--mw-hairline-strong)", borderRadius: 8, fontSize: 14 }}
                    data-testid={`loading-${asset}-${tone}`}
                    role="status"
                >
                    <span style={{ fontSize: 22 }}><Hourglass /></span>
                    <span>
                        {T.suggesting}
                        <span style={{ display: "block", fontSize: 12, color: "var(--mw-text-3)" }}>{T.loadingHint}</span>
                    </span>
                </div>
            )}
            {ready && (
                <>
                    <textarea
                        aria-label={`${T.caption} ${tone}`}
                        rows={8}
                        style={height ? { ...field, height } : field}
                        value={state.text}
                        data-testid={`text-${tone}-${asset}`}
                        onChange={(e) => onEdit(e.target.value)}
                    />
                    <span style={{ fontSize: 12, color: "var(--mw-text-3)" }}>{state.text.length}/2200</span>
                </>
            )}
            {state?.state === "error" && (
                <div style={{ fontSize: 13, color: "var(--mw-neg)" }} data-testid={`variant-error-${asset}`}>{state.text}</div>
            )}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button
                    type="button"
                    className="mw-btn mw-btn-secondary"
                    data-testid={`suggest-${tone}-${asset}`}
                    disabled={!valid || anyLoading}
                    onClick={onGenerate}
                >
                    {loading ? <><Hourglass /> {T.suggesting}</> : ready ? T.regenerate : T.generate}
                </button>
                {ready && (
                    <button type="button" className="mw-btn mw-btn-primary" data-testid={`use-${tone}-${asset}`} disabled={used} onClick={onUse}>
                        {used ? T.inUse : T.useThis}
                    </button>
                )}
            </div>
            {!ready && !loading && !state && anyLoading && <div style={{ fontSize: 12, color: "var(--mw-text-3)" }} data-testid={`wait-${asset}-${tone}`}>{T.waitHint}</div>}
            {!ready && !loading && !state?.state && !anyLoading && <div style={{ fontSize: 12, color: "var(--mw-text-3)" }}>{T.toneNote}</div>}
        </div>
    );
}

function CardPanel({ asset, etapa1, prefs, onSave, disabled, posts, appState, run, version }) {
    const [inputs, setInputs] = useState({ key: "", status: "loading" });
    const [excluded, setExcluded] = useState(() => new Set());
    const [captionText, setCaptionText] = useState(null); // null = legenda automática
    const [busy, setBusy] = useState(false);
    const [msg, setMsg] = useState("");
    const [tones, setTones] = useState({}); // { [tom]: { state: "loading" | "ready" | "error", text } }
    const [tab, setTab] = useState("original");
    const [usedTab, setUsedTab] = useState("original"); // qual versão vai para o rascunho
    const svgRef = useRef(null);
    // A legenda tem a mesma altura da caixa do card (a imagem), para os dois lados ficarem alinhados.
    const boxRef = useRef(null);
    const [boxH, setBoxH] = useState(0);
    useEffect(() => {
        const el = boxRef.current;
        if (!el || typeof ResizeObserver === "undefined") return undefined;
        const ro = new ResizeObserver(() => setBoxH(Math.round(el.getBoundingClientRect().height)));
        ro.observe(el);
        return () => ro.disconnect();
    }, []);
    const [pin, setPin] = useState(null); // etapa escolhida à mão ({key, n}); some quando o estado do post muda
    const wanted = `${asset}|${etapa1.selected_date}|${etapa1.timestamp || etapa1.updated_at || ""}`;

    useEffect(() => {
        let cancelled = false;
        loadCardInputs({ etapa1, asset, fetchDivs }).then((r) => {
            if (!cancelled) {
                setInputs({ ...r, key: wanted });
                setExcluded(new Set());
                setCaptionText(null);
                setTones({});
                setTab("original");
                setUsedTab("original");
            }
        });
        return () => {
            cancelled = true;
        };
        // wanted resume etapa1+asset; evita recarregar quando só a referência muda
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [wanted]);

    const ready = inputs.key === wanted;
    const dateInfo = useMemo(
        () => formatSessionDateBr(ready ? inputs.sessionDate || etapa1.selected_date : etapa1.selected_date),
        [ready, inputs.sessionDate, etapa1.selected_date]
    );
    const built = useMemo(
        () =>
            ready
                ? buildInstagramSignals(inputs.bars, inputs.divergences, asset, excluded)
                : { allSignals: [], activeSignals: [], summary: {} },
        [ready, inputs, asset, excluded]
    );
    const autoCaption = useMemo(() => {
        if (!ready) return "";
        const raw = buildInstagramCaption({
            symKey: asset,
            dateInfo,
            activeSignals: built.activeSignals,
            summary: built.summary,
            handle: prefs.handle,
        });
        return finalCaption(raw, "end_of_day", asset);
    }, [ready, asset, dateInfo, built, prefs.handle]);
    const original = captionText ?? autoCaption;
    const caption = usedTab !== "original" && tones[usedTab]?.state === "ready" ? tones[usedTab].text : original;
    const post = useMemo(() => findStudioPost(posts, asset, dateInfo.iso), [posts, asset, dateInfo.iso]);
    const derived = stepOfPost(post);
    const pinKey = `${derived}:${post?.id || ""}`;
    const pinned = pin && pin.key === pinKey ? pin.n : null;
    const setPinned = (n) => setPin(n == null ? null : { key: pinKey, n });
    const step = pinned ?? derived;
    // Qual versão da legenda o rascunho carrega (só se o texto ainda for idêntico ao dela: editou à mão, some).
    const same = (a, b) => (a || "").trim() === (b || "").trim();
    const versionLabel = !post
        ? ""
        : usedTab !== "original" && tones[usedTab]?.state === "ready" && same(post.caption, tones[usedTab].text)
          ? TABS.find((x) => x.id === usedTab)?.label || ""
          : same(post.caption, original)
            ? "Original"
            : "";
    const isWdo = asset === "WDO";
    const failed = ready && (inputs.status === "sem_barras" || inputs.status === "erro_motor");
    const valid = ready && !failed && built.activeSignals.length > 0;
    const canCreate = valid && !busy && !disabled;

    const cardProps = {
        bars: ready ? inputs.bars : [],
        walls: ready ? inputs.walls : [],
        activeSignals: built.activeSignals,
        summary: built.summary,
        symKey: asset,
        dateInfo,
        brandTitle: prefs.brandTitle,
        handle: prefs.handle,
        showFlow: prefs.showFlow,
        showGauss: prefs.showGauss,
        showWalls: prefs.showWalls,
        showMidWalls: prefs.showMidWalls,
        showDivLines: prefs.showDivLines,
        rulerMode: prefs.rulerMode,
    };

    const exportItem = async () => {
        if (!valid) throw new Error(`${asset}: ${failed ? T.engineError : T.noSignals}`);
        const blob = await svgElementToPngBlob(svgRef.current, CARD_DIMENSIONS.FEED.width, CARD_DIMENSIONS.FEED.height, { embedFonts: true });
        return { kind: "end_of_day", asset, refDate: dateInfo.iso, caption, blob, mime: "image/png" };
    };

    const createOne = async () => {
        setBusy(true);
        setMsg("");
        try {
            const id = await onSave([await exportItem()]);
            if (id) setPinned(null);
        } catch (err) {
            setMsg(String(err?.message || err));
        } finally {
            setBusy(false);
        }
    };

    const generateTone = async (tone) => {
        setTones((prev) => ({ ...prev, [tone]: { state: "loading" } }));
        try {
            // sempre parte da legenda ORIGINAL (nunca de outra versão da IA)
            const res = await fetch(`${BRIDGE_BASE}/suggest`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ body: captionBody(original), asset, tone }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.variant_b) throw new Error(data.detail || `HTTP ${res.status}`);
            setTones((prev) => ({ ...prev, [tone]: { state: "ready", text: finalCaption(data.variant_b, "end_of_day", asset) } }));
        } catch (err) {
            const offline = err instanceof TypeError;
            setTones((prev) => ({ ...prev, [tone]: { state: "error", text: offline ? T.bridgeDown : String(err?.message || err) } }));
        }
    };

    const setToneText = (tone, text) => setTones((prev) => ({ ...prev, [tone]: { ...prev[tone], text } }));
    const anyLoading = Object.values(tones).some((t) => t?.state === "loading");

    // Abrir uma aba de tom gera a versão uma única vez (e só se o Strata estiver livre).
    const openTab = (id) => {
        setTab(id);
        if (id !== "original" && valid && !tones[id] && !anyLoading) generateTone(id);
    };

    const toggleSignal = (id) =>
        setExcluded((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });

    return (
        <div style={{ ...card, display: "grid", gap: 14 }} data-testid={`card-panel-${asset}`}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <strong style={{ fontSize: 15 }}>{asset}</strong>
                <span style={{ fontSize: 12, color: "var(--mw-text-2)" }}>
                    {ready ? `${built.activeSignals.length}/${built.allSignals.length} sinais` : T.loading}
                </span>
                <span style={{ flex: 1 }} />
                {post ? <StatusPill status={post.status} testId={`status-${asset}`} /> : <span style={{ fontSize: 12, color: "var(--mw-text-3)", border: "1px solid var(--mw-hairline-strong)", borderRadius: 999, padding: "2px 9px" }} data-testid={`status-${asset}`}>{T.noDraft}</span>}
            </div>

            <StepBar asset={asset} step={step} derived={derived} onPick={setPinned} />

            {failed && (
                <div style={{ fontSize: 13, color: "var(--mw-neg)" }} data-testid={`card-error-${asset}`}>
                    {inputs.status === "sem_barras" ? T.noBars : T.engineError}
                </div>
            )}
            {ready && !failed && built.allSignals.length === 0 && (
                <div style={{ fontSize: 13, color: "var(--mw-flip)" }}>{T.noSignals}</div>
            )}

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 16, alignItems: "start" }}>
                <div>
                    <div
                        ref={boxRef}
                        style={{
                            background: "var(--mw-bg)",
                            border: "1px solid var(--mw-hairline-strong)",
                            borderRadius: 10,
                            padding: 12,
                            display: "flex",
                            justifyContent: "center",
                        }}
                    >
                        {/* O SVG fica sempre montado: é dele que sai o PNG ao criar o rascunho. */}
                        <div style={{ width: "100%", maxWidth: 440, display: step === 1 ? "block" : "none" }} data-testid={`card-preview-${asset}`}>
                            <InstagramCardSvg svgRef={svgRef} variant="FEED" {...cardProps} />
                        </div>
                        {step !== 1 && (
                            <div style={{ width: "100%", maxWidth: 440 }}>
                                <PostMedia asset={asset} post={post} version={version} />
                            </div>
                        )}
                    </div>
                    {step === 1 ? (
            <div style={{ marginTop: 12 }}>
                            <div style={label}>{T.filter}</div>
                            <div style={{ display: "grid", gap: 4, maxHeight: 150, overflowY: "auto" }}>
                                {built.allSignals.map((sig) => {
                                    const on = !excluded.has(sig.id);
                                    return (
                                        <label key={sig.id} style={{ display: "flex", gap: 8, fontSize: 12, opacity: on ? 1 : 0.5, cursor: "pointer" }}>
                                            <input type="checkbox" checked={on} onChange={() => toggleSignal(sig.id)} data-testid={`sig-${asset}-${sig.num}`} />
                                            <span style={{ flex: 1 }}>
                                                {sig.entryTime} · {sig.anchorCode} {sig.isBull ? "Compra" : "Venda"}
                                            </span>
                                            <span style={{ color: sig.isStopped ? "var(--mw-neg)" : "var(--mw-pos)" }}>
                                                {sig.isStopped ? `Stop ${formatPtsLabel(sig.resultPts, isWdo)}` : formatPtsLabel(sig.mfePts, isWdo)}
                                            </span>
                                        </label>
                                    );
                                })}
                            </div>
                        </div>

                    ) : (
                        <p style={{ fontSize: 12, color: "var(--mw-text-3)", margin: "10px 0 0" }} data-testid={`card-locked-${asset}`}>🔒 {T.locked}</p>
                    )}
                </div>

                <div>
                    {step === 1 && (
                        <>
                            <div data-testid={`captions-${asset}`}>
                                <div style={label}>{T.caption}</div>
                                <div role="tablist" aria-label={T.tabsLabel} style={{ display: "flex", gap: 4, borderBottom: "1px solid var(--mw-hairline-strong)", marginBottom: 10, flexWrap: "wrap" }}>
                                    {TABS.map((t) => {
                                        const active = tab === t.id;
                                        const used = usedTab === t.id;
                                        return (
                                            <button
                                                key={t.id}
                                                type="button"
                                                role="tab"
                                                aria-selected={active}
                                                data-testid={`tab-${asset}-${t.id}`}
                                                onClick={() => openTab(t.id)}
                                                style={{
                                                    background: "transparent",
                                                    border: "none",
                                                    borderBottom: active ? "2px solid var(--mw-accent, currentColor)" : "2px solid transparent",
                                                    padding: "6px 10px",
                                                    fontSize: 13,
                                                    fontWeight: active ? 700 : 500,
                                                    color: active ? "var(--mw-text-1, inherit)" : "var(--mw-text-2)",
                                                    cursor: "pointer",
                                                }}
                                            >
                                                {tones[t.id]?.state === "loading" && <span style={{ marginRight: 4 }}><Hourglass testId={`tab-loading-${asset}-${t.id}`} /></span>}
                                                {t.label}
                                                {used && (
                                    <span
                                        title={T.inUse}
                                        data-testid={`tab-used-${asset}-${t.id}`}
                                        style={{ marginLeft: 8, display: "inline-flex", alignItems: "center", gap: 5, padding: "1px 8px", borderRadius: 999, fontSize: 11, fontWeight: 600, color: "var(--mw-pos)", background: "var(--mw-pos-bg)" }}
                                    >
                                        <span style={{ width: 6, height: 6, borderRadius: "50%", background: "currentColor" }} />
                                        em uso
                                    </span>
                                )}
                                            </button>
                                        );
                                    })}
                                </div>

                                {tab === "original" ? (
                                    <div role="tabpanel">
                                        <textarea
                                            id={`cap-${asset}`}
                                            aria-label={T.caption}
                                            rows={7}
                                            style={boxH ? { ...field, height: boxH } : field}
                                            value={original}
                                            data-testid={`caption-${asset}`}
                                            onChange={(e) => setCaptionText(e.target.value)}
                                        />
                                        <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 6 }}>
                                            <span style={{ fontSize: 12, color: "var(--mw-text-3)", flex: 1 }}>{original.length}/2200</span>
                                            {captionText !== null && (
                                                <button type="button" className="mw-btn mw-btn-secondary" onClick={() => setCaptionText(null)}>
                                                    {T.regenCaption}
                                                </button>
                                            )}
                                            {usedTab !== "original" && (
                                                <button type="button" className="mw-btn mw-btn-secondary" data-testid={`use-original-${asset}`} onClick={() => setUsedTab("original")}>
                                                    {T.useThis}
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                ) : (
                                    <ToneTab
                                        height={boxH}
                                        asset={asset}
                                        tone={tab}
                                        state={tones[tab]}
                                        valid={valid}
                                        anyLoading={anyLoading}
                                        used={usedTab === tab}
                                        onGenerate={() => generateTone(tab)}
                                        onEdit={(text) => setToneText(tab, text)}
                                        onUse={() => setUsedTab(tab)}
                                    />
                                )}
                            </div>

                            {msg && <div style={{ fontSize: 13, color: "var(--mw-neg)", marginTop: 8 }} data-testid={`card-msg-${asset}`}>{msg}</div>}
                            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginTop: 14, paddingTop: 12, borderTop: "1px solid var(--mw-hairline)" }}>
                                <button type="button" className="mw-btn mw-btn-primary" data-testid={`create-card-${asset}`} disabled={!canCreate} onClick={createOne}>
                                    {busy ? T.creating : post ? T.updateNext : T.createNext}
                                </button>
                                <span style={{ fontSize: 12, color: "var(--mw-text-3)" }}>Nada é enviado ainda.</span>
                            </div>
                        </>
                    )}
                    {step !== 1 && post && (
                        <PostStages asset={asset} post={post} textareaHeight={boxH} versionLabel={versionLabel} step={step} appState={appState} busy={disabled} run={run} version={version} onBack={() => setPinned(1)} />
                    )}
                </div>
            </div>
        </div>
    );
}

export default function CardStudio({ onSave, busy, posts, active, focus, appState, run, version }) {
    const [date, setDate] = useState("");
    const [prefs, setPrefs] = useState(() => ({ ...DEFAULT_CARD_PREFS, ...loadPrefs() }));
    const etapa = useEtapa1(date);
    // Guarda a última lista de datas conhecida: se um dia falhar, o seletor continua com as opções para voltar.
    const [seenDates, setSeenDates] = useState({ src: null, list: [] });
    const fetchedDates = etapa.data?.available_dates;
    if (Array.isArray(fetchedDates) && fetchedDates.length && seenDates.src !== fetchedDates) {
        setSeenDates({ src: fetchedDates, list: fetchedDates });
    }
    const knownDates = seenDates.list;

    // O Histórico pode pedir um dia específico (ao abrir um post antigo).
    const [lastFocus, setLastFocus] = useState(null);
    if (focus && focus !== lastFocus) {
        setLastFocus(focus);
        if (focus.date) setDate(focus.date);
    }

    const update = (patch) =>
        setPrefs((prev) => {
            const next = { ...prev, ...patch };
            savePrefs(next);
            return next;
        });

    const dates = knownDates;
    const shownDate = etapa.data?.selected_date || date;

    return (
        <section style={card} data-testid="card-studio">
            <style>{HOURGLASS_CSS}</style>
            <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
                <h2 style={{ fontSize: 15, margin: 0 }}>{T.title}</h2>
                <span style={{ color: "var(--mw-text-2)", fontSize: 13 }}>{T.hint}</span>
            </div>

            {/* Linha 1: o que identifica o post. Linha 2: como o card é desenhado. Tudo com a mesma altura. */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 12, alignItems: "end" }}>
                <div>
                    <label style={label} htmlFor="studio-date">{T.date}</label>
                    <select id="studio-date" style={control} value={shownDate} onChange={(e) => setDate(e.target.value)} data-testid="studio-date">
                        {!dates.includes(shownDate) && <option value={shownDate}>{shownDate || "…"}</option>}
                        {dates.slice(0, 60).map((d) => (
                            <option key={d} value={d}>{d}</option>
                        ))}
                    </select>
                </div>
                <div>
                    <label style={label} htmlFor="studio-brand">{T.brand}</label>
                    <input id="studio-brand" style={control} value={prefs.brandTitle} onChange={(e) => update({ brandTitle: e.target.value })} />
                </div>
                <div>
                    <label style={label} htmlFor="studio-handle">{T.handle}</label>
                    <input id="studio-handle" style={control} value={prefs.handle} onChange={(e) => update({ handle: e.target.value })} />
                </div>
            </div>

            <div style={{ display: "flex", gap: 28, flexWrap: "wrap", alignItems: "flex-end", marginTop: 14, paddingTop: 12, borderTop: "1px solid var(--mw-hairline)" }}>
                <div>
                    <div style={label}>{T.layers}</div>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {LAYERS.map((l) => (
                            <button key={l.key} type="button" aria-pressed={!!prefs[l.key]} style={pill(prefs[l.key])} onClick={() => update({ [l.key]: !prefs[l.key] })}>
                                {l.label}
                            </button>
                        ))}
                    </div>
                </div>
                <div>
                    <div style={label}>{T.ruler}</div>
                    <div role="group" aria-label={T.ruler} style={{ display: "inline-flex", border: "1px solid var(--mw-hairline-strong)", borderRadius: 8, overflow: "hidden" }}>
                        {RULERS.map((r, i) => {
                            const on = prefs.rulerMode === r.id;
                            return (
                                <button
                                    key={r.id}
                                    type="button"
                                    aria-pressed={on}
                                    onClick={() => update({ rulerMode: r.id })}
                                    style={{
                                        height: PILL_H,
                                        padding: "0 14px",
                                        fontSize: 12,
                                        cursor: "pointer",
                                        border: "none",
                                        borderLeft: i ? "1px solid var(--mw-hairline-strong)" : "none",
                                        background: on ? "var(--mw-accent-soft)" : "transparent",
                                        color: on ? "var(--mw-accent-ink)" : "var(--mw-text-2)",
                                        fontWeight: on ? 700 : 500,
                                    }}
                                >
                                    {r.label}
                                </button>
                            );
                        })}
                    </div>
                </div>
            </div>
            <div style={{ fontSize: 12, color: "var(--mw-text-3)", margin: "12px 0" }}>{T.revisit}</div>
            
            {etapa.status === "loading" && <div style={{ color: "var(--mw-text-2)" }}>{T.loading}</div>}
            {etapa.status === "erro" && <div style={{ color: "var(--mw-neg)" }} data-testid="studio-load-error">{T.loadError}</div>}
            {etapa.status === "ok" &&
                ["WIN", "WDO"].map((a) => (
                    // os dois ficam montados (a aba inativa só some da tela): o que foi gerado/editado não se perde ao trocar de aba
                    <div key={a} style={{ display: active === a ? "block" : "none" }} data-testid={`asset-pane-${a}`}>
                        <CardPanel asset={a} etapa1={etapa.data} prefs={prefs} onSave={onSave} disabled={busy} posts={posts} appState={appState} run={run} version={version} />
                    </div>
                ))}
        </section>
    );
}
