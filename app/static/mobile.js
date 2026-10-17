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

/* ---------- Panier & Origines (Smart Split) & Multi-paiement ---------- */
let cart = [];            // { book, qty, lot }  lot: undefined = pas encore choisi | 'none' = hors stock | id de lot
let payOptions = [];
let originPayments = {};  // { [ownerName]: { method: 'CB'|'Espèces'|'Wero'|'Multi', parts: [{payment, amount}]|null } }

function getItemOwner(item) {
  if (item.lot === 'none') return 'Hors stock';
  if (item.lot === undefined) return 'À préciser';
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
  if (item.lot === undefined || item.lot === 'none') return Infinity;
  const l = item.book.lots.find(x => x.id === item.lot);
  return l ? l.remaining : 0;
}

function defaultLotForBook(book) {
  const lots = (book.lots || []).filter(l => l.remaining > 0);
  if (!lots.length) return undefined;
  if (lots.length === 1) return lots[0].id;
  const cr = lots.find(l => (l.owner || '').trim().toLowerCase() === 'cité royale');
  return cr ? cr.id : lots[0].id;
}

function addToCart(book) {
  if (book.is_pack) return toast('Pack : à encaisser depuis la caisse du poste (composition à répartir)', 'warn');
  beep();
  const defLot = defaultLotForBook(book);
  const ex = cart.find(i => i.book.id === book.id && (i.lot === defLot || i.lot === undefined));
  if (ex) {
    if (ex.lot === undefined && defLot !== undefined) ex.lot = defLot;
    if (ex.qty + 1 > lotRemaining(ex)) toast('Stock du lot choisi atteint', 'warn'); else ex.qty++;
  } else cart.push({ book, qty: 1, lot: defLot });
  toast('Ajouté : ' + book.title);
  renderCart();
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
  closeMultiPayModal();
  renderCart();
  toast('Cumul défini pour ' + activeMpOwner);
});

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
}
$('#clearCart').addEventListener('click', () => { cart = []; originPayments = {}; renderCart(); });

async function loadPayOptions() {
  try {
    const o = await api('/api/options');
    payOptions = (o.payment || []).map(p => (p.label === 'PayPal POS (CB)' || p.label.toLowerCase().includes('paypal') ? 'CB' : p.label));
  } catch (e) { payOptions = []; }
  if (!payOptions.length) payOptions = ['Espèces', 'CB', 'Wero'];
  payOptions = Array.from(new Set(payOptions));
  renderCart();
}

let mGender = '';
let mAge = '';
let mStar = 0;

function getAutoMobileMoment() {
  const isSunday = new Date().getDay() === 0;
  const currentHour = new Date().getHours();
  return isSunday ? (currentHour >= 12 ? '2e Culte (Jeunes EJP)' : '1er Culte (Principal)') : 'En semaine / Autre';
}

let mMoment = localStorage.getItem('librairie_mobile_moment') || getAutoMobileMoment();

function updateProfileSummary() {
  // Profil directement visible sans tiroir
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
    updateProfileSummary();
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
      updateProfileSummary();
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
      updateProfileSummary();
    }
  });
}

$('#btnValidate').addEventListener('click', async () => {
  if (!currentUser) return openUserModal();
  const btn = $('#btnValidate');
  btn.disabled = true; // anti double-envoi : un seul encaissement par appui
  
  const origins = getCartByOrigin();
  if (!origins.length) return;

  try {
    const validatedSales = [];
    for (let idx = 0; idx < origins.length; idx++) {
      const g = origins[idx];
      const payState = originPayments[g.owner] || { method: 'Espèces', parts: null };
      const lines = g.items.map(i => ({
        book_id: i.book.id,
        qty: i.qty,
        unit_price: i.book.price,
        allocations: [{ book_id: i.book.id, lot_id: i.lot === 'none' ? null : i.lot, qty: i.qty }]
      }));

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
    mGender = ''; mAge = ''; mStar = 0;
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
const INACTIVITY_MS = 15 * 1000; // 15 secondes sans scan (mode ultra-agressif anti-chauffe / économie batterie)

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
      const isFront = l.includes('front') || l.includes('avant') || l.includes('selfie') || l.includes('user');
      if (isFront) return false;
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

    return bestId || candidates[0].deviceId;
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
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'environment' },
            audio: false
          });
        } catch (e3) {
          // Dernier repli : n'importe quelle caméra vidéo
          stream = await navigator.mediaDevices.getUserMedia({
            video: true,
            audio: false
          });
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
              lastScanSuccessTime = Date.now();
              if (!isBurstMode) {
                isBurstMode = true;
                updateEcoBadge(true);
              }
              onCode(code);
            } else {
              // Sortie de champ détectée (aucun code devant l'objectif) :
              // Réinitialise immédiatement le verrou pour que le livre suivant (même s'il a le même code) soit pris instantanément
              lastCode = '';
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

    if (code) { lastCode = ''; onCode(code); }
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

// Essai de bascule automatique en plein écran au premier tap utilisateur (navigateurs Android)
let autoFullscreenTried = false;
function attemptAutoFullscreen() {
  if (autoFullscreenTried || isStandaloneMode()) return;
  autoFullscreenTried = true;
  const docEl = document.documentElement;
  const req = docEl.requestFullscreen || docEl.webkitRequestFullscreen;
  if (req) {
    req.call(docEl).catch(() => {});
  }
}
window.addEventListener('touchstart', attemptAutoFullscreen, { once: true, passive: true });
window.addEventListener('click', attemptAutoFullscreen, { once: true, passive: true });

['fullscreenchange', 'webkitfullscreenchange'].forEach(evt => {
  document.addEventListener(evt, updateFullscreenUI);
});
updateFullscreenUI();

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
