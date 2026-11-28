import { useCallback, useEffect, useState } from "react";
import { adminCall } from "./adminApi";
import { getStoredAuth } from "../utils/saasAuth";

// Administração de logins (somente plano admin). Abre em ?mode=admin.
// Consulta usuários, trials e convites; ações: estender trial, derrubar sessão, desbloquear e criar convite.
// Criar usuário com senha e mudar plano continuam fora daqui (só pela chave administrativa).

const card = { background: "var(--mw-card)", border: "1px solid var(--mw-hairline)", borderRadius: 10, padding: 14 };
const th = { textAlign: "left", fontSize: 12, color: "var(--mw-text-3)", fontWeight: 600, padding: "6px 8px", whiteSpace: "nowrap" };
const td = { padding: "7px 8px", fontSize: 13, borderTop: "1px solid var(--mw-hairline)", verticalAlign: "middle" };
const input = { height: 32, padding: "0 8px", borderRadius: 6, border: "1px solid var(--mw-hairline-strong)", background: "var(--mw-bg)", color: "var(--mw-text-1)", fontSize: 13 };

const STATUS = {
    active: { label: "Ativo", color: "var(--mw-pos)" },
    blocked: { label: "Bloqueado", color: "var(--mw-neg)" },
    suspended: { label: "Suspenso", color: "var(--mw-flip)" },
    past_due: { label: "Em atraso", color: "var(--mw-flip)" },
    cancelled: { label: "Cancelado", color: "var(--mw-text-3)" },
};

function fmtDate(v) {
    if (!v) return "—";
    const d = new Date(v);
    return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("pt-BR");
}

function Badge({ status }) {
    const s = STATUS[status] || { label: status || "—", color: "var(--mw-text-3)" };
    return <span style={{ color: s.color, border: `1px solid ${s.color}`, borderRadius: 999, padding: "1px 8px", fontSize: 12 }}>{s.label}</span>;
}

