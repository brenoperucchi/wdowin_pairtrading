// Páginas da área administrativa e quem pode vê-las. Função pura: a regra de acesso fica testável.
// A regra espelha o servidor (plano "admin"); o servidor continua sendo quem impõe o acesso de verdade.
//
// PARA ACRESCENTAR UMA TELA DE ADMINISTRAÇÃO:
//   1. uma linha aqui (key, label, mode = valor de ?mode= na URL);
//   2. o componente da tela em ADMIN_SCREENS, em src/admin/adminScreens.jsx.
// A barra do topo (a mesma nas telas todas) e o roteamento do main.jsx saem desta lista; nada mais muda.

export const ADMIN_PAGES = [
    { key: "charts", label: "Gráficos", mode: "" },
    { key: "marketing", label: "Marketing", mode: "marketing" },
    { key: "logins", label: "Logins", mode: "admin" },
];

export function isAdminUser(user) {
    return String(user?.plan || "").trim().toLowerCase() === "admin";
}

/** Páginas visíveis: usuário comum não vê nenhuma (só os gráficos, sem barra). */
export function visibleAdminPages({ saasEnabled, user }) {
    return saasEnabled && isAdminUser(user) ? ADMIN_PAGES : [];
}

export function pageForMode(mode) {
    return ADMIN_PAGES.find((p) => p.mode && p.mode === mode) || null;
}

export function pageKeyFromSearch(search) {
    const mode = new URLSearchParams(search || "").get("mode") || "";
    return ADMIN_PAGES.find((p) => p.mode === mode)?.key || "charts";
}

/** Endereço de uma página, mantendo o caminho atual e descartando os demais parâmetros. */
export function hrefForPage(page, pathname = "/") {
    return page.mode ? `${pathname}?mode=${page.mode}` : pathname;
}
