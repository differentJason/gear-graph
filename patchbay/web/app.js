'use strict';
/* Gear Patchbay: drag gear onto a canvas, patch jack to jack, note settings, save Songs/Sessions as YAML.
   State lives in `S.session` (plain JSON, the same shape the server saves). render() redraws from it. */

const $ = (sel, el = document) => el.querySelector(sel);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const uid = p => p + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
const clone = o => JSON.parse(JSON.stringify(o));
const slugify = s => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80);

const MEDIA = ['audio', 'midi', 'clock', 'cv', 'gate', 'usb', 'power'];
const MEDIA_LABEL = { audio: 'Audio', midi: 'MIDI', clock: 'Clock/Sync', cv: 'CV', gate: 'Gate/Trig', usb: 'USB', power: 'Power' };
// media that can meet on one cable without a converter (DIN sync clock rides MIDI-style jacks; Eurorack voltages mix)
const COMPAT = [new Set(['midi', 'clock']), new Set(['cv', 'gate', 'clock', 'audio'])];
const compatible = (a, b) => a === b || COMPAT.some(g => g.has(a) && g.has(b));
const CABLE_TYPES = ['', 'TS 1/4"', 'TRS 1/4"', 'XLR', 'MIDI DIN', 'TRS MIDI 3.5mm', 'Patch 3.5mm', 'USB', 'RCA', 'Other'];
const CLOCK_ROLES = ['', 'master', 'follows MIDI clock', 'follows sync/CV clock', 'free-running'];
const NODE_W = 216, HEAD_H = 62, ROW_H = 18, PAD = 8, COLLAPSE_AT = 12;

const S = {
  gear: null, byId: {}, session: null, slug: null, dirty: false,
  sel: null,                // {kind: 'node'|'cable', id}
  view: { x: 40, y: 40, k: 1 },
  undo: [], redo: [], portEdit: null, openSec: {},
};

/* ---------- server (or, on the public website, a read-only static stand-in) ---------- */
/* Static mode: the published site has no server, so gear comes from gear.json beside this page and sessions are kept
   in THIS browser's localStorage (never uploaded). Jack and panel edits need the local app (make serve). */
let STATIC = false;
const LS_SESSIONS = 'gpb:web-sessions';
function lsSessions() { try { return JSON.parse(localStorage.getItem(LS_SESSIONS) || '{}'); } catch (e) { return {}; } }
function lsWrite(all) {
  try { localStorage.setItem(LS_SESSIONS, JSON.stringify(all)); } catch (e) { throw new Error('browser storage is full or blocked'); }
}
async function staticApi(method, path, body) {
  if (path === '/api/gear') {
    const r = await fetch('gear.json');
    if (!r.ok) throw new Error('gear.json not found');
    return r.json();
  }
  if (path === '/api/sessions') {
    return Object.entries(lsSessions()).map(([slug, s]) => ({ slug, name: s.name, type: s.type, bpm: s.bpm, key: s.key,
      date: s.date, updated: s.updated, devices: (s.nodes || []).length, cables: (s.cables || []).length }));
  }
  const m = path.match(/^\/api\/sessions\/([\w-]+)$/);
  if (m) {
    const all = lsSessions();
    if (method === 'GET') { if (!all[m[1]]) throw new Error('not found'); return all[m[1]]; }
    if (method === 'PUT') { const updated = new Date().toISOString().slice(0, 19); all[m[1]] = { ...body, updated }; lsWrite(all); return { slug: m[1], updated }; }
    if (method === 'DELETE') { delete all[m[1]]; lsWrite(all); return {}; }
  }
  throw new Error('read-only on the website: editing jacks needs the local app (make serve)');
}
async function api(method, path, body) {
  if (STATIC) return staticApi(method, path, body);
  let r = null;
  try { r = await fetch(path, { method, headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined }); }
  catch (e) { r = null; }
  const json = r && (r.headers.get('content-type') || '').includes('json');
  if (path === '/api/gear' && (!r || !json)) {           // no server behind this page: the static website
    STATIC = true; document.body.classList.add('static');
    return staticApi(method, path, body);
  }
  if (!r) throw new Error('server not reachable');
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `${r.status} ${r.statusText}`);
  return data;
}
async function loadGear() {
  S.gear = await api('GET', '/api/gear');
  S.byId = Object.fromEntries(S.gear.devices.map(d => [d.id, d]));
}

/* ---------- session lifecycle ---------- */
function blankSession() {
  return { name: 'Untitled', type: 'session', bpm: '', key: '', date: new Date().toISOString().slice(0, 10), tags: '', notes: '', nodes: [], cables: [] };
}
function templateSession(id) {
  const t = clone(S.gear.templates[id]);
  t.cables.forEach(c => { c.uid = c.uid || uid('c'); });
  delete t.description;
  return { ...blankSession(), ...t, name: `Untitled ${t.name.toLowerCase()}` };
}
function templateButtons(attr) {
  return Object.entries(S.gear.templates).map(([id, t]) =>
    `<button ${attr}="${esc(id)}">${esc(t.name)}<small>${esc(t.description || '')} (${t.nodes.length} devices, ${t.cables.length} cables)</small></button>`).join('');
}
function setSession(sess, slug) {
  sess.nodes ||= []; sess.cables ||= [];
  sess.cables.forEach(c => { c.uid ||= uid('c'); c.settings ||= {}; });
  sess.nodes.forEach(n => { n.settings ||= {}; });
  sess.nodes.forEach(n => { if (n.rack) { n.rack.nodes ||= []; n.rack.cables ||= []; n.rack.cables.forEach(c => { c.uid ||= uid('c'); c.settings ||= {}; }); n.rack.nodes.forEach(m => { m.settings ||= {}; }); } });
  S.session = sess; S.slug = slug || null; S.sel = null; S.undo = []; S.redo = []; S.portEdit = null; S.scope = null; S.sessionView = null;
  setDirty(false);
  if (sess.view) S.view = { ...sess.view }; else S.view = { x: 40, y: 40, k: 1 };
  renderAll();
  if (!sess.view && sess.nodes.length) fit();
}
function setDirty(v) {
  S.dirty = v;
  $('#dirty').hidden = !v;
  document.title = (v ? '● ' : '') + (S.session?.name || 'Untitled') + ' · Gear Patchbay';
  if (v) saveDraft();
}
let draftTimer;
function saveDraft() {
  clearTimeout(draftTimer);
  draftTimer = setTimeout(() => {
    try { localStorage.setItem('gpb:draft', JSON.stringify({ slug: S.slug, session: S.session, at: Date.now() })); } catch (e) { /* storage unavailable */ }
  }, 400);
}
function clearDraft() { try { localStorage.removeItem('gpb:draft'); } catch (e) { /* ignore */ } }
function checkpoint() {
  S.undo.push(JSON.stringify(S.session));
  if (S.undo.length > 150) S.undo.shift();
  S.redo = [];
}
function changed() { setDirty(true); renderAll(); }
function undo() {
  if (!S.undo.length) return;
  S.redo.push(JSON.stringify(S.session)); S.session = JSON.parse(S.undo.pop()); S.sel = null; if (!scopeNode()) S.scope = null; changed();
}
function redo() {
  if (!S.redo.length) return;
  S.undo.push(JSON.stringify(S.session)); S.session = JSON.parse(S.redo.pop()); S.sel = null; if (!scopeNode()) S.scope = null; changed();
}

/* ---------- geometry ---------- */
/* The canvas shows ONE graph: the session, or the patch inside a Eurorack node (S.scope = that node's uid). */
const scopeNode = () => S.scope && S.session.nodes.find(n => n.uid === S.scope);
const G = () => scopeNode()?.rack || S.session;
const inRack = () => !!scopeNode();
const RACK_GROUPS = ['Eurorack modules', 'Eurorack cases & power'];
const IO_DEVICES = ['eurorack-in', 'eurorack-out'];
const nodeById = id => G().nodes.find(n => n.uid === id);
const cableById = id => G().cables.find(c => c.uid === id);
function devOf(n) {
  return S.byId[n.device] || { id: n.device, name: `${n.device} (not in gear-kb)`, ports: [], icon: 'icons/_glyph-utility.svg', category: '?', missing: true };
}
function usedPorts(nid) {
  const u = new Map();
  for (const c of G().cables) {
    if (c.from.uid === nid) u.set(c.from.port, c.medium);
    if (c.to.uid === nid) u.set(c.to.port, c.medium);
  }
  return u;
}
function nodePorts(n) {
  const all = devOf(n).ports.filter(p => !p.hidden);
  const used = usedPorts(n.uid);
  const collapsed = n.collapsed ?? all.length > COLLAPSE_AT;
  const names = new Set(all.map(p => p.name));
  const orphans = [...used.keys()].filter(u => !names.has(u)).map(u => ({ name: u, dir: 'bidir', medium: used.get(u), orphan: true }));
  const shown = (collapsed ? all.filter(p => used.has(p.name)) : all).concat(orphans);
  return {
    left: shown.filter(p => p.dir === 'in'), right: shown.filter(p => p.dir !== 'in'),
    collapsed, hiddenCount: all.length - shown.length + orphans.length, total: all.length, used,
  };
}
function nodeGeom(n) {
  const np = nodePorts(n);
  const rows = Math.max(np.left.length, np.right.length);
  const toggle = np.total > COLLAPSE_AT || (np.collapsed && np.hiddenCount > 0) || (n.collapsed === true);
  const h = HEAD_H + PAD + rows * ROW_H + (toggle ? ROW_H : 0) + PAD - (rows ? 0 : 4);
  const pos = {};
  const y0 = HEAD_H + PAD + ROW_H / 2;
  np.left.forEach((p, i) => { pos[p.name] ??= { x: 0, y: y0 + i * ROW_H, side: 'L', p }; });
  np.right.forEach((p, i) => { pos[p.name] ??= { x: NODE_W, y: y0 + i * ROW_H, side: 'R', p }; });
  return { ...np, rows, toggle, h, pos };
}
function portAnchor(nid, port) {
  const n = nodeById(nid); if (!n) return null;
  const g = nodeGeom(n);
  const p = g.pos[port] || { x: NODE_W / 2, y: HEAD_H / 2, side: 'R' };
  return { x: n.x + p.x, y: n.y + p.y, side: p.side };
}
function cablePath(a, b) {
  const dx = Math.max(50, Math.abs(b.x - a.x) * 0.5);
  const c1 = a.x + (a.side === 'L' ? -dx : dx), c2 = b.x + (b.side === 'R' ? dx : -dx);
  return `M${a.x},${a.y} C${c1},${a.y} ${c2},${b.y} ${b.x},${b.y}`;
}
function wrap(text, width, lines) {
  const out = []; let cur = '';
  for (const w of String(text).split(/\s+/)) {
    if ((cur + ' ' + w).trim().length > width && cur) { out.push(cur); cur = w; } else cur = (cur + ' ' + w).trim();
  }
  if (cur) out.push(cur);
  if (out.length > lines) { out.length = lines; out[lines - 1] = out[lines - 1].slice(0, width - 1) + '…'; }
  return out;
}
const trunc = (s, n) => (s.length > n ? s.slice(0, n - 1) + '…' : s);