export default function AdminLogins() {
    const [overview, setOverview] = useState(null);
    const [trials, setTrials] = useState(null);
    const [invites, setInvites] = useState([]);
    const [error, setError] = useState("");
    const [msg, setMsg] = useState("");
    const [busy, setBusy] = useState(false);
    const [confirmKick, setConfirmKick] = useState(null);
    const [days, setDays] = useState(15);
    const [inv, setInv] = useState({ code: "", label: "", trial_days: 15, max_uses: "" });
    const myEmail = String(getStoredAuth()?.user?.email || "").toLowerCase();

    const load = useCallback(async () => {
        try {
            const [o, t, i] = await Promise.all([adminCall("/overview"), adminCall("/trials"), adminCall("/invites")]);
            setOverview(o);
            setTrials(t);
            setInvites(i.invites || []);
            setError("");
        } catch (e) {
            setError(`Não foi possível carregar: ${e.message}`);
        }
    }, []);

    useEffect(() => {
        let alive = true;
        Promise.all([adminCall("/overview"), adminCall("/trials"), adminCall("/invites")])
            .then(([o, t, i]) => {
                if (!alive) return;
                setOverview(o);
                setTrials(t);
                setInvites(i.invites || []);
            })
            .catch((e) => alive && setError(`Não foi possível carregar: ${e.message}`));
        return () => {
            alive = false;
        };
    }, []);

    const act = async (label, fn) => {
        setBusy(true);
        setMsg("");
        try {
            await fn();
            setMsg(label);
            await load();
        } catch (e) {
            setError(e.message);
        } finally {
            setBusy(false);
            setConfirmKick(null);
        }
    };

    const extend = (u) => act(`Trial de ${u.email} estendido em ${days} dias.`, () => adminCall(`/users/${u.id}/extend`, { method: "POST", body: JSON.stringify({ days: Number(days) }) }));
    const kick = (u) => act(`Sessão de ${u.email} derrubada.`, () => adminCall(`/users/${u.id}/kick`, { method: "POST" }));
    const unblock = (u) => act(`${u.email} desbloqueado.`, () => adminCall(`/users/${u.id}/unblock`, { method: "POST" }));
    const createInvite = (ev) => {
        ev.preventDefault();
        const body = { code: inv.code.trim(), label: inv.label.trim(), trial_days: Number(inv.trial_days) || 15 };
        if (inv.max_uses !== "") body.max_uses = Number(inv.max_uses);
        act(`Convite ${body.code.toUpperCase()} salvo.`, async () => {
            await adminCall("/invites", { method: "POST", body: JSON.stringify(body) });
            setInv({ code: "", label: "", trial_days: 15, max_uses: "" });
        });
    };

    const users = overview?.users || [];
    const sum = trials?.summary || {};
    const stats = [
        ["Trials ativos", sum.active_trials], ["Vencem em 3 dias", sum.expiring_3d], ["Trials vencidos", sum.expired_trials],
        ["Converteram", sum.converted_trials], ["Nunca entraram", sum.never_logged_in], ["Lista de espera", sum.waitlist_count],
    ];

    return (
        <div style={{ minHeight: "100vh", background: "var(--mw-bg)", color: "var(--mw-text-1)", padding: "20px 16px" }}>
            <div style={{ maxWidth: 1180, margin: "0 auto", display: "grid", gap: 14 }}>
                <header style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                    <h1 style={{ fontSize: 22, margin: 0 }}>Logins</h1>
                    <span style={{ color: "var(--mw-text-2)", fontSize: 13, flex: 1, minWidth: 200 }}>Usuários, trials e convites. Só o plano admin chega aqui.</span>
                    <button type="button" className="mw-btn mw-btn-secondary" data-testid="logins-reload" onClick={load} disabled={busy}>Atualizar</button>
                </header>

                {error && <div style={{ ...card, color: "var(--mw-neg)" }} data-testid="logins-error" role="alert">{error}</div>}
                {msg && <div style={{ ...card, color: "var(--mw-pos)" }} data-testid="logins-msg" role="status">{msg}</div>}

                <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 }} data-testid="logins-stats">
                    {stats.map(([k, v]) => (
                        <div key={k} style={card}>
                            <div style={{ fontSize: 12, color: "var(--mw-text-3)" }}>{k}</div>
                            <div style={{ fontSize: 22, fontWeight: 700 }}>{v ?? "—"}</div>
                        </div>
                    ))}
                </section>

                <section style={{ ...card, overflowX: "auto" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8, flexWrap: "wrap" }}>
                        <h2 style={{ fontSize: 15, margin: 0, flex: 1 }}>Usuários ({users.length})</h2>
                        <label style={{ fontSize: 12, color: "var(--mw-text-2)" }}>
                            Dias ao estender{" "}
                            <input type="number" min={1} max={365} value={days} onChange={(e) => setDays(e.target.value)} style={{ ...input, width: 70 }} data-testid="extend-days" />
                        </label>
                    </div>
                    <table style={{ width: "100%", borderCollapse: "collapse" }} data-testid="users-table">
                        <thead><tr>{["E-mail", "Nome", "Plano", "Situação", "Expira", "Último acesso", "Ações"].map((h) => <th key={h} style={th}>{h}</th>)}</tr></thead>
                        <tbody>
                            {users.map((u) => {
                                const self = String(u.email || "").toLowerCase() === myEmail;
                                return (
                                    <tr key={u.id} data-testid={`user-row-${u.id}`}>
                                        <td style={td}>{u.email}{self ? " (você)" : ""}</td>
                                        <td style={td}>{u.full_name || "—"}</td>
                                        <td style={td}>{u.plan || "—"}</td>
                                        <td style={td}><Badge status={u.status} /></td>
                                        <td style={td}>{fmtDate(u.expires_at)}</td>
                                        <td style={td}>{fmtDate(u.last_login_at)}</td>
                                        <td style={{ ...td, whiteSpace: "nowrap" }}>
                                            <button type="button" className="mw-btn mw-btn-secondary" data-testid={`extend-${u.id}`} disabled={busy} onClick={() => extend(u)}>+ {days} dias</button>{" "}
                                            {u.status === "blocked" && (
                                                <button type="button" className="mw-btn mw-btn-secondary" data-testid={`unblock-${u.id}`} disabled={busy} onClick={() => unblock(u)}>Desbloquear</button>
                                            )}{" "}
                                            {!self && (confirmKick === u.id ? (
                                                <>
                                                    <button type="button" className="mw-btn mw-btn-secondary" style={{ color: "var(--mw-neg)" }} data-testid={`kick-confirm-${u.id}`} disabled={busy} onClick={() => kick(u)}>Confirmar</button>{" "}
                                                    <button type="button" className="mw-btn mw-btn-secondary" onClick={() => setConfirmKick(null)}>Cancelar</button>
                                                </>
                                            ) : (
                                                <button type="button" className="mw-btn mw-btn-secondary" data-testid={`kick-${u.id}`} disabled={busy} onClick={() => setConfirmKick(u.id)}>Derrubar sessão</button>
                                            ))}
                                        </td>
                                    </tr>
                                );
                            })}
                            {!users.length && <tr><td style={td} colSpan={7}>{overview ? "Nenhum usuário." : "Carregando…"}</td></tr>}
                        </tbody>
                    </table>
                </section>

                <section style={card}>
                    <h2 style={{ fontSize: 15, margin: "0 0 8px" }}>Convites de trial</h2>
                    <form onSubmit={createInvite} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "end", marginBottom: 10 }} data-testid="invite-form">
                        <label style={{ fontSize: 12, color: "var(--mw-text-2)" }}>Código<br /><input style={{ ...input, width: 140 }} required minLength={2} value={inv.code} onChange={(e) => setInv({ ...inv, code: e.target.value })} data-testid="invite-code" /></label>
                        <label style={{ fontSize: 12, color: "var(--mw-text-2)" }}>Rótulo<br /><input style={{ ...input, width: 180 }} value={inv.label} onChange={(e) => setInv({ ...inv, label: e.target.value })} /></label>
                        <label style={{ fontSize: 12, color: "var(--mw-text-2)" }}>Dias<br /><input type="number" min={1} max={90} style={{ ...input, width: 70 }} value={inv.trial_days} onChange={(e) => setInv({ ...inv, trial_days: e.target.value })} /></label>
                        <label style={{ fontSize: 12, color: "var(--mw-text-2)" }}>Usos máx.<br /><input type="number" min={1} style={{ ...input, width: 80 }} value={inv.max_uses} placeholder="sem teto" onChange={(e) => setInv({ ...inv, max_uses: e.target.value })} /></label>
                        <button type="submit" className="mw-btn mw-btn-primary" disabled={busy} data-testid="invite-save">Salvar convite</button>
                    </form>
                    <table style={{ width: "100%", borderCollapse: "collapse" }} data-testid="invites-table">
                        <thead><tr>{["Código", "Rótulo", "Dias", "Usos", "Ativo"].map((h) => <th key={h} style={th}>{h}</th>)}</tr></thead>
                        <tbody>
                            {invites.map((i) => (
                                <tr key={i.code}>
                                    <td style={td}>{i.code}</td><td style={td}>{i.label || "—"}</td><td style={td}>{i.trial_days}</td>
                                    <td style={td}>{i.used_count ?? 0}{i.max_uses ? ` / ${i.max_uses}` : ""}</td><td style={td}>{i.is_active === false || i.is_active === 0 ? "Não" : "Sim"}</td>
                                </tr>
                            ))}
                            {!invites.length && <tr><td style={td} colSpan={5}>Nenhum convite.</td></tr>}
                        </tbody>
                    </table>
                </section>
            </div>
        </div>
    );
}
