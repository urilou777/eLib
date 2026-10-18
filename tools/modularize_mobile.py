"""Script d'automatisation de la modularisation de mobile.js en Modules ES natifs.
Découpe app/static/mobile.js en 14 modules ES6 autonomes, documentés et testés sans bundler.
"""
import os
import shutil
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "app", "static")
TARGET_DIR = os.path.join(STATIC_DIR, "js", "mobile")
MOBILE_JS = os.path.join(STATIC_DIR, "mobile.js")
BACKUP_JS = os.path.join(STATIC_DIR, "mobile.js.bak")
MOBILE_HTML = os.path.join(STATIC_DIR, "mobile.html")
SW_JS = os.path.join(STATIC_DIR, "sw.js")

MODULES = {}

# =============================================================================
# 1. core.js
# =============================================================================
MODULES["core.js"] = """/* Librairie Mobile - Core DOM, Formatage & Utilitaires */
'use strict';

export const $ = s => document.querySelector(s);
export const $$ = s => document.querySelectorAll(s);
export const eur = n => (Number(n) || 0).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
export const TOKEN_KEY = 'librairie_device_token';
export const USER_KEY = 'librairie_user';

export const SVG_TAGS = new Set(['svg', 'path', 'line', 'circle', 'polyline', 'polygon', 'rect', 'g']);
export const SVG_NS = 'http://www.w3.org/2000/svg';

export function esc(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/* Construction DOM sûre : le texte passe toujours par textContent / createTextNode (Anti-XSS) */
export function el(tag, props = {}, ...kids) {
  const isSvg = SVG_TAGS.has(tag);
  const e = isSvg ? document.createElementNS(SVG_NS, tag) : document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') {
      if (isSvg) e.setAttribute('class', v);
      else e.className = v;
    }
    else if (k === 'text') e.textContent = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'style') e.style.cssText = v;
    else e.setAttribute(k, v);
  }
  kids.flat().forEach(c => { if (c != null) e.append(c.nodeType ? c : document.createTextNode(String(c))); });
  return e;
}

export function createStatsIcon() {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('style', 'width:12px;height:12px;stroke:currentColor;fill:none;stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round;color:#d8b4fe;display:inline-block;vertical-align:middle;flex-shrink:0');
  
  const l1 = document.createElementNS(SVG_NS, 'line');
  l1.setAttribute('x1', '18'); l1.setAttribute('y1', '20'); l1.setAttribute('x2', '18'); l1.setAttribute('y2', '10');
  const l2 = document.createElementNS(SVG_NS, 'line');
  l2.setAttribute('x1', '12'); l2.setAttribute('y1', '20'); l2.setAttribute('x2', '12'); l2.setAttribute('y2', '4');
  const l3 = document.createElementNS(SVG_NS, 'line');
  l3.setAttribute('x1', '6'); l3.setAttribute('y1', '20'); l3.setAttribute('x2', '6'); l3.setAttribute('y2', '14');
  
  svg.append(l1, l2, l3);
  return svg;
}

export function toast(msg, kind = 'ok') {
  const t = el('div', { class: 'toast ' + kind, text: msg });
  const toasts = $('#toasts');
  if (toasts) toasts.append(t);
  setTimeout(() => t.remove(), kind === 'err' ? 4500 : 2400);
}

export function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.connect(g); g.connect(ctx.destination); o.frequency.value = 1760; g.gain.value = 0.15;
    o.start(); o.stop(ctx.currentTime + 0.08);
  } catch (e) { /* audio indisponible : sans importance */ }
  if (navigator.vibrate) {
    try { navigator.vibrate(60); } catch (e) { }
  }
}

/* Gestion dynamique de la hauteur visible du viewport */
export function updateViewportHeight() {
  const vv = window.visualViewport;
  const h = vv ? vv.height : window.innerHeight;
  document.documentElement.style.setProperty('--vvh', `${Math.round(h)}px`);
  if (window.scrollY !== 0 || window.scrollX !== 0) {
    window.scrollTo(0, 0);
  }
}
updateViewportHeight();
if (window.visualViewport) {
  window.visualViewport.addEventListener('resize', updateViewportHeight);
  window.visualViewport.addEventListener('scroll', updateViewportHeight);
}
window.addEventListener('resize', updateViewportHeight);
window.addEventListener('orientationchange', () => setTimeout(updateViewportHeight, 100));
window.addEventListener('pageshow', updateViewportHeight);
window.addEventListener('focus', updateViewportHeight);
"""

# =============================================================================
# 2. state.js
# =============================================================================
MODULES["state.js"] = """/* Librairie Mobile - État global partagé centralisé */
'use strict';
import { USER_KEY } from './core.js';

export function getAutoMobileMoment() {
  const isSunday = new Date().getDay() === 0;
  const currentHour = new Date().getHours();
  return isSunday ? (currentHour >= 12 ? '2e Culte (Jeunes EJP)' : '1er Culte (Principal)') : 'En semaine / Autre';
}

export const state = {
  currentUser: localStorage.getItem(USER_KEY) || '',
  currentMode: 'sale', // 'sale' | 'recv'
  cart: [],            // [{ book, qty, lot }]
  recvList: [],        // [{ book, qty }]
  ownersList: [],
  payOptions: [],
  originPayments: {},  // { [owner]: { method, parts } }
  mGender: '',
  mAge: '',
  mStar: 0,
  mMoment: getAutoMobileMoment(),
  users: [],
  pendingNewCode: null,
  currentMatchedBook: null,
  isNetworkOnline: true,
  pingFailCount: 0,
  dbAuthors: [],
  dbPublishers: [],
  currentUpsellContext: null,
  activeMpOwner: null,
  activeMpTotal: 0,
  mpMode1: 'Espèces',
  mpMode2: 'CB',
  isLookingUp: false
};
"""

# =============================================================================
# 3. api.js
# =============================================================================
MODULES["api.js"] = """/* Librairie Mobile - Client API HTTP */
'use strict';
import { TOKEN_KEY } from './core.js';
import { state } from './state.js';
import { showPairing } from './pairing.js';
import { markNetworkOnline, markNetworkOffline } from './network.js';

export async function api(url, { method = 'GET', body, auth = true, timeoutMs = 4000 } = {}) {
  const headers = {};
  if (auth) {
    const tok = localStorage.getItem(TOKEN_KEY);
    if (tok) headers['Authorization'] = 'Bearer ' + tok;
    headers['X-User'] = encodeURIComponent(state.currentUser || '');
  }
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const r = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      cache: 'no-store',
      signal: controller.signal
    });
    clearTimeout(timer);
    if (r.status === 401 && auth) { localStorage.removeItem(TOKEN_KEY); showPairing(); }
    if (!r.ok) {
      let d = r.statusText;
      try { const j = await r.json(); d = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch (e) { }
      throw new Error(d);
    }
    markNetworkOnline();
    return r.json();
  } catch (err) {
    clearTimeout(timer);
    if (err.name === 'AbortError' || !navigator.onLine || (err.message && err.message.includes('fetch'))) {
      markNetworkOffline();
    }
    if (err.name === 'AbortError') {
      throw new Error('Poste central injoignable (délai dépassé). Vérifiez que l\\'ordinateur est allumé.');
    }
    throw err;
  }
}
"""

# =============================================================================
# 4. network.js
# =============================================================================
MODULES["network.js"] = """/* Librairie Mobile - Surveillance Réseau, Heartbeat & Synchronisation Régie */
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
"""

# =============================================================================
# 5. pairing.js
# =============================================================================
MODULES["pairing.js"] = """/* Librairie Mobile - Appairage Appareil & Profils Libraire */
'use strict';
import { $, el, toast, TOKEN_KEY, USER_KEY } from './core.js';
import { state } from './state.js';
import { api } from './api.js';
import { syncLiveCart } from './network.js';
import { stopCamera } from './scanner.js';

export function deviceLabel() {
  const m = navigator.userAgent.match(/\\(([^)]+)\\)/);
  return (m ? m[1] : 'Téléphone').replace(/[;]\\s*wv/i, '').slice(0, 50);
}

export async function pairFromHash() {
  const m = location.hash.match(/pair=([A-Za-z0-9_-]{8,64})/);
  if (!m) return;
  history.replaceState(null, '', location.pathname);
  try {
    const r = await api('/api/mobile/pair', { method: 'POST', body: { code: m[1], name: deviceLabel() }, auth: false });
    localStorage.setItem(TOKEN_KEY, r.token);
    toast('Téléphone appairé avec succès');
  } catch (e) { toast(e.message, 'err'); }
}

export function showPairing() {
  const ps = $('#pairScreen');
  if (ps) ps.hidden = false;
  stopCamera();
}

export function updateUser() {
  const un = $('#userName');
  if (un) un.textContent = state.currentUser || 'Choisir…';
}

export function openUserModal() {
  const list = $('#userList');
  if (!list) return;
  list.replaceChildren(...state.users.map(u => el('button', {
    class: 'user-btn', type: 'button', text: u.name,
    onclick: () => {
      state.currentUser = u.name;
      localStorage.setItem(USER_KEY, u.name);
      updateUser();
      const um = $('#userModal');
      if (um) um.hidden = true;
      toast('Connecté : ' + u.name);
      syncLiveCart({ type: 'user_connected', user_name: u.name });
    }
  })));
  const um = $('#userModal');
  if (um) um.hidden = false;
}

export function initPairing() {
  const btnRetry = $('#btnRetryPair');
  if (btnRetry) btnRetry.addEventListener('click', () => location.reload());
}

export function initUserModal() {
  const btnUser = $('#userBtn');
  if (btnUser) btnUser.addEventListener('click', openUserModal);
}
"""

# =============================================================================
# 6. book_stats.js
# =============================================================================
MODULES["book_stats.js"] = """/* Librairie Mobile - Modale Statistiques Livre & Réassurance Client */
'use strict';
import { $, el, eur, toast, createStatsIcon } from './core.js';
import { api } from './api.js';

export async function openMobileBookStats(bid) {
  const modal = $('#bookStatsModal');
  const cont = $('#mBookStatsContent');
  if (!modal || !cont) return;

  cont.replaceChildren(el('div', { class: 'muted', style: 'text-align:center;padding:24px;font-size:13px', text: 'Chargement des statistiques…' }));
  modal.hidden = false;

  try {
    const data = await api('/api/books/' + bid + '/stats');
    const b = data.book;
    const k = data.kpis;
    const d = data.demographics;
    const recent = data.recent_sales || [];
    const packs = data.packs || [];

    const totalGender = (d.gender.Femme || 0) + (d.gender.Homme || 0) + (d.gender.Couple || 0) + (d.gender.Autre || 0);
    const pFemme = totalGender ? Math.round(((d.gender.Femme || 0) / totalGender) * 100) : 0;
    const pHomme = totalGender ? Math.round(((d.gender.Homme || 0) / totalGender) * 100) : 0;
    const pCouple = totalGender ? Math.round(((d.gender.Couple || 0) / totalGender) * 100) : 0;
    const pAutre = totalGender ? Math.max(0, 100 - pFemme - pHomme - pCouple) : 0;

    const totalAge = (d.age_groups || []).reduce((s, a) => s + a.count, 0);

    const genderBarSegments = [];
    if (pFemme) genderBarSegments.push(el('div', { style: `width:${pFemme}%;background:#f472b6;height:100%`, title: `Femmes : ${pFemme}%` }));
    if (pHomme) genderBarSegments.push(el('div', { style: `width:${pHomme}%;background:#60a5fa;height:100%`, title: `Hommes : ${pHomme}%` }));
    if (pCouple) genderBarSegments.push(el('div', { style: `width:${pCouple}%;background:#c084fc;height:100%`, title: `Couples/Foyers : ${pCouple}%` }));
    if (pAutre) genderBarSegments.push(el('div', { style: `width:${pAutre}%;background:rgba(255,255,255,0.2);height:100%`, title: `Autre : ${pAutre}%` }));

    const genderLegend = el('div', { class: 'm-stats-legend' },
      el('span', { style: 'color:#f472b6' }, `Femme ${pFemme}%`),
      el('span', { style: 'color:#60a5fa' }, `Homme ${pHomme}%`),
      el('span', { style: 'color:#c084fc' }, `Couple ${pCouple}%`),
      pAutre ? el('span', { class: 'muted' }, `Autre ${pAutre}%`) : null
    );

    const agePills = (d.age_groups || []).map(ag => {
      const pct = totalAge ? Math.round((ag.count / totalAge) * 100) : 0;
      return el('div', { class: 'm-stats-age-pill' },
        el('span', { class: 'muted', style: 'margin-right:2px', text: ag.label.replace(' ans', '') }),
        el('b', { text: `${pct}%` })
      );
    });

    const recentItems = recent.slice(0, 3).map(r => {
      const datePart = (r.date || '').split('-').reverse().slice(0, 2).join('/');
      return el('div', { class: 'm-stats-sale-row' },
        el('div', {},
          el('b', { text: datePart }),
          el('span', { class: 'muted', style: 'margin-left:4px', text: r.service_moment || 'Culte' })
        ),
        el('div', { style: 'display:flex;align-items:center;gap:4px' },
          el('b', { text: `${r.qty} ex.` }),
          el('span', { class: 'chip', style: 'font-size:9.5px;padding:1px 5px;background:rgba(255,255,255,0.06)' },
            r.customer_gender ? (r.customer_gender === 'Femme' ? '♀' : r.customer_gender === 'Homme' ? '♂' : '👫') : '👤',
            r.is_star ? ' ⭐' : ''
          )
        )
      );
    });

    cont.replaceChildren(
      // Header
      el('div', { class: 'm-stats-header' },
        el('div', {},
          el('div', { class: 'm-stats-title' },
            b.is_pack ? el('span', { class: 'badge b-pack', style: 'background:linear-gradient(135deg, #9333ea, #c026d3);color:#fff;font-size:10px;font-weight:700;padding:1px 5px;border-radius:4px;margin-right:5px' }, 'PACK') : null,
            b.title
          ),
          el('div', { class: 'm-stats-sub' },
            el('b', { style: 'color:var(--good);font-size:12.5px', text: eur(b.price) }),
            ` · ${b.code}`
          )
        ),
        el('button', {
          type: 'button',
          class: 'btn ghost sm',
          style: 'padding:2px 8px;font-size:16px;color:var(--mut)',
          onclick: closeMobileBookStats
        }, '✕')
      ),

      // KPIs
      el('div', { class: 'm-stats-kpis' },
        el('div', { class: 'm-stats-kpi-card' },
          el('div', { class: 'm-stats-kpi-lbl', text: 'Total Ventes' }),
          el('div', { class: 'm-stats-kpi-val', style: 'color:var(--good)', text: `${k.total_sold} ex.` }),
          el('div', { class: 'muted', style: 'font-size:10px', text: eur(k.total_revenue) })
        ),
        el('div', { class: 'm-stats-kpi-card' },
          el('div', { class: 'm-stats-kpi-lbl', text: 'Dernier Achat' }),
          el('div', { class: 'm-stats-kpi-val', style: 'font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis',
            text: k.last_sale_date ? k.last_sale_date.split('-').reverse().slice(0, 2).join('/') : 'Aucun'
          }),
          el('div', { class: 'muted', style: 'font-size:10px', text: `${k.sold_last_30d} ex. / 30j` })
        ),
        el('div', { class: 'm-stats-kpi-card' },
          el('div', { class: 'm-stats-kpi-lbl', text: 'Stock Dispo' }),
          el('div', { class: 'm-stats-kpi-val', style: `color:${b.stock > 0 ? 'var(--good)' : 'var(--bad)'}`, text: `${b.stock} ex.` }),
          el('div', { class: 'muted', style: 'font-size:9.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis',
            text: (b.owners || []).map(o => `${o.name}: ${o.remaining}`).join(' · ') || 'Stock'
          })
        )
      ),

      // Profil Acheteurs
      el('div', { class: 'm-stats-box' },
        el('div', { class: 'm-stats-box-title' },
          el('svg', { style: 'width:12px;height:12px;stroke:currentColor;fill:none;stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round', viewBox: '0 0 24 24' },
            el('path', { d: 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2' }),
            el('circle', { cx: '12', cy: '7', r: '4' })
          ),
          el('span', { text: 'Profil des Acheteurs' })
        ),
        el('div', { class: 'm-stats-bar' }, ...genderBarSegments),
        genderLegend,
        el('div', { class: 'm-stats-ages' }, ...agePills),
        el('div', { class: 'm-stats-star' },
          el('svg', { style: 'width:13px;height:13px;fill:#fbbf24;stroke:#fbbf24;flex-shrink:0', viewBox: '0 0 24 24' },
            el('polygon', { points: '12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2' })
          ),
          el('span', { text: `${d.star.pct}% acheteurs STAR (${d.star.count} ex.)` })
        )
      ),

      // Derniers Achats
      recentItems.length ? el('div', { class: 'm-stats-box' },
        el('div', { class: 'm-stats-box-title' },
          el('svg', { style: 'width:12px;height:12px;stroke:currentColor;fill:none;stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round', viewBox: '0 0 24 24' },
            el('circle', { cx: '12', cy: '12', r: '10' }),
            el('polyline', { points: '12 6 12 12 16 14' })
          ),
          el('span', { text: 'Derniers Achats' })
        ),
        el('div', { class: 'm-stats-sales' }, ...recentItems)
      ) : null,

      // Pack associé
      packs.length > 0 ? el('div', { style: 'background:rgba(147,51,234,0.12);border:1px solid rgba(147,51,234,0.3);border-radius:8px;padding:5px 8px;font-size:11px' },
        el('div', { style: 'font-size:9.5px;color:#d8b4fe;font-weight:700;text-transform:uppercase', text: 'Inclus dans un pack :' }),
        el('div', { style: 'display:flex;justify-content:space-between;align-items:center;margin-top:2px' },
          el('b', { style: 'color:#fff', text: packs[0].title }),
          el('b', { style: 'color:#86efac', text: eur(packs[0].price) })
        )
      ) : null,

      // Bouton Fermer
      el('button', {
        type: 'button',
        class: 'btn sm',
        style: 'width:100%;padding:8px;font-weight:700;margin-top:2px',
        onclick: closeMobileBookStats
      }, 'Fermer')
    );
  } catch (err) {
    toast('Erreur statistiques : ' + err.message, 'err');
    closeMobileBookStats();
  }
}

export function closeMobileBookStats() {
  const modal = $('#bookStatsModal');
  if (modal) modal.hidden = true;
}

export function initBookStats() {
  const bsModalEl = $('#bookStatsModal');
  if (bsModalEl) {
    bsModalEl.addEventListener('click', e => {
      if (e.target === bsModalEl) closeMobileBookStats();
    });
  }
}
"""

