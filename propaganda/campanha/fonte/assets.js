// Modelos 3D procedurais da campanha AZOR (unidades em metros).
import {THREE, canvasTex, radialTex, hash} from './engine.js';
import {RoundedBoxGeometry} from 'three/addons/geometries/RoundedBoxGeometry.js';

/* ---------------- materiais ---------------- */
export const M = {
  alu: () => new THREE.MeshPhysicalMaterial({color: 0x17171c, metalness: 1, roughness: .3, clearcoat: .5, clearcoatRoughness: .22}),
  aluMid: () => new THREE.MeshPhysicalMaterial({color: 0x2a2a31, metalness: 1, roughness: .34}),
  silver: () => new THREE.MeshPhysicalMaterial({color: 0x9a9ca6, metalness: 1, roughness: .22}),
  plastic: () => new THREE.MeshStandardMaterial({color: 0x0c0c0f, roughness: .55, metalness: .1}),
  rubber: () => new THREE.MeshStandardMaterial({color: 0x09090b, roughness: .82, metalness: 0}),
  // vidro plano: só reflexo (aditivo) + leve escurecimento; sem refração, que custa uma renderização extra
  glass: () => new THREE.MeshPhysicalMaterial({color: 0x000000, metalness: 0, roughness: .03, transparent: true, opacity: 1, depthWrite: false,
    blending: THREE.AdditiveBlending, envMapIntensity: 2.2, specularIntensity: 1}),
  tint: () => new THREE.MeshBasicMaterial({color: 0x000000, transparent: true, opacity: .22, depthWrite: false}),
  led: (map, I = 3) => new THREE.MeshStandardMaterial({color: 0x000000, emissive: 0xffffff, emissiveMap: map, emissiveIntensity: I, roughness: .4}),
};

/* gradiente da marca para os LEDs (magenta → violeta → branco frio → magenta) */
export const ledTex = (stops = ['#ff2fc8', '#a03cff', '#6a7bff', '#ff2fc8']) => canvasTex(512, 8, (g, w, h) => {
  const gr = g.createLinearGradient(0, 0, w, 0);
  stops.forEach((c, i) => gr.addColorStop(i / (stops.length - 1), c));
  g.fillStyle = gr; g.fillRect(0, 0, w, h);
});

function roundedRectShape(w, h, r) {
  const s = new THREE.Shape(), x = -w / 2, y = -h / 2;
  s.moveTo(x + r, y); s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + h - r); s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y);
  return s;
}
const box = (w, h, d, mat, r = 0) => new THREE.Mesh(r > 0 ? new RoundedBoxGeometry(w, h, d, 3, r) : new THREE.BoxGeometry(w, h, d), mat);

