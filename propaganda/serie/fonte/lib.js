/* Biblioteca compartilhada da série de propagandas do AZOR (1080×1920).
   Cada vídeo define cenas e chama: AZ.caps(...), AZ.endCard(...), AZ.game(...), sfx(...). */
'use strict';
const W = 1080, H = 1920;
const $ = id => document.getElementById(id);
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const lerp = (a, b, k) => a + (b - a) * k;
const prog = (t, a, b) => clamp((t - a) / (b - a));
const eOut = k => 1 - Math.pow(1 - k, 3);
const eIn = k => k * k * k;
const eIO = k => k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
const eBack = (k, c1 = 1.7) => { const c3 = c1 + 1; return 1 + c3 * Math.pow(k - 1, 3) + c1 * Math.pow(k - 1, 2); };
const hash = n => { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); };
const smooth = (seed, t, f) => { const x = t * f, i = Math.floor(x), k = x - i, u = k * k * (3 - 2 * k);
  return (hash(i + seed * 101) * (1 - u) + hash(i + 1 + seed * 101) * u) * 2 - 1; };
const between = (t, a, b) => t >= a && t < b;

/* ---------- efeitos sonoros e música (lidos pelo audio.py) ---------- */
const SFX = [];
const sfx = (t, kind, v = 1, extra = {}) => SFX.push({t: +t.toFixed(3), kind, v, ...extra});
const music = (t, style, end, extra = {}) => SFX.push({t: +t.toFixed(3), kind: 'music', style, end, v: 1, ...extra});
window.SFX = SFX;

/* ---------- DOM ---------- */
function mk(tag, attrs = {}, parent = null, html = '') {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'style' && typeof v === 'object') Object.assign(e.style, v); else e.setAttribute(k, v);
  }
  if (html) e.innerHTML = html;
  if (parent) parent.appendChild(e);
  return e;
}
function show(e, a) { e.style.opacity = a; e.style.visibility = a > 0.003 ? 'visible' : 'hidden'; }

const ICONS = `<svg width="0" height="0" style="position:absolute"><defs>
<symbol id="tt" viewBox="0 0 24 24"><path fill="currentColor" d="M16.6 5.82A4.28 4.28 0 0 1 15.54 3h-3.09v12.4a2.59 2.59 0 0 1-2.59 2.5 2.6 2.6 0 0 1-2.6-2.6 2.6 2.6 0 0 1 3.4-2.47V9.67a5.73 5.73 0 0 0-.81-.06 5.69 5.69 0 0 0-5.69 5.69A5.69 5.69 0 0 0 9.85 21a5.69 5.69 0 0 0 5.69-5.69V9.01a7.35 7.35 0 0 0 4.3 1.38V7.3a4.3 4.3 0 0 1-3.24-1.48z"/></symbol>
<symbol id="ig" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="5.2" fill="none" stroke="currentColor" stroke-width="2.1"/><circle cx="12" cy="12" r="4.1" fill="none" stroke="currentColor" stroke-width="2.1"/><circle cx="17.2" cy="6.8" r="1.25" fill="currentColor"/></symbol>
<symbol id="bolt" viewBox="0 0 24 24"><path d="M13 2 4.5 13.5H11L10 22l8.5-11.5H12z" fill="currentColor"/></symbol>
<symbol id="check" viewBox="0 0 24 24"><path d="m5 12.5 4.5 4.5L19 7.5" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="xmark" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></symbol>
</defs></svg>`;

