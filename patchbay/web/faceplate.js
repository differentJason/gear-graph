'use strict';
/* Generic faceplates, drawn from data only (name, maker, HP/format, jacks): our own vector art, no product photos.
   VCV Rack's visual grammar: corner screws, name at the top, outputs on dark inset cells, colored jack rings.
   Eurorack modules: vertical panels at true HP width (15 px/HP), 3U = 380 px, 1U = 117 px.
   Everything else: a horizontal "rear panel" strip sized by its jack count.
   build() returns { w, h, body (SVG without jacks), spots: {jack name: {x, y, p, lx, ly, out}} } and is cached. */
const Faceplate = (() => {
  const HPX = 15, U3 = 380, U1 = 117;
  // panel [background, ink]: neutral finishes, picked per maker so a brand keeps one look (not its real trade dress)
  const FINISH = [['#2b2e34', '#eceef1'], ['#d5d8dc', '#1b1d21'], ['#33465b', '#eef2f7'], ['#e7e0cd', '#2b2620'],
                  ['#20392f', '#e7f0ec'], ['#4a2b2b', '#f4eaea'], ['#b7bdc5', '#15171a'], ['#3a3350', '#eeeaf7'],
                  ['#1c1d20', '#e4e6ea'], ['#8a5a2e', '#fbf3ea']];
  const ACCENT = ['#e0591a', '#0b7fe0', '#12a594', '#c29100', '#8e4ec6', '#d13b3f', '#5b8c32', '#d0579a'];
  const cache = new Map();
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const hash = s => { let h = 2166136261; for (const ch of String(s)) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; };
  const trunc = (s, n) => (s.length > n ? s.slice(0, Math.max(1, n - 1)) + '…' : s);
  function wrap(text, width, lines) {
    const out = []; let cur = '';
    for (const w of String(text).split(/\s+/)) {
      if ((cur + ' ' + w).trim().length > width && cur) { out.push(cur); cur = w; } else cur = (cur + ' ' + w).trim();
    }
    if (cur) out.push(cur);
    if (out.length > lines) { out.length = lines; out[lines - 1] = trunc(out[lines - 1], width); }
    return out.map(l => trunc(l, width));
  }
  const shortName = d => String(d.name || d.id).replace(new RegExp('^' + (d.manufacturer || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s+', 'i'), '');
  function finish(d) {
    const [bg, ink] = FINISH[hash(d.manufacturer || d.id) % FINISH.length];
    return { bg, ink, accent: ACCENT[hash(d.id) % ACCENT.length] };
  }
  const order = ports => [...ports.filter(p => p.dir === 'in'), ...ports.filter(p => p.dir !== 'in')];
  const screw = (x, y) => `<g class="fp-screw"><circle cx="${x}" cy="${y}" r="3.4"/><path d="M${x - 2},${y} h4 M${x},${y - 2} v4"/></g>`;

  /* jack grid: cells in reading order, inputs first; output cells get a dark inset */
  function grid(ports, x0, y0, cols, cw, ch, spots) {
    let cells = '';
    ports.forEach((p, i) => {
      const cx = x0 + (i % cols) * cw + cw / 2, top = y0 + Math.floor(i / cols) * ch, out = p.dir !== 'in';
      if (out) cells += `<rect class="fp-outcell" x="${cx - cw / 2 + 2}" y="${top + 1}" width="${cw - 4}" height="${ch - 2}" rx="4"/>`;
      spots[p.name] = { x: cx, y: top + ch * 0.64, lx: cx, ly: top + 10, p, out, chars: Math.max(3, Math.floor((cw - 4) / 4.6)) };
    });
    return cells;
  }

  function euro(d, ports, hp, format) {
    const w = hp * HPX, h = format === '1U' ? U1 : U3, f = finish(d), spots = {}, oneU = format === '1U';
    const narrow = w < 70, fs = narrow ? 7.5 : 10;
    const title = wrap(shortName(d).toUpperCase(), Math.max(4, Math.floor((w - 8) / (fs * 0.62))), oneU ? 1 : 3);
    const titleH = oneU ? 17 : 16 + title.length * (fs + 2);
    const avail = h - titleH - (oneU ? 8 : 22);
    let cols = Math.max(1, Math.floor((w - 6) / 40)), cw = (w - 6) / cols;
    let rows = Math.max(1, Math.ceil(ports.length / cols)), ch = Math.min(46, avail / rows);
    while (ch < 30 && cw > 28) { cols++; cw = (w - 6) / cols; rows = Math.ceil(ports.length / cols); ch = Math.min(46, avail / rows); }
    const y0 = titleH + (oneU ? 0 : Math.max(0, avail - rows * ch) * 0.35);
    const cells = grid(order(ports), 3, y0, cols, cw, ch, spots);
    const screws = [screw(7.5, 7), screw(w - 7.5, h - 7), ...(hp >= 10 ? [screw(w - 7.5, 7), screw(7.5, h - 7)] : [])].join('');
    const body = `<rect class="fp-bg" width="${w}" height="${h}" fill="${f.bg}"/>
      <rect x="0" y="0" width="${w}" height="${h}" fill="url(#fp-sheen)"/>${screws}
      <rect x="${w * 0.2}" y="${titleH - 5}" width="${w * 0.6}" height="1.6" fill="${f.accent}"/>
      ${title.map((t, i) => `<text class="fp-title" x="${w / 2}" y="${oneU ? 12 : 22 + i * (fs + 2)}" font-size="${fs}" fill="${f.ink}" text-anchor="middle">${esc(t)}</text>`).join('')}
      ${cells}
      ${oneU ? '' : `<text class="fp-maker" x="${w / 2}" y="${h - 8}" fill="${f.ink}" text-anchor="middle">${esc(trunc(d.manufacturer || '', Math.floor(w / 4.5)))}</text>`}`;
    return { w, h, body, spots, ink: f.ink };
  }

  function desk(d, ports) {
    const f = finish(d), spots = {}, n = ports.length;
    const rows = n <= 8 ? 1 : n <= 18 ? 2 : 3, cols = Math.max(1, Math.ceil(n / rows)), cw = 46, ch = 46, NAME = 124;
    const w = Math.max(200, NAME + cols * cw + 10), h = Math.max(88, 14 + rows * ch + 10);
    const cells = grid(order(ports), NAME, 12, cols, cw, ch, spots);
    const name = wrap(shortName(d), 17, 3);
    const body = `<rect class="fp-bg" width="${w}" height="${h}" rx="5" fill="${f.bg}"/>
      <rect x="0" y="0" width="${w}" height="${h}" rx="5" fill="url(#fp-sheen)"/>
      <rect x="0" y="0" width="${w}" height="5" rx="2" fill="${f.accent}"/>
      ${screw(8, h - 8)}${screw(w - 8, h - 8)}
      ${name.map((t, i) => `<text class="fp-dname" x="12" y="${26 + i * 14}" fill="${f.ink}">${esc(t)}</text>`).join('')}
      <text class="fp-maker" x="12" y="${26 + name.length * 14 + 2}" fill="${f.ink}">${esc(trunc(d.manufacturer || '', 24))}</text>
      <text class="fp-cat" x="12" y="${h - 22}" fill="${f.ink}">${esc(String(d.category || '').replace(/-/g, ' '))}</text>
      <line x1="${NAME - 6}" y1="12" x2="${NAME - 6}" y2="${h - 12}" stroke="${f.ink}" stroke-opacity=".18"/>
      ${cells}`;
    return { w, h, body, spots, ink: f.ink };
  }

  function build(d, ports, opts = {}) {
    const vis = ports.filter(p => !p.hidden);
    const key = [d.id, opts.kind, opts.hp, opts.format, vis.map(p => `${p.name}|${p.dir}|${p.medium}`).join(';')].join('#');
    if (!cache.has(key)) {
      if (cache.size > 400) cache.clear();
      cache.set(key, opts.kind === 'euro' ? euro(d, vis, opts.hp, opts.format) : desk(d, vis));
    }
    return cache.get(key);
  }

  /* small standalone SVG for palette / node icons */
  function mini(d, ports, opts, size = 40) {
    const fp = build(d, ports, opts);
    const jacks = Object.values(fp.spots).map(s => `<circle cx="${s.x}" cy="${s.y}" r="${Math.max(4, fp.w / 30)}" fill="#cfd3d8" stroke="${MEDIA_COLOR[s.p.medium] || '#888'}" stroke-width="2.5"/>`).join('');
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="-4 -4 ${fp.w + 8} ${fp.h + 8}" width="${size}" height="${size}" preserveAspectRatio="xMidYMid meet">${DEFS}${fp.body}${jacks}</svg>`;
  }
  const MEDIA_COLOR = { audio: '#e0591a', midi: '#8e4ec6', clock: '#0f9384', cv: '#0b7fe0', gate: '#b58800', usb: '#7d808a', power: '#d13b3f' };
  const DEFS = `<defs><linearGradient id="fp-sheen" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".10"/><stop offset=".5" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".12"/></linearGradient></defs>`;
  return { build, mini, DEFS, HPX, U3, U1 };
})();
