import { useEffect, useMemo, useRef, useState } from "react";
import MagicWallsMark from "./MagicWallsMark";

const FONT_SANS = "'IBM Plex Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
const FONT_MONO = "'IBM Plex Mono', ui-monospace, SFMono-Regular, Consolas, monospace";

const REAL_SESSION_PRINTS = [
    {
        id: "2026-11-13-dupla",
        featured: true,
        date: "13/11/2026",
        asset: "WIN × WDO · Visão dupla",
        regime: "Leitura simultânea M5",
        regimeTone: "#38bdf8",
        src: "./prints/real-2026-11-13-dupla.jpg",
        title: "Visão dupla lado a lado com Walls e divergências sincronizadas",
        summary:
            "WINZ26 marcou divergência de baixa (#2) na resistência 174.711 e defesa (#3) no suporte 173.701; no mesmo pregão, WDOZ26 registrou divergência de alta (#2) na parede 5.650,0 antes do avanço até 5.700,0.",
    },
    {
        id: "2026-11-19-win",
        featured: false,
        date: "19/11/2026",
        asset: "WINZ26 · Mini-Índice M5",
        regime: "Gamma negativo · Aceleração",
        regimeTone: "#e5484d",
        src: "./prints/real-2026-11-19-win.jpg",
        title: "Aceleração direcional abaixo da FlipWall com exaustão no fluxo",
        summary:
            "Abaixo da FlipWall (173.335), as divergências de baixa #4 e #6 no topo do canal antecederam a expansão vendedora até 166.959, onde o Fluxo Smart Money marcou absorção compradora (#8 e #9).",
    },
    {
        id: "2026-11-18-wdo",
        featured: false,
        date: "18/11/2026",
        asset: "WDOZ26 · Mini-Dólar M5",
        regime: "Gamma positivo · Defesa",
        regimeTone: "#4cc38a",
        src: "./prints/real-2026-11-18-wdo.jpg",
        title: "Defesa na Wall de 5.800,0 e deslocamento limpo entre MidWalls",
        summary:
            "Acima da FlipWall (5.679,2), o dólar encontrou suporte na região 5.800,0 (sinal #3) e avançou de forma cadenciada pelo Canal Gauss até testar a resistência de 5.900,0 (#8).",
    },
];

const FAQ_ITEMS = [
    {
        q: "O que exatamente está incluído na assinatura do Magic Walls?",
        a: "Você acessa o terminal web em tempo real para mini-índice (WIN) e mini-dólar (WDO) com o mapa diário de Walls (Call Wall, Put Wall, MidWalls e FlipWall), Canal Gauss e o subpainel Fluxo Smart Money com marcação visual de divergências em M5 e M1.",
    },
    {
        q: "Quando os níveis do dia ficam disponíveis?",
        a: "Os níveis são processados e liberados diariamente assim que a B3 publica os dados oficiais do pregão anterior. Em pregões regulares costumam ficar prontos cedo, podendo variar caso haja atraso na divulgação oficial da bolsa.",
    },
    {
        q: "Preciso instalar algum programa ou conectar minha corretora?",
        a: "Não. O Magic Walls é um terminal web completo acessado diretamente pelo navegador (computador, notebook, tablet ou celular), sem exigir instalação de plugins, arquivos externos nem integração com sua corretora.",
    },
    {
        q: "Qual a diferença prática entre Gamma positivo e Gamma negativo no pregão?",
        a: "Em Gamma positivo (preço acima da FlipWall), a liquidez tende a absorver extremos nas Walls e favorecer movimentos de retorno. Em Gamma negativo (abaixo da FlipWall), o mercado tende a ganhar velocidade e expandir amplitude direcional até alcançar paredes mais fortes.",
    },
    {
        q: "Como ler a marcação de divergência no Fluxo Smart Money?",
        a: "A marcação destaca quando o preço testa ou renova uma máxima/mínima em região de Wall, mas o fluxo institucional deixa de acompanhar o movimento (topo menor na alta ou fundo maior na baixa), evidenciando absorção passiva ou perda de força institucional naquele ponto.",
    },
    {
        q: "O Magic Walls é sala de sinais, call ao vivo ou robô automático?",
        a: "Não. O Magic Walls é um software analítico e educacional de leitura de liquidez e fluxo (Resolução CVM nº 20/2021). Ele não envia ordens automáticas nem faz recomendação de compra ou venda — toda decisão operacional é exclusivamente sua.",
    },
    {
        q: "Como faço para contratar ou acompanhar o trabalho antes de assinar?",
        a: "Fale diretamente com nossa equipe pelo Instagram oficial @magicwallsb3. Por lá também publicamos estudos do dia e resumos visuais de fechamento de pregão.",
    },
];

const HERO_SPECS = [
    { label: "Publicação", value: "Diária · B3" },
    { label: "Ativos", value: "WIN × WDO" },
    { label: "Leitura", value: "GEX + Fluxo" },
    { label: "Atualização", value: "Tempo real" },
];

const THREE_LAYERS = [
    {
        step: "01",
        title: "Mapa de exposição Gamma (GEX)",
        desc: "Níveis de Call Wall, Put Wall, MidWalls, FlipWall e Ímã GEX atualizados diariamente conforme a disponibilização dos dados oficiais da B3 para WINFUT e WDOFUT, delimitando regiões de defesa e zonas de aceleração.",
    },
    {
        step: "02",
        title: "Divergência no Fluxo Smart Money",
        desc: "Evidencia visualmente quando o preço pressiona uma Wall enquanto o fluxo institucional diverge, sinalizando absorção passiva e perda de força nas extremidades.",
    },
    {
        step: "03",
        title: "Leitura integrada do pregão",
        desc: "Painel web limpo em visualização Dupla, WIN ou WDO com Canal Gauss e marcação visual de divergências, acessível direto pelo navegador em desktop ou celular.",
    },
];

const INCLUDED_ITEMS = [
    "Terminal web em tempo real para WIN e WDO (desktop e mobile)",
    "Níveis diários de GEX: Call Wall, Put Wall, MidWalls, FlipWall e Ímã GEX",
    "Subpainel Fluxo Smart Money com marcação visual de divergências (M1 e M5)",
    "Acesso direto pelo navegador com atualização em tempo real, sem instalação",
];

const REGIME_DETAILS = {
    positive: {
        badge: "Gamma positivo · Acima da FlipWall",
        shortLabel: "Acima da FlipWall · Defesa nas extremidades",
        accent: "#4cc38a",
        softBg: "#10231b",
        hedgeMechanic:
            "Com Gamma líquido positivo, grandes agentes de liquidez atuam na contraparte dos deslocamentos, vendendo avanços esticados e comprando recuos para equilibrar exposição.",
        wallBehavior:
            "Esse comportamento reduz a amplitude errática e cria barreiras objetivas na Call Wall (resistência) e próximo à FlipWall / Put Wall (suporte), favorecendo movimentos de retorno.",
        flowReading:
            "Na marcação 1, o preço renova máxima na Call Wall enquanto o Fluxo Smart Money faz topo menor (divergência de baixa). Na marcação 2, novo fundo próximo à FlipWall vem com fundo maior no fluxo (divergência de alta).",
        candles: [
            { x: 194, o: 158, c: 138, h: 132, l: 164, time: "09:05", flowY: 344, activeLayer: 1 },
            { x: 222, o: 138, c: 108, h: 100, l: 144, time: "09:35", flowY: 322, activeLayer: 1 },
            { x: 250, o: 108, c: 76, h: 66, l: 112, time: "10:05", flowY: 298, activeLayer: 1 },
            { x: 278, o: 76, c: 92, h: 72, l: 100, time: "10:35", flowY: 318, activeLayer: 1 },
            { x: 306, o: 92, c: 62, h: 52, l: 96, time: "11:10", flowY: 314, activeLayer: 3, pin: "1", pinTone: "#e5484d", pinPos: "top" },
            { x: 334, o: 62, c: 98, h: 58, l: 106, time: "11:45", flowY: 334, activeLayer: 2 },
            { x: 362, o: 98, c: 132, h: 94, l: 140, time: "12:20", flowY: 352, activeLayer: 2 },
            { x: 390, o: 132, c: 162, h: 126, l: 168, time: "13:00", flowY: 362, activeLayer: 2 },
            { x: 418, o: 162, c: 178, h: 158, l: 184, time: "13:40", flowY: 368, activeLayer: 2 },
            { x: 446, o: 178, c: 166, h: 160, l: 182, time: "14:15", flowY: 352, activeLayer: 2 },
            { x: 474, o: 166, c: 186, h: 164, l: 194, time: "14:55", flowY: 346, activeLayer: 3, pin: "2", pinTone: "#4cc38a", pinPos: "bottom" },
            { x: 502, o: 186, c: 156, h: 150, l: 190, time: "15:30", flowY: 326, activeLayer: 2 },
            { x: 530, o: 156, c: 134, h: 128, l: 160, time: "16:05", flowY: 314, activeLayer: 2 },
            { x: 558, o: 134, c: 120, h: 114, l: 140, time: "16:40", flowY: 308, activeLayer: 2 },
        ],
        flowPath: "M 194 344 L 222 322 L 250 298 L 278 318 L 306 314 L 334 334 L 362 352 L 390 362 L 418 368 L 446 352 L 474 346 L 502 326 L 530 314 L 558 308",
        divergences: [
            {
                id: "div-bear",
                startIdx: 2,
                triggerIdx: 4,
                tone: "#e5484d",
                priceLine: { x1: 250, y1: 66, x2: 306, y2: 52 },
                flowLine: { x1: 250, y1: 298, x2: 306, y2: 314 },
                label: "Divergência de baixa",
                labelX: 320,
                labelY: 310,
                anchor: "start",
            },
            {
                id: "div-bull",
                startIdx: 8,
                triggerIdx: 10,
                tone: "#4cc38a",
                priceLine: { x1: 418, y1: 184, x2: 474, y2: 194 },
                flowLine: { x1: 418, y1: 368, x2: 474, y2: 346 },
                label: "Divergência de alta",
                labelX: 474,
                labelY: 380,
                anchor: "middle",
            },
        ],
        flowPins: [
            { x: 306, y: 314, label: "1", tone: "#e5484d", triggerIdx: 4 },
            { x: 474, y: 346, label: "2", tone: "#4cc38a", triggerIdx: 10 },
        ],
        ladderBars: [
            { y: 56, label: "Call Wall", price: "132.000", w: 96, color: "#e5484d" },
            { y: 110, label: "MidWall", price: "131.650", w: 56, color: "#848da2" },
            { y: 144, label: "Preço ref.", price: "131.480", w: 38, color: "#38bdf8", isRef: true },
            { y: 192, label: "FlipWall", price: "131.100", w: 68, color: "#d4a259", dashed: true },
            { y: 244, label: "Put Wall", price: "130.500", w: 86, color: "#4cc38a" },
        ],
        timelineEvents: [
            { from: 0, to: 3, text: "Abertura acima da FlipWall · Escada GEX mapeada", level: "Preço ref.", tone: "#38bdf8", layer: 1 },
            { from: 4, to: 4, text: "Sinal #1 confirmado · Divergência de baixa na Call Wall (132.000)", level: "Call Wall", tone: "#e5484d", layer: 3 },
            { from: 5, to: 9, text: "Defesa na Call Wall · Preço recua em direção à FlipWall", level: "MidWall", tone: "#a3a9b8", layer: 2 },
            { from: 10, to: 10, text: "Sinal #2 confirmado · Divergência de alta próxima à FlipWall", level: "FlipWall", tone: "#4cc38a", layer: 3 },
            { from: 11, to: 13, text: "Absorção compradora confirmada · Retorno controlado ao centro", level: "MidWall", tone: "#4cc38a", layer: 2 },
        ],
    },
    negative: {
        badge: "Gamma negativo · Abaixo da FlipWall",
        shortLabel: "Abaixo da FlipWall · Expansão direcional",
        accent: "#e5484d",
        softBg: "#261316",
        hedgeMechanic:
            "Abaixo da FlipWall, o Gamma passa para terreno negativo e os ajustes de liquidez passam a acompanhar a direção do rompimento, acelerando a velocidade do movimento.",
        wallBehavior:
            "O pregão deixa de trabalhar travado e expande amplitude direcional até encontrar a próxima grande zona de defesa institucional na Put Wall inferior.",
        flowReading:
            "Na marcação 1, o rompimento da FlipWall tem confirmação vendedora no fluxo. Ao testar a Put Wall em fundo menor (marcação 2), o Fluxo Smart Money desenha fundo mais alto (divergência na Put Wall), marcando absorção.",
        candles: [
            { x: 194, o: 108, c: 118, h: 102, l: 124, time: "09:05", flowY: 308, activeLayer: 1 },
            { x: 222, o: 118, c: 130, h: 114, l: 138, time: "09:35", flowY: 316, activeLayer: 1 },
            { x: 250, o: 130, c: 148, h: 126, l: 156, time: "10:05", flowY: 326, activeLayer: 1 },
            { x: 278, o: 148, c: 174, h: 144, l: 182, time: "10:35", flowY: 342, activeLayer: 3, pin: "1", pinTone: "#e5484d", pinPos: "top" },
            { x: 306, o: 174, c: 204, h: 170, l: 212, time: "11:10", flowY: 356, activeLayer: 2 },
            { x: 334, o: 204, c: 226, h: 198, l: 234, time: "11:45", flowY: 366, activeLayer: 2 },
            { x: 362, o: 226, c: 236, h: 220, l: 242, time: "12:20", flowY: 374, activeLayer: 2 },
            { x: 390, o: 236, c: 224, h: 218, l: 240, time: "13:00", flowY: 358, activeLayer: 2 },
            { x: 418, o: 224, c: 244, h: 220, l: 252, time: "13:40", flowY: 350, activeLayer: 3, pin: "2", pinTone: "#4cc38a", pinPos: "bottom" },
            { x: 446, o: 244, c: 222, h: 216, l: 248, time: "14:15", flowY: 332, activeLayer: 2 },
            { x: 474, o: 222, c: 204, h: 198, l: 228, time: "14:55", flowY: 320, activeLayer: 2 },
            { x: 502, o: 204, c: 190, h: 184, l: 210, time: "15:30", flowY: 312, activeLayer: 2 },
            { x: 530, o: 190, c: 182, h: 176, l: 196, time: "16:05", flowY: 308, activeLayer: 2 },
            { x: 558, o: 182, c: 186, h: 178, l: 192, time: "16:40", flowY: 312, activeLayer: 2 },
        ],
        flowPath: "M 194 308 L 222 316 L 250 326 L 278 342 L 306 356 L 334 366 L 362 374 L 390 358 L 418 350 L 446 332 L 474 320 L 502 312 L 530 308 L 558 312",
        divergences: [
            {
                id: "div-putwall",
                startIdx: 6,
                triggerIdx: 8,
                tone: "#4cc38a",
                priceLine: { x1: 362, y1: 242, x2: 418, y2: 252 },
                flowLine: { x1: 362, y1: 374, x2: 418, y2: 350 },
                label: "Divergência na Put Wall",
                labelX: 446,
                labelY: 380,
                anchor: "middle",
            },
        ],
        flowPins: [
            { x: 278, y: 342, label: "1", tone: "#e5484d", triggerIdx: 3 },
            { x: 418, y: 350, label: "2", tone: "#4cc38a", triggerIdx: 8 },
        ],
        ladderBars: [
            { y: 56, label: "Call Wall", price: "132.000", w: 74, color: "#e5484d" },
            { y: 106, label: "MidWall", price: "131.500", w: 50, color: "#848da2" },
            { y: 152, label: "FlipWall", price: "131.100", w: 80, color: "#d4a259", dashed: true },
            { y: 192, label: "Preço ref.", price: "130.820", w: 42, color: "#38bdf8", isRef: true },
            { y: 244, label: "Put Wall", price: "130.200", w: 98, color: "#4cc38a" },
        ],
        timelineEvents: [
            { from: 0, to: 2, text: "Pressão vendedora aproximando da FlipWall (131.100)", level: "FlipWall", tone: "#d4a259", layer: 1 },
            { from: 3, to: 3, text: "Sinal #1 confirmado · Rompimento da FlipWall com fluxo vendedor", level: "FlipWall", tone: "#e5484d", layer: 3 },
            { from: 4, to: 7, text: "Aceleração direcional em Gamma negativo rumo à Put Wall", level: "Preço ref.", tone: "#e5484d", layer: 2 },
            { from: 8, to: 8, text: "Sinal #2 confirmado · Divergência compradora na Put Wall (130.200)", level: "Put Wall", tone: "#4cc38a", layer: 3 },
            { from: 9, to: 13, text: "Absorção institucional na Put Wall · Alívio da queda", level: "Put Wall", tone: "#4cc38a", layer: 2 },
        ],
    },
};

