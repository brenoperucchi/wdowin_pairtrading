import { useEffect, useState } from "react";
import { readTheme, toggleTheme } from "../utils/theme";

// Botão único de tema, na barra de sessão: vale para o sistema inteiro.
export default function ThemeToggle() {
    const [theme, setThemeState] = useState(readTheme);
    useEffect(() => {
        const sync = (ev) => setThemeState(ev.detail.theme);
        window.addEventListener("mw-theme-changed", sync);
        return () => window.removeEventListener("mw-theme-changed", sync);
    }, []);
    return (
        <button
            type="button"
            className="mw-btn mw-btn-secondary"
            data-testid="theme-toggle"
            aria-label="Alternar entre modo claro e escuro"
            onClick={toggleTheme}
            style={{ height: 24, padding: "0 8px", fontSize: 11, borderRadius: 6 }}
        >
            {theme === "dark" ? "☀ Modo claro" : "☾ Modo escuro"}
        </button>
    );
}
