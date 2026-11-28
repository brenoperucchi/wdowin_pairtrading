import { API_BASE } from "../apiBase";
import { authFetch } from "../utils/saasAuth";

// Cliente fino da API administrativa de Marketing (/api/v1/admin/marketing). O servidor impõe as regras.
export const API = `${API_BASE}/api/v1/admin/marketing`;

export async function call(path, options = {}) {
    const res = await authFetch(`${API}${path}`, options);
    let body = null;
    try {
        body = await res.json();
    } catch {
        body = null;
    }
    if (!res.ok || (body && body.ok === false)) {
        const detail = (body && (body.detail || body.code)) || `HTTP ${res.status}`;
        throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return body;
}

export const STATUS_LABEL = {
    draft: "Rascunho",
    approved: "Aprovado",
    publishing: "Publicando",
    published: "Publicado",
    failed: "Falhou",
    rejected: "Rejeitado",
};

export const STATUS_COLOR = {
    draft: "var(--mw-flip)",
    approved: "var(--mw-accent-ink)",
    publishing: "var(--mw-flip)",
    published: "var(--mw-pos)",
    failed: "var(--mw-neg)",
    rejected: "var(--mw-text-3)",
};

export { stepOfPost, findStudioPost, findPublishedPost, isOpenPost, countOpenPosts, openPostBadgeText } from "./postState";
