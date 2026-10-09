// Ilustração vetorial detalhada de um PC gamer (lateral de vidro + frente em perspectiva).
// Coordenadas internas: 800 x 1000. Partes animáveis têm id.
const R = (n, d = 1) => +n.toFixed(d);

function blade(r0, r1) {
  const pts = [];
  for (let i = 0; i <= 10; i++) { const k = i / 10, r = r0 + (r1 - r0) * k, a = -.25 + .55 * k * k; pts.push([r * Math.cos(a), r * Math.sin(a)]); }
  for (let i = 10; i >= 0; i--) { const k = i / 10, r = r0 + (r1 - r0) * k, a = .32 + .34 * k; pts.push([r * Math.cos(a), r * Math.sin(a)]); }
  return 'M' + pts.map(p => `${R(p[0])} ${R(p[1])}`).join(' L') + 'Z';
}
const BLADE = blade(30, 96);

// ventoinha vista de frente (raio ~110); "id" recebe rotação
function fan(id, ledStroke = 'url(#led)') {
  const blades = Array.from({length: 9}, (_, i) => `<path d="${BLADE}" transform="rotate(${i * 40})" fill="url(#bladeG)" stroke="rgba(255,255,255,.08)" stroke-width="1"/>`).join('');
  return `
    <rect x="-118" y="-118" width="236" height="236" rx="26" fill="url(#fanFrame)" stroke="rgba(255,255,255,.07)" stroke-width="2"/>
    <circle r="108" fill="#07060a"/>
    <g class="lit"><circle r="104" fill="none" stroke="${ledStroke}" stroke-width="9" filter="url(#glow)"/></g>
    <circle r="104" fill="none" stroke="rgba(255,255,255,.35)" stroke-width="1.5"/>
    <g id="${id}">${blades}</g>
    <circle class="fblur" r="98" fill="url(#fanBlur)" opacity="0"/>
    <circle r="30" fill="url(#hub)" stroke="rgba(255,255,255,.12)" stroke-width="1.5"/>
    <circle r="12" fill="#ff2fc8" opacity=".55" class="lit"/>`;
}

