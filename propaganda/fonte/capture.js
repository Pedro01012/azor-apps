// Renderiza a interface real do AZOR (web/) com um backend simulado e salva telas em alta resolução.
const {chromium} = require('playwright');
const fs = require('fs');
const path = require('path');

const ROOT = __dirname;
const WEB = path.join(ROOT, 'web');
const OUT = path.join(ROOT, 'shots');
fs.mkdirSync(OUT, {recursive: true});
const MD = fs.readFileSync(process.argv[2], 'utf8');

/* ---------- catálogo de tweaks a partir do TWEAKS.md ---------- */
const GOAL_IDS = {'Mais FPS': ['fps', 'fps'], 'Menos delay': ['delay', 'delay'], 'Sem travadinhas': ['stutter', 'stutter'],
  'Internet e ping': ['ping', 'ping'], 'Windows leve': ['leve', 'leve'], 'Privacidade': ['privacidade', 'privacy'],
  'Visual e conforto': ['visual', 'visual'], 'Consertos': ['reparo', 'repair'], 'Avançado': ['avancado', 'lab']};
const goals = [], tasks = [];
let cur = null, hintNext = false, n = 0;
for (const line of MD.split('\n')) {
  const h = line.match(/^## (.+)$/);
  if (h) { const [id, ic] = GOAL_IDS[h[1].trim()] || ['avancado', 'lab']; cur = {id, label: h[1].trim(), icon: ic, hint: ''}; goals.push(cur); hintNext = true; continue; }
  if (cur && hintNext && line.trim() && !line.startsWith('|')) { cur.hint = line.trim(); hintNext = false; continue; }
  const r = line.match(/^\| \*\*(.+?)\*\*<br>(.+?) \| (.*?) \| (.*?) \| (.*?) \| (.*?) \|$/);
  if (r && cur) {
    const badges = [...r[3].matchAll(/`([^`]+)`/g)].map(m => m[1]);
    const boost = /Recomendado/.test(r[4]) ? 'recomendado' : /Extremo/.test(r[4]) ? 'extremo' : null;
    tasks.push({id: 't' + (++n), title: r[1], name: r[1], simple: r[2], description: r[2], badges, goal: cur.id,
      impact: badges.length >= 2 ? 3 : 2, boost, restart: r[5].trim() === 'sim', can_revert: r[6].trim() === 'sim', eligible: true, state: 'pending'});
  }
}
console.log('tweaks:', tasks.length, 'goals:', goals.length);

/* ---------- estado simulado ---------- */
const PC = {label: 'Desktop competitivo', cpu: '13th Gen Intel(R) Core(TM) i5-13400F', topology: {hybrid: true, performance_cores: 6, efficiency_cores: 4},
  gpus: ['NVIDIA GeForce GTX 1660 SUPER'], ram_gb: 16, battery: false};
const S = {after: false, jobStage: 0, jobDone: false};
const plan = () => S.after ? {score: 97, grade: 'NOTA', todo: 1, done: 23, pc: {label: 'Desktop competitivo'}, steps: []}
  : {score: 41, grade: 'NOTA', todo: 14, done: 6, pc: {label: 'Desktop competitivo'}, steps: []};
const overview = () => ({admin: true, mode: 'auto', windows: 'Windows-11', pc: PC, logon: {enabled: S.after},
  turbo: S.after ? {enabled: true, timer: {active: true, actual_ms: 0.5}, priority: {active: true, raised: 1}, memory: {active: true, cycles: 2}} : {enabled: false},
  plan: plan(), pending_reboot: S.after ? ['Agendamento de GPU por hardware'] : [],
  last_boost: S.after ? {time: Date.now() / 1000 - 30, detail: 'Modo AUTOMÁTICO · 71 ajustes · pré-set Desktop competitivo', report_id: 'r1'} : null});
const preset = {ok: true, name: 'Desktop · Intel 13ª/14ª geração · NVIDIA GTX 16xx · 16 GB · SSD NVMe · Jogo competitivo', key: 'desktop.intel13.gtx16.ram16.nvme',
  use: 'competitivo', turbo: true,
  chips: [['form', 'Desktop'], ['cpu', 'Intel 13ª/14ª geração'], ['gpu', 'NVIDIA GTX 16xx'], ['ram', '16 GB'], ['disk', 'SSD NVMe'], ['os', 'Windows 11'], ['net', 'Cabo de rede'], ['display', 'Monitor 144 Hz']].map(([dim, label]) => ({dim, label, detail: label})),
  add: {t1: 'GPU dedicada', t4: 'HAGS', t3: 'Plano de energia', t14: 'Mouse', t17: 'USB'}, skip: {t40: 'protegido', t41: 'protegido'}, notes: [],
  memory: {known: true, applied_count: 0}, library: {combinations: 4860}};
const monitor = () => S.after ? {cpu: {usage: 6, temp_c: 39}, gpu: {usage: 3, temp_c: 36, name: 'GTX 1660 SUPER'}, ram: {percent: 31, used_gb: 5, total_gb: 16}, disk: {percent: 52, used_gb: 242, total_gb: 465}}
  : {cpu: {usage: 34, temp_c: 57}, gpu: {usage: 18, temp_c: 46, name: 'GTX 1660 SUPER'}, ram: {percent: 71, used_gb: 11.4, total_gb: 16}, disk: {percent: 66, used_gb: 307, total_gb: 465}};

const pick = ids => ids.map(i => tasks[i]).filter(Boolean);
const EVENTS = [
  {name: 'Ponto de restauração', status: 'completed', detail: 'criado — dá para voltar tudo'},
  {name: 'Pré-set do hardware', status: 'completed', detail: 'Desktop competitivo reconhecido'},
  ...pick([0, 1, 2, 3, 5, 8, 13, 14, 16, 23, 24, 26]).map(t => ({name: t.title, status: 'completed', detail: 'aplicado e confirmado'})),
  {name: 'Apps inúteis', status: 'completed', detail: '23 removidos'},
  {name: 'Inicialização', status: 'completed', detail: '9 programas fora do boot'},
  {name: 'Arquivos inúteis', status: 'completed', detail: '6,7 GB liberados'},
];
const RESULT = {ok: true, restart: true, mode_label: 'AUTOMÁTICO', detail: 'Pré-set Desktop competitivo',
  tweaks: {changed: 64, already: 7, restart: true, failed_items: []}, apps: {removed: 23}, startup: {disabled: new Array(9).fill('x')},
  cleanup: {freed_mb: 6860}, before: {processes: 212, ram_used_mb: 11650}, after: {processes: 147, ram_used_mb: 7120}};

function api(url, method) {
  const p = new URL(url).pathname;
  if (method === 'POST') {
    if (p === '/api/jobs') return {job: {id: 'j1'}};
    return {ok: true, detail: 'ok'};
  }
  if (p === '/api/overview') return overview();
  if (p === '/api/plan') return plan();
  if (p === '/api/preset') return preset;
  if (p === '/api/monitor') return monitor();
  if (p === '/api/tweaks') return {goals, tasks: tasks.map(t => ({...t, state: S.after && t.boost ? 'applied' : 'pending'}))};
  if (p === '/api/settings') return {};
  if (p === '/api/dns') return {providers: [{id: 'cf', label: 'Cloudflare (1.1.1.1)'}], current: 'cf'};
  if (p.startsWith('/api/jobs/')) return {job: {id: 'j1', status: S.jobDone ? 'completed' : 'running', phase: 'Aplicando ajustes de desempenho…',
    events: EVENTS.slice(0, S.jobStage), result: S.jobDone ? RESULT : null}};
  return {};
}

const FONT_FIX = `
@font-face{font-family:"Segoe UI";src:local("Inter");}
:root{--font:"Inter",sans-serif !important;--font-title:"Inter Display","Inter",sans-serif !important;--font-display:"Inter Display","Inter",sans-serif !important;}
*{scrollbar-width:none} ::-webkit-scrollbar{display:none}
.backdrop,.modal,.toast{animation:none !important} [data-foot][hidden]{display:none !important}
`;

(async () => {
  const browser = await chromium.launch();
  const W = 1600, H = 900;
  const ctx = await browser.newContext({viewport: {width: W, height: H}, deviceScaleFactor: 2, reducedMotion: 'no-preference'});
  await ctx.route('http://azor.local/**', async route => {
    const req = route.request();
    const u = new URL(req.url());
    if (u.pathname.startsWith('/api/')) {
      return route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(api(req.url(), req.method()))});
    }
    const f = path.join(WEB, decodeURIComponent(u.pathname === '/' ? '/index.html' : u.pathname));
    if (!f.startsWith(WEB) || !fs.existsSync(f)) return route.fulfill({status: 404, body: ''});
    let body = fs.readFileSync(f);
    if (f.endsWith('index.html')) body = Buffer.from(body.toString().replace('</head>', `<style>${FONT_FIX}</style></head>`));
    return route.fulfill({status: 200, body});
  });
  const page = await ctx.newPage();
  const rects = {};
  const rect = async (name, sel) => { const b = await page.locator(sel).first().boundingBox(); if (b) rects[name] = b; };
  const shot = async name => { await page.waitForTimeout(450); await page.screenshot({path: path.join(OUT, name + '.png')}); console.log('shot', name); };

  await page.goto('http://azor.local/index.html#home');
  await page.waitForSelector('.pc-card .score-ring');
  await page.waitForTimeout(1500);
  await rect('home.boost', '#boostBtn');
  await rect('home.pc', '.pc-card');
  await rect('home.hero', '.boost-card');
  await rect('home.preset', '#presetCard');
  await rect('home.score', '.pc-card .score-ring');
  await shot('home_before');

  await page.click('#boostBtn');
  await page.waitForSelector('[data-go]');
  await rect('modal', '.modal');
  await rect('modal.go', '[data-go]');
  await shot('modal');

  await page.click('[data-go]');
  const stages = [1, 3, 5, 7, 9, 11, 13, 15, EVENTS.length];
  for (let i = 0; i < stages.length; i++) {
    S.jobStage = stages[i];
    await page.waitForTimeout(900);
    await shot('job_' + i);
  }
  await rect('job', '.modal');
  S.after = true;
  S.jobDone = true;
  await page.waitForSelector('.result-hero');
  await page.evaluate(() => { const ev = document.querySelector('[data-events]'); if (ev) ev.style.display = 'none'; });
  await rect('result', '.modal');
  await rect('result.hero', '.result-hero');
  await rect('result.compare', '.compare');
  await shot('result');

  await page.click('[data-close]');
  await page.waitForTimeout(400);
  await page.evaluate(() => AZ.go('home'));
  await page.waitForSelector('.pc-card .score-ring');
  await page.waitForFunction(() => document.querySelector('.pc-card .num b')?.textContent === '97');
  await page.waitForTimeout(1000);
  await rect('after.score', '.pc-card .score-ring');
  await rect('after.pc', '.pc-card');
  await shot('home_after');

  // Tweaks: página alta para fazer rolagem no vídeo.
  await page.setViewportSize({width: W, height: 3200});
  await page.evaluate(() => AZ.go('tweaks'));
  await page.waitForSelector('#tweakList .item');
  await page.waitForTimeout(800);
  await shot('tweaks_tall');

  fs.writeFileSync(path.join(OUT, 'rects.json'), JSON.stringify(rects, null, 1));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
