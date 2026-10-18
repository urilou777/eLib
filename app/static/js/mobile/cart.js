/* Librairie Mobile - Gestion du Panier, Origines, Multi-Paiement & Profil Vente */
'use strict';
import { $, el, eur, toast, beep, createStatsIcon, esc } from './core.js';
import { state } from './state.js';
import { api } from './api.js';
import { saveActiveCart, logMobileLiveActivity, clearLiveCartSync } from './network.js';
import { openUserModal } from './pairing.js';
import { openMobileBookStats } from './book_stats.js';

export function getItemOwner(item) {
  if (item.book.is_pack) return 'Cité Royale';
  if (item.lot === undefined || item.lot === null || item.lot === 'none') return 'À préciser';
  const l = (item.book.lots || []).find(x => x.id === item.lot);
  return (l && l.owner) ? l.owner.trim() : 'Autre';
}

export function getCartByOrigin() {
  const groups = {};
  for (const item of state.cart) {
    const owner = getItemOwner(item);
    if (!groups[owner]) {
      groups[owner] = { owner, items: [], total: 0, count: 0 };
    }
    groups[owner].items.push(item);
    groups[owner].total += item.qty * item.book.price;
    groups[owner].count += item.qty;
  }
  const list = Object.values(groups);
  list.sort((a, b) => {
    const aIsCR = a.owner.toLowerCase() === 'cité royale' ? 1 : 0;
    const bIsCR = b.owner.toLowerCase() === 'cité royale' ? 1 : 0;
    if (aIsCR !== bIsCR) return bIsCR - aIsCR;
    const aIsICC = a.owner.toLowerCase().includes('icc') ? 1 : 0;
    const bIsICC = b.owner.toLowerCase().includes('icc') ? 1 : 0;
    return bIsICC - aIsICC;
  });
  return list;
}

export function getDefaultPaymentForOwner(owner) {
  const ow = (owner || '').toLowerCase();
  if (ow === 'cité royale') return 'CB';
  return 'Espèces';
}

export function lotRemaining(item) {
  if (item.book.is_pack) return item.book.stock != null ? item.book.stock : 0;
  if (item.lot === undefined || item.lot === null || item.lot === 'none') return 0;
  const l = (item.book.lots || []).find(x => x.id === item.lot);
  return l ? l.remaining : 0;
}

export function defaultLotForBook(book) {
  const lots = (book.lots || []).filter(l => l.remaining > 0);
  if (!lots.length) return undefined;
  if (lots.length === 1) return lots[0].id;
  const cr = lots.find(l => (l.owner || '').trim().toLowerCase() === 'cité royale');
  return cr ? cr.id : lots[0].id;
}

export function checkAndShowPackUpsell(book) {
  const packs = (book.suggested_packs || []).filter(p => p.saving > 0);
  if (!packs.length) {
    hidePackUpsell();
    return;
  }
  const pack = packs.find(p => p.stock > 0) || packs[0];
  state.currentUpsellContext = { singleBook: book, pack };

  const card = $('#packUpsellCard');
  if (!card) return;
  $('#packUpsellTitle').textContent = pack.title;
  $('#packUpsellOldPrice').textContent = eur(pack.separate_price);
  $('#packUpsellPrice').textContent = eur(pack.price);
  $('#packUpsellOther').textContent = pack.other_items || 'Articles du pack';
  $('#packUpsellSavingBadge').textContent = `Éco ${eur(pack.saving)}`;
  card.style.display = 'block';
}

export function hidePackUpsell() {
  state.currentUpsellContext = null;
  const card = $('#packUpsellCard');
  if (card) card.style.display = 'none';
}

export function addPackToCart(pack) {
  const stock = pack.stock != null ? pack.stock : 0;
  if (stock <= 0) {
    toast(`Stock épuisé (0 dispo) pour ce pack. Vente impossible.`, 'err');
    return;
  }
  beep();
  const ex = state.cart.find(i => i.book.id === pack.id);
  if (ex) {
    if (ex.qty + 1 > stock) toast(`Stock maximum atteint (${stock} ex.) pour ce pack`, 'warn');
    else ex.qty++;
  } else {
    state.cart.push({ book: pack, qty: 1, lot: 'pack' });
  }
  toast('Pack ajouté : ' + pack.title);
  saveActiveCart({ type: 'pack_added', title: pack.title, price: pack.price });
  renderCart();
}

export function addToCart(book) {
  if (book.is_pack) {
    addPackToCart(book);
    return;
  }
  const totalStock = (book.lots || []).filter(l => l.remaining > 0).reduce((s, l) => s + l.remaining, 0);
  if (totalStock <= 0) {
    toast(`Stock épuisé (0 ex. disponible) pour « ${book.title} ». Vente impossible.`, 'err');
    return;
  }
  beep();
  const defLot = defaultLotForBook(book);
  const ex = state.cart.find(i => i.book.id === book.id && (i.lot === defLot || i.lot === undefined));
  if (ex) {
    if (ex.lot === undefined && defLot !== undefined) ex.lot = defLot;
    if (ex.qty + 1 > lotRemaining(ex)) {
      toast(`Stock disponible atteint (${lotRemaining(ex)} ex.) pour « ${book.title} ».`, 'warn');
      return;
    }
    ex.qty++;
  } else {
    state.cart.push({ book, qty: 1, lot: defLot });
  }
  toast('Ajouté : ' + book.title);
  saveActiveCart({ type: 'book_added', title: book.title, price: book.price });
  renderCart();
  checkAndShowPackUpsell(book);
}

