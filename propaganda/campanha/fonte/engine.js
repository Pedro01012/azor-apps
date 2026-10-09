// Motor da campanha AZOR: renderizador three.js, estúdio, pós-produção, tipografia e linha do tempo.
import * as THREE from 'three';
import {EffectComposer} from 'three/addons/postprocessing/EffectComposer.js';
import {RenderPass} from 'three/addons/postprocessing/RenderPass.js';
import {UnrealBloomPass} from 'three/addons/postprocessing/UnrealBloomPass.js';
import {OutputPass} from 'three/addons/postprocessing/OutputPass.js';
import {ShaderPass} from 'three/addons/postprocessing/ShaderPass.js';
import {BokehPass} from 'three/addons/postprocessing/BokehPass.js';
import {SMAAPass} from 'three/addons/postprocessing/SMAAPass.js';
import {RectAreaLightUniformsLib} from 'three/addons/lights/RectAreaLightUniformsLib.js';

export {THREE};
const QS = new URLSearchParams(location.search);
export const W = Number(QS.get('w') || 1080), H = Number(QS.get('h') || 1920);

/* ---------------- tempo e curvas ---------------- */
export const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
export const lerp = (a, b, k) => a + (b - a) * k;
export const prog = (t, a, b) => clamp((t - a) / (b - a));
export const ease = {
  out: k => 1 - Math.pow(1 - k, 3),
  out5: k => 1 - Math.pow(1 - k, 5),
  expo: k => k >= 1 ? 1 : 1 - Math.pow(2, -10 * k),
  in: k => k * k * k,
  io: k => k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2,
  sine: k => -(Math.cos(Math.PI * k) - 1) / 2,
  ioExpo: k => k <= 0 ? 0 : k >= 1 ? 1 : k < .5 ? Math.pow(2, 20 * k - 10) / 2 : (2 - Math.pow(2, -20 * k + 10)) / 2,
};
export const hash = n => { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); };
export const noise1 = (seed, t, f) => { const x = t * f, i = Math.floor(x), k = x - i, u = k * k * (3 - 2 * k);
  return (hash(i + seed * 101) * (1 - u) + hash(i + 1 + seed * 101) * u) * 2 - 1; };
// interpola chaves {t, ...valores} com curva suave entre elas
export function keys(t, list, fn = ease.io) {
  if (t <= list[0].t) return {...list[0]};
  for (let i = 0; i < list.length - 1; i++) {
    const a = list[i], b = list[i + 1];
    if (t <= b.t) {
      const k = (b.ease || fn)(prog(t, a.t, b.t));
      const o = {};
      for (const key in a) if (key !== 't' && key !== 'ease') o[key] = Array.isArray(a[key]) ? a[key].map((v, j) => lerp(v, b[key][j], k)) : lerp(a[key], b[key], k);
      return o;
    }
  }
  return {...list[list.length - 1]};
}

/* ---------------- som (lido pelo sound.py) ---------------- */
export const SFX = [];
window.SFX = SFX;
export const sfx = (t, kind, v = 1, extra = {}) => SFX.push({t: +t.toFixed(3), kind, v, ...extra});

/* ---------------- renderizador ---------------- */
const GradeShader = {
  uniforms: {tDiffuse: {value: null}, time: {value: 0}, vig: {value: .42}, grain: {value: .05}, ca: {value: .0016}, res: {value: new THREE.Vector2(W, H)},
    lift: {value: new THREE.Vector3(.012, .008, .016)}, fade: {value: 0}, fadeCol: {value: new THREE.Vector3(0, 0, 0)}},
  vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.); }',
  fragmentShader: `
    uniform sampler2D tDiffuse; uniform float time, vig, grain, ca, fade; uniform vec2 res; uniform vec3 lift, fadeCol; varying vec2 vUv;
    float h(vec2 p){ return fract(sin(dot(p, vec2(12.9898,78.233))) * 43758.5453); }
    void main(){
      vec2 c = vUv - .5; float r = length(c * vec2(res.x/res.y, 1.));
      vec2 off = c * ca * (.4 + r * 1.6);
      vec3 col = vec3(texture2D(tDiffuse, vUv + off).r, texture2D(tDiffuse, vUv).g, texture2D(tDiffuse, vUv - off).b);
      col = lift + col * (1. - lift);
      float v = smoothstep(1.05, .25, r); col *= mix(1. - vig, 1., v);
      float g = h(vUv * res + fract(time * 13.7) * 91.7) - .5;
      col += g * grain * (1. - dot(col, vec3(.299,.587,.114)) * .6);
      col = mix(col, fadeCol, fade);
      gl_FragColor = vec4(col, 1.);
    }`,
};

