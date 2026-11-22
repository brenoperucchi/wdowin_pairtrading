import { useCallback, useEffect, useState } from "react";
import { API_BASE } from "../apiBase";
import {
    authFetch,
    clearStoredAuth,
    getDeviceFingerprint,
    getStoredAuth,
    setStoredAuth,
} from "../utils/saasAuth";
import ForensicWatermark from "./ForensicWatermark";
import MagicWallsMark from "./MagicWallsMark";
import SaasWelcomePortal from "./SaasWelcomePortal";

const FONT_SANS = "'IBM Plex Sans', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif";
const FONT_MONO = "'IBM Plex Mono', 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace";

export default function SaasAuthGate({ children }) {
    const [authState, setAuthState] = useState(() => getStoredAuth());
    const [checking, setChecking] = useState(() => Boolean(getStoredAuth()?.access_token));
    const [bannerMsg, setBannerMsg] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const [submitting, setSubmitting] = useState(false);

    const [termsChecked, setTermsChecked] = useState(false);
    const [acceptingTerms, setAcceptingTerms] = useState(false);
    const [feedStatus, setFeedStatus] = useState("checking");
    const [cloudReachable, setCloudReachable] = useState(null);

    const forceLogoutWithReason = useCallback((msg) => {
        clearStoredAuth();
        setAuthState(null);
        setChecking(false);
        if (msg) setBannerMsg(msg);
    }, []);

    const verifySession = useCallback(async () => {
        const current = getStoredAuth();
        if (!current?.access_token) {
            setChecking(false);
            return;
        }
        try {
            const res = await authFetch(`${API_BASE}/auth/me`);
            if (res.status === 401 || res.status === 403) {
                const payload = await res.json().catch(() => ({}));
                if (payload?.code === "SESSION_REPLACED") {
                    forceLogoutWithReason("Acesso iniciado em outro dispositivo. Esta sessão foi encerrada.");
                } else if (payload?.code === "ACCOUNT_ABUSE_BLOCKED") {
                    forceLogoutWithReason(payload.detail || "Conta bloqueada por excesso de trocas de dispositivo.");
                } else if (payload?.code === "SUBSCRIPTION_INACTIVE") {
                    forceLogoutWithReason(payload.detail || "Assinatura inativa ou expirada.");
                } else {
                    forceLogoutWithReason("Sessão expirada. Faça login novamente.");
                }
                return;
            }
            if (res.ok) {
                const json = await res.json();
                if (json?.user) {
                    const updated = { ...current, user: json.user };
                    setStoredAuth(updated);
                    setAuthState(updated);
                }
            }
        } catch {
            // falha momentânea de rede não derruba a sessão local já carregada
        } finally {
            setChecking(false);
        }
    }, [forceLogoutWithReason]);

    useEffect(() => {
        verifySession();
    }, [verifySession]);

    // Escuta imediata de eventos 401/403 disparados por qualquer fetch do dashboard
    useEffect(() => {
        const onAuthError = (ev) => {
            const { code, detail } = ev.detail || {};
            if (code === "SESSION_REPLACED") {
                forceLogoutWithReason("Acesso iniciado em outro dispositivo. Esta sessão foi encerrada.");
            } else if (code === "UNAUTHENTICATED") {
                forceLogoutWithReason("Sessão expirada. Faça login novamente.");
            } else if (code === "ACCOUNT_ABUSE_BLOCKED") {
                forceLogoutWithReason(detail || "Conta bloqueada preventivamente por excesso de trocas de dispositivo.");
            } else if (code === "SUBSCRIPTION_INACTIVE") {
                forceLogoutWithReason(detail || "Assinatura inativa ou expirada.");
            } else if (code === "TERMS_NOT_ACCEPTED") {
                setAuthState((prev) => (prev?.user ? { ...prev, user: { ...prev.user, terms_accepted: false } } : prev));
            }
        };
        window.addEventListener("mw-saas-auth-error", onAuthError);
        return () => window.removeEventListener("mw-saas-auth-error", onAuthError);
    }, [forceLogoutWithReason]);

    // Heartbeat de sessão única a cada 2.5s (garante desconexão <= 3s em qualquer aba)
    useEffect(() => {
        if (!authState?.access_token) return undefined;
        const timer = setInterval(() => {
            verifySession();
        }, 2500);
        return () => clearInterval(timer);
    }, [authState?.access_token, verifySession]);

    // Monitor público do feed Cloud (recepção + usuário logado)
    useEffect(() => {
        let cancelled = false;
        const checkFeed = async () => {
            try {
                const r = await fetch(`${API_BASE}/api/v1/feed/status`);
                if (r.ok && !cancelled) {
                    const j = await r.json();
                    setCloudReachable(true);
                    setFeedStatus(j.status || "offline");
                } else if (!cancelled) {
                    setCloudReachable(false);
                    setFeedStatus("offline");
                }
            } catch {
                if (!cancelled) {
                    setCloudReachable(false);
                    setFeedStatus("offline");
                }
            }
        };
        checkFeed();
        const t = setInterval(checkFeed, 10000);
        return () => {
            cancelled = true;
            clearInterval(t);
        };
    }, []);

    const handleLogin = async (e) => {
        e.preventDefault();
        setBannerMsg("");
        setSubmitting(true);
        try {
            const res = await fetch(`${API_BASE}/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    email: email.trim(),
                    password,
                    device_fp: getDeviceFingerprint(),
                }),
            });
            const json = await res.json().catch(() => ({}));
            if (!res.ok || !json.access_token) {
                setBannerMsg(json.detail || "Não foi possível entrar. Verifique e-mail e senha.");
                return;
            }
            const nextAuth = {
                access_token: json.access_token,
                session_id: json.session_id,
                user: json.user,
            };
            setStoredAuth(nextAuth);
            setAuthState(nextAuth);
            setPassword("");
            setBannerMsg("");
        } catch {
            setBannerMsg("Erro de conexão com o servidor SaaS. Tente novamente.");
        } finally {
            setSubmitting(false);
        }
    };

    const handleAcceptTerms = async () => {
        if (!termsChecked || acceptingTerms) return;
        setAcceptingTerms(true);
        try {
            const reqVer = authState?.user?.required_terms_version || "2026.11";
            const res = await authFetch(`${API_BASE}/auth/accept-terms`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ terms_version: reqVer }),
            });
            const json = await res.json().catch(() => ({}));
            if (res.ok && json.user) {
                const updated = { ...authState, user: json.user };
                setStoredAuth(updated);
                setAuthState(updated);
            }
        } finally {
            setAcceptingTerms(false);
        }
    };

    const handleLogout = async () => {
        try {
            await authFetch(`${API_BASE}/auth/logout`, { method: "POST" });
        } catch {
            // ignore
        }
        forceLogoutWithReason("");
    };

    if (checking) {
        return (
            <div style={{ minHeight: "100svh", background: "#0e1118", color: "#a3a9b8", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: FONT_MONO, fontSize: 13 }}>
                Validando sessão Magic Walls...
            </div>
        );
    }

    // 1. Portal Técnico de Boas-Vindas + Autenticação (GEX + Fluxo)
    if (!authState?.access_token || !authState?.user) {
        return (
            <SaasWelcomePortal
                email={email}
                setEmail={setEmail}
                password={password}
                setPassword={setPassword}
                showPassword={showPassword}
                setShowPassword={setShowPassword}
                submitting={submitting}
                bannerMsg={bannerMsg}
                feedStatus={feedStatus}
                cloudReachable={cloudReachable}
                onSubmit={handleLogin}
            />
        );
    }

    // 2. Modal Clickwrap Obrigatório antes de liberar os gráficos
    if (!authState.user.terms_accepted) {
        return (
            <div
                style={{
                    minHeight: "100svh",
                    background: "#0a0c12",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    padding: 24,
                    fontFamily: FONT_SANS,
                    color: "#eef0f5",
                }}
            >
                <div
                    data-testid="saas-terms-modal"
                    style={{
                        width: "100%",
                        maxWidth: 560,
                        background: "#131720",
                        border: "1px solid rgba(238, 240, 245, 0.12)",
                        borderRadius: 12,
                        padding: 24,
                        display: "flex",
                        flexDirection: "column",
                        gap: 16,
                    }}
                >
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                            <MagicWallsMark size={18} variant="small" />
                            <div style={{ fontFamily: FONT_MONO, fontSize: 12, fontWeight: 400, color: "#848da2" }}>
                                Termo de aceite obrigatório · Versão {authState.user.required_terms_version || "2026.11"}
                            </div>
                        </div>
                        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 500, color: "#eef0f5", letterSpacing: "-0.015em" }}>
                            CVM 20, LGPD e licença individual
                        </h2>
                    </div>
                    <div
                        style={{
                            padding: 16,
                            borderRadius: 8,
                            background: "#0e1118",
                            border: "1px solid rgba(238, 240, 245, 0.08)",
                            fontSize: 13,
                            color: "#a3a9b8",
                            lineHeight: 1.6,
                            display: "flex",
                            flexDirection: "column",
                            gap: 12,
                        }}
                    >
                        <div>1. <strong style={{ color: "#eef0f5", fontWeight: 500 }}>Software analítico (CVM 20/2021):</strong> A Magic Walls fornece leituras quantitativas de exposição Gamma (GEX) e fluxo de mercado com caráter estritamente educacional e analítico. Não constitui recomendação de compra ou venda.</div>
                        <div>2. <strong style={{ color: "#eef0f5", fontWeight: 500 }}>Risco de mercado:</strong> Operações com mini-contratos futuros envolvem risco financeiro elevado; desempenhos passados não garantem resultados futuros.</div>
                        <div>3. <strong style={{ color: "#eef0f5", fontWeight: 500 }}>Licença individual e anti-rateio:</strong> O acesso é único por usuário. Novo login desconecta o dispositivo anterior automaticamente; compartilhamento, retransmissão ou excesso de trocas de dispositivo/IP no pregão gera bloqueio preventivo com identificação por marca d&apos;água forense.</div>
                    </div>

                    <label style={{ display: "flex", alignItems: "flex-start", gap: 12, fontSize: 13, lineHeight: 1.5, color: "#eef0f5", cursor: "pointer" }}>
                        <input
                            data-testid="saas-terms-checkbox"
                            type="checkbox"
                            checked={termsChecked}
                            onChange={(e) => setTermsChecked(e.target.checked)}
                            style={{ marginTop: 3 }}
                        />
                        <span>Li e aceito integralmente os termos de software analítico, ciência de risco, LGPD e licença individual.</span>
                    </label>

                    <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                        <button
                            onClick={handleLogout}
                            className="mw-btn mw-btn-secondary"
                            style={{ height: 40, padding: "0 16px" }}
                        >
                            Sair
                        </button>
                        <button
                            data-testid="saas-terms-accept-btn"
                            disabled={!termsChecked || acceptingTerms}
                            onClick={handleAcceptTerms}
                            style={{
                                flex: 1,
                                height: 40,
                                padding: "0 16px",
                                borderRadius: 8,
                                border: termsChecked ? "1px solid #38bdf8" : "1px solid rgba(238, 240, 245, 0.1)",
                                background: termsChecked ? "#38bdf8" : "#1b212e",
                                color: termsChecked ? "#070a10" : "#848da2",
                                fontSize: 13,
                                fontWeight: 500,
                                cursor: termsChecked ? "pointer" : "not-allowed",
                                boxShadow: termsChecked ? "inset 0 1px 0 rgba(255, 255, 255, 0.22)" : "none",
                            }}
                        >
                            {acceptingTerms ? "Registrando aceite..." : "Aceitar e acessar terminal"}
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    // 3. Usuário autenticado + Termos aceitos: Terminal + Watermark Forense
    const feedLabel = feedStatus === "live" ? "Ao vivo" : feedStatus === "stale" ? "Atrasado" : "Offline";
    const feedColor = feedStatus === "live" ? "#4cc38a" : feedStatus === "stale" ? "#d4a259" : "#e5484d";

    return (
        <>
            <div
                data-testid="saas-session-bar"
                style={{
                    background: "#0a0c12",
                    borderBottom: "1px solid rgba(238, 240, 245, 0.08)",
                    padding: "0 24px",
                    minHeight: 32,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 12,
                    fontSize: 12,
                    fontFamily: FONT_MONO,
                    color: "#a3a9b8",
                }}
            >
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <MagicWallsMark size={16} variant="small" />
                    <span style={{ color: "#eef0f5", fontWeight: 500 }}>Magic Walls SaaS</span>
                    <span style={{ color: "#848da2" }}>{authState.user.email}</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "#a3a9b8", fontWeight: 400 }}>
                        <span style={{ width: 6, height: 6, borderRadius: "50%", background: feedColor }} />
                        Feed {feedLabel}
                    </span>
                    <button
                        data-testid="saas-logout-btn"
                        onClick={handleLogout}
                        className="mw-btn mw-btn-secondary"
                        style={{ height: 24, padding: "0 8px", fontSize: 11, fontFamily: FONT_MONO, borderRadius: 6 }}
                    >
                        Sair
                    </button>
                </div>
            </div>
            {children}
            <ForensicWatermark label={authState.user.watermark_label} />
        </>
    );
}
