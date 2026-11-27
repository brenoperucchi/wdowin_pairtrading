import { API_BASE } from "../apiBase";
import { authFetch } from "../utils/saasAuth";

// Cliente fino das rotas administrativas (/api/v1/admin). O servidor decide quem pode: aqui vai o login do admin.
export async function adminCall(path, options = {}) {
    const headers = { ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) };
    const res = await authFetch(`${API_BASE}/api/v1/admin${path}`, { ...options, headers });
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
