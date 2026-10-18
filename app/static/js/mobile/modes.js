/* Librairie Mobile - Gestion des Modes Vente vs Réception Stock */
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
