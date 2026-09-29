/* Limpeza: arquivos inúteis e o que abre junto com o Windows. */
'use strict';
(() => {
  const {esc, icon} = AZ;
  const S = {tab: 'files', scan: null, sel: null, startup: null};
  const KIND = {
    conflito: ['Outros otimizadores', 'Mexem em prioridade, serviços e memória por conta própria e brigam com o AZOR. O BOOST tira do boot.', 'alert'],
    inutil: ['Inúteis', 'Não precisam abrir com o Windows. O BOOST desliga.', 'trash'],
    lancador: ['Lançadores e chat', 'Steam, Epic, Discord… Desligados, abrem na hora que você for jogar. O BOOST Extremo desliga.', 'games'],
    outro: ['Outros', 'Não reconhecidos. Desligue só se souber o que é.', 'info'],
    essencial: ['Essenciais', 'Driver, antivírus, anti-cheat e software do seu periférico. Deixe ligado.', 'shield'],
  };

  function tabs() {
    const u = S.startup ? S.startup.useless_on : 0;
    return `<div class="tabs"><button class="tab ${S.tab === 'files' ? 'active' : ''}" data-act="tab" data-t="files">${icon('cleanup')} Arquivos</button>
      <button class="tab ${S.tab === 'startup' ? 'active' : ''}" data-act="tab" data-t="startup">${icon('power')} Inicialização ${u ? `<span class="count">${u}</span>` : ''}</button></div>`;
  }

  function filesView() {
    const s = S.scan;
    if (!s) return AZ.skeleton(5);
    if (!S.sel) S.sel = new Set(s.targets.filter(t => t.boost && t.bytes > 0).map(t => t.id));
    const total = s.targets.filter(t => S.sel.has(t.id)).reduce((a, t) => a + t.bytes, 0);
    const disk = s.disk || {};
    const tone = disk.used_pct >= 90 ? 'bad' : disk.used_pct >= 80 ? 'warn' : 'good';
    return `<div class="card glow"><div class="spread"><div><span class="eyebrow">Disco do Windows ${esc(disk.drive || '')}</span>
      <div class="row" style="margin-top:8px"><span class="big-num">${String(disk.free_gb ?? '—').replace('.', ',')} GB</span><span class="muted">livres de ${String(disk.total_gb ?? '—').replace('.', ',')} GB</span></div></div>
      <div style="text-align:right"><span class="eyebrow">Selecionado</span><div class="big-num" style="margin-top:8px;color:var(--accent2)">${AZ.bytes(total)}</div></div></div>
      <div class="bar ${tone}" style="height:10px;margin-top:14px"><i style="width:${disk.used_pct || 0}%"></i></div></div>
      <div class="list">${s.targets.map(t => `<div class="item ${S.sel.has(t.id) ? 'selected' : ''} ${t.bytes ? '' : 'dim'}">
        <input type="checkbox" class="check" data-change="pick" data-id="${t.id}" ${S.sel.has(t.id) ? 'checked' : ''} ${t.blocked ? 'disabled' : ''}>
        <div><div class="title">${esc(t.label)} ${t.boost ? '<span class="pill todo"><i></i>BOOST</span>' : ''}</div>
          ${t.warn ? `<div class="desc warn">${icon('alert')} ${esc(t.warn)}</div>` : ''}
          ${t.blocked ? '<div class="desc soft">Precisa do AZOR como administrador.</div>' : ''}</div>
        <div class="side-actions"><b style="font:700 15px var(--font-display)">${t.bytes ? AZ.bytes(t.bytes) : 'limpo'}</b></div></div>`).join('')}</div>
      <div class="row" style="margin-top:6px"><button class="btn primary lg" data-act="clean" ${S.sel.size ? '' : 'disabled'}>${icon('trash')} Limpar ${AZ.bytes(total)}</button>
        <button class="btn" data-act="rescan">${icon('refresh')} Medir de novo</button></div>
      ${AZ.sectionTitle('disk', 'Mais espaço', 'Estes pedem confirmação porque não têm volta.')}
      <div class="grid g2">
        <div class="card tight"><div class="spread"><div><b>Lixeira</b><div class="muted" style="font-size:13px">${s.recycle?.items || 0} item(ns), ${AZ.bytes(s.recycle?.bytes || 0)}. Apaga para sempre.</div></div>
          <button class="btn sm danger" data-act="bin" ${s.recycle?.items ? '' : 'disabled'}>Esvaziar</button></div></div>
        <div class="card tight"><div class="spread"><div><b>Componentes antigos do Windows</b><div class="muted" style="font-size:13px">Versões antigas guardadas por atualizações (DISM). Costuma liberar de 1 a 5 GB. Leva de 5 a 20 min.</div></div>
          <button class="btn sm" data-act="deep">Limpar</button></div></div></div>
      <div class="card tight" style="margin-top:12px"><div class="row">${AZ.stateIcon('manual')}<div><b>O AZOR nunca apaga</b><div class="muted" style="font-size:13px">Seus arquivos, Downloads, saves, pastas de jogos, pontos de restauração e o Prefetch (que faz os programas abrirem rápido).</div></div></div></div>`;
  }

  function startupView() {
    const st = S.startup;
    if (!st) return AZ.skeleton(6);
    if (!st.items.length) return '<div class="empty">Nenhum programa abrindo com o Windows (ou a leitura não está disponível neste sistema).</div>';
    return `${AZ.how([['Veja o que abre com o Windows', 'A memória mostrada é o que o programa está usando agora.'],
                      ['Desligue o que não precisa', 'O programa continua instalado; só não abre sozinho.'],
                      ['Religue quando quiser', 'Mesmo registro do Gerenciador de Tarefas: volta com um clique.']])}
      <div class="row"><button class="btn primary" data-act="offuseless" ${st.useless_on ? '' : 'disabled'}>${icon('power')} Desligar os ${st.useless_on} inúteis${st.conflicts_on ? ` (${st.conflicts_on} otimizador${st.conflicts_on > 1 ? 'es' : ''})` : ''}</button>
        <button class="btn" data-act="offlaunchers" ${st.launchers_on ? '' : 'disabled'}>Desligar também os ${st.launchers_on} lançadores</button></div>
      ${['conflito', 'inutil', 'lancador', 'outro', 'essencial'].map(k => {
        const items = st.items.filter(i => i.kind === k);
        if (!items.length) return '';
        const [label, hint, ic] = KIND[k];
        return `<div class="group-head"><span class="ico">${icon(ic)}</span><div><h2>${label}</h2><p>${hint}</p></div></div>
          <div class="list">${items.map(i => `<div class="item ${i.enabled ? '' : 'dim'}">${AZ.stateIcon(i.enabled ? (k === 'essencial' ? 'ok' : 'todo') : 'manual')}
            <div><div class="title">${esc(i.name)} ${i.running ? '<span class="pill ok"><i></i>Rodando</span>' : ''}</div>
            <div class="desc">${i.memory_mb ? `Usando ${AZ.mb(i.memory_mb)} de RAM agora · ` : ''}${esc(i.scope_label || '')}</div></div>
            <div class="side-actions"><span class="soft" style="font-size:12px">${i.enabled ? 'Abre com o Windows' : 'Desligado'}</span>
              ${AZ.toggle(i.enabled, `data-act="toggle" data-scope="${esc(i.scope)}" data-name="${esc(i.name)}"`)}</div></div>`).join('')}</div>`;
      }).join('')}`;
  }

  function paint() {
    AZ.$('#clTabs').innerHTML = tabs();
    AZ.$('#clBody').innerHTML = S.tab === 'files' ? filesView() : startupView();
  }
  async function loadScan(force) {
    S.scan = await AZ.get('/api/cleanup' + (force ? '?force=1' : ''), 120000).catch(e => ({targets: [], disk: {}, detail: e.message}));
    S.sel = null;
    if (AZ.current?.id === 'cleanup') paint();
  }
  async function loadStartup(force) {
    S.startup = await AZ.get('/api/startup' + (force ? '?force=1' : ''), 60000).catch(() => ({items: []}));
    if (AZ.current?.id === 'cleanup') paint();
  }
  async function bulk(extreme) {
    await AZ.runJob('startup_bulk', {extreme}, {title: 'Limpando a inicialização'});
    loadStartup(true);
  }

  AZ.page('cleanup', {
    title: 'Limpeza',
    sub: 'Apaga só o que é lixo (mede antes e depois) e tira do boot o que não precisa abrir com o Windows.',
    async render(view, params) {
      if (params.tab) S.tab = params.tab === 'startup' ? 'startup' : 'files';
      view.innerHTML = '<div id="clTabs"></div><div id="clBody"></div>';
      paint();
      loadScan(false);
      loadStartup(false);
    },
    actions: {
      tab: el => { S.tab = el.dataset.t; paint(); },
      pick: el => { el.checked ? S.sel.add(el.dataset.id) : S.sel.delete(el.dataset.id); paint(); },
      rescan: () => { S.scan = null; paint(); loadScan(true); },
      clean: async () => {
        const r = await AZ.runJob('cleanup', {ids: [...S.sel]}, {title: 'Limpando', renderResult: x => `<div class="result-hero"><b>${AZ.mb(x.freed_mb || 0)} LIBERADOS</b><span>${x.disk ? `${x.disk.free_gb} GB livres agora` : ''}</span></div>`});
        if (r) loadScan(true);
      },
      bin: async () => {
        if (!await AZ.confirm('Esvaziar a Lixeira?', 'Os arquivos da Lixeira serão apagados para sempre.', 'Esvaziar', true)) return;
        await AZ.runJob('fix', {kind: 'recycle_bin'}, {title: 'Esvaziando a Lixeira'});
        loadScan(true);
      },
      deep: async () => { await AZ.runJob('fix', {kind: 'deep_cleanup'}, {title: 'Limpando componentes antigos', subtitle: 'O DISM pode levar até 20 minutos. Pode usar o PC enquanto isso.'}); loadScan(true); },
      toggle: async el => {
        const on = !el.classList.contains('on');
        el.disabled = true;
        const r = await AZ.action('startup_set', {scope: el.dataset.scope, item: el.dataset.name, enabled: on}).catch(e => ({ok: false, detail: e.message}));
        AZ.toast(r.detail || (on ? 'Religado.' : 'Desligado.'), r.ok);
        loadStartup(true);
      },
      offuseless: () => bulk(false),
      offlaunchers: () => bulk(true),
    },
  });
})();
