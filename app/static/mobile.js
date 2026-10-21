/* Librairie – scanner mobile. 100 % hors-ligne, aucun innerHTML avec des données (anti-XSS), CSP stricte. */
'use strict';
const $ = s => document.querySelector(s);
const eur = n => (Number(n) || 0).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
const TOKEN_KEY = 'librairie_device_token', USER_KEY = 'librairie_user';
const DEVICE_KEY = 'librairie_device_key';
let currentMode = 'sale'; // 'sale' | 'recv'

/* ---------- Gestion dynamique de la hauteur visible du viewport (non-fullscreen / plein écran) ---------- */
function updateViewportHeight() {
  const vv = window.visualViewport;
  const h = vv ? vv.height : window.innerHeight;
  document.documentElement.style.setProperty('--vvh', `${Math.round(h)}px`);
}
updateViewportHeight();
if (window.visualViewport) {
  window.visualViewport.addEventListener('resize', updateViewportHeight);
}
window.addEventListener('resize', updateViewportHeight);
window.addEventListener('orientationchange', () => setTimeout(updateViewportHeight, 100));
window.addEventListener('pageshow', updateViewportHeight);
window.addEventListener('focus', updateViewportHeight);

const SVG_TAGS = new Set(['svg', 'path', 'line', 'circle', 'polyline', 'polygon', 'rect', 'g']);
const SVG_NS = 'http://www.w3.org/2000/svg';

/* Construction DOM sûre : le texte passe toujours par textContent / createTextNode */
function el(tag, props = {}, ...kids) {
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

function createStatsIcon() {
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

function toast(msg, kind = 'ok') {
  const t = el('div', { class: 'toast ' + kind, text: msg });
  $('#toasts').append(t);
  setTimeout(() => t.remove(), kind === 'err' ? 4500 : 2400);
}
function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.connect(g); g.connect(ctx.destination); o.frequency.value = 1760; g.gain.value = 0.15;
    o.start(); o.stop(ctx.currentTime + 0.08);
  } catch (e) { /* audio indisponible : sans importance */ }
  if (navigator.vibrate) navigator.vibrate(60);
}

/* ---------- API (jeton d'appareil + identité du libraire) ---------- */
async function api(url, { method = 'GET', body, auth = true, timeoutMs = 4000 } = {}) {
  const headers = {};
  if (auth) {
    const tok = localStorage.getItem(TOKEN_KEY);
    if (tok) headers['Authorization'] = 'Bearer ' + tok;
    headers['X-User'] = encodeURIComponent(currentUser || '');
  }
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  // Timeout automatique pour éviter que les requêtes s'empilent si le PC dort ou est déconnecté
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
      throw new Error('Poste central injoignable (délai dépassé). Vérifiez que l\'ordinateur est allumé.');
    }
    throw err;
  }

}

/* ---------- Surveillance Réseau & Heartbeat (/api/ping) ---------- */
let isNetworkOnline = true;
let pingFailCount = 0;
let pingIntervalTimer = null;

function markNetworkOffline() {
  if (!isNetworkOnline) return;
  isNetworkOnline = false;
  const alertEl = $('#netAlertBanner');
  const successEl = $('#netSuccessBanner');
  if (successEl) successEl.style.display = 'none';
  if (alertEl) alertEl.style.display = 'block';
  if (navigator.vibrate) navigator.vibrate([120, 60, 120]);
}

function markNetworkOnline() {
  if (isNetworkOnline) return;
  isNetworkOnline = true;
  pingFailCount = 0;
  const alertEl = $('#netAlertBanner');
  const successEl = $('#netSuccessBanner');
  if (alertEl) alertEl.style.display = 'none';
  if (successEl) {
    successEl.style.display = 'block';
    setTimeout(() => { successEl.style.display = 'none'; }, 2600);
  }
}

async function checkPing(manual = false) {
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
        mMoment = data.active_moment;
      }
      if (data.ips && data.ips.length) {
        localStorage.setItem('librairie_known_ips', JSON.stringify({ ips: data.ips, mdns: data.mdns_host }));
      }
    } else {
      throw new Error('Ping ' + res.status);
    }
  } catch (err) {
    clearTimeout(timer);
    pingFailCount++;
    if (pingFailCount >= 2 || !navigator.onLine) {
      markNetworkOffline();
    }
  } finally {
    if (manual && retryBtn) retryBtn.textContent = 'Réessayer';
  }
}

function startNetworkMonitor() {
  if (pingIntervalTimer) clearInterval(pingIntervalTimer);
  pingIntervalTimer = setInterval(() => checkPing(false), 4000);

  window.addEventListener('offline', () => markNetworkOffline());
  window.addEventListener('online', () => checkPing(true));

  const retryBtn = $('#btnNetRetry');
  if (retryBtn) {
    retryBtn.addEventListener('click', () => checkPing(true));
  }
}

let liveCartSyncTimer = null;
let pendingLiveAction = null;