export function createStage({bloom = [.55, .55, .82], dof = false, exposure = 1, bg = 0x050407, msaa = Number(QS.get('msaa') || 0)} = {}) {
  const renderer = new THREE.WebGLRenderer({antialias: false, preserveDrawingBuffer: true, powerPreference: 'high-performance'});
  renderer.setPixelRatio(1);
  renderer.setSize(W, H);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = exposure;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.domElement.id = 'gl';
  document.getElementById('stage').prepend(renderer.domElement);
  RectAreaLightUniformsLib.init();
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(bg);
  const camera = new THREE.PerspectiveCamera(30, W / H, .01, 60);
  const rt = new THREE.WebGLRenderTarget(W, H, {type: THREE.HalfFloatType, samples: msaa});
  const composer = new EffectComposer(renderer, rt);
  composer.addPass(new RenderPass(scene, camera));
  let bokeh = null;
  if (dof) { bokeh = new BokehPass(scene, camera, {focus: 1, aperture: .002, maxblur: .006}); composer.addPass(bokeh); }
  const bloomPass = new UnrealBloomPass(new THREE.Vector2(W / 2, H / 2), bloom[0], bloom[1], bloom[2]);
  composer.addPass(bloomPass);
  composer.addPass(new OutputPass());
  if (!msaa) composer.addPass(new SMAAPass(W, H));
  const grade = new ShaderPass(GradeShader);
  composer.addPass(grade);
  return {renderer, scene, camera, composer, bloom: bloomPass, bokeh, grade,
    render(t) { grade.uniforms.time.value = t; composer.render(); }};
}

/* ---------------- estúdio: ambiente para reflexos ---------------- */
export function studioEnv(renderer, {key = 2.6, accent = 0xff2fc8, accent2 = 0x7b5cff, accentI = 3.2, cool = 1.6} = {}) {
  const s = new THREE.Scene();
  const room = new THREE.Mesh(new THREE.BoxGeometry(24, 12, 24), new THREE.MeshBasicMaterial({color: 0x030304, side: THREE.BackSide}));
  s.add(room);
  const panel = (w, h, col, I, pos, rot) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({color: new THREE.Color(col).multiplyScalar(I), side: THREE.DoubleSide}));
    m.position.set(...pos); m.rotation.set(...rot); s.add(m); return m;
  };
  panel(7, 3.2, 0xfff4ec, key, [-1.5, 5.8, 1.5], [Math.PI / 2, 0, 0]);          // softbox de cima
  panel(.8, 7, accent, accentI, [-8, 1.5, -2], [0, Math.PI / 2, 0]);            // faixa magenta à esquerda
  panel(.8, 7, accent2, accentI * .8, [8, 1.5, -3], [0, -Math.PI / 2, 0]);      // faixa violeta à direita
  panel(10, .6, 0xdfe6ff, cool, [0, 1.2, -11.5], [0, 0, 0]);                    // faixa fria ao fundo
  panel(3, 1.2, 0xffffff, key * .6, [4, 2.4, 9], [0, Math.PI, 0]);               // rebatedor frontal
  // faixas verticais finas que desenham linhas de luz nos vidros (vista 3/4 frontal-direita)
  panel(.35, 9, 0xffffff, 6, [6.5, 2, -9.5], [0, -.6, 0]);
  panel(.22, 9, 0xffe8f6, 4, [-6, 2, 9.5], [0, Math.PI - .56, 0]);
  panel(.18, 9, 0xffffff, 3.5, [10, 2, 3], [0, -Math.PI / 2, 0]);
  const pm = new THREE.PMREMGenerator(renderer);
  const tex = pm.fromScene(s, .035).texture;
  pm.dispose();
  return tex;
}

