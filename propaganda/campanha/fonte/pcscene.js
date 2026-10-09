// Estúdio compartilhado: o PC, luzes, chão, reflexo, poeira e controles de "potência".
import {THREE, studioEnv, loadTex, lerp, clamp, prog, ease} from '/engine.js';
import {buildPC, mirror, floor, contactShadow, halo, dust} from '/assets.js';

export async function pcStudio(st, opts = {}) {
  const {scene, renderer} = st;
  scene.environment = studioEnv(renderer);
  scene.environmentIntensity = opts.envI ?? .55;
  scene.fog = new THREE.Fog(0x050407, opts.fogNear ?? 2.6, opts.fogFar ?? 7);
  const logo = await loadTex('/web/assets/Azor_icon.png');
  const pc = buildPC({logoTex: logo});
  scene.add(pc.group);
  const refl = mirror(pc.group); scene.add(refl.group);
  scene.add(floor());
  scene.add(contactShadow(.5, .7, .95));
  const hl = halo(3.4, 3.4, [[0, 'rgba(255,47,200,.35)'], [.45, 'rgba(110,60,255,.1)'], [1, 'rgba(0,0,0,0)']], .12);
  hl.position.set(-.2, .55, -1.6); scene.add(hl);
  const dst = dust(90, [1.6, 1.0, 1.2], [.2, .5, 1.0]);
  dst.material.uniforms.opacity.value = .1; dst.material.uniforms.size.value = 70; scene.add(dst);
  const key = new THREE.RectAreaLight(0xfff1e6, 2.2, 1.2, .8); key.position.set(-.9, 1.3, 1.1); key.lookAt(0, .25, 0); scene.add(key);
  const rimM = new THREE.SpotLight(0xff2fc8, 2.6, 3, .26, .95, 2); rimM.position.set(-.6, 1.25, -.95); rimM.target.position.set(0, .46, -.05); scene.add(rimM, rimM.target);
  const rimV = new THREE.SpotLight(0xcfd8ff, 5, 4, .38, .9, 2); rimV.position.set(1.0, 1.0, -.8); rimV.target.position.set(0, .35, 0); scene.add(rimV, rimV.target);
  const glint = new THREE.RectAreaLight(0xffffff, 0, .05, 1.8); glint.position.set(0, .4, 1.0); glint.lookAt(0, .3, 0); scene.add(glint);
  const base = {ring: pc.ringMat.emissiveIntensity, ram: pc.ramMat.emissiveIntensity, line: pc.lineMat.emissiveIntensity,
    azor: pc.azorMat.emissiveIntensity, blade: pc.bladeMat.emissiveIntensity, lights: pc.lights.map(l => l.intensity)};
  // p: 0 = PC "preso" (luz fraca), 1 = desperto. wave: atraso extra por ventoinha (de baixo para cima)
  function power(t, t0 = Infinity, dur = 1.4, lo = .12) {
    const at = (delay) => lerp(lo, 1, ease.out(prog(t, t0 + delay, t0 + delay + dur)));
    pc.fanRings.forEach((m, i) => { m.emissiveIntensity = base.ring * at(i * .14); });
    pc.ringMat.emissiveIntensity = base.ring * at(.3);
    pc.ramMat.emissiveIntensity = base.ram * at(.42);
    pc.lineMat.emissiveIntensity = base.line * at(0);
    pc.azorMat.emissiveIntensity = base.azor * at(.2);
    pc.bladeMat.emissiveIntensity = base.blade * at(.1);
    pc.lights.forEach((l, i) => { l.intensity = base.lights[i] * at(.2); });
    return at(0);
  }
  // ventoinhas: velocidade em rotações/s com rampa suave; ângulo = integral da velocidade
  function fans(t, r0 = .6, r1 = 11, t0 = Infinity, dur = 1.6) {
    const speed = u => lerp(r0, r1, ease.io(prog(u, t0, t0 + dur)));
    let ang = 0;
    const steps = 240, dt = t / steps;
    for (let i = 0; i < steps; i++) ang += speed((i + .5) * dt) * dt;
    const rps = speed(t);
    pc.fans.forEach((f, i) => { f.rotor.rotation.z = (ang + i * .13) * Math.PI * 2; });
    refl.rotors.forEach((r, i) => { r.rotation.z = (ang + i * .13) * Math.PI * 2; });
    const blur = clamp((rps - 3.5) / 6);
    pc.bladeMat.opacity = 1 - .8 * blur;
    pc.blurMat.opacity = .5 * blur;
    return rps;
  }
  return {pc, refl, key, rimM, rimV, glint, dust: dst, halo: hl, power, fans, logo};
}
