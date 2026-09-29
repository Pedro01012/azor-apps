/* Início: o BOOST, o PC e o que está rodando agora. */
'use strict';
(() => {
  const {esc, icon} = AZ;
  let monitorTimer = 0;
  let mode = 'auto';
  const MODE_NAME = {auto: 'AUTOMÁTICO', maximo: 'RECOMENDADO', agressivo: 'EXTREMO'};
  const DIM_ICON = {form: 'hardware', cpu: 'cpu', gpu: 'gpu', ram: 'ram', disk: 'disk', os: 'apps', net: 'ping'};

  const MODE_TEXT = {
    auto: '<b>Automático:</b> o AZOR reconhece processador, placa de vídeo, memória, disco e formato e aplica o pré-set mais forte que ESTE PC aguenta: base Extremo, sem o que esta peça não suporta, mais os extras que ela pede.',
    maximo: '<b>Recomendado:</b> tudo que dá FPS, tira delay e limpa o Windows, sem custo que você sinta. Ideal para qualquer PC e notebook.',
    agressivo: '<b>Extremo:</b> o Recomendado + timer global, tela cheia exclusiva, rede sem espera, NVMe sempre ativo e lançadores fora do boot. Mais calor e consumo; overlays podem sumir. Para PC só de jogo.',
  };

  function pcCard(o, plan) {
    const pc = o.pc || {};
    const gpu = (pc.gpus || []).join(' + ') || 'Não identificada';
    const topo = pc.topology || {};
    return `<div class="card pc-card">
      <div class="spread" style="align-items:flex-start">
        <div><span class="eyebrow">Seu PC</span><div class="pc-type" style="margin-top:6px">${esc(plan?.pc?.label || pc.label || 'Lendo…')}</div>
          <p style="margin-top:4px;font-size:13px">${plan ? `${plan.todo} coisa(s) para fazer · ${plan.done} em dia` : 'Montando o plano deste PC…'}</p></div>
        ${AZ.scoreRing(plan?.score ?? '…', plan?.grade || 'NOTA')}
      </div>
      <div class="spec">
        <span>Processador</span><b>${esc(pc.cpu || '—')}${topo.hybrid ? ` <span class="soft">(${topo.performance_cores}P + ${topo.efficiency_cores}E)</span>` : ''}</b>
        <span>Vídeo</span><b>${esc(gpu)}</b>
        <span>Memória</span><b>${pc.ram_gb ? `${String(pc.ram_gb).replace('.', ',')} GB` : '—'}</b>
        <span>Windows</span><b>${esc((o.windows || '').replace(/^Windows-(\d+).*$/, 'Windows $1') || '—')}</b>
      </div>
      <div class="row" style="margin-top:16px"><button class="btn" data-act="go" data-page="plan">${icon('plan')} Ver o plano deste PC</button></div>
    </div>`;
  }

  function lastBoostCard(o) {
    const lb = o.last_boost;
    if (!lb) return '';
    return `<div class="card tight"><div class="spread"><div class="row">${AZ.stateIcon('ok')}<div><b>Último BOOST ${AZ.ago(lb.time)}</b>
      <div class="muted" style="font-size:13px">${esc(lb.detail || '')}</div></div></div>
      ${lb.report_id ? `<button class="btn sm ghost" data-act="report" data-id="${esc(lb.report_id)}">${icon('report')} Ver resultado</button>` : ''}</div></div>`;
  }

  function turboCard(o) {
    const t = o.turbo || {};
    const bits = [
      ['Timer 0,5 ms', t.timer?.active, t.timer?.actual_ms ? `${t.timer.actual_ms} ms` : ''],
      ['Prioridade do jogo', t.priority?.active, t.priority?.raised ? `${t.priority.raised} jogo(s)` : ''],
      ['Memória em espera', t.memory?.active, t.memory?.cycles ? `${t.memory.cycles} limpeza(s)` : ''],
    ];
    return `<div class="card">
      <div class="spread"><div><span class="eyebrow">Modo Turbo</span><h3 style="margin-top:6px">Menos delay enquanto você joga</h3></div>
        ${AZ.toggle(t.enabled, 'data-act="turbo"')}</div>
      <p style="margin-top:6px;font-size:13px">O AZOR fica na bandeja e, com o jogo aberto, deixa o timer do Windows em 0,5 ms, sobe o jogo para prioridade alta e libera RAM só quando ela acaba. Inicia com o Windows.</p>
      <div class="stack" style="margin-top:12px">${bits.map(([n, on, extra]) => `<div class="spread" style="font-size:13px"><span class="row" style="gap:8px"><span class="live-dot ${on ? 'on' : ''}"><i></i></span>${n}</span><span class="${on ? 'good' : 'soft'}">${on ? (extra || 'ativo') : 'parado'}</span></div>`).join('')}</div>
    </div>`;
  }

  function meters(m) {
    const cpu = m.cpu || {}, gpu = m.gpu || {}, ram = m.ram || {}, disk = m.disk || {};
    const cell = (label, value, detail, pct, tone = '') => `<div class="meter"><small>${label}</small><b>${value}</b><span>${esc(detail)}</span>
      <div class="bar ${tone}"><i style="width:${AZ.clamp(Number(pct) || 0, 0, 100)}%"></i></div></div>`;
    const tone = v => v >= 90 ? 'bad' : v >= 75 ? 'warn' : '';
    return `<div class="meters" id="meters">
      ${cell('PROCESSADOR', AZ.pct(cpu.usage), cpu.temp_c ? `${Math.round(cpu.temp_c)} °C` : 'uso agora', cpu.usage, tone(cpu.usage))}
      ${cell('PLACA DE VÍDEO', gpu.usage != null ? AZ.pct(gpu.usage) : '—', gpu.temp_c ? `${Math.round(gpu.temp_c)} °C · ${gpu.name || ''}` : (gpu.name || 'leitura NVIDIA'), gpu.usage, tone(gpu.usage))}
      ${cell('MEMÓRIA RAM', AZ.pct(ram.percent), ram.used_gb ? `${ram.used_gb} de ${ram.total_gb} GB` : '—', ram.percent, tone(ram.percent))}
      ${cell('DISCO DO WINDOWS', AZ.pct(disk.percent), disk.total_gb ? `${disk.used_gb} de ${disk.total_gb} GB` : '—', disk.percent, tone(disk.percent))}
    </div>`;
  }

  async function pollMonitor() {
    clearTimeout(monitorTimer);
    if (AZ.current?.id !== 'home') return;
    try {
      const m = await AZ.get('/api/monitor', 8000);
      const el = AZ.$('#meters');
      if (el && !m.loading) el.outerHTML = meters(m);
    } catch (e) { /* segue */ }
    monitorTimer = setTimeout(pollMonitor, 2500);
  }

  function render(view) {
    const o = AZ.state.overview || {};
    mode = o.mode || 'auto';
    const plan = AZ.state.plan;
    view.innerHTML = `
      <div class="hero">
        <div class="card glow boost-card">
          <div class="boost-grid">
            <button class="boost-btn" id="boostBtn" data-act="boost" aria-label="Iniciar BOOST"><span class="ring"></span><span class="face"><b>BOOST</b><small>1 clique</small></span></button>
            <div class="boost-side">
              <span class="eyebrow">Otimização completa</span>
              <h2>Mais <em>FPS</em>, menos <em>delay</em>, Windows leve.</h2>
              <p>Um clique aplica os ajustes de desempenho, remove os apps inúteis, tira do boot o que pesa e limpa o disco. Tudo tem desfazer.</p>
              <div class="seg" role="tablist">
                <button data-act="mode" data-mode="auto" class="${mode === 'auto' ? 'active' : ''}">AUTOMÁTICO</button>
                <button data-act="mode" data-mode="maximo" class="${mode === 'maximo' ? 'active' : ''}">RECOMENDADO</button>
                <button data-act="mode" data-mode="agressivo" class="extreme ${mode === 'agressivo' ? 'active' : ''}">EXTREMO</button>
              </div>
              <div class="mode-desc" id="modeDesc">${MODE_TEXT[mode]}</div>
              <div class="boost-does">
                <div>${icon('fps')} Ajustes de FPS e delay</div><div>${icon('trash')} Remove apps inúteis</div>
                <div>${icon('power')} Limpa a inicialização</div><div>${icon('cleanup')} Limpa arquivos inúteis</div>
                <div>${icon('cpu')} Fecha processos à toa</div><div>${icon('wand')} Pré-set do seu hardware</div>
              </div>
            </div>
          </div>
        </div>
        ${pcCard(o, plan)}
      </div>
      <div id="presetCard">${presetCard(AZ.state.preset)}</div>
      <div id="metersWrap">${meters({})}</div>
      <div class="grid g2">${turboCard(o)}<div class="stack">${lastBoostCard(o)}
        <div class="card tight"><div class="spread"><div class="row">${AZ.stateIcon('manual')}<div><b>Antes de tudo</b><div class="muted" style="font-size:13px">O BOOST cria um ponto de restauração do Windows e guarda o estado de cada ajuste. Reparar &gt; Desfazer tudo volta o PC a como estava.</div></div></div></div></div>
        ${o.pc?.battery ? `<div class="card tight"><div class="row">${AZ.stateIcon('manual')}<div><b>Notebook detectado</b><div class="muted" style="font-size:13px">Jogue na tomada. Na bateria o Windows corta o desempenho, com ou sem otimização.</div></div></div></div>` : ''}
      </div></div>`;
    pollMonitor();
  }

  function presetCard(p) {
    if (!p) return `<div class="card tight">${AZ.skeleton(1)}</div>`;
    if (!p.ok) return '';
    const m = p.memory || {};
    const actions = (p.notes || []).filter(n => n.level === 'action').length;
    return `<div class="card"><div class="spread nw"><div><span class="eyebrow">Pré-set deste PC ${m.known ? '· reconhecido da memória do AZOR' : '· PC novo'}</span>
        <h3 style="margin-top:6px">${esc(p.name)}</h3></div>
        <button class="btn sm" data-act="preset">${icon('wand')} Ver o que muda</button></div>
      <div class="row" style="margin-top:12px;gap:8px">${(p.chips || []).filter(c => c.label).map(c => `<span class="pill" title="${esc(c.detail)}">${icon(DIM_ICON[c.dim] || 'info')} ${esc(c.label)}</span>`).join('')}</div>
      <div class="row soft" style="margin-top:10px;font-size:12.5px;gap:16px">
        <span>${icon('bolt', 'good')} ${Object.keys(p.add || {}).length} ajuste(s) a mais para este hardware</span>
        <span>${icon('shield', 'good')} ${Object.keys(p.skip || {}).length} protegido(s) (esta peça piora com eles)</span>
        ${actions ? `<span class="warn">${icon('alert')} ${actions} coisa(s) para você fazer (BIOS/peça)</span>` : ''}
        ${m.applied_count ? `<span>${icon('clock')} BOOST aplicado ${m.applied_count}× neste PC</span>` : ''}
        <span>${icon('star')} biblioteca: ${Number((p.library || {}).combinations || 0).toLocaleString('pt-BR')} combinações</span></div></div>`;
  }

  function presetModal(p) {
    const row = (ic, cls, title, text) => `<div class="row" style="flex-wrap:nowrap;align-items:flex-start;gap:10px;margin-top:8px">
      <span class="state-ico ${cls}">${icon(ic)}</span><div><b style="font-size:13.5px">${esc(title)}</b><div class="muted" style="font-size:12.5px">${esc(text)}</div></div></div>`;
    const names = AZ.state.taskNames || {};
    AZ.modal(`<h2>Pré-set: ${esc(p.name)}</h2>
      <p>O AZOR encaixou cada peça numa família e juntou as regras. Chave: <code>${esc(p.key)}</code></p>
      ${Object.keys(p.add || {}).length ? `<h3 style="margin-top:14px">Liga a mais neste PC</h3>${Object.entries(p.add).map(([id, why]) => row('bolt', 'ok', names[id] || id, why)).join('')}` : ''}
      ${Object.keys(p.skip || {}).length ? `<h3 style="margin-top:14px">Não mexe neste PC (piora com esta peça)</h3>${Object.entries(p.skip).map(([id, why]) => row('shield', 'manual', names[id] || id, why)).join('')}` : ''}
      ${(p.notes || []).length ? `<h3 style="margin-top:14px">O que depende de você</h3>${p.notes.map(n => row(n.level === 'action' ? 'alert' : 'info', n.level === 'action' ? 'todo' : 'manual', n.title, n.text)).join('')}` : ''}
      <h3 style="margin-top:14px">Regras usadas</h3><div class="soft" style="font-size:12.5px">${(p.rules || []).map(esc).join(' · ')}</div>
      <div class="foot"><button class="btn primary" data-close>Fechar</button></div>`, {wide: true});
  }

  async function loadPreset() {
    try {
      AZ.state.preset = await AZ.get('/api/preset', 90000);
      const el = AZ.$('#presetCard');
      if (el && AZ.current?.id === 'home') el.innerHTML = presetCard(AZ.state.preset);
      if (!AZ.state.taskNames) {
        AZ.get('/api/tweaks').then(t => { AZ.state.taskNames = Object.fromEntries((t.tasks || []).map(x => [x.id, x.title || x.name])); }).catch(() => {});
      }
    } catch (e) { const el = AZ.$('#presetCard'); if (el) el.innerHTML = ''; }
  }

  async function loadPlan() {
    try {
      AZ.state.plan = await AZ.get('/api/plan', 120000);
      if (AZ.current?.id === 'home') {
        const card = AZ.$('.pc-card');
        if (card) card.outerHTML = pcCard(AZ.state.overview || {}, AZ.state.plan);
      }
      AZ.refreshOverview();
    } catch (e) { /* segue sem o plano */ }
  }

  function boostResult(r) {
    const t = r.tweaks || {};
    const b = r.before || {}, a = r.after || {};
    const dProc = (b.processes != null && a.processes != null) ? a.processes - b.processes : null;
    const dRam = (b.ram_used_mb != null && a.ram_used_mb != null) ? a.ram_used_mb - b.ram_used_mb : null;
    const fails = t.failed_items || [];
    return `<div class="result-hero"><b>PC OTIMIZADO</b><span>Modo ${esc(r.mode_label || '')} · ${esc(r.detail || '')}</span></div>
      <div class="compare" style="margin-top:14px">
        <div><small>AJUSTES APLICADOS</small><b>${(t.changed || 0) + (t.already || 0)}</b><span>${t.changed || 0} novos agora</span></div>
        <div><small>APPS REMOVIDOS</small><b>${r.apps?.removed || 0}</b><span>${(r.startup?.disabled || []).length} fora do boot</span></div>
        <div><small>ESPAÇO LIBERADO</small><b>${AZ.mb(r.cleanup?.freed_mb || 0)}</b><span>lixo apagado</span></div>
        <div><small>PROCESSOS</small><b>${a.processes ?? '—'}</b><span>${dProc != null ? `${dProc <= 0 ? '' : '+'}${dProc} vs antes` : ''}${dRam != null ? ` · RAM ${dRam <= 0 ? '' : '+'}${Math.round(dRam)} MB` : ''}</span></div>
      </div>
      ${t.restart ? `<p class="warn" style="margin-top:14px">${icon('alert')} Parte dos ajustes (timer, HAGS, núcleo na RAM) só vale depois de reiniciar o PC.</p>` : ''}
      ${fails.length ? `<details style="margin-top:12px"><summary class="muted">${fails.length} ajuste(s) não aplicado(s) — ver motivo</summary><div class="stack" style="margin-top:8px">${fails.map(f => `<div><b>${esc(f.name)}</b><div class="muted" style="font-size:12.5px">${esc(f.detail)}</div></div>`).join('')}</div></details>` : ''}`;
  }

  async function startBoost() {
    const o = AZ.state.overview || {};
    const pr = AZ.state.preset;
    const plan = AZ.state.plan;
    const step = id => (plan?.steps || []).find(s => s.id === id);
    const desktop = !o.pc?.battery;
    const opts = [
      ['debloat', 'Remover apps inúteis', step('bloat')?.detail || 'Notícias, Clima, Candy Crush, Copilot e afins. Voltam pela Microsoft Store.', true],
      ['startup', 'Tirar programas inúteis do boot', mode !== 'maximo' ? 'Inúteis, outros otimizadores e lançadores (Steam, Epic, Discord abrem quando você quiser).' : (step('startup')?.detail || 'Atualizadores, Edge, Teams e afins.'), true],
      ['processes', 'Fechar processos inúteis agora', 'Widgets, Vincular ao Celular, OneDrive, atualizadores do Google/Adobe/Java… Liberam RAM na hora.', true],
      ['cleanup', 'Limpar arquivos inúteis', step('junk')?.detail || 'Temporários, cache do Windows Update, sobras de driver.', true],
      ['keep_on_logon', 'Manter otimizado a cada login', 'O Windows Update desfaz ajustes; o AZOR confere e reaplica 45 s depois de entrar.', true],
      ['turbo', 'Ligar o Modo Turbo', 'Timer 0,5 ms + jogo acima de todos os outros apps + memória. O AZOR fica na bandeja.', pr?.ok ? !!pr.turbo : desktop],
    ];
    const m = AZ.modal(`<h2>BOOST ${MODE_NAME[mode] || 'AUTOMÁTICO'}</h2>
      <p>${MODE_TEXT[mode] || MODE_TEXT.auto}</p>
      ${pr && pr.ok ? `<div class="card tight" style="margin:10px 0"><div class="row" style="flex-wrap:nowrap">${icon('wand', 'good')}<div><b>Pré-set: ${esc(pr.name)}</b>
        <div class="muted" style="font-size:12.5px">${mode === 'auto' ? `${Object.keys(pr.add || {}).length} ajuste(s) a mais e ` : ''}${Object.keys(pr.skip || {}).length} protegido(s) para este hardware.</div></div></div></div>` : ''}
      ${opts.map(([k, t, d, on]) => `<label class="opt"><input type="checkbox" class="check" data-opt="${k}" ${on ? 'checked' : ''}><div><b>${t}</b><span>${esc(d)}</span></div></label>`).join('')}
      <div class="foot"><button class="btn ghost" data-close>Cancelar</button><button class="btn primary lg" data-go>${icon('bolt')} INICIAR BOOST</button></div>`);
    m.el.querySelector('[data-go]').addEventListener('click', async () => {
      const options = {};
      m.el.querySelectorAll('[data-opt]').forEach(c => { options[c.dataset.opt] = c.checked; });
      m.close();
      const btn = AZ.$('#boostBtn');
      if (btn) { btn.classList.add('running'); btn.disabled = true; }
      await AZ.runJob('boost', {mode, options}, {title: 'BOOST em andamento', doneTitle: 'BOOST concluído!', renderResult: boostResult});
      AZ.state.plan = null;
      if (AZ.current?.id === 'home') { AZ.reload(); loadPlan(); }
    });
  }

  AZ.page('home', {
    title: 'Início',
    sub: 'Aperte BOOST para deixar este PC no máximo. Quer ver antes o que vai mudar? Abra o Diagnóstico.',
    startBoost,
    boostResult,
    async render(view) {
      await AZ.refreshOverview();
      render(view);
      if (!AZ.state.plan) loadPlan();
      loadPreset();
    },
    leave() { clearTimeout(monitorTimer); },
    actions: {
      boost: () => startBoost(),
      mode: async el => {
        mode = el.dataset.mode;
        AZ.$$('.seg button').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
        AZ.$('#modeDesc').innerHTML = MODE_TEXT[mode];
        await AZ.post('/api/settings', {performance_mode: mode});
        AZ.refreshOverview();
        AZ.state.preset = null;
        loadPreset();
      },
      preset: () => { if (AZ.state.preset?.ok) presetModal(AZ.state.preset); },
      turbo: async el => {
        const on = !el.classList.contains('on');
        el.disabled = true;
        const r = await AZ.action('turbo', {enabled: on}).catch(e => ({ok: false, detail: e.message}));
        AZ.toast(on ? (r.ok ? 'Modo Turbo ligado.' : 'Parte do Turbo não ligou: ' + ((r.results || []).filter(x => !x.ok).map(x => x.name).join(', ') || r.detail)) : 'Modo Turbo desligado.', r.ok !== false);
        await AZ.refreshOverview();
        AZ.reload();
      },
      report: async el => {
        const r = await AZ.get(`/api/reports/${el.dataset.id}`);
        AZ.modal(`<h2>Resultado do BOOST</h2>${boostResult(r)}<div class="foot"><button class="btn primary" data-close>Fechar</button></div>`, {wide: true});
      },
    },
  });
})();
