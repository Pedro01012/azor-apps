/* Reparar: desfazer, ponto de restauração, consertos do Windows e histórico. */
'use strict';
(() => {
  const {esc, icon} = AZ;
  const S = {hist: null, dns: null, ping: null, pinging: false, showAll: false};
  const FIXES = [
    ['system', 'repair', 'Windows corrompido', 'Tela azul, programa fechando sozinho, erro de DLL, jogo que não abre sem motivo.',
      'Roda SFC e DISM (os consertos oficiais da Microsoft) e checa o disco. Leva de 10 a 30 minutos.', ['REPARO', 'ESTÁVEL']],
    ['network', 'ping', 'Internet com problema', 'Sem internet, Wi-Fi caindo, ping que subiu do nada, "sem acesso à rede".',
      'Reseta Winsock, TCP/IP e o cache de DNS para o padrão de fábrica. Precisa reiniciar.', ['PING', 'QUEDA']],
    ['update', 'refresh', 'Windows Update travado', 'Atualização parada em 0%, erro ao atualizar, download infinito.',
      'Para o serviço, limpa os caches do Update e religa. Não apaga atualização instalada.', ['REPARO']],
    ['legacy_games', 'games', 'Jogo antigo não abre', 'Jogos de 2002 a 2012 (GTA SA, CS 1.6, Age of Empires…) pedindo .NET ou DirectPlay.',
      'Liga o .NET Framework 3.5 e o DirectPlay pelo próprio Windows.', ['REPARO']],
    ['winget', 'download', 'Instalador de apps quebrado', 'A aba Apps não instala nada, "winget não reconhecido".',
      'Reinstala o Instalador de Aplicativos da Microsoft (winget).', ['REPARO']],
  ];
  const PANELS = [['devices', 'hardware', 'Gerenciador de dispositivos'], ['graphics', 'gpu', 'Gráficos por app'], ['gamemode', 'games', 'Modo de Jogo'],
    ['sound', 'play', 'Som'], ['network', 'ping', 'Conexões de rede'], ['power', 'power', 'Energia'], ['taskmgr', 'cpu', 'Gerenciador de tarefas'],
    ['update', 'refresh', 'Windows Update'], ['restore', 'undo', 'Restauração do sistema']];
  const STATUS = {applied: ['ok', 'Aplicado'], restored: ['manual', 'Desfeito'], rolled_back: ['manual', 'Voltou sozinho (não confirmou)'],
    recovery_required: ['bad', 'Precisa de atenção'], prepared: ['manual', 'Incompleto'], unreadable: ['bad', 'Registro ilegível']};

  const when = t => t ? new Date(t * 1000).toLocaleString('pt-BR', {day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'}) : '';

  function hero() {
    const h = S.hist || {};
    const pr = h.protection || {};
    const applied = (h.applied || []).length;
    return `<div class="grid g2">
      <div class="card glow"><span class="eyebrow">Botão do pânico</span><h2 style="margin-top:6px">Desfazer tudo do AZOR</h2>
        <p style="margin-top:6px;font-size:13px">Volta registro, energia, serviços, tarefas, inicialização e rede exatamente para como estavam antes da primeira otimização. ${applied ? `Hoje há ${applied} ajuste(s) do AZOR ativos.` : ''}</p>
        <div class="row" style="margin-top:14px"><button class="btn danger" data-act="undoall" ${h.baseline === false && !applied ? 'disabled' : ''}>${icon('undo')} Desfazer tudo</button>
          <button class="btn ghost" data-act="undolast">Desfazer só o último BOOST</button></div></div>
      <div class="card"><span class="eyebrow">Ponto de restauração</span><h2 style="margin-top:6px">${pr.enabled ? 'Proteção do Sistema ligada' : pr.enabled === false ? 'Proteção do Sistema desligada' : 'Proteção do Sistema'}</h2>
        <p style="margin-top:6px;font-size:13px">O Windows guarda uma cópia das configurações e drivers. Se algo der muito errado, dá para voltar pelo boot. O BOOST cria um antes de começar.
          ${pr.last_point ? `<br><span class="soft">Último ponto: ${esc(pr.last_point)}</span>` : ''}</p>
        <div class="row" style="margin-top:14px"><button class="btn" data-act="rp">${icon('shield')} Criar ponto agora</button>
          <button class="btn ghost" data-act="panel" data-p="restore">Abrir restauração do Windows</button></div></div></div>`;
  }

  function fixesView() {
    return `${AZ.sectionTitle('repair', 'Consertos', 'Escolha pelo sintoma. Cada um usa só as ferramentas oficiais do Windows.')}
      <div class="grid g2">${FIXES.map(([id, ic, title, sym, what, tags]) => `<div class="card"><div class="row" style="flex-wrap:nowrap;align-items:flex-start">
        <span class="state-ico todo">${icon(ic)}</span><div style="flex:1"><b>${title}</b> ${AZ.tags(tags)}
        <div class="muted" style="font-size:13px;margin-top:4px"><b style="color:var(--text)">Quando usar:</b> ${sym}</div>
        <div class="soft" style="font-size:12.5px;margin-top:4px">${what}</div>
        <button class="btn sm" style="margin-top:10px" data-act="fix" data-k="${id}">Consertar</button></div></div></div>`).join('')}</div>`;
  }

  function netView() {
    const p = S.ping, d = S.dns;
    const tone = !p?.avg_ms ? '' : p.avg_ms <= 30 ? 'good' : p.avg_ms <= 80 ? 'warn' : 'bad';
    return `${AZ.sectionTitle('ping', 'Internet', 'Teste de ping e DNS. DNS não baixa o ping do jogo; ele só deixa sites e logins mais rápidos e estáveis.')}
      <div class="grid g2"><div class="card"><span class="eyebrow">Ping agora</span>
        <div class="row" style="margin-top:8px"><span class="big-num ${tone}">${p?.avg_ms != null ? `${String(p.avg_ms).replace('.', ',')} ms` : '—'}</span>
          <span class="muted">${p?.avg_ms != null ? `mín ${p.min_ms} · máx ${p.max_ms} ms` : 'até a Cloudflare (1.1.1.1)'}</span></div>
        ${p && p.max_ms - p.min_ms > 30 ? '<div class="desc warn" style="margin-top:6px">Ping variando muito (jitter). Se estiver no Wi-Fi, teste no cabo: é a causa nº 1 de "teleporte" no jogo.</div>' : ''}
        ${p && !p.ok ? '<div class="desc bad" style="margin-top:6px">Sem resposta. Veja o cabo/Wi-Fi ou use o conserto "Internet com problema".</div>' : ''}
        <div class="row" style="margin-top:12px"><button class="btn" data-act="ping" ${S.pinging ? 'disabled' : ''}>${icon('ping')} ${S.pinging ? 'Testando…' : 'Testar ping'}</button>
          <button class="btn ghost" data-act="flush">Limpar cache de DNS</button></div></div>
        <div class="card"><span class="eyebrow">DNS</span>
          ${d ? `<p style="font-size:13px;margin-top:6px">Placa de rede: ${esc((d.adapters || []).map(a => a.name).join(', ') || '—')}</p>
            <select class="input" style="margin-top:10px;width:100%" data-change="dns">${(d.providers || []).map(pr => `<option value="${pr.id}" ${pr.id === d.current ? 'selected' : ''}>${esc(pr.label)}</option>`).join('')}</select>
            <p class="soft" style="font-size:12px;margin-top:8px">Cloudflare costuma ser o mais rápido no Brasil. "Automático" volta para o DNS da sua operadora.</p>` : AZ.skeleton(1)}</div></div>`;
  }

  function panelsView() {
    return `${AZ.sectionTitle('settings', 'Atalhos do Windows', 'Os painéis que técnico abre toda hora, num clique.')}
      <div class="row">${PANELS.map(([id, ic, l]) => `<button class="btn sm" data-act="panel" data-p="${id}">${icon(ic)} ${l}</button>`).join('')}</div>`;
  }

  function historyView() {
    const h = S.hist;
    if (!h) return AZ.skeleton(3);
    const rows = h.transactions || [];
    const shown = S.showAll ? rows : rows.slice(0, 15);
    return `${AZ.sectionTitle('clock', 'Histórico', 'Cada ajuste gravado pelo AZOR, com o valor de antes guardado. Desfaça um por um se quiser.')}
      ${(h.reports || []).length ? `<div class="list" style="margin-bottom:12px">${h.reports.slice(0, 5).map(r => `<div class="item">${AZ.stateIcon(r.ok ? 'ok' : 'atencao')}
        <div><div class="title">BOOST ${esc(r.mode || '')}</div><div class="desc">${esc(when(r.time))} · ${esc(r.detail || '')}</div></div><div></div></div>`).join('')}</div>` : ''}
      <div class="list">${shown.map(t => {
        const [st, label] = STATUS[t.status] || ['manual', t.status];
        return `<div class="item ${t.status === 'applied' ? '' : 'dim'}">${AZ.stateIcon(st)}
          <div><div class="title">${esc(t.name || t.task_id || 'Ajuste')} <span class="pill ${st === 'ok' ? 'ok' : st === 'bad' ? 'bad' : ''}"><i></i>${esc(label)}</span></div>
          <div class="desc">${esc(when(t.time))}${t.detail ? ` · ${esc(t.detail)}` : ''}</div></div>
          <div class="side-actions">${t.status === 'applied' ? `<button class="btn sm ghost" data-act="txundo" data-id="${esc(t.id)}">${icon('undo')} Desfazer</button>` : ''}</div></div>`;
      }).join('') || '<div class="empty">Nenhum ajuste gravado ainda. Rode o BOOST na Início.</div>'}</div>
      ${rows.length > 15 ? `<div class="row" style="margin-top:8px"><button class="linkbtn" data-act="more">${S.showAll ? 'Mostrar menos' : `Mostrar todos (${rows.length})`}</button></div>` : ''}`;
  }

  function paint() {
    const el = AZ.$('#rpBody');
    if (!el) return;
    el.innerHTML = `${S.hist ? hero() : AZ.skeleton(2)}${fixesView()}${netView()}${panelsView()}${historyView()}`;
  }
  async function load() {
    S.hist = await AZ.get('/api/history', 60000).catch(() => ({transactions: [], reports: []}));
    if (AZ.current?.id === 'repair') paint();
  }
  async function loadDns() {
    S.dns = await AZ.get('/api/dns', 45000).catch(() => null);
    if (AZ.current?.id === 'repair') paint();
  }

  AZ.page('repair', {
    title: 'Reparar',
    sub: 'Desfazer tudo num clique, ponto de restauração e os consertos oficiais do Windows escolhidos pelo sintoma.',
    async render(view) {
      view.innerHTML = '<div id="rpBody"></div>';
      paint();
      load();
      loadDns();
    },
    actions: {
      undoall: async () => {
        if (!await AZ.confirm('Desfazer tudo do AZOR?', 'Todos os ajustes voltam para como estavam antes do AZOR. Apps removidos não voltam sozinhos (reinstale pela Microsoft Store). O PC precisa reiniciar no fim.', 'Desfazer tudo', true)) return;
        await AZ.runJob('undo_everything', {}, {title: 'Desfazendo tudo'});
        load();
      },
      undolast: async () => {
        if (!await AZ.confirm('Desfazer o último BOOST?', 'Volta os ajustes do último BOOST para os valores de antes dele.', 'Desfazer')) return;
        await AZ.runJob('restore_all', {target: 'last'}, {title: 'Desfazendo o último BOOST'});
        load();
      },
      rp: () => AZ.runJob('fix', {kind: 'restore_point'}, {title: 'Criando ponto de restauração', subtitle: 'O Windows pode levar até 1 minuto.'}).then(load),
      fix: async el => {
        const f = FIXES.find(x => x[0] === el.dataset.k);
        if (!await AZ.confirm(`${f[2]}?`, f[4], 'Consertar')) return;
        AZ.runJob('fix', {kind: f[0]}, {title: f[2], subtitle: 'Pode usar o PC enquanto isso. Não desligue.'});
      },
      ping: async () => {
        S.pinging = true; paint();
        S.ping = await AZ.action('ping', {host: '1.1.1.1'}).catch(e => ({ok: false, detail: e.message}));
        S.pinging = false; paint();
      },
      flush: async () => { const r = await AZ.action('flush_dns'); AZ.toast(r.detail, r.ok); },
      dns: async el => {
        const r = await AZ.runJob('dns_set', {provider: el.value}, {title: 'Trocando o DNS'});
        if (r) loadDns();
      },
      panel: async el => { const r = await AZ.action('open_panel', {panel: el.dataset.p}); if (!r.ok) AZ.toast(r.detail, false); },
      txundo: async el => {
        await AZ.runJob('restore_transaction', {id: el.dataset.id}, {title: 'Desfazendo o ajuste'});
        load();
      },
      more: () => { S.showAll = !S.showAll; paint(); },
    },
  });
})();
