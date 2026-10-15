// Peças extras da campanha 2D: celular com o site real, balões de conversa, pente de RAM, teclas, chave e gráfico.
import {W, H, ease, prog, lerp, clamp, hash, $, el} from '/kit.js';

const CSS = `
.phone{position:absolute;left:0;top:0;width:520px;height:1060px;border-radius:78px;z-index:22;transform-origin:50% 50%;
  background:linear-gradient(150deg,#3a3442,#141218 40%,#24202b 70%,#0d0c10);padding:16px;
  box-shadow:0 0 0 2px rgba(255,255,255,.12),inset 0 0 0 2px rgba(255,255,255,.08),0 80px 160px rgba(0,0,0,.8),0 0 140px rgba(255,47,200,.22)}
.phone .scr{position:relative;width:488px;height:1028px;border-radius:64px;overflow:hidden;background:#0b0709}
.phone .scr img{position:absolute;left:0;top:0;width:488px}
.phone .isl{position:absolute;left:50%;top:30px;width:150px;height:42px;margin-left:-75px;border-radius:24px;background:#000;z-index:3}
.phone .gl{position:absolute;inset:0;border-radius:64px;z-index:2;background:linear-gradient(115deg,rgba(255,255,255,0) 35%,rgba(255,255,255,.10) 45%,rgba(255,255,255,0) 55%);background-size:300% 100%}
.bub{position:absolute;max-width:760px;padding:26px 34px 28px;border-radius:40px;font:500 40px/1.18 Geist;letter-spacing:-.02em;z-index:45;transform-origin:0 100%}
.bub small{display:block;font:500 20px GeistMono;letter-spacing:.24em;text-transform:uppercase;margin-bottom:10px;opacity:.6}
.bub.me{left:84px;background:rgba(255,255,255,.08);border:1.5px solid rgba(255,255,255,.12);border-bottom-left-radius:12px;color:#f7f3fa;backdrop-filter:blur(14px)}
.bub.az{right:84px;background:linear-gradient(135deg,#ff3fcf,#b44dff);color:#fff;border-bottom-right-radius:12px;transform-origin:100% 100%;box-shadow:0 20px 60px rgba(255,47,200,.35)}
.bub.az small{opacity:.85}
.bub .tag{display:inline-block;font:600 18px GeistMono;letter-spacing:.16em;padding:6px 12px;border-radius:12px;background:rgba(0,0,0,.22);margin-left:12px;vertical-align:2px}
.chip{position:absolute;padding:16px 26px;border-radius:999px;font:500 26px GeistMono;letter-spacing:.06em;color:#ffe6f8;z-index:46;
  background:rgba(255,47,200,.12);border:1.5px solid rgba(255,120,225,.45);box-shadow:0 0 40px rgba(255,47,200,.2);white-space:nowrap}
.note{position:absolute;left:84px;right:84px;font:500 20px GeistMono;letter-spacing:.2em;color:rgba(247,243,250,.45);text-transform:uppercase;z-index:50}
`;
let styled = false;
function style() { if (styled) return; styled = true; const s = document.createElement('style'); s.textContent = CSS; document.head.appendChild(s); }

// celular com uma captura real dentro; scroll em px da tela do celular
export function phone(src) {
  style();
  const e = el('div', 'phone', $('stage'), `<div class="scr"><img src="${src}"><div class="gl"></div><div class="isl"></div></div>`);
  const img = e.querySelector('img'), gl = e.querySelector('.gl');
  e.set = ({x = 540, y = 960, s = 1, ry = 0, rz = 0, scroll = 0, o = 1, shine = -1, blur = 0}) => {
    e.style.visibility = o > .002 ? 'visible' : 'hidden';
    e.style.transform = `translate(${x - 260}px,${y - 530}px) perspective(1800px) rotateY(${ry}deg) rotateZ(${rz}deg) scale(${s})`;
    e.style.opacity = o; img.style.transform = `translateY(${-scroll}px)`;
    gl.style.backgroundPosition = `${lerp(130, -30, clamp(shine))}% 0`; e.style.filter = blur > .05 ? `blur(${blur}px)` : 'none';
  };
  return e;
}

// balão de conversa (lado "me" ou "az")
export function bubble(side, html, top) {
  style();
  const e = el('div', 'bub ' + side, $('stage'), html); e.style.top = top + 'px';
  e.anim = (t, t0, t1, dy = 0) => {
    const v = t >= t0 && t < t1 + .4; e.style.visibility = v ? 'visible' : 'hidden'; if (!v) return;
    const k = ease.back(prog(t, t0, t0 + .45)), o = ease.in(prog(t, t1, t1 + .4));
    e.style.transform = `translateY(${dy + (1 - k) * 40}px) scale(${lerp(.6, 1, k)})`; e.style.opacity = clamp(prog(t, t0, t0 + .15)) * (1 - o);
    e.style.filter = o > 0 ? `blur(${o * 8}px)` : 'none';
  };
  return e;
}
export function chip(html, {top, left = 84}) {
  style();
  const e = el('div', 'chip', $('stage'), html); Object.assign(e.style, {top: top + 'px', left: left + 'px'});
  e.anim = (t, t0, t1) => { const v = t >= t0 && t < t1 + .4; e.style.visibility = v ? 'visible' : 'hidden'; if (!v) return;
    const k = ease.expo(prog(t, t0, t0 + .7)), o = prog(t, t1, t1 + .4); e.style.opacity = k * (1 - o); e.style.transform = `translateY(${(1 - k) * 30}px)`; };
  return e;
}
export function note(text, top) {
  style();
  const e = el('div', 'note', $('stage'), text); e.style.top = top + 'px';
  e.anim = (t, t0, t1) => { e.style.opacity = .9 * ease.out(prog(t, t0, t0 + .5)) * (1 - prog(t, t1, t1 + .3)); };
  return e;
}