/* ---------------- ventoinha RGB (olha para +z) ---------------- */
export function buildFan(size, ringMat, opts = {}) {
  const g = new THREE.Group();
  const frameShape = roundedRectShape(size, size, size * .1);
  const hole = new THREE.Path(); hole.absarc(0, 0, size * .465, 0, Math.PI * 2, true); frameShape.holes.push(hole);
  const frame = new THREE.Mesh(new THREE.ExtrudeGeometry(frameShape, {depth: size * .2, bevelEnabled: true, bevelSize: .0012, bevelThickness: .0012, bevelSegments: 2, curveSegments: 48}), opts.frameMat || M.plastic());
  frame.position.z = -size * .1;
  g.add(frame);
  // anel de LED (frente e verso) com difusor
  const ring = new THREE.Mesh(new THREE.TorusGeometry(size * .455, size * .03, 12, 120), ringMat);
  ring.position.z = size * .1 + .001; g.add(ring);
  const ring2 = ring.clone(); ring2.position.z = -size * .1 - .001; g.add(ring2);
  // rotor com pás translúcidas que pegam a cor do LED
  const rotor = new THREE.Group(); rotor.name = 'rotor';
  const bladeMat = opts.bladeMat || new THREE.MeshStandardMaterial({color: 0x2a2830, roughness: .35, metalness: .2, transparent: true, opacity: 1,
    emissive: new THREE.Color(0xff2fc8), emissiveIntensity: .12, side: THREE.DoubleSide});
  const n = 9, r0 = size * .16, r1 = size * .445, sweep = .62;
  const sh = new THREE.Shape();
  const P = (r, a) => new THREE.Vector2(r * Math.cos(a), r * Math.sin(a));
  const steps = 10;
  for (let i = 0; i <= steps; i++) { const k = i / steps, r = r0 + (r1 - r0) * k, a = -.22 + sweep * k * k * .9; const p = P(r, a); i ? sh.lineTo(p.x, p.y) : sh.moveTo(p.x, p.y); }
  for (let i = steps; i >= 0; i--) { const k = i / steps, r = r0 + (r1 - r0) * k, a = .3 + sweep * k * .55; const p = P(r, a); sh.lineTo(p.x, p.y); }
  const bladeGeo = new THREE.ExtrudeGeometry(sh, {depth: .0012, bevelEnabled: false, curveSegments: 6});
  for (let i = 0; i < n; i++) {
    const piv = new THREE.Group(); piv.rotation.z = i / n * Math.PI * 2;
    const b = new THREE.Mesh(bladeGeo, bladeMat); b.rotation.x = .22; piv.add(b); rotor.add(piv);
  }
  const hub = new THREE.Mesh(new THREE.CylinderGeometry(r0 * 1.02, r0 * 1.02, size * .14, 48), opts.hubMat || M.plastic());
  hub.rotation.x = Math.PI / 2; rotor.add(hub);
  const cap = new THREE.Mesh(new THREE.CircleGeometry(r0 * .92, 48), opts.capMat || new THREE.MeshPhysicalMaterial({color: 0x121216, metalness: .6, roughness: .3}));
  cap.position.z = size * .071; rotor.add(cap);
  g.add(rotor);
  const blurMat = opts.blurMat || new THREE.MeshBasicMaterial({color: 0x3a2a44, transparent: true, opacity: 0, depthWrite: false});
  const disc = new THREE.Mesh(new THREE.RingGeometry(r0 * 1.02, r1, 64), blurMat); disc.position.z = .002; g.add(disc);
  return {group: g, rotor, bladeMat, blurMat};
}

/* ---------------- textura da placa-mãe ---------------- */
function pcbTexture() {
  return canvasTex(1024, 1280, (g, w, h) => {
    g.fillStyle = '#0d0e11'; g.fillRect(0, 0, w, h);
    for (let i = 0; i < 520; i++) {
      const x = hash(i) * w, y = hash(i + 9) * h, horiz = hash(i + 3) > .5, len = 30 + hash(i + 5) * 220;
      g.strokeStyle = `rgba(${40 + hash(i + 7) * 25},${44 + hash(i + 7) * 25},${52 + hash(i + 7) * 30},.55)`; g.lineWidth = 1 + hash(i + 11) * 2;
      g.beginPath(); g.moveTo(x, y); horiz ? g.lineTo(x + len, y) : g.lineTo(x, y + len); g.lineTo(x + (horiz ? len + 20 : 20), y + (horiz ? 20 : len + 20)); g.stroke();
    }
    for (let i = 0; i < 160; i++) { g.fillStyle = hash(i + 50) > .7 ? '#2a2c33' : '#16171b'; g.fillRect(hash(i + 31) * w, hash(i + 37) * h, 6 + hash(i) * 26, 4 + hash(i + 2) * 14); }
    g.fillStyle = 'rgba(220,220,230,.22)'; g.font = '600 22px Geist, sans-serif';
    g.fillText('PCIe 5.0 x16', 560, 820); g.fillText('DDR5', 760, 260); g.fillText('M.2_1', 420, 700);
  });
}

