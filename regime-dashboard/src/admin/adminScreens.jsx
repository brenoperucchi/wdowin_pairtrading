import MarketingAdmin from "../components/MarketingAdmin.jsx";
import AdminLogins from "./AdminLogins.jsx";
import AdminHome from "./AdminHome.jsx";

// Componente de cada tela de ADMIN_PAGES (por key). "charts" é o painel raiz e não entra aqui.
// "home" é a raiz da área administrativa (/admin), que não é item da barra.
export const ADMIN_SCREENS = {
    home: AdminHome,
    marketing: MarketingAdmin,
    users: AdminLogins,
};