const STATS_30D = {
    period: "07/10 a 19/11/2026",
    sessions: 30,
    win: {
        posDays: 28,
        negDays: 2,
        totalSignals: 122,
        paidCount: 88,
        paidPct: 72.1,
        neutralCount: 6,
        neutralPct: 4.9,
        stopCount: 28,
        stopPct: 23.0,
        grossPts: 107005,
        stopPts: -10540,
        netPts: 96465,
        avgPerDay: 3216,
        avgPerSignal: 791,
        bestDayLabel: "26/10",
        bestDayPts: 10729,
        worstDayLabel: "17/11",
        worstDayPts: -919,
        maxLegPts: 7180,
        maxLegMeta: "26/10 · 11:25",
    },
    wdo: {
        posDays: 29,
        negDays: 1,
        totalSignals: 122,
        paidCount: 87,
        paidPct: 71.3,
        neutralCount: 8,
        neutralPct: 6.6,
        stopCount: 27,
        stopPct: 22.1,
        grossPts: 1869.5,
        stopPts: -276.0,
        netPts: 1593.5,
        avgPerDay: 53.1,
        avgPerSignal: 13.1,
        bestDayLabel: "29/10",
        bestDayPts: 216.5,
        worstDayLabel: "11/11",
        worstDayPts: -12.0,
        maxLegPts: 71.5,
        maxLegMeta: "29/10 · 10:10",
    },
};

function easeOutCubic(t) {
    const x = Math.max(0, Math.min(1, t));
    return 1 - (1 - x) ** 3;
}

function fmtPtInt(val) {
    return Math.round(val).toLocaleString("pt-BR");
}

function fmtPtDec1(val) {
    return Number(val).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function fmtSignedInt(val) {
    const r = Math.round(val);
    if (r > 0) return `+${fmtPtInt(r)}`;
    if (r < 0) return `-${fmtPtInt(Math.abs(r))}`;
    return "0";
}

function fmtSignedDec1(val) {
    const r = Math.round(val * 10) / 10;
    if (r > 0) return `+${fmtPtDec1(r)}`;
    if (r < 0) return `-${fmtPtDec1(Math.abs(r))}`;
    return fmtPtDec1(0);
}

function WallsMark() {
    return <MagicWallsMark size={20} variant="small" />;
}

function IconCheck() {
    return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polyline points="20 6 9 17 4 12" />
        </svg>
    );
}

function IconArrowUpRight() {
    return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <line x1="7" y1="17" x2="17" y2="7" />
            <polyline points="7 7 17 7 17 17" />
        </svg>
    );
}

function IconMaximize() {
    return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polyline points="15 3 21 3 21 9" />
            <polyline points="9 21 3 21 3 15" />
            <line x1="21" y1="3" x2="14" y2="10" />
            <line x1="3" y1="21" x2="10" y2="14" />
        </svg>
    );
}

function IconChevron({ open }) {
    return (
        <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
            style={{
                transform: open ? "rotate(180deg)" : "rotate(0deg)",
                transition: "transform 160ms cubic-bezier(0.22, 1, 0.36, 1)",
            }}
        >
            <polyline points="6 9 12 15 18 9" />
        </svg>
    );
}

