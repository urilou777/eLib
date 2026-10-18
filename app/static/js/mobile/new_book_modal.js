/* Librairie Mobile - Modale Fiche Nouveau Livre & Vérification BDD */
'use strict';
import { $, el, eur, toast, esc, updateViewportHeight } from './core.js';
import { state } from './state.js';
import { api } from './api.js';
import { addToCart } from './cart.js';
import { addToRecv } from './modes.js';
import { closeMobileBookStats } from './book_stats.js';
import { closeMultiPayModal } from './cart.js';

export function levenshteinDist(s1, s2) {
  const m = s1.length, n = s2.length;
  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = 0; i <= m; i++) dp[i][0] = i;
  for (let j = 0; j <= n; j++) dp[0][j] = j;
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      const cost = s1[i - 1] === s2[j - 1] ? 0 : 1;
      dp[i][j] = Math.min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost);
    }
  }
  return dp[m][n];
}

export function stringSimilarity(s1, s2) {
  if (!s1 || !s2) return 0;
  s1 = s1.toLowerCase().trim();
  s2 = s2.toLowerCase().trim();
  if (s1 === s2) return 1.0;
  const maxLen = Math.max(s1.length, s2.length);
  if (maxLen === 0) return 1.0;
  return (maxLen - levenshteinDist(s1, s2)) / maxLen;
}

export function checkFieldBdd(inputId, badgeId, suggestionId, canonicalList) {
  const input = $(inputId);
  const badge = $(badgeId);
  const sugg = $(suggestionId);
  if (!input) return;
  const val = input.value.trim();
  if (!val) {
    if (badge) badge.style.display = 'none';
    if (sugg) sugg.style.display = 'none';
    input.classList.remove('field-in-bdd');
    return;
  }
  const normVal = val.toLowerCase();
  const exact = (canonicalList || []).find(c => c && c.toLowerCase() === normVal);
  if (exact) {
    if (badge) {
      badge.textContent = '✓ BDD';
      badge.style.display = 'inline-flex';
    }
    if (sugg) sugg.style.display = 'none';
    input.classList.add('field-in-bdd');
    return;
  }
  input.classList.remove('field-in-bdd');
  if (badge) badge.style.display = 'none';

  let bestMatch = null, bestScore = 0;
  for (const item of (canonicalList || [])) {
    if (!item) continue;
    const score = stringSimilarity(val, item);
    if (score >= 0.72 && score > bestScore) {
      bestScore = score;
      bestMatch = item;
    }
  }
  if (bestMatch && sugg) {
    sugg.innerHTML = `<span class="typo-suggestion">💡 Suggestion BDD : <b>${esc(bestMatch)}</b> <span style="font-size:10px;opacity:0.8">(Cliquer pour corriger)</span></span>`;
    sugg.style.display = 'block';
    sugg.onclick = () => {
      input.value = bestMatch;
      checkFieldBdd(inputId, badgeId, suggestionId, canonicalList);
      toast(`Orthographe BDD appliquée : ${bestMatch}`, 'ok');
    };
  } else if (sugg) {
    sugg.style.display = 'none';
  }
}

export function triggerAllBddChecks() {
  checkFieldBdd('#nbAuthor', '#nbAuthorBddBadge', '#nbAuthorTypoSuggestion', state.dbAuthors);
  checkFieldBdd('#nbPublisher', '#nbPublisherBddBadge', '#nbPublisherTypoSuggestion', state.dbPublishers);
  const codeVal = $('#nbCode') ? $('#nbCode').value.trim() : '';
  if (codeVal) checkCodeInCatalog(codeVal);
  else hideExistingBookBanner();
}

export async function checkCodeInCatalog(code) {
  if (!code) {
    hideExistingBookBanner();
    return;
  }
  try {
    const book = await api('/api/books/scan/' + encodeURIComponent(code));
    if (book && book.id) {
      showExistingBookBanner(book);
    } else {
      hideExistingBookBanner();
    }
  } catch (e) {
    hideExistingBookBanner();
  }
}

