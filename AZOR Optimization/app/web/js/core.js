/* AZOR — núcleo da interface: API, jobs, componentes e roteador. */
'use strict';
const AZ = window.AZ = {pages: {}, state: {}, current: null};

/* ---------- utilidades ---------- */
AZ.$ = (sel, root = document) => root.querySelector(sel);
AZ.$$ = (sel, root = document) => [...root.querySelectorAll(sel)];
AZ.esc = v => String(v ?? '').replace(/[&<>'"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'}[c]));
AZ.clamp = (v, a, b) => Math.min(b, Math.max(a, v));
AZ.mb = v => {
  const n = Number(v) || 0;
  return n >= 1024 ? `${(n / 1024).toFixed(1).replace('.', ',')} GB` : `${Math.round(n)} MB`;
};
AZ.bytes = v => AZ.mb((Number(v) || 0) / 1048576);
AZ.pct = v => v == null || Number.isNaN(Number(v)) ? '—' : `${Math.round(Number(v))}%`;
AZ.ago = t => {
  if (!t) return '';
  const s = Math.max(0, Date.now() / 1000 - Number(t));
  if (s < 90) return 'agora há pouco';
  if (s < 3600) return `há ${Math.round(s / 60)} min`;
  if (s < 86400) return `há ${Math.round(s / 3600)} h`;
  const d = Math.round(s / 86400);
  return d === 1 ? 'ontem' : `há ${d} dias`;
};
AZ.key = () => (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36)).replace(/[^A-Za-z0-9-]/g, '') + 'azorreq';

/* ---------- API ---------- */
const TOKEN = () => AZ.$('meta[name="azor-token"]')?.content || '';
AZ.get = async (url, timeout = 45000) => {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeout);
  try {
    const r = await fetch(url, {cache: 'no-store', signal: ctl.signal});
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || `Erro ${r.status}`);
    return data;
  } finally { clearTimeout(timer); }
};
AZ.post = async (url, body = {}, timeout = 120000) => {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeout);
  try {
    const r = await fetch(url, {method: 'POST', cache: 'no-store', signal: ctl.signal,
      headers: {'Content-Type': 'application/json', 'X-Azor-Token': TOKEN()}, body: JSON.stringify(body)});
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || data.detail || `Erro ${r.status}`);
    return data;
  } finally { clearTimeout(timer); }
};
AZ.action = (name, extra = {}) => AZ.post('/api/action', {name, ...extra});

