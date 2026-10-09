// Kit de animação 2D da campanha: tempo, fundo cinematográfico, tipografia, efeitos e assinatura.
export const W = 1080, H = 1920;
export const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
export const lerp = (a, b, k) => a + (b - a) * k;
export const prog = (t, a, b) => clamp((t - a) / (b - a));
export const ease = {
  out: k => 1 - Math.pow(1 - k, 3), in: k => k * k * k, io: k => k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2,
  expo: k => k >= 1 ? 1 : 1 - Math.pow(2, -10 * k), sine: k => -(Math.cos(Math.PI * k) - 1) / 2,
  back: k => { const c = 1.6; return 1 + (c + 1) * Math.pow(k - 1, 3) + c * Math.pow(k - 1, 2); },
};
export const hash = n => { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); };
export function keys(t, list, fn = ease.io) {
  if (t <= list[0].t) return {...list[0]};
  for (let i = 0; i < list.length - 1; i++) { const a = list[i], b = list[i + 1];
    if (t <= b.t) { const k = (b.ease || fn)(prog(t, a.t, b.t)); const o = {}; for (const key in a) if (key !== 't' && key !== 'ease') o[key] = lerp(a[key], b[key], k); return o; } }
  return {...list[list.length - 1]};
}
export const SFX = []; window.SFX = SFX;
export const sfx = (t, kind, v = 1, extra = {}) => SFX.push({t: +t.toFixed(3), kind, v, ...extra});
export const $ = id => document.getElementById(id);
export function el(tag, cls, parent, html = '') { const e = document.createElement(tag); if (cls) e.className = cls; if (html) e.innerHTML = html; (parent || $('stage')).appendChild(e); return e; }