/* ---------- rendering ---------- */
function renderAll() { renderCanvas(); renderPalette(); renderInspector(); renderChrome(); }
function renderChrome() {
  const s = S.session;
  $('#session-name').textContent = s.name || 'Untitled';
  const b = $('#type-badge'); b.textContent = s.type || 'session'; b.className = 'badge ' + (s.type || '');
  $('#empty').hidden = G().nodes.length > 0;
  const sn = scopeNode();
  $('#crumbs').hidden = !sn;
  if (sn) $('#crumbs').innerHTML = `<button data-act="exit-rack" title="Back to the session (Esc)">← ${esc(s.name || 'Session')}</button><span>›</span><b>${esc(sn.label || 'Eurorack')} patch</b><span class="muted">${sn.rack.nodes.filter(n => !IO_DEVICES.includes(n.device)).length} modules · ${sn.rack.cables.length} cables</span>
      <button data-act="view-mode" title="Switch between faceplates and boxes">${panelMode() ? 'Node view' : 'Panel view'}</button>
      ${panelMode() ? `<button data-act="jack-labels">${S.jackLabels === false ? 'Show' : 'Hide'} jack names</button>` : ''}`;
  if (!s.nodes.length) $('#empty-actions').innerHTML = templateButtons('data-act="load-template" data-template');
  $('[data-act=undo]').disabled = !S.undo.length; $('[data-act=redo]').disabled = !S.redo.length;
  $('[data-act=view-mode]').textContent = panelMode() ? 'Boxes' : 'Panels';
  $('[data-act=photos]').classList.toggle('on', !!S.photos);
  document.title = (S.dirty ? '● ' : '') + (s.name || 'Untitled') + ' · Gear Patchbay';
}
function applyView() {
  $('#world').setAttribute('transform', `translate(${S.view.x},${S.view.y}) scale(${S.view.k})`);
  $('#grid-bg').setAttribute('transform', `translate(${S.view.x % (20 * S.view.k)},${S.view.y % (20 * S.view.k)}) scale(${S.view.k})`);
  $('#zoom').textContent = Math.round(S.view.k * 100) + '%';
}
function renderCanvas() {
  // node view: cables under the boxes; panel view: cables hang over the faceplates, like VCV
  const w = $('#world'), c = $('#cables'), nd = $('#nodes');
  if (panelMode()) { ensurePanelPos(); w.insertBefore(nd, c); } else w.insertBefore(c, nd);
  $('#canvas').classList.toggle('panelmode', panelMode());
  applyView(); renderNodes(); renderCables();
}

function nodeSummary(n, dev) {
  return (dev.rack && n.rack ? `${n.rack.nodes.filter(m => !IO_DEVICES.includes(m.device)).length} modules · ${n.rack.cables.length} patch cables · open ▸` : '')
    || stateSummary(n, dev) || n.settings?.preset || '';
}
function nodeSVG(n) {
  const dev = devOf(n), g = nodeGeom(n);
  const sel = S.sel?.kind === 'node' && S.sel.id === n.uid;
  const title = wrap(n.label || dev.name, 21, 2);
  const summary = nodeSummary(n, dev);
  const sub = n.label ? dev.name : [dev.manufacturer, dev.category].filter(Boolean).join(' · ');
  const port = (p, side) => {
    const pp = g.pos[p.name]; const used = g.used.has(p.name);
    const cx = side === 'L' ? 0 : NODE_W, tx = side === 'L' ? 11 : NODE_W - 11;
    const shape = p.dir === 'bidir'
      ? `<path class="jack ${used ? 'used' : ''}" d="M${cx},${pp.y - 6} L${cx + 6},${pp.y} L${cx},${pp.y + 6} L${cx - 6},${pp.y} Z"/>`
      : `<circle class="jack ${used ? 'used' : ''}" cx="${cx}" cy="${pp.y}" r="5.5"/>`;
    return `<g class="port m-${p.medium} ${p.orphan ? 'orphan' : ''}" data-node="${esc(n.uid)}" data-port="${esc(p.name)}">
      <circle class="jack-hit" cx="${cx}" cy="${pp.y}" r="10"/>${shape}
      <text class="port-label" x="${tx}" y="${pp.y + 3.5}" text-anchor="${side === 'L' ? 'start' : 'end'}">${esc(trunc(p.name, 17))}</text>
      <title>${esc(p.name)} · ${MEDIA_LABEL[p.medium] || p.medium} ${p.dir}${p.orphan ? ' · NOT a port of this device any more' : ''}${p.source ? ' · from ' + p.source : ''}</title></g>`;
  };
  const ty = HEAD_H + PAD + g.rows * ROW_H + ROW_H / 2 + 4;
  const toggle = g.toggle ? `<text class="more" data-toggle="${esc(n.uid)}" x="${NODE_W / 2}" y="${ty}" text-anchor="middle">${g.collapsed ? `▾ ${g.hiddenCount} more jack${g.hiddenCount === 1 ? '' : 's'}` : '▴ show used jacks only'}</text>` : '';
  return `<g class="node ${sel ? 'sel' : ''} ${dev.missing ? 'missing' : ''}" data-node="${esc(n.uid)}" data-device="${esc(n.device)}" transform="translate(${n.x},${n.y})">
    <rect class="node-body" width="${NODE_W}" height="${g.h}" rx="10"/>
    <rect class="icon-tile" x="8" y="8" width="46" height="46" rx="7"/>
    ${S.photos || dev.missing ? `<image href="${esc(dev.icon)}" x="10" y="10" width="42" height="42" preserveAspectRatio="xMidYMid meet"/>`
      : Faceplate.mini(dev, dev.ports, faceOpts(dev), 42).replace('<svg ', '<svg x="10" y="10" ')}
    ${title.map((t, i) => `<text class="node-title" x="62" y="${title.length === 1 ? 30 : 23 + i * 15}">${esc(t)}</text>`).join('')}
    <text class="${summary ? 'node-preset' : 'node-sub'}" x="62" y="${title.length === 1 ? 46 : 53}">${esc(trunc(summary || sub, 28))}</text>
    <line class="node-sep" x1="0" x2="${NODE_W}" y1="${HEAD_H}" y2="${HEAD_H}"/>
    ${g.left.map(p => port(p, 'L')).join('')}${g.right.map(p => port(p, 'R')).join('')}${toggle}
  </g>`;
}
function renderNodes() {
  if (panelMode()) { $('#nodes').innerHTML = renderRails() + G().nodes.map(panelSVG).join(''); return; }
  const bands = inRack() ? (G().bands || []).map(b => `<text class="band-label" x="320" y="${b.y}">${esc(b.text)}</text>`).join('') : '';
  $('#nodes').innerHTML = bands + G().nodes.map(nodeSVG).join('');
}
function cableLabel(c) {
  const s = c.settings || {};
  const parts = [];
  if (s.label) parts.push(s.label);
  if (c.medium === 'midi' && s.channel) parts.push('ch ' + s.channel);
  if (s.level) parts.push(s.level);
  return parts.join(' · ');
}
function renderCables() {
  $('#cables').innerHTML = G().cables.map(c => {
    const pm = panelMode();
    const a = pm ? panelAnchor(c.from.uid, c.from.port) : portAnchor(c.from.uid, c.from.port);
    const b = pm ? panelAnchor(c.to.uid, c.to.port) : portAnchor(c.to.uid, c.to.port);
    if (!a || !b) return '';
    const d = pm ? sagPath(a, b) : cablePath(a, b), sel = S.sel?.kind === 'cable' && S.sel.id === c.uid, lab = cableLabel(c);
    if (pm) return `<g class="cable vcv m-${c.medium} ${sel ? 'sel' : ''}" data-cable="${esc(c.uid)}">
      <path class="cable-hit" d="${d}"/><path class="cable-line" d="${d}"/>
      <circle class="plug" cx="${a.x}" cy="${a.y}" r="6.5"/><circle class="plug" cx="${b.x}" cy="${b.y}" r="6.5"/>
      ${lab ? `<text class="vcv-tag" x="${(a.x + b.x) / 2}" y="${Math.max(a.y, b.y) + 22 + Math.hypot(b.x - a.x, b.y - a.y) * 0.11}" text-anchor="middle">${esc(lab)}</text>` : ''}</g>`;
    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
    return `<g class="cable m-${c.medium} ${sel ? 'sel' : ''}" data-cable="${esc(c.uid)}">
      <path class="cable-hit" d="${d}"/><path class="cable-line" d="${d}"/>
      ${lab ? `<g class="cable-tag"><rect x="${mx - lab.length * 3.3 - 6}" y="${my - 9}" width="${lab.length * 6.6 + 12}" height="18" rx="9"/><text x="${mx}" y="${my + 4}" text-anchor="middle">${esc(lab)}</text></g>` : ''}
    </g>`;
  }).join('');
}
function renderLegend() {
  $('#legend').innerHTML = S.gear.media.map(m => `<span class="m-${m}"><i></i>${MEDIA_LABEL[m]}</span>`).join('') +
    '<span title="○ in / out · ◇ both ways">○ jack ◇ bidirectional</span>';
}

/* ---------- palette ---------- */
function renderPalette() {
  const q = $('#search').value.trim().toLowerCase(), inUse = $('#in-use').checked;
  const counts = {};
  G().nodes.forEach(n => { counts[n.device] = (counts[n.device] || 0) + 1; });
  const open = new Set([...document.querySelectorAll('.palette details[open]')].map(d => d.dataset.group));
  const first = !document.querySelector('.palette details');
  $('#palette-list').innerHTML = S.gear.groups.map(g => {
    if (RACK_GROUPS.includes(g) !== inRack()) return '';
    const items = S.gear.devices.filter(d => d.group === g && (!inUse || d.in_use) &&
      (!q || `${d.name} ${d.manufacturer} ${d.category} ${d.model}`.toLowerCase().includes(q)));
    if (!items.length) return '';
    const isOpen = q || first || open.has(g);
    return `<details data-group="${esc(g)}" ${isOpen ? 'open' : ''}><summary>${esc(g)} <span class="muted">${items.length}</span></summary>
      ${items.map(d => `<div class="pal-item" draggable="true" data-device="${esc(d.id)}" title="Drag onto the canvas (or double-click)">
        ${iconHTML(d)}<span class="nm"><b>${esc(d.name)}</b><small>${esc(d.category)}${d.in_use ? '' : ' · unused'}</small></span>
        <span class="cnt">${counts[d.id] ? '×' + counts[d.id] : ''}</span></div>`).join('')}</details>`;
  }).join('') || '<p class="muted" style="padding:8px">No gear matches.</p>';
}

