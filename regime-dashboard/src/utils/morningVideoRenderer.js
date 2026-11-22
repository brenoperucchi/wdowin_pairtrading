// Motor de renderização 60fps em Canvas 2D + Áudio Procedural Web Audio API
// Padrão Visual Oficial Magic Walls (Ink Azul / Unslop).

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

export function getVideoSpec(format = "REELS", focusMode = "BOTH") {
    const isLandscape = format === "LANDSCAPE";
    const width = isLandscape ? 1920 : 1080;
    const height = isLandscape ? 1080 : 1920;

    let acts;
    let duration;
    if (focusMode === "WIN_ONLY") {
        duration = 20.0;
        acts = [
            { id: "hook", label: "Abertura", start: 0.0, end: 3.5 },
            { id: "win", label: "WIN · Escada GEX", start: 3.5, end: 12.5 },
            { id: "macro", label: "Radar macro", start: 12.5, end: 16.5 },
            { id: "cta", label: "Fechamento", start: 16.5, end: 20.0 },
        ];
    } else if (focusMode === "WDO_ONLY") {
        duration = 20.0;
        acts = [
            { id: "hook", label: "Abertura", start: 0.0, end: 3.5 },
            { id: "wdo", label: "WDO · Escada GEX", start: 3.5, end: 12.5 },
            { id: "macro", label: "Radar macro", start: 12.5, end: 16.5 },
            { id: "cta", label: "Fechamento", start: 16.5, end: 20.0 },
        ];
    } else {
        duration = 30.0;
        acts = [
            { id: "hook", label: "Abertura", start: 0.0, end: 4.0 },
            { id: "win", label: "WIN · Escada GEX", start: 4.0, end: 13.0 },
            { id: "wdo", label: "WDO · Escada GEX", start: 13.0, end: 22.0 },
            { id: "macro", label: "Radar macro", start: 22.0, end: 26.5 },
            { id: "cta", label: "Fechamento", start: 26.5, end: 30.0 },
        ];
    }

    return {
        format: isLandscape ? "LANDSCAPE" : "REELS",
        focusMode,
        width,
        height,
        fps: 60,
        duration,
        acts,
    };
}

function clamp01(v) {
    return v < 0 ? 0 : v > 1 ? 1 : v;
}

function easeOutCubic(t) {
    const x = clamp01(t);
    return 1 - Math.pow(1 - x, 3);
}

function easeOutQuart(t) {
    const x = clamp01(t);
    return 1 - Math.pow(1 - x, 4);
}

function drawRoundRect(ctx, x, y, w, h, r) {
    const radius = Math.max(0, Math.min(r, w / 2, h / 2));
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.lineTo(x + w - radius, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
    ctx.lineTo(x + w, y + h - radius);
    ctx.quadraticCurveTo(x + w, y + h, x + w - radius, y + h);
    ctx.lineTo(x + radius, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - radius);
    ctx.lineTo(x, y + radius);
    ctx.quadraticCurveTo(x, y, x + radius, y);
    ctx.closePath();
}

function fitText(ctx, text, maxW) {
    const str = String(text || "");
    if (!str || ctx.measureText(str).width <= maxW) return str;
    let lo = 0;
    let hi = str.length;
    while (lo < hi) {
        const mid = Math.ceil((lo + hi) / 2);
        if (ctx.measureText(str.slice(0, mid) + "…").width <= maxW) {
            lo = mid;
        } else {
            hi = mid - 1;
        }
    }
    return str.slice(0, Math.max(1, lo)) + "…";
}

function wrapLines(ctx, text, maxW, maxLines = 3) {
    const words = String(text || "").split(/\s+/).filter(Boolean);
    const lines = [];
    let current = "";
    for (let i = 0; i < words.length; i++) {
        const w = words[i];
        const candidate = current ? `${current} ${w}` : w;
        if (ctx.measureText(candidate).width <= maxW) {
            current = candidate;
        } else {
            if (lines.length === maxLines - 1) {
                const rest = [current, ...words.slice(i)].filter(Boolean).join(" ");
                lines.push(fitText(ctx, rest, maxW));
                current = "";
                break;
            }
            if (current) lines.push(current);
            current = w;
        }
    }
    if (current && lines.length < maxLines) {
        lines.push(fitText(ctx, current, maxW));
    }
    return lines.slice(0, maxLines);
}

function formatLadderNumber(val, isWdo) {
    const n = Number(val);
    if (!Number.isFinite(n)) return "—";
    if (isWdo) return n.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    return Math.round(n).toLocaleString("pt-BR");
}

// Marca oficial Magic Walls — Flip Strata (BRAND_GUIDELINES.md, chanfros 45°, sem rx)
// Usa corte óptico pequeno (44u) para size <= 24px e corte mestre (36u) acima de 24px.
function drawWallsMark(ctx, x, y, size = 24) {
    const s = size / 256;
    const isSmall = size <= 24;

    ctx.save();
    ctx.translate(x, y);
    ctx.scale(s, s);

    if (isSmall) {
        // Call Wall (topo) — #eef0f5: M24 28 H178 L134 72 H24 Z
        ctx.fillStyle = INK.text1;
        ctx.beginPath();
        ctx.moveTo(24, 28);
        ctx.lineTo(178, 28);
        ctx.lineTo(134, 72);
        ctx.lineTo(24, 72);
        ctx.closePath();
        ctx.fill();

        // FlipWall (eixo central) — #38bdf8: M24 106 H232 V150 H24 Z
        ctx.fillStyle = INK.accent;
        ctx.fillRect(24, 106, 208, 44);

        // Put Wall (base) — #848da2: M122 184 H232 V228 H78 Z
        ctx.fillStyle = INK.text3;
        ctx.beginPath();
        ctx.moveTo(122, 184);
        ctx.lineTo(232, 184);
        ctx.lineTo(232, 228);
        ctx.lineTo(78, 228);
        ctx.closePath();
        ctx.fill();
    } else {
        // Call Wall (topo) — #eef0f5: M28 35 H175 L139 71 H28 Z
        ctx.fillStyle = INK.text1;
        ctx.beginPath();
        ctx.moveTo(28, 35);
        ctx.lineTo(175, 35);
        ctx.lineTo(139, 71);
        ctx.lineTo(28, 71);
        ctx.closePath();
        ctx.fill();

        // FlipWall (eixo central) — #38bdf8: M28 110 H228 V146 H28 Z
        ctx.fillStyle = INK.accent;
        ctx.fillRect(28, 110, 200, 36);

        // Put Wall (base) — #848da2: M117 185 H228 V221 H81 Z
        ctx.fillStyle = INK.text3;
        ctx.beginPath();
        ctx.moveTo(117, 185);
        ctx.lineTo(228, 185);
        ctx.lineTo(228, 221);
        ctx.lineTo(81, 221);
        ctx.closePath();
        ctx.fill();
    }

    ctx.restore();
}

// Indicador geométrico de 1–3 níveis de força GEX (substitui estrelas)
function drawStrengthBlocks(ctx, x, y, level, color) {
    const filled = Math.max(1, Math.min(3, Number(level) || 1));
    const bw = 5;
    const bh = 11;
    const gap = 3;
    for (let i = 0; i < 3; i += 1) {
        drawRoundRect(ctx, x + i * (bw + gap), y - bh / 2, bw, bh, 1.5);
        ctx.fillStyle = i < filled ? color : INK.raised;
        ctx.fill();
    }
}

function drawVectorCheck(ctx, cx, cy, size, color) {
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.4;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(cx - size * 0.42, cy + size * 0.02);
    ctx.lineTo(cx - size * 0.10, cy + size * 0.34);
    ctx.lineTo(cx + size * 0.44, cy - size * 0.28);
    ctx.stroke();
    ctx.restore();
}

function drawBackground(ctx, w, h) {
    ctx.fillStyle = INK.bg;
    ctx.fillRect(0, 0, w, h);
}

function drawSafeTopBar(ctx, spec, brief, tSec, activeAct, options) {
    const isLand = spec.format === "LANDSCAPE";
    const padX = isLand ? 68 : 56;
    const topY = isLand ? 28 : 80;
    const barW = spec.width - padX * 2;
    const actIdx = Math.max(0, spec.acts.findIndex((a) => a.id === activeAct.id));

    ctx.save();
    // Barra de progresso superior em N segmentos finos de 3px
    const gap = 8;
    const count = spec.acts.length;
    const segW = (barW - gap * (count - 1)) / count;
    for (let i = 0; i < count; i += 1) {
        const a = spec.acts[i];
        const sx = padX + i * (segW + gap);
        drawRoundRect(ctx, sx, topY, segW, 3, 1.5);
        ctx.fillStyle = INK.raised;
        ctx.fill();

        const actProg = clamp01((tSec - a.start) / Math.max(0.1, a.end - a.start));
        if (actProg > 0) {
            drawRoundRect(ctx, sx, topY, Math.max(3, segW * actProg), 3, 1.5);
            ctx.fillStyle = a.id === activeAct.id ? INK.accent : INK.hairlineStrong;
            ctx.fill();
        }
    }

    // Linha de marca + ato atual à esquerda e data à direita
    const rowY = topY + 26;
    const topMarkSize = 22;
    drawWallsMark(ctx, padX, rowY - topMarkSize / 2, topMarkSize);

    const title = String(options.brandTitle || "Magic Walls").trim() || "Magic Walls";
    ctx.font = `600 ${isLand ? 18 : 19}px ${FONT_SANS}`;
    ctx.fillStyle = INK.text1;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText(title, padX + topMarkSize + 12, rowY + 1);
    const titleW = ctx.measureText(title).width;

    ctx.font = `400 ${isLand ? 16 : 17}px ${FONT_MONO}`;
    ctx.fillStyle = INK.text3;
    ctx.fillText(`  ·  ${actIdx + 1}/${count} ${activeAct.label}`, padX + topMarkSize + 12 + titleW, rowY + 1);

    ctx.textAlign = "right";
    ctx.font = `500 ${isLand ? 16 : 17}px ${FONT_MONO}`;
    ctx.fillStyle = INK.text2;
    ctx.fillText(`${options.stampLabel || "Pré-pregão · 08:30 BRT"}  ·  ${brief.dateBr}`, padX + barW, rowY + 1);
    ctx.restore();
}

function drawSafeFooter(ctx, spec, options) {
    const isLand = spec.format === "LANDSCAPE";
    const padX = isLand ? 68 : 56;
    const barW = spec.width - padX * 2;
    const lineY = isLand ? spec.height - 54 : spec.height - 144;
    const textY = lineY + 24;

    ctx.save();
    ctx.strokeStyle = INK.hairline;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padX, lineY);
    ctx.lineTo(padX + barW, lineY);
    ctx.stroke();

    ctx.textBaseline = "middle";
    ctx.font = `500 ${isLand ? 14 : 15}px ${FONT_MONO}`;
    ctx.fillStyle = INK.text2;
    ctx.textAlign = "left";
    ctx.fillText(options.handle || "@magicwallsb3", padX, textY);

    ctx.font = `400 ${isLand ? 14 : 15}px ${FONT_SANS}`;
    ctx.fillStyle = INK.text3;
    ctx.textAlign = "right";
    ctx.fillText("Estudo quantitativo educacional · Sem recomendação", padX + barW, textY);
    ctx.restore();
}

