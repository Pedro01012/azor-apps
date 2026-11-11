// Notícias de tecnologia (novembro de 2026) usadas nos posts e vídeos. Só fatos confirmados em mais de uma fonte.
export const STORIES = [
  {
    id: 'hvci', tag: 'WINDOWS 11', art: 'shield',
    head: 'O Windows está ligando|um recurso que pode|<em>pesar no FPS.</em>',
    vhead: ['O Windows ligou|sozinho um recurso|que pode <em>pesar no FPS.</em>'],
    facts: ['A Integridade da memória está sendo ligada automaticamente em PCs compatíveis desde outubro',
      'Pode reduzir o FPS em jogos que puxam o processador, mais em CPUs antigas',
      'Ela protege contra drivers maliciosos, e alguns jogos exigem ela ligada'],
    path: ['Segurança do Windows', 'Segurança do dispositivo', 'Isolamento de núcleo', 'Integridade da memória'],
    take: 'Teste o jogo com e sem.|Desligar é escolha <em>sua.</em>',
    src: 'Fontes: Microsoft, via Tom\'s Hardware, PCWorld e TechRadar',
  },
  {
    id: 'gpu', tag: 'PLACAS DE VÍDEO', art: 'gpu',
    head: 'Placa de vídeo|ficou <em>mais cara.</em>',
    vhead: ['Placa de vídeo|ficou <em>mais cara.</em>'],
    facts: ['RTX 50: preço mediano subiu até 40% de junho a agosto na Newegg (EUA)',
      'O motivo é a falta de memória: os data centers de IA estão comprando a DRAM',
      'Fabricantes avisam que as placas de entrada devem ficar ainda mais escassas'],
    take: 'Antes de trocar a sua,|tire <em>tudo</em> dela.',
    src: 'Fontes: Tom\'s Hardware, TechSpot e Jon Peddie Research',
  },
  {
    id: 'gta', tag: 'GAMES', art: 'cal',
    head: 'GTA VI chega em|<em>19 de novembro.</em>',
    vhead: ['GTA VI chega em|<em>19 de novembro.</em>'],
    facts: ['Lançamento no PS5 e no Xbox Series X|S',
      'A versão para PC ainda não foi anunciada',
      'A data foi confirmada pela Rockstar e pela Take-Two'],
    take: 'Enquanto o PC não chega,|deixa o seu <em>no ponto.</em>',
    src: 'Fontes: Rockstar Games e Take-Two, via PCWorld e TechRadar',
  },
  {
    id: 'intel', tag: 'PROCESSADORES', art: 'cpu',
    head: 'Intel diz que o Nova Lake|está <em>adiantado.</em>',
    vhead: ['Intel diz que o|Nova Lake está|<em>adiantado.</em>'],
    facts: ['Vai ser o primeiro processador de PC feito no processo 18A-P',
      '18A-P: até 9% mais desempenho na mesma energia que o 18A (dado do processo, não do chip)',
      'Detalhes prometidos para a CES, em janeiro de 2027. Data e desempenho ainda não saíram'],
    take: 'Até lá, o melhor upgrade|é o que você <em>já tem.</em>',
    src: 'Fonte: Intel (resultados de 29/10), via Guru3D e Mixed',
  },
];

