import { ADMIN_PAGES, hrefForPage } from "./adminPages";

// Raiz da área administrativa (/admin): índice com um atalho para cada seção. A barra do topo já navega;
// aqui fica a visão geral para quem chega pelo endereço /admin.
export default function AdminHome() {
    const sections = ADMIN_PAGES.filter((p) => p.key !== "charts");
    return (
        <main data-testid="admin-home" style={{ minHeight: "100vh", background: "var(--mw-bg)", color: "var(--mw-text-1)", padding: "24px 16px" }}>
            <div style={{ maxWidth: 720, margin: "0 auto" }}>
                <h1 style={{ fontSize: 20, margin: "0 0 16px" }}>Administração</h1>
                <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
                    {sections.map((p) => (
                        <li key={p.key}>
                            <a
                                href={hrefForPage(p)}
                                data-testid={`admin-home-${p.key}`}
                                style={{ display: "block", padding: "12px 14px", borderRadius: 8, border: "1px solid var(--mw-hairline)", background: "var(--mw-card)", color: "var(--mw-text-1)", textDecoration: "none", fontWeight: 600 }}
                            >
                                {p.label}
                            </a>
                        </li>
                    ))}
                </ul>
            </div>
        </main>
    );
}
