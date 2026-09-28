/* Ajustes do próprio AZOR: atendimento, como ele roda, interface e sobre. */
'use strict';
(() => {
  const {esc, icon} = AZ;
  const S = {st: null};

  const row = (title, desc, control, tags = '') => `<div class="item"><span></span><div><div class="title">${title} ${tags}</div><div class="desc">${desc}</div></div>
    <div class="side-actions">${control}</div></div>`;

  function view() {
    const st = S.st, o = AZ.state.overview || {};
    if (!st) return AZ.skeleton(5);
    const logon = o.logon || {};
    return `${AZ.sectionTitle('report', 'Atendimento', 'Para quem otimiza PC de cliente: o nome vai no teste de FPS e no relatório.')}
      <div class="card"><div class="grid" style="grid-template-columns:minmax(0,1fr) auto;align-items:end">
        <label class="stack" style="gap:6px"><span class="soft" style="font-size:12px">Nome do cliente</span>
          <input class="input" data-change="customer" value="${esc(st.customer_name || '')}" maxlength="60" placeholder="Ex.: João — PC gamer"></label>
        <div class="row"><button class="btn" data-act="newclient">${icon('star')} Novo cliente</button>
          <button class="btn primary" data-act="report">${icon('report')} Gerar relatório</button></div></div>
        <p class="soft" style="font-size:12.5px;margin-top:10px">O relatório mostra a nota antes e depois, o que o BOOST fez, os ajustes ativos, o teste de FPS e o que ainda depende de BIOS ou peça. "Novo cliente" faz a nota atual virar o "antes".
          <button class="linkbtn" data-act="clientsdir">Abrir pasta dos relatórios</button></p></div>

      ${AZ.sectionTitle('power', 'Como o AZOR roda', '')}
      <div class="list">
        ${row('Manter otimizado a cada login', 'Alguns ajustes o Windows desfaz sozinho em atualizações. Com isto ligado, o AZOR confere e reaplica em silêncio quando você entra no Windows (tarefa agendada, sem janela).',
          AZ.toggle(!!logon.enabled, 'data-act="logon"'), AZ.tags(['ESTÁVEL']))}
        ${logon.stale ? `<div class="desc warn" style="padding:0 16px 8px">${icon('alert')} O login usa a cópia de outra versão. Rode o BOOST uma vez para atualizar.</div>` : ''}
        ${row('Abrir com o Windows', 'Necessário para o Modo Turbo (timer 0,5 ms, prioridade do jogo e memória) ficar ativo. O AZOR fica quietinho na bandeja, perto do relógio.',
          AZ.toggle(!!st.start_with_windows, 'data-act="set" data-k="start_with_windows"'))}
        ${row('Abrir minimizado', 'Quando abrir junto com o Windows, vai direto para a bandeja sem mostrar a janela.',
          AZ.toggle(!!st.start_minimized, 'data-act="set" data-k="start_minimized"'))}
        ${row('Faço live / gravo gameplay', 'Mantém o que OBS, Discord e o overlay precisam: não força tela cheia exclusiva e deixa folga de CPU para o encoder. Custa um pouquinho de FPS em troca de uma live sem travar.',
          AZ.toggle(!!st.streamer, 'data-act="set" data-k="streamer"'), AZ.tags(['STREAMER']))}
      </div>

      ${AZ.sectionTitle('visual', 'Interface', '')}
      <div class="list">
        ${row('Modo técnico', 'Mostra em cada tweak a fonte, a chave do registro, como medir o ganho e o custo técnico.',
          AZ.toggle(!!st.technician, 'data-act="set" data-k="technician"'))}
        ${row('Menos animação', 'Desliga transições e efeitos da interface. Bom para PC muito fraco ou acesso remoto.',
          AZ.toggle(!!st.reduce_motion, 'data-act="set" data-k="reduce_motion"'))}
      </div>

      ${AZ.sectionTitle('info', 'Sobre', '')}
      <div class="grid g2">
        <div class="card"><div class="row"><img src="assets/Azor_icon.png" alt="" style="width:44px;height:44px;border-radius:12px">
          <div><b style="font:800 18px var(--font-display);letter-spacing:.08em">AZOR OPTIMIZATION</b><div class="soft" style="font-size:12.5px">Versão ${esc(o.version || '')} · ${esc(o.build || '')}</div></div></div>
          <div class="kv" style="margin-top:10px"><span>Windows</span><b style="font-size:12.5px">${esc((o.windows || '—').replace(/^Windows-(\d+)-10\.0\.(\d+).*$/, 'Windows $1 · build $2'))}</b></div>
          <div class="kv"><span>Permissão</span><b>${o.admin ? 'Administrador' : 'Usuário comum'}</b></div>
          <div class="row" style="margin-top:12px"><button class="btn sm" data-act="logs">${icon('report')} Ver registro (log)</button>
            <button class="btn sm ghost" data-act="datadir">${icon('folder')} Pasta de dados</button></div></div>
        <div class="card"><b>Créditos</b><p style="font-size:13px;margin-top:6px">O catálogo de tweaks e a lista de apps juntam o motor do AZOR Obsidian com o melhor do
          <b>WinUtil</b> de Chris Titus Tech (licença MIT), reescritos com leitura antes/depois, desfazer exato e explicação em linguagem de jogador.</p>
          <p class="soft" style="font-size:12.5px;margin-top:8px">O AZOR nunca instala nada escondido, não coleta dados e não mexe na BIOS sozinho.</p></div></div>`;
  }

  function paint() {
    const el = AZ.$('#stBody');
    if (el) el.innerHTML = view();
  }
  async function load() {
    S.st = await AZ.get('/api/settings').catch(() => ({}));
    await AZ.refreshOverview();
    if (AZ.current?.id === 'settings') paint();
  }
  async function save(patch) {
    const r = await AZ.post('/api/settings', patch).catch(e => ({ok: false, error: e.message}));
    if (!r.ok) { AZ.toast(r.error || 'Não foi possível salvar.', false); return; }
    S.st = r.settings;
    document.body.classList.toggle('reduce-motion', !!S.st.reduce_motion);
    AZ.toast('Salvo.');
    await AZ.refreshOverview();
    paint();
  }

  AZ.page('settings', {
    title: 'Ajustes',
    sub: 'Atendimento de cliente, como o AZOR roda no Windows e informações do app.',
    async render(view) {
      view.innerHTML = '<div id="stBody"></div>';
      paint();
      load();
    },
    actions: {
      set: el => save({[el.dataset.k]: !el.classList.contains('on')}),
      customer: el => save({customer_name: el.value.trim()}),
      newclient: async () => {
        const name = AZ.$('#stBody .input')?.value.trim() || '';
        if (!await AZ.confirm('Começar um novo cliente?', 'A nota atual do diagnóstico passa a ser o "antes" do próximo relatório.', 'Começar')) return;
        const r = await AZ.action('new_customer', {customer: name});
        AZ.toast(r.detail, r.ok);
        load();
      },
      report: async el => {
        el.disabled = true;
        AZ.toast('Montando o relatório…');
        const r = await AZ.action('export_report').catch(e => ({ok: false, detail: e.message}));
        AZ.toast(r.detail, r.ok);
        el.disabled = false;
      },
      clientsdir: () => AZ.action('open_folder', {which: 'clients'}),
      datadir: () => AZ.action('open_folder', {which: 'data'}),
      logon: async el => {
        const on = !el.classList.contains('on');
        await AZ.runJob('logon_autoapply', {enabled: on, profile: AZ.state.overview?.mode || 'maximo'},
          {title: on ? 'Ligando a reaplicação no login' : 'Desligando a reaplicação no login'});
        load();
      },
      logs: async () => {
        const r = await AZ.get('/api/logs').catch(e => ({text: e.message}));
        AZ.modal(`<h2>Registro do AZOR</h2><p class="soft" style="font-size:12.5px">As últimas linhas. Útil para mandar para o suporte.</p>
          <pre style="max-height:52vh;overflow:auto;padding:12px;border-radius:10px;background:var(--bg2);border:1px solid var(--line);font:12px/1.5 var(--font-mono);white-space:pre-wrap">${esc(r.text || '(vazio)')}</pre>`, {wide: true});
      },
    },
  });
})();