export function showExistingBookBanner(b) {
  state.currentMatchedBook = b;
  const banner = $('#nbBookExistsBanner');
  const title = $('#nbExistsTitle');
  const badge = $('#nbExistsStockBadge');
  const codeBadge = $('#nbCodeBddBadge');
  if (!banner) return;
  title.textContent = `${b.title}${b.author ? ' · ' + b.author : ''} (${eur(b.price)})`;
  if (badge) badge.textContent = `Stock actuel : ${b.stock ?? 0} ex.`;
  if (codeBadge) {
    codeBadge.textContent = `✓ En base (${b.stock ?? 0} ex.)`;
    codeBadge.style.display = 'inline-flex';
  }
  banner.style.display = 'block';

  const addStockBtn = $('#nbBtnAddToStock');
  if (addStockBtn) {
    addStockBtn.onclick = () => {
      if (state.currentMode === 'recv') {
        addToRecv(b);
        toast(`📦 ${b.title} ajouté au carton de réception !`, 'ok');
      } else {
        addToCart(b);
        toast(`🛒 ${b.title} ajouté au panier !`, 'ok');
      }
      closeNewBookModal();
    };
  }

  const applyBtn = $('#nbBtnApplyMatch');
  if (applyBtn) {
    applyBtn.onclick = () => {
      $('#nbTitle').value = b.title;
      if (b.author) $('#nbAuthor').value = b.author;
      if (b.publisher && $('#nbPublisher')) $('#nbPublisher').value = b.publisher;
      if (b.price != null && b.price > 0) $('#nbPrice').value = b.price;
      banner.style.display = 'none';
      toast('Fiche officielle du livre appliquée !', 'ok');
      triggerAllBddChecks();
    };
  }
}

export function hideExistingBookBanner() {
  state.currentMatchedBook = null;
  const banner = $('#nbBookExistsBanner');
  if (banner) banner.style.display = 'none';
  const codeBadge = $('#nbCodeBddBadge');
  if (codeBadge) codeBadge.style.display = 'none';
}

export function toSentenceCase(str) {
  if (!str) return '';
  str = str.trim();
  if (!str) return '';
  const stopwords = new Set([
    'de', 'du', 'des', 'le', 'la', 'les', 'un', 'une', 'et', 'en', 'au', 'aux',
    'par', 'pour', 'sur', 'dans', 'a', 'd', 'l', 'ou', 'avec', 'sans', 'sous', 'vers', 'chez'
  ]);
  const words = str.split(/\s+/);
  const formatted = words.map((w, i) => {
    if (w.includes('-') && !w.startsWith('-') && !w.endsWith('-')) {
      return w.split('-').map((p, j) => (i === 0 && j === 0) ? p.charAt(0).toUpperCase() + p.slice(1).toLowerCase() : p.toLowerCase()).join('-');
    }
    if (w.includes("'") && !w.startsWith("'") && !w.endsWith("'")) {
      const [pre, rest] = w.split("'", 2);
      const preFmt = (i === 0) ? pre.charAt(0).toUpperCase() + pre.slice(1).toLowerCase() + "'" : pre.toLowerCase() + "'";
      const restFmt = (i === 0) ? rest.charAt(0).toUpperCase() + rest.slice(1).toLowerCase() : rest.toLowerCase();
      return preFmt + restFmt;
    }
    const low = w.toLowerCase();
    if (i === 0) return low.charAt(0).toUpperCase() + low.slice(1);
    return low;
  });
  let res = formatted.join(' ');
  res = res.replace(/([:\.?!]\s+)([a-zàéèêîôû])/g, (m, p1, p2) => p1 + p2.toUpperCase());
  return res.charAt(0).toUpperCase() + res.slice(1);
}

