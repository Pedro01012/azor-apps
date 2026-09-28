/* AZOR — menu, barra de status e inicialização. */
'use strict';
(() => {
  const NAV = [
    ['home', 'Início', 'home'],
    ['plan', 'Diagnóstico', 'plan'],
    ['tweaks', 'Tweaks', 'tweaks'],
    ['apps', 'Apps', 'apps'],
    ['cleanup', 'Limpeza', 'cleanup'],
    ['games', 'Jogos', 'games'],
    ['periph', 'Periféricos', 'periph'],
    ['hardware', 'Hardware e BIOS', 'hardware'],
    ['repair', 'Reparar', 'repair'],
    null,
    ['settings', 'Ajustes', 'settings'],
  ];

  function renderNav() {
    AZ.$('#nav').innerHTML = NAV.map(n => n ? `<button class="nav-btn" data-page="${n[0]}" title="${n[1]}">${AZ.icon(n[2])}<span class="label">${n[1]}</span><span class="count" data-count="${n[0]}" hidden></span></button>`
      : '<div class="nav-sep"></div>').join('');
    AZ.$('#nav').addEventListener('click', e => {
      const b = e.target.closest('.nav-btn');
      if (b) AZ.go(b.dataset.page);
    });
  }

  AZ.paintChrome = () => {
    const o = AZ.state.overview || {};
    const turbo = o.turbo || {};
    AZ.$('#sideFoot').innerHTML = `
      <div class="status-line"><i class="${o.admin ? 'on' : 'warn'}"></i><span>${o.admin ? 'Administrador: tudo liberado' : 'Sem administrador: o Windows vai pedir permissão'}</span></div>
      <div class="status-line"><i class="${turbo.enabled ? 'hot' : ''}"></i><span>Modo Turbo ${turbo.enabled ? 'ligado' : 'desligado'}</span></div>
      <div class="status-line"><i class="${o.logon?.enabled ? 'on' : ''}"></i><span>${o.logon?.enabled ? 'Mantido a cada login' : 'Sem reaplicação no login'}</span></div>`;
    const mode = o.mode === 'agressivo' ? 'EXTREMO' : 'RECOMENDADO';
    AZ.$('#topRight').innerHTML = `
      ${o.pending_reboot && o.pending_reboot.length ? `<span class="pill warn" title="${AZ.esc(o.pending_reboot.join(', '))}"><i></i>Reinicie para terminar</span>` : ''}
      ${o.job ? `<span class="pill hot"><i></i>${AZ.esc(o.job.phase || 'Trabalhando…')}</span>` : ''}
      <span class="pill ${o.mode === 'agressivo' ? 'warn' : 'todo'}"><i></i>Modo ${mode}</span>
      ${o.plan ? `<span class="pill ${o.plan.score >= 80 ? 'ok' : 'todo'}"><i></i>Nota ${o.plan.score}</span>` : ''}`;
    const todo = o.plan?.todo;
    const c = AZ.$('[data-count="plan"]');
    if (c) { c.hidden = !todo; c.textContent = todo || ''; }
  };

  async function boot() {
    renderNav();
    await AZ.refreshOverview();
    if (AZ.state.overview?.reduce_motion) document.body.classList.add('reduce-motion');
    const start = (location.hash || '#home').slice(1);
    AZ.go(AZ.pages[start] ? start : 'home');
    setInterval(() => { if (document.visibilityState === 'visible') AZ.refreshOverview(); }, 15000);
  }
  window.addEventListener('DOMContentLoaded', boot);
})();
