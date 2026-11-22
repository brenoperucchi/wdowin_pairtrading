import { useEffect, useState } from "react";
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
            { x: 194, o: 158, c: 138, h: 132, l: 164 },
            { x: 222, o: 138, c: 108, h: 100, l: 144 },
            { x: 250, o: 108, c: 76, h: 66, l: 112 },
            { x: 278, o: 76, c: 92, h: 72, l: 100 },
            { x: 306, o: 92, c: 62, h: 52, l: 96, pin: "1", pinTone: "#e5484d", pinPos: "top" },
            { x: 334, o: 62, c: 98, h: 58, l: 106 },
            { x: 362, o: 98, c: 132, h: 94, l: 140 },
            { x: 390, o: 132, c: 162, h: 126, l: 168 },
            { x: 418, o: 162, c: 178, h: 158, l: 184 },
            { x: 446, o: 178, c: 166, h: 160, l: 182 },
            { x: 474, o: 166, c: 186, h: 164, l: 194, pin: "2", pinTone: "#4cc38a", pinPos: "bottom" },
            { x: 502, o: 186, c: 156, h: 150, l: 190 },
            { x: 530, o: 156, c: 134, h: 128, l: 160 },
            { x: 558, o: 134, c: 120, h: 114, l: 140 },
        ],
        flowPath: "M 194 344 L 222 322 L 250 298 L 278 318 L 306 314 L 334 334 L 362 352 L 390 362 L 418 368 L 446 352 L 474 346 L 502 326 L 530 314 L 558 308",
        divergences: [
            {
                id: "div-bear",
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
            { x: 306, y: 314, label: "1", tone: "#e5484d" },
            { x: 474, y: 346, label: "2", tone: "#4cc38a" },
        ],
        ladderBars: [
            { y: 56, label: "Call Wall", price: "132.000", w: 96, color: "#e5484d" },
            { y: 110, label: "MidWall", price: "131.650", w: 56, color: "#848da2" },
            { y: 144, label: "Preço ref.", price: "131.480", w: 38, color: "#38bdf8", isRef: true },
            { y: 192, label: "FlipWall", price: "131.100", w: 68, color: "#d4a259", dashed: true },
            { y: 244, label: "Put Wall", price: "130.500", w: 86, color: "#4cc38a" },
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
            { x: 194, o: 108, c: 118, h: 102, l: 124 },
            { x: 222, o: 118, c: 130, h: 114, l: 138 },
            { x: 250, o: 130, c: 148, h: 126, l: 156 },
            { x: 278, o: 148, c: 174, h: 144, l: 182, pin: "1", pinTone: "#e5484d", pinPos: "top" },
            { x: 306, o: 174, c: 204, h: 170, l: 212 },
            { x: 334, o: 204, c: 226, h: 198, l: 234 },
            { x: 362, o: 226, c: 236, h: 220, l: 242 },
            { x: 390, o: 236, c: 224, h: 218, l: 240 },
            { x: 418, o: 224, c: 244, h: 220, l: 252, pin: "2", pinTone: "#4cc38a", pinPos: "bottom" },
            { x: 446, o: 244, c: 222, h: 216, l: 248 },
            { x: 474, o: 222, c: 204, h: 198, l: 228 },
            { x: 502, o: 204, c: 190, h: 184, l: 210 },
            { x: 530, o: 190, c: 182, h: 176, l: 196 },
            { x: 558, o: 182, c: 186, h: 178, l: 192 },
        ],
        flowPath: "M 194 308 L 222 316 L 250 326 L 278 342 L 306 356 L 334 366 L 362 374 L 390 358 L 418 350 L 446 332 L 474 320 L 502 312 L 530 308 L 558 312",
        divergences: [
            {
                id: "div-putwall",
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
            { x: 278, y: 342, label: "1", tone: "#e5484d" },
            { x: 418, y: 350, label: "2", tone: "#4cc38a" },
        ],
        ladderBars: [
            { y: 56, label: "Call Wall", price: "132.000", w: 74, color: "#e5484d" },
            { y: 106, label: "MidWall", price: "131.500", w: 50, color: "#848da2" },
            { y: 152, label: "FlipWall", price: "131.100", w: 80, color: "#d4a259", dashed: true },
            { y: 192, label: "Preço ref.", price: "130.820", w: 42, color: "#38bdf8", isRef: true },
            { y: 244, label: "Put Wall", price: "130.200", w: 98, color: "#4cc38a" },
        ],
    },
};

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
    const [regimeMode, setRegimeMode] = useState("positive");
    const [activePrint, setActivePrint] = useState(null);
    const [openFaqIdx, setOpenFaqIdx] = useState(0);
    const activeRegime = REGIME_DETAILS[regimeMode];
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
                @media (max-width: 960px) {
                    .mw-portal-hero,
                    .mw-anatomy-grid,
                    .mw-featured-print,
                    .mw-prints-secondary,
                    .mw-layers-grid,
                    .mw-product-grid {
                        grid-template-columns: 1fr;
                        gap: 24px;
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
            `}</style>

            {/* Topbar sólida (56px) */}
            <header
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
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                        <WallsMark />
                        <span style={{ fontSize: 16, fontWeight: 600, color: "#eef0f5", lineHeight: 1 }}>
                            Magic Walls
                        </span>
                        <span style={{ width: 1, height: 14, background: "rgba(238, 240, 245, 0.12)" }} />
                        <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: "#848da2" }}>
                            WIN × WDO · B3
                        </span>
                    </div>

                    <nav className="mw-nav-links" aria-label="Navegação técnica">
                        <a href="#regimes-gex" className="mw-p-nav-link">Regimes GEX</a>
                        <a href="#dias-reais" className="mw-p-nav-link">Dias reais</a>
                        <a href="#como-funciona" className="mw-p-nav-link">Como funciona</a>
                        <a href="#o-que-inclui" className="mw-p-nav-link">O que inclui</a>
                        <a href="#faq" className="mw-p-nav-link">FAQ</a>
                    </nav>

                    <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                        <span
                            data-testid="saas-cloud-status"
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
                            {statusLabel}
                        </span>

                        <a
                            href="https://instagram.com/magicwallsb3"
                            target="_blank"
                            rel="noreferrer noopener"
                            className="mw-p-btn-secondary"
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
                                Alterne o regime de Gamma para ver como o preço reage nas Walls e onde surgem as divergências
                            </p>
                        </div>

                        <div
                            role="tablist"
                            aria-label="Seletor de regime Gamma"
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
                                onClick={() => setRegimeMode("positive")}
                                className="mw-p-tab"
                            >
                                <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#4cc38a" }} />
                                <span>Gamma positivo</span>
                            </button>
                            <button
                                type="button"
                                role="tab"
                                aria-selected={regimeMode === "negative"}
                                onClick={() => setRegimeMode("negative")}
                                className="mw-p-tab"
                            >
                                <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#e5484d" }} />
                                <span>Gamma negativo</span>
                            </button>
                        </div>
                    </div>

                    <div className="mw-anatomy-grid">
                        {/* Diagrama Vetorial Plano */}
                        <div
                            style={{
                                background: "#0e1118",
                                border: "1px solid rgba(238, 240, 245, 0.08)",
                                borderRadius: 8,
                                padding: 16,
                                display: "flex",
                                flexDirection: "column",
                                gap: 12,
                            }}
                        >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                                <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: "#848da2" }}>
                                    Exemplo ilustrativo · WINFUT · M5
                                </span>
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
                                aria-label="Diagrama esquemático de Escada GEX e Divergências no Fluxo Smart Money"
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
                                {activeRegime.ladderBars.map((lvl) => (
                                    <g key={lvl.label}>
                                        <text x="16" y={lvl.y - 6} fill="#848da2" fontSize="10.5" fontFamily={FONT_SANS}>
                                            {lvl.label}
                                        </text>
                                        <text x="150" y={lvl.y - 6} textAnchor="end" fill={lvl.color} fontSize="10.5" fontWeight="500" fontFamily={FONT_MONO}>
                                            {lvl.price}
                                        </text>
                                        <rect x="16" y={lvl.y} width="134" height="4" rx="2" fill="#1b212e" />
                                        <rect x="16" y={lvl.y} width={lvl.w} height="4" rx="2" fill={lvl.color} />

                                        <line
                                            x1="176"
                                            y1={lvl.y}
                                            x2="586"
                                            y2={lvl.y}
                                            stroke={lvl.color}
                                            strokeOpacity={lvl.isRef ? 0.55 : 0.42}
                                            strokeWidth={lvl.isRef ? "1.2" : "1"}
                                            strokeDasharray={lvl.dashed ? "5 4" : lvl.isRef ? "2 3" : "4 4"}
                                        />
                                    </g>
                                ))}

                                {/* Candles + pinos 1 e 2 */}
                                {activeRegime.candles.map((cd, idx) => {
                                    const bullish = cd.c < cd.o;
                                    const topBody = Math.min(cd.o, cd.c);
                                    const bodyH = Math.max(4, Math.abs(cd.c - cd.o));
                                    const fill = bullish ? "#9aa5b6" : "#475266";
                                    const pinY = cd.pinPos === "top" ? cd.h - 14 : cd.l + 15;
                                    return (
                                        <g key={idx}>
                                            <line x1={cd.x} y1={cd.h} x2={cd.x} y2={cd.l} stroke={fill} strokeWidth="1.5" />
                                            <rect x={cd.x - 5} y={topBody} width="10" height={bodyH} rx="1.5" fill={fill} />
                                            {cd.pin && (
                                                <g>
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

                                {/* Linhas de divergência */}
                                {activeRegime.divergences.map((div) => (
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

                                {/* Curva Fluxo Smart Money */}
                                <path d={activeRegime.flowPath} fill="none" stroke="#38bdf8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />

                                {activeRegime.flowPins.map((fp) => (
                                    <g key={fp.label}>
                                        <line x1={fp.x} y1="276" x2={fp.x} y2="388" stroke={fp.tone} strokeOpacity="0.28" strokeDasharray="3 3" />
                                        <circle cx={fp.x} cy={fp.y} r="8" fill="#131720" stroke={fp.tone} strokeWidth="1.5" />
                                        <text x={fp.x} y={fp.y + 3.5} textAnchor="middle" fill={fp.tone} fontSize="10" fontWeight="600" fontFamily={FONT_MONO}>
                                            {fp.label}
                                        </text>
                                    </g>
                                ))}
                            </svg>
                        </div>

                        {/* Leitura Editorial Única (Trilho de assinatura reservado apenas ao regime ativo) */}
                        <div
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
                            }}
                        >
                            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                                <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: activeRegime.accent }}>
                                    {activeRegime.shortLabel}
                                </span>
                            </div>

                            <div style={{ display: "flex", flexDirection: "column", gap: 16, flex: 1 }}>
                                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                                    <div style={{ fontSize: 13, fontWeight: 500, color: "#eef0f5" }}>
                                        01 · Mecânica do regime Gamma
                                    </div>
                                    <p style={{ margin: 0, fontSize: 13, lineHeight: 1.55, color: "#a3a9b8" }}>
                                        {activeRegime.hedgeMechanic}
                                    </p>
                                </div>

                                <div style={{ borderTop: "1px solid rgba(238, 240, 245, 0.08)", paddingTop: 16, display: "flex", flexDirection: "column", gap: 4 }}>
                                    <div style={{ fontSize: 13, fontWeight: 500, color: "#eef0f5" }}>
                                        02 · Comportamento estatístico nas Walls
                                    </div>
                                    <p style={{ margin: 0, fontSize: 13, lineHeight: 1.55, color: "#a3a9b8" }}>
                                        {activeRegime.wallBehavior}
                                    </p>
                                </div>

                                <div style={{ borderTop: "1px solid rgba(238, 240, 245, 0.08)", paddingTop: 16, display: "flex", flexDirection: "column", gap: 4 }}>
                                    <div style={{ fontSize: 13, fontWeight: 500, color: "#eef0f5" }}>
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
                        className="mw-featured-print"
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
