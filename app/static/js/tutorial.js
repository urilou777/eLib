/* eLib – Visite guidée (overlay) : premier lancement automatique + bouton « ? Aide ».
   100 % local, sans dépendance. Ne modifie aucune donnée. */
(function () {
  'use strict';

  var KEY = 'librairie_tutorial_done_v2';

  var STEPS = [
    { title: 'Bienvenue dans eLib',
      text: "Cette visite vous montre les principaux écrans et où trouver les actions courantes. Elle ne modifie aucune donnée. Quittez-la avec Échap." },
    { view: 'dashboard', sel: '#dashTabSeg', pos: 'bottom', title: 'Lire le tableau de bord',
      text: "La Synthèse et le Studio présentent l’activité. Les filtres de période permettent de comparer les ventes et les stocks." },
    { view: 'pos', sel: '#q', pos: 'bottom', title: 'Trouver un livre',
      text: "Recherchez par titre ou saisissez un ISBN. Un lecteur de code-barres peut aussi remplir ce champ." },
    { view: 'pos', sel: '#items', pos: 'left', title: 'Composer le panier',
      text: "Ajoutez les livres, choisissez l’origine de chaque exemplaire et le mode de paiement. La vente n’est enregistrée qu’en appuyant sur Valider." },
    { view: 'stock', sel: '#newLot', pos: 'bottom', title: 'Réceptionner du stock',
      text: "Cette action ouvre un formulaire pour saisir le livre, l’origine, la quantité et la date. Les corrections de stock sont tracées depuis les lots." },
    { view: 'stock', sel: '#fs', pos: 'bottom', title: 'Surveiller les niveaux',
      text: "Filtrez les livres disponibles, en stock bas ou en rupture. Sélectionnez une ligne pour voir les lots et leur historique." },
    { view: 'catalog', sel: '#nb', pos: 'bottom', title: 'Gérer le catalogue',
      text: "Le catalogue sert à rechercher et modifier les fiches livres ou packs. Les boutons de création sont en haut de l’écran." },
    { view: 'sales', sel: '#view .table-wrap', pos: 'top', title: 'Consulter les ventes',
      text: "L’historique rassemble les ventes et leurs détails. L’annulation d’une vente restitue le stock : utilisez-la uniquement si nécessaire." },
    { view: 'treasury', sel: '#view .grid.g4', pos: 'bottom', title: 'Suivre la trésorerie',
      text: "Les indicateurs distinguent les espèces en caisse, les paiements à régulariser et les sommes à déposer. Les mouvements sont associés au libraire." },
    { view: 'audit', sel: '#bk', pos: 'bottom', title: 'Protéger les données',
      text: "Consultez les journaux et les sauvegardes ici. Créez un snapshot avant une opération importante ou une mise à jour." },
    { view: 'data', sel: '#view .card', pos: 'top', title: 'Données et Excel',
      text: "Retrouvez les outils d’import/export, les origines de stock et les listes personnalisables dans cette rubrique." },
    { sel: '#btnFocusMode', pos: 'bottom', title: 'Régie Live',
      text: "Pendant le culte, activez la Régie Live (F11) pour suivre en direct les scans et ventes des smartphones." },
    { sel: '#btnThemeToggle', pos: 'bottom', title: 'Thème',
      text: "Clair, sombre ou automatique (F10)." },
    { sel: null, title: "C'est parti !",
      text: "Revoyez cette visite à tout moment avec le bouton « ? Aide » en bas à droite." }
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
        '<div class="tut-count" id="tut-count"></div>' +
        '<h3 id="tut-title"></h3>' +
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
    b.title = 'Revoir la visite guidée';
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
