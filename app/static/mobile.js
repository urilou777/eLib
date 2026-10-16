/* Librairie – scanner mobile. 100 % hors-ligne, aucun innerHTML avec des données (anti-XSS), CSP stricte. */
'use strict';
const $ = s => document.querySelector(s);
const eur = n => (Number(n) || 0).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
const TOKEN_KEY = 'librairie_device_token', USER_KEY = 'librairie_user';

/* Construction DOM sûre : le texte passe toujours par textContent / createTextNode */
function el(tag, props = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') e.className = v;
    else if (k === 'text') e.textContent = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'style') e.style.cssText = v;
    else e.setAttribute(k, v);
  }
  kids.flat().forEach(c => { if (c != null) e.append(c.nodeType ? c : document.createTextNode(String(c))); });
  return e;
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
    return r.json();
  } catch (err) {
    clearTimeout(timer);
    if (err.name === 'AbortError') {
      throw new Error('Poste central injoignable (délai dépassé). Vérifiez que l\'ordinateur est allumé.');
    }
    throw err;
  }
}

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
    const r = await api('/api/mobile/pair', { method: 'POST', body: { code: m[1], name: deviceLabel() }, auth: false });
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
  list.replaceChildren(...users.map(u => el('button', {
    class: 'user-btn', type: 'button', text: u.name,
    onclick: () => { currentUser = u.name; localStorage.setItem(USER_KEY, u.name); updateUser(); $('#userModal').hidden = true; toast('Connecté : ' + u.name); }
  })));
  $('#userModal').hidden = false;
}
$('#userBtn').addEventListener('click', openUserModal);

/* ---------- panier (choix de l'origine TOUJOURS manuel, comme à la caisse du poste) ---------- */
let cart = [];            // { book, qty, lot }  lot: undefined = pas encore choisi | 'none' = hors stock | id de lot
let payOptions = [];

function lotRemaining(item) {
  if (item.lot === undefined || item.lot === 'none') return Infinity;
  const l = item.book.lots.find(x => x.id === item.lot);
  return l ? l.remaining : 0;
}
function addToCart(book) {
  if (book.is_pack) return toast('Pack : à encaisser depuis la caisse du poste (composition à répartir)', 'warn');
  beep();
  const ex = cart.find(i => i.book.id === book.id);
  if (ex) {
    if (ex.qty + 1 > lotRemaining(ex)) toast('Stock du lot choisi atteint', 'warn'); else ex.qty++;
  } else cart.push({ book, qty: 1, lot: undefined });
  toast('Ajouté : ' + book.title);
  renderCart();
}

