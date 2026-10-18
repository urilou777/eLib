/* Librairie Mobile - Mode Plein Écran Hybride (PWA Standalone + Fullscreen API) */
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
