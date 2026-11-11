// Visual "natural" para as notícias: fundo claro, texto preto, marca-texto rosa e ícones chapados.
export const NAT_CSS = `
@font-face{font-family:Geist;font-weight:400;src:url(/node_modules/@fontsource/geist/files/geist-latin-400-normal.woff2)}
@font-face{font-family:Geist;font-weight:500;src:url(/node_modules/@fontsource/geist/files/geist-latin-500-normal.woff2)}
@font-face{font-family:Geist;font-weight:600;src:url(/node_modules/@fontsource/geist/files/geist-latin-600-normal.woff2)}
@font-face{font-family:Geist;font-weight:700;src:url(/node_modules/@fontsource/geist/files/geist-latin-700-normal.woff2)}
*{box-sizing:border-box;margin:0;padding:0}
.n{position:relative;overflow:hidden;background:#f5f3ef;color:#151316;font-family:Geist,sans-serif;-webkit-font-smoothing:antialiased}
.n .hd{position:absolute;left:64px;right:64px;display:flex;align-items:center;gap:20px}
.n .hd img{width:76px;height:76px;border-radius:50%;background:#151316;padding:10px}
.n .hd b{display:block;font:700 32px Geist;letter-spacing:-.01em}
.n .hd span{display:block;font:400 26px Geist;color:#6f6a70;margin-top:2px}
.n .hd .dt{margin-left:auto;font:500 24px Geist;color:#6f6a70}
.n .tg{position:absolute;left:64px;display:inline-block;font:600 24px Geist;padding:10px 20px;border-radius:999px;background:#151316;color:#f5f3ef}
.n h1{position:absolute;left:64px;right:64px;font-weight:700;letter-spacing:-.035em;line-height:1.04}
.n mark{background:linear-gradient(transparent 52%,#ff9fe3 52%,#ff9fe3 92%,transparent 92%);color:inherit;padding:0 .06em}
.n .ic{position:absolute}
.n ol{position:absolute;left:64px;right:64px;list-style:none;display:flex;flex-direction:column}
.n li{display:flex;gap:22px;align-items:flex-start;font:500 34px/1.3 Geist;letter-spacing:-.01em;padding:22px 0;border-top:2px solid #e2ded8}
.n li:first-child{border-top:none}
.n li i{flex:none;font:700 26px Geist;font-style:normal;width:46px;height:46px;border-radius:50%;background:#ff4fcf;color:#fff;display:flex;align-items:center;justify-content:center;margin-top:2px}
.n .src{position:absolute;left:64px;right:64px;font:400 22px/1.35 Geist;color:#8a858b}
.n .ft{position:absolute;left:64px;right:64px;display:flex;justify-content:space-between;font:500 24px Geist;color:#151316}
.n .ft span:last-child{color:#c2189a}
`;
const STROKE = '#151316', PINK = '#ff4fcf';
export const ICON = {
  shield: () => `<svg viewBox="0 0 300 340" width="300" height="340"><path d="M150 14 L276 62 V160 C276 248 222 302 150 328 C78 302 24 248 24 160 V62 Z" fill="${PINK}" stroke="${STROKE}" stroke-width="10" stroke-linejoin="round"/>
    <rect x="98" y="150" width="104" height="86" rx="16" fill="#fff" stroke="${STROKE}" stroke-width="10"/><path d="M120 150 V124 A30 30 0 0 1 180 124 V150" fill="none" stroke="${STROKE}" stroke-width="10" stroke-linecap="round"/>
    <circle cx="150" cy="186" r="10" fill="${STROKE}"/><rect x="146" y="190" width="8" height="24" rx="4" fill="${STROKE}"/></svg>`,
  gpu: () => `<svg viewBox="0 0 460 230" width="460" height="230"><rect x="40" y="20" width="410" height="180" rx="22" fill="#fff" stroke="${STROKE}" stroke-width="10"/>
    <rect x="8" y="30" width="32" height="170" rx="6" fill="#d9d4cd" stroke="${STROKE}" stroke-width="8"/>
    ${[130, 245, 360].map(x => `<g class="fan" data-x="${x}"><circle cx="${x}" cy="110" r="56" fill="${PINK}" stroke="${STROKE}" stroke-width="9"/><g class="bl" transform="rotate(0 ${x} 110)">${[0, 72, 144, 216, 288].map(a => `<path d="M${x} 110 L${x + 40 * Math.cos(a * Math.PI / 180)} ${110 + 40 * Math.sin(a * Math.PI / 180)}" stroke="${STROKE}" stroke-width="7" stroke-linecap="round"/>`).join('')}</g><circle cx="${x}" cy="110" r="12" fill="${STROKE}"/></g>`).join('')}
    <path d="M80 200 v20 h60 v-20 M170 200 v20 h200 v-20" fill="none" stroke="${STROKE}" stroke-width="8" stroke-linejoin="round"/></svg>`,
  cal: () => `<svg viewBox="0 0 300 320" width="300" height="320"><rect x="14" y="40" width="272" height="266" rx="28" fill="#fff" stroke="${STROKE}" stroke-width="10"/>
    <path d="M14 112 V68 A28 28 0 0 1 42 40 H258 A28 28 0 0 1 286 68 V112 Z" fill="${PINK}" stroke="${STROKE}" stroke-width="10" stroke-linejoin="round"/>
    <rect x="76" y="14" width="18" height="54" rx="9" fill="${STROKE}"/><rect x="206" y="14" width="18" height="54" rx="9" fill="${STROKE}"/>
    <text x="150" y="94" text-anchor="middle" font-family="Geist" font-weight="700" font-size="30" fill="${STROKE}">NOV</text>
    <text class="day" x="150" y="262" text-anchor="middle" font-family="Geist" font-weight="700" font-size="138" letter-spacing="-6" fill="${STROKE}">19</text></svg>`,
  cpu: () => { const p = []; for (let i = 0; i < 6; i++) { const q = 86 + i * 26; p.push(`<path d="M${q} 18 v34 M${q} 248 v34 M18 ${q} h34 M248 ${q} h34" stroke="${STROKE}" stroke-width="10" stroke-linecap="round"/>`); }
    return `<svg viewBox="0 0 300 300" width="300" height="300">${p.join('')}<rect x="52" y="52" width="196" height="196" rx="24" fill="#fff" stroke="${STROKE}" stroke-width="10"/>
    <rect class="die" x="92" y="92" width="116" height="116" rx="14" fill="${PINK}" stroke="${STROKE}" stroke-width="9"/><text x="150" y="160" text-anchor="middle" font-family="Geist" font-weight="700" font-size="30" fill="${STROKE}">18A-P</text></svg>`; },
};
export const AVATAR = '/web/assets/Azor_icon.png';
export function header(top) {
  return `<div class="hd" style="top:${top}px"><img src="${AVATAR}"><div><b>Azor Tweaks</b><span>@azortweaks · @azorwrld</span></div><div class="dt">nov. 2026</div></div>`;
}
// converte o destaque <em> das manchetes em marca-texto e tira as quebras '|'
export const plain = h => h.replace(/<em>/g, '<mark>').replace(/<\/em>/g, '</mark>');
