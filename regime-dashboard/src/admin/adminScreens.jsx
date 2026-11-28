import MarketingAdmin from "../components/MarketingAdmin.jsx";
import AdminLogins from "./AdminLogins.jsx";

// Componente de cada tela de ADMIN_PAGES (por key). "charts" é o painel raiz e não entra aqui.
export const ADMIN_SCREENS = {
    marketing: MarketingAdmin,
    logins: AdminLogins,
};