/* ---------------- placa de vídeo (comprimento em x, altura em y, ventoinhas para -z) ---------------- */
export function buildGPU(ledMat, opts = {}) {
  const g = new THREE.Group();
  const L = .31, Hh = .125, T = .044;
  const shroud = box(L, Hh, T, M.alu(), .006); shroud.position.set(L / 2, Hh / 2, -.004); g.add(shroud);
  const back = box(L - .004, Hh - .004, .004, M.aluMid(), .0015); back.position.set(L / 2, Hh / 2, .02); g.add(back);
  // detalhes da placa traseira
  for (let i = 0; i < 6; i++) { const s = box(.002, Hh * .7, .0012, M.silver()); s.position.set(.04 + i * .006, Hh / 2, .0225); g.add(s); }
  // frente com ventoinhas
  const fronts = [];
  [.062, .155, .248].forEach(x => {
    const f = buildFan(.09, opts.fanRing || ledMat, {frameMat: M.aluMid(), bladeMat: opts.bladeMat, blurMat: opts.blurMat});
    f.group.rotation.y = Math.PI; f.group.position.set(x, Hh / 2 + .002, -.027); g.add(f.group); fronts.push(f);
  });
  // faixas prateadas e de luz no topo (borda que aparece pelo vidro)
  const strip = new THREE.Mesh(new THREE.BoxGeometry(L * .66, .004, .006), ledMat); strip.position.set(L * .52, Hh + .0005, -.004); g.add(strip);
  const acc = box(L * .9, .003, .002, M.silver()); acc.position.set(L / 2, Hh - .012, -.0265); g.add(acc);
  const acc2 = acc.clone(); acc2.position.y = .012; g.add(acc2);
  // suporte (bracket) e conector de energia
  const br = box(.002, .12, .04, M.silver()); br.position.set(-.002, .06, -.002); g.add(br);
  const pw = box(.022, .01, .012, M.plastic()); pw.position.set(.23, Hh + .005, .004); g.add(pw);
  return {group: g, fans: fronts, L, Hh, T};
}

