/* Librairie – interface (vanilla JS, 100 % hors-ligne) */
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const eur = n => (Number(n) || 0).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
const nf = n => (Number(n) || 0).toLocaleString('fr-FR');
const today = () => new Date().toISOString().slice(0, 10);
const MONTHS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
const mlabel = m => MONTHS[+m.slice(5) - 1] + ' ' + m.slice(2, 4);

/* ---------- gestion utilisateur actif ---------- */
function getCurrentUser() {
  return localStorage.getItem('librairie_user') || 'Responsable';
}
function setCurrentUser(name) {
  localStorage.setItem('librairie_user', name);
  updateUserDisplay();
}
function updateUserDisplay() {
  const u = getCurrentUser();
  const el = $('#userNameDisplay');
  if (el) el.textContent = u;
}

async function api(url, method = 'GET', body) {
  const o = { method, headers: { 'X-User': encodeURIComponent(getCurrentUser()) } };
  if (body instanceof FormData) o.body = body;
  else if (body !== undefined) { o.headers['Content-Type'] = 'application/json'; o.body = JSON.stringify(body); }
  const r = await fetch(url, o);
  if (!r.ok) { let d = r.statusText; try { d = (await r.json()).detail || d } catch (e) { } throw new Error(typeof d === 'string' ? d : JSON.stringify(d)); }
  return r.json();
}
function toast(msg, kind = 'ok') {
  const t = document.createElement('div'); t.className = 'toast ' + kind; t.textContent = msg;
  $('#toasts').appendChild(t); setTimeout(() => t.remove(), kind === 'err' ? 6000 : 3200);
}
const safe = fn => async (...a) => { try { return await fn(...a) } catch (e) { toast(e.message, 'err') } };

/* ---------- modal ---------- */
function modal(html, onMount) {
  const root = $('#modalRoot');
  root.innerHTML = `<div class="ov"><div class="modal">${html}</div></div>`;
  const ov = $('.ov', root);
  ov.addEventListener('mousedown', e => { if (e.target === ov) closeModal(); });
  onMount && onMount($('.modal', root));
}
const closeModal = () => $('#modalRoot').innerHTML = '';
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

/* ---------- état ---------- */
const S = { books: [], owners: [], options: { category: [], type: [], payment: [], publisher: [] }, cart: [], view: 'dashboard', range: 'all', from: '', to: '' };
const stockBadge = b => b.stock <= 0 ? '<span class="badge b-out">Rupture</span>' :
  b.stock <= b.min_stock ? `<span class="badge b-low">${b.stock} · bas</span>` : `<span class="badge b-ok">${b.stock}</span>`;
const ownerChips = b => (b.by_owner || []).map(o => `<span class="chip"><i style="background:${o.color}"></i>${esc(o.owner)} ${o.qty}</span>`).join('');

async function loadRef() { 
  [S.books, S.owners, S.options] = await Promise.all([api('/api/books'), api('/api/owners'), api('/api/options')]); 
}

/* ---------- Mode Focus (poste sécurisé non spécifique à une session) ---------- */
function isFocusMode() {
  return localStorage.getItem('librairie_focus_mode') === 'true';
}

function updateFocusUI() {
  const active = isFocusMode();
  document.body.classList.toggle('focus-mode-on', active);
  const btn = $('#btnFocusMode');
  const banner = $('#focusBanner');
  const label = $('#focusBtnLabel');
  if (btn) {
    btn.classList.toggle('focus-active', active);
    if (active) {
      btn.title = "Mode Focus ACTIF. Cliquez pour déverrouiller et revenir au mode complet.";
      if (label) label.textContent = "Quitter Focus";
    } else {
      btn.title = "Activer le Mode Focus (sécurise le poste, restreint aux opérations de vente/caisse)";
      if (label) label.textContent = "Mode Focus";
    }
  }
  if (banner) {
    banner.style.display = active ? 'inline-flex' : 'none';
  }
}

function toggleFocusMode() {
  const current = isFocusMode();
  if (current) {
    if (confirm("Désactiver le Mode Focus et réactiver l'accès complet à tous les onglets d'administration ?")) {
      localStorage.setItem('librairie_focus_mode', 'false');
      updateFocusUI();
      toast("Mode Focus désactivé : accès complet rétabli", "ok");
    }
  } else {
    localStorage.setItem('librairie_focus_mode', 'true');
    updateFocusUI();
    toast("Mode Focus activé : poste restreint aux opérations de caisse", "ok");
    if (S.view !== 'pos') {
      go('pos');
    }
  }
}

/* ---------- navigation ---------- */
const TITLES = { dashboard: 'Tableau de bord', pos: 'Caisse', stock: 'Stock', catalog: 'Catalogue & packs', sales: 'Historique des ventes', treasury: 'Trésorerie & Caisse', settle: 'Trésorerie & Caisse', orders: 'Réservations', audit: 'Historique & Sécurité des opérations', data: 'Données & Excel' };
async function go(v) {
  if (isFocusMode() && v !== 'pos') {
    toast("Accès bloqué : navigation verrouillée sur la Caisse uniquement.", "err");
    return;
  }
  S.view = v; $('#title').textContent = TITLES[v]; $('#topActions').innerHTML = ''; $('#view').onclick = null;
  document.querySelectorAll('#nav a').forEach(a => a.classList.toggle('on', a.dataset.v === v));
  $('#view').innerHTML = '<div class="empty">Chargement…</div>';
  try { await loadRef(); await VIEWS[v](); } catch (e) { toast(e.message, 'err'); }
}
$('#nav').addEventListener('click', e => { 
  if (isFocusMode()) {
    toast("Mode Focus actif : seul l'écran de Caisse est accessible.", "warn");
    return;
  }
  const a = e.target.closest('a'); 
  if (a) go(a.dataset.v); 
});

/* ---------- graphiques SVG ---------- */
function niceMax(v) { if (v <= 0) return 10; const p = Math.pow(10, Math.floor(Math.log10(v))); return Math.ceil(v / p * 2) / 2 * p; }
function trendChart(el, monthly, fc, ownerMonth) {
  const months = monthly.map(m => m.month || m.m);
  if (!months.length) { el.innerHTML = '<div class="empty">Aucune vente sur la période</div>'; return; }
  const last = months[months.length - 1]; const fut = [];
  let [y, mo] = last.split('-').map(Number);
  for (let i = 0; i < fc.length; i++) { mo++; if (mo > 12) { mo = 1; y++ } fut.push(`${y}-${String(mo).padStart(2, '0')}`); }
  const all = months.concat(fut); const W = 760, H = 280, L = 52, B = 30, T = 14, R = 12;
  const owners = {}; ownerMonth.forEach(r => { (owners[r.owner] ??= { color: r.color, v: {} }).v[r.m] = r.revenue });
  const names = Object.keys(owners);
  const totals = months.map(m => names.reduce((s, n) => s + (owners[n].v[m] || 0), 0));
  const max = niceMax(Math.max(...totals, ...fc));
  const bw = (W - L - R) / all.length, X = i => L + i * bw, Y = v => T + (H - T - B) * (1 - v / max);
  let s = `<svg viewBox="0 0 ${W} ${H}" class="chart" preserveAspectRatio="none">`;
  for (let i = 0; i <= 4; i++) { 
    const v = max * i / 4, y = Y(v); 
    s += `<line x1="${L}" x2="${W - R}" y1="${y}" y2="${y}" class="chart-grid-line"/><text x="${L - 8}" y="${y + 4}" text-anchor="end" class="chart-axis-text">${Math.round(v)}</text>`; 
  }
  months.forEach((m, i) => {
    let acc = 0;
    names.forEach(n => {
      const v = owners[n].v[m] || 0, h = (H - T - B) * v / max; acc += v;
      s += `<rect x="${X(i) + bw * .18}" y="${Y(acc)}" width="${bw * .64}" height="${h}" rx="3" fill="${owners[n].color}" opacity=".88"><title>${mlabel(m)} · ${n} : ${eur(v)}</title></rect>`;
    });
  });
  fut.forEach((m, i) => { 
    const idx = months.length + i; 
    s += `<rect x="${X(idx) + bw * .18}" y="${Y(fc[i])}" width="${bw * .64}" height="${(H - T - B) * fc[i] / max}" rx="3" fill="none" class="chart-forecast-bar" stroke-dasharray="4 3"><title>Prévision ${mlabel(m)} : ${eur(fc[i])}</title></rect>`; 
  });
  // moyenne mobile 3 mois
  const ma = totals.map((_, i) => { const sl = totals.slice(Math.max(0, i - 2), i + 1); return sl.reduce((a, b) => a + b, 0) / sl.length });
  s += `<polyline fill="none" class="chart-trend-line" stroke-width="2.5" stroke-linecap="round" points="${ma.map((v, i) => `${X(i) + bw / 2},${Y(v)}`).join(' ')}"/>`;
  ma.forEach((v, i) => s += `<circle cx="${X(i) + bw / 2}" cy="${Y(v)}" r="3.5" class="chart-trend-dot"/>`);
  all.forEach((m, i) => { if (all.length < 14 || i % 2 === 0) s += `<text x="${X(i) + bw / 2}" y="${H - 8}" text-anchor="middle" class="chart-axis-text">${mlabel(m)}</text>`; });
  el.innerHTML = s + '</svg>' + `<div class="legend">${names.map(n => `<span><i style="background:${owners[n].color}"></i>${esc(n)}</span>`).join('')}<span><i class="legend-trend-icon"></i>Tendance (moy. mobile 3 m.)</span><span><i class="legend-forecast-icon"></i>Prévision</span></div>`;
}
function donut(el, data, fmt = eur) {
  const tot = data.reduce((s, d) => s + d.value, 0); if (!tot) { el.innerHTML = '<div class="empty">—</div>'; return; }
  let a = -Math.PI / 2, s = '<svg viewBox="-105 -105 210 210" class="donut-svg">';
  data.forEach(d => {
    const ang = d.value / tot * Math.PI * 2, r = 92, x1 = r * Math.cos(a), y1 = r * Math.sin(a); a += ang;
    const x2 = r * Math.cos(a), y2 = r * Math.sin(a), big = ang > Math.PI ? 1 : 0;
    if (d.value / tot > .999) s += `<circle r="${r}" fill="none" stroke="${d.color}" stroke-width="25"/>`;
    else s += `<path d="M${x1} ${y1} A${r} ${r} 0 ${big} 1 ${x2} ${y2}" fill="none" stroke="${d.color}" stroke-width="25"><title>${esc(d.label)} : ${fmt(d.value)}</title></path>`;
  });
  s += `<text text-anchor="middle" y="-2" class="donut-total-val" style="font-size:23px;font-weight:800">${fmt(tot)}</text><text text-anchor="middle" y="16" class="donut-sub-text">total</text></svg>`;
  el.innerHTML = `<div class="donut-wrap">${s}<div class="legend" style="justify-content:center">${data.map(d => `<span><i style="background:${d.color}"></i>${esc(d.label)} · ${Math.round(d.value / tot * 100)}%</span>`).join('')}</div></div>`;
}
function hbars(el, rows, key = 'revenue', fmt = eur, sub) {
  if (!rows.length) { el.innerHTML = '<div class="empty">—</div>'; return; }
  const max = Math.max(...rows.map(r => r[key])) || 1;
  el.innerHTML = rows.map(r => `<div class="hbar"><span class="t" title="${esc(r.label || r.title)}">${esc(r.label || r.title)}</span><div class="tr"><div class="fl" style="width:${r[key] / max * 100}%"></div></div><b>${fmt(r[key])}${sub ? ` <span class="muted" style="font-weight:400">${sub(r)}</span>` : ''}</b></div>`).join('');
}
const PALETTE = ['#8f16ad', '#b452d3', '#ca88e3', '#e2c0f2', '#e6a73c', '#38c172', '#e04565'];

/* ================= VUES ================= */
const VIEWS = {};