/* ---------- inspector ---------- */
const field = (label, bind, value, opts = {}) => {
  const v = esc(value ?? '');
  let input;
  if (opts.options) input = `<select data-bind="${bind}">${opts.options.map(o => `<option value="${esc(o)}" ${String(o) === String(value ?? '') ? 'selected' : ''}>${esc(opts.labels?.[o] ?? (o || '—'))}</option>`).join('')}</select>`;
  else if (opts.area) input = `<textarea data-bind="${bind}" rows="${opts.rows || 4}" placeholder="${esc(opts.ph || '')}">${v}</textarea>`;
  else input = `<input data-bind="${bind}" value="${v}" placeholder="${esc(opts.ph || '')}" ${opts.type ? `type="${opts.type}"` : ''}>`;
  return `<label class="field"><span>${esc(label)}</span>${input}</label>`;
};
function renderInspector() {
  const el = $('#inspector');
  if (S.sel?.kind === 'node' && nodeById(S.sel.id)) el.innerHTML = nodeInspector(nodeById(S.sel.id));
  else if (S.sel?.kind === 'cable' && cableById(S.sel.id)) el.innerHTML = cableInspector(cableById(S.sel.id));
  else el.innerHTML = inRack() ? rackInspector() : sessionInspector();
}
function rackInspector() {
  const n = scopeNode(), r = n.rack, w = warnings();
  const placed = S.gear.devices.filter(d => d.placement?.case);
  const have = new Set(r.nodes.map(m => m.device));
  const missing = placed.filter(d => !have.has(d.id));
  return `<h3>${esc(n.label || 'Eurorack')} patch</h3>
    <p class="muted">Module-to-module patching for this ${S.session.type === 'song' ? 'song' : 'session'}. <b>Rack inputs</b> / <b>Rack outputs</b> are the Eurorack's jacks on the session canvas.</p>
    ${field('Patch notes', 'rack.notes', r.notes, { area: true, rows: 5, ph: 'What the patch does, knob positions to recall…' })}
    <div class="btns"><button data-act="rack-add-all" ${missing.length ? '' : 'disabled'}>Add installed modules (${missing.length})</button><button data-act="rack-arrange">Arrange by case</button></div>
    <p class="muted">Layout follows gear-kb placements: case → row → position (then name).</p>
    <h4>Checks</h4>${w.length ? w.map(x => `<div class="warn" data-goto="${esc(x.kind)}:${esc(x.id)}">⚠ ${esc(x.text)}</div>`).join('') : '<div class="ok">✓ No problems found</div>'}
    ${rackPower()}
    <div class="btns"><button data-act="exit-rack">← Back to session</button></div>`;
}
function rackPower() {
  const sup = S.byId.eurorack?.rack_supplies || [];
  if (!sup.length) return '';
  return `<h4>Power (gear-kb, all installed modules)</h4><dl class="facts">${sup.map(x => `<dt>${esc(x.name)}</dt><dd>${Object.entries(x.rails).map(([r, v]) => `${r} ${v.pct}%`).join(' · ')}</dd>`).join('')}</dl>`;
}
function sessionInspector() {
  const s = S.session, w = warnings();
  return `<h3>${s.type === 'song' ? 'Song' : 'Session'}</h3>
    ${field('Name', 'session.name', s.name)}
    <div class="row2">${field('Type', 'session.type', s.type, { options: ['session', 'song'], labels: { session: 'Session', song: 'Song' } })}${field('Date', 'session.date', s.date, { type: 'date' })}</div>
    <div class="row2">${field('BPM', 'session.bpm', s.bpm, { ph: '120' })}${field('Key / scale', 'session.key', s.key, { ph: 'F# minor' })}</div>
    ${field('Tags', 'session.tags', s.tags, { ph: 'live, techno, jam' })}
    ${field('Notes', 'session.notes', s.notes, { area: true, rows: 6, ph: 'Arrangement, what to recall, mix notes…' })}
    <h4>Checks</h4>${w.length ? w.map(x => `<div class="warn" data-goto="${esc(x.kind)}:${esc(x.id)}">⚠ ${esc(x.text)}</div>`).join('') : '<div class="ok">✓ No problems found</div>'}
    <h4>Summary</h4><p class="muted">${s.nodes.length} device${s.nodes.length === 1 ? '' : 's'}, ${s.cables.length} cable${s.cables.length === 1 ? '' : 's'}${S.slug ? ` · saved as <code>sessions/${esc(S.slug)}.yaml</code>` : ' · not saved yet'}</p>
    ${S.gear.open_statements?.length ? `<details><summary class="muted">Studio facts from gear-kb</summary><ul class="muted">${S.gear.open_statements.map(t => `<li>${esc(t)}</li>`).join('')}</ul></details>` : ''}
    <p class="muted">Gear data built ${esc(S.gear.generated)} from gear-kb ${esc(S.gear.kb_commit || '')}.</p>`;
}
function facts(dev) {
  const rows = [];
  if (dev.midi) rows.push(['Home MIDI ch', `in ${dev.midi.in ?? '—'} / out ${dev.midi.out ?? '—'}${dev.midi.role ? ` (${dev.midi.role})` : ''}`]);
  const sp = dev.specs || {};
  const val = k => sp[k] && sp[k].value != null ? `${sp[k].value}${sp[k].status && sp[k].status !== 'confirmed' ? ` (${sp[k].status})` : ''}` : null;
  if (val('hp')) rows.push(['Width', val('hp') + ' HP']);
  const draw = [['+12V', 'ma_p12'], ['−12V', 'ma_m12'], ['+5V', 'ma_p5']].map(([r, k]) => val(k) ? `${r} ${val(k)} mA` : null).filter(Boolean);
  if (draw.length) rows.push(['Draw', draw.join(', ')]);
  if (dev.placement) rows.push(['Placed in', `${S.byId[dev.placement.case]?.name || dev.placement.case}${dev.placement.row ? ' · ' + dev.placement.row : ''}`], ['Powered by', S.byId[dev.placement.powered_by]?.name || dev.placement.powered_by]);
  if (dev.supply_load) rows.push(['Load', Object.entries(dev.supply_load).map(([r, x]) => `${r} ${x.draw_ma}/${x.capacity_ma} mA (${x.pct}%)`).join(', ')]);
  if (dev.role) rows.push(['Role', dev.role]);
  return rows.length ? `<dl class="facts">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>` : '<p class="muted">No extra facts in gear-kb.</p>';
}
function nodeInspector(n) {
  const dev = devOf(n), st = n.settings || {};
  const midiPh = dev.midi?.in != null ? `home: ${dev.midi.in}` : '1–16 / omni';
  const midiOutPh = dev.midi?.out != null ? `home: ${dev.midi.out}` : '1–16';
  const custom = st.fields || [];
  return `<div class="dev-head">${iconHTML(dev, 56)}<div><b>${esc(dev.name)}</b><small>${esc([dev.manufacturer, dev.category].filter(Boolean).join(' · '))}</small></div></div>
    ${field('Label on canvas (optional)', 'node.label', n.label, { ph: dev.name })}
    <h4>Patch settings</h4>
    ${field('Preset / patch / pattern', 'node.settings.preset', st.preset, { ph: 'e.g. Kit 03, Pattern A07' })}
    <div class="row2">${field('MIDI in ch', 'node.settings.midi_in', st.midi_in, { ph: midiPh })}${field('MIDI out ch', 'node.settings.midi_out', st.midi_out, { ph: midiOutPh })}</div>
    ${field('Clock role', 'node.settings.clock', st.clock, { options: CLOCK_ROLES })}
    ${field('Levels / knob positions', 'node.settings.levels', st.levels, { area: true, rows: 3, ph: 'Cutoff 2 o\'clock, VOL 70%…' })}
    ${field('Notes', 'node.settings.notes', st.notes, { area: true, rows: 4 })}
    ${dev.fields ? stateInspector(n, dev) : ''}
    <h4>Extra fields</h4>
    ${custom.map((f, i) => `<div class="kv"><input data-bind="node.settings.fields.${i}.name" value="${esc(f.name)}" placeholder="name"><input data-bind="node.settings.fields.${i}.value" value="${esc(f.value)}" placeholder="value"><button data-act="field-del" data-i="${i}" title="Remove field">✕</button></div>`).join('')}
    <button data-act="field-add">+ Add field</button>
    ${dev.rack ? `<h4>Rack patch</h4><p class="muted">${n.rack ? `${n.rack.nodes.filter(m => !IO_DEVICES.includes(m.device)).map(m => esc(m.label || devOf(m).name)).join(', ') || 'No modules yet'}.` : ''}</p>
      <div class="btns"><button data-act="enter-rack" class="primary">Open rack patch ▸</button></div>${rackPower()}` : ''}
    <h4>From gear-kb</h4>${facts(dev)}
    ${dev.note ? `<p class="muted">${esc(dev.note)}</p>` : ''}
    ${panelMode() && usePhoto(n) ? (() => {
      const names = dev.ports.filter(p => !p.hidden).map(p => p.name), cal = dev.jack_pos || {};
      const k = names.filter(x => cal[x]).length;
      return `<h4>Jacks on the panel</h4><p class="muted">${k} of ${names.length} jacks placed on the ${dev.panel ? 'panel photo' : 'panel'}. Unplaced jacks sit in a default grid (dashed rings).</p>
        <div class="btns"><button data-act="place-jacks" class="primary" ${k === names.length ? 'disabled' : ''}>Place jacks…</button><button data-act="place-jacks" data-all="1">Re-place all</button>${k ? '<button data-act="place-reset" class="danger">Reset</button>' : ''}</div>`;
    })() : ''}
    <h4>Jacks</h4>${portEditor(n, dev)}
    <div class="btns"><button data-act="dup">Duplicate</button><button data-act="delete" class="danger">Remove from session</button></div>`;
}
function portEditor(n, dev) {
  if (dev.missing) return '<p class="muted">Device not in gear-kb; jacks can’t be edited.</p>';
  const g = nodeGeom(n);
  const toggle = `<label class="check"><input type="checkbox" data-act="collapse" ${g.collapsed ? '' : 'checked'}> Show all ${g.total} jacks on the canvas</label>`;
  if (!S.portEdit || S.portEdit.device !== dev.id) {
    const src = {};
    dev.ports.forEach(p => { src[p.source] = (src[p.source] || 0) + 1; });
    return `${toggle}<p class="muted">${dev.ports.filter(p => !p.hidden).length} jacks (${Object.entries(src).map(([k, v]) => `${v} ${k}`).join(', ')}).
      Manual-derived jacks are unverified; defaults are guesses by category.</p><button data-act="ports-edit">Edit jacks…</button>`;
  }
  const rows = S.portEdit.rows;
  return `${toggle}<table class="ports-tbl"><tbody>${rows.map((p, i) => `<tr class="${p.hidden ? 'hid' : ''}">
      <td><input type="text" data-pe="${i}.name" value="${esc(p.name)}"></td>
      <td><select data-pe="${i}.dir">${['in', 'out', 'bidir'].map(d => `<option ${p.dir === d ? 'selected' : ''}>${d}</option>`).join('')}</select></td>
      <td><select data-pe="${i}.medium">${MEDIA.map(m => `<option ${p.medium === m ? 'selected' : ''}>${m}</option>`).join('')}</select></td>
      <td><input type="checkbox" title="Hide this jack" data-pe="${i}.hidden" ${p.hidden ? 'checked' : ''}></td>
    </tr><tr><td colspan="4" class="src">${esc(p.source === 'you' ? 'yours' : p.source)}${p.evidence ? ' · ' + esc(trunc(p.evidence, 70)) : ''}</td></tr>`).join('')}</tbody></table>
    <p class="muted">Checkbox = hide. Saved for this device in every session (ports.yaml).</p>
    <div class="btns"><button data-act="port-add">+ Jack</button><button data-act="ports-save" class="primary">Save jacks</button><button data-act="ports-cancel">Cancel</button></div>`;
}
function cableInspector(c) {
  const a = nodeById(c.from.uid), b = nodeById(c.to.uid), st = c.settings || {};
  const w = warnings().filter(x => x.kind === 'cable' && x.id === c.uid);
  return `<h3><span class="pill m-${c.medium}"></span>Cable</h3>
    <p><b>${esc(a ? (a.label || devOf(a).name) : '?')}</b> · ${esc(c.from.port)}<br>→ <b>${esc(b ? (b.label || devOf(b).name) : '?')}</b> · ${esc(c.to.port)}</p>
    ${w.map(x => `<div class="warn">⚠ ${esc(x.text)}</div>`).join('')}
    ${field('Signal', 'cable.medium', c.medium, { options: MEDIA, labels: MEDIA_LABEL })}
    ${c.medium === 'midi' ? field('MIDI channel(s)', 'cable.settings.channel', st.channel, { ph: 'e.g. 1, or 1-4, or all' }) : ''}
    <div class="row2">${field('Cable', 'cable.settings.cable', st.cable, { options: CABLE_TYPES })}${field('Level / attenuation', 'cable.settings.level', st.level, { ph: '-6 dB, 50%' })}</div>
    ${field('Label on canvas', 'cable.settings.label', st.label, { ph: 'e.g. kick, bass CV' })}
    ${field('Notes', 'cable.settings.notes', st.notes, { area: true })}
    <div class="btns"><button data-act="reverse">Reverse direction</button><button data-act="delete" class="danger">Delete cable</button></div>`;
}

/* ---------- Eurorack panel view (VCV Rack style): faceplates sized by HP in case rows, sagging cables ----------
   Panel positions live in node.px/py (the node view keeps x/y), so each view keeps its own layout. */