# =============================================================================
# 7. modes.js
# =============================================================================
MODULES["modes.js"] = """/* Librairie Mobile - Gestion des Modes Vente vs Réception Stock */
'use strict';
import { $, el, eur, toast, beep } from './core.js';
import { state } from './state.js';
import { api } from './api.js';
import { logMobileLiveActivity, syncLiveCart } from './network.js';
import { openUserModal } from './pairing.js';

export function saveRecvList() {
  if (state.recvList && state.recvList.length > 0) {
    localStorage.setItem('librairie_mobile_recv_list', JSON.stringify(state.recvList));
  } else {
    localStorage.removeItem('librairie_mobile_recv_list');
  }
}

export function restoreRecvList() {
  const raw = localStorage.getItem('librairie_mobile_recv_list');
  if (!raw) return;
  try {
    const data = JSON.parse(raw);
    if (Array.isArray(data) && data.length > 0) {
      state.recvList = data;
      renderRecv();
    }
  } catch (e) {
    localStorage.removeItem('librairie_mobile_recv_list');
  }
}

export async function loadOwners() {
  try {
    state.ownersList = await api('/api/owners');
    const sel = $('#recvOwner');
    if (sel) {
      sel.replaceChildren(...state.ownersList.map(o => el('option', { value: o.id, text: o.name + (o.kind ? ` (${o.kind})` : '') })));
    }
  } catch (e) { state.ownersList = []; }
}

export function setMobileMode(mode, updateHash = true, showToast = false) {
  if (mode !== 'sale' && mode !== 'recv') mode = 'sale';
  state.currentMode = mode;
  if (updateHash && location.hash !== '#' + mode) {
    location.hash = '#' + mode;
  }
  const bSale = $('#btnModeSale'), bRecv = $('#btnModeRecv');
  if (bSale) bSale.classList.toggle('on', mode === 'sale');
  if (bRecv) bRecv.classList.toggle('on', mode === 'recv');
  const cCard = $('#cartCard'), sBot = $('#saleBottom');
  const rCard = $('#recvCard'), rBot = $('#recvBottom');
  if (cCard) cCard.hidden = (mode !== 'sale');
  if (sBot) sBot.hidden = (mode !== 'sale');
  if (rCard) rCard.hidden = (mode !== 'recv');
  if (rBot) rBot.hidden = (mode !== 'recv');
  if (mode === 'recv' && !state.ownersList.length) loadOwners();
  if (showToast) toast(mode === 'sale' ? 'Mode Vente actif' : 'Mode Réception actif', 'ok');
  syncLiveCart({ type: 'mode_changed', mode });
}

export function addToRecv(book) {
  beep();
  const ex = state.recvList.find(i => i.book.id === book.id);
  if (ex) {
    ex.qty++;
  } else {
    state.recvList.push({ book, qty: 1 });
  }
  toast(`+1 ${book.title}`, 'ok');
  logMobileLiveActivity('recv_item', book.title, `+1 ex. (total ${ex ? ex.qty : 1})`, { book_id: book.id });
  renderRecv();
}

export function renderRecv() {
  const count = state.recvList.reduce((s, i) => s + i.qty, 0);
  const rc = $('#recvCount'); if (rc) rc.textContent = count;
  const list = $('#recvItems');
  const btn = $('#btnValidateRecv');
  if (!list) return;

  if (!state.recvList.length) {
    list.replaceChildren(el('div', { class: 'muted', style: 'text-align:center;padding:18px', text: 'Scannez chaque livre du carton pour le comptabiliser.' }));
    if (btn) btn.disabled = true;
  } else {
    if (btn) btn.disabled = false;
    list.replaceChildren(...state.recvList.map((item, idx) => {
      const b = item.book;
      return el('div', { class: 'cart-item' },
        el('div', { class: 'ci-top' },
          el('div', {},
            el('div', { class: 'ci-title', text: b.title + (b.volume ? ' · Vol. ' + b.volume : '') }),
            el('div', { class: 'muted', text: `${b.code} · ${eur(b.price)}` })),
          el('div', { class: 'qty' },
            el('button', { type: 'button', text: '−', onclick: () => { item.qty--; if (item.qty <= 0) state.recvList.splice(idx, 1); renderRecv(); } }),
            el('b', { text: item.qty }),
            el('button', { type: 'button', text: '+', onclick: () => { item.qty++; renderRecv(); } }))));
    }));
  }
  saveRecvList();
}

export function initModes() {
  window.addEventListener('hashchange', () => {
    const h = location.hash.replace(/^#/, '');
    if ((h === 'sale' || h === 'recv') && h !== state.currentMode) {
      setMobileMode(h, false, false);
    }
  });

  const bSale = $('#btnModeSale'), bRecv = $('#btnModeRecv');
  if (bSale) bSale.addEventListener('click', () => setMobileMode('sale', true, true));
  if (bRecv) bRecv.addEventListener('click', () => setMobileMode('recv', true, true));

  const clrRecv = $('#clearRecv');
  if (clrRecv) {
    clrRecv.addEventListener('click', () => {
      state.recvList = [];
      localStorage.removeItem('librairie_mobile_recv_list');
      renderRecv();
    });
  }

  const btnValRecv = $('#btnValidateRecv');
  if (btnValRecv) {
    btnValRecv.addEventListener('click', async () => {
      if (!state.currentUser) return openUserModal();
      const sel = $('#recvOwner');
      const ownerId = sel ? parseInt(sel.value) : 0;
      if (!ownerId) return toast('Veuillez sélectionner un propriétaire', 'warn');
      btnValRecv.disabled = true;
      try {
        const totalCount = state.recvList.reduce((s, i) => s + i.qty, 0);
        const ownerLabel = $('#recvOwner option:checked')?.textContent || 'Rayon';
        for (const item of state.recvList) {
          await api('/api/lots', {
            method: 'POST',
            body: {
              book_id: item.book.id,
              owner_id: ownerId,
              qty_in: item.qty,
              note: `Réception mobile par ${state.currentUser}`
            }
          });
        }
        toast(`${totalCount} exemplaire(s) entrés en stock`, 'ok');
        logMobileLiveActivity('recv_validated', `${totalCount} ex. entrés en stock`, `Propriétaire : ${ownerLabel}`, { count: totalCount });
        if (navigator.vibrate) navigator.vibrate([60, 40, 60]);
        state.recvList = [];
        localStorage.removeItem('librairie_mobile_recv_list');
        renderRecv();
      } catch (e) {
        toast(e.message, 'err');
        btnValRecv.disabled = false;
      }
    });
  }
}
"""