/* ---- Tableau de bord ---- */
VIEWS.dashboard = async () => {
  const now = new Date(), y = now.getFullYear(), ms = `${y}-${String(now.getMonth() + 1).padStart(2, '0')}-01`;
  const d30 = new Date(Date.now() - 30 * 864e5).toISOString().slice(0, 10);
  const ranges = { all: ['', ''], '30': [d30, ''], month: [ms, ''], year: [`${y}-01-01`, ''], custom: [S.from, S.to] };
  const [from, to] = ranges[S.range];
  const st = await api(`/api/stats?start=${from}&end=${to}`);
  const k = st.kpi;
  $('#topActions').innerHTML = `<div class="row"><div class="seg" id="seg">${[['all', 'Tout'], ['year', 'Année'], ['month', 'Ce mois'], ['30', '30 jours']].map(([v, l]) => `<button data-r="${v}" class="${S.range === v ? 'on' : ''}">${l}</button>`).join('')}</div>
    <input type="date" id="dFrom" value="${S.from}"><input type="date" id="dTo" value="${S.to}"></div>`;
  $('#seg').onclick = e => { if (e.target.dataset.r) { S.range = e.target.dataset.r; VIEWS.dashboard() } };
  $('#dFrom').onchange = $('#dTo').onchange = () => { S.from = $('#dFrom').value; S.to = $('#dTo').value; S.range = 'custom'; VIEWS.dashboard() };
  const kp = [
    ['Chiffre d\'affaires', eur(k.revenue), `${nf(k.qty)} exemplaires`, '#7c5cff'],
    ['Marge conservée', eur(k.margin), k.revenue ? Math.round(k.margin / k.revenue * 100) + ' % du CA' : '', '#27d3c3'],
    ['Prix moyen / livre', eur(k.avg_book_price), k.pos_sales ? `Panier caisse ${eur(k.pos_avg_basket)} (${k.pos_sales} ticket${k.pos_sales > 1 ? 's' : ''})` : `${nf(k.qty)} livres vendus`, '#5a9bff'],
    ['À reverser', eur(k.due_open), 'reste à régler (global)', '#ffb454'],
    ['Valeur du stock', eur(k.stock_value), `${nf(k.stock_units)} exemplaires`, '#c77dff']
  ];
  $('#view').innerHTML = `<div class="grid g-kpi">${kp.map((x, i) => `<div class="card kpi" style="--c:${x[3]};animation-delay:${i * 60}ms"><div class="l">${x[0]}</div><div class="v">${x[1]}</div><div class="s">${x[2]}</div></div>`).join('')}</div>
  <div class="grid g2" style="margin-bottom:16px"><div class="card card-fill"><h3>Évolution mensuelle du CA par origine · tendance & prévision</h3><div id="cTrend"></div></div>
    <div class="card card-fill"><h3>Répartition par origine du stock</h3><div id="cOwner"></div></div></div>
  <div class="grid g3" style="margin-bottom:16px"><div class="card"><h3>Top 10 des ventes</h3><div id="cTop"></div></div>
    <div class="card"><h3>Par catégorie</h3><div id="cCat"></div><h3 style="margin-top:22px">Par éditeur</h3><div id="cPub"></div></div>
    <div class="card"><h3>Jours de la semaine</h3><div id="cWd"></div><h3 style="margin-top:22px">Moyens de paiement</h3><div id="cPay"></div></div></div>
  <div class="grid g3" style="margin-bottom:16px">
    <div class="card"><h3>Profil acheteurs · Tranche d'âge</h3><div id="cAge"></div></div>
    <div class="card"><h3>Profil acheteurs · Genre</h3><div id="cGen"></div></div>
    <div class="card"><h3>Engagement · Serviteurs STAR ⭐</h3><div id="cStar"></div></div>
  </div>
  <div class="card"><h3>Alertes de stock bas (${st.low_stock.length})</h3><div class="table-wrap" style="max-height:clamp(200px, 34vh, 420px)"><table><thead><tr><th>Titre</th><th>Origine</th><th class="num">Stock</th><th class="num">Seuil</th><th class="num">Autonomie estimée</th></tr></thead><tbody>
  ${st.low_stock.map(b => `<tr><td>${esc(b.title)} ${b.volume ? `<span class="muted">Vol. ${esc(b.volume)}</span>` : ''}</td><td>${ownerChips(b)}</td><td class="num">${stockBadge(b)}</td><td class="num">${b.min_stock}</td><td class="num">${b.days_left == null ? '<span class="muted">pas de ventes récentes</span>' : b.days_left + ' j'}</td></tr>`).join('') || '<tr><td colspan=5 class="muted">Stock optimal sur l\'ensemble des titres.</td></tr>'}</tbody></table></div></div>`;
  trendChart($('#cTrend'), st.monthly, st.forecast, st.by_owner_month);
  donut($('#cOwner'), st.by_owner.map((o, i) => ({ label: o.label, value: o.revenue, color: o.color })));
  hbars($('#cTop'), st.top, 'qty', nf, r => eur(r.revenue));
  hbars($('#cCat'), st.by_category); hbars($('#cPub'), st.by_publisher.slice(0, 6));
  const days = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam']; const wd = {}; st.weekday.forEach(w => wd[w.d] = w.revenue);
  hbars($('#cWd'), [0, 1, 2, 3, 4, 5, 6].map(d => ({ label: days[d], revenue: wd[d] || 0 })));
  hbars($('#cPay'), st.payments.map(p => ({ label: p.label, n: p.n })), 'n', nf);
  hbars($('#cAge'), (st.by_age || []).map(a => ({ label: a.label, revenue: a.revenue, n: a.n })), 'revenue', eur, r => `${r.n} ticket${r.n > 1 ? 's' : ''}`);
  hbars($('#cGen'), (st.by_gender || []).map(g => ({ label: g.label, revenue: g.revenue, n: g.n })), 'revenue', eur, r => `${r.n} ticket${r.n > 1 ? 's' : ''}`);
  hbars($('#cStar'), (st.by_star || []).map(s => ({ label: s.label, revenue: s.revenue, n: s.n })), 'revenue', eur, r => `${r.n} ticket${r.n > 1 ? 's' : ''}`);
};