function drawHookScene(ctx, spec, brief, tLocal, actDur, options) {
    const isLand = spec.format === "LANDSCAPE";
    const enter = easeOutCubic(tLocal / 0.75);
    const fadeOut = tLocal > actDur - 0.35 ? 1 - easeOutCubic((tLocal - (actDur - 0.35)) / 0.35) : 1;

    ctx.save();
    ctx.globalAlpha = fadeOut;
    const cx = spec.width / 2;
    const cy = isLand ? spec.height * 0.44 : spec.height * 0.40;
    const padX = isLand ? 68 : 56;

    // Símbolo oficial Flip Strata centralizado + pill estática
    const heroMarkSize = isLand ? 60 : 68;
    const markY = cy - (isLand ? 314 : 400) + (1 - enter) * 14;
    drawWallsMark(ctx, cx - heroMarkSize / 2, markY, heroMarkSize);

    const pillText = options.stampLabel || "Pré-pregão · 08:30 BRT";
    ctx.font = `500 17px ${FONT_MONO}`;
    const pillW = Math.min(spec.width - padX * 2, ctx.measureText(pillText).width + 40);
    const pillX = cx - pillW / 2;
    const pillY = markY + heroMarkSize + 24;
    drawRoundRect(ctx, pillX, pillY, pillW, 38, 8);
    ctx.fillStyle = INK.card;
    ctx.fill();
    ctx.strokeStyle = INK.hairlineStrong;
    ctx.lineWidth = 1.2;
    ctx.stroke();

    ctx.fillStyle = INK.accentInk;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(pillText, cx, pillY + 19);

    // Título principal em sentence case
    const headlineY = pillY + (isLand ? 84 : 104) + (1 - enter) * 16;
    ctx.font = `600 ${isLand ? 76 : 72}px ${FONT_SANS}`;
    ctx.fillStyle = INK.text1;
    ctx.fillText("Mapa de liquidez", cx, headlineY);

    ctx.font = `600 ${isLand ? 68 : 66}px ${FONT_MONO}`;
    ctx.fillStyle = INK.accent;
    ctx.fillText("WIN × WDO", cx, headlineY + (isLand ? 82 : 84));

    ctx.font = `500 ${isLand ? 22 : 24}px ${FONT_MONO}`;
    ctx.fillStyle = INK.text2;
    ctx.fillText(`Pregão ${brief.dateBr}`, cx, headlineY + (isLand ? 144 : 152));

    // Dois cards lado a lado WIN e WDO com trilho esquerdo semântico de 2px
    const cardsProg = easeOutQuart((tLocal - 0.55) / 0.75);
    if (cardsProg > 0) {
        const cardW = isLand ? 460 : 464;
        const cardH = isLand ? 176 : 216;
        const gap = isLand ? 36 : 24;
        const totalW = cardW * 2 + gap;
        const startX = cx - totalW / 2;
        const cardY = headlineY + (isLand ? 196 : 214) + (1 - cardsProg) * 16;

        const items = [
            { tag: "WIN", label: "Mini-Índice", data: brief.win },
            { tag: "WDO", label: `Mini-Dólar · ${brief.wdo.contract || "WDO"}`, data: brief.wdo },
        ];

        items.forEach((it, idx) => {
            const x = startX + idx * (cardW + gap);
            const regColor = it.data.isPositiveGamma ? INK.pos : INK.neg;
            const regSoft = it.data.isPositiveGamma ? INK.posSoft : INK.negSoft;

            ctx.save();
            ctx.globalAlpha *= cardsProg;
            drawRoundRect(ctx, x, cardY, cardW, cardH, 12);
            ctx.fillStyle = INK.card;
            ctx.fill();
            ctx.strokeStyle = INK.hairline;
            ctx.lineWidth = 1.2;
            ctx.stroke();

            // Trilho esquerdo 2.5px na cor do regime
            drawRoundRect(ctx, x, cardY + 14, 3, cardH - 28, 1.5);
            ctx.fillStyle = regColor;
            ctx.fill();

            drawRoundRect(ctx, x + 22, cardY + 20, 52, 24, 6);
            ctx.fillStyle = INK.raised;
            ctx.fill();
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.font = `600 13px ${FONT_MONO}`;
            ctx.fillStyle = INK.accentInk;
            ctx.fillText(it.tag, x + 48, cardY + 32);

            ctx.textAlign = "left";
            ctx.font = `500 16px ${FONT_SANS}`;
            ctx.fillStyle = INK.text3;
            ctx.fillText(fitText(ctx, it.label, cardW - 104), x + 84, cardY + 32);

            ctx.font = `600 ${isLand ? 40 : 42}px ${FONT_MONO}`;
            ctx.fillStyle = INK.text1;
            ctx.fillText(it.data.currentPriceLabel, x + 22, cardY + (isLand ? 82 : 90));

            ctx.font = `500 15px ${FONT_MONO}`;
            ctx.fillStyle = INK.flip;
            ctx.fillText(`FlipWall ${it.data.gammaFlipLabel}`, x + 22, cardY + (isLand ? 116 : 132));

            drawRoundRect(ctx, x + 22, cardY + cardH - 48, cardW - 44, 32, 6);
            ctx.fillStyle = regSoft;
            ctx.fill();
            ctx.font = `500 16px ${FONT_SANS}`;
            ctx.fillStyle = regColor;
            ctx.textAlign = "center";
            ctx.fillText(it.data.regimeLabel, x + cardW / 2, cardY + cardH - 32);
            ctx.restore();
        });
    }

    ctx.restore();
}