const CSS = `
@font-face{font-family:Geist;font-weight:400;src:url(/node_modules/@fontsource/geist/files/geist-latin-400-normal.woff2)}
@font-face{font-family:Geist;font-weight:500;src:url(/node_modules/@fontsource/geist/files/geist-latin-500-normal.woff2)}
@font-face{font-family:Geist;font-weight:600;src:url(/node_modules/@fontsource/geist/files/geist-latin-600-normal.woff2)}
@font-face{font-family:Geist;font-weight:700;src:url(/node_modules/@fontsource/geist/files/geist-latin-700-normal.woff2)}
@font-face{font-family:GeistMono;font-weight:500;src:url(/node_modules/@fontsource/geist-mono/files/geist-mono-latin-500-normal.woff2)}
@font-face{font-family:Serif;font-style:italic;src:url(/node_modules/@fontsource/instrument-serif/files/instrument-serif-latin-400-italic.woff2)}
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:${W}px;height:${H}px;overflow:hidden;background:#000}
#stage{position:absolute;left:0;top:0;width:${W}px;height:${H}px;overflow:hidden;background:#07050b;color:#f7f3fa;font-family:Geist,sans-serif;-webkit-font-smoothing:antialiased}
#bg,#fx,#grain{position:absolute;left:0;top:0;width:${W}px;height:${H}px}
#grain{opacity:.07;mix-blend-mode:overlay;z-index:90;pointer-events:none}
#scrim{position:absolute;left:0;top:0;width:${W}px;height:820px;background:linear-gradient(180deg,rgba(5,3,9,.7),rgba(5,3,9,.35) 50%,rgba(5,3,9,0));z-index:40;pointer-events:none}
.cam{position:absolute;left:0;top:0;width:${W}px;height:${H}px;transform-origin:0 0}
.t{position:absolute;left:84px;right:84px;font-weight:600;letter-spacing:-.045em;line-height:.98;color:#f7f3fa;z-index:50}
.t .l{display:block;overflow:hidden;padding:.08em 0 .12em;margin:-.08em 0 -.12em}
.t .l>span{display:inline-block}
.t em{font-family:Serif;font-style:italic;font-weight:400;letter-spacing:-.01em;background:linear-gradient(100deg,#ff7fe0 0%,#ff7fe0 38%,#fff3fc 50%,#c79bff 62%,#ff7fe0 100%);background-size:300% 100%;-webkit-background-clip:text;background-clip:text;color:transparent;padding-right:.08em}
.lab{position:absolute;left:84px;font-family:GeistMono;font-weight:500;font-size:24px;letter-spacing:.22em;text-transform:uppercase;color:rgba(247,243,250,.62);z-index:50}
.lab b{color:#ff7fe0;font-weight:500}
#vig{position:absolute;inset:0;z-index:85;pointer-events:none;background:radial-gradient(ellipse at 50% 46%,transparent 52%,rgba(0,0,0,.55) 100%)}
#fade{position:absolute;inset:0;z-index:95;background:#000;opacity:0;pointer-events:none}
#flash{position:absolute;inset:0;z-index:94;background:radial-gradient(circle at 50% 50%,rgba(255,220,248,.9),rgba(255,120,220,.25) 40%,rgba(0,0,0,0) 70%);opacity:0;mix-blend-mode:screen;pointer-events:none}
`;
let bgc, fxc, grc, grainTiles;
export function stage(extraCss = '') {
  const st = document.createElement('style'); st.textContent = CSS + extraCss; document.head.appendChild(st);
  const s = $('stage');
  bgc = el('canvas', '', s); bgc.id = 'bg'; bgc.width = W; bgc.height = H;
  fxc = el('canvas', '', s); fxc.id = 'fx'; fxc.width = W; fxc.height = H; fxc.style.zIndex = 30;
  el('div', '', s).id = 'scrim';
  el('div', '', s).id = 'vig'; el('div', '', s).id = 'flash'; el('div', '', s).id = 'fade';
  grc = el('canvas', '', s); grc.id = 'grain'; grc.width = 540; grc.height = 960;
  grainTiles = Array.from({length: 4}, (_, i) => { const c = document.createElement('canvas'); c.width = c.height = 256; const x = c.getContext('2d'); const d = x.createImageData(256, 256);
    for (let p = 0; p < d.data.length; p += 4) { const v = hash(p * .37 + i * 999) * 255; d.data[p] = d.data[p + 1] = d.data[p + 2] = v; d.data[p + 3] = 255; } x.putImageData(d, 0, 0); return c; });
  return {bg: bgc.getContext('2d'), fx: fxc.getContext('2d')};
}
// fundo: gradiente profundo + manchas de luz + bokeh com parallax
const BOKEH = Array.from({length: 26}, (_, i) => ({x: hash(i) * W, y: hash(i + 40) * H, r: 30 + hash(i + 9) * 110, a: .03 + hash(i + 3) * .07, d: .2 + hash(i + 7) * .8, c: i % 3}));
export function background(t, {px = 0, py = 0, mood = 1, hue = 0} = {}) {
  const g = bgc.getContext('2d');
  const gr = g.createLinearGradient(0, 0, 0, H); gr.addColorStop(0, '#0d0716'); gr.addColorStop(.55, '#08050e'); gr.addColorStop(1, '#040307');
  g.fillStyle = gr; g.fillRect(0, 0, W, H);
  const blob = (x, y, r, col, a) => { const rg = g.createRadialGradient(x, y, 0, x, y, r); rg.addColorStop(0, col.replace('A', a)); rg.addColorStop(1, col.replace('A', 0)); g.fillStyle = rg; g.fillRect(x - r, y - r, r * 2, r * 2); };
  blob(780 + Math.sin(t * .3) * 60 - px * .2, 760 + Math.cos(t * .25) * 40 - py * .2, 820, 'rgba(255,47,200,A)', .16 * mood);
  blob(240 + Math.cos(t * .27) * 70 - px * .15, 1150 + Math.sin(t * .22) * 50 - py * .15, 760, 'rgba(118,80,255,A)', .15 * mood);
  blob(540 - px * .1, 300 - py * .1, 600, 'rgba(255,140,230,A)', .05 * mood);
  BOKEH.forEach(b => { const x = (b.x - px * b.d * .5 + Math.sin(t * .2 + b.x) * 20) % (W + 200), y = b.y - py * b.d * .5 + Math.cos(t * .17 + b.y) * 24;
    blob(x, y, b.r, ['rgba(255,90,215,A)', 'rgba(160,120,255,A)', 'rgba(255,220,250,A)'][b.c], b.a * mood); });
}
export function post(t, {fade = 0, flash = 0} = {}) {
  $('fade').style.opacity = fade; $('flash').style.opacity = flash;
  const g = grc.getContext('2d'); g.clearRect(0, 0, 540, 960);
  g.fillStyle = g.createPattern(grainTiles[Math.floor(t * 24) % 4], 'repeat'); g.fillRect(0, 0, 540, 960);
}
// título com linhas que sobem da máscara; destaque com brilho que corre
export function headline(html, {top, size = 104, weight = 600, left = 84, z = 50} = {}) {
  const e = el('div', 't', $('stage'));
  Object.assign(e.style, {top: top + 'px', fontSize: size + 'px', fontWeight: weight, left: left + 'px', zIndex: z});
  e.innerHTML = html.split('|').map(l => `<span class="l"><span>${l}</span></span>`).join('');
  const lines = [...e.querySelectorAll('.l>span')], ems = [...e.querySelectorAll('em')];
  e.anim = (t, t0, t1, {stagger = .09, dur = .9, out = .5} = {}) => {
    const vis = t >= t0 - .01 && t < t1 + out; e.style.visibility = vis ? 'visible' : 'hidden'; if (!vis) return;
    lines.forEach((s, i) => { const k = ease.expo(prog(t, t0 + i * stagger, t0 + i * stagger + dur)), o = ease.in(prog(t, t1, t1 + out));
      s.style.transform = `translateY(${(1 - k) * 105 - o * 18}%)`; s.style.opacity = 1 - o; s.style.filter = o > 0 ? `blur(${o * 10}px)` : 'none'; });
    ems.forEach(m => { m.style.backgroundPosition = `${lerp(110, -10, ease.io(prog(t, t0 + .3, t0 + 1.8)))}% 0`; });
  };
  return e;
}
export function label(html, {top, left = 84} = {}) {
  const e = el('div', 'lab', $('stage'), html); Object.assign(e.style, {top: top + 'px', left: left + 'px'});
  e.anim = (t, t0, t1) => { const k = ease.out(prog(t, t0, t0 + .6)), o = prog(t, t1, t1 + .4);
    e.style.visibility = t >= t0 && t < t1 + .4 ? 'visible' : 'hidden'; e.style.opacity = k * (1 - o); e.style.letterSpacing = `${lerp(.4, .22, k)}em`; };
  return e;
}
// efeitos no canvas fx (coordenadas de tela)
export function ring(g, x, y, k, {r0 = 20, r1 = 900, col = '255,110,225', w = 6} = {}) {
  if (k <= 0 || k >= 1) return;
  const r = lerp(r0, r1, ease.out(k));
  g.save(); g.globalCompositeOperation = 'lighter';
  g.strokeStyle = `rgba(${col},${(1 - k) * .9})`; g.lineWidth = w * (1 - k * .6); g.shadowColor = `rgba(${col},1)`; g.shadowBlur = 30;
  g.beginPath(); g.arc(x, y, r, 0, 6.283); g.stroke(); g.restore();
}
export function sparkles(g, t, t0, x, y, {n = 26, spread = 260, dur = 1.4, seed = 1} = {}) {
  const k = prog(t, t0, t0 + dur); if (k <= 0 || k >= 1) return;
  g.save(); g.globalCompositeOperation = 'lighter';
  for (let i = 0; i < n; i++) {
    const a = hash(i * 3.1 + seed) * 6.283, sp = spread * (.4 + hash(i + seed * 7) * .8), kk = ease.out(k);
    const px = x + Math.cos(a) * sp * kk, py = y + Math.sin(a) * sp * kk - k * k * 40;
    const s = (3 + hash(i + 5) * 7) * (1 - k);
    g.fillStyle = `rgba(255,${200 + hash(i) * 55 | 0},250,${1 - k})`; g.shadowColor = '#ff6fe0'; g.shadowBlur = 16;
    g.beginPath(); g.moveTo(px, py - s * 2); g.lineTo(px + s * .5, py); g.lineTo(px, py + s * 2); g.lineTo(px - s * .5, py); g.closePath(); g.fill();
    g.beginPath(); g.moveTo(px - s * 2, py); g.lineTo(px, py + s * .5); g.lineTo(px + s * 2, py); g.lineTo(px, py - s * .5); g.closePath(); g.fill();
  }
  g.restore();
}
// assinatura final
export function lockup(tagline) {
  const e = el('div', '', $('stage'));
  e.id = 'lock';
  e.innerHTML = `<div class="lk-glow"></div><img class="lk-ic" src="/web/assets/Azor_icon.png"><div class="lk-w">AZOR</div><div class="lk-s">OPTIMIZATION</div><div class="lk-t">${tagline}</div>
    <div class="lk-soc"><span><svg viewBox="0 0 24 24"><path fill="currentColor" d="M16.6 5.82A4.28 4.28 0 0 1 15.54 3h-3.09v12.4a2.59 2.59 0 0 1-2.59 2.5 2.6 2.6 0 0 1-2.6-2.6 2.6 2.6 0 0 1 3.4-2.47V9.67a5.73 5.73 0 0 0-.81-.06 5.69 5.69 0 0 0-5.69 5.69A5.69 5.69 0 0 0 9.85 21a5.69 5.69 0 0 0 5.69-5.69V9.01a7.35 7.35 0 0 0 4.3 1.38V7.3a4.3 4.3 0 0 1-3.24-1.48z"/></svg>@azorwrld</span>
    <span><svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="5.2" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="12" r="4.1" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="17.2" cy="6.8" r="1.2" fill="currentColor"/></svg>@azortweaks</span></div><div class="lk-b">Link na bio</div>`;
  const st = document.createElement('style');
  st.textContent = `#lock{position:absolute;inset:0;z-index:80;visibility:hidden;background:radial-gradient(ellipse at 50% 46%,#1c0a24 0%,#0a0610 55%,#040307 100%)}
    #lock .lk-glow{position:absolute;left:190px;top:470px;width:700px;height:700px;border-radius:50%;background:radial-gradient(circle,rgba(255,47,200,.28),rgba(120,70,255,.08) 45%,transparent 70%)}
    #lock .lk-ic{position:absolute;left:440px;top:560px;width:200px;height:200px;border-radius:46px;box-shadow:0 0 80px rgba(255,47,200,.45)}
    #lock .lk-w{position:absolute;left:0;right:0;top:810px;text-align:center;font:600 100px Geist;letter-spacing:.34em;padding-left:.34em}
    #lock .lk-s{position:absolute;left:0;right:0;top:938px;text-align:center;font:500 26px GeistMono;letter-spacing:.5em;padding-left:.5em;color:rgba(247,243,250,.5)}
    #lock .lk-t{position:absolute;left:60px;right:60px;top:1040px;text-align:center;font:400 78px/1.1 Serif;font-style:italic;color:#ffd6f4}
    #lock .lk-soc{position:absolute;left:0;right:0;top:1240px;display:flex;justify-content:center;gap:48px;font:500 34px GeistMono;color:rgba(247,243,250,.85)}
    #lock .lk-soc span{display:flex;align-items:center;gap:14px}#lock .lk-soc svg{width:40px;height:40px}
    #lock .lk-b{position:absolute;left:0;right:0;top:1330px;text-align:center;font:500 24px GeistMono;letter-spacing:.42em;padding-left:.42em;text-transform:uppercase;color:rgba(247,243,250,.42)}`;
  document.head.appendChild(st);
  const q = s => e.querySelector(s);
  e.anim = t0 => t => {
    const v = t >= t0; e.style.visibility = v ? 'visible' : 'hidden'; if (!v) return;
    e.style.opacity = ease.out(prog(t, t0, t0 + .5));
    const k1 = ease.back(prog(t, t0 + .1, t0 + .9)); q('.lk-ic').style.transform = `scale(${lerp(.6, 1, k1)})`; q('.lk-ic').style.opacity = clamp((t - t0 - .1) * 4);
    q('.lk-glow').style.transform = `scale(${1 + .06 * Math.sin((t - t0) * 2.4)})`;
    const k2 = ease.expo(prog(t, t0 + .3, t0 + 1.4)); q('.lk-w').style.opacity = k2; q('.lk-w').style.letterSpacing = `${lerp(.6, .34, k2)}em`;
    q('.lk-s').style.opacity = ease.out(prog(t, t0 + .55, t0 + 1.3)) * .9;
    const k3 = ease.expo(prog(t, t0 + .7, t0 + 1.7)); q('.lk-t').style.opacity = k3; q('.lk-t').style.transform = `translateY(${(1 - k3) * 24}px)`; q('.lk-t').style.filter = `blur(${(1 - k3) * 8}px)`;
    q('.lk-soc').style.opacity = ease.out(prog(t, t0 + 1.05, t0 + 1.8)); q('.lk-b').style.opacity = ease.out(prog(t, t0 + 1.3, t0 + 2));
  };
  return e;
}
export async function ready() {
  await Promise.all(['400 40px Geist', '500 40px Geist', '600 40px Geist', '700 40px Geist', '500 40px GeistMono', 'italic 40px Serif'].map(f => document.fonts.load(f, 'AaÁçã')));
  await document.fonts.ready;
  await Promise.all([...document.images].map(i => i.decode().catch(() => {})));
  await Promise.all([...document.querySelectorAll('image')].map(i => new Promise(r => { const im = new Image(); im.onload = im.onerror = r; im.src = i.getAttribute('href'); })));
}