# =============================================================================
# 8. cart.js
# =============================================================================
MODULES["cart.js"] = """/* Librairie Mobile - Gestion du Panier, Origines, Multi-Paiement & Profil Vente */
'use strict';
import { $, el, eur, toast, beep, createStatsIcon, esc } from './core.js';
import { state } from './state.js';
import { api } from './api.js';
import { saveActiveCart, logMobileLiveActivity, clearLiveCartSync } from './network.js';
import { openUserModal } from './pairing.js';
import { openMobileBookStats } from './book_stats.js';

export function getItemOwner(item) {
  if (item.book.is_pack) return 'Cité Royale';
  if (item.lot === undefined || item.lot === null || item.lot === 'none') return 'À préciser';
  const l = (item.book.lots || []).find(x => x.id === item.lot);
  return (l && l.owner) ? l.owner.trim() : 'Autre';
}

export function getCartByOrigin() {
  const groups = {};
  for (const item of state.cart) {
    const owner = getItemOwner(item);
    if (!groups[owner]) {
      groups[owner] = { owner, items: [], total: 0, count: 0 };
    }
    groups[owner].items.push(item);
    groups[owner].total += item.qty * item.book.price;
    groups[owner].count += item.qty;
  }
  const list = Object.values(groups);
  list.sort((a, b) => {
    const aIsCR = a.owner.toLowerCase() === 'cité royale' ? 1 : 0;
    const bIsCR = b.owner.toLowerCase() === 'cité royale' ? 1 : 0;
    if (aIsCR !== bIsCR) return bIsCR - aIsCR;
    const aIsICC = a.owner.toLowerCase().includes('icc') ? 1 : 0;
    const bIsICC = b.owner.toLowerCase().includes('icc') ? 1 : 0;
    return bIsICC - aIsICC;
  });
  return list;
}

export function getDefaultPaymentForOwner(owner) {
  const ow = (owner || '').toLowerCase();
  if (ow === 'cité royale') return 'CB';
  return 'Espèces';
}

export function lotRemaining(item) {
  if (item.book.is_pack) return item.book.stock != null ? item.book.stock : 0;
  if (item.lot === undefined || item.lot === null || item.lot === 'none') return 0;
  const l = (item.book.lots || []).find(x => x.id === item.lot);
  return l ? l.remaining : 0;
}

export function defaultLotForBook(book) {
  const lots = (book.lots || []).filter(l => l.remaining > 0);
  if (!lots.length) return undefined;
  if (lots.length === 1) return lots[0].id;
  const cr = lots.find(l => (l.owner || '').trim().toLowerCase() === 'cité royale');
  return cr ? cr.id : lots[0].id;
}

export function checkAndShowPackUpsell(book) {
  const packs = (book.suggested_packs || []).filter(p => p.saving > 0);
  if (!packs.length) {
    hidePackUpsell();
    return;
  }
  const pack = packs.find(p => p.stock > 0) || packs[0];
  state.currentUpsellContext = { singleBook: book, pack };

  const card = $('#packUpsellCard');
  if (!card) return;
  $('#packUpsellTitle').textContent = pack.title;
  $('#packUpsellOldPrice').textContent = eur(pack.separate_price);
  $('#packUpsellPrice').textContent = eur(pack.price);
  $('#packUpsellOther').textContent = pack.other_items || 'Articles du pack';
  $('#packUpsellSavingBadge').textContent = `Éco ${eur(pack.saving)}`;
  card.style.display = 'block';
}

export function hidePackUpsell() {
  state.currentUpsellContext = null;
  const card = $('#packUpsellCard');
  if (card) card.style.display = 'none';
}

export function addPackToCart(pack) {
  const stock = pack.stock != null ? pack.stock : 0;
  if (stock <= 0) {
    toast(`Stock épuisé (0 dispo) pour ce pack. Vente impossible.`, 'err');
    return;
  }
  beep();
  const ex = state.cart.find(i => i.book.id === pack.id);
  if (ex) {
    if (ex.qty + 1 > stock) toast(`Stock maximum atteint (${stock} ex.) pour ce pack`, 'warn');
    else ex.qty++;
  } else {
    state.cart.push({ book: pack, qty: 1, lot: 'pack' });
  }
  toast('Pack ajouté : ' + pack.title);
  saveActiveCart({ type: 'pack_added', title: pack.title, price: pack.price });
  renderCart();
}

export function addToCart(book) {
  if (book.is_pack) {
    addPackToCart(book);
    return;
  }
  const totalStock = (book.lots || []).filter(l => l.remaining > 0).reduce((s, l) => s + l.remaining, 0);
  if (totalStock <= 0) {
    toast(`Stock épuisé (0 ex. disponible) pour « ${book.title} ». Vente impossible.`, 'err');
    return;
  }
  beep();
  const defLot = defaultLotForBook(book);
  const ex = state.cart.find(i => i.book.id === book.id && (i.lot === defLot || i.lot === undefined));
  if (ex) {
    if (ex.lot === undefined && defLot !== undefined) ex.lot = defLot;
    if (ex.qty + 1 > lotRemaining(ex)) {
      toast(`Stock disponible atteint (${lotRemaining(ex)} ex.) pour « ${book.title} ».`, 'warn');
      return;
    }
    ex.qty++;
  } else {
    state.cart.push({ book, qty: 1, lot: defLot });
  }
  toast('Ajouté : ' + book.title);
  saveActiveCart({ type: 'book_added', title: book.title, price: book.price });
  renderCart();
  checkAndShowPackUpsell(book);
}

export function openMultiPayModal(owner, total) {
  state.activeMpOwner = owner;
  state.activeMpTotal = total;
  const badge = $('#mpOriginBadge');
  if (badge) badge.textContent = owner;
  const tVal = $('#mpTotalVal');
  if (tVal) tVal.textContent = eur(total);
  
  if ((owner || '').toLowerCase() === 'cité royale') {
    state.mpMode1 = 'CB';
    state.mpMode2 = 'Espèces';
  } else {
    state.mpMode1 = 'Espèces';
    state.mpMode2 = 'CB';
  }

  const existing = state.originPayments[owner]?.parts;
  if (existing && existing.length >= 2) {
    state.mpMode1 = existing[0].payment;
    state.mpMode2 = existing[1].payment;
    $('#mpAmount1').value = existing[0].amount.toFixed(2);
    $('#mpAmount2').value = existing[1].amount.toFixed(2);
  } else {
    const half = Math.round((total / 2) * 100) / 100;
    $('#mpAmount1').value = half.toFixed(2);
    $('#mpAmount2').value = (Math.round((total - half) * 100) / 100).toFixed(2);
  }

  renderMpModes();
  updateMpCalculations();
  $('#multiPayModal').hidden = false;
}

export function closeMultiPayModal() {
  $('#multiPayModal').hidden = true;
  state.activeMpOwner = null;
}

export function renderMpModes() {
  const m1El = $('#mpModes1');
  const m2El = $('#mpModes2');
  if (!m1El || !m2El) return;
  const available = state.payOptions.length ? state.payOptions : ['Espèces', 'CB', 'Wero'];
  
  m1El.replaceChildren(...available.map(p => el('button', {
    type: 'button',
    class: 'chip' + (state.mpMode1 === p ? ' on' : ''),
    style: 'flex:1;justify-content:center;padding:5px 4px;font-size:11.5px',
    onclick: () => {
      state.mpMode1 = p;
      if (state.mpMode2 === p) {
        const other = available.find(x => x !== p);
        if (other) state.mpMode2 = other;
      }
      renderMpModes();
      updateMpCalculations();
    }
  }, p)));

  m2El.replaceChildren(...available.map(p => el('button', {
    type: 'button',
    class: 'chip' + (state.mpMode2 === p ? ' on' : ''),
    style: 'flex:1;justify-content:center;padding:5px 4px;font-size:11.5px',
    onclick: () => {
      state.mpMode2 = p;
      if (state.mpMode1 === p) {
        const other = available.find(x => x !== p);
        if (other) state.mpMode1 = other;
      }
      renderMpModes();
      updateMpCalculations();
    }
  }, p)));
}

export function updateMpCalculations() {
  const a1 = parseFloat($('#mpAmount1').value) || 0;
  const rem = Math.max(0, Math.round((state.activeMpTotal - a1) * 100) / 100);
  $('#mpAmount2').value = rem.toFixed(2);
  $('#mpRemainderBadge').textContent = 'Complément : ' + eur(rem);

  const btnApply = $('#btnApplyMultiPay');
  const hint = $('#mpHint');
  
  if (a1 <= 0) {
    btnApply.disabled = true;
    hint.textContent = 'Le 1er montant doit être supérieur à 0 €';
  } else if (rem <= 0) {
    btnApply.disabled = true;
    hint.textContent = 'Le 1er montant ne peut pas dépasser le total';
  } else if (state.mpMode1 === state.mpMode2) {
    btnApply.disabled = true;
    hint.textContent = 'Choisissez deux modes différents';
  } else {
    btnApply.disabled = false;
    hint.textContent = '';
  }
}

export function renderCart() {
  const count = state.cart.reduce((s, i) => s + i.qty, 0);
  const total = state.cart.reduce((s, i) => s + i.qty * i.book.price, 0);
  $('#cartCount').textContent = count;
  $('#totalVal').textContent = eur(total);
  updateMobileStandbyUI();

  const list = $('#cartItems');
  if (!state.cart.length) {
    list.replaceChildren(el('div', { class: 'muted', style: 'text-align:center;padding:18px', text: 'Visez le code-barres d\\'un livre pour commencer.' }));
  } else {
    list.replaceChildren(...state.cart.map((item, idx) => {
      const b = item.book;
      if (b.is_pack) {
        return el('div', { class: 'cart-item pack-cart-item' },
          el('div', { class: 'ci-top' },
            el('div', {},
              el('div', { class: 'ci-title' },
                el('span', { class: 'badge b-pack', style: 'background:linear-gradient(135deg, #9333ea, #c026d3);color:#fff;font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;margin-right:6px' }, 'PACK'),
                b.title
              ),
              el('div', { class: 'muted', style: 'font-size:11.5px;margin-top:2px' },
                `${eur(b.price)} / pack · ${(b.items || []).map(i => i.title).join(' + ')}`
              )
            ),
            el('div', { class: 'qty' },
              el('button', { type: 'button', text: '−', onclick: () => {
                item.qty--;
                const isRemoved = item.qty <= 0;
                if (isRemoved) state.cart.splice(idx, 1);
                saveActiveCart(isRemoved ? { type: 'book_removed', title: b.title } : { type: 'book_qty', title: b.title, qty: item.qty });
                renderCart();
              } }),
              el('b', { text: item.qty }),
              el('button', { type: 'button', text: '+', onclick: () => {
                if (item.qty + 1 > (b.stock || 999)) toast('Stock pack atteint', 'warn');
                else {
                  item.qty++;
                  saveActiveCart({ type: 'book_qty', title: b.title, qty: item.qty });
                  renderCart();
                }
              } })
            )
          ),
          el('div', { class: 'lots', style: 'display:flex;align-items:center;justify-content:space-between;padding:3px 0' },
            el('span', { style: 'font-size:11px;color:#c084fc;font-weight:600', text: `📦 Composition : ${b.items ? b.items.length : 2} livres groupés (Cité Royale)` }),
            el('button', {
              class: 'chip btn-m-stats',
              type: 'button',
              title: 'Statistiques du pack',
              onclick: (e) => { e.stopPropagation(); openMobileBookStats(b.id); }
            },
              createStatsIcon(),
              el('span', { text: 'Stats' })
            )
          )
        );
      }
      const availableLots = (b.lots || []).filter(l => l.remaining > 0);
      const lots = availableLots.map(l => el('button', {
        class: 'chip' + (item.lot === l.id ? ' on' : ''), type: 'button',
        onclick: () => { item.lot = l.id; item.qty = Math.min(item.qty, l.remaining); renderCart(); }
      }, el('i', { style: 'background:' + (/^#[0-9a-fA-F]{3,8}$/.test(l.color || '') ? l.color : '#8892b0') }),
         `${l.owner} · dispo ${l.remaining}`));
      if (!availableLots.length) {
        lots.push(el('span', { class: 'chip', style: 'border-color:var(--bad);color:var(--bad);cursor:default', text: 'Stock épuisé (0 dispo)' }));
      }
      lots.push(el('button', {
        class: 'chip btn-m-stats',
        type: 'button',
        title: 'Statistiques & tendances de vente',
        onclick: (e) => { e.stopPropagation(); openMobileBookStats(b.id); }
      },
        createStatsIcon(),
        el('span', { text: 'Stats' })
      ));
      return el('div', { class: 'cart-item' + (item.lot === undefined ? ' todo' : '') },
        el('div', { class: 'ci-top' },
          el('div', {}, el('div', { class: 'ci-title', text: b.title + (b.volume ? ' · Vol. ' + b.volume : '') }),
            el('div', { class: 'muted', text: eur(b.price) + ' / unité' })),
          el('div', { class: 'qty' },
            el('button', { type: 'button', text: '−', onclick: () => {
              item.qty--;
              const isRemoved = item.qty <= 0;
              if (isRemoved) state.cart.splice(idx, 1);
              saveActiveCart(isRemoved ? { type: 'book_removed', title: b.title } : { type: 'book_qty', title: b.title, qty: item.qty });
              renderCart();
            } }),
            el('b', { text: item.qty }),
            el('button', { type: 'button', text: '+', onclick: () => {
              const maxAvail = lotRemaining(item);
              if (item.qty + 1 > maxAvail) {
                toast(`Stock maximum atteint (${maxAvail} ex.) pour ce lot`, 'warn');
              } else {
                item.qty++;
                saveActiveCart({ type: 'book_qty', title: b.title, qty: item.qty });
                renderCart();
              }
            } }))),
        el('div', { class: 'lots' }, lots),
        item.lot === undefined ? el('div', { class: 'hint', text: 'Touchez l\\'origine de cet exemplaire' }) : null);
    }));
  }

  const origins = getCartByOrigin();
  const singleRow = $('#singleOriginRow');
  const splitCont = $('#splitOriginsContainer');
  const payChipsEl = $('#payChips');
  const availablePays = state.payOptions.length ? state.payOptions : ['Espèces', 'CB', 'Wero'];

  const validOwners = new Set(origins.map(o => o.owner));
  for (const k of Object.keys(state.originPayments)) {
    if (k !== '_default' && !validOwners.has(k)) {
      delete state.originPayments[k];
    }
  }

  const fAmt = a => (a % 1 === 0 ? a.toFixed(0) : a.toFixed(2).replace('.', ',')) + ' €';
  const fPay = p => (p === 'Espèces' ? 'Esp.' : p);

  if (origins.length <= 1) {
    if (singleRow) singleRow.style.display = 'block';
    if (splitCont) splitCont.style.display = 'none';

    const currentOwner = origins[0] ? origins[0].owner : '_default';
    if (!state.originPayments[currentOwner]) {
      state.originPayments[currentOwner] = { method: getDefaultPaymentForOwner(currentOwner), parts: null };
    }
    const currentPay = state.originPayments[currentOwner];

    if (currentPay.parts && currentPay.parts.length >= 2) {
      const sumParts = currentPay.parts.reduce((s, p) => s + p.amount, 0);
      if (Math.abs(sumParts - total) > 0.01) {
        currentPay.parts = null;
      }
    }

    if (payChipsEl) {
      const chips = availablePays.map(p => el('button', {
        type: 'button',
        class: 'chip' + (!currentPay.parts && currentPay.method === p ? ' on' : ''),
        style: 'flex:1;justify-content:center;padding:7px 2px;font-size:12px;white-space:nowrap',
        onclick: () => {
          state.originPayments[currentOwner] = { method: p, parts: null };
          saveActiveCart({ type: 'payment_selected', method: p, owner: currentOwner });
          renderCart();
        }
      }, p));

      const mpSumm = $('#multiPaySummary');
      if (currentPay.parts && currentPay.parts.length >= 2) {
        const p1 = currentPay.parts[0];
        const p2 = currentPay.parts[1];
        const mpText = `⚡ ${fAmt(p1.amount)} ${fPay(p1.payment)} + ${fAmt(p2.amount)} ${fPay(p2.payment)} ✎`;
        if (mpSumm) {
          mpSumm.textContent = mpText;
          mpSumm.style.display = 'inline-flex';
          mpSumm.onclick = () => openMultiPayModal(currentOwner, total);
        }
        chips.push(el('button', {
          type: 'button',
          class: 'chip multi-on',
          style: 'flex:1;justify-content:center;padding:7px 2px;font-size:12px;white-space:nowrap',
          title: 'Modifier le paiement combiné : ' + mpText,
          onclick: () => openMultiPayModal(currentOwner, total)
        }, '✓ Multi'));
      } else {
        if (mpSumm) mpSumm.style.display = 'none';
        chips.push(el('button', {
          type: 'button',
          class: 'chip',
          style: 'flex:1;justify-content:center;padding:7px 2px;font-size:12px;white-space:nowrap;color:var(--mut)',
          title: 'Combiner deux modes de paiement',
          onclick: () => {
            if (!total) return toast('Ajoutez d\\'abord un livre au panier', 'warn');
            openMultiPayModal(currentOwner, total);
          }
        }, '＋ Multi'));
      }
      payChipsEl.replaceChildren(...chips);
    }
    $('#btnValidate').textContent = total > 0 ? `Valider (${eur(total)})` : 'Valider';
  } else {
    if (singleRow) singleRow.style.display = 'none';
    const mpSumm = $('#multiPaySummary');
    if (mpSumm) mpSumm.style.display = 'none';
    if (splitCont) splitCont.style.display = 'flex';

    if (splitCont) {
      splitCont.replaceChildren(...origins.map(g => {
        if (!state.originPayments[g.owner]) {
          state.originPayments[g.owner] = { method: getDefaultPaymentForOwner(g.owner), parts: null };
        }
        const payState = state.originPayments[g.owner];
        if (payState.parts && payState.parts.length >= 2) {
          const sumParts = payState.parts.reduce((s, p) => s + p.amount, 0);
          if (Math.abs(sumParts - g.total) > 0.01) {
            payState.parts = null;
          }
        }

        const isCR = g.owner.toLowerCase() === 'cité royale';
        const isICC = g.owner.toLowerCase().includes('icc');
        const cardClass = isCR ? 'split-card cr' : isICC ? 'split-card icc' : 'split-card other';
        const icon = isCR ? '🏰 ' : isICC ? '🕊️ ' : '📦 ';

        const chips = availablePays.map(p => el('button', {
          type: 'button',
          class: 'chip' + (!payState.parts && payState.method === p ? ' on' : ''),
          style: 'flex:1;justify-content:center;padding:5px 2px;font-size:11.5px;white-space:nowrap',
          onclick: () => {
            state.originPayments[g.owner] = { method: p, parts: null };
            saveActiveCart({ type: 'payment_selected', method: p, owner: g.owner });
            renderCart();
          }
        }, p));

        if (payState.parts && payState.parts.length >= 2) {
          chips.push(el('button', {
            type: 'button',
            class: 'chip multi-on',
            style: 'flex:1;justify-content:center;padding:5px 2px;font-size:11.5px;white-space:nowrap',
            title: 'Modifier le paiement combiné',
            onclick: () => openMultiPayModal(g.owner, g.total)
          }, '✓ Multi'));
        } else {
          chips.push(el('button', {
            type: 'button',
            class: 'chip',
            style: 'flex:1;justify-content:center;padding:5px 2px;font-size:11.5px;white-space:nowrap;color:var(--mut)',
            onclick: () => openMultiPayModal(g.owner, g.total)
          }, '＋ Multi'));
        }

        const headRight = el('div', {
          style: 'display:flex;align-items:center;gap:6px;cursor:' + (payState.parts ? 'pointer' : 'default'),
          onclick: payState.parts ? () => openMultiPayModal(g.owner, g.total) : null
        },
          payState.parts && payState.parts.length >= 2
            ? el('span', { style: 'font-size:10px;color:#c4b5fd;font-weight:700;background:rgba(99,102,241,0.15);border:1px solid rgba(99,102,241,0.3);border-radius:5px;padding:2px 5px;white-space:nowrap' },
                `⚡ ${fAmt(payState.parts[0].amount)} ${fPay(payState.parts[0].payment)} + ${fAmt(payState.parts[1].amount)} ${fPay(payState.parts[1].payment)} ✎`)
            : null,
          el('span', { style: 'font-size:13px;font-weight:800;color:var(--good)' }, eur(g.total))
        );

        return el('div', { class: cardClass },
          el('div', { class: 'split-head' },
            el('span', { style: 'display:flex;align-items:center;gap:4px' },
              icon + g.owner,
              el('span', { style: 'font-size:10px;color:var(--mut);font-weight:400' }, `(${g.count} ex.)`)),
            headRight),
          el('div', { class: 'split-chips' }, chips));
      }));
    }
    $('#btnValidate').textContent = `Valider les ${origins.length} ventes (${eur(total)})`;
  }

  const missingLot = state.cart.some(i => i.lot === undefined);
  const missingPay = origins.some(g => !state.originPayments[g.owner] || (!state.originPayments[g.owner].method && !state.originPayments[g.owner].parts));
  $('#btnValidate').disabled = !state.cart.length || missingLot || missingPay;
  $('#validHint').textContent = !state.cart.length ? '' : missingLot ? 'Choisissez l\\'origine de chaque livre' : missingPay ? 'Choisissez le mode de paiement' : '';
  saveActiveCart();
}

export function updateMobileStandbyUI() {
  const raw = localStorage.getItem('librairie_mobile_standby_cart');
  const banner = $('#mStandbyBanner');
  const info = $('#mStandbyBannerInfo');
  const btnStby = $('#mBtnStandby');
  if (!banner || !btnStby) return;

  if (raw) {
    try {
      const data = JSON.parse(raw);
      banner.style.display = 'flex';
      if (info) info.textContent = `${data.qty || 0} livre${(data.qty || 0) > 1 ? 's' : ''} · ${data.total || '0,00 €'}`;
      btnStby.style.display = 'none';
    } catch (err) {
      localStorage.removeItem('librairie_mobile_standby_cart');
      banner.style.display = 'none';
      btnStby.style.display = state.cart.length > 0 ? 'inline-flex' : 'none';
    }
  } else {
    banner.style.display = 'none';
    btnStby.style.display = state.cart.length > 0 ? 'inline-flex' : 'none';
  }
}

export async function loadPayOptions() {
  try {
    const o = await api('/api/options');
    state.payOptions = (o.payment || []).map(p => (p.label === 'PayPal POS (CB)' || p.label.toLowerCase().includes('paypal') ? 'CB' : p.label));
    state.dbPublishers = (o.publisher || []).map(p => p.label);
    state.dbAuthors = o.authors || [];
    const dl = $('#dl_nb_publishers');
    if (dl && state.dbPublishers.length) {
      dl.innerHTML = state.dbPublishers.map(p => `<option value="${esc(p)}">`).join('');
    }
  } catch (e) { state.payOptions = []; }
  if (!state.payOptions.length) state.payOptions = ['Espèces', 'CB', 'Wero'];
  state.payOptions = Array.from(new Set(state.payOptions));
  renderCart();
}

let mDemoTimer = null;

export function getMobileProfileSummary() {
  const parts = [];
  if (state.mGender === 'Couple') parts.push('Couple 💜');
  else if (state.mGender) parts.push(state.mGender);

  const ageMap = {
    'Enfant / Ado': '<18 ans',
    'Jeune adulte': '18-29 ans',
    'Adulte': '30-59 ans',
    'Senior': '60+ ans'
  };
  if (state.mAge) parts.push(ageMap[state.mAge] || state.mAge);
  if (state.mStar) parts.push('⭐ STAR');
  return parts.join(' · ');
}

export function collapseMobileProfile() {
  const cardExp = $('#mDemoCardExpanded');
  const cardCol = $('#mDemoCardCollapsed');
  const sumTxt = $('#mDemoSummaryText');
  if (!cardExp || !cardCol) return;
  const summary = getMobileProfileSummary();
  if (!summary) return;
  if (sumTxt) sumTxt.textContent = summary;
  cardExp.style.display = 'none';
  cardCol.style.display = 'flex';
}

export function expandMobileProfile() {
  if (mDemoTimer) { clearTimeout(mDemoTimer); mDemoTimer = null; }
  const cardExp = $('#mDemoCardExpanded');
  const cardCol = $('#mDemoCardCollapsed');
  if (cardExp) cardExp.style.display = 'block';
  if (cardCol) cardCol.style.display = 'none';
}

export function scheduleMobileProfileCollapse() {
  if (mDemoTimer) { clearTimeout(mDemoTimer); mDemoTimer = null; }
  saveActiveCart();
  if (!state.mGender && !state.mAge && !state.mStar) {
    expandMobileProfile();
    return;
  }
  mDemoTimer = setTimeout(() => {
    collapseMobileProfile();
  }, 5000);
}

export function updateProfileSummary() {
  if (!state.mGender && !state.mAge && !state.mStar) {
    expandMobileProfile();
  } else {
    collapseMobileProfile();
  }
}

export function initCart() {
  const mpAmt1 = $('#mpAmount1');
  if (mpAmt1) mpAmt1.addEventListener('input', updateMpCalculations);

  document.querySelectorAll('[data-mpq]').forEach(btn => {
    btn.addEventListener('click', () => {
      const q = btn.dataset.mpq;
      let val = 0;
      if (q === 'half') val = Math.round((state.activeMpTotal / 2) * 100) / 100;
      else val = parseFloat(q) || 0;
      if (val >= state.activeMpTotal) val = Math.max(1, state.activeMpTotal - 1);
      $('#mpAmount1').value = val.toFixed(2);
      updateMpCalculations();
    });
  });

  const bCancelMp = $('#btnCancelMultiPay');
  if (bCancelMp) bCancelMp.addEventListener('click', closeMultiPayModal);

  const bApplyMp = $('#btnApplyMultiPay');
  if (bApplyMp) bApplyMp.addEventListener('click', () => {
    const a1 = parseFloat($('#mpAmount1').value) || 0;
    const a2 = parseFloat($('#mpAmount2').value) || 0;
    if (!state.activeMpOwner || a1 <= 0 || a2 <= 0) return;
    state.originPayments[state.activeMpOwner] = {
      method: 'Multi',
      parts: [
        { payment: state.mpMode1, amount: a1 },
        { payment: state.mpMode2, amount: a2 }
      ]
    };
    saveActiveCart({ type: 'smart_split', owner: state.activeMpOwner, detail: `${a1.toFixed(2)} € ${state.mpMode1} + ${a2.toFixed(2)} € ${state.mpMode2}` });
    closeMultiPayModal();
    renderCart();
    toast('Cumul défini pour ' + state.activeMpOwner);
  });

  $('#clearCart').addEventListener('click', () => {
    state.cart = [];
    state.originPayments = {};
    hidePackUpsell();
    state.mGender = ''; state.mAge = ''; state.mStar = 0;
    const sBtn = $('#mBtnStar'); if (sBtn) sBtn.classList.remove('on');
    const gEl = $('#mDemoGender');
    if (gEl) {
      gEl.classList.remove('is-couple');
      gEl.querySelectorAll('button').forEach(b => b.classList.remove('on'));
      const cb = $('#mCoupleBadge'); if (cb) cb.style.display = 'none';
    }
    const aEl = $('#mDemoAge');
    if (aEl) aEl.querySelectorAll('button').forEach(b => b.classList.remove('on'));
    if (mDemoTimer) { clearTimeout(mDemoTimer); mDemoTimer = null; }
    expandMobileProfile();
    localStorage.removeItem('librairie_mobile_active_cart');
    renderCart();
  });

  const mBtnStandby = $('#mBtnStandby');
  if (mBtnStandby) {
    mBtnStandby.addEventListener('click', () => {
      if (!state.cart.length) return;
      const count = state.cart.reduce((s, i) => s + i.qty, 0);
      const total = state.cart.reduce((s, i) => s + i.qty * i.book.price, 0);
      const standbyData = {
        cart: JSON.parse(JSON.stringify(state.cart)),
        originPayments: JSON.parse(JSON.stringify(state.originPayments)),
        gender: state.mGender,
        age: state.mAge,
        star: state.mStar,
        total: eur(total),
        qty: count,
        timestamp: Date.now()
      };
      localStorage.setItem('librairie_mobile_standby_cart', JSON.stringify(standbyData));
      localStorage.removeItem('librairie_mobile_active_cart');
      clearLiveCartSync('standby_saved');
      logMobileLiveActivity('standby_saved', 'Panier mis en attente', `${count} articles · ${eur(total)}`, { count, total });

      state.cart = [];
      state.originPayments = {};
      hidePackUpsell();
      state.mGender = ''; state.mAge = ''; state.mStar = 0;
      const mStarBtn = $('#mBtnStar'); if (mStarBtn) mStarBtn.classList.remove('on');
      const mGenEl = $('#mDemoGender');
      if (mGenEl) {
        mGenEl.classList.remove('is-couple');
        mGenEl.querySelectorAll('button').forEach(b => b.classList.remove('on'));
        const cb = $('#mCoupleBadge'); if (cb) cb.style.display = 'none';
      }
      const mAgeEl = $('#mDemoAge');
      if (mAgeEl) mAgeEl.querySelectorAll('button').forEach(b => b.classList.remove('on'));
      if (mDemoTimer) { clearTimeout(mDemoTimer); mDemoTimer = null; }
      expandMobileProfile();

      renderCart();
      toast("Panier mis en attente. Caisse mobile libre pour le client suivant !");
    });
  }

  const mBtnResumeStandby = $('#mBtnResumeStandby');
  if (mBtnResumeStandby) {
    mBtnResumeStandby.addEventListener('click', () => {
      const raw = localStorage.getItem('librairie_mobile_standby_cart');
      if (!raw) return;
      if (state.cart.length > 0) {
        if (!confirm("Un panier est déjà en cours. Voulez-vous le remplacer par le panier en attente ?")) return;
      }
      try {
        const data = JSON.parse(raw);
        state.cart = data.cart || [];
        state.originPayments = data.originPayments || {};
        state.mGender = data.gender || '';
        state.mAge = data.age || '';
        state.mStar = data.star || 0;

        const mStarBtn = $('#mBtnStar'); if (mStarBtn) mStarBtn.classList.toggle('on', !!state.mStar);
        const mGenEl = $('#mDemoGender');
        if (mGenEl) {
          mGenEl.classList.toggle('is-couple', state.mGender === 'Couple');
          mGenEl.querySelector('button[data-g="Femme"]')?.classList.toggle('on', state.mGender === 'Femme' || state.mGender === 'Couple');
          mGenEl.querySelector('button[data-g="Homme"]')?.classList.toggle('on', state.mGender === 'Homme' || state.mGender === 'Couple');
          const cb = $('#mCoupleBadge'); if (cb) cb.style.display = state.mGender === 'Couple' ? 'block' : 'none';
        }
        const mAgeEl = $('#mDemoAge');
        if (mAgeEl) {
          mAgeEl.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.a === state.mAge));
        }
        if (state.mGender || state.mAge || state.mStar) collapseMobileProfile(); else expandMobileProfile();

        localStorage.removeItem('librairie_mobile_standby_cart');
        saveActiveCart({ type: 'standby_resumed', count: state.cart.length });
        renderCart();
        toast("Panier précédent repris avec succès !");
      } catch (err) {
        toast("Erreur lors de la reprise du panier : " + err.message, "err");
      }
    });
  }

  const mBtnDiscardStandby = $('#mBtnDiscardStandby');
  if (mBtnDiscardStandby) {
    mBtnDiscardStandby.addEventListener('click', () => {
      if (confirm("Supprimer définitivement ce panier en attente ?")) {
        localStorage.removeItem('librairie_mobile_standby_cart');
        updateMobileStandbyUI();
        toast("Panier en attente supprimé.");
      }
    });
  }

  const btnConvert = $('#btnConvertPack');
  if (btnConvert) {
    btnConvert.addEventListener('click', () => {
      if (!state.currentUpsellContext) return;
      const { singleBook, pack } = state.currentUpsellContext;
      const idx = state.cart.findIndex(i => i.book.id === singleBook.id);
      if (idx !== -1) {
        if (state.cart[idx].qty > 1) {
          state.cart[idx].qty--;
        } else {
          state.cart.splice(idx, 1);
        }
      }
      addPackToCart(pack);
      toast(`✓ Converti en ${pack.title} (-${eur(pack.saving)} d\\'économie) !`);
      if (navigator.vibrate) navigator.vibrate([80, 50, 80]);
      hidePackUpsell();
    });
  }

  const btnCloseUpsell = $('#btnClosePackUpsell');
  if (btnCloseUpsell) {
    btnCloseUpsell.addEventListener('click', () => {
      hidePackUpsell();
    });
  }

  const mCardCol = $('#mDemoCardCollapsed');
  if (mCardCol) {
    mCardCol.onclick = () => {
      expandMobileProfile();
    };
  }

  const mStarBtn = $('#mBtnStar');
  if (mStarBtn) {
    mStarBtn.addEventListener('click', () => {
      state.mStar = state.mStar ? 0 : 1;
      mStarBtn.classList.toggle('on', !!state.mStar);
      scheduleMobileProfileCollapse();
      saveActiveCart({ type: 'profile_star', star: !!state.mStar });
    });
  }

  const mGenEl = $('#mDemoGender');
  if (mGenEl) {
    mGenEl.addEventListener('click', e => {
      const b = e.target.closest('button[data-g]');
      if (b) {
        b.classList.toggle('on');
        const fOn = mGenEl.querySelector('button[data-g="Femme"]')?.classList.contains('on');
        const hOn = mGenEl.querySelector('button[data-g="Homme"]')?.classList.contains('on');
        const cBadge = $('#mCoupleBadge');
        if (fOn && hOn) {
          state.mGender = 'Couple';
          mGenEl.classList.add('is-couple');
          if (cBadge) cBadge.style.display = 'block';
        } else if (fOn) {
          state.mGender = 'Femme';
          mGenEl.classList.remove('is-couple');
          if (cBadge) cBadge.style.display = 'none';
        } else if (hOn) {
          state.mGender = 'Homme';
          mGenEl.classList.remove('is-couple');
          if (cBadge) cBadge.style.display = 'none';
        } else {
          state.mGender = '';
          mGenEl.classList.remove('is-couple');
          if (cBadge) cBadge.style.display = 'none';
        }
        scheduleMobileProfileCollapse();
        saveActiveCart({ type: 'profile_gender', gender: state.mGender });
      }
    });
  }

  const mAgeEl = $('#mDemoAge');
  if (mAgeEl) {
    mAgeEl.addEventListener('click', e => {
      const b = e.target.closest('button[data-a]');
      if (b) {
        const isAlreadyOn = b.classList.contains('on');
        mAgeEl.querySelectorAll('button').forEach(btn => btn.classList.remove('on'));
        if (isAlreadyOn) {
          state.mAge = '';
        } else {
          b.classList.add('on');
          state.mAge = b.dataset.a;
        }
        scheduleMobileProfileCollapse();
        saveActiveCart({ type: 'profile_age', age: state.mAge });
      }
    });
  }

  $('#btnValidate').addEventListener('click', async () => {
    if (!state.currentUser) return openUserModal();
    const btn = $('#btnValidate');
    btn.disabled = true;
    
    const origins = getCartByOrigin();
    if (!origins.length) {
      btn.disabled = false;
      return;
    }

    const unassigned = state.cart.find(i => !i.book.is_pack && (i.lot === undefined || i.lot === null || i.lot === 'none'));
    if (unassigned) {
      toast(`Indiquez l\\'origine en stock pour « ${unassigned.book.title} » avant d\\'encaisser.`, 'warn');
      btn.disabled = false;
      return;
    }

    const zeroStock = state.cart.find(i => lotRemaining(i) < i.qty);
    if (zeroStock) {
      toast(`Stock insuffisant pour « ${zeroStock.book.title} » (${zeroStock.qty} demandés, ${lotRemaining(zeroStock)} dispo).`, 'err');
      btn.disabled = false;
      return;
    }

    try {
      const validatedSales = [];
      for (let idx = 0; idx < origins.length; idx++) {
        const g = origins[idx];
        const payState = state.originPayments[g.owner] || { method: 'Espèces', parts: null };
        const lines = g.items.map(i => {
          if (i.book.is_pack) {
            const allocs = [];
            for (const comp of (i.book.items || [])) {
              const compLots = (comp.lots || []).filter(l => l.remaining > 0);
              let chosenLot = compLots.find(l => (l.owner || '').trim().toLowerCase() === 'cité royale');
              if (!chosenLot && compLots.length) chosenLot = compLots[0];
              if (!chosenLot) {
                throw new Error(`Stock épuisé pour le composant « ${comp.title || comp.book_id} » du pack`);
              }
              allocs.push({
                book_id: comp.book_id,
                lot_id: chosenLot.id,
                qty: i.qty * (comp.qty || 1)
              });
            }
            return {
              book_id: i.book.id,
              qty: i.qty,
              unit_price: i.book.price,
              allocations: allocs
            };
          } else {
            return {
              book_id: i.book.id,
              qty: i.qty,
              unit_price: i.book.price,
              allocations: [{ book_id: i.book.id, lot_id: +i.lot, qty: i.qty }]
            };
          }
        });

        const payload = {
          payment: payState.parts ? payState.parts.map(p => `${p.amount.toFixed(2)} € ${p.payment}`).join(' + ') : payState.method,
          payments: payState.parts || null,
          note: origins.length > 1 ? `Vente mobile (${g.owner})` : 'Vente mobile',
          customer_gender: state.mGender || null,
          customer_age_group: state.mAge || null,
          is_star: state.mStar ? 1 : 0,
          service_moment: state.mMoment || null,
          lines
        };

        try {
          const res = await api('/api/sales', { method: 'POST', body: payload });
          validatedSales.push({ id: res.id, owner: g.owner, total: res.total });
          state.cart = state.cart.filter(item => getItemOwner(item) !== g.owner);
        } catch (err) {
          toast(`Erreur sur vente ${g.owner} : ${err.message}`, 'err');
          renderCart();
          btn.disabled = false;
          return;
        }
      }

      if (validatedSales.length === 1) {
        toast('Vente enregistrée : ' + eur(validatedSales[0].total));
      } else {
        toast(`✓ ${validatedSales.length} ventes validées : ` + validatedSales.map(v => `${eur(v.total)} (${v.owner})`).join(' + '));
      }

      if (navigator.vibrate) navigator.vibrate([60, 40, 60]);

      state.cart = [];
      state.originPayments = {};
      hidePackUpsell();
      state.mGender = ''; state.mAge = ''; state.mStar = 0;
      localStorage.removeItem('librairie_mobile_active_cart');
      if (mStarBtn) mStarBtn.classList.remove('on');
      if (mGenEl) {
        mGenEl.classList.remove('is-couple');
        mGenEl.querySelectorAll('button').forEach(b => b.classList.remove('on'));
        const cb = $('#mCoupleBadge'); if (cb) cb.style.display = 'none';
      }
      if (mAgeEl) mAgeEl.querySelectorAll('button').forEach(b => b.classList.remove('on'));
      updateProfileSummary();
    } catch (e) {
      toast(e.message, 'err');
    } finally {
      renderCart();
    }
  });
}
"""

