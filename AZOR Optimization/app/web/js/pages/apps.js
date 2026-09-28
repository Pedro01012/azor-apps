/* Apps: remover o lixo que vem com o Windows, instalar e atualizar programas. */
'use strict';
(() => {
  const {esc, icon} = AZ;
  const S = {tab: 'remove', bloat: null, apps: null, rm: new Set(), inst: new Set(), showAll: false};

  function tabs() {
    const n = S.bloat ? S.bloat.recommended_count : '';
    return `<div class="tabs">
      <button class="tab ${S.tab === 'remove' ? 'active' : ''}" data-act="tab" data-t="remove">${icon('trash')} Remover inúteis ${n ? `<span class="count">${n}</span>` : ''}</button>
      <button class="tab ${S.tab === 'install' ? 'active' : ''}" data-act="tab" data-t="install">${icon('download')} Instalar programas</button>
      <button class="tab ${S.tab === 'update' ? 'active' : ''}" data-act="tab" data-t="update">${icon('refresh')} Atualizar tudo</button></div>`;
  }

  function removeView() {
    const b = S.bloat;
    if (!b) return AZ.skeleton(5);
    if (!b.ok) return `<div class="empty">${esc(b.detail || 'Não foi possível ler os apps.')}</div>`;
    const items = b.items.filter(i => i.installed || S.showAll);
    const rec = items.filter(i => i.recommended), opt = items.filter(i => !i.recommended);
    const card = i => `<div class="item ${S.rm.has(i.package) ? 'selected' : ''} ${i.installed ? '' : 'dim'}">
      <input type="checkbox" class="check" data-change="rm" data-p="${esc(i.package)}" ${S.rm.has(i.package) ? 'checked' : ''} ${i.installed ? '' : 'disabled'}>
      <div><div class="title">${esc(i.name)} ${i.recommended ? '<span class="tag leve">LIXO</span>' : '<span class="tag neutral">OPCIONAL</span>'} ${i.installed ? '' : '<span class="pill">Não instalado</span>'}</div>
      <div class="desc">${esc(i.desc)}</div></div>
      <div class="side-actions">${i.store ? `<button class="linkbtn" data-act="store" data-url="${esc(i.store)}">Loja</button>` : ''}</div></div>`;
    return `${AZ.how([['Os marcados são lixo', 'Apps de propaganda, notícias e IA que ficam ocupando RAM e disco.'],
                      ['Desmarque o que você usa', 'Os opcionais (Fotos, Teams, Paint…) vêm desmarcados.'],
                      ['Clique Remover', 'Qualquer app volta pela Microsoft Store quando quiser.']])}
      <div class="spread"><span class="muted">${b.installed_count} app(s) da lista instalados · ${b.recommended_count} são lixo</span>
        <label class="row soft" style="font-size:12.5px;gap:8px"><input type="checkbox" class="check" data-change="showall" ${S.showAll ? 'checked' : ''}> Mostrar os não instalados</label></div>
      ${AZ.sectionTitle('trash', 'Lixo de verdade', 'Ninguém sente falta. Entram no BOOST.')}
      <div class="list">${rec.map(card).join('') || '<div class="empty">Nenhum app inútil instalado. Windows limpo!</div>'}</div>
      ${opt.length ? AZ.sectionTitle('apps', 'Opcionais', 'Remova só se você não usa.') + `<div class="list">${opt.map(card).join('')}</div>` : ''}
      <div class="card tight" style="margin-top:14px"><div class="row">${AZ.stateIcon('manual')}<div><b>O que o AZOR nunca remove</b>
        <div class="muted" style="font-size:13px">Xbox Identity e Xbox TCUI (login nos jogos), Game Bar (o Fortnite chama o overlay dela), Gaming Services, Microsoft Store, instalador de apps (winget) e o Edge (o próprio Windows usa o motor dele). No lugar, o AZOR impede o Edge de rodar escondido.</div></div></div></div>`;
  }

  function installView() {
    const a = S.apps;
    if (!a) return AZ.skeleton(6);
    const warn = !a.winget ? `<div class="card tight"><div class="spread"><div class="row">${AZ.stateIcon('bad')}<div><b>O winget não está funcionando</b>
      <div class="muted" style="font-size:13px">${esc(a.detail)}</div></div></div><button class="btn" data-act="wingetfix">${icon('repair')} Reinstalar o winget</button></div></div>` : '';
    return `${warn}${AZ.how([['Marque os programas', 'Clique no cartão para marcar. Os já instalados aparecem com o selo.'],
                  ['Clique Instalar', 'Instala a versão oficial mais nova, em silêncio, um depois do outro.'],
                  ['Pode usar o PC', 'O AZOR avisa quando terminar e mostra o que deu certo.']])}
      ${a.categories.map(c => {
        const list = a.apps.filter(x => x.category === c.id);
        return `<div class="group-head"><span class="ico">${icon(c.id === 'kit' ? 'wand' : c.id === 'launchers' ? 'games' : c.id === 'chat' ? 'ping' : c.id === 'stream' ? 'play' : c.id === 'tools' ? 'hardware' : c.id === 'browsers' ? 'link' : 'apps')}</span>
          <div><h2>${esc(c.label)}</h2><p>${esc(c.hint)}</p></div>
          ${c.id === 'kit' ? '<div class="row"><button class="btn sm primary" data-act="kit">Instalar kit completo</button></div>' : ''}</div>
          <div class="app-grid">${list.map(x => `<div class="app ${S.inst.has(x.id) ? 'selected' : ''}" data-act="pickapp" data-id="${x.id}">
            <input type="checkbox" class="check" tabindex="-1" ${S.inst.has(x.id) ? 'checked' : ''}>
            <div><b>${esc(x.name)} ${x.installed ? '<span class="installed">INSTALADO</span>' : ''}</b><small>${esc(x.desc)}</small></div></div>`).join('')}</div>`;
      }).join('')}`;
  }

  function updateView() {
    const a = S.apps;
    return `<div class="card glow"><div class="spread"><div><span class="eyebrow">winget</span><h2 style="margin-top:6px">Atualizar todos os programas</h2>
      <p style="margin-top:6px">Driver de periférico, launcher, navegador, Discord, 7-Zip… tudo que o winget reconhece vai para a versão mais nova de uma vez.</p></div>
      <button class="btn primary lg" data-act="upgrade" ${a && !a.winget ? 'disabled' : ''}>${icon('refresh')} Atualizar tudo</button></div></div>
      <div class="card tight"><div class="spread"><div class="row">${AZ.stateIcon(a?.winget ? 'ok' : 'bad')}<div><b>Gerenciador de pacotes (winget)</b>
        <div class="muted" style="font-size:13px">${a ? (a.winget ? 'Funcionando.' : esc(a.detail)) : 'Verificando…'}</div></div></div>
        <button class="btn sm ghost" data-act="wingetfix">${icon('repair')} Reinstalar o winget</button></div></div>
      <div class="card tight"><div class="row">${AZ.stateIcon('manual')}<div><b>E o driver de vídeo?</b><div class="muted" style="font-size:13px">O winget não atualiza driver de vídeo. Veja em Hardware e BIOS &gt; Drivers o link oficial da sua placa, ou instale o NVCleanstall (aba Instalar).</div></div></div></div>`;
  }

  function paint() {
    const body = S.tab === 'remove' ? removeView() : S.tab === 'install' ? installView() : updateView();
    AZ.$('#appsTabs').innerHTML = tabs();
    AZ.$('#appsBody').innerHTML = body;
    paintBar();
  }

  function paintBar() {
    const bar = AZ.$('#appsBar');
    if (!bar) return;
    if (S.tab === 'remove' && S.rm.size) {
      bar.hidden = false;
      bar.innerHTML = `<div><b>${S.rm.size} app(s) para remover</b><br><span>Voltam pela Microsoft Store se precisar.</span></div>
        <div class="row"><button class="btn ghost" data-act="rmclear">Desmarcar</button><button class="btn primary" data-act="rmgo">${icon('trash')} Remover ${S.rm.size}</button></div>`;
    } else if (S.tab === 'install' && S.inst.size) {
      const installed = [...S.inst].filter(id => (S.apps.apps.find(a => a.id === id) || {}).installed);
      bar.hidden = false;
      bar.innerHTML = `<div><b>${S.inst.size} programa(s) selecionado(s)</b><br><span>${installed.length} já instalado(s)</span></div>
        <div class="row"><button class="btn ghost" data-act="instclear">Limpar</button>
        ${installed.length ? `<button class="btn danger" data-act="uninst">Desinstalar ${installed.length}</button>` : ''}
        <button class="btn primary" data-act="instgo">${icon('download')} Instalar ${S.inst.size - installed.length || S.inst.size}</button></div>`;
    } else bar.hidden = true;
  }

  async function loadBloat(force) {
    S.bloat = await AZ.get('/api/bloat' + (force ? '?force=1' : ''), 90000).catch(e => ({ok: false, detail: e.message}));
    if (S.bloat.ok && !S.rmTouched) {
      S.rm = new Set(S.bloat.items.filter(i => i.installed && i.recommended).map(i => i.package));
    }
    if (AZ.current?.id === 'apps') paint();
  }
  async function loadApps(force) {
    S.apps = await AZ.get('/api/apps' + (force ? '?force=1' : ''), 150000).catch(e => ({categories: [], apps: [], winget: false, detail: e.message}));
    if (AZ.current?.id === 'apps') paint();
  }

  AZ.page('apps', {
    title: 'Apps',
    sub: 'Tire o lixo que vem com o Windows e instale só o que você usa, na versão oficial mais nova.',
    async render(view, params) {
      if (params.tab) S.tab = params.tab;
      view.innerHTML = `<div id="appsTabs"></div><div id="appsBody"></div><div class="actionbar" id="appsBar" hidden></div>`;
      paint();
      loadBloat(false);
      loadApps(false);
    },
    actions: {
      tab: el => { S.tab = el.dataset.t; paint(); },
      rm: el => { S.rmTouched = true; el.checked ? S.rm.add(el.dataset.p) : S.rm.delete(el.dataset.p); el.closest('.item').classList.toggle('selected', el.checked); paintBar(); },
      showall: el => { S.showAll = el.checked; paint(); },
      rmclear: () => { S.rmTouched = true; S.rm.clear(); paint(); },
      rmgo: async () => {
        await AZ.runJob('appx_remove', {packages: [...S.rm]}, {title: 'Removendo apps inúteis'});
        S.rmTouched = false;
        loadBloat(true);
      },
      store: el => AZ.action('open_link', {url: el.dataset.url}),
      pickapp: el => {
        const id = el.dataset.id;
        S.inst.has(id) ? S.inst.delete(id) : S.inst.add(id);
        el.classList.toggle('selected', S.inst.has(id));
        el.querySelector('.check').checked = S.inst.has(id);
        paintBar();
      },
      kit: () => { S.apps.kit.forEach(id => S.inst.add(id)); paint(); AZ.toast('Kit marcado. Clique em Instalar.'); },
      instclear: () => { S.inst.clear(); paint(); },
      instgo: async () => {
        const ids = [...S.inst].filter(id => !(S.apps.apps.find(a => a.id === id) || {}).installed);
        await AZ.runJob('apps_install', {ids: ids.length ? ids : [...S.inst]}, {title: 'Instalando programas', subtitle: 'Cada programa baixa da fonte oficial. Pode levar alguns minutos.'});
        S.inst.clear();
        loadApps(true);
      },
      uninst: async () => {
        const ids = [...S.inst].filter(id => (S.apps.apps.find(a => a.id === id) || {}).installed);
        if (!await AZ.confirm('Desinstalar programas?', `${ids.length} programa(s) serão desinstalados.`, 'Desinstalar', true)) return;
        await AZ.runJob('apps_uninstall', {ids}, {title: 'Desinstalando'});
        S.inst.clear();
        loadApps(true);
      },
      upgrade: () => AZ.runJob('apps_upgrade', {}, {title: 'Atualizando todos os programas', subtitle: 'Pode levar vários minutos. Programas abertos podem fechar para atualizar.'}),
      wingetfix: async () => { await AZ.runJob('fix', {kind: 'winget'}, {title: 'Reinstalando o winget'}); loadApps(true); },
    },
  });
})();
