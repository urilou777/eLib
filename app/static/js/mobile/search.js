/* Librairie Mobile - Recherche & Saisie Manuelle */
'use strict';
import { $, el, eur, toast } from './core.js';
import { state } from './state.js';
import { api } from './api.js';
import { addToCart } from './cart.js';
import { addToRecv } from './modes.js';
import { openNewBookModal } from './new_book_modal.js';

const codeCache = new Map(); // Cache local en mémoire vive pour réponse instantanée 0ms

export async function lookupCode(code) {
  if (state.isLookingUp) return;
  state.isLookingUp = true;
  try {
    let book = codeCache.get(code);
    if (!book) {
      book = await api('/api/books/scan/' + encodeURIComponent(code), { timeoutMs: 3500 });
      if (book && book.id) {
        codeCache.set(code, book);
        // Ne garde que les 150 derniers livres scannés en cache mémoire vive
        if (codeCache.size > 150) {
          const firstKey = codeCache.keys().next().value;
          codeCache.delete(firstKey);
        }
      }
    }
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
  if (/^[0-9][0-9\- ]{7,}$/.test(q)) { await lookupCode(q); $('#manualCode').value = ''; return; }
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