# =============================================================================
# 9. new_book_modal.js
# =============================================================================
MODULES["new_book_modal.js"] = """/* Librairie Mobile - Modale Fiche Nouveau Livre & Vérification BDD */
'use strict';
import { $, el, eur, toast, esc, updateViewportHeight } from './core.js';
import { state } from './state.js';
import { api } from './api.js';
import { addToCart } from './cart.js';
import { addToRecv } from './modes.js';
import { closeMobileBookStats } from './book_stats.js';
import { closeMultiPayModal } from './cart.js';

export function levenshteinDist(s1, s2) {
  const m = s1.length, n = s2.length;
  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = 0; i <= m; i++) dp[i][0] = i;
  for (let j = 0; j <= n; j++) dp[0][j] = j;
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      const cost = s1[i - 1] === s2[j - 1] ? 0 : 1;
      dp[i][j] = Math.min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost);
    }
  }
  return dp[m][n];
}

export function stringSimilarity(s1, s2) {
  if (!s1 || !s2) return 0;
  s1 = s1.toLowerCase().trim();
  s2 = s2.toLowerCase().trim();
  if (s1 === s2) return 1.0;
  const maxLen = Math.max(s1.length, s2.length);
  if (maxLen === 0) return 1.0;
  return (maxLen - levenshteinDist(s1, s2)) / maxLen;
}

export function checkFieldBdd(inputId, badgeId, suggestionId, canonicalList) {
  const input = $(inputId);
  const badge = $(badgeId);
  const sugg = $(suggestionId);
  if (!input) return;
  const val = input.value.trim();
  if (!val) {
    if (badge) badge.style.display = 'none';
    if (sugg) sugg.style.display = 'none';
    input.classList.remove('field-in-bdd');
    return;
  }
  const normVal = val.toLowerCase();
  const exact = (canonicalList || []).find(c => c && c.toLowerCase() === normVal);
  if (exact) {
    if (badge) {
      badge.textContent = '✓ BDD';
      badge.style.display = 'inline-flex';
    }
    if (sugg) sugg.style.display = 'none';
    input.classList.add('field-in-bdd');
    return;
  }
  input.classList.remove('field-in-bdd');
  if (badge) badge.style.display = 'none';

  let bestMatch = null, bestScore = 0;
  for (const item of (canonicalList || [])) {
    if (!item) continue;
    const score = stringSimilarity(val, item);
    if (score >= 0.72 && score > bestScore) {
      bestScore = score;
      bestMatch = item;
    }
  }
  if (bestMatch && sugg) {
    sugg.innerHTML = `<span class="typo-suggestion">💡 Suggestion BDD : <b>${esc(bestMatch)}</b> <span style="font-size:10px;opacity:0.8">(Cliquer pour corriger)</span></span>`;
    sugg.style.display = 'block';
    sugg.onclick = () => {
      input.value = bestMatch;
      checkFieldBdd(inputId, badgeId, suggestionId, canonicalList);
      toast(`Orthographe BDD appliquée : ${bestMatch}`, 'ok');
    };
  } else if (sugg) {
    sugg.style.display = 'none';
  }
}

export function triggerAllBddChecks() {
  checkFieldBdd('#nbAuthor', '#nbAuthorBddBadge', '#nbAuthorTypoSuggestion', state.dbAuthors);
  checkFieldBdd('#nbPublisher', '#nbPublisherBddBadge', '#nbPublisherTypoSuggestion', state.dbPublishers);
  const codeVal = $('#nbCode') ? $('#nbCode').value.trim() : '';
  if (codeVal) checkCodeInCatalog(codeVal);
  else hideExistingBookBanner();
}

export async function checkCodeInCatalog(code) {
  if (!code) {
    hideExistingBookBanner();
    return;
  }
  try {
    const book = await api('/api/books/scan/' + encodeURIComponent(code));
    if (book && book.id) {
      showExistingBookBanner(book);
    } else {
      hideExistingBookBanner();
    }
  } catch (e) {
    hideExistingBookBanner();
  }
}

export function showExistingBookBanner(b) {
  state.currentMatchedBook = b;
  const banner = $('#nbBookExistsBanner');
  const title = $('#nbExistsTitle');
  const badge = $('#nbExistsStockBadge');
  const codeBadge = $('#nbCodeBddBadge');
  if (!banner) return;
  title.textContent = `${b.title}${b.author ? ' · ' + b.author : ''} (${eur(b.price)})`;
  if (badge) badge.textContent = `Stock actuel : ${b.stock ?? 0} ex.`;
  if (codeBadge) {
    codeBadge.textContent = `✓ En base (${b.stock ?? 0} ex.)`;
    codeBadge.style.display = 'inline-flex';
  }
  banner.style.display = 'block';

  const addStockBtn = $('#nbBtnAddToStock');
  if (addStockBtn) {
    addStockBtn.onclick = () => {
      if (state.currentMode === 'recv') {
        addToRecv(b);
        toast(`📦 ${b.title} ajouté au carton de réception !`, 'ok');
      } else {
        addToCart(b);
        toast(`🛒 ${b.title} ajouté au panier !`, 'ok');
      }
      closeNewBookModal();
    };
  }

  const applyBtn = $('#nbBtnApplyMatch');
  if (applyBtn) {
    applyBtn.onclick = () => {
      $('#nbTitle').value = b.title;
      if (b.author) $('#nbAuthor').value = b.author;
      if (b.publisher && $('#nbPublisher')) $('#nbPublisher').value = b.publisher;
      if (b.price != null && b.price > 0) $('#nbPrice').value = b.price;
      banner.style.display = 'none';
      toast('Fiche officielle du livre appliquée !', 'ok');
      triggerAllBddChecks();
    };
  }
}

export function hideExistingBookBanner() {
  state.currentMatchedBook = null;
  const banner = $('#nbBookExistsBanner');
  if (banner) banner.style.display = 'none';
  const codeBadge = $('#nbCodeBddBadge');
  if (codeBadge) codeBadge.style.display = 'none';
}

export function toSentenceCase(str) {
  if (!str) return '';
  str = str.trim();
  if (!str) return '';
  const stopwords = new Set([
    'de', 'du', 'des', 'le', 'la', 'les', 'un', 'une', 'et', 'en', 'au', 'aux',
    'par', 'pour', 'sur', 'dans', 'a', 'd', 'l', 'ou', 'avec', 'sans', 'sous', 'vers', 'chez'
  ]);
  const words = str.split(/\\s+/);
  const formatted = words.map((w, i) => {
    if (w.includes('-') && !w.startsWith('-') && !w.endsWith('-')) {
      return w.split('-').map((p, j) => (i === 0 && j === 0) ? p.charAt(0).toUpperCase() + p.slice(1).toLowerCase() : p.toLowerCase()).join('-');
    }
    if (w.includes("'") && !w.startsWith("'") && !w.endsWith("'")) {
      const [pre, rest] = w.split("'", 2);
      const preFmt = (i === 0) ? pre.charAt(0).toUpperCase() + pre.slice(1).toLowerCase() + "'" : pre.toLowerCase() + "'";
      const restFmt = (i === 0) ? rest.charAt(0).toUpperCase() + rest.slice(1).toLowerCase() : rest.toLowerCase();
      return preFmt + restFmt;
    }
    const low = w.toLowerCase();
    if (i === 0) return low.charAt(0).toUpperCase() + low.slice(1);
    return low;
  });
  let res = formatted.join(' ');
  res = res.replace(/([:\\.?!]\\s+)([a-zàéèêîôû])/g, (m, p1, p2) => p1 + p2.toUpperCase());
  return res.charAt(0).toUpperCase() + res.slice(1);
}

export function toTitleCase(str) {
  if (!str) return '';
  str = str.trim();
  if (!str) return '';
  const stopwords = new Set([
    'de', 'du', 'des', 'le', 'la', 'les', 'un', 'une', 'et', 'en', 'au', 'aux',
    'par', 'pour', 'sur', 'dans', 'a', 'd', 'l', 'ou', 'avec', 'sans', 'sous', 'vers', 'chez'
  ]);
  const words = str.split(/\\s+/);
  const formatted = words.map((w, i) => {
    if (w.includes('-') && !w.startsWith('-') && !w.endsWith('-')) {
      return w.split('-').map(p => stopwords.has(p.toLowerCase()) ? p.toLowerCase() : (p.charAt(0).toUpperCase() + p.slice(1).toLowerCase())).join('-');
    }
    if (w.includes("'") && !w.startsWith("'") && !w.endsWith("'")) {
      const [pre, rest] = w.split("'", 2);
      const preFmt = (i === 0) ? pre.charAt(0).toUpperCase() + pre.slice(1).toLowerCase() + "'" : pre.toLowerCase() + "'";
      const restFmt = stopwords.has(rest.toLowerCase()) ? rest.toLowerCase() : (rest.charAt(0).toUpperCase() + rest.slice(1).toLowerCase());
      return preFmt + restFmt;
    }
    const low = w.toLowerCase();
    if (i === 0 || !stopwords.has(low)) {
      return low.charAt(0).toUpperCase() + low.slice(1);
    }
    return low;
  });
  let res = formatted.join(' ');
  res = res.replace(/([:\\.?!]\\s+)([a-zàéèêîôû])/g, (m, p1, p2) => p1 + p2.toUpperCase());
  return res.charAt(0).toUpperCase() + res.slice(1);
}

export function openNewBookModal(code = '', prefill = {}) {
  state.pendingNewCode = code || '';
  $('#nbCode').value = state.pendingNewCode;
  $('#nbTitle').value = prefill.matched_book ? (prefill.matched_book.title || '') : toSentenceCase(prefill.title || '');
  $('#nbAuthor').value = prefill.matched_book ? (prefill.matched_book.author || '') : toTitleCase(prefill.author || '');
  if ($('#nbPublisher')) $('#nbPublisher').value = prefill.matched_book ? (prefill.matched_book.publisher || '') : (prefill.publisher || '');
  $('#nbPrice').value = (prefill.price != null && prefill.price > 0) ? prefill.price : (prefill.matched_book && prefill.matched_book.price > 0 ? prefill.matched_book.price : '');
  
  const badge = $('#nbOcrBadge');
  if (badge) badge.style.display = prefill.lines ? 'inline-flex' : 'none';

  if (prefill.matched_book) {
    showExistingBookBanner(prefill.matched_book);
  } else if (state.pendingNewCode) {
    checkCodeInCatalog(state.pendingNewCode);
  } else {
    hideExistingBookBanner();
  }
  
  if (prefill.lines && prefill.lines.length) {
    if (window._renderOcrChips) window._renderOcrChips(prefill.lines);
  } else {
    const sect = $('#nbOcrChipsSection');
    if (sect) sect.style.display = 'none';
  }

  if (prefill.corrections) {
    if (prefill.corrections.author) {
      toast(`✨ Auteur corrigé d\\'après la base : ${prefill.corrections.author.corrected}`, 'ok');
    }
    if (prefill.corrections.publisher) {
      toast(`✨ Éditeur corrigé d\\'après la base : ${prefill.corrections.publisher.corrected}`, 'ok');
    }
  }

  triggerAllBddChecks();
  
  window.scrollTo(0, 0);
  updateViewportHeight();
  
  const m = $('#newBookModal');
  if (m) {
    m.hidden = false;
    m.style.removeProperty('display');
  }
  
  if (!prefill.lines || !prefill.lines.length) {
    setTimeout(() => {
      if (!$('#nbTitle').value) $('#nbTitle').focus();
      else if (!$('#nbPrice').value) $('#nbPrice').focus();
    }, 150);
  } else {
    if (document.activeElement && document.activeElement.blur) {
      document.activeElement.blur();
    }
  }
}

export function closeNewBookModal() {
  const m = $('#newBookModal');
  if (m) {
    m.hidden = true;
    m.style.setProperty('display', 'none', 'important');
  }
  state.pendingNewCode = null;
  const sect = $('#nbOcrChipsSection');
  if (sect) sect.style.display = 'none';
  const badge = $('#nbOcrBadge');
  if (badge) badge.style.display = 'none';
  hideExistingBookBanner();
  if (document.activeElement && document.activeElement.blur) {
    document.activeElement.blur();
  }
  window.scrollTo(0, 0);
  updateViewportHeight();
}

let titleCaseMode = 0;

export function initNewBookModal() {
  const nbBtnCloseTop = $('#nbBtnCloseTop');
  if (nbBtnCloseTop) {
    nbBtnCloseTop.addEventListener('click', closeNewBookModal);
  }

  const nbModalEl = $('#newBookModal');
  if (nbModalEl) {
    nbModalEl.addEventListener('click', e => {
      if (e.target === nbModalEl) closeNewBookModal();
    });
  }

  window.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      closeNewBookModal();
      closeMobileBookStats();
      closeMultiPayModal();
    }
  });

  const nbBtnCaseTitle = $('#nbBtnCaseTitle');
  if (nbBtnCaseTitle) {
    nbBtnCaseTitle.addEventListener('click', () => {
      const val = $('#nbTitle').value.trim();
      if (!val) return;
      titleCaseMode = (titleCaseMode + 1) % 2;
      if (titleCaseMode === 1) {
        $('#nbTitle').value = toTitleCase(val);
        toast('Titre formaté (Mots majuscules)', 'ok');
      } else {
        $('#nbTitle').value = toSentenceCase(val);
        toast('Titre formaté (Majuscule 1ère lettre)', 'ok');
      }
      triggerAllBddChecks();
    });
  }

  const nbBtnCaseAuthor = $('#nbBtnCaseAuthor');
  if (nbBtnCaseAuthor) {
    nbBtnCaseAuthor.addEventListener('click', () => {
      const val = $('#nbAuthor').value.trim();
      if (!val) return;
      $('#nbAuthor').value = toTitleCase(val);
      toast('Auteur formaté (Majuscules)', 'ok');
      triggerAllBddChecks();
    });
  }

  const bCancel = $('#btnCancelNewBook');
  if (bCancel) bCancel.addEventListener('click', closeNewBookModal);

  ['input', 'blur'].forEach(evt => {
    const codeInp = $('#nbCode');
    if (codeInp) codeInp.addEventListener(evt, () => checkCodeInCatalog(codeInp.value.trim()));

    const authInp = $('#nbAuthor');
    if (authInp) authInp.addEventListener(evt, () => checkFieldBdd('#nbAuthor', '#nbAuthorBddBadge', '#nbAuthorTypoSuggestion', state.dbAuthors));

    const pubInp = $('#nbPublisher');
    if (pubInp) pubInp.addEventListener(evt, () => checkFieldBdd('#nbPublisher', '#nbPublisherBddBadge', '#nbPublisherTypoSuggestion', state.dbPublishers));
  });

  const btnSave = $('#btnSaveNewBook');
  if (btnSave) {
    btnSave.addEventListener('click', async () => {
      const code = $('#nbCode').value.trim();
      const title = $('#nbTitle').value.trim();
      const author = $('#nbAuthor').value.trim();
      const publisher = $('#nbPublisher') ? $('#nbPublisher').value.trim() : null;
      const price = parseFloat($('#nbPrice').value) || 0;
      if (!title) return toast('Le titre est requis', 'warn');
      if (price <= 0) return toast('Indiquez un prix valide', 'warn');

      try {
        await api('/api/books', {
          method: 'POST',
          body: {
            code,
            title,
            author: author || null,
            publisher: publisher || null,
            price,
            category: 'Standard',
            min_stock: 2,
            is_pack: 0
          }
        });
        toast('Nouveau livre enregistré', 'ok');
        closeNewBookModal();
        const book = await api('/api/books/scan/' + encodeURIComponent(code));
        if (state.currentMode === 'sale') {
          addToCart(book);
        } else {
          addToRecv(book);
        }
      } catch (err) {
        toast(err.message, 'err');
      }
    });
  }
}
"""