/* ---- Caisse ---- */
VIEWS.pos = async () => {
  const info = await api('/api/info');
  $('#topActions').innerHTML = `
    <button class="btn ghost" id="btnMobileQr" style="display:flex;align-items:center;gap:6px">
      <svg class="ico sm" viewBox="0 0 24 24"><rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg>
      Scanner mobile
    </button>
  `;
  const btnQr = $('#btnMobileQr');
  if (btnQr) {
    btnQr.onclick = async () => {
      try {
        const minfo = await api('/api/mobile/info');
        if (!minfo.enabled) {
          modal(`
            <h2>Scanner Mobile non activé</h2>
            <p class="muted" style="margin-bottom:14px;font-size:13px;line-height:1.6">
              Le service HTTPS mobile n'est pas encore démarré.<br>
              Veuillez lancer <b>Installer_Mobile.bat</b> pour configurer le certificat et le pare-feu, puis redémarrer l'application.
            </p>
            <div class="actions">
              <button class="btn ghost" onclick="closeModal()">Fermer</button>
            </div>
          `);
          return;
        }

        const renderModalContent = (pairingUrl = null) => {
          const devList = (minfo.devices || []).map(d => `
            <div class="row" style="justify-content:space-between;padding:6px 10px;background:var(--panel2);border-radius:6px;margin-bottom:6px;font-size:12px">
              <div>
                <b>${esc(d.name || 'Téléphone')}</b> 
                <span class="muted">(vu ${esc(d.last_seen ? d.last_seen.slice(0, 16) : d.created_at ? d.created_at.slice(0, 10) : 'jamais')})</span>
              </div>
              <button class="btn ghost sm" style="color:var(--bad)" onclick="revokeDevice('${esc(d.id)}')">Révoquer</button>
            </div>
          `).join('') || '<div class="muted" style="font-size:12px;font-style:italic">Aucun smartphone appairé pour le moment.</div>';

          return `
            <h2><svg class="ico" viewBox="0 0 24 24"><rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg> Connexion Scanner Mobile</h2>
            <p class="muted" style="margin-bottom:12px;font-size:13px;line-height:1.5">
              Scannez ce QR code avec l'appareil photo du smartphone du libraire.<br>
              <b>Important :</b> Le téléphone et le PC doivent être sur le même Wi-Fi.
            </p>

            <div style="text-align:center;padding:12px;background:#fff;border-radius:12px;display:inline-block;margin:0 auto">
              ${pairingUrl ? `
                <img src="/api/qr?data=${encodeURIComponent(pairingUrl)}" alt="QR Code" style="display:block;width:clamp(160px, 28vw, 220px);height:clamp(160px, 28vw, 220px);margin:0 auto">
              ` : `
                <div style="width:clamp(160px, 28vw, 220px);height:clamp(160px, 28vw, 220px);display:flex;align-items:center;justify-content:center;color:#666;margin:0 auto">
                  <button class="btn good sm" id="btnGenPair">Générer le QR Code (5 min)</button>
                </div>
              `}
            </div>

            ${pairingUrl ? `
              <div style="margin-top:10px;text-align:center">
                <button class="btn ghost sm" id="btnGenPair"><svg class="ico sm" viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> Régénérer un nouveau QR Code</button>
              </div>
            ` : ''}

            <details style="margin-top:16px;text-align:left;background:var(--panel2);padding:10px 14px;border-radius:8px;font-size:12px">
              <summary style="cursor:pointer;font-weight:600"><svg class="ico sm" viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg> Certificat de sécurité (requis pour la caméra)</summary>
              <p style="margin:8px 0;line-height:1.5">
                Sur Android/iPhone, la caméra nécessite une connexion sécurisée. 
                Si votre navigateur affiche une alerte de sécurité :
              </p>
              <ol style="margin-left:18px;line-height:1.5">
                <li>Téléchargez et installez l'autorité racine : <a href="/api/ca.crt" download="Librairie-CA.crt" style="color:var(--a2);font-weight:bold">Télécharger Librairie-CA.crt</a></li>
                <li>Ou cliquez simplement sur <i>"Paramètres avancés" &gt; "Continuer vers le site"</i> sur votre téléphone.</li>
              </ol>
              <div style="margin-top:6px;font-family:monospace;font-size:11px;color:var(--muted)">
                Empreinte SHA-256 : ${esc(minfo.ca_fingerprint || 'Non disponible')}
              </div>
            </details>

            <div style="margin-top:16px;text-align:left">
              <h4 style="margin:0 0 8px 0;font-size:13px">Appareils autorisés</h4>
              ${devList}
            </div>

            <div class="actions" style="margin-top:18px">
              <button class="btn ghost" onclick="closeModal()">Fermer</button>
            </div>
          `;
        };

        window.revokeDevice = async (did) => {
          if (!confirm("Révoquer cet appareil ? Le smartphone devra être ré-appairé.")) return;
          try {
            await api('/api/mobile/devices/' + did, 'DELETE');
            closeModal();
            btnQr.click();
          } catch (e) {
            toast(e.message, 'err');
          }
        };

        const show = async (pairingUrl = null) => {
          modal(renderModalContent(pairingUrl));
          const btn = $('#btnGenPair');
          if (btn) {
            btn.onclick = async () => {
              try {
                btn.disabled = true;
                btn.textContent = 'Génération...';
                const res = await api('/api/mobile/pairing', 'POST');
                show(res.url);
              } catch (e) {
                toast(e.message, 'err');
                btn.disabled = false;
                btn.textContent = 'Générer le QR Code (5 min)';
              }
            };
          }
        };

        // Génération immédiate par défaut
        try {
          const res = await api('/api/mobile/pairing', 'POST');
          show(res.url);
        } catch (e) {
          show(null);
        }

      } catch (err) {
        modal(`<h2>Erreur</h2><p class="muted">${esc(err.message)}</p><div class="actions"><button class="btn ghost" onclick="closeModal()">Fermer</button></div>`);
      }
    };
  }

  $('#view').innerHTML = `<div class="pos"><div class="pos-l"><div class="toolbar"><input class="search" id="q" placeholder="Rechercher un titre, ou scanner / saisir un code ISBN puis Entrée…" autofocus>
    <select id="fOwner"><option value="">Toutes origines</option>${S.owners.map(o => `<option>${esc(o.name)}</option>`).join('')}</select><label class="row muted"><input type="checkbox" id="inStock" checked> En stock</label></div>
    <div class="books" id="books"></div></div>
    <div class="card cart" id="cart"><h3>Panier <button class="btn ghost sm" id="clear">Vider</button></h3><div class="cart-items" id="items"></div>
    <div class="total"><span>Total</span><b id="tot">0 €</b></div>
    <div class="row" style="margin-bottom:8px"><select id="pay" style="flex:1">${(S.options.payment || []).map(p => `<option>${esc(p.label)}</option>`).join('') || '<option>Espèces</option>'}</select><input type="date" id="sdate" value="${today()}"></div>
    
    <div class="card" style="padding:10px;margin-bottom:10px;background:var(--panel2);border:1px solid var(--line)">
      <div class="row" style="justify-content:space-between;margin-bottom:6px">
        <span style="font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:0.5px;font-weight:700">Profil client (statistique)</span>
        <button type="button" class="btn sm ghost demo-btn" id="btnStar" data-star="0" style="padding:2px 8px!important;font-weight:700">⭐ Serviteur STAR</button>
      </div>
      <div class="row" style="gap:6px;margin-bottom:6px" id="demoGender">
        <button type="button" class="btn sm ghost demo-btn on" data-g="">Indéfini</button>
        <button type="button" class="btn sm ghost demo-btn" data-g="Femme">Femme</button>
        <button type="button" class="btn sm ghost demo-btn" data-g="Homme">Homme</button>
      </div>
      <div class="row" style="gap:6px" id="demoAge">
        <button type="button" class="btn sm ghost demo-btn on" data-a="">Indéfini</button>
        <button type="button" class="btn sm ghost demo-btn" data-a="Enfant / Ado">Ado (&lt;18)</button>
        <button type="button" class="btn sm ghost demo-btn" data-a="Jeune adulte">18-29</button>
        <button type="button" class="btn sm ghost demo-btn" data-a="Adulte">30-59</button>
        <button type="button" class="btn sm ghost demo-btn" data-a="Senior">60+</button>
      </div>
    </div>

    <button class="btn good" id="valid" style="padding:13px;font-size:15px"><svg class="ico sm" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg> Valider la vente <span class="kbd-hint" style="margin-left:8px;background:rgba(0,0,0,0.2);border-color:rgba(255,255,255,0.3);color:#fff">F12</span></button></div></div>`;
  
  let curGender = '';
  let curAge = '';
  let curStar = 0;
  const btnStar = $('#btnStar');
  if (btnStar) {
    btnStar.onclick = () => {
      curStar = curStar ? 0 : 1;
      btnStar.classList.toggle('on', !!curStar);
      btnStar.style.background = curStar ? '#e6a73c' : '';
      btnStar.style.borderColor = curStar ? '#e6a73c' : '';
      btnStar.style.color = curStar ? '#000' : '';
    };
  }
  $('#demoGender').onclick = e => {
    const b = e.target.closest('button[data-g]');
    if (b) {
      $('#demoGender').querySelectorAll('button').forEach(btn => btn.classList.toggle('on', btn === b));
      curGender = b.dataset.g;
    }
  };
  $('#demoAge').onclick = e => {
    const b = e.target.closest('button[data-a]');
    if (b) {
      $('#demoAge').querySelectorAll('button').forEach(btn => btn.classList.toggle('on', btn === b));
      curAge = b.dataset.a;
    }
  };
  const draw = () => {
    const q = $('#q').value.trim().toLowerCase(), ow = $('#fOwner').value, ins = $('#inStock').checked;
    const list = S.books.filter(b => (!q || (b.title + ' ' + (b.series || '') + ' ' + b.code + ' ' + (b.author || '')).toLowerCase().includes(q))
      && (!ins || b.stock > 0) && (!ow || (b.by_owner || []).some(o => o.owner === ow)));
    $('#books').innerHTML = list.map(b => `<div class="bk ${b.stock <= 0 ? 'out' : ''}" draggable="true" data-id="${b.id}"><div class="t">${b.is_pack ? '<span class="badge b-pack">PACK</span> ' : ''}${esc(b.title)}${b.volume ? ' · Vol. ' + esc(b.volume) : ''}</div>
      <div>${ownerChips(b)}</div><div class="m"><span class="p">${eur(b.price)}</span>${stockBadge(b)}</div></div>`).join('') || '<div class="empty"><svg class="ico" style="width:28px;height:28px;margin-bottom:8px" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg><br>Aucun résultat</div>';
  };
  // Le libraire choisit lui-même, pour chaque exemplaire, de quel lot (origine) il sort. Rien n'est automatique.
  const comps = l => { const b = S.books.find(x => x.id === l.id); return b.is_pack ? (b.items || []).map(i => ({ book_id: i.book_id, title: i.title, need: l.qty * i.qty, lots: i.lots })) : [{ book_id: b.id, title: b.title, need: l.qty, lots: b.lots }] };
  const got = (l, bid) => Object.entries(l.alloc).filter(([k]) => k.startsWith(bid + '|')).reduce((s, [, v]) => s + v, 0);
  const complete = l => comps(l).every(c => got(l, c.book_id) === c.need);
  const add = id => { const l = S.cart.find(x => x.id === id); if (l) l.qty++; else { const b = S.books.find(x => x.id === id); S.cart.push({ id, qty: 1, price: b.price, alloc: {} }) } cart() };

  const updatePayDropdown = () => {
    const paySel = $('#pay');
    if (!paySel) return;
    const curVal = paySel.value;
    const usedOwners = new Set();
    for (const l of S.cart) {
      const b = S.books.find(x => x.id === l.id);
      const allLots = b.is_pack ? (b.items || []).flatMap(i => i.lots) : (b.lots || []);
      for (const [k, q] of Object.entries(l.alloc)) {
        if (q > 0) {
          const [, lid] = k.split('|');
          const lot = allLots.find(x => x.id === +lid);
          if (lot && lot.owner) usedOwners.add(lot.owner.trim().toLowerCase());
        }
      }
    }
    const hasNonCR = Array.from(usedOwners).some(o => o !== 'cité royale');
    const allPayOpts = S.options.payment || [];
    const availableOpts = allPayOpts.filter(p => {
      const isPaypal = p.label.toLowerCase().includes('paypal');
      if (isPaypal && hasNonCR) return false;
      return true;
    });

    paySel.innerHTML = availableOpts.map(p => `<option value="${esc(p.label)}" ${p.label === curVal ? 'selected' : ''}>${esc(p.label)}</option>`).join('') || '<option value="Espèces">Espèces</option>';
    if (curVal.toLowerCase().includes('paypal') && hasNonCR) {
      paySel.value = availableOpts[0] ? availableOpts[0].label : 'Espèces';
    }
  };

  const cart = () => {
    const el = $('#items');
    el.innerHTML = S.cart.map((l, i) => { const b = S.books.find(x => x.id === l.id); return `<div class="ci" style="grid-template-columns:1fr"><div class="row" style="justify-content:space-between;flex-wrap:nowrap"><div class="t">${b.is_pack ? '<span class="badge b-pack">PACK</span> ' : ''}${esc(b.title)}${b.volume ? ' · Vol. ' + esc(b.volume) : ''}</div>
      <div class="qty"><button data-i="${i}" data-d="-1">−</button><b>${l.qty}</b><button data-i="${i}" data-d="1">+</button></div></div>
      <div class="row" style="justify-content:flex-end"><span class="muted">Prix</span><input class="pr" type="number" step="0.5" value="${l.price}" data-p="${i}"> €</div>
      ${comps(l).map(c => { const g = got(l, c.book_id), ok = g === c.need; return `<div style="padding:8px 10px;border-radius:10px;background:var(--panel2);border:1px solid ${ok ? 'var(--good)' : 'var(--warn)'}"><div class="row" style="justify-content:space-between;font-size:12px"><span>${b.is_pack ? esc(c.title) : 'Origine des exemplaires'}</span><b style="color:${ok ? 'var(--good)' : 'var(--warn)'}">${g}/${c.need} ${ok ? 'complet' : 'à répartir'}</b></div>
        ${c.lots.map(t => `<div class="row" style="justify-content:space-between;margin-top:6px;flex-wrap:nowrap"><span class="chip"><i style="background:${t.color}"></i>${esc(t.owner)} · ${t.date} · dispo ${t.remaining}</span><span class="row" style="gap:4px;flex-wrap:nowrap"><input type="number" min="0" max="${t.remaining}" style="width:clamp(48px, 5vw, 68px);padding:4px 6px" value="${l.alloc[c.book_id + '|' + t.id] || 0}" data-a="${i}" data-k="${c.book_id}|${t.id}" data-max="${t.remaining}"><button class="btn ghost sm" data-fill="${i}" data-k="${c.book_id}|${t.id}" data-b="${c.book_id}" data-max="${t.remaining}" data-need="${c.need}">Max</button></span></div>`).join('') || '<div class="muted" style="font-size:12px;margin-top:6px">Aucun lot en stock.</div>'}
        <div class="row" style="justify-content:space-between;margin-top:6px;flex-wrap:nowrap"><span class="muted" style="font-size:12px">Hors stock (non tracé)</span><input type="number" min="0" style="width:clamp(48px, 5vw, 68px);padding:4px 6px" value="${l.alloc[c.book_id + '|none'] || 0}" data-a="${i}" data-k="${c.book_id}|none"></div></div>` }).join('')}</div>`}).join('') ||
      '<div class="empty"><svg class="ico" style="width:28px;height:28px;margin-bottom:8px" viewBox="0 0 24 24"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg><br>Glissez un livre ici<br>ou cliquez sur une carte</div>';
    $('#tot').textContent = eur(S.cart.reduce((s, l) => s + l.qty * l.price, 0));
    updatePayDropdown();
  };
  $('#q').oninput = $('#fOwner').onchange = $('#inStock').onchange = draw;
  $('#q').onkeydown = e => { if (e.key === 'Enter') { const q = $('#q').value.trim(); const b = S.books.find(x => x.code === q); if (b) { add(b.id); $('#q').value = ''; draw() } } };
  $('#books').onclick = e => { const c = e.target.closest('.bk'); if (c) add(+c.dataset.id) };
  $('#books').ondragstart = e => { const c = e.target.closest('.bk'); if (c) e.dataTransfer.setData('text/plain', c.dataset.id) };
  const cartEl = $('#cart');
  cartEl.ondragover = e => { e.preventDefault(); cartEl.classList.add('over') }; cartEl.ondragleave = () => cartEl.classList.remove('over');
  cartEl.ondrop = e => { e.preventDefault(); cartEl.classList.remove('over'); const id = +e.dataTransfer.getData('text/plain'); if (id) add(id) };
  $('#items').onclick = e => {
    const f = e.target.closest('button[data-fill]');
    if (f) { const l = S.cart[+f.dataset.fill], b = f.dataset.b, k = f.dataset.k; const others = got(l, b) - (l.alloc[k] || 0); l.alloc[k] = Math.max(0, Math.min(+f.dataset.max, +f.dataset.need - others)); return cart() }
    const bt = e.target.closest('button[data-i]'); if (!bt) return; const l = S.cart[+bt.dataset.i]; l.qty += +bt.dataset.d; l.alloc = {}; if (l.qty <= 0) S.cart.splice(+bt.dataset.i, 1); cart()
  };
  $('#items').onchange = e => {
    const t = e.target;
    if (t.dataset.p != null) { S.cart[+t.dataset.p].price = +t.value; cart() }
    else if (t.dataset.a != null) { const mx = t.dataset.max ? +t.dataset.max : Infinity; S.cart[+t.dataset.a].alloc[t.dataset.k] = Math.max(0, Math.min(mx, parseInt(t.value) || 0)); cart() }
  };
  $('#clear').onclick = () => { S.cart = []; cart() };
  $('#valid').onclick = safe(async () => {
    if (!S.cart.length) return toast('Panier vide', 'warn');
    const bad = S.cart.find(l => !complete(l));
    if (bad) return toast('Indiquez l\'origine de chaque exemplaire avant de valider (cadres orange).', 'warn');
    const payVal = $('#pay').value;
    const isPaypal = payVal.toLowerCase().includes('paypal');
    if (isPaypal) {
      for (const l of S.cart) {
        const b = S.books.find(x => x.id === l.id);
        const allLots = b.is_pack ? (b.items || []).flatMap(i => i.lots) : (b.lots || []);
        for (const [k, q] of Object.entries(l.alloc)) {
          if (q > 0) {
            const [, lid] = k.split('|');
            const lot = allLots.find(x => x.id === +lid);
            if (lot && lot.owner.trim().toLowerCase() !== 'cité royale') {
              return toast(`Le paiement PayPal POS est exclusivement réservé aux livres de Cité Royale. « ${lot.owner} » détecté.`, 'err');
            }
          }
        }
      }
    }
    const r = await api('/api/sales', 'POST', {
      date: $('#sdate').value,
      payment: payVal,
      customer_gender: curGender || null,
      customer_age_group: curAge || null,
      is_star: curStar ? 1 : 0,
      lines: S.cart.map(l => ({
        book_id: l.id, qty: l.qty, unit_price: l.price,
        allocations: Object.entries(l.alloc).filter(([, q]) => q > 0).map(([k, q]) => { const [bid, lid] = k.split('|'); return { book_id: +bid, lot_id: lid === 'none' ? null : +lid, qty: q } })
      }))
    });
    toast(`Vente enregistrée : ${eur(r.total)}`);
    S.cart = []; curGender = ''; curAge = ''; curStar = 0; await loadRef(); draw(); cart();
  });
  draw(); cart();
};

