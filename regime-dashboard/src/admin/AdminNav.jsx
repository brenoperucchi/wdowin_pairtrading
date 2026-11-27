import { visibleAdminPages, hrefForPage } from "./adminPages";
import { getStoredAuth, isSaasAuthEnabled } from "../utils/saasAuth";

// Barra de navegação da área administrativa. Só aparece para login com plano admin.
export default function AdminNav({ current }) {
    const pages = visibleAdminPages({ saasEnabled: isSaasAuthEnabled(), user: getStoredAuth()?.user });
    if (!pages.length) return null;
    const pathname = typeof window !== "undefined" ? window.location.pathname : "/";
    return (
        <nav aria-label="Administração" data-testid="admin-nav" style={{ display: "inline-flex", gap: 4, padding: 3, borderRadius: 8, background: "var(--mw-card)", border: "1px solid var(--mw-hairline)" }}>
            {pages.map((p) => {
                const active = p.key === current;
                return (
                    <a
                        key={p.key}
                        href={hrefForPage(p, pathname)}
                        data-testid={`admin-nav-${p.key}`}
                        aria-current={active ? "page" : undefined}
                        style={{
                            padding: "5px 12px", borderRadius: 6, fontSize: 13, fontWeight: 600, textDecoration: "none",
                            color: active ? "var(--mw-accent-on)" : "var(--mw-text-2)",
                            background: active ? "var(--mw-accent)" : "transparent",
                        }}
                    >
                        {p.label}
                    </a>
                );
            })}
        </nav>
    );
}