function drawLadderSlot(ctx, lvl, box, animProg) {
    if (animProg <= 0) return;
    const { x, y, w, h } = box;
    const slideOffset = (1 - easeOutCubic(animProg)) * 18;
    const barGrowth = easeOutQuart(Math.max(0, animProg - 0.12) / 0.88);

    ctx.save();
    ctx.globalAlpha *= easeOutCubic(animProg);
    ctx.translate(slideOffset, 0);

    let borderColor = INK.hairline;
    let bgFill = INK.card;
    let accent = lvl.distPts >= 0 ? INK.neg : INK.pos;
    let roleLabel = lvl.distPts >= 0 ? "Resistência" : "Suporte";

    if (lvl.isGammaFlip) {
        accent = INK.flip;
        borderColor = INK.flip;
        bgFill = INK.flipSoft;
        roleLabel = "FlipWall · divisor de regime";
    } else if (lvl.isMagnet) {
        accent = INK.accent;
        borderColor = INK.accent;
        bgFill = INK.accentSoft;
        roleLabel = "Grande muralha · Ímã GEX";
    } else if (lvl.isImmediateResistance) {
        accent = INK.neg;
        borderColor = INK.hairlineStrong;
        roleLabel = "Resistência imediata";
    } else if (lvl.isImmediateSupport) {
        accent = INK.pos;
        borderColor = INK.hairlineStrong;
        roleLabel = "Suporte imediato";
    }

    drawRoundRect(ctx, x, y, w, h, 10);
    ctx.fillStyle = bgFill;
    ctx.fill();
    ctx.strokeStyle = borderColor;
    ctx.lineWidth = lvl.isMagnet || lvl.isGammaFlip ? 1.5 : 1.0;
    ctx.stroke();

    // Trilho esquerdo de 3px
    drawRoundRect(ctx, x, y + 10, 3, h - 20, 1.5);
    ctx.fillStyle = accent;
    ctx.fill();

    // Preço da Wall à esquerda
    const priceX = x + 20;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.font = `600 ${h >= 84 ? 30 : 27}px ${FONT_MONO}`;
    ctx.fillStyle = INK.text1;
    ctx.fillText(lvl.priceLabel, priceX, y + h * 0.40);

    // Indicador geométrico de força + role label
    drawStrengthBlocks(ctx, priceX, y + h * 0.74, lvl.stars || 1, accent);
    ctx.font = `500 ${h >= 84 ? 14.5 : 13.5}px ${FONT_SANS}`;
    ctx.fillStyle = lvl.isMagnet || lvl.isGammaFlip ? accent : INK.text2;
    ctx.fillText(roleLabel, priceX + 28, y + h * 0.74);

    // Coluna direita: distância + barra fosca de 4px
    const rightColW = Math.min(320, w * 0.39);
    const barX = x + w - rightColW - 20;
    const distY = y + h * 0.36;

    ctx.textAlign = "right";
    ctx.font = `500 ${h >= 84 ? 18 : 16}px ${FONT_MONO}`;
    ctx.fillStyle = lvl.isGammaFlip ? INK.flip : INK.text2;
    ctx.fillText(lvl.distLabel, x + w - 20, distY);

    const gexTrackY = y + h * 0.68;
    const gexTrackH = 5;
    const gexTrackW = rightColW - 84;
    drawRoundRect(ctx, barX, gexTrackY - gexTrackH / 2, gexTrackW, gexTrackH, 2.5);
    ctx.fillStyle = INK.raised;
    ctx.fill();

    const fillW = Math.max(6, gexTrackW * lvl.gexRatio * barGrowth);
    drawRoundRect(ctx, barX, gexTrackY - gexTrackH / 2, fillW, gexTrackH, 2.5);
    ctx.fillStyle = accent;
    ctx.fill();

    ctx.font = `500 14.5px ${FONT_MONO}`;
    ctx.fillStyle = INK.text3;
    ctx.fillText(lvl.gexLabel, x + w - 20, gexTrackY);

    ctx.restore();
}

