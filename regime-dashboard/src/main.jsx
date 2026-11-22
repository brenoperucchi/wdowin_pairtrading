import React, { useEffect, useState } from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import MorningWallsVideoModal from './components/MorningWallsVideoModal.jsx'
import SaasAuthGate from './components/SaasAuthGate.jsx'
import { canAccessMediaStudio, isSaasAuthEnabled } from './utils/saasAuth.js'
import './index.css'

const isMorningVideoStandalone =
  typeof window !== 'undefined' &&
  new URLSearchParams(window.location.search || '').get('mode') === 'morning_video';

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

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {saasEnabled ? (
      <SaasAuthGate>
        {isMorningVideoStandalone ? <SaasMorningVideoEntry /> : <App />}
      </SaasAuthGate>
    ) : isMorningVideoStandalone ? (
      <MorningWallsVideoModal isOpen={true} standalone={true} />
    ) : (
      <App />
    )}
  </React.StrictMode>,
)