const BASE_CSS = `
@font-face{font-family:Anton;src:url(node_modules/@fontsource/anton/files/anton-latin-400-normal.woff2)}
@font-face{font-family:Mont;font-weight:800;src:url(node_modules/@fontsource/montserrat/files/montserrat-latin-800-normal.woff2)}
@font-face{font-family:Mont;font-weight:900;src:url(node_modules/@fontsource/montserrat/files/montserrat-latin-900-normal.woff2)}
@font-face{font-family:Orb;font-weight:900;src:url(node_modules/@fontsource/orbitron/files/orbitron-latin-900-normal.woff2)}
@font-face{font-family:Orb;font-weight:700;src:url(node_modules/@fontsource/orbitron/files/orbitron-latin-700-normal.woff2)}
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1080px;height:1920px;overflow:hidden;background:#07060a}
body{font-family:"Inter Display","Inter","Noto Color Emoji",sans-serif;color:#fff;-webkit-font-smoothing:antialiased}
#stage{position:absolute;left:0;top:0;width:1080px;height:1920px;overflow:hidden;background:#07060a}
.abs{position:absolute}
.cap{position:absolute;left:60px;right:60px;text-align:center;font-family:Mont,"Noto Color Emoji";font-weight:900;font-size:74px;line-height:1.08;
  text-transform:uppercase;letter-spacing:-.5px;z-index:50;pointer-events:none}
.cap span{display:inline-block;margin:0 9px;color:#fff;-webkit-text-stroke:9px #000;paint-order:stroke fill;
  text-shadow:0 8px 0 rgba(0,0,0,.55),0 0 30px rgba(0,0,0,.5)}
.cap span.on{color:#ffe14d}
.cap span.pk{color:#ff3fd0}.cap span.gr{color:#3dff9a}.cap span.rd{color:#ff4155}
.tbox{position:absolute;left:0;right:0;text-align:center;z-index:50}
.tbox span{display:inline-block;background:#fff;color:#111;font:700 50px/1.2 "Inter","Noto Color Emoji";padding:8px 22px;border-radius:14px;margin:4px 0;
  box-shadow:0 4px 18px rgba(0,0,0,.35)}
.dram{position:absolute;left:30px;bottom:26px;font:600 22px Inter;color:rgba(255,255,255,.55);z-index:60;letter-spacing:.3px}
#end{position:absolute;inset:0;z-index:80;visibility:hidden;background:radial-gradient(ellipse at 50% 42%,#2a0d33 0%,#0c0710 60%,#050407 100%)}
#end .lg{position:absolute;left:390px;top:500px;width:300px;height:300px;border-radius:70px}
#end .w1{position:absolute;left:0;right:0;top:850px;text-align:center;font-family:Orb;font-weight:900;font-size:112px;letter-spacing:22px;padding-left:22px;
  text-shadow:0 0 40px rgba(255,47,200,.8)}
#end .w2{position:absolute;left:0;right:0;top:990px;text-align:center;font-family:Orb;font-weight:700;font-size:34px;letter-spacing:14px;padding-left:14px;color:#ff66d9}
#end .tg{position:absolute;left:60px;right:60px;top:1090px;text-align:center;font-family:Mont;font-weight:900;font-size:56px;line-height:1.1}
#end .soc{position:absolute;left:0;right:0;top:1270px;display:flex;justify-content:center;gap:24px}
#end .soc span{display:flex;align-items:center;gap:14px;font:700 40px Inter;padding:18px 32px 18px 26px;border-radius:50px;
  background:rgba(255,255,255,.1);border:2px solid rgba(255,255,255,.18)}
#end .soc svg{width:44px;height:44px;color:#fff}
#end .bio{position:absolute;left:0;right:0;top:1400px;text-align:center;font:800 30px Mont;letter-spacing:8px;color:rgba(255,255,255,.6)}
#flash{position:absolute;inset:0;background:#fff;opacity:0;z-index:90;pointer-events:none}
#grain{position:absolute;left:0;top:0;width:1080px;height:1920px;z-index:95;pointer-events:none;opacity:.06;mix-blend-mode:overlay}
`;

const AZ = {};
AZ.init = (opts = {}) => {
  mk('style', {}, document.head, BASE_CSS + (opts.css || ''));
  document.body.insertAdjacentHTML('afterbegin', ICONS);
  const stage = $('stage');
  mk('div', {id: 'flash'}, stage);
  const g = mk('canvas', {id: 'grain', width: 540, height: 960}, stage);
  AZ.grainCtx = g.getContext('2d');
  AZ.grainTiles = Array.from({length: 4}, (_, i) => {
    const c = document.createElement('canvas'); c.width = c.height = 256; const x = c.getContext('2d'); const d = x.createImageData(256, 256);
    for (let p = 0; p < d.data.length; p += 4) { const v = hash(p * .37 + i * 999) * 255; d.data[p] = d.data[p + 1] = d.data[p + 2] = v; d.data[p + 3] = 255; }
    x.putImageData(d, 0, 0); return c;
  });
  if (opts.dram) mk('div', {class: 'dram'}, stage, opts.dram);
};
AZ.post = (t, flash = 0, shake = 0) => {
  $('flash').style.opacity = flash;
  const sx = (hash(Math.floor(t * 30)) - .5) * 2 * shake, sy = (hash(Math.floor(t * 30) + 77) - .5) * 2 * shake;
  $('stage').style.transform = shake > .3 ? `translate(${sx}px,${sy}px)` : 'none';
  const g = AZ.grainCtx; g.clearRect(0, 0, 540, 960);
  g.fillStyle = g.createPattern(AZ.grainTiles[Math.floor(t * 24) % 4], 'repeat'); g.fillRect(0, 0, 540, 960);
};