function drawCurrentPriceMarker(ctx, asset, box, animProg) {
    if (animProg <= 0) return;
    const { x, y, w, h } = box;
    const midY = y + h / 2;

    ctx.save();
    ctx.globalAlpha *= easeOutCubic(animProg);

    // Linha sólida nítida de preço de referência
    ctx.fillStyle = INK.accent;
    ctx.fillRect(x, midY - 1, w, 2);

    const pillW = Math.min(w - 24, 380);
    const pillH = Math.min(h - 6, 40);
    const px = x + 14;
    const py = midY - pillH / 2;

    drawRoundRect(ctx, px, py, pillW, pillH, 8);
    ctx.fillStyle = INK.accentSoft;
    ctx.fill();
    ctx.strokeStyle = INK.accent;
    ctx.lineWidth = 1.4;
    ctx.stroke();

    ctx.fillStyle = INK.accent;
    ctx.beginPath();
    ctx.arc(px + 18, midY, 4, 0, Math.PI * 2);
    ctx.fill();

    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.font = `600 16.5px ${FONT_MONO}`;
    ctx.fillStyle = INK.text1;
    ctx.fillText(`Preço ref. ${asset.currentPriceLabel}`, px + 32, midY);

    if (asset.magnetWall) {
        const dirArrow = asset.magnetWall.price >= asset.currentPrice ? "↑" : "↓";
        const magnetHint = `${dirArrow} Ímã GEX ${asset.magnetWall.priceLabel}`;
        ctx.font = `500 14.5px ${FONT_MONO}`;
        const mw = Math.min(260, ctx.measureText(magnetHint).width + 28);
        const mh = 32;
        const mx = x + w - mw - 12;
        const my = midY - mh / 2;
        drawRoundRect(ctx, mx, my, mw, mh, 8);
        ctx.fillStyle = INK.flipSoft;
        ctx.fill();
        ctx.strokeStyle = INK.flip;
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.textAlign = "center";
        ctx.fillStyle = INK.flip;
        ctx.fillText(magnetHint, mx + mw / 2, midY);
    }

    ctx.restore();
}

