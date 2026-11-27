import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import MagicWallsMark from "./MagicWallsMark";
import {
    buildInstagramCaption,
    buildInstagramSignals,
    describeSignalRule,
    formatPtsLabel,
    formatSessionDateBr,
} from "../utils/instagramSignalMetrics";
import {
    CARD_DIMENSIONS,
    DEFAULT_CARD_PREFS,
    FONT_MONO,
    FONT_SANS,
    INK,
    InstagramCardSvg,
    loadPrefs,
    savePrefs,
    svgElementToPngBlob,
    triggerBlobDownload,
} from "./instagramCard";

/* ── Ícones UI planos (stroke 1.5) e símbolo oficial Flip Strata ── */
function WallsMarkHtml() {
    return <MagicWallsMark size={20} variant="small" />;
}

function IconDownload() {
    return (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
        </svg>
    );
}

function IconShare() {
    return (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="18" cy="5" r="3" />
            <circle cx="6" cy="12" r="3" />
            <circle cx="18" cy="19" r="3" />
            <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
            <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
        </svg>
    );
}

function IconCopy() {
    return (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="9" y="9" width="13" height="13" rx="2" />
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
    );
}

function IconChevron({ open }) {
    return (
        <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
            style={{ transform: open ? "rotate(180deg)" : "rotate(0deg)" }}
        >
            <polyline points="6 9 12 15 18 9" />
        </svg>
    );
}

/* ══════════════════════════════════════════════════════════════════════════════
   MODAL PRINCIPAL: GERADOR DE CARD INSTAGRAM (INK AZUL)
   ══════════════════════════════════════════════════════════════════════════════ */
