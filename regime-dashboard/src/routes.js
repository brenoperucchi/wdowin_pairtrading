// Rotas do app. A URL é o estado da página: cada tela tem um caminho próprio (hierarquia de recursos, em inglês).
// Query string só para filtro, ordenação, paginação ou aba (?tab=). Sem alias nem redirecionamento: um caminho, uma tela.
//
// Prefixo de implantação: vem do `base` do build (Vite). Hoje o app mora na raiz ("/"); se um dia morar em
// "/algo/", muda só o `base` do build e todos os caminhos daqui e dos links acompanham.

export const ROUTE_PATHS = {
    charts: "/",
    manual: "/manual",
    morningVideo: "/morning-video",
    admin: "/admin",
    adminMarketing: "/admin/marketing",
    adminUsers: "/admin/users",
};

// Prefixo do painel público por túnel (scripts/painel_publico.py), que serve o app sob /magicwall.
const TUNNEL_PREFIX = "/magicwall";

/** Prefixo de implantação sem barra final: "" na raiz, "/algo" sob /algo/. Build com base relativa ("./") conta como raiz. */
export function appBasePath(baseUrl = import.meta.env?.BASE_URL) {
    const base = String(baseUrl ?? "/");
    if (!base.startsWith("/")) return "";
    return base.replace(/\/+$/, "");
}

/** Caminho da rota, sem o prefixo de implantação nem o do túnel. Sempre começa com "/" e não termina com "/". */
export function routePathFromPathname(pathname, base = appBasePath()) {
    let p = String(pathname || "/");
    if (base && (p === base || p.startsWith(`${base}/`))) p = p.slice(base.length);
    if (p === TUNNEL_PREFIX || p.startsWith(`${TUNNEL_PREFIX}/`)) p = p.slice(TUNNEL_PREFIX.length);
    if (p === "/index.html") p = "/";
    p = p.replace(/\/+$/, "");
    return p || "/";
}

/** Chave da rota ("charts", "adminMarketing"...) ou "notFound". */
export function routeKeyFromPathname(pathname, base = appBasePath()) {
    const p = routePathFromPathname(pathname, base);
    return Object.keys(ROUTE_PATHS).find((k) => ROUTE_PATHS[k] === p) || "notFound";
}

/** Endereço de uma rota, já com o prefixo de implantação. `params`: só filtros e abas (valor vazio é omitido). */
export function hrefForRoute(key, params = {}, base = appBasePath()) {
    const path = ROUTE_PATHS[key];
    if (path === undefined) throw new Error(`unknown route: ${key}`);
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== "") qs.set(k, String(v));
    const s = qs.toString();
    return `${base}${path === "/" && base ? "/" : path}${s ? `?${s}` : ""}`;
}
