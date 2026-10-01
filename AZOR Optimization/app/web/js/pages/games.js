/* Jogos: monitor no máximo, placa de vídeo certa, teste de FPS antes/depois e Fortnite. */
'use strict';
(() => {
  const {esc, icon} = AZ;
  const S = {data: null, test: null, customer: '', target: '', poll: 0, cfg: null};

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

  /* Configuração ideal por jogo: o que muda FPS e delay DENTRO do jogo (o Windows já é com o BOOST). */
  const GAME_TIPS = [
    {id: 'cs2', name: 'Counter-Strike 2', match: ['counter-strike', 'cs2'], launch: '-novid -fullscreen +fps_max 0',
      tips: ['NVIDIA Reflex: Ligado + Boost', 'Aumentar contraste dos jogadores: Ligado', 'Sombras, texturas e partículas: Baixo', 'MSAA: 2x ou Nenhum; FidelityFX: Desligado', 'Modo de exibição: Tela cheia']},
    {id: 'valorant', name: 'Valorant', match: ['valorant'], launch: '',
      tips: ['NVIDIA Reflex: Ligado + Boost', 'Qualidade de material, textura e detalhe: Baixa', 'Anti-aliasing: MSAA 2x ou Nenhum', 'V-Sync desligado; limite de FPS desligado (ou 3x a taxa do monitor)', 'Buffer de entrada bruta (Raw Input Buffer): Ligado']},
    {id: 'fortnite', name: 'Fortnite', match: ['fortnite'], launch: '-d3d12 -FeatureLevelEs31',
      tips: ['Modo de renderização: Desempenho (o argumento acima liga)', 'Resolução 3D 100% (baixe para 85% em PC fraco)', 'Distância de visão: Média; resto no mínimo', 'NVIDIA Reflex: Ligado + Boost', 'Use o preset competitivo do AZOR abaixo']},
    {id: 'apex', name: 'Apex Legends', match: ['apex'], launch: '-novid +fps_max 0 -dev',
      tips: ['NVIDIA Reflex: Ligado + Boost', 'Orçamento de textura: metade da sua VRAM', 'Sombras do sol e dinâmicas: Desligado', 'Detalhe de modelo: Baixo; efeitos: Baixo', 'V-Sync desligado']},
    {id: 'cod', name: 'Call of Duty / Warzone', match: ['call of duty', 'warzone', 'cod'], launch: '',
      tips: ['Streaming de texturas sob demanda: Desligado (menos stutter, usa disco)', 'NVIDIA Reflex: Ligado + Boost', 'DLSS/FSR: Qualidade ou Equilibrado', 'Oclusão de ambiente e reflexos: Desligado', 'Profundidade de campo e desfoque de movimento: Desligado']},
    {id: 'lol', name: 'League of Legends', match: ['league of legends'], launch: '',
      tips: ['Modo de janela: Tela cheia', 'Taxa de quadros: Sem limite (ou 240)', 'Sombras: Desligado; efeitos: Médio', 'Aguardar sincronização vertical: Desligado', 'Anti-aliasing: Desligado']},
    {id: 'dota2', name: 'Dota 2', match: ['dota'], launch: '-novid',
      tips: ['API: Vulkan em Radeon, DirectX 11 em NVIDIA (teste as duas)', 'Qualidade de renderização: 100%', 'Sombras e efeitos de água: Desligado', 'Limite de FPS: igual ou acima da taxa do monitor']},
    {id: 'minecraft', name: 'Minecraft Java', match: ['minecraft'], launch: '-Xmx4G -Xms4G',
      tips: ['Instale Fabric + Sodium: 2x a 3x mais FPS', 'Memória: 4 GB no argumento acima (6 GB com shaders); nunca mais que metade da RAM', 'Distância de renderização: 8 a 12 chunks', 'Nuvens e partículas: Mínimo']},
    {id: 'roblox', name: 'Roblox', match: ['roblox'], launch: '',
      tips: ['Configurações > Taxa máxima de quadros: 240 (ou a do monitor)', 'Modo gráfico: Manual, qualidade 3 a 5', 'Feche o navegador: o Roblox usa bem um núcleo só']},
    {id: 'gta5', name: 'GTA V', match: ['gta'], launch: '',
      tips: ['MSAA e FXAA: Desligado', 'Grama: Normal (a mais pesada do jogo)', 'Distância estendida: 0; população: metade', 'Qualidade de pós-processamento: Normal', 'DirectX 11']},
    {id: 'freefire', name: 'Free Fire (emulador)', match: ['bluestacks', 'ldplayer', 'gameloop', 'free fire'], launch: '',
      tips: ['BIOS: virtualização (VT-x / SVM) LIGADA — sem ela o emulador roda muito lento', 'Emulador: 4 núcleos e 4 GB de RAM; 120 FPS e Alta taxa de quadros ligados', 'Renderização: DirectX em NVIDIA, Vulkan/OpenGL em Radeon (teste)', 'Placa de vídeo: Alto desempenho (Jogos > placa forte)']},
    {id: 'rocketleague', name: 'Rocket League', match: ['rocket league'], launch: '-nomovie',
      tips: ['Qualidade de renderização: Alto desempenho', 'V-Sync desligado; FPS sem limite', 'Detalhe de mundo: Desempenho', 'Efeitos pesados (dinâmicos): Desligado']},
    {id: 'overwatch', name: 'Overwatch 2', match: ['overwatch'], launch: '',
      tips: ['NVIDIA Reflex: Ligado + Boost', 'Escala de renderização: 100%', 'Qualidade de sombras e reflexos: Baixo', 'Limite de FPS: personalizado, acima da taxa do monitor']},
    {id: 'pubg', name: 'PUBG', match: ['pubg'], launch: '',
      tips: ['Anti-aliasing: Ultra (ajuda a ver inimigo) e o resto no Muito Baixo', 'Textura: Médio; visão a distância: Médio', 'Escala de tela: 100', 'NVIDIA Reflex: Ligado + Boost']},
  ];

  function tipsCard(d) {
    const names = (d.installed || []).map(g => String(g.name || '').toLowerCase()).join(' | ');
    const mine = GAME_TIPS.filter(g => g.match.some(m => names.includes(m)));
    const list = S.allTips ? GAME_TIPS : (mine.length ? mine : GAME_TIPS.slice(0, 6));
    return `${AZ.sectionTitle('games', 'Configuração ideal por jogo', mine.length ? `${mine.length} jogo(s) seu(s) com guia. O Windows já é com o BOOST; isto é o que muda FPS e delay dentro do jogo.` : 'O Windows já é com o BOOST; isto é o que muda FPS e delay dentro do jogo.')}
      <div class="grid g2">${list.map(g => `<div class="card tight"><div class="spread"><b>${esc(g.name)}</b>${mine.includes(g) ? '<span class="pill ok"><i></i>Instalado</span>' : ''}</div>
        <ul style="margin:8px 0 0;padding-left:18px;font-size:13px">${g.tips.map(t => `<li>${esc(t)}</li>`).join('')}</ul>
        ${g.launch ? `<div class="row" style="margin-top:10px;flex-wrap:nowrap"><code class="path" style="flex:1;padding:6px 10px">${esc(g.launch)}</code>
          <button class="btn sm" data-act="copy" data-t="${esc(g.launch)}">Copiar</button></div>
          <div class="soft" style="font-size:11.5px;margin-top:4px">Opções de inicialização: Steam/Epic > propriedades do jogo.</div>` : ''}</div>`).join('')}</div>
      <div class="row" style="margin-top:8px"><button class="linkbtn" data-act="alltips">${S.allTips ? 'Mostrar só os meus' : `Ver os ${GAME_TIPS.length} jogos`}</button></div>`;
  }

  /* Arquivo de configuração do próprio jogo: sombras, partículas, V-Sync. Só edita o que já existe. */
  function cfgCard() {
    const list = S.cfg?.games || [];
    if (!list.length) return '';
    return `${AZ.sectionTitle('wand', 'Ajustes dentro do jogo', 'O AZOR muda o arquivo de configuração do próprio jogo (sombras, partículas, V-Sync). Só mexe no que já existe, guarda uma cópia do seu e volta com um clique. Feche o jogo antes.')}
      <div class="grid g2">${list.map(g => `
        <div class="card"><div class="spread"><b>${esc(g.label)}</b>${g.applied ? '<span class="pill ok"><i></i>PRESET APLICADO</span>' : ''}</div>
          ${g.running ? `<div class="desc warn" style="margin-top:6px">${icon('alert')} O jogo está aberto. Feche para aplicar.</div>` : ''}
          ${g.pending ? `<div class="stack" style="gap:4px;margin-top:8px">${g.preview.slice(0, 6).map(c => `<div class="row" style="gap:8px;font-size:12.5px"><span class="mono soft">${esc(c.key.replace('setting.', ''))}</span><span class="muted">${esc(c.from)} → <b>${esc(c.to)}</b></span></div>`).join('')}
              ${g.pending > 6 ? `<div class="soft" style="font-size:12px">…e mais ${g.pending - 6}</div>` : ''}</div>`
            : `<p class="muted" style="margin-top:8px;font-size:13px">${g.applied ? 'O arquivo já está no preset.' : 'Nada a mudar: o arquivo já está assim.'}</p>`}
          <p class="soft" style="margin-top:8px;font-size:12.5px">${esc(g.tip)}</p>
          <div class="row" style="margin-top:12px;gap:8px"><button class="btn primary" data-act="cfgapply" data-game="${g.id}" data-level="fps" ${g.running || !g.pending ? 'disabled' : ''}>${icon('bolt')} FPS máximo</button>
            <button class="btn" data-act="cfgapply" data-game="${g.id}" data-level="equilibrado" ${g.running ? 'disabled' : ''}>Equilibrado</button>
            ${g.applied ? `<button class="btn ghost" data-act="cfgrestore" data-game="${g.id}" ${g.running ? 'disabled' : ''}>${icon('undo')} Voltar o meu</button>` : ''}</div></div>`).join('')}</div>`;
  }

  function paint() {
    const d = S.data;
    const body = AZ.$('#gmBody');
    if (!body) return;
    if (!d) { body.innerHTML = AZ.skeleton(5); return; }
    body.innerHTML = `${monitorCard(d)}${gpuCard(d)}<div style="margin-top:12px">${priorityCard(d)}</div>${testCard()}${tipsCard(d)}${cfgCard()}${fortniteCard(d)}`;
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
    loadCfg();
  }

  async function loadCfg() {
    S.cfg = await AZ.action('gamecfg_scan').catch(() => null);
    if (AZ.current?.id === 'games') paintTest();
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
      alltips: () => { S.allTips = !S.allTips; paint(); },
      cfgapply: async el => {
        el.disabled = true;
        const r = await AZ.action('gamecfg_apply', {game: el.dataset.game, level: el.dataset.level}).catch(e => ({ok: false, detail: e.message}));
        AZ.toast(r.detail, r.ok);
        loadCfg();
      },
      cfgrestore: async el => {
        el.disabled = true;
        const r = await AZ.action('gamecfg_restore', {game: el.dataset.game}).catch(e => ({ok: false, detail: e.message}));
        AZ.toast(r.detail, r.ok);
        loadCfg();
      },
      copy: async el => {
        try { await navigator.clipboard.writeText(el.dataset.t); AZ.toast('Copiado. Cole nas opções de inicialização do jogo.'); }
        catch (e) { AZ.toast('Selecione o texto e copie com Ctrl+C.', false); }
      },
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
