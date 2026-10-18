/* Librairie Mobile - Point d'entrée principal de l'application modulaire */
'use strict';
import { TOKEN_KEY, USER_KEY, updateViewportHeight } from './core.js';
import { state } from './state.js';
import { api } from './api.js';
import { startNetworkMonitor, restoreActiveCart, syncLiveCart } from './network.js';
import { pairFromHash, showPairing, updateUser, openUserModal, initPairing, initUserModal } from './pairing.js';
import { restoreRecvList, setMobileMode, initModes } from './modes.js';
import { loadPayOptions, renderCart, initCart } from './cart.js';
import { closeNewBookModal, initNewBookModal } from './new_book_modal.js';
import { initBookStats } from './book_stats.js';
import { initOcr } from './ocr.js';
import { initSearch } from './search.js';
import { startCamera, initScanner } from './scanner.js';
import { initFullscreen } from './fullscreen.js';

(async function boot() {
  updateViewportHeight();
  initFullscreen();
  initPairing();
  initUserModal();
  initBookStats();
  initModes();
  initCart();
  initNewBookModal();
  initOcr();
  initSearch();
  initScanner();

  updateUser();
  renderCart();
  closeNewBookModal();
  startNetworkMonitor();
  restoreActiveCart();
  restoreRecvList();
  renderCart();
  await pairFromHash();

  const initHash = location.hash.replace(/^#/, '');
  setMobileMode(initHash === 'recv' ? 'recv' : 'sale', true, false);

  if (!localStorage.getItem(TOKEN_KEY)) {
    renderCart();
    return showPairing();
  }

  try {
    const fetchedUsers = await api('/api/users');
    if (Array.isArray(fetchedUsers)) {
      state.users = fetchedUsers;
      if (state.currentUser && !state.users.some(u => u.name === state.currentUser)) {
        state.currentUser = '';
        localStorage.removeItem(USER_KEY);
      }
    }
  } catch (e) {
    console.warn('Mode hors-ligne pour /api/users:', e);
  }

  updateUser();
  try {
    await loadPayOptions();
  } catch (e) {
    console.warn('Options de paiement par défaut utilisées:', e);
  }
  renderCart();
  syncLiveCart({ type: 'mobile_connected' });
  if (!state.currentUser) openUserModal();
  startCamera();
})();
