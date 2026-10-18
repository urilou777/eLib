/* Librairie Mobile - Client API HTTP */
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
      throw new Error('Poste central injoignable (délai dépassé). Vérifiez que l\'ordinateur est allumé.');
    }
    throw err;
  }
}