function logMobileLiveActivity(type, title, detail, data = {}) {
  api('/api/live/activity', {
    method: 'POST',
    body: {
      type,
      user_name: currentUser || 'Libraire Mobile',
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

function syncLiveCart(action = null) {
  if (!localStorage.getItem(TOKEN_KEY)) return;
  if (action) pendingLiveAction = action;
  if (liveCartSyncTimer) clearTimeout(liveCartSyncTimer);
  liveCartSyncTimer = setTimeout(async () => {
    const act = pendingLiveAction;
    pendingLiveAction = null;
    try {
      const isCartActive = cart && cart.length > 0;
      const total = isCartActive ? cart.reduce((s, i) => s + i.qty * (i.book ? i.book.price : 0), 0) : 0;
      const count = isCartActive ? cart.reduce((s, i) => s + i.qty, 0) : 0;
      const items = isCartActive ? cart.map(i => ({
        title: (i.book ? i.book.title : 'Livre') + (i.book && i.book.volume ? ' · Vol. ' + i.book.volume : ''),
        qty: i.qty,
        price: i.book ? i.book.price : 0
      })) : [];

      await api('/api/mobile/active-cart', {
        method: 'POST',
        body: {
          user_name: currentUser || 'Libraire Mobile',
          device_key: localStorage.getItem(DEVICE_KEY) || undefined,
          total,
          qty: count,
          items,
          mode: currentMode || 'sale',
          moment: (typeof mMoment !== 'undefined' && mMoment) ? mMoment : (typeof getAutoMobileMoment === 'function' ? getAutoMobileMoment() : 'En semaine / Autre'),
          gender: (typeof mGender !== 'undefined' && mGender) ? mGender : null,
          age: (typeof mAge !== 'undefined' && mAge) ? mAge : null,
          star: (typeof mStar !== 'undefined' && mStar) ? 1 : 0,
          battery: mobileBatteryInfo ? mobileBatteryInfo.level : null,
          is_charging: mobileBatteryInfo ? mobileBatteryInfo.charging : null,
          action: act
        }
      });
    } catch (e) {
      // Ignorer silencieusement si temporairement déconnecté
    }
  }, 120);
}

function clearLiveCartSync(reason = 'session_closed') {
  if (liveCartSyncTimer) { clearTimeout(liveCartSyncTimer); liveCartSyncTimer = null; }
  api(`/api/mobile/active-cart?reason=${encodeURIComponent(reason)}`, { method: 'DELETE' }).catch(() => {});
}

function saveActiveCart(action = null) {
  if (action && action.type && action.type !== 'cart_cleared' && action.type !== 'sale_cleared') {
    logMobileLiveActivity(action.type, action.title || '', action.detail || '', action);
  }
  if (cart && cart.length > 0) {
    const data = {
      cart,
      originPayments,
      gender: mGender,
      age: mAge,
      star: mStar,
      timestamp: Date.now()
    };
    localStorage.setItem('librairie_mobile_active_cart', JSON.stringify(data));
  } else {
    localStorage.removeItem('librairie_mobile_active_cart');
  }
  syncLiveCart(action);
}

function restoreActiveCart() {
  const raw = localStorage.getItem('librairie_mobile_active_cart');
  if (!raw) return;
  try {
    const data = JSON.parse(raw);
    if (data && data.cart && data.cart.length > 0) {
      cart = data.cart;
      originPayments = data.originPayments || {};
      mGender = data.gender || '';
      mAge = data.age || '';
      mStar = data.star || 0;
      const sBtn = $('#mBtnStar'); if (sBtn) sBtn.classList.toggle('on', !!mStar);
      const gEl = $('#mDemoGender');
      if (gEl) {
        gEl.classList.toggle('is-couple', mGender === 'Couple');
        gEl.querySelector('button[data-g="Femme"]')?.classList.toggle('on', mGender === 'Femme' || mGender === 'Couple');
        gEl.querySelector('button[data-g="Homme"]')?.classList.toggle('on', mGender === 'Homme' || mGender === 'Couple');
        const cb = $('#mCoupleBadge');
        if (cb) cb.style.display = mGender === 'Couple' ? 'block' : 'none';
      }
      const aEl = $('#mDemoAge');
      if (aEl) {
        aEl.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.a === mAge));
      }
      if (mGender || mAge || mStar) collapseMobileProfile();
      syncLiveCart();
    }
  } catch (e) {
    localStorage.removeItem('librairie_mobile_active_cart');
  }
}

// Heartbeat toutes les 15s pour maintenir le mobile connecté/actif sur la Régie Live
setInterval(() => {
  if (localStorage.getItem(TOKEN_KEY)) {
    syncLiveCart();
  }
}, 15000);

// Déconnexion propre de la session lors de la fermeture de l'onglet/navigateur
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

/* ---------- appairage ---------- */
function deviceLabel() {
  const m = navigator.userAgent.match(/\(([^)]+)\)/);
  return (m ? m[1] : 'Téléphone').replace(/[;]\s*wv/i, '').slice(0, 50);
}
async function pairFromHash() {
  const m = location.hash.match(/pair=([A-Za-z0-9_-]{8,64})/);
  if (!m) return;
  history.replaceState(null, '', location.pathname);        // le code disparaît de la barre d'adresse et de l'historique
  try {
    let deviceKey = localStorage.getItem(DEVICE_KEY);
    if (!deviceKey) {
      const bytes = new Uint8Array(24);
      crypto.getRandomValues(bytes);
      deviceKey = Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('');
      localStorage.setItem(DEVICE_KEY, deviceKey);
    }
    const r = await api('/api/mobile/pair', {
      method: 'POST',
      body: {
        code: m[1],
        name: deviceLabel(),
        device_key: deviceKey,
        previous_token: localStorage.getItem(TOKEN_KEY) || undefined
      },
      auth: false
    });
    localStorage.setItem(TOKEN_KEY, r.token);
    toast('Téléphone appairé avec succès');
  } catch (e) { toast(e.message, 'err'); }
}
function showPairing() { $('#pairScreen').hidden = false; stopCamera(); }
$('#btnRetryPair').addEventListener('click', () => location.reload());

/* ---------- profil libraire ---------- */
let currentUser = localStorage.getItem(USER_KEY) || '';
let users = [];
function updateUser() { $('#userName').textContent = currentUser || 'Choisir…'; }
function openUserModal() {
  const list = $('#userList');
  if (!users.length) {
    list.replaceChildren(
      el('p', { class: 'muted', style: 'margin-bottom:12px;font-size:12.5px', text: 'Serveur hors-ligne ou liste d\'utilisateurs indisponible. Saisissez votre prénom :' }),
      el('input', {
        class: 'field',
        id: 'offlineUserNameInput',
        placeholder: 'Votre prénom…',
        value: currentUser,
        style: 'width:100%;margin-bottom:10px;font-weight:700'
      }),
      el('button', {
        class: 'btn primary',
        type: 'button',
        style: 'width:100%;padding:12px;font-weight:700',
        text: 'Enregistrer mon profil',
        onclick: () => {
          const inp = $('#offlineUserNameInput');
          const val = inp ? inp.value.trim() : '';
          if (val) {
            currentUser = val;
            localStorage.setItem(USER_KEY, val);
            updateUser();
            $('#userModal').hidden = true;
            toast('Connecté : ' + val);
            syncLiveCart({ type: 'user_connected', user_name: val });
          }
        }
      })
    );
  } else {
    list.replaceChildren(...users.map(u => el('button', {
      class: 'user-btn', type: 'button', text: u.name,
      onclick: () => {
        currentUser = u.name;
        localStorage.setItem(USER_KEY, u.name);
        updateUser();
        $('#userModal').hidden = true;
        toast('Connecté : ' + u.name);
        syncLiveCart({ type: 'user_connected', user_name: u.name });
      }
    })));
  }
  $('#userModal').hidden = false;
}
$('#userBtn').addEventListener('click', openUserModal);
const userCloseBtn = $('#userModalClose');
if (userCloseBtn) userCloseBtn.addEventListener('click', () => { $('#userModal').hidden = true; });
const userModalEl = $('#userModal');
if (userModalEl) userModalEl.addEventListener('click', e => {
  if (e.target.id === 'userModal') userModalEl.hidden = true;
});

/* ---------- Panier & Origines (Smart Split) & Multi-paiement ---------- */
let cart = [];            // { book, qty, lot }  lot: undefined = pas encore choisi | id de lot
let payOptions = ['Espèces', 'CB', 'Wero'];
let originPayments = {};  // { [ownerName]: { method: 'CB'|'Espèces'|'Wero'|'Multi', parts: [{payment, amount}]|null } }

function getItemOwner(item) {
  if (item.book.is_pack) return 'Cité Royale';
  if (item.lot === undefined || item.lot === null || item.lot === 'none') return 'À préciser';
  const l = (item.book.lots || []).find(x => x.id === item.lot);
  return (l && l.owner) ? l.owner.trim() : 'Autre';
}

function getCartByOrigin() {
  const groups = {};
  for (const item of cart) {
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

function getDefaultPaymentForOwner(owner) {
  const ow = (owner || '').toLowerCase();
  if (ow === 'cité royale') return 'CB'; // Cité Royale va vers le TPE / PayPal POS
  return 'Espèces'; // ICC Rennes et autres alimentent la caisse physique
}

function lotRemaining(item) {
  if (item.book.is_pack) return item.book.stock != null ? item.book.stock : 0;
  if (item.lot === undefined || item.lot === null || item.lot === 'none') return 0;
  const l = (item.book.lots || []).find(x => x.id === item.lot);
  return l ? l.remaining : 0;
}

function defaultLotForBook(book) {
  const lots = (book.lots || []).filter(l => l.remaining > 0);
  if (!lots.length) return undefined;
  if (lots.length === 1) return lots[0].id;
  const cr = lots.find(l => (l.owner || '').trim().toLowerCase() === 'cité royale');
  return cr ? cr.id : lots[0].id;
}

let currentUpsellContext = null;

function checkAndShowPackUpsell(book) {
  const packs = (book.suggested_packs || []).filter(p => p.saving > 0);
  if (!packs.length) {
    hidePackUpsell();
    return;
  }
  const pack = packs.find(p => p.stock > 0) || packs[0];
  currentUpsellContext = { singleBook: book, pack };

  const card = $('#packUpsellCard');
  if (!card) return;
  $('#packUpsellTitle').textContent = pack.title;
  $('#packUpsellOldPrice').textContent = eur(pack.separate_price);
  $('#packUpsellPrice').textContent = eur(pack.price);
  $('#packUpsellOther').textContent = pack.other_items || 'Articles du pack';
  $('#packUpsellSavingBadge').textContent = `Éco ${eur(pack.saving)}`;
  card.style.display = 'block';
}

function hidePackUpsell() {
  currentUpsellContext = null;
  const card = $('#packUpsellCard');
  if (card) card.style.display = 'none';
}

function addPackToCart(pack) {
  const stock = pack.stock != null ? pack.stock : 0;
  if (stock <= 0) {
    toast(`Stock épuisé (0 dispo) pour ce pack. Vente impossible.`, 'err');
    return;
  }
  beep();
  const ex = cart.find(i => i.book.id === pack.id);
  if (ex) {
    if (ex.qty + 1 > stock) toast(`Stock maximum atteint (${stock} ex.) pour ce pack`, 'warn');
    else ex.qty++;
  } else {
    cart.push({ book: pack, qty: 1, lot: 'pack' });
  }
  toast('Pack ajouté : ' + pack.title);
  saveActiveCart({ type: 'pack_added', title: pack.title, price: pack.price });
  renderCart();
}

function addToCart(book) {
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
  const ex = cart.find(i => i.book.id === book.id && (i.lot === defLot || i.lot === undefined));
  if (ex) {
    if (ex.lot === undefined && defLot !== undefined) ex.lot = defLot;
    if (ex.qty + 1 > lotRemaining(ex)) {
      toast(`Stock disponible atteint (${lotRemaining(ex)} ex.) pour « ${book.title} ».`, 'warn');
      return;
    }
    ex.qty++;
  } else {
    cart.push({ book, qty: 1, lot: defLot });
  }
  toast('Ajouté : ' + book.title);
  saveActiveCart({ type: 'book_added', title: book.title, price: book.price });
  renderCart();
  checkAndShowPackUpsell(book);
}

/* ---------- Modale Paiement Fractionné / Multi-modes ---------- */
let activeMpOwner = null;
let activeMpTotal = 0;
let mpMode1 = 'Espèces';
let mpMode2 = 'CB';

function openMultiPayModal(owner, total) {
  activeMpOwner = owner;
  activeMpTotal = total;
  const badge = $('#mpOriginBadge');
  if (badge) badge.textContent = owner;
  const tVal = $('#mpTotalVal');
  if (tVal) tVal.textContent = eur(total);
  
  if ((owner || '').toLowerCase() === 'cité royale') {
    mpMode1 = 'CB';
    mpMode2 = 'Espèces';
  } else {
    mpMode1 = 'Espèces';
    mpMode2 = 'CB';
  }

  const existing = originPayments[owner]?.parts;
  if (existing && existing.length >= 2) {
    mpMode1 = existing[0].payment;
    mpMode2 = existing[1].payment;
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

function closeMultiPayModal() {
  $('#multiPayModal').hidden = true;
  activeMpOwner = null;
}

function renderMpModes() {
  const m1El = $('#mpModes1');
  const m2El = $('#mpModes2');
  if (!m1El || !m2El) return;
  const available = payOptions.length ? payOptions : ['Espèces', 'CB', 'Wero'];
  
  m1El.replaceChildren(...available.map(p => el('button', {
    type: 'button',
    class: 'chip' + (mpMode1 === p ? ' on' : ''),
    style: 'flex:1;justify-content:center;padding:5px 4px;font-size:11.5px',
    onclick: () => {
      mpMode1 = p;
      if (mpMode2 === p) {
        const other = available.find(x => x !== p);
        if (other) mpMode2 = other;
      }
      renderMpModes();
      updateMpCalculations();
    }
  }, p)));

  m2El.replaceChildren(...available.map(p => el('button', {
    type: 'button',
    class: 'chip' + (mpMode2 === p ? ' on' : ''),
    style: 'flex:1;justify-content:center;padding:5px 4px;font-size:11.5px',
    onclick: () => {
      mpMode2 = p;
      if (mpMode1 === p) {
        const other = available.find(x => x !== p);
        if (other) mpMode1 = other;
      }
      renderMpModes();
      updateMpCalculations();
    }
  }, p)));
}

function updateMpCalculations() {
  const a1 = parseFloat($('#mpAmount1').value) || 0;
  const rem = Math.max(0, Math.round((activeMpTotal - a1) * 100) / 100);
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
  } else if (mpMode1 === mpMode2) {
    btnApply.disabled = true;
    hint.textContent = 'Choisissez deux modes différents';
  } else {
    btnApply.disabled = false;
    hint.textContent = '';
  }
}

const mpAmt1 = $('#mpAmount1');
if (mpAmt1) mpAmt1.addEventListener('input', updateMpCalculations);
document.querySelectorAll('[data-mpq]').forEach(btn => {
  btn.addEventListener('click', () => {
    const q = btn.dataset.mpq;
    let val = 0;
    if (q === 'half') val = Math.round((activeMpTotal / 2) * 100) / 100;
    else val = parseFloat(q) || 0;
    if (val >= activeMpTotal) val = Math.max(1, activeMpTotal - 1);
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
  if (!activeMpOwner || a1 <= 0 || a2 <= 0) return;
  originPayments[activeMpOwner] = {
    method: 'Multi',
    parts: [
      { payment: mpMode1, amount: a1 },
      { payment: mpMode2, amount: a2 }
    ]
  };
  saveActiveCart({ type: 'smart_split', owner: activeMpOwner, detail: `${a1.toFixed(2)} € ${mpMode1} + ${a2.toFixed(2)} € ${mpMode2}` });
  closeMultiPayModal();
  renderCart();
  toast('Cumul défini pour ' + activeMpOwner);
});

/* Composant factorisé pour les éléments du panier mobile */
function renderMobileCartItem(item, idx) {
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
            if (isRemoved) cart.splice(idx, 1);
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
          if (isRemoved) cart.splice(idx, 1);
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
    item.lot === undefined ? el('div', { class: 'hint', text: 'Touchez l\'origine de cet exemplaire' }) : null);
}

function renderCart() {
  const count = cart.reduce((s, i) => s + i.qty, 0);
  const total = cart.reduce((s, i) => s + i.qty * i.book.price, 0);
  $('#cartCount').textContent = count;
  $('#totalVal').textContent = eur(total);
  updateMobileStandbyUI();

  const list = $('#cartItems');
  if (!cart.length) {
    list.replaceChildren(el('div', { class: 'muted', style: 'text-align:center;padding:18px', text: 'Visez le code-barres d\'un livre pour commencer.' }));
  } else {
    list.replaceChildren(...cart.map(renderMobileCartItem));
  }

  const origins = getCartByOrigin();
  const singleRow = $('#singleOriginRow');
  const splitCont = $('#splitOriginsContainer');
  const payChipsEl = $('#payChips');
  const availablePays = payOptions.length ? payOptions : ['Espèces', 'CB', 'Wero'];

  // Nettoyer originPayments des origines qui ne sont plus dans le panier
  const validOwners = new Set(origins.map(o => o.owner));
  for (const k of Object.keys(originPayments)) {
    if (k !== '_default' && !validOwners.has(k)) {
      delete originPayments[k];
    }
  }

  const fAmt = a => (a % 1 === 0 ? a.toFixed(0) : a.toFixed(2).replace('.', ',')) + ' €';
  const fPay = p => (p === 'Espèces' ? 'Esp.' : p);

  if (origins.length <= 1) {
    // Cas 1 : Origine Unique (ou panier vide)
    if (singleRow) singleRow.style.display = 'block';
    if (splitCont) splitCont.style.display = 'none';

    const currentOwner = origins[0] ? origins[0].owner : '_default';
    if (!originPayments[currentOwner]) {
      originPayments[currentOwner] = { method: getDefaultPaymentForOwner(currentOwner), parts: null };
    }
    const currentPay = originPayments[currentOwner];

    // Invalidation si le total a changé
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
          originPayments[currentOwner] = { method: p, parts: null };
          saveActiveCart({ type: 'payment_selected', method: p, owner: currentOwner });
          renderCart();
        }
      }, p));

      // Gestion du résumé multi-mode (sur la même ligne que Total) et du bouton Multi compact
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
            if (!total) return toast('Ajoutez d\'abord un livre au panier', 'warn');
            openMultiPayModal(currentOwner, total);
          }
        }, '＋ Multi'));
      }
      payChipsEl.replaceChildren(...chips);
    }
    $('#btnValidate').textContent = total > 0 ? `Valider (${eur(total)})` : 'Valider';
  } else {
    // Cas 2 : Smart Split - Origines multiples (Cité Royale + ICC Rennes...)
    if (singleRow) singleRow.style.display = 'none';
    const mpSumm = $('#multiPaySummary');
    if (mpSumm) mpSumm.style.display = 'none';
    if (splitCont) splitCont.style.display = 'flex';

    if (splitCont) {
      splitCont.replaceChildren(...origins.map(g => {
        if (!originPayments[g.owner]) {
          originPayments[g.owner] = { method: getDefaultPaymentForOwner(g.owner), parts: null };
        }
        const payState = originPayments[g.owner];
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
            originPayments[g.owner] = { method: p, parts: null };
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

  const missingLot = cart.some(i => i.lot === undefined);
  const missingPay = origins.some(g => !originPayments[g.owner] || (!originPayments[g.owner].method && !originPayments[g.owner].parts));
  $('#btnValidate').disabled = !cart.length || missingLot || missingPay;
  $('#validHint').textContent = !cart.length ? '' : missingLot ? 'Choisissez l\'origine de chaque livre' : missingPay ? 'Choisissez le mode de paiement' : '';
  saveActiveCart();
}
$('#clearCart').addEventListener('click', () => {
  cart = [];
  originPayments = {};
  hidePackUpsell();
  mGender = ''; mAge = ''; mStar = 0;
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

function updateMobileStandbyUI() {
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
      btnStby.style.display = cart.length > 0 ? 'inline-flex' : 'none';
    }
  } else {
    banner.style.display = 'none';
    btnStby.style.display = cart.length > 0 ? 'inline-flex' : 'none';
  }
}

const mBtnStandby = $('#mBtnStandby');
if (mBtnStandby) {
  mBtnStandby.addEventListener('click', () => {
    if (!cart.length) return;
    const count = cart.reduce((s, i) => s + i.qty, 0);
    const total = cart.reduce((s, i) => s + i.qty * i.book.price, 0);
    const standbyData = {
      cart: JSON.parse(JSON.stringify(cart)),
      originPayments: JSON.parse(JSON.stringify(originPayments)),
      gender: mGender,
      age: mAge,
      star: mStar,
      total: eur(total),
      qty: count,
      timestamp: Date.now()
    };
    localStorage.setItem('librairie_mobile_standby_cart', JSON.stringify(standbyData));
    localStorage.removeItem('librairie_mobile_active_cart');
    clearLiveCartSync('standby_saved');
    logMobileLiveActivity('standby_saved', 'Panier mis en attente', `${count} articles · ${eur(total)}`, { count, total });

    cart = [];
    originPayments = {};
    hidePackUpsell();
    mGender = ''; mAge = ''; mStar = 0;
    if (mStarBtn) mStarBtn.classList.remove('on');
    if (mGenEl) {
      mGenEl.classList.remove('is-couple');
      mGenEl.querySelectorAll('button').forEach(b => b.classList.remove('on'));
      const cb = $('#mCoupleBadge');
      if (cb) cb.style.display = 'none';
    }
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
    if (cart.length > 0) {
      if (!confirm("Un panier est déjà en cours. Voulez-vous le remplacer par le panier en attente ?")) return;
    }
    try {
      const data = JSON.parse(raw);
      cart = data.cart || [];
      originPayments = data.originPayments || {};
      mGender = data.gender || '';
      mAge = data.age || '';
      mStar = data.star || 0;

      if (mStarBtn) mStarBtn.classList.toggle('on', !!mStar);
      if (mGenEl) {
        mGenEl.classList.toggle('is-couple', mGender === 'Couple');
        mGenEl.querySelector('button[data-g="Femme"]')?.classList.toggle('on', mGender === 'Femme' || mGender === 'Couple');
        mGenEl.querySelector('button[data-g="Homme"]')?.classList.toggle('on', mGender === 'Homme' || mGender === 'Couple');
        const cb = $('#mCoupleBadge');
        if (cb) cb.style.display = mGender === 'Couple' ? 'block' : 'none';
      }
      if (mAgeEl) {
        mAgeEl.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.a === mAge));
      }
      if (mGender || mAge || mStar) collapseMobileProfile(); else expandMobileProfile();

      localStorage.removeItem('librairie_mobile_standby_cart');
      saveActiveCart({ type: 'standby_resumed', count: cart.length });
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
    if (!currentUpsellContext) return;
    const { singleBook, pack } = currentUpsellContext;
    const idx = cart.findIndex(i => i.book.id === singleBook.id);
    if (idx !== -1) {
      if (cart[idx].qty > 1) {
        cart[idx].qty--;
      } else {
        cart.splice(idx, 1);
      }
    }
    addPackToCart(pack);
    toast(`✓ Converti en ${pack.title} (-${eur(pack.saving)} d'économie) !`);
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

let dbAuthors = [];
let dbPublishers = [];

async function loadPayOptions() {
  try {
    const o = await api('/api/options');
    payOptions = (o.payment || []).map(p => (p.label === 'PayPal POS (CB)' || p.label.toLowerCase().includes('paypal') ? 'CB' : p.label));
    dbPublishers = (o.publisher || []).map(p => p.label);
    dbAuthors = o.authors || [];
    const dl = $('#dl_nb_publishers');
    if (dl && dbPublishers.length) {
      dl.innerHTML = dbPublishers.map(p => `<option value="${esc(p)}">`).join('');
    }
  } catch (e) { payOptions = []; }
  if (!payOptions.length) payOptions = ['Espèces', 'CB', 'Wero'];
  payOptions = Array.from(new Set(payOptions));
  renderCart();
}


let mGender = '';
let mAge = '';
let mStar = 0;

const MOMENT_ICONS = {
  '1er Culte (Principal)': '☀️ 1er Culte',
  '2e Culte (Jeunes EJP)': '⚡ 2e Culte',
  'Occasion spéciale': '✨ Spécial',
  'En semaine / Autre': '📅 Semaine',
};

function getAutoMobileMoment() {
  const isSunday = new Date().getDay() === 0;
  const currentHour = new Date().getHours();
  return isSunday ? (currentHour >= 12 ? '2e Culte (Jeunes EJP)' : '1er Culte (Principal)') : 'En semaine / Autre';
}

// Le réglage du culte / temps de vente est géré de manière maître sur le poste PC
let mMoment = getAutoMobileMoment();


let mDemoTimer = null;

function getMobileProfileSummary() {
  const parts = [];
  if (mGender === 'Couple') parts.push('Couple 💜');
  else if (mGender) parts.push(mGender);

  const ageMap = {
    'Enfant / Ado': '<18 ans',
    'Jeune adulte': '18-29 ans',
    'Adulte': '30-59 ans',
    'Senior': '60+ ans'
  };
  if (mAge) parts.push(ageMap[mAge] || mAge);
  if (mStar) parts.push('⭐ STAR');
  return parts.join(' · ');
}

function collapseMobileProfile() {
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

function expandMobileProfile() {
  if (mDemoTimer) { clearTimeout(mDemoTimer); mDemoTimer = null; }
  const cardExp = $('#mDemoCardExpanded');
  const cardCol = $('#mDemoCardCollapsed');
  if (cardExp) cardExp.style.display = 'block';
  if (cardCol) cardCol.style.display = 'none';
}

function scheduleMobileProfileCollapse() {
  if (mDemoTimer) { clearTimeout(mDemoTimer); mDemoTimer = null; }
  saveActiveCart();
  if (!mGender && !mAge && !mStar) {
    expandMobileProfile();
    return;
  }
  mDemoTimer = setTimeout(() => {
    collapseMobileProfile();
  }, 5000);
}

function updateProfileSummary() {
  if (!mGender && !mAge && !mStar) {
    expandMobileProfile();
  } else {
    collapseMobileProfile();
  }
}

const mCardCol = $('#mDemoCardCollapsed');
if (mCardCol) {
  mCardCol.onclick = () => {
    expandMobileProfile();
  };
}

/* ---------- Modale Statistiques Livre Caisse & Réassurance Mobile ---------- */
async function openMobileBookStats(bid) {
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

      // 3 KPIs
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

      // Derniers Achats (si existants)
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

      // Mention Pack associé
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

function closeMobileBookStats() {
  const modal = $('#bookStatsModal');
  if (modal) modal.hidden = true;
}

const bsModalEl = $('#bookStatsModal');
if (bsModalEl) {
  bsModalEl.addEventListener('click', e => {
    if (e.target === bsModalEl) closeMobileBookStats();
  });
}

/* ---------- Contrôle de la taille de la Caméra (Plein écran Panier) & Veille auto ---------- */
const camCont = $('#camContainer');
const btnToggleCamSize = $('#btnToggleCamSize');
const camMinibar = $('#camMinibar');
const camMinibarText = $('#camMinibarText');

function toggleCamMinimize(forceMin, reason = 'manual') {
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
if (btnToggleCamSize) btnToggleCamSize.addEventListener('click', () => toggleCamMinimize());
if (camMinibar) camMinibar.addEventListener('click', () => toggleCamMinimize(false));

const mStarBtn = $('#mBtnStar');
if (mStarBtn) {
  mStarBtn.addEventListener('click', () => {
    mStar = mStar ? 0 : 1;
    mStarBtn.classList.toggle('on', !!mStar);
    scheduleMobileProfileCollapse();
    saveActiveCart({ type: 'profile_star', star: !!mStar });
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
        mGender = 'Couple';
        mGenEl.classList.add('is-couple');
        if (cBadge) cBadge.style.display = 'block';
      } else if (fOn) {
        mGender = 'Femme';
        mGenEl.classList.remove('is-couple');
        if (cBadge) cBadge.style.display = 'none';
      } else if (hOn) {
        mGender = 'Homme';
        mGenEl.classList.remove('is-couple');
        if (cBadge) cBadge.style.display = 'none';
      } else {
        mGender = '';
        mGenEl.classList.remove('is-couple');
        if (cBadge) cBadge.style.display = 'none';
      }
      scheduleMobileProfileCollapse();
      saveActiveCart({ type: 'profile_gender', gender: mGender });
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
        mAge = '';
      } else {
        b.classList.add('on');
        mAge = b.dataset.a;
      }
      scheduleMobileProfileCollapse();
      saveActiveCart({ type: 'profile_age', age: mAge });
    }
  });
}

$('#btnValidate').addEventListener('click', async () => {
  if (!currentUser) return openUserModal();
  const btn = $('#btnValidate');
  btn.disabled = true; // anti double-envoi : un seul encaissement par appui
  
  const origins = getCartByOrigin();
  if (!origins.length) {
    btn.disabled = false;
    return;
  }

  const unassigned = cart.find(i => !i.book.is_pack && (i.lot === undefined || i.lot === null || i.lot === 'none'));
  if (unassigned) {
    toast(`Indiquez l'origine en stock pour « ${unassigned.book.title} » avant d'encaisser.`, 'warn');
    btn.disabled = false;
    return;
  }

  const zeroStock = cart.find(i => lotRemaining(i) < i.qty);
  if (zeroStock) {
    toast(`Stock insuffisant pour « ${zeroStock.book.title} » (${zeroStock.qty} demandés, ${lotRemaining(zeroStock)} dispo).`, 'err');
    btn.disabled = false;
    return;
  }

  try {
    const validatedSales = [];
    for (let idx = 0; idx < origins.length; idx++) {
      const g = origins[idx];
      const payState = originPayments[g.owner] || { method: 'Espèces', parts: null };
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
        customer_gender: mGender || null,
        customer_age_group: mAge || null,
        is_star: mStar ? 1 : 0,
        service_moment: mMoment || null,
        lines
      };

      try {
        const res = await api('/api/sales', { method: 'POST', body: payload });
        validatedSales.push({ id: res.id, owner: g.owner, total: res.total });
        // Retirer les articles validés du panier au fur et à mesure
        cart = cart.filter(item => getItemOwner(item) !== g.owner);
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

    cart = [];
    originPayments = {};
    hidePackUpsell();
    mGender = ''; mAge = ''; mStar = 0;
    localStorage.removeItem('librairie_mobile_active_cart');
    if (mStarBtn) mStarBtn.classList.remove('on');
    if (mGenEl) {
      mGenEl.classList.remove('is-couple');
      mGenEl.querySelectorAll('button').forEach(b => b.classList.remove('on'));
      const cb = $('#mCoupleBadge');
      if (cb) cb.style.display = 'none';
    }
    if (mAgeEl) mAgeEl.querySelectorAll('button').forEach(b => b.classList.remove('on'));
    updateProfileSummary();
  } catch (e) {
    toast(e.message, 'err');
  } finally {
    renderCart();
  }
});

/* ---------- Mode de travail Mobile : Vente vs Réception ---------- */
currentMode = 'sale'; // 'sale' | 'recv'
let recvList = [];        // [{ book, qty }]
let ownersList = [];

function saveRecvList() {
  if (recvList && recvList.length > 0) {
    localStorage.setItem('librairie_mobile_recv_list', JSON.stringify(recvList));
  } else {
    localStorage.removeItem('librairie_mobile_recv_list');
  }
}

function restoreRecvList() {
  const raw = localStorage.getItem('librairie_mobile_recv_list');
  if (!raw) return;
  try {
    const data = JSON.parse(raw);
    if (Array.isArray(data) && data.length > 0) {
      recvList = data;
      renderRecv();
    }
  } catch (e) {
    localStorage.removeItem('librairie_mobile_recv_list');
  }
}

async function loadOwners() {
  try {
    ownersList = await api('/api/owners');
    const sel = $('#recvOwner');
    if (sel) {
      sel.replaceChildren(...ownersList.map(o => el('option', { value: o.id, text: o.name + (o.kind ? ` (${o.kind})` : '') })));
    }
  } catch (e) { ownersList = []; }
}

function setMobileMode(mode, updateHash = true, showToast = false) {
  if (mode !== 'sale' && mode !== 'recv') mode = 'sale';
  currentMode = mode;
  if (updateHash && location.hash !== '#' + mode) {
    location.hash = '#' + mode;
  }
  $('#btnModeSale').classList.toggle('on', mode === 'sale');
  $('#btnModeRecv').classList.toggle('on', mode === 'recv');
  $('#cartCard').hidden = (mode !== 'sale');
  $('#saleBottom').hidden = (mode !== 'sale');
  $('#recvCard').hidden = (mode !== 'recv');
  $('#recvBottom').hidden = (mode !== 'recv');
  if (mode === 'recv' && !ownersList.length) loadOwners();
  if (showToast) toast(mode === 'sale' ? 'Mode Vente actif' : 'Mode Réception actif', 'ok');
  syncLiveCart({ type: 'mode_changed', mode });
}

window.addEventListener('hashchange', () => {
  const h = location.hash.replace(/^#/, '');
  if ((h === 'sale' || h === 'recv') && h !== currentMode) {
    setMobileMode(h, false, false);
  }
});

$('#btnModeSale').addEventListener('click', () => setMobileMode('sale', true, true));
$('#btnModeRecv').addEventListener('click', () => setMobileMode('recv', true, true));

/* ---------- Logique Réception de stock ---------- */
function addToRecv(book) {
  beep();
  const ex = recvList.find(i => i.book.id === book.id);
  if (ex) {
    ex.qty++;
  } else {
    recvList.push({ book, qty: 1 });
  }
  toast(`+1 ${book.title}`, 'ok');
  logMobileLiveActivity('recv_item', book.title, `+1 ex. (total ${ex ? ex.qty : 1})`, { book_id: book.id });
  renderRecv();
}

function renderRecv() {
  const count = recvList.reduce((s, i) => s + i.qty, 0);
  $('#recvCount').textContent = count;
  const list = $('#recvItems');
  if (!recvList.length) {
    list.replaceChildren(el('div', { class: 'muted', style: 'text-align:center;padding:18px', text: 'Scannez chaque livre du carton pour le comptabiliser.' }));
    $('#btnValidateRecv').disabled = true;
  } else {
    $('#btnValidateRecv').disabled = false;
    list.replaceChildren(...recvList.map((item, idx) => {
      const b = item.book;
      return el('div', { class: 'cart-item' },
        el('div', { class: 'ci-top' },
          el('div', {},
            el('div', { class: 'ci-title', text: b.title + (b.volume ? ' · Vol. ' + b.volume : '') }),
            el('div', { class: 'muted', text: `${b.code} · ${eur(b.price)}` })),
          el('div', { class: 'qty' },
            el('button', { type: 'button', text: '−', onclick: () => { item.qty--; if (item.qty <= 0) recvList.splice(idx, 1); renderRecv(); } }),
            el('b', { text: item.qty }),
            el('button', { type: 'button', text: '+', onclick: () => { item.qty++; renderRecv(); } }))));
    }));
  }
  saveRecvList();
}

$('#clearRecv').addEventListener('click', () => {
  recvList = [];
  localStorage.removeItem('librairie_mobile_recv_list');
  renderRecv();
});

$('#btnValidateRecv').addEventListener('click', async () => {
  if (!currentUser) return openUserModal();
  const ownerId = parseInt($('#recvOwner').value);
  if (!ownerId) return toast('Veuillez sélectionner un propriétaire', 'warn');
  const btn = $('#btnValidateRecv');
  btn.disabled = true;
  try {
    const totalCount = recvList.reduce((s, i) => s + i.qty, 0);
    const ownerLabel = $('#recvOwner option:checked')?.textContent || 'Rayon';
    for (const item of recvList) {
      await api('/api/lots', {
        method: 'POST',
        body: {
          book_id: item.book.id,
          owner_id: ownerId,
          qty_in: item.qty,
          note: `Réception mobile par ${currentUser}`
        }
      });
    }
    toast(`${totalCount} exemplaire(s) entrés en stock`, 'ok');
    logMobileLiveActivity('recv_validated', `${totalCount} ex. entrés en stock`, `Propriétaire : ${ownerLabel}`, { count: totalCount });
    if (navigator.vibrate) navigator.vibrate([60, 40, 60]);
    recvList = [];
    localStorage.removeItem('librairie_mobile_recv_list');
    renderRecv();
  } catch (e) {
    toast(e.message, 'err');
    btn.disabled = false;
  }
});

/* ---------- Traitement OCR Page de Garde & Couverture ---------- */
async function fileToResizedBase64(file, maxDim = 1600) {
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

async function performOcr(file) {
  const b64 = await fileToResizedBase64(file, 1600);
  return api('/api/ocr/scan', {
    method: 'POST',
    body: { image_base64: b64 },
    timeoutMs: 15000
  });
}

function updateOcrMergeButtons() {
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

function renderOcrChips(lines) {
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
      title: 'Remplacer l\'auteur par cette ligne',
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
      title: 'Ajouter cette ligne à l\'auteur existant',
      onclick: (e) => {
        e.stopPropagation();
        const cur = $('#nbAuthor').value.trim();
        $('#nbAuthor').value = toTitleCase(cur ? cur + ' ' + txt : txt);
        toast('Ligne ajoutée à l\'auteur', 'ok');
        triggerAllBddChecks();
      }
    });

    const btnPub = el('button', {
      type: 'button',
      text: 'Éditeur',
      class: 'ocr-pill-btn ocr-pill-pub',
      title: 'Remplacer l\'éditeur par cette ligne',
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

/* ---------- Modale de Création Rapide de Livre Inconnu & Gestion BDD ---------- */
let pendingNewCode = null;
let currentMatchedBook = null;

function levenshteinDist(s1, s2) {
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

function stringSimilarity(s1, s2) {
  if (!s1 || !s2) return 0;
  s1 = s1.toLowerCase().trim();
  s2 = s2.toLowerCase().trim();
  if (s1 === s2) return 1.0;
  const maxLen = Math.max(s1.length, s2.length);
  if (maxLen === 0) return 1.0;
  return (maxLen - levenshteinDist(s1, s2)) / maxLen;
}

function checkFieldBdd(inputId, badgeId, suggestionId, canonicalList) {
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

  // Détection de coquille / faute d'orthographe (proximité >= 0.72)
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

function triggerAllBddChecks() {
  checkFieldBdd('#nbAuthor', '#nbAuthorBddBadge', '#nbAuthorTypoSuggestion', dbAuthors);
  checkFieldBdd('#nbPublisher', '#nbPublisherBddBadge', '#nbPublisherTypoSuggestion', dbPublishers);
  const codeVal = $('#nbCode') ? $('#nbCode').value.trim() : '';
  if (codeVal) checkCodeInCatalog(codeVal);
  else if (!currentMatchedBook) hideExistingBookBanner();
}

async function checkCodeInCatalog(code) {
  if (!code) {
    hideExistingBookBanner();
    return;
  }
  try {
    const book = await api('/api/books/scan/' + encodeURIComponent(code));
    if (book && book.id) {
      showExistingBookBanner(book);
    } else {
      if (!currentMatchedBook) hideExistingBookBanner();
    }
  } catch (e) {
    if (!currentMatchedBook) hideExistingBookBanner();
  }
}

function showExistingBookBanner(b) {
  currentMatchedBook = b;
  const banner = $('#nbBookExistsBanner');
  const title = $('#nbExistsTitle');
  const badge = $('#nbExistsStockBadge');
  const codeBadge = $('#nbCodeBddBadge');
  if (!banner) return;
  title.textContent = `${b.title || 'Fiche sans titre'}${b.author ? ' · ' + b.author : ''} (${eur(b.price)})`;
  if (badge) badge.textContent = `Stock actuel : ${b.stock ?? 0} ex.`;
  if (codeBadge) {
    codeBadge.textContent = `✓ En base (${b.stock ?? 0} ex.)`;
    codeBadge.style.display = 'inline-flex';
  }
  banner.style.display = 'block';

  // Proposition 1 : Ajouter directement au stock / carton sans doublon
  const addStockBtn = $('#nbBtnAddToStock');
  if (addStockBtn) {
    addStockBtn.onclick = () => {
      if (currentMode === 'recv') {
        addToRecv(b);
        toast(`📦 ${b.title} ajouté au carton de réception !`, 'ok');
      } else {
        addToCart(b);
        toast(`🛒 ${b.title} ajouté au panier !`, 'ok');
      }
      closeNewBookModal();
    };
  }

  // Proposition 2 : Remplir la fiche
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

  const enrichBtn = $('#nbBtnEnrichMatch');
  if (enrichBtn) {
    enrichBtn.onclick = async () => {
      const code = $('#nbCode').value.trim();
      const price = parseFloat($('#nbPrice').value);
      const payload = {
        code: code || undefined,
        title: $('#nbTitle').value.trim() || undefined,
        author: $('#nbAuthor').value.trim() || undefined,
        publisher: $('#nbPublisher') ? $('#nbPublisher').value.trim() || undefined : undefined,
        price: Number.isFinite(price) && price > 0 ? price : undefined
      };
      try {
        const result = await api(`/api/books/${b.id}/enrich`, { method: 'POST', body: payload });
        toast(result.updated.length ? `Fiche complétée : ${result.updated.join(', ')}` : 'Aucune information manquante à compléter', 'ok');
        closeNewBookModal();
        const lookupCode = code || result.book.code;
        const book = await api('/api/books/scan/' + encodeURIComponent(lookupCode));
        if (currentMode === 'recv') addToRecv(book); else addToCart(book);
      } catch (err) {
        toast(err.message, 'err');
      }
    };
  }
}

function hideExistingBookBanner() {
  currentMatchedBook = null;
  const banner = $('#nbBookExistsBanner');
  if (banner) banner.style.display = 'none';
  const codeBadge = $('#nbCodeBddBadge');
  if (codeBadge) codeBadge.style.display = 'none';
}

function toSentenceCase(str) {
  if (!str) return '';
  str = str.trim();
  if (!str) return '';
  const stopwords = new Set([
    'de', 'du', 'des', 'le', 'la', 'les', 'un', 'une', 'et', 'en', 'au', 'aux',
    'par', 'pour', 'sur', 'dans', 'a', 'd', 'l', 'ou', 'avec', 'sans', 'sous', 'vers', 'chez'
  ]);
  const words = str.split(/\s+/);
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
  res = res.replace(/([:\.?!]\s+)([a-zàéèêîôû])/g, (m, p1, p2) => p1 + p2.toUpperCase());
  return res.charAt(0).toUpperCase() + res.slice(1);
}

function toTitleCase(str) {
  if (!str) return '';
  str = str.trim();
  if (!str) return '';
  const stopwords = new Set([
    'de', 'du', 'des', 'le', 'la', 'les', 'un', 'une', 'et', 'en', 'au', 'aux',
    'par', 'pour', 'sur', 'dans', 'a', 'd', 'l', 'ou', 'avec', 'sans', 'sous', 'vers', 'chez'
  ]);
  const words = str.split(/\s+/);
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
  res = res.replace(/([:\.?!]\s+)([a-zàéèêîôû])/g, (m, p1, p2) => p1 + p2.toUpperCase());
  return res.charAt(0).toUpperCase() + res.slice(1);
}

function openNewBookModal(code = '', prefill = {}) {
  pendingNewCode = code || '';
  const existing = prefill.existing_book || prefill.matched_book || null;
  $('#nbCode').value = pendingNewCode || (existing && existing.code) || '';
  $('#nbTitle').value = existing ? (existing.title || toSentenceCase(prefill.title || '')) : toSentenceCase(prefill.title || '');
  $('#nbAuthor').value = existing ? (existing.author || toTitleCase(prefill.author || '')) : toTitleCase(prefill.author || '');
  if ($('#nbPublisher')) $('#nbPublisher').value = existing ? (existing.publisher || prefill.publisher || '') : (prefill.publisher || '');
  $('#nbPrice').value = (prefill.price != null && prefill.price > 0) ? prefill.price : (existing && existing.price > 0 ? existing.price : '');
  
  const badge = $('#nbOcrBadge');
  if (badge) badge.style.display = prefill.lines ? 'inline-flex' : 'none';

  // Si le livre existe déjà en base, proposer immédiatement l'ajout au stock
  if (existing) {
    showExistingBookBanner(existing);
  } else if (pendingNewCode) {
    checkCodeInCatalog(pendingNewCode);
  } else {
    hideExistingBookBanner();
  }
  
  if (prefill.lines && prefill.lines.length) {
    renderOcrChips(prefill.lines);
  } else {
    const sect = $('#nbOcrChipsSection');
    if (sect) sect.style.display = 'none';
  }

  // Notifier si une faute d'orthographe a été corrigée
  if (prefill.corrections) {
    if (prefill.corrections.author) {
      toast(`✨ Auteur corrigé d'après la base : ${prefill.corrections.author.corrected}`, 'ok');
    }
    if (prefill.corrections.publisher) {
      toast(`✨ Éditeur corrigé d'après la base : ${prefill.corrections.publisher.corrected}`, 'ok');
    }
  }

  triggerAllBddChecks();
  
  // Réinitialiser tout décalage intempestif de défilement (retour caméra etc.) et actualiser la hauteur
  window.scrollTo(0, 0);
  updateViewportHeight();
  
  const m = $('#newBookModal');
  if (m) {
    m.hidden = false;
    m.style.removeProperty('display');
  }
  
  // Ne JAMAIS ouvrir le clavier virtuel automatiquement à l'ouverture de la modale
  // Cela garantit que la zone caméra et les boutons Enregistrer restent 100% visibles sans écrasement
  if (document.activeElement && document.activeElement.blur) {
    document.activeElement.blur();
  }
}

function closeNewBookModal() {
  const m = $('#newBookModal');
  if (m) {
    m.hidden = true;
    m.style.setProperty('display', 'none', 'important');
  }
  pendingNewCode = null;
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

// Fermeture par le bouton ✕ en haut de la fiche livre
const nbBtnCloseTop = $('#nbBtnCloseTop');
if (nbBtnCloseTop) {
  nbBtnCloseTop.addEventListener('click', closeNewBookModal);
}

// Fermeture en cliquant sur l'overlay sombre autour de la feuille
const nbModalEl = $('#newBookModal');
if (nbModalEl) {
  nbModalEl.addEventListener('click', e => {
    if (e.target === nbModalEl) closeNewBookModal();
  });
}

// Échappement clavier pour fermer la modale
window.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    closeNewBookModal();
    if (typeof closeMobileBookStats === 'function') closeMobileBookStats();
    if (typeof closeMultiPayModal === 'function') closeMultiPayModal();
  }
});

let titleCaseMode = 0;
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

$('#btnCancelNewBook').addEventListener('click', closeNewBookModal);

// Écouteurs en temps réel sur les champs pour la vérification BDD et la correction de coquilles
['input', 'blur'].forEach(evt => {
  const codeInp = $('#nbCode');
  if (codeInp) codeInp.addEventListener(evt, () => checkCodeInCatalog(codeInp.value.trim()));

  const authInp = $('#nbAuthor');
  if (authInp) authInp.addEventListener(evt, () => checkFieldBdd('#nbAuthor', '#nbAuthorBddBadge', '#nbAuthorTypoSuggestion', dbAuthors));

  const pubInp = $('#nbPublisher');
  if (pubInp) pubInp.addEventListener(evt, () => checkFieldBdd('#nbPublisher', '#nbPublisherBddBadge', '#nbPublisherTypoSuggestion', dbPublishers));
});

$('#btnSaveNewBook').addEventListener('click', async () => {
  const code = $('#nbCode').value.trim();
  const title = $('#nbTitle').value.trim();
  const author = $('#nbAuthor').value.trim();
  const publisher = $('#nbPublisher') ? $('#nbPublisher').value.trim() : null;
  const price = parseFloat($('#nbPrice').value) || 0;
  if (!title) return toast('Le titre est requis', 'warn');
  if (price <= 0) return toast('Indiquez un prix valide', 'warn');

  try {
    const res = await api('/api/books', {
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
    // Charger immédiatement le nouveau livre
    const book = await api('/api/books/scan/' + encodeURIComponent(code));
    if (currentMode === 'sale') {
      addToCart(book);
    } else {
      addToRecv(book);
    }
  } catch (err) {
    toast(err.message, 'err');
  }
});

// ==========================================
// SYSTÈME CAMÉRA LIVE OCR (GARANTIT LE CAPTEUR ARRIÈRE GEEKY / SAMSUNG S24)
// ==========================================
let ocrStream = null;
let currentOcrTarget = null; // 'modal' | 'recv'
let ocrAvailableRearDevices = [];
let ocrCurrentDeviceIdx = 0;

async function enumerateRearCamerasForOcr() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return [];
  try {
    const devs = await navigator.mediaDevices.enumerateDevices();
    const videoDevs = devs.filter(d => d.kind === 'videoinput');
    // Exclure formellement selfie/front/avant
    const rear = videoDevs.filter(d => {
      const l = (d.label || '').toLowerCase();
      const isFront = l.includes('front') || l.includes('avant') || l.includes('selfie') || l.includes('user') || l.includes('face');
      return !isFront;
    });
    return rear.length ? rear : videoDevs;
  } catch (e) {
    return [];
  }
}

async function stopOcrCameraStream() {
  const barcodeVid = $('#video');
  const isSharedWithBarcode = barcodeVid && barcodeVid.srcObject === ocrStream;
  if (ocrStream && !isSharedWithBarcode) {
    ocrStream.getTracks().forEach(t => t.stop());
  }
  ocrStream = null;
  const ocrVid = $('#ocrVideo');
  if (ocrVid) ocrVid.srcObject = null;
}

function closeOcrCameraModal() {
  stopOcrCameraStream();
  const modal = $('#ocrCamModal');
  if (modal) {
    modal.hidden = true;
    modal.style.display = 'none';
  }
  currentOcrTarget = null;
}

async function startOcrStream(deviceId = null) {
  const ocrVid = $('#ocrVideo');
  const spinner = $('#ocrCamSpinner');
  if (spinner) spinner.style.display = 'flex';
  await stopOcrCameraStream();

  let stream = null;
  const constraintsList = [];

  if (deviceId) {
    constraintsList.push({
      video: {
        deviceId: { exact: deviceId },
        width: { ideal: 1920, max: 2560 },
        height: { ideal: 1080, max: 1440 }
      },
      audio: false
    });
  }

  // Hierarchie de contraintes pour forcer l'arrière sans jamais tomber sur selfie
  constraintsList.push(
    {
      video: {
        facingMode: { exact: 'environment' },
        width: { ideal: 1920 },
        height: { ideal: 1080 }
      },
      audio: false
    },
    {
      video: {
        facingMode: { ideal: 'environment' },
        width: { ideal: 1920 },
        height: { ideal: 1080 }
      },
      audio: false
    },
    {
      video: {
        facingMode: 'environment'
      },
      audio: false
    }
  );

  for (const c of constraintsList) {
    try {
      stream = await navigator.mediaDevices.getUserMedia(c);
      const track = stream.getVideoTracks()[0];
      if (track) {
        const settings = track.getSettings ? track.getSettings() : {};
        if (settings.facingMode === 'user') {
          // Rejeter si le navigateur a renvoyé la caméra frontale malgré tout
          track.stop();
          stream = null;
          continue;
        }
      }
      if (stream) break;
    } catch (err) {}
  }

  if (!stream) {
    // Si getUserMedia n'a pas pu obtenir l'arrière
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    } catch (err) {
      if (spinner) spinner.style.display = 'none';
      throw new Error("Impossible d'accéder à la caméra arrière.");
    }
  }

  ocrStream = stream;
  if (ocrVid) {
    ocrVid.srcObject = stream;
    await ocrVid.play();
  }

  // Tenter focus continuous
  const vTrack = stream ? stream.getVideoTracks()[0] : null;
  if (vTrack && vTrack.applyConstraints) {
    try { await vTrack.applyConstraints({ advanced: [{ focusMode: 'continuous' }] }); } catch (e) {}
  }

  if (spinner) spinner.style.display = 'none';
}

let liveOcrTimer = null;
let isLiveOcrAnalyzing = false;
let lastLiveOcrResult = null;

function stopLiveOcrLoop() {
  if (liveOcrTimer) {
    clearTimeout(liveOcrTimer);
    liveOcrTimer = null;
  }
  isLiveOcrAnalyzing = false;
}

// Boucle continue de détection AR en temps réel AVANT d'appuyer sur le bouton
function startLiveOcrLoop() {
  stopLiveOcrLoop();

  const liveTick = async () => {
    const ocrVid = $('#ocrVideo');
    const modal = $('#ocrCamModal');
    if (!modal || modal.hidden || !ocrVid || !ocrStream || !ocrVid.videoWidth) {
      liveOcrTimer = setTimeout(liveTick, 900);
      return;
    }

    if (!isLiveOcrAnalyzing) {
      isLiveOcrAnalyzing = true;
      try {
        const vw = ocrVid.videoWidth || 1280;
        const vh = ocrVid.videoHeight || 720;
        const offCanvas = document.createElement('canvas');
        const scale = Math.min(1, 960 / Math.max(vw, vh));
        offCanvas.width = Math.round(vw * scale);
        offCanvas.height = Math.round(vh * scale);
        const offCtx = offCanvas.getContext('2d');
        offCtx.drawImage(ocrVid, 0, 0, offCanvas.width, offCanvas.height);

        const b64 = offCanvas.toDataURL('image/jpeg', 0.72).split(',')[1];
        const res = await api('/api/ocr/scan', {
          method: 'POST',
          body: { image_base64: b64 },
          timeoutMs: 4000
        });

        if (res && res.lines && res.lines.length && !modal.hidden) {
          lastLiveOcrResult = res;
          const c = res.candidates || {};
          res.lines.forEach(l => {
            const t = (l.text || '').toLowerCase();
            if (c.author && t.includes(c.author.toLowerCase())) l.tag = 'author';
            else if (c.publisher && t.includes(c.publisher.toLowerCase())) l.tag = 'publisher';
            else if (c.title && t.includes(c.title.toLowerCase())) l.tag = 'title';
          });

          // Projeter les cadres AR en continu sur la couverture
          renderOcrArBoxes(res.lines, offCanvas.width, offCanvas.height);

          const guideText = $('#ocrArGuideText');
          if (guideText) {
            const detectedTitle = c.title ? `« ${c.title.slice(0, 22)}… »` : `${res.lines.length} textes détectés`;
            guideText.innerHTML = `<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#22c55e"></span> Vision AR active · ${detectedTitle}`;
          }
        }
      } catch (err) {
      } finally {
        isLiveOcrAnalyzing = false;
      }
    }

    liveOcrTimer = setTimeout(liveTick, 750);
  };

  liveOcrTimer = setTimeout(liveTick, 350);
}

async function openOcrCameraModal(targetType = 'modal') {
  currentOcrTarget = targetType;
  lastLiveOcrResult = null;
  const modal = $('#ocrCamModal');
  if (!modal) return;

  const titleEl = $('#ocrCamModalTitle');
  if (titleEl) {
    titleEl.textContent = targetType === 'recv' ? 'Scan Carton (Page de Garde)' : 'Photo Page de Garde';
  }

  modal.hidden = false;
  modal.style.display = 'flex';

  try {
    const ocrVid = $('#ocrVideo');
    const spinner = $('#ocrCamSpinner');
    if (spinner) spinner.style.display = 'flex';

    // SOLUTION ROBUSTE S24 & SMARTPHONES :
    // Si le scanner code-barres principal est déjà actif avec la caméra arrière (#video.srcObject),
    // on clone ou réutilise immédiatement ce même flux arrière déjà validé sans conflit de matériel !
    const barcodeVid = $('#video');
    if (barcodeVid && barcodeVid.srcObject && barcodeVid.srcObject.active) {
      const liveTracks = barcodeVid.srcObject.getVideoTracks();
      if (liveTracks.length && liveTracks[0].readyState === 'live') {
        const liveTrack = liveTracks[0];
        const settings = liveTrack.getSettings ? liveTrack.getSettings() : {};
        if (settings.facingMode !== 'user') {
          // On partage le flux arrière parfait déjà actif !
          ocrStream = barcodeVid.srcObject;
          if (ocrVid) {
            ocrVid.srcObject = ocrStream;
            await ocrVid.play();
          }
          if (spinner) spinner.style.display = 'none';
          startLiveOcrLoop();
          return;
        }
      }
    }

    if (!bestCameraDeviceId) {
      bestCameraDeviceId = await findOptimalCamera();
    }

    ocrAvailableRearDevices = await enumerateRearCamerasForOcr();
    ocrCurrentDeviceIdx = 0;
    const targetDevId = bestCameraDeviceId || (ocrAvailableRearDevices.length ? ocrAvailableRearDevices[0].deviceId : null);
    await startOcrStream(targetDevId);
    startLiveOcrLoop();
  } catch (err) {
    toast(err.message || 'Erreur ouverture caméra arrière', 'err');
    closeOcrCameraModal();
    if (targetType === 'modal') {
      $('#nbOcrInput')?.click();
    } else {
      $('#recvOcrInput')?.click();
    }
  }
}

// Bouton changer de capteur arrière dans le viseur live
$('#btnSwitchOcrCam')?.addEventListener('click', async () => {
  if (!ocrAvailableRearDevices.length) {
    ocrAvailableRearDevices = await enumerateRearCamerasForOcr();
  }
  if (ocrAvailableRearDevices.length <= 1) {
    toast('Un seul capteur arrière disponible', 'info');
    return;
  }
  ocrCurrentDeviceIdx = (ocrCurrentDeviceIdx + 1) % ocrAvailableRearDevices.length;
  const nextDev = ocrAvailableRearDevices[ocrCurrentDeviceIdx];
  toast(`Capteur : ${nextDev.label || 'Caméra ' + (ocrCurrentDeviceIdx + 1)}`, 'info');
  try {
    await startOcrStream(nextDev.deviceId);
  } catch (e) {
    toast('Échec bascule capteur', 'warn');
  }
});

// Nettoyer l'overlay AR
function clearOcrArCanvas() {
  const arCanvas = $('#ocrArCanvas');
  if (arCanvas) {
    const ctx = arCanvas.getContext('2d');
    if (ctx) ctx.clearRect(0, 0, arCanvas.width, arCanvas.height);
  }
}

// Dessiner les cadres AR holographiques 3D au-dessus des textes reconnus
function renderOcrArBoxes(lines, imgWidth, imgHeight) {
  const arCanvas = $('#ocrArCanvas');
  const ocrVid = $('#ocrVideo');
  if (!arCanvas || !ocrVid) return;

  const rect = arCanvas.getBoundingClientRect();
  arCanvas.width = rect.width * (window.devicePixelRatio || 1);
  arCanvas.height = rect.height * (window.devicePixelRatio || 1);

  const ctx = arCanvas.getContext('2d');
  ctx.clearRect(0, 0, arCanvas.width, arCanvas.height);
  if (!lines || !lines.length) return;

  const scaleX = arCanvas.width / (imgWidth || 1600);
  const scaleY = arCanvas.height / (imgHeight || 1200);

  lines.forEach((l, idx) => {
    const box = l.box; // 4 points [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
    if (!box || box.length < 4) return;

    const tag = l.tag; // 'author' | 'title' | 'publisher' | etc.
    let strokeColor = 'rgba(168, 85, 247, 0.85)';
    let fillColor = 'rgba(168, 85, 247, 0.22)';
    let badgeText = l.text || '';

    if (tag === 'author') {
      strokeColor = 'rgba(34, 197, 94, 0.95)';
      fillColor = 'rgba(34, 197, 94, 0.28)';
      badgeText = '👤 ' + badgeText;
    } else if (tag === 'publisher') {
      strokeColor = 'rgba(59, 130, 246, 0.95)';
      fillColor = 'rgba(59, 130, 246, 0.28)';
      badgeText = '🏢 ' + badgeText;
    }

    ctx.save();
    ctx.beginPath();
    ctx.moveTo(box[0][0] * scaleX, box[0][1] * scaleY);
    ctx.lineTo(box[1][0] * scaleX, box[1][1] * scaleY);
    ctx.lineTo(box[2][0] * scaleX, box[2][1] * scaleY);
    ctx.lineTo(box[3][0] * scaleX, box[3][1] * scaleY);
    ctx.closePath();

    ctx.lineWidth = 2.5 * (window.devicePixelRatio || 1);
    ctx.strokeStyle = strokeColor;
    ctx.fillStyle = fillColor;
    ctx.shadowColor = strokeColor;
    ctx.shadowBlur = 8 * (window.devicePixelRatio || 1);
    ctx.fill();
    ctx.stroke();

    // Pastille de texte flottante en réalité augmentée
    const px = box[0][0] * scaleX;
    const py = Math.max(16, box[0][1] * scaleY - 6);
    ctx.font = `bold ${Math.round(11 * (window.devicePixelRatio || 1))}px Inter, sans-serif`;
    const textW = ctx.measureText(badgeText).width;

    ctx.fillStyle = 'rgba(15, 23, 42, 0.88)';
    ctx.shadowBlur = 0;
    ctx.beginPath();
    ctx.roundRect(px, py - 14 * (window.devicePixelRatio || 1), textW + 12, 16 * (window.devicePixelRatio || 1), 4);
    ctx.fill();

    ctx.fillStyle = '#ffffff';
    ctx.fillText(badgeText, px + 6, py - 2);
    ctx.restore();
  });
}

// Bouton Annuler le viseur live
$('#btnCloseOcrCam')?.addEventListener('click', () => {
  clearOcrArCanvas();
  closeOcrCameraModal();
});

// Bouton Déclencheur / Prise de vue HD live avec vision AR instantanée
$('#btnSnapOcrLive')?.addEventListener('click', async () => {
  const ocrVid = $('#ocrVideo');
  if (!ocrVid || !ocrStream) return;

  const btnSnap = $('#btnSnapOcrLive');
  const target = currentOcrTarget;

  // Si la Vision AR a déjà détecté le texte en direct pendant la visée, validation instantanée !
  if (lastLiveOcrResult && lastLiveOcrResult.candidates && (lastLiveOcrResult.candidates.title || lastLiveOcrResult.candidates.author)) {
    closeOcrCameraModal();
    clearOcrArCanvas();
    if (target === 'modal') {
      await applyOcrResultToModal(lastLiveOcrResult);
    } else {
      await applyOcrResultToRecv(lastLiveOcrResult);
    }
    return;
  }

  const guideText = $('#ocrArGuideText');
  const oldBtnHtml = btnSnap.innerHTML;
  btnSnap.disabled = true;
  btnSnap.innerHTML = '✨ Analyse Vision AR...';
  if (guideText) {
    guideText.innerHTML = '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#38c172;animation:pulse 0.6s infinite"></span> Détection holographique du texte...';
  }

  const vw = ocrVid.videoWidth || 1920;
  const vh = ocrVid.videoHeight || 1080;
  const canvas = document.createElement('canvas');
  canvas.width = vw;
  canvas.height = vh;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(ocrVid, 0, 0, vw, vh);

  canvas.toBlob(async (blob) => {
    if (!blob) {
      toast('Échec de la capture', 'err');
      btnSnap.disabled = false;
      btnSnap.innerHTML = oldBtnHtml;
      return;
    }
    const capturedFile = new File([blob], 'page_garde.jpg', { type: 'image/jpeg' });

    try {
      // 1. Appel instantané de l'OCR pour projeter la Vision AR
      const res = await performOcr(capturedFile);
      if (res && res.lines && res.lines.length) {
        // Taguer les lignes pour les couleurs AR
        const c = res.candidates || {};
        res.lines.forEach(l => {
          const t = (l.text || '').toLowerCase();
          if (c.author && t.includes(c.author.toLowerCase())) l.tag = 'author';
          else if (c.publisher && t.includes(c.publisher.toLowerCase())) l.tag = 'publisher';
          else if (c.title && t.includes(c.title.toLowerCase())) l.tag = 'title';
        });

        // Projection holographique sur le canvas au-dessus du flux vidéo
        renderOcrArBoxes(res.lines, vw, vh);
        if (guideText) {
          guideText.innerHTML = `✨ <b>${res.lines.length}</b> textes détectés en Réalité Augmentée !`;
        }
        await new Promise(r => setTimeout(r, 650)); // Petit instant de wow-effect pour apprécier l'AR
      }

      closeOcrCameraModal();
      clearOcrArCanvas();

      if (target === 'modal') {
        await applyOcrResultToModal(res);
      } else {
        await applyOcrResultToRecv(res);
      }
    } catch (err) {
      toast(err.message || 'Erreur vision OCR', 'err');
      closeOcrCameraModal();
      clearOcrArCanvas();
    } finally {
      btnSnap.disabled = false;
      btnSnap.innerHTML = oldBtnHtml;
    }
  }, 'image/jpeg', 0.92);
});

// Fonctions d'application directe des résultats déjà calculés
async function applyOcrResultToModal(res) {
  window.scrollTo(0, 0);
  updateViewportHeight();
  if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
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
      showExistingBookBanner(res.matched_book);
    }
    if (res.corrections) {
      if (res.corrections.author) {
        toast(`✨ Auteur corrigé d'après la base : ${res.corrections.author.corrected}`, 'ok');
      }
      if (res.corrections.publisher) {
        toast(`✨ Éditeur corrigé d'après la base : ${res.corrections.publisher.corrected}`, 'ok');
      }
    }
    triggerAllBddChecks();
    toast('Vision AR : Page de garde lue avec succès !', 'ok');
  }
}

async function applyOcrResultToRecv(res) {
  window.scrollTo(0, 0);
  updateViewportHeight();
  if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  if (res) {
    if (res.matched_book && res.matched_book.code) {
      try {
        const book = await api('/api/books/scan/' + encodeURIComponent(res.matched_book.code));
        addToRecv(book);
        toast(`📦 Livre en base ajouté au carton : ${book.title}`, 'ok');
        return;
      } catch (e) {}
    }
    const c = res.candidates || {};
    toast('Vision AR : Page de garde enregistrée', 'ok');
    openNewBookModal('', { ...c, lines: res.lines, matched_book: res.matched_book, corrections: res.corrections });
  } else {
    toast('Aucun texte lisible détecté', 'warn');
  }
}

// Fallback import fichier depuis le viseur live
$('#ocrFileFallback')?.addEventListener('change', async (e) => {
  const file = e.target.files && e.target.files[0];
  e.target.value = '';
  if (!file) return;
  const target = currentOcrTarget;
  closeOcrCameraModal();
  clearOcrArCanvas();
  if (target === 'modal') {
    await handleModalOcrFile(file);
  } else {
    await handleRecvOcrFile(file);
  }
});

async function handleModalOcrFile(file) {
  window.scrollTo(0, 0);
  updateViewportHeight();
  if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
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
        showExistingBookBanner(res.matched_book);
      }
      if (res.corrections) {
        if (res.corrections.author) {
          toast(`✨ Auteur corrigé d'après la base : ${res.corrections.author.corrected}`, 'ok');
        }
        if (res.corrections.publisher) {
          toast(`✨ Éditeur corrigé d'après la base : ${res.corrections.publisher.corrected}`, 'ok');
        }
      }
      triggerAllBddChecks();
      toast('Page de garde analysée avec succès', 'ok');
    }
  } catch (err) {
    toast(err.message || "Erreur lors de l'OCR", 'err');
  } finally {
    if (txtSpan) txtSpan.textContent = oldText;
    const inp = $('#nbOcrInput');
    if (inp) inp.value = '';
    window.scrollTo(0, 0);
    updateViewportHeight();
  }
}

async function handleRecvOcrFile(file) {
  window.scrollTo(0, 0);
  updateViewportHeight();
  if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  const txtSpan = $('#recvOcrText');
  const oldText = txtSpan ? txtSpan.textContent : '';
  if (txtSpan) txtSpan.textContent = '⏳ Scan OCR...';
  try {
    toast('Numérisation de la page de garde...', 'ok');
    const res = await performOcr(file);
    window.scrollTo(0, 0);
    updateViewportHeight();
    if (res) {
      if (res.matched_book && res.matched_book.code) {
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
    const inp = $('#recvOcrInput');
    if (inp) inp.value = '';
    window.scrollTo(0, 0);
    updateViewportHeight();
  }
}

// Clics sur les boutons OCR : ouvrent le viseur caméra ARRIÈRE garanti
const nbOcrBtn = $('#nbOcrBtn');
if (nbOcrBtn) {
  nbOcrBtn.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    openOcrCameraModal('modal');
  });
}

const recvOcrBtn = $('#recvOcrBtn');
if (recvOcrBtn) {
  recvOcrBtn.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    openOcrCameraModal('recv');
  });
}

// Écouteurs de repli sur les inputs file (au cas où déclenchés par l'utilisateur)
const nbOcrInput = $('#nbOcrInput');
if (nbOcrInput) {
  nbOcrInput.addEventListener('change', async e => {
    const file = e.target.files && e.target.files[0];
    if (file) await handleModalOcrFile(file);
  });
}

const recvOcrInput = $('#recvOcrInput');
if (recvOcrInput) {
  recvOcrInput.addEventListener('change', async e => {
    const file = e.target.files && e.target.files[0];
    if (file) await handleRecvOcrFile(file);
  });
}


/* ---------- recherche / saisie manuelle ---------- */
let isLookingUp = false;
const codeCache = new Map(); // Cache local en mémoire vive pour réponse instantanée 0ms

async function lookupCode(code) {
  if (isLookingUp) return; // Ignore tout nouveau scan si une requête est déjà en attente
  isLookingUp = true;
  try {
    let book = codeCache.get(code);
    if (!book) {
      book = await api('/api/books/scan/' + encodeURIComponent(code), { timeoutMs: 3500 });
      if (book && book.id) {
        codeCache.set(code, book);
        if (codeCache.size > 150) {
          const firstKey = codeCache.keys().next().value;
          codeCache.delete(firstKey);
        }
      }
    }
    if (!book.title || !book.title.trim()) {
      toast('Fiche sans titre : complétez-la avec la photo de couverture', 'warn');
      openNewBookModal(code, { existing_book: book });
      if (currentMode === 'recv') {
        setTimeout(() => openOcrCameraModal('modal'), 200);
      }
      return;
    }
    if (currentMode === 'sale') {
      addToCart(book);
    } else {
      addToRecv(book);
    }
  } catch (e) {
    if (e.message && e.message.includes('Aucun livre pour le code')) {
      if (currentMode === 'recv') {
        toast(`Code ${code} inconnu : scannez la page de garde pour créer le livre`, 'info');
        openNewBookModal(code);
        // Enchaînement fluide en Réception : déclencher immédiatement la Vision AR pour compléter la fiche
        setTimeout(() => openOcrCameraModal('modal'), 200);
      } else {
        toast('Livre inconnu : ouverture de la fiche', 'warn');
        openNewBookModal(code);
      }
    } else {
      toast(e.message, 'warn');
    }
  } finally {
    isLookingUp = false;
  }
}

async function manualSearch() {
  const q = $('#manualCode').value.trim();
  const box = $('#results'); box.replaceChildren();
  if (!q) return;
  if (/^[0-9][0-9\- ]{7,}$/.test(q)) { await lookupCode(q); $('#manualCode').value = ''; return; }
  try {
    const found = await api('/api/books/search?q=' + encodeURIComponent(q));
    if (!found.length) return toast('Aucun résultat', 'warn');
    box.replaceChildren(...found.map(b => el('button', {
      class: 'result', type: 'button',
      onclick: () => { 
        if (currentMode === 'sale') addToCart(b); else addToRecv(b);
        box.replaceChildren(); 
        $('#manualCode').value = ''; 
      }
    }, el('div', { class: 'ci-title', text: b.title + (b.volume ? ' · Vol. ' + b.volume : '') }),
       el('div', { class: 'muted', text: `${b.code} · ${eur(b.price)} · stock ${b.stock}` }))));
  } catch (e) { toast(e.message, 'err'); }
}
$('#btnSearch').addEventListener('click', manualSearch);
$('#manualCode').addEventListener('keydown', e => { if (e.key === 'Enter') manualSearch(); });

/* ---------- moteur de scan tolérant aux conditions dégradées (flou, reflets, faible éclairage) ---------- */
let stream = null, scanTimer = null, isScanning = false, lastCode = '', lastTime = 0;
let lockedBarcode = null;           // Code-barres actuellement verrouillé sous l'objectif (Règle 1 : Scan-and-Exit)
let emptyFramesCount = 0;           // Compteur de frames consécutives sans code (sortie de champ confirmée)
const EMPTY_FRAMES_REQUIRED = 3;    // Minimum 3 frames consécutives (~330ms) sans code pour valider la sortie physique du livre
const SAME_CODE_COOLDOWN_MS = 1200; // Règle 2 : Cooldown incompressible de 1.2s entre 2 scans consécutifs du MÊME livre
let videoTrack = null, currentZoom = 1, torchActive = false;

// Canvases hors-écran réutilisables pour le recadrage ROI et les filtres
const canvasRoi = document.createElement('canvas');
const ctxRoi = canvasRoi.getContext('2d', { willReadFrequently: true });
const canvasFilter = document.createElement('canvas');
const ctxFilter = canvasFilter.getContext('2d', { willReadFrequently: true });

// Initialisation du lecteur ZXing avec mode TRY_HARDER (reconstruction heuristique des codes dégradés)
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

// Détecteur natif Chromium
let nativeDetector = null;
if ('BarcodeDetector' in window) {
  try {
    nativeDetector = new BarcodeDetector({ formats: ['ean_13', 'ean_8', 'upc_a', 'code_128'] });
  } catch (e) {
    console.warn('BarcodeDetector non supporté ou erreur d initialisation:', e);
    nativeDetector = null;
  }
}

// Validation stricte des sommes de contrôle (permet d'être ultra-tolérant sans faux positifs)
function isValidBarcode(raw) {
  if (!raw) return false;
  const s = String(raw).trim();
  if (/^\d{8}$|^\d{13}$/.test(s)) {
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
  return /^[A-Za-z0-9\-\.\s]{3,30}$/.test(s);
}

// Décodeur ZXing double-binariseur (HybridBinarizer + GlobalHistogramBinarizer)
function decodeZxingBuffer(rgbaData, width, height) {
  if (!zxReader || !window.ZXing) return null;
  try {
    const lum = new ZXing.RGBLuminanceSource(rgbaData, width, height);
    const bitmap = new ZXing.BinaryBitmap(new ZXing.HybridBinarizer(lum));
    const txt = zxReader.decode(bitmap).getText();
    if (isValidBarcode(txt)) return txt;
  } catch (e) { /* ignore */ }

  try {
    const lum = new ZXing.RGBLuminanceSource(rgbaData, width, height);
    const bitmap = new ZXing.BinaryBitmap(new ZXing.GlobalHistogramBinarizer(lum));
    const txt = zxReader.decode(bitmap).getText();
    if (isValidBarcode(txt)) return txt;
  } catch (e) { /* ignore */ }

  return null;
}

// Algorithmes de traitement d'image pour conditions difficiles :
// 1) Égalisation min-max + netteté horizontale 1D (corrige le flou de près et le faible éclairage)
// 2) Binarisation adaptative locale de Bradley-Roth (élimine les reflets lumineux et les ombres)
function processDegradedFilters(data, width, height) {
  let min = 255, max = 0;
  const gray = new Uint8Array(width * height);
  for (let i = 0, j = 0; i < data.length; i += 4, j++) {
    const g = (data[i] * 299 + data[i + 1] * 587 + data[i + 2] * 114 + 500) >> 10;
    gray[j] = g;
    if (g < min) min = g;
    if (g > max) max = g;
  }
  const range = Math.max(1, max - min);

  // Filtre 1 : Netteté 1D + étirement de contraste
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

  // Filtre 2 : Binarisation adaptative locale Bradley-Roth
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

function flashSuccess() {
  const box = $('#targetBox');
  if (box) {
    box.classList.add('success');
    setTimeout(() => box.classList.remove('success'), 400);
  }
  if (navigator.vibrate) {
    try { navigator.vibrate(50); } catch (e) { }
  }
}

function onCode(code) {
  resetInactivity();
  if (isLookingUp || pendingNewCode) return; // En pause si recherche en cours ou modale de création ouverte
  
  const now = Date.now();

  // RÈGLE 1 : VERROU DE RUPTURE VISUELLE STRICTE (SCAN-AND-EXIT)
  // Tant que le livre reste immobile devant l'objectif (pas de sortie de champ >= 3 frames consécutives), on bloque
  if (code === lockedBarcode) {
    return;
  }

  // RÈGLE 2 : COOLDOWN TEMPOREL INCOMPRESSIBLE (GARDE-FOU HUMAIN 1.2s)
  // Même si le livre a micro-quitté le champ, pour le même livre consécutif, on impose au moins 1 200 ms
  // (Si le livre est différent : 0 ms de délai, débit instantané !)
  if (code === lastCode && (now - lastTime < SAME_CODE_COOLDOWN_MS)) {
    return;
  }

  // Nouveau scan validé
  lockedBarcode = code;
  lastCode = code;
  lastTime = now;
  emptyFramesCount = 0;
  flashSuccess();
  lookupCode(code);
}

let rearCameras = [];
let currentCamIndex = 0;

let inactivityTimer = null;
let isAutoPaused = false;
const INACTIVITY_MS = 10 * 1000; // 10 secondes sans scan (mise en veille automatique anti-chauffe / économie batterie)

const BURST_INTERVAL_MS = 110; // 9 FPS pendant le rush (0ms de latence)
const ECO_INTERVAL_MS = 330;   // 3 FPS en repos / attente (-66% CPU/GPU)
const BURST_DURATION_MS = 5000; // Maintien du mode rapide pendant 5 secondes après le dernier scan
let lastScanSuccessTime = 0;
let isBurstMode = false;
let torchTimer = null;

function updateEcoBadge(burst) {
  const badge = $('#camEcoBadge');
  if (badge) {
    badge.textContent = burst ? 'RAPIDE' : 'ÉCO';
    badge.classList.toggle('burst', burst);
    badge.title = burst ? 'Mode Rush : 9 FPS haute cadence' : 'Mode Éco : 3 FPS économie d\'énergie';
  }
}

function resetInactivity() {
  clearTimeout(inactivityTimer);
  // Si le scanner est masqué ou en veille automatique réduite,
  // on ne réveille PAS au simple touch sur le panier (pour laisser le libraire manipuler le panier confortablement)
  if (camCont && camCont.classList.contains('minimized')) {
    return;
  }
  if (stream) {
    inactivityTimer = setTimeout(() => {
      pauseCamera('auto');
    }, INACTIVITY_MS);
  }
}

function pauseCamera(reason = 'minimized') {
  stopCamera();
  isAutoPaused = true;
  // Veille automatique ou masquage : collapse / masque automatiquement la caméra pour libérer tout l'écran
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

// Réinitialiser le minuteur d'inactivité tant que la caméra est ouverte
['touchstart', 'mousedown', 'keydown'].forEach(evt => {
  window.addEventListener(evt, resetInactivity, { passive: true });
});

function stopCamera() {
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

function camStatus(show, title, msg, btnText = null, onBtn = null) {
  $('#camStatus').hidden = !show;
  const ctrl = $('#camControls');
  if (ctrl) ctrl.style.display = show ? 'none' : 'flex';
  if (title) $('#camTitle').textContent = title;
  if (msg) $('#camMsg').textContent = msg;
  const btn = $('#btnCam');
  if (btn) {
    btn.textContent = btnText || 'Activer la caméra';
    btn.onclick = onBtn || (() => startCamera());
  }
}

// Élection automatique du meilleur capteur photo via les API matérielles WebRTC (focusDistance, macro, résolution)
let bestCameraDeviceId = null;
let isStartingCamera = false;
try { localStorage.removeItem('librairie_best_cam'); } catch (e) { }

async function findOptimalCamera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return null;
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const videoDevices = devices.filter(d => d.kind === 'videoinput');
    if (!videoDevices.length) return null;

    // Filtrer les caméras arrière (exclusion stricte des caméras avant / selfie)
    const rear = videoDevices.filter(d => {
      const l = (d.label || '').toLowerCase();
      const isFront = l.includes('front') || l.includes('avant') || l.includes('selfie') || l.includes('user') || l.includes('face');
      if (isFront) return false;
      return l.includes('back') || l.includes('rear') || l.includes('environment') || l.includes('arrière');
    });

    const candidates = rear.length ? rear : videoDevices.filter(d => {
      const l = (d.label || '').toLowerCase();
      return !l.includes('front') && !l.includes('avant') && !l.includes('selfie') && !l.includes('user') && !l.includes('face');
    });
    if (candidates.length === 1) return candidates[0].deviceId;
    if (candidates.length === 0) return null;

    // Tester les capacités réelles de chaque capteur (focusDistance, focusMode, zoom)
    let bestId = null;
    let highestScore = -Infinity;

    for (const dev of candidates) {
      const label = (dev.label || '').toLowerCase();
      let score = 0;

      // 1. Pénalité sévère sur les ultra-grands angles (0.6x / ultrawide qui ne savent pas faire la macro de près)
      if (label.includes('ultra') || label.includes('0.6') || label.includes('wide-angle') || label.includes('grand angle')) {
        score -= 100;
      }
      // 2. Bonus sur les mentions de capteur principal / standard / macro
      if (label.includes('main') || label.includes('standard') || label.includes('primary') || label.includes('back') || label.includes('rear') || label.includes('arrière')) {
        score += 50;
      }

      // 3. Inspection matérielle avancée via getCapabilities()
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
            continue; // Écarter définitivement tout capteur selfie
          }
          if (track.getCapabilities) {
            const caps = track.getCapabilities();

            // Capacité d'autofocus continu (essentiel pour codes-barres)
            if (caps.focusMode && caps.focusMode.includes('continuous')) score += 40;

            // Capacité de distance de focus (macro de près)
            if (caps.focusDistance) {
              // Plus la distance minimale de focus est petite (ex: 0.05m = 5cm), meilleur est le capteur macro
              score += 30;
              if (caps.focusDistance.min !== undefined && caps.focusDistance.min < 0.15) score += 20;
            }

            // Capacité de zoom matériel optique/numérique
            if (caps.zoom) score += 10;
          }
        }
        testStream.getTracks().forEach(t => t.stop());
      } catch (err) {
        // En cas d'erreur de sonde sur ce capteur, on garde le score textuel
      }

      if (score > highestScore) {
        highestScore = score;
        bestId = dev.deviceId;
      }
    }

    return bestId || (candidates[0] ? candidates[0].deviceId : null);
  } catch (e) {
    return null;
  }
}

async function startCamera(specificDeviceId = null) {
  if (isStartingCamera) return;
  isStartingCamera = true;

  // Déplier automatiquement le scanner s'il était réduit/en veille
  if (camCont && camCont.classList.contains('minimized')) {
    camCont.classList.remove('minimized');
    if (btnToggleCamSize) btnToggleCamSize.textContent = '▲ Masquer';
  }
  isAutoPaused = false;

  stopCamera();
  if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    isStartingCamera = false;
    return camStatus(true, 'Caméra indisponible', 'Cette page nécessite une connexion HTTPS pour accéder à l\'appareil photo.');
  }

  const video = $('#video');
  if (video) video.style.opacity = '0';

  try {
    let targetDeviceId = specificDeviceId;

    // Si aucun capteur spécifié, trouver automatiquement le capteur le plus net (meilleure macro/focus)
    if (!targetDeviceId && !bestCameraDeviceId) {
      bestCameraDeviceId = await findOptimalCamera();
    }
    if (!targetDeviceId && bestCameraDeviceId) {
      targetDeviceId = bestCameraDeviceId;
    }

    // Contraintes adaptatives : idéal 1280x720, max 1080p (parfait pour vieux téléphones sans surchauffe)
    const baseVideoConstraints = {
      width: { ideal: 1280, max: 1920 },
      height: { ideal: 720, max: 1080 },
      frameRate: { ideal: 30, max: 30 }
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
            video: {
              facingMode: { ideal: 'environment' },
              width: { ideal: 1280 },
              height: { ideal: 720 }
            },
            audio: false
          });
        } catch (e3) {
          try {
            stream = await navigator.mediaDevices.getUserMedia({
              video: { facingMode: 'environment' },
              audio: false
            });
          } catch (e4) {
            stream = await navigator.mediaDevices.getUserMedia({
              video: true,
              audio: false
            });
          }
        }
      }
    }

    video.srcObject = stream;
    await video.play();

    // Révélation visuelle UNIQUEMENT de la caméra sélectionnée finale
    video.style.opacity = '1';
    camStatus(false);

    videoTrack = stream ? stream.getVideoTracks()[0] : null;

    // Verrouillage de l'autofocus continu matériel si supporté
    if (videoTrack && videoTrack.applyConstraints) {
      try { await videoTrack.applyConstraints({ advanced: [{ focusMode: 'continuous' }] }); } catch (e) { }
    }

    // Contrôle discret de la lampe torche si le téléphone le supporte
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
              // Extinction automatique de la torche après 15 secondes pour éviter la surchauffe LED
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

    // Démarrer la surveillance d'inactivité (veille auto après 15s)
    resetInactivity();

    // Tap sur l'écran pour recentrer la mise au point
    video.onclick = async () => {
      resetInactivity();
      if (videoTrack && videoTrack.applyConstraints) {
        try {
          await videoTrack.applyConstraints({ advanced: [{ focusMode: 'continuous' }] });
          toast('Mise au point recentrée', 'ok');
        } catch (e) { }
      }
    };

    // Ordonnanceur adaptatif dynamique (Mode Burst 110ms / Mode Éco 330ms basse conso)
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
            // 1. Cadrage Principal (72% de largeur - idéal pour codes de taille moyenne/grande et distance normale)
            const cw1 = Math.round(vw * 0.72);
            const ch1 = Math.round(vh * 0.48);
            const cx1 = Math.round((vw - cw1) / 2);
            const cy1 = Math.round((vh - ch1) / 2);

            // 2. Cadrage Macro Haute Densité (38% de largeur au centre - zoom optique logiciel 2x pour petits codes-barres de poche)
            const cw2 = Math.round(vw * 0.38);
            const ch2 = Math.round(vh * 0.28);
            const cx2 = Math.round((vw - cw2) / 2);
            const cy2 = Math.round((vh - ch2) / 2);

            let code = null;

            // Fonction d'analyse d'une région donnée
            const scanCrop = async (cx, cy, cw, ch, allowHeavyFilters) => {
              if (canvasRoi.width !== cw || canvasRoi.height !== ch) {
                canvasRoi.width = cw; canvasRoi.height = ch;
                canvasFilter.width = cw; canvasFilter.height = ch;
              }
              ctxRoi.drawImage(video, cx, cy, cw, ch, 0, 0, cw, ch);

              // 1. Test ultra-rapide avec BarcodeDetector natif matériel (C++ GPU)
              if (nativeDetector) {
                try {
                  const results = await nativeDetector.detect(canvasRoi);
                  for (const r of results) {
                    if (isValidBarcode(r.rawValue)) return r.rawValue;
                  }
                } catch (e) { }
              }

              // 2. Test avec ZXing TRY_HARDER
              const rawImg = ctxRoi.getImageData(0, 0, cw, ch);
              let found = decodeZxingBuffer(rawImg.data, cw, ch);
              if (found) return found;

              // 3. Filtres adaptatifs lourds CPU (netteté 1D + Bradley-Roth) réservés au mode Burst/actif
              if (allowHeavyFilters) {
                const { sharpened, binarized } = processDegradedFilters(rawImg.data, cw, ch);
                found = decodeZxingBuffer(sharpened, cw, ch);
                if (found) return found;
                found = decodeZxingBuffer(binarized, cw, ch);
                return found;
              }
              return null;
            };

            // ÉCHELLES MULTIPLES (PYRAMIDE D'ÉCHELLES) :
            // Échelle A : Découpe Macro centrale (zoom 2x virtuel) -> lit les petits codes-barres sans avoir à coller le téléphone !
            code = await scanCrop(cx2, cy2, cw2, ch2, burst);

            // Échelle B : Cadrage large standard -> lit les codes normaux et grands
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
              // RÈGLE 1 : RUPTURE VISUELLE (SCAN-AND-EXIT)
              // Il faut au moins EMPTY_FRAMES_REQUIRED frames consécutives sans code (~330ms)
              // pour prouver que le livre a physiquement quitté la zone de scan et déverrouiller
              emptyFramesCount++;
              if (emptyFramesCount >= EMPTY_FRAMES_REQUIRED) {
                lockedBarcode = null;
              }
            }
          }
        } catch (err) {
          // Ignorer les erreurs d'une frame isolée
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
      denied ? 'Android : touchez le cadenas dans la barre d\'adresse → Autorisations → Appareil photo → Autoriser, puis réessayez.'
             : (e && e.message ? `Erreur caméra : ${e.message}. Touchez "Activer la caméra" pour réessayer.` : 'Aucune caméra utilisable. Utilisez le bouton photo ou la saisie manuelle.'));
  } finally {
    isStartingCamera = false;
  }
}
$('#btnCam').addEventListener('click', startCamera);
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    pauseCamera('auto');
  } else if (localStorage.getItem(TOKEN_KEY) && !isAutoPaused) {
    startCamera();
  }
});