export function openMultiPayModal(owner, total) {
  state.activeMpOwner = owner;
  state.activeMpTotal = total;
  const badge = $('#mpOriginBadge');
  if (badge) badge.textContent = owner;
  const tVal = $('#mpTotalVal');
  if (tVal) tVal.textContent = eur(total);
  
  if ((owner || '').toLowerCase() === 'cité royale') {
    state.mpMode1 = 'CB';
    state.mpMode2 = 'Espèces';
  } else {
    state.mpMode1 = 'Espèces';
    state.mpMode2 = 'CB';
  }

  const existing = state.originPayments[owner]?.parts;
  if (existing && existing.length >= 2) {
    state.mpMode1 = existing[0].payment;
    state.mpMode2 = existing[1].payment;
    $('#mpAmount1').value = existing[0].amount.toFixed(2);
    $('#mpAmount2').value = existing[1].amount.toFixed(2);
  } else {
    const half = Math.round((total / 2) * 100) / 100;
    $('#mpAmount1').value = half.toFixed(2);
    $('#mpAmount2').value = (Math.round((total - half) * 100) / 100).toFixed(2);
  }

  renderMpModes();
  updateMpCalculations();
  $('#multiPayModal').hidden = false;
}

export function closeMultiPayModal() {
  $('#multiPayModal').hidden = true;
  state.activeMpOwner = null;
}

export function renderMpModes() {
  const m1El = $('#mpModes1');
  const m2El = $('#mpModes2');
  if (!m1El || !m2El) return;
  const available = state.payOptions.length ? state.payOptions : ['Espèces', 'CB', 'Wero'];
  
  m1El.replaceChildren(...available.map(p => el('button', {
    type: 'button',
    class: 'chip' + (state.mpMode1 === p ? ' on' : ''),
    style: 'flex:1;justify-content:center;padding:5px 4px;font-size:11.5px',
    onclick: () => {
      state.mpMode1 = p;
      if (state.mpMode2 === p) {
        const other = available.find(x => x !== p);
        if (other) state.mpMode2 = other;
      }
      renderMpModes();
      updateMpCalculations();
    }
  }, p)));

  m2El.replaceChildren(...available.map(p => el('button', {
    type: 'button',
    class: 'chip' + (state.mpMode2 === p ? ' on' : ''),
    style: 'flex:1;justify-content:center;padding:5px 4px;font-size:11.5px',
    onclick: () => {
      state.mpMode2 = p;
      if (state.mpMode1 === p) {
        const other = available.find(x => x !== p);
        if (other) state.mpMode1 = other;
      }
      renderMpModes();
      updateMpCalculations();
    }
  }, p)));
}

export function updateMpCalculations() {
  const a1 = parseFloat($('#mpAmount1').value) || 0;
  const rem = Math.max(0, Math.round((state.activeMpTotal - a1) * 100) / 100);
  $('#mpAmount2').value = rem.toFixed(2);
  $('#mpRemainderBadge').textContent = 'Complément : ' + eur(rem);

  const btnApply = $('#btnApplyMultiPay');
  const hint = $('#mpHint');
  
  if (a1 <= 0) {
    btnApply.disabled = true;
    hint.textContent = 'Le 1er montant doit être supérieur à 0 €';
  } else if (rem <= 0) {
    btnApply.disabled = true;
    hint.textContent = 'Le 1er montant ne peut pas dépasser le total';
  } else if (state.mpMode1 === state.mpMode2) {
    btnApply.disabled = true;
    hint.textContent = 'Choisissez deux modes différents';
  } else {
    btnApply.disabled = false;
    hint.textContent = '';
  }
}