function renderCart() {
  const count = cart.reduce((s, i) => s + i.qty, 0);
  const total = cart.reduce((s, i) => s + i.qty * i.book.price, 0);
  $('#cartCount').textContent = count;
  $('#totalVal').textContent = eur(total);

  const list = $('#cartItems');
  if (!cart.length) {
    list.replaceChildren(el('div', { class: 'muted', style: 'text-align:center;padding:18px', text: 'Visez le code-barres d\'un livre pour commencer.' }));
  } else {
    list.replaceChildren(...cart.map((item, idx) => {
      const b = item.book;
      const lots = b.lots.map(l => el('button', {
        class: 'chip' + (item.lot === l.id ? ' on' : ''), type: 'button',
        onclick: () => { item.lot = l.id; item.qty = Math.min(item.qty, l.remaining); renderCart(); }
      }, el('i', { style: 'background:' + (/^#[0-9a-fA-F]{3,8}$/.test(l.color || '') ? l.color : '#8892b0') }),
         `${l.owner} · dispo ${l.remaining}`));
      lots.push(el('button', {
        class: 'chip' + (item.lot === 'none' ? ' on' : ''), type: 'button',
        onclick: () => { item.lot = 'none'; renderCart(); }
      }, 'Hors stock (non tracé)'));
      return el('div', { class: 'cart-item' + (item.lot === undefined ? ' todo' : '') },
        el('div', { class: 'ci-top' },
          el('div', {}, el('div', { class: 'ci-title', text: b.title + (b.volume ? ' · Vol. ' + b.volume : '') }),
            el('div', { class: 'muted', text: eur(b.price) + ' / unité' })),
          el('div', { class: 'qty' },
            el('button', { type: 'button', text: '−', onclick: () => { item.qty--; if (item.qty <= 0) cart.splice(idx, 1); renderCart(); } }),
            el('b', { text: item.qty }),
            el('button', { type: 'button', text: '+', onclick: () => { if (item.qty + 1 > lotRemaining(item)) toast('Stock du lot choisi atteint', 'warn'); else { item.qty++; renderCart(); } } }))),
        el('div', { class: 'lots' }, lots),
        item.lot === undefined ? el('div', { class: 'hint', text: 'Touchez l\'origine de cet exemplaire' }) : null);
    }));
  }

  const missingLot = cart.some(i => i.lot === undefined);
  const missingPay = !$('#payMethod').value;
  $('#btnValidate').disabled = !cart.length || missingLot || missingPay;
  $('#validHint').textContent = !cart.length ? '' : missingLot ? 'Choisissez l\'origine de chaque livre' : missingPay ? 'Choisissez le mode de paiement' : '';
}
$('#clearCart').addEventListener('click', () => { cart = []; renderCart(); });
$('#payMethod').addEventListener('change', renderCart);

async function loadPayOptions() {
  try { const o = await api('/api/options'); payOptions = (o.payment || []).map(p => p.label); } catch (e) { payOptions = []; }
  if (!payOptions.length) payOptions = ['Espèces', 'PayPal POS', 'Wero (Compte perso libraire)'];
  $('#payMethod').replaceChildren(el('option', { value: '', text: '— Mode de paiement —' }), ...payOptions.map(p => el('option', { value: p, text: p })));
}

$('#btnValidate').addEventListener('click', async () => {
  if (!currentUser) return openUserModal();
  const btn = $('#btnValidate'); btn.disabled = true;           // anti double-envoi : un seul encaissement par appui
  try {
    const r = await api('/api/sales', {
      method: 'POST',
      body: {
        payment: $('#payMethod').value, note: 'Vente mobile',
        lines: cart.map(i => ({
          book_id: i.book.id, qty: i.qty, unit_price: i.book.price,
          allocations: [{ book_id: i.book.id, lot_id: i.lot === 'none' ? null : i.lot, qty: i.qty }]
        }))
      }
    });
    toast('Vente enregistrée : ' + eur(r.total));
    if (navigator.vibrate) navigator.vibrate([60, 40, 60]);
    cart = []; $('#payMethod').value = '';
  } catch (e) { toast(e.message, 'err'); }
  renderCart();
});

/* ---------- Mode de travail Mobile : Vente vs Réception ---------- */
let currentMode = 'sale'; // 'sale' | 'recv'
let recvList = [];        // [{ book, qty }]
let ownersList = [];

async function loadOwners() {
  try {
    ownersList = await api('/api/owners');
    const sel = $('#recvOwner');
    if (sel) {
      sel.replaceChildren(...ownersList.map(o => el('option', { value: o.id, text: o.name + (o.kind ? ` (${o.kind})` : '') })));
    }
  } catch (e) { ownersList = []; }
}

function setMobileMode(mode) {
  currentMode = mode;
  $('#btnModeSale').classList.toggle('on', mode === 'sale');
  $('#btnModeRecv').classList.toggle('on', mode === 'recv');
  $('#cartCard').hidden = (mode !== 'sale');
  $('#saleBottom').hidden = (mode !== 'sale');
  $('#recvCard').hidden = (mode !== 'recv');
  $('#recvBottom').hidden = (mode !== 'recv');
  if (mode === 'recv' && !ownersList.length) loadOwners();
  toast(mode === 'sale' ? 'Mode Vente actif' : 'Mode Réception actif', 'ok');
}

$('#btnModeSale').addEventListener('click', () => setMobileMode('sale'));
$('#btnModeRecv').addEventListener('click', () => setMobileMode('recv'));

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
}

$('#clearRecv').addEventListener('click', () => { recvList = []; renderRecv(); });

$('#btnValidateRecv').addEventListener('click', async () => {
  if (!currentUser) return openUserModal();
  const ownerId = parseInt($('#recvOwner').value);
  if (!ownerId) return toast('Veuillez sélectionner un propriétaire', 'warn');
  const btn = $('#btnValidateRecv');
  btn.disabled = true;
  try {
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
    toast(`${recvList.reduce((s, i) => s + i.qty, 0)} exemplaire(s) entrés en stock`, 'ok');
    if (navigator.vibrate) navigator.vibrate([60, 40, 60]);
    recvList = [];
    renderRecv();
  } catch (e) {
    toast(e.message, 'err');
    btn.disabled = false;
  }
});

/* ---------- Modale de Création Rapide de Livre Inconnu ---------- */
let pendingNewCode = null;

function openNewBookModal(code) {
  pendingNewCode = code;
  $('#nbCode').value = code;
  $('#nbTitle').value = '';
  $('#nbAuthor').value = '';
  $('#nbPrice').value = '';
  $('#newBookModal').hidden = false;
  setTimeout(() => $('#nbTitle').focus(), 150);
}

function closeNewBookModal() {
  $('#newBookModal').hidden = true;
  pendingNewCode = null;
}

$('#btnCancelNewBook').addEventListener('click', closeNewBookModal);

$('#btnSaveNewBook').addEventListener('click', async () => {
  const code = $('#nbCode').value.trim();
  const title = $('#nbTitle').value.trim();
  const author = $('#nbAuthor').value.trim();
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

/* ---------- recherche / saisie manuelle ---------- */
let isLookingUp = false;

async function lookupCode(code) {
  if (isLookingUp) return; // Ignore tout nouveau scan si une requête est déjà en attente
  isLookingUp = true;
  try {
    const book = await api('/api/books/scan/' + encodeURIComponent(code), { timeoutMs: 3500 });
    if (currentMode === 'sale') {
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
const nativeDetector = ('BarcodeDetector' in window)
  ? new BarcodeDetector({ formats: ['ean_13', 'ean_8', 'upc_a', 'code_128'] })
  : null;

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
  // RÈGLE AMAZON / LOGISTIQUE PRO :
  // 1. Si le livre est différent du précédent (ex: 100 livres différents dans un carton) : DÉBIT INSTANTANÉ (0 ms d'attente) !
  // 2. Si c'est le même livre consécutif, on attend soit que le livre sorte du champ (code == null), soit un micro-délai de 650 ms
  if (code === lastCode && (now - lastTime < 650)) {
    return;
  }
  
  lastCode = code;
  lastTime = now;
  flashSuccess();
  lookupCode(code);
}

let rearCameras = [];
let currentCamIndex = 0;

let inactivityTimer = null;
let isAutoPaused = false;
const INACTIVITY_MS = 90 * 1000; // 90 secondes sans scan ni interaction

function resetInactivity() {
  clearTimeout(inactivityTimer);
  // Si la caméra s'était mise en veille automatique et que l'utilisateur retouche l'écran : réveil automatique immédiat !
  if (isAutoPaused) {
    isAutoPaused = false;
    startCamera();
    return;
  }
  if (stream) {
    inactivityTimer = setTimeout(() => {
      pauseCamera('auto');
    }, INACTIVITY_MS);
  }
}

function pauseCamera(reason = 'manual') {
  stopCamera();
  if (reason === 'auto') {
    isAutoPaused = true;
    camStatus(true, 'Veille économie d\'énergie', 'Caméra en veille pour économiser la batterie. Touchez l\'écran pour la réactiver instantanément.', 'Reprendre le scan', () => { isAutoPaused = false; startCamera(); });
  } else {
    isAutoPaused = false;
    camStatus(true, 'Caméra en pause', 'Caméra suspendue. Appuyez sur le bouton dès que vous souhaitez scanner.', 'Reprendre le scan', () => { isAutoPaused = false; startCamera(); });
  }
}

// Réinitialiser le minuteur et réveiller automatiquement la caméra dès que le libraire touche l'écran
['touchstart', 'mousedown', 'keydown'].forEach(evt => {
  window.addEventListener(evt, resetInactivity, { passive: true });
});

function stopCamera() {
  clearInterval(scanTimer); scanTimer = null;
  clearTimeout(inactivityTimer); inactivityTimer = null;
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
  videoTrack = null;
  $('#video').srcObject = null;
  $('#btnTorch').hidden = true;
}

function camStatus(show, title, msg, btnText = null, onBtn = null) {
  $('#camStatus').hidden = !show;
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

async function findOptimalCamera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return null;
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const videoDevices = devices.filter(d => d.kind === 'videoinput');
    if (!videoDevices.length) return null;

    // Filtrer les caméras arrière
    const rear = videoDevices.filter(d => {
      const l = (d.label || '').toLowerCase();
      return l.includes('back') || l.includes('rear') || l.includes('environment') || l.includes('arrière') || l.includes('0');
    });

    const candidates = rear.length ? rear : videoDevices;
    if (candidates.length === 1) return candidates[0].deviceId;

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
      if (label.includes('main') || label.includes('standard') || label.includes('camera 0') || label.includes('camera2 0') || label.includes('primary')) {
        score += 50;
      }

      // 3. Inspection matérielle avancée via getCapabilities()
      try {
        const testStream = await navigator.mediaDevices.getUserMedia({
          video: { deviceId: { exact: dev.deviceId } },
          audio: false
        });
        const track = testStream.getVideoTracks()[0];
        if (track && track.getCapabilities) {
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
        testStream.getTracks().forEach(t => t.stop());
      } catch (err) {
        // En cas d'erreur de sonde sur ce capteur, on garde le score textuel
      }

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

async function startCamera(specificDeviceId = null) {
  stopCamera();
  if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    return camStatus(true, 'Caméra indisponible', 'Cette page nécessite une connexion HTTPS pour accéder à l\'appareil photo.');
  }
  try {
    let targetDeviceId = specificDeviceId;

    // Si aucun capteur spécifié, trouver automatiquement le capteur le plus net (meilleure macro/focus)
    if (!targetDeviceId && !bestCameraDeviceId) {
      bestCameraDeviceId = await findOptimalCamera();
    }
    if (!targetDeviceId && bestCameraDeviceId) {
      targetDeviceId = bestCameraDeviceId;
    }

    // Contraintes standards W3C (Full HD idéale)
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
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'environment' },
          audio: false
        });
      }
    }

    const video = $('#video');
    video.srcObject = stream;
    await video.play();
    camStatus(false);

    videoTrack = stream.getVideoTracks()[0];

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
            torchActive = !torchActive;
            await videoTrack.applyConstraints({ advanced: [{ torch: torchActive }] });
            btnTorch.classList.toggle('on', torchActive);
          } catch (err) { }
        };
      }
    }

    // Démarrer la surveillance d'inactivité (veille auto après 90s)
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

    // Boucle de numérisation universelle à résolution native (1:1 sans perte de netteté)
    scanTimer = setInterval(async () => {
      if (isScanning || video.readyState < 2) return;
      isScanning = true;
      try {
        const vw = video.videoWidth;
        const vh = video.videoHeight;
        if (!vw || !vh) return;

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
        const scanCrop = async (cx, cy, cw, ch) => {
          if (canvasRoi.width !== cw || canvasRoi.height !== ch) {
            canvasRoi.width = cw; canvasRoi.height = ch;
            canvasFilter.width = cw; canvasFilter.height = ch;
          }
          ctxRoi.drawImage(video, cx, cy, cw, ch, 0, 0, cw, ch);

          // Test rapide avec BarcodeDetector natif
          if (nativeDetector) {
            try {
              const results = await nativeDetector.detect(canvasRoi);
              for (const r of results) {
                if (isValidBarcode(r.rawValue)) return r.rawValue;
              }
            } catch (e) { }
          }

          // Test avec ZXing TRY_HARDER
          const rawImg = ctxRoi.getImageData(0, 0, cw, ch);
          let found = decodeZxingBuffer(rawImg.data, cw, ch);
          if (found) return found;

          // Test avec filtres adaptatifs (netteté 1D + Bradley-Roth)
          const { sharpened, binarized } = processDegradedFilters(rawImg.data, cw, ch);
          found = decodeZxingBuffer(sharpened, cw, ch);
          if (found) return found;
          found = decodeZxingBuffer(binarized, cw, ch);
          return found;
        };

        // ÉCHELLES MULTIPLES (PYRAMIDE D'ÉCHELLES) :
        // Échelle A : Découpe Macro centrale (zoom 2x virtuel) -> lit les petits codes-barres sans avoir à coller le téléphone !
        code = await scanCrop(cx2, cy2, cw2, ch2);

        // Échelle B : Cadrage large standard -> lit les codes normaux et grands
        if (!code) {
          code = await scanCrop(cx1, cy1, cw1, ch1);
        }

        if (code) {
          onCode(code);
        } else {
          // Sortie de champ détectée (aucun code devant l'objectif) :
          // Réinitialise immédiatement le verrou pour que le livre suivant (même s'il a le même code) soit pris instantanément
          lastCode = '';
        }
      } catch (err) {
        // Ignorer les erreurs d'une frame isolée
      } finally {
        isScanning = false;
      }
    }, 110);

  } catch (e) {
    const denied = e && (e.name === 'NotAllowedError' || e.name === 'SecurityError');
    camStatus(true, denied ? 'Autorisation caméra refusée' : 'Caméra indisponible',
      denied ? 'Android : touchez le cadenas dans la barre d\'adresse → Autorisations → Appareil photo → Autoriser, puis réessayez.'
             : 'Aucune caméra utilisable. Utilisez le bouton photo ou la saisie manuelle.');
  }
}
$('#btnCam').addEventListener('click', startCamera);
document.addEventListener('visibilitychange', () => {
  if (document.hidden) { stopCamera(); camStatus(true, 'Caméra en pause', 'Appuyez pour reprendre le scan.'); }
  else if (localStorage.getItem(TOKEN_KEY)) startCamera();
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

    if (code) { lastCode = ''; onCode(code); }
    else toast('Code-barres non lisible sur cette photo', 'warn');
  } catch (err) { toast('Erreur de lecture de la photo', 'warn'); }
  finally { URL.revokeObjectURL(url); }
});

/* ---------- démarrage ---------- */
(async function init() {
  await pairFromHash();
  if (!localStorage.getItem(TOKEN_KEY)) { renderCart(); return showPairing(); }
  try {
    users = await api('/api/users');
    if (!users.some(u => u.name === currentUser)) { currentUser = ''; localStorage.removeItem(USER_KEY); }
  } catch (e) { return; }                 // 401 géré dans api()
  updateUser();
  await loadPayOptions();
  renderCart();
  if (!currentUser) openUserModal();
  startCamera();
})();