/* ---- Stock ---- */
VIEWS.stock = async () => {
  $('#topActions').innerHTML = '<button class="btn" id="newLot">＋ Réception de stock</button>';
  $('#view').innerHTML = `<div class="toolbar"><input class="search" id="q" placeholder="Filtrer…"><select id="fo"><option value="">Toutes origines</option>${S.owners.map(o => `<option>${esc(o.name)}</option>`).join('')}</select>
  <select id="fs"><option value="">Tout le stock</option><option value="low">Stock bas</option><option value="out">Ruptures</option><option value="ok">Disponibles</option></select></div>
  <div class="card card-fill" style="padding:0"><div class="table-wrap"><table><thead><tr><th>Titre</th><th>Code</th><th>Origine du stock</th><th class="num">Prix</th><th class="num">Valeur</th><th class="num">Stock</th></tr></thead><tbody id="tb"></tbody></table></div></div>`;
  const draw = () => {
    const q = $('#q').value.toLowerCase(), fo = $('#fo').value, fs = $('#fs').value;
    const l = S.books.filter(b => (!q || (b.title + b.code + (b.series || '') + (b.publisher || '')).toLowerCase().includes(q)) && (!fo || b.by_owner.some(o => o.owner === fo)) &&
      (!fs || (fs === 'low' && b.stock > 0 && b.stock <= b.min_stock) || (fs === 'out' && b.stock <= 0) || (fs === 'ok' && b.stock > b.min_stock)));
    $('#tb').innerHTML = l.map(b => `<tr class="click" data-id="${b.id}"><td>${b.is_pack ? '<span class="badge b-pack">PACK</span> ' : ''}${esc(b.title)} ${b.volume ? `<span class="muted">Vol. ${esc(b.volume)}</span>` : ''}<div class="muted" style="font-size:12px">${esc(b.publisher || '')}</div></td><td class="muted">${esc(b.code)}</td><td>${b.is_pack ? '<span class="muted">calculé selon composants</span>' : ownerChips(b)}</td><td class="num">${eur(b.price)}</td><td class="num">${eur(b.stock * b.price)}</td><td class="num">${stockBadge(b)}</td></tr>`).join('');
  };
  $('#q').oninput = $('#fo').onchange = $('#fs').onchange = draw; draw();
  $('#tb').onclick = e => { const t = e.target.closest('tr'); if (t) lotsModal(+t.dataset.id) };
  $('#newLot').onclick = () => lotForm();
};
function lotForm(bookId) {
  const phys = S.books.filter(b => !b.is_pack);
  modal(`<h2>Réception de stock</h2><div class="form"><label class="f full">Livre<select id="lb">${phys.map(b => `<option value="${b.id}" ${b.id === bookId ? 'selected' : ''}>${esc(b.title)}${b.volume ? ' Vol. ' + esc(b.volume) : ''} (${esc(b.code)})</option>`).join('')}</select></label>
  <label class="f">Origine / propriétaire<select id="lo">${S.owners.map(o => `<option value="${o.id}">${esc(o.name)} (${o.kind === 'maison_mere' ? 'maison mère' : 'église locale'})</option>`).join('')}</select></label>
  <label class="f">Quantité<input type="number" id="lq" value="1" min="1"></label><label class="f">Date<input type="date" id="ld" value="${today()}"></label>
  <label class="f">Coût unitaire payé (acquis) – optionnel<input type="number" step="0.01" id="lc" placeholder="vide = % reversé"></label>
  <label class="f">% reversé à l'origine – optionnel<input type="number" step="1" id="lp" placeholder="défaut de l'origine"></label><label class="f full">Note<input id="ln"></label></div>
  <div class="actions"><button class="btn ghost" onclick="closeModal()">Annuler</button><button class="btn" id="ok">Enregistrer</button></div>`, m => {
    $('#ok', m).onclick = safe(async () => {
      const v = id => $(id, m).value;
      await api('/api/lots', 'POST', { book_id: +v('#lb'), owner_id: +v('#lo'), qty_in: +v('#lq'), date: v('#ld'), unit_cost: v('#lc') === '' ? null : +v('#lc'), reverse_pct: v('#lp') === '' ? null : +v('#lp'), note: v('#ln') });
      closeModal(); toast('Stock ajouté'); go(S.view);
    });
  });
}
async function lotsModal(id) {
  const b = S.books.find(x => x.id === id);
  if (b.is_pack) return packModal(b);
  const lots = await api(`/api/books/${id}/lots`);
  modal(`<h2>${esc(b.title)}</h2><p class="muted" style="margin-bottom:12px">${esc(b.code)} · prix ${eur(b.price)} · seuil ${b.min_stock}</p>
  <div class="table-wrap"><table><thead><tr><th>Date</th><th>Origine</th><th class="num">Reçu</th><th class="num">Restant</th><th>Règle</th><th></th></tr></thead><tbody>
  ${lots.map(l => `<tr><td>${l.date}</td><td><span class="chip"><i style="background:${l.color}"></i>${esc(l.owner)}</span></td><td class="num">${l.qty_in}</td><td class="num"><b>${l.remaining}</b></td>
  <td class="muted">${l.unit_cost != null ? 'acquis ' + eur(l.unit_cost) + '/u' : (l.reverse_pct ?? l.o_pct) + ' % reversé'}</td><td class="num"><button class="btn ghost sm" data-adj="${l.id}">Ajuster / Retour</button></td></tr>`).join('') || '<tr><td colspan=6 class="muted">Aucune entrée</td></tr>'}</tbody></table></div>

  <div class="actions"><button class="btn ghost" onclick="closeModal()">Fermer</button><button class="btn" id="add">＋ Réception</button></div>`, m => {
    $('#add', m).onclick = () => lotForm(id);
    m.onclick = safe(async e => {
      const a = e.target.closest('[data-adj]'); if (!a) return;
      const d = prompt('Variation de quantité (ex. -2 pour retour maison mère / casse / perte, +1 pour correction) :'); if (!d) return;
      const reason = prompt('Motif :', +d < 0 ? 'Retour maison mère' : 'Correction inventaire') || 'Ajustement';
      await api(`/api/lots/${a.dataset.adj}/adjust`, 'POST', { delta: parseInt(d), reason }); toast('Ajusté'); closeModal(); go(S.view);
    });
  });
}