/* ---------- ícones (traço 1.8, 24x24) ---------- */
const P = {
  home: 'M3 11.5 12 4l9 7.5M5.5 9.5V20h13V9.5M10 20v-5h4v5',
  plan: 'M9 5H6.5A1.5 1.5 0 0 0 5 6.5v13A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5v-13A1.5 1.5 0 0 0 17.5 5H15M9 5a3 3 0 0 1 6 0v1H9zM8.5 12.5l2 2 4.5-4.5M8.5 17.5h7',
  tweaks: 'M4 7h9M17 7h3M4 17h3M11 17h9M13 4.5v5M7 14.5v5',
  apps: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM17 14v6M14 17h6',
  cleanup: 'M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13M10 11v5.5M14 11v5.5',
  games: 'M7 9h10a4 4 0 0 1 4 4v1.5a2.5 2.5 0 0 1-4.6 1.4L15 14H9l-1.4 1.9A2.5 2.5 0 0 1 3 14.5V13a4 4 0 0 1 4-4ZM8 11.5v3M6.5 13h3M15.5 12h.01M17.5 14h.01',
  periph: 'M12 3a6 6 0 0 1 6 6v6a6 6 0 0 1-12 0V9a6 6 0 0 1 6-6ZM12 3v6M6 9.5h12',
  hardware: 'M7 7h10v10H7zM9.5 9.5h5v5h-5zM9 3v4M15 3v4M9 17v4M15 17v4M3 9h4M3 15h4M17 9h4M17 15h4',
  repair: 'M14.5 6.5a4 4 0 0 0-5.3 5.3L4 17l3 3 5.2-5.2a4 4 0 0 0 5.3-5.3l-2.6 2.6-2.4-.6-.6-2.4Z',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM19.4 13.5l1.3 1-1.8 3.1-1.6-.5a7 7 0 0 1-1.9 1.1L15 20.9h-3.6l-.4-1.7a7 7 0 0 1-1.9-1.1l-1.6.5-1.8-3.1 1.3-1a7 7 0 0 1 0-2.2l-1.3-1 1.8-3.1 1.6.5a7 7 0 0 1 1.9-1.1l.4-1.7H15l.4 1.7a7 7 0 0 1 1.9 1.1l1.6-.5 1.8 3.1-1.3 1a7 7 0 0 1 0 2.2Z',
  bolt: 'M13 3 5 13.5h6L10 21l8-10.5h-6Z',
  check: 'm5 12.5 4.5 4.5L19 7.5',
  x: 'M6 6l12 12M18 6 6 18',
  alert: 'M12 4 2.8 19.5h18.4ZM12 10v4.5M12 17.2h.01',
  info: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 11v5M12 7.8h.01',
  fps: 'M3 18 8.5 11l4 4L21 6M15 6h6v6',
  delay: 'M12 21a8 8 0 1 0 0-16 8 8 0 0 0 0 16ZM12 9v4l2.5 1.5M9.5 2.5h5',
  stutter: 'M3 12h3l2-5 3.5 10 2.5-7 1.5 2H21',
  ping: 'M2.5 9a14 14 0 0 1 19 0M5.5 12.2a9.5 9.5 0 0 1 13 0M8.8 15.3a5 5 0 0 1 6.4 0M12 18.6h.01',
  leve: 'M20 4C11 4 5 9 5 16c0 1.4.3 2.6.8 3.6M5.8 19.6C8 14 12 10 17 8M5.8 19.6 4 21',
  privacy: 'M12 3 4.5 6v5.5c0 4.6 3.2 8 7.5 9.5 4.3-1.5 7.5-4.9 7.5-9.5V6ZM9 12l2 2 4-4',
  visual: 'M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12ZM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
  lab: 'M9 3h6M10 3v6.5L4.8 18.2A1.8 1.8 0 0 0 6.3 21h11.4a1.8 1.8 0 0 0 1.5-2.8L14 9.5V3M7.5 15h9',
  cpu: 'M7 7h10v10H7zM10 10h4v4h-4zM9.5 3.5V7M14.5 3.5V7M9.5 17v3.5M14.5 17v3.5M3.5 9.5H7M3.5 14.5H7M17 9.5h3.5M17 14.5h3.5',
  gpu: 'M3 7h18v10H3zM7 12.5a2.5 2.5 0 1 0 5 0 2.5 2.5 0 0 0-5 0ZM15 10h3M15 13h3M6 17v3M10 17v3',
  ram: 'M3 8h18v8H3zM7 8v8M11 8v8M15 8v8M6 16v3M18 16v3',
  disk: 'M4 6.5C4 5 7.6 4 12 4s8 1 8 2.5v11c0 1.5-3.6 2.5-8 2.5s-8-1-8-2.5ZM4 6.5c0 1.5 3.6 2.5 8 2.5s8-1 8-2.5M4 12c0 1.5 3.6 2.5 8 2.5s8-1 8-2.5',
  temp: 'M10 14.8V5a2 2 0 1 1 4 0v9.8a4 4 0 1 1-4 0ZM12 9v7',
  trash: 'M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13',
  download: 'M12 4v11M7.5 10.5 12 15l4.5-4.5M5 19.5h14',
  refresh: 'M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5',
  undo: 'M9 14 4 9l5-5M4 9h10.5a5.5 5.5 0 0 1 0 11H11',
  link: 'M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1 1M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1-1',
  shield: 'M12 3 4.5 6v5.5c0 4.6 3.2 8 7.5 9.5 4.3-1.5 7.5-4.9 7.5-9.5V6Z',
  rocket: 'M5 15c-1.5 1.5-2 5-2 5s3.5-.5 5-2M14.5 9.5a1.5 1.5 0 1 0 0-.01M9 12 4.5 11 7 7.5h4.5M12 15l1 4.5 3.5-2.5v-4.5M9 12l3 3c5-2 8.5-6.5 8.5-11.5-5 0-9.5 3.5-11.5 8.5Z',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 7v5l3 2',
  star: 'm12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8L3.5 9.7l5.9-.9Z',
  power: 'M12 3v8M6.3 6.8a8 8 0 1 0 11.4 0',
  mouse: 'M12 3a6 6 0 0 1 6 6v6a6 6 0 0 1-12 0V9a6 6 0 0 1 6-6ZM12 3v6M6 9.5h12',
  keyboard: 'M3 7h18v10H3zM6.5 10.5h.01M9.5 10.5h.01M12.5 10.5h.01M15.5 10.5h.01M8 14h8',
  pad: 'M7 9h10a4 4 0 0 1 4 4v1.5a2.5 2.5 0 0 1-4.6 1.4L15 14H9l-1.4 1.9A2.5 2.5 0 0 1 3 14.5V13a4 4 0 0 1 4-4Z',
  monitor: 'M3 5h18v11H3zM8 20h8M12 16v4',
  flame: 'M12 21c-3.9 0-7-2.7-7-6.5 0-3 2-5.2 3.5-6.6.3 1.6 1.2 2.6 2.2 3.1C10.4 7.2 12 4.4 14.5 3c-.3 2.6.7 4.6 2.2 6.2A8.3 8.3 0 0 1 19 14.5c0 3.8-3.1 6.5-7 6.5Z',
  wand: 'm15 4 1 2 2 1-2 1-1 2-1-2-2-1 2-1ZM4 20 14 10M19 12l.6 1.4 1.4.6-1.4.6L19 16l-.6-1.4-1.4-.6 1.4-.6Z',
  folder: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z',
  play: 'M7 4.5v15l12-7.5Z',
  stop: 'M6 6h12v12H6z',
  report: 'M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6',
};
AZ.icon = (name, cls = '') => `<svg class="i ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${P[name] || P.info}"/></svg>`;