/* ---------------- gabinete completo ---------------- */
export function buildPC({accent = 0xff2fc8, ledI = 1.7, logoTex = null} = {}) {
  const pc = new THREE.Group();
  const CW = .235, CH = .48, CD = .46, FOOT = .012;
  const ltex = ledTex();
  const ringMat = M.led(ltex, ledI);
  const ramMat = M.led(ledTex(['#b01e8c', '#ff2fc8', '#6a4cff', '#b01e8c']), ledI * .55);
  const lineMat = new THREE.MeshStandardMaterial({color: 0, emissive: new THREE.Color(accent), emissiveIntensity: ledI * 1.2});
  const alu = M.alu(), aluMid = M.aluMid(), plastic = M.plastic();
  const bladeMat = new THREE.MeshStandardMaterial({color: 0x2a2830, roughness: .35, metalness: .2, transparent: true, opacity: 1,
    emissive: new THREE.Color(0xff2fc8), emissiveIntensity: .12, side: THREE.DoubleSide});
  const blurMat = new THREE.MeshBasicMaterial({color: 0x5a2a5c, transparent: true, opacity: 0, depthWrite: false});
  const y0 = FOOT;
  // estrutura
  const top = box(CW, .022, CD, alu, .007); top.position.set(0, y0 + CH - .011, 0); pc.add(top);
  const bot = box(CW, .026, CD, alu, .007); bot.position.set(0, y0 + .013, 0); pc.add(bot);
  const left = box(.01, CH - .04, CD, alu, .003); left.position.set(-CW / 2 + .005, y0 + CH / 2, 0); pc.add(left);
  const rear = box(CW - .01, CH - .04, .01, aluMid, .002); rear.position.set(.005, y0 + CH / 2, -CD / 2 + .005); pc.add(rear);
  [[-1, -1], [-1, 1], [1, -1], [1, 1]].forEach(([sx, sz]) => {
    const f = new THREE.Mesh(new THREE.CylinderGeometry(.012, .014, FOOT, 24), M.rubber()); f.position.set(sx * (CW / 2 - .03), FOOT / 2, sz * (CD / 2 - .04)); pc.add(f);
  });
  // vidros panorâmicos (frente e lateral) com borda serigrafada preta
  const glassMat = M.glass();
  const gh = CH - .046;
  const tint = M.tint();
  const gFront = new THREE.Mesh(new THREE.PlaneGeometry(CW - .006, gh), glassMat); gFront.position.set(.003, y0 + .026 + gh / 2, CD / 2 - .001); gFront.renderOrder = 5; pc.add(gFront);
  const tFront = new THREE.Mesh(new THREE.PlaneGeometry(CW - .006, gh), tint); tFront.position.set(.003, y0 + .026 + gh / 2, CD / 2 - .0015); tFront.renderOrder = 4; pc.add(tFront);
  const gSide = new THREE.Mesh(new THREE.PlaneGeometry(CD - .012, gh), glassMat); gSide.rotation.y = Math.PI / 2; gSide.position.set(CW / 2 - .001, y0 + .026 + gh / 2, .004); gSide.renderOrder = 5; pc.add(gSide);
  const tSide = new THREE.Mesh(new THREE.PlaneGeometry(CD - .012, gh), tint); tSide.rotation.y = Math.PI / 2; tSide.position.set(CW / 2 - .0015, y0 + .026 + gh / 2, .004); tSide.renderOrder = 4; pc.add(tSide);
  const frit = new THREE.MeshStandardMaterial({color: 0x050506, roughness: .3});
  const fr = (w, h, d, x, y, z) => { const m = box(w, h, d, frit); m.position.set(x, y, z); pc.add(m); };
  fr(CW - .006, .008, .0015, .003, y0 + .03, CD / 2 - .0045); fr(CW - .006, .008, .0015, .003, y0 + CH - .024, CD / 2 - .0045);
  fr(.0015, .008, CD - .012, CW / 2 - .0045, y0 + .03, .004); fr(.0015, .008, CD - .012, CW / 2 - .0045, y0 + CH - .024, .004);
  // linhas de luz da marca na base dos vidros
  const l1 = new THREE.Mesh(new THREE.BoxGeometry(CW - .03, .0025, .0025), lineMat); l1.position.set(.003, y0 + .0275, CD / 2 - .008); pc.add(l1);
  const l2 = new THREE.Mesh(new THREE.BoxGeometry(.0025, .0025, CD - .04), lineMat); l2.position.set(CW / 2 - .008, y0 + .0275, .004); pc.add(l2);
  // interior: bandeja e placa-mãe
  const tray = box(.004, CH - .05, CD - .03, new THREE.MeshStandardMaterial({color: 0x0a0a0c, roughness: .6, metalness: .3}));
  tray.position.set(-CW / 2 + .012, y0 + CH / 2, 0); pc.add(tray);
  const mbx = -CW / 2 + .0155;
  const mb = new THREE.Mesh(new THREE.PlaneGeometry(.245, .305), new THREE.MeshStandardMaterial({map: pcbTexture(), roughness: .62, metalness: .25}));
  mb.rotation.y = Math.PI / 2; mb.position.set(mbx, y0 + .13 + .1525, -.215 + .1225); pc.add(mb);
  const S = (w, h, d, x, y, z, mat) => { const m = box(w, h, d, mat, Math.min(w, h, d) * .25); m.position.set(x, y, z); pc.add(m); return m; };
  // dissipadores de VRM, tampa do I/O, chipset e M.2
  const vrm = M.aluMid();
  S(.024, .032, .12, mbx + .012, y0 + .418, -.13, vrm);
  S(.026, .13, .034, mbx + .013, y0 + .35, -.193, vrm);
  const ioStrip = new THREE.Mesh(new THREE.BoxGeometry(.002, .09, .003), lineMat); ioStrip.position.set(mbx + .027, y0 + .35, -.178); pc.add(ioStrip);
  S(.01, .055, .07, mbx + .005, y0 + .165, -.04, vrm);
  S(.006, .026, .085, mbx + .003, y0 + .283, -.11, M.silver());
  S(.008, .012, .02, mbx + .004, y0 + .3, .022, plastic);
  // memórias RAM com barra de luz
  for (let i = 0; i < 4; i++) {
    const z = -.058 + i * .0098;
    S(.036, .133, .0066, mbx + .018, y0 + .345, z, M.aluMid());
    const bar = new THREE.Mesh(new THREE.BoxGeometry(.005, .126, .0058), ramMat); bar.position.set(mbx + .0385, y0 + .345, z); pc.add(bar);
    const cap = box(.0015, .13, .0068, M.alu()); cap.position.set(mbx + .0418, y0 + .345, z); pc.add(cap);
  }
  // water cooler: bomba com o logo do AZOR
  const pump = new THREE.Group();
  const pBody = new THREE.Mesh(new THREE.CylinderGeometry(.034, .036, .024, 64), M.aluMid()); pBody.rotation.z = Math.PI / 2; pump.add(pBody);
  const pRing = new THREE.Mesh(new THREE.TorusGeometry(.031, .0022, 12, 96), ringMat); pRing.rotation.y = Math.PI / 2; pRing.position.x = .0125; pump.add(pRing);
  const pFace = new THREE.Mesh(new THREE.CircleGeometry(.028, 64), logoTex ? new THREE.MeshBasicMaterial({map: logoTex, color: new THREE.Color(.75, .75, .75)}) : M.plastic());
  pFace.rotation.y = Math.PI / 2; pFace.position.x = .0124; pump.add(pFace);
  const pGlass = new THREE.Mesh(new THREE.CircleGeometry(.0295, 64), new THREE.MeshPhysicalMaterial({color: 0, roughness: .05, transparent: true, opacity: 1, blending: THREE.AdditiveBlending, envMapIntensity: .7}));
  pGlass.rotation.y = Math.PI / 2; pGlass.position.x = .0127; pump.add(pGlass);
  pump.position.set(mbx + .0135, y0 + .36, -.118); pc.add(pump);
  // radiador no topo e mangueiras
  const rad = S(.115, .03, .36, .03, y0 + CH - .043, -.01, M.aluMid());
  for (let i = 0; i < 2; i++) {
    const curve = new THREE.CatmullRomCurve3([
      new THREE.Vector3(mbx + .02, y0 + .38, -.1 + i * .016), new THREE.Vector3(mbx + .05, y0 + .41, -.07 + i * .02),
      new THREE.Vector3(.0, y0 + .43, .05 + i * .02), new THREE.Vector3(.02, y0 + CH - .06, .11 + i * .02)]);
    pc.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 48, .0055, 16), M.rubber()));
  }
  // placa de vídeo horizontal: comprimento em z, altura em x (rumo ao vidro), ventoinhas para baixo
  const gpu = buildGPU(lineMat, {fanRing: ringMat, bladeMat, blurMat});
  const basis = new THREE.Matrix4().makeBasis(new THREE.Vector3(0, 0, 1), new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 1, 0));
  gpu.group.setRotationFromMatrix(basis);
  gpu.group.position.set(mbx + .006, y0 + .19, -CD / 2 + .02);
  pc.add(gpu.group);
  // tampa da fonte com AZOR retroiluminado
  const shroud = S(CW - .016, .078, CD - .09, .004, y0 + .026 + .039, -.03, alu);
  const azor = canvasTex(1024, 256, (g2, w, h) => {
    g2.fillStyle = '#000'; g2.fillRect(0, 0, w, h);
    g2.fillStyle = '#fff'; g2.font = '600 150px Geist, sans-serif'; g2.textAlign = 'center'; g2.textBaseline = 'middle';
    g2.letterSpacing = '60px'; g2.fillText('AZOR', w / 2 + 30, h / 2 + 6);
  });
  const azorMat = new THREE.MeshStandardMaterial({color: 0, emissive: new THREE.Color(0xffe6f8), emissiveMap: azor, emissiveIntensity: 1.3});
  const azorPlane = new THREE.Mesh(new THREE.PlaneGeometry(.18, .045), azorMat);
  azorPlane.rotation.y = Math.PI / 2; azorPlane.position.set(CW / 2 - .0039, y0 + .065, -.03); pc.add(azorPlane);
  // ventoinhas: 3 na frente, 1 atrás
  const fans = [];
  // cada ventoinha tem o próprio anel de LED, para a luz "subir" em onda
  const fanRings = [];
  [.105, .24, .375].forEach(y => { const rm = ringMat.clone(); fanRings.push(rm); const f = buildFan(.12, rm, {bladeMat, blurMat}); f.group.position.set(.005, y0 + y, CD / 2 - .045); pc.add(f.group); fans.push(f); });
  const rrm = ringMat.clone(); fanRings.push(rrm);
  const rf = buildFan(.12, rrm, {bladeMat, blurMat}); rf.group.rotation.y = Math.PI; rf.group.position.set(0, y0 + .37, -CD / 2 + .025); pc.add(rf.group); fans.push(rf);
  fans.push(...gpu.fans);
  // luzes internas (o RGB ilumina o interior)
  const lights = [];
  const pl = (col, I, x, y, z, d = .55) => { const l = new THREE.PointLight(col, I, d, 2); l.position.set(x, y0 + y, z); pc.add(l); lights.push(l); return l; };
  pl(accent, .12, .02, .25, .16, .4); pl(0x8b6cff, .1, .03, .38, -.12, .4); pl(0xfff0f8, .06, .07, .3, -.02, .35);
  return {group: pc, fans, fanRings, ringMat, ramMat, lineMat, azorMat, glassMat, bladeMat, blurMat, lights, pump, dims: {CW, CH, CD, y0}};
}

