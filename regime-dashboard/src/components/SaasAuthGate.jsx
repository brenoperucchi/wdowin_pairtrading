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
    const [trialConfig, setTrialConfig] = useState({
        mode: "open",
        trial_days: 15,
        accepting_trials: true,
        max_active: 50,
        active_trials: 0,
        slots_remaining: null,
        require_invite_code: false,
        turnstile_site_key: "",
        terms_version: "2026.11",
    });
    const [expiredTrialInfo, setExpiredTrialInfo] = useState(null);

    const forceLogoutWithReason = useCallback((msg) => {
        clearStoredAuth();
        setAuthState(null);
        setChecking(false);
        if (msg) setBannerMsg(msg);
    }, []);

    const fetchTrialConfig = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/api/v1/public/trial-config`);
            if (res.ok) {
                const json = await res.json().catch(() => null);
                if (json && json.ok) {
                    setTrialConfig(json);
                }
            }
        } catch {
            // fallback silencioso mantém defaults seguros
        }
    }, []);

    useEffect(() => {
        if (!authState?.access_token) {
            fetchTrialConfig();
        }
    }, [authState?.access_token, fetchTrialConfig]);

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
                if (payload?.code === "TRIAL_EXPIRED") {
                    setExpiredTrialInfo({
                        email: current?.user?.email || "",
                        token: current?.access_token || "",
                        submitted: false,
                        submitting: false,
                        msg: "",
                    });
                    forceLogoutWithReason("");
                    return;
                }
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
            if (code === "TRIAL_EXPIRED") {
                const current = getStoredAuth();
                setExpiredTrialInfo({
                    email: current?.user?.email || "",
                    token: current?.access_token || "",
                    submitted: false,
                    submitting: false,
                    msg: "",
                });
                forceLogoutWithReason("");
            } else if (code === "SESSION_REPLACED") {
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

    // Heartbeat de sessão única a cada 2.5s (reduzido para 15s em aba oculta; garante desconexão imediata ao voltar)
    useEffect(() => {
        if (!authState?.access_token) return undefined;
        let lastHiddenCheck = 0;
        const timer = setInterval(() => {
            if (typeof document !== "undefined" && document.hidden) {
                const now = Date.now();
                if (now - lastHiddenCheck < 15000) return;
                lastHiddenCheck = now;
            }
            verifySession();
        }, 2500);
        const onVis = () => {
            if (typeof document !== "undefined" && !document.hidden) verifySession();
        };
        if (typeof document !== "undefined") {
            document.addEventListener("visibilitychange", onVis);
        }
        return () => {
            clearInterval(timer);
            if (typeof document !== "undefined") {
                document.removeEventListener("visibilitychange", onVis);
            }
        };
    }, [authState?.access_token, verifySession]);

    // Monitor público do feed Cloud (recepção + usuário logado; pausa em aba oculta)
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
        const t = setInterval(() => {
            if (typeof document === "undefined" || !document.hidden) checkFeed();
        }, 10000);
        const onVis = () => {
            if (typeof document !== "undefined" && !document.hidden) checkFeed();
        };
        if (typeof document !== "undefined") {
            document.addEventListener("visibilitychange", onVis);
        }
        return () => {
            cancelled = true;
            clearInterval(t);
            if (typeof document !== "undefined") {
                document.removeEventListener("visibilitychange", onVis);
            }
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
                if (json?.code === "TRIAL_EXPIRED") {
                    setExpiredTrialInfo({
                        email: email.trim(),
                        token: "",
                        submitted: false,
                        submitting: false,
                        msg: "",
                    });
                    setBannerMsg("");
                    return;
                }
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
            setExpiredTrialInfo(null);
            setPassword("");
            setBannerMsg("");
        } catch {
            setBannerMsg("Erro de conexão com o servidor SaaS. Tente novamente.");
        } finally {
            setSubmitting(false);
        }
    };

    const handleTrialRegister = async (formData) => {
        try {
            const res = await fetch(`${API_BASE}/auth/trial/register`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    ...formData,
                    terms_version: trialConfig?.terms_version || "2026.11",
                    device_fp: getDeviceFingerprint(),
                }),
            });
            const json = await res.json().catch(() => ({}));
            if (!res.ok || !json.access_token) {
                if (json?.code === "TRIAL_CAPACITY_REACHED" || json?.code === "TRIAL_PAUSED") {
                    setTrialConfig((prev) => ({ ...prev, accepting_trials: false, slots_remaining: 0 }));
                }
                return {
                    ok: false,
                    code: json?.code || "TRIAL_ERROR",
                    detail: json?.detail || "Não foi possível ativar o teste agora.",
                };
            }
            const nextAuth = {
                access_token: json.access_token,
                session_id: json.session_id,
                user: json.user,
            };
            setStoredAuth(nextAuth);
            setAuthState(nextAuth);
            setExpiredTrialInfo(null);
            setBannerMsg("");
            return { ok: true };
        } catch {
            return {
                ok: false,
                code: "NETWORK_ERROR",
                detail: "Erro de conexão com o servidor SaaS. Tente novamente.",
            };
        }
    };

    const handleWaitlistSubmit = async (formData) => {
        try {
            const res = await fetch(`${API_BASE}/api/v1/public/waitlist`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(formData),
            });
            const json = await res.json().catch(() => ({}));
            if (!res.ok || !json.ok) {
                return {
                    ok: false,
                    code: json?.code || "WAITLIST_ERROR",
                    detail: json?.detail || "Não foi possível registrar na lista de espera.",
                };
            }
            return { ok: true };
        } catch {
            return {
                ok: false,
                code: "NETWORK_ERROR",
                detail: "Erro de conexão com o servidor SaaS. Tente novamente.",
            };
        }
    };

    const handleConversionIntent = async () => {
        if (!expiredTrialInfo || expiredTrialInfo.submitting || expiredTrialInfo.submitted) return;
        setExpiredTrialInfo((prev) => (prev ? { ...prev, submitting: true, msg: "" } : prev));
        try {
            const headers = { "Content-Type": "application/json" };
            if (expiredTrialInfo.token) {
                headers.Authorization = `Bearer ${expiredTrialInfo.token}`;
            }
            const res = await fetch(`${API_BASE}/auth/trial/conversion-intent`, {
                method: "POST",
                headers,
                body: JSON.stringify({
                    email: expiredTrialInfo.email || "",
                    note: "Solicitação após encerramento do trial de 15 dias",
                }),
            });
            const json = await res.json().catch(() => ({}));
            if (res.ok && json.ok) {
                setExpiredTrialInfo((prev) =>
                    prev
                        ? {
                              ...prev,
                              submitting: false,
                              submitted: true,
                              msg: json.message || "Interesse registrado. Nossa equipe avisará no WhatsApp e e-mail.",
                          }
                        : prev
                );
            } else {
                setExpiredTrialInfo((prev) =>
                    prev
                        ? {
                              ...prev,
                              submitting: false,
                              msg: json.detail || "Não foi possível registrar agora. Fale em @magicwallsb3.",
                          }
                        : prev
                );
            }
        } catch {
            setExpiredTrialInfo((prev) =>
                prev ? { ...prev, submitting: false, msg: "Erro de conexão. Tente novamente ou fale em @magicwallsb3." } : prev
            );
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

    // 1. Tela dedicada quando o período de teste de 15 dias terminou
    if (!authState?.access_token && expiredTrialInfo) {
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
                    data-testid="saas-trial-expired-view"
                    style={{
                        width: "100%",
                        maxWidth: 520,
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
                            <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: "#d4a259" }}>
                                Período de teste encerrado · 15 dias
                            </span>
                        </div>
                        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 500, color: "#eef0f5", letterSpacing: "-0.015em" }}>
                            Seu acesso experimental foi concluído
                        </h2>
                        {expiredTrialInfo.email && (
                            <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: "#848da2" }}>
                                {expiredTrialInfo.email}
                            </span>
                        )}
                    </div>

                    <div
                        style={{
                            padding: 16,
                            borderRadius: 8,
                            background: "#0e1118",
                            border: "1px solid rgba(238, 240, 245, 0.08)",
                            fontSize: 13.5,
                            color: "#a3a9b8",
                            lineHeight: 1.6,
                        }}
                    >
                        Os 15 dias de teste do terminal Magic Walls para WIN e WDO terminaram. Assim que o checkout oficial abrir, você poderá manter esta mesma conta com seu e-mail e senha atuais.
                    </div>

                    {expiredTrialInfo.msg && (
                        <div
                            data-testid="saas-trial-intent-msg"
                            style={{
                                padding: "10px 12px",
                                borderRadius: 8,
                                background: expiredTrialInfo.submitted ? "#10231b" : "#261316",
                                border: expiredTrialInfo.submitted
                                    ? "1px solid rgba(76, 195, 138, 0.36)"
                                    : "1px solid rgba(229, 72, 77, 0.36)",
                                color: expiredTrialInfo.submitted ? "#4cc38a" : "#fca5a5",
                                fontSize: 13,
                                lineHeight: 1.45,
                            }}
                        >
                            {expiredTrialInfo.msg}
                        </div>
                    )}

                    <button
                        type="button"
                        data-testid="saas-trial-intent-btn"
                        disabled={expiredTrialInfo.submitting || expiredTrialInfo.submitted}
                        onClick={handleConversionIntent}
                        style={{
                            height: 42,
                            padding: "0 16px",
                            borderRadius: 8,
                            border: "1px solid #38bdf8",
                            background: expiredTrialInfo.submitted ? "#1b212e" : "#38bdf8",
                            color: expiredTrialInfo.submitted ? "#7dd3fc" : "#070a10",
                            fontSize: 14,
                            fontWeight: 500,
                            cursor: expiredTrialInfo.submitting || expiredTrialInfo.submitted ? "default" : "pointer",
                            boxShadow: expiredTrialInfo.submitted ? "none" : "inset 0 1px 0 rgba(255, 255, 255, 0.22)",
                        }}
                    >
                        {expiredTrialInfo.submitted
                            ? "Interesse registrado"
                            : expiredTrialInfo.submitting
                              ? "Registrando interesse..."
                              : "Quero ser avisado quando abrir o pagamento"}
                    </button>

                    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                        <a
                            href="https://instagram.com/magicwallsb3"
                            target="_blank"
                            rel="noreferrer noopener"
                            className="mw-btn mw-btn-secondary"
                            style={{ height: 36, padding: "0 14px", textDecoration: "none", display: "inline-flex", alignItems: "center", fontSize: 13 }}
                        >
                            Falar no @magicwallsb3
                        </a>
                        <button
                            type="button"
                            onClick={() => setExpiredTrialInfo(null)}
                            className="mw-btn mw-btn-secondary"
                            style={{ height: 36, padding: "0 14px", fontSize: 13 }}
                        >
                            Voltar ao login
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    // 2. Portal Técnico de Boas-Vindas + Autenticação + Trial 15 dias (GEX + Fluxo)
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
                trialConfig={trialConfig}
                onTrialRegister={handleTrialRegister}
                onWaitlistSubmit={handleWaitlistSubmit}
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
    const isTrialUser = Boolean(authState.user.is_trial || String(authState.user.plan || "").toLowerCase() === "trial");
    const trialDaysLeft = authState.user.trial_days_left;
    const isTrialUrgent = typeof trialDaysLeft === "number" && trialDaysLeft <= 3;
    const trialBadgeText =
        trialDaysLeft === 0
            ? "Trial · último dia"
            : trialDaysLeft === 1
              ? "Trial · 1 dia restante"
              : typeof trialDaysLeft === "number"
                ? `Trial · ${trialDaysLeft} dias restantes`
                : "Trial · 15 dias";

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
                    {isTrialUser && (
                        <span
                            data-testid="saas-trial-badge"
                            style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 6,
                                padding: "1px 8px",
                                borderRadius: 4,
                                background: isTrialUrgent ? "#211d17" : "#1b212e",
                                border: isTrialUrgent
                                    ? "1px solid rgba(212, 162, 89, 0.3)"
                                    : "1px solid rgba(125, 211, 252, 0.22)",
                                color: isTrialUrgent ? "#d4a259" : "#7dd3fc",
                                fontSize: 11,
                                fontVariantNumeric: "tabular-nums",
                            }}
                        >
                            <span>{trialBadgeText}</span>
                            {isTrialUrgent && (
                                <a
                                    href="https://instagram.com/magicwallsb3"
                                    target="_blank"
                                    rel="noreferrer noopener"
                                    style={{ color: "#eef0f5", textDecoration: "underline", marginLeft: 4 }}
                                >
                                    Garantir vaga
                                </a>
                            )}
                        </span>
                    )}
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