/* Composant factorisé pour les éléments du panier mobile */
export function renderMobileCartItem(item, idx) {
  const b = item.book;
  if (b.is_pack) {
    return el('div', { class: 'cart-item pack-cart-item' },
      el('div', { class: 'ci-top' },
        el('div', {},
          el('div', { class: 'ci-title' },
            el('span', { class: 'badge b-pack', style: 'background:linear-gradient(135deg, #9333ea, #c026d3);color:#fff;font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;margin-right:6px' }, 'PACK'),
            b.title
          ),
          el('div', { class: 'muted', style: 'font-size:11.5px;margin-top:2px' },
            `${eur(b.price)} / pack · ${(b.items || []).map(i => i.title).join(' + ')}`
          )
        ),
        el('div', { class: 'qty' },
          el('button', { type: 'button', text: '−', onclick: () => {
            item.qty--;
            const isRemoved = item.qty <= 0;
            if (isRemoved) state.cart.splice(idx, 1);
            saveActiveCart(isRemoved ? { type: 'book_removed', title: b.title } : { type: 'book_qty', title: b.title, qty: item.qty });
            renderCart();
          } }),
          el('b', { text: item.qty }),
          el('button', { type: 'button', text: '+', onclick: () => {
            if (item.qty + 1 > (b.stock || 999)) toast('Stock pack atteint', 'warn');
            else {
              item.qty++;
              saveActiveCart({ type: 'book_qty', title: b.title, qty: item.qty });
              renderCart();
            }
          } })
        )
      ),
      el('div', { class: 'lots', style: 'display:flex;align-items:center;justify-content:space-between;padding:3px 0' },
        el('span', { style: 'font-size:11px;color:#c084fc;font-weight:600', text: `📦 Composition : ${b.items ? b.items.length : 2} livres groupés (Cité Royale)` }),
        el('button', {
          class: 'chip btn-m-stats',
          type: 'button',
          title: 'Statistiques du pack',
          onclick: (e) => { e.stopPropagation(); openMobileBookStats(b.id); }
        },
          createStatsIcon(),
          el('span', { text: 'Stats' })
        )
      )
    );
  }

  const availableLots = (b.lots || []).filter(l => l.remaining > 0);
  const lots = availableLots.map(l => el('button', {
    class: 'chip' + (item.lot === l.id ? ' on' : ''), type: 'button',
    onclick: () => { item.lot = l.id; item.qty = Math.min(item.qty, l.remaining); renderCart(); }
  }, el('i', { style: 'background:' + (/^#[0-9a-fA-F]{3,8}$/.test(l.color || '') ? l.color : '#8892b0') }),
     `${l.owner} · dispo ${l.remaining}`));

  if (!availableLots.length) {
    lots.push(el('span', { class: 'chip', style: 'border-color:var(--bad);color:var(--bad);cursor:default', text: 'Stock épuisé (0 dispo)' }));
  }
  lots.push(el('button', {
    class: 'chip btn-m-stats',
    type: 'button',
    title: 'Statistiques & tendances de vente',
    onclick: (e) => { e.stopPropagation(); openMobileBookStats(b.id); }
  },
    createStatsIcon(),
    el('span', { text: 'Stats' })
  ));

  return el('div', { class: 'cart-item' + (item.lot === undefined ? ' todo' : '') },
    el('div', { class: 'ci-top' },
      el('div', {}, el('div', { class: 'ci-title', text: b.title + (b.volume ? ' · Vol. ' + b.volume : '') }),
        el('div', { class: 'muted', text: eur(b.price) + ' / unité' })),
      el('div', { class: 'qty' },
        el('button', { type: 'button', text: '−', onclick: () => {
          item.qty--;
          const isRemoved = item.qty <= 0;
          if (isRemoved) state.cart.splice(idx, 1);
          saveActiveCart(isRemoved ? { type: 'book_removed', title: b.title } : { type: 'book_qty', title: b.title, qty: item.qty });
          renderCart();
        } }),
        el('b', { text: item.qty }),
        el('button', { type: 'button', text: '+', onclick: () => {
          const maxAvail = lotRemaining(item);
          if (item.qty + 1 > maxAvail) {
            toast(`Stock maximum atteint (${maxAvail} ex.) pour ce lot`, 'warn');
          } else {
            item.qty++;
            saveActiveCart({ type: 'book_qty', title: b.title, qty: item.qty });
            renderCart();
          }
        } }))),
    el('div', { class: 'lots' }, lots),
    item.lot === undefined ? el('div', { class: 'hint', text: 'Touchez l\'origine de cet exemplaire' }) : null);
}

export function renderCart() {
  const count = state.cart.reduce((s, i) => s + i.qty, 0);
  const total = state.cart.reduce((s, i) => s + i.qty * i.book.price, 0);
  $('#cartCount').textContent = count;
  $('#totalVal').textContent = eur(total);
  updateMobileStandbyUI();

  const list = $('#cartItems');
  if (!state.cart.length) {
    list.replaceChildren(el('div', { class: 'muted', style: 'text-align:center;padding:18px', text: 'Visez le code-barres d\'un livre pour commencer.' }));
  } else {
    list.replaceChildren(...state.cart.map(renderMobileCartItem));
  }

  const origins = getCartByOrigin();
  const singleRow = $('#singleOriginRow');
  const splitCont = $('#splitOriginsContainer');
  const payChipsEl = $('#payChips');
  const availablePays = state.payOptions.length ? state.payOptions : ['Espèces', 'CB', 'Wero'];

  const validOwners = new Set(origins.map(o => o.owner));
  for (const k of Object.keys(state.originPayments)) {
    if (k !== '_default' && !validOwners.has(k)) {
      delete state.originPayments[k];
    }
  }

  const fAmt = a => (a % 1 === 0 ? a.toFixed(0) : a.toFixed(2).replace('.', ',')) + ' €';
  const fPay = p => (p === 'Espèces' ? 'Esp.' : p);

  if (origins.length <= 1) {
    if (singleRow) singleRow.style.display = 'block';
    if (splitCont) splitCont.style.display = 'none';

    const currentOwner = origins[0] ? origins[0].owner : '_default';
    if (!state.originPayments[currentOwner]) {
      state.originPayments[currentOwner] = { method: getDefaultPaymentForOwner(currentOwner), parts: null };
    }
    const currentPay = state.originPayments[currentOwner];

    if (currentPay.parts && currentPay.parts.length >= 2) {
      const sumParts = currentPay.parts.reduce((s, p) => s + p.amount, 0);
      if (Math.abs(sumParts - total) > 0.01) {
        currentPay.parts = null;
      }
    }

    if (payChipsEl) {
      const chips = availablePays.map(p => el('button', {
        type: 'button',
        class: 'chip' + (!currentPay.parts && currentPay.method === p ? ' on' : ''),
        style: 'flex:1;justify-content:center;padding:7px 2px;font-size:12px;white-space:nowrap',
        onclick: () => {
          state.originPayments[currentOwner] = { method: p, parts: null };
          saveActiveCart({ type: 'payment_selected', method: p, owner: currentOwner });
          renderCart();
        }
      }, p));

      const mpSumm = $('#multiPaySummary');
      if (currentPay.parts && currentPay.parts.length >= 2) {
        const p1 = currentPay.parts[0];
        const p2 = currentPay.parts[1];
        const mpText = `⚡ ${fAmt(p1.amount)} ${fPay(p1.payment)} + ${fAmt(p2.amount)} ${fPay(p2.payment)} ✎`;
        if (mpSumm) {
          mpSumm.textContent = mpText;
          mpSumm.style.display = 'inline-flex';
          mpSumm.onclick = () => openMultiPayModal(currentOwner, total);
        }
        chips.push(el('button', {
          type: 'button',
          class: 'chip multi-on',
          style: 'flex:1;justify-content:center;padding:7px 2px;font-size:12px;white-space:nowrap',
          title: 'Modifier le paiement combiné : ' + mpText,
          onclick: () => openMultiPayModal(currentOwner, total)
        }, '✓ Multi'));
      } else {
        if (mpSumm) mpSumm.style.display = 'none';
        chips.push(el('button', {
          type: 'button',
          class: 'chip',
          style: 'flex:1;justify-content:center;padding:7px 2px;font-size:12px;white-space:nowrap;color:var(--mut)',
          title: 'Combiner deux modes de paiement',
          onclick: () => {
            if (!total) return toast('Ajoutez d\'abord un livre au panier', 'warn');
            openMultiPayModal(currentOwner, total);
          }
        }, '＋ Multi'));
      }
      payChipsEl.replaceChildren(...chips);
    }
    $('#btnValidate').textContent = total > 0 ? `Valider (${eur(total)})` : 'Valider';
  } else {
    if (singleRow) singleRow.style.display = 'none';
    const mpSumm = $('#multiPaySummary');
    if (mpSumm) mpSumm.style.display = 'none';
    if (splitCont) splitCont.style.display = 'flex';

    if (splitCont) {
      splitCont.replaceChildren(...origins.map(g => {
        if (!state.originPayments[g.owner]) {
          state.originPayments[g.owner] = { method: getDefaultPaymentForOwner(g.owner), parts: null };
        }
        const payState = state.originPayments[g.owner];
        if (payState.parts && payState.parts.length >= 2) {
          const sumParts = payState.parts.reduce((s, p) => s + p.amount, 0);
          if (Math.abs(sumParts - g.total) > 0.01) {
            payState.parts = null;
          }
        }

        const isCR = g.owner.toLowerCase() === 'cité royale';
        const isICC = g.owner.toLowerCase().includes('icc');
        const cardClass = isCR ? 'split-card cr' : isICC ? 'split-card icc' : 'split-card other';
        const icon = isCR ? '🏰 ' : isICC ? '🕊️ ' : '📦 ';

        const chips = availablePays.map(p => el('button', {
          type: 'button',
          class: 'chip' + (!payState.parts && payState.method === p ? ' on' : ''),
          style: 'flex:1;justify-content:center;padding:5px 2px;font-size:11.5px;white-space:nowrap',
          onclick: () => {
            state.originPayments[g.owner] = { method: p, parts: null };
            saveActiveCart({ type: 'payment_selected', method: p, owner: g.owner });
            renderCart();
          }
        }, p));

        if (payState.parts && payState.parts.length >= 2) {
          chips.push(el('button', {
            type: 'button',
            class: 'chip multi-on',
            style: 'flex:1;justify-content:center;padding:5px 2px;font-size:11.5px;white-space:nowrap',
            title: 'Modifier le paiement combiné',
            onclick: () => openMultiPayModal(g.owner, g.total)
          }, '✓ Multi'));
        } else {
          chips.push(el('button', {
            type: 'button',
            class: 'chip',
            style: 'flex:1;justify-content:center;padding:5px 2px;font-size:11.5px;white-space:nowrap;color:var(--mut)',
            onclick: () => openMultiPayModal(g.owner, g.total)
          }, '＋ Multi'));
        }

        const headRight = el('div', {
          style: 'display:flex;align-items:center;gap:6px;cursor:' + (payState.parts ? 'pointer' : 'default'),
          onclick: payState.parts ? () => openMultiPayModal(g.owner, g.total) : null
        },
          payState.parts && payState.parts.length >= 2
            ? el('span', { style: 'font-size:10px;color:#c4b5fd;font-weight:700;background:rgba(99,102,241,0.15);border:1px solid rgba(99,102,241,0.3);border-radius:5px;padding:2px 5px;white-space:nowrap' },
                `⚡ ${fAmt(payState.parts[0].amount)} ${fPay(payState.parts[0].payment)} + ${fAmt(payState.parts[1].amount)} ${fPay(payState.parts[1].payment)} ✎`)
            : null,
          el('span', { style: 'font-size:13px;font-weight:800;color:var(--good)' }, eur(g.total))
        );

        return el('div', { class: cardClass },
          el('div', { class: 'split-head' },
            el('span', { style: 'display:flex;align-items:center;gap:4px' },
              icon + g.owner,
              el('span', { style: 'font-size:10px;color:var(--mut);font-weight:400' }, `(${g.count} ex.)`)),
            headRight),
          el('div', { class: 'split-chips' }, chips));
      }));
    }
    $('#btnValidate').textContent = `Valider les ${origins.length} ventes (${eur(total)})`;
  }

  const missingLot = state.cart.some(i => i.lot === undefined);
  const missingPay = origins.some(g => !state.originPayments[g.owner] || (!state.originPayments[g.owner].method && !state.originPayments[g.owner].parts));
  $('#btnValidate').disabled = !state.cart.length || missingLot || missingPay;
  $('#validHint').textContent = !state.cart.length ? '' : missingLot ? 'Choisissez l\'origine de chaque livre' : missingPay ? 'Choisissez le mode de paiement' : '';
  saveActiveCart();
}

export function updateMobileStandbyUI() {
  const raw = localStorage.getItem('librairie_mobile_standby_cart');
  const banner = $('#mStandbyBanner');
  const info = $('#mStandbyBannerInfo');
  const btnStby = $('#mBtnStandby');
  if (!banner || !btnStby) return;

  if (raw) {
    try {
      const data = JSON.parse(raw);
      banner.style.display = 'flex';
      if (info) info.textContent = `${data.qty || 0} livre${(data.qty || 0) > 1 ? 's' : ''} · ${data.total || '0,00 €'}`;
      btnStby.style.display = 'none';
    } catch (err) {
      localStorage.removeItem('librairie_mobile_standby_cart');
      banner.style.display = 'none';
      btnStby.style.display = state.cart.length > 0 ? 'inline-flex' : 'none';
    }
  } else {
    banner.style.display = 'none';
    btnStby.style.display = state.cart.length > 0 ? 'inline-flex' : 'none';
  }
}

export async function loadPayOptions() {
  try {
    const o = await api('/api/options');
    state.payOptions = (o.payment || []).map(p => (p.label === 'PayPal POS (CB)' || p.label.toLowerCase().includes('paypal') ? 'CB' : p.label));
    state.dbPublishers = (o.publisher || []).map(p => p.label);
    state.dbAuthors = o.authors || [];
    const dl = $('#dl_nb_publishers');
    if (dl && state.dbPublishers.length) {
      dl.innerHTML = state.dbPublishers.map(p => `<option value="${esc(p)}">`).join('');
    }
  } catch (e) { state.payOptions = []; }
  if (!state.payOptions.length) state.payOptions = ['Espèces', 'CB', 'Wero'];
  state.payOptions = Array.from(new Set(state.payOptions));
  renderCart();
}

let mDemoTimer = null;

export function getMobileProfileSummary() {
  const parts = [];
  if (state.mGender === 'Couple') parts.push('Couple 💜');
  else if (state.mGender) parts.push(state.mGender);

  const ageMap = {
    'Enfant / Ado': '<18 ans',
    'Jeune adulte': '18-29 ans',
    'Adulte': '30-59 ans',
    'Senior': '60+ ans'
  };
  if (state.mAge) parts.push(ageMap[state.mAge] || state.mAge);
  if (state.mStar) parts.push('⭐ STAR');
  return parts.join(' · ');
}

export function collapseMobileProfile() {
  const cardExp = $('#mDemoCardExpanded');
  const cardCol = $('#mDemoCardCollapsed');
  const sumTxt = $('#mDemoSummaryText');
  if (!cardExp || !cardCol) return;
  const summary = getMobileProfileSummary();
  if (!summary) return;
  if (sumTxt) sumTxt.textContent = summary;
  cardExp.style.display = 'none';
  cardCol.style.display = 'flex';
}

export function expandMobileProfile() {
  if (mDemoTimer) { clearTimeout(mDemoTimer); mDemoTimer = null; }
  const cardExp = $('#mDemoCardExpanded');
  const cardCol = $('#mDemoCardCollapsed');
  if (cardExp) cardExp.style.display = 'block';
  if (cardCol) cardCol.style.display = 'none';
}

export function scheduleMobileProfileCollapse() {
  if (mDemoTimer) { clearTimeout(mDemoTimer); mDemoTimer = null; }
  saveActiveCart();
  if (!state.mGender && !state.mAge && !state.mStar) {
    expandMobileProfile();
    return;
  }
  mDemoTimer = setTimeout(() => {
    collapseMobileProfile();
  }, 5000);
}

export function updateProfileSummary() {
  if (!state.mGender && !state.mAge && !state.mStar) {
    expandMobileProfile();
  } else {
    collapseMobileProfile();
  }
}

export function initCart() {
  const mpAmt1 = $('#mpAmount1');
  if (mpAmt1) mpAmt1.addEventListener('input', updateMpCalculations);

  document.querySelectorAll('[data-mpq]').forEach(btn => {
    btn.addEventListener('click', () => {
      const q = btn.dataset.mpq;
      let val = 0;
      if (q === 'half') val = Math.round((state.activeMpTotal / 2) * 100) / 100;
      else val = parseFloat(q) || 0;
      if (val >= state.activeMpTotal) val = Math.max(1, state.activeMpTotal - 1);
      $('#mpAmount1').value = val.toFixed(2);
      updateMpCalculations();
    });
  });

  const bCancelMp = $('#btnCancelMultiPay');
  if (bCancelMp) bCancelMp.addEventListener('click', closeMultiPayModal);

  const bApplyMp = $('#btnApplyMultiPay');
  if (bApplyMp) bApplyMp.addEventListener('click', () => {
    const a1 = parseFloat($('#mpAmount1').value) || 0;
    const a2 = parseFloat($('#mpAmount2').value) || 0;
    if (!state.activeMpOwner || a1 <= 0 || a2 <= 0) return;
    state.originPayments[state.activeMpOwner] = {
      method: 'Multi',
      parts: [
        { payment: state.mpMode1, amount: a1 },
        { payment: state.mpMode2, amount: a2 }
      ]
    };
    saveActiveCart({ type: 'smart_split', owner: state.activeMpOwner, detail: `${a1.toFixed(2)} € ${state.mpMode1} + ${a2.toFixed(2)} € ${state.mpMode2}` });
    closeMultiPayModal();
    renderCart();
    toast('Cumul défini pour ' + state.activeMpOwner);
  });

  $('#clearCart').addEventListener('click', () => {
    state.cart = [];
    state.originPayments = {};
    hidePackUpsell();
    state.mGender = ''; state.mAge = ''; state.mStar = 0;
    const sBtn = $('#mBtnStar'); if (sBtn) sBtn.classList.remove('on');
    const gEl = $('#mDemoGender');
    if (gEl) {
      gEl.classList.remove('is-couple');
      gEl.querySelectorAll('button').forEach(b => b.classList.remove('on'));
      const cb = $('#mCoupleBadge'); if (cb) cb.style.display = 'none';
    }
    const aEl = $('#mDemoAge');
    if (aEl) aEl.querySelectorAll('button').forEach(b => b.classList.remove('on'));
    if (mDemoTimer) { clearTimeout(mDemoTimer); mDemoTimer = null; }
    expandMobileProfile();
    localStorage.removeItem('librairie_mobile_active_cart');
    renderCart();
  });

  const mBtnStandby = $('#mBtnStandby');
  if (mBtnStandby) {
    mBtnStandby.addEventListener('click', () => {
      if (!state.cart.length) return;
      const count = state.cart.reduce((s, i) => s + i.qty, 0);
      const total = state.cart.reduce((s, i) => s + i.qty * i.book.price, 0);
      const standbyData = {
        cart: JSON.parse(JSON.stringify(state.cart)),
        originPayments: JSON.parse(JSON.stringify(state.originPayments)),
        gender: state.mGender,
        age: state.mAge,
        star: state.mStar,
        total: eur(total),
        qty: count,
        timestamp: Date.now()
      };
      localStorage.setItem('librairie_mobile_standby_cart', JSON.stringify(standbyData));
      localStorage.removeItem('librairie_mobile_active_cart');
      clearLiveCartSync('standby_saved');
      logMobileLiveActivity('standby_saved', 'Panier mis en attente', `${count} articles · ${eur(total)}`, { count, total });

      state.cart = [];
      state.originPayments = {};
      hidePackUpsell();
      state.mGender = ''; state.mAge = ''; state.mStar = 0;
      const mStarBtn = $('#mBtnStar'); if (mStarBtn) mStarBtn.classList.remove('on');
      const mGenEl = $('#mDemoGender');
      if (mGenEl) {
        mGenEl.classList.remove('is-couple');
        mGenEl.querySelectorAll('button').forEach(b => b.classList.remove('on'));
        const cb = $('#mCoupleBadge'); if (cb) cb.style.display = 'none';
      }
      const mAgeEl = $('#mDemoAge');
      if (mAgeEl) mAgeEl.querySelectorAll('button').forEach(b => b.classList.remove('on'));
      if (mDemoTimer) { clearTimeout(mDemoTimer); mDemoTimer = null; }
      expandMobileProfile();

      renderCart();
      toast("Panier mis en attente. Caisse mobile libre pour le client suivant !");
    });
  }

  const mBtnResumeStandby = $('#mBtnResumeStandby');
  if (mBtnResumeStandby) {
    mBtnResumeStandby.addEventListener('click', () => {
      const raw = localStorage.getItem('librairie_mobile_standby_cart');
      if (!raw) return;
      if (state.cart.length > 0) {
        if (!confirm("Un panier est déjà en cours. Voulez-vous le remplacer par le panier en attente ?")) return;
      }
      try {
        const data = JSON.parse(raw);
        state.cart = data.cart || [];
        state.originPayments = data.originPayments || {};
        state.mGender = data.gender || '';
        state.mAge = data.age || '';
        state.mStar = data.star || 0;

        const mStarBtn = $('#mBtnStar'); if (mStarBtn) mStarBtn.classList.toggle('on', !!state.mStar);
        const mGenEl = $('#mDemoGender');
        if (mGenEl) {
          mGenEl.classList.toggle('is-couple', state.mGender === 'Couple');
          mGenEl.querySelector('button[data-g="Femme"]')?.classList.toggle('on', state.mGender === 'Femme' || state.mGender === 'Couple');
          mGenEl.querySelector('button[data-g="Homme"]')?.classList.toggle('on', state.mGender === 'Homme' || state.mGender === 'Couple');
          const cb = $('#mCoupleBadge'); if (cb) cb.style.display = state.mGender === 'Couple' ? 'block' : 'none';
        }
        const mAgeEl = $('#mDemoAge');
        if (mAgeEl) {
          mAgeEl.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.a === state.mAge));
        }
        if (state.mGender || state.mAge || state.mStar) collapseMobileProfile(); else expandMobileProfile();

        localStorage.removeItem('librairie_mobile_standby_cart');
        saveActiveCart({ type: 'standby_resumed', count: state.cart.length });
        renderCart();
        toast("Panier précédent repris avec succès !");
      } catch (err) {
        toast("Erreur lors de la reprise du panier : " + err.message, "err");
      }
    });
  }

  const mBtnDiscardStandby = $('#mBtnDiscardStandby');
  if (mBtnDiscardStandby) {
    mBtnDiscardStandby.addEventListener('click', () => {
      if (confirm("Supprimer définitivement ce panier en attente ?")) {
        localStorage.removeItem('librairie_mobile_standby_cart');
        updateMobileStandbyUI();
        toast("Panier en attente supprimé.");
      }
    });
  }

  const btnConvert = $('#btnConvertPack');
  if (btnConvert) {
    btnConvert.addEventListener('click', () => {
      if (!state.currentUpsellContext) return;
      const { singleBook, pack } = state.currentUpsellContext;
      const idx = state.cart.findIndex(i => i.book.id === singleBook.id);
      if (idx !== -1) {
        if (state.cart[idx].qty > 1) {
          state.cart[idx].qty--;
        } else {
          state.cart.splice(idx, 1);
        }
      }
      addPackToCart(pack);
      toast(`✓ Converti en ${pack.title} (-${eur(pack.saving)} d\'économie) !`);
      if (navigator.vibrate) navigator.vibrate([80, 50, 80]);
      hidePackUpsell();
    });
  }

  const btnCloseUpsell = $('#btnClosePackUpsell');
  if (btnCloseUpsell) {
    btnCloseUpsell.addEventListener('click', () => {
      hidePackUpsell();
    });
  }

  const mCardCol = $('#mDemoCardCollapsed');
  if (mCardCol) {
    mCardCol.onclick = () => {
      expandMobileProfile();
    };
  }

  const mStarBtn = $('#mBtnStar');
  if (mStarBtn) {
    mStarBtn.addEventListener('click', () => {
      state.mStar = state.mStar ? 0 : 1;
      mStarBtn.classList.toggle('on', !!state.mStar);
      scheduleMobileProfileCollapse();
      saveActiveCart({ type: 'profile_star', star: !!state.mStar });
    });
  }

  const mGenEl = $('#mDemoGender');
  if (mGenEl) {
    mGenEl.addEventListener('click', e => {
      const b = e.target.closest('button[data-g]');
      if (b) {
        b.classList.toggle('on');
        const fOn = mGenEl.querySelector('button[data-g="Femme"]')?.classList.contains('on');
        const hOn = mGenEl.querySelector('button[data-g="Homme"]')?.classList.contains('on');
        const cBadge = $('#mCoupleBadge');
        if (fOn && hOn) {
          state.mGender = 'Couple';
          mGenEl.classList.add('is-couple');
          if (cBadge) cBadge.style.display = 'block';
        } else if (fOn) {
          state.mGender = 'Femme';
          mGenEl.classList.remove('is-couple');
          if (cBadge) cBadge.style.display = 'none';
        } else if (hOn) {
          state.mGender = 'Homme';
          mGenEl.classList.remove('is-couple');
          if (cBadge) cBadge.style.display = 'none';
        } else {
          state.mGender = '';
          mGenEl.classList.remove('is-couple');
          if (cBadge) cBadge.style.display = 'none';
        }
        scheduleMobileProfileCollapse();
        saveActiveCart({ type: 'profile_gender', gender: state.mGender });
      }
    });
  }

  const mAgeEl = $('#mDemoAge');
  if (mAgeEl) {
    mAgeEl.addEventListener('click', e => {
      const b = e.target.closest('button[data-a]');
      if (b) {
        const isAlreadyOn = b.classList.contains('on');
        mAgeEl.querySelectorAll('button').forEach(btn => btn.classList.remove('on'));
        if (isAlreadyOn) {
          state.mAge = '';
        } else {
          b.classList.add('on');
          state.mAge = b.dataset.a;
        }
        scheduleMobileProfileCollapse();
        saveActiveCart({ type: 'profile_age', age: state.mAge });
      }
    });
  }

  $('#btnValidate').addEventListener('click', async () => {
    if (!state.currentUser) return openUserModal();
    const btn = $('#btnValidate');
    btn.disabled = true;
    
    const origins = getCartByOrigin();
    if (!origins.length) {
      btn.disabled = false;
      return;
    }

    const unassigned = state.cart.find(i => !i.book.is_pack && (i.lot === undefined || i.lot === null || i.lot === 'none'));
    if (unassigned) {
      toast(`Indiquez l\'origine en stock pour « ${unassigned.book.title} » avant d\'encaisser.`, 'warn');
      btn.disabled = false;
      return;
    }

    const zeroStock = state.cart.find(i => lotRemaining(i) < i.qty);
    if (zeroStock) {
      toast(`Stock insuffisant pour « ${zeroStock.book.title} » (${zeroStock.qty} demandés, ${lotRemaining(zeroStock)} dispo).`, 'err');
      btn.disabled = false;
      return;
    }

    try {
      const validatedSales = [];
      for (let idx = 0; idx < origins.length; idx++) {
        const g = origins[idx];
        const payState = state.originPayments[g.owner] || { method: 'Espèces', parts: null };
        const lines = g.items.map(i => {
          if (i.book.is_pack) {
            const allocs = [];
            for (const comp of (i.book.items || [])) {
              const compLots = (comp.lots || []).filter(l => l.remaining > 0);
              let chosenLot = compLots.find(l => (l.owner || '').trim().toLowerCase() === 'cité royale');
              if (!chosenLot && compLots.length) chosenLot = compLots[0];
              if (!chosenLot) {
                throw new Error(`Stock épuisé pour le composant « ${comp.title || comp.book_id} » du pack`);
              }
              allocs.push({
                book_id: comp.book_id,
                lot_id: chosenLot.id,
                qty: i.qty * (comp.qty || 1)
              });
            }
            return {
              book_id: i.book.id,
              qty: i.qty,
              unit_price: i.book.price,
              allocations: allocs
            };
          } else {
            return {
              book_id: i.book.id,
              qty: i.qty,
              unit_price: i.book.price,
              allocations: [{ book_id: i.book.id, lot_id: +i.lot, qty: i.qty }]
            };
          }
        });

        const payload = {
          payment: payState.parts ? payState.parts.map(p => `${p.amount.toFixed(2)} € ${p.payment}`).join(' + ') : payState.method,
          payments: payState.parts || null,
          note: origins.length > 1 ? `Vente mobile (${g.owner})` : 'Vente mobile',
          customer_gender: state.mGender || null,
          customer_age_group: state.mAge || null,
          is_star: state.mStar ? 1 : 0,
          service_moment: state.mMoment || null,
          lines
        };

        try {
          const res = await api('/api/sales', { method: 'POST', body: payload });
          validatedSales.push({ id: res.id, owner: g.owner, total: res.total });
          state.cart = state.cart.filter(item => getItemOwner(item) !== g.owner);
        } catch (err) {
          toast(`Erreur sur vente ${g.owner} : ${err.message}`, 'err');
          renderCart();
          btn.disabled = false;
          return;
        }
      }

      if (validatedSales.length === 1) {
        toast('Vente enregistrée : ' + eur(validatedSales[0].total));
      } else {
        toast(`✓ ${validatedSales.length} ventes validées : ` + validatedSales.map(v => `${eur(v.total)} (${v.owner})`).join(' + '));
      }

      if (navigator.vibrate) navigator.vibrate([60, 40, 60]);

      state.cart = [];
      state.originPayments = {};
      hidePackUpsell();
      state.mGender = ''; state.mAge = ''; state.mStar = 0;
      localStorage.removeItem('librairie_mobile_active_cart');
      if (mStarBtn) mStarBtn.classList.remove('on');
      if (mGenEl) {
        mGenEl.classList.remove('is-couple');
        mGenEl.querySelectorAll('button').forEach(b => b.classList.remove('on'));
        const cb = $('#mCoupleBadge'); if (cb) cb.style.display = 'none';
      }
      if (mAgeEl) mAgeEl.querySelectorAll('button').forEach(b => b.classList.remove('on'));
      updateProfileSummary();
    } catch (e) {
      toast(e.message, 'err');
    } finally {
      renderCart();
    }
  });
}