/* reflexo no chão: cópia espelhada sob um piso translúcido */
export function mirror(obj) {
  const m = obj.clone(true); m.scale.y = -obj.scale.y; m.position.y = -obj.position.y; m.updateMatrixWorld(true);
  m.traverse(o => { if (o.isPointLight) o.visible = false; });
  const rotors = []; m.traverse(o => { if (o.name === 'rotor') rotors.push(o); });
  m.traverse(o => { if (o.isLight) o.intensity *= .3; });
  return {group: m, rotors};
}
export function floor({opacity = .86, color = 0x070709} = {}) {
  const g = new THREE.Group();
  const f = new THREE.Mesh(new THREE.PlaneGeometry(40, 40), new THREE.MeshStandardMaterial({color, roughness: .42, metalness: .1, transparent: true, opacity, envMapIntensity: .6}));
  f.rotation.x = -Math.PI / 2; g.add(f);
  return g;
}
export function contactShadow(w, d, strength = .9) {
  const t = radialTex([[0, `rgba(0,0,0,${strength})`], [.55, `rgba(0,0,0,${strength * .55})`], [1, 'rgba(0,0,0,0)']]);
  const m = new THREE.Mesh(new THREE.PlaneGeometry(w, d), new THREE.MeshBasicMaterial({map: t, transparent: true, depthWrite: false}));
  m.rotation.x = -Math.PI / 2; m.position.y = .0008; m.renderOrder = 2;
  return m;
}
export function halo(w, h, stops, opacity = .5) {
  const t = radialTex(stops, 512);
  const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({map: t, transparent: true, opacity, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false}));
  return m;
}
/* poeira em suspensão (pega luz, vira bokeh) */
export function dust(n = 500, bounds = [2, 1.4, 2], center = [0, .6, 0]) {
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(n * 3), seed = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    pos[i * 3] = center[0] + (hash(i * 3.1) - .5) * bounds[0];
    pos[i * 3 + 1] = center[1] + (hash(i * 5.7) - .5) * bounds[1];
    pos[i * 3 + 2] = center[2] + (hash(i * 7.3) - .5) * bounds[2];
    seed[i] = hash(i * 1.37);
  }
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('seed', new THREE.BufferAttribute(seed, 1));
  const mat = new THREE.ShaderMaterial({
    uniforms: {time: {value: 0}, size: {value: 26}, color: {value: new THREE.Color(0xffd9f4)}, opacity: {value: .55}},
    vertexShader: `attribute float seed; uniform float time, size; varying float vA;
      void main(){ vec3 p = position; p.x += sin(time*.23 + seed*40.)*.03; p.y += sin(time*.17 + seed*90.)*.04 + time*.006*(seed-.5); p.z += cos(time*.19 + seed*70.)*.03;
        vec4 mv = modelViewMatrix * vec4(p,1.); gl_Position = projectionMatrix * mv;
        gl_PointSize = size * (.4 + seed) / -mv.z; vA = .25 + .75 * fract(seed*7.13); }`,
    fragmentShader: `uniform vec3 color; uniform float opacity; varying float vA;
      void main(){ float d = length(gl_PointCoord - .5); float a = smoothstep(.5, .0, d); gl_FragColor = vec4(color, a * opacity * vA); }`,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  });
  return new THREE.Points(geo, mat);
}