# =============================================================================
# 10. ocr.js
# =============================================================================
MODULES["ocr.js"] = """/* Librairie Mobile - Numérisation OCR Page de Garde & Couverture */
'use strict';
import { $, el, toast, updateViewportHeight } from './core.js';
import { api } from './api.js';
import { toSentenceCase, toTitleCase, triggerAllBddChecks, openNewBookModal } from './new_book_modal.js';
import { addToRecv } from './modes.js';

export async function fileToResizedBase64(file, maxDim = 1600) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = e => {
      const img = new Image();
      img.onload = () => {
        let { width, height } = img;
        if (width > maxDim || height > maxDim) {
          if (width > height) {
            height = Math.round((height * maxDim) / width);
            width = maxDim;
          } else {
            width = Math.round((width * maxDim) / height);
            height = maxDim;
          }
        }
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, width, height);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.88);
        resolve(dataUrl.split(',')[1]);
      };
      img.onerror = () => reject(new Error("Impossible de lire l'image"));
      img.src = e.target.result;
    };
    reader.onerror = () => reject(new Error("Échec de chargement du fichier"));
    reader.readAsDataURL(file);
  });
}

export async function performOcr(file) {
  const b64 = await fileToResizedBase64(file, 1600);
  return api('/api/ocr/scan', {
    method: 'POST',
    body: { image_base64: b64 },
    timeoutMs: 15000
  });
}

export function updateOcrMergeButtons() {
  const checks = document.querySelectorAll('.nb-line-check:checked');
  const count = checks.length;
  const btnTitle = $('#nbBtnMergeTitle');
  const btnAuthor = $('#nbBtnMergeAuthor');
  if (btnTitle) {
    btnTitle.textContent = count > 0 ? `🔗 Fusionner (${count}) en Titre` : '🔗 Fusionner en Titre';
    btnTitle.style.background = count > 0 ? 'rgba(143, 22, 173, 0.35)' : 'var(--card2)';
  }
  if (btnAuthor) {
    btnAuthor.textContent = count > 0 ? `🔗 Fusionner (${count}) en Auteur` : '🔗 Fusionner en Auteur';
    btnAuthor.style.background = count > 0 ? 'rgba(37, 99, 235, 0.35)' : 'var(--card2)';
  }
  const toggleBtn = $('#nbToggleAllOcr');
  if (toggleBtn) {
    const allChecks = document.querySelectorAll('.nb-line-check');
    toggleBtn.textContent = (allChecks.length && count === allChecks.length) ? 'Tout décocher' : 'Tout cocher';
  }
}

export function renderOcrChips(lines) {
  const list = $('#nbOcrChipsList');
  const sect = $('#nbOcrChipsSection');
  if (!list || !sect) return;
  list.replaceChildren();
  if (!lines || !lines.length) {
    sect.style.display = 'none';
    return;
  }
  const validLines = lines.filter(l => (l.text || '').trim().length >= 2);
  if (!validLines.length) {
    sect.style.display = 'none';
    return;
  }
  const countBadge = $('#nbOcrCount');
  if (countBadge) countBadge.textContent = validLines.length;

  validLines.forEach(line => {
    const txt = (line.text || '').trim();
    const chk = el('input', {
      type: 'checkbox',
      class: 'nb-line-check ocr-card-check',
      'data-txt': txt
    });

    const textSpan = el('span', {
      text: txt,
      class: 'ocr-card-text'
    });

    const label = el('label', { class: 'ocr-card-label' }, chk, textSpan);

    const btnTitle = el('button', {
      type: 'button',
      text: 'Titre',
      class: 'ocr-pill-btn ocr-pill-title',
      title: 'Remplacer le titre par cette ligne',
      onclick: (e) => {
        e.stopPropagation();
        $('#nbTitle').value = toSentenceCase(txt);
        toast('Titre défini (1ère lettre majuscule)', 'ok');
        triggerAllBddChecks();
      }
    });

    const btnTitleAdd = el('button', {
      type: 'button',
      text: '+ Titre',
      class: 'ocr-pill-btn ocr-pill-title-add',
      title: 'Ajouter cette ligne au titre existant',
      onclick: (e) => {
        e.stopPropagation();
        const cur = $('#nbTitle').value.trim();
        $('#nbTitle').value = toSentenceCase(cur ? cur + ' ' + txt : txt);
        toast('Ligne ajoutée au titre', 'ok');
        triggerAllBddChecks();
      }
    });

    const btnAuthor = el('button', {
      type: 'button',
      text: 'Auteur',
      class: 'ocr-pill-btn ocr-pill-author',
      title: 'Remplacer l\\'auteur par cette ligne',
      onclick: (e) => {
        e.stopPropagation();
        $('#nbAuthor').value = toTitleCase(txt);
        toast('Auteur défini (1ère lettre majuscule)', 'ok');
        triggerAllBddChecks();
      }
    });

    const btnAuthorAdd = el('button', {
      type: 'button',
      text: '+ Auteur',
      class: 'ocr-pill-btn ocr-pill-author-add',
      title: 'Ajouter cette ligne à l\\'auteur existant',
      onclick: (e) => {
        e.stopPropagation();
        const cur = $('#nbAuthor').value.trim();
        $('#nbAuthor').value = toTitleCase(cur ? cur + ' ' + txt : txt);
        toast('Ligne ajoutée à l\\'auteur', 'ok');
        triggerAllBddChecks();
      }
    });

    const btnPub = el('button', {
      type: 'button',
      text: 'Éditeur',
      class: 'ocr-pill-btn ocr-pill-pub',
      title: 'Remplacer l\\'éditeur par cette ligne',
      onclick: (e) => {
        e.stopPropagation();
        if ($('#nbPublisher')) $('#nbPublisher').value = txt;
        toast('Éditeur défini', 'ok');
        triggerAllBddChecks();
      }
    });

    const actionsBar = el('div', { class: 'ocr-card-actions' },
      btnTitle,
      btnTitleAdd,
      btnAuthor,
      btnAuthorAdd,
      btnPub
    );

    const card = el('div', { class: 'ocr-card' }, label, actionsBar);

    chk.addEventListener('change', () => {
      card.classList.toggle('selected', chk.checked);
      updateOcrMergeButtons();
    });

    list.append(card);
  });

  updateOcrMergeButtons();
  sect.style.display = 'block';
}
window._renderOcrChips = renderOcrChips;

export function initOcr() {
  const clearChipsBtn = $('#nbClearOcrChips');
  if (clearChipsBtn) {
    clearChipsBtn.addEventListener('click', () => {
      const sect = $('#nbOcrChipsSection');
      if (sect) sect.style.display = 'none';
    });
  }

  const toggleAllOcrBtn = $('#nbToggleAllOcr');
  if (toggleAllOcrBtn) {
    toggleAllOcrBtn.addEventListener('click', () => {
      const allChecks = document.querySelectorAll('.nb-line-check');
      const checked = document.querySelectorAll('.nb-line-check:checked');
      const shouldCheck = (checked.length < allChecks.length);
      allChecks.forEach(c => {
        c.checked = shouldCheck;
        const card = c.closest('.ocr-card');
        if (card) card.classList.toggle('selected', shouldCheck);
      });
      updateOcrMergeButtons();
    });
  }

  const mergeTitleBtn = $('#nbBtnMergeTitle');
  if (mergeTitleBtn) {
    mergeTitleBtn.addEventListener('click', () => {
      const checks = document.querySelectorAll('.nb-line-check:checked');
      if (!checks.length) return toast('Cochez au moins 1 ligne à fusionner en Titre', 'warn');
      const combined = Array.from(checks).map(c => c.getAttribute('data-txt')).join(' ');
      $('#nbTitle').value = toSentenceCase(combined);
      toast(`Titre fusionné et formaté (${checks.length} lignes)`, 'ok');
      triggerAllBddChecks();
      updateOcrMergeButtons();
    });
  }

  const mergeAuthorBtn = $('#nbBtnMergeAuthor');
  if (mergeAuthorBtn) {
    mergeAuthorBtn.addEventListener('click', () => {
      const checks = document.querySelectorAll('.nb-line-check:checked');
      if (!checks.length) return toast('Cochez au moins 1 ligne à fusionner en Auteur', 'warn');
      const combined = Array.from(checks).map(c => c.getAttribute('data-txt')).join(' ');
      $('#nbAuthor').value = toTitleCase(combined);
      toast(`Auteur fusionné et formaté (${checks.length} lignes)`, 'ok');
      triggerAllBddChecks();
      updateOcrMergeButtons();
    });
  }

  const nbOcrInput = $('#nbOcrInput');
  if (nbOcrInput) {
    nbOcrInput.addEventListener('change', async e => {
      window.scrollTo(0, 0);
      updateViewportHeight();
      if (document.activeElement && document.activeElement.blur) document.activeElement.blur();

      const file = e.target.files && e.target.files[0];
      if (!file) return;
      const txtSpan = $('#nbOcrText');
      const oldText = txtSpan ? txtSpan.textContent : '';
      if (txtSpan) txtSpan.textContent = '⏳ Analyse OCR en cours...';
      try {
        toast('Analyse de la page de garde...', 'ok');
        const res = await performOcr(file);
        window.scrollTo(0, 0);
        updateViewportHeight();
        if (res && res.candidates) {
          const c = res.candidates;
          if (c.title) $('#nbTitle').value = c.title;
          if (c.author) $('#nbAuthor').value = c.author;
          if (c.publisher && $('#nbPublisher')) $('#nbPublisher').value = c.publisher;
          if (c.price != null && c.price > 0) $('#nbPrice').value = c.price;
          const badge = $('#nbOcrBadge');
          if (badge) badge.style.display = 'inline-flex';
          renderOcrChips(res.lines);
          
          if (res.matched_book) {
            import('./new_book_modal.js').then(m => m.showExistingBookBanner(res.matched_book));
          }

          if (res.corrections) {
            if (res.corrections.author) {
              toast(`✨ Auteur corrigé d\\'après la base : ${res.corrections.author.corrected}`, 'ok');
            }
            if (res.corrections.publisher) {
              toast(`✨ Éditeur corrigé d\\'après la base : ${res.corrections.publisher.corrected}`, 'ok');
            }
          }

          triggerAllBddChecks();
          toast('Page de garde analysée avec succès', 'ok');
        }
      } catch (err) {
        toast(err.message || "Erreur lors de l'OCR", 'err');
      } finally {
        if (txtSpan) txtSpan.textContent = oldText;
        nbOcrInput.value = '';
        window.scrollTo(0, 0);
        updateViewportHeight();
      }
    });
  }

  const recvOcrInput = $('#recvOcrInput');
  if (recvOcrInput) {
    recvOcrInput.addEventListener('change', async e => {
      window.scrollTo(0, 0);
      updateViewportHeight();
      if (document.activeElement && document.activeElement.blur) document.activeElement.blur();

      const file = e.target.files && e.target.files[0];
      if (!file) return;
      const txtSpan = $('#recvOcrText');
      const oldText = txtSpan ? txtSpan.textContent : '';
      if (txtSpan) txtSpan.textContent = '⏳ Scan OCR...';
      try {
        toast('Numérisation de la page de garde...', 'ok');
        const res = await performOcr(file);
        window.scrollTo(0, 0);
        updateViewportHeight();
        if (res) {
          if (res.matched_book) {
            try {
              const book = await api('/api/books/scan/' + encodeURIComponent(res.matched_book.code));
              addToRecv(book);
              toast(`📦 Livre en base ajouté au carton : ${book.title}`, 'ok');
              return;
            } catch (e) {}
          }

          const c = res.candidates || {};
          toast('Page de garde lue : vérifiez et enregistrez', 'ok');
          openNewBookModal('', { ...c, lines: res.lines, matched_book: res.matched_book, corrections: res.corrections });
        } else {
          toast('Aucun texte lisible détecté', 'warn');
        }
      } catch (err) {
        toast(err.message || "Erreur lors de l'analyse OCR", 'err');
      } finally {
        if (txtSpan) txtSpan.textContent = oldText;
        recvOcrInput.value = '';
        window.scrollTo(0, 0);
        updateViewportHeight();
      }
    });
  }
}
"""

