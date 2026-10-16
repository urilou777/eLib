/* Librairie – interface (vanilla JS, 100 % hors-ligne) */
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const eur = n => (Number(n) || 0).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
const nf = n => (Number(n) || 0).toLocaleString('fr-FR');
const today = () => new Date().toISOString().slice(0, 10);
const MONTHS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
const mlabel = m => MONTHS[+m.slice(5) - 1] + ' ' + m.slice(2, 4);

async function api(url, method = 'GET', body) {
  const o = { method, headers: {} };
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
const S = { books: [], owners: [], cart: [], view: 'dashboard', range: 'all', from: '', to: '' };
const stockBadge = b => b.stock <= 0 ? '<span class="badge b-out">Rupture</span>' :
  b.stock <= b.min_stock ? `<span class="badge b-low">${b.stock} · bas</span>` : `<span class="badge b-ok">${b.stock}</span>`;
const ownerChips = b => (b.by_owner || []).map(o => `<span class="chip"><i style="background:${o.color}"></i>${esc(o.owner)} ${o.qty}</span>`).join('');

async function loadRef() { [S.books, S.owners] = await Promise.all([api('/api/books'), api('/api/owners')]); }

/* ---------- navigation ---------- */
const TITLES = { dashboard: 'Tableau de bord', pos: 'Caisse', stock: 'Stock', catalog: 'Catalogue & packs', sales: 'Historique des ventes', settle: 'Reversements', orders: 'Réservations', data: 'Données & Excel' };
async function go(v) {
  S.view = v; $('#title').textContent = TITLES[v]; $('#topActions').innerHTML = ''; $('#view').onclick = null;
  document.querySelectorAll('#nav a').forEach(a => a.classList.toggle('on', a.dataset.v === v));
  $('#view').innerHTML = '<div class="empty">Chargement…</div>';
  try { await loadRef(); await VIEWS[v](); } catch (e) { toast(e.message, 'err'); }
}
$('#nav').addEventListener('click', e => { const a = e.target.closest('a'); if (a) go(a.dataset.v); });

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
  for (let i = 0; i <= 4; i++) { const v = max * i / 4, y = Y(v); s += `<line x1="${L}" x2="${W - R}" y1="${y}" y2="${y}" stroke="rgba(255,255,255,.07)"/><text x="${L - 8}" y="${y + 4}" text-anchor="end">${Math.round(v)}</text>`; }
  months.forEach((m, i) => {
    let acc = 0;
    names.forEach(n => {
      const v = owners[n].v[m] || 0, h = (H - T - B) * v / max; acc += v;
      s += `<rect x="${X(i) + bw * .18}" y="${Y(acc)}" width="${bw * .64}" height="${h}" rx="3" fill="${owners[n].color}" opacity=".88"><title>${mlabel(m)} · ${n} : ${eur(v)}</title></rect>`;
    });
  });
  fut.forEach((m, i) => { const idx = months.length + i; s += `<rect x="${X(idx) + bw * .18}" y="${Y(fc[i])}" width="${bw * .64}" height="${(H - T - B) * fc[i] / max}" rx="3" fill="none" stroke="#b9a8ff" stroke-dasharray="4 3"><title>Prévision ${mlabel(m)} : ${eur(fc[i])}</title></rect>`; });
  // moyenne mobile 3 mois
  const ma = totals.map((_, i) => { const sl = totals.slice(Math.max(0, i - 2), i + 1); return sl.reduce((a, b) => a + b, 0) / sl.length });
  s += `<polyline fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" points="${ma.map((v, i) => `${X(i) + bw / 2},${Y(v)}`).join(' ')}"/>`;
  ma.forEach((v, i) => s += `<circle cx="${X(i) + bw / 2}" cy="${Y(v)}" r="3.2" fill="#fff"/>`);
  all.forEach((m, i) => { if (all.length < 14 || i % 2 === 0) s += `<text x="${X(i) + bw / 2}" y="${H - 8}" text-anchor="middle">${mlabel(m)}</text>`; });
  el.innerHTML = s + '</svg>' + `<div class="legend">${names.map(n => `<span><i style="background:${owners[n].color}"></i>${esc(n)}</span>`).join('')}<span><i style="background:#fff"></i>Tendance (moy. mobile 3 m.)</span><span><i style="border:1.5px dashed #b9a8ff;background:none"></i>Prévision</span></div>`;
}
function donut(el, data, fmt = eur) {
  const tot = data.reduce((s, d) => s + d.value, 0); if (!tot) { el.innerHTML = '<div class="empty">—</div>'; return; }
  let a = -Math.PI / 2, s = '<svg viewBox="-110 -110 220 220" style="width:100%;height:210px">';
  data.forEach(d => {
    const ang = d.value / tot * Math.PI * 2, r = 90, x1 = r * Math.cos(a), y1 = r * Math.sin(a); a += ang;
    const x2 = r * Math.cos(a), y2 = r * Math.sin(a), big = ang > Math.PI ? 1 : 0;
    if (d.value / tot > .999) s += `<circle r="${r}" fill="none" stroke="${d.color}" stroke-width="26"/>`;
    else s += `<path d="M${x1} ${y1} A${r} ${r} 0 ${big} 1 ${x2} ${y2}" fill="none" stroke="${d.color}" stroke-width="26"><title>${esc(d.label)} : ${fmt(d.value)}</title></path>`;
  });
  s += `<text text-anchor="middle" y="-2" style="fill:#fff;font-size:20px;font-weight:700">${fmt(tot)}</text><text text-anchor="middle" y="16">total</text></svg>`;
  el.innerHTML = s + `<div class="legend" style="justify-content:center">${data.map(d => `<span><i style="background:${d.color}"></i>${esc(d.label)} · ${Math.round(d.value / tot * 100)}%</span>`).join('')}</div>`;
}
function hbars(el, rows, key = 'revenue', fmt = eur, sub) {
  if (!rows.length) { el.innerHTML = '<div class="empty">—</div>'; return; }
  const max = Math.max(...rows.map(r => r[key])) || 1;
  el.innerHTML = rows.map(r => `<div class="hbar"><span class="t" title="${esc(r.label || r.title)}">${esc(r.label || r.title)}</span><div class="tr"><div class="fl" style="width:${r[key] / max * 100}%"></div></div><b>${fmt(r[key])}${sub ? ` <span class="muted" style="font-weight:400">${sub(r)}</span>` : ''}</b></div>`).join('');
}
const PALETTE = ['#7c5cff', '#27d3c3', '#ffb454', '#ff6b8b', '#5a9bff', '#4be0a0', '#c77dff'];

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
  const kp = [['Chiffre d\'affaires', eur(k.revenue), `${nf(k.qty)} exemplaires`, '#7c5cff'], ['Marge conservée', eur(k.margin), k.revenue ? Math.round(k.margin / k.revenue * 100) + ' % du CA' : '', '#27d3c3'],
  ['Ventes', nf(k.sales), `Panier moyen ${eur(k.avg_basket)}`, '#5a9bff'], ['À reverser', eur(k.due_open), 'reste à régler (global)', '#ffb454'], ['Valeur du stock', eur(k.stock_value), `${nf(k.stock_units)} exemplaires`, '#c77dff']];
  $('#view').innerHTML = `<div class="grid g-kpi">${kp.map((x, i) => `<div class="card kpi" style="--c:${x[3]};animation-delay:${i * 60}ms"><div class="l">${x[0]}</div><div class="v">${x[1]}</div><div class="s">${x[2]}</div></div>`).join('')}</div>
  <div class="grid g2" style="margin-bottom:16px"><div class="card"><h3>Évolution mensuelle du CA par origine · tendance & prévision</h3><div id="cTrend"></div></div>
    <div class="card"><h3>Répartition par origine du stock</h3><div id="cOwner"></div></div></div>
  <div class="grid g3" style="margin-bottom:16px"><div class="card"><h3>Top 10 des ventes</h3><div id="cTop"></div></div>
    <div class="card"><h3>Par catégorie</h3><div id="cCat"></div><h3 style="margin-top:22px">Par éditeur</h3><div id="cPub"></div></div>
    <div class="card"><h3>Jours de la semaine</h3><div id="cWd"></div><h3 style="margin-top:22px">Moyens de paiement</h3><div id="cPay"></div></div></div>
  <div class="card"><h3>⚠️ Alertes de stock bas (${st.low_stock.length})</h3><div class="scroll" style="max-height:300px;overflow:auto"><table><thead><tr><th>Titre</th><th>Origine</th><th class="num">Stock</th><th class="num">Seuil</th><th class="num">Autonomie estimée</th></tr></thead><tbody>
  ${st.low_stock.map(b => `<tr><td>${esc(b.title)} ${b.volume ? `<span class="muted">Vol. ${esc(b.volume)}</span>` : ''}</td><td>${ownerChips(b)}</td><td class="num">${stockBadge(b)}</td><td class="num">${b.min_stock}</td><td class="num">${b.days_left == null ? '<span class="muted">pas de ventes récentes</span>' : b.days_left + ' j'}</td></tr>`).join('') || '<tr><td colspan=5 class="muted">Tout est bien approvisionné 🎉</td></tr>'}</tbody></table></div></div>`;
  trendChart($('#cTrend'), st.monthly, st.forecast, st.by_owner_month);
  donut($('#cOwner'), st.by_owner.map((o, i) => ({ label: o.label, value: o.revenue, color: o.color })));
  hbars($('#cTop'), st.top, 'qty', nf, r => eur(r.revenue));
  hbars($('#cCat'), st.by_category); hbars($('#cPub'), st.by_publisher.slice(0, 6));
  const days = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam']; const wd = {}; st.weekday.forEach(w => wd[w.d] = w.revenue);
  hbars($('#cWd'), [1, 2, 3, 4, 5, 6, 0].map(d => ({ label: days[d], revenue: wd[d] || 0 })));
  hbars($('#cPay'), st.payments.map(p => ({ label: p.label, n: p.n })), 'n', nf);
};