/* ---------------- monitor ---------------- */
export function buildMonitor(screenMat, {w = .62} = {}) {
  const g = new THREE.Group();
  const h = w * 9 / 16;
  const body = box(w + .018, h + .018, .014, M.alu(), .005); g.add(body);
  const scr = new THREE.Mesh(new THREE.PlaneGeometry(w, h), screenMat); scr.position.z = .0072; g.add(scr);
  const gl = new THREE.Mesh(new THREE.PlaneGeometry(w + .012, h + .012), new THREE.MeshPhysicalMaterial({color: 0, roughness: .06, transparent: true, blending: THREE.AdditiveBlending, envMapIntensity: .55}));
  gl.position.z = .0076; g.add(gl);
  const backC = box(w * .5, h * .5, .03, M.aluMid(), .01); backC.position.set(0, -h * .05, -.02); g.add(backC);
  const neck = box(.05, .26, .02, M.alu(), .006); neck.position.set(0, -h / 2 - .06, -.045); g.add(neck);
  const base = box(.26, .012, .19, M.alu(), .005); base.position.set(0, -h / 2 - .19, -.03); g.add(base);
  return {group: g, screen: scr, w, h};
}

/* ---------------- painel de interface flutuante ---------------- */
export function buildPanel(tex, w, aspect, {radius = .03, glow = .25} = {}) {
  const g = new THREE.Group();
  const h = w / aspect;
  const shape = roundedRectShape(w, h, radius);
  const geo = new THREE.ShapeGeometry(shape, 24);
  // UVs para a textura cobrir o retângulo inteiro
  const p = geo.attributes.position, uv = geo.attributes.uv;
  for (let i = 0; i < p.count; i++) uv.setXY(i, p.getX(i) / w + .5, p.getY(i) / h + .5);
  const mat = new THREE.MeshBasicMaterial({map: tex, toneMapped: false, transparent: true});
  const m = new THREE.Mesh(geo, mat); g.add(m);
  const edge = new THREE.Mesh(new THREE.ShapeGeometry(roundedRectShape(w + .006, h + .006, radius + .003), 24),
    new THREE.MeshBasicMaterial({color: 0xffffff, transparent: true, opacity: .14, toneMapped: false}));
  edge.position.z = -.001; g.add(edge);
  const sh = halo(w * 1.9, h * 2.1, [[0, 'rgba(255,47,200,.55)'], [.5, 'rgba(120,70,255,.18)'], [1, 'rgba(0,0,0,0)']], glow);
  sh.position.z = -.02; g.add(sh);
  return {group: g, mat, w, h};
}