/* ---- Catalogue & packs ---- */
function bookForm(b = {}) {
  const f = (k, l, t = 'text') => `<label class="f"><span>${l}</span><input id="f_${k}" type="${t}" value="${esc(b[k] ?? '')}"></label>`;
  const cats = S.options.category || [];
  const types = S.options.type || [];
  const pubs = S.options.publisher || [];
  modal(`<h2>${b.id ? 'Modifier' : 'Nouveau'} ${b.is_pack ? 'pack' : 'livre'}</h2><div class="form">${f('code', 'Code (ISBN)')}${f('title', 'Titre')}${f('series', 'Série')}${f('volume', 'Volume')}${f('author', 'Auteur')}
  <label class="f"><span>Éditeur</span><input id="f_publisher" list="dl_pubs" value="${esc(b.publisher ?? '')}"><datalist id="dl_pubs">${pubs.map(p => `<option value="${esc(p.label)}">`).join('')}</datalist></label>
  <label class="f"><span>Catégorie</span><input id="f_category" list="dl_cats" value="${esc(b.category || 'Standard')}"><datalist id="dl_cats">${cats.map(c => `<option value="${esc(c.label)}">`).join('')}</datalist></label>
  <label class="f"><span>Type / Reliure</span><input id="f_type" list="dl_types" value="${esc(b.type || 'Souple')}"><datalist id="dl_types">${types.map(t => `<option value="${esc(t.label)}">`).join('')}</datalist></label>
  ${f('location', 'Emplacement')}${f('price', 'Prix de vente €', 'number')}${f('min_stock', 'Seuil d\'alerte', 'number')}</div>
  <div class="actions">${b.id ? '<button class="btn bad" id="del">Archiver</button>' : ''}<button class="btn ghost" onclick="closeModal()">Annuler</button><button class="btn" id="ok">Enregistrer</button></div>`, m => {
    $('#ok', m).onclick = safe(async () => {
      const g = k => $('#f_' + k, m).value.trim();
      const body = { code: g('code'), title: g('title'), series: g('series') || null, volume: g('volume') || null, author: g('author') || null, publisher: g('publisher') || null, category: g('category') || 'Standard', type: g('type') || null, location: g('location') || null, price: +g('price') || 0, min_stock: +g('min_stock') || 0, is_pack: b.is_pack || 0 };
      if (!body.code || !body.title) throw new Error('Code et titre requis');
      b.id ? await api(`/api/books/${b.id}`, 'PUT', body) : await api('/api/books', 'POST', body);
      closeModal(); toast('Enregistré'); go('catalog');
    });
    const d = $('#del', m); if (d) d.onclick = safe(async () => { if (confirm('Archiver cet article ?')) { await api(`/api/books/${b.id}`, 'DELETE'); closeModal(); go('catalog') } });
  });
}
function packModal(p) {
  let items = (p.items || []).map(i => ({ ...i }));
  modal(`<h2><svg class="ico" viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg> ${esc(p.title)}</h2><p class="muted" style="margin-bottom:10px">Glissez des livres dans la composition. Le prix du pack (${eur(p.price)}) est réparti sur les composants au prorata de leurs prix publics.</p>
  <div class="grid g-eq"><div><input id="pq" class="search" placeholder="Chercher un livre…" style="width:100%;margin-bottom:8px"><div id="pl" style="max-height:clamp(180px, 32vh, 360px);overflow:auto;display:flex;flex-direction:column;gap:5px"></div></div>
  <div><div class="packzone" id="pz"></div><p class="muted" style="margin-top:8px" id="pinfo"></p></div></div>
  <div class="actions"><button class="btn ghost" onclick="closeModal()">Fermer</button><button class="btn" id="ok">Enregistrer la composition</button></div>`, m => {
    const phys = S.books.filter(b => !b.is_pack);
    const list = () => { const q = $('#pq', m).value.toLowerCase(); $('#pl', m).innerHTML = phys.filter(b => !q || (b.title + b.code).toLowerCase().includes(q)).slice(0, 60).map(b => `<div class="bk" style="padding:8px 10px;flex-direction:row;justify-content:space-between" draggable="true" data-id="${b.id}"><span>${esc(b.title)}${b.volume ? ' · V' + esc(b.volume) : ''}</span><span class="muted">${eur(b.price)}</span></div>`).join('') };
    const draw = () => {
      $('#pz', m).innerHTML = items.map((i, n) => `<div class="ci" style="grid-template-columns:1fr auto"><span>${esc(i.title)}</span><span class="qty"><button data-n="${n}" data-d="-1">−</button><b>${i.qty}</b><button data-n="${n}" data-d="1">+</button></span></div>`).join('') || '<div class="empty">Déposez les livres ici</div>';
      const sum = items.reduce((s, i) => s + (phys.find(b => b.id === i.book_id)?.price || 0) * i.qty, 0);
      $('#pinfo', m).textContent = `Somme des prix publics : ${eur(sum)} · pack ${eur(p.price)} → ${sum ? (sum - p.price >= 0 ? 'économie client ' + eur(sum - p.price) : 'pack plus cher que la somme !') : ''}`;
    };
    const add = id => { const b = phys.find(x => x.id === id); if (!b) return; const e = items.find(i => i.book_id === id); e ? e.qty++ : items.push({ book_id: id, qty: 1, title: b.title + (b.volume ? ' · V' + b.volume : '') }); draw() };
    $('#pq', m).oninput = list; $('#pl', m).onclick = e => { const c = e.target.closest('.bk'); c && add(+c.dataset.id) };
    $('#pl', m).ondragstart = e => { const c = e.target.closest('.bk'); c && e.dataTransfer.setData('text/plain', c.dataset.id) };
    const z = $('#pz', m); z.ondragover = e => { e.preventDefault(); z.classList.add('over') }; z.ondragleave = () => z.classList.remove('over');
    z.ondrop = e => { e.preventDefault(); z.classList.remove('over'); add(+e.dataTransfer.getData('text/plain')) };
    z.onclick = e => { const b = e.target.closest('button[data-n]'); if (!b) return; const i = items[+b.dataset.n]; i.qty += +b.dataset.d; if (i.qty <= 0) items.splice(+b.dataset.n, 1); draw() };
    $('#ok', m).onclick = safe(async () => { await api(`/api/books/${p.id}/pack`, 'PUT', items.map(i => ({ book_id: i.book_id, qty: i.qty }))); closeModal(); toast('Pack mis à jour'); go('catalog') });
    list(); draw();
  });
}
VIEWS.catalog = async () => {
  $('#topActions').innerHTML = '<div class="row"><button class="btn ghost" id="np"><svg class="ico sm" viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg> Nouveau pack</button><button class="btn" id="nb">＋ Nouveau livre</button></div>';
  $('#nb').onclick = () => bookForm(); $('#np').onclick = () => bookForm({ is_pack: 1, category: 'Pack', code: 'PACK-' + String(S.books.filter(b => b.is_pack).length + 1).padStart(3, '0') });
  $('#view').innerHTML = `<div class="toolbar"><input class="search" id="q" placeholder="Rechercher…"></div><div class="card card-fill" style="padding:0"><div class="table-wrap"><table><thead><tr><th>Titre</th><th>Code</th><th>Auteur</th><th>Éditeur</th><th>Type</th><th class="num">Prix</th><th></th></tr></thead><tbody id="tb"></tbody></table></div></div>`;
  const draw = () => {
    const q = $('#q').value.toLowerCase();
    $('#tb').innerHTML = S.books.filter(b => !q || (b.title + b.code + (b.author || '') + (b.publisher || '') + (b.series || '')).toLowerCase().includes(q)).map(b => `<tr><td>${b.is_pack ? '<span class="badge b-pack">PACK</span> ' : ''}${esc(b.title)} ${b.volume ? `<span class="muted">Vol. ${esc(b.volume)}</span>` : ''}${b.is_pack ? `<div class="muted" style="font-size:12px">${(b.items || []).map(i => i.qty + '× ' + esc(i.title)).join(' + ') || 'composition vide'}</div>` : ''}</td><td class="muted">${esc(b.code)}</td><td>${esc(b.author || '')}</td><td>${esc(b.publisher || '')}</td><td>${esc(b.type || '')}</td><td class="num">${eur(b.price)}</td>
    <td class="num"><button class="btn ghost sm" data-e="${b.id}">Modifier</button> ${b.is_pack ? `<button class="btn sm" data-p="${b.id}">Composer</button>` : ''}</td></tr>`).join('');
  };
  $('#q').oninput = draw; draw();
  $('#tb').onclick = e => { const b = e.target.closest('button'); if (!b) return; const id = +(b.dataset.e || b.dataset.p); const bk = S.books.find(x => x.id === id); b.dataset.e ? bookForm(bk) : packModal(bk) };
};

/* ---- Ventes ---- */
VIEWS.sales = async () => {
  const rows = await api('/api/sales?limit=500');
  $('#view').innerHTML = `<div class="card card-fill" style="padding:0"><div class="table-wrap"><table><thead><tr><th>Date</th><th>Détail</th><th>Paiement</th><th>Libraire</th><th class="num">Qté</th><th class="num">Total</th><th></th></tr></thead><tbody>
  ${rows.map(s => `<tr><td>${s.date}</td><td class="td-wrap">${esc(s.detail)}</td><td><span class="chip">${esc(s.payment)}</span></td><td><span class="chip"><i style="background:var(--a1)"></i>${esc(s.user_name || 'Anonyme')}</span></td><td class="num">${s.qty}</td><td class="num"><b>${eur(s.total)}</b></td><td class="num"><button class="btn bad sm" data-id="${s.id}">Annuler</button></td></tr>`).join('') || '<tr><td colspan=7 class="muted">Aucune vente</td></tr>'}</tbody></table></div></div>`;
  $('#view').onclick = safe(async e => { const b = e.target.closest('button[data-id]'); if (b && confirm('Annuler cette vente ? Le stock sera restitué.')) { await api(`/api/sales/${b.dataset.id}`, 'DELETE'); toast('Vente annulée'); go('sales') } });
};