/* ---------- etiquetas gamer ---------- */
AZ.tagClass = t => {
  const s = String(t).toUpperCase();
  if (s.includes('FPS')) return 'fps';
  if (s.includes('DELAY') || s.includes('MIRA') || s.includes('POP-UP') || s.includes('CONTROLE') || s.includes('TECLADO')) return 'delay';
  if (s.includes('STUTTER') || s.includes('ESTÁVEL') || s.includes('LOADING') || s === 'RAM') return 'stutter';
  if (s.includes('PING') || s.includes('QUEDA') || s.includes('UPLOAD') || s.includes('DOWNLOAD') || s.includes('INTERNET')) return 'ping';
  if (s.includes('LEVE') || s.includes('LIXO') || s.includes('ESPAÇO') || s.includes('DISCO') || s.includes('BOOT') || s.includes('SSD')) return 'leve';
  if (s.includes('REPARO')) return 'repair';
  if (s.includes('TESTE') || s.includes('RISCO') || s.includes('SEGURANÇA-') || s.includes('CALOR') || s.includes('ANTI-CHEAT')) return 'risk';
  return 'neutral';
};
AZ.tags = list => (list || []).map(t => `<span class="tag ${AZ.tagClass(t)}">${AZ.esc(t)}</span>`).join(' ');
AZ.impact = n => `<span class="impact l${AZ.clamp(Number(n) || 1, 1, 3)}" title="Impacto ${['baixo', 'médio', 'alto'][AZ.clamp(Number(n) || 1, 1, 3) - 1]}"><i></i><i></i><i></i></span>`;
AZ.toggle = (on, attrs = '') => `<button type="button" class="toggle${on ? ' on' : ''}" role="switch" aria-checked="${on ? 'true' : 'false'}" ${attrs}></button>`;
AZ.stateIcon = st => {
  const map = {ok: ['ok', 'check'], applied: ['ok', 'check'], todo: ['todo', 'bolt'], recommended: ['todo', 'bolt'],
    manual: ['manual', 'info'], falha: ['bad', 'x'], atencao: ['manual', 'alert'], bad: ['bad', 'x']};
  const [cls, ic] = map[st] || ['manual', 'info'];
  return `<span class="state-ico ${cls}">${AZ.icon(ic)}</span>`;
};
AZ.skeleton = (n = 3) => Array.from({length: n}, () => '<div class="skeleton"></div>').join('');
AZ.sectionTitle = (icon, title, sub = '') => `<div class="section-title"><span class="ico">${AZ.icon(icon)}</span><div><h2>${title}</h2>${sub ? `<p>${sub}</p>` : ''}</div></div>`;
AZ.how = steps => `<div class="steps3">${steps.map((s, i) => `<div class="how"><span class="num">${i + 1}</span><div><b>${s[0]}</b><span>${s[1]}</span></div></div>`).join('')}</div>`;
AZ.scoreRing = (score, label) => {
  const r = 52, c = 2 * Math.PI * r, off = c * (1 - AZ.clamp(Number(score) || 0, 0, 100) / 100);
  return `<div class="score-ring"><svg viewBox="0 0 120 120"><circle class="track" cx="60" cy="60" r="${r}" fill="none" stroke-width="10"/>
    <circle class="val" cx="60" cy="60" r="${r}" fill="none" stroke-width="10" stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${off.toFixed(1)}"/></svg>
    <div class="num"><div><b>${score ?? '—'}</b><small>${AZ.esc(label || 'NOTA')}</small></div></div></div>`;
};