function drawAssetScene(ctx, spec, asset, tLocal, actDur, isWdo) {
    const isLand = spec.format === "LANDSCAPE";
    const headerEnter = easeOutCubic(tLocal / 0.55);
    const fadeOut = tLocal > actDur - 0.35 ? 1 - easeOutCubic((tLocal - (actDur - 0.35)) / 0.35) : 1;

    ctx.save();
    ctx.globalAlpha = fadeOut;

    const padX = isLand ? 68 : 56;
    const contentW = spec.width - padX * 2;
    const accent = asset.isPositiveGamma ? INK.pos : INK.neg;
    const regSoft = asset.isPositiveGamma ? INK.posSoft : INK.negSoft;

    const countT = easeOutCubic(tLocal / 0.95);
    const animPriceVal = asset.currentPrice * (0.985 + 0.015 * countT);
    const animPriceText = countT >= 0.99 ? asset.currentPriceLabel : formatLadderNumber(animPriceVal, isWdo);

    const tacticCards = [
        {
            label: "Resistência imediata",
            val: asset.immediateResistance?.priceLabel || "—",
            sub: asset.immediateResistance?.distLabel || "",
            color: INK.neg,
        },
        {
            label: "Suporte imediato",
            val: asset.immediateSupport?.priceLabel || "—",
            sub: asset.immediateSupport?.distLabel || "",
            color: INK.pos,
        },
        {
            label: "Ímã GEX",
            val: asset.magnetWall?.priceLabel || "—",
            sub: asset.magnetWall?.distLabel || "",
            color: INK.flip,
            stars: asset.magnetWall?.stars || 3,
        },
    ];

    const institutionalPhrase = asset.isPositiveGamma
        ? "Acima da FlipWall: agentes de liquidez atuam absorvendo extremos e defendendo as Walls."
        : "Abaixo da FlipWall: ajustes amplificam amplitude e aceleração rumo ao Ímã GEX.";

    if (!isLand) {
        // ── LAYOUT REELS 9:16 (1080×1920) ──
        const headerY = 154 + (1 - headerEnter) * 14;
        const headerH = 192;

        drawRoundRect(ctx, padX, headerY, contentW, headerH, 14);
        ctx.fillStyle = INK.card;
        ctx.fill();
        ctx.strokeStyle = INK.hairline;
        ctx.lineWidth = 1.2;
        ctx.stroke();

        // Trilho esquerdo 3px
        drawRoundRect(ctx, padX, headerY + 16, 3, headerH - 32, 1.5);
        ctx.fillStyle = accent;
        ctx.fill();

        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        ctx.font = `600 18px ${FONT_MONO}`;
        ctx.fillStyle = INK.accentInk;
        ctx.fillText(
            isWdo ? `WDO · Mini-Dólar · ${asset.contract || "WDO"}` : `WIN · Mini-Índice · ${asset.contract || "WIN"}`,
            padX + 26,
            headerY + 36
        );

        ctx.font = `600 62px ${FONT_MONO}`;
        ctx.fillStyle = INK.text1;
        ctx.fillText(animPriceText, padX + 26, headerY + 102);

        ctx.font = `400 16px ${FONT_MONO}`;
        ctx.fillStyle = INK.text3;
        ctx.fillText(`FlipWall ${asset.gammaFlipLabel} · ${asset.totalWallsCount} Walls mapeadas`, padX + 26, headerY + 158);

        // Card regime à direita
        const regW = 320;
        const regH = 108;
        const regX = padX + contentW - regW - 22;
        const regY = headerY + 42;
        drawRoundRect(ctx, regX, regY, regW, regH, 10);
        ctx.fillStyle = regSoft;
        ctx.fill();
        ctx.strokeStyle = asset.isPositiveGamma ? "rgba(76, 195, 138, 0.45)" : "rgba(229, 72, 77, 0.45)";
        ctx.lineWidth = 1.2;
        ctx.stroke();

        ctx.textAlign = "center";
        ctx.font = `600 20px ${FONT_SANS}`;
        ctx.fillStyle = accent;
        ctx.fillText(asset.regimeLabel, regX + regW / 2, regY + 38);

        ctx.font = `400 15.5px ${FONT_SANS}`;
        ctx.fillStyle = INK.text2;
        ctx.fillText(asset.regimeShort, regX + regW / 2, regY + 74);

        // Escada Vertical (7 níveis + marcador ref)
        const ladderTop = 368;
        const ladderBot = 1320;
        const levels = asset.levels || [];
        const totalItems = levels.length + 1;
        const slotGap = 10;
        const markerH = 50;
        const availForWalls = ladderBot - ladderTop - markerH - slotGap * Math.max(0, totalItems - 1);
        const wallH = Math.min(110, Math.floor(availForWalls / Math.max(1, levels.length)));

        let curY = ladderTop;
        for (let idx = 0; idx <= levels.length; idx += 1) {
            if (idx === asset.insertIndex) {
                const markerAnim = clamp01((tLocal - 0.30) / 0.50);
                drawCurrentPriceMarker(ctx, asset, { x: padX, y: curY, w: contentW, h: markerH }, markerAnim);
                curY += markerH + slotGap;
            }
            if (idx < levels.length) {
                const lvl = levels[idx];
                const delay = 0.30 + idx * 0.30;
                const animProg = clamp01((tLocal - delay) / 0.70);
                drawLadderSlot(ctx, lvl, { x: padX, y: curY, w: contentW, h: wallH }, animProg);
                curY += wallH + slotGap;
            }
        }

        // 3 Cards Táticos na base
        const cardsProg = easeOutCubic((tLocal - 2.45) / 0.70);
        if (cardsProg > 0) {
            const cardGap = 14;
            const cw = (contentW - cardGap * 2) / 3;
            const cy = 1344 + (1 - cardsProg) * 16;
            const ch = 148;
            tacticCards.forEach((tc, i) => {
                const cxBox = padX + i * (cw + cardGap);
                ctx.save();
                ctx.globalAlpha *= cardsProg;
                drawRoundRect(ctx, cxBox, cy, cw, ch, 12);
                ctx.fillStyle = INK.card;
                ctx.fill();
                ctx.strokeStyle = INK.hairline;
                ctx.lineWidth = 1.2;
                ctx.stroke();

                drawRoundRect(ctx, cxBox + 14, cy, cw - 28, 2.5, 1);
                ctx.fillStyle = tc.color;
                ctx.fill();

                ctx.textAlign = "left";
                ctx.textBaseline = "middle";
                ctx.font = `500 14px ${FONT_SANS}`;
                ctx.fillStyle = INK.text2;
                ctx.fillText(fitText(ctx, tc.label, cw - (tc.stars ? 56 : 28)), cxBox + 16, cy + 30);
                if (tc.stars) {
                    drawStrengthBlocks(ctx, cxBox + cw - 40, cy + 30, tc.stars, tc.color);
                }

                ctx.font = `600 30px ${FONT_MONO}`;
                ctx.fillStyle = INK.text1;
                ctx.fillText(tc.val, cxBox + 16, cy + 78);

                ctx.font = `500 15px ${FONT_MONO}`;
                ctx.fillStyle = tc.color;
                ctx.fillText(tc.sub || " ", cxBox + 16, cy + 120);
                ctx.restore();
            });
        }

        // Bloco Dinâmica dos market makers
        const noteProg = easeOutCubic((tLocal - 3.10) / 0.70);
        if (noteProg > 0) {
            const ny = 1514;
            const nh = 138;
            ctx.save();
            ctx.globalAlpha *= noteProg;
            drawRoundRect(ctx, padX, ny, contentW, nh, 12);
            ctx.fillStyle = INK.card;
            ctx.fill();
            ctx.strokeStyle = INK.hairline;
            ctx.lineWidth = 1.2;
            ctx.stroke();

            drawRoundRect(ctx, padX, ny + 14, 3, nh - 28, 1.5);
            ctx.fillStyle = INK.accent;
            ctx.fill();

            ctx.textAlign = "left";
            ctx.textBaseline = "middle";
            ctx.font = `500 15px ${FONT_SANS}`;
            ctx.fillStyle = INK.accentInk;
            ctx.fillText("Dinâmica dos market makers", padX + 22, ny + 28);

            ctx.font = `400 18px ${FONT_SANS}`;
            ctx.fillStyle = INK.text2;
            const lines = wrapLines(ctx, institutionalPhrase, contentW - 44, 3);
            lines.forEach((ln, li) => {
                ctx.fillText(ln, padX + 22, ny + 62 + li * 27);
            });
            ctx.restore();
        }
    } else {
        // ── LAYOUT WIDESCREEN 16:9 (1920×1080) ──
        const leftX = padX;
        const leftW = 640;
        const rightX = leftX + leftW + 40;
        const rightW = contentW - leftW - 40;
        const topY = 104;

        drawRoundRect(ctx, leftX, topY, leftW, 260, 14);
        ctx.fillStyle = INK.card;
        ctx.fill();
        ctx.strokeStyle = INK.hairline;
        ctx.lineWidth = 1.2;
        ctx.stroke();

        drawRoundRect(ctx, leftX, topY + 16, 3, 228, 1.5);
        ctx.fillStyle = accent;
        ctx.fill();

        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        ctx.font = `600 18px ${FONT_MONO}`;
        ctx.fillStyle = INK.accentInk;
        ctx.fillText(
            isWdo ? `WDO · Mini-Dólar · ${asset.contract || "WDO"}` : `WIN · Mini-Índice · ${asset.contract || "WIN"}`,
            leftX + 26,
            topY + 34
        );

        ctx.font = `600 66px ${FONT_MONO}`;
        ctx.fillStyle = INK.text1;
        ctx.fillText(animPriceText, leftX + 26, topY + 106);

        drawRoundRect(ctx, leftX + 26, topY + 168, leftW - 52, 68, 10);
        ctx.fillStyle = regSoft;
        ctx.fill();
        ctx.strokeStyle = accent;
        ctx.lineWidth = 1.2;
        ctx.stroke();

        ctx.font = `600 19px ${FONT_SANS}`;
        ctx.fillStyle = accent;
        ctx.fillText(asset.regimeLabel, leftX + 44, topY + 190);
        ctx.font = `400 15.5px ${FONT_MONO}`;
        ctx.fillStyle = INK.text2;
        ctx.fillText(`FlipWall ${asset.gammaFlipLabel} · ${asset.regimeShort}`, leftX + 44, topY + 216);

        const cardsProg = easeOutCubic((tLocal - 2.45) / 0.70);
        tacticCards.forEach((tc, i) => {
            const cy = topY + 280 + i * 114;
            ctx.save();
            ctx.globalAlpha *= cardsProg;
            drawRoundRect(ctx, leftX, cy, leftW, 100, 12);
            ctx.fillStyle = INK.card;
            ctx.fill();
            ctx.strokeStyle = INK.hairline;
            ctx.lineWidth = 1.2;
            ctx.stroke();

            drawRoundRect(ctx, leftX, cy + 12, 3, 76, 1.5);
            ctx.fillStyle = tc.color;
            ctx.fill();

            ctx.textAlign = "left";
            ctx.font = `500 14.5px ${FONT_SANS}`;
            ctx.fillStyle = INK.text2;
            ctx.fillText(tc.label, leftX + 22, cy + 30);
            if (tc.stars) {
                drawStrengthBlocks(ctx, leftX + 94, cy + 30, tc.stars, tc.color);
            }

            ctx.font = `600 32px ${FONT_MONO}`;
            ctx.fillStyle = INK.text1;
            ctx.fillText(tc.val, leftX + 22, cy + 68);

            ctx.textAlign = "right";
            ctx.font = `500 18px ${FONT_MONO}`;
            ctx.fillStyle = tc.color;
            ctx.fillText(tc.sub || "", leftX + leftW - 22, cy + 52);
            ctx.restore();
        });

        const noteY = topY + 626;
        const noteH = 236;
        ctx.save();
        ctx.globalAlpha *= easeOutCubic((tLocal - 3.10) / 0.70);
        drawRoundRect(ctx, leftX, noteY, leftW, noteH, 12);
        ctx.fillStyle = INK.card;
        ctx.fill();
        ctx.strokeStyle = INK.hairline;
        ctx.lineWidth = 1.2;
        ctx.stroke();

        drawRoundRect(ctx, leftX, noteY + 14, 3, noteH - 28, 1.5);
        ctx.fillStyle = INK.accent;
        ctx.fill();

        ctx.textAlign = "left";
        ctx.font = `500 15.5px ${FONT_SANS}`;
        ctx.fillStyle = INK.accentInk;
        ctx.fillText("Dinâmica dos market makers", leftX + 22, noteY + 32);

        ctx.font = `400 19.5px ${FONT_SANS}`;
        ctx.fillStyle = INK.text2;
        const lines = wrapLines(ctx, institutionalPhrase, leftW - 44, 4);
        lines.forEach((ln, li) => {
            ctx.fillText(ln, leftX + 22, noteY + 72 + li * 30);
        });
        ctx.restore();

        const levels = asset.levels || [];
        const totalSlots = levels.length + 1;
        const slotGap = 10;
        const markerH = 48;
        const availH = 862 - markerH - slotGap * Math.max(0, totalSlots - 1);
        const wallH = Math.min(100, Math.floor(availH / Math.max(1, levels.length)));

        let curY = topY;
        for (let idx = 0; idx <= levels.length; idx += 1) {
            if (idx === asset.insertIndex) {
                const markerAnim = clamp01((tLocal - 0.30) / 0.50);
                drawCurrentPriceMarker(ctx, asset, { x: rightX, y: curY, w: rightW, h: markerH }, markerAnim);
                curY += markerH + slotGap;
            }
            if (idx < levels.length) {
                const lvl = levels[idx];
                const delay = 0.30 + idx * 0.30;
                const animProg = clamp01((tLocal - delay) / 0.70);
                drawLadderSlot(ctx, lvl, { x: rightX, y: curY, w: rightW, h: wallH }, animProg);
                curY += wallH + slotGap;
            }
        }
    }

    ctx.restore();
}

