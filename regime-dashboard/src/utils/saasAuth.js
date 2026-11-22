// Gerenciamento de sessão SaaS, fingerprint de dispositivo e wrapper authFetch().
// Quando VITE_SAAS_AUTH !== "1" e ?saas !== "1", o modo local permanece 100% intacto.

const AUTH_STORAGE_KEY = "mw_saas_auth_v1";
const FP_STORAGE_KEY = "mw_device_fp_v1";

export function isSaasAuthEnabled() {
    if (import.meta.env.VITE_SAAS_AUTH === "1") return true;
    if (typeof window === "undefined") return false;
    try {
        const params = new URLSearchParams(window.location.search || "");
        return params.get("saas") === "1";
    } catch {
        return false;
    }
}

export function getDeviceFingerprint() {
    if (typeof window === "undefined") return "ssr";
    try {
        const existing = window.localStorage.getItem(FP_STORAGE_KEY);
        if (existing) return existing;
        const nav = window.navigator || {};
        const scr = window.screen || {};
        const raw = `${nav.platform || "win"}|${scr.width || 0}x${scr.height || 0}|${Intl.DateTimeFormat().resolvedOptions().timeZone || "utc"}|${Math.random().toString(36).slice(2, 10)}`;
        let hash = 0;
        for (let i = 0; i < raw.length; i++) {
            hash = ((hash << 5) - hash + raw.charCodeAt(i)) | 0;
        }
        const fp = `mwfp_${Math.abs(hash).toString(36)}_${Date.now().toString(36).slice(-4)}`;
        window.localStorage.setItem(FP_STORAGE_KEY, fp);
        return fp;
    } catch {
        return "mwfp_fallback";
    }
}

export function getStoredAuth() {
    if (typeof window === "undefined") return null;
    try {
        const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        if (!parsed || !parsed.access_token) return null;
        return parsed;
    } catch {
        return null;
    }
}

export function setStoredAuth(authObj) {
    if (typeof window === "undefined") return;
    try {
        window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(authObj));
        window.dispatchEvent(new CustomEvent("mw-saas-auth-updated", { detail: authObj || null }));
    } catch {
        // storage unavailable
    }
}

export function clearStoredAuth() {
    if (typeof window === "undefined") return;
    try {
        window.localStorage.removeItem(AUTH_STORAGE_KEY);
        window.dispatchEvent(new CustomEvent("mw-saas-auth-updated", { detail: null }));
    } catch {
        // ignore
    }
}

export function canAccessMediaStudio(userOverride = null) {
    if (!isSaasAuthEnabled()) return true;
    const user = userOverride || getStoredAuth()?.user;
    return String(user?.plan || "").trim().toLowerCase() === "admin";
}

export async function authFetch(url, options = {}) {
    if (!isSaasAuthEnabled()) {
        return fetch(url, options);
    }

    const auth = getStoredAuth();
    const headers = new Headers(options.headers || {});
    if (auth?.access_token && !headers.has("Authorization")) {
        headers.set("Authorization", `Bearer ${auth.access_token}`);
    }
    headers.set("X-Device-FP", getDeviceFingerprint());

    const res = await fetch(url, { ...options, headers });
    if ((res.status === 401 || res.status === 403) && typeof window !== "undefined") {
        try {
            const payload = await res.clone().json();
            if (payload && payload.code) {
                window.dispatchEvent(
                    new CustomEvent("mw-saas-auth-error", {
                        detail: {
                            status: res.status,
                            code: payload.code,
                            detail: payload.detail || "",
                        },
                    })
                );
            }
        } catch {
            // non-json error body
        }
    }
    return res;
}
