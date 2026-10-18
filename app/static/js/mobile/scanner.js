/* Librairie Mobile - Moteur de Scan Haute Tolérance & Cycle de Vie Caméra */
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

let nativeDetector = null;
if ('BarcodeDetector' in window) {
  try {
    nativeDetector = new BarcodeDetector({ formats: ['ean_13', 'ean_8', 'upc_a', 'code_128'] });
  } catch (e) {
    console.warn('BarcodeDetector non supporté ou erreur d initialisation:', e);
    nativeDetector = null;
  }
}

export function isValidBarcode(raw) {
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
    badge.title = burst ? 'Mode Rush : 9 FPS haute cadence' : 'Mode Éco : 3 FPS économie d\'énergie';
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
    return camStatus(true, 'Caméra indisponible', 'Cette page nécessite une connexion HTTPS pour accéder à l\'appareil photo.');
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
      denied ? 'Android : touchez le cadenas dans la barre d\'adresse → Autorisations → Appareil photo → Autoriser, puis réessayez.'
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