/* ---------- toast e modal ---------- */
let toastTimer = 0;
AZ.toast = (msg, ok = true) => {
  const t = AZ.$('#toast');
  t.textContent = msg;
  t.className = `toast show ${ok ? '' : 'bad'}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 4200);
};
AZ.modal = (html, {wide = false, closable = true, onClose} = {}) => {
  const root = AZ.$('#modalRoot');
  const wrap = document.createElement('div');
  wrap.className = 'backdrop';
  wrap.innerHTML = `<div class="modal${wide ? ' wide' : ''}" role="dialog" aria-modal="true">${closable ? '<button class="close" data-close aria-label="Fechar">×</button>' : ''}${html}</div>`;
  root.appendChild(wrap);
  const close = () => { wrap.remove(); onClose && onClose(); };
  wrap.addEventListener('click', e => {
    if (closable && (e.target === wrap || e.target.closest('[data-close]'))) close();
  });
  const esc = e => { if (e.key === 'Escape' && closable) { close(); document.removeEventListener('keydown', esc); } };
  document.addEventListener('keydown', esc);
  wrap.querySelector('button:not(.close), .input')?.focus({preventScroll: true});
  return {el: wrap.firstElementChild, close};
};
AZ.confirm = (title, text, okLabel = 'Confirmar', danger = false) => new Promise(resolve => {
  let done = false;
  const m = AZ.modal(`<h2>${title}</h2><p>${text}</p><div class="foot"><button class="btn ghost" data-close>Cancelar</button>
    <button class="btn ${danger ? 'danger' : 'primary'}" data-ok>${okLabel}</button></div>`, {onClose: () => { if (!done) resolve(false); }});
  m.el.querySelector('[data-ok]').addEventListener('click', () => { done = true; m.close(); resolve(true); });
});

/* ---------- jobs: qualquer operação que mexe no Windows ---------- */
const STATUS_TXT = {applying: 'aplicando', reading: 'lendo', waiting: 'aguardando', completed: 'ok', failed: 'falhou', not_applicable: 'não se aplica'};
AZ.runJob = (operation, params = {}, opts = {}) => new Promise(resolve => {
  const title = opts.title || 'Trabalhando…';
  const m = AZ.modal(`<div class="job"><div class="job-top"><div class="spinner" data-spin></div><div><b data-title>${AZ.esc(title)}</b>
    <span data-phase>${AZ.esc(opts.subtitle || 'Não feche o AZOR. Se o Windows pedir permissão, clique em Sim.')}</span></div></div>
    <div class="events" data-events><div class="event applying"><i></i><div><b>Iniciando</b></div></div></div>
    <div data-result></div><div class="foot" data-foot hidden><button class="btn primary" data-close>Fechar</button></div></div>`,
    {wide: true, closable: false});
  const el = m.el;
  let seen = 0;
  const events = el.querySelector('[data-events]');
  const paint = job => {
    const evs = job.events || [];
    if (evs.length && seen === 0) events.innerHTML = '';
    for (const ev of evs.slice(seen)) {
      const row = document.createElement('div');
      row.className = `event ${ev.status}`;
      row.innerHTML = `<i></i><div><b>${AZ.esc(ev.name)}</b> <span>— ${AZ.esc(ev.detail || STATUS_TXT[ev.status] || ev.status)}</span></div>`;
      events.appendChild(row);
    }
    seen = evs.length;
    events.scrollTop = events.scrollHeight;
    if (job.phase) el.querySelector('[data-phase]').textContent = job.phase;
  };
  const finish = (ok, result, errText) => {
    const spin = el.querySelector('[data-spin]');
    spin.outerHTML = `<span class="state-ico big ${ok ? 'ok' : 'bad'}">${AZ.icon(ok ? 'check' : 'alert')}</span>`;
    el.querySelector('[data-title]').textContent = ok ? (opts.doneTitle || 'Pronto!') : (opts.failTitle || 'Terminou com avisos');
    el.querySelector('[data-phase]').textContent = errText || result?.detail || '';
    const box = el.querySelector('[data-result]');
    box.innerHTML = opts.renderResult ? opts.renderResult(result || {}) : AZ.genericResult(result || {});
    const foot = el.querySelector('[data-foot]');
    foot.hidden = false;
    if (result?.restart) {
      const b = document.createElement('button');
      b.className = 'btn';
      b.innerHTML = `${AZ.icon('power')} Reiniciar agora`;
      b.onclick = async () => { const r = await AZ.action('restart_pc', {delay: 10}); AZ.toast(r.detail || 'Reiniciando…', r.ok); };
      foot.prepend(b);
    }
    foot.querySelector('[data-close]').addEventListener('click', () => { m.close(); resolve(result || {ok: false}); });
    AZ.refreshOverview();
  };
  (async () => {
    let job;
    try {
      const r = await AZ.post('/api/jobs', {operation, ...params, request_key: AZ.key()});
      job = r.job;
    } catch (e) { finish(false, null, e.message); return; }
    const poll = async () => {
      try {
        const r = await AZ.get(`/api/jobs/${job.id}`);
        paint(r.job);
        if (['completed', 'failed', 'interrupted'].includes(r.job.status)) {
          finish(r.job.status === 'completed', r.job.result, r.job.detail);
          return;
        }
      } catch (e) { /* servidor ocupado: tenta de novo */ }
      setTimeout(poll, 650);
    };
    poll();
  })();
});
AZ.genericResult = r => {
  const rows = r.results || [];
  if (!rows.length) return '';
  const bad = rows.filter(x => x.ok === false || x.status === 'failed');
  if (!bad.length) return '';
  return `<div class="card tight" style="margin-top:6px"><h3 class="bad">O que não deu certo</h3><div class="stack" style="margin-top:8px">
    ${bad.slice(0, 12).map(x => `<div><b>${AZ.esc(x.name || x.label || x.id || x.package)}</b><div class="muted" style="font-size:12.5px">${AZ.esc(x.detail || '')}</div></div>`).join('')}</div></div>`;
};

/* ---------- roteador ---------- */
AZ.page = (id, def) => { AZ.pages[id] = {id, ...def}; };
AZ.go = async (id, params = {}) => {
  const page = AZ.pages[id] || AZ.pages.home;
  if (AZ.current && AZ.current.leave) { try { AZ.current.leave(); } catch (e) { /* segue */ } }
  AZ.current = page;
  AZ.params = params;
  AZ.$$('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.page === page.id));
  AZ.$('#pageTitle').textContent = page.title;
  AZ.$('#pageSub').textContent = page.sub || '';
  const view = AZ.$('#view');
  view.scrollTop = 0;
  view.innerHTML = AZ.skeleton(4);
  try { await page.render(view, params); } catch (e) {
    console.error(e);
    view.innerHTML = `<div class="empty">Não foi possível carregar esta tela: ${AZ.esc(e.message)}<br><br><button class="btn" data-act="reload">Tentar de novo</button></div>`;
  }
  try { history.replaceState(null, '', `#${page.id}`); } catch (e) { /* segue */ }
};
AZ.reload = () => AZ.go(AZ.current?.id || 'home', AZ.params || {});