function drawMacroScene(ctx, spec, brief, tLocal, actDur) {
    const isLand = spec.format === "LANDSCAPE";
    const enter = easeOutCubic(tLocal / 0.55);
    const fadeOut = tLocal > actDur - 0.35 ? 1 - easeOutCubic((tLocal - (actDur - 0.35)) / 0.35) : 1;

    ctx.save();
    ctx.globalAlpha = fadeOut;

    const padX = isLand ? 68 : 56;
    const contentW = spec.width - padX * 2;
    const topY = (isLand ? 108 : 154) + (1 - enter) * 14;

    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.font = `500 18px ${FONT_MONO}`;
    ctx.fillStyle = INK.accentInk;
    ctx.fillText("Radar macro e consolidação GEX", padX, topY + 14);

    ctx.font = `600 ${isLand ? 40 : 42}px ${FONT_SANS}`;
    ctx.fillStyle = INK.text1;
    ctx.fillText(`Janelas de volatilidade · ${brief.dateBr}`, padX, topY + 58);

    // Resumo WIN vs WDO
    const compY = topY + 102;
    const compGap = 20;
    const compW = (contentW - compGap) / 2;
    const compH = isLand ? 230 : 258;

    [
        { title: "WIN · Mini-Índice", a: brief.win },
        { title: `WDO · ${brief.wdo.contract || "WDO"} · Mini-Dólar`, a: brief.wdo },
    ].forEach((col, i) => {
        const cx = padX + i * (compW + compGap);
        const cardProg = easeOutCubic((tLocal - i * 0.14) / 0.5);
        const regCol = col.a.isPositiveGamma ? INK.pos : INK.neg;
        ctx.save();
        ctx.globalAlpha *= cardProg;
        drawRoundRect(ctx, cx, compY, compW, compH, 12);
        ctx.fillStyle = INK.card;
        ctx.fill();
        ctx.strokeStyle = INK.hairline;
        ctx.lineWidth = 1.2;
        ctx.stroke();

        drawRoundRect(ctx, cx, compY + 14, 3, compH - 28, 1.5);
        ctx.fillStyle = regCol;
        ctx.fill();

        ctx.font = `500 16px ${FONT_MONO}`;
        ctx.fillStyle = INK.text3;
        ctx.fillText(col.title, cx + 22, compY + 32);

        ctx.font = `600 22px ${FONT_SANS}`;
        ctx.fillStyle = regCol;
        ctx.fillText(col.a.regimeLabel, cx + 22, compY + 74);

        ctx.font = `500 16.5px ${FONT_MONO}`;
        ctx.fillStyle = INK.text2;
        ctx.fillText(`FlipWall ${col.a.gammaFlipLabel}`, cx + 22, compY + 118);
        ctx.fillText(
            `Res ${col.a.immediateResistance?.priceLabel || "—"} | Sup ${col.a.immediateSupport?.priceLabel || "—"}`,
            cx + 22,
            compY + 156
        );

        ctx.fillStyle = INK.flip;
        ctx.fillText(`Ímã GEX ${col.a.magnetWall?.priceLabel || "—"}`, cx + 22, compY + (isLand ? 196 : 206));
        drawStrengthBlocks(ctx, cx + 22 + 198, compY + (isLand ? 196 : 206), col.a.magnetWall?.stars || 3, INK.flip);
        ctx.restore();
    });

    // Painel de Agenda BRT
    const calY = compY + compH + (isLand ? 24 : 34);
    const calH = isLand ? 448 : 800;
    drawRoundRect(ctx, padX, calY, contentW, calH, 14);
    ctx.fillStyle = INK.card;
    ctx.fill();
    ctx.strokeStyle = INK.hairline;
    ctx.lineWidth = 1.2;
    ctx.stroke();

    ctx.font = `500 18px ${FONT_MONO}`;
    ctx.fillStyle = INK.accentInk;
    ctx.fillText("Horários de liquidez · Agenda BRT", padX + 24, calY + 38);

    const events = brief.calendar.events || [];
    if (!events.length) {
        ctx.font = `500 22px ${FONT_SANS}`;
        ctx.fillStyle = INK.text3;
        ctx.fillText(`Sem eventos macro arquivados para ${brief.dateBr}.`, padX + 24, calY + 120);
    } else {
        const listTop = calY + 76;
        const rowGap = isLand ? 12 : 20;
        const availCalH = calH - 104 - (brief.globalAssets?.length ? 70 : 20);
        const rowH = Math.min(isLand ? 78 : 138, Math.floor((availCalH - rowGap * (events.length - 1)) / events.length));

        events.forEach((ev, idx) => {
            const evProg = easeOutCubic((tLocal - 0.35 - idx * 0.30) / 0.60);
            if (evProg <= 0) return;
            const ry = listTop + idx * (rowH + rowGap);
            const rx = padX + 24;
            const rw = contentW - 48;

            ctx.save();
            ctx.globalAlpha *= evProg;
            ctx.translate((1 - evProg) * 18, 0);

            drawRoundRect(ctx, rx, ry, rw, rowH, 10);
            ctx.fillStyle = INK.bg;
            ctx.fill();
            ctx.strokeStyle = INK.hairline;
            ctx.lineWidth = 1.0;
            ctx.stroke();

            const timeW = 108;
            drawRoundRect(ctx, rx + 16, ry + rowH / 2 - 20, timeW, 40, 8);
            ctx.fillStyle = INK.accentSoft;
            ctx.fill();
            ctx.font = `600 20px ${FONT_MONO}`;
            ctx.fillStyle = INK.accentInk;
            ctx.textAlign = "center";
            ctx.fillText(ev.time, rx + 16 + timeW / 2, ry + rowH / 2);

            const currW = 80;
            const currX = rx + 16 + timeW + 12;
            const isBrl = ev.currency === "BRL";
            drawRoundRect(ctx, currX, ry + rowH / 2 - 20, currW, 40, 8);
            ctx.fillStyle = isBrl ? INK.posSoft : INK.flipSoft;
            ctx.fill();
            ctx.font = `600 18px ${FONT_MONO}`;
            ctx.fillStyle = isBrl ? INK.pos : INK.flip;
            ctx.fillText(ev.currency, currX + currW / 2, ry + rowH / 2);

            const textX = currX + currW + 20;
            const maxTextW = rx + rw - textX - 20;
            ctx.textAlign = "left";
            ctx.font = `500 ${isLand ? 20 : 22}px ${FONT_SANS}`;
            ctx.fillStyle = INK.text1;
            if (ev.detail) {
                ctx.fillText(fitText(ctx, ev.title, maxTextW), textX, ry + rowH * (isLand ? 0.34 : 0.37));
                ctx.font = `400 ${isLand ? 14.5 : 17}px ${FONT_MONO}`;
                ctx.fillStyle = INK.text3;
                ctx.fillText(fitText(ctx, ev.detail, maxTextW), textX, ry + rowH * (isLand ? 0.72 : 0.72));
            } else {
                ctx.fillText(fitText(ctx, ev.title, maxTextW), textX, ry + rowH * 0.5);
            }
            ctx.restore();
        });
    }

    // Faixa Global GEX discreta
    if (brief.globalAssets && brief.globalAssets.length) {
        const stripY = calY + calH - 54;
        const gGap = 12;
        const gCount = brief.globalAssets.length;
        const gw = (contentW - 48 - gGap * (gCount - 1)) / gCount;
        brief.globalAssets.forEach((ga, gi) => {
            const gx = padX + 24 + gi * (gw + gGap);
            drawRoundRect(ctx, gx, stripY, gw, 36, 8);
            ctx.fillStyle = INK.bg;
            ctx.fill();
            ctx.strokeStyle = INK.hairline;
            ctx.lineWidth = 1;
            ctx.stroke();

            const isPos = ga.regime === "POSITIVE";
            ctx.fillStyle = isPos ? INK.pos : INK.neg;
            ctx.beginPath();
            ctx.arc(gx + 16, stripY + 18, 4, 0, Math.PI * 2);
            ctx.fill();

            ctx.textAlign = "left";
            ctx.font = `500 14px ${FONT_MONO}`;
            ctx.fillStyle = INK.text2;
            ctx.fillText(fitText(ctx, `${ga.ticker.replace("_", " ")}  ${isPos ? "Γ+" : "Γ-"}`, gw - 34), gx + 28, stripY + 18);
        });
    }

    ctx.restore();
}