/* Repli photo (fonctionne même sans flux vidéo avec pipeline tolérant) */
$('#fileSnap').addEventListener('change', async e => {
  const file = e.target.files[0]; e.target.value = '';
  if (!file) return;
  const url = URL.createObjectURL(file);
  try {
    const img = new Image(); img.src = url; await img.decode();
    let code = null;

    // Redimensionnement sur canvas temporaire pour décodage rapide
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

    // 1. Détecteur natif
    if (nativeDetector) {
      try {
        const r = await nativeDetector.detect(snapCanvas);
        if (r.length && isValidBarcode(r[0].rawValue)) code = r[0].rawValue;
      } catch (err) { }
    }

    // 2. ZXing double binariseur brut
    if (!code) {
      const snapData = snapCtx.getImageData(0, 0, sw, sh);
      code = decodeZxingBuffer(snapData.data, sw, sh);

      // 3. Filtres adaptatifs (contraste, netteté 1D, Bradley-Roth)
      if (!code) {
        const { sharpened, binarized } = processDegradedFilters(snapData.data, sw, sh);
        code = decodeZxingBuffer(sharpened, sw, sh) || decodeZxingBuffer(binarized, sw, sh);
      }
    }

    if (code) { lockedBarcode = null; lastCode = ''; onCode(code); }
    else toast('Code-barres non lisible sur cette photo', 'warn');
  } catch (err) { toast('Erreur de lecture de la photo', 'warn'); }
  finally { URL.revokeObjectURL(url); }
});