/* ---- Trésorerie & Caisse ---- */
VIEWS.treasury = async () => {
  const [tr, os] = await Promise.all([api('/api/treasury'), api('/api/settlements')]);
  $('#topActions').innerHTML = `
    <div class="row">
      <button class="btn good" id="btnDeposit"><svg class="ico sm" viewBox="0 0 24 24"><path d="M12 5v14M19 12l-7 7-7-7"/></svg> Déposer argent en caisse ICC</button>
      <button class="btn ghost" id="btnWithdraw"><svg class="ico sm" viewBox="0 0 24 24"><path d="M12 19V5M5 12l7-7 7 7"/></svg> Sortie / Remboursement caisse ICC</button>
    </div>
  `;

  $('#view').innerHTML = `
    <div class="grid g4">
      <div class="card" style="border-top:4px solid var(--good)">
        <div class="muted">Tiroir-Caisse physique (ICC Rennes)</div>
        <div class="big" style="color:var(--good);margin-top:6px">${eur(tr.cash_in_drawer)}</div>
        <div class="muted" style="font-size:11px;margin-top:4px">Espèces directes ICC (${eur(tr.sales_cash)}) + Dépôts (${eur(tr.deposits_cash)}) - Sorties (${eur(tr.withdrawals_cash)})</div>
      </div>
      <div class="card" style="border-top:4px solid #ffb454">
        <div class="muted">Borne PayPal POS (Cité Royale 100%)</div>
        <div class="big" style="color:#ffb454;margin-top:6px">${eur(tr.cr_paypal_total || 0)}</div>
        <div class="muted" style="font-size:11px;margin-top:4px">100% encaissé directement chez Cité Royale (exclu de la caisse)</div>
      </div>
      <div class="card" style="border-top:4px solid var(--warn)">
        <div class="muted">À régulariser sur PayPal POS (Cité Royale)</div>
        <div class="big" style="color:${(tr.cr_non_paypal_total || 0) > 0.005 ? 'var(--warn)' : 'var(--good)'};margin-top:6px">${eur(tr.cr_non_paypal_total || 0)}</div>
        <div class="muted" style="font-size:11px;margin-top:4px">Cité Royale payée hors PayPal : le libraire doit payer sur la borne</div>
      </div>
      <div class="card" style="border-top:4px solid var(--a2)">
        <div class="muted">À déposer en caisse locale (ICC Rennes)</div>
        <div class="big" style="color:${tr.user_balances.some(u => u.net_to_deposit > 0.005) ? 'var(--warn)' : 'var(--good)'};margin-top:6px">
          ${eur(tr.user_balances.reduce((s, u) => s + Math.max(0, u.net_to_deposit), 0))}
        </div>
        <div class="muted" style="font-size:11px;margin-top:4px">Somme due par les libraires ayant perçu des Wero ICC</div>
      </div>
    </div>

    <!-- Balance par libraire -->
    <div class="card" style="margin-bottom:16px">
      <h3>Balance &amp; Traçabilité par Libraire</h3>
      <p class="muted" style="font-size:12px;margin-bottom:12px;line-height:1.6">
        <b>1. Cité Royale</b> : 100% du produit revient à Cité Royale via PayPal POS (CB). Si un client a payé un livre Cité Royale autrement (espèces ou Wero), le libraire connecté <b>doit régulariser en payant lui-même sur la borne PayPal POS (CB)</b>.<br>
        <b>2. ICC Rennes (Wero)</b> : Les paiements Wero arrivent directement sur le compte personnel du <b>libraire connecté lors de la vente</b>. Ce dernier doit <b>déposer les fonds en espèces dans le tiroir-caisse physique</b> pour régulariser sa balance.<br>
        <span style="color:var(--a1)">Sécurité &amp; Intégrité : La balance Wero est automatiquement attribuée au libraire connecté (<b>${esc(getCurrentUser())}</b>).</span>
      </p>
      <div class="table-wrap">
        <table>
        <thead>
          <tr>
            <th>Libraire</th>
            <th class="num">À régulariser sur PayPal POS<br><span class="muted" style="font-size:10px">(Cité Royale)</span></th>
            <th class="num">Wero perçus sur compte<br><span class="muted" style="font-size:10px">(ICC Rennes)</span></th>
            <th class="num">Déjà déposé en tiroir<br><span class="muted" style="font-size:10px">(Caisse ICC)</span></th>
            <th class="num">Remboursé / Retiré</th>
            <th class="num">Reste à déposer en tiroir<br><span class="muted" style="font-size:10px">(Caisse ICC)</span></th>
            <th class="num">Action tiroir</th>
          </tr>
        </thead>
        <tbody>
          ${tr.user_balances.map(u => {
            const isMe = u.user_name === getCurrentUser();
            return `
            <tr style="${isMe ? 'background:rgba(124,92,255,0.08)' : ''}">
              <td>
                <b><span class="chip"><i style="background:${isMe ? 'var(--good)' : 'var(--a1)'}"></i>${esc(u.user_name)} ${isMe ? '(Vous)' : ''}</span></b>
              </td>
              <td class="num">
                <b style="color:${u.cr_due_to_paypal > 0.005 ? '#ffb454' : 'var(--good)'}">
                  ${u.cr_due_to_paypal > 0.005 ? `Payer ${eur(u.cr_due_to_paypal)} sur borne` : 'À jour (0 €)'}
                </b>
              </td>
              <td class="num">${eur(u.icc_wero_received)}</td>
              <td class="num" style="color:var(--good)">${eur(u.deposited)}</td>
              <td class="num muted">${eur(u.withdrawn)}</td>
              <td class="num">
                <b style="font-size:14px;color:${u.net_to_deposit > 0.005 ? 'var(--warn)' : u.net_to_deposit < -0.005 ? 'var(--bad)' : 'var(--good)'}">
                  ${u.net_to_deposit > 0.005 ? `Doit déposer ${eur(u.net_to_deposit)}` : u.net_to_deposit < -0.005 ? `Trop déposé (${eur(Math.abs(u.net_to_deposit))})` : 'À jour (0 €)'}
                </b>
              </td>
              <td class="num">
                ${isMe ? (u.net_to_deposit > 0.005 ? `
                  <button class="btn good sm" data-quick-deposit="${esc(u.user_name)}" data-amount="${u.net_to_deposit.toFixed(2)}">
                    Déposer ${eur(u.net_to_deposit)}
                  </button>
                ` : `
                  <button class="btn ghost sm" data-quick-deposit="${esc(u.user_name)}" data-amount="0">
                    + Déposer
                  </button>
                `) : `<span class="muted" style="font-size:11px" title="Connectez-vous avec ce profil pour enregistrer ses opérations">Verrouillé</span>`}
              </td>
            </tr>
          `}).join('') || '<tr><td colspan=7 class="muted">Aucun libraire enregistré</td></tr>'}
        </tbody>
      </table>
      </div>
    </div>


    <!-- Mouvements et régularisations de caisse -->
    <div class="grid g-eq">
      <div class="card" style="padding:0">
        <div style="padding:16px 18px 10px;border-bottom:1px solid var(--line)">
          <h3 style="margin:0">Journal des Dépôts &amp; Mouvements de caisse physique (ICC)</h3>
          <p class="muted" style="font-size:12px;margin:4px 0 0">Traçabilité complète des remises d'espèces et régularisations locales</p>
        </div>
        <div class="table-wrap" style="max-height:clamp(200px, 34vh, 420px)">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Libraire</th>
                <th>Type</th>
                <th class="num">Montant</th>
                <th>Note</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              ${tr.movements.map(m => {
                const canDel = m.user_name === getCurrentUser();
                return `
                <tr>
                  <td class="muted">${esc(m.date)}</td>
                  <td><b>${esc(m.user_name)}</b> ${canDel ? '<span class="chip" style="font-size:10px;padding:2px 5px">Vous</span>' : ''}</td>
                  <td>
                    <span class="badge ${m.type === 'DEPOSIT' ? 'b-ok' : 'b-low'}">
                      ${m.type === 'DEPOSIT' ? 'Dépôt en caisse' : 'Sortie / Remboursement'}
                    </span>
                  </td>
                  <td class="num"><b style="color:${m.type === 'DEPOSIT' ? 'var(--good)' : 'var(--bad)'}">${m.type === 'DEPOSIT' ? '+' : '−'} ${eur(m.amount)}</b></td>
                  <td class="muted" style="font-size:12px">${esc(m.note || '')}</td>
                  <td class="num">
                    ${canDel ? `<button class="btn bad sm" data-del-mov="${m.id}" title="Annuler votre mouvement">✕</button>` : `<span class="muted" style="font-size:12px" title="Seul l'auteur peut annuler cette ligne">Verrouillé</span>`}
                  </td>
                </tr>
              `}).join('') || '<tr><td colspan=6 class="muted" style="padding:16px">Aucun mouvement enregistré.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>

      <!-- Répartition globale des encaissements -->
      <div class="card">
        <h3>Encaissements cumulés par canal</h3>
        <p class="muted" style="font-size:12px;margin-bottom:14px">Historique total de tous les paiements enregistrés</p>
        <div class="table-wrap">
          <table>
          <thead>
            <tr>
              <th>Mode d'encaissement</th>
              <th class="num">Nombre de ventes</th>
              <th class="num">Total perçu</th>
            </tr>
          </thead>
          <tbody>
            ${tr.sales_by_pay.map(p => `
              <tr>
                <td><b>${esc(p.payment)}</b></td>
                <td class="num muted">${p.count}</td>
                <td class="num"><b>${eur(p.total)}</b></td>
              </tr>
            `).join('') || '<tr><td colspan=3 class="muted">Aucune vente</td></tr>'}
          </tbody>
        </table>
        </div>


        <!-- Synthèse globale propriétaire (archives) -->
        <h4 style="margin-top:20px;font-size:13px;color:var(--mut)">Synthèse par origine du stock (Gestion responsables)</h4>
        <div style="margin-top:8px">
          ${os.map(o => `
            <div class="tl" style="align-items:center">
              <span><span class="chip"><i style="background:${o.color}"></i>${esc(o.name)}</span></span>
              <span class="muted" style="font-size:12px">Ventes: ${eur(o.revenue)} · Part origine: ${eur(o.due)}</span>
              <b>Reste réglé: ${eur(o.remaining)}</b>
            </div>
          `).join('')}
        </div>
      </div>
    </div>
  `;

  // Gestion des dépôts et retraits pour l'utilisateur connecté uniquement
  const showMovementModal = (type = 'DEPOSIT', defaultAmount = '') => {
    const me = getCurrentUser();
    modal(`
      <h2>${type === 'DEPOSIT' ? 'Déposer de l\'argent dans la caisse' : 'Enregistrer une sortie de caisse'}</h2>
      <div class="form">
        <label class="f">Libraire connecté (fixe)
          <input id="mUser" value="${esc(me)}" disabled style="opacity:.8;cursor:not-allowed">
        </label>
        <label class="f">Montant €
          <input id="mAmount" type="number" step="0.01" min="0.01" value="${defaultAmount || ''}" placeholder="ex: 35.00" autofocus>
        </label>
        <label class="f">Date
          <input id="mDate" type="date" value="${today()}">
        </label>
        <label class="f">Canal physique
          <select id="mChannel">
            <option value="ESPECES">Espèces (remise physique dans le tiroir)</option>
          </select>
        </label>
        <label class="f full">Motif / Commentaire
          <input id="mNote" placeholder="${type === 'DEPOSIT' ? 'Régularisation encaissement Wero du dimanche...' : 'Remboursement avance de frais...'}">
        </label>
      </div>
      <div class="actions">
        <button class="btn ghost" onclick="closeModal()">Annuler</button>
        <button class="btn ${type === 'DEPOSIT' ? 'good' : 'bad'}" id="mOk">Enregistrer pour ${esc(me)}</button>
      </div>
    `, m => {
      $('#mOk', m).onclick = safe(async () => {
        const amt = +$('#mAmount', m).value;
        if (!amt || amt <= 0) return toast('Veuillez indiquer un montant valide', 'warn');
        await api('/api/treasury/movements', 'POST', {
          user_name: me,
          type: type,
          channel: $('#mChannel', m).value,
          amount: amt,
          date: $('#mDate', m).value,
          note: $('#mNote', m).value
        });
        closeModal();
        toast(type === 'DEPOSIT' ? 'Dépôt enregistré avec succès' : 'Sortie de caisse enregistrée');
        VIEWS.treasury();
      });
    });
  };

  $('#btnDeposit').onclick = () => showMovementModal('DEPOSIT');
  $('#btnWithdraw').onclick = () => showMovementModal('WITHDRAWAL');

  $('#view').onclick = safe(async e => {
    const qd = e.target.closest('button[data-quick-deposit]');
    if (qd) {
      if (qd.dataset.quickDeposit !== getCurrentUser()) {
        return toast('Connectez-vous d\'abord avec ce profil pour enregistrer son opération', 'warn');
      }
      showMovementModal('DEPOSIT', +qd.dataset.amount > 0 ? qd.dataset.amount : '');
      return;
    }
    const delMov = e.target.closest('button[data-del-mov]');
    if (delMov) {
      if (confirm('Annuler ce mouvement de caisse ?')) {
        await api(`/api/treasury/movements/${delMov.dataset.delMov}`, 'DELETE');
        toast('Mouvement annulé');
        VIEWS.treasury();
      }
      return;
    }
  });
};

/* ---- Réservations ---- */
VIEWS.orders = async () => {
  $('#topActions').innerHTML = '<button class="btn" id="nr">＋ Nouvelle réservation</button>';
  const rows = await api('/api/reservations');
  $('#view').innerHTML = `<div class="card card-fill" style="padding:0"><div class="table-wrap"><table><thead><tr><th>Client</th><th>Téléphone</th><th>Titre</th><th class="num">Qté</th><th>Statut</th><th></th></tr></thead><tbody>
  ${rows.map(r => `<tr><td>${esc(r.name)}</td><td>${esc(r.phone || '')}</td><td>${esc(r.title)}</td><td class="num">${r.qty}</td><td><span class="badge ${r.status === 'Servie' ? 'b-ok' : 'b-low'}">${esc(r.status)}</span></td>
  <td class="num"><button class="btn ghost sm" data-s="${r.id}">${r.status === 'Servie' ? 'Rouvrir' : 'Servie'}</button> <button class="btn bad sm" data-d="${r.id}">✕</button></td></tr>`).join('') || '<tr><td colspan=6 class="muted">Aucune réservation</td></tr>'}</tbody></table></div>`;
  $('#nr').onclick = () => modal(`<h2>Réservation</h2><div class="form"><label class="f">Nom<input id="n"></label><label class="f">Téléphone<input id="p"></label><label class="f full">Titre demandé<input id="t" list="dl"></label><datalist id="dl">${S.books.map(b => `<option value="${esc(b.title)}">`).join('')}</datalist><label class="f">Quantité<input id="q" type="number" value="1"></label></div><div class="actions"><button class="btn ghost" onclick="closeModal()">Annuler</button><button class="btn" id="ok">Enregistrer</button></div>`, m => {
    $('#ok', m).onclick = safe(async () => { await api('/api/reservations', 'POST', { name: $('#n', m).value, phone: $('#p', m).value, title: $('#t', m).value, qty: +$('#q', m).value || 1 }); closeModal(); go('orders') });
  });
  $('#view').onclick = safe(async e => {
    const s = e.target.closest('[data-s]'), d = e.target.closest('[data-d]');
    if (s) { const r = rows.find(x => x.id == s.dataset.s); await api(`/api/reservations/${r.id}`, 'PUT', { ...r, status: r.status === 'Servie' ? 'En attente' : 'Servie' }); go('orders') }
    if (d && confirm('Supprimer ?')) { await api(`/api/reservations/${d.dataset.d}`, 'DELETE'); go('orders') }
  });
};

