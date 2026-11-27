// Tema e constantes do card Instagram Magic Walls (movido de InstagramCardModal.jsx sem alterações de valor).

export const FONT_SANS = "'IBM Plex Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
export const FONT_MONO = "'IBM Plex Mono', ui-monospace, SFMono-Regular, Consolas, monospace";

// Paleta Oficial Magic Walls (Ink Azul)
export const INK = {
    chrome: "#0a0c12",
    bg: "#0e1118",
    card: "#131720",
    stopCard: "#191318",
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

// Dimensões de cada formato, em pixels. Feed 4:5, Stories 9:16 e os dois slides do carrossel (4:5).
// "CAROUSEL" é a chave do formatMode do modal (cada slide tem a dimensão de CAROUSEL_1/CAROUSEL_2).
export const CARD_DIMENSIONS = {
    FEED: { width: 1080, height: 1350 },
    STORIES: { width: 1080, height: 1920 },
    CAROUSEL: { width: 1080, height: 1350 },
    CAROUSEL_1: { width: 1080, height: 1350 },
    CAROUSEL_2: { width: 1080, height: 1350 },
};

/** Dimensão da variante do SVG (variante desconhecida cai em 1080x1350, como antes). */
export function getCardDimensions(variant) {
    return variant === "STORIES" ? CARD_DIMENSIONS.STORIES : CARD_DIMENSIONS.FEED;
}
