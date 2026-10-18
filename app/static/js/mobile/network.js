/* Librairie Mobile - Surveillance Réseau, Heartbeat & Synchronisation Régie */
'use strict';
import { $, TOKEN_KEY } from './core.js';
import { state } from './state.js';
import { api } from './api.js';

export function markNetworkOffline() {
  if (!state.isNetworkOnline) return;
  state.isNetworkOnline = false;
  const alertEl = $('#netAlertBanner');
  const successEl = $('#netSuccessBanner');
  if (successEl) successEl.style.display = 'none';
  if (alertEl) alertEl.style.display = 'block';
  if (navigator.vibrate) navigator.vibrate([120, 60, 120]);
}

export function markNetworkOnline() {
  if (state.isNetworkOnline) return;
  state.isNetworkOnline = true;
  state.pingFailCount = 0;
  const alertEl = $('#netAlertBanner');
  const successEl = $('#netSuccessBanner');
  if (alertEl) alertEl.style.display = 'none';
  if (successEl) {
    successEl.style.display = 'block';
    setTimeout(() => { successEl.style.display = 'none'; }, 2600);
  }
}

export async function checkPing(manual = false) {
  const retryBtn = $('#btnNetRetry');
  if (manual && retryBtn) retryBtn.textContent = 'Test...';

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 2000);

  try {
    const res = await fetch('/api/ping', {
      method: 'GET',
      cache: 'no-store',
      signal: controller.signal
    });
    clearTimeout(timer);

    if (res.ok) {
      const data = await res.json();
      markNetworkOnline();
      if (data.active_moment) {
        state.mMoment = data.active_moment;
      }
      if (data.ips && data.ips.length) {
        localStorage.setItem('librairie_known_ips', JSON.stringify({ ips: data.ips, mdns: data.mdns_host }));
      }
    } else {
      throw new Error('Ping ' + res.status);
    }
  } catch (err) {
    clearTimeout(timer);
    state.pingFailCount++;
    if (state.pingFailCount >= 2 || !navigator.onLine) {
      markNetworkOffline();
    }
  } finally {
    if (manual && retryBtn) retryBtn.textContent = 'Réessayer';
  }
}

let pingIntervalTimer = null;
export function startNetworkMonitor() {
  if (pingIntervalTimer) clearInterval(pingIntervalTimer);
  pingIntervalTimer = setInterval(() => checkPing(false), 4000);

  window.addEventListener('offline', () => markNetworkOffline());
  window.addEventListener('online', () => checkPing(true));

  const retryBtn = $('#btnNetRetry');
  if (retryBtn) {
    retryBtn.addEventListener('click', () => checkPing(true));
  }
}

export function logMobileLiveActivity(type, title, detail, data = {}) {
  api('/api/live/activity', {
    method: 'POST',
    body: {
      type,
      user_name: state.currentUser || 'Libraire Mobile',
      title,
      detail,
      data
    }
  }).catch(() => {});
}

let mobileBatteryInfo = null;
if (typeof navigator !== 'undefined' && navigator.getBattery) {
  navigator.getBattery().then(b => {
    const updateBat = () => { mobileBatteryInfo = { level: Math.round(b.level * 100), charging: b.charging }; };
    updateBat();
    b.addEventListener('levelchange', updateBat);
    b.addEventListener('chargingchange', updateBat);
  }).catch(() => {});
}

let liveCartSyncTimer = null;
let pendingLiveAction = null;

