/* Tweaks: o catálogo inteiro, agrupado pelo que cada ajuste dá para quem joga. */
'use strict';
(() => {
  const {esc, icon} = AZ;
  const S = {data: null, sel: new Set(), filter: 'all', q: '', pending: false, dns: null};

  const stateOf = t => t.state === 'applied' ? 'applied' : (t.eligible ? 'pending' : 'na');

  function row(t) {
    const st = stateOf(t);
    const on = S.sel.has(t.id);
    const tech = AZ.state.settings?.technician;
    const boost = t.boost === 'recomendado' ? '<span class="pill todo" title="Entra no BOOST Recomendado e no Extremo"><i></i>BOOST</span>'
      : t.boost === 'extremo' ? '<span class="pill warn" title="Entra só no BOOST Extremo"><i></i>EXTREMO</span>'
      : t.ab_test ? '<span class="pill bad" title="Fora do BOOST: teste você mesmo"><i></i>TESTE</span>' : '';
    const pill = st === 'applied' ? '<span class="pill ok"><i></i>Aplicado</span>'
      : st === 'pending' ? '<span class="pill"><i></i>Pendente</span>' : '<span class="pill" title="' + esc(t.reason) + '">Não se aplica</span>';
    return `<div class="item ${on ? 'selected' : ''} ${st === 'na' ? 'dim' : ''}" data-row="${t.id}">
      <input type="checkbox" class="check" data-change="pick" data-id="${t.id}" ${on ? 'checked' : ''} ${st === 'na' ? 'disabled' : ''} aria-label="Selecionar ${esc(t.title)}">
      <div>
        <div class="title">${esc(t.title || t.name)} ${boost} ${pill}</div>
        <div class="desc">${esc(t.simple || t.description)}</div>
        <div class="meta">${AZ.tags(t.badges)} ${AZ.impact(t.impact)}
          ${t.restart ? `<span class="soft" style="font-size:12px">${icon('power')} vale depois de reiniciar</span>` : ''}
          ${t.one_way ? '<span class="tag risk">SEM DESFAZER</span>' : ''}</div>
        ${st === 'na' ? `<div class="meta"><span class="soft" style="font-size:12.5px">${esc(t.reason)}</span></div>` : ''}
        <details ${tech ? 'open' : ''}><summary>O que muda na prática</summary><div class="tech">
          <div><b>O que faz:</b> ${esc(t.description)}</div>
          ${t.trade_off ? `<div><b>O que você perde:</b> ${esc(t.trade_off)}</div>` : ''}
          ${t.audit_reason && !t.boost ? `<div><b>Por que não está no BOOST:</b> ${esc(t.audit_reason)}</div>` : ''}
          ${tech && t.source ? `<div><b>Fonte:</b> ${esc(t.source)}</div>` : ''}
          ${tech && t.metric ? `<div><b>Mede em:</b> ${esc(t.metric)}</div>` : ''}
          ${tech && t.current ? `<div><b>Leitura agora:</b> ${esc(t.state_detail || t.current)}</div>` : ''}
        </div></details>
      </div>
      <div class="side-actions">
        ${st === 'applied' && t.can_revert ? `<button class="btn sm ghost" data-act="undo1" data-id="${t.id}">${icon('undo')} Desfazer</button>` : ''}
        ${st === 'pending' ? `<button class="btn sm" data-act="apply1" data-id="${t.id}">Aplicar</button>` : ''}
      </div>
    </div>`;
  }

  function dnsCard() {
    const d = S.dns;
    if (!d) return `<div class="card tight" id="dnsCard">${AZ.skeleton(1)}</div>`;
    return `<div class="card tight" id="dnsCard"><div class="spread"><div><div class="title" style="font:650 14px var(--font-title)">DNS da internet
      <span class="tag ping">INTERNET</span></div>
      <div class="desc muted" style="font-size:13px;margin-top:4px">O DNS não muda o ping da partida, mas deixa sites, logins e lojas abrindo mais rápido e resolve "sem conexão" com a internet funcionando.</div></div>
      <select class="input" data-change="dns">${(d.providers || []).map(p => `<option value="${p.id}" ${p.id === d.current ? 'selected' : ''}>${esc(p.label)}</option>`).join('')}</select></div></div>`;
  }

  function visible(t) {
    if (S.filter !== 'all' && t.goal !== S.filter) return false;
    if (S.pending && stateOf(t) !== 'pending') return false;
    if (S.q) {
      const hay = `${t.title} ${t.name} ${t.simple} ${(t.badges || []).join(' ')}`.toLowerCase();
      if (!hay.includes(S.q)) return false;
    }
    return true;
  }

  function paintList() {
    const d = S.data;
    const goals = d.goals || [];
    const html = goals.map(g => {
      const items = d.tasks.filter(t => t.goal === g.id && visible(t));
      if (!items.length) return '';
      const applied = items.filter(t => stateOf(t) === 'applied').length;
      return `<div class="group-head"><span class="ico">${icon(g.icon)}</span><div><h2>${esc(g.label)}</h2><p>${esc(g.hint)}</p></div>
        <div class="row"><span class="soft" style="font-size:12.5px">${applied} de ${items.length} aplicados</span>
        <button class="btn sm ghost" data-act="pickgroup" data-goal="${g.id}">Marcar pendentes</button></div></div>
        ${g.id === 'ping' ? dnsCard() : ''}
        <div class="list">${items.map(row).join('')}</div>`;
    }).join('');
    AZ.$('#tweakList').innerHTML = html || '<div class="empty">Nenhum ajuste com esse filtro.</div>';
    paintBar();
  }

  function paintBar() {
    const n = S.sel.size;
    const bar = AZ.$('#tweakBar');
    if (!bar) return;
    const applied = [...S.sel].filter(id => stateOf(S.data.tasks.find(t => t.id === id) || {}) === 'applied').length;
    bar.hidden = !n;
    bar.innerHTML = `<div><b>${n} ajuste(s) selecionado(s)</b><br><span>${n - applied} para aplicar · ${applied} já aplicado(s)</span></div>
      <div class="row"><button class="btn ghost" data-act="clear">Limpar</button>
      ${applied ? `<button class="btn" data-act="undosel">${icon('undo')} Desfazer ${applied}</button>` : ''}
      ${n - applied ? `<button class="btn primary" data-act="applysel">${icon('bolt')} Aplicar ${n - applied}</button>` : ''}</div>`;
  }

  function stats() {
    const t = S.data.tasks;
    const c = s => t.filter(x => stateOf(x) === s).length;
    return `<div class="meters">
      <div class="meter"><small>APLICADOS</small><b class="good">${c('applied')}</b><span>confirmados por releitura</span></div>
      <div class="meter"><small>PENDENTES</small><b style="color:var(--accent2)">${c('pending')}</b><span>podem ser aplicados</span></div>
      <div class="meter"><small>NO BOOST</small><b>${t.filter(x => x.boost).length}</b><span>entram no clique único</span></div>
      <div class="meter"><small>NÃO SE APLICAM</small><b class="soft">${c('na')}</b><span>não servem para este PC</span></div></div>`;
  }

  async function run(op, ids, title) {
    const r = await AZ.runJob(op, {ids}, {title, renderResult: res => {
      const rows = res.results || [];
      return rows.length ? `<div class="list" style="margin-top:6px">${rows.map(x => `<div class="item tight" style="grid-template-columns:auto minmax(0,1fr)">${AZ.stateIcon(x.ok || x.status === 'completed' ? 'ok' : (x.status === 'not_applicable' ? 'manual' : 'bad'))}
        <div><b>${esc((S.data.tasks.find(t => t.id === x.id) || {}).title || x.name || x.id)}</b><div class="muted" style="font-size:12.5px">${esc(x.detail || '')}</div></div></div>`).join('')}</div>` : '';
    }});
    S.sel.clear();
    await load(true);
    return r;
  }

  async function load(force) {
    S.data = await AZ.get('/api/tweaks' + (force ? '?force=1' : ''), 120000);
    if (AZ.current?.id === 'tweaks') {
      AZ.$('#tweakStats').innerHTML = stats();
      paintList();
    }
  }

  AZ.page('tweaks', {
    title: 'Tweaks',
    sub: 'Cada ajuste diz o que ele dá: +FPS, -DELAY, PING, -STUTTER, +LEVE. Marque, aplique e desfaça quando quiser.',
    async render(view, params = {}) {
      if (params.goal) S.filter = params.goal;
      if (params.q != null) S.q = String(params.q);
      AZ.state.settings = await AZ.get('/api/settings').catch(() => ({}));
      view.innerHTML = `
        ${AZ.how([['Marque o que quer', 'Ou use os atalhos Recomendado / Extremo, que marcam o mesmo que o BOOST.'],
                  ['Clique em Aplicar', 'Cada ajuste é gravado, relido e só conta se o Windows confirmar.'],
                  ['Desfaça quando quiser', 'Um clique volta o valor exato de antes. Nada é definitivo.']])}
        <div id="tweakStats">${AZ.skeleton(1)}</div>
        <div class="card tight"><div class="spread">
          <div class="row"><button class="btn sm" data-act="preset" data-p="recomendado">${icon('bolt')} Marcar Recomendado</button>
            <button class="btn sm" data-act="preset" data-p="extremo">${icon('flame')} Marcar Extremo</button>
            <label class="row soft" style="font-size:12.5px;gap:8px"><input type="checkbox" class="check" data-change="pending" ${S.pending ? 'checked' : ''}> Só pendentes</label></div>
          <input class="input search" type="search" placeholder="Buscar: mouse, rede, fps, Edge…" data-input="search" value="${esc(S.q)}">
        </div>
        <div class="filters" style="margin-top:12px"><button class="filter ${S.filter === 'all' ? 'active' : ''}" data-act="filter" data-f="all">Todos</button>
          ${[['fps', 'Mais FPS'], ['delay', 'Menos delay'], ['stutter', 'Sem travadinhas'], ['ping', 'Internet e ping'], ['leve', 'Windows leve'], ['privacidade', 'Privacidade'], ['visual', 'Visual e conforto'], ['reparo', 'Consertos'], ['avancado', 'Avançado']]
            .map(([k, l]) => `<button class="filter ${S.filter === k ? 'active' : ''}" data-act="filter" data-f="${k}">${l}</button>`).join('')}</div></div>
        <div id="tweakList">${AZ.skeleton(6)}</div>
        <div class="actionbar" id="tweakBar" hidden></div>`;
      await load(false);
      AZ.get('/api/dns').then(d => { S.dns = d; const c = AZ.$('#dnsCard'); if (c) c.outerHTML = dnsCard(); }).catch(() => {});
    },
    actions: {
      pick: el => {
        el.checked ? S.sel.add(el.dataset.id) : S.sel.delete(el.dataset.id);
        el.closest('.item').classList.toggle('selected', el.checked);
        paintBar();
      },
      pickgroup: el => {
        S.data.tasks.filter(t => t.goal === el.dataset.goal && stateOf(t) === 'pending' && visible(t)).forEach(t => S.sel.add(t.id));
        paintList();
      },
      preset: el => {
        const want = el.dataset.p === 'extremo' ? ['recomendado', 'extremo'] : ['recomendado'];
        S.data.tasks.filter(t => want.includes(t.boost) && stateOf(t) === 'pending').forEach(t => S.sel.add(t.id));
        paintList();
        AZ.toast(`${S.sel.size} ajuste(s) marcado(s). Revise e clique em Aplicar.`);
      },
      clear: () => { S.sel.clear(); paintList(); },
      filter: el => { S.filter = el.dataset.f; AZ.$$('.filter').forEach(b => b.classList.toggle('active', b === el)); paintList(); },
      pending: el => { S.pending = el.checked; paintList(); },
      search: el => { S.q = el.value.trim().toLowerCase(); paintList(); },
      apply1: el => run('apply_tasks', [el.dataset.id], 'Aplicando ajuste'),
      undo1: el => run('revert_tasks', [el.dataset.id], 'Desfazendo ajuste'),
      applysel: () => run('apply_tasks', [...S.sel].filter(id => stateOf(S.data.tasks.find(t => t.id === id) || {}) !== 'applied'), 'Aplicando ajustes'),
      undosel: () => run('revert_tasks', [...S.sel].filter(id => stateOf(S.data.tasks.find(t => t.id === id) || {}) === 'applied'), 'Desfazendo ajustes'),
      dns: async el => {
        const r = await AZ.runJob('dns_set', {provider: el.value}, {title: 'Trocando o DNS'});
        if (r?.state) { S.dns = r.state; }
      },
    },
  });
})();
