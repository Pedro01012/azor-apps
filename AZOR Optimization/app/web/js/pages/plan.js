/* Diagnóstico: o que fazer NESTE PC, em ordem, com um botão em cada passo. */
'use strict';
(() => {
  const {esc, icon} = AZ;
  const BTN = {boost: 'Rodar BOOST', goto: 'Abrir', fix: 'Corrigir agora', link: 'Baixar', info: ''};

  function stepCard(s, i) {
    const a = s.action || {};
    const label = a.kind === 'goto' ? ({apps: 'Ir para Apps', cleanup: 'Ir para Limpeza', hardware: 'Ver como fazer'}[a.target] || 'Abrir') : BTN[a.kind];
    const status = s.status === 'ok' ? '<span class="pill ok"><i></i>Em dia</span>'
      : s.status === 'manual' ? '<span class="pill warn"><i></i>Você faz</span>' : '<span class="pill todo"><i></i>Fazer</span>';
    return `<div class="item ${s.status === 'ok' ? 'dim' : ''}">
      ${AZ.stateIcon(s.status)}
      <div><div class="title">${esc(s.title)} ${status}</div>
        <div class="desc">${esc(s.why)}</div>
        <div class="meta">${AZ.tags(s.badges)} ${AZ.impact(s.impact)} ${s.detail ? `<span class="soft" style="font-size:12.5px">${esc(s.detail)}</span>` : ''}</div></div>
      <div class="side-actions">${s.status !== 'ok' && label ? `<button class="btn ${a.kind === 'boost' ? 'primary' : ''} sm" data-act="step" data-i="${i}">${label}</button>` : ''}</div>
    </div>`;
  }

  function compatCard(c) {
    if (!c || !c.checks || !c.checks.length) return c?.detail ? `<div class="empty">${esc(c.detail)}</div>` : '';
    return `<div class="list">${c.checks.map((k, i) => `<div class="item ${k.status === 'ok' ? 'dim' : ''}">
      ${AZ.stateIcon(k.status)}
      <div><div class="title">${esc(k.name)}</div><div class="desc">${esc(k.detail)}</div>
        <div class="meta"><span class="soft" style="font-size:12px">Jogos: ${esc(k.games)}</span></div>
        ${k.status !== 'ok' && k.fix ? `<div class="meta"><span class="muted" style="font-size:12.5px">${icon('info', 'soft')} ${esc(k.fix)}</span></div>` : ''}</div>
      <div class="side-actions">${k.status !== 'ok' && k.can_fix ? `<button class="btn sm" data-act="compat" data-i="${i}">${k.link ? 'Abrir' : 'Corrigir'}</button>` : ''}</div>
    </div>`).join('')}</div>`;
  }

  AZ.page('plan', {
    title: 'Diagnóstico',
    sub: 'O AZOR leu este PC e montou o que fazer, na ordem do que mais dá resultado. Faça de cima para baixo.',
    async render(view, params) {
      const plan = await AZ.get('/api/plan' + (params.force ? '?force=1' : ''), 120000);
      AZ.state.plan = plan;
      this.plan = plan;
      const pc = plan.pc || {};
      view.innerHTML = `
        <div class="grid" style="grid-template-columns:minmax(0,1.1fr) minmax(0,1fr)">
          <div class="card glow"><div class="row" style="gap:22px;flex-wrap:nowrap">${AZ.scoreRing(plan.score, plan.grade)}
            <div><span class="eyebrow">Nota deste PC</span><h2 style="margin-top:6px">${esc(pc.label || 'PC')}: ${plan.todo ? `${plan.todo} coisa(s) para fazer` : 'tudo em dia'}</h2>
            <p style="margin-top:6px">A nota sobe a cada passo feito. ${plan.manual ? `${plan.manual} passo(s) dependem de você (BIOS, peça ou site do fabricante).` : ''}</p>
            <div class="row" style="margin-top:14px"><button class="btn primary" data-act="boost">${icon('bolt')} Rodar BOOST</button>
            <button class="btn ghost" data-act="refresh">${icon('refresh')} Ler de novo</button></div></div></div></div>
          <div class="card"><span class="eyebrow">Guia para ${esc((pc.label || 'este PC').toLowerCase())}</span>
            <div class="stack" style="margin-top:12px">${(pc.tips || []).map(t => `<div class="row" style="flex-wrap:nowrap;align-items:flex-start;gap:10px">${icon('check', 'good')}<span style="font-size:13.5px">${esc(t)}</span></div>`).join('')}</div></div>
        </div>
        ${AZ.sectionTitle('plan', 'Passo a passo', 'O que falta primeiro; o que já está certo fica no fim, apagado.')}
        <div class="list">${plan.steps.map(stepCard).join('')}</div>
        ${AZ.sectionTitle('wand', 'Pré-set deste hardware', 'O que o AZOR decidiu por causa das SUAS peças, e o que depende de você.')}
        <div id="presetBox">${AZ.skeleton(2)}</div>
        ${AZ.sectionTitle('shield', 'Seus jogos vão abrir?', 'Requisitos de anti-cheat (Valorant, CS2/FACEIT, CoD, Fortnite) e o básico que segura qualquer jogo.')}
        <div id="compat">${AZ.skeleton(3)}</div>`;
      AZ.get('/api/preset', 90000).then(p => {
        AZ.state.preset = p;
        const el = AZ.$('#presetBox');
        if (!el) return;
        if (!p.ok) { el.innerHTML = `<div class="empty">${esc(p.detail || 'Hardware não reconhecido.')}</div>`; return; }
        const item = (st, title, text, act) => `<div class="item">${AZ.stateIcon(st)}<div><div class="title">${esc(title)}</div><div class="desc">${esc(text)}</div></div>
          <div class="side-actions">${act ? `<button class="btn sm" data-act="presetact" data-i="${act}">Abrir</button>` : ''}</div></div>`;
        this.presetNotes = p.notes || [];
        el.innerHTML = `<div class="card tight"><b>${esc(p.name)}</b><div class="row" style="margin-top:8px;gap:8px">${(p.chips || []).map(c => `<span class="pill" title="${esc(c.detail)}">${esc(c.label)}</span>`).join('')}</div>
          <div class="soft" style="font-size:12.5px;margin-top:8px">${Object.keys(p.add || {}).length} ajuste(s) a mais e ${Object.keys(p.skip || {}).length} protegido(s) no BOOST para este hardware.</div></div>
          <div class="list">${this.presetNotes.map((n, i) => item(n.level === 'action' ? 'todo' : n.level === 'warn' ? 'atencao' : 'manual', n.title, n.text, n.action ? String(i) : '')).join('')
            || '<div class="empty">Nada para fazer à mão: o BOOST resolve tudo neste hardware.</div>'}</div>`;
      }).catch(e => { const el = AZ.$('#presetBox'); if (el) el.innerHTML = `<div class="empty">${esc(e.message)}</div>`; });
      AZ.get('/api/compat', 120000).then(c => {
        this.compat = c;
        const el = AZ.$('#compat');
        if (el) el.innerHTML = compatCard(c);
      }).catch(e => { const el = AZ.$('#compat'); if (el) el.innerHTML = `<div class="empty">${esc(e.message)}</div>`; });
    },
    actions: {
      boost: () => AZ.pages.home.startBoost(),
      refresh: () => AZ.go('plan', {force: 1}),
      step: (el) => AZ.runStepAction(AZ.current.plan.steps[Number(el.dataset.i)].action, el),
      presetact: el => AZ.runStepAction(AZ.current.presetNotes[Number(el.dataset.i)].action, el),
      compat: async (el) => {
        const k = AZ.current.compat.checks[Number(el.dataset.i)];
        if (k.link) return AZ.runStepAction({kind: 'link', url: k.link});
        if (k.id === 'disk') return AZ.go('cleanup');
        await AZ.runStepAction({kind: 'fix', target: k.id}, el);
      },
    },
  });
})();
