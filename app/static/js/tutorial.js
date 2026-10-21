/* eLib – Visite guidée avec Eli, le libraire-guide : premier lancement automatique + bouton « ? Aide ».
   100 % local, sans dépendance, sans image externe. Ne modifie aucune donnée. */
(function () {
  'use strict';

  var KEY = 'librairie_tutorial_done_v3';

  /* ---------- Eli : personnage SVG composable (aucun emoji, aucune image externe) ---------- */

  var P = {
    cardigan: '#5e2f7d', cardiganDark: '#3f1f57', shirt: '#f4ead9',
    skin: '#c68d5e', skinDark: '#a56f45', hair: '#241626',
    glass: '#e6a73c', dark: '#2a1830', blush: '#d98a66',
    book: '#ca88e3', gold: '#f5d27a', cream: '#faf7f2'
  };

  /* Yeux */
  function eyes(kind) {
    var L = 50, R = 70, y = 53;
    if (kind === 'happy') return '<path d="M' + (L - 6) + ' ' + y + ' Q' + L + ' ' + (y - 6) + ' ' + (L + 6) + ' ' + y + '" fill="none" stroke="' + P.dark + '" stroke-width="2.6" stroke-linecap="round"/>' +
      '<path d="M' + (R - 6) + ' ' + y + ' Q' + R + ' ' + (y - 6) + ' ' + (R + 6) + ' ' + y + '" fill="none" stroke="' + P.dark + '" stroke-width="2.6" stroke-linecap="round"/>';
    if (kind === 'wide') return '<circle cx="' + L + '" cy="' + y + '" r="4.6" fill="#fff"/><circle cx="' + L + '" cy="' + (y + 1) + '" r="2.2" fill="' + P.dark + '"/>' +
      '<circle cx="' + R + '" cy="' + y + '" r="4.6" fill="#fff"/><circle cx="' + R + '" cy="' + (y + 1) + '" r="2.2" fill="' + P.dark + '"/>';
    if (kind === 'wink') return '<path d="M' + (L - 6) + ' ' + y + ' Q' + L + ' ' + (y - 6) + ' ' + (L + 6) + ' ' + y + '" fill="none" stroke="' + P.dark + '" stroke-width="2.6" stroke-linecap="round"/>' +
      '<circle cx="' + R + '" cy="' + y + '" r="2.6" fill="' + P.dark + '"/>';
    if (kind === 'up') return '<circle cx="' + L + '" cy="' + (y + 1) + '" r="2.6" fill="' + P.dark + '"/><circle cx="' + R + '" cy="' + (y + 1) + '" r="2.6" fill="' + P.dark + '"/>' +
      '<path d="M' + (L - 6) + ' ' + (y + 3) + ' Q' + L + ' ' + (y - 7) + ' ' + (L + 6) + ' ' + (y + 3) + '" fill="none" stroke="' + P.dark + '" stroke-width="0"/>';
    return '<circle cx="' + L + '" cy="' + y + '" r="2.6" fill="' + P.dark + '"/><circle cx="' + R + '" cy="' + y + '" r="2.6" fill="' + P.dark + '"/>';
  }

  /* Sourcils */
  function brows(kind) {
    var a = 'stroke="' + P.hair + '" stroke-width="2.6" stroke-linecap="round" fill="none"';
    if (kind === 'raised') return '<path d="M43 42 Q50 38 57 41" ' + a + '/><path d="M63 41 Q70 38 77 42" ' + a + '/>';
    if (kind === 'knit') return '<path d="M43 40 L57 43" ' + a + '/><path d="M63 43 L77 40" ' + a + '/>';
    if (kind === 'one') return '<path d="M43 42 Q50 39 57 42" ' + a + '/><path d="M63 43 L77 41" ' + a + '/>';
    return '<path d="M44 41 L56 40.5" ' + a + '/><path d="M64 40.5 L76 41" ' + a + '/>';
  }

  /* Bouches */
  function mouth(kind) {
    var a = 'stroke="' + P.dark + '" stroke-width="2.4" stroke-linecap="round" fill="none"';
    if (kind === 'grin') return '<path d="M50 66 Q60 79 70 66 Q60 70 50 66 Z" fill="' + P.dark + '"/>';
    if (kind === 'o') return '<ellipse cx="60" cy="69" rx="3.4" ry="4" fill="' + P.dark + '"/>';
    if (kind === 'small') return '<path d="M55 68 L65 68" ' + a + '/>';
    if (kind === 'determined') return '<path d="M52 69 Q60 65 68 69" ' + a + '/>';
    if (kind === 'think') return '<path d="M53 68 Q60 72 67 67" ' + a + '/>';
    return '<path d="M52 66 Q60 73 68 66" ' + a + '/>';
  }

  /* Bras (droite du personnage = gauche visuelle inversée : on dessine côté fût simple) */
  function arm(side, x1, y1, x2, y2, bend) {
    var mx = (x1 + x2) / 2 + bend.x, my = (y1 + y2) / 2 + bend.y;
    return '<path d="M' + x1 + ' ' + y1 + ' Q' + mx + ' ' + my + ' ' + x2 + ' ' + y2 + '" fill="none" stroke="' + P.cardigan + '" stroke-width="9" stroke-linecap="round"/>' +
      '<circle cx="' + x2 + '" cy="' + y2 + '" r="5" fill="' + P.skin + '"/>';
  }

  /* Accessoires */
  function props(kind) {
    if (kind === 'book') return '<g><rect x="47" y="92" width="16" height="22" rx="2.5" fill="' + P.book + '"/><rect x="47" y="92" width="4" height="22" rx="2" fill="' + P.cardiganDark + '"/><path d="M54 96 L58 100 M54 102 L60 108" stroke="' + P.cream + '" stroke-width="1.4" stroke-linecap="round"/></g>';
    if (kind === 'stack') return '<g><rect x="42" y="108" width="36" height="9" rx="2" fill="' + P.gold + '"/><rect x="45" y="99" width="30" height="9" rx="2" fill="' + P.book + '"/><rect x="49" y="90" width="22" height="9" rx="2" fill="' + P.cream + '"/></g>';
    if (kind === 'shield') return '<g><path d="M66 88 L80 82 L94 88 Q94 104 80 110 Q66 104 66 88 Z" fill="' + P.cardigan + '" stroke="' + P.gold + '" stroke-width="2.5"/><path d="M74 94 L79 99 L88 90" fill="none" stroke="' + P.gold + '" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></g>';
    if (kind === 'coins') return '<g><circle cx="20" cy="88" r="4" fill="' + P.gold + '"/><circle cx="16" cy="78" r="4" fill="' + P.gold + '"/><circle cx="24" cy="72" r="4" fill="' + P.gold + '"/><path d="M10 60 l2 5 M14 58 l-1 4" stroke="' + P.gold + '" stroke-width="1.6" stroke-linecap="round"/></g>';
    if (kind === 'confetti') return '<g><rect x="14" y="18" width="5" height="5" rx="1" fill="' + P.gold + '" transform="rotate(20 16 20)"/><rect x="100" y="14" width="5" height="5" rx="1" fill="' + P.book + '" transform="rotate(-15 102 16)"/><circle cx="22" cy="46" r="2.4" fill="' + P.gold + '"/><circle cx="102" cy="44" r="2.4" fill="' + P.book + '"/><rect x="94" y="30" width="4" height="4" rx="1" fill="' + P.cream + '" transform="rotate(30 96 32)"/><circle cx="60" cy="12" r="2.2" fill="' + P.gold + '"/></g>';
    if (kind === 'motion') return '<g><path d="M20 70 q6 -6 4 -14 M102 74 q-6 -6 -4 -14" fill="none" stroke="' + P.gold + '" stroke-width="2.2" stroke-linecap="round" opacity="0.8"/></g>';
    return '';
  }

  /* Poses : combinaison yeux/sourcils/bouche/bras/accessoire, une par étape de la visite */
  var EMO = {
    wave:   { e: 'happy', b: 'raised', m: 'grin',  arms: [null, ['right', 98, 96, 102, 74, { x: 12, y: -6 }]], prop: '' },
    present:{ e: 'open',   b: 'flat',   m: 'smile', arms: [['left', 22, 100, 10, 96, { x: -2, y: -8 }], ['right', 98, 100, 92, 112, { x: 8, y: 2 }]], prop: '' },
    scan:   { e: 'wide',  b: 'raised', m: 'o',     arms: [['left', 22, 104, 26, 114, { x: -2, y: 4 }], ['right', 98, 98, 86, 46, { x: 12, y: 8 }]], prop: '' },
    hold:   { e: 'open',   b: 'flat',   m: 'smile', arms: [['left', 24, 100, 50, 112, { x: 2, y: -6 }], ['right', 96, 100, 72, 112, { x: -2, y: -6 }]], prop: 'book' },
    effort: { e: 'open',   b: 'knit',   m: 'determined', arms: [['left', 24, 100, 48, 116, { x: 0, y: 2 }], ['right', 96, 100, 74, 116, { x: 0, y: 2 }]], prop: 'stack' },
    alert:  { e: 'wide',  b: 'raised', m: 'small', arms: [['left', 22, 100, 14, 78, { x: -6, y: -8 }], ['right', 98, 104, 96, 116, { x: 6, y: 4 }]], prop: '' },
    point:  { e: 'open',   b: 'raised', m: 'smile', arms: [['left', 22, 104, 20, 116, { x: -4, y: 2 }], ['right', 98, 98, 108, 76, { x: 8, y: -4 }]], prop: '' },
    think:  { e: 'up',    b: 'one',     m: 'think', arms: [['left', 22, 104, 24, 116, { x: 0, y: 4 }], ['right', 96, 100, 74, 76, { x: 10, y: 2 }]], prop: '' },
    count:  { e: 'open',   b: 'one',     m: 'smile', arms: [['left', 22, 100, 18, 84, { x: -6, y: -6 }], ['right', 96, 104, 88, 116, { x: 4, y: 4 }]], prop: 'coins' },
    shield: { e: 'open',   b: 'flat',   m: 'small', arms: [['left', 24, 100, 64, 106, { x: 4, y: -6 }], ['right', 96, 104, 92, 116, { x: 4, y: 2 }]], prop: 'shield' },
    busy:   { e: 'happy', b: 'knit',   m: 'determined', arms: [['left', 24, 100, 46, 114, { x: 0, y: 0 }], ['right', 96, 100, 76, 114, { x: 0, y: 0 }]], prop: 'stack' },
    cheer:  { e: 'happy', b: 'raised', m: 'grin',  arms: [['left', 26, 96, 20, 68, { x: -8, y: -6 }], ['right', 94, 96, 100, 68, { x: 8, y: -6 }]], prop: 'motion' },
    wink:   { e: 'wink',  b: 'one',     m: 'smile', arms: [['left', 22, 104, 24, 116, { x: -2, y: 4 }], ['right', 98, 104, 92, 116, { x: 2, y: 2 }]], prop: '' },
    party:  { e: 'happy', b: 'raised', m: 'grin',  arms: [['left', 26, 96, 18, 66, { x: -8, y: -6 }], ['right', 94, 96, 102, 66, { x: 8, y: -6 }]], prop: 'confetti' }
  };

  /* Corps de base : bras arrière, torse, cou, tête, oreilles, cheveux, lunettes, joues */
  function guideSVG(emo) {
    var cfg = EMO[emo] || EMO.present;
    var arms = '';
    (cfg.arms || []).forEach(function (a) { if (a) arms += arm(a[0], a[1], a[2], a[3], a[4], a[5]); });
    var hair = '<g fill="' + P.hair + '">' +
      '<circle cx="44" cy="36" r="10"/><circle cx="53" cy="30" r="11"/><circle cx="63" cy="28" r="12"/><circle cx="73" cy="31" r="10"/>' +
      '<circle cx="80" cy="39" r="8"/><circle cx="40" cy="43" r="8"/><circle cx="37" cy="50" r="5"/><circle cx="83" cy="50" r="5"/></g>';
    var glasses = '<g fill="rgba(255,255,255,0.05)" stroke="' + P.glass + '" stroke-width="2.2">' +
      '<circle cx="50" cy="53" r="9"/><circle cx="70" cy="53" r="9"/></g>' +
      '<path d="M59 53 L61 53" stroke="' + P.glass + '" stroke-width="2.2"/><path d="M41 53 L35 50 M79 53 L85 50" stroke="' + P.glass + '" stroke-width="2.2" stroke-linecap="round"/>';
    var base =
      '<rect x="54" y="76" width="12" height="10" fill="' + P.skinDark + '"/>' +
      '<path d="M26 120 C26 96 40 86 60 86 C80 86 94 96 94 120 Z" fill="' + P.cardigan + '"/>' +
      '<path d="M47 86 L60 104 L73 86 Z" fill="' + P.shirt + '"/>' +
      '<path d="M47 86 L52 93 L56 87 Z M73 86 L68 93 L64 87 Z" fill="' + P.cardiganDark + '"/>' +
      '<circle cx="34" cy="58" r="4.5" fill="' + P.skin + '"/><circle cx="86" cy="58" r="4.5" fill="' + P.skin + '"/>' +
      '<circle cx="60" cy="54" r="26" fill="' + P.skin + '"/>' +
      hair +
      '<ellipse cx="44" cy="63" rx="4" ry="2.6" fill="' + P.blush + '" opacity="0.55"/>' +
      '<ellipse cx="76" cy="63" rx="4" ry="2.6" fill="' + P.blush + '" opacity="0.55"/>' +
      brows(cfg.b) + eyes(cfg.e) + glasses + mouth(cfg.m) + arms + props(cfg.prop);
    return '<svg viewBox="0 0 120 120" width="76" height="76" role="img" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg">' + base + '</svg>';
  }

  /* ---------- Étapes : chaque instruction a sa pose d'Eli ---------- */

  var STEPS = [
    { emo: 'wave', title: 'Bienvenue dans eLib',
      text: "Bonjour, je suis Eli ! Je vous fais visiter les principaux écrans. Rien ne sera modifié. Quittez avec Échap à tout moment." },
    { emo: 'present', view: 'dashboard', sel: '#dashTabSeg', pos: 'bottom', title: 'Lire le tableau de bord',
      text: "Voici la Synthèse et le Studio : l'activité d'un coup d'œil. Les filtres de période comparent ventes et stocks." },
    { emo: 'scan', view: 'pos', sel: '#q', pos: 'bottom', title: 'Trouver un livre',
      text: "Je scrute pour vous : tapez un titre ou un ISBN. Un lecteur de code-barres peut aussi remplir ce champ." },
    { emo: 'hold', view: 'pos', sel: '#items', pos: 'left', title: 'Composer le panier',
      text: "On rassemble les livres, on choisit l'origine de chaque exemplaire et le mode de paiement. Rien n'est enregistré avant « Valider »." },
    { emo: 'effort', view: 'stock', sel: '#newLot', pos: 'bottom', title: 'Réceptionner du stock',
      text: "Cette réception, je la porte à votre place : livre, origine, quantité, date. Les corrections passent par les lots et restent tracées." },
    { emo: 'alert', view: 'stock', sel: '#fs', pos: 'bottom', title: 'Surveiller les niveaux',
      text: "Restez vigilant ici : disponibles, stock bas, rupture. Sélectionnez une ligne pour voir les lots et leur historique." },
    { emo: 'point', view: 'catalog', sel: '#nb', pos: 'bottom', title: 'Gérer le catalogue',
      text: "Le catalogue, c'est votre rayonnage numérique : fiches livres et packs. Les boutons de création sont en haut de l'écran." },
    { emo: 'think', view: 'sales', sel: '#view .table-wrap', pos: 'top', title: 'Consulter les ventes',
      text: "Réfléchissez à deux fois ici : l'annulation d'une vente restitue le stock. À réserver aux vraies erreurs." },
    { emo: 'count', view: 'treasury', sel: '#view .grid.g4', pos: 'bottom', title: 'Suivre la trésorerie',
      text: "Chaque pièce compte : espèces en caisse, paiements à régulariser, sommes à déposer, associées au libraire." },
    { emo: 'shield', view: 'audit', sel: '#bk', pos: 'bottom', title: 'Protéger les données',
      text: "Ici je monte la garde : journaux et sauvegardes. Créez un snapshot avant toute opération importante ou mise à jour." },
    { emo: 'busy', view: 'data', sel: '#view .card', pos: 'top', title: 'Données et Excel',
      text: "La remise en ordre : imports/exports, origines de stock et listes personnalisables se trouvent dans cette rubrique." },
    { emo: 'cheer', sel: '#btnFocusMode', pos: 'bottom', title: 'Régie Live',
      text: "Le moment fort : pendant le culte, activez la Régie Live (F11) et suivez en direct les scans des smartphones !" },
    { emo: 'wink', sel: '#btnThemeToggle', pos: 'bottom', title: 'Thème',
      text: "Et une touche de style : clair, sombre ou automatique (F10), selon votre goût." },
    { emo: 'party', sel: null, title: "C'est parti !",
      text: "Vous êtes prêt ! Je reste disponible : cliquez sur « ? Aide » en bas à droite pour revoir cette visite." }
  ];

  var list = [], idx = 0, active = false, navigating = false, root = null;

  function $(id) { return document.getElementById(id); }

  function targetOf(step) {
    if (!step.sel) return null;
    var el = document.querySelector(step.sel);
    if (!el) return null;
    var r = el.getBoundingClientRect();
    return (r.width > 0 && r.height > 0) ? el : null;
  }

  async function showStep() {
    var step = list[idx];
    navigating = true;
    $('tut-prev').disabled = true;
    $('tut-next').disabled = true;
    $('tut-skip').disabled = true;
    place();
    try {
      if (step.view && typeof window.navigateToView === 'function') {
        await window.navigateToView(step.view);
      }
      place();
    } finally {
      navigating = false;
      if (root) {
        $('tut-prev').disabled = idx === 0;
        $('tut-next').disabled = false;
        $('tut-skip').disabled = false;
      }
    }
  }

  function build() {
    root = document.createElement('div');
    root.id = 'tut-root';
    root.innerHTML =
      '<div class="tut-block"></div>' +
      '<div class="tut-spot" id="tut-spot" style="display:none"></div>' +
      '<div class="tut-card" id="tut-card" role="dialog" aria-modal="true" aria-labelledby="tut-title">' +
        '<div class="tut-head">' +
          '<div class="tut-guide-wrap"><div class="tut-guide" id="tut-guide"></div><div class="tut-name">Eli</div></div>' +
          '<div class="tut-headtext">' +
            '<div class="tut-count" id="tut-count"></div>' +
            '<h3 id="tut-title"></h3>' +
          '</div>' +
        '</div>' +
        '<p id="tut-text"></p>' +
        '<div class="tut-actions">' +
          '<button type="button" class="tut-skip" id="tut-skip">Passer</button>' +
          '<span class="tut-spacer"></span>' +
          '<button type="button" class="tut-btn" id="tut-prev">Précédent</button>' +
          '<button type="button" class="tut-btn tut-primary" id="tut-next">Suivant</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(root);
    $('tut-skip').onclick = function () { finish(true); };
    $('tut-prev').onclick = function () { prev(); };
    $('tut-next').onclick = function () { next(); };
    document.addEventListener('keydown', onKey, true);
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
  }

  function place() {
    if (!root) return;
    var s = list[idx];
    var target = targetOf(s);
    var card = $('tut-card'), spot = $('tut-spot');

    $('tut-title').textContent = s.title;
    $('tut-text').textContent = s.text;
    $('tut-count').textContent = (idx + 1) + ' / ' + list.length;
    $('tut-prev').style.visibility = idx === 0 ? 'hidden' : 'visible';
    $('tut-next').textContent = idx === list.length - 1 ? 'Terminer' : 'Suivant';

    /* Eli change de pose à chaque étape, avec une petite entrée vivante */
    var g = $('tut-guide');
    g.innerHTML = guideSVG(s.emo);
    g.classList.remove('tut-pop');
    void g.offsetWidth;
    g.classList.add('tut-pop');

    if (!target) {
      root.classList.add('tut-nospot');
      spot.style.display = 'none';
      card.classList.add('tut-center');
      card.style.left = '';
      card.style.top = '';
      return;
    }

    root.classList.remove('tut-nospot');
    card.classList.remove('tut-center');
    spot.style.display = 'block';

    var r = target.getBoundingClientRect(), pad = 6;
    spot.style.left = (r.left - pad) + 'px';
    spot.style.top = (r.top - pad) + 'px';
    spot.style.width = (r.width + pad * 2) + 'px';
    spot.style.height = (r.height + pad * 2) + 'px';

    var cw = card.offsetWidth, ch = card.offsetHeight;
    var vw = window.innerWidth, vh = window.innerHeight;
    var left, top;
    if (s.pos === 'right') {
      left = r.right + 18;
      top = r.top + r.height / 2 - ch / 2;
    } else if (s.pos === 'left') {
      left = r.left - cw - 18;
      top = r.top + r.height / 2 - ch / 2;
      if (left < 12) left = r.right + 18;
    } else {
      left = r.left + r.width / 2 - cw / 2;
      top = r.bottom + 18;
      if (top + ch > vh) top = r.top - ch - 18;
    }
    left = Math.max(12, Math.min(left, vw - cw - 12));
    top = Math.max(12, Math.min(top, vh - ch - 12));
    card.style.left = left + 'px';
    card.style.top = top + 'px';
  }

  async function next() {
    if (navigating) return;
    if (idx >= list.length - 1) return finish(true);
    idx++;
    await showStep();
  }

  async function prev() {
    if (navigating) return;
    if (idx > 0) { idx--; await showStep(); }
  }

  function onKey(e) {
    if (!active) return;
    if (e.key === 'Escape') { e.preventDefault(); finish(true); }
    else if (e.key === 'ArrowRight' || e.key === 'Enter') { e.preventDefault(); if (!navigating) next(); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); if (!navigating) prev(); }
    else if (e.key === 'Tab') { e.stopPropagation(); }
  }

  function finish(markDone) {
    if (markDone) {
      try { localStorage.setItem(KEY, '1'); } catch (e) { /* stockage indisponible : sans gravité */ }
    }
    active = false;
    document.removeEventListener('keydown', onKey, true);
    window.removeEventListener('resize', place);
    window.removeEventListener('scroll', place, true);
    if (root) { root.remove(); root = null; }
  }

  function start() {
    if (active) return;
    list = STEPS.slice();
    active = true;
    idx = 0;
    build();
    showStep();
  }

  function addHelpButton() {
    var b = document.createElement('button');
    b.id = 'tut-help-btn';
    b.type = 'button';
    b.textContent = '? Aide';
    b.title = 'Revoir la visite guidée avec Eli';
    b.onclick = start;
    document.body.appendChild(b);
  }

  function boot() {
    addHelpButton();
    var done = false;
    try { done = localStorage.getItem(KEY) === '1'; } catch (e) { done = false; }
    if (!done) setTimeout(start, 800);
  }

  // API publique (utile pour un réglage ou un test) : window.eLibTutorial.start()
  window.eLibTutorial = {
    start: start,
    reset: function () { try { localStorage.removeItem(KEY); } catch (e) { } }
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
