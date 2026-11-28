import React, { useEffect, useState } from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import MorningWallsVideoModal from './components/MorningWallsVideoModal.jsx'
import SaasAuthGate from './components/SaasAuthGate.jsx'
import MarketingAdmin from './components/MarketingAdmin.jsx'
import { ADMIN_SCREENS } from './admin/adminScreens.jsx'
import { pageForMode } from './admin/adminPages.js'
import { canAccessMediaStudio, isSaasAuthEnabled } from './utils/saasAuth.js'
import { applyTheme, readTheme } from './utils/theme.js'
import './index.css'

applyTheme(readTheme())

const isMorningVideoStandalone =
  typeof window !== 'undefined' &&
  new URLSearchParams(window.location.search || '').get('mode') === 'morning_video';

const modeParam =
  typeof window !== 'undefined' ? new URLSearchParams(window.location.search || '').get('mode') : null;
const adminPage = pageForMode(modeParam);
const isMarketingStandalone = modeParam === 'marketing';

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

/* Tela de administração: só abre para plano admin; os demais caem no painel. Serve a toda tela de ADMIN_PAGES. */
/* eslint-disable-next-line react-refresh/only-export-components */
function SaasAdminScreen({ screen }) {
  const [allowed, setAllowed] = useState(() => canAccessMediaStudio());

  useEffect(() => {
    const sync = (ev) => setAllowed(canAccessMediaStudio(ev?.detail?.user));
    window.addEventListener('mw-saas-auth-updated', sync);
    return () => window.removeEventListener('mw-saas-auth-updated', sync);
  }, []);

  return allowed ? React.createElement(screen) : <App />;
}

function pickScreen() {
  const Screen = adminPage && ADMIN_SCREENS[adminPage.key];
  if (Screen) return <SaasAdminScreen screen={Screen} />;
  if (isMorningVideoStandalone) return <SaasMorningVideoEntry />;
  return <App />;
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {saasEnabled ? (
      <SaasAuthGate>{pickScreen()}</SaasAuthGate>
    ) : isMarketingStandalone ? (
      <MarketingAdmin />
    ) : isMorningVideoStandalone ? (
      <MorningWallsVideoModal isOpen={true} standalone={true} />
    ) : (
      <App />
    )}
  </React.StrictMode>,
)