const HPX = 15, U3 = 380, U1 = 117;  // px per HP; 3U = 128.5 mm and 1U (Intellijel) = 39.65 mm at the same scale
const panelMode = () => S.viewMode !== 'nodes';
/* Generated faceplates (web/faceplate.js). Photo panels were retired 2026-09-23 (no dev.panel), so this is always false. */
const usePhoto = n => S.photos && inRack() && !!devOf(n).panel && !IO_DEVICES.includes(n.device);
const EURO_CATS = ['eurorack-module', 'eurorack-case', 'eurorack-power', 'rack-io'];
function faceOpts(d, n) {
  const euro = n ? inRack() : EURO_CATS.includes(d.category);
  if (!euro) return { kind: 'desk' };
  const io = IO_DEVICES.includes(d.id), isCase = d.category === 'eurorack-case' || d.category === 'eurorack-power';
  return { kind: 'euro', hp: io || isCase ? 6 : (d.hp || 8), format: io || isCase ? '3U' : (d.format || '3U') };
}
const fpOf = n => Faceplate.build(devOf(n), devOf(n).ports, faceOpts(devOf(n), n));
function iconHTML(d, size = 36) {
  return S.photos ? `<img src="${esc(d.icon)}" alt="" loading="lazy">` : `<span class="mini">${Faceplate.mini(d, d.ports, faceOpts(d), size)}</span>`;
}
/* Nodes that have never been shown as panels get a position: the rack arranges by case, the session scales the
   box layout (panels are wider and flatter than boxes). */
function ensurePanelPos() {
  const ns = G().nodes.filter(n => n.px == null);
  if (!ns.length) return;
  if (inRack()) return arrangePanels();
  ns.forEach(n => { n.px = Math.round(n.x * 2.1); n.py = Math.round(n.y * 0.75); });
}
function panelSize(n) {
  if (!usePhoto(n)) { const f = fpOf(n), o = faceOpts(devOf(n), n); return { w: f.w, h: f.h, hp: o.hp || Math.round(f.w / HPX) }; }
  const d = devOf(n);
  const hp = IO_DEVICES.includes(n.device) ? 6 : (d.hp || (d.category === 'eurorack-case' ? 6 : 8));
  return { w: hp * HPX, h: d.format === '1U' ? U1 : U3, hp };
}
/* Jack spots: calibrated ones from panels.yaml (fractions of the panel), others in a tidy grid on the lower panel. */
function jackSpots(n) {
  if (!usePhoto(n)) {  // generated faceplate: jacks are exactly where the generator drew them
    const spots = { ...fpOf(n).spots };
    [...usedPorts(n.uid).keys()].filter(k => !spots[k]).forEach((k, i) => { spots[k] = { x: 10 + i * 14, y: 10, p: { name: k, dir: 'bidir', medium: 'audio', orphan: true }, cal: true }; });
    Object.values(spots).forEach(sp => { sp.cal = true; });
    return spots;
  }
  const d = devOf(n), { w, h, hp } = panelSize(n), cal = d.jack_pos || {};
  const ports = d.ports.filter(p => !p.hidden);
  const ordered = [...ports.filter(p => p.dir === 'in'), ...ports.filter(p => p.dir !== 'in')];
  const free = ordered.filter(p => !cal[p.name]);
  const cols = Math.max(1, Math.min(6, Math.floor(hp / 4) || 1)), rows = Math.max(1, Math.ceil(free.length / cols));
  const oneU = d.format === '1U', top = oneU ? 0.3 : (IO_DEVICES.includes(n.device) ? 0.16 : 0.5), bottom = oneU ? 0.78 : 0.93;
  const spots = {};
  free.forEach((p, i) => {
    const r = Math.floor(i / cols), c = i % cols;
    spots[p.name] = { x: w * (c + 0.5) / cols, y: h * (rows === 1 ? (top + bottom) / 2 : top + (bottom - top) * r / (rows - 1)), p, cal: false };
  });
  ordered.forEach(p => { if (cal[p.name]) spots[p.name] = { x: cal[p.name][0] * w, y: cal[p.name][1] * h, p, cal: true }; });
  // cables on jacks that no longer exist: park them at the top edge so they stay visible
  [...usedPorts(n.uid).keys()].filter(k => !spots[k]).forEach((k, i) => { spots[k] = { x: 10 + i * 14, y: 10, p: { name: k, dir: 'bidir', medium: 'audio', orphan: true }, cal: false }; });
  return spots;
}
function panelSVG(n) {
  const d = devOf(n), { w, h } = panelSize(n), sel = S.sel?.kind === 'node' && S.sel.id === n.uid;
  const spots = jackSpots(n), used = usedPorts(n.uid), labels = S.jackLabels !== false;
  const placing = S.placing?.uid === n.uid ? S.placing.queue[S.placing.i] : null;
  const cols = Math.max(1, Math.min(6, Math.floor(panelSize(n).hp / 4) || 1));
  const labelChars = Math.max(4, Math.floor(w / cols / 5.2));  // a label never runs past its jack column
  const gen = !usePhoto(n), fp = gen ? fpOf(n) : null;
  const face = gen ? fp.body : d.panel
    ? `<image href="${esc(d.panel)}" width="${w}" height="${h}" preserveAspectRatio="none"/>`
    : `<rect class="panel-plain" width="${w}" height="${h}"/>${wrap(n.label || d.name, Math.max(6, Math.floor(w / 7)), 4).map((t, i) =>
        `<text class="panel-name" x="${w / 2}" y="${26 + i * 13}" text-anchor="middle">${esc(t)}</text>`).join('')}`;
  const jacks = Object.entries(spots).map(([name, sp]) => `<g class="port vjack m-${sp.p.medium} ${sp.cal ? '' : 'approx'} ${placing === name ? 'placing' : ''} ${sp.p.orphan ? 'orphan' : ''}" data-node="${esc(n.uid)}" data-port="${esc(name)}">
      <circle class="jack-hit" cx="${sp.x}" cy="${sp.y}" r="11"/><circle class="vjack-ring" cx="${sp.x}" cy="${sp.y}" r="7"/><circle class="vjack-hole ${used.has(name) ? 'used' : ''}" cx="${sp.x}" cy="${sp.y}" r="3.2"/>
      ${labels ? (gen && sp.ly != null
        ? `<text class="fp-jlabel" x="${sp.lx}" y="${sp.ly}" fill="${sp.out ? '#f2f3f5' : fp.ink}" text-anchor="middle">${esc(trunc(name, sp.chars))}</text>`
        : `<text class="vjack-label" x="${sp.x}" y="${sp.y + 17}" text-anchor="middle">${esc(trunc(name, labelChars))}</text>`) : ''}
      <title>${esc(name)} · ${MEDIA_LABEL[sp.p.medium] || sp.p.medium} ${sp.p.dir}${sp.cal ? '' : ' · approximate spot (use Place jacks)'}${sp.p.source ? ' · from ' + sp.p.source : ''}</title></g>`).join('');
  return `<g class="node panel ${sel ? 'sel' : ''}" data-node="${esc(n.uid)}" data-device="${esc(n.device)}" transform="translate(${n.px},${n.py})">
    <rect class="panel-shadow" x="2" y="3" width="${w}" height="${h}" rx="2"/>${face}
    ${gen && faceOpts(d, n).kind === 'desk' && nodeSummary(n, d) ? `<rect class="fp-sumbg" x="6" y="${h - 21}" width="${Math.min(w - 12, 170)}" height="15" rx="3"/><text class="fp-summary" x="11" y="${h - 10}">${esc(trunc(nodeSummary(n, d), Math.floor(Math.min(w - 12, 170) / 5.8)))}</text>` : ''}
    ${n.label && gen ? `<text class="fp-label" x="${w / 2}" y="-6" text-anchor="middle">${esc(n.label)}</text>` : ''}
    <rect class="panel-edge" width="${w}" height="${h}" rx="1.5"/>${jacks}<title>${esc(n.label || d.name)}${d.hp ? ` · ${d.hp} HP` : ''}</title></g>`;
}
function panelAnchor(nid, port) {
  const n = nodeById(nid); if (!n) return null;
  const sp = jackSpots(n)[port] || { x: panelSize(n).w / 2, y: 10 };
  return { x: n.px + sp.x, y: n.py + sp.y, side: 'P' };
}
/* VCV-style cable: hangs under its own weight (control point below the midpoint, deeper for longer spans). */
function sagPath(a, b) {
  const dist = Math.hypot(b.x - a.x, b.y - a.y), sag = 30 + dist * 0.22;
  return `M${a.x},${a.y} Q${(a.x + b.x) / 2},${Math.max(a.y, b.y) + sag} ${b.x},${b.y}`;
}
function renderRails() {
  return (G().rails || []).map(r => `<g class="rail"><rect class="rail-bg" x="${r.x}" y="${r.y}" width="${r.w}" height="${r.h}"/>
    <rect class="rail-bar" x="${r.x}" y="${r.y - 7}" width="${r.w}" height="7"/><rect class="rail-bar" x="${r.x}" y="${r.y + r.h}" width="${r.w}" height="7"/>
    <text class="band-label" x="${r.x}" y="${r.y - 14}">${esc(r.label)}</text></g>`).join('');
}
/* Rows from the gear-kb cases (top to bottom); modules by placement row + position, spilling into the next row of the
   same format when a row is full. placement.row may be a format (1U/3U) or a 1-based row number. */
function arrangePanels() {
  const r = G(), GAP = 70; let y = 40; const rails = [], slots = [];
  for (const c of S.gear.cases || []) c.rows.forEach((row, i) => {
    slots.push({ caseId: c.id, idx: i + 1, format: row.format, hp: row.hp, used: 0, label: `${c.name} · row ${i + 1} (${row.format}, ${row.hp} HP)` });
  });
  const mods = r.nodes.filter(n => !IO_DEVICES.includes(n.device) && devOf(n).category !== 'eurorack-case');
  const order = (a, b) => (devOf(a).placement?.position ?? 999) - (devOf(b).placement?.position ?? 999) || devOf(a).name.localeCompare(devOf(b).name);
  const extra = { caseId: null, idx: 0, format: '3U', hp: 84, used: 0, label: 'Not placed in a case (gear-kb)' };
  const placed = new Map();
  for (const n of mods.sort(order)) {
    const pl = devOf(n).placement, { hp } = panelSize(n), fmt = devOf(n).format;
    let cand = slots.filter(sl => pl?.case && sl.caseId === pl.case && sl.format === fmt);
    // gear-kb row_index (1-based, the case's `rows` order) is exact; a bare number in `row` means the same.
    // "3U" in `row` is a format, not row 3: then fill the first row of that format with room, spilling downward.
    const want = pl?.row_index ? +pl.row_index : /^\d+$/.test(String(pl?.row ?? '')) ? +pl.row : 0;
    const exact = want ? slots.find(sl => sl.caseId === pl.case && sl.idx === want) : null;
    const slot = exact || cand.find(sl => sl.used + hp <= sl.hp) || (pl?.case ? cand.at(-1) : null) || extra;
    placed.set(n.uid, { slot, x: slot.used }); slot.used += hp;
  }
  const all = [...slots, ...(extra.used ? [extra] : [])];
  for (const sl of all) {
    const h = sl.format === '1U' ? U1 : U3;
    sl.y = y; rails.push({ x: 200, y, w: Math.max(sl.hp, sl.used) * HPX, h, label: sl.label + (sl.used > sl.hp ? ` · ${sl.used} HP placed: over by ${sl.used - sl.hp}` : '') });
    y += h + GAP;
  }
  for (const n of mods) { const pl = placed.get(n.uid); n.px = 200 + pl.x * HPX; n.py = pl.slot.y; }
  // case jacks (NiftyCASE MIDI/CV) and the rack I/O sit outside the rows
  const cases = r.nodes.filter(n => devOf(n).category === 'eurorack-case');
  cases.forEach((n, i) => { n.px = 200 - 110 - i * 100; n.py = (all.find(sl => sl.caseId === n.device) || all[0]).y; });
  const right = Math.max(...rails.map(x => x.x + x.w), 800) + 40;
  r.nodes.filter(n => n.device === 'eurorack-in').forEach(n => { n.px = 200 - 110 - cases.length * 100; n.py = 40; });
  r.nodes.filter(n => n.device === 'eurorack-out').forEach(n => { n.px = right; n.py = 40; });
  r.rails = rails;
}
function snapPanel(n, x, y) {
  const nx = Math.round(x / HPX) * HPX;
  const rail = (G().rails || []).find(r => Math.abs(r.y - y) < 90 && (devOf(n).format === '1U') === (r.h === U1));
  return [nx, rail ? rail.y : Math.round(y / 10) * 10];
}
async function savePanelPositions(device) {
  const pos = S.byId[device].jack_pos || {};
  try { await api('PUT', `/api/panels/${device}`, { positions: pos }); toast('Jack positions saved (panels.yaml)'); }
  catch (e) { toast('Could not save jack positions: ' + e.message, 5000); }
}
function placingBanner() {
  const b = $('#placing'); const pl = S.placing;
  if (!pl) { b.hidden = true; return; }
  const name = pl.queue[pl.i];
  b.hidden = false;
  b.innerHTML = `Click the panel where <b>${esc(name)}</b> is (${pl.i + 1} of ${pl.queue.length}) · <button data-act="place-skip">Skip</button> <button data-act="place-done" class="primary">Done</button>`;
}
function stopPlacing(save = true) {
  const pl = S.placing; S.placing = null; placingBanner(); renderNodes(); renderCables();
  if (pl && save && pl.changed) savePanelPositions(pl.device);
}