// pente de memória visto de frente (900 x 260)
export function ramSVG(id = 'ram') {
  const chips = Array.from({length: 8}, (_, i) => `<rect x="${96 + i * 92}" y="112" width="70" height="56" rx="4" fill="#0c0b10" stroke="rgba(255,255,255,.08)"/>`).join('');
  const pins = Array.from({length: 120}, (_, i) => i === 62 ? '' : `<rect x="${32 + i * 7}" y="226" width="4.6" height="26" rx="1" fill="url(#${id}Gold)"/>`).join('');
  const fins = Array.from({length: 26}, (_, i) => `<path d="M${70 + i * 30} 22 l14 -16 h12 l-14 16 z" fill="rgba(255,255,255,.05)"/>`).join('');
  return `<svg viewBox="0 0 900 270" width="900" height="270" xmlns="http://www.w3.org/2000/svg" overflow="visible">
<defs>
  <linearGradient id="${id}Gold" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffe7a0"/><stop offset=".5" stop-color="#d4a640"/><stop offset="1" stop-color="#8a6a20"/></linearGradient>
  <linearGradient id="${id}Body" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3b3746"/><stop offset=".45" stop-color="#1b1922"/><stop offset="1" stop-color="#121016"/></linearGradient>
  <linearGradient id="${id}Rgb" x1="0" y1="0" x2="1" y2="0" spreadMethod="repeat"><stop offset="0" stop-color="#ff2fc8"/><stop offset=".33" stop-color="#9b5cff"/><stop offset=".66" stop-color="#ff8fe6"/><stop offset="1" stop-color="#ff2fc8"/></linearGradient>
  <filter id="${id}Glow" x="-20%" y="-200%" width="140%" height="500%"><feGaussianBlur stdDeviation="10"/></filter>
</defs>
<rect x="20" y="96" width="860" height="132" rx="6" fill="#0f2a1e"/>
<rect x="20" y="96" width="860" height="132" rx="6" fill="rgba(0,0,0,.45)"/>
${chips}${pins}
<rect x="472" y="220" width="10" height="40" fill="#07050b"/>
<path d="M20 30 Q20 18 32 18 H868 Q880 18 880 30 V196 H20 Z" fill="url(#${id}Body)" stroke="rgba(255,255,255,.14)" stroke-width="2"/>
${fins}
<path d="M40 60 L300 60 L330 90 L860 90" stroke="rgba(255,255,255,.12)" stroke-width="2" fill="none"/>
<path d="M20 196 H880" stroke="rgba(255,255,255,.1)" stroke-width="2"/>
<text x="64" y="160" font-family="Geist" font-weight="600" font-size="34" letter-spacing="10" fill="#f7f3fa" opacity=".9">AZOR</text>
<text x="66" y="186" font-family="GeistMono" font-size="16" letter-spacing="4" fill="rgba(247,243,250,.5)">DDR4 · 16 GB · 3200 MHz</text>
<g class="rgb"><rect x="30" y="-6" width="840" height="26" rx="10" fill="url(#${id}Rgb)" filter="url(#${id}Glow)" opacity=".9"/>
<rect x="30" y="-6" width="840" height="26" rx="10" fill="url(#${id}Rgb)"/>
<rect x="30" y="-6" width="840" height="9" rx="4" fill="rgba(255,255,255,.35)"/></g>
<rect class="dim" x="30" y="-6" width="840" height="26" rx="10" fill="#14111a" opacity="0"/>
</svg>`;
}
export function ramUpdate(root, {power = 1, t = 0, id = 'ram'}) {
  root.querySelector(`#${id}Rgb`).setAttribute('gradientTransform', `translate(${(t * .35 % 1).toFixed(3)} 0)`);
  root.querySelector('.dim').setAttribute('opacity', (1 - power) * .85);
}

// tecla
export function keycap(label, w = 200) {
  return `<div class="key" style="position:absolute;width:${w}px;height:130px;border-radius:26px;background:linear-gradient(180deg,#2a2631,#17151c);
    box-shadow:0 10px 0 #0b0a0e,0 14px 30px rgba(0,0,0,.6),inset 0 2px 0 rgba(255,255,255,.12);display:flex;align-items:center;justify-content:center;
    font:600 40px Geist;color:#f7f3fa;letter-spacing:-.01em">${label}</div>`;
}

// curva de frametime determinística (ms) para o gráfico
export function frametime(n, {base, jit, spikes, seed}) {
  return Array.from({length: n}, (_, i) => {
    let v = base + (hash(i * 1.7 + seed) - .5) * jit + Math.sin(i * .35 + seed) * jit * .25;
    if (spikes && hash(i * 9.1 + seed * 3) > 1 - spikes) v += 18 + hash(i + seed) * 22;
    return v;
  });
}