function drawCtaScene(ctx, spec, brief, tLocal, options) {
    const isLand = spec.format === "LANDSCAPE";
    const cx = spec.width / 2;
    const cy = spec.height / 2;
    const stampProg = easeOutCubic(tLocal / 0.50);
    const cardProg = easeOutQuart((tLocal - 0.30) / 0.65);

    ctx.save();

    // Símbolo oficial Flip Strata no encerramento + pill estática com check vetorial verde
    const ctaMarkSize = isLand ? 52 : 60;
    const ctaMarkY = cy - (isLand ? 316 : 416) + (1 - stampProg) * 14;
    ctx.save();
    ctx.globalAlpha = stampProg;
    drawWallsMark(ctx, cx - ctaMarkSize / 2, ctaMarkY, ctaMarkSize);
    ctx.restore();

    const stampText = `Publicado antes da abertura · ${brief.dateBr}`;
    ctx.font = `500 ${isLand ? 22 : 22}px ${FONT_MONO}`;
    const stampW = Math.min(isLand ? 820 : 860, ctx.measureText(stampText).width + 92);
    const stampH = 60;
    const stampY = ctaMarkY + ctaMarkSize + (isLand ? 48 : 62);

    ctx.save();
    ctx.globalAlpha = stampProg;
    drawRoundRect(ctx, cx - stampW / 2, stampY - stampH / 2, stampW, stampH, 10);
    ctx.fillStyle = INK.posSoft;
    ctx.fill();
    ctx.strokeStyle = INK.pos;
    ctx.lineWidth = 1.4;
    ctx.stroke();

    drawVectorCheck(ctx, cx - stampW / 2 + 28, stampY, 20, INK.pos);
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillStyle = INK.pos;
    ctx.fillText(stampText, cx - stampW / 2 + 52, stampY);
    ctx.restore();

    // Chamada central em sentence case
    ctx.save();
    ctx.globalAlpha = cardProg;
    const headlineY = stampY + (isLand ? 110 : 140) + (1 - cardProg) * 14;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = `600 ${isLand ? 48 : 48}px ${FONT_SANS}`;
    ctx.fillStyle = INK.text1;
    ctx.fillText("Salve este mapa e confira", cx, headlineY);
    ctx.fillStyle = INK.accent;
    ctx.fillText("no fechamento às 17h", cx, headlineY + 60);

    // Card CTA plano com botão sólido #38bdf8 + texto #070a10
    const cardW = isLand ? 860 : 880;
    const cardH = isLand ? 228 : 284;
    const cardX = cx - cardW / 2;
    const cardY = headlineY + (isLand ? 118 : 156) + (1 - cardProg) * 14;

    drawRoundRect(ctx, cardX, cardY, cardW, cardH, 16);
    ctx.fillStyle = INK.card;
    ctx.fill();
    ctx.strokeStyle = INK.hairlineStrong;
    ctx.lineWidth = 1.4;
    ctx.stroke();

    ctx.font = `500 ${isLand ? 22 : 23}px ${FONT_SANS}`;
    ctx.fillStyle = INK.text2;
    ctx.fillText("Terminal GEX + Fluxo Smart Money em tempo real", cx, cardY + 52);

    const urlW = isLand ? 540 : 600;
    const urlH = 66;
    const urlX = cx - urlW / 2;
    const urlY = cardY + (isLand ? 90 : 104);
    drawRoundRect(ctx, urlX, urlY, urlW, urlH, 10);
    ctx.fillStyle = INK.accent;
    ctx.fill();

    ctx.font = `600 ${isLand ? 28 : 30}px ${FONT_MONO}`;
    ctx.fillStyle = INK.onAccent;
    ctx.fillText(fitText(ctx, options.ctaUrl || "app.magicwalls.com.br", urlW - 40), cx, urlY + urlH / 2);

    ctx.font = `500 ${isLand ? 20 : 22}px ${FONT_MONO}`;
    ctx.fillStyle = INK.accentInk;
    ctx.fillText(options.handle || "@magicwallsb3", cx, cardY + cardH - 38);

    ctx.restore();
    ctx.restore();
}