# =============================================================================
# 11. search.js
# =============================================================================
MODULES["search.js"] = """/* Librairie Mobile - Recherche & Saisie Manuelle */
'use strict';
import { $, el, eur, toast } from './core.js';
import { state } from './state.js';
import { api } from './api.js';
import { addToCart } from './cart.js';
import { addToRecv } from './modes.js';
import { openNewBookModal } from './new_book_modal.js';

export async function lookupCode(code) {
  if (state.isLookingUp) return;
  state.isLookingUp = true;
  try {
    const book = await api('/api/books/scan/' + encodeURIComponent(code), { timeoutMs: 3500 });
    if (state.currentMode === 'sale') {
      addToCart(book);
    } else {
      addToRecv(book);
    }
  } catch (e) {
    if (e.message && e.message.includes('Aucun livre pour le code')) {
      toast('Livre inconnu : ouverture de la fiche', 'warn');
      openNewBookModal(code);
    } else {
      toast(e.message, 'warn');
    }
  } finally {
    state.isLookingUp = false;
  }
}

export async function manualSearch() {
  const q = $('#manualCode').value.trim();
  const box = $('#results'); box.replaceChildren();
  if (!q) return;
  if (/^[0-9][0-9\\- ]{7,}$/.test(q)) { await lookupCode(q); $('#manualCode').value = ''; return; }
  try {
    const found = await api('/api/books/search?q=' + encodeURIComponent(q));
    if (!found.length) return toast('Aucun résultat', 'warn');
    box.replaceChildren(...found.map(b => el('button', {
      class: 'result', type: 'button',
      onclick: () => { 
        if (state.currentMode === 'sale') addToCart(b); else addToRecv(b);
        box.replaceChildren(); 
        $('#manualCode').value = ''; 
      }
    }, el('div', { class: 'ci-title', text: b.title + (b.volume ? ' · Vol. ' + b.volume : '') }),
       el('div', { class: 'muted', text: `${b.code} · ${eur(b.price)} · stock ${b.stock}` }))));
  } catch (e) { toast(e.message, 'err'); }
}

export function initSearch() {
  const btnSearch = $('#btnSearch');
  if (btnSearch) btnSearch.addEventListener('click', manualSearch);
  const manualCode = $('#manualCode');
  if (manualCode) manualCode.addEventListener('keydown', e => { if (e.key === 'Enter') manualSearch(); });
}
"""