export function pcSVG() {
  const vent = Array.from({length: 26}, (_, i) => `<rect x="${92 + i * 21}" y="56" width="12" height="22" rx="4" fill="#07060a" opacity=".9"/>`).join('');
  const fins = (x, y, w, h, n, vertical = true) => Array.from({length: n}, (_, i) => vertical
    ? `<rect x="${R(x + i * w / n)}" y="${y}" width="${R(w / n * .55)}" height="${h}" fill="url(#finG)"/>`
    : `<rect x="${x}" y="${R(y + i * h / n)}" width="${w}" height="${R(h / n * .55)}" fill="url(#finGh)"/>`).join('');
  const dots = []; for (let r = 0; r < 9; r++) for (let c = 0; c < 18; c++) dots.push(`<circle cx="${110 + c * 13 + (r % 2) * 6.5}" cy="${768 + r * 13}" r="3.4" fill="#06050a"/>`);
  const grom = Array.from({length: 8}, (_, i) => `<rect x="536" y="${220 + i * 60}" width="22" height="40" rx="10" fill="#050407" stroke="#1d1a24" stroke-width="2"/>`).join('');
  const sleeve = (d, n, w, gap, id = '') => Array.from({length: n}, (_, i) => `<path d="${d}" transform="translate(${i * gap} 0)" fill="none" stroke="${i % 2 ? 'url(#sleeveA)' : 'url(#sleeveB)'}" stroke-width="${w}" stroke-linecap="round"/>`).join('');
  const ram = Array.from({length: 4}, (_, k) => { const i = 3 - k, x = 418 + i * 13;
    return `<g><rect x="${x}" y="196" width="36" height="252" rx="4" fill="url(#ramBody)" stroke="rgba(255,255,255,.1)"/>
      <path d="M${x + 4} 260 L${x + 32} 240 L${x + 32} 300 L${x + 4} 320 Z" fill="rgba(255,255,255,.06)"/>
      <rect class="ramLed" x="${x + 3}" y="200" width="30" height="34" rx="6" fill="url(#ramLed)" filter="url(#glow)"/>
      <rect x="${x + 3}" y="200" width="30" height="34" rx="6" fill="url(#ramLed)"/></g>`; }).join('');
  const traces = [
    'M310 370 V420 L330 440 H410 V470', 'M376 300 H404 L414 290 V236', 'M244 300 H222 L210 288 V230', 'M310 234 V218 L322 206 H396',
    'M350 352 L386 388 H482 V560', 'M268 352 L232 388 V452 H170 V560', 'M244 330 H196 V430', 'M372 330 H480 L496 346 V380'];
  const traceBase = traces.map(d => `<path d="${d}" fill="none" stroke="rgba(255,120,220,.16)" stroke-width="3" stroke-linejoin="round"/>`).join('');
  const traceFlow = traces.map((d, i) => `<path class="flow" d="${d}" fill="none" stroke="#ff4fd6" stroke-width="10" stroke-linecap="round" stroke-linejoin="round" filter="url(#glow)" pathLength="100" stroke-dasharray="34 66" stroke-dashoffset="100" opacity="0" data-i="${i}"/>
    <path class="flow" d="${d}" fill="none" stroke="#fff4fd" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" pathLength="100" stroke-dasharray="34 66" stroke-dashoffset="100" opacity="0" data-i="${i}"/>`).join('');
  return `<svg id="pc" viewBox="0 0 800 1000" width="800" height="1000" xmlns="http://www.w3.org/2000/svg" overflow="visible">
<defs>
  <linearGradient id="led" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ff2fc8"/><stop offset=".5" stop-color="#9b5cff"/><stop offset="1" stop-color="#ff5fd8"/></linearGradient>
  <linearGradient id="ledH" x1="0" x2="1"><stop offset="0" stop-color="#ff2fc8"/><stop offset=".5" stop-color="#a66bff"/><stop offset="1" stop-color="#ff2fc8"/></linearGradient>
  <linearGradient id="ramLed" x1="0" y1="0" x2="0" y2="1" gradientUnits="objectBoundingBox" spreadMethod="repeat" gradientTransform="translate(0 0)">
    <stop offset="0" stop-color="#ff2fc8"/><stop offset=".33" stop-color="#8b5cff"/><stop offset=".66" stop-color="#4fb3ff"/><stop offset="1" stop-color="#ff2fc8"/></linearGradient>
  <linearGradient id="caseSide" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#25222d"/><stop offset=".5" stop-color="#15131b"/><stop offset="1" stop-color="#0b0a0f"/></linearGradient>
  <linearGradient id="caseFront" x1="0" x2="1"><stop offset="0" stop-color="#1b1922"/><stop offset="1" stop-color="#2c2934"/></linearGradient>
  <linearGradient id="rail" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#34303d"/><stop offset=".15" stop-color="#1d1a24"/><stop offset="1" stop-color="#121017"/></linearGradient>
  <linearGradient id="metal" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#4a4655"/><stop offset=".45" stop-color="#25222c"/><stop offset="1" stop-color="#16141b"/></linearGradient>
  <linearGradient id="metalLight" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#8e8a99"/><stop offset=".5" stop-color="#d6d2de"/><stop offset="1" stop-color="#7c7887"/></linearGradient>
  <linearGradient id="finG" x1="0" x2="1"><stop offset="0" stop-color="#5b5766"/><stop offset="1" stop-color="#25222c"/></linearGradient>
  <linearGradient id="finGh" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5b5766"/><stop offset="1" stop-color="#25222c"/></linearGradient>
  <linearGradient id="ramBody" x1="0" x2="1"><stop offset="0" stop-color="#3a3644"/><stop offset=".5" stop-color="#1c1a22"/><stop offset="1" stop-color="#2a2731"/></linearGradient>
  <linearGradient id="gpuBody" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3b3746"/><stop offset=".35" stop-color="#22202a"/><stop offset="1" stop-color="#121016"/></linearGradient>
  <linearGradient id="shroudG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2d2a36"/><stop offset=".08" stop-color="#1c1a23"/><stop offset="1" stop-color="#0f0e13"/></linearGradient>
  <linearGradient id="tube" x1="0" x2="1"><stop offset="0" stop-color="#0c0b10"/><stop offset=".45" stop-color="#3a3644"/><stop offset="1" stop-color="#0c0b10"/></linearGradient>
  <linearGradient id="sleeveA" x1="0" x2="1"><stop offset="0" stop-color="#ffd6f4"/><stop offset="1" stop-color="#e9a7ff"/></linearGradient>
  <linearGradient id="sleeveB" x1="0" x2="1"><stop offset="0" stop-color="#2c2834"/><stop offset="1" stop-color="#4a4456"/></linearGradient>
  <linearGradient id="bladeG" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#3a2f46"/><stop offset="1" stop-color="#17131d"/></linearGradient>
  <linearGradient id="fanFrame" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2a2731"/><stop offset="1" stop-color="#121016"/></linearGradient>
  <radialGradient id="hub"><stop offset="0" stop-color="#3a3644"/><stop offset="1" stop-color="#121016"/></radialGradient>
  <radialGradient id="fanBlur"><stop offset=".25" stop-color="rgba(60,40,80,0)"/><stop offset=".35" stop-color="rgba(120,70,150,.45)"/><stop offset=".95" stop-color="rgba(160,90,190,.35)"/><stop offset="1" stop-color="rgba(160,90,190,0)"/></radialGradient>
  <radialGradient id="pumpG" cx=".4" cy=".35"><stop offset="0" stop-color="#3d3948"/><stop offset="1" stop-color="#0f0e13"/></radialGradient>
  <radialGradient id="glowM"><stop offset="0" stop-color="rgba(255,47,200,.55)"/><stop offset="1" stop-color="rgba(255,47,200,0)"/></radialGradient>
  <radialGradient id="glowV"><stop offset="0" stop-color="rgba(139,92,255,.5)"/><stop offset="1" stop-color="rgba(139,92,255,0)"/></radialGradient>
  <linearGradient id="glassG" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="rgba(255,255,255,.07)"/><stop offset=".4" stop-color="rgba(255,255,255,.015)"/><stop offset="1" stop-color="rgba(255,255,255,.04)"/></linearGradient>
  <linearGradient id="sweepG" x1="0" x2="1"><stop offset="0" stop-color="rgba(255,255,255,0)"/><stop offset=".5" stop-color="rgba(255,255,255,.22)"/><stop offset="1" stop-color="rgba(255,255,255,0)"/></linearGradient>
  <pattern id="pcbP" width="48" height="48" patternUnits="userSpaceOnUse">
    <rect width="48" height="48" fill="#121019"/>
    <path d="M0 12 H18 L24 18 V48 M30 0 V8 L36 14 H48 M6 30 H14 L20 36 V48" fill="none" stroke="#1d1a27" stroke-width="2"/>
    <rect x="34" y="28" width="8" height="5" rx="1" fill="#24212c"/><circle cx="10" cy="40" r="2" fill="#2a2633"/></pattern>
  <filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <filter id="glowBig" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="16"/></filter>
  <filter id="soft"><feGaussianBlur stdDeviation="2"/></filter>
  <clipPath id="win"><rect x="76" y="92" width="552" height="816" rx="6"/></clipPath>
</defs>

<!-- sombra no chão -->
<ellipse cx="400" cy="985" rx="380" ry="26" fill="rgba(0,0,0,.6)" filter="url(#glowBig)"/>
<!-- frente em perspectiva -->
<path d="M650 40 L744 74 L744 926 L650 960 Z" fill="url(#caseFront)" stroke="rgba(255,255,255,.1)" stroke-width="2"/>
<g transform="translate(698 500)">
  ${[-272, 0, 272].map((y, i) => `<g transform="translate(0 ${y * .93}) skewY(${[14, 0, -14][i]}) scale(.3 .9)">${fan('ff' + i)}</g>`).join('')}
</g>
<path d="M650 40 L744 74 L744 926 L650 960 Z" fill="url(#glassG)"/>
<path d="M652 44 L742 76" stroke="rgba(255,255,255,.25)" stroke-width="2"/>
<path class="lit" d="M740 84 L740 916" stroke="url(#led)" stroke-width="3" filter="url(#glow)"/>

<!-- lateral: corpo -->
<rect x="52" y="40" width="600" height="920" rx="22" fill="url(#caseSide)" stroke="rgba(255,255,255,.1)" stroke-width="2"/>
<rect x="52" y="40" width="600" height="52" rx="22" fill="url(#rail)"/>${vent}
<rect x="52" y="908" width="600" height="52" rx="18" fill="url(#rail)"/>
<rect x="90" y="958" width="70" height="14" rx="6" fill="#0a090d"/><rect x="560" y="958" width="70" height="14" rx="6" fill="#0a090d"/>

<!-- interior -->
<g clip-path="url(#win)">
  <rect x="76" y="92" width="552" height="816" fill="#0b0a0f"/>
  <g class="lit"><ellipse cx="580" cy="440" rx="320" ry="440" fill="url(#glowM)" opacity=".85"/><ellipse cx="260" cy="190" rx="280" ry="220" fill="url(#glowV)" opacity=".8"/><ellipse cx="310" cy="300" rx="200" ry="180" fill="url(#glowM)" opacity=".5"/></g>
  <!-- radiador e ventoinhas de cima -->
  <rect x="150" y="98" width="452" height="34" rx="4" fill="url(#metal)"/>
  ${fins(156, 102, 440, 26, 60)}
  ${[0, 1, 2].map(i => `<rect x="${160 + i * 147}" y="132" width="138" height="24" rx="5" fill="#141218" stroke="rgba(255,255,255,.08)"/><rect class="lit" x="${166 + i * 147}" y="152" width="126" height="3" rx="1.5" fill="url(#ledH)" filter="url(#glow)"/>`).join('')}
  <!-- ventoinha traseira (de lado) -->
  <rect x="84" y="150" width="28" height="170" rx="6" fill="#141218" stroke="rgba(255,255,255,.08)"/>
  <rect class="lit" x="108" y="158" width="3" height="154" rx="1.5" fill="url(#led)" filter="url(#glow)"/>
  <g id="exhaust"></g>
  <!-- placa-mãe -->
  <rect x="120" y="170" width="380" height="470" rx="10" fill="url(#pcbP)" stroke="#262230" stroke-width="2"/>
  ${traceBase}
  <!-- tampa do I/O com faixa de luz -->
  <path d="M120 172 H178 V392 L160 420 H120 Z" fill="url(#metal)" stroke="rgba(255,255,255,.1)"/>
  <path d="M132 190 L164 190 L164 300 L132 330 Z" fill="rgba(255,255,255,.05)"/>
  <rect class="lit" x="170" y="190" width="3.5" height="200" rx="1.7" fill="url(#led)" filter="url(#glow)"/>
  <!-- dissipadores de VRM -->
  <rect x="186" y="178" width="222" height="40" rx="5" fill="#1a1820"/>${fins(190, 181, 214, 34, 26)}
  <rect x="186" y="222" width="36" height="150" rx="5" fill="#1a1820"/>${fins(189, 226, 30, 142, 16, false)}
  <!-- capacitores, indutores, áudio, SATA -->
  ${[0,1,2,3,4,5,6].map(i => `<rect x="${232 + i * 24}" y="226" width="18" height="18" rx="3" fill="#2b2833" stroke="rgba(255,255,255,.08)"/>`).join('')}
  ${[0,1,2,3,4,5].map(i => `<circle cx="${240 + i * 24}" cy="258" r="7" fill="url(#metalLight)" opacity=".75"/><circle cx="${240 + i * 24}" cy="258" r="2.5" fill="#3a3644"/>`).join('')}
  <path d="M128 470 V630 H210 L226 614 V470 Z" fill="url(#metal)" opacity=".9"/><text x="140" y="560" font-family="GeistMono" font-size="11" fill="rgba(255,255,255,.35)" transform="rotate(-90 140 560)" letter-spacing="3">AUDIO</text>
  ${[0,1,2,3].map(i => `<rect x="${478}" y="${500 + i * 26}" width="20" height="18" rx="2" fill="#0d0c11" stroke="rgba(255,255,255,.14)"/>`).join('')}
  ${[0,1,2,3,4,5,6,7].map(i => `<circle cx="${132 + (i % 2) * 360}" cy="${182 + Math.floor(i / 2) * 150}" r="5" fill="#2e2a37" stroke="rgba(255,255,255,.2)"/>`).join('')}
  <!-- M.2 -->
  <rect x="236" y="410" width="160" height="30" rx="5" fill="url(#metalLight)" opacity=".85"/>
  <text x="246" y="430" font-family="GeistMono" font-size="12" fill="#2b2833" letter-spacing="2">M.2 · GEN4</text>
  <!-- memórias -->
  ${ram}
  <!-- conector 24 pinos e cabos trançados -->
  <rect x="486" y="300" width="16" height="86" rx="3" fill="#0d0c11" stroke="rgba(255,255,255,.12)"/>
  ${sleeve('M500 312 C528 312 536 326 536 360 L536 720', 6, 4.2, 5.2)}
  <!-- passa-cabos -->
  ${grom}
  <!-- bomba do water cooler com o logo -->
  <path d="M352 260 C400 210 430 170 470 156" fill="none" stroke="url(#tube)" stroke-width="18" stroke-linecap="round"/>
  <path d="M362 280 C420 230 470 190 530 156" fill="none" stroke="url(#tube)" stroke-width="18" stroke-linecap="round"/>
  <g transform="translate(310 300)">
    <circle r="74" fill="url(#pumpG)" stroke="rgba(255,255,255,.12)" stroke-width="2"/>
    <circle r="66" fill="none" stroke="url(#metalLight)" stroke-width="2" opacity=".4"/>
    <g class="lit" id="pumpRing"><circle r="60" fill="none" stroke="url(#led)" stroke-width="7" filter="url(#glow)"/></g>
    <circle r="54" fill="#08070b"/>
    <image id="pumpLogo" href="/web/assets/Azor_icon.png" x="-44" y="-44" width="88" height="88" opacity=".9"/>
    <ellipse cx="-16" cy="-24" rx="30" ry="14" fill="rgba(255,255,255,.08)" transform="rotate(-30)"/>
  </g>
  ${traceFlow}
  <!-- chipset e slots -->
  <rect x="140" y="600" width="300" height="8" rx="3" fill="#07060a"/><rect x="140" y="620" width="300" height="8" rx="3" fill="#07060a"/>
  <rect x="352" y="590" width="120" height="40" rx="6" fill="url(#metal)"/><rect class="lit" x="362" y="608" width="100" height="3" rx="1.5" fill="url(#ledH)" filter="url(#glow)"/>
  <!-- placa de vídeo -->
  <rect x="92" y="458" width="14" height="140" rx="2" fill="url(#metalLight)"/>
  <rect x="104" y="464" width="500" height="12" rx="4" fill="url(#metal)"/>
  <path d="M104 476 H600 L612 492 V566 L598 584 H104 Z" fill="url(#gpuBody)" stroke="rgba(255,255,255,.12)" stroke-width="1.5"/>
  <path d="M130 484 H300 L282 508 H130 Z" fill="rgba(255,255,255,.05)"/>
  <path d="M420 484 H590 L600 496 V520 H440 Z" fill="rgba(255,255,255,.04)"/>
  <rect x="130" y="530" width="460" height="3" rx="1.5" fill="url(#metalLight)" opacity=".5"/>
  <text id="gpuLogo" class="lit" x="352" y="522" text-anchor="middle" font-family="Geist" font-weight="600" font-size="26" letter-spacing="10" fill="#ffe6f8" filter="url(#glow)">AZOR</text>
  <rect class="lit" x="140" y="572" width="440" height="4" rx="2" fill="url(#ledH)" filter="url(#glow)"/>
  ${sleeve('M520 464 C520 420 530 404 540 400', 3, 5, 9)}
  <!-- tampa da fonte -->
  <rect x="76" y="720" width="552" height="188" rx="6" fill="url(#shroudG)" stroke="rgba(255,255,255,.1)"/>
  <rect x="76" y="720" width="552" height="3" fill="rgba(255,255,255,.18)"/>
  ${dots.join('')}
  <text id="psuLogo" class="lit" x="480" y="842" text-anchor="middle" font-family="Geist" font-weight="600" font-size="44" letter-spacing="18" fill="#ffd6f4" filter="url(#glow)">AZOR</text>
  <rect class="lit" x="96" y="896" width="512" height="3" rx="1.5" fill="url(#ledH)" filter="url(#glow)"/>
  <!-- vidro: reflexos -->
  <rect x="76" y="92" width="552" height="816" fill="url(#glassG)"/>
  <path d="M76 300 L360 92 H430 L76 360 Z" fill="rgba(255,255,255,.035)"/>
  <rect id="sweep" x="-300" y="60" width="220" height="900" fill="url(#sweepG)" transform="skewX(-18)" opacity="0"/>
</g>
<rect x="76" y="92" width="552" height="816" rx="6" fill="none" stroke="rgba(255,255,255,.14)" stroke-width="2"/>
<rect x="76" y="92" width="552" height="816" rx="6" fill="none" stroke="#050407" stroke-width="10" opacity=".7"/>
</svg>`;
}

