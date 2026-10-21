/* eLib – Visite guidée mise en scène avec Eli le libraire-guide et Plume le petit livre volant.
   Décors concrets par étape, navigation réelle entre écrans, projecteur sur l'élément ciblé.
   100 % local, aucun asset externe, aucun emoji. */
(function () {
  'use strict';

  var KEY = 'librairie_tutorial_done_v7';

  var P = {
    cardigan: '#5e2f7d', cardiganDark: '#3f1f57', shirt: '#f4ead9',
    skin: '#c68d5e', skinDark: '#a56f45', hair: '#241626',
    glass: '#e6a73c', dark: '#2a1830', blush: '#d98a66',
    book: '#ca88e3', gold: '#f5d27a', cream: '#faf7f2',
    wood: '#7a4a2b', woodLight: '#9a6238', night: '#1a1030',
    purple: '#8f16ad', deep: '#5e0b75', paper: '#efe6d4',
    ok: '#4caf7d', low: '#e6a73c', out: '#d95f5f', excel: '#217346'
  };

  /* ---------- Eli : visage et poses (repère 120x120 ancré bas) ---------- */

  function eyes(kind) {
    var L = 50, R = 70, y = 53;
    if (kind === 'happy') return '<path d="M' + (L - 6) + ' ' + y + ' Q' + L + ' ' + (y - 6) + ' ' + (L + 6) + ' ' + y + '" fill="none" stroke="' + P.dark + '" stroke-width="2.6" stroke-linecap="round"/><path d="M' + (R - 6) + ' ' + y + ' Q' + R + ' ' + (y - 6) + ' ' + (R + 6) + ' ' + y + '" fill="none" stroke="' + P.dark + '" stroke-width="2.6" stroke-linecap="round"/>';
    if (kind === 'wide') return '<circle cx="' + L + '" cy="' + y + '" r="4.6" fill="#fff"/><circle cx="' + L + '" cy="' + (y + 1) + '" r="2.2" fill="' + P.dark + '"/><circle cx="' + R + '" cy="' + y + '" r="4.6" fill="#fff"/><circle cx="' + R + '" cy="' + (y + 1) + '" r="2.2" fill="' + P.dark + '"/>';
    if (kind === 'wink') return '<path d="M' + (L - 6) + ' ' + y + ' Q' + L + ' ' + (y - 6) + ' ' + (L + 6) + ' ' + y + '" fill="none" stroke="' + P.dark + '" stroke-width="2.6" stroke-linecap="round"/><circle cx="' + R + '" cy="' + y + '" r="2.6" fill="' + P.dark + '"/>';
    if (kind === 'up') return '<circle cx="' + L + '" cy="' + (y - 1) + '" r="2.6" fill="' + P.dark + '"/><circle cx="' + R + '" cy="' + (y - 1) + '" r="2.6" fill="' + P.dark + '"/>';
    if (kind === 'closed') return '<path d="M' + (L - 6) + ' ' + (y + 1) + ' Q' + L + ' ' + (y + 5) + ' ' + (L + 6) + ' ' + (y + 1) + '" fill="none" stroke="' + P.dark + '" stroke-width="2.6" stroke-linecap="round"/><path d="M' + (R - 6) + ' ' + (y + 1) + ' Q' + R + ' ' + (y + 5) + ' ' + (R + 6) + ' ' + (y + 1) + '" fill="none" stroke="' + P.dark + '" stroke-width="2.6" stroke-linecap="round"/>';
    return '<circle cx="' + L + '" cy="' + y + '" r="2.6" fill="' + P.dark + '"/><circle cx="' + R + '" cy="' + y + '" r="2.6" fill="' + P.dark + '"/>';
  }

  function brows(kind) {
    var a = 'stroke="' + P.hair + '" stroke-width="2.6" stroke-linecap="round" fill="none"';
    if (kind === 'raised') return '<path d="M43 42 Q50 38 57 41" ' + a + '/><path d="M63 41 Q70 38 77 42" ' + a + '/>';
    if (kind === 'knit') return '<path d="M43 40 L57 43" ' + a + '/><path d="M63 43 L77 40" ' + a + '/>';
    if (kind === 'one') return '<path d="M43 42 Q50 39 57 42" ' + a + '/><path d="M63 43 L77 41" ' + a + '/>';
    return '<path d="M44 41 L56 40.5" ' + a + '/><path d="M64 40.5 L76 41" ' + a + '/>';
  }

  function mouth(kind) {
    var a = 'stroke="' + P.dark + '" stroke-width="2.4" stroke-linecap="round" fill="none"';
    if (kind === 'grin') return '<path d="M50 66 Q60 79 70 66 Q60 70 50 66 Z" fill="' + P.dark + '"/>';
    if (kind === 'o') return '<ellipse cx="60" cy="69" rx="3.4" ry="4" fill="' + P.dark + '"/>';
    if (kind === 'small') return '<path d="M55 68 L65 68" ' + a + '/>';
    if (kind === 'determined') return '<path d="M52 69 Q60 65 68 69" ' + a + '/>';
    if (kind === 'think') return '<path d="M53 68 Q60 72 67 67" ' + a + '/>';
    return '<path d="M52 66 Q60 73 68 66" ' + a + '/>';
  }

  function arm(x1, y1, x2, y2, bend) {
    var mx = (x1 + x2) / 2 + bend.x, my = (y1 + y2) / 2 + bend.y;
    return '<path d="M' + x1 + ' ' + y1 + ' Q' + mx + ' ' + my + ' ' + x2 + ' ' + y2 + '" fill="none" stroke="' + P.cardigan + '" stroke-width="9" stroke-linecap="round"/><circle cx="' + x2 + '" cy="' + y2 + '" r="5" fill="' + P.skin + '"/>';
  }

  var EMO = {
    wave:   { e: 'happy', b: 'raised', m: 'grin',  L: null, R: [98, 96, 102, 74, 12, -6] },
    present:{ e: 'open',  b: 'flat',  m: 'smile', L: [22, 100, 10, 96, -2, -8], R: [98, 100, 92, 112, 8, 2] },
    scan:   { e: 'wide',  b: 'raised',m: 'o',     L: [22, 104, 26, 114, -2, 4],  R: [98, 98, 86, 46, 12, 8] },
    hold:   { e: 'open',  b: 'flat',  m: 'smile', L: [24, 100, 50, 112, 2, -6],  R: [96, 100, 72, 112, -2, -6] },
    effort: { e: 'closed',b: 'knit',  m: 'determined', L: [24, 100, 48, 116, 0, 2], R: [96, 100, 74, 116, 0, 2] },
    alert:  { e: 'wide',  b: 'raised',m: 'small', L: [22, 100, 14, 78, -6, -8],  R: [98, 104, 96, 116, 6, 4] },
    point:  { e: 'open',  b: 'raised',m: 'smile', L: [22, 104, 20, 116, -4, 2],  R: [98, 98, 108, 76, 8, -4] },
    think:  { e: 'up',    b: 'one',   m: 'think', L: [22, 104, 24, 116, 0, 4],   R: [96, 100, 74, 76, 10, 2] },
    count:  { e: 'open',  b: 'one',   m: 'smile', L: [22, 100, 18, 84, -6, -6],  R: [96, 104, 88, 116, 4, 4] },
    shield: { e: 'open',  b: 'flat',  m: 'small', L: [24, 100, 64, 106, 4, -6],  R: [96, 104, 92, 116, 4, 2] },
    busy:   { e: 'happy', b: 'knit',  m: 'determined', L: [24, 100, 46, 114, 0, 0], R: [96, 100, 76, 114, 0, 0] },
    cheer:  { e: 'happy', b: 'raised',m: 'grin',  L: [26, 96, 20, 68, -8, -6],    R: [94, 96, 100, 68, 8, -6] },
    wink:   { e: 'wink',  b: 'one',   m: 'smile', L: [22, 104, 24, 116, -2, 4],  R: [98, 104, 92, 116, 2, 2] },
    party:  { e: 'happy', b: 'raised',m: 'grin',  L: [26, 96, 18, 66, -8, -6],   R: [94, 96, 102, 66, 8, -6] }
  };

  function eliGroup(emo) {
    var cfg = EMO[emo] || EMO.present;
    var arms = '';
    if (cfg.L) arms += arm(cfg.L[0], cfg.L[1], cfg.L[2], cfg.L[3], { x: cfg.L[4], y: cfg.L[5] });
    if (cfg.R) arms += arm(cfg.R[0], cfg.R[1], cfg.R[2], cfg.R[3], { x: cfg.R[4], y: cfg.R[5] });
    var hair = '<g fill="' + P.hair + '"><circle cx="44" cy="36" r="10"/><circle cx="53" cy="30" r="11"/><circle cx="63" cy="28" r="12"/><circle cx="73" cy="31" r="10"/><circle cx="80" cy="39" r="8"/><circle cx="40" cy="43" r="8"/><circle cx="37" cy="50" r="5"/><circle cx="83" cy="50" r="5"/></g>';
    var glasses = '<g fill="rgba(255,255,255,0.05)" stroke="' + P.glass + '" stroke-width="2.2"><circle cx="50" cy="53" r="9"/><circle cx="70" cy="53" r="9"/></g><path d="M59 53 L61 53" stroke="' + P.glass + '" stroke-width="2.2"/><path d="M41 53 L35 50 M79 53 L85 50" stroke="' + P.glass + '" stroke-width="2.2" stroke-linecap="round"/>';
    return '<g>' +
      '<rect x="54" y="76" width="12" height="10" fill="' + P.skinDark + '"/>' + arms +
      '<path d="M26 120 C26 96 40 86 60 86 C80 86 94 96 94 120 Z" fill="' + P.cardigan + '"/>' +
      '<path d="M47 86 L60 104 L73 86 Z" fill="' + P.shirt + '"/>' +
      '<path d="M47 86 L52 93 L56 87 Z M73 86 L68 93 L64 87 Z" fill="' + P.cardiganDark + '"/>' +
      '<circle cx="34" cy="58" r="4.5" fill="' + P.skin + '"/><circle cx="86" cy="58" r="4.5" fill="' + P.skin + '"/>' +
      '<circle cx="60" cy="54" r="26" fill="' + P.skin + '"/>' + hair +
      '<ellipse cx="44" cy="63" rx="4" ry="2.6" fill="' + P.blush + '" opacity="0.55"/>' +
      '<ellipse cx="76" cy="63" rx="4" ry="2.6" fill="' + P.blush + '" opacity="0.55"/>' +
      brows(cfg.b) + eyes(cfg.e) + glasses + mouth(cfg.m) + '</g>';
  }

  /* ---------- Plume, le petit livre ailé (remplace la colombe, définitivement) ---------- */
  function plume(pose, x, y, s) {
    s = s || 1;
    var g = '<g transform="translate(' + x + ',' + y + ') scale(' + s + ')">';
    /* marque-page doré */
    g += '<path d="M11 20 L11 26 L14 23.5 L17 26 L17 20" fill="' + P.gold + '"/>';
    /* corps : petit livre fermé */
    g += '<rect x="0" y="0" width="28" height="20" rx="3" fill="' + P.book + '"/>' +
         '<rect x="0" y="0" width="5" height="20" rx="2.5" fill="' + P.deep + '"/>' +
         '<rect x="25" y="2.5" width="3" height="15" rx="1" fill="' + P.cream + '"/>';
    /* tranche de pages */
    g += '<path d="M25 2.5 L28 2.5 L28 17.5 L25 17.5" fill="' + P.paper + '"/>';
    /* visage : deux yeux ronds et un petit sourire */
    g += '<circle cx="12" cy="8" r="2" fill="' + P.dark + '"/><circle cx="19" cy="8" r="2" fill="' + P.dark + '"/>' +
         '<path d="M13 13 Q15.5 15 18 13" fill="none" stroke="' + P.dark + '" stroke-width="1.6" stroke-linecap="round"/>';
    /* joues */
    g += '<circle cx="8.5" cy="12" r="1.5" fill="' + P.blush + '" opacity="0.6"/><circle cx="22.5" cy="12" r="1.5" fill="' + P.blush + '" opacity="0.6"/>';
    /* ailes : éventail de plumes arrondies sur les CÔTÉS (jamais au-dessus : pas de cornes) */
    if (pose === 'fly') {
      g += '<g fill="' + P.paper + '">' +
           '<ellipse cx="-5" cy="14" rx="7" ry="3.2" transform="rotate(-12 -5 14)"/>' +
           '<ellipse cx="-6.5" cy="10.5" rx="8" ry="3.4" transform="rotate(-30 -6.5 10.5)"/>' +
           '<ellipse cx="-6" cy="7" rx="8" ry="3.6" transform="rotate(-48 -6 7)"/>' +
           '</g>';
      g += '<g fill="' + P.paper + '">' +
           '<ellipse cx="33" cy="14" rx="7" ry="3.2" transform="rotate(12 33 14)"/>' +
           '<ellipse cx="34.5" cy="10.5" rx="8" ry="3.4" transform="rotate(30 34.5 10.5)"/>' +
           '<ellipse cx="34" cy="7" rx="8" ry="3.6" transform="rotate(48 34 7)"/>' +
           '</g>';
    } else {
      g += '<path d="M1 8 Q-5 8.5 -6 13.5 Q-1 15.5 1.5 12 Z" fill="' + P.paper + '"/>' +
           '<path d="M27 8 Q33 8.5 34 13.5 Q29 15.5 26.5 12 Z" fill="' + P.paper + '"/>';
    }
    if (pose === 'talk') g += '<path d="M14 -6 Q12 -11 16 -12.5 Q20 -11 18 -6" fill="none" stroke="' + P.gold + '" stroke-width="1.4"/>';
    g += '</g>';
    return g;
  }

  /* Voix hors-champ : pointillés animés côté droit */
  function offstageVoice(x, y) {
    return '<g transform="translate(' + x + ',' + y + ')">' +
      '<path d="M0 0 Q10 -6 16 0 Q10 6 0 0" fill="' + P.gold + '" opacity="0.9"/>' +
      '<circle cx="-8" cy="-2" r="2" fill="' + P.gold + '"><animate attributeName="opacity" values="0.2;1;0.2" dur="1.2s" repeatCount="indefinite"/></circle>' +
      '<circle cx="-8" cy="4" r="2" fill="' + P.gold + '" opacity="0.5"/>' +
      '</g>';
  }

  /* ---------- Décors : mini-interfaces concrètes, pas des papiers abstraits ---------- */

  function bookRow(x, y, w) {
    var out = '', bw = 7, i = 0, cols = [P.book, P.gold, P.paper, P.purple, P.cream];
    while (i * bw < w) {
      var h = 10 + (i % 3) * 3;
      out += '<rect x="' + (x + i * bw) + '" y="' + (y - h) + '" width="' + (bw - 1.6) + '" height="' + h + '" rx="1" fill="' + cols[i % cols.length] + '" opacity="0.9"/>';
      i++;
    }
    return out;
  }

  var SCENES = {
    shop: function () {
      return '<rect x="0" y="0" width="170" height="120" fill="#251238"/>' +
        '<rect x="8" y="18" width="70" height="4" rx="2" fill="' + P.wood + '"/>' + bookRow(10, 18, 66) +
        '<rect x="8" y="52" width="70" height="4" rx="2" fill="' + P.wood + '"/>' + bookRow(10, 52, 60) +
        '<rect x="104" y="14" width="56" height="38" rx="6" fill="' + P.cardiganDark + '"/>' +
        '<rect x="110" y="20" width="44" height="26" rx="4" fill="' + P.paper + '"/>' +
        '<path d="M132 26 v14 M125 32 h14" stroke="' + P.deep + '" stroke-width="3" stroke-linecap="round"/>' +
        '<path d="M108 56 q62 10 56 24" fill="none" stroke="' + P.gold + '" stroke-width="1.4" opacity="0.7"/>';
    },
    catalog: function () {
      return '<rect x="0" y="0" width="170" height="120" fill="#2c153f"/>' +
        '<rect x="0" y="8" width="170" height="4" fill="' + P.wood + '"/>' + bookRow(2, 8, 164) +
        '<rect x="0" y="42" width="170" height="4" fill="' + P.wood + '"/>' + bookRow(2, 42, 160) +
        '<rect x="0" y="76" width="170" height="4" fill="' + P.wood + '"/>' + bookRow(2, 76, 158) +
        '<g transform="translate(134,34) rotate(14)"><rect x="0" y="0" width="4" height="66" rx="2" fill="' + P.woodLight + '"/><rect x="-7" y="0" width="18" height="4" rx="2" fill="' + P.woodLight + '"/><rect x="-4" y="60" width="12" height="4" rx="2" fill="' + P.woodLight + '"/></g>';
    },
    chart: function () {
      return '<rect x="0" y="0" width="170" height="120" fill="#1d0a28"/>' +
        '<rect x="22" y="8" width="60" height="54" rx="5" fill="' + P.paper + '"/>' +
        '<g fill="' + P.purple + '"><rect x="28" y="34" width="8" height="22" rx="1.6"/><rect x="40" y="26" width="8" height="30" rx="1.6"/><rect x="52" y="40" width="8" height="16" rx="1.6"/><rect x="64" y="20" width="8" height="36" rx="1.6"/></g>' +
        '<rect x="92" y="8" width="60" height="54" rx="5" fill="' + P.paper + '"/>' +
        '<path d="M98 48 L112 34 L126 40 L144 22" fill="none" stroke="' + P.purple + '" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>' +
        '<circle cx="144" cy="22" r="3" fill="' + P.gold + '"/>' +
        '<g stroke="' + P.deep + '" stroke-width="1.6" opacity="0.35"><path d="M98 56 L146 56 M98 48 L146 48 M98 40 L146 40 M98 32 L146 32"/></g>' +
        '<rect x="46" y="78" width="78" height="8" rx="4" fill="' + P.cardiganDark + '" opacity="0.8"/>';
    },
    scanScene: function () {
      return '<rect x="0" y="0" width="170" height="120" fill="#251238"/>' +
        '<rect x="96" y="14" width="66" height="5" rx="2" fill="' + P.wood + '"/>' + bookRow(98, 14, 62) +
        '<rect x="96" y="48" width="66" height="5" rx="2" fill="' + P.wood + '"/>' + bookRow(98, 48, 58) +
        '<path d="M30 78 q-14 -30 22 -34" fill="none" stroke="' + P.paper + '" stroke-width="5" opacity="0.25" stroke-linecap="round"/>' +
        '<g transform="translate(120,88)"><circle r="16" fill="none" stroke="' + P.gold + '" stroke-width="4" opacity="0.85"/><path d="M11 11 L20 20" stroke="' + P.gold + '" stroke-width="5" stroke-linecap="round"/></g>';
    },
    counter: function () {
      return '<rect x="0" y="0" width="170" height="120" fill="#251238"/>' +
        '<rect x="0" y="78" width="170" height="42" fill="' + P.wood + '"/>' +
        '<rect x="0" y="78" width="170" height="7" fill="' + P.woodLight + '"/>' +
        '<g transform="translate(108,42)"><rect x="0" y="0" width="42" height="34" rx="4" fill="' + P.cardiganDark + '"/><rect x="4" y="4" width="34" height="12" rx="2" fill="' + P.night + '"/><text x="21" y="13" text-anchor="middle" font-family="monospace" font-size="8" fill="' + P.ok + '">12,50€</text><g fill="' + P.gold + '"><rect x="4" y="20" width="6" height="5" rx="1"/><rect x="12" y="20" width="6" height="5" rx="1"/><rect x="20" y="20" width="6" height="5" rx="1"/><rect x="28" y="20" width="6" height="5" rx="1"/><rect x="8" y="27" width="6" height="5" rx="1"/><rect x="16" y="27" width="6" height="5" rx="1"/><rect x="24" y="27" width="6" height="5" rx="1"/></g></g>' +
        '<g transform="translate(20,60)"><path d="M0 14 L4 2 L26 2 L30 14 Z" fill="none" stroke="' + P.gold + '" stroke-width="2.4" stroke-linejoin="round"/><rect x="9" y="-8" width="14" height="11" rx="1.6" fill="' + P.book + '" transform="rotate(-10 16 -3)"/></g>';
    },
    warehouse: function () {
      return '<rect x="0" y="0" width="170" height="120" fill="#2c153f"/>' +
        '<rect x="0" y="78" width="170" height="42" fill="' + P.wood + '"/>' +
        '<rect x="0" y="78" width="170" height="7" fill="' + P.woodLight + '"/>' +
        '<g><rect x="46" y="52" width="40" height="28" rx="2" fill="' + P.paper + '" stroke="' + P.wood + '" stroke-width="1.6"/><path d="M46 66 L86 66" stroke="' + P.wood + '" stroke-width="1.4" opacity="0.7"/><rect x="60" y="46" width="12" height="34" rx="1" fill="' + P.gold + '" opacity="0.5"/></g>' +
        '<g><rect x="98" y="60" width="28" height="20" rx="2" fill="' + P.paper + '" stroke="' + P.wood + '" stroke-width="1.6"/><rect x="104" y="56" width="16" height="6" rx="1" fill="' + P.book + '" opacity="0.8"/></g>' +
        '<g transform="translate(20,42)"><path d="M0 22 Q-2 8 12 6 Q26 8 24 22 Z" fill="' + P.gold + '"/><path d="M0 22 L24 22 L22 26 L2 26 Z" fill="' + P.wood + '"/><g stroke="' + P.paper + '" stroke-width="1.2" stroke-linecap="round"><path d="M8 4 L8 -2 M8 4 L5 -1 M8 4 L11 -1"/></g></g>' +
        '<rect x="128" y="8" width="40" height="72" rx="3" fill="' + P.night + '"/>' +
        '<path d="M132 14 L164 14 M132 22 L164 22" stroke="' + P.cardigan + '" stroke-width="1.6" opacity="0.6"/>' +
        '<g stroke="' + P.gold + '" stroke-width="2" stroke-linecap="round" opacity="0.9"><path d="M144 50 q14 -2 14 -14"/><path d="M144 50 q10 4 10 12"/></g>';
    },
    levels: function () {
      return '<rect x="0" y="0" width="170" height="120" fill="#1d0a28"/>' +
        '<g><rect x="12" y="14" width="44" height="40" rx="6" fill="' + P.cardiganDark + '"/><rect x="18" y="20" width="20" height="26" rx="2" fill="' + P.book + '" opacity="0.7"/><circle cx="46" cy="46" r="4.4" fill="' + P.ok + '"/><path d="M43.6 46 L45.4 48 L48.6 44" stroke="' + P.night + '" stroke-width="1.6" fill="none" stroke-linecap="round"/></g>' +
        '<g><rect x="63" y="14" width="44" height="40" rx="6" fill="' + P.cardiganDark + '"/><rect x="69" y="26" width="20" height="20" rx="2" fill="' + P.book + '" opacity="0.55"/><circle cx="97" cy="46" r="4.4" fill="' + P.low + '"/><path d="M95 44 L99 48 M99 44 L95 48" stroke="' + P.night + '" stroke-width="1.6" stroke-linecap="round"/></g>' +
        '<g><rect x="114" y="14" width="44" height="40" rx="6" fill="' + P.cardiganDark + '"/><rect x="120" y="34" width="20" height="12" rx="2" fill="' + P.book + '" opacity="0.25"/><circle cx="148" cy="46" r="4.4" fill="' + P.out + '"/><path d="M146 44 L150 48 M150 44 L146 48" stroke="' + P.night + '" stroke-width="1.6" stroke-linecap="round"/></g>' +
        '<path d="M34 72 L34 92 M34 92 l-4 -6 M34 92 l4 -6" stroke="' + P.gold + '" stroke-width="1.8" fill="none" stroke-linecap="round" opacity="0.7"/>' +
        '<g transform="translate(126,74)"><path d="M0 4 Q10 8 18 0 L26 -6 Q27 -1 24 3 Q16 12 4 9 Z" fill="' + P.gold + '" stroke="' + P.wood + '" stroke-width="1"/><path d="M0 4 L-3 9" stroke="' + P.wood + '" stroke-width="2" stroke-linecap="round"/></g>' +
        '<text x="85" y="98" text-anchor="middle" font-family="system-ui, sans-serif" font-size="7" fill="' + P.paper + '" opacity="0.75">disponibles · stock bas · rupture</text>';
    },
    ledger: function () {
      return '<rect x="0" y="0" width="170" height="120" fill="#1d0a28"/>' +
        '<rect x="16" y="10" width="138" height="88" rx="6" fill="' + P.paper + '"/>' +
        '<rect x="16" y="10" width="138" height="14" rx="6" fill="' + P.purple + '"/>' +
        '<text x="24" y="20" font-family="system-ui, sans-serif" font-size="7.5" font-weight="bold" fill="#fff">Livre</text>' +
        '<text x="96" y="20" font-family="system-ui, sans-serif" font-size="7.5" font-weight="bold" fill="#fff" text-anchor="middle">Qté</text>' +
        '<text x="140" y="20" font-family="system-ui, sans-serif" font-size="7.5" font-weight="bold" fill="#fff" text-anchor="end">Montant</text>' +
        '<g font-family="system-ui, sans-serif" font-size="7" fill="' + P.deep + '" opacity="0.85">' +
        '<text x="24" y="36">Ruth</text><text x="96" y="36" text-anchor="middle">1</text><text x="140" y="36" text-anchor="end">12,00€</text>' +
        '<text x="24" y="48">Pack Ruth &amp; Marie</text><text x="96" y="48" text-anchor="middle">1</text><text x="140" y="48" text-anchor="end">35,00€</text>' +
        '<text x="24" y="60">Les 7 armes de Dieu</text><text x="96" y="60" text-anchor="middle">2</text><text x="140" y="60" text-anchor="end">24,00€</text>' +
        '<text x="24" y="72">Mariage</text><text x="96" y="72" text-anchor="middle">1</text><text x="140" y="72" text-anchor="end">5,00€</text></g>' +
        '<g stroke="' + P.deep + '" stroke-width="0.8" opacity="0.2"><path d="M16 40 L154 40 M16 52 L154 52 M16 64 L154 64 M16 76 L154 76 M16 84 L154 84"/></g>' +
        '<rect x="16" y="84" width="138" height="14" rx="0" fill="' + P.gold + '" opacity="0.9"/>' +
        '<text x="24" y="94" font-family="system-ui, sans-serif" font-size="7.5" font-weight="bold" fill="' + P.deep + '">Total</text>' +
        '<text x="140" y="94" font-family="system-ui, sans-serif" font-size="7.5" font-weight="bold" fill="' + P.deep + '" text-anchor="end">76,00€</text>';
    },
    vault: function () {
      return '<rect x="0" y="0" width="170" height="120" fill="#1d0a28"/>' +
        '<circle cx="85" cy="58" r="34" fill="' + P.cardiganDark + '" stroke="' + P.gold + '" stroke-width="3.4"/>' +
        '<circle cx="85" cy="58" r="9" fill="' + P.gold + '"/>' +
        '<path d="M85 49 L85 28 M85 67 L85 88 M76 58 L54 58 M94 58 L116 58" stroke="' + P.gold + '" stroke-width="3" stroke-linecap="round"/>' +
        '<circle cx="34" cy="86" r="6" fill="' + P.gold + '"/><circle cx="146" cy="80" r="7" fill="' + P.gold + '"/><circle cx="40" cy="26" r="4" fill="' + P.gold + '"/>';
    },
    night: function () {
      return '<rect x="0" y="0" width="170" height="120" fill="' + P.night + '"/>' +
        '<circle cx="140" cy="24" r="14" fill="' + P.cream + '"/>' +
        '<circle cx="134" cy="20" r="3.6" fill="' + P.night + '"/><circle cx="145" cy="28" r="2.6" fill="' + P.night + '"/>' +
        '<g fill="' + P.cream + '" opacity="0.9"><circle cx="24" cy="22" r="1.6"/><circle cx="52" cy="14" r="1.2"/><circle cx="70" cy="34" r="1.4"/><circle cx="12" cy="44" r="1.2"/></g>' +
        '<rect x="46" y="72" width="50" height="42" rx="6" fill="' + P.cardiganDark + '" stroke="' + P.gold + '" stroke-width="2.5"/>' +
        '<circle cx="71" cy="93" r="6" fill="' + P.gold + '"/><rect x="68" y="90" width="6" height="14" rx="2" fill="' + P.gold + '"/>';
    },
    sheet: function () {
      return '<rect x="0" y="0" width="170" height="120" fill="#1d0a28"/>' +
        '<rect x="18" y="6" width="134" height="98" rx="5" fill="' + P.paper + '"/>' +
        '<rect x="18" y="6" width="134" height="12" rx="5" fill="' + P.excel + '"/>' +
        '<g font-family="system-ui, sans-serif" font-size="7" font-weight="bold" fill="' + P.paper + '" text-anchor="middle">' +
        '<text x="30" y="15">A</text><text x="60" y="15">B</text><text x="90" y="15">C</text><text x="120" y="15">D</text></g>' +
        '<g font-family="system-ui, sans-serif" font-size="6.5" font-weight="bold" fill="' + P.deep + '" text-anchor="middle" opacity="0.8">' +
        '<text x="27" y="30">1</text><text x="27" y="50">2</text><text x="27" y="70">3</text></g>' +
        '<g stroke="' + P.deep + '" stroke-width="0.7" opacity="0.25"><path d="M36 24 L152 24 M36 44 L152 44 M36 64 L152 64 M36 84 L152 84 M36 22 L36 98 M66 22 L66 98 M96 22 L96 98 M126 22 L126 98"/></g>' +
        '<g font-family="system-ui, sans-serif" font-size="7" fill="' + P.deep + '" opacity="0.85">' +
        '<text x="42" y="36">Ruth</text><text x="70" y="36">12</text><text x="100" y="36" fill="' + P.excel + '">12,00</text>' +
        '<text x="42" y="56">Marie</text><text x="70" y="56">5</text><text x="100" y="56" fill="' + P.excel + '">5,00</text>' +
        '<text x="42" y="76">David</text><text x="70" y="76">9</text><text x="100" y="76" fill="' + P.excel + '">9,00</text>' +
        '<text x="42" y="92" font-weight="bold">Total</text><text x="100" y="92" font-weight="bold">26,00</text></g>';
    },
    stage: function () {
      return '<rect x="0" y="0" width="170" height="120" fill="#150a20"/>' +
        '<path d="M85 0 L20 120 L150 120 Z" fill="' + P.gold + '" opacity="0.13"/>' +
        '<path d="M85 0 L40 120 L130 120 Z" fill="' + P.gold + '" opacity="0.10"/>' +
        '<rect x="0" y="106" width="170" height="14" fill="#241626"/>' +
        '<rect x="30" y="106" width="110" height="8" fill="' + P.purple + '" opacity="0.55"/>' +
        '<g stroke="' + P.gold + '" stroke-width="2" opacity="0.8"><path d="M30 6 l0 10 M25 11 l10 0"/><path d="M148 40 l0 10 M143 45 l10 0"/></g>';
    },
    split: function () {
      return '<rect x="0" y="0" width="85" height="120" fill="#f7ead2"/>' +
        '<rect x="85" y="0" width="85" height="120" fill="' + P.night + '"/>' +
        '<circle cx="38" cy="30" r="13" fill="' + P.gold + '"/>' +
        '<g stroke="' + P.gold + '" stroke-width="2" stroke-linecap="round"><path d="M38 12 v6 M38 42 v6 M20 30 h6 M50 30 h6 M25 17 l4 4 M47 39 l4 4 M51 17 l-4 4 M29 39 l-4 4"/></g>' +
        '<circle cx="128" cy="30" r="13" fill="' + P.cream + '"/><circle cx="124" cy="27" r="3" fill="' + P.night + '"/><circle cx="133" cy="34" r="2.4" fill="' + P.night + '"/>' +
        '<g fill="' + P.cream + '"><circle cx="110" cy="60" r="1.4"/><circle cx="150" cy="52" r="1.4"/><circle cx="160" cy="78" r="1.2"/></g>';
    },
    finale: function () {
      return '<rect x="0" y="0" width="170" height="120" fill="#251238"/>' +
        '<path d="M0 0 L170 120 M170 0 L0 120" stroke="' + P.purple + '" stroke-width="34" opacity="0.12"/>' +
        '<g><rect x="16" y="18" width="6" height="6" rx="1" fill="' + P.gold + '" transform="rotate(20 19 21)"/><rect x="148" y="12" width="6" height="6" rx="1" fill="' + P.book + '" transform="rotate(-15 151 15)"/><rect x="120" y="34" width="5" height="5" rx="1" fill="' + P.cream + '" transform="rotate(30 122 36)"/><rect x="30" y="44" width="5" height="5" rx="1" fill="' + P.gold + '" transform="rotate(-25 32 46)"/><circle cx="60" cy="10" r="2.4" fill="' + P.gold + '"/><circle cx="154" cy="58" r="2.4" fill="' + P.book + '"/></g>' +
        '<path d="M55 88 Q85 74 115 88" fill="none" stroke="' + P.gold + '" stroke-width="3"/>' +
        '<path d="M78 80 Q85 70 92 80" fill="none" stroke="' + P.gold + '" stroke-width="2.4"/>';
    }
  };

  function stageSVG(step) {
    var scene = (SCENES[step.scene] || SCENES.shop)();
    var eli = '', sidekick = '', voice = '';
    if (step.off) {
      voice = offstageVoice(122, 96);
      if (step.plume) sidekick = plume(step.plume, step.doveX || 118, step.doveY || 60, step.doveS || 1.2);
    } else {
      var t = step.zoom === 'close' ? 'translate(28,44) scale(1.35)' : 'translate(25,14) scale(0.85)';
      eli = '<g transform="' + t + '">' + eliGroup(step.emo) + '</g>';
      if (step.plume) sidekick = plume(step.plume, step.doveX || 118, step.doveY || 24, step.doveS || 1.15);
    }
    return '<svg viewBox="0 0 170 120" width="170" height="120" role="img" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg">' + scene + eli + sidekick + voice + '</svg>';
  }

  /* ---------- Étapes : navigation réelle + projecteur RESTAURÉS, décor et pose par étape ---------- */

  var STEPS = [
    { scene: 'shop', emo: 'wave', plume: 'fly', doveX: 118, doveY: 22, title: 'Bienvenue dans eLib',
      ref: { q: "Ne crains rien, car je t'ai appelé par ton nom", r: 'Ésaïe 43:1' },
      text: "Bonjour, je suis Eli — et voici Plume, notre petit livre ailé ! Suivez-nous, rien ne sera modifié. Échap pour quitter." },
    { scene: 'chart', emo: 'present', view: 'dashboard', sel: '#dashTabSeg', pos: 'bottom', title: 'Lire le tableau de bord',
      ref: { q: "Écris la vision, grave-la sur des tables, afin qu'on puisse la lire couramment", r: 'Habakuk 2:2' },
      text: "Voici l'activité d'un coup d'œil : la Synthèse et le Studio. Les filtres de période comparent ventes et stocks." },
    { scene: 'scanScene', emo: 'scan', view: 'pos', sel: '#q', pos: 'bottom', title: 'Trouver un livre',
      ref: { q: "Cherchez, et vous trouverez", r: 'Matthieu 7:7' },
      text: "Je scrute les rayonnages : tapez un titre ou un ISBN. Un lecteur de code-barres remplit aussi ce champ." },
    { scene: 'counter', emo: 'hold', view: 'pos', sel: '#items', pos: 'left', title: 'Composer le panier',
      ref: { q: "Il prit les pains, et les distribua", r: 'Jean 6:11' },
      text: "On rassemble, on choisit l'origine de chaque exemplaire et le paiement. Rien n'est enregistré avant « Valider »." },
    { scene: 'warehouse', emo: 'effort', off: true, view: 'stock', sel: '#newLot', pos: 'bottom', title: 'Réceptionner du stock',
      ref: { q: "Joseph amassa du blé... une quantité innombrable", r: 'Genèse 41:49' },
      text: "Deux secondes, je range les sacs de blé ! — Pendant ce temps : cette action ouvre le formulaire livre, origine, quantité, date." },
    { scene: 'levels', emo: 'alert', off: true, plume: 'talk', doveX: 66, doveY: 64, view: 'stock', sel: '#fs', pos: 'bottom', title: 'Surveiller les niveaux',
      ref: { q: "La sentinelle... sonne de la trompette", r: 'Ézéchiel 33:6' },
      text: "« Je sonne l'alerte d'ici ! » — disponibles, stock bas, rupture. Sélectionnez une ligne pour les lots et l'historique." },
    { scene: 'catalog', emo: 'effort', enter: true, view: 'catalog', sel: '#nb', pos: 'bottom', title: 'Gérer le catalogue',
      ref: { q: "Que tout se fasse avec ordre", r: '1 Corinthiens 14:40' },
      text: "Me revoilà, tout est en ordre ! Le catalogue est votre rayonnage numérique : fiches livres et packs, création en haut d'écran." },
    { scene: 'ledger', emo: 'think', view: 'sales', sel: '#view .table-wrap', pos: 'top', title: 'Consulter les ventes',
      ref: { q: "Enseigne-nous à bien compter nos jours", r: 'Psaume 90:12' },
      text: "Là, on réfléchit à deux fois : l'annulation d'une vente restitue le stock. Réservez-la aux vraies erreurs." },
    { scene: 'vault', emo: 'count', view: 'treasury', sel: '#view .grid.g4', pos: 'bottom', title: 'Suivre la trésorerie',
      ref: { q: "Là où est ton trésor, là aussi sera ton cœur", r: 'Matthieu 6:21' },
      text: "Chaque pièce compte : espèces en caisse, paiements à régulariser, sommes à déposer — associées au libraire." },
    { scene: 'night', emo: 'shield', view: 'audit', sel: '#bk', pos: 'bottom', title: 'Protéger les données',
      ref: { q: "Celui qui garde Israël ne sommeille ni ne dort", r: 'Psaume 121:4' },
      text: "La nuit, je monte la garde : journaux et sauvegardes ici. Créez un snapshot avant toute opération importante." },
    { scene: 'sheet', emo: 'busy', view: 'data', sel: '#view .card', pos: 'top', title: 'Données et Excel',
      ref: { q: "Il appliqua son cœur à étudier... et à mettre en pratique", r: 'Esdras 7:10' },
      text: "Comme Esdras le scribe, on remet de l'ordre : imports/exports, origines de stock et listes personnalisables." },
    { scene: 'stage', emo: 'cheer', plume: 'fly', doveX: 130, doveY: 18, sel: '#btnFocusMode', pos: 'bottom', title: 'Régie Live',
      ref: { q: "Je suis dans la joie quand on me dit : allons à la maison de l'Éternel", r: 'Psaume 122:1' },
      text: "Le grand soir : pendant le culte, activez la Régie Live (F11) et suivez en direct les scans des smartphones !" },
    { scene: 'split', emo: 'wink', sel: '#btnThemeToggle', pos: 'bottom', title: 'Thème',
      ref: { q: "La nuit brille comme le jour", r: 'Psaume 139:12' },
      text: "Jour ou nuit, selon votre goût : clair, sombre ou automatique (F10)." },
    { scene: 'finale', emo: 'party', plume: 'fly', doveX: 126, doveY: 12, title: "C'est parti !",
      ref: { q: "Tout ce que vous faites, faites-le de bon cœur, comme pour le Seigneur", r: 'Colossiens 3:23' },
      text: "Vous êtes prêt ! Plume et moi restons là : cliquez sur « ? Aide » en bas à droite pour revoir cette visite." }
  ];

  var list = [], idx = 0, active = false, navigating = false, root = null, stageIdx = -1;

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
        '<div class="tut-stage-wrap"><div class="tut-stage" id="tut-guide"></div></div>' +
        '<div class="tut-count" id="tut-count"></div>' +
        '<h3 id="tut-title"></h3>' +
        '<p id="tut-text"></p>' +
        '<div class="tut-ref" id="tut-ref"></div>' +
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
    var card = $('tut-card'), spot = $('tut-spot'), stage = $('tut-guide');

    $('tut-title').textContent = s.title;
    $('tut-text').textContent = s.text;
    var refEl = $('tut-ref');
    if (s.ref) {
      refEl.style.display = '';
      refEl.textContent = '« ' + s.ref.q + ' » — ' + s.ref.r;
    } else {
      refEl.style.display = 'none';
    }
    $('tut-count').textContent = (idx + 1) + ' / ' + list.length;
    $('tut-prev').style.visibility = idx === 0 ? 'hidden' : 'visible';
    $('tut-next').textContent = idx === list.length - 1 ? 'Terminer' : 'Suivant';

    /* La scène ne se rejoue qu'au changement d'étape (place() est appelé deux fois par étape) */
    if (stageIdx !== idx) {
      stageIdx = idx;
      stage.classList.remove('tut-pop', 'tut-exit', 'tut-enter');
      void stage.offsetWidth;
      stage.innerHTML = stageSVG(s);
      if (s.enter) stage.classList.add('tut-enter');
      else if (s.off) stage.classList.add('tut-exit');
      else stage.classList.add('tut-pop');
    }

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
    stageIdx = -1;
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
    b.title = 'Revoir la visite guidée avec Eli et Plume';
    b.onclick = start;
    document.body.appendChild(b);
  }

  function boot() {
    addHelpButton();
    var done = false;
    try { done = localStorage.getItem(KEY) === '1'; } catch (e) { done = false; }
    if (!done) setTimeout(start, 800);
  }

  // API publique : window.eLibTutorial.start()
  window.eLibTutorial = {
    start: start,
    reset: function () { try { localStorage.removeItem(KEY); } catch (e) { } }
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