/* ---- Données & Excel ---- */
VIEWS.data = async () => {
  const info = await api('/api/info');
  $('#view').innerHTML = `<div class="grid g-eq"><div class="card"><h3>Importer un fichier Excel</h3><div class="drop" id="drop"><div style="margin-bottom:8px"><svg class="ico" style="width:36px;height:36px;stroke-width:1.5" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg></div><b>Glissez votre fichier .xlsx ici</b><div class="muted">ou cliquez pour parcourir<br>(Catalogue STD, Catalogue PACK, Livraisons, Ventes, Commande)</div></div><input type="file" id="file" accept=".xlsx" hidden>
  <label class="row muted" style="margin-top:12px"><input type="checkbox" id="rep" checked> Remplacer les données actuelles (une copie de sécurité est faite avant)</label><div id="rep-out" style="margin-top:10px"></div></div>
  <div class="card"><h3>Export complet Excel</h3><div class="row"><a class="btn" href="/api/export" download>Exporter tout en Excel (.xlsx)</a></div>
  <p class="muted" style="margin-top:14px;line-height:1.7">Un <b>fichier Excel miroir</b> est synchronisé en continu :<br><code>${esc(info.mirror)}</code><br>Dossier de stockage des archives :<br><code>${esc(info.backups)}</code><br>Base SQLite (WAL mode, transactions atomiques, anti-crash coupure secteur).<br><i>Les sauvegardes horodatées, points de restauration et l'audit sont consultables dans l'onglet <b>Historique &amp; Audit</b>.</i></p></div></div>

  <div class="card" style="margin-top:16px"><h3>Origines du stock &amp; règles de reversement <button class="btn sm" id="no">＋ Ajouter</button></h3><div class="table-wrap"><table><thead><tr><th>Nom</th><th>Type</th><th class="num">% reversé</th><th class="num">Ordre (import Excel uniquement)</th><th></th></tr></thead><tbody>
  ${S.owners.map(o => {
    const isFixed = ['cité royale', 'icc rennes'].includes(o.name.trim().toLowerCase());
    return `<tr><td><span class="chip"><i style="background:${o.color}"></i>${esc(o.name)}</span> ${isFixed ? '<span class="badge b-ok" style="font-size:10px">Fixe</span>' : ''}</td><td>${o.kind === 'maison_mere' ? 'Maison mère (dépôt)' : 'Église locale (acquis)'}</td><td class="num">${o.reverse_pct} %</td><td class="num">${o.priority}</td><td class="num">${isFixed ? '<span class="muted" style="font-size:12px;font-style:italic">Protégé</span>' : `<button class="btn ghost sm" data-o="${o.id}">Modifier</button>`}</td></tr>`;
  }).join('')}</tbody></table></div>

  <p class="muted" style="margin-top:10px;font-size:12px;line-height:1.6"><b>Cité Royale</b> et <b>ICC Rennes</b> sont les 2 origines fondamentales fixes et non modifiables. <b>% reversé</b> = part du prix de vente rendue à l'origine (100 = Cité Royale 100% de reversement ; 0 = stock acquis ICC Rennes). En caisse, <b>PayPal POS</b> est réservé exclusivement aux ouvrages de Cité Royale.</p></div>
  
  <div class="card" style="margin-top:16px">
    <h3>Listes &amp; Paramètres personnalisables (Catégories, Types, Paiements, Éditeurs)</h3>
    <p class="muted" style="font-size:12px;margin-bottom:12px;line-height:1.6">
      Vous pouvez <b>ajouter</b>, <b>renommer</b> ou <b>fusionner</b> des libellés.
      En cas de renommage ou de fusion, la mise à jour s'applique <b>en cascade sur tous les livres et ventes existants</b>, ainsi que sur les futurs miroirs et exports Excel. 
      Un <b>point de restauration automatique</b> est créé au préalable pour une sécurité absolue.
    </p>
    <div class="grid g-eq" style="margin-top:12px">
      ${[
        ['category', 'Catégories de livres'],
        ['type', 'Types & Reliures (Souple, Rigide...)'],
        ['payment', 'Moyens de paiement en caisse'],
        ['publisher', 'Éditeurs fréquents']
      ].map(([grp, titre]) => `
        <div style="background:var(--panel2);padding:14px;border-radius:12px;border:1px solid var(--line)">
          <div class="row" style="justify-content:space-between;margin-bottom:10px">
            <b>${titre}</b>
            <button class="btn sm" data-add-opt="${grp}">＋ Ajouter</button>
          </div>
          <div class="row" style="flex-wrap:wrap;gap:6px">
            ${(S.options[grp] || []).map(opt => `
              <span class="chip" style="padding:4px 8px 4px 10px;display:inline-flex;align-items:center;gap:6px">
                <span>${esc(opt.label)}</span>
                <button class="btn-chip-action" data-edit-opt="${opt.id}" data-grp="${grp}" data-lbl="${esc(opt.label)}" title="Renommer ou fusionner ce libellé">
                  <svg class="ico sm" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                </button>
                <b class="tag-x" data-del-opt="${opt.id}" data-lbl="${esc(opt.label)}" title="Supprimer de la liste">×</b>
              </span>
            `).join('') || '<span class="muted" style="font-size:12px">Aucune option</span>'}
          </div>
        </div>
      `).join('')}
    </div>
  </div>`;
  const send = safe(async f => {
    if (!f) return; const fd = new FormData(); fd.append('file', f);
    const r = await api(`/api/import?replace=${$('#rep').checked}`, 'POST', fd);
    $('#rep-out').innerHTML = `<div class="toast ok">${r.books} livres, ${r.packs} packs, ${r.lots} entrées de stock, ${r.sales} ventes, ${r.reservations} réservations importés.${r.skipped.length ? `<details><summary>${r.skipped.length} ligne(s) ignorée(s)</summary>${r.skipped.map(esc).join('<br>')}</details>` : ''}</div>`;
    await loadRef();
  });
  const dz = $('#drop'); dz.onclick = () => $('#file').click(); $('#file').onchange = e => send(e.target.files[0]);
  dz.ondragover = e => { e.preventDefault(); dz.classList.add('over') }; dz.ondragleave = () => dz.classList.remove('over');
  dz.ondrop = e => { e.preventDefault(); dz.classList.remove('over'); send(e.dataTransfer.files[0]) };
  const bkBtn = $('#bk');
  if (bkBtn) {
    bkBtn.onclick = safe(async () => { 
      await api('/api/backup', 'POST'); 
      toast('Snapshot de sécurité créé'); 
      VIEWS.data(); 
    });
  }
  const ownerForm = (o = {}) => modal(`<h2>${o.id ? 'Modifier' : 'Nouvelle'} origine</h2><div class="form"><label class="f full">Nom<input id="n" value="${esc(o.name || '')}"></label>
    <label class="f">Type<select id="k"><option value="maison_mere" ${o.kind === 'maison_mere' ? 'selected' : ''}>Maison mère (dépôt)</option><option value="locale" ${o.kind === 'locale' ? 'selected' : ''}>Église locale (acquis)</option></select></label>
    <label class="f">% reversé<input id="r" type="number" value="${o.reverse_pct ?? 100}"></label><label class="f">Ordre (import Excel uniquement)<input id="p" type="number" value="${o.priority ?? 5}"></label><label class="f">Couleur<input id="c" type="color" value="${o.color || '#6c8cff'}"></label></div>
    <div class="actions"><button class="btn ghost" onclick="closeModal()">Annuler</button><button class="btn" id="ok">Enregistrer</button></div>`, m => {
    $('#ok', m).onclick = safe(async () => { const body = { name: $('#n', m).value, kind: $('#k', m).value, reverse_pct: +$('#r', m).value, priority: +$('#p', m).value, color: $('#c', m).value }; o.id ? await api(`/api/owners/${o.id}`, 'PUT', body) : await api('/api/owners', 'POST', body); closeModal(); go('data') });
  });
  const noBtn = $('#no');
  if (noBtn) noBtn.onclick = () => ownerForm(); 

  // Modal interactif de renommage / fusion avec calcul d'impact
  const renameOptionModal = async (optId, grpKey, currentLabel) => {
    const impact = await api(`/api/options/${optId}/impact`);
    const otherOptions = (S.options[grpKey] || []).filter(o => o.id !== +optId);

    modal(`
      <h2>Renommer ou Fusionner « ${esc(currentLabel)} »</h2>
      <p class="muted" style="margin-bottom:14px;line-height:1.6">
        ${impact.total_impact > 0 
          ? `Cette option est actuellement utilisée sur <b>${impact.books_count} livre(s)</b> et <b>${impact.sales_count} vente(s)</b>.` 
          : `Cette option n'est actuellement liée à aucun livre ou vente enregistrée.`}
        <br>Un <b>point de restauration automatique</b> sera créé avant la modification.
      </p>

      <div class="form">
        <label class="f full">Nouveau nom (ou choisissez un nom existant pour fusionner) :
          <input id="renLabel" value="${esc(currentLabel)}" list="optSuggestions" autofocus>
          <datalist id="optSuggestions">
            ${otherOptions.map(o => `<option value="${esc(o.label)}">`).join('')}
          </datalist>
        </label>
        
        <label class="row full muted" style="margin-top:6px;cursor:pointer">
          <input type="checkbox" id="chkCascade" checked>
          <span>Appliquer la modification en cascade aux <b>${impact.total_impact} élément(s) existant(s)</b> et au miroir Excel</span>
        </label>
      </div>

      <div class="actions">
        <button class="btn ghost" onclick="closeModal()">Annuler</button>
        <button class="btn good" id="btnConfirmRen">Confirmer</button>
      </div>
    `, m => {
      $('#btnConfirmRen', m).onclick = safe(async () => {
        const val = $('#renLabel', m).value.trim();
        const cascade = $('#chkCascade', m).checked;
        if (!val) return toast('Le libellé ne peut pas être vide', 'warn');
        if (val === currentLabel) return closeModal();

        const res = await api(`/api/options/${optId}`, 'PUT', { new_label: val, cascade });
        closeModal();
        if (res.is_merge) {
          toast(`Fusion réussie vers « ${val} » (${res.updated_books} livres et ${res.updated_sales} ventes mis à jour)`, 'ok');
        } else {
          toast(`Option renommée en « ${val} » (${res.updated_books} livres mis à jour)`, 'ok');
        }
        await loadRef();
        go('data');
      });
    });
  };

  $('#view').onclick = safe(async e => { 
    const b = e.target.closest('button[data-o]'); 
    if (b) return ownerForm(S.owners.find(x => x.id == b.dataset.o));
    
    const addBtn = e.target.closest('button[data-add-opt]');
    if (addBtn) {
      const grp = addBtn.dataset.addOpt;
      const val = prompt('Nouveau libellé :');
      if (val && val.trim()) {
        await api('/api/options', 'POST', { group_key: grp, label: val.trim() });
        toast('Option ajoutée');
        await loadRef();
        go('data');
      }
      return;
    }

    const editBtn = e.target.closest('button[data-edit-opt], .btn-chip-action[data-edit-opt]');
    if (editBtn) {
      return renameOptionModal(editBtn.dataset.editOpt, editBtn.dataset.grp, editBtn.dataset.lbl);
    }

    const delBtn = e.target.closest('[data-del-opt]');
    if (delBtn) {
      if (confirm(`Supprimer l'option « ${delBtn.dataset.lbl || ''} » de la liste des choix ? (Les données existantes ne seront pas altérées)`)) {
        await api(`/api/options/${delBtn.dataset.delOpt}`, 'DELETE');
        toast('Option retirée de la liste');
        await loadRef();
        go('data');
      }
      return;
    }
  });
};

