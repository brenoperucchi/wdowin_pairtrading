import React, { useEffect, useState } from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import MorningWallsVideoModal from './components/MorningWallsVideoModal.jsx'
import SaasAuthGate from './components/SaasAuthGate.jsx'
import MarketingAdmin from './components/MarketingAdmin.jsx'
import { ADMIN_SCREENS } from './admin/adminScreens.jsx'
import { pageForPathname } from './admin/adminPages.js'
import { routeKeyFromPathname } from './routes.js'
import { canAccessMediaStudio, isSaasAuthEnabled } from './utils/saasAuth.js'
import { applyTheme, readTheme } from './utils/theme.js'
import './index.css'

applyTheme(readTheme())

// A tela vem do caminho da URL (src/routes.js); nada de ?mode=.
const routeKey = routeKeyFromPathname(typeof window !== 'undefined' ? window.location.pathname : '/');
const adminPage = pageForPathname(typeof window !== 'undefined' ? window.location.pathname : '/');
const isMorningVideoStandalone = routeKey === 'morningVideo';
const isMarketingStandalone = routeKey === 'adminMarketing';

const saasEnabled = isSaasAuthEnabled();

/* eslint-disable-next-line react-refresh/only-export-components */
function SaasMorningVideoEntry() {
  const [allowed, setAllowed] = useState(() => canAccessMediaStudio());

  useEffect(() => {
    const sync = (ev) => setAllowed(canAccessMediaStudio(ev?.detail?.user));
    window.addEventListener('mw-saas-auth-updated', sync);
    return () => window.removeEventListener('mw-saas-auth-updated', sync);
  }, []);

  return allowed ? <MorningWallsVideoModal isOpen={true} standalone={true} /> : <App />;
}

/* Tela de administração: só abre para plano admin; os demais veem o aviso de acesso restrito no próprio endereço. */
/* eslint-disable-next-line react-refresh/only-export-components */
function SaasAdminScreen({ screen }) {
  const [allowed, setAllowed] = useState(() => canAccessMediaStudio());

  useEffect(() => {
    const sync = (ev) => setAllowed(canAccessMediaStudio(ev?.detail?.user));
    window.addEventListener('mw-saas-auth-updated', sync);
    return () => window.removeEventListener('mw-saas-auth-updated', sync);
  }, []);

  return allowed ? React.createElement(screen) : <AccessDenied />;
}

/* eslint-disable-next-line react-refresh/only-export-components */
function AccessDenied() {
  return (
    <main data-testid="access-denied" style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: 'var(--mw-bg)', color: 'var(--mw-text-1)' }}>
      <p>
        Acesso restrito a administradores. <a href="/" style={{ color: 'var(--mw-accent)' }}>Voltar aos gráficos</a>
      </p>
    </main>
  );
}

/* eslint-disable-next-line react-refresh/only-export-components */
function NotFound() {
  return (
    <main data-testid="not-found" style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: 'var(--mw-bg)', color: 'var(--mw-text-1)' }}>
      <p>
        Página não encontrada. <a href="/" style={{ color: 'var(--mw-accent)' }}>Voltar aos gráficos</a>
      </p>
    </main>
  );
}

function pickScreen() {
  if (routeKey === 'notFound') return <NotFound />;
  if (routeKey === 'admin') return <SaasAdminScreen screen={ADMIN_SCREENS.home} />;
  const Screen = adminPage && ADMIN_SCREENS[adminPage.key];
  if (Screen) return <SaasAdminScreen screen={Screen} />;
  if (isMorningVideoStandalone) return <SaasMorningVideoEntry />;
  return <App />;
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {saasEnabled ? (
      <SaasAuthGate>{pickScreen()}</SaasAuthGate>
    ) : routeKey === 'notFound' ? (
      <NotFound />
    ) : isMarketingStandalone ? (
      <MarketingAdmin />
    ) : isMorningVideoStandalone ? (
      <MorningWallsVideoModal isOpen={true} standalone={true} />
    ) : (
      <App />
    )}
  </React.StrictMode>,
)