/* ---------- legendas estilo CapCut: palavra por palavra, a atual em destaque ----------
   lines: [[início, fim, 'texto com *destaque* rosa, _verde_, ~vermelho~'], ...] */
AZ.caps = (lines, top = 1180, opts = {}) => {
  const box = mk('div', {class: 'cap', style: {top: top + 'px', fontSize: (opts.size || 74) + 'px'}}, $('stage'));
  const parsed = lines.map(([a, b, txt]) => {
    const words = txt.split(' ').filter(Boolean).map(w => {
      let cls = '';
      if (/^\*.*\*[!?.,]*$/.test(w)) cls = 'pk'; else if (/^_.*_[!?.,]*$/.test(w)) cls = 'gr'; else if (/^~.*~[!?.,]*$/.test(w)) cls = 'rd';
      return {w: w.replace(/[*_~]/g, ''), cls};
    });
    // palavras aparecem em ~75% do tempo da linha
    const span = (b - a) * .75;
    words.forEach((w, i) => { w.t = a + span * i / words.length; });
    return {a, b, words};
  });
  let cur = null;
  return t => {
    const L = parsed.find(l => t >= l.a && t < l.b);
    if (L !== cur) {
      box.innerHTML = L ? L.words.map(w => `<span data-c="${w.cls}">${w.w}</span>`).join(' ') : '';
      cur = L;
    }
    if (!L) return;
    [...box.children].forEach((s, i) => {
      const w = L.words[i];
      const k = prog(t, w.t, w.t + .12);
      s.style.opacity = k > 0 ? 1 : 0;
      s.style.transform = `scale(${k > 0 ? lerp(1.35, 1, eOut(k)) : 1})`;
      const next = L.words[i + 1];
      const active = t >= w.t && (!next || t < next.t);
      s.className = w.cls || (active && !opts.noHl ? 'on' : '');
    });
  };
};

/* ---------- caixa branca de legenda (estilo texto do TikTok) ---------- */
AZ.tbox = (lines, top) => {
  const b = mk('div', {class: 'tbox', style: {top: top + 'px'}}, $('stage'));
  b.innerHTML = lines.map(l => `<span>${l}</span>`).join('<br>');
  return b;
};

/* ---------- cartão final com logo e redes ---------- */
AZ.endCard = (t0, tagline) => {
  const e = mk('div', {id: 'end'}, $('stage'));
  e.innerHTML = `<img class="lg" src="web/assets/Azor_icon.png"><div class="w1">AZOR</div><div class="w2">OPTIMIZATION</div>
    <div class="tg">${tagline}</div>
    <div class="soc"><span><svg><use href="#tt"/></svg>@azorwrld</span><span><svg><use href="#ig"/></svg>@azortweaks</span></div>
    <div class="bio">LINK NA BIO</div>`;
  const q = s => e.querySelector(s);
  sfx(t0, 'whoosh', .8); sfx(t0 + .05, 'hit', .7); sfx(t0 + .9, 'chime', .7);
  return t => {
    const k = prog(t, t0, t0 + .25);
    show(e, k);
    if (k <= 0) return;
    const lk = eBack(prog(t, t0, t0 + .5));
    q('.lg').style.transform = `scale(${lerp(.3, 1, lk)})`;
    q('.lg').style.filter = `drop-shadow(0 0 ${40 + 15 * Math.sin(t * 6)}px rgba(255,47,200,.85))`;
    const k2 = eOut(prog(t, t0 + .15, t0 + .55));
    q('.w1').style.opacity = k2; q('.w1').style.letterSpacing = lerp(60, 22, k2) + 'px';
    q('.w2').style.opacity = eOut(prog(t, t0 + .3, t0 + .7));
    const k3 = eBack(prog(t, t0 + .45, t0 + .8));
    q('.tg').style.opacity = clamp((t - t0 - .45) * 6); q('.tg').style.transform = `scale(${lerp(1.3, 1, k3)})`;
    const k4 = eOut(prog(t, t0 + .7, t0 + 1.05));
    q('.soc').style.opacity = k4; q('.soc').style.transform = `translateY(${(1 - k4) * 40}px)`;
    q('.bio').style.opacity = eOut(prog(t, t0 + 1, t0 + 1.4));
  };
};