/* ---------- Eurorack: the patch inside the rack ---------- */
function enterRack(nid) {
  const n = S.session.nodes.find(m => m.uid === nid); if (!n) return;
  n.rack ||= { ...clone(S.gear.rack_seed), notes: '' };
  for (const [dev, x] of [['eurorack-in', 40], ['eurorack-out', 1400]]) {  // older sessions: make sure the I/O exists
    if (!n.rack.nodes.some(m => m.device === dev)) n.rack.nodes.push({ uid: uid('r'), device: dev, x, y: 40, settings: {} });
  }
  S.sessionView = { ...S.view }; S.scope = nid; S.sel = null; S.portEdit = null;
  if (panelMode() && n.rack.nodes.some(m => m.px == null)) arrangePanels();
  S.view = n.rack.view ? { ...n.rack.view } : { x: 40, y: 40, k: 1 };
  renderAll();
  if (!n.rack.view) fit();
}
function exitRack() {
  const n = scopeNode(); if (n) n.rack.view = { ...S.view };
  S.scope = null; S.sel = null; S.portEdit = null;
  S.view = S.sessionView ? { ...S.sessionView } : { x: 40, y: 40, k: 1 };
  renderAll();
}
/* Lay modules out like the cases: one band per case row (gear-kb placements), left->right by position then name.
   Rack inputs on the far left, Rack outputs on the far right. Unplaced modules go in a last band. */
function arrangeRack() {
  const r = G(); const bands = new Map(); const COLW = 250, PER = 7;
  const mods = r.nodes.filter(n => !IO_DEVICES.includes(n.device));
  const key = n => { const p = devOf(n).placement; return p ? `${S.byId[p.case]?.name || p.case}|${p.row_index ? 'row ' + p.row_index : p.row || ''}` : '~unplaced|'; };
  mods.forEach(n => { const k = key(n); if (!bands.has(k)) bands.set(k, []); bands.get(k).push(n); });
  let y = 60, maxX = 0; const labels = [];
  for (const k of [...bands.keys()].sort()) {
    const [caseName, row] = k.split('|');
    labels.push({ text: caseName === '~unplaced' ? 'Not placed in a case (gear-kb)' : `${caseName}${row ? ' · ' + (row.startsWith('row') ? row : row + ' row') : ''}`, y: y - 14 });
    const list = bands.get(k).sort((a, b) => (devOf(a).placement?.position ?? 999) - (devOf(b).placement?.position ?? 999) || devOf(a).name.localeCompare(devOf(b).name));
    let rowH = 0;
    list.forEach((n, i) => {
      if (i && i % PER === 0) { y += rowH + 40; rowH = 0; }
      n.x = 320 + (i % PER) * COLW; n.y = y; rowH = Math.max(rowH, nodeGeom(n).h); maxX = Math.max(maxX, n.x);
    });
    y += rowH + 70;
  }
  r.nodes.filter(n => n.device === 'eurorack-in').forEach(n => { n.x = 40; n.y = 40; });
  r.nodes.filter(n => n.device === 'eurorack-out').forEach(n => { n.x = maxX + COLW + 60; n.y = 40; });
  r.bands = labels;  // drawn behind the modules; re-run Arrange by case after moving modules or updating placements
}
function rackAddAll() {
  checkpoint();
  const have = new Set(G().nodes.map(n => n.device));
  let added = 0, patched = 0;
  for (const d of S.gear.devices.filter(d => d.placement?.case && !have.has(d.id))) {
    const n = { uid: uid('n'), device: d.id, x: 0, y: 0, collapsed: true, settings: {} };
    G().nodes.push(n); added++; patched += autoPatch(n);
  }
  arrangeRack(); arrangePanels(); changed(); fit();
  toast(`Added ${added} module${added === 1 ? '' : 's'}${patched ? `, ${patched} cable${patched === 1 ? '' : 's'} from gear-kb` : ''}`);
}