// Controle por quadro: p = potência (0 apagado .. 1 aceso), ang = ângulo das ventoinhas (rad), blur 0..1
export function pcUpdate(root, s) {
  const p = s.power ?? 1;
  root.querySelectorAll('.lit').forEach(e => { e.style.opacity = (e.dataset.base ??= getComputedStyle(e).opacity || 1) * (.12 + .88 * p); });
  ['ff0', 'ff1', 'ff2'].forEach((id, i) => { const g = root.querySelector('#' + id); if (g) g.setAttribute('transform', `rotate(${(s.ang * 180 / Math.PI + i * 17).toFixed(2)})`); });
  root.querySelectorAll('.fblur').forEach(e => e.setAttribute('opacity', (.85 * (s.blur || 0)).toFixed(3)));
  root.querySelectorAll('[id^=ff]').forEach(e => e.style.opacity = 1 - .75 * (s.blur || 0));
  const rg = root.querySelector('#ramLed'); if (rg) rg.setAttribute('gradientTransform', `translate(0 ${((s.t || 0) * .6 % 1).toFixed(3)})`);
  root.querySelectorAll('.flow').forEach(e => {
    const i = +e.dataset.i, k = s.flow == null ? -1 : s.flow - i * .06;
    e.setAttribute('opacity', k > 0 && k < 1.2 ? 1 : 0);
    e.setAttribute('stroke-dashoffset', (100 - Math.min(1.2, Math.max(0, k)) * 118).toFixed(1));
  });
  const sw = root.querySelector('#sweep');
  if (sw) { const k = s.sweep ?? -1; sw.setAttribute('opacity', k > 0 && k < 1 ? 1 : 0); sw.setAttribute('x', (-300 + k * 1200).toFixed(1)); }
  const logo = root.querySelector('#pumpLogo'); if (logo) logo.setAttribute('opacity', (.35 + .6 * p).toFixed(3));
}