/* ---- Caisse ---- */
VIEWS.pos = async () => {
  $('#view').innerHTML = `<div class="pos"><div class="pos-l"><div class="toolbar"><input class="search" id="q" placeholder="Rechercher un titre, ou scanner / saisir un code ISBN puis Entrée…" autofocus>
    <select id="fOwner"><option value="">Toutes origines</option>${S.owners.map(o => `<option>${esc(o.name)}</option>`).join('')}</select><label class="row muted"><input type="checkbox" id="inStock" checked> En stock</label></div>
    <div class="books" id="books"></div></div>
    <div class="card cart" id="cart"><h3>Panier <button class="btn ghost sm" id="clear">Vider</button></h3><div class="cart-items" id="items"></div>
    <div class="total"><span>Total</span><b id="tot">0 €</b></div>
    <div class="row" style="margin-bottom:10px"><select id="pay" style="flex:1"><option>Espèces</option><option>Carte</option><option>Chèque</option><option>Virement</option><option>Don / Offert</option></select><input type="date" id="sdate" value="${today()}"></div>
    <button class="btn good" id="valid" style="padding:13px;font-size:15px">✔ Valider la vente</button></div></div>`;
  const draw = () => {
    const q = $('#q').value.trim().toLowerCase(), ow = $('#fOwner').value, ins = $('#inStock').checked;
    const list = S.books.filter(b => (!q || (b.title + ' ' + (b.series || '') + ' ' + b.code + ' ' + (b.author || '')).toLowerCase().includes(q))
      && (!ins || b.stock > 0) && (!ow || (b.by_owner || []).some(o => o.owner === ow)));
    $('#books').innerHTML = list.map(b => `<div class="bk ${b.stock <= 0 ? 'out' : ''}" draggable="true" data-id="${b.id}"><div class="t">${b.is_pack ? '<span class="badge b-pack">PACK</span> ' : ''}${esc(b.title)}${b.volume ? ' · Vol. ' + esc(b.volume) : ''}</div>
      <div>${ownerChips(b)}</div><div class="m"><span class="p">${eur(b.price)}</span>${stockBadge(b)}</div></div>`).join('') || '<div class="empty"><b>🔍</b>Aucun résultat</div>';
  };
  // Le libraire choisit lui-même, pour chaque exemplaire, de quel lot (origine) il sort. Rien n'est automatique.
  const comps = l => { const b = S.books.find(x => x.id === l.id); return b.is_pack ? (b.items || []).map(i => ({ book_id: i.book_id, title: i.title, need: l.qty * i.qty, lots: i.lots })) : [{ book_id: b.id, title: b.title, need: l.qty, lots: b.lots }] };
  const got = (l, bid) => Object.entries(l.alloc).filter(([k]) => k.startsWith(bid + '|')).reduce((s, [, v]) => s + v, 0);
  const complete = l => comps(l).every(c => got(l, c.book_id) === c.need);
  const add = id => { const l = S.cart.find(x => x.id === id); if (l) l.qty++; else { const b = S.books.find(x => x.id === id); S.cart.push({ id, qty: 1, price: b.price, alloc: {} }) } cart() };
  const cart = () => {
    const el = $('#items');
    el.innerHTML = S.cart.map((l, i) => { const b = S.books.find(x => x.id === l.id); return `<div class="ci" style="grid-template-columns:1fr"><div class="row" style="justify-content:space-between;flex-wrap:nowrap"><div class="t">${b.is_pack ? '<span class="badge b-pack">PACK</span> ' : ''}${esc(b.title)}${b.volume ? ' · Vol. ' + esc(b.volume) : ''}</div>
      <div class="qty"><button data-i="${i}" data-d="-1">−</button><b>${l.qty}</b><button data-i="${i}" data-d="1">+</button></div></div>
      <div class="row" style="justify-content:flex-end"><span class="muted">Prix</span><input class="pr" type="number" step="0.5" value="${l.price}" data-p="${i}"> €</div>
      ${comps(l).map(c => { const g = got(l, c.book_id), ok = g === c.need; return `<div style="padding:8px 10px;border-radius:10px;background:var(--panel2);border:1px solid ${ok ? 'var(--good)' : 'var(--warn)'}"><div class="row" style="justify-content:space-between;font-size:12px"><span>${b.is_pack ? esc(c.title) : 'Origine des exemplaires'}</span><b style="color:${ok ? 'var(--good)' : 'var(--warn)'}">${g}/${c.need} ${ok ? '✔' : 'à répartir'}</b></div>
        ${c.lots.map(t => `<div class="row" style="justify-content:space-between;margin-top:6px;flex-wrap:nowrap"><span class="chip"><i style="background:${t.color}"></i>${esc(t.owner)} · ${t.date} · dispo ${t.remaining}</span><span class="row" style="gap:4px;flex-wrap:nowrap"><input type="number" min="0" max="${t.remaining}" style="width:56px;padding:4px 6px" value="${l.alloc[c.book_id + '|' + t.id] || 0}" data-a="${i}" data-k="${c.book_id}|${t.id}" data-max="${t.remaining}"><button class="btn ghost sm" data-fill="${i}" data-k="${c.book_id}|${t.id}" data-b="${c.book_id}" data-max="${t.remaining}" data-need="${c.need}">Max</button></span></div>`).join('') || '<div class="muted" style="font-size:12px;margin-top:6px">Aucun lot en stock.</div>'}
        <div class="row" style="justify-content:space-between;margin-top:6px;flex-wrap:nowrap"><span class="muted" style="font-size:12px">Hors stock (non tracé)</span><input type="number" min="0" style="width:56px;padding:4px 6px" value="${l.alloc[c.book_id + '|none'] || 0}" data-a="${i}" data-k="${c.book_id}|none"></div></div>` }).join('')}</div>`}).join('') ||
      '<div class="empty"><b>🛒</b>Glissez un livre ici<br>ou cliquez sur une carte</div>';
    $('#tot').textContent = eur(S.cart.reduce((s, l) => s + l.qty * l.price, 0));
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
    const r = await api('/api/sales', 'POST', { date: $('#sdate').value, payment: $('#pay').value, lines: S.cart.map(l => ({ book_id: l.id, qty: l.qty, unit_price: l.price,
      allocations: Object.entries(l.alloc).filter(([, q]) => q > 0).map(([k, q]) => { const [bid, lid] = k.split('|'); return { book_id: +bid, lot_id: lid === 'none' ? null : +lid, qty: q } }) })) });
    toast(`Vente enregistrée : ${eur(r.total)}`);
    S.cart = []; await loadRef(); draw(); cart();
  });
  draw(); cart();
};

