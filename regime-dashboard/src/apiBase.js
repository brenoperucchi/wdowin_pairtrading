import { getStoredAuth, isSaasAuthEnabled } from "./utils/saasAuth";

// Endereço do backend (server.py). Local: http://localhost:8080 (padrão).
// Versão pública (link do túnel): build com VITE_API_BASE="" → caminhos relativos (/api/... ou /magicwall/api/...),
// servidos pelo intermediário somente-leitura (scripts/painel_publico.py).
function resolveApiBase() {
    if (typeof window !== "undefined") {
        const params = new URLSearchParams(window.location.search || "");
        const apiOverride = (params.get("api") || "").trim().replace(/\/+$/, "");
        if (apiOverride && (apiOverride.startsWith("http://") || apiOverride.startsWith("https://") || apiOverride.startsWith("/"))) {
            return apiOverride;
        }
    }
    if (import.meta.env.VITE_API_BASE === undefined) return "http://localhost:8080";
    const envBase = String(import.meta.env.VITE_API_BASE || "").replace(/\/+$/, "");
    if (!envBase && typeof window !== "undefined") {
        const p = window.location.pathname || "/";
        if (p === "/magicwall" || p.startsWith("/magicwall/")) {
            return "/magicwall";
        }
    }
    return envBase;
}

export const API_BASE = resolveApiBase();

// Dados do painel (etapa1, datas e motor). Em produção é a mesma API; em teste local, VITE_COMPASS_BASE
// aponta para o servidor de dados congelados (porta 8096) quando a API local não tem pregões.
export const COMPASS_BASE = import.meta.env.VITE_COMPASS_BASE ?? API_BASE;

// Versão pública do painel 5176: força o modo Walls & Fluxo (no local ele é detectado pela porta 5176).
export const FORCE_WALLS_FLOW = import.meta.env.VITE_FORCE_WALLS_FLOW === "1";

// Versão focada em operação manual (porta 5178, ?mode=manual ou VITE_MANUAL_ONLY=1):
// exibe apenas o gráfico diário WIN/WDO com Walls, Canal Gauss e Fluxo, sem marcações de trades ou históricos.
export const MANUAL_ONLY = import.meta.env.VITE_MANUAL_ONLY === "1";

export function isManualChartMode() {
    if (MANUAL_ONLY) return true;
    if (isSaasAuthEnabled()) {
        const plan = String(getStoredAuth()?.user?.plan || "").toLowerCase();
        if (plan === "core" || plan === "trial") return true;
    }
    if (typeof window === "undefined") return false;
    const port = String(window.location.port || "");
    const params = new URLSearchParams(window.location.search || "");
    if (params.get("mode") === "manual") return true;
    if (params.get("mode") === "walls_flow" || params.get("mode") === "mt5") return false;
    return port === "5178";
}

export function isWallsFlowMode() {
    if (FORCE_WALLS_FLOW) return true;
    if (typeof window === "undefined") return false;
    const port = String(window.location.port || "");
    const params = new URLSearchParams(window.location.search || "");
    if (params.get("mode") === "walls_flow") return true;
    if (params.get("mode") === "mt5" || params.get("mode") === "manual") return false;
    return port === "5176";
}