// Placa de vídeo vista pelo lado das ventoinhas (1000 x 420)
export function gpuSVG() {
  const screws = [[70, 70], [70, 350], [960, 70], [960, 350]].map(([x, y]) => `<circle cx="${x}" cy="${y}" r="6" fill="url(#metalLight)" opacity=".7"/><path d="M${x - 3} ${y} H${x + 3}" stroke="#2a2733" stroke-width="1.5"/>`).join('');
  const ports = [70, 130, 190, 250, 320].map((y, i) => `<rect x="10" y="${y}" width="18" height="${i === 4 ? 36 : 42}" rx="3" fill="#0b0a0e" stroke="rgba(255,255,255,.2)"/>`).join('');
  return `<svg id="gpu" viewBox="0 0 1000 420" width="1000" height="420" xmlns="http://www.w3.org/2000/svg" overflow="visible">
<ellipse cx="510" cy="470" rx="470" ry="30" fill="rgba(0,0,0,.6)" filter="url(#glowBig)"/>
<rect x="0" y="30" width="40" height="370" rx="4" fill="url(#metalLight)"/>${ports}
<rect x="40" y="22" width="940" height="20" rx="6" fill="url(#metal)"/>
<rect class="lit" x="120" y="30" width="760" height="4" rx="2" fill="url(#ledH)" filter="url(#glow)"/>
<path d="M40 42 H940 L980 82 V340 L940 392 H40 Z" fill="url(#gpuBody)" stroke="rgba(255,255,255,.14)" stroke-width="2"/>
<path d="M40 42 H380 L340 92 H40 Z" fill="rgba(255,255,255,.05)"/>
<path d="M640 392 L700 330 H980 V340 L940 392 Z" fill="rgba(255,255,255,.04)"/>
<path d="M60 380 H920" stroke="url(#metalLight)" stroke-width="3" opacity=".45"/>
<path d="M980 100 V320" stroke="url(#led)" stroke-width="4" class="lit" filter="url(#glow)"/>
${screws}
${[220, 510, 800].map((x, i) => `<circle cx="${x}" cy="211" r="132" fill="#09080c" stroke="rgba(255,255,255,.1)" stroke-width="2"/>
  <g transform="translate(${x} 211) scale(1.12)">${fan('gf' + i)}</g>`).join('')}
<text class="lit" x="900" y="74" text-anchor="end" font-family="Geist" font-weight="600" font-size="22" letter-spacing="8" fill="#ffe6f8" filter="url(#glow)">AZOR</text>
<path d="M380 42 L340 92 M640 392 L700 330" stroke="rgba(255,255,255,.12)" stroke-width="2"/>
</svg>`;
}
export function gpuUpdate(root, s) {
  const p = s.power ?? 1;
  root.querySelectorAll('.lit').forEach(e => { e.style.opacity = .12 + .88 * p; });
  ['gf0', 'gf1', 'gf2'].forEach((id, i) => { const g = root.querySelector('#' + id); if (g) g.setAttribute('transform', `rotate(${(s.ang * 180 / Math.PI + i * 23).toFixed(2)})`); });
}