/* ---------- cena de jogo estilizada (túnel neon com mira e HUD) ----------
   gt = tempo do jogo (pode "travar"), quality: 'lag' | 'ok' */
AZ.game = (ctx, x, y, w, h, gt, o = {}) => {
  ctx.save();
  ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip();
  const cx = x + w / 2, hz = y + h * .46;
  const sky = ctx.createLinearGradient(0, y, 0, hz);
  sky.addColorStop(0, '#0b0420'); sky.addColorStop(1, '#3a0d4a');
  ctx.fillStyle = sky; ctx.fillRect(x, y, w, hz - y);
  // sol listrado
  const sr = w * .2;
  const sg = ctx.createLinearGradient(0, hz - sr * 1.6, 0, hz);
  sg.addColorStop(0, '#ffd34d'); sg.addColorStop(1, '#ff2fa0');
  ctx.fillStyle = sg; ctx.beginPath(); ctx.arc(cx, hz, sr, Math.PI, 0); ctx.fill();
  ctx.fillStyle = '#2a0a3a';
  for (let i = 0; i < 6; i++) { const yy = hz - sr * (.12 + i * .15); ctx.fillRect(cx - sr, yy, sr * 2, 3 + i * 1.6); }
  // montanhas
  ctx.fillStyle = '#16072a';
  ctx.beginPath(); ctx.moveTo(x, hz);
  for (let i = 0; i <= 24; i++) { const xx = x + w * i / 24; ctx.lineTo(xx, hz - (hash(i * 3.3) * .12 + .03) * h); }
  ctx.lineTo(x + w, hz); ctx.fill();
  // chão
  const fg = ctx.createLinearGradient(0, hz, 0, y + h);
  fg.addColorStop(0, '#1a0526'); fg.addColorStop(1, '#07020c');
  ctx.fillStyle = fg; ctx.fillRect(x, hz, w, y + h - hz);
  ctx.strokeStyle = '#ff2fc8'; ctx.lineWidth = Math.max(1.5, w / 400); ctx.shadowColor = '#ff2fc8'; ctx.shadowBlur = 10;
  const sway = Math.sin(gt * .8) * w * .08;
  for (let i = -14; i <= 14; i++) { ctx.beginPath(); ctx.moveTo(cx + i * w * .02 + sway * .2, hz); ctx.lineTo(cx + i * w * .22 + sway, y + h); ctx.stroke(); }
  const off = (gt * 1.6) % 1;
  for (let j = 0; j < 14; j++) {
    const k = (j + off) / 14, yy = hz + Math.pow(k, 2.6) * (y + h - hz);
    ctx.globalAlpha = .25 + k * .75; ctx.beginPath(); ctx.moveTo(x, yy); ctx.lineTo(x + w, yy); ctx.stroke();
  }
  ctx.globalAlpha = 1; ctx.shadowBlur = 0;
  // alvos vindo em direção ao jogador
  for (let i = 0; i < 4; i++) {
    const ph = (gt * .35 + i / 4) % 1, s = Math.pow(ph, 2.2);
    const tx = cx + (hash(i + Math.floor(gt * .35 + i / 4) * 9) - .5) * w * .9 * s + sway * s;
    const ty = hz + s * h * .32, r = 6 + s * w * .06;
    ctx.fillStyle = `rgba(80,230,255,${.3 + s * .7})`; ctx.shadowColor = '#50e6ff'; ctx.shadowBlur = 20 * s;
    ctx.beginPath(); ctx.moveTo(tx, ty - r); ctx.lineTo(tx + r, ty); ctx.lineTo(tx, ty + r); ctx.lineTo(tx - r, ty); ctx.closePath(); ctx.fill();
  }
  ctx.shadowBlur = 0;
  // mira
  const s = w / 1080;
  ctx.strokeStyle = '#fff'; ctx.lineWidth = 4 * s;
  ctx.beginPath(); ctx.moveTo(cx - 34 * s, y + h * .55); ctx.lineTo(cx - 12 * s, y + h * .55); ctx.moveTo(cx + 12 * s, y + h * .55); ctx.lineTo(cx + 34 * s, y + h * .55);
  ctx.moveTo(cx, y + h * .55 - 34 * s); ctx.lineTo(cx, y + h * .55 - 12 * s); ctx.moveTo(cx, y + h * .55 + 12 * s); ctx.lineTo(cx, y + h * .55 + 34 * s); ctx.stroke();
  // HUD
  ctx.fillStyle = 'rgba(0,0,0,.45)'; ctx.fillRect(x + w - 250 * s, y + h - 100 * s, 220 * s, 70 * s);
  ctx.fillStyle = '#fff'; ctx.font = `900 ${44 * s}px Orb`; ctx.fillText('30 / 90', x + w - 236 * s, y + h - 50 * s);
  ctx.fillStyle = 'rgba(0,0,0,.45)'; ctx.fillRect(x + 30 * s, y + h - 100 * s, 260 * s, 70 * s);
  ctx.fillStyle = '#3dff9a'; ctx.fillRect(x + 44 * s, y + h - 80 * s, 200 * s, 30 * s);
  ctx.restore();
};