/* ---- Stock ---- */
VIEWS.stock = async () => {
  $('#topActions').innerHTML = '<button class="btn" id="newLot">＋ Réception de stock</button>';
  $('#view').innerHTML = `<div class="toolbar"><input class="search" id="q" placeholder="Filtrer…"><select id="fo"><option value="">Toutes origines</option>${S.owners.map(o => `<option>${esc(o.name)}</option>`).join('')}</select>
  <select id="fs"><option value="">Tout le stock</option><option value="low">Stock bas</option><option value="out">Ruptures</option><option value="ok">Disponibles</option></select></div>
  <div class="card" style="padding:0"><div class="scroll" style="max-height:calc(100vh - 220px);overflow:auto"><table><thead><tr><th>Titre</th><th>Code</th><th>Origine du stock</th><th class="num">Prix</th><th class="num">Valeur</th><th class="num">Stock</th></tr></thead><tbody id="tb"></tbody></table></div></div>`;
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
  <table><thead><tr><th>Date</th><th>Origine</th><th class="num">Reçu</th><th class="num">Restant</th><th>Règle</th><th></th></tr></thead><tbody>
  ${lots.map(l => `<tr><td>${l.date}</td><td><span class="chip"><i style="background:${l.color}"></i>${esc(l.owner)}</span></td><td class="num">${l.qty_in}</td><td class="num"><b>${l.remaining}</b></td>
  <td class="muted">${l.unit_cost != null ? 'acquis ' + eur(l.unit_cost) + '/u' : (l.reverse_pct ?? l.o_pct) + ' % reversé'}</td><td class="num"><button class="btn ghost sm" data-adj="${l.id}">Ajuster / Retour</button></td></tr>`).join('') || '<tr><td colspan=6 class="muted">Aucune entrée</td></tr>'}</tbody></table>
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
  modal(`<h2>${b.id ? 'Modifier' : 'Nouveau'} ${b.is_pack ? 'pack' : 'livre'}</h2><div class="form">${f('code', 'Code (ISBN)')}${f('title', 'Titre')}${f('series', 'Série')}${f('volume', 'Volume')}${f('author', 'Auteur')}${f('publisher', 'Éditeur')}
  <label class="f">Catégorie<select id="f_category">${['Standard', 'Bible', 'Pack', 'Autre'].map(c => `<option ${b.category === c ? 'selected' : ''}>${c}</option>`).join('')}</select></label>${f('type', 'Type (Souple/Rigide…)')}${f('location', 'Emplacement')}${f('price', 'Prix de vente €', 'number')}${f('min_stock', 'Seuil d\'alerte', 'number')}</div>
  <div class="actions">${b.id ? '<button class="btn bad" id="del">Archiver</button>' : ''}<button class="btn ghost" onclick="closeModal()">Annuler</button><button class="btn" id="ok">Enregistrer</button></div>`, m => {
    $('#ok', m).onclick = safe(async () => {
      const g = k => $('#f_' + k, m).value;
      const body = { code: g('code'), title: g('title'), series: g('series') || null, volume: g('volume') || null, author: g('author') || null, publisher: g('publisher') || null, category: g('category'), type: g('type') || null, location: g('location') || null, price: +g('price') || 0, min_stock: +g('min_stock') || 0, is_pack: b.is_pack || 0 };
      if (!body.code || !body.title) throw new Error('Code et titre requis');
      b.id ? await api(`/api/books/${b.id}`, 'PUT', body) : await api('/api/books', 'POST', body);
      closeModal(); toast('Enregistré'); go('catalog');
    });
    const d = $('#del', m); if (d) d.onclick = safe(async () => { if (confirm('Archiver cet article ?')) { await api(`/api/books/${b.id}`, 'DELETE'); closeModal(); go('catalog') } });
  });
}
function packModal(p) {
  let items = (p.items || []).map(i => ({ ...i }));
  modal(`<h2>🎁 ${esc(p.title)}</h2><p class="muted" style="margin-bottom:10px">Glissez des livres dans la composition. Le prix du pack (${eur(p.price)}) est réparti sur les composants au prorata de leurs prix publics.</p>
  <div class="grid g-eq"><div><input id="pq" class="search" placeholder="Chercher un livre…" style="width:100%;margin-bottom:8px"><div id="pl" style="max-height:300px;overflow:auto;display:flex;flex-direction:column;gap:5px"></div></div>
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
  $('#topActions').innerHTML = '<div class="row"><button class="btn ghost" id="np">🎁 Nouveau pack</button><button class="btn" id="nb">＋ Nouveau livre</button></div>';
  $('#nb').onclick = () => bookForm(); $('#np').onclick = () => bookForm({ is_pack: 1, category: 'Pack', code: 'PACK-' + String(S.books.filter(b => b.is_pack).length + 1).padStart(3, '0') });
  $('#view').innerHTML = `<div class="toolbar"><input class="search" id="q" placeholder="Rechercher…"></div><div class="card" style="padding:0"><div class="scroll" style="max-height:calc(100vh - 220px);overflow:auto"><table><thead><tr><th>Titre</th><th>Code</th><th>Auteur</th><th>Éditeur</th><th>Type</th><th class="num">Prix</th><th></th></tr></thead><tbody id="tb"></tbody></table></div></div>`;
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
  $('#view').innerHTML = `<div class="card" style="padding:0"><div class="scroll" style="max-height:calc(100vh - 150px);overflow:auto"><table><thead><tr><th>Date</th><th>Détail</th><th>Paiement</th><th class="num">Qté</th><th class="num">Total</th><th></th></tr></thead><tbody>
  ${rows.map(s => `<tr><td>${s.date}</td><td style="max-width:520px">${esc(s.detail)}</td><td>${esc(s.payment)}</td><td class="num">${s.qty}</td><td class="num"><b>${eur(s.total)}</b></td><td class="num"><button class="btn bad sm" data-id="${s.id}">Annuler</button></td></tr>`).join('') || '<tr><td colspan=6 class="muted">Aucune vente</td></tr>'}</tbody></table></div></div>`;
  $('#view').onclick = safe(async e => { const b = e.target.closest('button[data-id]'); if (b && confirm('Annuler cette vente ? Le stock sera restitué.')) { await api(`/api/sales/${b.dataset.id}`, 'DELETE'); toast('Vente annulée'); go('sales') } });
};

/* ---- Reversements ---- */
VIEWS.settle = async () => {
  const os = await api('/api/settlements');
  $('#view').innerHTML = `<div class="grid g-eq">${os.map(o => `<div class="card owner-card" style="--c:${o.color}"><h3>${esc(o.name)} <span class="chip">${o.kind === 'maison_mere' ? 'Maison mère' : 'Église locale'}</span></h3>
  <div class="grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:14px"><div><div class="muted">CA généré</div><div class="big" style="font-size:22px">${eur(o.revenue)}</div></div><div><div class="muted">Dû à l'origine</div><div class="big" style="font-size:22px">${eur(o.due)}</div></div><div><div class="muted">Marge gardée</div><div class="big" style="font-size:22px;color:var(--good)">${eur(o.margin)}</div></div></div>
  <div class="row" style="justify-content:space-between;padding:12px;border-radius:12px;background:var(--panel2)"><div><div class="muted">Reste à régler</div><div class="big" style="color:${o.remaining > 0.005 ? 'var(--warn)' : 'var(--good)'}">${eur(o.remaining)}</div></div><button class="btn good" data-o="${o.id}" data-r="${Math.max(0, o.remaining).toFixed(2)}">Enregistrer un règlement</button></div>
  <div style="margin-top:12px">${o.history.map(h => `<div class="tl"><span>${h.date} ${esc(h.note || '')}</span><b>− ${eur(h.amount)}</b></div>`).join('')}</div>
  <p class="muted" style="margin-top:10px;font-size:12px">${o.qty} exemplaires vendus · règle par défaut : ${o.reverse_pct} % reversé</p></div>`).join('')}</div>`;
  $('#view').onclick = e => {
    const b = e.target.closest('button[data-o]'); if (!b) return;
    modal(`<h2>Règlement</h2><div class="form"><label class="f">Montant €<input id="am" type="number" step="0.01" value="${b.dataset.r}"></label><label class="f">Date<input id="dt" type="date" value="${today()}"></label><label class="f full">Note<input id="nt" placeholder="Virement, chèque n°…"></label></div><div class="actions"><button class="btn ghost" onclick="closeModal()">Annuler</button><button class="btn good" id="ok">Valider</button></div>`, m => {
      $('#ok', m).onclick = safe(async () => { await api('/api/settlements', 'POST', { owner_id: +b.dataset.o, amount: +$('#am', m).value, date: $('#dt', m).value, note: $('#nt', m).value }); closeModal(); toast('Règlement enregistré'); go('settle') });
    });
  };
};

/* ---- Réservations ---- */
VIEWS.orders = async () => {
  $('#topActions').innerHTML = '<button class="btn" id="nr">＋ Nouvelle réservation</button>';
  const rows = await api('/api/reservations');
  $('#view').innerHTML = `<div class="card" style="padding:0"><table><thead><tr><th>Client</th><th>Téléphone</th><th>Titre</th><th class="num">Qté</th><th>Statut</th><th></th></tr></thead><tbody>
  ${rows.map(r => `<tr><td>${esc(r.name)}</td><td>${esc(r.phone || '')}</td><td>${esc(r.title)}</td><td class="num">${r.qty}</td><td><span class="badge ${r.status === 'Servie' ? 'b-ok' : 'b-low'}">${esc(r.status)}</span></td>
  <td class="num"><button class="btn ghost sm" data-s="${r.id}">${r.status === 'Servie' ? 'Rouvrir' : '✔ Servie'}</button> <button class="btn bad sm" data-d="${r.id}">✕</button></td></tr>`).join('') || '<tr><td colspan=6 class="muted">Aucune réservation</td></tr>'}</tbody></table></div>`;
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
  $('#view').innerHTML = `<div class="grid g-eq"><div class="card"><h3>📥 Importer un fichier Excel</h3><div class="drop" id="drop"><div style="font-size:38px">📄</div><b>Glissez votre fichier .xlsx ici</b><div class="muted">ou cliquez pour parcourir<br>(Catalogue STD, Catalogue PACK, Livraisons, Ventes, Commande)</div></div><input type="file" id="file" accept=".xlsx" hidden>
  <label class="row muted" style="margin-top:12px"><input type="checkbox" id="rep" checked> Remplacer les données actuelles (une copie de sécurité est faite avant)</label><div id="rep-out" style="margin-top:10px"></div></div>
  <div class="card"><h3>📤 Export &amp; sauvegardes</h3><div class="row"><a class="btn" href="/api/export" download>Exporter tout en Excel</a><button class="btn ghost" id="bk">Sauvegarder maintenant</button></div>
  <p class="muted" style="margin-top:14px;line-height:1.7">Un <b>fichier Excel miroir</b> est mis à jour automatiquement après chaque modification :<br><code>${esc(info.mirror)}</code><br>Une archive datée (Excel + base) est créée chaque jour dans :<br><code>${esc(info.backups)}</code><br>La base <b>librairie.db</b> (SQLite) est lisible avec LibreOffice Base, DB Browser for SQLite, etc.</p></div></div>
  <div class="card" style="margin-top:16px"><h3>🏛️ Origines du stock &amp; règles de reversement <button class="btn sm" id="no">＋ Ajouter</button></h3><table><thead><tr><th>Nom</th><th>Type</th><th class="num">% reversé</th><th class="num">Ordre (import Excel uniquement)</th><th></th></tr></thead><tbody>
  ${S.owners.map(o => `<tr><td><span class="chip"><i style="background:${o.color}"></i>${esc(o.name)}</span></td><td>${o.kind === 'maison_mere' ? 'Maison mère (dépôt)' : 'Église locale (acquis)'}</td><td class="num">${o.reverse_pct} %</td><td class="num">${o.priority}</td><td class="num"><button class="btn ghost sm" data-o="${o.id}">Modifier</button></td></tr>`).join('')}</tbody></table>
  <p class="muted" style="margin-top:10px;font-size:12px;line-height:1.6"><b>% reversé</b> = part du prix de vente rendue à l'origine (100 = tout le prix revient à la maison mère ; 0 = stock acquis, marge entière gardée). Pour un lot acquis avec marge négociée, indiquez le <i>coût unitaire</i> à la réception du stock. <b>Ordre</b> : n'est utilisé que pour répartir les ventes de l'<i>import Excel historique</i>. En caisse, c'est toujours vous qui choisissez l'origine de chaque exemplaire.</p></div>`;
  const send = safe(async f => {
    if (!f) return; const fd = new FormData(); fd.append('file', f);
    const r = await api(`/api/import?replace=${$('#rep').checked}`, 'POST', fd);
    $('#rep-out').innerHTML = `<div class="toast ok">✔ ${r.books} livres, ${r.packs} packs, ${r.lots} entrées de stock, ${r.sales} ventes, ${r.reservations} réservations importés.${r.skipped.length ? `<details><summary>${r.skipped.length} ligne(s) ignorée(s)</summary>${r.skipped.map(esc).join('<br>')}</details>` : ''}</div>`;
    await loadRef();
  });
  const dz = $('#drop'); dz.onclick = () => $('#file').click(); $('#file').onchange = e => send(e.target.files[0]);
  dz.ondragover = e => { e.preventDefault(); dz.classList.add('over') }; dz.ondragleave = () => dz.classList.remove('over');
  dz.ondrop = e => { e.preventDefault(); dz.classList.remove('over'); send(e.dataTransfer.files[0]) };
  $('#bk').onclick = safe(async () => { await api('/api/backup', 'POST'); toast('Sauvegarde créée') });
  const ownerForm = (o = {}) => modal(`<h2>${o.id ? 'Modifier' : 'Nouvelle'} origine</h2><div class="form"><label class="f full">Nom<input id="n" value="${esc(o.name || '')}"></label>
    <label class="f">Type<select id="k"><option value="maison_mere" ${o.kind === 'maison_mere' ? 'selected' : ''}>Maison mère (dépôt)</option><option value="locale" ${o.kind === 'locale' ? 'selected' : ''}>Église locale (acquis)</option></select></label>
    <label class="f">% reversé<input id="r" type="number" value="${o.reverse_pct ?? 100}"></label><label class="f">Ordre (import Excel uniquement)<input id="p" type="number" value="${o.priority ?? 5}"></label><label class="f">Couleur<input id="c" type="color" value="${o.color || '#6c8cff'}"></label></div>
    <div class="actions"><button class="btn ghost" onclick="closeModal()">Annuler</button><button class="btn" id="ok">Enregistrer</button></div>`, m => {
    $('#ok', m).onclick = safe(async () => { const body = { name: $('#n', m).value, kind: $('#k', m).value, reverse_pct: +$('#r', m).value, priority: +$('#p', m).value, color: $('#c', m).value }; o.id ? await api(`/api/owners/${o.id}`, 'PUT', body) : await api('/api/owners', 'POST', body); closeModal(); go('data') });
  });
  $('#no').onclick = () => ownerForm(); $('#view').onclick = e => { const b = e.target.closest('button[data-o]'); if (b) ownerForm(S.owners.find(x => x.id == b.dataset.o)) };
};

go('dashboard');
