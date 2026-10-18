/* Librairie Mobile - Appairage Appareil & Profils Libraire */
'use strict';
import { $, el, toast, TOKEN_KEY, USER_KEY } from './core.js';
import { state } from './state.js';
import { api } from './api.js';
import { syncLiveCart } from './network.js';
import { stopCamera } from './scanner.js';

export function deviceLabel() {
  const m = navigator.userAgent.match(/\(([^)]+)\)/);
  return (m ? m[1] : 'Téléphone').replace(/[;]\s*wv/i, '').slice(0, 50);
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
