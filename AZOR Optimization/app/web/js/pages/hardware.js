/* Hardware e BIOS: o que o PC tem, o que está segurando o desempenho e o passo a passo da BIOS. */
'use strict';
(() => {
  const {esc, icon} = AZ;
  const S = {tab: 'pc', hw: null, bios: null, fw: null};
  const DRIVER_LINKS = {
    nvidia: [['Driver NVIDIA oficial', 'https://www.nvidia.com/pt-br/drivers/'], ['NVIDIA App', 'https://www.nvidia.com/pt-br/software/nvidia-app/']],
    amd: [['Driver AMD oficial', 'https://www.amd.com/pt/support/download/drivers.html']],
    intel: [['Driver Intel oficial', 'https://www.intel.com.br/content/www/br/pt/download-center/home.html']],
  };

  function tabs() {
    const t = [['pc', 'hardware', 'Meu PC'], ['bios', 'cpu', 'BIOS'], ['drivers', 'gpu', 'Drivers'], ['disks', 'disk', 'Discos']];
    return `<div class="tabs">${t.map(([id, ic, l]) => `<button class="tab ${S.tab === id ? 'active' : ''}" data-act="tab" data-t="${id}">${icon(ic)} ${l}</button>`).join('')}</div>`;
  }

  /* ---------- meu PC ---------- */
  function pcView() {
    const h = S.hw;
    if (!h) return AZ.skeleton(5);
    const p = h.profile || {}, mem = h.memory || {}, th = h.thermal || {}, disp = h.display || {}, bios = (h.bios || {}).BIOS || {}, board = (h.bios || {}).BaseBoard || {};
    const issues = [];
    if (mem.single_channel) issues.push(['bad', 'Memória em canal único', `Só ${mem.sticks || 1} pente trabalhando sozinho. Dual channel (2 pentes, nos slots certos) dá até 20% mais FPS e muito menos travada em jogo pesado de processador (Valorant, CS2, Fortnite). Veja no manual da placa os slots certos (normalmente o 2º e o 4º).`, ['+FPS', '-STUTTER']]);
    if (mem.xmp_off) issues.push(['bad', 'Memória abaixo da velocidade', `Seus pentes aguentam ${mem.rated_mhz} MHz e estão rodando a ${mem.configured_mhz} MHz. Ligue o XMP/EXPO na BIOS (aba BIOS mostra o caminho exato).`, ['+FPS', '-STUTTER']]);
    if (disp.below_max) issues.push(['bad', 'Monitor abaixo da taxa máxima', `Rodando a ${disp.current_hz} Hz, mas aguenta ${disp.max_hz} Hz.`, ['+FPS NA TELA']]);
    if (th.cpu_temp_c >= 90) issues.push(['bad', 'Processador muito quente', `${Math.round(th.cpu_temp_c)} °C. Acima de 90 °C ele perde velocidade para se proteger (FPS cai sozinho no meio da partida). Limpe a poeira, troque a pasta térmica, revise o cooler.`, ['-STUTTER', 'CALOR']]);
    if ((th.throttle || {}).available && (th.throttle.reasons || []).length) issues.push(['warn', 'Processador segurando a velocidade', (th.throttle.reasons || []).map(r => typeof r === 'string' ? r : (r.text || r.reason || '')).join(' · '), ['-STUTTER']]);
    if (p.battery) issues.push(['manual', 'Notebook', 'Jogue sempre na tomada. Na bateria o Windows e a placa de vídeo cortam o desempenho pela metade.', ['+FPS']]);
    const spec = [
      ['Processador', p.cpu], ['Placa de vídeo', (p.gpus || []).join(' + ')],
      ['Memória', `${p.ram_gb ?? mem.total_gb ?? '—'} GB${mem.sticks ? ` · ${mem.sticks} pente(s)` : ''}${mem.configured_mhz ? ` · ${mem.configured_mhz} MHz` : ''}${mem.single_channel === false ? ' · dual channel' : mem.single_channel ? ' · canal único' : ''}`],
      ['Monitor', disp.ok ? `${disp.width}×${disp.height} · ${disp.current_hz} Hz (máx. ${disp.max_hz} Hz)` : '—'],
      ['Placa-mãe', [board.Manufacturer, board.Product].filter(Boolean).join(' ') || '—'],
      ['BIOS', [bios.SMBIOSBIOSVersion, bios.ReleaseDate ? `de ${String(bios.ReleaseDate).slice(0, 10)}` : ''].filter(Boolean).join(' ') || '—'],
      ['Núcleos', p.cores ? `${p.cores} núcleos / ${p.logical_processors} threads${p.topology?.hybrid ? ` (${p.topology.performance_cores}P + ${p.topology.efficiency_cores}E)` : ''}` : '—'],
    ];
    return `<div class="grid" style="grid-template-columns:minmax(0,1.2fr) minmax(0,1fr)">
      <div class="card glow pc-card"><span class="eyebrow">Este PC</span><div class="pc-type" style="margin-top:6px">${esc(p.label || 'PC')}</div>
        <div class="spec">${spec.map(([k, v]) => `<span>${k}</span><b>${esc(v || '—')}</b>`).join('')}</div></div>
      <div class="stack"><div class="meters" style="grid-template-columns:repeat(2,minmax(0,1fr))">
        <div class="meter"><small>CPU</small><b class="${th.cpu_temp_c >= 90 ? 'bad' : th.cpu_temp_c >= 80 ? 'warn' : ''}">${th.cpu_temp_c != null ? Math.round(th.cpu_temp_c) + ' °C' : '—'}</b><span>${th.cpu_temp_c != null ? esc(th.cpu_temp_source || '') : 'sensor não exposto pelo Windows'}</span></div>
        <div class="meter"><small>PLACA DE VÍDEO</small><b class="${th.gpu_temp_c >= 85 ? 'bad' : th.gpu_temp_c >= 78 ? 'warn' : ''}">${th.gpu_temp_c != null ? Math.round(th.gpu_temp_c) + ' °C' : '—'}</b><span>${esc(th.gpu_name || '')}</span></div>
        <div class="meter"><small>CLOCK CPU</small><b>${th.cpu_clock_mhz ? (th.cpu_clock_mhz / 1000).toFixed(2).replace('.', ',') + ' GHz' : '—'}</b><span>${th.cpu_clock_ratio ? `${Math.round(th.cpu_clock_ratio * 100)}% do máximo` : ''}</span></div>
        <div class="meter"><small>RAM</small><b>${p.ram_gb ?? '—'} GB</b><span>${p.ram_gb && p.ram_gb < 16 ? '16 GB é o mínimo para jogar hoje' : 'suficiente para jogar'}</span></div></div>
        <p class="soft" style="font-size:12px">Temperatura de processador só aparece se o Windows ou um monitor (LibreHardwareMonitor) expuser o sensor. O AZOR nunca inventa número.</p></div></div>
      ${AZ.sectionTitle('alert', issues.length ? 'O que está segurando este PC' : 'Nada segurando o hardware', issues.length ? 'Coisas que nenhum tweak resolve: dependem de peça, BIOS ou limpeza.' : 'Memória, monitor e temperatura dentro do esperado.')}
      <div class="list">${issues.map(([st, t, d, tags]) => `<div class="item">${AZ.stateIcon(st)}<div><div class="title">${esc(t)}</div><div class="desc">${esc(d)}</div><div class="meta">${AZ.tags(tags)}</div></div>
        <div class="side-actions">${t.startsWith('Memória abaixo') ? '<button class="btn sm" data-act="tab" data-t="bios">Ver na BIOS</button>' : t.startsWith('Monitor') ? '<button class="btn sm primary" data-act="hz">Corrigir</button>' : ''}</div></div>`).join('')
        || '<div class="empty">Hardware em ordem. O resto é com o BOOST e com a aba Jogos.</div>'}</div>`;
  }

  /* ---------- BIOS ---------- */
  function biosView() {
    const b = S.bios, fw = S.fw || {};
    if (!b) return AZ.skeleton(5);
    if (!b.supported) return `<div class="empty">${esc(b.reason || 'Não foi possível ler a placa-mãe.')}</div>`;
    const steps = b.steps || [];
    const todo = steps.filter(s => s.status === 'action').length;
    return `<div class="card glow"><div class="spread nw"><div><span class="eyebrow">${esc(b.vendor_label || 'Placa-mãe')} · ${esc([b.board?.manufacturer, b.board?.product].filter(Boolean).join(' '))}</span>
        <h2 style="margin-top:6px">${todo ? `${todo} ajuste(s) de BIOS para fazer` : 'BIOS sem pendências que o Windows consiga ver'}</h2>
        <p style="margin-top:6px;font-size:13px">A BIOS não é mexida por programa nenhum com segurança, então o AZOR mostra o caminho exato da sua placa e confere depois do reboot o que o Windows consegue reler.</p></div>
        <div class="stack" style="align-items:flex-end">${fw.uefi ? `<button class="btn primary" data-act="fwboot">${icon('power')} Reiniciar direto na BIOS</button>` : ''}
          <button class="btn sm ghost" data-act="fwcancel">Cancelar reinício</button></div></div>
      <div class="grid g2" style="margin-top:14px"><div class="card tight"><b>Como entrar</b><div class="muted" style="font-size:13px">${esc(b.enter)}</div></div>
        <div class="card tight"><b>Como salvar</b><div class="muted" style="font-size:13px">${esc(b.save)}</div></div></div></div>
      <div class="list">${steps.map(s => {
        const st = s.status === 'confirmed' ? 'ok' : s.status === 'action' ? 'todo' : 'manual';
        return `<div class="item ${s.status === 'confirmed' ? 'dim' : ''}">${AZ.stateIcon(st)}
          <div><div class="title">${esc(s.name)} ${s.status === 'confirmed' ? '<span class="pill ok"><i></i>Confirmado</span>' : s.status === 'action' ? '<span class="pill todo"><i></i>Fazer</span>' : '<span class="pill"><i></i>Confira</span>'}
            ${s.marked && s.status !== 'confirmed' ? '<span class="pill warn"><i></i>Marcado como feito</span>' : ''}</div>
            <div class="desc">${esc(s.detail)}</div>
            ${s.path ? `<div class="path" style="margin-top:8px">${esc(s.path)}</div>` : ''}
            <details><summary>Por que e qual o risco</summary><div class="tech"><div><b>Ganho:</b> ${esc(s.why)}</div>${s.risk ? `<div><b>Risco:</b> ${esc(s.risk)}</div>` : ''}</div></details></div>
          <div class="side-actions"><label class="row soft" style="font-size:12.5px;gap:8px"><input type="checkbox" class="check" data-change="biosmark" data-k="${esc(s.key)}" ${s.marked ? 'checked' : ''}> Já fiz</label></div></div>`;
      }).join('')}</div>
      <p class="soft" style="font-size:12px;margin-top:10px">${esc(b.accuracy_note || '')}</p>`;
  }

  /* ---------- drivers ---------- */
  function driversView() {
    const h = S.hw;
    if (!h) return AZ.skeleton(5);
    const g = h.driver_guide || {}, dr = h.drivers || {};
    const guide = g.guide;
    const links = DRIVER_LINKS[g.vendor] || [];
    const key = dr.key_drivers || [];
    return `${guide ? `<div class="card glow"><span class="eyebrow">Painel da placa de vídeo · ${esc(guide.label)}</span>
        <h2 style="margin-top:6px">O que ligar no painel do driver</h2>
        <p style="margin-top:6px;font-size:13px">Estas opções dão menos delay, mas ficam atrás do painel da ${esc(guide.label)} (sem API pública). Configure por jogo:</p>
        <div class="path" style="margin-top:10px">${esc(guide.panel)}</div>
        <div class="list" style="margin-top:12px">${guide.items.map(([k, v, why]) => `<div class="item"><span class="state-ico todo">${icon('delay')}</span>
          <div><div class="title">${esc(k)}: <span style="color:var(--accent2)">${esc(v)}</span></div><div class="desc">${esc(why)}</div></div><div></div></div>`).join('')}</div>
        <div class="row" style="margin-top:12px">${links.map(([l, u]) => `<button class="btn sm" data-act="link" data-url="${esc(u)}">${icon('download')} ${esc(l)}</button>`).join('')}</div></div>`
      : '<div class="empty">Placa de vídeo não identificada.</div>'}
      ${AZ.sectionTitle('gpu', 'Drivers que importam para jogo', 'Vídeo, rede e armazenamento, com a data que o Windows reporta.')}
      <div class="list">${key.map(d => {
        const old = (d.age_days || 0) > 540;
        return `<div class="item">${AZ.stateIcon(old ? 'todo' : 'ok')}<div><div class="title">${esc(d.name)} <span class="pill">${esc(d.cls)}</span></div>
          <div class="desc">Versão ${esc(d.version)} · ${esc(d.date || 'sem data')}${d.age_days != null ? ` · ${Math.round(d.age_days / 30)} meses` : ''} · ${esc(d.vendor)}</div>
          ${old ? '<div class="desc warn">Driver com mais de 1 ano e meio. Baixe o mais novo no site do fabricante.</div>' : ''}</div><div></div></div>`;
      }).join('') || `<div class="empty">${esc(dr.reason || 'Nenhum driver de fabricante listado.')}</div>`}</div>
      <p class="soft" style="font-size:12px;margin-top:10px">${esc(dr.note || '')}</p>`;
  }

  /* ---------- discos ---------- */
  function disksView() {
    const h = S.hw;
    if (!h) return AZ.skeleton(4);
    const s = h.storage || {};
    if (!s.supported) return `<div class="empty">${esc(s.reason || 'Leitura de discos indisponível.')}</div>`;
    const find = s.findings || [];
    return `${find.length ? `<div class="list" style="margin-bottom:12px">${find.map(f => `<div class="item">${AZ.stateIcon(f.level === 'bad' ? 'bad' : 'atencao')}<div><div class="desc" style="color:var(--text)">${esc(f.text)}</div></div><div></div></div>`).join('')}</div>` : ''}
      <div class="grid g2">${(s.disks || []).map(d => {
        const ssd = /ssd|nvme/i.test(`${d.Media} ${d.Bus}`);
        return `<div class="card"><div class="spread"><div class="row">${icon('disk')}<b>${esc(d.Name)}</b></div><span class="pill ${String(d.Health).toLowerCase() === 'healthy' ? 'ok' : 'bad'}"><i></i>${String(d.Health).toLowerCase() === 'healthy' ? 'Saudável' : esc(d.Health || '—')}</span></div>
          <div class="kv"><span>Tipo</span><b>${esc(d.Bus === 'NVMe' ? 'SSD NVMe' : ssd ? 'SSD' : d.Media === 'HDD' ? 'HD (mecânico)' : (d.Media || '—'))}</b></div>
          <div class="kv"><span>Tamanho</span><b>${esc(d.SizeGB)} GB</b></div>
          ${d.Wear != null ? `<div class="kv"><span>Desgaste</span><b>${esc(d.Wear)}%</b></div>` : ''}
          ${d.TempC ? `<div class="kv"><span>Temperatura</span><b class="${d.TempC >= 70 ? 'warn' : ''}">${esc(d.TempC)} °C</b></div>` : ''}
          ${d.PowerOnHours ? `<div class="kv"><span>Horas ligado</span><b>${esc(d.PowerOnHours)} h</b></div>` : ''}
          ${!ssd && d.Media === 'HDD' ? '<div class="desc warn" style="margin-top:8px">HD mecânico: jogo instalado aqui carrega devagar e trava ao abrir mapa. Coloque os jogos num SSD.</div>' : ''}</div>`;
      }).join('')}</div>
      ${AZ.sectionTitle('folder', 'Partições', 'Com menos de 10% livre o Windows e os jogos começam a travar.')}
      <div class="list">${(s.volumes || []).map(v => {
        const used = v.SizeGB ? 100 - (v.FreeGB / v.SizeGB * 100) : 0;
        const tone = used >= 90 ? 'bad' : used >= 80 ? 'warn' : 'good';
        return `<div class="item"><span class="state-ico ${tone === 'good' ? 'ok' : tone === 'warn' ? 'manual' : 'bad'}">${icon('disk')}</span>
          <div><div class="title">${esc(v.Letter)}: ${esc(v.Label || '')} <span class="pill">${esc(v.FS)}</span></div>
          <div class="bar ${tone}" style="height:8px;margin-top:8px;max-width:420px"><i style="width:${Math.round(used)}%"></i></div></div>
          <div class="side-actions"><b style="font:700 14px var(--font-display)">${esc(v.FreeGB)} GB livres</b></div></div>`;
      }).join('')}</div>
      <div class="card tight" style="margin-top:12px"><div class="row">${AZ.stateIcon(s.trim?.ntfs === false ? 'bad' : 'ok')}<div><b>TRIM do SSD</b>
        <div class="muted" style="font-size:13px">${s.trim?.ntfs === false ? 'Desligado: o SSD perde velocidade com o tempo. O BOOST religa.' : 'Ligado: o SSD mantém a velocidade de fábrica.'}</div></div></div></div>`;
  }

  function paint() {
    if (!AZ.$('#hwBody')) return;
    AZ.$('#hwTabs').innerHTML = tabs();
    AZ.$('#hwBody').innerHTML = S.tab === 'bios' ? biosView() : S.tab === 'drivers' ? driversView() : S.tab === 'disks' ? disksView() : pcView();
  }
  async function load(force) {
    S.hw = await AZ.get('/api/hardware' + (force ? '?force=1' : ''), 120000).catch(e => ({profile: {}, detail: e.message}));
    if (AZ.current?.id === 'hardware') paint();
  }
  async function loadBios() {
    [S.bios, S.fw] = await Promise.all([AZ.get('/api/bios', 60000).catch(e => ({supported: false, reason: e.message})), AZ.get('/api/firmware').catch(() => ({}))]);
    if (AZ.current?.id === 'hardware') paint();
  }

  AZ.page('hardware', {
    title: 'Hardware e BIOS',
    sub: 'O que este PC tem, o que está segurando o desempenho (memória, calor, disco) e o caminho exato na BIOS da sua placa.',
    async render(view, params) {
      if (params.tab) S.tab = params.tab;
      view.innerHTML = '<div id="hwTabs"></div><div id="hwBody"></div>';
      paint();
      load(false);
      loadBios();
    },
    actions: {
      tab: el => { S.tab = el.dataset.t; paint(); },
      link: async el => { const r = await AZ.action('open_link', {url: el.dataset.url}); AZ.toast(r.ok ? 'Abrindo no navegador…' : r.detail, r.ok); },
      hz: async el => { el.disabled = true; const r = await AZ.action('refresh_max'); AZ.toast(r.detail, r.ok); load(true); },
      biosmark: async el => {
        const r = await AZ.action('bios_check', {key: el.dataset.k, done: el.checked}).catch(e => ({ok: false, detail: e.message}));
        if (!r.ok) AZ.toast(r.detail, false);
        loadBios();
      },
      fwboot: async () => {
        if (!await AZ.confirm('Reiniciar na BIOS?', 'O PC reinicia em 15 segundos direto na tela da BIOS. Salve o que estiver aberto.', 'Reiniciar')) return;
        const r = await AZ.action('reboot_to_firmware', {delay: 15}).catch(e => ({ok: false, detail: e.message}));
        AZ.toast(r.detail, r.ok);
      },
      fwcancel: async () => { const r = await AZ.action('abort_reboot'); AZ.toast(r.detail, r.ok); },
    },
  });
})();