export function toTitleCase(str) {
  if (!str) return '';
  str = str.trim();
  if (!str) return '';
  const stopwords = new Set([
    'de', 'du', 'des', 'le', 'la', 'les', 'un', 'une', 'et', 'en', 'au', 'aux',
    'par', 'pour', 'sur', 'dans', 'a', 'd', 'l', 'ou', 'avec', 'sans', 'sous', 'vers', 'chez'
  ]);
  const words = str.split(/\s+/);
  const formatted = words.map((w, i) => {
    if (w.includes('-') && !w.startsWith('-') && !w.endsWith('-')) {
      return w.split('-').map(p => stopwords.has(p.toLowerCase()) ? p.toLowerCase() : (p.charAt(0).toUpperCase() + p.slice(1).toLowerCase())).join('-');
    }
    if (w.includes("'") && !w.startsWith("'") && !w.endsWith("'")) {
      const [pre, rest] = w.split("'", 2);
      const preFmt = (i === 0) ? pre.charAt(0).toUpperCase() + pre.slice(1).toLowerCase() + "'" : pre.toLowerCase() + "'";
      const restFmt = stopwords.has(rest.toLowerCase()) ? rest.toLowerCase() : (rest.charAt(0).toUpperCase() + rest.slice(1).toLowerCase());
      return preFmt + restFmt;
    }
    const low = w.toLowerCase();
    if (i === 0 || !stopwords.has(low)) {
      return low.charAt(0).toUpperCase() + low.slice(1);
    }
    return low;
  });
  let res = formatted.join(' ');
  res = res.replace(/([:\.?!]\s+)([a-zàéèêîôû])/g, (m, p1, p2) => p1 + p2.toUpperCase());
  return res.charAt(0).toUpperCase() + res.slice(1);
}

export function openNewBookModal(code = '', prefill = {}) {
  state.pendingNewCode = code || '';
  $('#nbCode').value = state.pendingNewCode;
  $('#nbTitle').value = prefill.matched_book ? (prefill.matched_book.title || '') : toSentenceCase(prefill.title || '');
  $('#nbAuthor').value = prefill.matched_book ? (prefill.matched_book.author || '') : toTitleCase(prefill.author || '');
  if ($('#nbPublisher')) $('#nbPublisher').value = prefill.matched_book ? (prefill.matched_book.publisher || '') : (prefill.publisher || '');
  $('#nbPrice').value = (prefill.price != null && prefill.price > 0) ? prefill.price : (prefill.matched_book && prefill.matched_book.price > 0 ? prefill.matched_book.price : '');
  
  const badge = $('#nbOcrBadge');
  if (badge) badge.style.display = prefill.lines ? 'inline-flex' : 'none';

  if (prefill.matched_book) {
    showExistingBookBanner(prefill.matched_book);
  } else if (state.pendingNewCode) {
    checkCodeInCatalog(state.pendingNewCode);
  } else {
    hideExistingBookBanner();
  }
  
  if (prefill.lines && prefill.lines.length) {
    if (window._renderOcrChips) window._renderOcrChips(prefill.lines);
  } else {
    const sect = $('#nbOcrChipsSection');
    if (sect) sect.style.display = 'none';
  }

  if (prefill.corrections) {
    if (prefill.corrections.author) {
      toast(`✨ Auteur corrigé d\'après la base : ${prefill.corrections.author.corrected}`, 'ok');
    }
    if (prefill.corrections.publisher) {
      toast(`✨ Éditeur corrigé d\'après la base : ${prefill.corrections.publisher.corrected}`, 'ok');
    }
  }

  triggerAllBddChecks();
  
  window.scrollTo(0, 0);
  updateViewportHeight();
  
  const m = $('#newBookModal');
  if (m) {
    m.hidden = false;
    m.style.removeProperty('display');
  }
  
  if (!prefill.lines || !prefill.lines.length) {
    setTimeout(() => {
      if (!$('#nbTitle').value) $('#nbTitle').focus();
      else if (!$('#nbPrice').value) $('#nbPrice').focus();
    }, 150);
  } else {
    if (document.activeElement && document.activeElement.blur) {
      document.activeElement.blur();
    }
  }
}

