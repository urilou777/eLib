/* Librairie Mobile - Core DOM, Formatage & Utilitaires */
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
}
updateViewportHeight();
if (window.visualViewport) {
  window.visualViewport.addEventListener('resize', updateViewportHeight);
}
window.addEventListener('resize', updateViewportHeight);
window.addEventListener('orientationchange', () => setTimeout(updateViewportHeight, 100));
window.addEventListener('pageshow', updateViewportHeight);
window.addEventListener('focus', updateViewportHeight);
