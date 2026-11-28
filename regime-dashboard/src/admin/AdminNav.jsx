import { visibleAdminPages, hrefForPage } from "./adminPages";
import { getStoredAuth, isSaasAuthEnabled } from "../utils/saasAuth";
import { useOpenPostCount } from "../marketing/useOpenPostCount";

// Barra de navegação da área administrativa. Só aparece para login com plano admin.
export default function AdminNav({ current }) {
    const pages = visibleAdminPages({ saasEnabled: isSaasAuthEnabled(), user: getStoredAuth()?.user });
    const openPosts = useOpenPostCount(pages.length > 0);
    if (!pages.length) return null;
    return (
        <nav aria-label="Administração" data-testid="admin-nav" style={{ display: "flex", gap: 2, padding: 2, borderRadius: 8, background: "var(--mw-card)", border: "1px solid var(--mw-hairline)", maxWidth: "100%", overflowX: "auto", scrollbarWidth: "none" }}>
            {pages.map((p) => {
                const active = p.key === current;
                return (
                    <a
                        key={p.key}
                        href={hrefForPage(p)}
                        data-testid={`admin-nav-${p.key}`}
                        aria-current={active ? "page" : undefined}
                        style={{
                            padding: "2px 12px", borderRadius: 6, fontSize: 12, fontWeight: 600, textDecoration: "none", whiteSpace: "nowrap", flex: "0 0 auto", fontFamily: "var(--sans, inherit)",
                            color: active ? "var(--mw-accent-on)" : "var(--mw-text-2)",
                            background: active ? "var(--mw-accent)" : "transparent",
                        }}
                    >
                        {p.label}
                        {p.key === "marketing" && openPosts > 0 && (
                            <span
                                data-testid="admin-nav-marketing-open"
                                title={`${openPosts} ${openPosts === 1 ? "publicação em aberto" : "publicações em aberto"}: não publicada${openPosts === 1 ? "" : "s"} nem cancelada${openPosts === 1 ? "" : "s"}`}
                                aria-label={`${openPosts} ${openPosts === 1 ? "rascunho em aberto" : "rascunhos em aberto"}`}
                                style={{ marginLeft: 6, minWidth: 16, padding: "0 5px", borderRadius: 999, background: "var(--mw-flip)", color: "var(--mw-bg)", fontSize: 10, fontWeight: 800, display: "inline-block", textAlign: "center", lineHeight: "16px" }}
                            >
                                {openPosts}
                            </span>
                        )}
                    </a>
                );
            })}
        </nav>
    );
}
