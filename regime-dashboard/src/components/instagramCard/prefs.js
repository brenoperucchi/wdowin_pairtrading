// Preferências do card Instagram: valores padrão e persistência em localStorage (movido de InstagramCardModal.jsx).

// Padrões usados pelo modal. Atenção ao operador de cada chave no consumo: formatMode, rulerMode e handle usam `||`
// (string vazia cai no padrão); showFlow, showGauss, showWalls, showMidWalls, showDivLines e brandTitle usam `??`.
export const DEFAULT_CARD_PREFS = {
    formatMode: "FEED",
    showFlow: true,
    showGauss: false,
    showWalls: true,
    showMidWalls: true,
    showDivLines: false,
    rulerMode: "BEST",
    brandTitle: "Magic Walls",
    handle: "@magicwallsb3",
};

export const STORAGE_KEY = "mw_instagram_card_prefs_v2";
export const LEGACY_STORAGE_KEY = "mw_instagram_card_prefs_v1";

export function loadPrefs() {
    try {
        const raw = window.localStorage.getItem(STORAGE_KEY);
        if (raw) {
            const parsed = JSON.parse(raw) || {};
            if (parsed.brandTitle === "MAGIC WALLS") parsed.brandTitle = "Magic Walls";
            if (!parsed.handle || parsed.handle === "@magicwalls") parsed.handle = "@magicwallsb3";
            return parsed;
        }
        const legacyRaw = window.localStorage.getItem(LEGACY_STORAGE_KEY);
        if (legacyRaw) {
            const legacy = JSON.parse(legacyRaw) || {};
            return {
                brandTitle: legacy.brandTitle === "MAGIC WALLS" ? "Magic Walls" : legacy.brandTitle,
                handle: legacy.handle === "@magicwalls" ? "@magicwallsb3" : legacy.handle,
            };
        }
        return {};
    } catch {
        return {};
    }
}

export function savePrefs(next) {
    try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
        // storage unavailable
    }
}
