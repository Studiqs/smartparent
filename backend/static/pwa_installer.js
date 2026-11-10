/**
 * STUDIQS® SmartParent™ - Progressive Web App (PWA) Native Install Banner
 * Implements Day 5: Android Chrome + Mobile Web Home-Screen Installation
 */

(function () {
  let deferredPrompt = null;
  const installBannerId = 'studiqs-pwa-install-banner';

  window.addEventListener('beforeinstallprompt', (e) => {
    // Prevent the default browser mini-infobar from appearing
    e.preventDefault();
    deferredPrompt = e;

    // Check if parent previously dismissed the banner in this session
    if (sessionStorage.getItem('pwa_prompt_dismissed') === 'true') {
      return;
    }

    showNativeInstallPrompt();
  });

  function showNativeInstallPrompt() {
    if (document.getElementById(installBannerId)) return;

    const banner = document.createElement('div');
    banner.id = installBannerId;
    banner.style.cssText = `
      position: fixed;
      bottom: 20px;
      left: 50%;
      transform: translateX(-50%);
      width: calc(100% - 32px);
      max-width: 440px;
      background: #1e1b4b;
      color: #ffffff;
      padding: 16px;
      border-radius: 14px;
      box-shadow: 0 12px 30px rgba(0, 0, 0, 0.4);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      z-index: 99999;
      border: 1px solid rgba(99, 102, 241, 0.3);
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    `;

    banner.innerHTML = `
      <div style="display: flex; align-items: center; gap: 12px; flex: 1;">
        <div style="width: 44px; height: 44px; border-radius: 10px; background: #4f46e5; display: flex; align-items: center; justify-content: center; font-size: 22px;">
          🎓
        </div>
        <div>
          <div style="font-weight: 700; font-size: 14px; line-height: 1.2;">Install SmartParent™</div>
          <div style="font-size: 11px; color: #a5b4fc; margin-top: 2px;">Instant 1-tap home screen access</div>
        </div>
      </div>
      <div style="display: flex; align-items: center; gap: 8px;">
        <button id="pwa-install-confirm" style="
          background: #4f46e5;
          color: #ffffff;
          border: none;
          padding: 8px 14px;
          border-radius: 8px;
          font-weight: 600;
          font-size: 12px;
          cursor: pointer;
        ">Install</button>
        <button id="pwa-install-dismiss" style="
          background: transparent;
          color: #94a3b8;
          border: none;
          padding: 8px 6px;
          font-size: 16px;
          cursor: pointer;
        ">✕</button>
      </div>
    `;

    document.body.appendChild(banner);

    document.getElementById('pwa-install-confirm').addEventListener('click', async () => {
      if (!deferredPrompt) return;
      banner.remove();
      deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      console.log(`[PWA] Parent installation outcome: ${outcome}`);
      deferredPrompt = null;
    });

    document.getElementById('pwa-install-dismiss').addEventListener('click', () => {
      banner.remove();
      sessionStorage.setItem('pwa_prompt_dismissed', 'true');
    });
  }

  // Register service worker if supported
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/static/sw.js')
        .then((reg) => console.log('[PWA] ServiceWorker registration successful:', reg.scope))
        .catch((err) => console.warn('[PWA] ServiceWorker registration failed:', err));
    });
  }
})();