export default function SaasWelcomePortal({
    email,
    setEmail,
    password,
    setPassword,
    showPassword,
    setShowPassword,
    submitting,
    bannerMsg,
    feedStatus,
    cloudReachable,
    onSubmit,
}) {
    const [prefersReducedMotion] = useState(
        () => typeof window !== "undefined" && Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches)
    );
    const [regimeMode, setRegimeMode] = useState("positive");
    const [activePrint, setActivePrint] = useState(null);
    const [openFaqIdx, setOpenFaqIdx] = useState(0);

    // Simulação animada na Anatomia do Método (#regimes-gex)
    const anatomyRef = useRef(null);
    const [anatomyInView, setAnatomyInView] = useState(true);
    const [simPlaying, setSimPlaying] = useState(() => !prefersReducedMotion);
    const [simProgress, setSimProgress] = useState(() => (prefersReducedMotion ? 13 : 0));

    // Contagem unificada na tabela de 30 pregões (#resultados-30d)
    const statsRef = useRef(null);
    const statsTriggeredRef = useRef(false);
    const [statsRunId, setStatsRunId] = useState(0);
    const [statsT, setStatsT] = useState(() => (prefersReducedMotion ? 1 : 0));

    const activeRegime = REGIME_DETAILS[regimeMode];
    const maxCandleIdx = activeRegime.candles.length - 1;
    const featuredPrint = REAL_SESSION_PRINTS[0];
    const secondaryPrints = REAL_SESSION_PRINTS.slice(1);

    useEffect(() => {
        if (!activePrint) return undefined;
        const onKeyDown = (ev) => {
            if (ev.key === "Escape") setActivePrint(null);
        };
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [activePrint]);

    // Pausa animação da Anatomia quando fora da viewport
    useEffect(() => {
        const el = anatomyRef.current;
        if (!el || typeof IntersectionObserver === "undefined") return undefined;
        const io = new IntersectionObserver(
            (entries) => {
                if (entries[0]) setAnatomyInView(entries[0].isIntersecting);
            },
            { threshold: 0.12 }
        );
        io.observe(el);
        return () => io.disconnect();
    }, []);

    // Loop suave rAF da Anatomia do Método (~0.48s por candle + 2.6s de pausa no fechamento)
    useEffect(() => {
        if (prefersReducedMotion || !simPlaying || !anatomyInView) return undefined;
        let rafId = 0;
        let lastTs = null;
        let holdUntil = 0;
        const BAR_DUR_SEC = 0.48;
        const END_HOLD_MS = 2600;

        const tick = (nowTs) => {
            if (lastTs === null) lastTs = nowTs;
            const dtSec = Math.min(0.1, Math.max(0, (nowTs - lastTs) / 1000));
            lastTs = nowTs;

            setSimProgress((prev) => {
                if (holdUntil > 0) {
                    if (nowTs < holdUntil) return maxCandleIdx;
                    holdUntil = 0;
                    return 0;
                }
                const next = prev + dtSec / BAR_DUR_SEC;
                if (next >= maxCandleIdx) {
                    holdUntil = nowTs + END_HOLD_MS;
                    return maxCandleIdx;
                }
                return next;
            });
            rafId = requestAnimationFrame(tick);
        };

        rafId = requestAnimationFrame(tick);
        return () => cancelAnimationFrame(rafId);
    }, [prefersReducedMotion, simPlaying, anatomyInView, maxCandleIdx, regimeMode]);

    // Dispara contagem dos 30 pregões ao entrar na viewport (uma vez automaticamente)
    useEffect(() => {
        if (prefersReducedMotion) return undefined;
        const el = statsRef.current;
        if (!el || typeof IntersectionObserver === "undefined") {
            const id = requestAnimationFrame(() => setStatsRunId((r) => (r === 0 ? 1 : r)));
            return () => cancelAnimationFrame(id);
        }
        const io = new IntersectionObserver(
            (entries) => {
                if (entries[0]?.isIntersecting && !statsTriggeredRef.current) {
                    statsTriggeredRef.current = true;
                    setStatsRunId((r) => r + 1);
                }
            },
            { threshold: 0.18 }
        );
        io.observe(el);
        return () => io.disconnect();
    }, [prefersReducedMotion]);

    // Animação rAF de 2200ms da contagem progressiva / regressiva
    useEffect(() => {
        if (prefersReducedMotion || statsRunId === 0) return undefined;
        let rafId = 0;
        let startTs = null;
        const DURATION_MS = 2200;

        const step = (nowTs) => {
            if (startTs === null) startTs = nowTs;
            const t = Math.min(1, (nowTs - startTs) / DURATION_MS);
            setStatsT(t);
            if (t < 1) {
                rafId = requestAnimationFrame(step);
            }
        };
        rafId = requestAnimationFrame(step);
        return () => cancelAnimationFrame(rafId);
    }, [prefersReducedMotion, statsRunId]);

    const handleRegimeChange = (mode) => {
        setRegimeMode(mode);
        setSimProgress(prefersReducedMotion ? REGIME_DETAILS[mode].candles.length - 1 : 0);
        if (!prefersReducedMotion) setSimPlaying(true);
    };

    const handleReplayAnatomy = () => {
        setSimProgress(0);
        if (!prefersReducedMotion) setSimPlaying(true);
    };

    const handleTriggerStats = () => {
        statsTriggeredRef.current = true;
        if (prefersReducedMotion) {
            setStatsT(1);
            return;
        }
        setStatsT(0);
        setStatsRunId((r) => r + 1);
    };

    // Variáveis derivadas do quadro atual da simulação
    const currentIdx = Math.max(0, Math.min(maxCandleIdx, Math.floor(simProgress)));
    const barFrac = currentIdx >= maxCandleIdx ? 1 : Math.max(0.18, simProgress - Math.floor(simProgress));
    const activeCandle = activeRegime.candles[currentIdx] || activeRegime.candles[0];
    const nextCandle = activeRegime.candles[Math.min(maxCandleIdx, currentIdx + 1)] || activeCandle;
    const partialFrac = currentIdx >= maxCandleIdx ? 0 : Math.max(0, simProgress - Math.floor(simProgress));
    const cursorX = activeCandle.x + (nextCandle.x - activeCandle.x) * partialFrac;
    const cursorFlowY = activeCandle.flowY + (nextCandle.flowY - activeCandle.flowY) * partialFrac;

    const activeFlowPath = useMemo(() => {
        const pts = activeRegime.candles.slice(0, currentIdx + 1).map((c) => `${c.x} ${c.flowY}`);
        if (currentIdx < maxCandleIdx && partialFrac > 0.02) {
            pts.push(`${cursorX.toFixed(1)} ${cursorFlowY.toFixed(1)}`);
        }
        return pts.length > 0 ? `M ${pts.join(" L ")}` : "";
    }, [activeRegime.candles, currentIdx, maxCandleIdx, partialFrac, cursorX, cursorFlowY]);

    const activeTimeline =
        activeRegime.timelineEvents.find((ev) => currentIdx >= ev.from && currentIdx <= ev.to) ||
        activeRegime.timelineEvents[0];

    // Variáveis derivadas da contagem de 30 pregões
    const easedP = easeOutCubic(statsT);
    const sessionProgressCount = Math.max(1, Math.min(30, Math.round(1 + easedP * 29)));
    const sessionsRemaining = Math.max(0, Math.min(30, Math.round((1 - easedP) * 30)));
    const winNetAnim = STATS_30D.win.netPts * easedP;
    const wdoNetAnim = STATS_30D.wdo.netPts * easedP;

    const statsRows = [
        {
            key: "sessions",
            label: "Pregões analisados",
            win: (
                <>
                    {fmtPtInt(STATS_30D.sessions * easedP)}{" "}
                    <span style={{ color: "#848da2", fontStyle: "italic" }}>
                        ({fmtPtInt(STATS_30D.win.posDays * easedP)} pos · {fmtPtInt(STATS_30D.win.negDays * easedP)} neg)
                    </span>
                </>
            ),
            winColor: "#eef0f5",
            wdo: (
                <>
                    {fmtPtInt(STATS_30D.sessions * easedP)}{" "}
                    <span style={{ color: "#848da2", fontStyle: "italic" }}>
                        ({fmtPtInt(STATS_30D.wdo.posDays * easedP)} pos · {fmtPtInt(STATS_30D.wdo.negDays * easedP)} neg)
                    </span>
                </>
            ),
            wdoColor: "#eef0f5",
        },
        {
            key: "signals",
            label: "Total de sinais",
            win: fmtPtInt(STATS_30D.win.totalSignals * easedP),
            winColor: "#eef0f5",
            winWeight: 600,
            wdo: fmtPtInt(STATS_30D.wdo.totalSignals * easedP),
            wdoColor: "#eef0f5",
            wdoWeight: 600,
        },
        {
            key: "paid",
            label: "Pagaram (≥150 / ≥4 pts)",
            win: `${fmtPtInt(STATS_30D.win.paidCount * easedP)} (${fmtPtDec1(STATS_30D.win.paidPct * easedP)}%)`,
            winColor: "#4cc38a",
            winWeight: 600,
            wdo: `${fmtPtInt(STATS_30D.wdo.paidCount * easedP)} (${fmtPtDec1(STATS_30D.wdo.paidPct * easedP)}%)`,
            wdoColor: "#4cc38a",
            wdoWeight: 600,
        },
        {
            key: "neutral",
            label: "Neutros (sem stop e < limiar)",
            win: `${fmtPtInt(STATS_30D.win.neutralCount * easedP)} (${fmtPtDec1(STATS_30D.win.neutralPct * easedP)}%)`,
            winColor: "#a3a9b8",
            wdo: `${fmtPtInt(STATS_30D.wdo.neutralCount * easedP)} (${fmtPtDec1(STATS_30D.wdo.neutralPct * easedP)}%)`,
            wdoColor: "#a3a9b8",
        },
        {
            key: "stops-cnt",
            label: "Stops (na outra Wall)",
            win: `${fmtPtInt(STATS_30D.win.stopCount * easedP)} (${fmtPtDec1(STATS_30D.win.stopPct * easedP)}%)`,
            winColor: "#e5484d",
            winWeight: 600,
            wdo: `${fmtPtInt(STATS_30D.wdo.stopCount * easedP)} (${fmtPtDec1(STATS_30D.wdo.stopPct * easedP)}%)`,
            wdoColor: "#e5484d",
            wdoWeight: 600,
        },
        {
            key: "gross",
            label: "Soma Bruta (máx. a favor)",
            win: `${fmtSignedInt(STATS_30D.win.grossPts * easedP)} pts`,
            winColor: "#4cc38a",
            winWeight: 500,
            wdo: `${fmtSignedDec1(STATS_30D.wdo.grossPts * easedP)} pts`,
            wdoColor: "#4cc38a",
            wdoWeight: 500,
        },
        {
            key: "stops-pts",
            label: "Soma dos Stops",
            win: `${fmtSignedInt(STATS_30D.win.stopPts * easedP)} pts`,
            winColor: "#e5484d",
            winWeight: 500,
            wdo: `${fmtSignedDec1(STATS_30D.wdo.stopPts * easedP)} pts`,
            wdoColor: "#e5484d",
            wdoWeight: 500,
        },
        {
            key: "net",
            label: "Saldo Líquido (30 pregões)",
            highlight: true,
            win: `${fmtSignedInt(winNetAnim)} pts`,
            winColor: "#4cc38a",
            winWeight: 600,
            wdo: `${fmtSignedDec1(wdoNetAnim)} pts`,
            wdoColor: "#4cc38a",
            wdoWeight: 600,
        },
        {
            key: "avg",
            label: "Média por pregão / por sinal",
            win: `${fmtSignedInt(STATS_30D.win.avgPerDay * easedP)} pts/dia · ${fmtSignedInt(STATS_30D.win.avgPerSignal * easedP)} pts/sinal`,
            winColor: "#eef0f5",
            wdo: `${fmtSignedDec1(STATS_30D.wdo.avgPerDay * easedP)} pts/dia · ${fmtSignedDec1(STATS_30D.wdo.avgPerSignal * easedP)} pts/sinal`,
            wdoColor: "#eef0f5",
        },
        {
            key: "best-worst",
            label: "Melhor dia / Pior dia",
            win: `${STATS_30D.win.bestDayLabel} (${fmtSignedInt(STATS_30D.win.bestDayPts * easedP)}) / ${STATS_30D.win.worstDayLabel} (${fmtSignedInt(STATS_30D.win.worstDayPts * easedP)})`,
            winColor: "#eef0f5",
            wdo: `${STATS_30D.wdo.bestDayLabel} (${fmtSignedDec1(STATS_30D.wdo.bestDayPts * easedP)}) / ${STATS_30D.wdo.worstDayLabel} (${fmtSignedDec1(STATS_30D.wdo.worstDayPts * easedP)})`,
            wdoColor: "#eef0f5",
        },
        {
            key: "max-leg",
            label: "Maior pernada única",
            win: (
                <>
                    {fmtSignedInt(STATS_30D.win.maxLegPts * easedP)} pts{" "}
                    <span style={{ fontWeight: 400, color: "#848da2" }}>({STATS_30D.win.maxLegMeta})</span>
                </>
            ),
            winColor: "#eef0f5",
            winWeight: 600,
            wdo: (
                <>
                    {fmtSignedDec1(STATS_30D.wdo.maxLegPts * easedP)} pts{" "}
                    <span style={{ fontWeight: 400, color: "#848da2" }}>({STATS_30D.wdo.maxLegMeta})</span>
                </>
            ),
            wdoColor: "#eef0f5",
            wdoWeight: 600,
        },
    ];

    const statusLabel =
        cloudReachable === null
            ? "Conectando"
            : !cloudReachable
              ? "Servidor offline"
              : feedStatus === "live"
                ? "Feed ao vivo"
                : "Fora do pregão";
    const statusDotColor =
        cloudReachable === false ? "#e5484d" : feedStatus === "live" ? "#4cc38a" : cloudReachable ? "#848da2" : "#38bdf8";

    return (
        <div
            className="mw-portal-root"
            style={{
                minHeight: "100svh",
                background: "#0e1118",
                color: "#eef0f5",
                fontFamily: FONT_SANS,
                display: "flex",
                flexDirection: "column",
            }}
        >
            <style>{`
                .mw-portal-root {
                    --p-ease: cubic-bezier(0.22, 1, 0.36, 1);
                    overflow-x: clip;
                }
                .mw-portal-root * {
                    box-sizing: border-box;
                }
                .mw-portal-hero {
                    display: grid;
                    grid-template-columns: minmax(0, 1.32fr) minmax(340px, 400px);
                    gap: 48px;
                    align-items: center;
                    padding: 24px 0 8px;
                }
                .mw-specs-strip {
                    display: grid;
                    grid-template-columns: repeat(4, minmax(0, 1fr));
                    gap: 16px;
                    padding-top: 24px;
                    border-top: 1px solid rgba(238, 240, 245, 0.08);
                }
                .mw-anatomy-grid {
                    display: grid;
                    grid-template-columns: minmax(0, 1.48fr) minmax(280px, 0.92fr);
                    gap: 24px;
                    align-items: stretch;
                }
                .mw-featured-print {
                    display: grid;
                    grid-template-columns: minmax(0, 1.42fr) minmax(280px, 1fr);
                    gap: 24px;
                    align-items: center;
                }
                .mw-prints-secondary {
                    display: grid;
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                    gap: 16px;
                }
                .mw-layers-grid {
                    display: grid;
                    grid-template-columns: repeat(3, minmax(0, 1fr));
                    gap: 24px;
                }
                .mw-product-grid {
                    display: grid;
                    grid-template-columns: minmax(0, 1.35fr) minmax(280px, 0.95fr);
                    gap: 32px;
                    align-items: center;
                }
                .mw-portal-hero > *,
                .mw-anatomy-grid > *,
                .mw-featured-print > *,
                .mw-prints-secondary > *,
                .mw-layers-grid > *,
                .mw-product-grid > *,
                .mw-stats-cards-grid > * {
                    min-width: 0;
                    max-width: 100%;
                }
                .mw-nav-links {
                    display: flex;
                    align-items: center;
                    gap: 24px;
                }
                .mw-p-nav-link {
                    font-size: 13px;
                    font-weight: 400;
                    color: #a3a9b8;
                    text-decoration: none;
                    transition: color 140ms var(--p-ease);
                }
                .mw-p-nav-link:hover {
                    color: #eef0f5;
                }
                .mw-p-nav-link:focus-visible,
                .mw-p-btn-primary:focus-visible,
                .mw-p-btn-secondary:focus-visible,
                .mw-p-tab:focus-visible,
                .mw-p-input:focus-visible,
                .mw-p-img-btn:focus-visible,
                .mw-p-faq-btn:focus-visible,
                .mw-p-text-link:focus-visible {
                    outline: 2px solid rgba(56, 189, 248, 0.45);
                    outline-offset: 2px;
                }
                .mw-p-input {
                    width: 100%;
                    height: 40px;
                    box-sizing: border-box;
                    padding: 0 12px;
                    border-radius: 8px;
                    background: #0a0c12;
                    border: 1px solid rgba(238, 240, 245, 0.12);
                    color: #eef0f5;
                    font-size: 14px;
                    font-family: ${FONT_SANS};
                    transition: border-color 140ms var(--p-ease), background-color 140ms var(--p-ease);
                }
                .mw-p-input::placeholder {
                    color: #848da2;
                }
                .mw-p-input:hover {
                    border-color: rgba(238, 240, 245, 0.22);
                }
                .mw-p-input:focus {
                    border-color: rgba(56, 189, 248, 0.5);
                }
                .mw-p-btn-primary {
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    gap: 8px;
                    height: 40px;
                    padding: 0 16px;
                    border-radius: 8px;
                    border: 1px solid #38bdf8;
                    background: #38bdf8;
                    color: #070a10;
                    font-family: ${FONT_SANS};
                    font-size: 14px;
                    font-weight: 500;
                    text-decoration: none;
                    cursor: pointer;
                    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.22);
                    transition: opacity 140ms var(--p-ease), transform 120ms var(--p-ease);
                }
                .mw-p-btn-primary:hover:not(:disabled) {
                    opacity: 0.92;
                }
                .mw-p-btn-primary:active:not(:disabled) {
                    transform: scale(0.98);
                }
                .mw-p-btn-primary:disabled {
                    opacity: 0.65;
                    cursor: wait;
                }
                .mw-p-btn-secondary {
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    gap: 8px;
                    height: 36px;
                    padding: 0 12px;
                    border-radius: 8px;
                    border: 1px solid rgba(238, 240, 245, 0.12);
                    background: #1b212e;
                    color: #eef0f5;
                    font-family: ${FONT_SANS};
                    font-size: 13px;
                    font-weight: 500;
                    text-decoration: none;
                    cursor: pointer;
                    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);
                    transition: background-color 140ms var(--p-ease), border-color 140ms var(--p-ease), transform 120ms var(--p-ease);
                }
                .mw-p-btn-secondary:hover {
                    background: #232a3a;
                    border-color: rgba(238, 240, 245, 0.2);
                }
                .mw-p-btn-secondary:active {
                    transform: scale(0.98);
                }
                .mw-p-tab {
                    display: inline-flex;
                    align-items: center;
                    gap: 8px;
                    height: 32px;
                    padding: 0 12px;
                    border-radius: 6px;
                    border: 1px solid transparent;
                    background: transparent;
                    color: #848da2;
                    font-family: ${FONT_SANS};
                    font-size: 13px;
                    font-weight: 500;
                    cursor: pointer;
                    transition: background-color 140ms var(--p-ease), color 140ms var(--p-ease), border-color 140ms var(--p-ease);
                }
                .mw-p-tab:hover {
                    color: #eef0f5;
                }
                .mw-p-tab[aria-selected="true"] {
                    background: #1b212e;
                    border-color: rgba(238, 240, 245, 0.14);
                    color: #eef0f5;
                    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
                }
                .mw-p-img-btn {
                    padding: 0;
                    border: 1px solid rgba(238, 240, 245, 0.08);
                    border-radius: 8px;
                    background: #0a0c12;
                    overflow: hidden;
                    cursor: pointer;
                    display: block;
                    width: 100%;
                    transition: border-color 140ms var(--p-ease);
                }
                .mw-p-img-btn:hover {
                    border-color: rgba(56, 189, 248, 0.36);
                }
                .mw-p-faq-btn {
                    width: 100%;
                    padding: 16px 20px;
                    background: transparent;
                    border: none;
                    color: #eef0f5;
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    gap: 16px;
                    text-align: left;
                    font-family: ${FONT_SANS};
                    font-size: 14px;
                    font-weight: 500;
                    cursor: pointer;
                    transition: background-color 140ms var(--p-ease);
                }
                .mw-p-faq-btn:hover {
                    background: rgba(238, 240, 245, 0.03);
                }
                .mw-p-text-link {
                    color: #7dd3fc;
                    text-decoration: none;
                    font-weight: 500;
                    transition: color 140ms var(--p-ease);
                }
                .mw-p-text-link:hover {
                    color: #eef0f5;
                }
                .mw-p-keycap {
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    height: 20px;
                    padding: 0 6px;
                    border-radius: 4px;
                    background: #0a0c12;
                    border: 1px solid rgba(238, 240, 245, 0.14);
                    font-family: ${FONT_MONO};
                    font-size: 11px;
                    color: #a3a9b8;
                }
                @keyframes mw-pin-ring {
                    0% {
                        transform: scale(1);
                        opacity: 0.75;
                    }
                    100% {
                        transform: scale(1.85);
                        opacity: 0;
                    }
                }
                @keyframes mw-pulse-dot {
                    0%, 100% {
                        opacity: 1;
                    }
                    50% {
                        opacity: 0.45;
                    }
                }
                .mw-pin-ring {
                    transform-box: fill-box;
                    transform-origin: center;
                    animation: mw-pin-ring 0.9s cubic-bezier(0.22, 1, 0.36, 1) forwards;
                }
                .mw-cursor-dot {
                    animation: mw-pulse-dot 1.4s ease-in-out infinite;
                }
                .mw-stats-cards-grid {
                    display: grid;
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                    gap: 16px;
                }
                .mw-stats-table-wrap {
                    width: 100%;
                    overflow-x: auto;
                    border: 1px solid rgba(238, 240, 245, 0.08);
                    border-radius: 10px;
                    background: #0e1118;
                }
                .mw-stats-mobile-list {
                    display: none;
                }
                .mw-stats-table {
                    width: 100%;
                    border-collapse: collapse;
                    font-size: 13px;
                }
                .mw-stats-table th,
                .mw-stats-table td {
                    padding: 11px 16px;
                    border-bottom: 1px solid rgba(238, 240, 245, 0.06);
                    text-align: left;
                }
                .mw-stats-table th {
                    background: #0a0c12;
                    color: #848da2;
                    font-size: 12px;
                    font-weight: 500;
                    white-space: nowrap;
                }
                .mw-stats-table th:not(:first-child),
                .mw-stats-table td:not(:first-child) {
                    text-align: center;
                    font-family: ${FONT_MONO};
                    font-variant-numeric: tabular-nums;
                    white-space: nowrap;
                }
                .mw-stats-table tbody tr:nth-child(even) {
                    background: rgba(255, 255, 255, 0.015);
                }
                .mw-stats-table tbody tr:last-child td {
                    border-bottom: none;
                }
                @media (prefers-reduced-motion: reduce) {
                    .mw-pin-ring,
                    .mw-cursor-dot {
                        animation: none;
                    }
                }
                @media (max-width: 960px) {
                    .mw-portal-hero,
                    .mw-anatomy-grid,
                    .mw-featured-print,
                    .mw-prints-secondary,
                    .mw-layers-grid,
                    .mw-product-grid,
                    .mw-stats-cards-grid {
                        grid-template-columns: minmax(0, 1fr);
                        gap: 20px;
                    }
                    .mw-portal-hero {
                        padding: 8px 0 0;
                    }
                    .mw-specs-strip {
                        grid-template-columns: repeat(2, minmax(0, 1fr));
                    }
                    .mw-nav-links {
                        display: none;
                    }
                }
                @media (max-width: 720px) {
                    .mw-stats-table-wrap {
                        display: none;
                    }
                    .mw-stats-mobile-list {
                        display: flex;
                        flex-direction: column;
                        width: 100%;
                        border: 1px solid rgba(238, 240, 245, 0.08);
                        border-radius: 10px;
                        background: #0e1118;
                        overflow: hidden;
                    }
                    .mw-stats-mobile-row {
                        padding: 12px 14px;
                        border-bottom: 1px solid rgba(238, 240, 245, 0.06);
                        display: flex;
                        flex-direction: column;
                        gap: 8px;
                    }
                    .mw-stats-mobile-row:nth-child(even) {
                        background: rgba(255, 255, 255, 0.015);
                    }
                    .mw-stats-mobile-row:last-child {
                        border-bottom: none;
                    }
                    .mw-stats-mobile-cols {
                        display: grid;
                        grid-template-columns: repeat(2, minmax(0, 1fr));
                        gap: 10px;
                    }
                }
                @media (max-width: 640px) {
                    .mw-portal-header {
                        padding: 0 14px !important;
                    }
                    .mw-header-inner {
                        flex-wrap: nowrap !important;
                        gap: 8px !important;
                        padding: 6px 0 !important;
                    }
                    .mw-header-sub,
                    .mw-header-status-text {
                        display: none !important;
                    }
                    .mw-header-ig-btn {
                        height: 30px !important;
                        padding: 0 10px !important;
                        font-size: 11.5px !important;
                    }
                    .mw-portal-main {
                        padding: 20px 14px 56px !important;
                        gap: 36px !important;
                    }
                    .mw-section-card {
                        padding: 16px !important;
                        border-radius: 12px !important;
                        gap: 16px !important;
                    }
                    .mw-anatomy-stage {
                        padding: 12px !important;
                    }
                    .mw-anatomy-editorial {
                        padding: 16px !important;
                    }
                    .mw-regime-tabs {
                        width: 100%;
                        display: grid !important;
                        grid-template-columns: repeat(2, minmax(0, 1fr));
                    }
                    .mw-regime-tabs .mw-p-tab {
                        justify-content: center;
                        white-space: nowrap;
                        font-size: 12px;
                        padding: 0 8px;
                    }
                    .mw-anatomy-controls {
                        width: 100%;
                        display: grid !important;
                        grid-template-columns: repeat(2, minmax(0, 1fr));
                    }
                    .mw-anatomy-controls button {
                        height: 34px !important;
                        width: 100%;
                    }
                    .mw-stats-replay-btn {
                        width: 100%;
                    }
                    .mw-print-card {
                        padding: 16px !important;
                    }
                    .mw-portal-footer {
                        padding: 20px 14px !important;
                    }
                }
            `}</style>

            {/* Topbar sólida (56px) */}
            <header
                className="mw-portal-header"
                style={{
                    position: "sticky",
                    top: 0,
                    zIndex: 30,
                    background: "#0a0c12",
                    borderBottom: "1px solid rgba(238, 240, 245, 0.08)",
                    padding: "0 24px",
                }}
            >
                <div
                    className="mw-header-inner"
                    style={{
                        maxWidth: 1200,
                        minHeight: 56,
                        margin: "0 auto",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: 16,
                        flexWrap: "wrap",
                        padding: "8px 0",
                    }}
                >
                    <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
                        <WallsMark />
                        <span style={{ fontSize: 16, fontWeight: 600, color: "#eef0f5", lineHeight: 1, whiteSpace: "nowrap" }}>
                            Magic Walls
                        </span>
                        <span className="mw-header-sub" style={{ width: 1, height: 14, background: "rgba(238, 240, 245, 0.12)" }} />
                        <span className="mw-header-sub" style={{ fontFamily: FONT_MONO, fontSize: 12, color: "#848da2" }}>
                            WIN × WDO · B3
                        </span>
                    </div>

                    <nav className="mw-nav-links" aria-label="Navegação técnica">
                        <a href="#regimes-gex" className="mw-p-nav-link">Regimes GEX</a>
                        <a href="#resultados-30d" className="mw-p-nav-link">30 pregões</a>
                        <a href="#dias-reais" className="mw-p-nav-link">Dias reais</a>
                        <a href="#como-funciona" className="mw-p-nav-link">Como funciona</a>
                        <a href="#o-que-inclui" className="mw-p-nav-link">O que inclui</a>
                        <a href="#faq" className="mw-p-nav-link">FAQ</a>
                    </nav>

                    <div style={{ display: "flex", alignItems: "center", gap: 12, flexShrink: 0 }}>
                        <span
                            data-testid="saas-cloud-status"
                            title={statusLabel}
                            style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 8,
                                fontFamily: FONT_MONO,
                                fontSize: 12,
                                fontWeight: 400,
                                fontVariantNumeric: "tabular-nums",
                                color: "#a3a9b8",
                            }}
                        >
                            <span style={{ width: 6, height: 6, borderRadius: "50%", background: statusDotColor }} />
                            <span className="mw-header-status-text">{statusLabel}</span>
                        </span>

                        <a
                            href="https://instagram.com/magicwallsb3"
                            target="_blank"
                            rel="noreferrer noopener"
                            className="mw-p-btn-secondary mw-header-ig-btn"
                            style={{ height: 32, padding: "0 12px", fontFamily: FONT_MONO, fontSize: 12 }}
                        >
                            <span>@magicwallsb3</span>
                            <IconArrowUpRight />
                        </a>
                    </div>
                </div>
            </header>

            {/* Conteúdo Principal */}
            <main
                className="mw-portal-main"
                style={{
                    flex: 1,
                    maxWidth: 1200,
                    width: "100%",
                    margin: "0 auto",
                    padding: "32px 24px 72px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 64,
                }}
            >
                {/* Faixa 1: Hero Editorial Aberto + Card de Autenticação */}
                <section className="mw-portal-hero">
                    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
                        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                            <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: "#7dd3fc" }}>
                                Mapa de liquidez GEX · Fluxo Smart Money
                            </span>

                            <h1
                                style={{
                                    margin: 0,
                                    fontSize: "clamp(32px, 3.8vw, 44px)",
                                    lineHeight: 1.12,
                                    fontWeight: 500,
                                    color: "#eef0f5",
                                    letterSpacing: "-0.025em",
                                    maxWidth: "20ch",
                                }}
                            >
                                Exposição Gamma e fluxo institucional
                            </h1>

                            <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6, color: "#a3a9b8", maxWidth: "56ch" }}>
                                O Magic Walls mapeia diariamente, assim que os dados oficiais ficam disponíveis, as zonas de defesa e aceleração para o índice futuro (WIN) e o dólar futuro (WDO), combinando os níveis de Walls com a leitura de divergências no Fluxo Smart Money ao longo do pregão.
                            </p>
                        </div>

                        <div className="mw-specs-strip">
                            {HERO_SPECS.map((spec) => (
                                <div key={spec.label} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                                    <span style={{ fontSize: 12, color: "#848da2" }}>{spec.label}</span>
                                    <span
                                        style={{
                                            fontFamily: FONT_MONO,
                                            fontSize: 14,
                                            fontWeight: 500,
                                            fontVariantNumeric: "tabular-nums",
                                            color: "#eef0f5",
                                        }}
                                    >
                                        {spec.value}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Card de Acesso do Assinante */}
                    <aside id="login-card">
                        <form
                            onSubmit={onSubmit}
                            style={{
                                background: "#131720",
                                border: "1px solid rgba(238, 240, 245, 0.1)",
                                borderRadius: 12,
                                padding: 24,
                                display: "flex",
                                flexDirection: "column",
                                gap: 16,
                            }}
                        >
                            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                                <h2 style={{ margin: 0, fontSize: 18, fontWeight: 500, color: "#eef0f5", lineHeight: 1.25 }}>
                                    Acesso ao terminal
                                </h2>
                                <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: "#848da2" }}>
                                    Magic Walls · WIN × WDO
                                </span>
                            </div>

                            {bannerMsg && (
                                <div
                                    data-testid="saas-auth-banner"
                                    style={{
                                        padding: "10px 12px",
                                        borderRadius: 8,
                                        background: "#261316",
                                        border: "1px solid rgba(229, 72, 77, 0.36)",
                                        color: "#fca5a5",
                                        fontSize: 13,
                                        lineHeight: 1.45,
                                    }}
                                >
                                    {bannerMsg}
                                </div>
                            )}

                            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                <label
                                    htmlFor="mw-email-input"
                                    style={{ fontSize: 12, fontWeight: 500, color: "#a3a9b8" }}
                                >
                                    E-mail da assinatura
                                </label>
                                <input
                                    id="mw-email-input"
                                    data-testid="saas-email-input"
                                    type="email"
                                    required
                                    autoComplete="email"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    placeholder="voce@exemplo.com"
                                    className="mw-p-input"
                                />
                            </div>

                            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                <label
                                    htmlFor="mw-password-input"
                                    style={{ fontSize: 12, fontWeight: 500, color: "#a3a9b8" }}
                                >
                                    Senha
                                </label>
                                <div style={{ position: "relative" }}>
                                    <input
                                        id="mw-password-input"
                                        data-testid="saas-password-input"
                                        type={showPassword ? "text" : "password"}
                                        required
                                        autoComplete="current-password"
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        placeholder="••••••••"
                                        className="mw-p-input"
                                        style={{ paddingRight: 76 }}
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowPassword((prev) => !prev)}
                                        style={{
                                            position: "absolute",
                                            right: 6,
                                            top: "50%",
                                            transform: "translateY(-50%)",
                                            height: 28,
                                            padding: "0 8px",
                                            borderRadius: 6,
                                            border: "1px solid rgba(238, 240, 245, 0.1)",
                                            background: "#1b212e",
                                            color: "#a3a9b8",
                                            fontFamily: FONT_MONO,
                                            fontSize: 11,
                                            fontWeight: 400,
                                            cursor: "pointer",
                                        }}
                                    >
                                        {showPassword ? "Ocultar" : "Mostrar"}
                                    </button>
                                </div>
                            </div>

                            <button
                                data-testid="saas-login-btn"
                                type="submit"
                                disabled={submitting}
                                className="mw-p-btn-primary"
                                style={{ marginTop: 4 }}
                            >
                                {submitting ? "Autenticando..." : "Entrar no terminal"}
                            </button>

                            <div
                                style={{
                                    borderTop: "1px solid rgba(238, 240, 245, 0.08)",
                                    paddingTop: 12,
                                    fontSize: 12,
                                    color: "#848da2",
                                    lineHeight: 1.5,
                                }}
                            >
                                Sem acesso ou precisa de suporte? Fale em{" "}
                                <a
                                    href="https://instagram.com/magicwallsb3"
                                    target="_blank"
                                    rel="noreferrer noopener"
                                    className="mw-p-text-link"
                                >
                                    @magicwallsb3
                                </a>
                            </div>
                        </form>
                    </aside>
                </section>

                {/* Faixa 2: Momento #1 — Anatomia Interativa GEX + Fluxo e Divergências */}
                <section
                    id="regimes-gex"
                    ref={anatomyRef}
                    className="mw-section-card"
                    style={{
                        background: "#131720",
                        border: "1px solid rgba(238, 240, 245, 0.08)",
                        borderRadius: 16,
                        padding: 24,
                        display: "flex",
                        flexDirection: "column",
                        gap: 24,
                    }}
                >
                    <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
                        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            <h2 style={{ margin: 0, fontSize: 20, fontWeight: 500, color: "#eef0f5", letterSpacing: "-0.015em" }}>
                                Anatomia do método: GEX e Fluxo Smart Money na prática
                            </h2>
                            <p style={{ margin: 0, fontSize: 14, color: "#a3a9b8" }}>
                                Simulação contínua do pregão mostrando o avanço do fluxo institucional e a formação das divergências nas Walls
                            </p>
                        </div>

                        <div
                            role="tablist"
                            aria-label="Seletor de regime Gamma"
                            className="mw-regime-tabs"
                            style={{
                                display: "inline-flex",
                                background: "#0a0c12",
                                border: "1px solid rgba(238, 240, 245, 0.08)",
                                borderRadius: 8,
                                padding: 4,
                                gap: 4,
                            }}
                        >
                            <button
                                type="button"
                                role="tab"
                                aria-selected={regimeMode === "positive"}
                                onClick={() => handleRegimeChange("positive")}
                                className="mw-p-tab"
                            >
                                <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#4cc38a" }} />
                                <span>Gamma positivo</span>
                            </button>
                            <button
                                type="button"
                                role="tab"
                                aria-selected={regimeMode === "negative"}
                                onClick={() => handleRegimeChange("negative")}
                                className="mw-p-tab"
                            >
                                <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#e5484d" }} />
                                <span>Gamma negativo</span>
                            </button>
                        </div>
                    </div>

                    <div className="mw-anatomy-grid">
                        {/* Diagrama Vetorial Animado */}
                        <div
                            className="mw-anatomy-stage"
                            style={{
                                background: "#0e1118",
                                border: "1px solid rgba(238, 240, 245, 0.08)",
                                borderRadius: 8,
                                padding: 16,
                                display: "flex",
                                flexDirection: "column",
                                gap: 12,
                                minWidth: 0,
                            }}
                        >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                                    <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: "#848da2" }}>
                                        Simulação M5 · WINFUT
                                    </span>
                                    <span
                                        data-testid="anatomy-sim-clock"
                                        style={{
                                            padding: "2px 8px",
                                            borderRadius: 6,
                                            background: "#131720",
                                            border: "1px solid rgba(238, 240, 245, 0.1)",
                                            fontFamily: FONT_MONO,
                                            fontSize: 12,
                                            fontVariantNumeric: "tabular-nums",
                                            color: "#eef0f5",
                                        }}
                                    >
                                        {activeCandle.time} BRT
                                    </span>
                                </div>
                                <span
                                    style={{
                                        padding: "2px 8px",
                                        borderRadius: 6,
                                        background: activeRegime.softBg,
                                        color: activeRegime.accent,
                                        fontFamily: FONT_MONO,
                                        fontSize: 12,
                                        fontWeight: 500,
                                    }}
                                >
                                    {activeRegime.badge}
                                </span>
                            </div>

                            <svg
                                viewBox="0 0 600 400"
                                width="100%"
                                style={{ display: "block", height: "auto" }}
                                role="img"
                                aria-label="Simulação animada de Escada GEX e Divergências no Fluxo Smart Money ao longo do pregão"
                            >
                                {/* Escada GEX */}
                                <rect x="6" y="12" width="154" height="252" rx="6" fill="#131720" stroke="#232836" />
                                <text x="16" y="34" fill="#a3a9b8" fontSize="11" fontWeight="500" fontFamily={FONT_SANS}>
                                    Escada GEX
                                </text>

                                {/* Área de candles */}
                                <rect x="170" y="12" width="424" height="252" rx="6" fill="#0e1118" stroke="#232836" />

                                {/* Área Fluxo Smart Money */}
                                <rect x="170" y="276" width="424" height="114" rx="6" fill="#0e1118" stroke="#232836" />
                                <text x="182" y="294" fill="#7dd3fc" fontSize="11" fontWeight="500" fontFamily={FONT_SANS}>
                                    Fluxo Smart Money · Divergências
                                </text>
                                <line x1="178" y1="332" x2="586" y2="332" stroke="#232836" strokeDasharray="3 3" />

                                {/* Níveis da Escada + Linhas */}
                                {activeRegime.ladderBars.map((lvl) => {
                                    const isFocusLvl = lvl.label === activeTimeline.level;
                                    return (
                                        <g key={lvl.label}>
                                            <text
                                                x="16"
                                                y={lvl.y - 6}
                                                fill={isFocusLvl ? "#eef0f5" : "#848da2"}
                                                fontSize="10.5"
                                                fontWeight={isFocusLvl ? "500" : "400"}
                                                fontFamily={FONT_SANS}
                                            >
                                                {lvl.label}
                                            </text>
                                            <text x="150" y={lvl.y - 6} textAnchor="end" fill={lvl.color} fontSize="10.5" fontWeight="500" fontFamily={FONT_MONO}>
                                                {lvl.price}
                                            </text>
                                            <rect x="16" y={lvl.y} width="134" height={isFocusLvl ? 5 : 4} rx="2" fill="#1b212e" />
                                            <rect x="16" y={lvl.y} width={lvl.w} height={isFocusLvl ? 5 : 4} rx="2" fill={lvl.color} fillOpacity={isFocusLvl ? 1 : 0.72} />

                                            <line
                                                x1="176"
                                                y1={lvl.y}
                                                x2="586"
                                                y2={lvl.y}
                                                stroke={lvl.color}
                                                strokeOpacity={isFocusLvl ? 0.75 : lvl.isRef ? 0.5 : 0.36}
                                                strokeWidth={isFocusLvl ? "1.5" : lvl.isRef ? "1.2" : "1"}
                                                strokeDasharray={lvl.dashed ? "5 4" : lvl.isRef ? "2 3" : "4 4"}
                                            />
                                        </g>
                                    );
                                })}

                                {/* Cursor vertical de avanço do pregão */}
                                <line
                                    x1={cursorX}
                                    y1="20"
                                    x2={cursorX}
                                    y2="258"
                                    stroke="#38bdf8"
                                    strokeOpacity="0.3"
                                    strokeWidth="1"
                                    strokeDasharray="2 3"
                                />
                                <line
                                    x1={cursorX}
                                    y1="280"
                                    x2={cursorX}
                                    y2="386"
                                    stroke="#38bdf8"
                                    strokeOpacity="0.3"
                                    strokeWidth="1"
                                    strokeDasharray="2 3"
                                />

                                {/* Rastro sutil da curva completa futura no Fluxo */}
                                <path
                                    d={activeRegime.flowPath}
                                    fill="none"
                                    stroke="#38bdf8"
                                    strokeOpacity="0.12"
                                    strokeWidth="1.25"
                                    strokeDasharray="2 4"
                                />

                                {/* Candles progressivos até currentIdx */}
                                {activeRegime.candles.slice(0, currentIdx + 1).map((cd, idx) => {
                                    const isLatest = idx === currentIdx && currentIdx < maxCandleIdx;
                                    const interpC = isLatest ? cd.o + (cd.c - cd.o) * barFrac : cd.c;
                                    const interpH = isLatest ? cd.o + (cd.h - cd.o) * barFrac : cd.h;
                                    const interpL = isLatest ? cd.o + (cd.l - cd.o) * barFrac : cd.l;
                                    const topWick = Math.min(interpH, cd.o, interpC);
                                    const botWick = Math.max(interpL, cd.o, interpC);
                                    const bullish = interpC < cd.o;
                                    const topBody = Math.min(cd.o, interpC);
                                    const bodyH = Math.max(4, Math.abs(interpC - cd.o));
                                    const fill = isLatest ? "#cbd5e1" : bullish ? "#9aa5b6" : "#475266";
                                    const pinY = cd.pinPos === "top" ? cd.h - 14 : cd.l + 15;
                                    const showPin = Boolean(cd.pin) && (!isLatest || barFrac >= 0.55);

                                    return (
                                        <g key={cd.time}>
                                            <line x1={cd.x} y1={topWick} x2={cd.x} y2={botWick} stroke={fill} strokeWidth="1.5" />
                                            <rect x={cd.x - 5} y={topBody} width="10" height={bodyH} rx="1.5" fill={fill} />
                                            {showPin && (
                                                <g>
                                                    {idx === currentIdx && (
                                                        <circle
                                                            cx={cd.x}
                                                            cy={pinY}
                                                            r="9.5"
                                                            fill="none"
                                                            stroke={cd.pinTone}
                                                            strokeWidth="1.5"
                                                            className="mw-pin-ring"
                                                        />
                                                    )}
                                                    <circle cx={cd.x} cy={pinY} r="9.5" fill="#131720" stroke={cd.pinTone} strokeWidth="1.5" />
                                                    <text
                                                        x={cd.x}
                                                        y={pinY + 3.5}
                                                        textAnchor="middle"
                                                        fill={cd.pinTone}
                                                        fontSize="10.5"
                                                        fontWeight="600"
                                                        fontFamily={FONT_MONO}
                                                    >
                                                        {cd.pin}
                                                    </text>
                                                </g>
                                            )}
                                        </g>
                                    );
                                })}

                                {/* Linhas de divergência reveladas no gatilho */}
                                {activeRegime.divergences
                                    .filter((div) => currentIdx >= div.triggerIdx)
                                    .map((div) => (
                                        <g key={div.id}>
                                            <line
                                                x1={div.priceLine.x1}
                                                y1={div.priceLine.y1}
                                                x2={div.priceLine.x2}
                                                y2={div.priceLine.y2}
                                                stroke={div.tone}
                                                strokeWidth="1.75"
                                                strokeDasharray="4 3"
                                            />
                                            <circle cx={div.priceLine.x1} cy={div.priceLine.y1} r="2.8" fill={div.tone} />
                                            <circle cx={div.priceLine.x2} cy={div.priceLine.y2} r="2.8" fill={div.tone} />

                                            <line
                                                x1={div.flowLine.x1}
                                                y1={div.flowLine.y1}
                                                x2={div.flowLine.x2}
                                                y2={div.flowLine.y2}
                                                stroke={div.tone}
                                                strokeWidth="1.8"
                                                strokeDasharray="4 3"
                                            />
                                            <circle cx={div.flowLine.x1} cy={div.flowLine.y1} r="3" fill={div.tone} />
                                            <text
                                                x={div.labelX}
                                                y={div.labelY}
                                                textAnchor={div.anchor}
                                                fill={div.tone}
                                                fontSize="10.5"
                                                fontWeight="500"
                                                fontFamily={FONT_MONO}
                                            >
                                                {div.label}
                                            </text>
                                        </g>
                                    ))}

                                {/* Curva progressiva Fluxo Smart Money */}
                                {activeFlowPath && (
                                    <path
                                        d={activeFlowPath}
                                        fill="none"
                                        stroke="#38bdf8"
                                        strokeWidth="2"
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                    />
                                )}

                                {/* Ponto vivo na extremidade da curva de fluxo */}
                                <circle
                                    cx={cursorX}
                                    cy={cursorFlowY}
                                    r="3.5"
                                    fill="#38bdf8"
                                    stroke="#0e1118"
                                    strokeWidth="1.2"
                                    className="mw-cursor-dot"
                                />

                                {activeRegime.flowPins
                                    .filter((fp) => currentIdx >= fp.triggerIdx)
                                    .map((fp) => (
                                        <g key={fp.label}>
                                            <line x1={fp.x} y1="276" x2={fp.x} y2="388" stroke={fp.tone} strokeOpacity="0.28" strokeDasharray="3 3" />
                                            {currentIdx === fp.triggerIdx && (
                                                <circle
                                                    cx={fp.x}
                                                    cy={fp.y}
                                                    r="8"
                                                    fill="none"
                                                    stroke={fp.tone}
                                                    strokeWidth="1.4"
                                                    className="mw-pin-ring"
                                                />
                                            )}
                                            <circle cx={fp.x} cy={fp.y} r="8" fill="#131720" stroke={fp.tone} strokeWidth="1.5" />
                                            <text x={fp.x} y={fp.y + 3.5} textAnchor="middle" fill={fp.tone} fontSize="10" fontWeight="600" fontFamily={FONT_MONO}>
                                                {fp.label}
                                            </text>
                                        </g>
                                    ))}
                            </svg>

                            {/* Barra de telemetria + controles da simulação */}
                            <div
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "space-between",
                                    gap: 12,
                                    flexWrap: "wrap",
                                    paddingTop: 10,
                                    borderTop: "1px solid rgba(238, 240, 245, 0.08)",
                                }}
                            >
                                <div style={{ display: "flex", flexDirection: "column", gap: 8, flex: "1 1 260px", minWidth: 0, width: "100%" }}>
                                    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
                                        <span
                                            data-testid="anatomy-sim-status"
                                            style={{
                                                fontSize: 12.5,
                                                lineHeight: 1.4,
                                                fontWeight: 500,
                                                color: activeTimeline.tone,
                                                minWidth: 0,
                                            }}
                                        >
                                            {activeTimeline.text}
                                        </span>
                                        <span style={{ fontFamily: FONT_MONO, fontSize: 11.5, color: "#848da2", fontVariantNumeric: "tabular-nums", flexShrink: 0, whiteSpace: "nowrap" }}>
                                            {currentIdx + 1}/{maxCandleIdx + 1}
                                        </span>
                                    </div>

                                    <div
                                        style={{
                                            display: "grid",
                                            gridTemplateColumns: `repeat(${activeRegime.candles.length}, minmax(0, 1fr))`,
                                            gap: 3,
                                        }}
                                        aria-label="Linha do tempo do pregão ilustrativo"
                                    >
                                        {activeRegime.candles.map((cd, idx) => {
                                            const active = idx <= currentIdx;
                                            const barTone = cd.pin ? cd.pinTone : active ? "#38bdf8" : "#1b212e";
                                            return (
                                                <button
                                                    key={cd.time}
                                                    type="button"
                                                    onClick={() => {
                                                        setSimPlaying(false);
                                                        setSimProgress(idx);
                                                    }}
                                                    title={cd.pin ? `${cd.time} BRT · Sinal #${cd.pin}` : `${cd.time} BRT`}
                                                    aria-label={`Ir para barra ${cd.time}${cd.pin ? ` (Sinal #${cd.pin})` : ""}`}
                                                    style={{
                                                        height: cd.pin ? 7 : 4,
                                                        alignSelf: "center",
                                                        borderRadius: 2,
                                                        border: "none",
                                                        padding: 0,
                                                        background: barTone,
                                                        opacity: active ? 1 : 0.45,
                                                        cursor: "pointer",
                                                    }}
                                                />
                                            );
                                        })}
                                    </div>
                                </div>

                                <div className="mw-anatomy-controls" style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                                    <button
                                        type="button"
                                        data-testid="anatomy-sim-toggle"
                                        onClick={() => setSimPlaying((p) => !p)}
                                        className="mw-p-btn-secondary"
                                        style={{ height: 30, padding: "0 11px", fontFamily: FONT_MONO, fontSize: 12 }}
                                    >
                                        {simPlaying ? "Pausar" : "Simular"}
                                    </button>
                                    <button
                                        type="button"
                                        data-testid="anatomy-sim-replay"
                                        onClick={handleReplayAnatomy}
                                        className="mw-p-btn-secondary"
                                        style={{ height: 30, padding: "0 11px", fontFamily: FONT_MONO, fontSize: 12 }}
                                    >
                                        Reiniciar
                                    </button>
                                </div>
                            </div>
                        </div>

                        {/* Leitura Editorial Única Sincronizada com a Simulação */}
                        <div
                            className="mw-anatomy-editorial"
                            style={{
                                background: "#0e1118",
                                border: "1px solid rgba(238, 240, 245, 0.08)",
                                borderLeft: `2px solid ${activeRegime.accent}`,
                                borderRadius: 8,
                                padding: 20,
                                display: "flex",
                                flexDirection: "column",
                                justifyContent: "space-between",
                                gap: 16,
                                minWidth: 0,
                            }}
                        >
                            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                                <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: activeRegime.accent }}>
                                    {activeRegime.shortLabel}
                                </span>
                            </div>

                            <div style={{ display: "flex", flexDirection: "column", gap: 16, flex: 1 }}>
                                <div
                                    style={{
                                        display: "flex",
                                        flexDirection: "column",
                                        gap: 4,
                                        paddingLeft: 10,
                                        borderLeft: `2px solid ${activeTimeline.layer === 1 ? activeRegime.accent : "transparent"}`,
                                        transition: "border-color 220ms var(--p-ease)",
                                    }}
                                >
                                    <div style={{ fontSize: 13, fontWeight: 500, color: activeTimeline.layer === 1 ? "#eef0f5" : "#a3a9b8" }}>
                                        01 · Mecânica do regime Gamma
                                    </div>
                                    <p style={{ margin: 0, fontSize: 13, lineHeight: 1.55, color: "#a3a9b8" }}>
                                        {activeRegime.hedgeMechanic}
                                    </p>
                                </div>

                                <div
                                    style={{
                                        borderTop: "1px solid rgba(238, 240, 245, 0.08)",
                                        paddingTop: 16,
                                        display: "flex",
                                        flexDirection: "column",
                                        gap: 4,
                                        paddingLeft: 10,
                                        borderLeft: `2px solid ${activeTimeline.layer === 2 ? activeRegime.accent : "transparent"}`,
                                        transition: "border-color 220ms var(--p-ease)",
                                    }}
                                >
                                    <div style={{ fontSize: 13, fontWeight: 500, color: activeTimeline.layer === 2 ? "#eef0f5" : "#a3a9b8" }}>
                                        02 · Comportamento estatístico nas Walls
                                    </div>
                                    <p style={{ margin: 0, fontSize: 13, lineHeight: 1.55, color: "#a3a9b8" }}>
                                        {activeRegime.wallBehavior}
                                    </p>
                                </div>

                                <div
                                    style={{
                                        borderTop: "1px solid rgba(238, 240, 245, 0.08)",
                                        paddingTop: 16,
                                        display: "flex",
                                        flexDirection: "column",
                                        gap: 4,
                                        paddingLeft: 10,
                                        borderLeft: `2px solid ${activeTimeline.layer === 3 ? activeRegime.accent : "transparent"}`,
                                        transition: "border-color 220ms var(--p-ease)",
                                    }}
                                >
                                    <div style={{ fontSize: 13, fontWeight: 500, color: activeTimeline.layer === 3 ? "#eef0f5" : "#a3a9b8" }}>
                                        03 · Divergência no Fluxo Smart Money
                                    </div>
                                    <p style={{ margin: 0, fontSize: 13, lineHeight: 1.55, color: "#a3a9b8" }}>
                                        {activeRegime.flowReading}
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>

                {/* Faixa 2.5: Resumo Acumulado — Últimos 30 Pregões */}
                <section
                    id="resultados-30d"
                    ref={statsRef}
                    data-testid="stats-30d-section"
                    className="mw-section-card"
                    style={{
                        background: "#131720",
                        border: "1px solid rgba(238, 240, 245, 0.08)",
                        borderRadius: 16,
                        padding: 24,
                        display: "flex",
                        flexDirection: "column",
                        gap: 20,
                    }}
                >
                    <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
                        <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                                <h2 style={{ margin: 0, fontSize: 20, fontWeight: 500, color: "#eef0f5", letterSpacing: "-0.015em" }}>
                                    Resumo acumulado — Últimos 30 pregões
                                </h2>
                                <span
                                    style={{
                                        padding: "2px 9px",
                                        borderRadius: 6,
                                        background: "#1b212e",
                                        border: "1px solid rgba(56, 189, 248, 0.25)",
                                        fontFamily: FONT_MONO,
                                        fontSize: 12,
                                        fontVariantNumeric: "tabular-nums",
                                        color: "#7dd3fc",
                                    }}
                                >
                                    {STATS_30D.period}
                                </span>
                            </div>
                            <p style={{ margin: 0, fontSize: 14, color: "#a3a9b8" }}>
                                Consolidação histórica sinal a sinal em WIN e WDO com proteção na outra Wall (critério alvo ≥150 / ≥4 pts)
                            </p>
                        </div>

                        <button
                            type="button"
                            data-testid="stats-30d-replay"
                            onClick={handleTriggerStats}
                            className="mw-p-btn-secondary mw-stats-replay-btn"
                            style={{ height: 34, padding: "0 14px", fontFamily: FONT_MONO, fontSize: 12, flexShrink: 0 }}
                        >
                            Reexecutar
                        </button>
                    </div>

                    {/* Barra de evolução + contagem simultânea dos 30 pregões */}
                    <div
                        style={{
                            background: "#0e1118",
                            border: "1px solid rgba(238, 240, 245, 0.08)",
                            borderRadius: 8,
                            padding: "10px 14px",
                            display: "flex",
                            flexDirection: "column",
                            gap: 8,
                        }}
                    >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap", fontFamily: FONT_MONO, fontSize: 12, fontVariantNumeric: "tabular-nums" }}>
                            <span style={{ color: "#eef0f5", whiteSpace: "nowrap" }}>
                                Pregão {String(sessionProgressCount).padStart(2, "0")}/{STATS_30D.sessions}
                            </span>
                            <span
                                data-testid="stats-30d-countdown"
                                style={{ color: statsT >= 1 ? "#4cc38a" : "#7dd3fc", whiteSpace: "nowrap" }}
                            >
                                {statsT >= 1
                                    ? "30/30 · Consolidado"
                                    : `Faltam ${String(sessionsRemaining).padStart(2, "0")} pregões`}
                            </span>
                        </div>
                        <div style={{ width: "100%", height: 3, borderRadius: 999, background: "#1b212e", overflow: "hidden" }}>
                            <div
                                style={{
                                    width: `${(easedP * 100).toFixed(1)}%`,
                                    height: "100%",
                                    background: "#38bdf8",
                                }}
                            />
                        </div>
                    </div>

                    {/* 2 Cards-Resumo Lado a Lado (WIN e WDO) */}
                    <div className="mw-stats-cards-grid">
                        {[
                            {
                                id: "win",
                                title: "WIN · Mini-Índice",
                                netTxt: `${fmtSignedInt(winNetAnim)} pts`,
                                grossTxt: `${fmtSignedInt(STATS_30D.win.grossPts * easedP)}`,
                                stopTxt: `${fmtSignedInt(STATS_30D.win.stopPts * easedP)}`,
                                paidPct: STATS_30D.win.paidPct,
                                neutralPct: STATS_30D.win.neutralPct,
                                stopPct: STATS_30D.win.stopPct,
                                posDays: Math.round(STATS_30D.win.posDays * easedP),
                                negDays: Math.round(STATS_30D.win.negDays * easedP),
                            },
                            {
                                id: "wdo",
                                title: "WDO · Mini-Dólar",
                                netTxt: `${fmtSignedDec1(wdoNetAnim)} pts`,
                                grossTxt: `${fmtSignedDec1(STATS_30D.wdo.grossPts * easedP)}`,
                                stopTxt: `${fmtSignedDec1(STATS_30D.wdo.stopPts * easedP)}`,
                                paidPct: STATS_30D.wdo.paidPct,
                                neutralPct: STATS_30D.wdo.neutralPct,
                                stopPct: STATS_30D.wdo.stopPct,
                                posDays: Math.round(STATS_30D.wdo.posDays * easedP),
                                negDays: Math.round(STATS_30D.wdo.negDays * easedP),
                            },
                        ].map((card) => (
                            <div
                                key={card.id}
                                style={{
                                    background: "#0e1118",
                                    border: "1px solid rgba(238, 240, 245, 0.08)",
                                    borderRadius: 10,
                                    padding: 16,
                                    display: "flex",
                                    flexDirection: "column",
                                    gap: 12,
                                }}
                            >
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                                    <span style={{ fontSize: 13, fontWeight: 500, color: "#a3a9b8" }}>
                                        {card.title}
                                    </span>
                                    <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: "#848da2", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
                                        {card.posDays} pos · {card.negDays} neg
                                    </span>
                                </div>

                                <div
                                    data-testid={`stats-30d-net-${card.id}`}
                                    style={{
                                        fontFamily: FONT_MONO,
                                        fontSize: "clamp(26px, 2.8vw, 32px)",
                                        fontWeight: 600,
                                        lineHeight: 1.15,
                                        fontVariantNumeric: "tabular-nums",
                                        color: "#4cc38a",
                                    }}
                                >
                                    {card.netTxt}
                                </div>

                                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap", fontFamily: FONT_MONO, fontSize: 12, fontVariantNumeric: "tabular-nums" }}>
                                    <span style={{ color: "#4cc38a", whiteSpace: "nowrap" }}>Bruto {card.grossTxt} pts</span>
                                    <span style={{ color: "#e5484d", whiteSpace: "nowrap" }}>Stops {card.stopTxt} pts</span>
                                </div>

                                <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 2 }}>
                                    <div style={{ display: "flex", height: 4, borderRadius: 999, background: "#1b212e", overflow: "hidden" }}>
                                        <div style={{ width: `${(card.paidPct * easedP).toFixed(1)}%`, background: "#4cc38a" }} />
                                        <div style={{ width: `${(card.neutralPct * easedP).toFixed(1)}%`, background: "#848da2" }} />
                                        <div style={{ width: `${(card.stopPct * easedP).toFixed(1)}%`, background: "#e5484d" }} />
                                    </div>
                                    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 4, fontFamily: FONT_MONO, fontSize: 11, color: "#848da2", fontVariantNumeric: "tabular-nums" }}>
                                        <span style={{ color: "#4cc38a", textAlign: "left" }}>Pagaram {fmtPtDec1(card.paidPct * easedP)}%</span>
                                        <span style={{ textAlign: "center" }}>Neutros {fmtPtDec1(card.neutralPct * easedP)}%</span>
                                        <span style={{ color: "#e5484d", textAlign: "right" }}>Stops {fmtPtDec1(card.stopPct * easedP)}%</span>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* Tabela Desktop (> 720px) */}
                    <div className="mw-stats-table-wrap">
                        <table className="mw-stats-table" data-testid="stats-30d-table">
                            <thead>
                                <tr>
                                    <th>Métrica</th>
                                    <th>WIN (Índice)</th>
                                    <th>WDO (Dólar)</th>
                                </tr>
                            </thead>
                            <tbody>
                                {statsRows.map((row) => (
                                    <tr key={row.key} style={row.highlight ? { background: "#111824" } : undefined}>
                                        <td style={{ color: row.highlight ? "#eef0f5" : "#a3a9b8", fontWeight: row.highlight ? 600 : 400 }}>
                                            {row.label}
                                        </td>
                                        <td style={{ color: row.winColor, fontWeight: row.winWeight || 400 }}>{row.win}</td>
                                        <td style={{ color: row.wdoColor, fontWeight: row.wdoWeight || 400 }}>{row.wdo}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    {/* Lista Mobile Simétrica WIN × WDO (≤ 720px, zero scroll horizontal) */}
                    <div className="mw-stats-mobile-list" data-testid="stats-30d-mobile-list">
                        {statsRows.map((row) => (
                            <div
                                key={row.key}
                                className="mw-stats-mobile-row"
                                style={row.highlight ? { background: "#111824" } : undefined}
                            >
                                <div style={{ fontSize: 12, fontWeight: row.highlight ? 600 : 500, color: row.highlight ? "#eef0f5" : "#a3a9b8" }}>
                                    {row.label}
                                </div>
                                <div className="mw-stats-mobile-cols">
                                    <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                                        <span style={{ fontFamily: FONT_MONO, fontSize: 10, color: "#848da2" }}>WIN (Índice)</span>
                                        <span style={{ fontFamily: FONT_MONO, fontSize: 12.5, fontVariantNumeric: "tabular-nums", lineHeight: 1.35, color: row.winColor, fontWeight: row.winWeight || 400 }}>
                                            {row.win}
                                        </span>
                                    </div>
                                    <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                                        <span style={{ fontFamily: FONT_MONO, fontSize: 10, color: "#848da2" }}>WDO (Dólar)</span>
                                        <span style={{ fontFamily: FONT_MONO, fontSize: 12.5, fontVariantNumeric: "tabular-nums", lineHeight: 1.35, color: row.wdoColor, fontWeight: row.wdoWeight || 400 }}>
                                            {row.wdo}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>

                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", fontSize: 12, color: "#848da2" }}>
                        <span>Amostra auditada dos pregões de 07/10 a 19/11/2026 com motor oficial de divergências V3.2 nas Walls.</span>
                        <span style={{ fontFamily: FONT_MONO }}>Resultados históricos não garantem retornos futuros (CVM 20).</span>
                    </div>
                </section>

                {/* Faixa 3: Momento #2 — Prints de Dias Reais (Destaque Assimétrico + Par) */}
                <section id="dias-reais" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                    <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            <h2 style={{ margin: 0, fontSize: 22, fontWeight: 500, color: "#eef0f5", letterSpacing: "-0.015em" }}>
                                Prints de dias reais do sistema
                            </h2>
                            <p style={{ margin: 0, fontSize: 14, color: "#a3a9b8" }}>
                                Capturas diretas de pregões encerrados em WIN e WDO. Clique em qualquer imagem para ampliar
                            </p>
                        </div>
                        <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: "#848da2" }}>
                            Capturas reais · Sem edição gráfica
                        </span>
                    </div>

                    {/* Card Principal em Destaque Amplo */}
                    <article
                        className="mw-featured-print mw-print-card"
                        style={{
                            background: "#131720",
                            border: "1px solid rgba(238, 240, 245, 0.08)",
                            borderRadius: 12,
                            padding: 20,
                        }}
                    >
                        <button
                            type="button"
                            onClick={() => setActivePrint(featuredPrint)}
                            aria-label={`Ampliar print real de ${featuredPrint.date} (${featuredPrint.asset})`}
                            className="mw-p-img-btn"
                        >
                            <img
                                src={featuredPrint.src}
                                alt={`${featuredPrint.asset} - pregão real de ${featuredPrint.date}`}
                                loading="lazy"
                                style={{
                                    width: "100%",
                                    aspectRatio: "16 / 9",
                                    objectFit: "cover",
                                    objectPosition: "top center",
                                    display: "block",
                                }}
                            />
                        </button>

                        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 12, fontFamily: FONT_MONO, fontSize: 12 }}>
                                <span style={{ color: "#7dd3fc", fontVariantNumeric: "tabular-nums" }}>{featuredPrint.date}</span>
                                <span style={{ color: "#848da2" }}>{featuredPrint.asset}</span>
                            </div>

                            <h3 style={{ margin: 0, fontSize: 18, fontWeight: 500, color: "#eef0f5", lineHeight: 1.3 }}>
                                {featuredPrint.title}
                            </h3>

                            <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: "#a3a9b8" }}>
                                {featuredPrint.summary}
                            </p>

                            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, paddingTop: 12, borderTop: "1px solid rgba(238, 240, 245, 0.08)" }}>
                                <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: "#848da2" }}>
                                    {featuredPrint.regime}
                                </span>
                                <button
                                    type="button"
                                    onClick={() => setActivePrint(featuredPrint)}
                                    className="mw-p-btn-secondary"
                                    style={{ height: 32, padding: "0 12px", fontFamily: FONT_MONO, fontSize: 12 }}
                                >
                                    <IconMaximize />
                                    <span>Ampliar</span>
                                </button>
                            </div>
                        </div>
                    </article>

                    {/* Par Secundário (WIN e WDO) */}
                    <div className="mw-prints-secondary">
                        {secondaryPrints.map((item) => (
                            <article
                                key={item.id}
                                className="mw-print-card"
                                style={{
                                    background: "#131720",
                                    border: "1px solid rgba(238, 240, 245, 0.08)",
                                    borderRadius: 12,
                                    padding: 20,
                                    display: "flex",
                                    flexDirection: "column",
                                    gap: 12,
                                }}
                            >
                                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, fontFamily: FONT_MONO, fontSize: 12 }}>
                                    <span style={{ display: "inline-flex", alignItems: "center", gap: 8, color: "#eef0f5", fontVariantNumeric: "tabular-nums" }}>
                                        <span style={{ width: 6, height: 6, borderRadius: "50%", background: item.regimeTone }} />
                                        {item.date}
                                    </span>
                                    <span style={{ color: "#848da2" }}>{item.asset}</span>
                                </div>

                                <button
                                    type="button"
                                    onClick={() => setActivePrint(item)}
                                    aria-label={`Ampliar print real de ${item.date} (${item.asset})`}
                                    className="mw-p-img-btn"
                                >
                                    <img
                                        src={item.src}
                                        alt={`${item.asset} - pregão real de ${item.date}`}
                                        loading="lazy"
                                        style={{
                                            width: "100%",
                                            aspectRatio: "16 / 10",
                                            objectFit: "cover",
                                            objectPosition: "top center",
                                            display: "block",
                                        }}
                                    />
                                </button>

                                <div style={{ display: "flex", flexDirection: "column", gap: 6, flex: 1 }}>
                                    <h3 style={{ margin: 0, fontSize: 15, fontWeight: 500, color: "#eef0f5", lineHeight: 1.35 }}>
                                        {item.title}
                                    </h3>
                                    <p style={{ margin: 0, fontSize: 13, lineHeight: 1.55, color: "#a3a9b8" }}>
                                        {item.summary}
                                    </p>
                                </div>

                                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, paddingTop: 12, borderTop: "1px solid rgba(238, 240, 245, 0.08)" }}>
                                    <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: "#848da2" }}>
                                        {item.regime}
                                    </span>
                                    <button
                                        type="button"
                                        onClick={() => setActivePrint(item)}
                                        className="mw-p-btn-secondary"
                                        style={{ height: 32, padding: "0 12px", fontFamily: FONT_MONO, fontSize: 12 }}
                                    >
                                        <IconMaximize />
                                        <span>Ampliar</span>
                                    </button>
                                </div>
                            </article>
                        ))}
                    </div>
                </section>

                {/* Faixa 4: Arquitetura Analítica em 3 Camadas (Layout Editorial sem Caixas Repetidas) */}
                <section id="como-funciona" style={{ display: "flex", flexDirection: "column", gap: 24 }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 500, color: "#eef0f5", letterSpacing: "-0.015em" }}>
                            Como o terminal combina GEX e fluxo em tempo real
                        </h2>
                        <p style={{ margin: 0, fontSize: 14, color: "#a3a9b8", maxWidth: "62ch" }}>
                            Cada elemento da tela responde a uma camada objetiva de leitura, sem indicadores atrasados baseados apenas em candles passados
                        </p>
                    </div>

                    <div className="mw-layers-grid">
                        {THREE_LAYERS.map((layer) => (
                            <div
                                key={layer.step}
                                style={{
                                    borderTop: "1px solid rgba(238, 240, 245, 0.12)",
                                    paddingTop: 20,
                                    display: "flex",
                                    flexDirection: "column",
                                    gap: 8,
                                }}
                            >
                                <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: "#848da2", fontVariantNumeric: "tabular-nums" }}>
                                    {layer.step}
                                </span>
                                <h3 style={{ margin: 0, fontSize: 16, fontWeight: 500, color: "#eef0f5", lineHeight: 1.3 }}>
                                    {layer.title}
                                </h3>
                                <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: "#a3a9b8" }}>
                                    {layer.desc}
                                </p>
                            </div>
                        ))}
                    </div>
                </section>

                {/* Faixa 5: Produto Único — O que está incluído */}
                <section
                    id="o-que-inclui"
                    className="mw-section-card"
                    style={{
                        background: "#131720",
                        border: "1px solid rgba(238, 240, 245, 0.08)",
                        borderRadius: 16,
                        padding: 32,
                    }}
                >
                    <div className="mw-product-grid">
                        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: "#848da2" }}>
                                    Assinatura única · GEX + Fluxo institucional
                                </span>
                                <h2 style={{ margin: 0, fontSize: 22, fontWeight: 500, color: "#eef0f5", letterSpacing: "-0.015em" }}>
                                    O que está incluído no terminal Magic Walls
                                </h2>
                                <p style={{ margin: 0, fontSize: 14, color: "#a3a9b8", lineHeight: 1.6, maxWidth: "54ch" }}>
                                    Produto direto ao ponto para quem opera mini-índice (WIN) e mini-dólar (WDO) com leitura objetiva de liquidez e divergências.
                                </p>
                            </div>

                            <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 12 }}>
                                {INCLUDED_ITEMS.map((item) => (
                                    <li key={item} style={{ display: "flex", alignItems: "flex-start", gap: 12, fontSize: 14, color: "#eef0f5", lineHeight: 1.5 }}>
                                        <span style={{ width: 16, height: 16, marginTop: 3, color: "#a3a9b8", flexShrink: 0, display: "inline-flex" }}>
                                            <IconCheck />
                                        </span>
                                        <span>{item}</span>
                                    </li>
                                ))}
                            </ul>
                        </div>

                        <div
                            style={{
                                background: "#0a0c12",
                                border: "1px solid rgba(238, 240, 245, 0.08)",
                                borderRadius: 8,
                                padding: 24,
                                display: "flex",
                                flexDirection: "column",
                                gap: 16,
                            }}
                        >
                            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                <h3 style={{ margin: 0, fontSize: 16, fontWeight: 500, color: "#eef0f5" }}>
                                    Quer contratar ou conhecer o terminal?
                                </h3>
                                <p style={{ margin: 0, fontSize: 13, lineHeight: 1.6, color: "#a3a9b8" }}>
                                    Fale diretamente com nossa equipe pelo Instagram oficial{" "}
                                    <span style={{ color: "#eef0f5", fontFamily: FONT_MONO }}>@magicwallsb3</span> para liberar seu acesso ao terminal ou acompanhar os estudos de pregão.
                                </p>
                            </div>

                            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                <a
                                    href="https://instagram.com/magicwallsb3"
                                    target="_blank"
                                    rel="noreferrer noopener"
                                    className="mw-p-btn-primary"
                                >
                                    <span>Falar no @magicwallsb3</span>
                                    <IconArrowUpRight />
                                </a>

                                <a
                                    href="#login-card"
                                    className="mw-p-btn-secondary"
                                    style={{ height: 40 }}
                                >
                                    Já sou assinante · Ir para o login
                                </a>
                            </div>
                        </div>
                    </div>
                </section>

                {/* Faixa 6: Perguntas Frequentes (Accordion Único Dividido por Hairlines) */}
                <section id="faq" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 500, color: "#eef0f5", letterSpacing: "-0.015em" }}>
                            Perguntas frequentes
                        </h2>
                        <p style={{ margin: 0, fontSize: 14, color: "#a3a9b8" }}>
                            Dúvidas diretas sobre o terminal Magic Walls no dia a dia de pregão
                        </p>
                    </div>

                    <div
                        style={{
                            background: "#131720",
                            border: "1px solid rgba(238, 240, 245, 0.08)",
                            borderRadius: 12,
                            overflow: "hidden",
                        }}
                    >
                        {FAQ_ITEMS.map((item, idx) => {
                            const isOpen = openFaqIdx === idx;
                            return (
                                <div
                                    key={item.q}
                                    style={{
                                        borderTop: idx > 0 ? "1px solid rgba(238, 240, 245, 0.08)" : "none",
                                    }}
                                >
                                    <button
                                        type="button"
                                        aria-expanded={isOpen}
                                        onClick={() => setOpenFaqIdx(isOpen ? -1 : idx)}
                                        className="mw-p-faq-btn"
                                    >
                                        <span>{item.q}</span>
                                        <span style={{ color: isOpen ? "#eef0f5" : "#848da2", flexShrink: 0, display: "inline-flex" }}>
                                            <IconChevron open={isOpen} />
                                        </span>
                                    </button>
                                    {isOpen && (
                                        <div
                                            style={{
                                                padding: "0 20px 16px",
                                                fontSize: 14,
                                                lineHeight: 1.6,
                                                color: "#a3a9b8",
                                                maxWidth: "74ch",
                                            }}
                                        >
                                            {item.a}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </section>
            </main>

            {/* Lightbox de Ampliação de Print Real */}
            {activePrint && (
                <div
                    role="dialog"
                    aria-modal="true"
                    aria-label={`Print real de ${activePrint.date}`}
                    onClick={() => setActivePrint(null)}
                    style={{
                        position: "fixed",
                        inset: 0,
                        zIndex: 100,
                        background: "rgba(10, 12, 18, 0.94)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        padding: 24,
                    }}
                >
                    <div
                        onClick={(e) => e.stopPropagation()}
                        style={{
                            width: "100%",
                            maxWidth: 1180,
                            background: "#131720",
                            border: "1px solid rgba(238, 240, 245, 0.14)",
                            borderRadius: 16,
                            padding: 20,
                            display: "flex",
                            flexDirection: "column",
                            gap: 16,
                        }}
                    >
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
                            <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
                                <span style={{ fontFamily: FONT_MONO, fontSize: 12, fontWeight: 500, color: "#7dd3fc", fontVariantNumeric: "tabular-nums" }}>
                                    {activePrint.date}
                                </span>
                                <span style={{ fontSize: 15, fontWeight: 500, color: "#eef0f5" }}>
                                    {activePrint.asset} · {activePrint.title}
                                </span>
                            </div>
                            <button
                                type="button"
                                onClick={() => setActivePrint(null)}
                                className="mw-p-btn-secondary"
                                style={{ height: 32, padding: "0 12px" }}
                            >
                                <span>Fechar</span>
                                <span className="mw-p-keycap">Esc</span>
                            </button>
                        </div>

                        <img
                            src={activePrint.src}
                            alt={`${activePrint.asset} - pregão real de ${activePrint.date}`}
                            style={{
                                width: "100%",
                                maxHeight: "74vh",
                                objectFit: "contain",
                                borderRadius: 8,
                                border: "1px solid rgba(238, 240, 245, 0.08)",
                                background: "#0a0c12",
                                display: "block",
                            }}
                        />

                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap", fontSize: 13, color: "#a3a9b8" }}>
                            <span style={{ maxWidth: "74ch" }}>{activePrint.summary}</span>
                            <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: "#848da2" }}>
                                Pregão encerrado · Resultados passados não garantem retornos futuros
                            </span>
                        </div>
                    </div>
                </div>
            )}

            {/* Rodapé Institucional CVM 20 */}
            <footer
                className="mw-portal-footer"
                style={{
                    borderTop: "1px solid rgba(238, 240, 245, 0.08)",
                    background: "#0a0c12",
                    padding: "24px",
                }}
            >
                <div
                    style={{
                        maxWidth: 1200,
                        margin: "0 auto",
                        display: "flex",
                        flexDirection: "column",
                        gap: 12,
                    }}
                >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", fontSize: 12, color: "#a3a9b8" }}>
                        <span style={{ fontWeight: 500, color: "#eef0f5" }}>Magic Walls · GEX + Fluxo institucional</span>
                        <span style={{ fontFamily: FONT_MONO, color: "#848da2" }}>@magicwallsb3</span>
                    </div>
                    <p style={{ margin: 0, fontSize: 12, lineHeight: 1.6, color: "#848da2" }}>
                        <strong style={{ color: "#a3a9b8", fontWeight: 500 }}>Aviso legal (Resolução CVM nº 20/2021):</strong> A Magic Walls é uma ferramenta de software voltada à análise quantitativa e educacional de dados de mercado. Os níveis, métricas históricas e sinalizações exibidas não constituem recomendação de compra ou venda de ativos mobiliários. Operações em mercados futuros envolvem risco elevado de perda financeira; resultados passados ou simulados não garantem retornos futuros.
                    </p>
                </div>
            </footer>
        </div>
    );
}