/* ---------- Mode Plein Écran Hybride (PWA Standalone + Fullscreen API) ---------- */
function isStandaloneMode() {
  return window.navigator.standalone === true ||
    window.matchMedia('(display-mode: standalone)').matches ||
    window.matchMedia('(display-mode: fullscreen)').matches;
}

function updateFullscreenUI() {
  const isFull = !!(document.fullscreenElement || document.webkitFullscreenElement);
  const btn = $('#btnFullscreen');
  if (!btn) return;
  if (isStandaloneMode()) {
    // En mode PWA installé sur l'écran d'accueil, l'application est DÉJÀ en plein écran natif autonome
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

async function toggleFullscreen() {
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

const btnFullscreen = $('#btnFullscreen');
if (btnFullscreen) {
  btnFullscreen.addEventListener('click', toggleFullscreen);
}

// Plein écran contrôlé explicitement par l'utilisateur via le bouton #btnFullscreen ou mode PWA autonome


['fullscreenchange', 'webkitfullscreenchange'].forEach(evt => {
  document.addEventListener(evt, updateFullscreenUI);
});
updateFullscreenUI();

/* ---------- démarrage ---------- */
(async function init() {
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
      users = fetchedUsers;
      if (currentUser && !users.some(u => u.name === currentUser)) {
        currentUser = '';
        localStorage.removeItem(USER_KEY);
      }
    }
  } catch (e) {
    console.warn('Mode hors-ligne ou serveur indisponible pour /api/users:', e);
  }
  updateUser();
  try {
    await loadPayOptions();
  } catch (e) {
    console.warn('Options de paiement par défaut utilisées:', e);
  }
  renderCart();
  syncLiveCart({ type: 'mobile_connected' });
  if (!currentUser) openUserModal();
  startCamera();
})();
