// Tema claro/escuro do sistema inteiro (painel, Marketing e Logins). Uma chave só, aplicada na raiz do documento.
export const THEME_KEY = "mw_theme";
const LEGACY_KEY = "mw_marketing_theme"; // antes só o Marketing tinha tema

export function normalizeTheme(value) {
    return value === "light" ? "light" : "dark";
}

export function nextTheme(theme) {
    return normalizeTheme(theme) === "dark" ? "light" : "dark";
}

let current = null;

export function readTheme() {
    if (current) return current;
    try {
        current = normalizeTheme(localStorage.getItem(THEME_KEY) || localStorage.getItem(LEGACY_KEY));
    } catch {
        current = "dark"; // sem armazenamento: vale só nesta visita
    }
    return current;
}

export function applyTheme(theme) {
    current = normalizeTheme(theme);
    if (typeof document === "undefined") return current;
    document.documentElement.setAttribute("data-mw-theme", current);
    document.documentElement.style.colorScheme = current;
    return current;
}

export function setTheme(theme) {
    const t = applyTheme(theme);
    try {
        localStorage.setItem(THEME_KEY, t);
    } catch {
        /* sem armazenamento */
    }
    if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent("mw-theme-changed", { detail: { theme: t } }));
    return t;
}

export function toggleTheme() {
    return setTheme(nextTheme(readTheme()));
}