/* ---------- overlay de desempenho (FPS + frametime) ---------- */
AZ.perf = (ctx, x, y, s, t, lag, label = true) => {
  ctx.save();
  ctx.fillStyle = 'rgba(0,0,0,.6)'; ctx.beginPath(); ctx.roundRect(x, y, 330 * s, 150 * s, 14 * s); ctx.fill();
  ctx.font = `900 ${30 * s}px Orb`;
  ctx.fillStyle = lag ? '#ff4155' : '#3dff9a';
  if (label) ctx.fillText(lag ? 'FPS ' + (24 + Math.floor(hash(Math.floor(t * 6)) * 19)) : '✓ ESTÁVEL', x + 18 * s, y + 42 * s);
  if (lag) { ctx.font = `800 ${20 * s}px Mont`; ctx.fillStyle = 'rgba(255,255,255,.7)'; ctx.fillText('INSTÁVEL', x + 220 * s, y + 40 * s); }
  ctx.beginPath(); ctx.lineWidth = 3.5 * s; ctx.strokeStyle = lag ? '#ff4155' : '#3dff9a';
  for (let i = 0; i <= 60; i++) {
    const n = Math.floor(t * 30) - 60 + i;
    let v = lag ? .3 + hash(n) * .2 + (hash(n * 3.7) > .82 ? .45 : 0) : .3 + hash(n) * .05;
    const px = x + 18 * s + i * 4.9 * s, py = y + 135 * s - v * 75 * s;
    i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
  }
  ctx.stroke(); ctx.restore();
};

/* ---------- brilho suave em canvas ---------- */
AZ.blob = (ctx, x, y, rx, ry, rgb, a) => {
  if (a <= .003) return;
  ctx.save(); ctx.translate(x, y); ctx.scale(rx / 100, ry / 100);
  const g = ctx.createRadialGradient(0, 0, 0, 0, 0, 100);
  g.addColorStop(0, `rgba(${rgb},${a})`); g.addColorStop(.55, `rgba(${rgb},${a * .45})`); g.addColorStop(1, `rgba(${rgb},0)`);
  ctx.fillStyle = g; ctx.beginPath(); ctx.arc(0, 0, 100, 0, 6.283); ctx.fill(); ctx.restore();
};

AZ.ready = async () => {
  await Promise.all(['400 40px Anton', '800 40px Mont', '900 40px Mont', '900 40px Orb', '700 40px Orb', '700 40px Inter', '600 40px "Inter Display"', '40px "Noto Color Emoji"']
    .map(f => document.fonts.load(f, 'Aá😭🔥')));
  await document.fonts.ready;
  await Promise.all([...document.images].map(i => i.decode().catch(() => {})));
  return {D: window.DURATION};
};
window.ready = AZ.ready;