/* ---------------- texturas utilitárias ---------------- */
export function canvasTex(w, h, draw, srgb = true) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}
export function radialTex(stops = [[0, 'rgba(255,255,255,1)'], [1, 'rgba(255,255,255,0)']], size = 256) {
  return canvasTex(size, size, (g, w) => {
    const gr = g.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2);
    stops.forEach(([o, c]) => gr.addColorStop(o, c));
    g.fillStyle = gr; g.fillRect(0, 0, w, w);
  });
}
export async function loadTex(url) {
  const t = await new THREE.TextureLoader().loadAsync(url);
  t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  return t;
}

/* ---------------- tipografia (DOM sobre o 3D) ---------------- */
export const TYPE_CSS = `
@font-face{font-family:Geist;font-weight:300;src:url(/node_modules/@fontsource/geist/files/geist-latin-300-normal.woff2)}
@font-face{font-family:Geist;font-weight:400;src:url(/node_modules/@fontsource/geist/files/geist-latin-400-normal.woff2)}
@font-face{font-family:Geist;font-weight:500;src:url(/node_modules/@fontsource/geist/files/geist-latin-500-normal.woff2)}
@font-face{font-family:Geist;font-weight:600;src:url(/node_modules/@fontsource/geist/files/geist-latin-600-normal.woff2)}
@font-face{font-family:Geist;font-weight:700;src:url(/node_modules/@fontsource/geist/files/geist-latin-700-normal.woff2)}
@font-face{font-family:GeistMono;font-weight:400;src:url(/node_modules/@fontsource/geist-mono/files/geist-mono-latin-400-normal.woff2)}
@font-face{font-family:GeistMono;font-weight:500;src:url(/node_modules/@fontsource/geist-mono/files/geist-mono-latin-500-normal.woff2)}
@font-face{font-family:Serif;font-style:italic;src:url(/node_modules/@fontsource/instrument-serif/files/instrument-serif-latin-400-italic.woff2)}
@font-face{font-family:Serif;font-style:normal;src:url(/node_modules/@fontsource/instrument-serif/files/instrument-serif-latin-400-normal.woff2)}
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:${W}px;height:${H}px;overflow:hidden;background:#000}
#stage{position:absolute;left:0;top:0;width:${W}px;height:${H}px;overflow:hidden;background:#000;color:#f4f1f6;font-family:Geist,sans-serif;-webkit-font-smoothing:antialiased}
#gl{position:absolute;left:0;top:0}
.ov{position:absolute;left:0;top:0;width:${W}px;height:${H}px;pointer-events:none}
.t{position:absolute;left:84px;right:84px;font-family:Geist;font-weight:600;letter-spacing:-.04em;line-height:.98;color:#f6f3f8}
.t .l{display:block;overflow:hidden;padding:.06em 0 .1em;margin:-.06em 0 -.1em}
.t .l>span{display:inline-block;will-change:transform}
.t em{font-family:Serif;font-style:italic;font-weight:400;letter-spacing:-.01em;color:#ff7fe0}
.t em.w{color:#f6f3f8}
.lab{position:absolute;left:84px;font-family:GeistMono;font-weight:500;font-size:24px;letter-spacing:.22em;text-transform:uppercase;color:rgba(246,243,248,.62)}
.lab b{color:#ff7fe0;font-weight:500}
`;
export function mountType(extraCss = '') {
  const st = document.createElement('style'); st.textContent = TYPE_CSS + extraCss; document.head.appendChild(st);
  const ov = document.createElement('div'); ov.className = 'ov'; ov.id = 'ov'; document.getElementById('stage').appendChild(ov);
  const scrim = document.createElement('div'); scrim.id = 'scrim';
  Object.assign(scrim.style, {position: 'absolute', left: 0, top: 0, width: W + 'px', height: '760px', background: 'linear-gradient(180deg,rgba(3,2,4,.62) 0%,rgba(3,2,4,.38) 45%,rgba(3,2,4,0) 100%)'});
  ov.appendChild(scrim);
  return ov;
}
// Título em linhas que sobem de dentro de uma máscara (padrão de filme de produto).
export function headline(html, {top, size = 104, align = 'left', weight = 600, cls = ''} = {}) {
  const el = document.createElement('div');
  el.className = 't ' + cls;
  Object.assign(el.style, {top: top + 'px', fontSize: size + 'px', textAlign: align, fontWeight: weight});
  el.innerHTML = html.split('|').map(l => `<span class="l"><span>${l}</span></span>`).join('');
  document.getElementById('ov').appendChild(el);
  const lines = [...el.querySelectorAll('.l>span')];
  // a(t): entra em t0 (linhas escalonadas), sai em t1
  el.anim = (t, t0, t1, {stagger = .09, dur = .9, out = .5} = {}) => {
    const vis = t >= t0 - .01 && t < t1 + out;
    el.style.visibility = vis ? 'visible' : 'hidden';
    if (!vis) return;
    lines.forEach((s, i) => {
      const k = ease.expo(prog(t, t0 + i * stagger, t0 + i * stagger + dur));
      const o = ease.in(prog(t, t1, t1 + out));
      s.style.transform = `translateY(${(1 - k) * 105 - o * 18}%)`;
      s.style.opacity = 1 - o;
      s.style.filter = o > 0 ? `blur(${o * 10}px)` : 'none';
    });
  };
  return el;
}
export function label(html, {top, left = 84} = {}) {
  const el = document.createElement('div'); el.className = 'lab';
  Object.assign(el.style, {top: top + 'px', left: left + 'px'}); el.innerHTML = html;
  document.getElementById('ov').appendChild(el);
  el.anim = (t, t0, t1) => {
    const k = ease.out(prog(t, t0, t0 + .6)), o = prog(t, t1, t1 + .4);
    el.style.visibility = t >= t0 && t < t1 + .4 ? 'visible' : 'hidden';
    el.style.opacity = k * (1 - o);
    el.style.letterSpacing = `${lerp(.4, .22, k)}em`;
  };
  return el;
}