/* ---------- device start state (data/device_fields.yaml, Elektron boxes) ---------- */
function stateSummary(n, dev) {
  const st = n.settings?.state; if (!dev.fields || !st) return '';
  return dev.fields.summary.filter(p => p.keys.every(k => st[k])).map(p => p.fmt.replace(/\{(\w+)\}/g, (_, k) => st[k])).join(' · ');
}
function homeChannelOptions() {
  const by = {};
  S.gear.devices.forEach(d => { if (d.midi?.in && /^\d+$/.test(String(d.midi.in))) (by[d.midi.in] ||= []).push(d.name.replace(/^(Behringer|Elektron|Korg|Akai|Donner|Dreadbox|Roland|Sonicware) /, '')); });
  return ['', ...Array.from({ length: 16 }, (_, i) => String(i + 1))].map(c => [c, c ? `${c}${by[c] ? ' · ' + by[c].join(', ') : ''}` : '—']);
}
function stateField(f, st, base) {
  const v = st[f.key] ?? '', bind = `${base}.${f.key}`;
  if (f.type === 'tracks') {
    const muted = new Set(st[f.key] || []);
    return `<div class="field"><span>${esc(f.label || 'Mutes')}</span><div class="mutes">${f.tracks.map(t =>
      `<label class="${muted.has(t) ? 'muted-trk' : ''}" title="${muted.has(t) ? 'muted' : 'playing'}"><input type="checkbox" data-mute="${esc(f.key)}|${esc(t)}" ${muted.has(t) ? 'checked' : ''}>${esc(t)}</label>`).join('')}</div></div>`;
  }
  if (f.type === 'table') {
    const val = st[f.key] || {};
    const cell = (r, c) => {
      const cv = val[r]?.[c.key] ?? '', b = `${bind}.${r}.${c.key}`;
      if (c.options === 'home_channels') return `<select data-bind="${b}">${homeChannelOptions().map(([o, l]) => `<option value="${o}" ${o === String(cv) ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
      if (Array.isArray(c.options)) return `<select data-bind="${b}">${c.options.map(o => `<option value="${esc(o)}" ${o === cv ? 'selected' : ''}>${esc(o || '—')}</option>`).join('')}</select>`;
      return `<input data-bind="${b}" value="${esc(cv)}" placeholder="${esc(c.ph || '')}">`;
    };
    return `<table class="state-tbl"><thead><tr><th></th>${f.cols.map(c => `<th>${esc(c.label)}</th>`).join('')}</tr></thead><tbody>${f.rows.map(r =>
      `<tr><th>${esc(r)}</th>${f.cols.map(c => `<td>${cell(r, c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  }
  const hint = f.kb ? `studio: ${f.kb}` : (f.ph || '');
  const input = f.type === 'select'
    ? `<select data-bind="${bind}"><option value="">${esc(f.kb ? `— (studio: ${f.kb})` : '—')}</option>${f.options.map(o => `<option ${String(o) === String(v) ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>`
    : `<input data-bind="${bind}" value="${esc(v)}" placeholder="${esc(hint)}">`;
  return `<label class="field ${f.kb && v && String(v) !== String(f.kb) ? 'differs' : ''}"><span>${esc(f.label)}${f.help ? ` <i title="${esc(f.help)}">ⓘ</i>` : ''}</span>${input}</label>`;
}
function stateInspector(n, dev) {
  const F = dev.fields, st = n.settings?.state || {};
  const secs = F.sections.map(sec => {
    const id = `${dev.id}:${sec.name}`;
    const open = S.openSec[id] ?? !/global/i.test(sec.name);
    const simple = sec.fields.filter(f => !f.type || f.type === 'text' || f.type === 'select');
    const body = simple.length === sec.fields.length
      ? `<div class="grid2">${sec.fields.map(f => stateField(f, st, 'node.settings.state')).join('')}</div>`
      : sec.fields.map(f => stateField(f, st, 'node.settings.state')).join('');
    return `<details class="state-sec" data-sec="${esc(id)}" ${open ? 'open' : ''}><summary>${esc(sec.name)}</summary>${sec.help ? `<p class="muted">${esc(sec.help)}</p>` : ''}${body}</details>`;
  }).join('');
  const hasKb = F.sections.some(s => s.fields.some(f => f.kb));
  return `<h4>${esc(F.title)}</h4>${secs}
    <div class="btns">${hasKb ? '<button data-act="state-kb" title="Fill empty fields that have a studio default recorded in gear-kb">Fill studio defaults</button>' : ''}<button data-act="state-clear" class="danger">Clear start state</button></div>
    <p class="muted">Fields from ${esc(F.source)}.</p>`;
}

/* ---------- checks ---------- */
function warnings() {
  const out = [], s = G();
  const nm = n => n.label || devOf(n).name;
  const inputUse = {};
  for (const c of s.cables) {
    const a = nodeById(c.from.uid), b = nodeById(c.to.uid);
    if (!a || !b) continue;
    const pa = devOf(a).ports.find(p => p.name === c.from.port), pb = devOf(b).ports.find(p => p.name === c.to.port);
    for (const [n, port, p] of [[a, c.from.port, pa], [b, c.to.port, pb]]) {
      if (!p) out.push({ kind: 'cable', id: c.uid, text: `${nm(n)}: “${port}” is not a jack of this device (renamed or hidden?)` });
      else if (p.hidden) out.push({ kind: 'cable', id: c.uid, text: `${nm(n)}: “${port}” is hidden` });
    }
    for (const p of [pa, pb]) if (p && !compatible(p.medium, c.medium)) out.push({ kind: 'cable', id: c.uid, text: `${MEDIA_LABEL[c.medium]} cable on a ${MEDIA_LABEL[p.medium]} jack (${p.name}): needs a converter?` });
    if (pb && pb.dir === 'in') {
      const k = c.to.uid + '|' + c.to.port;
      (inputUse[k] ||= []).push(c);
    }
  }
  for (const [k, cs] of Object.entries(inputUse)) if (cs.length > 1) {
    const [nid, port] = k.split('|');
    out.push({ kind: 'cable', id: cs[1].uid, text: `${cs.length} cables into one input: ${nm(nodeById(nid))} · ${port} (needs a mult/merge)` });
  }
  // MIDI: devices reachable over MIDI cables from the same chain must not share a receive channel
  const midi = s.cables.filter(c => c.medium === 'midi');
  const parent = {};
  const find = x => (parent[x] ??= x) === x ? x : (parent[x] = find(parent[x]));
  midi.forEach(c => { parent[find(c.from.uid)] = find(c.to.uid); });
  const recv = {};
  for (const c of midi) {
    const n = nodeById(c.to.uid); if (!n) continue;
    const ch = String(n.settings?.midi_in || devOf(n).midi?.in || '').trim().toLowerCase();
    if (!ch || ch === 'omni' || ch === 'off' || ch === 'all') continue;
    const key = find(n.uid) + '|' + ch;
    (recv[key] ||= new Set()).add(n.uid);
  }
  for (const [k, set] of Object.entries(recv)) if (set.size > 1) {
    const ns = [...set].map(nodeById);
    if (new Set(ns.map(n => n.device)).size > 1) out.push({ kind: 'node', id: ns[1].uid, text: `MIDI ch ${k.split('|')[1]} is received by ${ns.map(nm).join(' and ')} on one chain` });
  }
  return out;
}

/* ---------- mutations ---------- */
function addNode(deviceId, x, y) {
  checkpoint();
  // dropped gear starts with every jack visible (you are about to patch it); collapse with the ▴ toggle
  const n = { uid: uid('n'), device: deviceId, x: Math.round(x / 10) * 10, y: Math.round(y / 10) * 10, collapsed: false, settings: {} };
  if (S.byId[deviceId]?.rack) n.rack = { ...clone(S.gear.rack_seed), notes: '' };
  if (panelMode()) [n.px, n.py] = snapPanel(n, x + NODE_W / 2 - panelSize(n).w / 2, y + 30);
  G().nodes.push(n); S.sel = { kind: 'node', id: n.uid };
  const auto = autoPatchOn() ? autoPatch(n) : 0;
  changed();
  if (auto) toast(`Patched ${auto} cable${auto === 1 ? '' : 's'} from gear-kb (undo removes the device and its cables)`);
}
const autoPatchOn = () => $('#auto-patch')?.checked !== false;
/* Connect a just-added node to gear already on the canvas, using the cables gear-kb records between them.
   Skips a cable whose input jack is already taken, and never duplicates an existing cable. */
function autoPatch(n) {
  let added = 0;
  const taken = new Set(G().cables.map(c => c.to.uid + '|' + c.to.port));
  const jack = (node, name) => devOf(node).ports.find(p => p.name === name && !p.hidden);
  for (const l of (inRack() ? S.gear.rack_links : S.gear.kb_links) || []) {
    const outgoing = l.from === n.device, incoming = l.to === n.device;
    if (!outgoing && !incoming) continue;
    const other = G().nodes.find(m => m !== n && m.device === (outgoing ? l.to : l.from));
    if (!other) continue;
    const [a, b] = outgoing ? [n, other] : [other, n];
    if (!jack(a, l.from_port) || !jack(b, l.to_port)) continue;
    if (!l.bidirectional && taken.has(b.uid + '|' + l.to_port)) continue;
    if (G().cables.some(c => c.from.uid === a.uid && c.from.port === l.from_port && c.to.uid === b.uid && c.to.port === l.to_port)) continue;
    const settings = l.note ? { notes: l.note } : {};
    G().cables.push({ uid: uid('c'), from: { uid: a.uid, port: l.from_port }, to: { uid: b.uid, port: l.to_port }, medium: l.medium, settings });
    taken.add(b.uid + '|' + l.to_port); added++;
  }
  return added;
}
function addCable(a, b) {
  // a, b: {uid, port, p (port object)}. Orient output -> input.
  if (a.uid === b.uid) return toast('Patch between two different devices');
  let from = a, to = b;
  if (a.p.dir === 'in' && b.p.dir !== 'in') { from = b; to = a; }
  else if (a.p.dir === 'in' && b.p.dir === 'in') return toast('Both jacks are inputs');
  else if (a.p.dir === 'out' && b.p.dir === 'out') return toast('Both jacks are outputs');
  if (G().cables.some(c => c.from.uid === from.uid && c.from.port === from.port && c.to.uid === to.uid && c.to.port === to.port)) return toast('Already patched');
  checkpoint();
  const medium = from.p.medium === 'usb' || to.p.medium === 'usb' ? 'usb' : from.p.medium;
  const c = { uid: uid('c'), from: { uid: from.uid, port: from.port }, to: { uid: to.uid, port: to.port }, medium, settings: {} };
  G().cables.push(c); S.sel = { kind: 'cable', id: c.uid }; changed();
  if (!compatible(from.p.medium, to.p.medium)) toast(`${MEDIA_LABEL[from.p.medium]} → ${MEDIA_LABEL[to.p.medium]}: check you need a converter`);
}
function deleteSelection() {
  if (!S.sel) return;
  if (S.sel.kind === 'node' && IO_DEVICES.includes(nodeById(S.sel.id)?.device)) return toast('Rack inputs/outputs are part of the rack');
  checkpoint();
  if (S.sel.kind === 'node') {
    G().nodes = G().nodes.filter(n => n.uid !== S.sel.id);
    G().cables = G().cables.filter(c => c.from.uid !== S.sel.id && c.to.uid !== S.sel.id);
  } else G().cables = G().cables.filter(c => c.uid !== S.sel.id);
  S.sel = null; changed();
}
function duplicateNode() {
  const n = S.sel?.kind === 'node' && nodeById(S.sel.id); if (!n) return;
  checkpoint();
  const d = { ...clone(n), uid: uid('n'), x: n.x + 30, y: n.y + 30, ...(n.px != null ? { px: n.px + panelSize(n).w, py: n.py } : {}) };
  G().nodes.push(d); S.sel = { kind: 'node', id: d.uid }; changed();
}
function setPath(obj, path, value) {
  const keys = path.split('.'); let o = obj;
  keys.slice(0, -1).forEach(k => { o[k] ??= k === 'fields' ? [] : {}; o = o[k]; });
  const last = keys[keys.length - 1];
  if (value === '' && !Array.isArray(o)) delete o[last]; else o[last] = value;
}
function bindTarget(bind) {
  const [root, ...rest] = bind.split('.');
  const obj = root === 'session' ? S.session : root === 'rack' ? scopeNode()?.rack : root === 'node' ? nodeById(S.sel?.id) : cableById(S.sel?.id);
  return [obj, rest.join('.')];
}

/* ---------- canvas interaction ---------- */
const svg = () => $('#canvas');
function toWorld(cx, cy) {
  const r = svg().getBoundingClientRect();
  return { x: (cx - r.left - S.view.x) / S.view.k, y: (cy - r.top - S.view.y) / S.view.k };
}
let drag = null;
function onPointerDown(e) {
  if (e.button !== 0 && e.button !== 1) return;
  // in panel view cables hang over the jacks: a press on a jack still starts a new cable
  const portEl = e.target.closest('[data-port]') || (panelMode() && !S.placing
    ? document.elementsFromPoint(e.clientX, e.clientY).map(el => el.closest?.('[data-port]')).find(Boolean) : null);
  const toggleEl = e.target.closest('[data-toggle]');
  if (S.placing && e.button === 0) {  // Place jacks: this click marks where the current jack is on the panel
    const pl = S.placing, n = nodeById(pl.uid), w = toWorld(e.clientX, e.clientY), { w: pw, h: ph } = panelSize(n);
    const fx = (w.x - n.px) / pw, fy = (w.y - n.py) / ph;
    if (fx >= 0 && fx <= 1 && fy >= 0 && fy <= 1) {
      const dev = S.byId[n.device]; dev.jack_pos = { ...(dev.jack_pos || {}), [pl.queue[pl.i]]: [+fx.toFixed(4), +fy.toFixed(4)] };
      pl.changed = true; pl.i++;
      if (pl.i >= pl.queue.length) stopPlacing(); else { placingBanner(); renderNodes(); renderCables(); }
    } else toast('Click inside the highlighted module’s panel');
    return;
  }
  const nodeEl = e.target.closest('.node'), cableEl = e.target.closest('[data-cable]');
  svg().setPointerCapture(e.pointerId);
  if (toggleEl) {
    const n = nodeById(toggleEl.dataset.toggle); checkpoint();
    n.collapsed = !nodeGeom(n).collapsed; changed(); drag = null; return;
  }
  if (portEl && e.button === 0) {
    const n = nodeById(portEl.dataset.node), port = portEl.dataset.port;
    const p = panelMode() ? jackSpots(n)[port]?.p : nodeGeom(n).pos[port]?.p;
    drag = { kind: 'cable', from: { uid: n.uid, port, p }, anchor: panelMode() ? panelAnchor(n.uid, port) : portAnchor(n.uid, port) };
    svg().classList.add('patching');
    return;
  }
  if (nodeEl && e.button === 0) {
    const n = nodeById(nodeEl.dataset.node);
    if (S.sel?.kind !== 'node' || S.sel.id !== n.uid) { S.sel = { kind: 'node', id: n.uid }; S.portEdit = null; renderNodes(); renderCables(); renderInspector(); }
    const w = toWorld(e.clientX, e.clientY), pm = panelMode();
    drag = { kind: 'node', n, pm, dx: w.x - (pm ? n.px : n.x), dy: w.y - (pm ? n.py : n.y), before: JSON.stringify(S.session), moved: false };
    return;
  }
  if (cableEl && e.button === 0) {
    S.sel = { kind: 'cable', id: cableEl.dataset.cable }; S.portEdit = null; renderCables(); renderNodes(); renderInspector(); drag = null; return;
  }
  drag = { kind: 'pan', sx: e.clientX, sy: e.clientY, vx: S.view.x, vy: S.view.y, moved: false };
  svg().classList.add('panning');
}
function onPointerMove(e) {
  if (!drag) return;
  if (drag.kind === 'pan') {
    S.view.x = drag.vx + e.clientX - drag.sx; S.view.y = drag.vy + e.clientY - drag.sy;
    drag.moved ||= Math.abs(e.clientX - drag.sx) + Math.abs(e.clientY - drag.sy) > 3;
    applyView();
  } else if (drag.kind === 'node') {
    const w = toWorld(e.clientX, e.clientY);
    const [nx, ny] = drag.pm ? snapPanel(drag.n, w.x - drag.dx, w.y - drag.dy)
      : [Math.round((w.x - drag.dx) / 10) * 10, Math.round((w.y - drag.dy) / 10) * 10];
    const [cx, cy] = drag.pm ? [drag.n.px, drag.n.py] : [drag.n.x, drag.n.y];
    if (nx !== cx || ny !== cy) {
      if (drag.pm) { drag.n.px = nx; drag.n.py = ny; } else { drag.n.x = nx; drag.n.y = ny; }
      drag.moved = true;
      document.querySelector(`.node[data-node="${CSS.escape(drag.n.uid)}"]`)?.setAttribute('transform', `translate(${nx},${ny})`);
      renderCables();
    }
  } else if (drag.kind === 'cable') {
    const w = toWorld(e.clientX, e.clientY);
    const target = { x: w.x, y: w.y, side: drag.anchor.side === 'L' ? 'R' : 'L' };
    const [a, b] = drag.from.p?.dir === 'in' ? [target, drag.anchor] : [drag.anchor, target];
    const d = $('#drag-cable'); d.setAttribute('d', panelMode() ? sagPath(a, b) : cablePath(a, b)); d.setAttribute('class', `cable-line drag m-${drag.from.p?.medium || 'audio'}`);
    document.querySelectorAll('.port.hover').forEach(el => el.classList.remove('hover'));
    document.elementFromPoint(e.clientX, e.clientY)?.closest('[data-port]')?.classList.add('hover');
  }
}
function onPointerUp(e) {
  if (!drag) return;
  const d = drag; drag = null;
  svg().classList.remove('panning', 'patching');
  if (d.kind === 'node' && d.moved) { S.undo.push(d.before); S.redo = []; setDirty(true); renderChrome(); }
  if (d.kind === 'pan' && !d.moved && S.sel) { S.sel = null; S.portEdit = null; renderNodes(); renderCables(); renderInspector(); }
  if (d.kind === 'cable') {
    $('#drag-cable').setAttribute('d', '');
    const el = document.elementsFromPoint(e.clientX, e.clientY).map(x => x.closest?.('[data-port]')).find(x => x && x.id !== 'drag-cable');
    if (el) {
      const n = nodeById(el.dataset.node), port = el.dataset.port;
      const p = panelMode() ? jackSpots(n)[port]?.p : nodeGeom(n).pos[port]?.p;
      if (p && d.from.p) addCable(d.from, { uid: n.uid, port, p });
    }
  }
}
function onWheel(e) {
  e.preventDefault();
  const r = svg().getBoundingClientRect();
  const k = Math.min(2.5, Math.max(0.2, S.view.k * Math.exp(-e.deltaY * 0.0015)));
  const px = e.clientX - r.left, py = e.clientY - r.top;
  S.view.x = px - (px - S.view.x) * (k / S.view.k); S.view.y = py - (py - S.view.y) * (k / S.view.k); S.view.k = k;
  applyView();
}
function bounds() {
  const ns = G().nodes; if (!ns.length) return null;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  if (panelMode()) {
    ns.forEach(n => { const { w, h } = panelSize(n); x0 = Math.min(x0, n.px); y0 = Math.min(y0, n.py - 30); x1 = Math.max(x1, n.px + w); y1 = Math.max(y1, n.py + h + 40); });
    (G().rails || []).forEach(r => { x0 = Math.min(x0, r.x); y0 = Math.min(y0, r.y - 30); x1 = Math.max(x1, r.x + r.w); y1 = Math.max(y1, r.y + r.h + 10); });
    return { x0, y0, x1, y1 };
  }
  ns.forEach(n => { const h = nodeGeom(n).h; x0 = Math.min(x0, n.x); y0 = Math.min(y0, n.y); x1 = Math.max(x1, n.x + NODE_W); y1 = Math.max(y1, n.y + h); });
  return { x0, y0, x1, y1 };
}
function fit() {
  const b = bounds(); if (!b) return;
  const r = svg().getBoundingClientRect(), m = 40, top = inRack() ? 70 : m;  // room for the rack breadcrumb
  const k = Math.min(1.2, Math.max(0.2, Math.min((r.width - 2 * m) / (b.x1 - b.x0), (r.height - 2 * m) / (b.y1 - b.y0))));
  S.view = { k, x: m + ((r.width - 2 * m) - (b.x1 - b.x0) * k) / 2 - b.x0 * k, y: top - b.y0 * k };
  applyView();
}

/* ---------- save / open ---------- */
function toast(msg, ms = 2600) {
  const t = $('#toast'); t.textContent = msg; t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => { t.hidden = true; }, ms);
}
function modal(html) {
  const d = $('#modal'); $('#modal-body').innerHTML = html; d.showModal(); return d;
}
function ask(title, label, value) {
  return new Promise(res => {
    const d = modal(`<h3>${esc(title)}</h3><form method="dialog"><label class="field"><span>${esc(label)}</span><input id="ask-in" value="${esc(value)}" required></label>
      <div class="btns"><button value="ok" class="primary">OK</button><button value="cancel" formnovalidate>Cancel</button></div></form>`);
    const inp = $('#ask-in'); inp.select();
    d.addEventListener('close', () => res(d.returnValue === 'ok' ? inp.value.trim() : null), { once: true });
  });
}
function confirmBox(title, text, okLabel = 'OK') {
  return new Promise(res => {
    const d = modal(`<h3>${esc(title)}</h3><p>${esc(text)}</p><form method="dialog"><div class="btns"><button value="ok" class="primary">${esc(okLabel)}</button><button value="cancel">Cancel</button></div></form>`);
    d.addEventListener('close', () => res(d.returnValue === 'ok'), { once: true });
  });
}
async function save(asNew) {
  let slug = S.slug;
  if (asNew || !slug) {
    const name = await ask(asNew ? 'Save a copy' : 'Save session', 'Name', asNew ? `${S.session.name} copy` : S.session.name);
    if (!name) return;
    slug = slugify(name);
    if (!slug) return toast('Name needs letters or digits');
    const list = await api('GET', '/api/sessions');
    if (list.some(x => x.slug === slug) && slug !== S.slug && !(await confirmBox('Overwrite?', `“${slug}” already exists. Replace it?`, 'Replace'))) return;
    S.session.name = name;
    if (asNew) delete S.session.created;
  }
  if (inRack()) scopeNode().rack.view = { ...S.view };
  const body = { ...S.session, view: { ...(inRack() ? S.sessionView : S.view) }, gear_kb_commit: S.gear.kb_commit };
  try {
    const r = await api('PUT', `/api/sessions/${slug}`, body);
    S.slug = slug; S.session.updated = r.updated; if (!S.session.created) S.session.created = r.updated;
    setDirty(false); clearDraft(); renderAll(); toast(STATIC ? `Saved “${slug}” in this browser` : `Saved sessions/${slug}.yaml`);
  } catch (e) { toast('Save failed: ' + e.message, 5000); }
}
async function openDialog() {
  const list = await api('GET', '/api/sessions');
  const d = modal(`<h3>Open</h3>${list.length ? `<div class="sess-list">${list.map(s => `<div class="sess-row" data-open="${esc(s.slug)}">
      <div><b>${esc(s.name)}</b> <span class="badge ${esc(s.type)}">${esc(s.type)}</span><small>${[s.bpm && s.bpm + ' BPM', s.key, `${s.devices} devices`, `${s.cables} cables`, s.updated && 'saved ' + String(s.updated).replace('T', ' ')].filter(Boolean).map(esc).join(' · ')}</small></div>
      <button data-del="${esc(s.slug)}" class="danger" title="Delete (moves to sessions/.trash)">Delete</button></div>`).join('')}</div>` : '<p class="muted">No saved sessions yet.</p>'}
    <form method="dialog"><div class="btns"><button>Close</button></div></form>`);
  d.onclick = async e => {
    const del = e.target.closest('[data-del]'), row = e.target.closest('[data-open]');
    if (del) {
      e.stopPropagation(); d.close();
      if (await confirmBox('Delete session?', `Move “${del.dataset.del}” to sessions/.trash/?`, 'Delete')) {
        await api('DELETE', `/api/sessions/${del.dataset.del}`);
        if (S.slug === del.dataset.del) { S.slug = null; setDirty(true); }
        toast(STATIC ? 'Deleted from this browser' : 'Moved to sessions/.trash/');
      }
      return openDialog();
    }
    if (row) {
      if (S.dirty && !(await confirmBox('Discard changes?', 'The current session has unsaved changes.', 'Discard'))) return;
      d.close();
      const sess = await api('GET', `/api/sessions/${row.dataset.open}`);
      setSession(sess, row.dataset.open); clearDraft();
    }
  };
}
async function newDialog() {
  if (S.dirty && !(await confirmBox('Discard changes?', 'The current session has unsaved changes.', 'Discard'))) return;
  const d = modal(`<h3>New</h3><div class="choice">
    <button data-new="blank">Blank canvas<small>Start empty and drag gear in.</small></button>
    ${templateButtons('data-new')}
    </div><form method="dialog"><div class="btns"><button>Cancel</button></div></form>`);
  d.onclick = e => {
    const b = e.target.closest('[data-new]'); if (!b) return;
    d.close(); setSession(b.dataset.new === 'blank' ? blankSession() : templateSession(b.dataset.new), null); clearDraft();
  };
}

/* ---------- export ---------- */
async function exportSVG() {
  const b = bounds(); if (!b) return toast('Nothing to export');
  const m = 30, headH = 54, w = b.x1 - b.x0 + 2 * m, h = b.y1 - b.y0 + 2 * m + headH;
  const cs = getComputedStyle(document.documentElement);
  const vars = ['--bg', '--panel', '--ink', '--muted', '--line', '--node', '--node-line', '--tile', '--accent', '--sel', ...MEDIA.map(x => '--' + x)]
    .map(v => `${v}:${cs.getPropertyValue(v).trim()}`).join(';');
  const icons = {};
  const toDataURL = async src => {
    const blob = await (await fetch(src)).blob();
    return new Promise(res => { const r = new FileReader(); r.onload = () => res(r.result); r.readAsDataURL(blob); });
  };
  for (const n of G().nodes) {
    for (const src of [devOf(n).icon, devOf(n).panel].filter(Boolean)) if (!icons[src]) icons[src] = await toDataURL(src);
  }
  const world = $('#world').cloneNode(true);
  world.removeAttribute('transform'); world.querySelector('#drag-cable')?.remove();
  world.querySelectorAll('.sel').forEach(el => el.classList.remove('sel'));
  world.querySelectorAll('image').forEach(im => im.setAttribute('href', icons[im.getAttribute('href')] || im.getAttribute('href')));
  const s = S.session;
  const meta = [inRack() ? `${scopeNode().label || 'Eurorack'} patch` : '', s.type === 'song' ? 'Song' : 'Session', s.bpm && `${s.bpm} BPM`, s.key, s.date].filter(Boolean).join(' · ');
  const css = [...document.styleSheets].flatMap(sh => { try { return [...sh.cssRules]; } catch (e) { return []; } })
    .map(r => r.cssText).filter(t => /^(\.node|\.port|\.jack|\.cable|\.m-|\.icon-tile|\.more|\.panel|\.vjack|\.plug|\.rail|\.band|\.vcv|\.fp-)/.test(t)).join('\n');
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" style="${vars}">
${Faceplate.DEFS}<style>svg{font-family:system-ui,-apple-system,'Segoe UI',sans-serif} ${css}</style>
<rect width="100%" height="100%" fill="var(--bg)"/>
<text x="${m}" y="${m + 6}" font-size="20" font-weight="700" fill="var(--ink)">${esc(s.name)}</text>
<text x="${m}" y="${m + 28}" font-size="13" fill="var(--muted)">${esc(meta)}</text>
<g transform="translate(${m - b.x0},${m + headH - b.y0})">${world.innerHTML}</g></svg>`;
}
function download(name, blob) {
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
async function exportFile(kind) {
  const text = await exportSVG(); if (!text) return;
  const base = S.slug || slugify(S.session.name) || 'session';
  if (kind === 'svg') return download(base + '.svg', new Blob([text], { type: 'image/svg+xml' }));
  const img = new Image();
  img.onload = () => {
    const c = document.createElement('canvas'); c.width = img.width * 2; c.height = img.height * 2;
    const ctx = c.getContext('2d'); ctx.scale(2, 2); ctx.drawImage(img, 0, 0);
    c.toBlob(bl => download(base + '.png', bl), 'image/png');
  };
  img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(text)));
}

/* ---------- port editing ---------- */
async function savePorts() {
  const pe = S.portEdit, dev = S.byId[pe.device];
  const seed = Object.fromEntries(dev.ports.map(p => [p.name, p]));
  const out = [], renames = {};
  for (const r of pe.rows) {
    const name = r.name.trim(); if (!name) continue;
    const orig = r.orig && seed[r.orig];
    if (orig && r.orig !== name) { out.push({ name: r.orig, dir: orig.dir, medium: orig.medium, hidden: true }); renames[r.orig] = name; }
    const same = orig && r.orig === name && orig.dir === r.dir && orig.medium === r.medium && !!orig.hidden === !!r.hidden;
    if (!same || orig.source === 'you') out.push({ name, dir: r.dir, medium: r.medium, hidden: !!r.hidden });
  }
  try {
    await api('PUT', `/api/ports/${pe.device}`, { ports: out });
    await loadGear();
    if (Object.keys(renames).length) {
      checkpoint();
      const mine = new Set(G().nodes.filter(n => n.device === pe.device).map(n => n.uid));
      G().cables.forEach(c => ['from', 'to'].forEach(end => { if (mine.has(c[end].uid) && renames[c[end].port]) c[end].port = renames[c[end].port]; }));
      setDirty(true);
    }
    S.portEdit = null; renderAll(); toast('Jacks saved to ports.yaml');
  } catch (e) { toast('Could not save jacks: ' + e.message, 5000); }
}

/* ---------- wiring ---------- */
function onAction(act, el) {
  const n = S.sel?.kind === 'node' ? nodeById(S.sel.id) : null;
  switch (act) {
    case 'new': return newDialog();
    case 'open': return openDialog();
    case 'save': return save(false);
    case 'saveas': return save(true);
    case 'undo': return undo();
    case 'redo': return redo();
    case 'fit': return fit();
    case 'export-svg': return exportFile('svg');
    case 'export-png': return exportFile('png');
    case 'theme': {
      const cur = document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      const next = cur === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = next;
      try { localStorage.setItem('gpb:theme', next); } catch (e) { /* ignore */ }
      return;
    }
    case 'enter-rack': return enterRack(n.uid);
    case 'exit-rack': return exitRack();
    case 'rack-add-all': return rackAddAll();
    case 'rack-arrange': checkpoint(); panelMode() ? arrangePanels() : arrangeRack(); changed(); return fit();
    case 'view-mode': {
      S.viewMode = panelMode() ? 'nodes' : 'panel';
      try { localStorage.setItem('gpb:viewmode', S.viewMode); } catch (x) { /* ignore */ }
      S.sel = null; renderAll(); return fit();
    }
    case 'photos': {
      S.photos = !S.photos;
      try { localStorage.setItem('gpb:photos', S.photos ? '1' : '0'); } catch (x) { /* ignore */ }
      renderAll(); return toast(S.photos ? 'Illustrated icons on' : 'Generated faceplates');
    }
    case 'jack-labels': S.jackLabels = S.jackLabels === false; return renderAll();
    case 'place-jacks': {
      const d = devOf(n), cal = d.jack_pos || {};
      const names = d.ports.filter(p => !p.hidden).map(p => p.name);
      const queue = el.dataset.all ? names : names.filter(x => !cal[x]);
      if (!queue.length) return toast('Every jack is placed. Use “Re-place all” to redo.');
      S.placing = { uid: n.uid, device: n.device, queue, i: 0, changed: false }; placingBanner(); return renderNodes();
    }
    case 'place-skip': S.placing.i++; if (S.placing.i >= S.placing.queue.length) return stopPlacing(); placingBanner(); return renderNodes();
    case 'place-done': return stopPlacing();
    case 'place-reset': {
      const d = S.byId[n.device]; d.jack_pos = {}; renderAll(); return savePanelPositions(n.device);
    }
    case 'load-template': setSession(templateSession(el.dataset.template), null); setDirty(true); return;
    case 'delete': return deleteSelection();
    case 'dup': return duplicateNode();
    case 'reverse': {
      const c = cableById(S.sel.id); checkpoint(); [c.from, c.to] = [c.to, c.from]; return changed();
    }
    case 'state-kb': {
      checkpoint(); const st = (n.settings.state ||= {}); let k = 0;
      devOf(n).fields.sections.forEach(sec => sec.fields.forEach(f => { if (f.kb && !st[f.key]) { st[f.key] = f.kb; k++; } }));
      toast(k ? `Filled ${k} studio default${k === 1 ? '' : 's'} from gear-kb` : 'Nothing to fill'); return changed();
    }
    case 'state-clear': checkpoint(); delete n.settings.state; return changed();
    case 'field-add': checkpoint(); (n.settings.fields ||= []).push({ name: '', value: '' }); return changed();
    case 'field-del': checkpoint(); n.settings.fields.splice(+el.dataset.i, 1); return changed();
    case 'collapse': checkpoint(); n.collapsed = !el.checked; return changed();
    case 'ports-edit': S.portEdit = { device: n.device, rows: devOf(n).ports.map(p => ({ ...p, orig: p.name })) }; return renderInspector();
    case 'port-add': S.portEdit.rows.push({ name: '', dir: 'in', medium: 'audio', source: 'you' }); renderInspector();
      return document.querySelector(`[data-pe="${S.portEdit.rows.length - 1}.name"]`)?.focus();
    case 'ports-cancel': S.portEdit = null; return renderInspector();
    case 'ports-save': return savePorts();
  }
}

let liveTimer;
function init() {
  try { const t = localStorage.getItem('gpb:theme'); if (t) document.documentElement.dataset.theme = t; } catch (e) { /* ignore */ }
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-act]'); if (b && b.type !== 'checkbox') onAction(b.dataset.act, b);
    const g = e.target.closest('[data-goto]');
    if (g) { const [kind, id] = g.dataset.goto.split(':'); S.sel = { kind, id }; renderAll(); }
  });
  const ins = $('#inspector');
  ins.addEventListener('focusin', e => { if (e.target.dataset.bind) checkpoint(); });
  const onEdit = e => {
    const t = e.target;
    if (t.dataset.act === 'collapse' && e.type === 'change') return onAction('collapse', t);
    if (t.dataset.mute && e.type === 'change') {
      const n = nodeById(S.sel.id); const [key, trk] = t.dataset.mute.split('|');
      checkpoint(); const st = (n.settings.state ||= {}); const set = new Set(st[key] || []);
      t.checked ? set.add(trk) : set.delete(trk);
      st[key] = [...set]; if (!set.size) delete st[key];
      return changed();
    }
    if (t.dataset.mute) return;
    if (t.dataset.pe) {
      const [i, k] = t.dataset.pe.split('.');
      S.portEdit.rows[+i][k] = t.type === 'checkbox' ? t.checked : t.value;
      if (t.type === 'checkbox') renderInspector();
      return;
    }
    if (!t.dataset.bind) return;
    const [obj, path] = bindTarget(t.dataset.bind); if (!obj) return;
    setPath(obj, path, t.value);
    setDirty(true);
    clearTimeout(liveTimer);
    liveTimer = setTimeout(() => {
      renderNodes(); renderCables(); renderChrome();
      if (t.tagName === 'SELECT' || e.type === 'change') renderInspector();
    }, 120);
  };
  ins.addEventListener('input', onEdit);
  ins.addEventListener('change', e => { if (e.target.tagName === 'SELECT' || e.target.type === 'checkbox') onEdit(e); });
  ins.addEventListener('toggle', e => { const d = e.target.closest?.('[data-sec]'); if (d) S.openSec[d.dataset.sec] = d.open; }, true);
  $('#auto-patch').addEventListener('change', e => { try { localStorage.setItem('gpb:autopatch', e.target.checked ? '1' : '0'); } catch (x) { /* ignore */ } });
  try { if (localStorage.getItem('gpb:autopatch') === '0') $('#auto-patch').checked = false; } catch (x) { /* ignore */ }
  try { S.viewMode = localStorage.getItem('gpb:viewmode') || 'panel'; S.photos = localStorage.getItem('gpb:photos') === '1'; }
  catch (x) { S.viewMode = 'panel'; S.photos = false; }

  const c = svg();
  c.addEventListener('pointerdown', onPointerDown);
  c.addEventListener('pointermove', onPointerMove);
  c.addEventListener('pointerup', onPointerUp);
  c.addEventListener('pointercancel', onPointerUp);
  c.addEventListener('wheel', onWheel, { passive: false });
  c.addEventListener('dblclick', e => {
    // the first click re-rendered the node, so e.target may be detached: look up what is under the pointer now
    const r = document.elementFromPoint(e.clientX, e.clientY)?.closest('.node'); const rn = r && nodeById(r.dataset.node);
    if (rn && S.byId[rn.device]?.rack && !inRack()) return enterRack(rn.uid);
    if (r) { S.sel = { kind: 'node', id: r.dataset.node }; renderAll(); ins.querySelector('input')?.focus(); }
  });

  const list = $('#palette-list');
  list.addEventListener('dragstart', e => {
    const it = e.target.closest('[data-device]'); if (!it) return;
    e.dataTransfer.setData('text/x-gear', it.dataset.device); e.dataTransfer.effectAllowed = 'copy';
  });
  list.addEventListener('dblclick', e => {
    const it = e.target.closest('[data-device]'); if (!it) return;
    const r = c.getBoundingClientRect(); const w = toWorld(r.left + r.width / 2, r.top + r.height / 3);
    addNode(it.dataset.device, w.x - NODE_W / 2 + (Math.random() * 60 - 30), w.y);
  });
  const stage = $('#stage');
  stage.addEventListener('dragover', e => { if (e.dataTransfer.types.includes('text/x-gear')) { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; } });
  stage.addEventListener('drop', e => {
    const id = e.dataTransfer.getData('text/x-gear'); if (!id) return;
    e.preventDefault(); const w = toWorld(e.clientX, e.clientY); addNode(id, w.x - NODE_W / 2, w.y - 30);
  });
  $('#search').addEventListener('input', renderPalette);
  $('#in-use').addEventListener('change', renderPalette);

  document.addEventListener('keydown', e => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName);
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key.toLowerCase() === 's') { e.preventDefault(); return save(false); }
    if (e.key === 'Escape' && !$('#modal').open) {
      document.activeElement?.blur();
      if (S.placing) return stopPlacing();
      if (!S.sel && inRack() && !typing) return exitRack();
      S.sel = null; S.portEdit = null; return renderAll();
    }
    if (typing) return;
    if (mod && e.key.toLowerCase() === 'z') { e.preventDefault(); return e.shiftKey ? redo() : undo(); }
    if (mod && e.key.toLowerCase() === 'y') { e.preventDefault(); return redo(); }
    if (mod && e.key.toLowerCase() === 'd') { e.preventDefault(); return duplicateNode(); }
    if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); return deleteSelection(); }
    if (e.key === 'Escape') { S.sel = null; S.portEdit = null; renderAll(); }
    if (e.key === 'f') fit();
  });
  window.addEventListener('beforeunload', e => { if (S.dirty) { e.preventDefault(); e.returnValue = ''; } });
  window.addEventListener('resize', applyView);
}

async function boot() {
  init();
  try { await loadGear(); } catch (e) {
    document.body.innerHTML = `<p style="padding:20px">Could not load gear data: ${esc(e.message)}. Is the server running (make serve)?</p>`; return;
  }
  renderLegend();
  if (STATIC) toast('Website version: sessions are saved in this browser only. Run the app locally (make serve) to save files and edit jacks.', 7000);
  let draft = null;
  try { draft = JSON.parse(localStorage.getItem('gpb:draft') || 'null'); } catch (e) { /* ignore */ }
  const want = new URLSearchParams(location.search).get('session');
  if (want) {
    try { setSession(await api('GET', `/api/sessions/${want}`), want); return; } catch (e) { toast(`No session “${want}”`); }
  }
  setSession(blankSession(), null);
  if (draft?.session && (draft.session.nodes?.length || draft.session.cables?.length)) {
    const when = new Date(draft.at).toLocaleString();
    if (await confirmBox('Restore unsaved work?', `An unsaved draft of “${draft.session.name}” from ${when} was found in this browser.`, 'Restore')) {
      setSession(draft.session, draft.slug); setDirty(true);
    } else clearDraft();
  }
}
boot();
