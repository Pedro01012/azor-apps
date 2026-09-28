/* Jogos: monitor no máximo, placa de vídeo certa, teste de FPS antes/depois e Fortnite. */
'use strict';
(() => {
  const {esc, icon} = AZ;
  const S = {data: null, test: null, customer: '', target: '', poll: 0};

  const num = (v, d = 0) => v == null ? '—' : Number(v).toFixed(d).replace('.', ',');

  function monitorCard(d) {
    const disp = d.display || {};
    if (!disp.ok) return `<div class="card tight"><div class="row">${AZ.stateIcon('manual')}<div><b>Monitor</b><div class="muted" style="font-size:13px">Não foi possível ler a taxa do monitor neste sistema.</div></div></div></div>`;
    const low = disp.below_max;
    const rates = (d.rates || []).filter(r => r >= 50).slice(0, 6);
    return `<div class="card ${low ? 'glow' : ''}"><div class="spread"><div class="row" style="gap:16px;flex-wrap:nowrap">
      ${AZ.stateIcon(low ? 'todo' : 'ok')}
      <div><span class="eyebrow">Monitor · ${esc(disp.width)}×${esc(disp.height)}</span>
        <div class="row" style="margin-top:6px"><span class="big-num">${esc(disp.current_hz)} Hz</span><span class="muted">de ${esc(disp.max_hz)} Hz possíveis</span></div>
        <p style="margin-top:6px;font-size:13px">${low ? `Seu monitor aguenta ${esc(disp.max_hz)} Hz, mas está rodando a ${esc(disp.current_hz)} Hz. Você está jogando com menos quadros na tela do que pagou. Um clique resolve.`
          : 'Rodando na taxa máxima. Cada quadro que a placa gera aparece na tela.'}</p>
        <div class="meta" style="margin-top:8px">${AZ.tags(['+FPS NA TELA', '-DELAY'])}</div></div></div>
      ${low ? `<button class="btn primary lg" data-act="hz" data-hz="${esc(disp.max_hz)}">${icon('monitor')} Ligar ${esc(disp.max_hz)} Hz</button>` : ''}</div>
      ${rates.length > 1 ? `<div class="row" style="margin-top:14px"><span class="soft" style="font-size:12px">Trocar para:</span><div class="seg">${rates.map(r =>
        `<button class="${r === disp.current_hz ? 'active' : ''}" data-act="hz" data-hz="${r}">${r} Hz</button>`).join('')}</div></div>` : ''}</div>`;
  }

  function gpuCard(d) {
    const prefs = new Map(((d.gpu || {}).games || []).map(g => [String(g.exe).toLowerCase(), g]));
    const games = (d.installed || []).map(g => ({...g, pref: prefs.get(String(g.exe).toLowerCase())}));
    const on = games.filter(g => g.pref?.high_performance).length;
    return `${AZ.sectionTitle('gpu', 'Placa de vídeo forte em cada jogo', 'Em notebook (e PC com vídeo integrado + placa), o Windows às vezes abre o jogo na placa fraca. Isto obriga a usar a placa de vídeo dedicada.')}
      <div class="row" style="margin-bottom:10px"><span class="muted">${games.length} jogo(s) encontrado(s) · ${on} com placa forte</span>
        <button class="btn sm" data-act="addgame">${icon('folder')} Adicionar jogo (.exe)</button>
        ${games.length > on ? `<button class="btn sm primary" data-act="allgpu">${icon('bolt')} Ligar em todos</button>` : ''}</div>
      <div class="list">${games.map(g => `<div class="item ${g.pref?.high_performance ? '' : ''}">
        ${AZ.stateIcon(g.pref?.high_performance ? 'ok' : 'todo')}
        <div><div class="title">${esc(g.name)} <span class="pill">${esc(g.source || '')}</span></div>
          <div class="desc path" title="${esc(g.exe)}">${esc(g.exe)}</div></div>
        <div class="side-actions"><span class="soft" style="font-size:12px">${g.pref?.high_performance ? 'Placa forte' : 'Windows decide'}</span>
          ${AZ.toggle(!!g.pref?.high_performance, `data-act="gpu" data-exe="${esc(g.exe)}"`)}</div></div>`).join('')
        || '<div class="empty">Nenhum jogo encontrado nas pastas da Steam, Epic e Riot. Use "Adicionar jogo" e escolha o .exe do jogo.</div>'}</div>`;
  }

  function priorityCard(d) {
    const pr = d.priority || {};
    const on = !!pr.running;
    return `<div class="card tight"><div class="spread nw"><div class="row" style="flex-wrap:nowrap">${AZ.stateIcon(on ? 'ok' : 'todo')}
      <div><b>Prioridade automática do jogo</b> ${AZ.tags(['-STUTTER'])}
        <div class="muted" style="font-size:13px">Quando um jogo abre, o AZOR dá prioridade alta para ele no processador e baixa para o que roda atrás (Discord, navegador, launcher). ${pr.raised ? `Agora: ${esc(pr.raised)} jogo(s) acelerado(s).` : ''} Faz parte do Modo Turbo.</div></div></div>
      ${AZ.toggle(on, 'data-act="prio"')}</div></div>`;
  }

  function testStatusText(t) {
    const map = {idle: 'Parado', waiting: 'Esperando o jogo abrir…', capturing: 'Medindo…', finalizing: 'Montando o relatório…',
      completed: 'Pronto', cancelled: 'Cancelado', error: 'Erro'};
    return map[t.status] || t.status || 'Parado';
  }

  function comparisonView(c) {
    const rows = (c && c.rows) || [];
    const pick = ['FPS médio', '1% Low', 'Frametime médio', 'CPU média'];
    const shown = pick.map(k => rows.find(r => r.metric === k)).filter(Boolean);
    if (!shown.length) return '';
    return `<div class="compare" style="margin-top:14px">${shown.map(r => {
      const sign = r.delta > 0 ? '+' : '';
      const col = r.improved === true ? 'var(--good)' : r.improved === false ? 'var(--bad)' : 'var(--muted)';
      return `<div><small>${esc(r.metric.toUpperCase())}</small><b>${num(r.after, r.unit === 'fps' ? 0 : 1)}${r.unit === 'ms' ? ' ms' : r.unit === '%' ? '%' : ''}</b>
        <span style="color:${col}">${r.delta == null ? 'sem dado' : `${sign}${num(r.delta, 1)} ${r.unit === 'fps' ? 'FPS' : r.unit}`} vs antes</span></div>`;
    }).join('')}</div>`;
  }

  function testCard() {
    const t = S.test || {};
    const pm = t.presentmon || {};
    const running = !!t.running;
    const sum = t.summary || {};
    const f = sum.frames || {};
    return `${AZ.sectionTitle('fps', 'Teste de FPS antes e depois', 'Prova para o cliente: mede o jogo antes de otimizar e depois, e mostra a diferença. Sem overlay, sem mexer no jogo (não dá ban).')}
      ${AZ.how([['Meça o ANTES', 'Clique "Medir ANTES", abra o jogo e jogue 2 a 3 minutos numa partida normal.'],
                ['Otimize', 'Rode o BOOST, reinicie o PC se ele pedir.'],
                ['Meça o DEPOIS', 'Mesmo jogo, mesmo mapa, mesmo tempo. O AZOR compara os dois sozinho.']])}
      <div class="card">
        ${pm.available ? '' : `<div class="spread" style="margin-bottom:14px"><div class="row" style="flex-wrap:nowrap">${AZ.stateIcon('manual')}<div><b>Medidor de FPS não instalado</b>
          <div class="muted" style="font-size:13px">Sem ele o teste mede só CPU, placa e RAM. O AZOR baixa o PresentMon oficial (Intel, código aberto, ~1 MB).</div></div></div>
          <button class="btn sm" data-act="pmsetup">${icon('download')} Instalar medidor</button></div>`}
        <div class="grid g2">
          <label class="stack" style="gap:6px"><span class="soft" style="font-size:12px">Nome do cliente (vai no relatório)</span>
            <input class="input" data-input="customer" value="${esc(S.customer)}" maxlength="60" placeholder="Ex.: João — PC gamer" ${running ? 'disabled' : ''}></label>
          <label class="stack" style="gap:6px"><span class="soft" style="font-size:12px">Jogo (opcional, nome do .exe)</span>
            <input class="input" data-input="target" value="${esc(S.target)}" maxlength="80" placeholder="Em branco: o AZOR detecta sozinho" ${running ? 'disabled' : ''}></label>
        </div>
        <div class="spread" style="margin-top:16px"><div class="live-dot ${running ? 'on' : ''}"><i></i> ${esc(testStatusText(t))} ${t.game_name ? `· ${esc(t.game_name)}` : ''} ${running && t.samples ? `· ${t.samples} amostras` : ''}</div>
          <div class="row">${running ? `<button class="btn primary" data-act="tstop">${icon('stop')} Parar e gerar relatório</button>`
            : `<button class="btn" data-act="tstart" data-l="antes">${icon('play')} Medir ANTES</button><button class="btn primary" data-act="tstart" data-l="depois">${icon('play')} Medir DEPOIS</button>`}</div></div>
        ${t.status === 'completed' && !(t.comparison?.rows || []).length && (f.fps_avg != null || sum.cpu) ? `<div class="meters" style="margin-top:16px">
          <div class="meter"><small>FPS MÉDIO</small><b>${num(f.fps_avg)}</b><span>${esc(t.label || '')}</span></div>
          <div class="meter"><small>1% LOW</small><b>${num(f.fps_1_low)}</b><span>as travadas</span></div>
          <div class="meter"><small>FRAMETIME</small><b>${num(f.frametime_avg_ms, 1)} ms</b><span>menor = mais liso</span></div>
          <div class="meter"><small>CPU</small><b>${AZ.pct((sum.cpu || {}).avg_percent)}</b><span>uso médio</span></div></div>` : ''}
        ${comparisonView(t.comparison)}
        ${t.report_html ? `<div class="row" style="margin-top:12px"><button class="btn sm ghost" data-act="openrep" data-path="${esc(t.report_html)}">${icon('report')} Abrir relatório</button></div>` : ''}
      </div>
      ${reportsList()}`;
  }

  function reportsList() {
    const reps = (S.data?.reports || []).slice(0, 8);
    if (!reps.length) return '';
    return `<div class="spread" style="margin:14px 0 8px"><span class="eyebrow">Testes anteriores</span><button class="linkbtn" data-act="repfolder">Abrir pasta</button></div>
      <div class="list">${reps.map(r => `<div class="item">${AZ.stateIcon(r.label === 'depois' ? 'ok' : 'manual')}
        <div><div class="title">${esc(r.customer || 'Cliente')} <span class="pill ${r.label === 'depois' ? 'ok' : ''}"><i></i>${esc((r.label || '').toUpperCase())}</span></div>
          <div class="desc">${esc(r.started_at || '')} · FPS médio ${num(r.fps_avg)} · 1% low ${num(r.fps_1_low)}</div></div>
        <div class="side-actions"><button class="btn sm ghost" data-act="openrep" data-path="${esc(r.path)}\\Relatorio_AZOR.html">Abrir</button></div></div>`).join('')}</div>`;
  }

  function fortniteCard(d) {
    const f = d.fortnite || {};
    if (!f.installed && !f.config) return '';
    return `${AZ.sectionTitle('flame', 'Fortnite', 'Ajustes dentro do arquivo de configuração do jogo. Feche o Fortnite antes.')}
      <div class="grid g2">
        <div class="card"><b>Preset competitivo</b> ${AZ.tags(['+FPS', '-DELAY'])}
          <p style="margin-top:6px;font-size:13px">Sombras, efeitos, pós-processamento e vegetação no mínimo, V-Sync desligado. É o que os pros usam: inimigo mais visível e muito mais FPS. O AZOR guarda uma cópia do seu arquivo antes.</p>
          <div class="row" style="margin-top:12px"><button class="btn primary" data-act="fnpreset" ${f.config ? '' : 'disabled'}>${icon('bolt')} Aplicar preset</button>
            <button class="btn ghost" data-act="fnrestore">${icon('undo')} Voltar o meu</button></div>
          ${f.config ? '' : '<div class="desc warn" style="margin-top:8px">Abra o Fortnite uma vez para ele criar o arquivo de configuração.</div>'}</div>
        <div class="card"><b>Resolução 3D</b> ${AZ.tags(['+FPS'])}
          <p style="margin-top:6px;font-size:13px">Renderiza o jogo em menos pixels e estica para a tela. 100% = nítido. 75–85% = bem mais FPS em PC fraco, com imagem um pouco mais suave.</p>
          <div class="row" style="margin-top:12px"><div class="seg">${[100, 90, 85, 75, 67].map(p => `<button data-act="fnres" data-p="${p}">${p}%</button>`).join('')}</div></div></div>
      </div>`;
  }

  function paint() {
    const d = S.data;
    const body = AZ.$('#gmBody');
    if (!body) return;
    if (!d) { body.innerHTML = AZ.skeleton(5); return; }
    body.innerHTML = `${monitorCard(d)}${gpuCard(d)}<div style="margin-top:12px">${priorityCard(d)}</div>${testCard()}${fortniteCard(d)}`;
  }

  function paintTest() {
    // Repinta só o bloco do teste, sem perder o foco dos campos.
    if (document.activeElement && document.activeElement.matches('#gmBody .input')) return;
    paint();
  }

  async function load(force) {
    S.data = await AZ.get('/api/games' + (force ? '?force=1' : ''), 90000).catch(e => ({installed: [], gpu: {}, fortnite: {}, priority: {}, test: {}, reports: [], display: {}, rates: [], detail: e.message}));
    S.test = S.data.test || {};
    if (AZ.current?.id === 'games') paint();
    schedule();
  }

  function schedule() {
    clearTimeout(S.poll);
    if (AZ.current?.id !== 'games' || !S.test?.running) return;
    S.poll = setTimeout(async () => {
      try {
        const was = S.test.running;
        S.test = await AZ.get('/api/game-test');
        if (was && !S.test.running) { load(true); return; }
        paintTest();
      } catch (e) { /* tenta de novo */ }
      schedule();
    }, 2000);
  }

  AZ.page('games', {
    title: 'Jogos',
    sub: 'Monitor na taxa máxima, placa de vídeo certa em cada jogo e o teste de FPS que prova o resultado para o cliente.',
    async render(view) {
      view.innerHTML = '<div id="gmBody"></div>';
      if (!S.customer) {
        AZ.get('/api/settings').then(st => { if (!S.customer && st.customer_name) { S.customer = st.customer_name; paint(); } }).catch(() => {});
      }
      paint();
      load(false);
    },
    leave() { clearTimeout(S.poll); },
    actions: {
      hz: async el => {
        el.disabled = true;
        const r = await AZ.action('refresh_max', {hz: Number(el.dataset.hz)}).catch(e => ({ok: false, detail: e.message}));
        AZ.toast(r.detail, r.ok);
        if (r.display && S.data) S.data.display = r.display;
        paint();
      },
      gpu: async el => {
        const on = !el.classList.contains('on');
        el.disabled = true;
        const r = await AZ.action(on ? 'game_gpu_high' : 'game_gpu_restore', {exe: el.dataset.exe}).catch(e => ({ok: false, detail: e.message}));
        AZ.toast(r.detail || (on ? 'Placa forte ligada.' : 'Voltou para o padrão.'), r.ok);
        load(true);
      },
      allgpu: async el => {
        el.disabled = true;
        const r = await AZ.action('game_gpu_all').catch(e => ({ok: false, detail: e.message}));
        AZ.toast(r.detail, r.ok);
        load(true);
      },
      addgame: async () => {
        const r = await AZ.action('pick_game_exe').catch(e => ({ok: false, detail: e.message}));
        if (!r.ok || !r.exe) { if (r.detail) AZ.toast(r.detail, false); return; }
        const g = await AZ.action('game_gpu_high', {exe: r.exe});
        AZ.toast(g.detail, g.ok);
        load(true);
      },
      prio: async el => {
        const on = !el.classList.contains('on');
        const r = await AZ.action('priority', {enabled: on}).catch(e => ({ok: false, detail: e.message}));
        AZ.toast(r.detail, r.ok);
        load(true);
      },
      customer: el => { S.customer = el.value; },
      target: el => { S.target = el.value; },
      tstart: async el => {
        const label = el.dataset.l;
        if (S.customer) AZ.post('/api/settings', {customer_name: S.customer}).catch(() => {});
        const r = await AZ.action('game_test_start', {label, customer: S.customer, target: S.target}).catch(e => ({ok: false, detail: e.message}));
        AZ.toast(r.detail, r.ok);
        if (r.status) S.test = r.status;
        paint();
        schedule();
      },
      tstop: async el => {
        el.disabled = true;
        AZ.toast('Finalizando o relatório…');
        const r = await AZ.action('game_test_stop').catch(e => ({ok: false, detail: e.message}));
        AZ.toast(r.detail, r.ok);
        load(true);
      },
      pmsetup: async el => {
        el.disabled = true;
        el.textContent = 'Baixando…';
        const r = await AZ.action('game_test_setup').catch(e => ({ok: false, detail: e.message}));
        AZ.toast(r.detail || (r.ok ? 'Medidor pronto.' : 'Não foi possível instalar.'), r.ok);
        load(true);
      },
      openrep: async el => {
        const r = await AZ.action('open_report', {path: el.dataset.path});
        if (!r.ok) AZ.toast(r.detail, false);
      },
      repfolder: () => AZ.action('open_folder', {which: 'reports'}),
      fnpreset: async () => {
        const r = await AZ.action('fortnite_preset').catch(e => ({ok: false, detail: e.message}));
        AZ.toast(r.detail, r.ok);
      },
      fnrestore: async () => {
        const r = await AZ.action('fortnite_restore').catch(e => ({ok: false, detail: e.message}));
        AZ.toast(r.detail, r.ok);
      },
      fnres: async el => {
        const r = await AZ.action('fortnite_res', {percent: Number(el.dataset.p)}).catch(e => ({ok: false, detail: e.message}));
        AZ.toast(r.detail, r.ok);
        if (r.ok) { AZ.$$('[data-act="fnres"]').forEach(b => b.classList.toggle('active', b === el)); }
      },
    },
  });
})();