export async function fontsReady() {
  await Promise.all(['300 40px Geist', '400 40px Geist', '500 40px Geist', '600 40px Geist', '700 40px Geist', '400 40px GeistMono', '500 40px GeistMono', 'italic 40px Serif', '40px Serif']
    .map(f => document.fonts.load(f, 'AaÁçã')));
  await document.fonts.ready;
}

/* ---------------- assinatura final (logo + redes) ---------------- */
export function lockup(tagline, {sub = 'OPTIMIZATION'} = {}) {
  const el = document.createElement('div');
  el.id = 'lock';
  el.innerHTML = `<div class="lk-glow"></div><img class="lk-ic" src="/web/assets/Azor_icon.png">
    <div class="lk-w">AZOR</div><div class="lk-s">${sub}</div><div class="lk-t">${tagline}</div>
    <div class="lk-soc"><span><svg viewBox="0 0 24 24"><path fill="currentColor" d="M16.6 5.82A4.28 4.28 0 0 1 15.54 3h-3.09v12.4a2.59 2.59 0 0 1-2.59 2.5 2.6 2.6 0 0 1-2.6-2.6 2.6 2.6 0 0 1 3.4-2.47V9.67a5.73 5.73 0 0 0-.81-.06 5.69 5.69 0 0 0-5.69 5.69A5.69 5.69 0 0 0 9.85 21a5.69 5.69 0 0 0 5.69-5.69V9.01a7.35 7.35 0 0 0 4.3 1.38V7.3a4.3 4.3 0 0 1-3.24-1.48z"/></svg>@azorwrld</span>
    <span><svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="5.2" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="12" r="4.1" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="17.2" cy="6.8" r="1.2" fill="currentColor"/></svg>@azortweaks</span></div>
    <div class="lk-b">Link na bio</div>`;
  const css = document.createElement('style');
  css.textContent = `#lock{position:absolute;inset:0;visibility:hidden;background:#030204}
    #lock .lk-glow{position:absolute;left:-20%;right:-20%;top:${H * .3}px;height:${H * .45}px;background:radial-gradient(ellipse at 50% 50%,rgba(255,47,200,.16),rgba(110,60,255,.06) 40%,transparent 70%)}
    #lock .lk-ic{position:absolute;left:${W / 2 - 100}px;top:${H * .5 - 400}px;width:200px;height:200px;border-radius:46px;box-shadow:0 0 60px rgba(255,47,200,.25)}
    #lock .lk-w{position:absolute;left:0;right:0;top:${H * .5 - 150}px;text-align:center;font:600 100px Geist;letter-spacing:.34em;padding-left:.34em;color:#f6f3f8}
    #lock .lk-s{position:absolute;left:0;right:0;top:${H * .5 - 22}px;text-align:center;font:500 26px GeistMono;letter-spacing:.5em;padding-left:.5em;color:rgba(246,243,248,.5)}
    #lock .lk-t{position:absolute;left:60px;right:60px;top:${H * .5 + 80}px;text-align:center;font:400 78px/1.1 Serif;font-style:italic;color:#ffd6f4}
    #lock .lk-soc{position:absolute;left:0;right:0;top:${H * .5 + 280}px;display:flex;justify-content:center;gap:48px;font:500 34px GeistMono;color:rgba(246,243,248,.82)}
    #lock .lk-soc span{display:flex;align-items:center;gap:14px}#lock .lk-soc svg{width:40px;height:40px;color:#f6f3f8}
    #lock .lk-b{position:absolute;left:0;right:0;top:${H * .5 + 370}px;text-align:center;font:500 24px GeistMono;letter-spacing:.42em;padding-left:.42em;text-transform:uppercase;color:rgba(246,243,248,.42)}`;
  document.head.appendChild(css);
  document.getElementById('ov').appendChild(el);
  const q = s => el.querySelector(s);
  el.anim = (t, t0) => {
    const v = t >= t0;
    el.style.visibility = v ? 'visible' : 'hidden';
    if (!v) return;
    el.style.opacity = ease.out(prog(t, t0, t0 + .5));
    const k1 = ease.expo(prog(t, t0 + .1, t0 + 1.2));
    q('.lk-ic').style.transform = `translateY(${(1 - k1) * 30}px) scale(${lerp(.9, 1, k1)})`; q('.lk-ic').style.opacity = k1;
    const k2 = ease.expo(prog(t, t0 + .3, t0 + 1.4));
    q('.lk-w').style.opacity = k2; q('.lk-w').style.letterSpacing = `${lerp(.6, .34, k2)}em`;
    q('.lk-s').style.opacity = ease.out(prog(t, t0 + .55, t0 + 1.3)) * .9;
    const k3 = ease.expo(prog(t, t0 + .7, t0 + 1.7));
    q('.lk-t').style.opacity = k3; q('.lk-t').style.transform = `translateY(${(1 - k3) * 24}px)`; q('.lk-t').style.filter = `blur(${(1 - k3) * 8}px)`;
    const k4 = ease.out(prog(t, t0 + 1.05, t0 + 1.8));
    q('.lk-soc').style.opacity = k4; q('.lk-b').style.opacity = ease.out(prog(t, t0 + 1.3, t0 + 2));
  };
  return el;
}