/* ---- Vue Audit & Historique d'actions ---- */
VIEWS.audit = async () => {
  const [logs, backups] = await Promise.all([api('/api/audit?limit=200'), api('/api/backups')]);
  $('#topActions').innerHTML = `<button class="btn good" id="bk"><svg class="ico sm" viewBox="0 0 24 24"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg> Créer un snapshot de sécurité maintenant</button>`;
  const bkBtn = $('#bk');
  if (bkBtn) bkBtn.onclick = safe(async () => {
    await api('/api/backup', 'POST');
    toast('Point de restauration créé');
    VIEWS.audit();
  });

  $('#view').innerHTML = `
  <div class="card" style="margin-bottom:16px">
    <h3>Sauvegardes &amp; Points de restauration automatiques (${backups.length})</h3>
    <p class="muted" style="font-size:12px;margin-bottom:10px;line-height:1.6">
      Protection anti-corruption : chaque fichier est écrit via un fichier temporaire sécurisé (<code>.tmp</code>).
      Vous pouvez <b>télécharger</b> un fichier pour sauvegarde externe (clé USB), ou <b>restaurer</b> directement l'état de la base à un instant précis (une copie de précaution de l'état actuel est créée automatiquement).
    </p>
    <div class="table-wrap" style="max-height:clamp(280px, 45vh, 520px)">
      <table>
        <thead>
          <tr>
            <th>Fichier</th>
            <th>Type</th>
            <th class="num">Taille</th>
            <th>Horodatage</th>
            <th class="num">Actions</th>
          </tr>
        </thead>
        <tbody>
          ${backups.map(b => `
            <tr>
              <td class="td-wrap" style="min-width:240px"><b>${esc(b.filename)}</b></td>
              <td style="white-space:nowrap"><span class="chip">${b.kind === 'database' ? 'Base SQLite' : 'Classeur Excel'}</span></td>
              <td class="num muted">${esc(b.size_human)}</td>
              <td class="muted" style="white-space:nowrap">${esc(b.modified)}</td>
              <td class="num" style="white-space:nowrap">
                <a class="btn ghost sm" href="/api/backups/${encodeURIComponent(b.filename)}/download" download="${esc(b.filename)}" title="Télécharger sur clé USB ou disque externe">Télécharger</a>
                ${b.kind === 'database' ? `<button class="btn bad sm" data-restore="${esc(b.filename)}" title="Restaurer l'état de cette date">Restaurer</button>` : ''}
                <button class="btn ghost sm" data-del-bk="${esc(b.filename)}" style="color:var(--bad)" title="Supprimer ce fichier">✕</button>
              </td>
            </tr>
          `).join('') || '<tr><td colspan=5 class="muted">Aucun fichier de sauvegarde pour l\'instant.</td></tr>'}
        </tbody>
      </table>
    </div>

  </div>

  <div class="card" style="margin-bottom:16px">
    <h3>Journal d'audit atomique &amp; Réversibilité des actions</h3>
    <p class="muted" style="line-height:1.6;font-size:13px">
      Toutes les opérations d'écriture sur la base de données sont horodatées et associées au profil actif.
      Vous pouvez <b>annuler</b> (Rollback / Undo) les erreurs d'un simple clic.
    </p>
  </div>
  <div class="card card-fill" style="padding:0">
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Date & Heure</th>
            <th>Utilisateur</th>
            <th>Opération</th>
            <th>Type</th>
            <th>Détail de l'opération</th>
            <th>Statut</th>
            <th class="num">Action</th>
          </tr>
        </thead>
        <tbody>
          ${logs.map(l => `
            <tr style="${l.undone ? 'opacity:.55;text-decoration:line-through' : ''}">
              <td class="muted" style="white-space:nowrap">${esc(l.timestamp)}</td>
              <td><span class="chip"><i style="background:var(--a1)"></i>${esc(l.user_name)}</span></td>
              <td><span class="badge ${l.action === 'INSERT' ? 'b-ok' : l.action === 'DELETE' ? 'b-out' : 'b-low'}">${esc(l.action)}</span></td>
              <td><span class="muted">${esc(l.target_type)}</span></td>
              <td class="td-wrap">${esc(l.summary)}</td>
              <td>${l.undone ? `<span class="badge b-out">Annulé le ${esc(l.undone_at || '')} par ${esc(l.undone_by || '')}</span>` : '<span class="badge b-ok">Actif</span>'}</td>
              <td class="num">
                ${!l.undone && l.action !== 'UNDO' ? `<button class="btn ghost sm" data-undo="${l.id}">⤺ Annuler</button>` : ''}
              </td>
            </tr>
          `).join('') || '<tr><td colspan=7 class="muted">Aucune entrée d\'audit pour le moment.</td></tr>'}
        </tbody>
      </table>
    </div>
  </div>`;

  $('#view').onclick = safe(async e => {
    // Restauration d'un fichier de sauvegarde
    const rst = e.target.closest('button[data-restore]');
    if (rst) {
      const fn = rst.dataset.restore;
      if (confirm(`ATTENTION : Voulez-vous restaurer la base à partir de « ${fn} » ?\n(Une sauvegarde de l'état actuel sera automatiquement créée avant)`)) {
        const res = await api(`/api/backups/${encodeURIComponent(fn)}/restore`, 'POST');
        toast(`Base restaurée avec succès ! (Précaution : ${res.pre_backup})`);
        await loadRef();
        VIEWS.audit();
      }
      return;
    }
    
    // Suppression d'un fichier de sauvegarde
    const delBk = e.target.closest('button[data-del-bk]');
    if (delBk) {
      const fn = delBk.dataset.delBk;
      if (confirm(`Supprimer définitivement le fichier « ${fn} » ?`)) {
        await api(`/api/backups/${encodeURIComponent(fn)}`, 'DELETE');
        toast('Fichier supprimé');
        VIEWS.audit();
      }
      return;
    }

    // Annulation unitaire d'audit
    const btn = e.target.closest('button[data-undo]');
    if (btn) {
      if (confirm('Voulez-vous vraiment annuler cette action et restaurer l\'état précédent ?')) {
        await api(`/api/audit/${btn.dataset.undo}/undo`, 'POST');
        toast('Opération annulée avec succès (Rollback effectué)');
        await loadRef();
        VIEWS.audit();
      }
      return;
    }
  });
};

/* ---------- modal de sélection / gestion des utilisateurs ---------- */
async function userModal() {
  const users = await api('/api/users');
  const current = getCurrentUser();
  modal(`<h2>Profils Utilisateurs</h2>
    <p class="muted" style="margin-bottom:14px">Choisissez votre prénom pour signer vos opérations en caisse et vos modifications :</p>
    <div style="display:flex;flex-direction:column;gap:8px;max-height:clamp(180px, 36vh, 320px);overflow:auto;margin-bottom:16px">
      ${users.map(u => `
        <div class="row" style="justify-content:space-between;padding:10px 14px;border-radius:12px;background:var(--panel2);border:1px solid ${u.name === current ? 'var(--a1)' : 'var(--line)'}">
          <label style="display:flex;align-items:center;gap:10px;cursor:pointer;flex:1">
            <input type="radio" name="sel_u" value="${esc(u.name)}" ${u.name === current ? 'checked' : ''}>
            <b style="font-size:15px">${esc(u.name)}</b>
          </label>
          <div class="row" style="gap:6px">
            <button class="btn ghost sm" data-ren-u="${u.id}" data-name="${esc(u.name)}">Modifier</button>
            <button class="btn bad sm" data-del-u="${u.id}" data-name="${esc(u.name)}">✕</button>
          </div>
        </div>
      `).join('') || '<div class="muted">Aucun profil</div>'}
    </div>
    <div class="row" style="justify-content:space-between">
      <button class="btn ghost" id="btnAddUser">＋ Nouveau profil</button>
      <div class="actions" style="margin:0">
        <button class="btn ghost" onclick="closeModal()">Fermer</button>
        <button class="btn good" id="btnApplyUser">Sélectionner</button>
      </div>
    </div>`, m => {
      $('#btnApplyUser', m).onclick = () => {
        const rad = $('input[name="sel_u"]:checked', m);
        if (rad) {
          setCurrentUser(rad.value);
          toast(`Connecté en tant que ${rad.value}`);
          closeModal();
        }
      };
      $('#btnAddUser', m).onclick = safe(async () => {
        const name = prompt('Prénom du nouvel utilisateur :');
        if (name && name.trim()) {
          await api('/api/users', 'POST', { name: name.trim() });
          toast('Utilisateur créé');
          closeModal();
          userModal();
        }
      });
      m.onclick = safe(async e => {
        const ren = e.target.closest('button[data-ren-u]');
        if (ren) {
          const nv = prompt('Nouveau prénom :', ren.dataset.name);
          if (nv && nv.trim() && nv.trim() !== ren.dataset.name) {
            await api(`/api/users/${ren.dataset.renU}`, 'PUT', { name: nv.trim() });
            if (getCurrentUser() === ren.dataset.name) setCurrentUser(nv.trim());
            toast('Profil mis à jour');
            closeModal();
            userModal();
          }
          return;
        }
        const del = e.target.closest('button[data-del-u]');
        if (del) {
          if (confirm(`Supprimer le profil « ${del.dataset.name} » ?`)) {
            await api(`/api/users/${del.dataset.delU}`, 'DELETE');
            toast('Profil supprimé');
            if (getCurrentUser() === del.dataset.name) setCurrentUser('Responsable');
            closeModal();
            userModal();
          }
          return;
        }
      });
    });
}

// Clic sur le badge utilisateur en haut à gauche
const ub = $('#userBadge');
if (ub) ub.onclick = userModal;
const bsu = $('#btnSwitchUser');
if (bsu) bsu.onclick = (e) => { e.stopPropagation(); userModal(); };

// Bouton rouge persistant Mode Focus (accessible partout)
const bFocus = $('#btnFocusMode');
if (bFocus) bFocus.onclick = toggleFocusMode;

/* ---------- Gestion dynamique du thème (Système / Clair / Sombre) ---------- */
function getSystemTheme() {
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

function getSavedThemePreference() {
  return localStorage.getItem('librairie_theme_preference') || 'auto'; // 'auto' | 'light' | 'dark'
}

function applyTheme(pref) {
  const effective = (pref === 'auto') ? getSystemTheme() : pref;
  if (pref === 'auto') {
    document.documentElement.removeAttribute('data-theme');
  } else {
    document.documentElement.setAttribute('data-theme', pref);
  }

  // Adapter le logo selon le thème effectif
  const logoImg = $('.brand-logo-img');
  if (logoImg) {
    if (effective === 'light') {
      logoImg.src = '/static/img/logo_icc_rennes_bar.png'; // Version noire sur fond clair
    } else {
      logoImg.src = '/static/img/logo_icc_rennes_bar_white.png'; // Version blanche sur fond sombre
    }
  }

  // Mettre à jour l'intitulé et l'icône du bouton
  const label = $('#themeLabel');
  const btn = $('#btnThemeToggle');
  if (label && btn) {
    if (pref === 'auto') {
      label.textContent = 'Auto';
      btn.title = 'Thème : Aligné sur votre système d\'exploitation (Cliquez pour forcer Clair)';
    } else if (pref === 'light') {
      label.textContent = 'Clair';
      btn.title = 'Thème : Clair fixé (Cliquez pour forcer Sombre)';
    } else {
      label.textContent = 'Sombre';
      btn.title = 'Thème : Sombre fixé (Cliquez pour revenir au mode Auto)';
    }
  }
}

function cycleTheme() {
  const current = getSavedThemePreference();
  let next = 'auto';
  if (current === 'auto') next = 'light';
  else if (current === 'light') next = 'dark';
  else next = 'auto';
  
  localStorage.setItem('librairie_theme_preference', next);
  applyTheme(next);
  toast(`Thème basculé : ${next === 'auto' ? 'Adaptatif Système' : next === 'light' ? 'Clair' : 'Sombre'}`, 'ok');
}

const btnTheme = $('#btnThemeToggle');
if (btnTheme) btnTheme.onclick = cycleTheme;

// Écouter les changements de thème du système en temps réel
window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
  if (getSavedThemePreference() === 'auto') {
    applyTheme('auto');
  }
});

/* ---------- Raccourcis clavier globaux (F1 à F12) ---------- */
const KEY_TO_VIEW = {
  F1: 'dashboard',
  F2: 'pos',
  F3: 'stock',
  F4: 'catalog',
  F5: 'sales',
  F6: 'treasury',
  F7: 'orders',
  F8: 'audit',
  F9: 'data'
};

document.addEventListener('keydown', e => {
  // Navigation directe F1 -> F9
  if (KEY_TO_VIEW[e.key]) {
    e.preventDefault();
    go(KEY_TO_VIEW[e.key]);
    return;
  }

  // F10 : Basculer le thème (Auto / Clair / Sombre)
  if (e.key === 'F10') {
    e.preventDefault();
    cycleTheme();
    return;
  }

  // F11 : Activer / Désactiver le Mode Focus
  if (e.key === 'F11') {
    e.preventDefault();
    toggleFocusMode();
    return;
  }

  // F12 : Raccourci rapide d'action (Valider la vente en caisse, ou valider le modal ouvert)
  if (e.key === 'F12') {
    e.preventDefault();
    // 1. Si un modal avec bouton de confirmation #ok ou #mOk est ouvert, on le valide
    const modalOk = $('#modalRoot #ok, #modalRoot #mOk, #modalRoot #btnConfirmRen, #modalRoot #btnApplyUser');
    if (modalOk && !modalOk.disabled && modalOk.offsetParent !== null) {
      modalOk.click();
      return;
    }
    // 2. Sinon, en caisse (POS), déclenche la validation de la vente
    const validBtn = $('#valid');
    if (validBtn && validBtn.offsetParent !== null) {
      validBtn.click();
      return;
    }
  }
});

applyTheme(getSavedThemePreference());
updateUserDisplay();
updateFocusUI();
go(isFocusMode() ? 'pos' : 'dashboard');


