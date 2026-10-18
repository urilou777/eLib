/* Librairie Mobile - Numérisation OCR Page de Garde & Couverture */
'use strict';
import { $, el, toast, updateViewportHeight } from './core.js';
import { api } from './api.js';
import { toSentenceCase, toTitleCase, triggerAllBddChecks, openNewBookModal } from './new_book_modal.js';
import { addToRecv } from './modes.js';

export async function fileToResizedBase64(file, maxDim = 1600) {
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

export async function performOcr(file) {
  const b64 = await fileToResizedBase64(file, 1600);
  return api('/api/ocr/scan', {
    method: 'POST',
    body: { image_base64: b64 },
    timeoutMs: 15000
  });
}

export function updateOcrMergeButtons() {
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

export function renderOcrChips(lines) {
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
window._renderOcrChips = renderOcrChips;

export function initOcr() {
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

  const nbOcrInput = $('#nbOcrInput');
  if (nbOcrInput) {
    nbOcrInput.addEventListener('change', async e => {
      window.scrollTo(0, 0);
      updateViewportHeight();
      if (document.activeElement && document.activeElement.blur) document.activeElement.blur();

      const file = e.target.files && e.target.files[0];
      if (!file) return;
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
            import('./new_book_modal.js').then(m => m.showExistingBookBanner(res.matched_book));
          }

          if (res.corrections) {
            if (res.corrections.author) {
              toast(`✨ Auteur corrigé d\'après la base : ${res.corrections.author.corrected}`, 'ok');
            }
            if (res.corrections.publisher) {
              toast(`✨ Éditeur corrigé d\'après la base : ${res.corrections.publisher.corrected}`, 'ok');
            }
          }

          triggerAllBddChecks();
          toast('Page de garde analysée avec succès', 'ok');
        }
      } catch (err) {
        toast(err.message || "Erreur lors de l'OCR", 'err');
      } finally {
        if (txtSpan) txtSpan.textContent = oldText;
        nbOcrInput.value = '';
        window.scrollTo(0, 0);
        updateViewportHeight();
      }
    });
  }

  const recvOcrInput = $('#recvOcrInput');
  if (recvOcrInput) {
    recvOcrInput.addEventListener('change', async e => {
      window.scrollTo(0, 0);
      updateViewportHeight();
      if (document.activeElement && document.activeElement.blur) document.activeElement.blur();

      const file = e.target.files && e.target.files[0];
      if (!file) return;
      const txtSpan = $('#recvOcrText');
      const oldText = txtSpan ? txtSpan.textContent : '';
      if (txtSpan) txtSpan.textContent = '⏳ Scan OCR...';
      try {
        toast('Numérisation de la page de garde...', 'ok');
        const res = await performOcr(file);
        window.scrollTo(0, 0);
        updateViewportHeight();
        if (res) {
          if (res.matched_book) {
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
        recvOcrInput.value = '';
        window.scrollTo(0, 0);
        updateViewportHeight();
      }
    });
  }
}
