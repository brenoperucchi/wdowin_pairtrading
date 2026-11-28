// Páginas da área administrativa e quem pode vê-las. Função pura: a regra de acesso fica testável.
// A regra espelha o servidor (plano "admin"); o servidor continua sendo quem impõe o acesso de verdade.
//
// PARA ACRESCENTAR UMA TELA DE ADMINISTRAÇÃO:
//   1. a rota em src/routes.js (ROUTE_PATHS), sempre em inglês e sob /admin (ex.: adminReports: "/admin/reports");
//   2. uma linha aqui (key, label visível, route = chave da rota);
//   3. o componente da tela em ADMIN_SCREENS, em src/admin/adminScreens.jsx.
// A barra do topo, o índice de /admin e o roteamento do main.jsx saem desta lista; nada mais muda.

import { hrefForRoute, routeKeyFromPathname } from "../routes.js";

export const ADMIN_PAGES = [
    { key: "charts", label: "Gráficos", route: "charts" },
    { key: "marketing", label: "Marketing", route: "adminMarketing" },
    { key: "users", label: "Logins", route: "adminUsers" },
];

export function isAdminUser(user) {
    return String(user?.plan || "").trim().toLowerCase() === "admin";
}

/** Páginas visíveis: usuário comum não vê nenhuma (só os gráficos, sem barra). */
export function visibleAdminPages({ saasEnabled, user }) {
    return saasEnabled && isAdminUser(user) ? ADMIN_PAGES : [];
}

/** Página do registro que corresponde ao caminho atual, ou null (ex.: /admin, /manual, caminho desconhecido). */
export function pageForPathname(pathname) {
    const route = routeKeyFromPathname(pathname);
    return ADMIN_PAGES.find((p) => p.route === route) || null;
}

/** Chave da página atual para destacar na barra; "" quando a tela não é uma página da barra. */
export function pageKeyFromPathname(pathname) {
    return pageForPathname(pathname)?.key || "";
}

/** Endereço de uma página: o caminho dela, sem parâmetros. */
export function hrefForPage(page) {
    return hrefForRoute(page.route);
}