export function renderMorningFrame(ctx, tSec, brief, options = {}) {
    const format = options.format || "REELS";
    const focusMode = options.focusMode || "BOTH";
    const spec = getVideoSpec(format, focusMode);
    const w = spec.width;
    const h = spec.height;

    ctx.save();
    ctx.clearRect(0, 0, w, h);

    const tClamped = Math.max(0, Math.min(spec.duration, Number(tSec) || 0));
    const activeAct =
        spec.acts.find((a) => tClamped >= a.start && tClamped < a.end) || spec.acts[spec.acts.length - 1];

    drawBackground(ctx, w, h);

    const tLocal = Math.max(0, tClamped - activeAct.start);
    const actDur = Math.max(0.1, activeAct.end - activeAct.start);

    if (activeAct.id === "hook") {
        drawHookScene(ctx, spec, brief, tLocal, actDur, options);
    } else if (activeAct.id === "win") {
        drawAssetScene(ctx, spec, brief.win, tLocal, actDur, false);
    } else if (activeAct.id === "wdo") {
        drawAssetScene(ctx, spec, brief.wdo, tLocal, actDur, true);
    } else if (activeAct.id === "macro") {
        drawMacroScene(ctx, spec, brief, tLocal, actDur);
    } else {
        drawCtaScene(ctx, spec, brief, tLocal, options);
    }

    drawSafeTopBar(ctx, spec, brief, tClamped, activeAct, options);
    drawSafeFooter(ctx, spec, options);

    ctx.restore();
}

// ── Motor de Áudio Procedural Web Audio API ───────────────────────────────────

function createNoiseBuffer(audioCtx, durationSec = 1.0) {
    const sampleRate = audioCtx.sampleRate || 44100;
    const length = Math.floor(sampleRate * durationSec);
    const buf = audioCtx.createBuffer(1, length, sampleRate);
    const data = buf.getChannelData(0);
    let seed = 1337;
    for (let i = 0; i < length; i++) {
        seed = (seed * 1664525 + 1013904223) >>> 0;
        data[i] = (seed / 4294967296) * 2 - 1;
    }
    return buf;
}

export function scheduleMorningAudio(audioCtx, destination, spec, startOffsetSec = 0) {
    if (!audioCtx || !destination || !spec) {
        return { stop: () => {} };
    }

    const baseTime = audioCtx.currentTime + 0.02;
    const remainingDur = Math.max(0.2, spec.duration - startOffsetSec);
    const nodes = [];

    const master = audioCtx.createGain();
    master.gain.setValueAtTime(0.0001, baseTime);
    master.gain.exponentialRampToValueAtTime(0.28, baseTime + 0.15);
    master.gain.setValueAtTime(0.28, baseTime + Math.max(0.2, remainingDur - 0.35));
    master.gain.exponentialRampToValueAtTime(0.0001, baseTime + remainingDur);

    const comp = audioCtx.createDynamicsCompressor();
    comp.threshold.value = -16;
    comp.ratio.value = 4;
    master.connect(comp);
    comp.connect(destination);
    nodes.push(master, comp);

    const atTime = (videoTimeSec) => baseTime + (videoTimeSec - startOffsetSec);

    const padGain = audioCtx.createGain();
    padGain.gain.setValueAtTime(0.18, baseTime);
    const padFilter = audioCtx.createBiquadFilter();
    padFilter.type = "lowpass";
    padFilter.frequency.setValueAtTime(220, baseTime);
    padGain.connect(padFilter);
    padFilter.connect(master);

    [55.0, 82.41].forEach((freq, idx) => {
        const osc = audioCtx.createOscillator();
        osc.type = idx === 0 ? "sine" : "triangle";
        osc.frequency.setValueAtTime(freq, baseTime);
        const oscG = audioCtx.createGain();
        oscG.gain.value = idx === 0 ? 0.65 : 0.25;
        osc.connect(oscG);
        oscG.connect(padGain);
        osc.start(baseTime);
        osc.stop(baseTime + remainingDur + 0.05);
        nodes.push(osc, oscG);
    });
    nodes.push(padGain, padFilter);

    const noiseBuf = createNoiseBuffer(audioCtx, 0.8);

    const triggerTone = (tWhen, freqStart, freqEnd, dur, gainPeak, type = "sine") => {
        if (tWhen < baseTime - 0.02 || tWhen > baseTime + remainingDur) return;
        const when = Math.max(baseTime, tWhen);
        const osc = audioCtx.createOscillator();
        const g = audioCtx.createGain();
        osc.type = type;
        osc.frequency.setValueAtTime(freqStart, when);
        if (freqEnd !== freqStart) {
            osc.frequency.exponentialRampToValueAtTime(Math.max(20, freqEnd), when + dur);
        }
        g.gain.setValueAtTime(0.0001, when);
        g.gain.exponentialRampToValueAtTime(gainPeak, when + 0.015);
        g.gain.exponentialRampToValueAtTime(0.0001, when + dur);
        osc.connect(g);
        g.connect(master);
        osc.start(when);
        osc.stop(when + dur + 0.02);
        nodes.push(osc, g);
    };

    const triggerWhoosh = (tWhen) => {
        if (tWhen < baseTime - 0.05 || tWhen > baseTime + remainingDur) return;
        const when = Math.max(baseTime, tWhen);
        const src = audioCtx.createBufferSource();
        src.buffer = noiseBuf;
        const filt = audioCtx.createBiquadFilter();
        filt.type = "bandpass";
        filt.Q.value = 1.8;
        filt.frequency.setValueAtTime(280, when);
        filt.frequency.exponentialRampToValueAtTime(1400, when + 0.28);
        const g = audioCtx.createGain();
        g.gain.setValueAtTime(0.0001, when);
        g.gain.exponentialRampToValueAtTime(0.18, when + 0.10);
        g.gain.exponentialRampToValueAtTime(0.0001, when + 0.36);
        src.connect(filt);
        filt.connect(g);
        g.connect(master);
        src.start(when);
        src.stop(when + 0.40);
        nodes.push(src, filt, g);
    };

    if (startOffsetSec < 0.3) {
        triggerTone(atTime(0.06), 115, 42, 0.42, 0.55, "sine");
        triggerTone(atTime(0.20), 880, 1320, 0.25, 0.14, "triangle");
    }

    spec.acts.forEach((act) => {
        if (act.start > 0.05) {
            triggerWhoosh(atTime(act.start));
        }
        if (act.id === "win" || act.id === "wdo") {
            for (let i = 0; i < 6; i++) {
                const tickTime = act.start + 0.35 + i * 0.34;
                const pitch = 620 + i * 65;
                triggerTone(atTime(tickTime), pitch, pitch * 1.15, 0.08, 0.11, "triangle");
            }
            triggerTone(atTime(act.start + 2.65), 1046.5, 1318.5, 0.16, 0.13, "sine");
        }
        if (act.id === "cta") {
            [220.0, 329.63, 493.88, 554.37].forEach((f) => {
                triggerTone(atTime(act.start + 0.08), f, f, 2.6, 0.09, "sine");
            });
        }
    });

    let stopped = false;
    return {
        stop: () => {
            if (stopped) return;
            stopped = true;
            const now = audioCtx.currentTime;
            try {
                master.gain.cancelScheduledValues(now);
                master.gain.setValueAtTime(0.0001, now);
            } catch {
                // ignore
            }
            nodes.forEach((n) => {
                try {
                    if (typeof n.stop === "function") n.stop(now + 0.01);
                } catch {
                    // ignore
                }
                try {
                    n.disconnect();
                } catch {
                    // ignore
                }
            });
        },
    };
}