export function closeNewBookModal() {
  const m = $('#newBookModal');
  if (m) {
    m.hidden = true;
    m.style.setProperty('display', 'none', 'important');
  }
  state.pendingNewCode = null;
  const sect = $('#nbOcrChipsSection');
  if (sect) sect.style.display = 'none';
  const badge = $('#nbOcrBadge');
  if (badge) badge.style.display = 'none';
  hideExistingBookBanner();
  if (document.activeElement && document.activeElement.blur) {
    document.activeElement.blur();
  }
  window.scrollTo(0, 0);
  updateViewportHeight();
}

let titleCaseMode = 0;

export function initNewBookModal() {
  const nbBtnCloseTop = $('#nbBtnCloseTop');
  if (nbBtnCloseTop) {
    nbBtnCloseTop.addEventListener('click', closeNewBookModal);
  }

  const nbModalEl = $('#newBookModal');
  if (nbModalEl) {
    nbModalEl.addEventListener('click', e => {
      if (e.target === nbModalEl) closeNewBookModal();
    });
  }

  window.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      closeNewBookModal();
      closeMobileBookStats();
      closeMultiPayModal();
    }
  });

  const nbBtnCaseTitle = $('#nbBtnCaseTitle');
  if (nbBtnCaseTitle) {
    nbBtnCaseTitle.addEventListener('click', () => {
      const val = $('#nbTitle').value.trim();
      if (!val) return;
      titleCaseMode = (titleCaseMode + 1) % 2;
      if (titleCaseMode === 1) {
        $('#nbTitle').value = toTitleCase(val);
        toast('Titre formaté (Mots majuscules)', 'ok');
      } else {
        $('#nbTitle').value = toSentenceCase(val);
        toast('Titre formaté (Majuscule 1ère lettre)', 'ok');
      }
      triggerAllBddChecks();
    });
  }

  const nbBtnCaseAuthor = $('#nbBtnCaseAuthor');
  if (nbBtnCaseAuthor) {
    nbBtnCaseAuthor.addEventListener('click', () => {
      const val = $('#nbAuthor').value.trim();
      if (!val) return;
      $('#nbAuthor').value = toTitleCase(val);
      toast('Auteur formaté (Majuscules)', 'ok');
      triggerAllBddChecks();
    });
  }

  const bCancel = $('#btnCancelNewBook');
  if (bCancel) bCancel.addEventListener('click', closeNewBookModal);

  ['input', 'blur'].forEach(evt => {
    const codeInp = $('#nbCode');
    if (codeInp) codeInp.addEventListener(evt, () => checkCodeInCatalog(codeInp.value.trim()));

    const authInp = $('#nbAuthor');
    if (authInp) authInp.addEventListener(evt, () => checkFieldBdd('#nbAuthor', '#nbAuthorBddBadge', '#nbAuthorTypoSuggestion', state.dbAuthors));

    const pubInp = $('#nbPublisher');
    if (pubInp) pubInp.addEventListener(evt, () => checkFieldBdd('#nbPublisher', '#nbPublisherBddBadge', '#nbPublisherTypoSuggestion', state.dbPublishers));
  });

  const btnSave = $('#btnSaveNewBook');
  if (btnSave) {
    btnSave.addEventListener('click', async () => {
      const code = $('#nbCode').value.trim();
      const title = $('#nbTitle').value.trim();
      const author = $('#nbAuthor').value.trim();
      const publisher = $('#nbPublisher') ? $('#nbPublisher').value.trim() : null;
      const price = parseFloat($('#nbPrice').value) || 0;
      if (!title) return toast('Le titre est requis', 'warn');
      if (price <= 0) return toast('Indiquez un prix valide', 'warn');

      try {
        await api('/api/books', {
          method: 'POST',
          body: {
            code,
            title,
            author: author || null,
            publisher: publisher || null,
            price,
            category: 'Standard',
            min_stock: 2,
            is_pack: 0
          }
        });
        toast('Nouveau livre enregistré', 'ok');
        closeNewBookModal();
        const book = await api('/api/books/scan/' + encodeURIComponent(code));
        if (state.currentMode === 'sale') {
          addToCart(book);
        } else {
          addToRecv(book);
        }
      } catch (err) {
        toast(err.message, 'err');
      }
    });
  }
}
