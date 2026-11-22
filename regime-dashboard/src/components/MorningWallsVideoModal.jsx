import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { API_BASE } from "../apiBase";
import { authFetch } from "../utils/saasAuth";
import MagicWallsMark from "./MagicWallsMark";
import {
    buildMorningBriefFromCompass,
    buildMorningCaption,
    DEFAULT_FALLBACK_BRIEF,
    normalizeMorningBrief,
} from "../utils/morningVideoData";
import {
    getVideoSpec,
    renderMorningFrame,
    scheduleMorningAudio,
} from "../utils/morningVideoRenderer";

const FONT_SANS = "'IBM Plex Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
const FONT_MONO = "'IBM Plex Mono', ui-monospace, SFMono-Regular, Consolas, monospace";

const INK = {
    chrome: "#0a0c12",
    bg: "#0e1118",
    card: "#131720",
    raised: "#1b212e",
    hairline: "#232836",
    hairlineStrong: "#2e3545",
    text1: "#eef0f5",
    text2: "#a3a9b8",
    text3: "#848da2",
    accent: "#38bdf8",
    accentInk: "#7dd3fc",
    accentSoft: "#102333",
    onAccent: "#070a10",
    pos: "#4cc38a",
    posSoft: "#10231b",
    neg: "#e5484d",
    negSoft: "#261316",
    flip: "#d4a259",
    flipSoft: "#211d17",
};

const STORAGE_KEY = "mw_morning_video_prefs_v1";
const IG_STORAGE_KEY = "mw_instagram_card_prefs_v2";

function loadVideoPrefs() {
    try {
        const raw = window.localStorage.getItem(STORAGE_KEY);
        if (raw) {
            const parsed = JSON.parse(raw) || {};
            if (parsed.handle === "@magicwalls") parsed.handle = "@magicwallsb3";
            if (parsed.brandTitle === "MAGIC WALLS") parsed.brandTitle = "Magic Walls";
            if (parsed.ctaUrl === "magicwalls.com.br" || parsed.ctaUrl === "walls.css-pro.com.br") {
                parsed.ctaUrl = "app.magicwalls.com.br";
            }
            if (parsed.stampLabel === "PRÉ-PREGÃO · 08:30 BRT") {
                parsed.stampLabel = "Pré-pregão · 08:30 BRT";
            }
            return parsed;
        }
        const igRaw = window.localStorage.getItem(IG_STORAGE_KEY);
        if (igRaw) {
            const ig = JSON.parse(igRaw) || {};
            const igHandle = !ig.handle || ig.handle === "@magicwalls" ? "@magicwallsb3" : ig.handle;
            return {
                brandTitle: !ig.brandTitle || ig.brandTitle === "MAGIC WALLS" ? "Magic Walls" : ig.brandTitle,
                handle: igHandle,
            };
        }
    } catch {
        // storage unavailable
    }
    return {};
}

function saveVideoPrefs(next) {
    try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
        // ignore
    }
}

function pickSupportedRecorderMime(withAudio) {
    if (typeof MediaRecorder === "undefined") return "";
    const candidates = withAudio
        ? [
            "video/mp4;codecs=avc1,mp4a.40.2",
            "video/mp4",
            "video/webm;codecs=vp9,opus",
            "video/webm;codecs=vp8,opus",
            "video/webm",
        ]
        : [
            "video/mp4;codecs=avc1",
            "video/mp4",
            "video/webm;codecs=vp9",
            "video/webm;codecs=vp8",
            "video/webm",
        ];
    for (const mime of candidates) {
        try {
            if (MediaRecorder.isTypeSupported(mime)) return mime;
        } catch {
            // ignore
        }
    }
    return "";
}

function triggerDownloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
}

/* ── Ícones UI planos (stroke 1.5) e símbolo oficial Flip Strata ── */
function WallsMarkHtml() {
    return <MagicWallsMark size={20} variant="small" />;
}

function IconRefresh() {
    return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polyline points="23 4 23 10 17 10" />
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
        </svg>
    );
}

function IconFilm() {
    return (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="2" y="4" width="20" height="16" rx="2" />
            <path d="m10 9 5 3-5 3V9z" />
        </svg>
    );
}

