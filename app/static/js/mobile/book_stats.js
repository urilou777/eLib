/* Librairie Mobile - Modale Statistiques Livre & Réassurance Client */
'use strict';
import { $, el, eur, toast, createStatsIcon } from './core.js';
import { api } from './api.js';

export async function openMobileBookStats(bid) {
  const modal = $('#bookStatsModal');
  const cont = $('#mBookStatsContent');
  if (!modal || !cont) return;

  cont.replaceChildren(el('div', { class: 'muted', style: 'text-align:center;padding:24px;font-size:13px', text: 'Chargement des statistiques…' }));
  modal.hidden = false;

  try {
    const data = await api('/api/books/' + bid + '/stats');
    const b = data.book;
    const k = data.kpis;
    const d = data.demographics;
    const recent = data.recent_sales || [];
    const packs = data.packs || [];

    const totalGender = (d.gender.Femme || 0) + (d.gender.Homme || 0) + (d.gender.Couple || 0) + (d.gender.Autre || 0);
    const pFemme = totalGender ? Math.round(((d.gender.Femme || 0) / totalGender) * 100) : 0;
    const pHomme = totalGender ? Math.round(((d.gender.Homme || 0) / totalGender) * 100) : 0;
    const pCouple = totalGender ? Math.round(((d.gender.Couple || 0) / totalGender) * 100) : 0;
    const pAutre = totalGender ? Math.max(0, 100 - pFemme - pHomme - pCouple) : 0;

    const totalAge = (d.age_groups || []).reduce((s, a) => s + a.count, 0);

    const genderBarSegments = [];
    if (pFemme) genderBarSegments.push(el('div', { style: `width:${pFemme}%;background:#f472b6;height:100%`, title: `Femmes : ${pFemme}%` }));
    if (pHomme) genderBarSegments.push(el('div', { style: `width:${pHomme}%;background:#60a5fa;height:100%`, title: `Hommes : ${pHomme}%` }));
    if (pCouple) genderBarSegments.push(el('div', { style: `width:${pCouple}%;background:#c084fc;height:100%`, title: `Couples/Foyers : ${pCouple}%` }));
    if (pAutre) genderBarSegments.push(el('div', { style: `width:${pAutre}%;background:rgba(255,255,255,0.2);height:100%`, title: `Autre : ${pAutre}%` }));

    const genderLegend = el('div', { class: 'm-stats-legend' },
      el('span', { style: 'color:#f472b6' }, `Femme ${pFemme}%`),
      el('span', { style: 'color:#60a5fa' }, `Homme ${pHomme}%`),
      el('span', { style: 'color:#c084fc' }, `Couple ${pCouple}%`),
      pAutre ? el('span', { class: 'muted' }, `Autre ${pAutre}%`) : null
    );

    const agePills = (d.age_groups || []).map(ag => {
      const pct = totalAge ? Math.round((ag.count / totalAge) * 100) : 0;
      return el('div', { class: 'm-stats-age-pill' },
        el('span', { class: 'muted', style: 'margin-right:2px', text: ag.label.replace(' ans', '') }),
        el('b', { text: `${pct}%` })
      );
    });

    const recentItems = recent.slice(0, 3).map(r => {
      const datePart = (r.date || '').split('-').reverse().slice(0, 2).join('/');
      return el('div', { class: 'm-stats-sale-row' },
        el('div', {},
          el('b', { text: datePart }),
          el('span', { class: 'muted', style: 'margin-left:4px', text: r.service_moment || 'Culte' })
        ),
        el('div', { style: 'display:flex;align-items:center;gap:4px' },
          el('b', { text: `${r.qty} ex.` }),
          el('span', { class: 'chip', style: 'font-size:9.5px;padding:1px 5px;background:rgba(255,255,255,0.06)' },
            r.customer_gender ? (r.customer_gender === 'Femme' ? '♀' : r.customer_gender === 'Homme' ? '♂' : '👫') : '👤',
            r.is_star ? ' ⭐' : ''
          )
        )
      );
    });

    cont.replaceChildren(
      // Header
      el('div', { class: 'm-stats-header' },
        el('div', {},
          el('div', { class: 'm-stats-title' },
            b.is_pack ? el('span', { class: 'badge b-pack', style: 'background:linear-gradient(135deg, #9333ea, #c026d3);color:#fff;font-size:10px;font-weight:700;padding:1px 5px;border-radius:4px;margin-right:5px' }, 'PACK') : null,
            b.title
          ),
          el('div', { class: 'm-stats-sub' },
            el('b', { style: 'color:var(--good);font-size:12.5px', text: eur(b.price) }),
            ` · ${b.code}`
          )
        ),
        el('button', {
          type: 'button',
          class: 'btn ghost sm',
          style: 'padding:2px 8px;font-size:16px;color:var(--mut)',
          onclick: closeMobileBookStats
        }, '✕')
      ),

      // KPIs
      el('div', { class: 'm-stats-kpis' },
        el('div', { class: 'm-stats-kpi-card' },
          el('div', { class: 'm-stats-kpi-lbl', text: 'Total Ventes' }),
          el('div', { class: 'm-stats-kpi-val', style: 'color:var(--good)', text: `${k.total_sold} ex.` }),
          el('div', { class: 'muted', style: 'font-size:10px', text: eur(k.total_revenue) })
        ),
        el('div', { class: 'm-stats-kpi-card' },
          el('div', { class: 'm-stats-kpi-lbl', text: 'Dernier Achat' }),
          el('div', { class: 'm-stats-kpi-val', style: 'font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis',
            text: k.last_sale_date ? k.last_sale_date.split('-').reverse().slice(0, 2).join('/') : 'Aucun'
          }),
          el('div', { class: 'muted', style: 'font-size:10px', text: `${k.sold_last_30d} ex. / 30j` })
        ),
        el('div', { class: 'm-stats-kpi-card' },
          el('div', { class: 'm-stats-kpi-lbl', text: 'Stock Dispo' }),
          el('div', { class: 'm-stats-kpi-val', style: `color:${b.stock > 0 ? 'var(--good)' : 'var(--bad)'}`, text: `${b.stock} ex.` }),
          el('div', { class: 'muted', style: 'font-size:9.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis',
            text: (b.owners || []).map(o => `${o.name}: ${o.remaining}`).join(' · ') || 'Stock'
          })
        )
      ),

      // Profil Acheteurs
      el('div', { class: 'm-stats-box' },
        el('div', { class: 'm-stats-box-title' },
          el('svg', { style: 'width:12px;height:12px;stroke:currentColor;fill:none;stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round', viewBox: '0 0 24 24' },
            el('path', { d: 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2' }),
            el('circle', { cx: '12', cy: '7', r: '4' })
          ),
          el('span', { text: 'Profil des Acheteurs' })
        ),
        el('div', { class: 'm-stats-bar' }, ...genderBarSegments),
        genderLegend,
        el('div', { class: 'm-stats-ages' }, ...agePills),
        el('div', { class: 'm-stats-star' },
          el('svg', { style: 'width:13px;height:13px;fill:#fbbf24;stroke:#fbbf24;flex-shrink:0', viewBox: '0 0 24 24' },
            el('polygon', { points: '12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2' })
          ),
          el('span', { text: `${d.star.pct}% acheteurs STAR (${d.star.count} ex.)` })
        )
      ),

      // Derniers Achats
      recentItems.length ? el('div', { class: 'm-stats-box' },
        el('div', { class: 'm-stats-box-title' },
          el('svg', { style: 'width:12px;height:12px;stroke:currentColor;fill:none;stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round', viewBox: '0 0 24 24' },
            el('circle', { cx: '12', cy: '12', r: '10' }),
            el('polyline', { points: '12 6 12 12 16 14' })
          ),
          el('span', { text: 'Derniers Achats' })
        ),
        el('div', { class: 'm-stats-sales' }, ...recentItems)
      ) : null,

      // Pack associé
      packs.length > 0 ? el('div', { style: 'background:rgba(147,51,234,0.12);border:1px solid rgba(147,51,234,0.3);border-radius:8px;padding:5px 8px;font-size:11px' },
        el('div', { style: 'font-size:9.5px;color:#d8b4fe;font-weight:700;text-transform:uppercase', text: 'Inclus dans un pack :' }),
        el('div', { style: 'display:flex;justify-content:space-between;align-items:center;margin-top:2px' },
          el('b', { style: 'color:#fff', text: packs[0].title }),
          el('b', { style: 'color:#86efac', text: eur(packs[0].price) })
        )
      ) : null,

      // Bouton Fermer
      el('button', {
        type: 'button',
        class: 'btn sm',
        style: 'width:100%;padding:8px;font-weight:700;margin-top:2px',
        onclick: closeMobileBookStats
      }, 'Fermer')
    );
  } catch (err) {
    toast('Erreur statistiques : ' + err.message, 'err');
    closeMobileBookStats();
  }
}

export function closeMobileBookStats() {
  const modal = $('#bookStatsModal');
  if (modal) modal.hidden = true;
}

export function initBookStats() {
  const bsModalEl = $('#bookStatsModal');
  if (bsModalEl) {
    bsModalEl.addEventListener('click', e => {
      if (e.target === bsModalEl) closeMobileBookStats();
    });
  }
}