# =============================================================================
# 12. scanner.js
# =============================================================================
MODULES["scanner.js"] = """/* Librairie Mobile - Moteur de Scan Haute Tolérance & Cycle de Vie Caméra */
'use strict';
import { $ } from './core.js';
import { state } from './state.js';
import { lookupCode } from './search.js';

let stream = null, scanTimer = null, isScanning = false, lastCode = '', lastTime = 0;
let lockedBarcode = null;
let emptyFramesCount = 0;
const EMPTY_FRAMES_REQUIRED = 3;
const SAME_CODE_COOLDOWN_MS = 1200;
let videoTrack = null, torchActive = false;

const canvasRoi = document.createElement('canvas');
const ctxRoi = canvasRoi.getContext('2d', { willReadFrequently: true });
const canvasFilter = document.createElement('canvas');
const ctxFilter = canvasFilter.getContext('2d', { willReadFrequently: true });

let zxReader = null;
if (window.ZXing) {
  try {
    const hints = new Map();
    hints.set(ZXing.DecodeHintType.TRY_HARDER, true);
    hints.set(ZXing.DecodeHintType.POSSIBLE_FORMATS, [
      ZXing.BarcodeFormat.EAN_13,
      ZXing.BarcodeFormat.EAN_8,
      ZXing.BarcodeFormat.UPC_A,
      ZXing.BarcodeFormat.CODE_128
    ]);
    zxReader = new ZXing.MultiFormatReader();
    zxReader.setHints(hints);
  } catch (e) { console.warn('ZXing init error', e); }
}

const nativeDetector = ('BarcodeDetector' in window)
  ? new BarcodeDetector({ formats: ['ean_13', 'ean_8', 'upc_a', 'code_128'] })
  : null;

export function isValidBarcode(raw) {
  if (!raw) return false;
  const s = String(raw).trim();
  if (/^\\d{8}$|^\\d{13}$/.test(s)) {
    let sum = 0;
    const len = s.length;
    for (let i = 0; i < len - 1; i++) {
      const d = parseInt(s[i], 10);
      const w = (len === 13) ? (i % 2 === 0 ? 1 : 3) : (i % 2 === 0 ? 3 : 1);
      sum += d * w;
    }
    const check = (10 - (sum % 10)) % 10;
    return check === parseInt(s[len - 1], 10);
  }
  return /^[A-Za-z0-9\\-\\.\\s]{3,30}$/.test(s);
}

export function decodeZxingBuffer(rgbaData, width, height) {
  if (!zxReader || !window.ZXing) return null;
  try {
    const lum = new ZXing.RGBLuminanceSource(rgbaData, width, height);
    const bitmap = new ZXing.BinaryBitmap(new ZXing.HybridBinarizer(lum));
    const txt = zxReader.decode(bitmap).getText();
    if (isValidBarcode(txt)) return txt;
  } catch (e) { }

  try {
    const lum = new ZXing.RGBLuminanceSource(rgbaData, width, height);
    const bitmap = new ZXing.BinaryBitmap(new ZXing.GlobalHistogramBinarizer(lum));
    const txt = zxReader.decode(bitmap).getText();
    if (isValidBarcode(txt)) return txt;
  } catch (e) { }

  return null;
}

export function processDegradedFilters(data, width, height) {
  let min = 255, max = 0;
  const gray = new Uint8Array(width * height);
  for (let i = 0, j = 0; i < data.length; i += 4, j++) {
    const g = (data[i] * 299 + data[i + 1] * 587 + data[i + 2] * 114 + 500) >> 10;
    gray[j] = g;
    if (g < min) min = g;
    if (g > max) max = g;
  }
  const range = Math.max(1, max - min);

  const sharpened = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) {
    const row = y * width;
    for (let x = 0; x < width; x++) {
      const idx = row + x;
      const left = x > 0 ? gray[idx - 1] : gray[idx];
      const right = x < width - 1 ? gray[idx + 1] : gray[idx];
      let v = 3.2 * gray[idx] - 1.1 * left - 1.1 * right;
      v = ((v - min) * 255) / range;
      v = v < 0 ? 0 : v > 255 ? 255 : (v | 0);
      const o = idx * 4;
      sharpened[o] = v; sharpened[o + 1] = v; sharpened[o + 2] = v; sharpened[o + 3] = 255;
    }
  }

  const binarized = new Uint8ClampedArray(width * height * 4);
  const halfWin = 14;
  const t = 0.88;
  for (let y = 0; y < height; y++) {
    const row = y * width;
    let sum = 0;
    for (let i = 0; i < Math.min(width, halfWin); i++) sum += gray[row + i];
    for (let x = 0; x < width; x++) {
      const addX = x + halfWin;
      const remX = x - halfWin - 1;
      if (addX < width) sum += gray[row + addX];
      if (remX >= 0) sum -= gray[row + remX];
      const count = Math.min(width - 1, addX) - Math.max(0, remX);
      const mean = sum / (count || 1);
      const v = (gray[row + x] < mean * t) ? 0 : 255;
      const o = (row + x) * 4;
      binarized[o] = v; binarized[o + 1] = v; binarized[o + 2] = v; binarized[o + 3] = 255;
    }
  }
  return { sharpened, binarized };
}

export function flashSuccess() {
  const box = $('#targetBox');
  if (box) {
    box.classList.add('success');
    setTimeout(() => box.classList.remove('success'), 400);
  }
  if (navigator.vibrate) {
    try { navigator.vibrate(50); } catch (e) { }
  }
}

export function onCode(code) {
  resetInactivity();
  if (state.isLookingUp || state.pendingNewCode) return;
  
  const now = Date.now();

  // Règle 1 : Scan-and-Exit
  if (code === lockedBarcode) {
    return;
  }

  // Règle 2 : Cooldown 1.2s même livre
  if (code === lastCode && (now - lastTime < SAME_CODE_COOLDOWN_MS)) {
    return;
  }

  lockedBarcode = code;
  lastCode = code;
  lastTime = now;
  emptyFramesCount = 0;
  flashSuccess();
  lookupCode(code);
}

let inactivityTimer = null;
let isAutoPaused = false;
const INACTIVITY_MS = 10 * 1000;
const BURST_INTERVAL_MS = 110;
const ECO_INTERVAL_MS = 330;
const BURST_DURATION_MS = 5000;
let lastScanSuccessTime = 0;
let isBurstMode = false;
let torchTimer = null;

export function updateEcoBadge(burst) {
  const badge = $('#camEcoBadge');
  if (badge) {
    badge.textContent = burst ? 'RAPIDE' : 'ÉCO';
    badge.classList.toggle('burst', burst);
    badge.title = burst ? 'Mode Rush : 9 FPS haute cadence' : 'Mode Éco : 3 FPS économie d\\'énergie';
  }
}

export function resetInactivity() {
  clearTimeout(inactivityTimer);
  const camCont = $('#camContainer');
  if (camCont && camCont.classList.contains('minimized')) {
    return;
  }
  if (stream) {
    inactivityTimer = setTimeout(() => {
      pauseCamera('auto');
    }, INACTIVITY_MS);
  }
}

export function pauseCamera(reason = 'minimized') {
  stopCamera();
  isAutoPaused = true;
  const camCont = $('#camContainer');
  const btnToggleCamSize = $('#btnToggleCamSize');
  const camMinibarText = $('#camMinibarText');
  if (camCont && !camCont.classList.contains('minimized')) {
    camCont.classList.add('minimized');
    if (btnToggleCamSize) btnToggleCamSize.textContent = '▼ Scanner';
  }
  if (camMinibarText) {
    camMinibarText.textContent = (reason === 'auto')
      ? 'Scanner en veille · Toucher pour réactiver'
      : 'Scanner masqué · Toucher pour agrandir';
  }
}

export function stopCamera() {
  clearTimeout(scanTimer); scanTimer = null;
  clearTimeout(inactivityTimer); inactivityTimer = null;
  clearTimeout(torchTimer); torchTimer = null;
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
  videoTrack = null;
  const video = $('#video');
  if (video) {
    video.style.opacity = '0';
    video.srcObject = null;
  }
  const btnTorch = $('#btnTorch');
  if (btnTorch) {
    btnTorch.hidden = true;
    btnTorch.classList.remove('on');
  }
  torchActive = false;
  updateEcoBadge(false);
}

export function camStatus(show, title, msg, btnText = null, onBtn = null) {
  const cs = $('#camStatus');
  if (cs) cs.hidden = !show;
  if (title) $('#camTitle').textContent = title;
  if (msg) $('#camMsg').textContent = msg;
  const btn = $('#btnCam');
  if (btn) {
    btn.textContent = btnText || 'Activer la caméra';
    btn.onclick = onBtn || (() => startCamera());
  }
}

let bestCameraDeviceId = null;
let isStartingCamera = false;

export async function findOptimalCamera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return null;
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const videoDevices = devices.filter(d => d.kind === 'videoinput');
    if (!videoDevices.length) return null;

    const rear = videoDevices.filter(d => {
      const l = (d.label || '').toLowerCase();
      const isFront = l.includes('front') || l.includes('avant') || l.includes('selfie') || l.includes('user');
      if (isFront) return false;
      return l.includes('back') || l.includes('rear') || l.includes('environment') || l.includes('arrière') || l.includes('0');
    });

    const candidates = rear.length ? rear : videoDevices;
    if (candidates.length === 1) return candidates[0].deviceId;

    let bestId = null;
    let highestScore = -Infinity;

    for (const dev of candidates) {
      const label = (dev.label || '').toLowerCase();
      let score = 0;

      if (label.includes('ultra') || label.includes('0.6') || label.includes('wide-angle') || label.includes('grand angle')) {
        score -= 100;
      }
      if (label.includes('main') || label.includes('standard') || label.includes('camera 0') || label.includes('camera2 0') || label.includes('primary')) {
        score += 50;
      }

      try {
        const testStream = await navigator.mediaDevices.getUserMedia({
          video: { deviceId: { exact: dev.deviceId } },
          audio: false
        });
        const track = testStream.getVideoTracks()[0];
        if (track) {
          const settings = track.getSettings ? track.getSettings() : {};
          if (settings.facingMode === 'user') {
            testStream.getTracks().forEach(t => t.stop());
            continue;
          }
          if (track.getCapabilities) {
            const caps = track.getCapabilities();
            if (caps.focusMode && caps.focusMode.includes('continuous')) score += 40;
            if (caps.focusDistance) {
              score += 30;
              if (caps.focusDistance.min !== undefined && caps.focusDistance.min < 0.15) score += 20;
            }
            if (caps.zoom) score += 10;
          }
        }
        testStream.getTracks().forEach(t => t.stop());
      } catch (err) { }

      if (score > highestScore) {
        highestScore = score;
        bestId = dev.deviceId;
      }
    }

    return bestId || candidates[0].deviceId;
  } catch (e) {
    return null;
  }
}

export async function startCamera(specificDeviceId = null) {
  if (isStartingCamera) return;
  isStartingCamera = true;

  const camCont = $('#camContainer');
  const btnToggleCamSize = $('#btnToggleCamSize');
  if (camCont && camCont.classList.contains('minimized')) {
    camCont.classList.remove('minimized');
    if (btnToggleCamSize) btnToggleCamSize.textContent = '▲ Masquer';
  }
  isAutoPaused = false;

  stopCamera();
  if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    isStartingCamera = false;
    return camStatus(true, 'Caméra indisponible', 'Cette page nécessite une connexion HTTPS pour accéder à l\\'appareil photo.');
  }

  const video = $('#video');
  if (video) video.style.opacity = '0';

  try {
    let targetDeviceId = specificDeviceId;

    if (!targetDeviceId && !bestCameraDeviceId) {
      bestCameraDeviceId = await findOptimalCamera();
    }
    if (!targetDeviceId && bestCameraDeviceId) {
      targetDeviceId = bestCameraDeviceId;
    }

    const baseVideoConstraints = {
      width: { ideal: 1920 },
      height: { ideal: 1080 }
    };

    const videoConstraints = targetDeviceId
      ? { ...baseVideoConstraints, deviceId: { exact: targetDeviceId } }
      : { ...baseVideoConstraints, facingMode: { ideal: 'environment' } };

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { ...videoConstraints, advanced: [{ focusMode: 'continuous' }] },
        audio: false
      });
    } catch (e1) {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: videoConstraints,
          audio: false
        });
      } catch (e2) {
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'environment' },
            audio: false
          });
        } catch (e3) {
          stream = await navigator.mediaDevices.getUserMedia({
            video: true,
            audio: false
          });
        }
      }
    }

    video.srcObject = stream;
    await video.play();

    video.style.opacity = '1';
    camStatus(false);

    videoTrack = stream ? stream.getVideoTracks()[0] : null;

    if (videoTrack && videoTrack.applyConstraints) {
      try { await videoTrack.applyConstraints({ advanced: [{ focusMode: 'continuous' }] }); } catch (e) { }
    }

    if (videoTrack && videoTrack.getCapabilities) {
      const caps = videoTrack.getCapabilities();
      if (caps.torch) {
        const btnTorch = $('#btnTorch');
        btnTorch.hidden = false;
        torchActive = false;
        btnTorch.classList.remove('on');
        btnTorch.onclick = async () => {
          try {
            clearTimeout(torchTimer);
            torchActive = !torchActive;
            await videoTrack.applyConstraints({ advanced: [{ torch: torchActive }] });
            btnTorch.classList.toggle('on', torchActive);
            if (torchActive) {
              torchTimer = setTimeout(async () => {
                if (torchActive && videoTrack) {
                  try {
                    torchActive = false;
                    await videoTrack.applyConstraints({ advanced: [{ torch: false }] });
                    btnTorch.classList.remove('on');
                  } catch (e) { }
                }
              }, 15000);
            }
          } catch (e) { }
        };
      }
    }

    resetInactivity();

    video.onclick = async () => {
      resetInactivity();
      if (videoTrack && videoTrack.applyConstraints) {
        try {
          await videoTrack.applyConstraints({ advanced: [{ focusMode: 'continuous' }] });
          import('./core.js').then(c => c.toast('Mise au point recentrée', 'ok'));
        } catch (e) { }
      }
    };

    const scanTick = async () => {
      if (!stream) return;
      const now = Date.now();
      const burst = (now - lastScanSuccessTime < BURST_DURATION_MS);
      if (burst !== isBurstMode) {
        isBurstMode = burst;
        updateEcoBadge(burst);
      }

      if (!isScanning && video.readyState >= 2) {
        isScanning = true;
        try {
          const vw = video.videoWidth;
          const vh = video.videoHeight;
          if (vw && vh) {
            const cw1 = Math.round(vw * 0.72);
            const ch1 = Math.round(vh * 0.48);
            const cx1 = Math.round((vw - cw1) / 2);
            const cy1 = Math.round((vh - ch1) / 2);

            const cw2 = Math.round(vw * 0.38);
            const ch2 = Math.round(vh * 0.28);
            const cx2 = Math.round((vw - cw2) / 2);
            const cy2 = Math.round((vh - ch2) / 2);

            let code = null;

            const scanCrop = async (cx, cy, cw, ch, allowHeavyFilters) => {
              if (canvasRoi.width !== cw || canvasRoi.height !== ch) {
                canvasRoi.width = cw; canvasRoi.height = ch;
                canvasFilter.width = cw; canvasFilter.height = ch;
              }
              ctxRoi.drawImage(video, cx, cy, cw, ch, 0, 0, cw, ch);

              if (nativeDetector) {
                try {
                  const results = await nativeDetector.detect(canvasRoi);
                  for (const r of results) {
                    if (isValidBarcode(r.rawValue)) return r.rawValue;
                  }
                } catch (e) { }
              }

              const rawImg = ctxRoi.getImageData(0, 0, cw, ch);
              let found = decodeZxingBuffer(rawImg.data, cw, ch);
              if (found) return found;

              if (allowHeavyFilters) {
                const { sharpened, binarized } = processDegradedFilters(rawImg.data, cw, ch);
                found = decodeZxingBuffer(sharpened, cw, ch);
                if (found) return found;
                found = decodeZxingBuffer(binarized, cw, ch);
                return found;
              }
              return null;
            };

            code = await scanCrop(cx2, cy2, cw2, ch2, burst);

            if (!code) {
              code = await scanCrop(cx1, cy1, cw1, ch1, burst);
            }

            if (code) {
              emptyFramesCount = 0;
              lastScanSuccessTime = Date.now();
              if (!isBurstMode) {
                isBurstMode = true;
                updateEcoBadge(true);
              }
              onCode(code);
            } else {
              emptyFramesCount++;
              if (emptyFramesCount >= EMPTY_FRAMES_REQUIRED) {
                lockedBarcode = null;
              }
            }
          }
        } catch (err) {
        } finally {
          isScanning = false;
        }
      }

      const nextDelay = isBurstMode ? BURST_INTERVAL_MS : ECO_INTERVAL_MS;
      scanTimer = setTimeout(scanTick, nextDelay);
    };

    scanTick();

  } catch (e) {
    console.error('Camera startup error:', e);
    const denied = e && (e.name === 'NotAllowedError' || e.name === 'SecurityError');
    camStatus(true, denied ? 'Autorisation caméra refusée' : 'Caméra indisponible',
      denied ? 'Android : touchez le cadenas dans la barre d\\'adresse → Autorisations → Appareil photo → Autoriser, puis réessayez.'
             : (e && e.message ? `Erreur caméra : ${e.message}. Touchez "Activer la caméra" pour réessayer.` : 'Aucune caméra utilisable. Utilisez le bouton photo ou la saisie manuelle.'));
  } finally {
    isStartingCamera = false;
  }
}

export function toggleCamMinimize(forceMin, reason = 'manual') {
  const camCont = $('#camContainer');
  const btnToggleCamSize = $('#btnToggleCamSize');
  const camMinibarText = $('#camMinibarText');
  if (!camCont) return;
  const isMin = forceMin !== undefined ? forceMin : !camCont.classList.contains('minimized');
  camCont.classList.toggle('minimized', isMin);
  if (btnToggleCamSize) {
    btnToggleCamSize.textContent = isMin ? '▼ Scanner' : '▲ Masquer';
  }
  if (camMinibarText && isMin) {
    camMinibarText.textContent = (reason === 'auto')
      ? 'Scanner en veille · Toucher pour réactiver'
      : 'Scanner masqué · Toucher pour agrandir';
  }
  if (isMin) {
    pauseCamera(reason);
  } else {
    isAutoPaused = false;
    startCamera();
  }
}

export function initScanner() {
  const btnCam = $('#btnCam');
  if (btnCam) btnCam.addEventListener('click', startCamera);

  const btnToggleCamSize = $('#btnToggleCamSize');
  if (btnToggleCamSize) btnToggleCamSize.addEventListener('click', () => toggleCamMinimize());

  const camMinibar = $('#camMinibar');
  if (camMinibar) camMinibar.addEventListener('click', () => toggleCamMinimize(false));

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      pauseCamera('auto');
    } else if (localStorage.getItem('librairie_device_token') && !isAutoPaused) {
      startCamera();
    }
  });

  ['touchstart', 'mousedown', 'keydown'].forEach(evt => {
    window.addEventListener(evt, resetInactivity, { passive: true });
  });

  const fileSnap = $('#fileSnap');
  if (fileSnap) {
    fileSnap.addEventListener('change', async e => {
      const file = e.target.files[0]; e.target.value = '';
      if (!file) return;
      const url = URL.createObjectURL(file);
      try {
        const img = new Image(); img.src = url; await img.decode();
        let code = null;

        const snapCanvas = document.createElement('canvas');
        const maxDim = 1200;
        let sw = img.naturalWidth || img.width;
        let sh = img.naturalHeight || img.height;
        if (sw > maxDim || sh > maxDim) {
          if (sw > sh) { sh = Math.round((sh * maxDim) / sw); sw = maxDim; }
          else { sw = Math.round((sw * maxDim) / sh); sh = maxDim; }
        }
        snapCanvas.width = sw; snapCanvas.height = sh;
        const snapCtx = snapCanvas.getContext('2d', { willReadFrequently: true });
        snapCtx.drawImage(img, 0, 0, sw, sh);

        if (nativeDetector) {
          try {
            const r = await nativeDetector.detect(snapCanvas);
            if (r.length && isValidBarcode(r[0].rawValue)) code = r[0].rawValue;
          } catch (err) { }
        }

        if (!code) {
          const snapData = snapCtx.getImageData(0, 0, sw, sh);
          code = decodeZxingBuffer(snapData.data, sw, sh);

          if (!code) {
            const { sharpened, binarized } = processDegradedFilters(snapData.data, sw, sh);
            code = decodeZxingBuffer(sharpened, sw, sh) || decodeZxingBuffer(binarized, sw, sh);
          }
        }

        if (code) {
          lockedBarcode = null;
          lastCode = '';
          onCode(code);
        } else {
          import('./core.js').then(c => c.toast('Code-barres non lisible sur cette photo', 'warn'));
        }
      } catch (err) {
        import('./core.js').then(c => c.toast('Erreur de lecture de la photo', 'warn'));
      } finally {
        URL.revokeObjectURL(url);
      }
    });
  }
}
"""