export default function InstagramCardModal({
    isOpen,
    onClose,
    symKey = "WIN",
    sessionDate = "",
    bars = [],
    walls = [],
    divergences = [],
}) {
    const initialPrefs = useMemo(() => loadPrefs(), []);
    const [formatMode, setFormatMode] = useState(initialPrefs.formatMode || DEFAULT_CARD_PREFS.formatMode);
    const [carouselSlide, setCarouselSlide] = useState(1);
    const [showFlow, setShowFlow] = useState(initialPrefs.showFlow ?? DEFAULT_CARD_PREFS.showFlow);
    const [showGauss, setShowGauss] = useState(initialPrefs.showGauss ?? DEFAULT_CARD_PREFS.showGauss);
    const [showWalls, setShowWalls] = useState(initialPrefs.showWalls ?? DEFAULT_CARD_PREFS.showWalls);
    const [showMidWalls, setShowMidWalls] = useState(initialPrefs.showMidWalls ?? DEFAULT_CARD_PREFS.showMidWalls);
    const [showDivLines, setShowDivLines] = useState(initialPrefs.showDivLines ?? DEFAULT_CARD_PREFS.showDivLines);
    const [rulerMode, setRulerMode] = useState(initialPrefs.rulerMode || DEFAULT_CARD_PREFS.rulerMode);
    const [brandTitle, setBrandTitle] = useState(initialPrefs.brandTitle ?? DEFAULT_CARD_PREFS.brandTitle);
    const [handle, setHandle] = useState(initialPrefs.handle || DEFAULT_CARD_PREFS.handle);
    const [excludedIds, setExcludedIds] = useState(() => new Set());
    const [busyAction, setBusyAction] = useState("");
    const [statusMsg, setStatusMsg] = useState("");
    const [showSignalFilter, setShowSignalFilter] = useState(false);

    const mainSvgRef = useRef(null);
    const slide1SvgRef = useRef(null);
    const slide2SvgRef = useRef(null);

    useEffect(() => {
        setExcludedIds(new Set());
    }, [symKey, sessionDate]);

    useEffect(() => {
        savePrefs({
            formatMode,
            showFlow,
            showGauss,
            showWalls,
            showMidWalls,
            showDivLines,
            rulerMode,
            brandTitle,
            handle,
        });
    }, [formatMode, showFlow, showGauss, showWalls, showMidWalls, showDivLines, rulerMode, brandTitle, handle]);

    useEffect(() => {
        if (!isOpen) return undefined;
        const onKey = (e) => {
            if (e.key === "Escape") onClose?.();
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [isOpen, onClose]);

    const dateInfo = useMemo(() => formatSessionDateBr(sessionDate), [sessionDate]);

    const { allSignals, activeSignals, summary } = useMemo(
        () => buildInstagramSignals(bars, divergences, symKey, excludedIds, walls),
        [bars, divergences, symKey, excludedIds, walls],
    );

    const isWdo = String(symKey || "").toUpperCase() === "WDO";
    const { protTxt } = describeSignalRule(symKey);

    const flashStatus = (msg) => {
        setStatusMsg(msg);
        setTimeout(() => {
            setStatusMsg((cur) => (cur === msg ? "" : cur));
        }, 3200);
    };

    const toggleSignalId = (id) => {
        setExcludedIds((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    const buildExportFiles = async () => {
        const baseName = `magic-walls-${symKey}-${dateInfo.iso}`;
        if (formatMode === "STORIES") {
            const blob = await svgElementToPngBlob(mainSvgRef.current, CARD_DIMENSIONS.STORIES.width, CARD_DIMENSIONS.STORIES.height);
            return [{ blob, filename: `${baseName}-stories.png` }];
        }
        if (formatMode === "FEED") {
            const blob = await svgElementToPngBlob(mainSvgRef.current, CARD_DIMENSIONS.FEED.width, CARD_DIMENSIONS.FEED.height);
            return [{ blob, filename: `${baseName}-feed.png` }];
        }
        const blob1 = await svgElementToPngBlob(slide1SvgRef.current, CARD_DIMENSIONS.CAROUSEL_1.width, CARD_DIMENSIONS.CAROUSEL_1.height);
        const blob2 = await svgElementToPngBlob(slide2SvgRef.current, CARD_DIMENSIONS.CAROUSEL_2.width, CARD_DIMENSIONS.CAROUSEL_2.height);
        return [
            { blob: blob1, filename: `${baseName}-carrossel-1-grafico.png` },
            { blob: blob2, filename: `${baseName}-carrossel-2-sinais.png` },
        ];
    };

    const handleDownloadPng = async () => {
        setBusyAction("download");
        try {
            const files = await buildExportFiles();
            files.forEach((f, idx) => {
                setTimeout(() => triggerBlobDownload(f.blob, f.filename), idx * 240);
            });
            flashStatus(files.length > 1 ? "2 slides PNG baixados" : "PNG 1080px baixado");
        } catch (err) {
            flashStatus(`Erro ao exportar: ${err?.message || err}`);
        } finally {
            setBusyAction("");
        }
    };

    const handleShareNative = async () => {
        setBusyAction("share");
        try {
            const files = await buildExportFiles();
            const shareFiles = files.map((f) => new File([f.blob], f.filename, { type: "image/png" }));
            if (navigator.canShare && navigator.canShare({ files: shareFiles })) {
                await navigator.share({
                    files: shareFiles,
                    title: `${brandTitle || "Magic Walls"} · ${symKey} (${dateInfo.short})`,
                    text: buildInstagramCaption({ symKey, dateInfo, activeSignals, summary, handle }),
                });
                flashStatus("Compartilhado");
            } else {
                files.forEach((f, idx) => {
                    setTimeout(() => triggerBlobDownload(f.blob, f.filename), idx * 240);
                });
                flashStatus("Compartilhamento indisponível aqui — PNG baixado");
            }
        } catch (err) {
            if (err?.name !== "AbortError") {
                flashStatus(`Erro ao compartilhar: ${err?.message || err}`);
            }
        } finally {
            setBusyAction("");
        }
    };

    const handleCopyCaption = async () => {
        const caption = buildInstagramCaption({ symKey, dateInfo, activeSignals, summary, handle });
        try {
            await navigator.clipboard.writeText(caption);
            flashStatus("Legenda copiada");
        } catch {
            flashStatus("Não foi possível copiar automaticamente");
        }
    };

    if (!isOpen) return null;

    const canNativeShare = typeof navigator !== "undefined" && typeof navigator.share === "function";

    const sharedCardProps = {
        bars,
        walls,
        activeSignals,
        summary,
        symKey,
        dateInfo,
        brandTitle,
        handle,
        showFlow,
        showGauss,
        showWalls,
        showMidWalls,
        showDivLines,
        rulerMode,
    };

    const inputStyle = {
        width: "100%",
        boxSizing: "border-box",
        height: 36,
        padding: "0 10px",
        borderRadius: 6,
        background: INK.chrome,
        border: `1px solid ${INK.hairlineStrong}`,
        color: INK.text1,
        fontSize: 12,
        fontFamily: FONT_MONO,
    };

    const modalContent = (
        <div
            onClick={(e) => {
                if (e.target === e.currentTarget) onClose?.();
            }}
            style={{
                position: "fixed",
                inset: 0,
                zIndex: 9999,
                background: "rgba(10, 12, 18, 0.92)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                padding: 16,
                overflowY: "auto",
            }}
        >
            <div
                data-testid="ig-card-modal"
                style={{
                    width: "min(1120px, 100%)",
                    maxHeight: "94vh",
                    background: INK.bg,
                    border: `1px solid ${INK.hairlineStrong}`,
                    borderRadius: 12,
                    display: "flex",
                    flexDirection: "column",
                    overflow: "hidden",
                    color: INK.text1,
                    fontFamily: FONT_SANS,
                }}
            >
                {/* Cabeçalho sólido Ink Azul */}
                <div
                    style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: 12,
                        padding: "12px 16px",
                        borderBottom: `1px solid ${INK.hairline}`,
                        background: INK.chrome,
                        flexWrap: "wrap",
                    }}
                >
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                        <WallsMarkHtml />
                        <div>
                            <div style={{ fontWeight: 600, fontSize: 14, color: INK.text1, lineHeight: 1.25 }}>
                                Gerador de Card Instagram · {symKey}
                            </div>
                            <div style={{ fontSize: 12, color: INK.text3, fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }}>
                                {dateInfo.short} · {activeSignals.length} sinais ({summary.stopCount} stop{summary.stopCount === 1 ? "" : "s"}) · Protegido após +{protTxt}
                            </div>
                        </div>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        {statusMsg && (
                            <span
                                style={{
                                    fontSize: 12,
                                    fontFamily: FONT_MONO,
                                    color: INK.accentInk,
                                    background: INK.accentSoft,
                                    border: `1px solid rgba(56, 189, 248, 0.35)`,
                                    padding: "4px 10px",
                                    borderRadius: 6,
                                }}
                            >
                                {statusMsg}
                            </span>
                        )}
                        <button
                            type="button"
                            onClick={onClose}
                            className="mw-btn mw-btn-secondary"
                            style={{ height: 32, padding: "0 12px" }}
                        >
                            Fechar
                        </button>
                    </div>
                </div>

                {/* Corpo: Controles + Preview WYSIWYG */}
                <div
                    style={{
                        display: "flex",
                        flexWrap: "wrap",
                        flex: 1,
                        overflowY: "auto",
                        minHeight: 0,
                    }}
                >
                    {/* Coluna Esquerda: Controles */}
                    <div
                        style={{
                            flex: "1 1 320px",
                            maxWidth: 380,
                            padding: 16,
                            borderRight: `1px solid ${INK.hairline}`,
                            display: "flex",
                            flexDirection: "column",
                            gap: 16,
                            background: INK.bg,
                        }}
                    >
                        {/* Formato do Post */}
                        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                            <div style={{ fontSize: 12, fontWeight: 500, color: INK.text2 }}>
                                Formato do post
                            </div>
                            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6, padding: 4, background: INK.chrome, borderRadius: 8, border: `1px solid ${INK.hairline}` }}>
                                {[
                                    { id: "FEED", label: "Feed", sub: "4:5" },
                                    { id: "STORIES", label: "Stories", sub: "9:16" },
                                    { id: "CAROUSEL", label: "Carrossel", sub: "2× 4:5" },
                                ].map((opt) => {
                                    const active = formatMode === opt.id;
                                    return (
                                        <button
                                            key={opt.id}
                                            type="button"
                                            onClick={() => setFormatMode(opt.id)}
                                            style={{
                                                padding: "6px 8px",
                                                borderRadius: 6,
                                                cursor: "pointer",
                                                background: active ? INK.raised : "transparent",
                                                border: active ? `1px solid ${INK.hairlineStrong}` : "1px solid transparent",
                                                color: active ? INK.text1 : INK.text3,
                                                display: "flex",
                                                flexDirection: "column",
                                                alignItems: "center",
                                                gap: 2,
                                                fontFamily: FONT_SANS,
                                            }}
                                        >
                                            <span style={{ fontSize: 12, fontWeight: 500 }}>{opt.label}</span>
                                            <span style={{ fontSize: 11, fontFamily: FONT_MONO, color: active ? INK.accentInk : INK.text3 }}>{opt.sub}</span>
                                        </button>
                                    );
                                })}
                            </div>
                            {formatMode === "CAROUSEL" && (
                                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                                    {[
                                        { id: 1, label: "Slide 1 · Gráfico" },
                                        { id: 2, label: "Slide 2 · Sinais" },
                                    ].map((sl) => {
                                        const active = carouselSlide === sl.id;
                                        return (
                                            <button
                                                key={sl.id}
                                                type="button"
                                                onClick={() => setCarouselSlide(sl.id)}
                                                style={{
                                                    height: 32,
                                                    padding: "0 8px",
                                                    borderRadius: 6,
                                                    fontSize: 12,
                                                    fontWeight: 500,
                                                    fontFamily: FONT_MONO,
                                                    cursor: "pointer",
                                                    background: active ? INK.raised : INK.card,
                                                    border: active ? `1px solid ${INK.accent}` : `1px solid ${INK.hairline}`,
                                                    color: active ? INK.accentInk : INK.text2,
                                                }}
                                            >
                                                {sl.label}
                                            </button>
                                        );
                                    })}
                                </div>
                            )}
                        </div>

                        {/* Camadas do Gráfico */}
                        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                            <div style={{ fontSize: 12, fontWeight: 500, color: INK.text2 }}>
                                Camadas do gráfico
                            </div>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                                {[
                                    { label: "Fluxo Smart Money", val: showFlow, onToggle: () => setShowFlow((v) => !v) },
                                    { label: "Canal Gauss", val: showGauss, onToggle: () => setShowGauss((v) => !v) },
                                    { label: "Walls", val: showWalls, onToggle: () => setShowWalls((v) => !v) },
                                    {
                                        label: "MidWalls",
                                        val: showWalls && showMidWalls,
                                        onToggle: () => {
                                            if (!showWalls) {
                                                setShowWalls(true);
                                                setShowMidWalls(true);
                                            } else {
                                                setShowMidWalls((v) => !v);
                                            }
                                        },
                                    },
                                    { label: "Linhas div.", val: showDivLines, onToggle: () => setShowDivLines((v) => !v) },
                                ].map((t) => (
                                    <button
                                        key={t.label}
                                        type="button"
                                        onClick={t.onToggle}
                                        style={{
                                            height: 28,
                                            padding: "0 10px",
                                            borderRadius: 6,
                                            fontSize: 12,
                                            fontWeight: 500,
                                            fontFamily: FONT_SANS,
                                            cursor: "pointer",
                                            display: "inline-flex",
                                            alignItems: "center",
                                            gap: 6,
                                            background: t.val ? INK.accentSoft : INK.card,
                                            border: t.val ? "1px solid rgba(56, 189, 248, 0.35)" : `1px solid ${INK.hairline}`,
                                            color: t.val ? INK.accentInk : INK.text3,
                                        }}
                                    >
                                        <span style={{ width: 6, height: 6, borderRadius: "50%", background: t.val ? INK.accent : INK.text3 }} />
                                        <span>{t.label}</span>
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Régua de pontos no gráfico */}
                        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                            <div style={{ fontSize: 12, fontWeight: 500, color: INK.text2 }}>
                                Régua de pontos no gráfico
                            </div>
                            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6, padding: 4, background: INK.chrome, borderRadius: 8, border: `1px solid ${INK.hairline}` }}>
                                {[
                                    { id: "BEST", label: "Melhor" },
                                    { id: "ALL", label: "Todos" },
                                    { id: "OFF", label: "Ocultar" },
                                ].map((r) => {
                                    const active = rulerMode === r.id;
                                    return (
                                        <button
                                            key={r.id}
                                            type="button"
                                            onClick={() => setRulerMode(r.id)}
                                            style={{
                                                height: 28,
                                                padding: "0 8px",
                                                borderRadius: 6,
                                                fontSize: 12,
                                                fontWeight: 500,
                                                fontFamily: FONT_SANS,
                                                cursor: "pointer",
                                                background: active ? INK.raised : "transparent",
                                                border: active ? `1px solid ${INK.hairlineStrong}` : "1px solid transparent",
                                                color: active ? INK.text1 : INK.text3,
                                            }}
                                        >
                                            {r.label}
                                        </button>
                                    );
                                })}
                            </div>
                        </div>

                        {/* Título & Handle */}
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                            <div>
                                <label style={{ display: "block", fontSize: 11.5, fontWeight: 500, color: INK.text3, marginBottom: 4 }}>
                                    Título do card
                                </label>
                                <input
                                    type="text"
                                    value={brandTitle}
                                    onChange={(e) => setBrandTitle(e.target.value)}
                                    placeholder="Magic Walls"
                                    maxLength={24}
                                    style={inputStyle}
                                />
                            </div>
                            <div>
                                <label style={{ display: "block", fontSize: 11.5, fontWeight: 500, color: INK.text3, marginBottom: 4 }}>
                                    Seu @instagram
                                </label>
                                <input
                                    type="text"
                                    value={handle}
                                    onChange={(e) => setHandle(e.target.value)}
                                    placeholder="@magicwallsb3"
                                    maxLength={32}
                                    style={inputStyle}
                                />
                            </div>
                        </div>

                        {/* Filtro por sinal */}
                        <div style={{ border: `1px solid ${INK.hairline}`, borderRadius: 8, background: INK.card, overflow: "hidden" }}>
                            <button
                                type="button"
                                onClick={() => setShowSignalFilter((v) => !v)}
                                style={{
                                    width: "100%",
                                    padding: "10px 12px",
                                    background: "transparent",
                                    border: "none",
                                    color: INK.text2,
                                    fontSize: 12,
                                    fontWeight: 500,
                                    fontFamily: FONT_MONO,
                                    display: "flex",
                                    justifyContent: "space-between",
                                    alignItems: "center",
                                    cursor: "pointer",
                                }}
                            >
                                <span>Filtrar sinais ({activeSignals.length}/{allSignals.length})</span>
                                <IconChevron open={showSignalFilter} />
                            </button>
                            {showSignalFilter && (
                                <div style={{ padding: "0 12px 12px", display: "flex", flexDirection: "column", gap: 4, maxHeight: 168, overflowY: "auto" }}>
                                    {allSignals.length === 0 ? (
                                        <div style={{ fontSize: 12, color: INK.text3 }}>Nenhum sinal detectado hoje.</div>
                                    ) : (
                                        allSignals.map((sig) => {
                                            const enabled = !excludedIds.has(sig.id);
                                            const dirCol = sig.isBull ? INK.pos : INK.neg;
                                            const resCol = sig.isStopped ? INK.neg : INK.pos;
                                            return (
                                                <label
                                                    key={sig.id}
                                                    style={{
                                                        display: "flex",
                                                        alignItems: "center",
                                                        justifyContent: "space-between",
                                                        gap: 8,
                                                        fontSize: 12,
                                                        fontFamily: FONT_MONO,
                                                        padding: "4px 8px",
                                                        borderRadius: 6,
                                                        background: enabled ? INK.chrome : "transparent",
                                                        opacity: enabled ? 1 : 0.45,
                                                        cursor: "pointer",
                                                    }}
                                                >
                                                    <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                                        <input
                                                            type="checkbox"
                                                            checked={enabled}
                                                            onChange={() => toggleSignalId(sig.id)}
                                                        />
                                                        <span style={{ color: INK.text1, fontWeight: 500 }}>{sig.entryTime}</span>
                                                        <span style={{ color: dirCol, fontWeight: 500 }}>
                                                            {sig.anchorCode} {sig.isBull ? "C" : "V"}
                                                        </span>
                                                    </span>
                                                    <span style={{ color: resCol, fontWeight: 500 }}>
                                                        {sig.isStopped ? `Stop ${formatPtsLabel(sig.resultPts, isWdo)}` : formatPtsLabel(sig.mfePts, isWdo)}
                                                    </span>
                                                </label>
                                            );
                                        })
                                    )}
                                </div>
                            )}
                        </div>

                        {/* Botões de Exportação */}
                        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: "auto" }}>
                            <button
                                type="button"
                                data-testid="export-ig-png-btn"
                                onClick={handleDownloadPng}
                                disabled={busyAction !== ""}
                                style={{
                                    width: "100%",
                                    height: 40,
                                    padding: "0 14px",
                                    borderRadius: 8,
                                    border: `1px solid ${INK.accent}`,
                                    background: INK.accent,
                                    color: INK.onAccent,
                                    fontSize: 13,
                                    fontWeight: 600,
                                    fontFamily: FONT_SANS,
                                    display: "inline-flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    gap: 8,
                                    cursor: busyAction ? "wait" : "pointer",
                                }}
                            >
                                <IconDownload />
                                <span>
                                    {busyAction === "download"
                                        ? "Gerando PNG..."
                                        : formatMode === "CAROUSEL"
                                            ? "Baixar 2 slides PNG (1080×1350)"
                                            : formatMode === "STORIES"
                                                ? "Baixar Stories PNG (1080×1920)"
                                                : "Baixar Feed PNG (1080×1350)"}
                                </span>
                            </button>

                            <div style={{ display: "grid", gridTemplateColumns: canNativeShare ? "1fr 1fr" : "1fr", gap: 8 }}>
                                {canNativeShare && (
                                    <button
                                        type="button"
                                        onClick={handleShareNative}
                                        disabled={busyAction !== ""}
                                        className="mw-btn mw-btn-secondary"
                                        style={{ height: 36, justifyContent: "center" }}
                                    >
                                        <IconShare />
                                        <span>Compartilhar</span>
                                    </button>
                                )}
                                <button
                                    type="button"
                                    onClick={handleCopyCaption}
                                    className="mw-btn mw-btn-secondary"
                                    style={{ height: 36, justifyContent: "center" }}
                                >
                                    <IconCopy />
                                    <span>Copiar legenda</span>
                                </button>
                            </div>
                        </div>
                    </div>

                    {/* Coluna Direita: Preview WYSIWYG */}
                    <div
                        style={{
                            flex: "2 1 440px",
                            padding: 20,
                            display: "flex",
                            flexDirection: "column",
                            alignItems: "center",
                            justifyContent: "flex-start",
                            background: INK.chrome,
                            overflowY: "auto",
                        }}
                    >
                        <div
                            style={{
                                width: "100%",
                                maxWidth: formatMode === "STORIES" ? 375 : 460,
                            }}
                        >
                            {formatMode === "STORIES" && (
                                <InstagramCardSvg svgRef={mainSvgRef} variant="STORIES" {...sharedCardProps} />
                            )}
                            {formatMode === "FEED" && (
                                <InstagramCardSvg svgRef={mainSvgRef} variant="FEED" {...sharedCardProps} />
                            )}
                            {formatMode === "CAROUSEL" && (
                                <>
                                    <div style={{ display: carouselSlide === 1 ? "block" : "none" }}>
                                        <InstagramCardSvg svgRef={slide1SvgRef} variant="CAROUSEL_1" {...sharedCardProps} />
                                    </div>
                                    <div style={{ display: carouselSlide === 2 ? "block" : "none" }}>
                                        <InstagramCardSvg svgRef={slide2SvgRef} variant="CAROUSEL_2" {...sharedCardProps} />
                                    </div>
                                </>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );

    if (typeof document !== "undefined" && document.body) {
        return createPortal(modalContent, document.body);
    }
    return modalContent;
}