/* Cliques: cada página declara actions {nome: fn(el, ev)} e os elementos usam data-act. */
document.addEventListener('click', ev => {
  const el = ev.target.closest('[data-act]');
  if (!el || !AZ.$('#view').contains(el)) return;
  const name = el.dataset.act;
  if (name === 'reload') { AZ.reload(); return; }
  if (name === 'go') { AZ.go(el.dataset.page, {tab: el.dataset.tab}); return; }
  const fn = AZ.current?.actions?.[name];
  if (fn) fn(el, ev);
});
document.addEventListener('change', ev => {
  const el = ev.target.closest('[data-change]');
  if (!el || !AZ.$('#view').contains(el)) return;
  const fn = AZ.current?.actions?.[el.dataset.change];
  if (fn) fn(el, ev);
});
document.addEventListener('input', ev => {
  const el = ev.target.closest('[data-input]');
  if (!el || !AZ.$('#view').contains(el)) return;
  const fn = AZ.current?.actions?.[el.dataset.input];
  if (fn) fn(el, ev);
});

/* Ações de plano/diagnóstico usadas em várias telas. */
AZ.runStepAction = async (action, btn) => {
  if (!action) return;
  if (action.kind === 'boost') return AZ.pages.home.startBoost();
  if (action.kind === 'goto') return AZ.go(action.target, {tab: action.tab});
  if (action.kind === 'link') {
    const r = await AZ.action('open_link', {url: action.url});
    return AZ.toast(r.ok ? 'Abrindo no navegador…' : r.detail, r.ok);
  }
  if (action.kind === 'fix') {
    if (action.target === 'refresh') {
      if (btn) btn.disabled = true;
      const r = await AZ.action('refresh_max');
      AZ.toast(r.detail, r.ok);
      return AZ.reload();
    }
    const r = await AZ.runJob('compat_fix', {id: action.target}, {title: 'Consertando'});
    if (r) AZ.reload();
  }
};

AZ.refreshOverview = async () => {
  try {
    AZ.state.overview = await AZ.get('/api/overview');
    AZ.paintChrome && AZ.paintChrome();
  } catch (e) { /* servidor reiniciando */ }
  return AZ.state.overview;
};