# =============================================================================
# 13. fullscreen.js
# =============================================================================
MODULES["fullscreen.js"] = """/* Librairie Mobile - Mode Plein Écran Hybride (PWA Standalone + Fullscreen API) */
'use strict';
import { $ } from './core.js';

export function isStandaloneMode() {
  return window.navigator.standalone === true ||
    window.matchMedia('(display-mode: standalone)').matches ||
    window.matchMedia('(display-mode: fullscreen)').matches;
}

export function updateFullscreenUI() {
  const isFull = !!(document.fullscreenElement || document.webkitFullscreenElement);
  const btn = $('#btnFullscreen');
  if (!btn) return;
  if (isStandaloneMode()) {
    btn.style.display = 'none';
  } else {
    btn.style.display = 'inline-flex';
    btn.title = isFull ? 'Quitter le plein écran' : 'Passer en plein écran';
    btn.style.color = isFull ? 'var(--good)' : 'var(--mut)';
    btn.style.borderColor = isFull ? 'var(--good)' : 'var(--line)';
    const ico = $('#icoFullscreen');
    if (ico) {
      ico.innerHTML = isFull
        ? '<path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/>'
        : '<path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>';
    }
  }
}

export async function toggleFullscreen() {
  try {
    if (!document.fullscreenElement && !document.webkitFullscreenElement) {
      const docEl = document.documentElement;
      const req = docEl.requestFullscreen || docEl.webkitRequestFullscreen || docEl.mozRequestFullScreen || docEl.msRequestFullscreen;
      if (req) await req.call(docEl);
    } else {
      const exit = document.exitFullscreen || document.webkitExitFullscreen || document.mozCancelFullScreen || document.msExitFullscreen;
      if (exit) await exit.call(document);
    }
  } catch (e) { }
  updateFullscreenUI();
}

export function initFullscreen() {
  const btnFullscreen = $('#btnFullscreen');
  if (btnFullscreen) {
    btnFullscreen.addEventListener('click', toggleFullscreen);
  }
  ['fullscreenchange', 'webkitfullscreenchange'].forEach(evt => {
    document.addEventListener(evt, updateFullscreenUI);
  });
  updateFullscreenUI();
}
"""

# =============================================================================
# 14. main.js (Entry Point)
# =============================================================================
MODULES["main.js"] = """/* Librairie Mobile - Point d'entrée principal de l'application modulaire */
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

  closeNewBookModal();
  startNetworkMonitor();
  restoreActiveCart();
  restoreRecvList();
  await pairFromHash();

  const initHash = location.hash.replace(/^#/, '');
  setMobileMode(initHash === 'recv' ? 'recv' : 'sale', true, false);

  if (!localStorage.getItem(TOKEN_KEY)) {
    renderCart();
    return showPairing();
  }

  try {
    state.users = await api('/api/users');
    if (!state.users.some(u => u.name === state.currentUser)) {
      state.currentUser = '';
      localStorage.removeItem(USER_KEY);
    }
  } catch (e) {
    return;
  }

  updateUser();
  await loadPayOptions();
  renderCart();
  syncLiveCart({ type: 'mobile_connected' });
  if (!state.currentUser) openUserModal();
  startCamera();
})();
"""

def run():
    print(f"[*] Modularisation de {MOBILE_JS}...")
    
    # 1. Sauvegarde
    if not os.path.exists(BACKUP_JS):
        shutil.copyfile(MOBILE_JS, BACKUP_JS)
        print(f"[+] Sauvegarde originale créée : {BACKUP_JS}")

    # 2. Création du dossier cible
    os.makedirs(TARGET_DIR, exist_ok=True)
    print(f"[+] Dossier de destination : {TARGET_DIR}")

    # 3. Écriture de tous les modules
    for filename, code in MODULES.items():
        filepath = os.path.join(TARGET_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code.strip() + "\n")
        print(f"  -> Module généré : {filename} ({len(code.splitlines())} lignes)")

    # 4. Vérification de la syntaxe JS via Node.js
    print("[*] Validation syntaxique de chaque module via Node.js...")
    import json
    pkg_json = os.path.join(TARGET_DIR, "package.json")
    with open(pkg_json, "w", encoding="utf-8") as f:
        json.dump({"type": "module"}, f)

    all_valid = True
    for filename in MODULES.keys():
        filepath = os.path.join(TARGET_DIR, filename)
        res = subprocess.run(["node", "-c", filepath], capture_output=True, text=True)
        if res.returncode != 0:
            print(f"  [!] ERREUR syntaxe dans {filename}:")
            print(res.stderr)
            all_valid = False
        else:
            print(f"  [OK] {filename}")

    # Nettoyage package.json
    if os.path.exists(pkg_json):
        os.remove(pkg_json)

    if not all_valid:
        print("[!] Des erreurs de syntaxe ont été détectées. Arrêt du script.")
        sys.exit(1)

    # 5. Mise à jour de mobile.html pour charger le module principal
    print(f"[*] Mise à jour de {MOBILE_HTML}...")
    with open(MOBILE_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    # Remplacer la balise script simple par le module ES6 + repli nomodule
    old_script_pattern = '<script src="/static/mobile.js'
    new_script_tag = '<script type="module" src="/static/js/mobile/main.js?v=20261018_v1"></script>\n  <script nomodule src="/static/mobile.js?v=20261017_opt"></script>'
    
    if old_script_pattern in html:
        # Trouver la balise complète
        import re
        html_updated = re.sub(r'<script src="/static/mobile\.js[^"]*"></script>', new_script_tag, html)
        with open(MOBILE_HTML, "w", encoding="utf-8") as f:
            f.write(html_updated)
        print("[+] mobile.html mis à jour avec <script type='module'> !")
    elif 'type="module"' in html:
        print("[+] mobile.html utilise déjà les modules ES.")

    # 6. Mise à jour de sw.js pour le cache shell hors-ligne
    print(f"[*] Mise à jour de {SW_JS}...")
    with open(SW_JS, "r", encoding="utf-8") as f:
        sw = f.read()

    if "librairie-shell-v7" in sw:
        sw = sw.replace("librairie-shell-v7", "librairie-shell-v8")
    
    module_assets = """  '/mobile',
  '/static/mobile.js',
  '/static/js/mobile/main.js',
  '/static/js/mobile/core.js',
  '/static/js/mobile/state.js',
  '/static/js/mobile/api.js',
  '/static/js/mobile/network.js',
  '/static/js/mobile/pairing.js',
  '/static/js/mobile/cart.js',
  '/static/js/mobile/book_stats.js',
  '/static/js/mobile/modes.js',
  '/static/js/mobile/ocr.js',
  '/static/js/mobile/new_book_modal.js',
  '/static/js/mobile/search.js',
  '/static/js/mobile/scanner.js',
  '/static/js/mobile/fullscreen.js',"""

    if "SHELL_ASSETS = [" in sw and "/static/js/mobile/main.js" not in sw:
        sw = sw.replace("  '/mobile',\n  '/static/mobile.js',", module_assets)
        with open(SW_JS, "w", encoding="utf-8") as f:
            f.write(sw)
        print("[+] sw.js mis à jour avec la liste complète des modules ES hors-ligne !")

    print("[SUCCESS] Modularisation terminée avec succès !")

if __name__ == "__main__":
    run()