export function syncLiveCart(action = null) {
  if (!localStorage.getItem(TOKEN_KEY)) return;
  if (action) pendingLiveAction = action;
  if (liveCartSyncTimer) clearTimeout(liveCartSyncTimer);
  liveCartSyncTimer = setTimeout(async () => {
    const act = pendingLiveAction;
    pendingLiveAction = null;
    try {
      const isCartActive = state.cart && state.cart.length > 0;
      const total = isCartActive ? state.cart.reduce((s, i) => s + i.qty * (i.book ? i.book.price : 0), 0) : 0;
      const count = isCartActive ? state.cart.reduce((s, i) => s + i.qty, 0) : 0;
      const items = isCartActive ? state.cart.map(i => ({
        title: (i.book ? i.book.title : 'Livre') + (i.book && i.book.volume ? ' · Vol. ' + i.book.volume : ''),
        qty: i.qty,
        price: i.book ? i.book.price : 0
      })) : [];

      await api('/api/mobile/active-cart', {
        method: 'POST',
        body: {
          user_name: state.currentUser || 'Libraire Mobile',
          total,
          qty: count,
          items,
          mode: state.currentMode || 'sale',
          moment: state.mMoment || 'Culte',
          gender: state.mGender || null,
          age: state.mAge || null,
          star: state.mStar ? 1 : 0,
          battery: mobileBatteryInfo ? mobileBatteryInfo.level : null,
          is_charging: mobileBatteryInfo ? mobileBatteryInfo.charging : null,
          action: act
        }
      });
    } catch (e) {
      // Ignorer silencieusement si déconnecté temporairement
    }
  }, 120);
}

export function clearLiveCartSync(reason = 'session_closed') {
  if (liveCartSyncTimer) { clearTimeout(liveCartSyncTimer); liveCartSyncTimer = null; }
  api(`/api/mobile/active-cart?reason=${encodeURIComponent(reason)}`, { method: 'DELETE' }).catch(() => {});
}

export function saveActiveCart(action = null) {
  if (action && action.type && action.type !== 'cart_cleared' && action.type !== 'sale_cleared') {
    logMobileLiveActivity(action.type, action.title || '', action.detail || '', action);
  }
  if (state.cart && state.cart.length > 0) {
    const data = {
      cart: state.cart,
      originPayments: state.originPayments,
      gender: state.mGender,
      age: state.mAge,
      star: state.mStar,
      timestamp: Date.now()
    };
    localStorage.setItem('librairie_mobile_active_cart', JSON.stringify(data));
  } else {
    localStorage.removeItem('librairie_mobile_active_cart');
  }
  syncLiveCart(action);
}

export function restoreActiveCart() {
  const raw = localStorage.getItem('librairie_mobile_active_cart');
  if (!raw) return;
  try {
    const data = JSON.parse(raw);
    if (data && data.cart && data.cart.length > 0) {
      state.cart = data.cart;
      state.originPayments = data.originPayments || {};
      state.mGender = data.gender || '';
      state.mAge = data.age || '';
      state.mStar = data.star || 0;
      const sBtn = $('#mBtnStar'); if (sBtn) sBtn.classList.toggle('on', !!state.mStar);
      const gEl = $('#mDemoGender');
      if (gEl) {
        gEl.classList.toggle('is-couple', state.mGender === 'Couple');
        gEl.querySelector('button[data-g="Femme"]')?.classList.toggle('on', state.mGender === 'Femme' || state.mGender === 'Couple');
        gEl.querySelector('button[data-g="Homme"]')?.classList.toggle('on', state.mGender === 'Homme' || state.mGender === 'Couple');
        const cb = $('#mCoupleBadge');
        if (cb) cb.style.display = state.mGender === 'Couple' ? 'block' : 'none';
      }
      const aEl = $('#mDemoAge');
      if (aEl) {
        aEl.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.a === state.mAge));
      }
      syncLiveCart();
    }
  } catch (e) {
    localStorage.removeItem('librairie_mobile_active_cart');
  }
}

// Heartbeat 15s
setInterval(() => {
  if (localStorage.getItem(TOKEN_KEY)) {
    syncLiveCart();
  }
}, 15000);

// Déconnexion propre lors de la fermeture
window.addEventListener('pagehide', () => {
  const tok = localStorage.getItem(TOKEN_KEY);
  if (tok) {
    try {
      if (navigator.sendBeacon) {
        navigator.sendBeacon('/api/mobile/active-cart?reason=session_closed');
      } else {
        fetch('/api/mobile/active-cart?reason=session_closed', { method: 'DELETE', keepalive: true }).catch(() => {});
      }
    } catch (e) {}
  }
});