function IconImage() {
    return (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <polyline points="21 15 16 10 5 21" />
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

function IconPlay({ playing }) {
    if (playing) {
        return (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect x="6" y="4" width="4" height="16" />
                <rect x="14" y="4" width="4" height="16" />
            </svg>
        );
    }
    return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polygon points="5 3 19 12 5 21 5 3" />
        </svg>
    );
}

function IconVolume({ muted }) {
    return (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
            {muted ? (
                <>
                    <line x1="23" y1="9" x2="17" y2="15" />
                    <line x1="17" y1="9" x2="23" y2="15" />
                </>
            ) : (
                <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
            )}
        </svg>
    );
}

export default function MorningWallsVideoModal({
    isOpen,
    onClose,
    standalone = false,
    selectedDate = "",
    compassData = null,
}) {
    const initialPrefs = useMemo(() => loadVideoPrefs(), []);

    const [format, setFormat] = useState(initialPrefs.format === "LANDSCAPE" ? "LANDSCAPE" : "REELS");
    const [focusMode, setFocusMode] = useState(
        ["BOTH", "WIN_ONLY", "WDO_ONLY"].includes(initialPrefs.focusMode) ? initialPrefs.focusMode : "BOTH"
    );
    const [sfxEnabled, setSfxEnabled] = useState(initialPrefs.sfxEnabled !== false);
    const [brandTitle, setBrandTitle] = useState(initialPrefs.brandTitle || "Magic Walls");
    const [handle, setHandle] = useState(initialPrefs.handle || "@magicwallsb3");
    const [ctaUrl, setCtaUrl] = useState(initialPrefs.ctaUrl || "app.magicwalls.com.br");
    const [stampLabel, setStampLabel] = useState(initialPrefs.stampLabel || "Pré-pregão · 08:30 BRT");

    const [liveBriefState, setLiveBriefState] = useState(null);
    const [loadingBrief, setLoadingBrief] = useState(false);

    const [isPlaying, setIsPlaying] = useState(true);
    const [loopEnabled, setLoopEnabled] = useState(true);
    const [playbackRate, setPlaybackRate] = useState(1.0);
    const [currentTime, setCurrentTime] = useState(0);

    const [exportState, setExportState] = useState({ busy: false, progress: 0, message: "" });
    const [copiedCaption, setCopiedCaption] = useState(false);

    const canvasRef = useRef(null);
    const playTimeRef = useRef(0);
    const lastFrameTsRef = useRef(null);
    const rafRef = useRef(null);
    const audioCtxRef = useRef(null);
    const audioHandleRef = useRef(null);
    const exportCancelRef = useRef(false);

    const { brief: resolvedRawBrief, source: resolvedSource } = useMemo(
        () => buildMorningBriefFromCompass(compassData, selectedDate, liveBriefState),
        [compassData, selectedDate, liveBriefState]
    );
    const brief = useMemo(() => normalizeMorningBrief(resolvedRawBrief || DEFAULT_FALLBACK_BRIEF), [resolvedRawBrief]);
    const spec = useMemo(() => getVideoSpec(format, focusMode), [format, focusMode]);

    const renderOptions = useMemo(
        () => ({
            format,
            focusMode,
            brandTitle,
            handle,
            ctaUrl,
            stampLabel,
        }),
        [format, focusMode, brandTitle, handle, ctaUrl, stampLabel]
    );

    useEffect(() => {
        saveVideoPrefs({
            format,
            focusMode,
            sfxEnabled,
            brandTitle,
            handle,
            ctaUrl,
            stampLabel,
        });
    }, [format, focusMode, sfxEnabled, brandTitle, handle, ctaUrl, stampLabel]);

    const stopPlaybackAudio = useCallback(() => {
        if (audioHandleRef.current) {
            try {
                audioHandleRef.current.stop();
            } catch {
                // ignore
            }
            audioHandleRef.current = null;
        }
    }, []);

    const startPlaybackAudio = useCallback(
        (offsetSec) => {
            stopPlaybackAudio();
            if (!sfxEnabled) return;
            try {
                const AudioCtx = window.AudioContext || window.webkitAudioContext;
                if (!AudioCtx) return;
                if (!audioCtxRef.current || audioCtxRef.current.state === "closed") {
                    audioCtxRef.current = new AudioCtx();
                }
                const ctx = audioCtxRef.current;
                if (ctx.state === "suspended") {
                    ctx.resume().catch(() => {});
                }
                audioHandleRef.current = scheduleMorningAudio(ctx, ctx.destination, spec, offsetSec);
            } catch {
                // audio unavailable in headless/restricted environment
            }
        },
        [sfxEnabled, spec, stopPlaybackAudio]
    );

    const fetchBrief = useCallback(async () => {
        setLoadingBrief(true);
        try {
            const res = await authFetch(`${API_BASE}/api/morning-brief`, { cache: "no-store" });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const json = await res.json();
            if (json && json.ok && json.win && json.wdo) {
                setLiveBriefState(json);
            } else {
                setLiveBriefState(null);
            }
        } catch {
            setLiveBriefState(null);
        } finally {
            setLoadingBrief(false);
        }
    }, []);

    useEffect(() => {
        if (!isOpen && !standalone) return;
        fetchBrief();
    }, [isOpen, standalone, fetchBrief]);

    useEffect(() => {
        if (playTimeRef.current >= spec.duration) {
            playTimeRef.current = 0;
            setCurrentTime(0);
        }
        const canvas = canvasRef.current;
        if (canvas) {
            const ctx = canvas.getContext("2d");
            if (ctx) renderMorningFrame(ctx, playTimeRef.current, brief, renderOptions);
        }
    }, [spec, brief, renderOptions]);

    useEffect(() => {
        if (!isOpen && !standalone) return;
        if (!isPlaying) {
            stopPlaybackAudio();
            lastFrameTsRef.current = null;
            if (rafRef.current) cancelAnimationFrame(rafRef.current);
            const canvas = canvasRef.current;
            if (canvas && canvas.getContext) {
                renderMorningFrame(canvas.getContext("2d"), playTimeRef.current, brief, renderOptions);
            }
            return;
        }

        if (sfxEnabled) {
            startPlaybackAudio(playTimeRef.current);
        } else {
            stopPlaybackAudio();
        }

        let cancelled = false;
        const tick = (nowTs) => {
            if (cancelled) return;
            if (lastFrameTsRef.current == null) {
                lastFrameTsRef.current = nowTs;
            }
            const dt = Math.min(0.1, (nowTs - lastFrameTsRef.current) / 1000) * playbackRate;
            lastFrameTsRef.current = nowTs;

            let nextT = playTimeRef.current + dt;
            if (nextT >= spec.duration) {
                if (loopEnabled) {
                    nextT = 0;
                    if (sfxEnabled) startPlaybackAudio(0);
                } else {
                    nextT = spec.duration;
                    playTimeRef.current = nextT;
                    setCurrentTime(nextT);
                    setIsPlaying(false);
                    stopPlaybackAudio();
                    const canvas = canvasRef.current;
                    if (canvas) {
                        renderMorningFrame(canvas.getContext("2d"), nextT, brief, renderOptions);
                    }
                    return;
                }
            }

            playTimeRef.current = nextT;
            setCurrentTime(nextT);
            const canvas = canvasRef.current;
            if (canvas) {
                renderMorningFrame(canvas.getContext("2d"), nextT, brief, renderOptions);
            }
            rafRef.current = requestAnimationFrame(tick);
        };

        rafRef.current = requestAnimationFrame(tick);
        return () => {
            cancelled = true;
            if (rafRef.current) cancelAnimationFrame(rafRef.current);
            stopPlaybackAudio();
            lastFrameTsRef.current = null;
        };
    }, [isOpen, standalone, isPlaying, loopEnabled, playbackRate, sfxEnabled, spec, brief, renderOptions, startPlaybackAudio, stopPlaybackAudio]);

    useEffect(() => {
        return () => {
            stopPlaybackAudio();
            if (audioCtxRef.current && audioCtxRef.current.state !== "closed") {
                audioCtxRef.current.close().catch(() => {});
            }
        };
    }, [stopPlaybackAudio]);

    useEffect(() => {
        if (!isOpen || standalone) return;
        const onKeyDown = (e) => {
            if (e.key === "Escape") onClose?.();
        };
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [isOpen, standalone, onClose]);

    const seekTo = useCallback(
        (targetSec, pauseAfter = false) => {
            const clamped = Math.max(0, Math.min(spec.duration, Number(targetSec) || 0));
            playTimeRef.current = clamped;
            setCurrentTime(clamped);
            lastFrameTsRef.current = null;
            const canvas = canvasRef.current;
            if (canvas) {
                renderMorningFrame(canvas.getContext("2d"), clamped, brief, renderOptions);
            }
            if (pauseAfter) {
                setIsPlaying(false);
                stopPlaybackAudio();
            } else if (isPlaying && sfxEnabled) {
                startPlaybackAudio(clamped);
            }
        },
        [spec.duration, brief, renderOptions, isPlaying, sfxEnabled, startPlaybackAudio, stopPlaybackAudio]
    );

    const handleTogglePlay = () => {
        if (!isPlaying && playTimeRef.current >= spec.duration - 0.05) {
            playTimeRef.current = 0;
            setCurrentTime(0);
        }
        setIsPlaying((p) => !p);
    };

    const handleRestart = () => {
        playTimeRef.current = 0;
        setCurrentTime(0);
        lastFrameTsRef.current = null;
        if (isPlaying && sfxEnabled) {
            startPlaybackAudio(0);
        } else {
            setIsPlaying(true);
        }
    };

    const handleDownloadCoverPng = () => {
        const off = document.createElement("canvas");
        off.width = spec.width;
        off.height = spec.height;
        const ctx = off.getContext("2d");
        const snapTime = Math.min(spec.duration - 0.5, spec.acts[1]?.start + 3.2 || 2.0);
        renderMorningFrame(ctx, snapTime, brief, renderOptions);
        off.toBlob((blob) => {
            if (!blob) return;
            const dateTag = brief.dateBr.replace(/\//g, "-");
            const fname = `magic-walls-mapa-gex-${format.toLowerCase()}-${dateTag}.png`;
            triggerDownloadBlob(blob, fname);
            setExportState({ busy: false, progress: 100, message: "Capa PNG exportada" });
        }, "image/png", 1.0);
    };

    const handleCopyCaption = async () => {
        const txt = buildMorningCaption(brief, renderOptions);
        try {
            await navigator.clipboard.writeText(txt);
            setCopiedCaption(true);
            setTimeout(() => setCopiedCaption(false), 2600);
        } catch {
            // clipboard fallback
        }
    };

    const handleExportVideo = async () => {
        if (exportState.busy) return;
        if (typeof MediaRecorder === "undefined") {
            setExportState({
                busy: false,
                progress: 0,
                message: "Navegador sem suporte a MediaRecorder para exportar vídeo.",
            });
            return;
        }

        setIsPlaying(false);
        stopPlaybackAudio();
        exportCancelRef.current = false;
        setExportState({
            busy: true,
            progress: 1,
            message: `Renderizando ${spec.duration.toFixed(0)}s em 60fps...`,
        });

        const exportCanvas = document.createElement("canvas");
        exportCanvas.width = spec.width;
        exportCanvas.height = spec.height;
        const ectx = exportCanvas.getContext("2d");

        const videoStream = exportCanvas.captureStream(60);
        let exportAudioCtx = null;
        let exportAudioHandle = null;
        let combinedStream = videoStream;

        if (sfxEnabled) {
            try {
                const AudioCtx = window.AudioContext || window.webkitAudioContext;
                if (AudioCtx) {
                    exportAudioCtx = new AudioCtx();
                    if (exportAudioCtx.state === "suspended") {
                        await exportAudioCtx.resume();
                    }
                    const dest = exportAudioCtx.createMediaStreamDestination();
                    exportAudioHandle = scheduleMorningAudio(exportAudioCtx, dest, spec, 0);
                    const tracks = [...videoStream.getVideoTracks(), ...dest.stream.getAudioTracks()];
                    combinedStream = new MediaStream(tracks);
                }
            } catch {
                combinedStream = videoStream;
            }
        }

        const mime = pickSupportedRecorderMime(combinedStream.getAudioTracks().length > 0)
            || pickSupportedRecorderMime(false);
        const chunks = [];
        let recorder;
        try {
            recorder = new MediaRecorder(combinedStream, {
                ...(mime ? { mimeType: mime } : {}),
                videoBitsPerSecond: spec.format === "LANDSCAPE" ? 10_000_000 : 8_000_000,
                audioBitsPerSecond: 128_000,
            });
        } catch {
            recorder = new MediaRecorder(videoStream);
        }

        recorder.ondataavailable = (ev) => {
            if (ev.data && ev.data.size > 0) chunks.push(ev.data);
        };

        const donePromise = new Promise((resolve) => {
            recorder.onstop = resolve;
        });

        renderMorningFrame(ectx, 0, brief, renderOptions);
        recorder.start(250);

        const startPerf = performance.now();
        await new Promise((resolveLoop) => {
            const stepExport = (nowPerf) => {
                if (exportCancelRef.current) {
                    resolveLoop();
                    return;
                }
                const elapsedSec = (nowPerf - startPerf) / 1000;
                const tFrame = Math.min(spec.duration, elapsedSec);
                renderMorningFrame(ectx, tFrame, brief, renderOptions);

                const pct = Math.min(99, Math.round((tFrame / spec.duration) * 100));
                setExportState({
                    busy: true,
                    progress: pct,
                    message: `Renderizando vídeo 60fps (${pct}% · ${tFrame.toFixed(1)}s / ${spec.duration.toFixed(0)}s)`,
                });

                if (elapsedSec >= spec.duration) {
                    resolveLoop();
                } else {
                    requestAnimationFrame(stepExport);
                }
            };
            requestAnimationFrame(stepExport);
        });

        try {
            if (recorder.state !== "inactive") recorder.stop();
        } catch {
            // ignore
        }
        await donePromise;

        if (exportAudioHandle) {
            try {
                exportAudioHandle.stop();
            } catch {
                // ignore
            }
        }
        if (exportAudioCtx && exportAudioCtx.state !== "closed") {
            exportAudioCtx.close().catch(() => {});
        }
        combinedStream.getTracks().forEach((tr) => tr.stop());

        if (exportCancelRef.current) {
            setExportState({ busy: false, progress: 0, message: "Exportação cancelada" });
            return;
        }

        const outMime = recorder.mimeType || mime || "video/webm";
        const ext = outMime.includes("mp4") ? "mp4" : "webm";
        const blob = new Blob(chunks, { type: outMime });
        const dateTag = brief.dateBr.replace(/\//g, "-");
        const fname = `magic-walls-pre-pregao-${format.toLowerCase()}-${focusMode.toLowerCase()}-${dateTag}.${ext}`;
        triggerDownloadBlob(blob, fname);

        setExportState({
            busy: false,
            progress: 100,
            message: `Vídeo .${ext.toUpperCase()} exportado`,
        });
    };

    const handleCancelExport = () => {
        exportCancelRef.current = true;
    };

    if (!isOpen && !standalone) return null;

    const activeAct =
        spec.acts.find((a) => currentTime >= a.start && currentTime < a.end) || spec.acts[spec.acts.length - 1];

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

    const studioContent = (
        <div
            onClick={(e) => {
                if (!standalone && e.target === e.currentTarget) onClose?.();
            }}
            style={{
                position: standalone ? "relative" : "fixed",
                inset: standalone ? undefined : 0,
                minHeight: standalone ? "100vh" : undefined,
                zIndex: standalone ? 1 : 9999,
                background: standalone ? INK.bg : "rgba(10, 12, 18, 0.92)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                padding: standalone ? 16 : 16,
                boxSizing: "border-box",
                fontFamily: FONT_SANS,
                color: INK.text1,
            }}
        >
            <div
                data-testid="morning-video-studio"
                style={{
                    width: "100%",
                    maxWidth: 1320,
                    maxHeight: standalone ? "calc(100vh - 32px)" : "94vh",
                    background: INK.bg,
                    border: `1px solid ${INK.hairlineStrong}`,
                    borderRadius: 12,
                    display: "flex",
                    flexDirection: "column",
                    overflow: "hidden",
                }}
            >
                {/* Cabeçalho sólido Ink Azul */}
                <div
                    style={{
                        padding: "12px 16px",
                        borderBottom: `1px solid ${INK.hairline}`,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: 12,
                        background: INK.chrome,
                        flexWrap: "wrap",
                    }}
                >
                    <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                        <WallsMarkHtml />
                        <div>
                            <div style={{ fontSize: 14, fontWeight: 600, color: INK.text1, lineHeight: 1.25 }}>
                                Estúdio pré-pregão · Vídeo Magic Walls 08h30
                            </div>
                            <div style={{ fontSize: 12, color: INK.text3, fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }}>
                                WIN + WDO + FlipWall + Ímã GEX + Agenda macro · 60fps com áudio
                            </div>
                        </div>
                        <span
                            data-testid="brief-source-badge"
                            style={{
                                height: 24,
                                padding: "0 10px",
                                borderRadius: 999,
                                fontSize: 11.5,
                                fontWeight: 500,
                                fontFamily: FONT_MONO,
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 6,
                                background:
                                    resolvedSource === "LIVE"
                                        ? INK.posSoft
                                        : resolvedSource === "COMPASS_DAY"
                                            ? INK.accentSoft
                                            : INK.flipSoft,
                                border: `1px solid ${
                                    resolvedSource === "LIVE"
                                        ? INK.pos
                                        : resolvedSource === "COMPASS_DAY"
                                            ? INK.accentBorder
                                            : INK.flip
                                }`,
                                color:
                                    resolvedSource === "LIVE"
                                        ? INK.pos
                                        : resolvedSource === "COMPASS_DAY"
                                            ? INK.accentInk
                                            : INK.flip,
                            }}
                        >
                            {loadingBrief
                                ? "Carregando..."
                                : resolvedSource === "LIVE"
                                    ? `Dados reais · ${brief.dateBr}`
                                    : resolvedSource === "COMPASS_DAY"
                                        ? `Pregão ${brief.dateBr} · Dados do dia`
                                        : `Snapshot local · ${brief.dateBr}`}
                        </span>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <button
                            type="button"
                            onClick={fetchBrief}
                            disabled={loadingBrief}
                            className="mw-btn mw-btn-secondary"
                            style={{ height: 32, padding: "0 12px", fontFamily: FONT_MONO, fontSize: 12, display: "inline-flex", alignItems: "center", gap: 6 }}
                        >
                            <IconRefresh />
                            <span>Recarregar</span>
                        </button>
                        {!standalone && onClose && (
                            <button
                                type="button"
                                onClick={onClose}
                                className="mw-btn mw-btn-secondary"
                                style={{ height: 32, padding: "0 12px" }}
                            >
                                Fechar
                            </button>
                        )}
                    </div>
                </div>

                {/* Corpo */}
                <div style={{ display: "flex", flex: 1, minHeight: 0, overflow: "hidden", flexWrap: "wrap" }}>
                    {/* Coluna Esquerda: Controles */}
                    <div
                        style={{
                            flex: "1 1 350px",
                            maxWidth: 400,
                            padding: 16,
                            borderRight: `1px solid ${INK.hairline}`,
                            background: INK.bg,
                            display: "flex",
                            flexDirection: "column",
                            gap: 14,
                            overflowY: "auto",
                        }}
                    >
                        {/* Formato do vídeo */}
                        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                            <div style={{ fontSize: 12, fontWeight: 500, color: INK.text2 }}>
                                Formato do vídeo
                            </div>
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, padding: 4, background: INK.chrome, borderRadius: 8, border: `1px solid ${INK.hairline}` }}>
                                {[
                                    { id: "REELS", label: "9:16 Reels / Stories", sub: "1080×1920" },
                                    { id: "LANDSCAPE", label: "16:9 YouTube / Live", sub: "1920×1080" },
                                ].map((f) => {
                                    const active = format === f.id;
                                    return (
                                        <button
                                            key={f.id}
                                            type="button"
                                            data-testid={`format-${f.id}`}
                                            onClick={() => setFormat(f.id)}
                                            style={{
                                                padding: "8px 10px",
                                                borderRadius: 6,
                                                cursor: "pointer",
                                                textAlign: "left",
                                                fontFamily: FONT_SANS,
                                                background: active ? INK.raised : "transparent",
                                                border: active ? `1px solid ${INK.hairlineStrong}` : "1px solid transparent",
                                                color: active ? INK.text1 : INK.text3,
                                            }}
                                        >
                                            <div style={{ fontSize: 12, fontWeight: 500 }}>{f.label}</div>
                                            <div style={{ fontSize: 11, fontFamily: FONT_MONO, color: active ? INK.accentInk : INK.text3 }}>{f.sub}</div>
                                        </button>
                                    );
                                })}
                            </div>
                        </div>

                        {/* Roteiro e ativos */}
                        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                            <div style={{ fontSize: 12, fontWeight: 500, color: INK.text2 }}>
                                Roteiro e ativos
                            </div>
                            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6, padding: 4, background: INK.chrome, borderRadius: 8, border: `1px solid ${INK.hairline}` }}>
                                {[
                                    { id: "BOTH", label: "WIN + WDO", sub: "30s" },
                                    { id: "WIN_ONLY", label: "Só WIN", sub: "20s" },
                                    { id: "WDO_ONLY", label: "Só WDO", sub: "20s" },
                                ].map((m) => {
                                    const active = focusMode === m.id;
                                    return (
                                        <button
                                            key={m.id}
                                            type="button"
                                            data-testid={`focus-${m.id}`}
                                            onClick={() => setFocusMode(m.id)}
                                            style={{
                                                padding: "6px 8px",
                                                borderRadius: 6,
                                                cursor: "pointer",
                                                fontFamily: FONT_SANS,
                                                background: active ? INK.raised : "transparent",
                                                border: active ? `1px solid ${INK.hairlineStrong}` : "1px solid transparent",
                                                color: active ? INK.text1 : INK.text3,
                                            }}
                                        >
                                            <div style={{ fontSize: 12, fontWeight: 500 }}>{m.label}</div>
                                            <div style={{ fontSize: 11, fontFamily: FONT_MONO, color: active ? INK.accentInk : INK.text3 }}>{m.sub}</div>
                                        </button>
                                    );
                                })}
                            </div>
                        </div>

                        {/* Saltar para cena */}
                        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                            <div style={{ fontSize: 12, fontWeight: 500, color: INK.text2 }}>
                                Saltar para cena
                            </div>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                                {spec.acts.map((act, idx) => {
                                    const active = activeAct.id === act.id;
                                    const targetT = Math.min(act.end - 0.15, act.start + (act.end - act.start) * 0.52);
                                    return (
                                        <button
                                            key={act.id}
                                            type="button"
                                            data-testid={`scene-${act.id}`}
                                            onClick={() => seekTo(targetT, true)}
                                            style={{
                                                height: 28,
                                                padding: "0 10px",
                                                borderRadius: 6,
                                                fontSize: 11.5,
                                                fontFamily: FONT_MONO,
                                                fontWeight: 500,
                                                cursor: "pointer",
                                                background: active ? INK.accentSoft : INK.card,
                                                border: active ? "1px solid rgba(56, 189, 248, 0.45)" : `1px solid ${INK.hairline}`,
                                                color: active ? INK.accentInk : INK.text3,
                                            }}
                                        >
                                            {idx + 1}. {act.label}
                                        </button>
                                    );
                                })}
                            </div>
                        </div>

                        {/* Inputs de marca e CTA */}
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                            <div>
                                <label style={{ display: "block", fontSize: 11.5, fontWeight: 500, color: INK.text3, marginBottom: 4 }}>
                                    Título / marca
                                </label>
                                <input
                                    type="text"
                                    value={brandTitle}
                                    onChange={(e) => setBrandTitle(e.target.value)}
                                    maxLength={24}
                                    style={inputStyle}
                                />
                            </div>
                            <div>
                                <label style={{ display: "block", fontSize: 11.5, fontWeight: 500, color: INK.text3, marginBottom: 4 }}>
                                    @Instagram
                                </label>
                                <input
                                    type="text"
                                    value={handle}
                                    onChange={(e) => setHandle(e.target.value)}
                                    maxLength={32}
                                    style={inputStyle}
                                />
                            </div>
                            <div>
                                <label style={{ display: "block", fontSize: 11.5, fontWeight: 500, color: INK.text3, marginBottom: 4 }}>
                                    URL CTA final
                                </label>
                                <input
                                    type="text"
                                    value={ctaUrl}
                                    onChange={(e) => setCtaUrl(e.target.value)}
                                    maxLength={36}
                                    style={inputStyle}
                                />
                            </div>
                            <div>
                                <label style={{ display: "block", fontSize: 11.5, fontWeight: 500, color: INK.text3, marginBottom: 4 }}>
                                    Carimbo horário
                                </label>
                                <input
                                    type="text"
                                    value={stampLabel}
                                    onChange={(e) => setStampLabel(e.target.value)}
                                    maxLength={28}
                                    style={inputStyle}
                                />
                            </div>
                        </div>

                        {/* Toggle Áudio */}
                        <button
                            type="button"
                            onClick={() => setSfxEnabled((v) => !v)}
                            style={{
                                height: 36,
                                padding: "0 12px",
                                borderRadius: 8,
                                border: sfxEnabled ? "1px solid rgba(56, 189, 248, 0.35)" : `1px solid ${INK.hairline}`,
                                background: sfxEnabled ? INK.accentSoft : INK.card,
                                color: sfxEnabled ? INK.accentInk : INK.text3,
                                fontSize: 12,
                                fontWeight: 500,
                                fontFamily: FONT_SANS,
                                display: "flex",
                                justifyContent: "space-between",
                                alignItems: "center",
                                cursor: "pointer",
                            }}
                        >
                            <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                                <IconVolume muted={!sfxEnabled} />
                                <span>SFX e trilha institucional</span>
                            </span>
                            <span style={{ fontFamily: FONT_MONO, fontSize: 11 }}>{sfxEnabled ? "Ativo" : "Mudo"}</span>
                        </button>

                        {/* Progresso da exportação */}
                        {exportState.message && (
                            <div
                                style={{
                                    padding: "8px 10px",
                                    borderRadius: 8,
                                    border: `1px solid ${INK.hairlineStrong}`,
                                    background: INK.card,
                                    fontSize: 11.5,
                                    fontFamily: FONT_MONO,
                                    color: INK.text1,
                                }}
                            >
                                <div style={{ marginBottom: exportState.busy ? 6 : 0 }}>{exportState.message}</div>
                                {exportState.busy && (
                                    <div style={{ height: 4, borderRadius: 2, background: INK.raised, overflow: "hidden" }}>
                                        <div
                                            style={{
                                                width: `${exportState.progress}%`,
                                                height: "100%",
                                                background: INK.accent,
                                                transition: "width 120ms linear",
                                            }}
                                        />
                                    </div>
                                )}
                            </div>
                        )}

                        {/* Botões de Exportação */}
                        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: "auto" }}>
                            {!exportState.busy ? (
                                <button
                                    type="button"
                                    data-testid="export-video-btn"
                                    onClick={handleExportVideo}
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
                                        cursor: "pointer",
                                    }}
                                >
                                    <IconFilm />
                                    <span>Exportar vídeo (60fps + áudio)</span>
                                </button>
                            ) : (
                                <button
                                    type="button"
                                    onClick={handleCancelExport}
                                    style={{
                                        width: "100%",
                                        height: 40,
                                        padding: "0 14px",
                                        borderRadius: 8,
                                        border: `1px solid ${INK.neg}`,
                                        background: INK.negSoft,
                                        color: INK.neg,
                                        fontSize: 13,
                                        fontWeight: 600,
                                        fontFamily: FONT_SANS,
                                        cursor: "pointer",
                                    }}
                                >
                                    Cancelar exportação ({exportState.progress}%)
                                </button>
                            )}

                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                                <button
                                    type="button"
                                    data-testid="download-cover-btn"
                                    onClick={handleDownloadCoverPng}
                                    className="mw-btn mw-btn-secondary"
                                    style={{ height: 36, justifyContent: "center" }}
                                >
                                    <IconImage />
                                    <span>Baixar capa PNG</span>
                                </button>
                                <button
                                    type="button"
                                    data-testid="copy-caption-btn"
                                    onClick={handleCopyCaption}
                                    className="mw-btn mw-btn-secondary"
                                    style={{
                                        height: 36,
                                        justifyContent: "center",
                                        borderColor: copiedCaption ? INK.pos : undefined,
                                        color: copiedCaption ? INK.pos : undefined,
                                    }}
                                >
                                    <IconCopy />
                                    <span>{copiedCaption ? "Legenda copiada" : "Copiar legenda"}</span>
                                </button>
                            </div>
                        </div>
                    </div>

                    {/* Coluna Direita: Palco & Transporte Ink Azul */}
                    <div
                        style={{
                            flex: "2 1 520px",
                            padding: 20,
                            display: "flex",
                            flexDirection: "column",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: 16,
                            background: INK.chrome,
                            minHeight: 0,
                        }}
                    >
                        <div
                            style={{
                                flex: 1,
                                width: "100%",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                minHeight: 0,
                            }}
                        >
                            <canvas
                                ref={canvasRef}
                                data-testid="morning-video-canvas"
                                width={spec.width}
                                height={spec.height}
                                style={{
                                    borderRadius: 12,
                                    border: `1px solid ${INK.hairline}`,
                                    background: INK.bg,
                                    ...(format === "LANDSCAPE"
                                        ? { width: "100%", maxWidth: 820, maxHeight: "66vh", aspectRatio: "16 / 9", objectFit: "contain" }
                                        : { height: "68vh", maxHeight: 650, maxWidth: "100%", aspectRatio: "9 / 16", objectFit: "contain" }),
                                }}
                            />
                        </div>

                        {/* Barra de Transporte */}
                        <div
                            style={{
                                width: "100%",
                                maxWidth: 820,
                                padding: "12px 14px",
                                borderRadius: 10,
                                background: INK.card,
                                border: `1px solid ${INK.hairline}`,
                                display: "flex",
                                flexDirection: "column",
                                gap: 10,
                            }}
                        >
                            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                                <span style={{ fontFamily: FONT_MONO, fontSize: 12, fontWeight: 500, color: INK.accentInk, minWidth: 100, fontVariantNumeric: "tabular-nums" }}>
                                    {currentTime.toFixed(1)}s / {spec.duration.toFixed(1)}s
                                </span>
                                <input
                                    data-testid="timeline-slider"
                                    type="range"
                                    min={0}
                                    max={spec.duration}
                                    step={0.05}
                                    value={currentTime}
                                    onChange={(e) => seekTo(parseFloat(e.target.value), true)}
                                    style={{ flex: 1, accentColor: INK.accent, cursor: "pointer" }}
                                />
                                <span
                                    style={{
                                        fontFamily: FONT_MONO,
                                        fontSize: 12,
                                        fontWeight: 500,
                                        color: INK.text2,
                                        minWidth: 120,
                                        textAlign: "right",
                                    }}
                                >
                                    {activeAct.label}
                                </span>
                            </div>

                            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                    <button
                                        type="button"
                                        data-testid="play-pause-btn"
                                        onClick={handleTogglePlay}
                                        className="mw-btn mw-btn-secondary"
                                        style={{
                                            height: 32,
                                            padding: "0 12px",
                                            fontFamily: FONT_MONO,
                                            borderColor: isPlaying ? "rgba(56, 189, 248, 0.45)" : INK.pos,
                                            color: INK.text1,
                                            display: "inline-flex",
                                            alignItems: "center",
                                            gap: 6,
                                        }}
                                    >
                                        <IconPlay playing={isPlaying} />
                                        <span>{isPlaying ? "Pausar" : "Play"}</span>
                                    </button>
                                    <button
                                        type="button"
                                        data-testid="restart-btn"
                                        onClick={handleRestart}
                                        className="mw-btn mw-btn-secondary"
                                        style={{ height: 32, padding: "0 12px", fontFamily: FONT_MONO }}
                                    >
                                        Reiniciar
                                    </button>
                                </div>

                                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                    {[1.0, 0.5].map((spd) => (
                                        <button
                                            key={spd}
                                            type="button"
                                            onClick={() => setPlaybackRate(spd)}
                                            style={{
                                                height: 28,
                                                padding: "0 10px",
                                                borderRadius: 6,
                                                border: playbackRate === spd ? "1px solid rgba(56, 189, 248, 0.45)" : `1px solid ${INK.hairline}`,
                                                background: playbackRate === spd ? INK.accentSoft : INK.bg,
                                                color: playbackRate === spd ? INK.accentInk : INK.text3,
                                                fontSize: 11.5,
                                                fontWeight: 500,
                                                fontFamily: FONT_MONO,
                                                cursor: "pointer",
                                            }}
                                        >
                                            {spd}x
                                        </button>
                                    ))}
                                    <button
                                        type="button"
                                        onClick={() => setLoopEnabled((v) => !v)}
                                        style={{
                                            height: 28,
                                            padding: "0 10px",
                                            borderRadius: 6,
                                            border: loopEnabled ? `1px solid ${INK.pos}` : `1px solid ${INK.hairline}`,
                                            background: loopEnabled ? INK.posSoft : INK.bg,
                                            color: loopEnabled ? INK.pos : INK.text3,
                                            fontSize: 11.5,
                                            fontWeight: 500,
                                            fontFamily: FONT_MONO,
                                            cursor: "pointer",
                                        }}
                                    >
                                        Loop {loopEnabled ? "ON" : "OFF"}
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );

    if (standalone) {
        return studioContent;
    }

    if (typeof document !== "undefined" && document.body) {
        return createPortal(studioContent, document.body);
    }
    return studioContent;
}
