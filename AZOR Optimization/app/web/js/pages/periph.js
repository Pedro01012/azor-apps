/* Periféricos: teste ao vivo de mouse, teclado e controle + latência do USB. */
'use strict';
(() => {
  const {esc, icon} = AZ;
  const S = {tab: 'mouse', es: null, snap: null, caps: null, kbFmt: 'auto', kbDetected: null, layoutMap: null,
    maxKeys: 0, raf: 0, padTimer: 0, server: null, rest: {l: [], r: []}, irq: null, paused: false};

  /* ---------------- mouse ---------------- */
  const MOUSE_SHELL = 'M230 34c98 0 168 74 168 186v146c0 142-70 208-168 208S62 508 62 366V220C62 108 132 34 230 34Z';
  function mouseSvg() {
    return `<svg viewBox="0 0 460 620" role="img" aria-label="Mouse ao vivo">
      <defs><clipPath id="msClip"><path d="${MOUSE_SHELL}"/></clipPath></defs>
      <path class="shell-main" d="${MOUSE_SHELL}"/>
      <g clip-path="url(#msClip)">
        <path class="ms-part" data-k="left-click" d="M62 252V214C62 110 132 38 227 34v218Z"/>
        <path class="ms-part" data-k="right-click" d="M233 34c95 4 165 76 165 180v38H233Z"/>
      </g>
      <path class="shell-glow" d="${MOUSE_SHELL}" opacity=".55"/>
      <rect class="ms-part" data-k="wheel" x="208" y="92" width="44" height="80" rx="22"/>
      ${[0, 1, 2, 3, 4, 5].map(i => `<rect x="216" y="${104 + i * 10}" width="28" height="3" rx="1.5" fill="#2e2c38"/>`).join('')}
      <path class="ms-part" data-k="wheel-up" d="M218 82l12-12 12 12Z"/>
      <path class="ms-part" data-k="wheel-down" d="M218 182l12 12 12-12Z"/>
      <rect class="ms-part" data-k="side-2" x="46" y="212" width="40" height="24" rx="12"/>
      <rect class="ms-part" data-k="side-1" x="44" y="246" width="40" height="24" rx="12"/>
      <g transform="translate(230 360)">
        <circle r="62" fill="none" stroke="#2c2a36" stroke-width="1.5"/>
        <path d="M-62 0h124M0-62v124" stroke="#24222d" stroke-width="1"/>
        <line class="ms-vec" id="msVec" x1="0" y1="0" x2="0" y2="0"/>
        <circle r="5" fill="#ff66d9"/>
      </g>
      <path d="M198 486l32-54 32 54M211 468h38" fill="none" stroke="rgba(255,47,200,.35)" stroke-width="4" stroke-linejoin="round" stroke-linecap="round"/>
    </svg>`;
  }

  function mouseSide() {
    const snap = S.snap || {};
    const m = snap.mouse || {};
    const pol = snap.polling || {};
    const hz = pol.hz ? Math.round(pol.hz) : null;
    const nominal = pol.nominal_hz || hz;
    const delayMs = nominal ? (1000 / nominal) : null;
    const tone = !nominal ? '' : nominal >= 1000 ? 'good' : nominal >= 500 ? 'warn' : 'bad';
    const clicks = m.clicks || {}, chatter = m.chatter || {};
    const bad = Object.entries(chatter).filter(([, n]) => n > 0);
    const caps = (S.caps?.kinds || {}).mouse || {};
    return `<div class="card"><span class="eyebrow">Taxa de envio (polling)</span>
      <div class="row" style="margin-top:8px"><span class="big-num ${tone}">${nominal ? `${nominal} Hz` : '—'}</span>
        <span class="muted">${delayMs ? `= ${delayMs.toFixed(delayMs < 1 ? 2 : 1).replace('.', ',')} ms de atraso do mouse` : 'mova o mouse em círculos'}</span></div>
      <p style="font-size:12.5px;margin-top:8px">${!nominal ? 'Mexa o mouse rápido, em círculos, por uns 3 segundos. O AZOR cronometra cada envio do sensor.'
        : nominal >= 1000 ? 'Ótimo. 1000 Hz ou mais é o padrão competitivo.'
        : `Seu mouse está mandando só ${nominal} vezes por segundo. No software do mouse, coloque 1000 Hz: são ${(1000 / nominal - 1).toFixed(0)} ms a menos de delay em cada movimento.`}</p>
      ${pol.jitter_ms != null ? `<div class="kv"><span>Variação entre envios</span><b>${String(pol.jitter_ms).replace('.', ',')} ms</b></div>` : ''}
      ${pol.stability ? `<div class="kv"><span>Envios no tempo certo</span><b>${AZ.pct(pol.stability.on_beat)}</b></div>` : ''}
      <div class="kv"><span>Velocidade do sensor</span><b>${m.counts_per_s != null ? `${m.counts_per_s} contagens/s` : '—'}</b></div>
      ${caps.display_name ? `<div class="kv"><span>Mouse</span><b style="font-size:12.5px">${esc(caps.display_name)}</b></div>` : ''}
      </div>
      <div class="card"><span class="eyebrow">Teste de clique</span>
      <p style="font-size:12.5px;margin-top:6px">Clique normal em cada botão. Se aparecer <b>clique duplo fantasma</b>, o botão está registrando 2 cliques quando você deu 1: é o switch gasto (defeito físico).</p>
      ${[['left-click', 'Esquerdo'], ['right-click', 'Direito'], ['wheel', 'Roda'], ['side-1', 'Lateral 1'], ['side-2', 'Lateral 2']].map(([k, l]) =>
        `<div class="kv"><span>${l}</span><b>${clicks[k] || 0} clique(s)${chatter[k] ? ` <span class="bad">· ${chatter[k]} duplo(s) fantasma</span>` : ''}</b></div>`).join('')}
      ${bad.length ? `<div class="desc warn" style="margin-top:8px">${icon('alert')} Clique duplo fantasma detectado. Se repetir, troque o switch ou use a garantia.</div>` : ''}
      </div>`;
  }

  function paintMouse() {
    const m = (S.snap || {}).mouse || {};
    const down = new Set(m.buttons || []);
    if (m.wheel && m.wheel_dir > 0) down.add('wheel-up');
    if (m.wheel && m.wheel_dir < 0) down.add('wheel-down');
    AZ.$$('#stage [data-k]').forEach(el => el.classList.toggle('pressed', down.has(el.dataset.k)));
    const v = AZ.$('#msVec');
    if (v) {
      const dx = m.moving ? m.dx : 0, dy = m.moving ? m.dy : 0;
      const len = Math.hypot(dx, dy) || 1, k = Math.min(58, len * 2.2) / len;
      v.setAttribute('x2', (dx * k).toFixed(1));
      v.setAttribute('y2', (dy * k).toFixed(1));
    }
    const side = AZ.$('#side');
    if (side && !side.matches(':hover')) side.innerHTML = mouseSide();
  }

  /* ---------------- teclado ---------------- */
  const KB = [
    [['ESC', 1], ['', .5], ['F1', 1], ['F2', 1], ['F3', 1], ['F4', 1], ['', .5], ['F5', 1], ['F6', 1], ['F7', 1], ['F8', 1], ['', .5], ['F9', 1], ['F10', 1], ['F11', 1], ['F12', 1], ['', .4], ['PrtSc', 1], ['ScrLk', 1], ['Pause', 1]],
    [['`', 1], ['1', 1], ['2', 1], ['3', 1], ['4', 1], ['5', 1], ['6', 1], ['7', 1], ['8', 1], ['9', 1], ['0', 1], ['-', 1], ['=', 1], ['⌫', 2], ['', .4], ['Ins', 1], ['Home', 1], ['PgUp', 1]],
    [['TAB', 1.5], ['Q', 1], ['W', 1], ['E', 1], ['R', 1], ['T', 1], ['Y', 1], ['U', 1], ['I', 1], ['O', 1], ['P', 1], ['[', 1], [']', 1], ['\\', 1.5], ['', .4], ['Del', 1], ['End', 1], ['PgDn', 1]],
    [['CAPS', 1.75], ['A', 1], ['S', 1], ['D', 1], ['F', 1], ['G', 1], ['H', 1], ['J', 1], ['K', 1], ['L', 1], [';', 1], ["'", 1], ['ENTER', 2.25]],
    [['SHIFT', 2.25], ['Z', 1], ['X', 1], ['C', 1], ['V', 1], ['B', 1], ['N', 1], ['M', 1], [',', 1], ['.', 1], ['/', 1], ['SHIFT', 2.75], ['', 1.4], ['↑', 1]],
    [['CTRL', 1.25], ['WIN', 1.25], ['ALT', 1.25], ['SPACE', 6.25], ['ALT', 1.25], ['WIN', 1.25], ['MENU', 1.25], ['CTRL', 1.25], ['', .4], ['←', 1], ['↓', 1], ['→', 1]],
  ];
  // ABNT2: Enter em L, a tecla extra ao lado do Z (ISO) e a do lado do ponto (RO).
  const KB_ABNT2 = [KB[0], KB[1],
    [['TAB', 1.5], ['Q', 1], ['W', 1], ['E', 1], ['R', 1], ['T', 1], ['Y', 1], ['U', 1], ['I', 1], ['O', 1], ['P', 1], ['[', 1], [']', 1], ['ENTER', 1.5, 'iso'], ['', .4], ['Del', 1], ['End', 1], ['PgDn', 1]],
    [['CAPS', 1.75], ['A', 1], ['S', 1], ['D', 1], ['F', 1], ['G', 1], ['H', 1], ['J', 1], ['K', 1], ['L', 1], [';', 1], ["'", 1], ['\\', 1], ['', 1.25]],
    [['SHIFT', 1.25], ['ISO', 1], ['Z', 1], ['X', 1], ['C', 1], ['V', 1], ['B', 1], ['N', 1], ['M', 1], [',', 1], ['.', 1], ['/', 1], ['RO', 1], ['SHIFT', 1.75], ['', 1.4], ['↑', 1]],
    KB[5]];
  const KB_LIT = new Set(['W', 'A', 'S', 'D', 'Q', 'E', 'R', 'SHIFT', 'CTRL', 'SPACE', '1', '2', '3', '4']);
  const KB_CODE = {'`': 'Backquote', '-': 'Minus', '=': 'Equal', '[': 'BracketLeft', ']': 'BracketRight', '\\': 'Backslash',
    ';': 'Semicolon', "'": 'Quote', ',': 'Comma', '.': 'Period', '/': 'Slash', 'ISO': 'IntlBackslash', 'RO': 'IntlRo'};
  const KB_ABNT2_LEGEND = {'`': "'", '[': '´', ']': '[', '\\': ']', ';': 'Ç', "'": '~', '/': ';', 'ISO': '\\', 'RO': '/'};
  const kbFormat = () => S.kbFmt === 'auto' ? (S.kbDetected || 'ansi') : S.kbFmt;
  function legend(label) {
    const code = KB_CODE[label] || (/^[A-Z]$/.test(label) ? 'Key' + label : /^[0-9]$/.test(label) ? 'Digit' + label : null);
    const ch = code && S.layoutMap && S.kbFmt === 'auto' ? S.layoutMap.get(code) : null;
    if (ch && ch.length === 1 && ch.trim()) return ch.toUpperCase();
    if (kbFormat() === 'abnt2' && KB_ABNT2_LEGEND[label]) return KB_ABNT2_LEGEND[label];
    return label === 'ISO' ? '\\' : label === 'RO' ? '/' : label;
  }
  function keyboardSvg() {
    const rows = kbFormat() === 'abnt2' ? KB_ABNT2 : KB;
    const U = 46, GAP = 5, PX = 22, PY = 22;
    let y = PY, maxX = 0;
    const keys = [];
    rows.forEach((row, r) => {
      let x = PX;
      if (r === 1) y += 10;
      const h = r === 0 ? 30 : 40;
      row.forEach(([label, units, shape]) => {
        const w = units * U + (units - 1) * GAP;
        if (!label) { x += w + GAP; return; }
        const lg = legend(label);
        let base, top;
        if (shape === 'iso') {
          const w2 = 1.25 * U + .25 * GAP, H = 2 * h + GAP, xb = w - w2;
          const outline = d => `M${d} ${d}H${w - d}V${H - d}H${xb + d}V${h - d}H${d}Z`;
          base = `<path class="kb-base" d="${outline(0)}"/>`;
          top = `<path class="kb-top" d="${outline(2.5)}"/>`;
        } else {
          base = `<rect class="kb-base" width="${w}" height="${h}" rx="7"/>`;
          top = `<rect class="kb-top" x="2.5" y="1.5" width="${w - 5}" height="${h - 6}" rx="6"/>`;
        }
        keys.push(`<g class="kb-key${KB_LIT.has(label) ? ' lit' : ''}" data-k="${esc(label)}" transform="translate(${x},${y})">${base}
          <g class="kb-cap">${top}<text x="${w / 2}" y="${h / 2 + 3}" text-anchor="middle"${lg.length > 3 ? ' class="small"' : ''}>${esc(lg)}</text></g></g>`);
        x += w + GAP;
        maxX = Math.max(maxX, x);
      });
      y += h + GAP;
    });
    const W = maxX + PX - GAP, H = y + PY - GAP;
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Teclado ${kbFormat().toUpperCase()} ao vivo">
            <rect class="shell-main" x="4" y="4" width="${W - 8}" height="${H - 8}" rx="16"/>
      <rect class="shell-glow" x="4" y="4" width="${W - 8}" height="${H - 8}" rx="16" opacity=".35"/>${keys.join('')}</svg>`;
  }
  function keyboardSide() {
    const k = (S.snap || {}).keyboard || {};
    const now = (k.down || []).length;
    const caps = (S.caps?.kinds || {}).keyboard || {};
    return `<div class="card"><span class="eyebrow">Teclas apertadas juntas</span>
      <div class="row" style="margin-top:8px"><span class="big-num">${now}</span><span class="muted">agora · recorde ${S.maxKeys}</span></div>
      <p style="font-size:12.5px;margin-top:8px">Aperte <b>W + A + SHIFT + ESPAÇO + C</b> juntos (correr, pular e agachar). Se as 5 acenderem, seu teclado não "come" tecla no meio da jogada.
        ${S.maxKeys >= 6 ? '<br><span class="good">Seu teclado aceita 6 ou mais teclas juntas (anti-ghosting). Perfeito para jogar.</span>'
          : S.maxKeys >= 3 ? '<br><span class="soft">Continue: tente 5 ou mais teclas juntas.</span>' : ''}</p>
      <div class="kv"><span>Toques contados</span><b>${k.press_count || 0}</b></div>
      ${caps.display_name ? `<div class="kv"><span>Teclado</span><b style="font-size:12.5px">${esc(caps.display_name)}</b></div>` : ''}</div>
      <div class="card"><span class="eyebrow">Formato do desenho</span>
      <div class="seg" style="margin-top:10px">${[['auto', 'Automático'], ['ansi', 'ANSI (EUA)'], ['abnt2', 'ABNT2 (Brasil)']].map(([id, l]) =>
        `<button class="${S.kbFmt === id ? 'active' : ''}" data-act="kbfmt" data-f="${id}">${l}</button>`).join('')}</div>
      <p style="font-size:12px;margin-top:10px" class="soft">A tecla acende pela posição física, então funciona em qualquer formato. Privacidade: o AZOR só vê qual tecla está apertada agora; não grava nada.</p></div>`;
  }
  function paintKeyboard() {
    const k = (S.snap || {}).keyboard || {};
    const down = new Set(k.down || []);
    S.maxKeys = Math.max(S.maxKeys, down.size);
    AZ.$$('#stage [data-k]').forEach(el => el.classList.toggle('pressed', down.has(el.dataset.k)));
    const side = AZ.$('#side');
    if (side && !side.matches(':hover')) side.innerHTML = keyboardSide();
  }
  function detectLayout() {
    if (S.layoutAsked) return;
    S.layoutAsked = true;
    try {
      navigator.keyboard?.getLayoutMap?.().then(map => {
        S.layoutMap = map;
        S.kbDetected = map.get('Semicolon') === 'ç' ? 'abnt2' : 'ansi';
        if (S.tab === 'keyboard' && AZ.current?.id === 'periph') paint();
      }).catch(() => {});
    } catch (e) { /* navegador sem mapa de teclado */ }
  }

  /* ---------------- controle ---------------- */
  const PAD_BTN = {0: 'A', 1: 'B', 2: 'X', 3: 'Y', 4: 'LB', 5: 'RB', 8: 'BACK', 9: 'START', 10: 'L3', 11: 'R3', 12: 'UP', 13: 'DOWN', 14: 'LEFT', 15: 'RIGHT', 16: 'GUIDE'};
  function padSvg() {
    const body = 'M150 110h260c58 0 92 34 108 92l40 150c14 54-10 98-56 98-30 0-50-18-68-46l-28-42H154l-28 42c-18 28-38 46-68 46-46 0-70-44-56-98l40-150c16-58 50-92 108-92Z';
    const face = (k, cx, cy) => `<circle class="pad-part" data-k="${k}" cx="${cx}" cy="${cy}" r="17"/><text class="pad-label" x="${cx}" y="${cy + 4}" text-anchor="middle">${k}</text>`;
    return `<svg viewBox="0 0 560 470" role="img" aria-label="Controle ao vivo">
            <rect class="pad-part" data-k="LT" x="112" y="40" width="86" height="30" rx="12"/><text class="pad-label" x="155" y="60" text-anchor="middle">LT</text>
      <rect class="pad-part" data-k="RT" x="362" y="40" width="86" height="30" rx="12"/><text class="pad-label" x="405" y="60" text-anchor="middle">RT</text>
      <rect class="pad-part" data-k="LB" x="108" y="78" width="100" height="24" rx="10"/><text class="pad-label" x="158" y="94" text-anchor="middle">LB</text>
      <rect class="pad-part" data-k="RB" x="352" y="78" width="100" height="24" rx="10"/><text class="pad-label" x="402" y="94" text-anchor="middle">RB</text>
      <path class="shell-main" d="${body}"/><path class="shell-glow" d="${body}" opacity=".45"/>
      <circle cx="160" cy="190" r="44" fill="#121118" stroke="#2c2a36"/>
      <circle class="stick-cap" data-k="L3" id="stL" cx="160" cy="190" r="28"/>
      <circle cx="350" cy="280" r="44" fill="#121118" stroke="#2c2a36"/>
      <circle class="stick-cap" data-k="R3" id="stR" cx="350" cy="280" r="28"/>
      <g><rect class="pad-part" data-k="UP" x="197" y="236" width="26" height="30" rx="5"/><rect class="pad-part" data-k="DOWN" x="197" y="294" width="26" height="30" rx="5"/>
        <rect class="pad-part" data-k="LEFT" x="166" y="267" width="30" height="26" rx="5"/><rect class="pad-part" data-k="RIGHT" x="224" y="267" width="30" height="26" rx="5"/></g>
      ${face('Y', 400, 148)}${face('X', 366, 182)}${face('B', 434, 182)}${face('A', 400, 216)}
      <rect class="pad-part" data-k="BACK" x="232" y="176" width="30" height="16" rx="8"/><rect class="pad-part" data-k="START" x="298" y="176" width="30" height="16" rx="8"/>
      <circle class="pad-part" data-k="GUIDE" cx="280" cy="136" r="16"/><path d="M270 142l10-14 10 14M274 137h12" fill="none" stroke="#ff66d9" stroke-width="2.2" stroke-linecap="round"/>
    </svg>`;
  }
  function radar(id, label) {
    return `<div class="stack" style="align-items:center;gap:6px"><svg class="radar" viewBox="-100 -100 200 200" aria-label="Analógico ${label}">
      <circle r="96" fill="#0c0c12" stroke="#2c2a36"/><circle r="12" fill="none" stroke="rgba(255,195,92,.45)" stroke-dasharray="3 3"/>
      <path d="M-96 0h192M0-96v192" stroke="#1f1e28"/><circle r="48" fill="none" stroke="#1f1e28"/>
      <path id="${id}Trail" fill="none" stroke="rgba(255,47,200,.35)" stroke-width="2"/>
      <circle id="${id}Dot" r="7" fill="#ff2fc8"/></svg><b style="font-size:12px" class="soft">${label}</b></div>`;
  }
  function padConn() {
    const slot = (S.server?.slots || [])[0] || {};
    const pol = slot.polling || {};
    const bat = slot.battery || {};
    return `<div class="card"><span class="eyebrow">Conexão</span>
      <div class="kv"><span>Taxa de envio</span><b>${pol.nominal_hz || (pol.hz ? Math.round(pol.hz) : '—')}${pol.hz ? ' Hz' : ''}</b></div>
      <p style="font-size:12px;margin-top:-4px" class="soft">${esc(pol.detail || (S.server?.available === false ? (S.server.detail || '') : 'Gire um analógico em círculos para medir.'))}</p>
      ${slot.vendor ? `<div class="kv"><span>Fabricante</span><b>${esc(slot.vendor)}</b></div>` : ''}
      ${slot.wireless != null ? `<div class="kv"><span>Ligação</span><b>${slot.wireless ? 'Sem fio' : 'Cabo USB'}</b></div>` : ''}
      ${bat.level ? `<div class="kv"><span>Bateria</span><b>${esc(bat.level)}</b></div>` : ''}
      <p style="font-size:12px;margin-top:8px" class="soft">Dica: com cabo USB o controle manda até 8× mais rápido que no Bluetooth. Para competitivo, use o cabo.</p></div>`;
  }
  function padSide() {
    return `<div class="card"><span class="eyebrow">Analógicos (drift)</span>
      <p style="font-size:12.5px;margin-top:6px">Solte os dois analógicos. O ponto tem que parar dentro do círculo amarelo. Se ficar fora, é <b>drift</b>: a mira ou o boneco andam sozinhos.</p>
      <div class="row" style="justify-content:space-around;margin-top:10px">${radar('rl', 'Esquerdo')}${radar('rr', 'Direito')}</div>
      <div class="kv"><span>Esquerdo parado</span><b id="driftL">—</b></div><div class="kv"><span>Direito parado</span><b id="driftR">—</b></div>
      <div style="margin-top:10px"><span class="soft" style="font-size:12px">Gatilhos LT / RT</span>
        <div class="trig" style="margin-top:6px"><i id="trL"></i></div><div class="trig" style="margin-top:6px"><i id="trR"></i></div></div></div>
      <div id="padConn">${padConn()}</div>`;
  }
  function readPad() {
    let pads = [];
    try { pads = [...(navigator.getGamepads ? navigator.getGamepads() : [])].filter(Boolean); } catch (e) { pads = []; }
    const gp = pads.find(p => p.connected);
    if (gp) {
      const b = new Set();
      gp.buttons.forEach((x, i) => { if (x.pressed && PAD_BTN[i]) b.add(PAD_BTN[i]); });
      return {src: 'browser', name: gp.id, buttons: b, lx: gp.axes[0] || 0, ly: gp.axes[1] || 0, rx: gp.axes[2] || 0, ry: gp.axes[3] || 0,
        lt: gp.buttons[6]?.value || 0, rt: gp.buttons[7]?.value || 0};
    }
    const st = (S.server?.slots || [])[0]?.state;
    if (st) {
      const n = v => AZ.clamp(v / 32767, -1, 1);
      return {src: 'xinput', buttons: new Set(st.buttons || []), lx: n(st.lx), ly: -n(st.ly), rx: n(st.rx), ry: -n(st.ry), lt: st.lt / 255, rt: st.rt / 255};
    }
    return null;
  }
  function restValue(list, mag) {
    const now = performance.now();
    list.push([now, mag]);
    while (list.length && now - list[0][0] > 1500) list.shift();
    return list.length > 20 ? Math.min(...list.map(x => x[1])) : null;
  }
  function driftText(v) {
    if (v == null) return '—';
    const p = Math.round(v * 100);
    if (v > .12) return `<span class="bad">${p}% · DRIFT</span>`;
    if (v > .06) return `<span class="warn">${p}% · use zona morta ${p + 2}%</span>`;
    return `<span class="good">${p}% · ok</span>`;
  }
  function padLoop() {
    if (S.tab !== 'pad' || AZ.current?.id !== 'periph') return;
    const st = readPad();
    const hint = AZ.$('#padHint');
    if (hint) hint.hidden = !!st;
    if (st) {
      const pressed = new Set(st.buttons);
      if (st.lt > .1) pressed.add('LT');
      if (st.rt > .1) pressed.add('RT');
      AZ.$$('#stage [data-k]').forEach(el => el.classList.toggle('pressed', pressed.has(el.dataset.k)));
      const move = (id, x, y) => { const el = AZ.$(id); if (el) el.setAttribute('transform', `translate(${(x * 14).toFixed(1)} ${(y * 14).toFixed(1)})`); };
      move('#stL', st.lx, st.ly);
      move('#stR', st.rx, st.ry);
      for (const [id, x, y, key, out] of [['rl', st.lx, st.ly, 'l', '#driftL'], ['rr', st.rx, st.ry, 'r', '#driftR']]) {
        const dot = AZ.$(`#${id}Dot`);
        if (dot) { dot.setAttribute('cx', (x * 90).toFixed(1)); dot.setAttribute('cy', (y * 90).toFixed(1)); }
        const rest = restValue(S.rest[key], Math.hypot(x, y));
        const o = AZ.$(out);
        if (o) o.innerHTML = driftText(rest);
      }
      const tl = AZ.$('#trL'), tr = AZ.$('#trR');
      if (tl) tl.style.width = `${Math.round(st.lt * 100)}%`;
      if (tr) tr.style.width = `${Math.round(st.rt * 100)}%`;
    }
    S.raf = requestAnimationFrame(padLoop);
  }
  async function pollServerPad() {
    clearTimeout(S.padTimer);
    if (S.tab !== 'pad' || AZ.current?.id !== 'periph') return;
    try {
      S.server = await AZ.get('/api/gamepad-live', 5000);
      const conn = AZ.$('#padConn');
      if (conn && Date.now() - (S.connAt || 0) > 700) { S.connAt = Date.now(); conn.innerHTML = padConn(); }
    } catch (e) { /* segue */ }
    const browserPad = (() => { try { return [...navigator.getGamepads()].some(Boolean); } catch (e) { return false; } })();
    S.padTimer = setTimeout(pollServerPad, browserPad ? 900 : 90);
  }

  /* ---------------- USB e latência ---------------- */
  function usbView() {
    const d = S.irq;
    if (!d) return `${AZ.skeleton(3)}<p class="soft" style="text-align:center">Medindo as interrupções do processador por 2 segundos…</p>`;
    const st = d.state || {}, load = d.load || {};
    const rows = (load.rows || []).slice().sort((a, b) => (b.dpcs || 0) - (a.dpcs || 0)).slice(0, 8);
    const maxDpc = Math.max(1, ...rows.map(r => r.dpcs || 0));
    return `<div class="card ${st.hybrid && !st.all_on_ecores ? 'glow' : ''}"><div class="spread nw"><div class="row" style="flex-wrap:nowrap">${AZ.stateIcon(!st.hybrid ? 'manual' : st.all_on_ecores ? 'ok' : 'todo')}
      <div><b>USB do mouse/controle nos núcleos E</b> ${AZ.tags(['-DELAY', '-STUTTER', 'TESTE'])}
        <div class="muted" style="font-size:13px">${st.hybrid
          ? 'Seu Intel tem núcleos P (os fortes, onde o jogo roda) e núcleos E. Mandar as interrupções do USB para os núcleos E tira esse trabalho do caminho do jogo. Vale depois de reiniciar. Se o mouse ficar estranho, desligue aqui.'
          : 'Seu processador não tem núcleos E (só Intel de 12ª geração em diante tem). Nada para fazer aqui.'}</div></div></div>
      ${st.hybrid ? AZ.toggle(!!st.all_on_ecores, 'data-act="irq"') : ''}</div>
      ${(st.hosts || []).length ? `<div class="stack" style="margin-top:10px">${st.hosts.map(h => `<div class="row soft" style="font-size:12.5px">${icon(h.on_ecores ? 'check' : 'info', h.on_ecores ? 'good' : '')} ${esc(h.name)}</div>`).join('')}</div>` : ''}</div>
      ${AZ.sectionTitle('cpu', 'Quem está interrompendo o processador', 'Chamadas de driver (DPC) por núcleo nos últimos 2 segundos. Um núcleo muito acima dos outros costuma ser driver de rede, áudio ou vídeo atrapalhando o jogo.')}
      ${rows.length ? `<div class="card">${rows.map(r => `<div class="kv"><span>Núcleo ${r.cpu}${r.cpu === load.busiest ? ' <span class="tag risk">MAIS CARREGADO</span>' : ''}</span>
        <b style="min-width:240px;display:flex;gap:10px;align-items:center;justify-content:flex-end"><span class="bar" style="width:120px;height:8px"><i style="width:${Math.round((r.dpcs || 0) / maxDpc * 100)}%"></i></span>${Math.round(r.dpcs || 0)} DPC/s</b></div>`).join('')}</div>`
        : `<div class="empty">${esc(load.detail || 'Leitura indisponível neste sistema.')}</div>`}
      <div class="row" style="margin-top:10px"><button class="btn sm" data-act="irqreload">${icon('refresh')} Medir de novo</button>
        <button class="btn sm ghost" data-act="gotweaks">${icon('tweaks')} Ajustes de delay do Windows</button></div>`;
  }

  /* ---------------- estrutura ---------------- */
  function tabs() {
    const t = [['mouse', 'mouse', 'Mouse'], ['keyboard', 'keyboard', 'Teclado'], ['pad', 'pad', 'Controle'], ['usb', 'cpu', 'USB e latência']];
    return `<div class="tabs">${t.map(([id, ic, l]) => `<button class="tab ${S.tab === id ? 'active' : ''}" data-act="tab" data-t="${id}">${icon(ic)} ${l}</button>`).join('')}</div>`;
  }
  function paint() {
    const root = AZ.$('#pfBody');
    if (!root) return;
    AZ.$('#pfTabs').innerHTML = tabs();
    if (S.tab === 'usb') { root.innerHTML = usbView(); return; }
    const stage = S.tab === 'mouse' ? mouseSvg() : S.tab === 'keyboard' ? keyboardSvg() : padSvg();
    const side = S.tab === 'mouse' ? mouseSide() : S.tab === 'keyboard' ? keyboardSide() : padSide();
    const hint = S.tab === 'mouse' ? 'Mexa e clique com esta tela aberta.' : S.tab === 'keyboard' ? 'Aperte as teclas: cada uma acende no desenho.' : 'Aperte qualquer botão do controle para ele aparecer.';
    root.innerHTML = `<div class="spread" style="margin-bottom:12px"><div class="live-dot ${S.paused ? '' : 'on'}" id="liveDot"><i></i> ${S.paused ? 'Pausado: um jogo está aberto na frente' : 'Ao vivo'}</div>
        <span class="soft" style="font-size:12.5px">${hint}</span></div>
      <div class="lab ${S.tab === 'keyboard' ? 'wide' : ''}"><div class="lab-stage" id="stage">${stage}${S.tab === 'pad' ? '<p id="padHint" class="soft" style="margin-top:10px">Nenhum controle respondendo ainda. Conecte e aperte um botão.</p>' : ''}</div>
        <div class="stack" id="side">${side}</div></div>
      <div class="card tight" style="margin-top:14px"><div class="spread"><div class="row" style="flex-wrap:nowrap">${AZ.stateIcon('manual')}<div><b>O Windows também atrasa a mira</b>
        <div class="muted" style="font-size:13px">Aceleração do mouse, teclas de aderência, repetição lenta de tecla… O BOOST já corrige. Para ver item por item, abra os ajustes de delay.</div></div></div>
        <button class="btn sm" data-act="gotweaks">${icon('delay')} Ajustes de delay</button></div></div>`;
    if (S.tab === 'pad') { cancelAnimationFrame(S.raf); S.raf = requestAnimationFrame(padLoop); }
    else if (S.snap) (S.tab === 'mouse' ? paintMouse : paintKeyboard)();
  }

  function openStream() {
    closeStream();
    if (!window.EventSource) return;
    const es = new EventSource('/api/input-live/stream');
    S.es = es;
    es.onmessage = ev => {
      let d;
      try { d = JSON.parse(ev.data); } catch (e) { return; }
      const paused = !!d.paused;
      if (paused !== S.paused) { S.paused = paused; const dot = AZ.$('#liveDot'); if (dot) { dot.classList.toggle('on', !paused); dot.lastChild.textContent = paused ? ' Pausado: um jogo está aberto na frente' : ' Ao vivo'; } }
      if (paused || !d.ok) return;
      S.snap = d;
      if (S.tab === 'mouse') paintMouse();
      else if (S.tab === 'keyboard') paintKeyboard();
    };
    es.onerror = () => { /* o navegador reconecta sozinho */ };
  }
  function closeStream() {
    if (S.es) { S.es.close(); S.es = null; }
  }
  function stopAll() {
    closeStream();
    cancelAnimationFrame(S.raf);
    clearTimeout(S.padTimer);
  }
  function enterTab() {
    stopAll();
    if (S.tab === 'mouse' || S.tab === 'keyboard') openStream();
    if (S.tab === 'pad') { S.rest = {l: [], r: []}; pollServerPad(); }
    if (S.tab === 'usb' && !S.irq) loadIrq();
    paint();
  }
  async function loadIrq() {
    S.irq = null;
    paint();
    S.irq = await AZ.get('/api/usb-irq', 30000).catch(e => ({state: {}, load: {detail: e.message}}));
    if (S.tab === 'usb' && AZ.current?.id === 'periph') paint();
  }

  AZ.page('periph', {
    title: 'Periféricos',
    sub: 'Teste ao vivo: taxa real do mouse, clique duplo fantasma, teclas que somem e drift do controle. E o que o Windows faz para atrasar sua mira.',
    async render(view, params) {
      if (params.tab) S.tab = params.tab;
      view.innerHTML = '<div id="pfTabs"></div><div id="pfBody"></div>';
      detectLayout();
      AZ.get('/api/devices', 30000).then(d => { S.caps = d.caps || null; }).catch(() => {});
      enterTab();
    },
    leave() {
      stopAll();
      AZ.action('input_stop').catch(() => {});
    },
    actions: {
      tab: el => { S.tab = el.dataset.t; enterTab(); },
      kbfmt: el => { S.kbFmt = el.dataset.f; paint(); },
      gotweaks: () => AZ.go('tweaks', {goal: 'delay'}),
      irqreload: () => loadIrq(),
      irq: async el => {
        const on = !el.classList.contains('on');
        el.disabled = true;
        const r = await AZ.action('usb_irq', {enabled: on}).catch(e => ({ok: false, detail: e.message}));
        AZ.toast(r.detail, r.ok);
        loadIrq();
      },
    },
  });
})();