// ilustrações
export function shieldSVG() {
  return `<svg viewBox="0 0 400 460" width="400" height="460" xmlns="http://www.w3.org/2000/svg" overflow="visible">
<defs><linearGradient id="shG" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#3a2a48"/><stop offset="1" stop-color="#120c18"/></linearGradient>
<linearGradient id="shL" x1="0" x2="1"><stop offset="0" stop-color="#ff3fcf"/><stop offset="1" stop-color="#b44dff"/></linearGradient>
<filter id="shGl" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="14"/></filter></defs>
<path class="glow" d="M200 20 L360 80 V220 C360 330 290 400 200 440 C110 400 40 330 40 220 V80 Z" fill="none" stroke="url(#shL)" stroke-width="16" filter="url(#shGl)" opacity=".8"/>
<path d="M200 20 L360 80 V220 C360 330 290 400 200 440 C110 400 40 330 40 220 V80 Z" fill="url(#shG)" stroke="url(#shL)" stroke-width="8"/>
<path d="M200 60 L325 107 V220 C325 305 270 360 200 395 Z" fill="rgba(255,255,255,.05)"/>
<g transform="translate(200 210)"><rect x="-70" y="-30" width="140" height="110" rx="18" fill="#1d1426" stroke="rgba(255,255,255,.25)" stroke-width="4"/>
<path d="M-42 -30 V-62 A42 42 0 0 1 42 -62 V-30" fill="none" stroke="rgba(255,255,255,.75)" stroke-width="14" stroke-linecap="round"/>
<circle cx="0" cy="20" r="14" fill="#ff7fe0"/><rect x="-5" y="22" width="10" height="34" rx="5" fill="#ff7fe0"/></g>
</svg>`;
}
export function cpuSVG() {
  const pins = []; for (let i = 0; i < 14; i++) { const p = 64 + i * 20; pins.push(`<rect x="${p}" y="10" width="8" height="26" rx="2" fill="url(#cpG)"/><rect x="${p}" y="364" width="8" height="26" rx="2" fill="url(#cpG)"/><rect x="10" y="${p}" width="26" height="8" rx="2" fill="url(#cpG)"/><rect x="364" y="${p}" width="26" height="8" rx="2" fill="url(#cpG)"/>`); }
  const grid = []; for (let r = 0; r < 6; r++) for (let c = 0; c < 6; c++) grid.push(`<rect class="core" data-i="${r * 6 + c}" x="${118 + c * 28}" y="${118 + r * 28}" width="22" height="22" rx="4" fill="#ff5fd8" opacity=".15"/>`);
  return `<svg viewBox="0 0 400 400" width="400" height="400" xmlns="http://www.w3.org/2000/svg" overflow="visible">
<defs><linearGradient id="cpG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffe7a0"/><stop offset="1" stop-color="#b08a30"/></linearGradient>
<linearGradient id="cpB" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#4a4456"/><stop offset=".5" stop-color="#25212d"/><stop offset="1" stop-color="#3a3444"/></linearGradient>
<filter id="cpGl" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="16"/></filter></defs>
${pins.join('')}
<rect x="36" y="36" width="328" height="328" rx="22" fill="#0f2a1e" stroke="rgba(255,255,255,.12)" stroke-width="2"/>
<rect x="70" y="70" width="260" height="260" rx="18" fill="url(#cpB)" stroke="rgba(255,255,255,.25)" stroke-width="3"/>
<rect class="glow" x="100" y="100" width="200" height="200" rx="14" fill="#ff2fc8" opacity=".25" filter="url(#cpGl)"/>
<rect x="100" y="100" width="200" height="200" rx="14" fill="#0c0a10" stroke="rgba(255,120,225,.5)" stroke-width="3"/>
${grid.join('')}
<text x="200" y="352" text-anchor="middle" font-family="GeistMono" font-size="16" letter-spacing="6" fill="rgba(247,243,250,.55)">18A-P</text>
</svg>`;
}
export function calHTML() {
  return `<div class="cal"><div class="cal-top">NOVEMBRO · 2026</div><div class="cal-d">19</div><div class="cal-b">QUINTA-FEIRA</div></div>`;
}
export const ART_CSS = `
.cal{width:380px;height:420px;border-radius:44px;overflow:hidden;background:linear-gradient(160deg,#2a1c34,#110b16);border:2px solid rgba(255,255,255,.14);
  box-shadow:0 50px 120px rgba(0,0,0,.7),0 0 120px rgba(255,47,200,.3);text-align:center}
.cal-top{height:96px;line-height:96px;background:linear-gradient(90deg,#ff3fcf,#b44dff);font:600 26px GeistMono;letter-spacing:.24em;color:#fff}
.cal-d{font:600 230px/1 Geist;letter-spacing:-.06em;margin-top:24px;color:#f7f3fa}
.cal-b{font:500 22px GeistMono;letter-spacing:.3em;color:rgba(247,243,250,.55);margin-top:10px}
`;
