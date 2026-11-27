import React, { useEffect, useState } from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import MorningWallsVideoModal from './components/MorningWallsVideoModal.jsx'
import SaasAuthGate from './components/SaasAuthGate.jsx'
import MarketingAdmin from './components/MarketingAdmin.jsx'
import { canAccessMediaStudio, isSaasAuthEnabled } from './utils/saasAuth.js'
import './index.css'

const isMorningVideoStandalone =
  typeof window !== 'undefined' &&
  new URLSearchParams(window.location.search || '').get('mode') === 'morning_video';

const isMarketingStandalone =
  typeof window !== 'undefined' &&
  new URLSearchParams(window.location.search || '').get('mode') === 'marketing';

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

/* eslint-disable-next-line react-refresh/only-export-components */
function SaasMarketingEntry() {
  const [allowed, setAllowed] = useState(() => canAccessMediaStudio());

  useEffect(() => {
    const sync = (ev) => setAllowed(canAccessMediaStudio(ev?.detail?.user));
    window.addEventListener('mw-saas-auth-updated', sync);
    return () => window.removeEventListener('mw-saas-auth-updated', sync);
  }, []);

  return allowed ? <MarketingAdmin /> : <App />;
}

function pickScreen() {
  if (isMarketingStandalone) return <SaasMarketingEntry />;
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
