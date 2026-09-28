const $ = (s, r=document) => r.querySelector(s);
const $$ = (s, r=document) => [...r.querySelectorAll(s)];

// ---------------------------------------------------------------------------
// Quatro destinos, nao doze
// ---------------------------------------------------------------------------
//
// O menu tinha 12 entradas em 3 grupos, e o app respondia por 24 rotas. Isso
// pede que o cliente saiba de antemao que "Arsenal", "Plano de Acao" e
// "Otimizar PC" sao a mesma tarefa vista de tres angulos - e ninguem sabe.
//
// Nenhuma tela foi apagada e nenhuma funcao saiu do codigo: cada rota antiga
// continua existindo e continua respondendo pelo mesmo nome. O que mudou e que
// elas viraram ABAS dentro de cinco agrupadores. Um link velho para 'stutter'
// abre o agrupador Maquina ja na aba certa.
//
// A tela inicial passou a resolver sozinha o que a maioria quer: escolher entre
// MAXIMO e AGRESSIVO e tocar em BOOST. O que era o agrupador "Maquina" virou aba
// de "Avancado", para quem nao entende de PC nao precisar abrir nada.
const NAV = [
  ['home','⌂','Início'],
  ['quick','ϟ','Avançado'],
  ['device','◈','Periféricos'],
  ['settings','⚙','Ajustes'],
];

// hub -> abas. A ordem aqui e a ordem na tela.
const HUBS = {
  quick:   {label:'Avançado', tabs:[
    ['quick','Otimização'], ['monitor','Monitoramento'], ['energy','Energia'], ['gameMode','Modo de jogo'],
    ['declutter','Windows mais limpo'], ['services','Serviços'], ['plan','Plano de Ação'], ['arsenal','Todos os ajustes'],
    ['hardware','Hardware'], ['bios','BIOS'], ['fortnite','Fortnite'], ['games','Outros Jogos'], ['windows','Windows'],
    ['network','Rede'], ['stutter','Travamentos'], ['latency','Latência & ISLC'], ['gameDiag','Diagnóstico'],
    ['guardian','Guardian'], ['maintenance','Manutenção'], ['advanced','Comandos avançados']]},
  device:  {label:'Periféricos', tabs:[]},   // ja tem abas proprias por dentro
  settings:{label:'Ajustes', tabs:[
    ['settings','Configurações'], ['restore','Restaurar'], ['logs','Registros']]},
};

// Rota -> agrupador que a contem. Serve para acender o item certo do menu
// quando alguem chega por um link antigo.
const PAGE_HUB = (() => {
  const m = {};
  for(const [hub, def] of Object.entries(HUBS)){
    m[hub] = hub;
    for(const [page] of def.tabs) m[page] = hub;
  }
  for(const p of ['keyboardmouse','controller']) m[p] = 'device';
  for(const p of ['islc','measure']) m[p] = 'quick';
  return m;
})();

function hubOf(page){ return PAGE_HUB[page] || (page === 'home' ? 'home' : null); }

function hubTabs(page){
 const hub=hubOf(page),def=hub&&HUBS[hub];
 if(!def||!def.tabs.length)return '';
 const primary=new Set(['quick','declutter','monitor','gameMode','settings','restore',page]);
 const tab=([key,label])=>`<button type="button" class="hub-tab ${key===page?'active':''}" data-hub-tab="${key}" aria-current="${key===page?'page':'false'}">${label}</button>`;
 const visible=def.tabs.filter(([key])=>S.settings.mode==='Expert'||primary.has(key));
 const extras=def.tabs.filter(([key])=>!visible.some(([v])=>v===key));
 return `<nav class="hub-tabs" aria-label="${def.label}">${visible.map(tab).join('')}${extras.length?`<details><summary class="hub-tab">Mais ferramentas</summary><div class="hub-tabs">${extras.map(tab).join('')}</div></details>`:''}</nav>`;
}

const S = {
  page:'home', summary:null, monitor:null, history:{cpu:[],gpu:[],ram:[],net:[],sleep:[]},
  controllerType:'xbox', controllerHue:0, latencyTab:'islc', settings:{mode:'Simple',accent:'#ff2fc8',animations:true,show_tips:true},
  monitorTimer:null, lastPing:null, measureResult:null, latencyBaseline:null, latencyAfter:null, latencyOptimizing:false, latencyProgress:'', competitiveSessionRunning:false, lastQuickResult:null, sessionMeasurement:null, health:null, maintenance:null, bios:null, analysis:null, stutter:null, gameDiag:null, gameReports:[], gameDiagPoll:null, gamesGpu:[], selectedGameExe:'', quickProfile:(()=>{try{const saved=localStorage.getItem('azor.quickProfile');return saved&&saved!=='auto'?saved:'maximo'}catch(e){return 'maximo'}})(),
  inputLab:null, hardware:null, thermal:null, biosCopilot:null, azorWindows:null, inputLive:null, inputLiveSource:null,
  inputSelected:{controller:0,mouse:0,keyboard:0},
  periphTab:'controller', padSkin:'auto', inputCaps:null, remap:null, remapDraft:null, remapPick:null,
  padLive:null, kbFormat:'auto', kbLayoutMap:null, kbDetected:null, kbMax:0, kbPressBase:0, clickBase:null, cpsTimes:[], cpsMax:0, mousePeak:0,
  inputPreset:{controller:'competitive',mouse:'competitive',keyboard:'competitive'}, inputDeviceTab:'mouse',
  selectionReady:true, restorePoints:null, simulation:null, autostart:null, autostartLoading:false, modeCleanup:null, modeCleanupLoading:false, usbIrq:null, usbIrqLoading:false,
  arsenal:null, arsenalFilter:'all', arsenalQuery:'', azorIndex:null, startup:null, firmware:null, drift:null, proofs:{}, driverGuide:null, plan:null,
  boost:{running:false,phase:null,progress:0,log:[],analysisBefore:null,analysisAfter:null,result:null,latencyBefore:null,latencyAfter:null,finishedAt:null,bottleneck:null,indexBefore:null,indexAfter:null},
};

const controllerAssets = {
  xbox:{name:'Xbox / XInput',accent:'#38e577',desc:'Visual 2D genérico, sem logo de terceiros.'},
  ps5:{name:'PS5 / DualSense style',accent:'#35a8ff',desc:'Visual 2D genérico inspirado no formato, sem marca impressa.'},
  ps4:{name:'PS4 / DualShock style',accent:'#8a69ff',desc:'Visual 2D genérico inspirado no formato, sem marca impressa.'}
};
const controllerColors={0:'#ffffff',45:'#ff4dce',90:'#a75cff',150:'#2f9cff',215:'#30e1c2',280:'#54e878'};
function controllerTint(){return controllerColors[S.controllerHue]||controllerAssets[S.controllerType].accent}

function esc(v=''){return String(v).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
function fmt(v,suffix=''){return v===null||v===undefined||Number.isNaN(Number(v))?'Indisponível':`${v}${suffix}`}
function clamp(v,a,b){return Math.min(b,Math.max(a,v))}
const PROFILE_NAMES={auto:'AUTO',safe:'SEGURO',competitive:'COMPETITIVO',ultra:'AZOR ULTRA',campanha:'CAMPANHA',stream:'JOGO + LIVE',maximo:'MÁXIMO',agressivo:'AGRESSIVO'};
// Os dois modos da tela inicial. O que ganha e o que custa, sem sigla: quem abre
// o AZOR pela primeira vez precisa decidir isso sem ler documentação.
const PERFORMANCE_MODES={
  maximo:{label:'MÁXIMO',tag:'Recomendado',hint:'Conserta o que outros programas quebraram e aplica tudo que acelera de verdade, com volta garantida.'},
  agressivo:{label:'AGRESSIVO',tag:'Sem freio',hint:'Libera também os ajustes arriscados: mais calor, mais consumo e chance de instabilidade.'},
};
function profileLabel(value){return PROFILE_NAMES[value]||'COMPETITIVO'}
// Converts CSS hex colors to the "r,g,b" form used by --accent-rgb.
// V5.2 referenced this helper from all Device pages but never defined it,
// which made Device Lab / Keyboard & Mouse / Controller fail before 3D mounted.
function hexRgb(value='#ff2fc8'){
  let s=String(value||'').trim().replace('#','');
  if(s.length===3)s=s.split('').map(x=>x+x).join('');
  if(!/^[0-9a-f]{6}$/i.test(s))s='ff2fc8';
  return `${parseInt(s.slice(0,2),16)},${parseInt(s.slice(2,4),16)},${parseInt(s.slice(4,6),16)}`;
}
function navIcon(key){
  const paths={home:'M3 10 12 3l9 7M5 9v12h5v-7h4v7h5V9',
    quick:'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
    device:'M8 7h8a5 5 0 0 1 5 5l1 5a3 3 0 0 1-5 2l-2-2H9l-2 2a3 3 0 0 1-5-2l1-5a5 5 0 0 1 5-5ZM6 12h4M8 10v4M16 11h.01M18 14h.01',
    monitor:'M4 3v18h18M8 16v-4M13 16V8M18 16V5',
    settings:'M4 6h16M4 12h16M4 18h16M8 3v6M16 9v6M10 15v6'};
  return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="'+paths[key]+'"/></svg>';
}
// Icones de linha no mesmo traco do menu. Os glifos Unicode antigos dos cards
// vinham de fontes diferentes, e cada card parecia de um app.
const UI_ICONS={
  bolt:'m13 2-9 12h7l-1 8 10-12h-7z',
  checklist:'m3 17 2 2 4-4M3 7l2 2 4-4M13 6h8M13 12h8M13 18h8',
  sliders:'M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M2 14h4M10 8h4M18 16h4',
  target:'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20ZM22 12h-4M6 12H2M12 6V2M12 22v-4',
  gamepad:'M8 7h8a5 5 0 0 1 5 5l1 5a3 3 0 0 1-5 2l-2-2H9l-2 2a3 3 0 0 1-5-2l1-5a5 5 0 0 1 5-5ZM6 12h4M8 10v4M16 11h.01M18 14h.01',
  activity:'M22 12h-4l-3 9L9 3l-3 9H2',
  chip:'M4 4h16v16H4zM9 9h6v6H9zM9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3',
  wave:'M2 13a2 2 0 0 0 2-2V7a2 2 0 0 1 4 0v13a2 2 0 0 0 4 0V4a2 2 0 0 1 4 0v13a2 2 0 0 0 4 0v-4a2 2 0 0 1 2-2',
  signal:'M12 20h.01M2 8.82a15 15 0 0 1 20 0M5 12.86a10 10 0 0 1 14 0M8.5 16.43a5 5 0 0 1 7 0',
  timer:'M10 2h4M12 14l3-3M12 22a8 8 0 1 0 0-16 8 8 0 0 0 0 16Z',
  undo:'M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8M3 3v5h5',
  arrow:'M7 7h10v10M7 17 17 7',
};
function uiIcon(key){return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="'+(UI_ICONS[key]||UI_ICONS.arrow)+'"/></svg>'}
function applyAccent(value='#ff2fc8'){
  const color=/^#[0-9a-f]{6}$/i.test(String(value||''))?String(value):'#ff2fc8';
  const root=document.documentElement;
  root.style.setProperty('--accent',color);
  root.style.setProperty('--accent-rgb',hexRgb(color));
  root.style.setProperty('--brand',color);
  root.style.setProperty('--brand-rgb',hexRgb(color));
  document.body?.classList.toggle('reduce-motion',S.settings.animations===false);
}
// Every call is bounded in time. Without this a single request that never
// answers (backend killed, machine asleep mid-request) left the polling loop
// waiting forever and the screen frozen on stale numbers with no error shown.
const API_TIMEOUT_MS=20000;
const ANALYSIS_TIMEOUT_MS=90000;
const ACTION_TIMEOUT_MS=240000;
const resultOK=x=>['completed','verified','applied'].includes(x?.status);
const resultPreserved=x=>['skipped','preserved','not_applicable'].includes(x?.status);
const resultFailed=x=>['failed','error'].includes(x?.status);
function requestTimeout(url){return /\/api\/(analyze|bottleneck|hardware-profile|action-plan|arsenal|azor-index)/.test(url)?ANALYSIS_TIMEOUT_MS:API_TIMEOUT_MS}
// Handed over by the backend inside the page it served. A page from any other
// origin cannot read it, which is what stops a random website from POSTing
// system changes to the local port.
let AZOR_TOKEN=document.querySelector('meta[name="azor-token"]')?.content||'';
// O backend sorteia um token novo a cada vez que sobe. Uma janela aberta durante
// um reinicio do backend ficaria com o token velho e todo POST passaria a falhar
// em silencio; entao o token e relido da propria pagina e a chamada e repetida
// uma vez.
async function refreshAzorToken(){
  try{
    const html=await (await apiFetch('/',{},8000)).text();
    const found=html.match(/name="azor-token"\s+content="([^"]+)"/);
    if(found&&found[1]&&found[1]!==AZOR_TOKEN){AZOR_TOKEN=found[1];return true}
  }catch(e){}
  return false;
}
async function apiFetch(url,options={},timeout=API_TIMEOUT_MS){
  const ctl=new AbortController();
  const timer=setTimeout(()=>ctl.abort(),timeout);
  try{return await fetch(url,{cache:'no-store',signal:ctl.signal,...options})}
  catch(e){if(e?.name==='AbortError'){const err=new Error(`A operação demorou mais que o esperado (${Math.round(timeout/1000)}s). O resultado ainda não foi confirmado.`);err.code='TIMEOUT';throw err}throw e}
  finally{clearTimeout(timer)}
}
async function getJSON(url,timeout=requestTimeout(url)){const r=await apiFetch(url,{},timeout);if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json()}
async function postJSON(url,data,timeout=url==='/api/action'?ACTION_TIMEOUT_MS:API_TIMEOUT_MS){
  const send=()=>apiFetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-Azor-Token':AZOR_TOKEN},body:JSON.stringify(data)},timeout);
  let r=await send();
  if(r.status===403&&await refreshAzorToken())r=await send();
  const j=await r.json().catch(()=>({}));
  if(!r.ok)throw new Error(j.error||j.detail||`HTTP ${r.status}`);
  return j;
}
function toast(msg,ok=true){const t=$('#toast');t.textContent=msg;t.className=`toast show ${ok?'good':'bad'}`;clearTimeout(t._tm);t._tm=setTimeout(()=>t.className='toast',3600)}
// O dialogo devolve o foco para quem o abriu e prende o Tab enquanto esta
// aberto. Sem isso o teclado continuava navegando a pagina atras do modal.
let modalReturnFocus=null;
function openModal(title,html){
  $('#modalBody').innerHTML=`<h2 id="modalTitle">${title}</h2>${html}`;
  modalReturnFocus=document.activeElement;
  $('#modal').classList.remove('hidden');
  const close=$('#modalClose');
  // setTimeout e nao requestAnimationFrame: uma janela minimizada nao compoe
  // quadros, e o foco tem de acontecer mesmo assim.
  if(close)setTimeout(()=>close.focus(),0);
}
function closeModal(){
  $('#modal').classList.add('hidden');
  const back=modalReturnFocus;modalReturnFocus=null;
  if(back&&document.contains(back)){try{back.focus({preventScroll:true})}catch(e){}}
}
function trapModalTab(e){
  const modal=$('#modal');
  if(e.key!=='Tab'||!modal||modal.classList.contains('hidden'))return;
  const focusable=$$('a[href],button:not([disabled]),input:not([disabled]),select,textarea,[tabindex]:not([tabindex="-1"])',modal);
  if(!focusable.length)return;
  const first=focusable[0],last=focusable[focusable.length-1];
  if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}
  else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}
}
document.addEventListener('keydown',trapModalTab);
window.closeModal=closeModal;
// Bound here instead of an inline onclick so the page can run under a Content
// Security Policy without 'unsafe-inline' for scripts.
document.addEventListener('DOMContentLoaded',()=>{
  const close=$('#modalClose');if(close)close.onclick=closeModal;
  const back=$('#modal');if(back)back.addEventListener('click',e=>{if(e.target===back)closeModal()});
},{once:true});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('#modal')?.classList.contains('hidden'))closeModal()});
// Os atalhos da Home sao <article data-go>: Enter e Espaco abrem como um link.
document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target instanceof Element&&e.target.matches('article[data-go]')){e.preventDefault();e.target.click()}});

function markCurrent2DBuild(){
  const chip=$('#uiBuildChip');
  if(chip){chip.textContent='AZOR';chip.classList.add('build-current-chip')}
  document.title='AZOR Optimization';
}

function nav(){
  const n=$('#nav');n.innerHTML='';
  for(const row of NAV){
    if(row.length===1){const d=document.createElement('div');d.className='nav-section';d.textContent=row[0];n.appendChild(d);continue}
    const [key,icon,label]=row;const b=document.createElement('button');b.className='nav-btn';b.dataset.page=key;b.setAttribute('aria-label',label);b.title=label;b.innerHTML=`<span class="nav-icon">${navIcon(key)}</span><span class="nav-text">${label}</span>`;
    b.onclick=()=>go(key);n.appendChild(b);
  }
}
function go(page){if(page==='islc'||page==='measure')page='latency';S.page=page;try{render();const v=$('#view');if(v)v.scrollTop=0;}catch(e){console.error('Navigation failure',page,e);toast('Falha ao abrir '+page+': '+(e.message||e),false);}}
function setActiveNav(){
  // Chegando em 'stutter', quem acende e 'Maquina' - senao o cliente fica numa
  // tela sem saber de onde ela veio.
  const hub = hubOf(S.page);
  $$('.nav-btn').forEach(b=>b.classList.toggle('active', b.dataset.page===S.page || b.dataset.page===hub));
}
function head(title,sub,actions=''){return `<div class="page-head"><div class="page-title"><h1>${title}</h1><p>${sub}</p></div><div class="head-actions">${actions}</div></div>`}
function guide(title,text,step=1,total=4){if(S.settings.show_tips===false)return '';return `<div class="guide card"><div class="guide-icon">?</div><div><h4>${title}</h4><p>${text}</p></div><div class="guide-steps">${Array.from({length:total},(_,i)=>`<i class="step-dot ${i<step?'on':''}"></i>`).join('')}</div></div>`}
function cardModule(icon,title,desc,page){return `<article class="card module-card" data-go="${page}" tabindex="0" role="link" aria-label="${esc(title)}"><span class="arrow">${uiIcon('arrow')}</span><div class="module-icon">${UI_ICONS[icon]?uiIcon(icon):icon}</div><h3>${title}</h3><p>${desc}</p></article>`}
// display_name vem da identificação pelo VID do USB (servidor). O `name` é o do
// driver: um controle de terceiro em modo XInput chega como "Xbox 360".
function deviceName(key){const a=S.summary?.devices?.[key]||[];return a[0]?.display_name||a[0]?.name||'Nenhum dispositivo detectado'}
function deviceStatus(key){const a=S.summary?.devices?.[key]||[];return a.length? a[0]?.status||'Detectado':'Não detectado'}
function deviceCount(key){return (S.summary?.devices?.[key]||[]).length}
function detectionSource(){const m=S.summary?.device_detection;return (m?.methods||[]).length?(m.methods||[]).join(' + '):'Windows'}

function genericDeviceCard(key,title,model,accent,page){
  const found=deviceCount(key)>0;const name=deviceName(key);
  return `<article class="card device-card input-device-card" style="--accent:${accent};--accent-rgb:${hexRgb(accent)}">
    <div class="device-head"><div class="device-head-left"><div class="device-badge">${key==='keyboard'?'⌨':key==='mouse'?'◉':'🎮'}</div><div><h3>${title}</h3><p title="${esc(name)}">${esc(name)}</p></div></div><span class="pill ${found?'':'off'}">${found?'DETECTADO':'VISUAL GENÉRICO'}</span></div>
    ${input2DStage(key,title,accent)}
    <div class="device-simple-status"><span><i class="${found?'online':'waiting'}"></i>${found?`${deviceCount(key)} encontrado(s)`:'Conecte para detectar'}</span><b>${found?'Pronto para configurar':'Você ainda pode preparar um perfil'}</b></div>
    <div class="device-actions"><button class="btn primary" data-go="${page}">CONFIGURAR ${title.toUpperCase()}</button></div>
  </article>`
}

function input2DStage(kind,title,accent='#ff2fc8'){
  const art=kind==='controller'?controllerSvg():kind==='mouse'?mouseSvg():keyboardSvg();
  const liveHint=kind==='controller'?'Pressione os botões ou mova os analógicos':kind==='mouse'?'Clique, role ou use os botões laterais':'Pressione as teclas com esta janela em foco';
  return `<div class="device-stage premium2d input2d-stage ${kind}-2d" style="--accent:${accent};--accent-rgb:${hexRgb(accent)}">
    <div class="input2d-top"><span class="two-badge">2D AO VIVO</span><span class="input-live-dot"></span><strong class="input-live-text" data-live-kind="${kind}">${liveHint}</strong></div>
    <div class="input2d-art">${art}</div>
    <div class="input2d-foot"><span>Visual interativo</span><small>Responde aos inputs que o navegador consegue receber. Não altera o hardware só por animar.</small></div>
  </div>`;
}

function pcEvolution(){
  const sm=S.summary||{},timer=sm.timer||{},islc=sm.islc||{};
  const active=String(sm.power_scheme||'').toLowerCase();const schemes=sm.power_schemes||[];const plan=schemes.find(x=>String(x.guid||'').toLowerCase()===active)||{};
  const powerName=String(plan.name||'').toLowerCase();const powerOk=/azor fps boost|ultimate|high performance|alto desempenho|desempenho m[aá]ximo/.test(powerName);
  const latencyChecks=[!!timer.active];if(islc.found)latencyChecks.push(!!islc.running);
  const pct=a=>a.length?Math.round(a.filter(Boolean).length/a.length*100):0;
  return [
    {name:'Windows para jogos',score:pct([!!sm.game_mode_verified,!!sm.game_dvr_off_verified])},
    {name:'Latência preparada',score:pct(latencyChecks)},
    {name:'Plano de energia',score:powerOk?100:0},
    {name:'Proteção / Restore',score:sm.restore_available?100:0},
  ];
}
// Contagem, nao porcentagem. "3 de 4" e um fato conferivel; "75% evoluido" com
// barra de progresso se le como medidor de desempenho, e nenhuma nota de rodape
// desfaz essa leitura. O disclaimer virou o proprio formato.
function evolutionPanel(){const rows=pcEvolution();const on=rows.filter(x=>x.score>=100).length;return `<article class="card pad evolution-card"><div class="device-head"><div><span class="eyebrow">CONFIGURAÇÃO</span><h3 class="section-title">${on} de ${rows.length} áreas verificadas</h3></div><span class="pill ${on===rows.length?'goodpill':''}">${on}/${rows.length}</span></div><p class="section-sub">Estado das configurações que o AZOR consegue reler e confirmar. Não mede FPS nem desempenho.</p><div class="evolution-list">${rows.map(x=>`<div class="evolution-row"><span>${x.name}</span><b class="${x.score>=100?'good':'muted'}">${x.score>=100?'verificada':'pendente'}</b></div>`).join('')}</div></article>`}

function verifiedReadiness(){
  const sm=S.summary||{},timer=sm.timer||{},islc=sm.islc||{},power=sm.azor_power||{};
  const checks=[
    {label:'Game Mode',ok:!!sm.game_mode_verified},
    {label:'Captura em background',ok:!!sm.game_dvr_off_verified},
    {label:'AZOR FPS BOOST',ok:!!power.active},
    {label:'Restore',ok:!!sm.restore_available},
    {label:'Timer',ok:!!timer.active},
  ];
  if(islc.found)checks.push({label:'ISLC',ok:!!islc.running});
  const done=checks.filter(x=>x.ok).length,score=checks.length?Math.round(done/checks.length*100):0;
  return {checks,done,total:checks.length,score};
}
function readinessStrip(){
  const r=verifiedReadiness();
  const tone=r.score>=85?'good':r.score>=55?'warn':'muted';
  const label=r.score>=85?'PRONTO PARA JOGAR':r.score>=55?'QUASE PRONTO':'CONFIGURAÇÃO PENDENTE';
  return `<section class="readiness-strip card"><div class="readiness-score"><span>STATUS VERIFICADO</span><strong class="${tone}">${r.score}%</strong><small>${label}</small></div><div class="readiness-checks">${r.checks.map(x=>`<span class="${x.ok?'ok':'pending'}"><i>${x.ok?'✓':'•'}</i>${esc(x.label)}</span>`).join('')}</div><button class="btn ${r.score>=85?'ghost':'primary'}" data-go="quick">${r.score>=85?'REVISAR':'OTIMIZAR AGORA'}</button></section>`;
}
function quickResultSummary(){
 const r=S.lastQuickResult;if(!r)return '';
 const rows=Array.isArray(r.results)?r.results:[];
 const setup=x=>['Hardware profile','Backup / Restore'].includes(x.name);
 const confirmed=rows.filter(x=>resultOK(x)&&!setup(x));
 const unchanged=confirmed.filter(x=>x.already_applied).length;
 const changed=confirmed.length-unchanged;
 const preserved=rows.filter(resultPreserved).length;
 const failures=rows.filter(resultFailed);
 const unknown=rows.filter(x=>!resultOK(x)&&!resultFailed(x)&&!resultPreserved(x));
 const failed=r.ok===false||failures.length>0;
 const uncertain=r.ok!==true||unknown.length>0||!rows.length;
 const title=failed?'Não foi possível concluir tudo':uncertain?'Resultado ainda não confirmado':changed?'Alterações confirmadas':unchanged?'Preferências já estavam corretas':'Nenhuma alteração necessária neste perfil';
 return `<article class="card pad quick-result-card" role="status"><span class="eyebrow">ÚLTIMA APLICAÇÃO</span><h3>${title}</h3>
 <p class="section-sub">${esc(r.detail||'Confira os resultados abaixo. Não há medição de ganho de FPS nesta operação.')}</p>
 <div class="result-kpis"><span><b>${changed}</b> alterações confirmadas</span><span><b>${unchanged}</b> já corretas</span><span><b>${preserved}</b> preservadas</span><span><b>${failures.length}</b> falhas nos itens</span></div>
 ${unchanged?'<p class="section-sub">Preferências já corretas foram confirmadas sem gravar novamente.</p>':''}
 ${failed||uncertain?'<p>Confira o histórico antes de tentar novamente. Uma resposta ausente não prova que nada foi alterado.</p>':''}
 <details ${failed||uncertain?'open':''}><summary>Ver o resultado de cada item</summary><div class="action-list compact">${rows.map(x=>`<div class="action-row"><div><b>${esc(x.name||x.id||'Etapa')}</b><p>${esc(x.detail||'Sem detalhe adicional.')}</p></div><span class="pill">${resultFailed(x)?'Falhou':resultPreserved(x)?'Preservado':resultOK(x)?(x.already_applied?'Já correto':'Confirmado'):'Não confirmado'}</span></div>`).join('')||'<p>Nenhum resultado detalhado recebido.</p>'}</div></details>
 <div class="quick-buttons"><button class="btn ghost" data-go="restore">HISTÓRICO E RESTAURAÇÃO</button><button class="btn ghost" data-go="gameDiag">MEDIR NO JOGO</button></div></article>`;
}
function renderHome(){
  const m=S.monitor||{};const sm=S.summary||{};const auto=S.autostart;
  const cpu=m.cpu?.usage;const ram=m.ram?.percent;const gpu=m.gpu?.available?m.gpu?.usage:null;
  const mode=PERFORMANCE_MODES[S.quickProfile];
  // A barra sob cada leitura usa o mesmo valor do numero, na escala 0-100.
  const gauge=(label,value)=>{const n=Number(value);const pct=value!=null&&Number.isFinite(n)?clamp(n,0,100):0;return `<div class="score"><small>${label}</small><strong>${fmt(value,'%')}</strong><i class="score-bar" aria-hidden="true"><span style="width:${pct}%"></span></i></div>`};
  const row=(label,value,tone,title='')=>`<div class="status-item"><span>${label}</span><span class="${tone}"${title?` title="${esc(title)}"`:''}>${value}</span></div>`;
  const last=auto&&auto.last_run;
  return `${head('Azor Optimization','Um toque no BOOST deixa o PC no modo escolhido. Antes de mexer, o AZOR guarda como tudo estava.')}
  ${adminGapBanner()}
  ${modeCleanupBanner()}
  <section class="hero">
    <div class="card hero-main glow-purple boost-card">${boostStage()}</div>
    <div class="card hero-side glow-blue">
      <div class="hero-side-head"><span class="eyebrow">PC agora</span><small>Leituras do Windows</small></div>
      <div class="score-row">${gauge('CPU',cpu)}${gauge('RAM',ram)}${gauge('GPU',gpu)}<div class="score score-text"><small>BACKUP</small><strong>${sm.restore_available===true?'Disponível':sm.restore_available===false?'Ao aplicar':'Aguardando'}</strong></div></div>
      <div class="status-list">
        ${row('Modo escolhido',mode?mode.label:esc(profileLabel(S.quickProfile)),'good',mode?mode.hint:'')}
        ${row('Ao entrar no Windows',!auto?'Consultando…':auto.stale?'Versão anterior':auto.enabled?'Reaplica sozinho':'Só quando você clicar',auto&&auto.stale?'warn':auto&&auto.enabled?'good':'muted',auto?auto.detail:'')}
        ${row('Última vez sozinho',last&&last.time?esc(new Date(last.time*1000).toLocaleString('pt-BR',{dateStyle:'short',timeStyle:'short'})):'Ainda não rodou',last&&last.outcome==='applied'?'good':last&&(last.outcome==='partial'||last.outcome==='failed')?'warn':'muted',last?last.detail:'')}
        ${row('Perfil de hardware',esc(sm.hardware_profile?.label||'Analisando'),'muted')}
      </div>
    </div>
  </section>
  ${startupRestoreBanner()}
  ${rebootConfirmBanner()}
  <section class="home-shortcuts">
    <button class="home-shortcut" type="button" data-go="restore"><span class="module-icon">${uiIcon('undo')}</span><span><b>Desfazer alterações</b><small>Volta cada ajuste ao estado anterior ao AZOR.</small></span></button>
    <button class="home-shortcut" type="button" data-go="monitor"><span class="module-icon">${uiIcon('activity')}</span><span><b>Ver desempenho</b><small>CPU, GPU, RAM, disco e temperaturas em tempo real.</small></span></button>
    <button class="home-shortcut" type="button" data-go="quick"><span class="module-icon">${uiIcon('sliders')}</span><span><b>Opções avançadas</b><small>Ajuste por ajuste, energia, jogos e diagnóstico.</small></span></button>
  </section>`
}

function recommend(icon,t,d){return `<div class="card pad"><div class="module-icon">${icon}</div><h3 class="section-title">${t}</h3><p class="section-sub">${d}</p></div>`}

function ensureInputProfiles(){
  const defaults={
    controller:Array.from({length:4},(_,i)=>({name:`Perfil ${i+1}`,poll_rate:1000,latency_mode:'competitive',vibration:false,left_deadzone:5,right_deadzone:5,left_antideadzone:0,right_antideadzone:0,lt_deadzone:2,rt_deadzone:2,trigger_mode:'adaptive',stick_curve:'linear',button_response:'fast',overclock_hz:1000,oc_mode:'safe'})),
    mouse:Array.from({length:4},(_,i)=>({name:`Perfil ${i+1}`,poll_rate:1000,latency_mode:'competitive',dpi_x:1600,dpi_y:1600,debounce:1,smoothing:0,angle_snapping:false,lod:'low',motion_sync:false,enhanced_pointer_precision:false,usb_suspend_off:true,overclock_hz:1000})),
    keyboard:Array.from({length:4},(_,i)=>({name:`Perfil ${i+1}`,poll_rate:1000,scan_rate:1000,latency_mode:'competitive',debounce:1,repeat_rate:31,repeat_delay:1,nkro:true,rapid_trigger:false,actuation:1.2,reset_point:1.0,socd:'off',overclock_hz:1000}))
  };
  const src=S.summary?.settings?.input_lab_profiles||S.settings?.input_lab_profiles||{};
  const out={};
  for(const kind of Object.keys(defaults)) out[kind]=defaults[kind].map((row,i)=>({...row,...((src[kind]||[])[i]||{})}));
  S.settings.input_lab_profiles=out;return out;
}
function currentProfile(kind){const ps=ensureInputProfiles();const i=Math.max(0,Math.min(3,S.inputSelected?.[kind]||0));return ps[kind][i]}

function profileVisual(kind){
  const p=currentProfile(kind);
  if(kind==='controller'){
    return {
      ldz: clamp((Number(p.left_deadzone)||0)/20,0,1), rdz: clamp((Number(p.right_deadzone)||0)/20,0,1),
      lt: clamp((Number(p.lt_deadzone)||0)/20,0,1), rt: clamp((Number(p.rt_deadzone)||0)/20,0,1),
      adl: clamp((Number(p.left_antideadzone)||0)/20,0,1), adr: clamp((Number(p.right_antideadzone)||0)/20,0,1),
      accent: p.latency_mode==='competitive'?'#b160ff':(p.latency_mode==='balanced'?'#3fa7ff':'#4ce98a'),
      poll: Number(p.overclock_hz||p.poll_rate||1000)
    }
  }
  if(kind==='mouse'){
    return {
      dpi: clamp((Number(p.dpi_x)||1600)/6400,0,1), debounce: clamp((Number(p.debounce)||0)/12,0,1),
      accent: p.latency_mode==='competitive'?'#59a6ff':(p.latency_mode==='balanced'?'#7a8cff':'#65d0ae'),
      poll: Number(p.overclock_hz||p.poll_rate||1000)
    }
  }
  return {
    actuation: clamp((Number(p.actuation)||1.2)/4,0,1), debounce: clamp((Number(p.debounce)||0)/12,0,1),
    accent: p.latency_mode==='competitive'?'#b160ff':(p.latency_mode==='balanced'?'#6ca9ff':'#76d08f'),
    poll: Number(p.overclock_hz||p.poll_rate||1000)
  }
}

function deviceRow(kind){return (S.summary?.devices?.[kind]||[])[0]||{}}
function parseVidPid(id=''){const m=String(id||'').match(/VID_([0-9A-F]{4}).*PID_([0-9A-F]{4})/i);return m?{vid:m[1].toUpperCase(),pid:m[2].toUpperCase()}:{vid:'—',pid:'—'}}
function inferConnection(dev){const t=((dev.id||'')+' '+(dev.name||'')).toLowerCase();if(t.includes('bth')||t.includes('bluetooth'))return 'Bluetooth';if(t.includes('wireless')||t.includes('2.4')||t.includes('dongle'))return 'Dongle / Wireless';if(t.includes('usb')||t.includes('vid_'))return 'USB';return 'Windows HID'}
function supportedHz(kind){const low=String(deviceName(kind)||'').toLowerCase();const base=[125,250,500,1000];if(kind!=='controller'){if(/8k|8000/.test(low))return [...base,2000,4000,8000];if(/4k|4000/.test(low))return [...base,2000,4000];if(/2k|2000/.test(low))return [...base,2000]}return base}
function inputProfileTabs(kind){const fallback=['Principal','Alternativo','Estável','Personalizado'];return `<div class="profile-row saved-profile-row">${ensureInputProfiles()[kind].map((p,i)=>{const raw=String(p.name||'');const label=/^Perfil\s+\d+$/i.test(raw)?fallback[i]:raw||fallback[i];const active=(S.inputSelected?.[kind]||0)===i;return `<button type="button" class="profile-pill ${active?'active':''}" data-input-profile="${kind}:${i}" aria-pressed="${active}">${esc(label)}</button>`}).join('')}</div>`}
function hzButtons(kind,val){const supported=supportedHz(kind);const all=[125,250,500,1000,2000,4000,8000];return `<div class="hz-grid">${all.map(h=>{const active=Number(val)===h;return `<button type="button" class="hz-pill ${active?'active':''} ${supported.includes(h)?'':'experimental'}" data-input-hz="${kind}:${h}" aria-pressed="${active}" title="${supported.includes(h)?'Disponível para este perfil':'Experimental: só use se o hardware e o driver suportarem'}">${h}Hz</button>`}).join('')}</div>`}
function sliderRow(kind,key,label,val,min,max,step=1,suffix=''){return `<label class="field compact"><div class="field-head"><span>${label}</span><span>${val}${suffix}</span></div><input class="range" type="range" min="${min}" max="${max}" step="${step}" value="${val}" data-input-slider="${kind}:${key}" data-input-suffix="${esc(suffix)}"></label>`}
function inputOptionLabel(value){return ({competitive:'Competitivo',balanced:'Equilibrado',stable:'Estável',low:'Baixa',medium:'Média',high:'Alta',off:'Desligado',safe:'Seguro',fast:'Rápida',ultra:'Muito rápida',linear:'Linear',smooth:'Suave',aggressive:'Agressiva',adaptive:'Adaptável',fixed:'Fixo',hair:'Curso curto',instant:'Instantâneo',moderate:'Moderado','last input':'Última tecla',neutral:'Neutro'})[String(value)]||String(value)}
function selectRow(kind,key,label,val,opts){return `<label class="field compact"><div class="field-head"><span>${label}</span><span>${esc(inputOptionLabel(val))}</span></div><select class="select" data-input-select="${kind}:${key}">${opts.map(o=>`<option value="${esc(o)}" ${String(val)===String(o)?'selected':''}>${esc(inputOptionLabel(o))}</option>`).join('')}</select></label>`}
function toggleRow(kind,key,label,on){return `<div class="switch-row"><span>${label}</span><button type="button" class="toggle ${on?'on':''}" data-input-toggle="${kind}:${key}" role="switch" aria-checked="${!!on}" aria-label="${esc(label)}"></button></div>`}
function diagTable(kind){const dev=deviceRow(kind);const ids=parseVidPid(dev.id);const count=deviceCount(kind);return `<div class="diag-grid">${diagStat('Dispositivo',dev.name||'Não detectado')}${diagStat('Status',dev.status||'—')}${diagStat('Conexão',inferConnection(dev))}${diagStat('VID / PID',`${ids.vid} / ${ids.pid}`)}${diagStat('Fonte',dev.source||detectionSource())}${diagStat('Qtd',String(count))}${diagStat('Polling efetivo','Não medido')}${diagStat('Jitter','Não medido')}</div>`}
function diagStat(name,val){return `<div class="diag-stat"><span>${name}</span><b>${esc(val)}</b></div>`}
function controlHero(kind,title,icon,desc,page){const found=deviceCount(kind)>0;const dev=deviceName(kind);return `<article class="card input-hero-card"><div class="input-hero-top"><div class="module-icon">${icon}</div><span class="pill ${found?'':'off'}">${found?'DETECTADO':'AGUARDANDO'}</span></div><h3>${title}</h3><p>${desc}</p><div class="input-hero-device">${esc(dev)}</div><div class="input-hero-actions"><button class="btn primary" data-go="${page}">ABRIR PAINEL</button><button class="btn ghost" data-input-action="refresh-devices:${kind}">ATUALIZAR</button></div></article>`}

const INPUT_PRESETS={
  controller:{
    competitive:{title:'Competitivo',tag:'MAIS DESEMPENHO',desc:'Perfil com zonas mortas baixas e vibração desligada; a latência é o que entra no Windows.',values:{poll_rate:1000,overclock_hz:1000,latency_mode:'competitive',vibration:false,left_deadzone:3,right_deadzone:3,left_antideadzone:0,right_antideadzone:0,lt_deadzone:2,rt_deadzone:2,trigger_mode:'hair',stick_curve:'competitive',button_response:'ultra',oc_mode:'safe'}},
    balanced:{title:'Equilibrado',tag:'RECOMENDADO GERAL',desc:'Perfil equilibrado entre conforto e resposta, com latência no alvo médio.',values:{poll_rate:1000,overclock_hz:1000,latency_mode:'balanced',vibration:true,left_deadzone:5,right_deadzone:5,left_antideadzone:0,right_antideadzone:0,lt_deadzone:4,rt_deadzone:4,trigger_mode:'adaptive',stick_curve:'linear',button_response:'fast',oc_mode:'safe'}},
    stable:{title:'Estável',tag:'SEM FIO / ANTIGO',desc:'Perfil tolerante a drift e conexão variável, com latência conservadora.',values:{poll_rate:500,overclock_hz:500,latency_mode:'stable',vibration:true,left_deadzone:8,right_deadzone:8,left_antideadzone:0,right_antideadzone:0,lt_deadzone:6,rt_deadzone:6,trigger_mode:'fixed',stick_curve:'smooth',button_response:'safe',oc_mode:'off'}}
  },
  mouse:{
    competitive:{title:'Competitivo',tag:'FPS',desc:'Aceleração do ponteiro desligada, USB sem suspender e alvo de latência agressivo.',values:{poll_rate:1000,overclock_hz:1000,latency_mode:'competitive',dpi_x:1600,dpi_y:1600,debounce:1,smoothing:0,angle_snapping:false,lod:'low',motion_sync:false,enhanced_pointer_precision:false,usb_suspend_off:true}},
    balanced:{title:'Equilibrado',tag:'USO GERAL',desc:'Aceleração desligada, energia USB no padrão e latência equilibrada.',values:{poll_rate:1000,overclock_hz:1000,latency_mode:'balanced',dpi_x:1200,dpi_y:1200,debounce:2,smoothing:0,angle_snapping:false,lod:'low',motion_sync:true,enhanced_pointer_precision:false,usb_suspend_off:false}},
    stable:{title:'Precisão',tag:'CONTROLE FINO',desc:'Aceleração desligada e alvo de latência conservador, para conexão instável.',values:{poll_rate:500,overclock_hz:500,latency_mode:'stable',dpi_x:800,dpi_y:800,debounce:4,smoothing:0,angle_snapping:false,lod:'medium',motion_sync:false,enhanced_pointer_precision:false,usb_suspend_off:false}}
  },
  keyboard:{
    competitive:{title:'Competitivo',tag:'RESPOSTA RÁPIDA',desc:'Repetição de tecla no máximo, sem atraso inicial, latência agressiva.',values:{poll_rate:1000,overclock_hz:1000,scan_rate:1000,latency_mode:'competitive',debounce:1,repeat_rate:31,repeat_delay:0,nkro:true,rapid_trigger:true,actuation:1.0,reset_point:0.8,socd:'off'}},
    balanced:{title:'Equilibrado',tag:'RECOMENDADO GERAL',desc:'Rápido para jogos sem deixar a digitação sensível demais.',values:{poll_rate:1000,overclock_hz:1000,scan_rate:1000,latency_mode:'balanced',debounce:2,repeat_rate:25,repeat_delay:1,nkro:true,rapid_trigger:false,actuation:1.6,reset_point:1.4,socd:'off'}},
    stable:{title:'Estável',tag:'COMPATIBILIDADE',desc:'Repetição conservadora e latência estável, para qualquer teclado.',values:{poll_rate:500,overclock_hz:500,scan_rate:500,latency_mode:'stable',debounce:4,repeat_rate:20,repeat_delay:1,nkro:true,rapid_trigger:false,actuation:2.0,reset_point:1.8,socd:'off'}}
  }
};
function inputPresetCards(kind){const active=S.inputPreset?.[kind];return `<div class="simple-preset-grid">${Object.entries(INPUT_PRESETS[kind]).map(([id,p],i)=>{const selected=active===id;return `<button type="button" class="simple-preset ${selected?'active':''} ${id==='balanced'?'recommended':''}" data-input-preset="${kind}:${id}" aria-pressed="${selected}" aria-label="Perfil ${p.title}: ${p.desc}">${id==='balanced'?'<span class="preset-recommended">RECOMENDADO</span>':''}<span class="preset-check">${selected?'✓':i+1}</span><span class="preset-copy"><small>${p.tag}</small><b>${p.title}</b><em>${p.desc}</em></span></button>`}).join('')}</div>
  <p class="preset-truth">O AZOR aplica o que o Windows expõe: aceleração do ponteiro, repetição de tecla,
  energia USB e alvo de latência. DPI, polling e zonas mortas ficam salvos como perfil — quem manda neles
  é o firmware do aparelho, e o relatório de aplicação separa um do outro.</p>`}
function inputDeviceHeader(kind,title){const count=deviceCount(kind),found=count>0;const countText=count===1?'1 dispositivo detectado':`${count} dispositivos detectados`;return `<div class="simple-device-head"><div><span class="eyebrow">${title}</span><h2>${esc(deviceName(kind))}</h2><p>${found?`${countText} • ${esc(deviceStatus(kind))}`:'Nenhum dispositivo detectado; o perfil pode ser preparado mesmo assim.'}</p></div><span class="pill ${found?'':'off'}">${found?'PRONTO':'NÃO DETECTADO'}</span></div>`}
function advancedInput(title,summary,content){const open=S.settings.mode==='Expert'?'open':'';return `<details class="advanced-disclosure" ${open}><summary><span><b>Ajustes avançados</b><small>${summary}</small></span><strong>${title} <i>⌄</i></strong></summary><div class="advanced-content">${content}</div></details>`}
// Estes numeros sao o ALVO escolhido no perfil, nunca leitura do aparelho - e o
// rotulo precisa dizer isso, porque logo ao lado existe um card informando que o
// DPI real nao pode ser lido. Duas caixas com numeros diferentes e sem rotulo
// claro e a maneira mais rapida de o cliente achar que o mouse foi alterado.
function inputTruth(kind){const p=currentProfile(kind);const main=kind==='controller'?`${p.left_deadzone}% de zona morta • ${p.poll_rate} Hz`:kind==='mouse'?`${p.dpi_x} DPI • ${p.poll_rate} Hz • ${p.debounce} ms`:`${p.poll_rate} Hz • atuação ${p.actuation} mm`;return `<div class="input-truth"><span>Alvo do perfil — não é leitura do aparelho</span><b>${esc(main)}</b><small>O AZOR aplica o que o Windows permite e informa separadamente o que depende do firmware do dispositivo.</small></div>`}


// ===========================================================================
// Desenhos 2D dos periféricos
//
// A versão anterior era plástico branco chapado sobre um painel escuro: os três
// aparelhos pareciam recortes de papel colados na tela, e a peça mais importante
// — o estado ao vivo do que está sendo pressionado — sumia no branco.
//
// Esta versão desenha hardware escuro, do mesmo mundo do resto do app, com três
// camadas em cada peça: corpo (gradiente com luz vindo de cima), realce de borda
// (a linha clara de 1px que dá espessura) e sombra interna. O acento do perfil
// vira LUZ do periférico — a fita de RGB do mouse, o brilho do WASD, os gatilhos
// do controle — em vez de ser só a cor de um contorno.
//
// Contrato preservado: todo elemento clicável mantém o mesmo `data-pressable`,
// porque é por ele que o input ao vivo acende as teclas.
// ===========================================================================

// ===========================================================================
// PERIFÉRICOS 2D — identidade AZOR: grafite + rosa neon
//
// Três peças desenhadas em SVG, não imagens: cada botão é um nó próprio com
// `data-pressable`, e é por ele que o input ao vivo acende a região certa.
//
// Regras de desenho que valem para os três:
//   corpo      gradiente escuro com luz vindo de cima (#2a3345 → #080d16)
//   borda      traço rosa de 2px com brilho — é o que dá a leitura "premium"
//   legenda    #c9d4e6 sobre keycap escuro; acende para #fff quando pressionado
//   acento     só rosa. Sem RGB arco-íris, sem cor de marca em botão de ação.
//   glow       suave e sempre atrás do conteúdo, nunca por cima da legenda
// ===========================================================================

function azorDefs(id, opts){
  const glow = (opts && opts.glow) || 9;
  return `
  <linearGradient id="${id}Body" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#23232b"/><stop offset=".42" stop-color="#18181e"/>
    <stop offset="1" stop-color="#101014"/></linearGradient>
  <linearGradient id="${id}Cap" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#2c2c35"/><stop offset="1" stop-color="#212128"/></linearGradient>
  <linearGradient id="${id}CapLit" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#3b2035"/><stop offset="1" stop-color="#2a1627"/></linearGradient>
  <linearGradient id="${id}Neon" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="var(--accent)" stop-opacity=".2"/>
    <stop offset=".5" stop-color="var(--accent)" stop-opacity="1"/>
    <stop offset="1" stop-color="var(--accent)" stop-opacity=".2"/></linearGradient>
  <radialGradient id="${id}Halo" cx="50%" cy="50%">
    <stop offset="0" stop-color="var(--accent)" stop-opacity=".55"/>
    <stop offset="1" stop-color="var(--accent)" stop-opacity="0"/></radialGradient>
  <filter id="${id}Glow" x="-45%" y="-45%" width="190%" height="190%">
    <feDropShadow dx="0" dy="0" stdDeviation="${glow}" flood-color="var(--accent)" flood-opacity=".7"/></filter>
  <filter id="${id}Depth" x="-25%" y="-30%" width="150%" height="165%">
    <feDropShadow dx="0" dy="12" stdDeviation="16" flood-color="#000" flood-opacity=".62"/></filter>`;
}

// --------------------------------------------------------------------------
// CONTROLE — dois formatos, só estética
//
// O seletor Xbox/PS5 muda APENAS o desenho. Ele não converte um controle no
// outro, não mexe em driver e não muda como o Windows enxerga o dispositivo —
// e a tela diz isso ao lado do seletor.
//
// O botão central é um guia neutro iluminado, e não a logo do fabricante: o
// AZOR não reproduz marca registrada de terceiro no próprio produto.
// --------------------------------------------------------------------------
// Layout do desenho. 'auto' segue o fabricante detectado pelo VID (controles da
// Sony têm os dois analógicos lado a lado; o resto do mercado, assimétrico).
// 'xbox' e 'ps5' continuam sendo os nomes internos dos dois desenhos.
function padVariant(){
  const skin = S.padSkin || 'auto';
  if(skin === 'ps5') return 'ps5';
  if(skin === 'xbox') return 'xbox';
  return padIdentity().layout === 'symmetric' ? 'ps5' : 'xbox';
}
function padSlot(){
  const slots = (S.padLive && S.padLive.slots) || [];
  const pick = S.padDeviceIndex;
  if(pick != null && pick !== 'auto'){ const n = Number(pick); return slots.find(s => s.index === n) || null; }
  return slots[0] || null;
}
function padIdentity(){
  const caps = S.inputCaps?.kinds?.controller || {};
  const row = deviceRow('controller');
  const slot = padSlot();
  const ids = parseVidPid(row.id);
  return {
    display: caps.display_name || row.display_name || row.name || '',
    vendor: slot?.vendor || caps.vendor || row.vendor || null,
    note: caps.note || row.note || '',
    xinput: !!(caps.xinput || row.xinput),
    layout: caps.layout || row.layout || 'asymmetric',
    vid: slot?.vid || caps.vid || row.vid || (ids.vid !== '—' ? ids.vid : null),
    pid: slot?.pid || caps.pid || row.pid || (ids.pid !== '—' ? ids.pid : null),
  };
}
// O nome que a janela recebe do navegador é o do DRIVER ("Xbox 360 Controller
// (XInput STANDARD GAMEPAD)"). Em modo XInput vale o que a detecção identificou
// pelo VID; fora dele, o nome sem o sufixo técnico.
function padLabel(gp){
  const id = String(gp?.id || '');
  if(/xinput/i.test(id)){ const who = padIdentity(); return who.display || 'Controle em modo XInput'; }
  const name = id.replace(/\s*\(.*$/, '').trim();
  const m = id.match(/Vendor:\s*([0-9a-f]{4}).*?Product:\s*([0-9a-f]{4})/i);
  return name || (m ? `Controle ${m[1].toUpperCase()}:${m[2].toUpperCase()}` : 'Controle');
}

function controllerSvg(){
  const variant = padVariant();
  const cp = currentProfile('controller');
  // Assimétrico: analógico esquerdo em cima, direito embaixo.
  // Simétrico: os dois analógicos embaixo, direcional e ação em cima.
  const sticks = variant === 'ps5'
    ? { l: [378, 330], r: [522, 330] }
    : { l: [262, 222], r: [505, 322] };
  const dpad = variant === 'ps5' ? [268, 220] : [378, 318];
  const face = variant === 'ps5' ? [632, 220] : [648, 222];
  const R_RING = 52, R_WELL = 44, R_CAP = 31, R_TOP = 23, R_FACE = 22, FACE_OFF = 41;

  // Simétrico usa formas geométricas (triângulo, círculo, X, quadrado) — símbolos
  // genéricos, não logos. Assimétrico usa as letras.
  const faceGlyph = (pos, key, label) => {
    const [cx, cy] = pos;
    const shape = variant === 'ps5' ? {
      Y: `<path d="M${cx} ${cy-10} L${cx+10} ${cy+7} L${cx-10} ${cy+7} Z"/>`,
      B: `<circle cx="${cx}" cy="${cy}" r="9.5"/>`,
      A: `<path d="M${cx-8} ${cy-8} L${cx+8} ${cy+8} M${cx+8} ${cy-8} L${cx-8} ${cy+8}"/>`,
      X: `<rect x="${cx-8.5}" y="${cy-8.5}" width="17" height="17" rx="2"/>`,
    }[key] : `<text x="${cx}" y="${cy+7}" text-anchor="middle">${label}</text>`;
    return `<g class="pressable face-btn" data-pressable="${key}">
      <circle cx="${cx}" cy="${cy}" r="${R_FACE}"/>
      <circle class="face-rim" cx="${cx}" cy="${cy}" r="${R_FACE - 5}"/>
      <g class="face-glyph">${shape}</g></g>`;
  };

  const body = variant === 'ps5'
    ? "M196 150c44-40 118-58 254-58s210 18 254 58c58 52 96 214 74 276-16 46-64 60-104 24-30-27-40-74-84-101-40-24-92-30-140-30s-100 6-140 30c-44 27-54 74-84 101-40 36-88 22-104-24-22-62 16-224 74-276Z"
    : "M165 122c50-32 127-48 285-48s235 16 285 48c64 41 119 234 98 311-14 54-59 75-104 37-34-28-42-79-90-112-42-29-101-35-189-35s-147 6-189 35c-48 33-56 84-90 112-45 38-90 17-104-37-21-77 34-270 98-311Z";

  // O chapéu do analógico anda dentro do poço (setStickVisual). Anel e chapéu têm
  // o mesmo data-pressable, então o clique L3/R3 acende os dois.
  const stick = (pos, key) => {
    const [cx, cy] = pos;
    return `<g class="stick-group">
      <circle class="pressable analog-ring" data-pressable="${key}" cx="${cx}" cy="${cy}" r="${R_RING}"/>
      <circle class="analog-well" cx="${cx}" cy="${cy}" r="${R_WELL}"/>
      <g class="pressable analog-core" data-pressable="${key}">
        <circle class="cap-skirt" cx="${cx}" cy="${cy}" r="${R_CAP}"/>
        <circle class="cap-top" cx="${cx}" cy="${cy}" r="${R_TOP}"/>
        <circle class="cap-dot" cx="${cx}" cy="${cy}" r="3.2"/>
      </g>
    </g>`;
  };

  // Gatilho: o contorno acende no toque e a barra interna enche com a pressão
  // analógica real (setTriggerVisual), recortada no formato do gatilho.
  const trig = (key, x) => `
    <g class="pressable trigger-ghost" data-pressable="${key}"><rect x="${x}" y="54" width="92" height="34" rx="15"/></g>
    <rect class="trigger-fill" data-trigger-fill="${key}" x="${x}" y="54" width="0" height="34" clip-path="url(#ctl${key}Clip)"/>
    <text class="pad-tag" x="${x + 46}" y="76" text-anchor="middle">${key.toUpperCase()}</text>`;
  const bump = (key, x) => `
    <g class="pressable trigger-ghost bumper" data-pressable="${key}"><rect x="${x}" y="100" width="112" height="24" rx="12"/></g>
    <text class="pad-tag" x="${x + 56}" y="117" text-anchor="middle">${key.toUpperCase()}</text>`;

  const [dx, dy] = dpad;
  const [fx, fy] = face;
  return `<svg class="input-svg controller-svg interactive-surface" viewBox="0 0 900 520"
    role="img" aria-label="Representação do controle, layout ${variant === 'ps5' ? 'simétrico' : 'assimétrico'}">
  <defs>${azorDefs('ctl', {glow: 10})}
    <clipPath id="ctlShellClip"><path d="${body}"/></clipPath>
    <clipPath id="ctlltClip"><rect x="202" y="54" width="92" height="34" rx="15"/></clipPath>
    <clipPath id="ctlrtClip"><rect x="606" y="54" width="92" height="34" rx="15"/></clipPath>
    <radialGradient id="ctlSheen" cx="50%" cy="0%" r="80%">
      <stop offset="0" stop-color="#fff" stop-opacity=".09"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
  </defs>

  <g class="pad-shell">
    <path class="shell-main" d="${body}" fill="url(#ctlBody)"/>
    <g clip-path="url(#ctlShellClip)"><ellipse cx="450" cy="60" rx="380" ry="200" fill="url(#ctlSheen)"/></g>
    <path class="shell-bevel" d="${body}" transform="translate(450 250) scale(.955) translate(-450 -250)"/>
  </g>

  <g class="trigger-row">${trig('lt', 202)}${trig('rt', 606)}${bump('lb', 192)}${bump('rb', 596)}</g>

  ${stick(sticks.l, 'stick-left')}
  ${stick(sticks.r, 'stick-right')}

  <g class="dpad-group">
    <rect class="dpad-base" x="${dx-50}" y="${dy-50}" width="100" height="100" rx="50"/>
    <g class="pressable" data-pressable="UP"><rect x="${dx-14}" y="${dy-44}" width="28" height="32" rx="6"/></g>
    <g class="pressable" data-pressable="DOWN"><rect x="${dx-14}" y="${dy+12}" width="28" height="32" rx="6"/></g>
    <g class="pressable" data-pressable="LEFT"><rect x="${dx-44}" y="${dy-14}" width="32" height="28" rx="6"/></g>
    <g class="pressable" data-pressable="RIGHT"><rect x="${dx+12}" y="${dy-14}" width="32" height="28" rx="6"/></g>
    <rect class="dpad-hub" x="${dx-13}" y="${dy-13}" width="26" height="26" rx="5"/>
  </g>

  <g class="face-buttons">
    <circle class="face-well" cx="${fx}" cy="${fy}" r="${FACE_OFF + R_FACE + 7}"/>
    ${faceGlyph([fx, fy - FACE_OFF], 'Y', 'Y')}
    ${faceGlyph([fx + FACE_OFF, fy], 'B', 'B')}
    ${faceGlyph([fx - FACE_OFF, fy], 'X', 'X')}
    ${faceGlyph([fx, fy + FACE_OFF], 'A', 'A')}
  </g>

  <g class="center-row">
    <g class="pressable center-btn" data-pressable="BACK"><rect x="388" y="174" width="44" height="22" rx="11"/>
      <path class="btn-glyph" d="M403 180h8v8h-8zM407 184h8v8h-8"/></g>
    <g class="pressable center-btn" data-pressable="START"><rect x="468" y="174" width="44" height="22" rx="11"/>
      <path class="btn-glyph" d="M482 180h16M482 185h16M482 190h16"/></g>
    <g class="pressable guide-btn" data-pressable="home">
      <circle cx="450" cy="138" r="25"/><circle class="guide-ring" cx="450" cy="138" r="14"/>
    </g>
    ${variant === 'ps5' ? '<rect class="touchpad" x="376" y="206" width="148" height="44" rx="12"/>' : ''}
  </g>

  <g class="profile-badges">
    <rect x="300" y="414" width="300" height="52" rx="14"/>
    <text x="450" y="436" text-anchor="middle" class="pad-badge-main">PERFIL ${esc(inputOptionLabel(cp.latency_mode || '').toUpperCase())}</text>
    <text x="450" y="455" text-anchor="middle" class="pad-badge-sub">Zona morta L ${cp.left_deadzone}% · R ${cp.right_deadzone}%</text>
  </g>
</svg>`;
}

// --------------------------------------------------------------------------
// TECLADO — TKL de verdade, com as seis fileiras e larguras proporcionais
//
// A versão anterior tinha cinco fileiras improvisadas e nenhuma tecla de função.
// Aqui as larguras seguem a unidade real do padrão (1u = 46px) e cada tecla é um
// nó com `data-pressable` no mesmo nome que o Raw Input devolve.
// --------------------------------------------------------------------------
const KB_ROWS = [
  [['ESC',1],['',0.5],['F1',1],['F2',1],['F3',1],['F4',1],['',0.5],['F5',1],['F6',1],['F7',1],['F8',1],
   ['',0.5],['F9',1],['F10',1],['F11',1],['F12',1],['',0.4],['PrtSc',1],['ScrLk',1],['Pause',1]],
  [['`',1],['1',1],['2',1],['3',1],['4',1],['5',1],['6',1],['7',1],['8',1],['9',1],['0',1],['-',1],['=',1],['⌫',2],
   ['',0.4],['Ins',1],['Home',1],['PgUp',1]],
  [['TAB',1.5],['Q',1],['W',1],['E',1],['R',1],['T',1],['Y',1],['U',1],['I',1],['O',1],['P',1],['[',1],[']',1],['\\',1.5],
   ['',0.4],['Del',1],['End',1],['PgDn',1]],
  [['CAPS',1.75],['A',1],['S',1],['D',1],['F',1],['G',1],['H',1],['J',1],['K',1],['L',1],[';',1],["'",1],['ENTER',2.25]],
  [['SHIFT',2.25],['Z',1],['X',1],['C',1],['V',1],['B',1],['N',1],['M',1],[',',1],['.',1],['/',1],['SHIFT',2.75],
   ['',1.4],['↑',1]],
  [['CTRL',1.25],['WIN',1.25],['ALT',1.25],['SPACE',6.25],['ALT',1.25],['WIN',1.25],['MENU',1.25],['CTRL',1.25],
   ['',0.4],['←',1],['↓',1],['→',1]],
];

// ABNT2 (teclado brasileiro): Enter em L ocupando duas fileiras, a tecla extra ao
// lado do Z (ISO) e a do lado do ponto (RO, "/?"). As posições são físicas; o
// monitor acende pelo scan code, então a tecla certa acende em qualquer layout.
const KB_ROWS_ABNT2 = [
  KB_ROWS[0], KB_ROWS[1],
  [['TAB',1.5],['Q',1],['W',1],['E',1],['R',1],['T',1],['Y',1],['U',1],['I',1],['O',1],['P',1],['[',1],[']',1],['ENTER',1.5,'iso'],
   ['',0.4],['Del',1],['End',1],['PgDn',1]],
  [['CAPS',1.75],['A',1],['S',1],['D',1],['F',1],['G',1],['H',1],['J',1],['K',1],['L',1],[';',1],["'",1],['\\',1],['',1.25]],
  [['SHIFT',1.25],['ISO',1],['Z',1],['X',1],['C',1],['V',1],['B',1],['N',1],['M',1],[',',1],['.',1],['/',1],['RO',1],['SHIFT',1.75],
   ['',1.4],['↑',1]],
  KB_ROWS[5],
];

// Teclas de jogo acesas por padrão: WASD, o entorno e as modificadoras usadas em
// competitivo. É o que dá a leitura de "teclado gamer" sem RGB arco-íris.
const KB_LIT = new Set(['W','A','S','D','Q','E','R','SHIFT','CTRL','SPACE','1','2','3','4','↑','↓','←','→']);

// Legenda de cada posição no layout do Windows. Com o mapa do navegador
// (navigator.keyboard) a legenda é a real do PC - ABNT2, ANSI, AZERTY; sem ele,
// o formato escolhido decide.
const KB_CODE = {'`':'Backquote','-':'Minus','=':'Equal','[':'BracketLeft',']':'BracketRight','\\':'Backslash',
  ';':'Semicolon',"'":'Quote',',':'Comma','.':'Period','/':'Slash','ISO':'IntlBackslash','RO':'IntlRo'};
const KB_ABNT2_LEGEND = {'`':"'",'[':'´',']':'[','\\':']',';':'Ç',"'":'~','/':';','ISO':'\\','RO':'/'};
function kbFormat(){ const f = S.kbFormat || 'auto'; return f === 'auto' ? (S.kbDetected || 'ansi') : f; }
function kbLegend(label){
  const code = KB_CODE[label] || (/^[A-Z]$/.test(label) ? 'Key' + label : /^[0-9]$/.test(label) ? 'Digit' + label : null);
  const ch = code && S.kbLayoutMap && (S.kbFormat || 'auto') === 'auto' ? S.kbLayoutMap.get(code) : null;
  if(ch && ch.length === 1 && ch.trim()) return ch.toUpperCase();
  if(kbFormat() === 'abnt2' && KB_ABNT2_LEGEND[label]) return KB_ABNT2_LEGEND[label];
  if(label === 'ISO') return '\\';
  if(label === 'RO') return '/';
  return label;
}
function kbLegendSignature(){ return kbFormat() + ':' + Object.keys(KB_CODE).map(kbLegend).join('') + 'ASDW'.split('').map(kbLegend).join(''); }
// Uma vez por sessão. Só redesenha se o formato ou alguma legenda mudou: num PC
// americano o mapa confirma o desenho padrão e nada pisca.
function detectKeyboardLayout(){
  if(S.kbLayoutAsked) return;
  S.kbLayoutAsked = true;
  try{
    const k = navigator.keyboard;
    if(!k || !k.getLayoutMap) return;
    k.getLayoutMap().then(map => {
      const before = kbLegendSignature();
      S.kbLayoutMap = map;
      S.kbDetected = map.get('Semicolon') === 'ç' ? 'abnt2' : 'ansi';
      if(kbLegendSignature() !== before && isInputPage() && S.periphTab === 'keyboard') render();
    }).catch(() => {});
  }catch(e){}
}

function keyboardSvg(){
  const kp = currentProfile('keyboard');
  const abnt2 = kbFormat() === 'abnt2';
  const rows = abnt2 ? KB_ROWS_ABNT2 : KB_ROWS;
  const U = 46, GAP = 5, PADX = 26, PADY = 26;
  let y = PADY + 14, maxX = 0;
  const keys = [];
  rows.forEach((row, r) => {
    let x = PADX;
    // A fileira de função tem uma folga a mais embaixo, como num TKL real.
    if(r === 1) y += 10;
    const h = r === 0 ? 30 : 40;
    row.forEach(([label, units, shape]) => {
      const w = units * U + (units - 1) * GAP;
      if(!label){ x += w + GAP; return; }
      const lit = KB_LIT.has(label);
      const legend = kbLegend(label);
      let base, top;
      if(shape === 'iso'){
        // Enter em L: largura cheia na fileira de cima, 1,25u encostado à direita na de baixo.
        const w2 = 1.25 * U + 0.25 * GAP, H = 2 * h + GAP, xb = w - w2;
        const outline = d => `M${d} ${d}H${w - d}V${H - d}H${xb + d}V${h - d}H${d}Z`;
        base = `<path class="kb-base" d="${outline(0)}"/>`;
        top = `<path class="kb-top" d="${outline(2.5)}"/>`;
      }else{
        base = `<rect class="kb-base" width="${w}" height="${h}" rx="7"/>`;
        top = `<rect class="kb-top" x="2.5" y="1.5" width="${w - 5}" height="${h - 6}" rx="6"/>`;
      }
      keys.push(`<g class="pressable kb-key${lit ? ' kb-lit' : ''}" data-pressable="${esc(label)}" transform="translate(${x},${y})">
        ${base}<g class="kb-cap">${top}${lit ? `<rect class="kb-led" x="7" y="${h - 9.5}" width="${w - 14}" height="2.4" rx="1.2"/>` : ''}
        <text x="${w / 2}" y="${h / 2 + 3}" text-anchor="middle"${legend.length > 3 ? ' class="kb-small"' : ''}>${esc(legend)}</text></g>
      </g>`);
      x += w + GAP;
      maxX = Math.max(maxX, x);
    });
    y += h + GAP;
  });
  const keysBottom = y - GAP;
  const W = maxX + PADX - GAP, H = y + PADY + 34;
  return `<svg class="input-svg keyboard-svg interactive-surface" viewBox="0 0 ${W} ${H}"
    role="img" aria-label="Representação de teclado TKL no formato ${abnt2 ? 'ABNT2' : 'ANSI'}">
  <defs>${azorDefs('kb', {glow: 7})}</defs>
  <g class="kb-shell">
    <rect class="shell-main" x="8" y="8" width="${W - 16}" height="${H - 46}" rx="18" fill="url(#kbBody)"/>
    <rect class="shell-plate" x="${PADX - 8}" y="${PADY + 6}" width="${W - (PADX - 8) * 2}" height="${keysBottom - PADY + 2}" rx="10"/>
  </g>
  <rect class="kb-strip" x="${PADX}" y="${H - 46}" width="${W - PADX * 2}" height="4" rx="2" fill="url(#kbNeon)"/>
  ${keys.join('')}
  <text x="${W / 2}" y="${H - 12}" text-anchor="middle" class="kb-foot">Perfil salvo: ${kp.nkro ? 'NKRO' : '6KRO'} · atuação ${kp.actuation} mm · desenho ${abnt2 ? 'ABNT2' : 'ANSI'}</text>
</svg>`;
}

// --------------------------------------------------------------------------
// MOUSE — simétrico, sem marca
//
// Sem logo de fabricante. A única marca é o "A" do AZOR gravado discretamente no
// apoio da palma, desenhado em traço, não imagem.
// --------------------------------------------------------------------------
function mouseSvg(){
  const mp = currentProfile('mouse');
  const shell = "M230 34c98 0 168 74 168 186v146c0 142-70 208-168 208S62 508 62 366V220C62 108 132 34 230 34Z";
  return `<svg class="input-svg mouse-svg interactive-surface" viewBox="0 0 460 640"
    role="img" aria-label="Representação de mouse, com rolagem e direção do movimento ao vivo">
  <defs>${azorDefs('ms', {glow: 8})}
    <clipPath id="msClip"><path d="${shell}"/></clipPath>
    <radialGradient id="msSheen" cx="50%" cy="8%" r="70%">
      <stop offset="0" stop-color="#fff" stop-opacity=".10"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
  </defs>

  <path class="shell-main" d="${shell}" fill="url(#msBody)"/>
  <g clip-path="url(#msClip)">
    <path class="pressable mouse-left" data-pressable="left-click" d="M62 252V214C62 110 132 38 227 34v218Z"/>
    <path class="pressable mouse-right" data-pressable="right-click" d="M233 34c95 4 165 76 165 180v38H233Z"/>
    <path class="mouse-grip" d="M62 300c30 34 34 128 24 214H40Z"/>
    <path class="mouse-grip" d="M398 300c-30 34-34 128-24 214h46Z"/>
    <ellipse cx="230" cy="70" rx="210" ry="160" fill="url(#msSheen)"/>
    <path class="mouse-seam" d="M230 34v218M62 252h336"/>
  </g>
  <path class="shell-edge" d="${shell}"/>

  <g class="mouse-wheel-group">
    <rect class="pressable mouse-wheel" data-pressable="wheel" x="208" y="92" width="44" height="80" rx="22"/>
    <g class="wheel-ridges">${[0, 1, 2, 3, 4, 5].map(i => `<rect x="216" y="${104 + i * 10}" width="28" height="3" rx="1.5"/>`).join('')}</g>
    <path class="wheel-arrow wheel-arrow-up" d="M221 84l9-10 9 10"/>
    <path class="wheel-arrow wheel-arrow-down" d="M221 180l9 10 9-10"/>
  </g>
  <rect class="pressable mouse-dpi" data-pressable="dpi" x="212" y="198" width="36" height="16" rx="8"/>
  <rect class="pressable side-btn" data-pressable="side-1" x="54" y="214" width="42" height="22" rx="11"/>
  <rect class="pressable side-btn" data-pressable="side-2" x="52" y="246" width="42" height="22" rx="11"/>
  <path class="mouse-led" d="M150 408h160"/>

  <g class="mouse-vector" transform="translate(230 332)">
    <circle class="vector-ring" r="48"/>
    <path class="vector-cross" d="M-48 0h96M0-48v96"/>
    <line class="vector-line" data-mouse-vector x1="0" y1="0" x2="0" y2="0"/>
    <circle class="vector-dot" r="4"/>
  </g>

  <g class="ms-badge">
    <rect x="84" y="516" width="292" height="62" rx="14"/>
    <text x="230" y="542" text-anchor="middle" class="ms-badge-main">PERFIL ${esc(inputOptionLabel(mp.latency_mode || '').toUpperCase())}</text>
    <text x="230" y="563" text-anchor="middle" class="ms-badge-sub">Filtro de clique ${mp.debounce} ms</text>
  </g>
</svg>`;
}

// ===========================================================================
// ÁREA DE PERIFÉRICOS
//
// Uma tela, três abas. Substituiu as três páginas separadas (Input Lab, Teclado
// & Mouse, Controle) que mostravam o mesmo periférico em lugares diferentes.
//
// Regra que manda em tudo aqui: NENHUM número aparece sem leitura real.
//   polling  medido pelo azor_input_monitor cronometrando os relatórios do
//            dispositivo; mostra a confiança junto e some quando não há amostra
//   DPI      o Windows não expõe. Diz "não disponível" e explica por quê
//   remap    salvo como perfil, NÃO aplicado — e a tela afirma isso
// ===========================================================================

const PERIPH_TABS = [
  ['controller', 'Controle', '◎'],
  ['keyboard',   'Teclado',  '⌨'],
  ['mouse',      'Mouse',    '◉'],
];

function periphTabs(){
  const cur = S.periphTab || 'controller';
  return `<div class="periph-tabs" role="tablist" aria-label="Periférico">
    ${PERIPH_TABS.map(([id, label, icon]) => {
      const on = cur === id, found = deviceCount(id) > 0;
      return `<button type="button" class="periph-tab ${on ? 'active' : ''}" data-periph-tab="${id}"
        role="tab" aria-selected="${on}">
        <span class="periph-tab-icon">${icon}</span>
        <b>${label}</b>
        <i class="periph-dot ${found ? 'on' : ''}" aria-hidden="true"></i>
      </button>`;
    }).join('')}
  </div>`;
}

// Cabeçalho do aparelho: o nome identificado (fabricante pelo VID), o código USB
// e, quando o aparelho emula outro, a explicação do nome que o Windows mostra.
function periphStatus(kind){
  const count = deviceCount(kind), found = count > 0;
  const row = deviceRow(kind), caps = S.inputCaps?.kinds?.[kind] || {};
  const vid = row.vid || caps.vid, pid = row.pid || caps.pid;
  const note = row.note || caps.note || '';
  return `<div class="periph-status">
    <span class="periph-live ${found ? 'on' : ''}"></span>
    <div>
      <b>${found ? esc(deviceName(kind)) : (kind === 'controller' ? 'Controle não detectado' : 'Não detectado')}</b>
      <small>${found
        ? `${vid ? `VID ${esc(vid)} · PID ${esc(pid || '—')}` : 'Windows HID'}${count > 1 ? ` · ${count} dispositivos` : ''}`
        : 'Conecte o aparelho e clique em Detectar novamente.'}</small>
      ${found && note ? `<p class="periph-note">${esc(note)}</p>` : ''}
    </div>
  </div>`;
}

// Métricas reais, e só elas. Se o AZOR não consegue ler, ele diz que não consegue
// em vez de repetir o número que o usuário escolheu no perfil.
function realMetrics(kind){
  const caps = S.inputCaps?.kinds?.[kind] || {};
  if(kind === 'controller') return padMetricsHtml(caps);
  const pol = S.inputLive?.polling || {};
  const measured = pol.confidence === 'measured' || pol.confidence === 'partial';
  const canPoll = caps.readable?.polling;

  const pollCard = !canPoll
    ? `<div class="metric-real off"><small>Polling Rate</small><b>não disponível</b>
        <span>${esc(caps.polling_reason || 'O AZOR mede a taxa cronometrando os relatórios do dispositivo.')}</span></div>`
    : measured
      ? `<div class="metric-real ${pol.confidence === 'measured' ? 'good' : ''}">
          <small>Polling Rate · medido</small>
          <b>${pol.hz} <i>Hz</i></b>
          <span>${pol.nominal_hz ? `Compatível com ${pol.nominal_hz} Hz nominais. ` : ''}${esc(pol.detail || '')}${
            pol.jitter_ms != null ? ` Variação p95: ${pol.jitter_ms} ms.` : ''}</span></div>`
      : `<div class="metric-real off"><small>Polling Rate</small><b>não disponível</b>
          <span>${esc(pol.detail || caps.polling_reason || 'Mova o mouse com esta tela aberta para o AZOR medir.')}</span></div>`;

  const dpiCard = `<div class="metric-real off"><small>DPI</small><b>não disponível</b>
    <span>${esc(caps.dpi_reason || 'O Windows não expõe o DPI do mouse por nenhuma API.')}</span></div>`;

  const maker = caps.vendor ? `${caps.vendor}${caps.vendor_kind === 'chip' ? ' (chip)' : ''}` : (caps.connection || '—');
  const idCard = `<div class="metric-real"><small>Fabricante</small>
    <b class="metric-id">${esc(maker)}</b>
    <span>VID ${esc(caps.vid || '—')} · PID ${esc(caps.pid || '—')}${caps.connection ? ' · ' + esc(caps.connection) : ''}${caps.status ? ' · ' + esc(caps.status) : ''}</span></div>`;

  return `<div class="metric-real-grid">${kind === 'mouse' ? dpiCard : ''}${pollCard}${idCard}</div>`;
}

// Controle: taxa contada pelos pacotes do XInput, bateria e fabricante. Os três
// são preenchidos ao vivo por paintPadMetrics, sem redesenhar a tela.
function padMetricsHtml(caps){
  const who = padIdentity();
  const canPoll = !!caps.readable?.polling, canBattery = !!caps.readable?.battery;
  return `<div class="metric-real-grid pad-metrics">
    <div class="metric-real ${canPoll ? '' : 'off'}" data-pad-card="hz"><small>Taxa de envio · XInput</small>
      <b data-pad-metric="hz">${canPoll ? '—' : 'não disponível'}</b>
      <span data-pad-metric="hz-detail">${esc(canPoll
        ? 'Gire um analógico em círculos, sem parar, para o AZOR contar os pacotes.'
        : (caps.polling_reason || 'Conecte o controle para medir.'))}</span></div>
    <div class="metric-real ${canBattery ? '' : 'off'}"><small>Bateria</small>
      <b data-pad-metric="battery">${canBattery ? '—' : 'não disponível'}</b>
      <span data-pad-metric="battery-detail">${canBattery ? 'Lida pelo XInput.' : 'O Windows só informa bateria de controle em modo XInput.'}</span></div>
    <div class="metric-real"><small>Fabricante</small>
      <b class="metric-id" data-pad-metric="vendor">${esc(who.vendor || 'não identificado')}</b>
      <span>${who.vid ? `VID ${esc(who.vid)} · PID ${esc(who.pid || '—')}` : 'Sem código USB lido'}${who.xinput ? ' · modo XInput' : ''}</span></div>
  </div>`;
}

// --------------------------------------------------------------------------
// Remapeamento
//
// LEIA: o AZOR não remapeia o controle de verdade. O Windows não dá caminho para
// um app comum reescrever botões de gamepad — precisaria de um controle virtual
// (ViGEmBus) e esconder o físico do jogo (HidHide). O ponto de integração está
// documentado em azor_core.controller_remap(). Aqui o mapa é salvo como perfil,
// e a tela diz isso em vez de fingir.
// --------------------------------------------------------------------------
function remapCard(){
  const r = S.remap || {};
  const changed = r.changed || 0;
  return `<article class="card pad remap-card">
    <div class="remap-icon">⇄</div>
    <h3>Remapeamento</h3>
    <p>Monte o mapa de botões do seu controle e guarde no perfil do AZOR.</p>
    ${changed ? `<div class="remap-count">${changed} botão(ões) remapeado(s) no perfil</div>` : ''}
    <div class="remap-warn">
      <b>Salvo como perfil, não aplicado ao controle.</b>
      <span>O Windows não permite que um aplicativo comum reescreva os botões de um gamepad.
      Fazer isso de verdade exige um controle virtual e esconder o físico do jogo — sem isso o
      jogo enxerga os dois e conta entrada dobrada. O AZOR não marca como aplicado o que não aplicou.</span>
    </div>
    <button class="btn primary" id="openRemap">Remapear botões</button>
  </article>`;
}

function remapModalHtml(){
  const r = S.remap || {};
  const buttons = r.buttons || [];
  const draft = S.remapDraft || {};
  const picking = S.remapPick;
  return `<div class="remap-modal">
    <p class="remap-help">${picking
      ? `Escolha a função que o botão <b>${esc(picking)}</b> vai passar a ter.`
      : 'Clique no botão que você quer trocar e depois escolha a função dele.'}</p>
    <div class="remap-grid">
      ${buttons.map(b => {
        const to = draft[b];
        const isPick = picking === b;
        return `<button type="button" class="remap-btn ${to ? 'mapped' : ''} ${isPick ? 'picking' : ''}"
          data-remap-origin="${b}">
          <b>${b}</b>${to ? `<i>→ ${to}</i>` : '<i>sem troca</i>'}</button>`;
      }).join('')}
    </div>
    ${picking ? `<div class="remap-target">
      <span>Nova função para <b>${esc(picking)}</b>:</span>
      <div class="remap-grid target">
        ${buttons.map(b => `<button type="button" class="remap-btn ${b === picking ? 'self' : ''}"
          data-remap-target="${b}" ${b === picking ? 'disabled' : ''}>${b}</button>`).join('')}
        <button type="button" class="remap-btn clear" data-remap-target="__clear__">sem troca</button>
      </div></div>` : ''}
    <div class="remap-actions">
      <button class="btn ghost" id="remapReset">Restaurar padrão</button>
      <button class="btn ghost" id="remapCancel">Cancelar</button>
      <button class="btn primary" id="remapApply">Salvar no perfil</button>
    </div>
  </div>`;
}

function openRemapModal(){
  S.remapDraft = { ...((S.remap || {}).mapping || {}) };
  S.remapPick = null;
  openModal('Remapeamento do controle', remapModalHtml());
  bindRemapModal();
}

function bindRemapModal(){
  $$('[data-remap-origin]').forEach(b => b.onclick = () => {
    S.remapPick = S.remapPick === b.dataset.remapOrigin ? null : b.dataset.remapOrigin;
    $('#modalBody').innerHTML = `<h2 class="modal-title">Remapeamento do controle</h2>` + remapModalHtml();
    bindRemapModal();
  });
  $$('[data-remap-target]').forEach(b => b.onclick = () => {
    const t = b.dataset.remapTarget;
    if(S.remapPick){
      if(t === '__clear__') delete S.remapDraft[S.remapPick];
      else S.remapDraft[S.remapPick] = t;
    }
    S.remapPick = null;
    $('#modalBody').innerHTML = `<h2 class="modal-title">Remapeamento do controle</h2>` + remapModalHtml();
    bindRemapModal();
  });
  const reset = $('#remapReset');
  if(reset) reset.onclick = () => { S.remapDraft = {}; S.remapPick = null;
    $('#modalBody').innerHTML = `<h2 class="modal-title">Remapeamento do controle</h2>` + remapModalHtml();
    bindRemapModal(); };
  const cancel = $('#remapCancel');
  if(cancel) cancel.onclick = closeModal;
  const apply = $('#remapApply');
  if(apply) apply.onclick = async () => {
    apply.disabled = true; apply.textContent = 'SALVANDO…';
    try{
      const r = await postJSON('/api/action', { name:'save_controller_remap', mapping:S.remapDraft || {} });
      S.remap = r;
      // A mensagem repete o que o card já diz: salvo NÃO é aplicado.
      toast(r.changed
        ? `${r.changed} botão(ões) salvos no perfil. Ainda não aplicados ao controle.`
        : 'Mapa limpo. Nenhuma troca salva.', true);
      closeModal(); render();
    }catch(e){ toast(e.message, false); }
    finally{ apply.disabled = false; apply.textContent = 'Salvar no perfil'; }
  };
}

// --------------------------------------------------------------------------
// Painéis
// --------------------------------------------------------------------------
// Radar do analógico: posição, rastro, zona morta do perfil e o contorno medido
// da circularidade. Desenhado em canvas fora do SVG, então analisar o analógico
// nunca reescreve o desenho do controle.
function stickCard(side){
  const label = side === 'left' ? 'ESQUERDO' : 'DIREITO';
  return `<div class="stick-card" data-stick-card="${side}">
    <div class="stick-card-head"><span class="eyebrow">ANALÓGICO ${label}</span>
      <b class="side-readout" data-readout="stick-${side}">centro</b></div>
    <canvas class="stick-radar" data-stick-radar="${side}" width="176" height="176" role="img"
      aria-label="Posição do analógico ${label.toLowerCase()} com rastro, zona morta do perfil e contorno da circularidade"></canvas>
    <dl class="stick-stats">
      <div><dt>X</dt><dd data-stick-x="${side}">0.000</dd></div>
      <div><dt>Y</dt><dd data-stick-y="${side}">0.000</dd></div>
      <div class="wide"><dt>Deriva parado</dt><dd data-pad-drift="${side}">medindo…</dd>
        <small data-pad-drift-note="${side}">Solte o analógico por 2 segundos.</small></div>
      <div class="wide"><dt>Circularidade</dt><dd data-pad-circ="${side}">0% da volta</dd>
        <small data-pad-circ-note="${side}">Gire encostado na borda, uma volta inteira.</small></div>
    </dl>
  </div>`;
}

// Índice = posição do botão no mapeamento padrão da Gamepad API.
function padChips(variant){
  const face = variant === 'ps5' ? {0:'✕',1:'○',2:'□',3:'△'} : {0:'A',1:'B',2:'X',3:'Y'};
  return [[0,face[0]],[1,face[1]],[2,face[2]],[3,face[3]],[4,'LB'],[5,'RB'],[6,'LT'],[7,'RT'],
    [8,'Voltar'],[9,'Menu'],[10,'L3'],[11,'R3'],[12,'↑'],[13,'↓'],[14,'←'],[15,'→'],[16,'Guia']];
}
function padChipsHtml(variant){
  return `<div class="pad-chips" aria-label="Botões recebidos agora">${padChips(variant)
    .map(([i, label]) => `<span class="pad-chip" data-pad-chip="${i}">${esc(label)}</span>`).join('')}</div>`;
}

function controllerPanel(){
  const cp = currentProfile('controller');
  const skin = S.padSkin || 'auto';
  const variant = padVariant();
  return `<section class="periph-panel card">
    <div class="periph-head">
      ${periphStatus('controller')}
      <label class="pad-device-picker">Entrada<select id="gamepadDevice" aria-label="Controle a testar">${[['auto','Automático'],['0','Controle 1'],['1','Controle 2'],['2','Controle 3'],['3','Controle 4']].map(([v,t])=>`<option value="${v}" ${String(S.padDeviceIndex??'auto')===v?'selected':''}>${t}</option>`).join('')}</select></label>
      <div class="skin-switch" role="radiogroup" aria-label="Layout do desenho">
        <span class="skin-label">Layout do desenho</span>
        <div>
          ${[['auto','Automático'],['xbox','Assimétrico'],['ps5','Simétrico']].map(([id,label]) => `
            <button type="button" class="skin-btn ${skin === id ? 'active' : ''}" data-pad-skin="${id}"
              role="radio" aria-checked="${skin === id}">${label}</button>`).join('')}
        </div>
      </div>
    </div>
    <p class="skin-note">Troca só o desenho desta tela. Não altera driver, não converte o controle e não
    muda como o Windows o identifica.${skin === 'auto' ? ' No automático, o layout segue o fabricante detectado.' : ''}</p>

    <div class="pad-layout">
      ${stickCard('left')}
      <div class="periph-stage pad-stage ${variant}">
        <div class="periph-live-top">
          <span class="two-badge">AO VIVO</span>
          <span class="input-live-dot"></span>
          <strong class="input-live-text" data-live-kind="controller">Pressione os botões ou mova os analógicos</strong>
        </div>
        ${controllerSvg()}
      </div>
      ${stickCard('right')}
    </div>

    <div class="pad-lower">
      <div class="periph-trigger-readouts">${['lt','rt'].map(k=>`<div class="trigger-readout"><span>${k.toUpperCase()}</span><div class="trigger-track"><i data-trigger-meter="${k}"></i></div><b data-trigger-value="${k}">—</b><em data-trigger-max="${k}">máx —</em></div>`).join('')}<small>Pressão dos gatilhos ao vivo. O máximo mostra se o gatilho chega a 100%.</small></div>
      <div class="pad-buttons-card">
        <div class="pad-buttons-head"><span class="eyebrow">BOTÕES</span>
          <span>Ação <b class="side-readout" data-readout="face">nenhum</b></span>
          <span>Direcional <b class="side-readout" data-readout="dpad">solto</b></span></div>
        ${padChipsHtml(variant)}
      </div>
    </div>
    <div class="pad-tests-bar"><span>Deriva, circularidade e curso dos gatilhos saem dos valores que o controle manda
      para esta janela. Nada aqui é estimado.</span><button type="button" class="btn ghost small" id="padTestReset">REFAZER TESTES</button></div>
    ${realMetrics('controller')}

    <div class="periph-config">
      <div class="periph-presets">
        <div class="section-step"><span>1</span><div><b>Escolha como quer jogar</b>
          <small>Você pode trocar o perfil antes de aplicar.</small></div></div>
        ${inputPresetCards('controller')}
        <div class="simple-actions">
          <button class="btn ghost" data-input-action="save-profile:controller">SÓ SALVAR</button>
          <button class="btn primary" data-input-action="apply-profile:controller">APLICAR NO CONTROLE</button>
        </div>
      </div>
      ${remapCard()}
    </div>

    ${advancedInput('CONTROLE','Zonas mortas, gatilhos, curvas e conexão.',
      `<div class="advanced-top"><span>Perfis salvos</span>${inputProfileTabs('controller')}</div>
       <div class="advanced-columns">
         <div class="side-stack"><h3>Sticks</h3>
           ${sliderRow('controller','left_deadzone','Zona morta esquerda',cp.left_deadzone,0,20,1,'%')}
           ${sliderRow('controller','right_deadzone','Zona morta direita',cp.right_deadzone,0,20,1,'%')}
           ${sliderRow('controller','left_antideadzone','Compensação esquerda',cp.left_antideadzone,0,20,1,'%')}
           ${sliderRow('controller','right_antideadzone','Compensação direita',cp.right_antideadzone,0,20,1,'%')}
           ${selectRow('controller','stick_curve','Curva dos sticks',cp.stick_curve,['linear','smooth','aggressive','competitive'])}
         </div>
         <div class="side-stack"><h3>Gatilhos e conexão</h3>
           ${toggleRow('controller','vibration','Vibração',!!cp.vibration)}
           ${sliderRow('controller','lt_deadzone','Zona morta do gatilho esquerdo',cp.lt_deadzone,0,20,1,'%')}
           ${sliderRow('controller','rt_deadzone','Zona morta do gatilho direito',cp.rt_deadzone,0,20,1,'%')}
           ${selectRow('controller','trigger_mode','Comportamento do gatilho',cp.trigger_mode,['adaptive','fixed','hair','instant'])}
           ${selectRow('controller','latency_mode','Comportamento geral',cp.latency_mode,['competitive','balanced','stable'])}
         </div>
       </div>
       <div class="advanced-warning"><b>Importante:</b> zona morta e recursos específicos dependem do
       driver ou do software do fabricante. O AZOR salva o perfil e só confirma como aplicado o que o
       Windows realmente expõe. A zona morta do perfil aparece no radar para comparar com a deriva medida.</div>`)}
  </section>`;
}

function keyboardPanel(){
  const kp = currentProfile('keyboard');
  const fmt = S.kbFormat || 'auto';
  detectKeyboardLayout();
  return `<section class="periph-panel card">
    <div class="periph-head">${periphStatus('keyboard')}
      <div class="skin-switch" role="radiogroup" aria-label="Formato do teclado">
        <span class="skin-label">Formato do desenho</span>
        <div>${[['auto','Automático'],['ansi','ANSI (EUA)'],['abnt2','ABNT2 (Brasil)']].map(([id,label]) => `
          <button type="button" class="skin-btn ${fmt === id ? 'active' : ''}" data-kb-format="${id}"
            role="radio" aria-checked="${fmt === id}">${label}</button>`).join('')}</div>
      </div>
    </div>
    <div class="periph-stage keyboard-stage">
      <div class="periph-live-top">
        <span class="two-badge">AO VIVO</span>
        <span class="input-live-dot"></span>
        <strong class="input-live-text" data-live-kind="keyboard">Pressione as teclas com esta janela em foco</strong>
      </div>
      ${keyboardSvg()}
    </div>
    <div class="lab-grid">
      <article class="lab-card rollover-card">
        <div class="lab-head"><span class="eyebrow">TECLAS AO MESMO TEMPO</span>
          <button type="button" class="btn ghost small" id="rolloverReset">ZERAR</button></div>
        <div class="lab-reads">
          <div><b data-kb-held>0</b><small>seguradas agora</small></div>
          <div><b data-kb-max>${S.kbMax || 0}</b><small>máximo registrado</small></div>
        </div>
        <p class="lab-note" data-kb-verdict>Segure W, A, S, D, Shift e Espaço juntos e vá somando teclas.
        O número mostra quantas o Windows recebeu ao mesmo tempo.</p>
      </article>
      <article class="lab-card">
        <div class="lab-head"><span class="eyebrow">TECLAS PRESSIONADAS</span></div>
        <div class="lab-reads single"><div><b data-kb-presses>0</b><small>nesta sessão</small></div></div>
        <p class="lab-note">O AZOR conta quantas vezes uma tecla desceu, nunca quais nem em que ordem.
        O desenho acende pela posição física da tecla, então funciona em ABNT2 e ANSI.</p>
      </article>
    </div>
    ${realMetrics('keyboard')}
    <div class="periph-config single">
      <div class="periph-presets">
        <div class="section-step"><span>1</span><div><b>Escolha o comportamento</b>
          <small>O AZOR equilibra rapidez, sensibilidade e estabilidade.</small></div></div>
        ${inputPresetCards('keyboard')}
        <div class="simple-actions">
          <button class="btn ghost" data-input-action="save-profile:keyboard">SÓ SALVAR</button>
          <button class="btn primary" data-input-action="apply-profile:keyboard">APLICAR NO TECLADO</button>
        </div>
      </div>
    </div>
    ${advancedInput('TECLADO','Repetição, atuação, NKRO e Rapid Trigger.',
      `<div class="advanced-top"><span>Perfis salvos</span>${inputProfileTabs('keyboard')}</div>
       <div class="advanced-columns">
         <div class="side-stack"><h3>Resposta das teclas</h3>
           ${sliderRow('keyboard','debounce','Filtro de tecla',kp.debounce,0,12,1,' ms')}
           ${toggleRow('keyboard','nkro','Reconhecer várias teclas (NKRO)',!!kp.nkro)}
           ${toggleRow('keyboard','rapid_trigger','Rapid Trigger, se suportado',!!kp.rapid_trigger)}
           ${selectRow('keyboard','socd','Teclas opostas / SOCD',kp.socd,['off','last input','neutral'])}
         </div>
         <div class="side-stack"><h3>Repetição e sensibilidade</h3>
           ${sliderRow('keyboard','repeat_delay','Espera para repetir',kp.repeat_delay,0,3,1)}
           ${sliderRow('keyboard','repeat_rate','Velocidade de repetição',kp.repeat_rate,0,31,1)}
           ${sliderRow('keyboard','actuation','Ponto de acionamento',kp.actuation,0.1,4,0.1,' mm')}
           ${selectRow('keyboard','latency_mode','Comportamento',kp.latency_mode,['competitive','balanced','stable'])}
         </div>
       </div>
       <div class="advanced-warning"><b>Importante:</b> atuação, Rapid Trigger e SOCD só existem em
       teclado que expõe isso ao Windows. O AZOR guarda no perfil e aplica o que o sistema aceita —
       repetição e filtro de tecla são reais e verificados.</div>`)}
  </section>`;
}

const CLICK_BUTTONS = [['left-click','Esquerdo'],['right-click','Direito'],['wheel','Meio'],['side-1','Lateral 1'],['side-2','Lateral 2']];

function mousePanel(){
  const mp = currentProfile('mouse');
  return `<section class="periph-panel card">
    <div class="periph-head">${periphStatus('mouse')}</div>
    <div class="periph-stage-grid mouse-grid">
      <div class="periph-side">
        <div class="side-card"><span class="eyebrow">BOTÃO ESQUERDO</span>
          <div class="side-readout" data-readout="left-click">solto</div></div>
        <div class="side-card"><span class="eyebrow">BOTÕES LATERAIS</span>
          <div class="side-readout" data-readout="side">solto</div></div>
      </div>
      <div class="periph-stage mouse-stage">
        <div class="periph-live-top">
          <span class="two-badge">AO VIVO</span>
          <span class="input-live-dot"></span>
          <strong class="input-live-text" data-live-kind="mouse">Clique, role ou use os botões laterais</strong>
        </div>
        ${mouseSvg()}
      </div>
      <div class="periph-side">
        <div class="side-card"><span class="eyebrow">BOTÃO DIREITO</span>
          <div class="side-readout" data-readout="right-click">solto</div></div>
        <div class="side-card"><span class="eyebrow">SCROLL</span>
          <div class="side-readout" data-readout="wheel">parado</div></div>
      </div>
    </div>

    <div class="lab-grid three">
      <article class="lab-card click-card">
        <div class="lab-head"><span class="eyebrow">TESTE DE CLIQUE</span>
          <button type="button" class="btn ghost small" id="clickTestReset">ZERAR</button></div>
        <div class="click-grid">${CLICK_BUTTONS.map(([k, l]) => `<div><small>${l}</small><b data-click-count="${k}">0</b></div>`).join('')}</div>
        <div class="click-cps"><span>Cliques por segundo</span><b data-cps>0</b><small data-cps-max>recorde 0</small></div>
        <p class="lab-note" data-click-verdict>Clique algumas vezes em cada botão. Um clique que vira dois sozinho aparece aqui.</p>
      </article>
      <article class="lab-card rhythm-card">
        <div class="lab-head"><span class="eyebrow">RITMO DO POLLING</span><b data-rhythm-hz>—</b></div>
        <div class="rhythm-bar" aria-hidden="true"><i class="on" data-stab="on_beat"></i><i class="early" data-stab="early"></i><i class="late" data-stab="late"></i><i class="gaps" data-stab="gaps"></i></div>
        <ul class="rhythm-legend">
          <li><i class="on"></i>No ritmo <b data-stab-text="on_beat">—</b></li>
          <li><i class="early"></i>Adiantado <b data-stab-text="early">—</b></li>
          <li><i class="late"></i>Atrasado <b data-stab-text="late">—</b></li>
          <li><i class="gaps"></i>Pausa ou relatório perdido <b data-stab-text="gaps">—</b></li>
        </ul>
        <p class="lab-note">Mova o mouse rápido e sem parar. Movimento lento também abre intervalo, porque o
        mouse só manda relatório quando anda.</p>
      </article>
      <article class="lab-card">
        <div class="lab-head"><span class="eyebrow">SENSOR</span></div>
        <div class="lab-reads">
          <div><b data-mouse-counts>0</b><small>contagens/s agora</small></div>
          <div><b data-mouse-peak>${S.mousePeak || 0}</b><small>pico da sessão</small></div>
        </div>
        <p class="lab-note">Contagem crua do sensor, antes da aceleração do Windows. Dividida pelo DPI do
        mouse vira polegadas por segundo — o DPI o Windows não informa.</p>
      </article>
    </div>
    ${realMetrics('mouse')}
    <div class="periph-config single">
      <div class="periph-presets">
        <div class="section-step"><span>1</span><div><b>Como você vai usar?</b>
          <small>O AZOR prepara resposta, estabilidade e energia da porta.</small></div></div>
        ${inputPresetCards('mouse')}
        <div class="simple-actions">
          <button class="btn ghost" data-input-action="save-profile:mouse">SÓ SALVAR</button>
          <button class="btn primary" data-input-action="apply-profile:mouse">APLICAR NO MOUSE</button>
        </div>
      </div>
    </div>
    ${advancedInput('MOUSE','Aceleração, filtro de clique e energia USB.',
      `<div class="advanced-top"><span>Perfis salvos</span>${inputProfileTabs('mouse')}</div>
       <div class="advanced-columns">
         <div class="side-stack"><h3>Movimento</h3>
           ${toggleRow('mouse','enhanced_pointer_precision','Aceleração do ponteiro do Windows',!!mp.enhanced_pointer_precision)}
           ${selectRow('mouse','lod','Distância ao levantar',mp.lod,['low','medium','high'])}
           ${toggleRow('mouse','angle_snapping','Correção de linha (angle snapping)',!!mp.angle_snapping)}
         </div>
         <div class="side-stack"><h3>Cliques e conexão</h3>
           ${sliderRow('mouse','debounce','Filtro de clique (debounce)',mp.debounce,0,12,1,' ms')}
           ${selectRow('mouse','latency_mode','Comportamento',mp.latency_mode,['competitive','balanced','stable'])}
           ${toggleRow('mouse','usb_suspend_off','Impedir economia de energia USB',!!mp.usb_suspend_off)}
         </div>
       </div>
       <div class="advanced-warning"><b>Sobre DPI e polling:</b> o AZOR não escreve DPI nem taxa de
       envio — os dois vivem no firmware do mouse e só o software do fabricante altera. O que aparece
       acima como Polling Rate é <b>medido</b> dos relatórios reais do seu mouse, não configurado.</div>`)}
  </section>`;
}

function renderPeripherals(){
  const tab = S.periphTab || 'controller';
  const panel = tab === 'keyboard' ? keyboardPanel() : tab === 'mouse' ? mousePanel() : controllerPanel();
  return `${head('Periféricos','Controle, teclado e mouse com resposta ao vivo. Nenhum número aqui é estimado: o que o AZOR não consegue ler, ele diz que não consegue.',
    '<button class="btn ghost" id="refreshDevices">↻ DETECTAR NOVAMENTE</button>')}
  ${periphTabs()}
  ${tab === 'controller' ? usbIrqCard() : ''}
  ${panel}`;
}

// Controle em 4K/8K: para onde o Windows manda as interrupções da controladora USB.
function usbIrqCard(){
  const r=S.usbIrq, st=r&&r.state, load=r&&r.load, b=load&&load.busiest;
  const n=v=>Number(v||0).toLocaleString('pt-BR',{maximumFractionDigits:0});
  let body;
  if(S.usbIrqLoading) body='<p class="section-sub">Medindo por 2 segundos… deixe o jogo aberto e mexa no controle para ver o pico.</p>';
  else if(!r) body='<p class="section-sub">Em 4K ou 8K o controle manda milhares de relatórios por segundo, e o Windows entrega as interrupções da controladora USB num núcleo só — quase sempre um núcleo P, o mesmo que o jogo usa. Meça com o jogo aberto para ver onde elas estão caindo.</p>';
  else{
    const hosts=(st&&st.hosts)||[];
    const where=hosts.length?hosts.map(h=>`${esc(h.name)} (${esc((h.controllers||[]).join(', ')||'controle')})`).join('; '):'Nenhum controle de jogo conectado por USB agora.';
    const busy=b?`<div class="usb-irq-row ${b.efficiency?'':'bad'}"><span>Núcleo mais carregado</span><b>CPU ${b.cpu} · ${b.efficiency?'núcleo E':'núcleo P'}</b><small>${n(b.interrupts)} interrupções/s · ${n(b.dpcs)} DPCs/s · ${Number(b.busy_pct||0).toFixed(1)}% do tempo dele${load.others_median_dpcs!=null?` · nos outros núcleos, ~${n(load.others_median_dpcs)} DPCs/s`:''}</small></div>`:'<p class="section-sub">O Windows não devolveu os contadores de processador.</p>';
    const aff=!st?'':!st.hybrid?'Este processador não tem núcleos E: o ajuste não se aplica.':st.all_on_ecores?`Gravado para os núcleos E (CPU ${(st.ecore_cpus||[]).join(', ')}). Se aplicou agora, reinicie e meça de novo.`:'Padrão do Windows.';
    body=`${busy}<div class="usb-irq-row"><span>Onde o controle está</span><small>${where}</small></div><div class="usb-irq-row"><span>Destino das interrupções</span><small>${esc(aff)}</small></div>`;
  }
  const canApply=st&&st.hybrid&&(st.hosts||[]).length&&!st.all_on_ecores;
  const canRevert=st&&st.all_on_ecores;
  return `<article class="card pad usb-irq-card">
    <div class="device-head"><div><span class="eyebrow">Controle em 4K ou 8K</span><h3>Stutter com polling alto</h3></div></div>
    ${body}
    <div class="quick-buttons">
      <button class="btn ghost" type="button" id="usbIrqMeasure" ${S.usbIrqLoading?'disabled':''}>${r?'MEDIR DE NOVO':'MEDIR AGORA'}</button>
      ${canApply?'<button class="btn primary" type="button" id="usbIrqApply">MANDAR PARA OS NÚCLEOS E</button>':''}
      ${canRevert?'<button class="btn ghost" type="button" id="usbIrqRevert">DESFAZER</button>':''}
    </div>
    <p class="section-sub setting-note">Vale depois de reiniciar e muda também o teclado e o mouse ligados na mesma controladora. Se ainda travar em 8K, use 4K ou 2K: a 180 FPS, a diferença de 8K para 2K é menor que um décimo de quadro.</p>
  </article>`;
}

async function measureUsbIrq(){
  if(S.usbIrqLoading)return;
  S.usbIrqLoading=true;render();
  try{S.usbIrq=await getJSON('/api/usb-irq')}
  catch(e){toast('Medição falhou: '+e.message,false)}
  finally{S.usbIrqLoading=false;if(isInputPage())render()}
}

async function usbIrqAction(kind,btn){
  const apply=kind==='apply';
  if(!confirm(apply
    ?'Mandar as interrupções da controladora USB do controle para os núcleos E?\n\nSó passa a valer depois de reiniciar o Windows. Teclado e mouse ligados na mesma controladora também mudam de núcleo. O AZOR cria um ponto de restauração antes, e o DESFAZER volta ao padrão.'
    :'Voltar as interrupções da controladora USB ao padrão do Windows? Só passa a valer depois de reiniciar.'))return;
  const old=btn?.textContent;if(btn){btn.disabled=true;btn.textContent=apply?'APLICANDO…':'DESFAZENDO…'}
  try{
    const r=apply
      ?await postJSON('/api/action',{name:'apply_task',id:'usb_interrupts_ecores',profile:PERFORMANCE_MODES[S.quickProfile]?S.quickProfile:'maximo'},ACTION_TIMEOUT_MS)
      :await postJSON('/api/action',{name:'revert_task',id:'usb_interrupts_ecores'},ACTION_TIMEOUT_MS);
    toast(r.detail||(r.ok?'Feito. Reinicie o Windows e meça de novo.':'Não foi possível concluir.'),r.ok===true);
  }catch(e){toast(e.message,false)}
  finally{S.usbIrq=null;S.arsenal=null;if(btn){btn.disabled=false;btn.textContent=old}render()}
}

async function loadInputCaps(){
  try{ S.inputCaps = await getJSON('/api/input-capabilities');
    S.remap = S.inputCaps.remap || S.remap;
    if(isInputPage()) render();
  }catch(e){ console.warn('input caps', e); }
}

// As tres rotas antigas continuam existindo - elas sao linkadas da Home, da
// Otimizacao Rapida e do menu - mas todas abrem a mesma tela, na aba certa.
function renderDevice(){ S.periphTab = S.periphTab || 'controller'; return renderPeripherals(); }
function renderKeyboardMouse(){ if(!['keyboard','mouse'].includes(S.periphTab)) S.periphTab='mouse'; return renderPeripherals(); }
function renderController(){ S.periphTab = 'controller'; return renderPeripherals(); }

function _legacyRenderDevice(){return `${head('AZOR INPUT LAB','Escolha o periférico, selecione um objetivo e aplique. Os ajustes técnicos continuam disponíveis quando você precisar.','<button class="btn ghost" id="refreshDevices">↻ DETECTAR NOVAMENTE</button>')}
  <section class="input-flow card"><div class="flow-step active"><span>1</span><div><b>Escolha o dispositivo</b><small>Controle, mouse ou teclado</small></div></div><i>›</i><div class="flow-step"><span>2</span><div><b>Escolha o objetivo</b><small>Competitivo, equilibrado ou estável</small></div></div><i>›</i><div class="flow-step"><span>3</span><div><b>Revise e aplique</b><small>O AZOR mostra o que realmente mudou</small></div></div></section>
  <section class="card input-lab-intro"><div><span class="eyebrow">CONFIGURAÇÃO GUIADA</span><h2>Mais simples por fora.<br><span>Completo por dentro.</span></h2><p>Você escolhe como quer usar o periférico. O AZOR prepara os detalhes técnicos e mantém cada opção avançada acessível, sem obrigar ninguém a entender siglas.</p></div><div class="intro-points"><span><b>✓</b> Detecção real do Windows</span><span><b>✓</b> Preview 2D interativo e responsivo aos inputs</span><span><b>✓</b> Resultado explicado após aplicar</span></div></section>
  <section class="device-cards input-device-grid">${genericDeviceCard('controller','Controle','','#9b54ff','controller')}${genericDeviceCard('mouse','Mouse','','#3f9dff','keyboardmouse')}${genericDeviceCard('keyboard','Teclado','','#de42ff','keyboardmouse')}</section>
  ${pollingPanel()}
  <div class="simple-note card"><span>i</span><p><b>Nenhum número é inventado.</b> DPI, polling físico e recursos do fabricante só aparecem como aplicados quando houver confirmação compatível.</p></div>`}
function _legacyRenderKeyboardMouse(){const mp=currentProfile('mouse'),kp=currentProfile('keyboard');return `${head('Teclado & Mouse','Escolha o dispositivo e um perfil pronto. A tela mostra apenas o necessário para concluir cada configuração.')}
  <section class="input-device-switcher card"><button type="button" class="device-switch ${S.inputDeviceTab==='mouse'?'active':''}" data-input-device-tab="mouse" aria-pressed="${S.inputDeviceTab==='mouse'}"><span>◉</span><div><b>Mouse</b><small>${esc(deviceName('mouse'))}</small></div><i>${deviceCount('mouse')?'DETECTADO':'NÃO DETECTADO'}</i></button><button type="button" class="device-switch ${S.inputDeviceTab==='keyboard'?'active':''}" data-input-device-tab="keyboard" aria-pressed="${S.inputDeviceTab==='keyboard'}"><span>⌨</span><div><b>Teclado</b><small>${esc(deviceName('keyboard'))}</small></div><i>${deviceCount('keyboard')?'DETECTADO':'NÃO DETECTADO'}</i></button></section>
  <section class="simple-input-section card ${S.inputDeviceTab==='mouse'?'':'input-tab-hidden'}">
    ${inputDeviceHeader('mouse','MOUSE')}
    <div class="simple-input-grid"><div class="simple-visual">${input2DStage('mouse','Mouse','#3f9dff')}${inputTruth('mouse')}</div><div class="simple-config"><div class="section-step"><span>1</span><div><b>Como você vai usar?</b><small>O AZOR ajusta o que é do Windows e guarda o resto como perfil.</small></div></div>${inputPresetCards('mouse')}<div class="section-step compact-step"><span>2</span><div><b>Confira e aplique</b><small>Nada muda até você confirmar.</small></div></div><div class="simple-actions"><button class="btn ghost" data-input-action="save-profile:mouse">SÓ SALVAR</button><button class="btn primary" data-input-action="apply-profile:mouse">APLICAR NO MOUSE</button></div></div></div>
    ${advancedInput('MOUSE','DPI, debounce, sensor, polling e energia USB.',`<div class="advanced-top"><span>Perfis salvos</span>${inputProfileTabs('mouse')}</div><div class="advanced-columns"><div class="side-stack"><h3>Movimento</h3>${sliderRow('mouse','dpi_x','DPI horizontal',mp.dpi_x,200,6400,100)}${sliderRow('mouse','dpi_y','DPI vertical',mp.dpi_y,200,6400,100)}${sliderRow('mouse','smoothing','Suavização',mp.smoothing,0,20,1,'%')}${toggleRow('mouse','angle_snapping','Correção de linha (Angle snapping)',!!mp.angle_snapping)}${toggleRow('mouse','motion_sync','Sincronização de movimento',!!mp.motion_sync)}${selectRow('mouse','lod','Distância ao levantar',mp.lod,['low','medium','high'])}</div><div class="side-stack"><h3>Cliques e conexão</h3>${sliderRow('mouse','debounce','Filtro de clique (debounce)',mp.debounce,0,12,1,' ms')}${selectRow('mouse','latency_mode','Comportamento',mp.latency_mode,['competitive','balanced','stable'])}${toggleRow('mouse','enhanced_pointer_precision','Aceleração do ponteiro do Windows',!!mp.enhanced_pointer_precision)}${toggleRow('mouse','usb_suspend_off','Impedir economia de energia USB',!!mp.usb_suspend_off)}<div class="hz-title">Taxa desejada</div>${hzButtons('mouse',mp.overclock_hz||mp.poll_rate)}</div></div>${diagTable('mouse')}`)}
  </section>
  <section class="simple-input-section card ${S.inputDeviceTab==='keyboard'?'':'input-tab-hidden'}">
    ${inputDeviceHeader('keyboard','TECLADO')}
    <div class="simple-input-grid"><div class="simple-visual">${input2DStage('keyboard','Teclado','#de42ff')}${inputTruth('keyboard')}</div><div class="simple-config"><div class="section-step"><span>1</span><div><b>Escolha o comportamento</b><small>O AZOR equilibra rapidez, sensibilidade e estabilidade.</small></div></div>${inputPresetCards('keyboard')}<div class="section-step compact-step"><span>2</span><div><b>Confira e aplique</b><small>O relatório final separa o perfil do que o Windows alterou.</small></div></div><div class="simple-actions"><button class="btn ghost" data-input-action="save-profile:keyboard">SÓ SALVAR</button><button class="btn primary" data-input-action="apply-profile:keyboard">APLICAR NO TECLADO</button></div></div></div>
    ${advancedInput('TECLADO','Polling, repetição, atuação, NKRO, Rapid Trigger e SOCD.',`<div class="advanced-top"><span>Perfis salvos</span>${inputProfileTabs('keyboard')}</div><div class="advanced-columns"><div class="side-stack"><h3>Resposta das teclas</h3>${sliderRow('keyboard','poll_rate','Taxa de resposta',kp.poll_rate,125,1000,125,' Hz')}${sliderRow('keyboard','scan_rate','Leitura interna',kp.scan_rate,125,1000,125,' Hz')}${sliderRow('keyboard','debounce','Filtro de tecla',kp.debounce,0,12,1,' ms')}${toggleRow('keyboard','nkro','Reconhecer várias teclas (NKRO)',!!kp.nkro)}${toggleRow('keyboard','rapid_trigger','Rapid Trigger, se suportado',!!kp.rapid_trigger)}${selectRow('keyboard','socd','Teclas opostas / SOCD',kp.socd,['off','last input','neutral'])}</div><div class="side-stack"><h3>Sensibilidade e repetição</h3>${sliderRow('keyboard','repeat_delay','Espera para repetir',kp.repeat_delay,0,3,1)}${sliderRow('keyboard','repeat_rate','Velocidade de repetição',kp.repeat_rate,0,31,1)}${sliderRow('keyboard','actuation','Ponto de acionamento',kp.actuation,0.1,4,0.1,' mm')}${sliderRow('keyboard','reset_point','Ponto de retorno',kp.reset_point,0.1,4,0.1,' mm')}${selectRow('keyboard','latency_mode','Comportamento',kp.latency_mode,['competitive','balanced','stable'])}<div class="hz-title">Taxa desejada</div>${hzButtons('keyboard',kp.overclock_hz||kp.poll_rate)}</div></div>${diagTable('keyboard')}`)}
  </section>`}
function _legacyRenderController(){const cp=currentProfile('controller');return `${head('Controle','Escolha um objetivo e deixe o AZOR preparar o perfil. Os ajustes técnicos ficam organizados em uma área avançada.')}
  <section class="simple-input-section card controller-simple-section">
    ${inputDeviceHeader('controller','CONTROLE')}
    <div class="simple-input-grid controller-simple-grid"><div class="simple-visual">${input2DStage('controller','Controle','#9b54ff')}${inputTruth('controller')}</div><div class="simple-config"><div class="section-step"><span>1</span><div><b>Escolha como quer jogar</b><small>Você pode trocar o perfil antes de aplicar.</small></div></div>${inputPresetCards('controller')}<div class="what-changes"><h3>O que esse perfil organiza</h3><div><span>◎ Sticks</span><span>◒ Gatilhos</span><span>ϟ Resposta</span><span>⌁ Conexão USB</span></div></div><div class="section-step compact-step"><span>2</span><div><b>Revise e aplique</b><small>O AZOR cria o relatório do resultado real.</small></div></div><div class="simple-actions"><button class="btn ghost" data-input-action="save-profile:controller">SÓ SALVAR</button><button class="btn primary" data-input-action="apply-profile:controller">APLICAR NO CONTROLE</button></div></div></div>
    ${advancedInput('CONTROLE','Zonas mortas, gatilhos, curvas, botões, polling e modo experimental.',`<div class="advanced-top"><span>Perfis salvos</span>${inputProfileTabs('controller')}</div><div class="advanced-columns"><div class="side-stack"><h3>Sticks e botões</h3>${sliderRow('controller','left_deadzone','Zona morta esquerda',cp.left_deadzone,0,20,1,'%')}${sliderRow('controller','right_deadzone','Zona morta direita',cp.right_deadzone,0,20,1,'%')}${sliderRow('controller','left_antideadzone','Compensação esquerda',cp.left_antideadzone,0,20,1,'%')}${sliderRow('controller','right_antideadzone','Compensação direita',cp.right_antideadzone,0,20,1,'%')}${selectRow('controller','stick_curve','Curva dos sticks',cp.stick_curve,['linear','smooth','aggressive','competitive'])}${selectRow('controller','button_response','Resposta dos botões',cp.button_response,['safe','fast','ultra'])}</div><div class="side-stack"><h3>Gatilhos e conexão</h3>${toggleRow('controller','vibration','Vibração',!!cp.vibration)}${sliderRow('controller','lt_deadzone','Zona morta do gatilho esquerdo',cp.lt_deadzone,0,20,1,'%')}${sliderRow('controller','rt_deadzone','Zona morta do gatilho direito',cp.rt_deadzone,0,20,1,'%')}${selectRow('controller','trigger_mode','Comportamento do gatilho',cp.trigger_mode,['adaptive','fixed','hair','instant'])}${selectRow('controller','latency_mode','Comportamento geral',cp.latency_mode,['competitive','balanced','stable'])}${selectRow('controller','oc_mode','Modo experimental',cp.oc_mode,['off','safe','moderate','aggressive'])}<div class="hz-title">Taxa desejada</div>${hzButtons('controller',cp.overclock_hz||cp.poll_rate)}</div></div><div class="advanced-warning"><b>Importante:</b> zonas mortas e recursos específicos dependem do driver ou software do controle. O AZOR salva o perfil e só confirma como aplicado o que o Windows realmente expõe.</div>${diagTable('controller')}`)}
  </section>`}
function gameMonitorStrip(){const d=S.gameDiag||{};const live=d.live||{};const running=!!d.running;const detected=running&&!d.waiting_for_game;return `<article class="card game-live-strip ${detected?'active':''}"><div><span class="eyebrow">MONITOR DE JOGO</span><h3>${detected?'Fortnite em análise':running?'Aguardando Fortnite':'Pronto para analisar uma partida'}</h3><p>${detected?`CPU ${fmt(live.cpu,'%')} • GPU ${fmt(live.gpu,'%')} • RAM ${fmt(live.ram,'%')} • ${d.samples||0} amostras`:'Faça uma coleta Antes e Depois para comparar uso, FPS/frametime quando disponível e processos em background.'}</p></div><div class="game-live-actions"><span class="pill ${detected?'goodpill':''}">${detected?'AO VIVO':running?'AGUARDANDO':'OFF'}</span><button class="btn primary" data-go="gameDiag">ABRIR MONITOR DE JOGO</button></div></article>`}

function renderMonitor(
){
  const m=S.monitor||{};const cpu=m.cpu||{},gpu=m.gpu||{},ram=m.ram||{},disk=m.disk||{},net=m.network||{};
  return `${head('Monitoramento do PC','Telemetria real do sistema em tempo real. Sensores não disponíveis aparecem como indisponíveis, nunca como valores inventados.','<button class="btn ghost" id="refreshMonitor">↻ ATUALIZAR</button>')}${guide('Como ler esta página','Uso de CPU/RAM vem do Windows. GPU usa nvidia-smi quando disponível. Temperatura da CPU e fans aparecem quando LibreHardwareMonitor/OpenHardwareMonitor estiver expondo sensores.',3,5)}${gameMonitorStrip()}<section class="monitor-summary">${metric('CPU','⌁',fmt(cpu.usage,'%'),`Temp: ${fmt(cpu.temp_c,'°C')}`,cpu.usage)}${metric('GPU','◇',fmt(gpu.available?gpu.usage:null,'%'),gpu.available?`${esc(gpu.name||'GPU')} • ${fmt(gpu.temp_c,'°C')}`:'Sensor não disponível',gpu.usage)}${metric('RAM','▤',fmt(ram.percent,'%'),ram.total_gb?`${ram.used_gb} / ${ram.total_gb} GB`:'Indisponível',ram.percent)}${metric('Disco','▥',fmt(disk.percent,'%'),disk.total_gb?`${disk.used_gb} / ${disk.total_gb} GB ocupados`:'Indisponível',disk.percent)}${metric('Download','↓',fmt(net.down_mbps,' Mbps'),'Tráfego atual',null)}${metric('Upload','↑',fmt(net.up_mbps,' Mbps'),'Tráfego atual',null)}</section><section class="monitor-grid"><article class="card chart-card"><div class="chart-head"><h3>Uso em tempo real</h3><div class="chart-legend"><span><i class="legend-dot" style="background:#ff5cd6"></i>CPU</span><span><i class="legend-dot" style="background:#a08cff"></i>GPU</span><span><i class="legend-dot" style="background:#56d6a8"></i>RAM</span></div></div><canvas id="usageChart" class="chart"></canvas></article><article class="card chart-card"><div class="chart-head"><h3>Processos com maior memória</h3><span class="section-sub">Atualiza a cada ~5 s</span></div><div class="process-list">${(m.processes||[]).length?(m.processes||[]).map(p=>`<div class="process"><b>${esc(p.name)}</b><span>${p.memory_mb} MB</span></div>`).join(''):'<div class="empty">Leitura de processos indisponível.</div>'}</div></article></section><section class="grid cols-3" style="margin-top:14px"><article class="card pad"><h3 class="section-title">Temperaturas</h3><p class="section-sub">CPU: <b>${fmt(cpu.temp_c,'°C')}</b><br>GPU: <b>${fmt(gpu.available?gpu.temp_c:null,'°C')}</b><br>Fonte: ${esc(m.sensor_source||'Windows/GPU; CPU pode exigir monitor de hardware')}</p></article><article class="card pad"><h3 class="section-title">Clocks</h3><p class="section-sub">CPU: <b>${fmt(cpu.clock_mhz,' MHz')}</b><br>GPU: <b>${fmt(gpu.available?gpu.clock_mhz:null,' MHz')}</b></p></article><article class="card pad"><h3 class="section-title">Ventoinhas</h3><p class="section-sub">${(m.fans||[]).length?(m.fans||[]).map(f=>`${esc(f.name)}: <b>${f.rpm} RPM</b>`).join('<br>'):'Nenhum sensor de fan disponível.'}</p></article></section>`
}


function renderGameDiagnostic(){
  const d=S.gameDiag||{};const live=d.live||{};const rep=d.last_report?.summary||d.summary||{};const frames=rep.frames||{};const pm=d.presentmon||{};const running=!!d.running;const waiting=!!d.waiting_for_game;
  const statusLabel=d.status==='capturing'?'COLETANDO':d.status==='waiting'?'AGUARDANDO FORTNITE':d.status==='finalizing'?'FINALIZANDO':d.status==='completed'?'CONCLUÍDO':d.status==='error'?'ERRO':'PRONTO';
  const statusClass=d.status==='completed'?'goodpill':(d.status==='error'?'off':'');
  const reports=Array.isArray(S.gameReports)?S.gameReports:[];
  const pmText=pm.available?'ETW headless disponível':'ETW de FPS não disponível';
  return `${head('Diagnóstico em Jogo','Analise o PC do cliente durante uma partida real do Fortnite e compare Antes × Depois. A coleta roda em segundo plano, sem overlay e sem injeção no jogo.','<button class="btn ghost" id="refreshGameDiag">↻ ATUALIZAR</button>')}
  ${guide('Como usar','Digite um nome para identificar o cliente, inicie ANTES, entre em uma partida por alguns minutos e finalize. Depois da otimização repita em DEPOIS. O AZOR salva JSON, TXT e HTML dentro da pasta Relatorios.',4,5)}
  <section class="grid cols-2">
    <article class="card pad glow-purple">
      <div class="device-head"><div><span class="eyebrow">SESSÃO</span><h3 class="section-title">${esc(statusLabel)}</h3></div><span class="pill ${statusClass}">${running?'ATIVO':'OFF'}</span></div>
      <label class="field" style="margin-top:14px"><div class="field-head"><span>Identificação do cliente</span></div><input class="input" id="gameDiagCustomer" maxlength="60" placeholder="Ex.: Cliente Pedro" value="${esc(d.customer||'')}"></label>
      <p class="section-sub" style="margin-top:10px">${esc(d.detail||'Pronto para iniciar uma coleta.')}</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:14px">
        <button class="btn primary" id="gameDiagBefore" ${running?'disabled':''}>INICIAR ANTES</button>
        <button class="btn cyan" id="gameDiagAfter" ${running?'disabled':''}>INICIAR DEPOIS</button>
        <button class="btn danger" id="gameDiagStop" ${running?'':'disabled'}>FINALIZAR ANÁLISE</button>
      </div>
      <div class="capability-grid" style="margin-top:14px"><div class="capability real"><b>✓ SEM OVERLAY</b><span>Coleta do Windows em segundo plano. O AZOR não injeta DLL nem mexe na memória do Fortnite.</span></div><div class="capability ${pm.available?'real':'no'}"><b>${pm.available?'✓ FPS / FRAMETIME':'! FPS / FRAMETIME'}</b><span>${esc(pmText)}. Quando indisponível, o AZOR não inventa FPS, 1% Low ou frametime.</span></div></div>
      ${pm.available?'':`<button class="btn ghost" id="setupFrameCapture" style="margin-top:10px">ATIVAR FPS / 1% LOW / FRAMETIME</button>`}
    </article>
    <article class="card pad">
      <span class="eyebrow">AO VIVO</span><h3 class="section-title">${waiting?'Aguardando o jogo abrir':running?'Fortnite detectado':'Última leitura'}</h3>
      <div class="preset-grid" style="margin-top:14px">
        <div class="preset"><strong>CPU</strong><span>${fmt(live.cpu,'%')}</span></div><div class="preset"><strong>GPU</strong><span>${fmt(live.gpu,'%')}</span></div><div class="preset"><strong>RAM</strong><span>${fmt(live.ram,'%')}</span></div><div class="preset"><strong>Fortnite CPU</strong><span>${fmt(live.fortnite_cpu,'%')}</span></div><div class="preset"><strong>Fortnite GPU</strong><span>${fmt(live.fortnite_gpu,'%')}</span></div><div class="preset"><strong>Amostras</strong><span>${d.samples??0}</span></div>
      </div>
      <div class="explain-box"><h4>O que fica registrado</h4><p>CPU por núcleo e clocks expostos pelo Windows, CPU total, RAM, disco, rede, processo do Fortnite, processos em background, GPU/VRAM/temperatura quando o hardware expõe esses sensores e frames via ETW quando o coletor está presente.</p></div>
    </article>
  </section>
  <section class="grid cols-4" style="margin-top:14px">${metric('FPS MÉDIO','FPS',fmt(frames.fps_avg,''),frames.available?'ETW / PresentMon':'Indisponível',null)}${metric('1% LOW','1%',fmt(frames.fps_1_low,''),frames.available?`${frames.frames||0} frames capturados`:'Indisponível',null)}${metric('FRAMETIME','ms',fmt(frames.frametime_avg_ms,' ms'),frames.available?`P99 ${fmt(frames.frametime_p99_ms,' ms')}`:'Indisponível',null)}${metric('STUTTERS','〽',frames.available?(frames.stutter_events??0):'—',frames.available?`Limiar ${fmt(frames.stutter_threshold_ms,' ms')}`:'Sem captura de frames',null)}</section>
  ${frametimePanel(frames)}
  ${renderGameComparison(d.last_report?.comparison||d.comparison)}
  <article class="card pad" style="margin-top:14px"><div class="device-head"><div><span class="eyebrow">RELATÓRIOS</span><h3 class="section-title">Pasta Relatorios</h3></div><button class="btn ghost" id="refreshGameReports">↻ ATUALIZAR LISTA</button></div><div class="path-box">${esc(d.reports_dir||'Relatorios')}</div><div class="restore-list" style="margin-top:12px">${reports.length?reports.map(r=>`<div class="restore-item card"><div><h4>${esc((r.customer||'Cliente')+' • '+String(r.label||'').toUpperCase())}</h4><p>${esc(r.started_at||'')} • ${r.samples??0} amostras</p></div><span class="pill ${r.label==='depois'?'goodpill':''}">${r.fps_avg!=null?`${r.fps_avg} FPS • 1% ${r.fps_1_low??'—'}`:'TELEMETRIA'}</span></div>`).join(''):'<div class="empty">Nenhum relatório de jogo salvo ainda.</div>'}</div></article>`;
}

function renderGameComparison(c){
  if(!c?.rows?.length)return '';
  const rows=c.rows.map(r=>{const ok=r.improved===true,bad=r.improved===false;const delta=r.delta==null?'—':`${r.delta>0?'+':''}${r.delta} ${r.unit||''}`;return `<div class="restore-item card"><div><h4>${esc(r.metric||'Métrica')}</h4><p>Antes: ${r.before??'—'} ${esc(r.unit||'')} • Depois: ${r.after??'—'} ${esc(r.unit||'')}</p></div><span class="pill ${ok?'goodpill':bad?'off':''}">${esc(delta)}</span></div>`}).join('');
  return `<article class="card pad" style="margin-top:14px"><div class="device-head"><div><span class="eyebrow">ANTES × DEPOIS</span><h3 class="section-title">Comparação automática</h3></div><span class="pill goodpill">MESMO CLIENTE</span></div><div class="restore-list" style="margin-top:12px">${rows}</div></article>`;
}

function metric(name,icon,value,detail,percent){return `<article class="card metric"><div class="metric-top"><span class="metric-name">${name}</span><span class="metric-icon">${icon}</span></div><div class="metric-value">${value}</div><div class="metric-detail">${detail}</div><div class="bar"><span style="width:${percent==null?0:clamp(percent,0,100)}%"></span></div></article>`}

function renderStutter(){
  const d=S.stutter||{};const fs=d.findings||[];const score=d.score??'—';
  const sevClass=s=>s==='critical'?'bad':s==='warn'?'warn':s==='good'?'good':'muted';
  const top=Array.isArray(d.top_processes)?d.top_processes:[];
  return `${head('Stutter Lab','Diagnóstico orientado a evidências para frametime irregular. O Azor procura sinais reais antes de recomendar mudanças.','<button class="btn ghost" id="runStutterDiag">↻ ANALISAR STUTTER</button>')}${guide('FPS médio não conta a história toda','Stutter costuma aparecer no frametime. Aqui o Azor procura pressão de RAM, paginação, pouco espaço, WHEA, timeouts de armazenamento e resets do driver de vídeo.',3,5)}
  <section class="grid cols-4"><article class="card metric"><div class="metric-top"><span class="metric-name">ESTABILIDADE</span><span class="metric-icon">〽</span></div><div class="metric-value">${score}<small>/100</small></div><div class="metric-detail">Score diagnóstico, não benchmark de FPS</div><div class="bar"><span style="width:${typeof score==='number'?clamp(score,0,100):0}%"></span></div></article>${metric('RAM','▤',fmt(d.ram_percent,'%'),`${fmt(d.ram_free_gb,' GB')} livres`,d.ram_percent)}${metric('DISCO','◫',fmt(d.disk_free_percent,'%'),'Espaço livre no volume do Windows',d.disk_free_percent==null?null:100-d.disk_free_percent)}${metric('WHEA 7 DIAS','! ',d.whea_7d??'—',d.whea_7d?'Investigar estabilidade antes de tweaks':'Nenhum evento selecionado',d.whea_7d?100:0)}</section>
  <section class="stutter-layout"><article class="card pad"><div class="device-head"><div><span class="eyebrow">ACHADOS</span><h3 class="section-title">${fs.length?fs.length+' verificações':'Execute a análise'}</h3></div><span class="pill ${d.ok?'goodpill':'off'}">${d.ok?'DIAGNÓSTICO CONCLUÍDO':'AGUARDANDO'}</span></div><div class="action-list compact">${fs.length?fs.map(x=>`<div class="analysis-row"><div><b class="${sevClass(x.severity)}">${esc(String(x.severity||'info').toUpperCase())}</b><small>${esc(x.text||'')}</small></div><span class="pill ${x.severity==='good'?'goodpill':x.severity==='critical'||x.severity==='warn'?'off':''}">${esc(x.code||'CHECK')}</span></div>`).join(''):'<div class="empty">Clique em “Analisar Stutter”. Nenhuma otimização é aplicada durante o diagnóstico.</div>'}</div></article>
  <article class="card pad"><span class="eyebrow">CORREÇÕES SEGURAS</span><h3 class="section-title">Aplicar somente o que pode ser verificado</h3><p class="section-sub">Game Mode, captura em background, perfil de energia quando apropriado, paginação automática se estiver desativada e limpeza conservadora de TEMP. Sem overclock e sem mexer em BIOS.</p><div class="preset-grid" style="margin-top:14px"><div class="preset"><strong>WHEA</strong><span>${d.whea_7d??'—'} em 7 dias</span></div><div class="preset"><strong>Armazenamento</strong><span>${d.storage_errors_7d??'—'} evento(s)</span></div><div class="preset"><strong>Driver de vídeo</strong><span>${d.display_resets_7d??'—'} reset(s)</span></div><div class="preset"><strong>Pagefile</strong><span>${d.automatic_pagefile===true?'Automático':d.automatic_pagefile===false?'Desativado/manual':'Indisponível'}</span></div></div><div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:14px"><button class="btn primary" id="applyStutterFix">APLICAR CORREÇÕES SEGURAS</button><button class="btn ghost" data-action="retrim_system">RETRIM DO SSD</button></div><p class="section-sub" style="margin-top:12px">Se houver WHEA ou reset de GPU, o Azor não tenta mascarar isso com tweaks: teste clocks stock, drivers e estabilidade do hardware.</p></article></section>
  <article class="card pad" style="margin-top:14px"><h3 class="section-title">Processos com maior uso de RAM</h3><div class="restore-list" style="margin-top:10px">${top.length?top.map(p=>`<div class="restore-item card"><div><h4>${esc(p.Name||'Processo')}</h4><p>PID ${esc(p.Id??'—')}</p></div><span class="pill">${esc(p.RAM_MB??'—')} MB</span></div>`).join(''):'<div class="empty">Dados aparecem após a análise.</div>'}</div></article>`
}

function renderDeclutter(){
 const choices=[
  ['widgets','Ocultar Widgets','Tira o botão de clima e notícias. Não desinstala Widgets nem garante encerrar seus processos.'],
  ['windows_suggestions','Reduzir sugestões promocionais','Desliga as preferências suportadas de sugestões do Windows.'],
  ['search_highlights_off','Pesquisa sem destaques','Retira conteúdo promocional da busca, preservando a pesquisa local.'],
  ['transparency','Desligar transparência','Deixa janelas e menus opacos. Não altera fontes nem seus arquivos.'],
  ['background_apps','Restringir apps compatíveis em segundo plano','Pode atrasar mensagens e atualizações de apps. Não fecha programas comuns nem antivírus.']
 ];
 const tasks=S.arsenal?.tasks||[];
 const rows=choices.map(([id,title,desc])=>{
  const t=tasks.find(x=>x.id===id);
  const can=t?.eligible&&t.can_apply!==false&&t.state!=='applied';
  const state=!t?'Ainda não verificado':t.state==='applied'?'Preferência confirmada':t.eligible?'Disponível para escolher':'Indisponível neste PC';
  return `<article class="card pad"><h3>${title}</h3><p class="section-sub">${desc}</p><p>${state}</p><div class="quick-buttons">${can?`<button class="btn primary" data-apply-tweak="${id}">APLICAR</button>`:''}${t?.state==='applied'&&t.can_revert?`<button class="btn ghost" data-revert="${id}">DESFAZER</button>`:''}</div></article>`;
 }).join('');
 return `${head('Windows mais limpo','Menos distrações, sem remover componentes essenciais. Cada escolha é independente.')}
 <div class="quick-buttons"><button class="btn ghost" id="refreshArsenal">VERIFICAR PREFERÊNCIAS</button><button class="btn ghost" data-go="restore">RESTAURAR ALTERAÇÕES</button></div>
 ${S.arsenal?.ok===false?'<p role="status">Não foi possível verificar. Tente novamente; nenhum sucesso foi presumido.</p>':''}
 <section class="grid cols-2">${rows}</section>
 <section class="grid cols-3" style="margin-top:14px">
 <article class="card pad"><h3>Sem animações</h3><p class="section-sub">Abra Efeitos visuais e desligue Efeitos de animação. A fonte continua legível. A escolha é feita no Windows.</p><button class="btn ghost" data-settings-page="animations">ABRIR EFEITOS VISUAIS</button></article>
 <article class="card pad"><h3>Menos notificações</h3><p class="section-sub">Escolha quais apps podem avisar ou use Não incomodar. Preserve alarmes e avisos importantes.</p><button class="btn ghost" data-settings-page="notifications">ESCOLHER NOTIFICAÇÕES</button></article>
 <article class="card pad"><h3>Liberar espaço</h3><p class="section-sub">Revise os arquivos temporários no Windows antes de excluir. Downloads, Lixeira e instalações anteriores podem conter arquivos necessários. Exclusão não tem restauração pelo AZOR.</p><button class="btn ghost" data-settings-page="storage">REVISAR ARMAZENAMENTO</button></article></section>
 <p class="section-sub">Abrir uma configuração não significa que ela foi aplicada. O AZOR não faz limpeza indiscriminada do Registro e não remove Defender, Windows Update ou drivers.</p>`;
}

function renderQuick(){
 const items=S.analysis?.items||[];
 const profiles=[['maximo','Máximo','Tudo que acelera, com desfazer'],['agressivo','Agressivo','Libera também os arriscados'],['auto','Automático','Escolhe pelo hardware'],['competitive','Jogar','Prioriza desempenho'],['ultra','Jogar + menos distrações','Inclui preferências visuais'],['safe','Essencial','Mudanças básicas'],['stream','Jogar e transmitir','Preserva captura'],['campanha','Jogar e gravar','Preserva captura']];
 return `${head('Otimizar seu PC','Escolha seu uso. O AZOR verifica compatibilidade, guarda o estado anterior e confere cada ajuste.')}
 <section class="card pad quick-flow"><h2 class="step-title"><span class="step-num">1</span>Como você usa o PC?</h2><div class="profile-switch quick-profile-grid" role="radiogroup" aria-label="Modo de otimização">${profiles.map(([id,title,desc])=>`<button class="profile-btn ${S.quickProfile===id?'active':''}" data-qprofile="${id}" role="radio" aria-checked="${S.quickProfile===id}"><span>${title}</span><small>${desc}</small></button>`).join('')}</div>
 <h2 class="step-title"><span class="step-num">2</span>Confira antes de aplicar</h2><p class="section-sub">Analisar não altera o Windows. O perfil escolhido mantém a mesma profundidade de otimização no modo simples e no avançado.</p><div class="quick-buttons"><button class="btn ghost" id="analyzeQuick">ANALISAR PC</button><button class="btn primary" id="runQuick" ${items.length?'':'disabled'}>APLICAR RECOMENDADAS</button><button class="btn ghost" data-go="restore">DESFAZER ALTERAÇÕES</button></div></section>
 ${quickResultSummary()}
 ${items.length?`<details class="card pad"><summary>Ver as ${items.length} verificações e seus motivos</summary><div class="action-list compact">${items.map(analysisRow).join('')}</div></details>`:'<p class="section-sub quick-wait">Aguardando análise. Nenhum ajuste aplicado nesta tela.</p>'}
 <section class="card pad quick-flow"><h2 class="step-title"><span class="step-num">3</span>Deixe o Windows do seu jeito</h2><p class="section-sub">Widgets, sugestões e aparência são escolhas separadas. Menos distrações não é uma promessa de mais FPS.</p><button class="btn primary" data-go="declutter">WINDOWS MAIS LIMPO</button></section>
 <details class="card pad"><summary>Mais opções e ferramentas avançadas</summary><div class="quick-buttons"><button class="btn ghost" id="simulateQuick">SIMULAR SEM ALTERAR</button><button class="btn ghost" data-go="arsenal">TODOS OS AJUSTES</button><button class="btn ghost" data-go="gameDiag">MEDIR DURANTE O JOGO</button><button class="btn ghost" data-go="device">PERIFÉRICOS</button></div></details>`;
}

// These two were referenced by the Windows / Guardian / Manutencao pages but
// never defined, so those three routes threw on render. Rebuilt here against the
// markup the existing .action-row / .status-card-v4 styles already expect.
function actionRow(title,desc,risk='BAIXO',action=''){
  const level=String(risk||'').toUpperCase();
  const cls=level.startsWith('BAIX')?'low':level.startsWith('M')?'mid':'';
  return `<div class="action-row card"><div><h3>${esc(title)} <span class="risk ${cls}">${esc(level)}</span></h3><p>${esc(desc)}</p></div><button class="btn primary" data-action="${esc(action)}">APLICAR</button></div>`;
}
function statusCard(title,ok,detail=''){
  return `<article class="card pad status-card-v4"><div class="device-head"><span class="metric-name">${esc(title)}</span><span class="pill ${ok?'goodpill':'off'}">${ok?'OK':'REVISAR'}</span></div><div class="hw-metric-value" style="font-size:15px;margin-top:10px">${esc(detail)}</div></article>`;
}

// Cada linha da analise carrega a mesma informacao que o motor declara: por que
// existe (fonte), o que custa (trade-off), que numero deveria mover (metrica) e
// se da para desfazer so ela. Um tweak sem essas quatro respostas nao entra.
function analysisRow(x){
  const status=String(x.status||'').replaceAll('_',' ').toUpperCase();
  const pill=x.status==='applied'?'goodpill':x.status==='recommended'?'':'off';
  const canRevert=!!x.can_revert&&x.status==='applied';
  const why=[
    x.trade_off?`<p><b>O que custa:</b> ${esc(x.trade_off)}</p>`:'',
    x.metric?`<p><b>Número que isso move:</b> ${esc(x.metric)}</p>`:'<p><b>Número que isso move:</b> nenhum. É preferência, não desempenho.</p>',
    x.source?`<p><b>Fonte:</b> ${esc(x.source)}</p>`:'',
    x.restart?'<p><b>Exige reiniciar</b> para valer por completo.</p>':'',
    x.reversible===false?'<p><b>Não é reversível.</b> Esta é a única ação da lista que não volta atrás.</p>':''
  ].join('');
  return `<div class="analysis-row"><div><b>${esc(x.name)} <span class="module-tag">${esc(x.module||'engine')}</span> <span class="risk ${x.risk==='low'?'low':'mid'}">${esc(String(x.risk_label||x.risk||'').toUpperCase())}</span></b><small>${esc(x.detail||'')}</small>${why?`<details class="tweak-why"><summary>ver detalhe técnico</summary><div class="tweak-why-body">${why}</div></details>`:''}</div><div class="analysis-row-actions"><span class="pill ${pill}">${esc(status)}</span>${canRevert?`<button class="btn small ghost" data-revert="${esc(x.id||'')}">DESFAZER</button>`:''}</div></div>`;
}

function quickStep(name,desc,status,cls=''){return `<article class="card quick-step ${cls}" data-step="${esc(name)}"><div class="step-state">${cls==='done'?'✓':cls==='fail'?'!':'•'}</div><div><h4>${name}</h4><p>${desc}</p></div><span class="state-label">${status}</span></article>`}

function renderAdvanced(){
 const rows=[
  ['Modo de Jogo','Ativa o Game Mode do Windows. Ajuste reversível pelo snapshot.','Baixo','low','game_mode_on'],
  ['Game DVR / captura','Desativa captura em segundo plano e App Capture.','Baixo','low','game_dvr_off'],
  ['Apps em segundo plano','Usa a configuração global suportada para reduzir execução em background.','Médio','mid','background_apps_off'],
  ['Efeitos visuais: desempenho','Reduz efeitos visuais do Windows para priorizar responsividade.','Médio','mid','visual_effects_perf'],
  ['AZOR FPS BOOST','Plano próprio baseado no Ultimate: prioridade máxima de desempenho nos índices AC expostos e verificação por GUID.','Médio','mid','power_azor'],
  ['Limpeza de temporários','Remove entradas antigas da pasta temporária do usuário.','Baixo','low','clean_temp'],
  ['Limpar cache DNS','Executa o flush DNS do Windows. Não promete reduzir ping por si só.','Baixo','low','flush_dns'],
 ];
 return `${head('Otimização Avançada','Ações individuais com explicação, risco e resultado. Use apenas o que você entende.')}${guide('Modo avançado','Cada botão executa uma ação específica. O Azor evita agrupar tweaks agressivos e mostra a resposta real do Windows.',2,4)}<article class="card pad"><span class="eyebrow">CAPACIDADES REAIS</span><h3 class="section-title">O que o Azor realmente consegue fazer</h3><div class="capability-grid"><div class="capability real"><b>✓ APLICA E VERIFICA</b><span>Game Mode, Game DVR, plano de energia, EPP do mouse, repeat do teclado, USB selective suspend quando solicitado, preferência de GPU e chaves suportadas do Fortnite.</span></div><div class="capability real"><b>✓ MEDE / RELÊ</b><span>Estado do Registro, GUID do plano, Timer Resolution reportado pelo Windows, arquivo GameUserSettings.ini, processos, RAM/CPU e sensores disponíveis.</span></div><div class="capability profile"><b>◐ SOMENTE PERFIL</b><span>DPI físico, polling/overclock de mouse/teclado/controle, deadzone de controle, Rapid Trigger, SOCD e RGB sem API oficial do fabricante.</span></div><div class="capability no"><b>× NÃO FAZ / NÃO PROMETE</b><span>Overclock de CPU/GPU, escrita automática de BIOS, XMP/EXPO, FPS garantido, ping mágico ou tweak que não consiga reler e confirmar.</span></div></div></article><div class="action-list" style="margin-top:14px">${rows.map(r=>`<article class="card action-row"><div><h3>${r[0]} <span class="risk ${r[3]}">${r[2]}</span></h3><p>${r[1]}</p></div><button class="btn ghost" data-action="${r[4]}">APLICAR</button></article>`).join('')}</div>`
}


function boolPill(v,on='ATIVO',off='INATIVO'){return `<span class="pill ${v?'':'off'}">${v?on:off}</span>`}
function renderGuardian(){const h=S.health||{};const a=S.summary?.agent||{};const gm=S.summary?.game_monitor||{};const islc=S.summary?.islc||{};return `${head('Azor Guardian','Guardian sob demanda, sem VBS, sem tarefa agendada e sem inicialização automática do Windows.','<button class="btn ghost" id="refreshHealth">↻ VERIFICAR AGORA</button>')}${guide('Versão limpa','O Guardian pode ser iniciado manualmente durante a sessão. Ao abrir o AZOR, resíduos de versões antigas como AzorGuardianWatchdog e AzorGuardian são removidos para impedir popups repetidos.',3,5)}<section class="grid cols-4">${statusCard('Guardian',!!a.running,a.running?'Executando nesta sessão':'Parado')}${statusCard('Persistência automática',true,'DESATIVADA')}${statusCard('Game Monitor',!!S.settings.game_monitor_enabled,gm.running?'Jogo detectado':'Aguardando jogo')}${statusCard('Memory Engine',true,islc.running?'Ativo':'Pronto')}</section><article class="card pad" style="margin-top:14px"><div class="device-head"><div><h3 class="section-title">Health Check</h3><p class="section-sub">${h.ok?'Verificações disponíveis concluídas.':(h.problems||[]).length+' aviso(s) encontrado(s).'}</p></div><span class="pill ${h.ok?'goodpill':'off'}">${h.ok?'VALIDADO':'REVISAR'}</span></div><div class="action-list">${(h.problems||[]).length?(h.problems||[]).map(x=>`<div class="action-row card"><div><h3>${esc(x)}</h3><p>O AZOR registra a falha e não cria mecanismos ocultos de recuperação automática.</p></div><span class="pill off">ATENÇÃO</span></div>`).join(''):'<div class="empty">Nenhum problema detectado pelo último Health Check.</div>'}</div><div style="display:flex;gap:8px;margin-top:12px"><button class="btn primary" data-action="guardian_repair">VERIFICAR E REPARAR AJUSTES</button><button class="btn ghost" data-action="start_agent">INICIAR GUARDIAN NESTA SESSÃO</button></div></article>`}
function renderMaintenance(){const m=S.maintenance||S.summary?.maintenance||{};const r=m.recoverable||{};return `${head('Azor Maintenance','Limpeza segura executada somente quando você pedir. A versão limpa não cria tarefas agendadas no Windows.')}${guide('Limpeza manual e segura','A rotina não toca em Downloads, saves, screenshots, drivers, shader cache de jogos ou arquivos desconhecidos do Windows. Ela remove apenas temporários antigos do usuário.',3,4)}<section class="grid cols-3">${statusCard('Automação',true,'DESATIVADA')}${statusCard('Recuperável',true,`${r.mb??0} MB em temporários antigos`)}${statusCard('Recuperado no mês',true,`${m.recovered_month_mb??0} MB`)}</section><article class="card pad" style="margin-top:14px"><div class="info-row"><span>Última manutenção</span><span>${esc(m.last_run||'Ainda não executada')}</span></div><div class="info-row"><span>Modo</span><span>Manual • TEMP com mais de 48 h</span></div><div class="info-row"><span>Proteção</span><span class="good">SEM DOWNLOADS / SAVES / DRIVERS</span></div><button class="btn primary" data-action="maintenance_now" style="margin-top:14px">EXECUTAR MANUTENÇÃO AGORA</button></article>`}
function renderWindows(){return `${head('Windows Optimization','Ajustes reais, reversíveis e verificados. O app usa o mesmo motor do AZOR Windows quando ele estiver instalado.')}${guide('Um único motor de otimização','Se C:\\AZOR estiver presente, estes botões chamam exatamente as rotinas do próprio AZOR Windows. Assim o app e o sistema não aplicam tweaks diferentes nem brigam entre si.',4,5)}<article class="card pad glow-purple" style="margin-bottom:14px"><span class="eyebrow">AZOR WINDOWS ENGINE</span><h3>Otimização do sistema integrada</h3><p class="section-sub">No AZOR Windows: rotina diária, preparação para jogo, armazenamento multi-SSD/HDD, hardware, verificação, manutenção profunda e restauração usam C:\\AZOR\AZOR-CLI.ps1. Em Windows comum, as otimizações nativas abaixo continuam funcionando.</p><div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:14px"><button class="btn primary" data-action="azor_windows_daily">OTIMIZAÇÃO DIÁRIA</button><button class="btn primary" data-action="azor_windows_gameprep">PREPARAR PARA JOGAR</button><button class="btn ghost" data-action="azor_windows_verify">VERIFICAR AZOR</button><button class="btn ghost" data-action="azor_windows_storage">ANALISAR DISCOS</button><button class="btn ghost" data-action="azor_windows_hardware">ATUALIZAR HARDWARE</button><button class="btn ghost" data-action="azor_windows_deep">MANUTENÇÃO PROFUNDA</button><button class="btn ghost" data-action="azor_windows_drivers">DRIVERS</button><button class="btn ghost" data-action="azor_windows_restore">RESTAURAR AZOR</button></div></article>${guide('Aplicação verificável','Game Mode, captura, plano de energia e preferências escolhidas são validadas no momento da aplicação. Recursos críticos do Windows ficam fora da automação agressiva.',3,5)}<article class="card pad" style="margin-bottom:14px"><span class="eyebrow">FERRAMENTAS EXTRAS</span><div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px"><button class="btn ghost" data-go="advanced">AJUSTES AVANÇADOS</button><button class="btn ghost" data-go="stutter">STUTTER LAB</button><button class="btn ghost" data-go="network">REDE / PING</button><button class="btn ghost" data-go="bios">BIOS ASSISTIDA</button><button class="btn ghost" data-go="maintenance">MANUTENÇÃO</button><button class="btn ghost" data-go="logs">LOGS</button></div></article><div class="action-list">${actionRow('Modo de Jogo','Ativa e lê novamente o estado antes de marcar como concluído.','BAIXO','game_mode_on')}${actionRow('Game DVR / captura','Desativa as preferências suportadas de captura em segundo plano e valida o registro.','BAIXO','game_dvr_off')}${actionRow('AZOR DESEMPENHO','Solicita o plano de desempenho próprio do AZOR e verifica os valores suportados. Não força a CPU a trabalhar em 100% continuamente; consumo e temperatura dependem da carga.','BAIXO','power_azor')}${actionRow('Sugestões promocionais','Desliga sugestões suportadas para o usuário atual.','BAIXO','windows_suggestions_off')}${actionRow('Transparência','Desliga transparência do Windows e valida a preferência.','BAIXO','transparency_off')}${actionRow('Widgets na barra','Oculta o botão de Widgets para o usuário atual.','BAIXO','widgets_off')}</div>`}
function renderFortnite(){const f=S.summary?.fortnite||{};const on=!!f.installed;return `${head('Fortnite Optimizer','Só altera o que o Azor consegue localizar, salvar, reler e confirmar. Nada de valor inventado.')}${guide('Fortnite real','Feche o Fortnite antes de alterar o GameUserSettings.ini. O Azor cria backup, grava e relê. Se a chave não existir ou o arquivo estiver somente leitura, ele para e mostra a falha.',3,5)}<section class="fort-layout"><article class="card fort-card glow-purple"><span class="eyebrow">STATUS DO JOGO</span><div class="status-line"><i class="status-dot" style="background:${on?'var(--green)':'var(--amber)'}"></i>${on?'Fortnite detectado':'Fortnite não detectado'}</div><p class="section-sub">Executável:</p><div class="path-box">${esc(f.exe||'Não encontrado')}</div><p class="section-sub" style="margin-top:10px">Configuração:</p><div class="path-box">${esc(f.config||'GameUserSettings.ini ainda não encontrado')}</div></article><article class="card fort-card"><h3 class="section-title">Otimizações verificáveis</h3><p class="section-sub">Essas ações retornam sucesso somente depois da releitura.</p><div class="preset-grid"><div class="preset"><strong>GPU: Alto desempenho</strong><span>Usa o caminho exato do FortniteClient-Win64-Shipping.exe, grava GpuPreference=2 e relê antes de confirmar.</span></div><div class="preset"><strong>Qualidade competitiva</strong><span>Reduz apenas chaves sg.* que já existem no arquivo.</span></div><div class="preset"><strong>Resolução 3D</strong><span>70%, 85% ou 100%; grava sg.ResolutionQuality e relê o valor.</span></div><div class="preset"><strong>Restore</strong><span>Backup antes das mudanças e restauração byte por byte.</span></div></div><div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:14px"><button class="btn primary" data-action="fortnite_gpu">GPU ALTO DESEMPENHO</button><button class="btn ghost" data-go="games">OUTRO JOGO</button><button class="btn ghost" data-action="fortnite_preset">QUALIDADE COMPETITIVA</button><button class="btn ghost" data-action="fortnite_res_70">3D 70%</button><button class="btn ghost" data-action="fortnite_res_85">3D 85%</button><button class="btn ghost" data-action="fortnite_res_100">3D 100%</button><button class="btn ghost" data-action="fortnite_restore">RESTAURAR CONFIG</button></div></article></section><article class="card pad" style="margin-top:14px"><span class="eyebrow">MODO DE RENDERIZAÇÃO</span><h3 class="section-title">Performance ou DirectX 12</h3><p class="section-sub">O Fortnite atual não oferece mais DirectX 11 no menu. Quando o modo não fica salvo, o método oficial é usar os argumentos adicionais da Epic Games. O Azor não edita uma configuração interna não documentada do Launcher: ele copia o argumento oficial pra você colar.</p><div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px"><button class="btn primary" data-copy="-d3d12 -FeatureLevelEs31">COPIAR PERFORMANCE</button><button class="btn ghost" data-copy="-d3d12 -sm6">COPIAR DX12</button><button class="btn ghost" data-copy="-d3d11">COPIAR DX11</button><button class="btn ghost" data-copy="-d3d11 -FeatureLevelEs31">COPIAR DX11 + PERFORMANCE</button></div><div class="capability-grid"><div class="capability real"><b>✓ SUPORTADO</b><span>Performance: -d3d12 -FeatureLevelEs31 • DX12: -d3d12 -sm6</span></div><div class="capability profile"><b>◐ DX11 — TENTE E CONFIRA</b><span>O argumento é <b>-d3d11</b> e continua sendo aceito pela linha de comando da Unreal. O que a Epic removeu foi a <i>opção no menu</i> do jogo, não o argumento — mas em versões recentes o Fortnite pode ignorá-lo e voltar para DX12 sozinho. Cole, entre no jogo e confira em Configurações &gt; Vídeo qual modo está ativo: se voltou para DX12, esta versão não aceita mais. O AZOR prefere te dar o argumento e o jeito de conferir a fingir que não existe.</span></div></div><div class="capability-grid" style="margin-top:10px"><div class="capability real"><b>ONDE COLAR</b><span>Epic Games Launcher &gt; Biblioteca &gt; ⋯ no Fortnite &gt; Gerenciar &gt; Argumentos de linha de comando adicionais. Cole, feche o launcher e abra o jogo de novo.</span></div></div></article>`}
function renderNetwork(){const adapters=S._network?.adapters||[];const p=S.lastPing;return `${head('Rede / Ping','Diagnóstico de rede e latência real. O Azor não promete “zerar ping” com DNS ou ajustes mágicos.')}${guide('Ping e DNS','Teste de ping mede o caminho atual até o host escolhido. Limpar DNS pode resolver cache de nomes, mas não reduz fisicamente a distância até o servidor.',2,4)}<section class="network-layout"><article class="card pad glow-blue"><span class="eyebrow">PING EM TEMPO REAL</span><div class="ping-value">${p?.avg_ms!=null?p.avg_ms:'—'} <small>ms</small></div><p class="section-sub">Destino padrão: 1.1.1.1 • mínimo ${p?.min_ms??'—'} ms • máximo ${p?.max_ms??'—'} ms</p><div style="display:flex;gap:8px;margin-top:14px"><button class="btn cyan" id="testPing">TESTAR PING</button><button class="btn ghost" data-action="flush_dns">FLUSH DNS</button></div></article><article class="card pad"><h3 class="section-title">Adaptadores</h3><p class="section-sub">Dados reportados pelo Windows.</p><div class="adapter-list">${adapters.length?adapters.map(a=>`<div class="adapter"><b>${esc(a.InterfaceAlias||'Adaptador')}</b><span>IPv4: ${esc(a.IPv4||'—')}<br>Gateway: ${esc(a.Gateway||'—')}<br>DNS: ${esc(a.DNS||'—')}</span></div>`).join(''):'<div class="empty">Clique em atualizar ou aguarde a leitura.</div>'}</div></article></section>`}

function latencyReadiness(){
  const sm=S.summary||{}, timer=sm.timer||{}, islc=sm.islc||{};
  const checks=[
    {name:'Timer de baixa latência',supported:true,ok:!!timer.active},
    {name:'Game Mode',supported:true,ok:!!sm.game_mode_verified},
    {name:'Captura em background',supported:true,ok:!!sm.game_dvr_off_verified},
    {name:'AZOR Memory Engine',supported:true,ok:!!islc.running},
  ];
  const eligible=checks.filter(x=>x.supported);const done=eligible.filter(x=>x.ok).length;
  return {score:eligible.length?Math.round(done/eligible.length*100):0,checks};
}
function deltaMetric(before,after,key){
  const a=Number(before?.[key]),b=Number(after?.[key]);if(!Number.isFinite(a)||!Number.isFinite(b))return null;
  const diff=b-a;const pct=a!==0?(diff/a)*100:null;return {diff,pct,better:diff<0};
}
function latencyConfidence(){
  if(!S.latencyBaseline)return null;
  const vals=[S.latencyBaseline.stability_pct,S.latencyAfter?.stability_pct].filter(Number.isFinite);
  if(!vals.length)return null;return Math.round(Math.min(...vals));
}
function confidenceLabel(v){return v==null?'Aguardando':v>=90?'Excelente':v>=75?'Boa':v>=55?'Moderada':'Baixa'}

function comparisonMetric(label,key,suffix='ms'){
  const b=S.latencyBaseline,a=S.latencyAfter,d=deltaMetric(b,a,key);
  const bv=b?Number(b[key]).toFixed(3):'—',av=a?Number(a[key]).toFixed(3):'—';
  const trend=d==null?'AGUARDANDO':Math.abs(d.diff)<0.0005?'SEM MUDANÇA':d.better?'MELHOROU':'PIOROU';
  return `<div class="compare-metric"><span>${label}</span><div><b>${bv} ${suffix}</b><i>→</i><strong>${av} ${suffix}</strong></div><small class="${d?.better?'good':d&&d.diff>0?'warn':'muted'}">${trend}${d?.pct!=null?` • ${Math.abs(d.pct).toFixed(1)}%`:''}</small></div>`;
}

function median(values){
  const a=values.map(Number).filter(Number.isFinite).sort((x,y)=>x-y);if(!a.length)return null;
  const m=Math.floor(a.length/2);return a.length%2?a[m]:(a[m-1]+a[m])/2;
}
function aggregateLatencyRuns(runs){
  const keys=['avg_ms','min_ms','max_ms','p95_ms','jitter_ms','avg_overshoot_ms'];
  const last=runs[runs.length-1]||{};const out={...last,passes:runs.length,iterations:runs.reduce((n,x)=>n+Number(x.iterations||0),0)};
  keys.forEach(k=>{const v=median(runs.map(x=>x[k]));if(v!=null)out[k]=Number(v.toFixed(4))});
  const avgs=runs.map(x=>Number(x.avg_ms)).filter(Number.isFinite);const center=median(avgs);
  const spread=center&&avgs.length>1?((Math.max(...avgs)-Math.min(...avgs))/center)*100:0;
  out.run_spread_pct=Number(spread.toFixed(2));out.stability_pct=Math.round(clamp(100-spread*7,0,100));
  out.samples=runs.flatMap(x=>Array.isArray(x.samples)?x.samples:[]).slice(-160);
  return out;
}
function latencyComposite(){
  if(!S.latencyBaseline||!S.latencyAfter)return null;
  const parts=[['avg_ms',.35],['p95_ms',.35],['jitter_ms',.20],['avg_overshoot_ms',.10]];
  let total=0,weight=0;
  for(const [key,w] of parts){const d=deltaMetric(S.latencyBaseline,S.latencyAfter,key);if(!d||d.pct==null)continue;total+=(-d.pct)*w;weight+=w}
  if(!weight)return null;return clamp(total/weight,-99,99);
}
function latencyResultBanner(){
  const score=latencyComposite();if(score==null)return '';
  const cls=score>0.5?'good':score<-0.5?'warn':'muted';const word=score>0.5?'MELHOROU':score<-0.5?'PIOROU':'ESTÁVEL';
  return `<div class="latency-result-banner ${cls}"><div><span>RESULTADO COMBINADO DAS MÉTRICAS</span><strong>${word} ${Math.abs(score).toFixed(1)}%</strong></div><p>Índice calculado apenas com Média, P95, Jitter e Overshoot medidos. Não é FPS e não é input lag direto.</p></div>`;
}
function renderLatency(){
  const islc=S.summary?.islc||{},timer=S.summary?.timer||{},ready=latencyReadiness(),power=S.summary?.azor_power||{},confidence=latencyConfidence();
  const current=timer.actual_ms==null?'Indisponível':`${Number(timer.actual_ms).toFixed(Number(timer.actual_ms)<1?3:2)} ms`;
  const baselineInfo=S.latencyBaseline?`${S.latencyBaseline.passes||1} rodadas • ${S.latencyBaseline.iterations||0} amostras`:'Aguardando primeira medição';
  const afterInfo=S.latencyAfter?`${S.latencyAfter.passes||1} rodadas • ${S.latencyAfter.iterations||0} amostras`:'Aguardando otimização';
  return `${head('Latência & Memória','Timer Resolution, AZOR Memory Engine e Measure Sleep em um fluxo único, sem programa externo.')}
  ${guide('Comparação mais confiável','O AZOR aquece o teste, executa 5 rodadas antes e 5 depois e usa a mediana. Também mostra a consistência entre as rodadas para você saber quando o resultado está ruidoso.',4,5)}
  <section class="grid cols-4 latency-top-grid">
    <article class="card pad glow-purple"><span class="eyebrow">TIMER ATUAL</span><h2 class="latency-kpi">${current}</h2><p class="section-sub">${timer.active?'Solicitação ativa e relida no Windows.':'Timer padrão do sistema.'}</p></article>
    <article class="card pad"><span class="eyebrow">AZOR MEMORY ENGINE</span><h2 class="latency-kpi small">${islc.running?'Ativo':'Pronto'}</h2><p class="section-sub">Interno • ${fmt(islc.available_mb,' MB livres')} • limite ${fmt(islc.threshold_mb,' MB')}</p></article>
    <article class="card pad"><span class="eyebrow">PREPARAÇÃO</span><h2 class="latency-kpi">${ready.score}%</h2><div class="progress-track"><i style="width:${ready.score}%"></i></div><p class="section-sub">Itens suportados e verificados. Não é ganho de FPS.</p></article>
    <article class="card pad ${confidence!=null&&confidence>=75?'glow-green':''}"><span class="eyebrow">CONFIABILIDADE DO TESTE</span><h2 class="latency-kpi ${confidence!=null&&confidence<55?'warn':''}">${confidence==null?'—':confidence+'%'}</h2><p class="section-sub">${confidenceLabel(confidence)} • mede consistência entre rodadas, não desempenho.</p></article>
  </section>
  <section class="latency-layout" style="margin-top:14px">
    <article class="card lat-card glow-blue"><span class="eyebrow">MEDIÇÃO ANTES / DEPOIS</span><h3 class="section-title">Mesma rotina, repetida dos dois lados</h3>
      <div class="measure-meta"><span><b>ANTES</b>${baselineInfo}</span><span><b>DEPOIS</b>${afterInfo}</span></div>
      <div class="compare-grid">${comparisonMetric('Média','avg_ms')}${comparisonMetric('P95','p95_ms')}${comparisonMetric('Jitter','jitter_ms')}${comparisonMetric('Overshoot','avg_overshoot_ms')}</div>
      ${latencyResultBanner()}
      <div class="latency-progress">${S.latencyProgress?`<span class="pulse-dot"></span><b>${esc(S.latencyProgress)}</b>`:'<span class="idle-dot"></span><b>Pronto para medir</b>'}</div>
      <div class="latency-actions"><button class="btn ghost" id="latencyBaseline" ${S.latencyOptimizing?'disabled':''}>1. MEDIR AGORA</button><button class="btn primary" id="latencyOptimize" ${S.latencyOptimizing?'disabled':''}>2. OTIMIZAR E MEDIR DEPOIS</button><button class="btn ghost" id="latencyReset" ${S.latencyOptimizing?'disabled':''}>LIMPAR</button></div>
      <div class="explain-box"><h4>O que esse teste significa</h4><p>Measure Sleep avalia a precisão e a variação do agendamento de sleep do Windows. Ele ajuda a comparar a temporização do sistema, mas não representa input lag direto do mouse, teclado ou controle.</p></div>
    </article>
    <article class="card lat-card"><span class="eyebrow">LATENCY ENGINE</span><div class="big-state"><div class="state-orb">${timer.active?'ON':'OFF'}</div><div><h4>${timer.active?'Ativo e consultado':'Pronto para ativar'}</h4><p>${timer.mode?esc(timer.mode):'NtSetTimerResolution com consulta posterior.'}</p></div></div>
      <div class="info-row"><span>Alvo solicitado</span><span>${Number(timer.requested_ms??0.5).toFixed(1)} ms</span></div><div class="info-row"><span>Resolução consultada</span><span class="${timer.active?'good':'muted'}">${current}</span></div>
      ${timer.active&&timer.global&&!timer.global.reaches_the_game
        ? '<p class="timer-scope-warn">⚠ <b>O timer está ativo, mas não alcança o jogo.</b> '+esc(timer.global.detail)+'</p>'
        : ''}
      <div class="latency-status-grid"><span class="${timer.active&&timer.global&&timer.global.reaches_the_game?'verified':''}"><b>${timer.active&&timer.global&&timer.global.reaches_the_game?'✓':'—'}</b>Timer</span><span class="${power.active?'verified':''}"><b>${power.active?'✓':'—'}</b>FPS BOOST</span><span class="${islc.running?'verified':''}"><b>${islc.running?'✓':'—'}</b>MEMÓRIA</span></div>
      <div class="latency-actions compact"><button class="btn primary" data-action="timer_half">0,5 MS</button><button class="btn ghost" data-action="timer_one">1,0 MS</button><button class="btn ghost" data-action="timer_off">PADRÃO</button></div>
      <div class="path-box" style="margin-top:14px">AZOR Memory Engine • interno ao aplicativo • ${islc.cycles||0} limpeza(s) • última ${esc(islc.last_cleanup||'ainda não necessária')}</div><div class="latency-actions compact" style="margin-top:10px"><button class="btn primary" data-action="launch_islc">${islc.running?'ENGINE ATIVO':'ATIVAR ENGINE'}</button><button class="btn ghost" data-action="islc_stop">PARAR</button></div><p class="section-sub" style="margin-top:8px">O motor age sozinho e apenas sob pressão de memória, com intervalo mínimo de 20 s. Não existe botão de limpeza manual: purgar a standby list sem pressão descarta cache útil e piora o carregamento — é o comportamento de "limpador de RAM" que o AZOR não faz.</p>
      <div class="latency-note"><b>Sem placebo nos números.</b><span>O painel só marca melhora quando a segunda medição realmente retorna menor.</span></div>
    </article>
  </section>`;
}

function renderISLC(){return renderLatency()}
function renderMeasure(){return renderLatency()}
function miniRes(n,v,s){return `<div class="mini-result"><span>${n}</span><b>${v}${s}</b></div>`}


function renderGames(){
  const games=S.gamesGpu||[];
  const selected=S.selectedGameExe||'';
  const rows=games.length?games.map(g=>`<div class="game-pref-row"><div class="game-pref-icon">▰</div><div class="game-pref-main"><b>${esc(g.name||'Jogo')}</b><small title="${esc(g.exe||'')}">${esc(g.exe||'')}</small></div><span class="pill ${g.high_performance?'goodpill':'off'}">${g.high_performance?'ALTO DESEMPENHO':'PADRÃO'}</span><button class="btn ghost small" data-game-apply="${encodeURIComponent(g.exe||'')}">APLICAR</button><button class="btn ghost small" data-game-restore="${encodeURIComponent(g.exe||'')}">RESTAURAR</button></div>`).join(''):'<div class="empty">Nenhum outro jogo foi configurado pelo AZOR ainda.</div>';
  return `${head('Alto Desempenho por Jogo','Escolha o executável real de qualquer jogo e o AZOR define a preferência gráfica do Windows como Alto desempenho. O sucesso só aparece depois da releitura do Registro.')}
  ${guide('Selecione o executável certo','Escolha o .exe que realmente executa o jogo, não apenas o launcher. Ex.: o executável do jogo dentro da pasta Binaries/Win64. O AZOR valida o arquivo antes de aplicar.',2,4)}
  <section class="card pad game-picker-card"><div class="device-head"><div><span class="eyebrow">NOVO JOGO</span><h3 class="section-title">Selecionar executável</h3></div><span class="pill">WINDOWS GRAPHICS</span></div>
  <p class="section-sub">Isso equivale a Configurações → Sistema → Tela → Gráficos → Opções → Alto desempenho, mas com verificação automática.</p>
  <div class="game-pick-line"><input id="gameExePath" class="path-input" spellcheck="false" placeholder="C:\\Caminho\\Do\\Jogo\\Game.exe" value="${esc(selected)}"><button class="btn ghost" id="pickGameExe">ESCOLHER .EXE</button><button class="btn primary" id="applyGameGpu">DEFINIR ALTO DESEMPENHO</button></div>
  <div class="capability-grid"><div class="capability real"><b>✓ VERIFICAÇÃO REAL</b><span>O AZOR grava GpuPreference=2 para o caminho exato e relê a mesma entrada antes de confirmar.</span></div><div class="capability profile"><b>◐ IMPORTANTE</b><span>Em PCs com uma única GPU, a preferência pode não alterar FPS; em notebooks/iGPU+dGPU ela é especialmente útil.</span></div></div></section>
  <article class="card pad" style="margin-top:14px"><div class="device-head"><div><span class="eyebrow">JOGOS CONFIGURADOS</span><h3 class="section-title">Preferências verificadas</h3></div><button class="btn ghost" id="refreshGamesGpu">↻ ATUALIZAR</button></div><div class="game-pref-list">${rows}</div></article>`;
}

function renderRestore(){
  const rp=S.restorePoints;const has=S.summary?.restore_available;
  const snaps=rp?.snapshots||[];const baseline=snaps.find(s=>s.kind==='baseline');
  const batches=snaps.filter(s=>s.kind==='batch');
  const prot=rp?.windows_protection||{};
  const revertible=rp?.revertible||[];
  const baselineCard=`<article class="card pad ${baseline?'glow-green':''}"><span class="eyebrow">BASELINE</span><h2 style="font-size:22px;margin:8px 0">${baseline?'Capturado':'Ainda não capturado'}</h2><p class="section-sub">${baseline?`Como este PC estava antes do AZOR tocar em qualquer coisa, em ${esc(baseline.created_at||'data desconhecida')}. ${baseline.registry_keys||0} valores registrados.${baseline.derived_from?' Derivado de '+esc(baseline.derived_from)+', então pode já conter ajustes de uma versão anterior.':''}`:'Ele é escrito uma única vez, na primeira captura, e nunca mais é sobrescrito. É a única cópia do estado anterior ao AZOR.'}</p><button class="btn green" data-action="snapshot" style="margin-top:14px">CRIAR / ATUALIZAR SNAPSHOT</button></article>`;
  const restoreCard=`<article class="card pad"><span class="eyebrow">RESTAURAÇÃO</span><h2 style="font-size:22px;margin:8px 0">Voltar ao estado anterior ao AZOR</h2><p class="section-sub">Restaura o que está no baseline: registro rastreado, plano de energia, paginação, USB selective suspend e preferência de GPU. Não é um ponto de restauração do Windows — esse é o botão ao lado.</p><button class="btn danger" id="restoreAll" style="margin-top:14px" ${has||baseline?'':'disabled'}>RESTAURAR TUDO AO BASELINE</button></article>`;
  const winCard=`<article class="card pad"><span class="eyebrow">PONTO DE RESTAURAÇÃO DO WINDOWS</span><h2 style="font-size:22px;margin:8px 0">${prot.restore_points==null?'Estado não confirmado':prot.restore_points+' ponto(s) existente(s)'}</h2><p class="section-sub">Isto é o recurso do próprio Windows, separado do snapshot do AZOR. Ele exige Proteção do Sistema ligada e administrador, e o Windows normalmente ignora um segundo ponto criado no mesmo dia.${prot.last_point?' Último ponto: '+esc(String(prot.last_point))+'.':''}</p><button class="btn ghost" data-action="windows_restore_point" style="margin-top:14px">CRIAR PONTO DE RESTAURAÇÃO DO WINDOWS</button></article>`;
  const revertList=revertible.length?`<section class="card pad" style="margin-top:14px"><h3 class="section-title">Desfazer item por item</h3><p class="section-sub">Cada tweak volta sozinho ao valor do baseline, sem desfazer os outros. O que não pode ser desfeito aparece dizendo por quê.</p><div class="restore-list" style="margin-top:10px">${revertible.map(t=>`<div class="restore-item card"><div><h4>${esc(t.name)}</h4><p>${esc(t.can_revert?('Volta ao valor registrado no baseline. Módulo: '+(t.module||'engine')):(t.trade_off||'Sem reversão individual.'))}</p></div>${t.can_revert?`<button class="btn small ghost" data-revert="${esc(t.id)}">DESFAZER</button>`:'<span class="pill off">SEM VOLTA</span>'}</div>`).join('')}</div></section>`:'';
  const history=batches.length?`<section class="card pad" style="margin-top:14px"><h3 class="section-title">Histórico de snapshots por lote</h3><p class="section-sub">Um arquivo por execução, para que um segundo lote nunca apague o registro do primeiro.</p><div class="restore-list" style="margin-top:10px">${batches.slice(0,10).map(s=>`<div class="restore-item card"><div><h4>${esc(s.created_at||'sem data')}</h4><p>${s.registry_keys||0} valores de registro capturados.</p></div><span class="pill">ARQUIVADO</span></div>`).join('')}</div></section>`:'';
  return `${head('Restaurar alterações','Veja o que foi alterado e volte ao estado salvo antes de cada ajuste.')}${recoveryHistoryHtml()}`+`
  <article class="card pad keep-card"><div class="device-head"><div><span class="eyebrow">AJUSTES MANTIDOS</span><h3 class="section-title">Conferência dos ajustes</h3><p class="section-sub">A abertura do app apenas confere os ajustes. Para reaplicar uma configuração, use uma ação explícita. Desfazer remove o ajuste da lista de preferências mantidas.</p></div><span class="pill goodpill">${(S.startup?.reconcile?.checked ?? '—')} MONITORADOS</span></div><button class="btn ghost" data-action="reconcile_now" style="margin-top:12px">RECONFERIR AGORA</button></article>${guide('O que volta atrás','O AZOR desfaz o que ele mesmo escreveu e releu. Ele não promete restaurar o Windows inteiro, e por isso oferece o ponto de restauração nativo como camada separada.',2,4)}<section class="grid cols-3">${baselineCard}${restoreCard}${winCard}</section>${revertList}${history}`;
}

function renderLogs(){return `${head('Logs & Histórico','Ações executadas pelo engine, com horário e detalhes. Útil para suporte e diagnóstico.','<button class="btn primary" data-action="export_report">EXPORTAR RELATÓRIO</button><button class="btn ghost" id="refreshLogs">↻ ATUALIZAR</button>')}<pre class="logs" id="logText">Carregando histórico…</pre>`}

function renderSettings(){const st=S.settings||{};const interval=st.monitor_interval||1.5;const auto=S.autostart;const last=auto&&auto.last_run;
const autoState=!auto?'Consultando a tarefa do Windows…':auto.stale?auto.detail:auto.enabled
  ?`Ativo: reaplica o modo ${(PERFORMANCE_MODES[auto.profile]||PERFORMANCE_MODES.maximo).label} ao entrar no Windows, também na bateria.`
  :(auto.detail||'Desligado. O BOOST nos modos Máximo e Agressivo liga sozinho.');
return `${head('Configurações','Preferências do aplicativo. Mudar a aparência não aplica ajustes no Windows.')}<section class="settings-grid">
<article class="card setting-card"><h3>Desempenho automático</h3><p class="section-sub">O Windows desfaz ajustes em atualizações. Com isto ligado, o AZOR recoloca tudo sozinho quando você entra.</p><div class="switch-list"><div class="switch-row"><span>Manter no máximo ao entrar no Windows</span><button type="button" class="toggle ${auto&&auto.enabled?'on':''}" id="logonAutoToggle" role="switch" aria-checked="${!!(auto&&auto.enabled)}" aria-label="Manter no máximo ao entrar no Windows" ${auto?'':'disabled'}></button></div></div><p class="section-sub setting-note">${esc(autoState)}${last&&last.time?` Última execução: ${esc(new Date(last.time*1000).toLocaleString('pt-BR'))} — ${esc(last.detail||last.outcome||'')}`:''} Ligar ou desligar pede autorização de administrador.</p></article>
<article class="card setting-card"><h3>Aparência e leitura</h3><p class="section-sub">Quanto detalhe técnico o AZOR mostra em cada tela.</p><label class="field-label" for="modeSelect">Modo de exibição</label><select class="select" id="modeSelect">${['Simple','Expert','Guided'].map((v,i)=>`<option value="${v}" ${st.mode===v?'selected':''}>${['Simples','Avançado','Guiado'][i]}</option>`).join('')}</select><div class="switch-list">${toggleSetting('Mostrar dicas','tipsToggle',st.show_tips!==false)}${toggleSetting('Animações','animToggle',st.animations!==false)}${toggleSetting('Iniciar na bandeja','startMinimizedToggle',st.start_minimized===true)}</div><p class="section-sub setting-note">O AZOR não aplica otimizações ao abrir. O modo de jogo é iniciado explicitamente na sua própria tela.</p></article>
<article class="card setting-card"><h3>Identidade AZOR</h3><p class="section-sub">Preto e rosa neon, consistentes em todas as telas.</p><span class="field-label">Cor de destaque</span><div class="color-row">${['#ff2fc8','#ef2bd4','#b13cff'].map(c=>`<button type="button" class="color-dot ${st.accent===c?'selected':''}" aria-label="Usar cor ${c}" aria-pressed="${st.accent===c}" style="background:${c}" data-color="${c}"></button>`).join('')}<button type="button" class="btn ghost small" id="resetIdentity">RESTAURAR MAGENTA ORIGINAL</button></div><label class="field-label" for="monitorRange">Atualização do monitor <b id="monitorV">${interval}s</b></label><input id="monitorRange" class="range" type="range" min="1" max="5" step="0.5" value="${interval}"><p class="section-sub">Frequência com que Início, Monitoramento e Latência pedem novas leituras.</p></article>
<article class="card setting-card"><h3>Controles do PC</h3><p class="section-sub">Energia, serviços e modo de jogo têm ações separadas, com estado e restauração visíveis.</p><div class="setting-actions"><button class="btn ghost" data-go="energy">ENERGIA</button><button class="btn ghost" data-go="gameMode">MODO DE JOGO</button><button class="btn ghost" data-go="restore">RESTAURAÇÃO</button></div></article></section>
<div class="autosave-row"><span>Preferências salvas automaticamente. Validar faz somente uma leitura do plano de energia.</span><span id="autoSaveMark" class="autosave-mark"></span><button class="btn primary" id="saveSettings">VALIDAR LEITURA</button></div>`}

function toggleSetting(label,id,on){return `<div class="switch-row"><span>${label}</span><button type="button" class="toggle ${on?'on':''}" id="${id}" role="switch" aria-checked="${on}" aria-label="${esc(label)}"></button></div>`}


// ==================== HARDWARE COMMAND CENTER ====================
// One page for what the machine actually is and how it is behaving. Every number
// here comes from a Windows read; anything Windows will not answer is shown as
// "indisponivel" rather than filled in with an estimate.

function hwSkeleton(lines=3){return `<div class="skeleton-stack">${Array.from({length:lines},(_,i)=>`<span class="skeleton ${i?'line-sm':'line-lg'}"></span>`).join('')}</div>`}

function hwMetric(label,value,detail,tone=''){
  return `<article class="card pad hw-metric ${tone}"><span class="metric-name">${label}</span><div class="hw-metric-value">${value}</div><p class="section-sub">${detail}</p></article>`;
}

function tempTone(v,warn,bad){return v==null?'':v>=bad?'bad':v>=warn?'warn':'good'}

function hardwareVitals(){
  const h=S.hardware||{};const mon=h.monitor||{};const th=S.thermal||{};
  // While the first read is still in flight, show skeletons. "Indisponivel"
  // means Windows answered and had nothing - it must not double as "loading".
  if(!h.monitor) return `<section class="grid cols-4">${Array.from({length:8},()=>`<article class="card pad hw-metric">${hwSkeleton(2)}</article>`).join('')}</section>`;
  const cpu=mon.cpu||{},gpu=mon.gpu||{},ram=mon.ram||{},disk=mon.disk||{};
  const cpuTemp=cpu.temp_c??th.cpu_temp_c;
  const gpuTemp=gpu.temp_c??th.gpu_temp_c;
  return `<section class="grid cols-4 stagger">
    ${hwMetric('CPU',fmt(cpu.usage,'%'),`${esc(h.profile?.cpu||'Processador')} • ${h.profile?.logical_processors??'—'} threads`)}
    ${hwMetric('GPU',gpu.available?fmt(gpu.usage,'%'):'—',gpu.available?`${esc(gpu.name||'')} • ${fmt(gpu.vram_used_mb,' MB')} de ${fmt(gpu.vram_total_mb,' MB')}`:'Sem leitura de GPU por nvidia-smi neste PC.')}
    ${hwMetric('RAM',fmt(ram.percent,'%'),`${fmt(ram.used_gb,' GB')} em uso de ${fmt(ram.total_gb,' GB')}`)}
    ${hwMetric('Disco do Windows',fmt(disk.percent,'%'),`${fmt(disk.used_gb,' GB')} usados de ${fmt(disk.total_gb,' GB')}`)}
    ${hwMetric('Temperatura da CPU',cpuTemp!=null?`${Math.round(cpuTemp)}°`:'Sem sensor',cpuTemp!=null?esc(th.cpu_temp_source||'sensor disponível'):'Sem API oficial no Windows. Abra o LibreHardwareMonitor para ter esse dado.',tempTone(cpuTemp,85,95))}
    ${hwMetric('Temperatura da GPU',gpuTemp!=null?`${Math.round(gpuTemp)}°`:'Sem sensor',gpuTemp!=null?'Reportada pelo driver da GPU.':'A GPU não expôs temperatura.',tempTone(gpuTemp,78,85))}
    ${hwMetric('Clock da CPU',th.cpu_clock_mhz?`${Math.round(th.cpu_clock_mhz)}`:'—',th.cpu_max_clock_mhz?`de ${Math.round(th.cpu_max_clock_mhz)} MHz nominais`:'MHz reportados pelo Windows')}
    ${hwMetric('Redução de clock',(th.throttle?.reasons||[]).length?'Ativa':(th.throttle?.available?'Nenhuma':'—'),(th.throttle?.reasons||[]).length?esc(th.throttle.reasons.join(' • ')):(th.throttle?.available?'O driver não reporta corte por calor ou energia agora.':'Só GPUs NVIDIA expõem esse dado por aqui.'),(th.throttle?.reasons||[]).length?'bad':'')}
  </section>`;
}

function storagePanel(){
  const st=(S.hardware||{}).storage;
  if(!st) return `<article class="card pad">${hwSkeleton(4)}</article>`;
  if(!st.supported) return `<article class="card pad"><h3 class="section-title">Armazenamento</h3><p class="section-sub">${esc(st.reason||'Leitura indisponível neste sistema.')}</p></article>`;
  const disks=(st.disks||[]).map(d=>{
    const media=String(d.Media||'').toUpperCase();
    const healthy=String(d.Health||'').toLowerCase()==='healthy';
    const cells=[
      ['Interface',`${esc(d.Bus||'—')} • ${esc(media||'—')}`],
      ['Capacidade',fmt(d.SizeGB,' GB')],
      ['Desgaste',d.Wear!=null?`${d.Wear}%`:'Não reportado'],
      ['Temperatura',d.TempC!=null?`${d.TempC} °C`:'Não reportada'],
      ['Horas ligado',d.PowerOnHours!=null?`${d.PowerOnHours} h`:'Não reportado'],
    ];
    return `<div class="hw-disk card"><div class="device-head"><div><h4>${esc(d.Name||'Disco')}</h4><p class="section-sub">${esc(d.Operational||'')}</p></div><span class="pill ${healthy?'goodpill':'off'}">${esc(String(d.Health||'—').toUpperCase())}</span></div>
      <div class="hw-disk-grid">${cells.map(([k,v])=>`<span><small>${k}</small><b>${v}</b></span>`).join('')}</div></div>`;
  }).join('')||'<div class="empty">Nenhum disco físico retornado pelo Windows.</div>';
  const vols=(st.volumes||[]).map(v=>{
    const pct=v.SizeGB>0?Math.round((1-(v.FreeGB/v.SizeGB))*100):0;
    return `<div class="hw-vol"><div class="hw-vol-head"><b>${esc(v.Letter||'?')}: ${esc(v.Label||'')}</b><span>${fmt(v.FreeGB,' GB')} livres de ${fmt(v.SizeGB,' GB')}</span></div><div class="bar"><span style="width:${pct}%"></span></div></div>`;
  }).join('');
  const trim=st.trim||{};
  const trimPill=trim.ntfs===true?'goodpill':trim.ntfs===false?'off':'off';
  return `<article class="card pad">
    <div class="device-head"><div><span class="eyebrow">ARMAZENAMENTO</span><h3 class="section-title">Saúde dos discos e espaço livre</h3></div>
    <span class="pill ${trimPill}">TRIM: ${trim.ntfs===true?'ATIVO':trim.ntfs===false?'DESLIGADO':'DESCONHECIDO'}</span></div>
    <div class="hw-disk-list">${disks}</div>
    <div class="hw-vol-list">${vols}</div>
    ${(st.findings||[]).length?`<div class="action-list compact" style="margin-top:12px">${st.findings.map(f=>`<div class="analysis-row"><div><b class="${f.level==='bad'?'bad':'warn'}">${esc(f.text)}</b></div></div>`).join('')}</div>`:'<div class="explain-box" style="margin-top:12px"><h4>Nenhum alerta de armazenamento</h4><p>Nenhum disco reportou estado ruim, desgaste alto ou pouco espaço livre nesta leitura.</p></div>'}
    <div class="explain-box"><h4>De onde vem esse dado</h4><p>${esc(st.smart_note||'')}</p></div>
    <div class="action-row card" style="margin-top:12px"><div><h3>ReTrim do volume do Windows</h3><p>Pede ao Windows que reenvie as marcações de TRIM ao SSD. Não apaga arquivo nenhum e não mexe em jogos.</p></div><button class="btn ghost" data-action="retrim_system">EXECUTAR RETRIM</button></div>
  </article>`;
}

function driversPanel(){
  const dv=(S.hardware||{}).drivers;
  if(!dv) return `<article class="card pad">${hwSkeleton(3)}</article>`;
  if(!dv.supported) return `<article class="card pad"><h3 class="section-title">Drivers</h3><p class="section-sub">${esc(dv.reason||'Leitura indisponível.')}</p></article>`;
  const rows=(dv.key_drivers||[]).map(d=>{
    const age=d.age_days;
    const tone=age==null?'':age>540?'warn':'good';
    const years=age!=null?(age/365).toFixed(1):null;
    return `<div class="analysis-row"><div><b>${esc(d.name)}</b><small>${esc(d.vendor||'')} • versão ${esc(d.version||'—')} • ${esc(d.date||'data não reportada')}</small></div><span class="pill ${tone==='good'?'goodpill':'off'}">${age!=null?`${years} ano(s)`:'SEM DATA'}</span></div>`;
  }).join('')||'<div class="empty">Nenhum driver de fabricante identificado.</div>';
  return `<article class="card pad">
    <div class="device-head"><div><span class="eyebrow">DRIVERS</span><h3 class="section-title">Idade dos drivers que afetam jogo</h3><p class="section-sub">${dv.vendor_count} driver(es) de fabricante entre ${dv.total} instalados.</p></div><span class="pill ${dv.stale_count?'off':'goodpill'}">${dv.stale_count?`${dv.stale_count} ANTIGO(S)`:'SEM ANTIGOS'}</span></div>
    <div class="action-list compact" style="margin-top:12px">${rows}</div>
    <div class="explain-box"><h4>O que o AZOR não afirma</h4><p>${esc(dv.note||'')}</p></div>
    <div class="explain-box"><h4>Por que WAN Miniport não aparece</h4><p>${esc(dv.scope_note||'')}</p></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px"><button class="btn ghost" data-action="azor_windows_drivers">ABRIR FLUXO DE DRIVERS</button><button class="btn ghost" id="refreshDrivers">↻ RELER DRIVERS</button></div>
  </article>`;
}

function startupPanel(){
  const su=(S.hardware||{}).startup;
  if(!su) return `<article class="card pad">${hwSkeleton(3)}</article>`;
  if(!su.supported) return `<article class="card pad"><h3 class="section-title">Inicialização</h3><p class="section-sub">${esc(su.reason||'Leitura indisponível.')}</p></article>`;
  const rows=(su.items||[]).map(x=>{
    const on=x.enabled!==false;
    const mem=x.memory_mb!=null?`${x.memory_mb} MB agora`:(x.running?'em execução':'não está em execução');
    return `<div class="analysis-row startup-row"><div><b>${esc(x.name)}</b><small>${esc(x.scope_label)} • ${esc(x.exe||'programa não identificado')} • ${mem}</small></div>
      <div class="startup-actions">
        <span class="pill ${on?'':'off'}">${on?'LIGADO':'DESLIGADO'}</span>
        <button class="btn small ${on?'ghost':'primary'}" data-startup="${esc(x.scope)}|${encodeURIComponent(x.name)}|${on?'0':'1'}">${on?'DESATIVAR':'REATIVAR'}</button>
      </div></div>`;
  }).join('')||'<div class="empty">Nenhum item de inicialização no registro Run.</div>';
  return `<article class="card pad">
    <div class="device-head"><div><span class="eyebrow">INICIALIZAÇÃO</span><h3 class="section-title">O que abre junto com o Windows</h3><p class="section-sub">${su.enabled_count} de ${su.total} habilitados • ${su.measured_mb} MB medidos agora nos que estão rodando.</p></div><span class="pill">ITEM POR ITEM</span></div>
    <div class="action-list compact" style="margin-top:12px">${rows}</div>
    <div class="explain-box"><h4>Nada em massa</h4><p>${esc(su.policy||'')}</p></div>
    <div class="explain-box"><h4>Por que não existe nota de impacto</h4><p>${esc(su.impact_note||'')}</p></div>
  </article>`;
}

function azorWindowsPanel(){
  const aw=(S.hardware||{}).azor_windows||S.azorWindows;
  if(!aw) return '';
  if(!aw.installed||!aw.cli){
    return `<article class="card pad"><div class="device-head"><div><span class="eyebrow">AZOR WINDOWS</span><h3 class="section-title">Motor de sistema não encontrado</h3></div><span class="pill off">NÃO INSTALADO</span></div><p class="section-sub">O AZOR procurou o motor em <b>${esc(aw.root||'C:\\AZOR')}</b> e não encontrou. As otimizações nativas do app continuam funcionando normalmente.</p></article>`;
  }
  const ver=aw.verification||{};
  const last=aw.daily_status||{};
  const checks=(ver.Checks||[]);
  const failed=checks.filter(c=>String(c.Status||'').toUpperCase()!=='OK');
  return `<article class="card pad glow-pink">
    <div class="device-head"><div><span class="eyebrow">AZOR WINDOWS</span><h3 class="section-title">Motor de sistema conectado</h3><p class="section-sub">${esc(aw.product||'AZOR Windows')} em ${esc(aw.root||'')} • estado da sessão: <b>${esc(aw.session_state||'—')}</b></p></div><span class="pill goodpill">INSTALADO</span></div>
    <div class="grid cols-3" style="margin-top:12px">
      <div class="score"><small>ÚLTIMA VERIFICAÇÃO</small><strong>${esc(String(ver.Overall||'—'))}</strong><span class="section-sub">${checks.length} checagens • ${failed.length} para revisar</span></div>
      <div class="score"><small>ÚLTIMO COMANDO</small><strong>${esc(String(last.Command||'—'))}</strong><span class="section-sub">${last.Updated?esc(last.Updated):'nenhum comando registrado ainda'}${last.ExitCode!=null?` • código ${last.ExitCode}`:''}</span></div>
      <div class="score"><small>DISCOS ACOMPANHADOS</small><strong>${Object.keys(aw.storage||{}).length||'—'}</strong><span class="section-sub">TRIM e manutenção por unidade</span></div>
    </div>
    ${failed.length?`<div class="action-list compact" style="margin-top:12px">${failed.slice(0,6).map(c=>`<div class="analysis-row"><div><b>${esc(c.Check||'')}</b><small>${esc(c.Detail||'')}</small></div><span class="pill off">${esc(String(c.Status||'').toUpperCase())}</span></div>`).join('')}</div>`:''}
    <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:14px">
      <button class="btn primary" data-action="azor_windows_daily">OTIMIZAÇÃO DIÁRIA</button>
      <button class="btn primary" data-action="azor_windows_gameprep">PREPARAR PARA JOGAR</button>
      <button class="btn ghost" data-action="azor_windows_verify">VERIFICAR</button>
      <button class="btn ghost" data-action="azor_windows_storage">ANALISAR DISCOS</button>
      <button class="btn ghost" data-action="azor_windows_hardware">RELER HARDWARE</button>
      <button class="btn ghost" data-action="azor_windows_deep">MANUTENÇÃO PROFUNDA</button>
      <button class="btn ghost" data-action="azor_windows_restore">RESTAURAR</button>
    </div>
    <div class="explain-box"><h4>Um motor só</h4><p>Quando o AZOR Windows está instalado, estes botões chamam exatamente as rotinas de ${esc(aw.root||'C:\\AZOR')}. Assim o app e o sistema nunca aplicam ajustes diferentes nem brigam entre si. Cada comando pede elevação ao Windows na hora de executar.</p></div>
  </article>`;
}

function renderHardware(){
  const h=S.hardware||{};const p=h.profile||S.summary?.hardware_profile||{};const bios=h.bios||{};
  const bb=bios.BaseBoard||{},bi=bios.BIOS||{};
  return `${head('Hardware Command Center','Tudo que o AZOR consegue ler deste PC em uma tela só: componentes, temperatura, discos, drivers e o que abre com o Windows.','<button class="btn ghost" id="refreshHardware">↻ RELER HARDWARE</button><button class="btn primary" data-action="export_report">EXPORTAR RELATÓRIO</button>')}
  ${guide('Leitura, não palpite','Cada valor aqui vem de uma leitura do Windows feita agora. Onde o Windows não responde, o AZOR escreve “não reportado” em vez de estimar um número para preencher a tela.',1,4)}
  <section class="grid cols-4 stagger" style="margin-bottom:14px">
    <article class="card pad"><span class="eyebrow">PERFIL</span><h3>${esc(p.label||'Analisando')}</h3><p class="section-sub">AUTO recomenda ${esc(String(p.recommended||'safe').toUpperCase())}</p></article>
    <article class="card pad"><span class="eyebrow">PLACA-MÃE</span><h3>${esc(bb.Manufacturer||'—')}</h3><p class="section-sub">${esc(bb.Product||'Modelo não detectado')}</p></article>
    <article class="card pad"><span class="eyebrow">BIOS</span><h3>${esc(bi.SMBIOSBIOSVersion||'—')}</h3><p class="section-sub">${esc(bi.Manufacturer||'')}</p></article>
    <article class="card pad"><span class="eyebrow">MEMÓRIA</span><h3>${fmt(p.ram_gb,' GB')}</h3><p class="section-sub">${(p.gpus||[]).length?esc(p.gpus[0]):'GPU não detectada'}</p></article>
  </section>
  ${hardwareVitals()}
  <div class="hw-columns">
    ${storagePanel()}
    ${driversPanel()}
  </div>
  ${startupPanel()}
  ${azorWindowsPanel()}
  <div class="tip-banner card"><span><strong>PRÓXIMO PASSO</strong> A BIOS tem os ajustes de maior impacto real, e eles precisam ser feitos por você.</span><div class="compact-actions"><button class="btn small primary" data-go="bios">ABRIR BIOS COPILOTO</button><button class="btn small ghost" data-go="stutter">STUTTER LAB</button></div></div>`;
}

// ==================== BIOS COPILOT ====================
function biosStepIcon(status){return status==='confirmed'?'✓':status==='action'?'!':status==='prereq'?'◆':'?'}

// Abrir a BIOS sem depender da tecla no boot.
//
// Em PC com inicialização rápida, a janela para apertar DEL é de fração de
// segundo e o cliente tenta cinco vezes antes de conseguir. O Windows tem um
// caminho oficial para isso, mas ele só existe em UEFI — então o app confere o
// firmware ANTES e diz o que falta, em vez de disparar um comando que falha
// calado numa máquina legada.
function firmwareBootCard(){
  const f = S.firmware;
  if(!f) return '';
  const ready = !!f.ready;
  return `<article class="card pad firmware-card ${ready ? '' : 'blocked'}">
    <div class="device-head"><div>
      <span class="eyebrow">ENTRAR NA BIOS</span>
      <h3 class="section-title">Reiniciar direto na configuração da ${esc(f.firmware || 'UEFI')}</h3>
      <p class="section-sub">${esc(f.detail || '')}</p>
    </div><span class="pill ${ready ? 'goodpill' : 'off'}">${ready ? 'DISPONÍVEL' : 'INDISPONÍVEL'}</span></div>
    ${ready ? `<div class="firmware-actions">
      <button class="btn primary" id="rebootFirmware">REINICIAR NA BIOS AGORA</button>
      <button class="btn ghost" data-action="abort_reboot">CANCELAR REINÍCIO</button>
    </div>
    <p class="firmware-note">O reinício é agendado com 15 segundos de folga e pode ser cancelado
    no botão ao lado. Salve o que estiver aberto antes de confirmar — o Windows fecha os programas.</p>` : ''}
  </article>`;
}

async function loadFirmware(){
  try{ S.firmware = await getJSON('/api/firmware'); if(S.page === 'bios') render(); }
  catch(e){ console.warn('firmware', e); }
}

async function rebootToFirmware(btn){
  // Confirmação explícita: é a única ação do app que desliga o PC do cliente.
  if(!confirm('O Windows vai reiniciar este PC em 15 segundos e abrir direto a configuração da BIOS/UEFI.\n\nSalve tudo o que estiver aberto.\n\nContinuar?')) return;
  const old = btn?.textContent;
  if(btn){ btn.disabled = true; btn.textContent = 'AGENDANDO…'; }
  try{
    const r = await postJSON('/api/action', { name:'reboot_to_firmware', delay:15 });
    toast(r.detail || (r.ok ? 'Reinício agendado.' : 'Não foi possível agendar.'), !!r.ok);
  }catch(e){ toast(e.message, false); }
  finally{ if(btn){ btn.disabled = false; btn.textContent = old; } }
}

function renderBios(){
  const b=S.biosCopilot;
  if(!b) return `${head('BIOS Copiloto','Detectando a placa-mãe para montar o passo a passo do seu fabricante.')}<article class="card pad">${hwSkeleton(5)}</article>`;
  if(!b.supported) return `${head('BIOS Copiloto','Diagnóstico e orientação compatível com o hardware.')}<article class="card pad"><h3 class="section-title">Hardware não pôde ser lido</h3><p class="section-sub">${esc(b.reason||'')}</p></article>`;
  const steps=(b.steps||[]).map(s=>{
    const cls=s.status==='confirmed'?'confirmed':s.status==='action'?'action':'neutral';
    return `<article class="card bios-step ${cls}">
      <div class="bios-step-head"><div class="bios-step-icon">${biosStepIcon(s.status)}</div>
        <div><h3>${esc(s.name)}</h3><p class="section-sub">${esc(s.detail)}</p></div>
        <span class="pill ${s.status==='confirmed'?'goodpill':'off'}">${s.status==='confirmed'?'CONFIRMADO PELO WINDOWS':s.status==='action'?'AÇÃO NA BIOS':s.status==='prereq'?'PRÉ-REQUISITO':'NÃO VERIFICÁVEL'}</span>
      </div>
      <div class="bios-path"><small>CAMINHO NA SUA BIOS</small><b>${esc(s.path)}</b></div>
      <p class="section-sub bios-why"><strong>Por que importa:</strong> ${esc(s.why)}</p>
      <div class="bios-step-foot">
        <label class="bios-check"><span class="toggle ${s.marked?'on':''}" role="switch" aria-checked="${!!s.marked}" data-bios-check="${esc(s.key)}|${s.marked?'0':'1'}"></span><span>Já alterei este item na BIOS</span></label>
        ${s.marked?`<small class="${s.verified_after_mark?'good':'warn'}">${s.verified_after_mark?'Marcado em '+esc(s.marked_at||'')+' e confirmado pela releitura.':'Marcado em '+esc(s.marked_at||'')+', mas o Windows ainda não confirma. Reinicie e volte aqui.'}</small>`:''}
      </div>
    </article>`;
  }).join('');
  return `${head('BIOS Copiloto','Passo a passo com o caminho exato do menu da sua placa. O AZOR lê, explica e confirma — mas nunca grava firmware.','<button class="btn ghost" id="refreshBios">↻ VERIFICAR AGORA</button><button class="btn primary" data-action="export_report">EXPORTAR RELATÓRIO</button>')}
  ${firmwareBootCard()}
  <section class="card pad bios-hero glow-pink">
    <div><span class="eyebrow">${esc(b.vendor_label)}</span><h2 class="bios-board">${esc(b.board.manufacturer||'')} ${esc(b.board.product||'')}</h2>
    <p class="section-sub">${esc(b.cpu.name||'')} • perfil de memória chamado de <b>${esc(b.memory_feature)}</b> nesta plataforma</p></div>
    <div class="bios-enter"><div><small>COMO ENTRAR</small><p>${esc(b.enter)}</p></div><div><small>COMO SALVAR</small><p>${esc(b.save)}</p></div></div>
  </section>
  <div class="bios-steps stagger">${steps}</div>
  <article class="card pad"><h3 class="section-title">Por que o AZOR não faz isso sozinho</h3><p class="section-sub">${esc(b.policy)}</p>
  <div class="explain-box"><h4>Sobre os nomes dos menus</h4><p>${esc(b.accuracy_note)}</p></div></article>`;
}


// ==================== LIVE DEVICE STREAM ====================
// The browser can only see input while the window is focused, which made the
// visualiser go dead the moment you clicked into a game or another window, and
// left polling rate permanently "not measured". The backend reads Windows Raw
// Input instead - one event per HID report - and streams it here over SSE.
//
// Privacy: the stream carries only which keys/buttons are held right now plus
// timing. No sequence of keystrokes is ever built, nothing is written to disk,
// and the listener stops itself a few seconds after this page closes.

let inputStreamRetry=null, inputFallbackTimer=null, inputPaintFrame=0;
let inputStreamEpoch=0, inputPendingFrame=null;
let inputMonitorRequested=false;
function isInputPage(){return S.page==='device'||S.page==='keyboardmouse'||S.page==='controller'}
function isInputVisible(){return isInputPage() && document.visibilityState!=='hidden' && document.hasFocus()}
function wantsNativeInput(){return isInputVisible() && S.periphTab!=='controller'}
function queueLiveInput(live){
  inputPendingFrame=live;
  if(inputPaintFrame)return;
  inputPaintFrame=requestAnimationFrame(()=>{
    inputPaintFrame=0;
    const latest=inputPendingFrame;inputPendingFrame=null;
    if(wantsNativeInput() && latest)applyLiveInput(latest);
  });
}
function startInputStream(){
  if(!wantsNativeInput() || S.inputLiveSource || inputMonitorRequested)return;
  inputMonitorRequested=true;
  const epoch=++inputStreamEpoch;
  try{
    const src=new EventSource('/api/input-live/stream');
    S.inputLiveSource=src;
    src.onmessage=ev=>{
      if(epoch!==inputStreamEpoch || !wantsNativeInput())return;
      try{S.inputLive=JSON.parse(ev.data);queueLiveInput(S.inputLive)}catch(e){}
    };
    src.onerror=()=>{
      if(S.inputLiveSource!==src)return;
      src.close();S.inputLiveSource=null;inputMonitorRequested=false;
      clearTimeout(inputStreamRetry);
      if(wantsNativeInput())inputStreamRetry=setTimeout(startInputStream,1500);
    };
  }catch(e){pollInputFallback(epoch)}
}
function stopInputStream(){
  ++inputStreamEpoch;
  clearTimeout(inputStreamRetry);clearTimeout(inputFallbackTimer);
  cancelAnimationFrame(inputPaintFrame);inputPaintFrame=0;inputPendingFrame=null;
  const hadStream=!!S.inputLiveSource;
  if(S.inputLiveSource){try{S.inputLiveSource.close()}catch(e){}S.inputLiveSource=null}
  if(!hadStream&&!inputMonitorRequested)return;
  inputMonitorRequested=false;
  postJSON('/api/action',{name:'input_monitor_stop'}).catch(()=>{});
}
async function pollInputFallback(epoch=inputStreamEpoch){
  if(!wantsNativeInput() || epoch!==inputStreamEpoch)return;
  try{
    const live=await getJSON('/api/input-live');
    if(wantsNativeInput() && epoch===inputStreamEpoch){S.inputLive=live;queueLiveInput(live)}
  }catch(e){}
  if(wantsNativeInput() && epoch===inputStreamEpoch)inputFallbackTimer=setTimeout(()=>pollInputFallback(epoch),33);
}

let lastLiveKeys='';
function applyLiveInput(live){
  if(!live || !isInputVisible())return;
  const m=live.mouse||{},kb=live.keyboard||{};
  const keys=(kb.down||[]);
  const signature=[...keys].sort().join(',');
  if(signature!==lastLiveKeys){
    $$('.keyboard-svg [data-pressable]').forEach(el=>{
      const name=el.getAttribute('data-pressable');
      // O filtro deixou de ser so letra e numero: o TKL desenha simbolo, seta e
      // bloco de navegacao, e o monitor ja devolve todos esses rotulos.
      if(name){
        el.classList.toggle('pressed',keys.includes(name));
      }
    });
    lastLiveKeys=signature;
    setLiveText('keyboard',keys.length?`Pressionado agora: ${keys.join(' + ')}`:'Teclado pronto',keys.length>0);
  }
  const buttons=m.buttons||[];
  ['left-click','right-click','wheel','side-1','side-2'].forEach(b=>pressVisual(b,buttons.includes(b)));
  setReadout('left-click', buttons.includes('left-click')?'pressionado':'solto');
  setReadout('right-click', buttons.includes('right-click')?'pressionado':'solto');
  setReadout('wheel', m.wheel?'girando':(buttons.includes('wheel')?'clique do meio':'parado'));
  setReadout('side', ['side-1','side-2'].filter(b=>buttons.includes(b)).join(' + ') || 'solto');
  if(m.wheel)flashVisual('wheel',120);
  const svg=$('.mouse-svg');
  if(svg){
    if(m.moving){const dx=clamp((m.dx||0)*.28,-9,9),dy=clamp((m.dy||0)*.28,-9,9);svg.style.transform=`translate(${dx}px,${dy}px)`}
    else svg.style.transform='';
  }
  const hz=live.polling?.hz;
  setLiveText('mouse',
    buttons.length?`Botão ${buttons.join(' + ')}`:
    m.moving?(hz?`Movimento • ${Math.round(hz)} Hz medidos`:'Movimento detectado'):'Mouse pronto',
    buttons.length>0||!!m.moving);
  const badge=$('#pollingLive');
  if(badge)badge.textContent=hz?`${Math.round(hz)} Hz`:'—';
  const reports=$('#pollingReports');
  if(reports)reports.textContent=String(m.reports??0);
  paintInputLabs(live);
}

// Cartões de teste do mouse e do teclado. Os números vêm do monitor de Raw
// Input; "zerar" só guarda a linha de base aqui na tela, o monitor não esquece.
function clickTotals(m){
  const base=S.clickBase||{clicks:{},chatter:{}};
  const clicks={},chatter={};
  for(const [k] of CLICK_BUTTONS){
    clicks[k]=Math.max(0,((m.clicks||{})[k]||0)-(base.clicks[k]||0));
    chatter[k]=Math.max(0,((m.chatter||{})[k]||0)-(base.chatter[k]||0));
  }
  return {clicks,chatter};
}
function paintInputLabs(live){
  const m=live.mouse||{},kb=live.keyboard||{},now=performance.now();
  const svg=$('.mouse-svg');
  if(svg){
    const dir=m.wheel?m.wheel_dir||0:0;
    if(svg.classList.contains('wheel-up')!==(dir>0))svg.classList.toggle('wheel-up',dir>0);
    if(svg.classList.contains('wheel-down')!==(dir<0))svg.classList.toggle('wheel-down',dir<0);
    const line=svg.querySelector('[data-mouse-vector]');
    if(line){
      let x=0,y=0;
      if(m.moving){const len=Math.hypot(m.dx||0,m.dy||0)||1,k=Math.min(46,6+Math.log2(1+len)*7)/len;x=(m.dx||0)*k;y=(m.dy||0)*k}
      const x2=x.toFixed(1),y2=y.toFixed(1);
      if(line.getAttribute('x2')!==x2)line.setAttribute('x2',x2);
      if(line.getAttribute('y2')!==y2)line.setAttribute('y2',y2);
    }
  }
  if($('[data-click-count]')){
    const {clicks,chatter}=clickTotals(m);
    for(const [k] of CLICK_BUTTONS)setNodeText(`[data-click-count="${k}"]`,String(clicks[k]),'bad',chatter[k]>0);
    const total=Object.values(clicks).reduce((a,b)=>a+b,0);
    const last=S._clickTotal??total;
    for(let i=0;i<total-last&&i<50;i++)S.cpsTimes.push(now);
    S._clickTotal=total;
    while(S.cpsTimes.length&&now-S.cpsTimes[0]>1000)S.cpsTimes.shift();
    const cps=S.cpsTimes.length;if(cps>S.cpsMax)S.cpsMax=cps;
    setNodeText('[data-cps]',String(cps));setNodeText('[data-cps-max]',`recorde ${S.cpsMax}`);
    const bad=CLICK_BUTTONS.filter(([k])=>chatter[k]>0);
    setNodeText('[data-click-verdict]',bad.length
      ?`${bad.map(([k,l])=>`${l}: ${chatter[k]} clique(s) colado(s)`).join(' · ')}. Um clique que chega menos de 30 ms depois de soltar não é dedo: é o switch "quicando", o defeito que vira clique duplo sozinho.`
      :total?'Nenhum clique duplo sozinho até agora. Cada clique chegou separado do anterior.'
      :'Clique algumas vezes em cada botão. Um clique que vira dois sozinho aparece aqui.','bad',bad.length>0);
  }
  const st=live.polling?.stability;
  if(st&&$('.rhythm-bar')){
    for(const k of ['on_beat','early','late','gaps']){
      const el=$(`[data-stab="${k}"]`);if(el){const w=`${st[k]||0}%`;if(el.style.width!==w)el.style.width=w}
      setNodeText(`[data-stab-text="${k}"]`,`${(st[k]||0).toFixed(1)}%`);
    }
    setNodeText('[data-rhythm-hz]',live.polling?.hz?`${Math.round(live.polling.hz)} Hz`:'—');
  }
  if($('[data-mouse-counts]')){
    const cps=Number(m.counts_per_s)||0;if(cps>S.mousePeak)S.mousePeak=cps;
    setNodeText('[data-mouse-counts]',cps.toLocaleString('pt-BR'));
    setNodeText('[data-mouse-peak]',S.mousePeak.toLocaleString('pt-BR'));
  }
  if($('[data-kb-held]')){
    const held=(kb.down||[]).length;if(held>S.kbMax)S.kbMax=held;
    setNodeText('[data-kb-held]',String(held));setNodeText('[data-kb-max]',String(S.kbMax));
    setNodeText('[data-kb-presses]',String(Math.max(0,(kb.press_count||0)-(S.kbPressBase||0))));
    setNodeText('[data-kb-verdict]',S.kbMax>=10
      ?`O Windows recebeu ${S.kbMax} teclas seguradas juntas: o teclado não trava combinações de jogo.`
      :S.kbMax>=6?`${S.kbMax} teclas juntas. Suficiente para jogar; continue somando teclas para ver o limite.`
      :S.kbMax>=3?`${S.kbMax} teclas juntas até agora. Segure mais para achar o limite do teclado.`
      :'Segure W, A, S, D, Shift e Espaço juntos e vá somando teclas. O número mostra quantas o Windows recebeu ao mesmo tempo.');
  }
}

function pollingPanel(){
  const live=S.inputLive||{};const p=live.polling||{};const running=!!live.running;
  const measured=p.confidence==='measured';
  return `<article class="card pad polling-card ${running?'live':''}">
    <div class="device-head"><div><span class="eyebrow">TAXA DE ENVIO MEDIDA</span>
      <h3 class="section-title">O AZOR conta os relatórios reais do seu mouse</h3>
      <p class="section-sub">Cada movimento gera um relatório do dispositivo. O AZOR conta quantos chegam por segundo em vez de repetir o número da caixa.</p></div>
      <span class="pill ${running?'goodpill':'off'}">${running?'OUVINDO':'PARADO'}</span></div>
    <div class="polling-readout">
      <div><small>MEDIDO AGORA</small><b id="pollingLive">${p.hz?Math.round(p.hz)+' Hz':'—'}</b></div>
      <div><small>RELATÓRIOS RECEBIDOS</small><b id="pollingReports">${live.mouse?.reports??0}</b></div>
      <div><small>OSCILAÇÃO</small><b>${p.jitter_ms!=null?p.jitter_ms+' ms':'—'}</b></div>
      <div><small>MAIS PRÓXIMO DE</small><b>${p.nominal_hz?p.nominal_hz+' Hz':'—'}</b></div>
    </div>
    <p class="section-sub polling-hint">${esc(p.detail||'Mova o mouse para o AZOR começar a medir.')}${measured?'':' Só é chamado de medido depois de 200 relatórios.'}</p>
    <div class="explain-box privacy-box"><h4>Privacidade desta tela</h4><p>${esc(live.privacy||'Esta tela mostra apenas qual tecla ou botão está pressionado agora, para desenhar o periférico e medir a taxa de envio. Nada do que você digita é gravado ou salvo.')}</p></div>
  </article>`;
}


// Numbers that were just measured read better arriving than appearing finished.
// Only decorative: the DOM already holds the real value, and reduced-motion or a
// missing rAF simply leaves the final number in place.
let lastAnimatedPage=null;
function animateCounters(root=document){
  if(S.settings.animations===false)return;
  if(window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  $$('[data-count]',root).forEach(el=>{
    const target=Number(el.dataset.count);
    if(!isFinite(target)||el._counted)return;
    el._counted=true;
    const suffix=el.dataset.countSuffix||'';
    const prefix=el.dataset.countPrefix||'';
    const decimals=Number(el.dataset.countDecimals||0)||0;
    const dur=520,t0=performance.now();
    const step=now=>{
      const k=Math.min(1,(now-t0)/dur);
      const eased=1-Math.pow(1-k,3);
      const value=target*eased;
      el.textContent=prefix+(decimals?value.toFixed(decimals):String(Math.round(value)))+suffix;
      if(k<1)requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}


// ==================== FRAMETIME VISUALS ====================
// The engine already measured all of this; these two views just stop it from
// being four numbers in a row. Nothing here derives a value of its own - every
// bar and every spike is a frame PresentMon actually recorded.

function frametimeHistogram(frames){
  const h=frames?.histogram||[];
  if(!h.length)return '';
  const max=Math.max(...h.map(b=>b.count))||1;
  const median=frames.frametime_median_ms;
  const bars=h.map(b=>{
    const pct=Math.round(b.count/max*100);
    const label=b.overflow?`acima de ${b.from_ms} ms`:`${b.from_ms}–${b.to_ms} ms`;
    const slow=b.overflow||(median&&b.from_ms>median*2);
    return `<div class="ft-bar ${slow?'slow':''}" style="--h:${pct}%" title="${esc(label)}: ${b.count} frame(s)"><i></i></div>`;
  }).join('');
  return `<div class="ft-chart"><div class="ft-bars">${bars}</div>
    <div class="ft-axis"><span>${h[0].from_ms} ms</span><span>mais rápido → mais lento</span><span>${h[h.length-1].overflow?'+':''}${h[h.length-1].from_ms} ms</span></div></div>`;
}

function frametimeTimeline(frames){
  const t=frames?.timeline||[];
  if(!t.length)return '';
  const threshold=frames.stutter_threshold_ms||Math.max(20,(frames.frametime_median_ms||16.7)*2);
  const max=Math.max(...t);
  const pts=t.map((v,i)=>{
    const x=(i/(t.length-1||1))*100;
    const y=100-Math.min(100,(v/max)*100);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(' ');
  const marks=t.map((v,i)=>v>=threshold?`<circle cx="${((i/(t.length-1||1))*100).toFixed(2)}" cy="${(100-Math.min(100,(v/max)*100)).toFixed(2)}" r="1.4"/>`:'').join('');
  return `<div class="ft-timeline">
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Frametime ao longo da sessão">
      <polyline points="${pts}" class="ft-line" vector-effect="non-scaling-stroke"/>
      <g class="ft-spikes">${marks}</g>
    </svg>
    <div class="ft-axis"><span>início da sessão</span><span>picos marcados acima de ${Math.round(threshold)} ms</span><span>fim</span></div>
  </div>`;
}

function frametimePanel(frames){
  if(!frames?.available||!(frames.histogram||[]).length)return '';
  return `<article class="card pad" style="margin-top:14px">
    <div class="device-head"><div><span class="eyebrow">FRAMETIME REAL</span><h3 class="section-title">Como os ${frames.frames||0} frames se distribuíram</h3>
    <p class="section-sub">Barras à esquerda são frames rápidos; à direita, lentos. Uma cauda comprida à direita é o que se sente como travadinha, mesmo com FPS médio alto.</p></div>
    <span class="pill ${(frames.stutter_events||0)?'off':'goodpill'}">${frames.stutter_events||0} STUTTER(S)</span></div>
    ${frametimeHistogram(frames)}
    <h4 class="section-title" style="margin-top:18px">Linha do tempo da sessão</h4>
    <p class="section-sub">Cada ponto é o frame mais lento daquele trecho, para que um pico não desapareça na média.</p>
    ${frametimeTimeline(frames)}
    <div class="explain-box"><h4>Como ler</h4><p>1% low é a média dos 1% de frames mais lentos: é o número que representa a pior parte da experiência. FPS médio pode ficar bonito enquanto o 1% low está ruim, e é exatamente aí que o jogo parece travado.</p></div>
  </article>`;
}

function render(){
  setActiveNav();
  const pages={
    home:renderHome, plan:renderPlan, quick:renderQuick, declutter:renderDeclutter, arsenal:renderArsenal, advanced:renderAdvanced, fortnite:renderFortnite, games:renderGames,
    device:renderDevice, keyboardmouse:renderKeyboardMouse, controller:renderController,
    monitor:renderMonitor, gameDiag:renderGameDiagnostic, stutter:renderStutter, windows:renderWindows, guardian:renderGuardian, maintenance:renderMaintenance,
    bios:renderBios, hardware:renderHardware, network:renderNetwork, latency:renderLatency, islc:renderLatency, measure:renderLatency,
    restore:renderRestore, logs:renderLogs, settings:renderSettings, ...performancePages()
  };
  const fn=pages[S.page]||renderHome;
  const view=$('#view');
  if(!view)return;
  // The whole view is rebuilt on every data tick. Without this, the live poll
  // threw the user back to the top of the page every 1,5 s and wiped whatever
  // was being typed, because the focused node stopped existing mid-keystroke.
  const keptScroll=view.scrollTop;
  const active=document.activeElement;
  const keptFocus=active&&view.contains(active)&&active.id?{id:active.id,start:active.selectionStart,end:active.selectionEnd,value:active.value}:null;
  try{view.innerHTML=hubTabs(S.page)+fn();}
  catch(e){console.error(e);view.innerHTML=`<article class="card pad"><h2>Falha ao renderizar esta tela</h2><p class="section-sub">${esc(e.message||e)}</p></article>`;}
  if(keptScroll)view.scrollTop=keptScroll;
  if(keptFocus){
    const again=document.getElementById(keptFocus.id);
    if(again){
      try{
        if(again.value!==undefined&&keptFocus.value!==undefined&&again.value!==keptFocus.value)again.value=keptFocus.value;
        again.focus({preventScroll:true});
        if(keptFocus.start!=null&&again.setSelectionRange)again.setSelectionRange(keptFocus.start,keptFocus.end);
      }catch(e){}
    }
  }
  rebuildInputVisualCache();
  bindCommon();
  syncGamepadVisual();
  // Counters are an arrival animation, so they belong to arriving on a page.
  // Replaying them on every poll made every number on screen jump back to zero
  // once per tick.
  if(S.page!==lastAnimatedPage){lastAnimatedPage=S.page;animateCounters(view);}
  if(S.page==='monitor'){requestAnimationFrame(drawUsageChart);if(!S.gameDiag)loadGameDiag(false).then(()=>{if(S.page==='monitor')render()})}
  if(S.page==='latency'&&S.latencyAfter) requestAnimationFrame(drawSleepChart);
  if(S.page==='games'&&!S._gamesLoaded) loadGamesGpu(false).then(()=>{S._gamesLoaded=true;if(S.page==='games')render()});
  if(S.page==='network'&&!S._network) loadNetwork();
  if(S.page==='logs') loadLogs();
  if(S.page==='guardian'&&!S.health) loadHealth();
  if(S.page==='maintenance'&&!S.maintenance) loadMaintenance();
  if(isInputPage()){if(wantsNativeInput())startInputStream();else stopInputStream();if(!S.inputCaps)loadInputCaps();if(S.inputLive)applyLiveInput(S.inputLive)}else{stopInputStream()}
  if(S.page==='bios'&&!S.biosCopilot) loadBiosCopilot();
  if(S.page==='bios'&&!S.firmware) loadFirmware();
  if(S.page==='hardware'&&!S.hardware) loadHardware();
  if(S.page==='stutter'&&!S.stutter) loadStutter();
  if(['arsenal','declutter'].includes(S.page)&&!S.arsenal) loadArsenal();
  if(S.page==='arsenal'&&!S.drift) loadDrift();
  if(S.page==='arsenal'&&!S.driverGuide) loadDriverGuide();
  if(S.page==='plan'&&!S.plan) loadPlan();
  // O índice mede de verdade e por isso demora alguns segundos: ele chega
  // depois, sobre um esqueleto, em vez de segurar a tela inteira.
  if(S.page==='arsenal'&&!S.azorIndex&&!S.boost.running) loadAzorIndex();
  if(['home','settings'].includes(S.page)&&!S.autostart&&!S.autostartLoading)loadAutostart();
  if(S.page==='home'&&!S.modeCleanup&&!S.modeCleanupLoading)loadModeCleanup();
  if(S.page==='restore'&&!S.restorePoints) loadRestorePoints();
  if(S.page==='energy'&&!S.powerControl)loadPerformancePage('energy');
  if(S.page==='services'&&!S.serviceControl)loadPerformancePage('services');
  if(S.page==='gameMode'&&!S.gameModeControl)loadPerformancePage('gameMode');
  if(S.page==='gameDiag'){ if(!S.gameDiag) loadGameDiag(); if(!S.gameReports.length) loadGameReports(); }
}

function bindCommon(){
  bindPerformancePage();
  $$('[data-go]').forEach(e=>e.onclick=()=>go(e.dataset.go));
  $$('[data-hub-tab]').forEach(e=>e.onclick=()=>go(e.dataset.hubTab));
  if(S.page==='games')bindGamesGpu();
  $$('[data-help="device"]').forEach(e=>e.onclick=()=>openModal('AZOR INPUT LAB','<p>O Input Lab usa ilustrações premium 2D estáveis. O nome e o status do periférico vêm do Windows; a arte visual é uma representação neutra e não promete identidade exata do seu hardware.</p>'));
  $$('[data-action]').forEach(b=>b.onclick=()=>runAction(b.dataset.action,b));
  $$('[data-copy]').forEach(b=>b.onclick=async()=>{const text=b.dataset.copy||'';try{await navigator.clipboard.writeText(text);toast('Copiado: '+text,true)}catch(e){prompt('Copie o argumento abaixo:',text)}});
  $$('[data-toggle]').forEach(t=>t.onclick=()=>t.classList.toggle('on'));
  bindInputLab();
  $$('[data-controller]').forEach(b=>b.onclick=()=>{S.controllerType=b.dataset.controller;S.controllerHue=0;render()});$$('[data-controller-hue]').forEach(b=>b.onclick=()=>{S.controllerHue=Number(b.dataset.controllerHue);render()});
  $$('[data-latency-tab]').forEach(b=>b.onclick=()=>go('latency'));
  const rh=$('#refreshHealth');if(rh)rh.onclick=loadHealth;
  const rhw=$('#refreshHardware');if(rhw)rhw.onclick=()=>{S.hardware=null;render();loadHardware(true)};
  const rdv=$('#refreshDrivers');if(rdv)rdv.onclick=()=>loadHardware(true);
  const rbc=$('#refreshBios');if(rbc)rbc.onclick=()=>{S.biosCopilot=null;S.firmware=null;render();loadBiosCopilot();loadFirmware()};
  const rfw=$('#rebootFirmware');if(rfw)rfw.onclick=()=>rebootToFirmware(rfw);
  $$('[data-bios-check]').forEach(t=>t.onclick=()=>{const [key,done]=String(t.dataset.biosCheck||'').split('|');toggleBiosCheck(key,done==='1',t)});
  $$('[data-startup]').forEach(b=>b.onclick=()=>{const [scope,name,en]=String(b.dataset.startup||'').split('|');toggleStartupItem(scope,name,en==='1',b)});
  const rd=$('#refreshDevices');if(rd)rd.onclick=refreshDevices;
  const rm=$('#refreshMonitor');if(rm)rm.onclick=()=>refreshMonitor().catch(()=>toast('Backend indisponivel agora.',false));
  $$('[data-qprofile]').forEach(b=>b.onclick=()=>{if(S.boost.running)return;const next=b.dataset.qprofile;
   if(next==='agressivo'&&S.quickProfile!=='agressivo'&&!confirm('Modo AGRESSIVO: além do Máximo, liga ajustes que a auditoria tinha tirado do padrão (timer global, Nagle, placa de rede sem moderação, NVMe sempre ativo, tela cheia exclusiva global e outros). O PC esquenta mais, consome mais energia e pode ficar instável em parte dos hardwares, e a tela cheia exclusiva global pode esconder o overlay do Discord e do OBS nos jogos. Tudo continua com backup e com desfazer. Usar o modo Agressivo?'))return;
   S.quickProfile=next;S.analysis=null;S.arsenal=null;try{localStorage.setItem('azor.quickProfile',next)}catch(e){}
   if(PERFORMANCE_MODES[next])scheduleSettingsSave({performance_mode:next});
   render();toast('Modo '+profileLabel(next)+' selecionado.',true)});const aq=$('#analyzeQuick');if(aq)aq.onclick=runAnalyze;const rq=$('#runQuick');if(rq)rq.onclick=runQuick;
  const sq=$('#simulateQuick');if(sq)sq.onclick=()=>runSimulation(sq);
  $$('[data-revert]').forEach(b=>b.onclick=()=>revertTweak(b.dataset.revert,b));
  $$('[data-transaction]').forEach(b=>b.onclick=()=>restoreTransaction(b.dataset.transaction,b));
  $$('[data-report]').forEach(b=>b.onclick=()=>downloadOptimizationReport(b.dataset.report,b));
  const identity=$('#resetIdentity');
  if(identity)identity.onclick=()=>{S.settings.accent='#ff2fc8';applyAccent('#ff2fc8');scheduleSettingsSave();identity.textContent='MAGENTA ORIGINAL RESTAURADO'};
  $$('[data-apply-tweak]').forEach(b=>b.onclick=()=>applyTweak(b.dataset.applyTweak,b));
  $$('[data-settings-page]').forEach(b=>b.onclick=async()=>{
   b.disabled=true;
   try{const r=await postJSON('/api/action',{name:'open_windows_settings',page:b.dataset.settingsPage});toast(r.detail,!!r.ok)}
   catch(e){toast(e.message,false)}finally{b.disabled=false}
  });
  $$('[data-prove-tweak]').forEach(b=>b.onclick=()=>proveTweak(b.dataset.proveTweak,b));
  $$('[data-arsenal-filter]').forEach(b=>b.onclick=()=>{S.arsenalFilter=b.dataset.arsenalFilter;render()});
  const ra=$('#refreshArsenal');if(ra)ra.onclick=()=>{S.arsenal=null;render();loadArsenal(true)};
  const rp=$('#refreshPlan');if(rp)rp.onclick=()=>{S.plan=null;render();loadPlan(true)};
  const asq=$('#arsenalSearch');if(asq){asq.oninput=()=>{S.arsenalQuery=asq.value;render()}}
  const rad=$('#relaunchAdmin');if(rad)rad.onclick=()=>relaunchAsAdmin(rad);
  const ri=$('#refreshIndex');if(ri)ri.onclick=()=>{S.azorIndex=null;render();loadAzorIndex(true)};
  const cs=$('#competitiveSession');if(cs)cs.onclick=()=>runCompetitiveSession(cs);
  const boost=$('#boostBtn');
  if(boost){
    boost.onclick=()=>runBoost();
    boost.onpointerenter=()=>{if(!S.boost.running)boostParticles(true)};
    boost.onpointerleave=()=>{if(!S.boost.running)boostParticles(false)};
    boost.onfocus=()=>{if(!S.boost.running)boostParticles(true)};
    boost.onblur=()=>{if(!S.boost.running)boostParticles(false)};
  }
  const qi=$('#quickInputOptimize');if(qi)qi.onclick=()=>runQuickInput(qi);
  const tp=$('#testPing');if(tp)tp.onclick=testPing;
  const mc=$('#modeCleanupBtn');if(mc)mc.onclick=()=>runModeCleanup(mc);
  const um=$('#usbIrqMeasure');if(um)um.onclick=()=>measureUsbIrq();
  const ua=$('#usbIrqApply');if(ua)ua.onclick=()=>usbIrqAction('apply',ua);
  const ur=$('#usbIrqRevert');if(ur)ur.onclick=()=>usbIrqAction('revert',ur);
  const rc=$('#restoreAll');if(rc)rc.onclick=()=>{if(confirm('Voltar todas as configurações rastreadas ao estado anterior ao AZOR (baseline)?'))runAction('restore_all',rc)};
  const rl=$('#refreshLogs');if(rl)rl.onclick=loadLogs;
  const dz1=$('#dz1'),dz2=$('#dz2');if(dz1)dz1.oninput=()=>$('#dz1v').textContent=dz1.value+'%';if(dz2)dz2.oninput=()=>$('#dz2v').textContent=dz2.value+'%';
  const scp=$('#saveControllerProfile');if(scp)scp.onclick=()=>toast('Perfil visual salvo no Azor. Ajustes de hardware só são aplicados quando houver API compatível.',true);
  const diag=$('#diagController');if(diag)diag.onclick=()=>openModal('Diagnóstico do controle',`<p>Detectado pelo Windows: <b>${esc(deviceName('controller'))}</b></p><p>Status: ${esc(deviceStatus('controller'))}</p><p>Bateria, deadzone e polling dependem de APIs específicas do controle/driver e não são inventados pelo Azor.</p>`);
  const si=$('#sleepInterval'),it=$('#sleepIter');if(si)si.oninput=()=>$('#sleepIntervalV').textContent=(Number(si.value)/10).toFixed(1)+' ms';if(it)it.oninput=()=>$('#sleepIterV').textContent=it.value;
  const ms=$('#runMeasure');if(ms)ms.onclick=runMeasure;
  const lb=$('#latencyBaseline');if(lb)lb.onclick=()=>runLatencyBaseline(lb);
  const lo=$('#latencyOptimize');if(lo)lo.onclick=()=>runLatencyOptimize(lo);
  const lr=$('#latencyReset');if(lr)lr.onclick=()=>{S.latencyBaseline=null;S.latencyAfter=null;render();toast('Comparação de latência limpa.',true)};
  const sd=$('#runStutterDiag');if(sd)sd.onclick=loadStutter;
  const sf=$('#applyStutterFix');if(sf)sf.onclick=()=>runStutterFix(sf);
  const gdR=$('#refreshGameDiag');if(gdR)gdR.onclick=()=>loadGameDiag(true);
  const gdF=$('#setupFrameCapture');if(gdF)gdF.onclick=()=>setupFrameCapture(gdF);
  const gdB=$('#gameDiagBefore');if(gdB)gdB.onclick=()=>startGameDiag('antes',gdB);
  const gdA=$('#gameDiagAfter');if(gdA)gdA.onclick=()=>startGameDiag('depois',gdA);
  const gdS=$('#gameDiagStop');if(gdS)gdS.onclick=()=>stopGameDiag(gdS);
  const gdL=$('#refreshGameReports');if(gdL)gdL.onclick=loadGameReports;
  bindSettings();
}


async function runAction(name,btn){const old=btn?.textContent;if(btn){btn.disabled=true;btn.textContent='APLICANDO…'}try{const r=await postJSON('/api/action',{name});toast(r.detail||'Concluído',!!r.ok);await refreshSummary(false);if(S.page==='latency'||S.page==='restore'||S.page==='fortnite'||S.page==='advanced')render();}catch(e){toast(e.message,false)}finally{if(btn){btn.disabled=false;btn.textContent=old}}}

async function loadAutostart(){
  if(S.autostartLoading)return;
  S.autostartLoading=true;
  try{S.autostart=await getJSON('/api/logon-autoapply')}
  catch(e){S.autostart={enabled:false,detail:'Estado não consultado: '+e.message}}
  finally{S.autostartLoading=false;if(['home','settings'].includes(S.page))render()}
}

// Itens que sairam do modo Agressivo e continuam aplicados neste PC.
async function loadModeCleanup(){
  if(S.modeCleanupLoading)return;
  S.modeCleanupLoading=true;
  try{S.modeCleanup=await getJSON('/api/mode-cleanup')}
  catch(e){S.modeCleanup={ok:false,items:[]}}
  finally{S.modeCleanupLoading=false;if(S.page==='home'&&(S.modeCleanup.items||[]).length)render()}
}

async function runModeCleanup(btn){
  const items=(S.modeCleanup&&S.modeCleanup.items)||[];
  if(!items.length)return;
  if(!confirm(`Desfazer ${items.length} ajuste(s)?\n\n${items.map(x=>'• '+x.name).join('\n')}\n\nCada um volta ao valor de antes do AZOR e é relido. O Windows pede autorização uma vez.`))return;
  const old=btn?.textContent;if(btn){btn.disabled=true;btn.textContent='DESFAZENDO…'}
  try{
    const r=await postJSON('/api/mode-cleanup',{},ACTION_TIMEOUT_MS);
    toast(r.detail||(r.ok?'Ajustes desfeitos.':'Nem tudo pôde ser desfeito.'),r.ok===true);
  }catch(e){toast(e.message,false)}
  finally{S.modeCleanup=null;S.arsenal=null;S.analysis=null;if(btn){btn.disabled=false;btn.textContent=old}render()}
}

async function loadRestorePoints(){
  try{
    const [points,records]=await Promise.all([getJSON('/api/restore-points'),getJSON('/api/transactions')]);
    S.restorePoints=points;S.transactions=records.items||[];if(S.page==='restore')render()
  }
  catch(e){console.warn('restore points',e)}
}

function recoveryHistoryHtml(){
  const items=S.transactions;
  if(!items)return '<article class="card pad"><h3 class="section-title">Histórico de alterações</h3><p class="section-sub">Consultando registros de restauração…</p></article>';
  const names={applied:'Aplicado e verificado',restored:'Restaurado',rolled_back:'Desfeito após falha',prepared:'Execução não confirmada',recovery_required:'Restauração pendente',unreadable:'Registro ilegível'};
  return '<article class="card pad"><h3 class="section-title">Histórico de alterações</h3><p class="section-sub">Cada item guarda seu estado imediatamente anterior. Restaure primeiro o mais recente quando houver ajustes relacionados.</p><div class="recovery-list">'+(items.length?items.slice(0,50).map(row=>`<div class="recovery-row"><div><b>${esc(row.name||'Registro de alteração')}</b><p>${esc(names[row.status]||'Estado não confirmado')} · ${row.time?esc(new Date(row.time*1000).toLocaleString('pt-BR')):'data indisponível'}</p><small>${esc(row.detail||'')}</small></div>${['applied','prepared','recovery_required'].includes(row.status)?`<button class="btn ghost" data-transaction="${esc(row.id)}">RESTAURAR</button>`:''}</div>`).join(''):'<p class="section-sub">Nenhuma alteração registrada por esta versão. Os backups anteriores continuam abaixo.</p>')+'</div></article>';
}
async function restoreTransaction(id,button){
  if(!window.confirm('Restaurar o estado salvo antes desta alteração? Outras alterações relacionadas podem precisar ser desfeitas primeiro.'))return;
  button.disabled=true;button.textContent='RESTAURANDO…';
  try{const r=await postJSON('/api/transactions/restore',{id});toast(r.detail,!!r.ok);await loadRestorePoints()}
  catch(e){toast(e.message,false)}
  finally{button.disabled=false;button.textContent='RESTAURAR'}
}
async function downloadOptimizationReport(id,button){
  button.disabled=true;
  try{
    const report=await getJSON('/api/reports/'+encodeURIComponent(id));
    const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='AZOR-relatorio-'+id+'.json';link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(e){toast(e.message,false)}
  finally{button.disabled=false}
}

// Desfazer um tweak sozinho. O botao so aparece quando o motor declara que existe
// codigo de reversao para ele - nunca por suposicao.
async function revertTweak(id,btn){
  if(!id)return;
  const old=btn?.textContent;if(btn){btn.disabled=true;btn.textContent='DESFAZENDO…'}
  try{
    const r=await postJSON('/api/action',{name:'revert_task',id});
    toast(r.detail||(r.ok?'Revertido.':'Não foi possível reverter.'),!!r.ok);
    await refreshSummary(false);
    try{S.analysis=await getJSON('/api/analyze?profile='+encodeURIComponent(S.quickProfile))}catch(e){}
    S.restorePoints=null;
    S.azorIndex=null;
    if(S.page==='restore')await loadRestorePoints();
    if(['arsenal','declutter'].includes(S.page))await loadArsenal(true);
    render();
  }catch(e){toast(e.message,false)}
  finally{if(btn){btn.disabled=false;btn.textContent=old}}
}

// Modo simulacao: a lista exata do que o botao Aplicar faria agora, sem fazer.
async function runSimulation(btn){
  const old=btn?.textContent;if(btn){btn.disabled=true;btn.textContent='SIMULANDO…'}
  try{
    const s=await getJSON('/api/optimization-simulate?profile='+encodeURIComponent(S.quickProfile));
    S.simulation=s;
    const group=(action)=>(s.steps||[]).filter(x=>x.action===action);
    const fix=(x)=>x.module==='repair';
    const row=(x)=>`<div class="analysis-row"><div><b>${esc(x.name)} <span class="risk ${x.risk==='low'?'low':'mid'}">${esc(String(x.risk_label||x.risk||'').toUpperCase())}</span></b><small>${esc(x.detail||'')}</small>${x.trade_off?`<small class="soft">Custo: ${esc(x.trade_off)}</small>`:''}</div><span class="pill ${fix(x)?'goodpill':x.reversible?'':'off'}">${fix(x)?'CONSERTO':x.reversible?'REVERSÍVEL':'SEM VOLTA'}</span></div>`;
    const applying=group('apply');
    const repairs=applying.filter(fix).length;
    const noWayBack=applying.filter(x=>!x.reversible&&!fix(x)).length;
    const section=(title,items)=>items.length?`<h3 class="section-title" style="margin-top:14px">${title} (${items.length})</h3><div class="action-list compact">${items.map(row).join('')}</div>`:'';
    openModal('Simulação — nada foi alterado',
      `<p class="section-sub">${esc(s.note||'')} Perfil resolvido: <b>${esc(profileLabel(s.resolved_profile||'safe'))}</b>.</p>`+
      (s.restart_count?`<p class="section-sub warn">${s.restart_count} item(ns) só valem por completo depois de reiniciar.</p>`:'')+
      (repairs?`<p class="section-sub">${repairs} conserto(s) de estrago deixado por outro programa. Eles devolvem o padrão do Windows e não entram no Desfazer.</p>`:'')+
      (noWayBack?`<p class="section-sub bad">${noWayBack} item(ns) desta lista não podem ser desfeitos.</p>`:'')+
      section('Seriam aplicados',applying)+
      section('Ficam de fora',group('skip'))+
      section('Continuam manuais',group('manual')));
  }catch(e){toast('Simulação falhou: '+e.message,false)}
  finally{if(btn){btn.disabled=false;btn.textContent=old}}
}

async function runAnalyze(){const b=$('#analyzeQuick');if(!b)return;const old=b.textContent;b.disabled=true;b.textContent='ANALISANDO…';try{const profile=S.quickProfile;const result=await getJSON('/api/analyze?profile='+encodeURIComponent(profile));if(S.quickProfile!==profile)return;S.analysis=result;render();toast('Análise concluída. O Azor separou o que já está aplicado, o que recomenda e o que não se aplica ao PC.',true)}catch(e){toast('Análise falhou: '+e.message,false)}finally{if($('#analyzeQuick')){$('#analyzeQuick').disabled=false;$('#analyzeQuick').textContent=old}}}

async function runCompetitiveSession(btn){
  if(S.competitiveSessionRunning)return;
  S.competitiveSessionRunning=true;S.sessionMeasurement=null;const old=btn?.textContent;if(btn){btn.disabled=true;btn.textContent='MEDINDO ANTES…'}
  let measured=false;
  try{
    try{S.latencyBaseline=await measureLatencyStableSample('SESSÃO • ANTES');S.latencyAfter=null;measured=true}catch(e){console.warn('Medição inicial da sessão',e)}
    if(btn)btn.textContent='APLICANDO PERFIL…';
    const r=await postJSON('/api/action',{name:'quick_optimize',profile:'competitive'});S.lastQuickResult=r;
    await refreshSummary(false);
    if(measured){
      if(btn)btn.textContent='MEDINDO DEPOIS…';await new Promise(r=>setTimeout(r,700));
      try{S.latencyAfter=await measureLatencyStableSample('SESSÃO • DEPOIS');S.measureResult=S.latencyAfter;S.sessionMeasurement={at:Date.now(),ok:true}}catch(e){console.warn('Medição final da sessão',e)}
    }
    try{S.analysis=await getJSON('/api/analyze?profile=competitive')}catch(e){}
    const failed=(r.results||[]).filter(x=>x.status==='failed');
    toast(failed.length?`Sessão concluída com ${failed.length} item(ns) para revisar.`:`Sessão competitiva aplicada${S.sessionMeasurement?' e medida':''}.`,failed.length===0);
    S.latencyProgress='';go('quick');
  }catch(e){toast('Sessão competitiva: '+e.message,false)}
  finally{S.competitiveSessionRunning=false;S.latencyProgress='';if(btn){btn.disabled=false;btn.textContent=old||'ϟ PREPARAR PARA JOGAR'}}
}
async function runQuickInput(btn){const old=btn?.textContent;if(btn){btn.disabled=true;btn.textContent='OTIMIZANDO INPUT…'}try{const ps=ensureInputProfiles();const kinds=['mouse','keyboard','controller'];let failed=0,verified=0,profileOnly=0;for(const kind of kinds){const preset=INPUT_PRESETS[kind].competitive;Object.assign(ps[kind][0],preset.values);S.inputSelected[kind]=0;S.inputPreset[kind]='competitive';const r=await postJSON('/api/action',{name:'apply_input_profile',kind,profile_index:0,profile:ps[kind][0]});failed+=Number(r.failed||0);verified+=Number(r.applied_verified||0);profileOnly+=Number(r.profile_only||0)}await refreshSummary(false);toast(`Input concluído: ${verified} ajuste(s) verificado(s), ${profileOnly} item(ns) dependem do hardware/driver, ${failed} falha(s).`,failed===0);render()}catch(e){toast('Input: '+e.message,false)}finally{const b=$('#quickInputOptimize');if(b){b.disabled=false;b.textContent=old||'OTIMIZAR INPUT COMPLETO'}}}

async function runQuick(){
 if(S.boost.running)return;
 const items=S.analysis?.items;
 if(!Array.isArray(items)||!items.length){toast('Analise o PC antes de aplicar.',false);return}
 if(!confirm('Aplicar as recomendações do perfil '+profileLabel(S.quickProfile)+'?\n\nO AZOR verificará compatibilidade e salvará o estado anterior. Algumas preferências podem afetar captura, notificações e consumo de energia, conforme o perfil.\n\nVocê poderá conferir o resultado e restaurar as alterações rastreadas.'))return;
 S.boost.running=true;S.lastQuickResult=null;
 const button=$('#runQuick');if(button){button.disabled=true;button.textContent='APLICANDO RECOMENDADAS…'}
 try{const result=await postJSON('/api/action',{name:'quick_optimize',profile:S.quickProfile},ACTION_TIMEOUT_MS);S.lastQuickResult=result;toast(result.detail,result.ok===true);try{await refreshSummary(false)}catch(e){toast('Resultado recebido; o painel não pôde ser atualizado agora.',false)}}
 catch(e){S.lastQuickResult={ok:null,detail:'A resposta não foi confirmada. Consulte o histórico antes de repetir.',results:[{name:'Comunicação com a execução',status:'unknown',detail:e.message}]};toast('Resultado ainda não confirmado. Confira o histórico antes de repetir. '+e.message,false)}
 finally{S.boost.running=false;render()}
}

async function measureLatencySample(iterations=140){const r=await postJSON('/api/measure-sleep',{interval_ms:1.0,iterations});return r.result}
async function measureLatencyStableSample(label='MEDINDO'){
  const runs=[];
  S.latencyProgress=`${label} • aquecendo medição`;if(S.page==='latency')render();
  await measureLatencySample(35);
  for(let i=0;i<5;i++){
    S.latencyProgress=`${label} • rodada ${i+1}/5`;if(S.page==='latency')render();
    runs.push(await measureLatencySample(140));
    if(i<4)await new Promise(r=>setTimeout(r,90));
  }
  return aggregateLatencyRuns(runs);
}
async function runLatencyBaseline(btn){
  if(S.latencyOptimizing)return;S.latencyOptimizing=true;const old=btn?.textContent;if(btn){btn.disabled=true;btn.textContent='MEDINDO…'}
  try{
    S.latencyAfter=null;
    S.latencyBaseline=await measureLatencyStableSample('MEDINDO ANTES');
    S.latencyProgress='Medição inicial concluída';render();
    toast(`Antes: média ${S.latencyBaseline.avg_ms} ms • P95 ${S.latencyBaseline.p95_ms} ms`,true);
  }catch(e){toast('Medição: '+e.message,false)}
  finally{
    S.latencyOptimizing=false;S.latencyProgress='';render();
    const b=$('#latencyBaseline');if(b){b.disabled=false;b.textContent=old||'1. MEDIR AGORA'}
  }
}
async function runLatencyOptimize(btn){
  if(S.latencyOptimizing)return;S.latencyOptimizing=true;const old=btn?.textContent;if(btn){btn.disabled=true;btn.textContent='OTIMIZANDO…'}
  try{
    if(!S.latencyBaseline)S.latencyBaseline=await measureLatencyStableSample('CRIANDO REFERÊNCIA');
    S.latencyProgress='Ativando Timer Resolution 0,5 ms';render();
    const timer=await postJSON('/api/action',{name:'timer_half'});if(!timer.ok)throw new Error(timer.detail||'O timer não pôde ser ativado.');
    S.latencyProgress='Aplicando AZOR FPS BOOST';render();
    const pwr=await postJSON('/api/action',{name:'power_max'});if(!pwr.ok)console.warn('AZOR FPS BOOST',pwr.detail);
    S.latencyProgress='Ativando AZOR Memory Engine';render();
    try{await postJSON('/api/action',{name:'launch_islc'})}catch(e){console.warn('Memory Engine',e)}
    S.latencyProgress='Aguardando o sistema estabilizar';render();
    await new Promise(r=>setTimeout(r,1000));await refreshSummary(false);
    S.latencyAfter=await measureLatencyStableSample('MEDINDO DEPOIS');S.measureResult=S.latencyAfter;
    S.latencyProgress='Comparação concluída';await refreshSummary(false);render();
    const score=latencyComposite();
    toast(score!=null&&score>0.5?`Métricas combinadas melhoraram ${score.toFixed(1)}%.`:'Comparação concluída. Confira os valores medidos.',true);
  }catch(e){toast('Latência: '+e.message,false)}
  finally{
    S.latencyOptimizing=false;
    setTimeout(()=>{S.latencyProgress='';if(S.page==='latency')render()},900);
    const b=$('#latencyOptimize');if(b){b.disabled=false;b.textContent=old||'2. OTIMIZAR E MEDIR DEPOIS'}
  }
}
async function runMeasure(){const b=$('#runMeasure');const interval=Number($('#sleepInterval').value)/10;const iterations=Number($('#sleepIter').value);b.disabled=true;b.textContent='MEDINDO…';try{const r=await postJSON('/api/measure-sleep',{interval_ms:interval,iterations});S.measureResult=r.result;render();toast(`Measure Sleep: média ${r.result.avg_ms} ms • jitter ${r.result.jitter_ms} ms`,true)}catch(e){toast(e.message,false)}finally{if($('#runMeasure')){$('#runMeasure').disabled=false;$('#runMeasure').textContent='◷ INICIAR MEASURE SLEEP'}}}
async function testPing(){const b=$('#testPing');b.disabled=true;b.textContent='TESTANDO…';try{S.lastPing=await postJSON('/api/ping',{host:'1.1.1.1'});render();toast(S.lastPing.avg_ms!=null?`Ping médio: ${S.lastPing.avg_ms} ms`:'Não foi possível medir o ping',S.lastPing.ok)}catch(e){toast(e.message,false)}finally{if($('#testPing')){$('#testPing').disabled=false;$('#testPing').textContent='TESTAR PING'}}}


async function loadGamesGpu(renderAfter=true){
  try{const r=await getJSON('/api/games-gpu');S.gamesGpu=r.games||[];S._gamesLoaded=true;if(renderAfter&&S.page==='games')render();}
  catch(e){if(renderAfter)toast('Jogos: '+e.message,false)}
}
async function chooseGameExe(btn){
  const old=btn?.textContent;if(btn){btn.disabled=true;btn.textContent='ABRINDO…'}
  try{const r=await postJSON('/api/action',{name:'pick_game_exe'});if(r.ok&&r.exe){S.selectedGameExe=r.exe;const input=$('#gameExePath');if(input)input.value=r.exe;toast('Executável selecionado.',true)}else if(r.detail&&r.detail!=='Nenhum executável foi selecionado.')toast(r.detail,false)}
  catch(e){toast('Seletor: '+e.message,false)}finally{if(btn){btn.disabled=false;btn.textContent=old||'ESCOLHER .EXE'}}
}
async function applyGameGpu(exe,btn){
  exe=String(exe||'').trim();if(!exe){toast('Selecione ou cole o caminho de um .exe de jogo.',false);return}
  const old=btn?.textContent;if(btn){btn.disabled=true;btn.textContent='VERIFICANDO…'}
  try{const r=await postJSON('/api/action',{name:'game_gpu_high',exe});S.gamesGpu=r.games||S.gamesGpu;S._gamesLoaded=true;toast(r.detail,!!r.ok);if(S.page==='games')render()}
  catch(e){toast('GPU do jogo: '+e.message,false)}finally{if(btn){btn.disabled=false;btn.textContent=old||'APLICAR'}}
}
async function restoreGameGpu(exe,btn){
  const old=btn?.textContent;if(btn){btn.disabled=true;btn.textContent='RESTAURANDO…'}
  try{const r=await postJSON('/api/action',{name:'game_gpu_restore',exe});S.gamesGpu=r.games||S.gamesGpu;S._gamesLoaded=true;toast(r.detail,!!r.ok);if(S.page==='games')render()}
  catch(e){toast('Restore GPU: '+e.message,false)}finally{if(btn){btn.disabled=false;btn.textContent=old||'RESTAURAR'}}
}
function bindGamesGpu(){
  const pick=$('#pickGameExe');if(pick)pick.onclick=()=>chooseGameExe(pick);
  const input=$('#gameExePath');if(input)input.oninput=()=>{S.selectedGameExe=input.value};
  const apply=$('#applyGameGpu');if(apply)apply.onclick=()=>applyGameGpu($('#gameExePath')?.value||S.selectedGameExe,apply);
  const refresh=$('#refreshGamesGpu');if(refresh)refresh.onclick=()=>loadGamesGpu(true);
  $$('[data-game-apply]').forEach(b=>b.onclick=()=>applyGameGpu(decodeURIComponent(b.dataset.gameApply||''),b));
  $$('[data-game-restore]').forEach(b=>b.onclick=()=>restoreGameGpu(decodeURIComponent(b.dataset.gameRestore||''),b));
}

function bindSettings(){
 const colors=$$('[data-color]');colors.forEach(c=>c.onclick=()=>{colors.forEach(x=>{x.classList.remove('selected');x.setAttribute('aria-pressed','false')});c.classList.add('selected');c.setAttribute('aria-pressed','true');S.settings.accent=c.dataset.color;applyAccent(c.dataset.color);scheduleSettingsSave()});
 for(const id of ['tipsToggle','animToggle','startupToggle','guardianToggle','gameMonitorToggle','dailyToggle','islcAutoToggle','latencyEngineToggle','watchdogTaskToggle','latencyGameOnlyToggle','islcGameOnlyToggle','gameModePersistToggle','dvrPersistToggle','suggestionsPersistToggle','transparencyPersistToggle','widgetsPersistToggle','startMinimizedToggle','gamePriorityToggle']){const el=$('#'+id);if(el)el.onclick=()=>{el.classList.toggle('on');el.setAttribute('aria-checked',String(el.classList.contains('on')));scheduleSettingsSave()}}
 const ms=$('#modeSelect');if(ms)ms.onchange=()=>scheduleSettingsSave();
 const mr=$('#monitorRange');if(mr){mr.oninput=()=>{$('#monitorV').textContent=mr.value+'s';scheduleSettingsSave()}}
 const logon=$('#logonAutoToggle');
 if(logon)logon.onclick=async()=>{
  const enable=!logon.classList.contains('on');logon.disabled=true;
  try{const r=await postJSON('/api/logon-autoapply',{enabled:enable,profile:PERFORMANCE_MODES[S.quickProfile]?S.quickProfile:'maximo'},ACTION_TIMEOUT_MS);
   toast(r.detail||(r.ok?'Preferência atualizada.':'Não foi possível alterar.'),r.ok===true)}
  catch(e){toast(e.message,false)}
  finally{S.autostart=null;render()}
 };
 const save=$('#saveSettings');if(save)save.onclick=saveSettings;
}
// A tela de Configuracoes tinha um botao SALVAR, e o cliente que mexia num
// interruptor e fechava o app perdia a mudanca sem nenhum aviso. Agora toda
// alteracao e gravada sozinha, com um atraso curto para nao gravar a cada pixel
// de um controle deslizante. O botao continua existindo, mas so para revalidar.
let autoSaveTimer=null, autoSaveInFlight=false;
function settingsPayload(){const on=(id,key)=>$('#'+id)?$('#'+id).classList.contains('on'):S.settings[key];return{
  mode:$('#modeSelect')?.value||S.settings.mode,accent:S.settings.accent,
  show_tips:on('tipsToggle','show_tips'),animations:on('animToggle','animations'),
  start_minimized:on('startMinimizedToggle','start_minimized'),
  monitor_interval:Number($('#monitorRange')?.value||S.settings.monitor_interval||1.5)};}

function markSaved(text){const el=$('#autoSaveMark');if(!el)return;el.textContent=text;el.classList.add('on');clearTimeout(el._tm);el._tm=setTimeout(()=>el.classList.remove('on'),2200);}

// Debounce curto: grava depois que a pessoa para de mexer, nao durante.
function scheduleSettingsSave(extra){
  clearTimeout(autoSaveTimer);
  autoSaveTimer=setTimeout(async()=>{
    if(autoSaveInFlight)return scheduleSettingsSave(extra);
    autoSaveInFlight=true;
    try{
      const r=await postJSON('/api/settings',{...settingsPayload(),...(extra||{})});
      S.settings={...S.settings,...(r.settings||{})};
      markSaved('salvo');
    }catch(e){markSaved('não salvou');console.warn('auto-save',e)}
    finally{autoSaveInFlight=false}
  },650);
}

// O Input Lab guardava o perfil so na memoria da pagina ate alguem clicar em
// aplicar. Fechou o app antes disso, perdeu.
function scheduleInputProfilesSave(){
  clearTimeout(autoSaveTimer);
  autoSaveTimer=setTimeout(async()=>{
    try{
      const r=await postJSON('/api/settings',{input_lab_profiles:S.settings.input_lab_profiles});
      S.settings={...S.settings,...(r.settings||{})};
      markSaved('perfil salvo');
    }catch(e){console.warn('auto-save input',e)}
  },700);
}

// O botao continua existindo, mas mudou de papel: salvar ja acontece sozinho a
// cada clique, e este aqui forca a revalidacao cara (plano de energia) que o
// auto-save de proposito nao roda.
async function saveSettings(){
  const data={...settingsPayload(),validate:true};
  try{const r=await postJSON('/api/settings',data);S.settings=r.settings;applyAccent(S.settings.accent);updateTop();const failed=(r.apply_results||[]).filter(x=>!x.ok);toast(failed.length?`Configurações salvas, mas ${failed.length} tarefa(s) não foram validadas.`:'Configurações salvas e tarefas validadas.',failed.length===0);render()}catch(e){toast(e.message,false)}}





let inputLiveBound=false;
let gamepadLoopStarted=false, gamepadVisualFrame=0, gamepadVisualTimer=0;
let lastGamepadSignature=null;
let inputVisualNodes=new Map(), inputReadoutNodes=new Map();
function rebuildInputVisualCache(){
  inputVisualNodes.clear();inputReadoutNodes.clear();lastLiveKeys=null;lastGamepadSignature=null;
  $$('.interactive-surface [data-pressable]').forEach(el=>{
    const kind=el.closest('.keyboard-svg')?'keyboard':el.closest('.mouse-svg')?'mouse':'controller';
    const key=kind+':'+el.dataset.pressable;
    if(!inputVisualNodes.has(key))inputVisualNodes.set(key,[]);
    inputVisualNodes.get(key).push(el);
  });
  $$('[data-readout]').forEach(el=>inputReadoutNodes.set(el.dataset.readout,el));
}
function visualNodes(name,kind){
  if(kind)return inputVisualNodes.get(kind+':'+name)||[];
  return ['keyboard','mouse','controller'].flatMap(k=>inputVisualNodes.get(k+':'+name)||[]);
}
function stopGamepadVisual(){
  clearTimeout(gamepadVisualTimer);cancelAnimationFrame(gamepadVisualFrame);
  gamepadVisualTimer=gamepadVisualFrame=0;gamepadLoopStarted=false;lastGamepadSignature=null;
  stopPadLive();
}
function syncGamepadVisual(){
  if(!isInputVisible() || !$('.controller-svg')){stopGamepadVisual();return}
  // A tela acabou de ser redesenhada: os radares nascem vazios e as métricas do
  // XInput voltam a ser pintadas com a última leitura.
  drawStickRadar('left');drawStickRadar('right');paintPadTexts(true);paintPadMetrics();
  startPadLive();
  if(gamepadLoopStarted)return;
  gamepadLoopStarted=true;gamepadVisualFrame=requestAnimationFrame(pollGamepadVisual);
}
function clearInputVisualState(){
  for(const nodes of inputVisualNodes.values())for(const el of nodes){el.classList.remove('pressed');if(el.classList.contains('analog-core'))el.style.transform=''}
  lastLiveKeys=null;lastGamepadSignature=null;
}
function resumeInputVisuals(){
  if(wantsNativeInput())startInputStream();
  syncGamepadVisual();
}
function pauseInputVisuals(){stopInputStream();stopGamepadVisual();clearInputVisualState();S.inputLive=null;setTriggerVisual('lt',0);setTriggerVisual('rt',0)}
function setTriggerVisual(key,value){
  const amount=Math.round(clamp(Number(value)||0,0,1)*100);
  const meter=$('[data-trigger-meter="'+key+'"]');
  if(meter){const width=amount+'%';if(meter.style.width!==width)meter.style.width=width}
  const text=$('[data-trigger-value="'+key+'"]');
  if(text&&text.textContent!==amount+'%')text.textContent=amount+'%';
  // O gatilho do desenho enche com a mesma pressão (92 = largura do gatilho no SVG).
  const fill=$('[data-trigger-fill="'+key+'"]');
  if(fill){const w=(92*amount/100).toFixed(1);if(fill.getAttribute('width')!==w)fill.setAttribute('width',w)}
}
const KEY_LABELS={
  Escape:'ESC',Backspace:'⌫',Tab:'TAB',CapsLock:'CAPS',Enter:'ENTER',
  ShiftLeft:'SHIFT',ShiftRight:'SHIFT',ControlLeft:'CTRL',ControlRight:'CTRL',
  MetaLeft:'WIN',MetaRight:'WIN',AltLeft:'ALT',AltRight:'ALT',Space:'SPACE',ContextMenu:'MENU',
  Minus:'-',Equal:'=',BracketLeft:'[',BracketRight:']',Backslash:'\\',Semicolon:';',Quote:"'",Comma:',',Period:'.',Slash:'/',
  // Mesmos rótulos que o monitor devolve por posição física (azor_input_monitor.SCAN_LABELS).
  Backquote:'`',IntlBackslash:'ISO',IntlRo:'RO',
  ArrowUp:'↑',ArrowDown:'↓',ArrowLeft:'←',ArrowRight:'→',Insert:'Ins',Delete:'Del',Home:'Home',End:'End',
  PageUp:'PgUp',PageDown:'PgDn',PrintScreen:'PrtSc',ScrollLock:'ScrLk',Pause:'Pause'
};
function keyLabelFromEvent(ev){
  const c=ev.code||'';
  if(KEY_LABELS[c])return KEY_LABELS[c];
  if(/^F([1-9]|1[0-2])$/.test(c))return c;
  if(/^Key[A-Z]$/.test(c))return c.slice(3);
  if(/^Digit[0-9]$/.test(c))return c.slice(5);
  return String(ev.key||'').length===1?String(ev.key).toUpperCase():'';
}
// Leitura textual ao lado do desenho: o cliente confere o que acendeu sem
// precisar olhar para o pixel certo.
function setReadout(key,text){
  const el=inputReadoutNodes.get(key);
  if(el&&el.textContent!==text){el.textContent=text;el.classList.add('hot');clearTimeout(el._tm);el._tm=setTimeout(()=>el.classList.remove('hot'),320)}
}
function stickText(x,y,clicked){
  if(clicked)return 'clique (L3/R3)';
  const mag=Math.hypot(x,y);
  if(mag<0.14)return 'centro';
  const dir=[Math.abs(y)>0.25?(y<0?'cima':'baixo'):'',Math.abs(x)>0.25?(x<0?'esquerda':'direita'):''].filter(Boolean).join('-');
  return `${dir||'movendo'} · ${Math.round(mag*100)}%`;
}
function pressVisual(name,on=true,kind){
  if(!name)return;
  for(const el of visualNodes(String(name),kind))if(el.classList.contains('pressed')!==!!on)el.classList.toggle('pressed',!!on);
}
const flashVisualTimers=new Map();
function flashVisual(name,ms=130){
  pressVisual(name,true,'mouse');clearTimeout(flashVisualTimers.get(name));
  flashVisualTimers.set(name,setTimeout(()=>{pressVisual(name,false,'mouse');flashVisualTimers.delete(name)},ms));
}
function setLiveText(kind,text,active=true){
  $$(`[data-live-kind="${kind}"]`).forEach(el=>{
    if(el.textContent!==text)el.textContent=text;
    const stage=el.closest('.input2d-stage,.periph-stage');
    if(stage && stage.classList.contains('live-active')!==!!active)stage.classList.toggle('live-active',!!active);
  });
}
function bindLiveInputOnce(){
  if(inputLiveBound)return; inputLiveBound=true;
  window.addEventListener('keydown',ev=>{if(!isInputVisible()||S.periphTab!=='keyboard')return;const label=keyLabelFromEvent(ev);if(label){pressVisual(label,true,'keyboard');setLiveText('keyboard',`Tecla ${label} pressionada`,true)}} ,true);
  window.addEventListener('keyup',ev=>{if(!isInputVisible()||S.periphTab!=='keyboard')return;const label=keyLabelFromEvent(ev);if(label){pressVisual(label,false,'keyboard');setLiveText('keyboard',`Tecla ${label} liberada`,false)}} ,true);
  window.addEventListener('mousedown',ev=>{if(!isInputVisible()||S.periphTab!=='mouse')return;const map={0:'left-click',1:'wheel',2:'right-click',3:'side-1',4:'side-2'};const name=map[ev.button];if(name){pressVisual(name,true);setLiveText('mouse',name==='left-click'?'Clique esquerdo':name==='right-click'?'Clique direito':name==='wheel'?'Clique da roda':`Botão lateral ${name==='side-1'?'1':'2'}`,true)}} ,true);
  window.addEventListener('mouseup',ev=>{if(!isInputVisible()||S.periphTab!=='mouse')return;const map={0:'left-click',1:'wheel',2:'right-click',3:'side-1',4:'side-2'};const name=map[ev.button];if(name){pressVisual(name,false);setLiveText('mouse','Mouse pronto',false)}} ,true);
  window.addEventListener('wheel',()=>{if(!isInputVisible()||S.periphTab!=='mouse')return;flashVisual('wheel',150);setLiveText('mouse','Scroll detectado',true);setTimeout(()=>setLiveText('mouse','Mouse pronto',false),180)},{passive:true,capture:true});
  let mouseMoveTm=0; window.addEventListener('mousemove',ev=>{if(!isInputVisible()||S.periphTab!=='mouse')return;const svg=$('.mouse-svg');if(!svg)return;const dx=clamp(ev.movementX||0,-10,10)*.32,dy=clamp(ev.movementY||0,-10,10)*.32;svg.style.transform=`translate(${dx}px,${dy}px)`;setLiveText('mouse','Movimento detectado',true);clearTimeout(mouseMoveTm);mouseMoveTm=setTimeout(()=>{const now=$('.mouse-svg');if(now)now.style.transform='';setLiveText('mouse','Mouse pronto',false)},90)},{passive:true,capture:true});
  window.addEventListener('gamepadconnected',ev=>setLiveText('controller',`Controle conectado: ${padLabel(ev.gamepad)}`,true));
  window.addEventListener('gamepaddisconnected',()=>setLiveText('controller','Controle desconectado',false));
  window.addEventListener('blur',pauseInputVisuals);
  window.addEventListener('focus',resumeInputVisuals);
}
function setStickVisual(name,x,y,pressed){
  // 14 px: o chapéu anda até a borda do poço sem sair do desenho.
  const dx=Math.round(clamp(Number(x)||0,-1,1)*14),dy=Math.round(clamp(Number(y)||0,-1,1)*14);
  visualNodes(name,'controller').filter(el=>el.classList.contains('analog-core')).forEach(el=>{
    el.classList.toggle('pressed',!!pressed);
    el.style.transform=`translate(${dx}px,${dy}px)${pressed?' scale(.96)':''}`;
  });
}
// ---------------------------------------------------------------------------
// Análise dos analógicos e dos gatilhos
//
// Rastro, deriva parado, circularidade e curso máximo saem dos valores que o
// controle entrega a esta janela, quadro a quadro. Nada é estimado: sem amostra
// suficiente, a tela diz "medindo" em vez de um número.
// ---------------------------------------------------------------------------
const PAD_BINS=72, PAD_REST_MS=1200, PAD_TRAIL_MS=320;
const PAD_TEST={left:null,right:null,lt:0,rt:0,textAt:0};
function padStick(side){
  return PAD_TEST[side]||(PAD_TEST[side]={bins:new Float32Array(PAD_BINS),restSum:0,restN:0,drift:null,
    movedAt:performance.now(),trail:[],x:0,y:0,pressed:false,dirty:true});
}
function resetPadTests(){
  PAD_TEST.left=PAD_TEST.right=null;PAD_TEST.lt=PAD_TEST.rt=0;
  drawStickRadar('left');drawStickRadar('right');paintPadTexts(true);
}
function feedStick(side,x,y,pressed,now){
  const t=padStick(side),mag=Math.hypot(x,y);
  if(x!==t.x||y!==t.y||pressed!==t.pressed){t.x=x;t.y=y;t.pressed=pressed;t.dirty=true;t.trail.push([x,y,now])}
  // Deriva: só conta com o analógico solto há PAD_REST_MS. Qualquer toque zera a
  // janela. O resultado sai por TEMPO parado (meio segundo), não por número de
  // quadros: com a janela em segundo plano o navegador cai para 1 ou 2 quadros/s.
  if(mag>.3||pressed){t.movedAt=now;t.restSum=0;t.restN=0;t.restFrom=0}
  else if(now-t.movedAt>PAD_REST_MS){
    if(!t.restFrom)t.restFrom=now;
    t.restSum+=mag;t.restN++;
    if(t.restN>=5&&now-t.restFrom>=500)t.drift=t.restSum/t.restN;
    if(t.restN>=2400){t.restSum/=2;t.restN/=2}
  }
  // Circularidade: o maior raio alcançado em cada fatia de 5 graus.
  if(mag>.5){const bin=Math.min(PAD_BINS-1,Math.floor((Math.atan2(y,x)+Math.PI)/(2*Math.PI)*PAD_BINS));if(mag>t.bins[bin])t.bins[bin]=mag}
  while(t.trail.length&&(t.trail.length>40||now-t.trail[0][2]>PAD_TRAIL_MS)){t.trail.shift();t.dirty=true}
}
function padCircularity(t){
  let n=0,err=0,sum=0;
  for(const r of t.bins){if(r>0){n++;err+=Math.abs(r-1);sum+=r}}
  return {filled:n,ready:n>=Math.round(PAD_BINS*.85),error:n?err/n:null,avg:n?sum/n:null};
}
function rgbaOf(hex,alpha){return `rgba(${hexRgb(hex)},${alpha})`}
function drawStickRadar(side){
  const c=$(`[data-stick-radar="${side}"]`);if(!c||!c.getContext)return;
  const t=padStick(side);t.dirty=false;
  const css=c.clientWidth||176,dpr=window.devicePixelRatio||1,px=Math.round(css*dpr);
  if(c.width!==px){c.width=px;c.height=px}
  const g=c.getContext('2d');g.setTransform(dpr,0,0,dpr,0,0);g.clearRect(0,0,css,css);
  const cx=css/2,cy=css/2,R=css/2-12;
  const acc=(getComputedStyle(document.documentElement).getPropertyValue('--accent')||'').trim()||'#ff2fc8';
  g.fillStyle='#0c0c11';g.beginPath();g.arc(cx,cy,R+8,0,Math.PI*2);g.fill();
  g.strokeStyle='rgba(255,255,255,.08)';g.lineWidth=1;
  g.beginPath();g.moveTo(cx-R,cy);g.lineTo(cx+R,cy);g.moveTo(cx,cy-R);g.lineTo(cx,cy+R);g.stroke();
  for(const k of [.5,1]){g.beginPath();g.arc(cx,cy,R*k,0,Math.PI*2);g.stroke()}
  const p=currentProfile('controller');
  const dz=clamp(Number(side==='left'?p.left_deadzone:p.right_deadzone)||0,0,40)/100;
  if(dz>0){g.save();g.fillStyle=rgbaOf(acc,.12);g.strokeStyle=rgbaOf(acc,.6);g.setLineDash([3,3]);
    g.beginPath();g.arc(cx,cy,R*dz,0,Math.PI*2);g.fill();g.stroke();g.restore()}
  const circ=padCircularity(t);
  if(circ.filled>=8){
    g.strokeStyle='rgba(255,255,255,.42)';g.lineWidth=1.3;g.beginPath();let pen=false;
    for(let i=0;i<PAD_BINS;i++){const r=t.bins[i];if(!r){pen=false;continue}
      const a=(i+.5)/PAD_BINS*2*Math.PI-Math.PI,x=cx+Math.cos(a)*Math.min(r,1.5)*R,y=cy+Math.sin(a)*Math.min(r,1.5)*R;
      if(pen)g.lineTo(x,y);else{g.moveTo(x,y);pen=true}}
    g.stroke();
  }
  const tr=t.trail;
  if(tr.length>1){g.lineCap='round';for(let i=1;i<tr.length;i++){const k=i/tr.length;g.strokeStyle=rgbaOf(acc,k*.75);g.lineWidth=1+k*2.6;
    g.beginPath();g.moveTo(cx+tr[i-1][0]*R,cy+tr[i-1][1]*R);g.lineTo(cx+tr[i][0]*R,cy+tr[i][1]*R);g.stroke()}}
  const x=cx+clamp(t.x,-1.5,1.5)*R,y=cy+clamp(t.y,-1.5,1.5)*R;
  g.fillStyle=t.pressed?'#ffffff':acc;g.beginPath();g.arc(x,y,6,0,Math.PI*2);g.fill();
  if(t.pressed){g.strokeStyle=acc;g.lineWidth=2;g.beginPath();g.arc(x,y,10.5,0,Math.PI*2);g.stroke()}
}
function setNodeText(sel,text,cls,on){
  const el=$(sel);if(!el)return;
  if(el.textContent!==text)el.textContent=text;
  if(cls&&el.classList.contains(cls)!==!!on)el.classList.toggle(cls,!!on);
}
function paintPadTexts(force){
  const now=performance.now();
  if(!force&&now-PAD_TEST.textAt<200)return;
  PAD_TEST.textAt=now;
  const p=currentProfile('controller');
  for(const side of ['left','right']){
    const t=padStick(side),dzPct=Number(side==='left'?p.left_deadzone:p.right_deadzone)||0;
    // Y invertido para leitura humana: para cima é positivo.
    setNodeText(`[data-stick-x="${side}"]`,t.x.toFixed(3));
    setNodeText(`[data-stick-y="${side}"]`,(t.y?-t.y:0).toFixed(3));
    const d=t.drift,pct=d==null?null:d*100,over=pct!=null&&pct>dzPct;
    setNodeText(`[data-pad-drift="${side}"]`,pct==null?'medindo…':`${pct.toFixed(1)}%`,'bad',over);
    setNodeText(`[data-pad-drift-note="${side}"]`,pct==null?'Solte o analógico por 2 segundos.'
      :over?`Acima da zona morta do perfil (${dzPct}%): o jogo pode andar sozinho.`
      :`Dentro da zona morta do perfil (${dzPct}%).`);
    const c=padCircularity(t);
    setNodeText(`[data-pad-circ="${side}"]`,c.ready?`${(c.error*100).toFixed(1)}% de erro`:`${Math.round(c.filled/PAD_BINS*100)}% da volta`,
      'bad',c.ready&&c.error>=.1&&c.avg<=1.08);
    setNodeText(`[data-pad-circ-note="${side}"]`,!c.ready?'Gire encostado na borda, uma volta inteira.'
      :c.avg>1.08?'Saída quadrada: nas diagonais o analógico passa de 100%. É do firmware, não defeito.'
      :c.error<.06?'Círculo regular.':'Borda irregular: pode ser desgaste do analógico ou calibração.');
  }
  for(const k of ['lt','rt'])setNodeText(`[data-trigger-max="${k}"]`,PAD_TEST[k]>0?`máx ${Math.round(PAD_TEST[k]*100)}%`:'máx —');
}

// ---------------------------------------------------------------------------
// Leitura do XInput pelo servidor: taxa de envio medida, bateria e fabricante.
// Só roda com a aba Controle aberta e em foco; cada pedido é também o sinal de
// vida que mantém a coleta ligada no servidor.
// ---------------------------------------------------------------------------
let padLiveTimer=0, padLiveRunning=false;
function wantsPadLive(){return isInputVisible()&&S.periphTab==='controller'&&!!$('.controller-svg')}
function startPadLive(){if(padLiveRunning||padLiveTimer||!wantsPadLive())return;padLiveTimer=setTimeout(pollPadLive,0)}
function stopPadLive(){
  clearTimeout(padLiveTimer);padLiveTimer=0;
  if(padLiveRunning){padLiveRunning=false;postJSON('/api/action',{name:'gamepad_monitor_stop'}).catch(()=>{})}
}
async function pollPadLive(){
  padLiveTimer=0;
  if(!wantsPadLive()){stopPadLive();return}
  padLiveRunning=true;
  try{S.padLive=await getJSON('/api/gamepad-live');paintPadMetrics()}catch(e){}
  if(padLiveRunning&&wantsPadLive())padLiveTimer=setTimeout(pollPadLive,300);
}
function paintPadMetrics(){
  const hz=$('[data-pad-metric="hz"]');if(!hz)return;
  const live=S.padLive;if(!live||!Array.isArray(live.slots))return;
  const slot=padSlot(),card=$('[data-pad-card="hz"]');
  const pol=slot&&slot.polling;
  let value,detail,good=false;
  if(!live.available){value='não disponível';detail=live.detail||'O XInput não respondeu neste Windows.'}
  else if(!slot){value='sem controle';detail='Nenhum controle no XInput. Controle só-HID acende o desenho, mas não tem contador de pacotes.'}
  else if(pol&&pol.hz){value=`${Math.round(pol.hz)} Hz`;good=pol.confidence==='measured';
    detail=`${pol.nominal_hz?`Compatível com ${pol.nominal_hz} Hz. `:''}${pol.detail||''}`}
  else{value='medindo…';detail=(pol&&pol.detail)||'Gire um analógico em círculos, sem parar.'}
  setNodeText('[data-pad-metric="hz"]',value);
  setNodeText('[data-pad-metric="hz-detail"]',detail);
  if(card){card.classList.toggle('good',good);card.classList.remove('off')}
  const bat=slot&&slot.battery;
  setNodeText('[data-pad-metric="battery"]',!slot?'—':!bat?'não informada':bat.wired?'com fio':(bat.level?bat.level.charAt(0).toUpperCase()+bat.level.slice(1):'não informada'));
  setNodeText('[data-pad-metric="battery-detail"]',!slot?'Conecte o controle.':!bat?'O XInput não devolveu a bateria deste controle.'
    :bat.wired?'Ligado por cabo: não há bateria para medir.':`Tipo: ${bat.type}. O XInput só informa quatro níveis.`);
  if(slot&&slot.vendor)setNodeText('[data-pad-metric="vendor"]',slot.vendor);
}

function pollGamepadVisual(){
  gamepadVisualFrame=0;gamepadVisualTimer=0;
  if(!isInputVisible() || !$('.controller-svg')){stopGamepadVisual();return}
  let connected=false;
  try{
    const pads=navigator.getGamepads?navigator.getGamepads():[];
    const chosen=$('#gamepadDevice');
    const index=chosen?.value??'auto';
    const gp=index==='auto'?[...pads].find(Boolean):pads[Number(index)];
    if(gp&&gp.connected!==false){
      connected=true;
      const b=gp.buttons||[], ax=gp.axes||[]; const on=i=>!!(b[i]&&(b[i].pressed||b[i].value>.18));
      const signature=JSON.stringify([gp.index,b.map(x=>[x.pressed,x.value]),ax]);
      if(signature!==lastGamepadSignature){
        lastGamepadSignature=signature;
        [['A',0],['B',1],['X',2],['Y',3],['lb',4],['rb',5],['lt',6],['rt',7],['BACK',8],['START',9],['home',16]].forEach(([n,i])=>pressVisual(n,on(i)));
        // Cada direcao acende sozinha: o D-Pad deixou de ser um bloco unico.
        [['UP',12],['DOWN',13],['LEFT',14],['RIGHT',15]].forEach(([n,i])=>pressVisual(n,on(i)));
        $$('[data-pad-chip]').forEach(el=>{const lit=on(Number(el.dataset.padChip));if(el.classList.contains('on')!==lit)el.classList.toggle('on',lit)});
        setReadout('dpad', [['UP','cima'],['DOWN','baixo'],['LEFT','esquerda'],['RIGHT','direita']]
          .filter(([n],k)=>on(12+k)).map(([,t])=>t).join(' + ') || 'solto');
        const faceNames=padVariant()==='ps5'?{3:'△',1:'○',2:'□',0:'✕'}:{3:'Y',1:'B',2:'X',0:'A'};
        setReadout('face', [3,1,2,0].filter(i=>on(i)).map(i=>faceNames[i]).join(' + ') || 'nenhum');
        setStickVisual('stick-left',ax[0]||0,ax[1]||0,on(10)); setStickVisual('stick-right',ax[2]||0,ax[3]||0,on(11));
        setReadout('stick-left', stickText(ax[0]||0,ax[1]||0,on(10)));
        setReadout('stick-right', stickText(ax[2]||0,ax[3]||0,on(11)));
        const activity=b.some(x=>x&&(x.pressed||x.value>.18))||ax.some(x=>Math.abs(x)>.12);
        setTriggerVisual('lt',b[6]?.value);setTriggerVisual('rt',b[7]?.value);
        setLiveText('controller',activity?`Entrada recebida · ${padLabel(gp)}`:`Conectado · ${padLabel(gp)}`,activity);
      }
      // A análise roda todo quadro (o repouso é medido no tempo), mas só pinta
      // fora do SVG: canvas dos radares e textos dos cartões.
      const now=performance.now();
      feedStick('left',ax[0]||0,ax[1]||0,on(10),now);
      feedStick('right',ax[2]||0,ax[3]||0,on(11),now);
      const lv=Number(b[6]?.value)||0,rv=Number(b[7]?.value)||0;
      if(lv>PAD_TEST.lt)PAD_TEST.lt=lv;if(rv>PAD_TEST.rt)PAD_TEST.rt=rv;
      if(padStick('left').dirty)drawStickRadar('left');
      if(padStick('right').dirty)drawStickRadar('right');
      paintPadTexts(false);
    }else if(lastGamepadSignature!=='disconnected'){
      clearInputVisualState();lastGamepadSignature='disconnected';
      for(const key of ['stick-left','stick-right','face','dpad'])setReadout(key,'Não conectado');
      $$('[data-pad-chip].on').forEach(el=>el.classList.remove('on'));
      setTriggerVisual('lt',0);setTriggerVisual('rt',0);
      setLiveText('controller','Conecte o controle e pressione um botão',false);
    }
  }catch(e){console.warn('Gamepad visual',e)}
  if(!gamepadLoopStarted)return;
  // Conectado: lê a cada quadro da tela (60, 144, 180 Hz - o que o monitor der).
  // Antes era um quadro MAIS 16 ms de espera, o que dava ~30 leituras por segundo.
  if(connected)gamepadVisualFrame=requestAnimationFrame(pollGamepadVisual);
  else gamepadVisualTimer=setTimeout(()=>{if(gamepadLoopStarted)gamepadVisualFrame=requestAnimationFrame(pollGamepadVisual)},1000);
}
function bindPressableSurfaces(){
  $$('.interactive-surface .pressable').forEach(el=>{
    const arm=()=>{el.classList.add('pressed'); clearTimeout(el._pressTm); el._pressTm=setTimeout(()=>el.classList.remove('pressed'),220)};
    el.onpointerdown=(ev)=>{ev.preventDefault(); arm()};
    el.onclick=(ev)=>{ev.preventDefault(); arm()};
    el.onpointerup=()=>{clearTimeout(el._pressTm); el._pressTm=setTimeout(()=>el.classList.remove('pressed'),150)};
    el.onpointerleave=()=>{clearTimeout(el._pressTm); el._pressTm=setTimeout(()=>el.classList.remove('pressed'),110)};
  });
}

async function saveInputProfiles(silent=false){
  try{
    const r=await postJSON('/api/settings',{input_lab_profiles:ensureInputProfiles()});
    S.settings={...S.settings,...(r.settings||{})};
    if(!silent)toast('Perfis do Input Lab salvos.',true);
  }catch(e){if(!silent)toast('Perfis: '+e.message,false);throw e}
}
function updateInputProfileValue(kind,key,value){const p=currentProfile(kind);if(key in p)p[key]=value;ensureInputProfiles()[kind][S.inputSelected[kind]||0]=p;scheduleInputProfilesSave();}
function applyInputPreset(kind,id){const preset=INPUT_PRESETS?.[kind]?.[id];if(!preset)return;const profile=currentProfile(kind);Object.assign(profile,preset.values);ensureInputProfiles()[kind][S.inputSelected[kind]||0]=profile;S.inputPreset[kind]=id;scheduleInputProfilesSave();render();toast(`Perfil ${preset.title} preparado e salvo. Clique em aplicar para gravar no Windows.`,true)}
async function handleInputAction(action,kind,btn){if(action==='refresh-devices')return refreshDevices();if(action==='save-profile')return saveInputProfiles();if(action==='apply-profile'){const old=btn?.textContent;if(btn){btn.disabled=true;btn.textContent='APLICANDO…'}try{await saveInputProfiles(true);const res=await postJSON('/api/action',{name:'apply_input_profile',kind,profile_index:S.inputSelected[kind]||0,profile:currentProfile(kind)});const details=(res.results||[]).map(x=>`<li><b>${esc(x.name||'Etapa')}</b> — ${esc(x.detail||'')}</li>`).join(''); if(details)openModal('Aplicação do perfil',`<ul class="modal-list">${details}</ul>`); toast(res.detail||'Perfil processado.',!!res.ok);await refreshSummary(false);render();}catch(e){toast('Input Lab: '+e.message,false)}finally{if(btn){btn.disabled=false;btn.textContent=old||'APLICAR PERFIL'}}}}
function bindInputLab(){
  const picker=$('#gamepadDevice');if(picker)picker.onchange=()=>{S.padDeviceIndex=picker.value;lastGamepadSignature=null;syncGamepadVisual()};
  bindLiveInputOnce();
  bindPressableSurfaces();
  $$('[data-input-device-tab]').forEach(b=>b.onclick=()=>{S.inputDeviceTab=b.dataset.inputDeviceTab||'mouse';render()});
  $$('[data-periph-tab]').forEach(b=>b.onclick=()=>{S.periphTab=b.dataset.periphTab;render()});
  // Troca de aparencia: so redesenha. Nao toca em driver nem no dispositivo.
  $$('[data-pad-skin]').forEach(b=>b.onclick=()=>{S.padSkin=b.dataset.padSkin;render()});
  $$('[data-kb-format]').forEach(b=>b.onclick=()=>{S.kbFormat=b.dataset.kbFormat;render()});
  const ptr=$('#padTestReset');if(ptr)ptr.onclick=resetPadTests;
  const ctr=$('#clickTestReset');if(ctr)ctr.onclick=()=>{const m=S.inputLive?.mouse||{};S.clickBase={clicks:{...(m.clicks||{})},chatter:{...(m.chatter||{})}};S.cpsTimes=[];S.cpsMax=0;S._clickTotal=0;if(S.inputLive)paintInputLabs(S.inputLive);else render()};
  const rr=$('#rolloverReset');if(rr)rr.onclick=()=>{S.kbMax=0;S.kbPressBase=S.inputLive?.keyboard?.press_count||0;setNodeText('[data-kb-max]','0');setNodeText('[data-kb-presses]','0')};
  const orm=$('#openRemap');if(orm)orm.onclick=openRemapModal;
  $$('[data-input-preset]').forEach(b=>b.onclick=()=>{const [kind,id]=String(b.dataset.inputPreset||'').split(':');applyInputPreset(kind,id)});
  $$('[data-input-profile]').forEach(b=>b.onclick=()=>{const [kind,idx]=String(b.dataset.inputProfile||'').split(':');S.inputSelected[kind]=Number(idx)||0;S.inputPreset[kind]='custom';render()});
  $$('[data-input-slider]').forEach(i=>{i.oninput=()=>{const [kind,key]=String(i.dataset.inputSlider||'').split(':');const v=Number(i.value);updateInputProfileValue(kind,key,v);S.inputPreset[kind]='custom';const value=i.closest('.field')?.querySelector('.field-head span:last-child');if(value)value.textContent=`${i.value}${i.dataset.inputSuffix||''}`};i.onchange=()=>render()});
  $$('[data-input-select]').forEach(s=>s.onchange=()=>{const [kind,key]=String(s.dataset.inputSelect||'').split(':');updateInputProfileValue(kind,key,s.value);S.inputPreset[kind]='custom';render()});
  $$('[data-input-toggle]').forEach(t=>t.onclick=()=>{t.classList.toggle('on');const [kind,key]=String(t.dataset.inputToggle||'').split(':');updateInputProfileValue(kind,key,t.classList.contains('on'));S.inputPreset[kind]='custom';render()});
  $$('[data-input-hz]').forEach(b=>b.onclick=()=>{const [kind,hz]=String(b.dataset.inputHz||'').split(':');updateInputProfileValue(kind,'overclock_hz',Number(hz)||1000);updateInputProfileValue(kind,'poll_rate',Number(hz)||1000);S.inputPreset[kind]='custom';render()});
  $$('[data-input-action]').forEach(b=>b.onclick=()=>{const [action,kind]=String(b.dataset.inputAction||'').split(':');handleInputAction(action,kind,b)});
}

async function refreshDevices(){
  const b=$('#refreshDevices');const old=b?.textContent;if(b){b.disabled=true;b.textContent='DETECTANDO…'}
  try{
    const r=await getJSON('/api/devices');
    S.summary=S.summary||{};S.summary.devices=r.devices||{keyboard:[],mouse:[],controller:[]};S.summary.device_count=r.device_count||0;S.summary.device_detection=r.detection||{};
    render();
    const counts=S.summary.devices;const msg=`Teclado: ${(counts.keyboard||[]).length} • Mouse: ${(counts.mouse||[]).length} • Controle: ${(counts.controller||[]).length}`;
    toast(msg,true);
  }catch(e){toast('Detecção de dispositivos: '+e.message,false)}
  finally{const x=$('#refreshDevices');if(x){x.disabled=false;x.textContent=old||'↻ ATUALIZAR DETECÇÃO'}}
}

async function refreshSummary(doRender=true){if(S.boost.running)doRender=false;try{S.summary=await getJSON('/api/summary');S.settings={...S.settings,...(S.summary.settings||{})};ensureInputProfiles();applyAccent(S.settings.accent);updateTop();if(doRender)render()}catch(e){$('#engineStatus').textContent='Backend indisponível';$('#topStatus').textContent='Modo preview';console.warn(e);
  // Repassa o erro: quem agenda o proximo poll precisa saber que falhou
  // para aplicar backoff. Engolindo o erro aqui, o loop reencostava no
  // backend morto na velocidade total, para sempre.
  throw e}}
async function refreshMonitor(doRender=true){try{
 S.monitor=await getJSON('/api/monitor');pushHistory();
 const canRender=!S.boost.running&&(S.page==='monitor'||S.page==='home'||(S.page==='latency'&&!S.latencyOptimizing&&!S.competitiveSessionRunning));
 if(doRender&&canRender){
  if(S.page==='home'){
   const fields=$$('.hero-side .score strong'),bars=$$('.hero-side .score-bar>span'),values=[S.monitor.cpu?.usage,S.monitor.ram?.percent,S.monitor.gpu?.available?S.monitor.gpu?.usage:null];
   values.forEach((value,i)=>{if(fields[i])fields[i].textContent=fmt(value,'%');if(bars[i])bars[i].style.width=(value!=null&&Number.isFinite(Number(value))?clamp(Number(value),0,100):0)+'%'});
  }else render();
 }
}catch(e){console.warn('monitor',e);throw e}}
function pushHistory(){const m=S.monitor||{};if(m.loading||m.stale||m.paused)return;for(const [k,v] of [['cpu',m.cpu?.usage],['gpu',m.gpu?.available?m.gpu?.usage:null],['ram',m.ram?.percent],['net',m.network?.down_mbps]]){if(v!=null&&Number.isFinite(Number(v))){S.history[k].push(Number(v));if(S.history[k].length>70)S.history[k].shift()}}}
async function loadNetwork(){try{S._network=await getJSON('/api/network');if(S.page==='network')renderNetworkOnly()}catch(e){console.warn(e)}}
function renderNetworkOnly(){const old=S.page;S.page='network';$('#view').innerHTML=renderNetwork();bindCommon();S.page=old}
async function loadLogs(){try{const j=await getJSON('/api/logs');const el=$('#logText');if(el)el.textContent=j.text||'Nenhum log ainda.'}catch(e){const el=$('#logText');if(el)el.textContent=e.message}}
async function loadGameDiag(doRender=false){try{S.gameDiag=await getJSON('/api/game-diagnostic');if(doRender&&S.page==='gameDiag')render()}catch(e){console.warn('game diagnostic',e)}}
async function loadGameReports(){try{const r=await getJSON('/api/game-diagnostic/reports');S.gameReports=r.reports||[];if(S.page==='gameDiag')render()}catch(e){console.warn('game reports',e)}}
async function setupFrameCapture(btn){const old=btn?.textContent;if(btn){btn.disabled=true;btn.textContent='ATIVANDO…'}try{const r=await postJSON('/api/game-diagnostic/setup-frame-capture',{});toast(r.detail||'Captura configurada.',!!r.ok);await loadGameDiag(false);if(S.page==='gameDiag')render()}catch(e){toast('Captura de FPS: '+e.message,false)}finally{const x=$('#setupFrameCapture');if(x){x.disabled=false;x.textContent=old||'ATIVAR FPS / 1% LOW / FRAMETIME'}}}
async function startGameDiag(label,btn){const old=btn?.textContent;const customer=$('#gameDiagCustomer')?.value?.trim()||'';if(btn){btn.disabled=true;btn.textContent='INICIANDO…'}try{const r=await postJSON('/api/game-diagnostic/start',{label,customer});S.gameDiag=r.status||S.gameDiag;toast(r.detail||'Diagnóstico iniciado.',!!r.ok);if(S.page==='gameDiag')render()}catch(e){toast('Diagnóstico em jogo: '+e.message,false)}finally{const x=label==='antes'?$('#gameDiagBefore'):$('#gameDiagAfter');if(x){x.disabled=!!S.gameDiag?.running;x.textContent=old||x.textContent}}}
async function stopGameDiag(btn){const old=btn?.textContent;if(btn){btn.disabled=true;btn.textContent='FINALIZANDO…'}try{const r=await postJSON('/api/game-diagnostic/stop',{});S.gameDiag=r.status||S.gameDiag;toast(r.detail||'Coleta finalizada.',!!r.ok);await loadGameReports();await loadGameDiag(false);if(S.page==='gameDiag')render()}catch(e){toast('Finalização: '+e.message,false)}finally{const x=$('#gameDiagStop');if(x){x.textContent=old||'FINALIZAR ANÁLISE'}}}
async function loadStutter(){const b=$('#runStutterDiag');if(b){b.disabled=true;b.textContent='ANALISANDO…'}try{S.stutter=await getJSON('/api/stutter');if(S.page==='stutter')render();toast('Diagnóstico de stutter concluído.',!!S.stutter?.ok)}catch(e){toast('Stutter Lab: '+e.message,false)}finally{const x=$('#runStutterDiag');if(x){x.disabled=false;x.textContent='↻ ANALISAR STUTTER'}}}
async function runStutterFix(btn){const old=btn?.textContent;if(btn){btn.disabled=true;btn.textContent='APLICANDO…'}try{const r=await postJSON('/api/action',{name:'stutter_safe_fix'});toast(r.detail||'Correção concluída.',!!r.ok);S.stutter=await getJSON('/api/stutter');if(S.page==='stutter')render()}catch(e){toast('Correção: '+e.message,false)}finally{const x=$('#applyStutterFix');if(x){x.disabled=false;x.textContent=old||'APLICAR CORREÇÕES SEGURAS'}}}
async function loadHealth(){try{S.health=await getJSON('/api/health');if(S.page==='guardian')render()}catch(e){toast('Health Check: '+e.message,false)}}
async function loadMaintenance(){try{S.maintenance=await getJSON('/api/maintenance');if(S.page==='maintenance')render()}catch(e){toast('Manutenção: '+e.message,false)}}
async function loadBios(){try{S.bios=await getJSON('/api/bios');if(S.page==='bios')render()}catch(e){toast('BIOS: '+e.message,false)}}
async function loadBiosCopilot(){try{S.biosCopilot=await getJSON('/api/bios-copilot');if(S.page==='bios')render()}catch(e){toast('BIOS: '+e.message,false)}}
// The heavy sections each cost a separate PowerShell round trip, so waiting for
// all of them before painting left the page skeletonised for ten seconds or more.
// Fast reads land first and every slow section repaints as soon as it arrives.
async function loadHardware(force=false){
  const q=force?'?force=1':'';
  S.hardware=S.hardware||{};
  const paint=()=>{if(S.page==='hardware')render()};
  const section=async(key,url)=>{
    try{S.hardware[key]=await getJSON(url);paint()}
    catch(e){console.warn('hardware section '+key,e)}
  };
  try{
    const [profile,monitor]=await Promise.all([
      getJSON('/api/hardware-profile'+q).catch(()=>({})),
      getJSON('/api/monitor').catch(()=>({})),
    ]);
    S.hardware.profile=profile;S.hardware.monitor=monitor;paint();
  }catch(e){}
  section('bios','/api/bios').then(()=>{
    if(S.hardware.bios&&S.hardware.bios.hardware)S.hardware.bios=S.hardware.bios.hardware;paint();
  });
  getJSON('/api/thermal').then(t=>{S.thermal=t;paint()}).catch(()=>{});
  section('azor_windows','/api/azor-windows');
  section('startup','/api/startup');
  section('storage','/api/storage-health'+q);
  section('drivers','/api/drivers'+q);
}
async function toggleBiosCheck(key,done,el){
  try{el?.classList.toggle('on',done);await postJSON('/api/bios-checklist',{key,done});S.biosCopilot=await getJSON('/api/bios-copilot');render();
    toast(done?'Marcado. Depois de reiniciar, o AZOR relê e confirma se a mudança pegou.':'Marcação removida.',true)}
  catch(e){toast('Checklist: '+e.message,false)}
}
async function toggleStartupItem(scope,name,enabled,btn){
  const old=btn?.textContent;if(btn){btn.disabled=true;btn.textContent='APLICANDO…'}
  try{
    const r=await postJSON('/api/action',{name:'startup_toggle',scope,name:decodeURIComponent(name),enabled});
    if(r.startup&&S.hardware)S.hardware.startup=r.startup;
    toast(r.detail||'Item atualizado.',!!r.ok);
    if(S.page==='hardware')render();
  }catch(e){toast('Inicialização: '+e.message,false)}
  finally{if(btn){btn.disabled=false;btn.textContent=old}}
}
function updateTop(){const sm=S.summary||{};$('#modeChip').textContent=`Perfil: ${profileLabel(S.quickProfile)}`;$('#windowsChip').textContent=(sm.windows||'Windows').includes('Windows-11')?'Windows 11':(sm.windows||'Windows').includes('Windows-10')?'Windows 10':'Windows';$('#adminChip').textContent=sm.admin?'Administrador':'Permissão limitada';$('#engineStatus').textContent='Engine conectado';$('#topStatus').textContent='Sistema conectado'}

function drawUsageChart(){const c=$('#usageChart');if(!c)return;drawLines(c,[{data:S.history.cpu,color:'#ff5cd6'},{data:S.history.gpu,color:'#a08cff'},{data:S.history.ram,color:'#56d6a8'}],0,100)}
function drawSleepChart(){const c=$('#sleepChart');if(!c||!S.measureResult)return;const data=S.measureResult.samples||[];const max=Math.max(...data,S.measureResult.requested_ms*1.25);drawLines(c,[{data,color:'#2bd4ff'}],0,max)}
function drawLines(canvas,series,min,max){const dpr=window.devicePixelRatio||1;const rect=canvas.getBoundingClientRect();canvas.width=Math.max(10,rect.width*dpr);canvas.height=Math.max(10,rect.height*dpr);const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);const w=rect.width,h=rect.height;ctx.clearRect(0,0,w,h);ctx.strokeStyle='rgba(255,255,255,.06)';ctx.lineWidth=1;for(let i=0;i<=4;i++){let y=10+(h-20)*i/4;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke()}for(const s of series){if(!s.data?.length)continue;ctx.strokeStyle=s.color;ctx.lineWidth=1.8;ctx.beginPath();s.data.forEach((v,i)=>{const x=s.data.length===1?w/2:i/(Math.max(1,s.data.length-1))*w;const y=h-10-clamp((v-min)/(max-min||1),0,1)*(h-20);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y)});ctx.stroke();ctx.shadowBlur=0}}

function clock(){const d=new Date();$('#clockChip').textContent=d.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})}
function uiSelfTest(){
  const previous=S.page, failures=[];
  const tests=[
    ['home',()=>renderHome()],['quick',()=>renderQuick()],['advanced',()=>renderAdvanced()],['fortnite',()=>renderFortnite()],['games',()=>renderGames()],
    ['device',()=>renderDevice()],['keyboardmouse',()=>renderKeyboardMouse()],['controller',()=>renderController()],
    ['monitor',()=>renderMonitor()],['gameDiag',()=>renderGameDiagnostic()],['stutter',()=>renderStutter()],['windows',()=>renderWindows()],['guardian',()=>renderGuardian()],
    ['maintenance',()=>renderMaintenance()],['bios',()=>renderBios()],['hardware',()=>renderHardware()],['network',()=>renderNetwork()],
    ['islc',()=>renderLatency('islc')],['measure',()=>renderLatency('measure')],['restore',()=>renderRestore()],
    ['logs',()=>renderLogs()],['settings',()=>renderSettings()],
    ['arsenal',()=>renderArsenal()],
    ['plano',()=>renderPlan()],
    ['plano:carregando',()=>{const k=S.plan;S.plan=null;try{return renderPlan()}finally{S.plan=k}}],
    ['plano:vazio',()=>{const k=S.plan;S.plan={ok:true,steps:[],counts:{},total:0};try{return renderPlan()}finally{S.plan=k}}],
    ['arsenal:carregando',()=>{const keep=S.arsenal;S.arsenal=null;try{return renderArsenal()}finally{S.arsenal=keep}}],
    ['arsenal:erro',()=>{const keep=S.arsenal;S.arsenal={ok:false,reason:'teste'};try{return renderArsenal()}finally{S.arsenal=keep}}],
    // Auxiliares que o self-test do backend so conferia PELO NOME
    // ('function hexRgb' in app_text). Um check assim passa ate se o corpo
    // virar `return null` - entao aqui eles sao CHAMADOS e o resultado e
    // conferido. Cada linha abaixo substitui um check decorativo.
    ['aux:hexRgb',()=>{const v=hexRgb('#ff2fc8');if(!/^\d+,\s*\d+,\s*\d+$/.test(String(v)))throw new Error('hexRgb devolveu '+v);return 'hexRgb(#ff2fc8) devolveu rgb valido: '+v}],
    ['aux:profileLabel',()=>{const v=profileLabel('ultra');if(v!=='AZOR ULTRA')throw new Error('profileLabel(ultra)='+v);
      if(profileLabel('safe')!=='SEGURO')throw new Error('profileLabel(safe)='+profileLabel('safe'));return 'profileLabel conferido para ultra, safe e competitive'}],
    ['aux:verifiedReadiness',()=>{const r=verifiedReadiness();
      if(!r||typeof r.score!=='number'||r.score<0||r.score>100)throw new Error('score invalido: '+JSON.stringify(r));return 'verifiedReadiness devolveu score dentro de 0..100: '+r.score}],
    ['aux:statusCard',()=>{const h=statusCard('T','v','d');if(!h||h.indexOf('<')<0)throw new Error('statusCard nao devolveu HTML');return h}],
    ['aux:actionRow',()=>{const h=actionRow('N','D','BAIXO','game_mode_on');
      if(!h||h.indexOf('data-action="game_mode_on"')<0)throw new Error('actionRow perdeu o data-action');return h}],
    ['aux:input2DStage',()=>{const h=input2DStage('mouse','Mouse','#3f9dff');if(!h||h.indexOf('svg')<0)throw new Error('input2DStage sem svg');return h}],
    ['aux:adminGapBanner',()=>{
      // Com folga de permissao, precisa sair o banner com o botao de resolver;
      // sem folga, precisa sair vazio - nao um banner mentindo que falta algo.
      const keep=S.summary;
      try{
        S.summary={...(keep||{}),admin_gap:{is_admin:false,blocked:9,total:70,percent:13,names:['a','b']}};
        const com=adminGapBanner();
        if(!com||com.includes('relaunch_admin')||!com.includes('somente para essa operação'))throw new Error('banner deve explicar permissão por operação, sem elevar a interface');
        S.summary={...(keep||{}),admin_gap:{is_admin:true,blocked:0,total:70,percent:0,names:[]}};
        if(adminGapBanner()!=='')throw new Error('banner apareceu com o app ja elevado');
        return 'adminGapBanner: aparece com folga de permissao e some quando elevado';
      } finally { S.summary=keep; }
    }],
    ['indice',()=>azorIndexCard()||'<i>indice sem dados</i>'],
    ['indice:carregando',()=>{const keep=S.azorIndex;S.azorIndex=null;try{return azorIndexCard()}finally{S.azorIndex=keep}}],
    ['boost:indice',()=>{
      // O cartao do BOOST tem tres caminhos e todos ja apareceram quebrados em
      // desenvolvimento: sem medicao, sem "antes" comparavel, e com os dois.
      const keep={a:S.boost.indexAfter,b:S.boost.indexBefore};
      try{
        S.boost.indexAfter=null;S.boost.indexBefore=null;
        let html=boostIndexCard()===''?'vazio ok':'deveria ser vazio';
        S.boost.indexAfter={score:700,possible:1000,grade:'BOM'};
        html+=boostIndexCard();
        S.boost.indexBefore={score:500,possible:1000,grade:'REGULAR'};
        return html+boostIndexCard();
      }finally{S.boost.indexAfter=keep.a;S.boost.indexBefore=keep.b}
    }],
  ];
  for(const [name,fn] of tests){
    try{const html=fn();if(!html||String(html).length<40)failures.push(name+': saída vazia');}
    catch(e){failures.push(name+': '+(e?.message||e));}
  }
  S.page=previous;
  window.__AZOR_UI_SELFTEST__={ok:failures.length===0,failures,routes:tests.length};
  if(failures.length)console.error('AZOR UI self-test failed',failures);
  return window.__AZOR_UI_SELFTEST__;
}
window.AzorUiSelfTest=uiSelfTest;
window.addEventListener('error',e=>console.error('AZOR UI error',e.error||e.message));
window.addEventListener('unhandledrejection',e=>console.error('AZOR async error',e.reason));

// ===========================================================================
// BOOST
//
// Um botão, uma sequência, nenhum número inventado. Cada fase abaixo executa
// trabalho real do próprio AZOR e o log mostra o que a leitura devolveu:
//   SCAN     perfil de hardware + estado atual + latência medida antes
//   ANALYZE  /api/analyze com o perfil resolvido para esta máquina
//   OPTIMIZE quick_optimize (que só aplica com snapshot válido)
//   VERIFY   releitura do estado + nova análise + latência medida depois
//   DONE     contadores com os números que saíram das medições
// Quando o ganho é pequeno, a tela diz isso em vez de inflar o resultado.
// ===========================================================================

const BOOST_PHASES=[
  ['scan','LEITURA','Lendo o PC'],
  ['analyze','ANÁLISE','Procurando estragos e o que dá para melhorar'],
  ['optimize','AJUSTES','Consertando, aplicando e relendo'],
  ['verify','CONFERIR','Conferindo o resultado'],
  ['done','FIM','Execução encerrada'],
];

function boostProfile(){
  return S.quickProfile||'maximo';
}

function boostStage(){
  const b=S.boost;
  const idle=!b.running&&!b.finishedAt;
  const at=BOOST_PHASES.findIndex(p=>p[0]===b.phase);
  const selected=S.quickProfile||'maximo';
  const mode=PERFORMANCE_MODES[selected];
  return `
  <div class="boost-stage${b.running?' is-running':''}" id="boostStage">
    <div class="boost-main">
      <div class="boost-ring-wrap">
        <canvas class="boost-particles" id="boostParticles" aria-hidden="true"></canvas>
        <button class="boost-btn" id="boostBtn" type="button" ${b.running?'disabled':''}
          aria-label="${idle?'Deixar este PC no máximo agora':'Aplicar de novo'}">
          <svg class="boost-ring" viewBox="0 0 220 220" aria-hidden="true">
            <defs><linearGradient id="boostRingGradient" x1="0" y1="0" x2="1" y2="1"><stop class="ring-stop-a" offset="0"/><stop class="ring-stop-b" offset="1"/></linearGradient></defs>
            <circle class="ring-track" cx="110" cy="110" r="96"></circle>
            <circle class="ring-progress" cx="110" cy="110" r="96"
              style="stroke-dashoffset:${(603.2*(1-clamp(b.progress,0,1))).toFixed(1)}"></circle>
          </svg>
          <span class="boost-face">
            <b id="boostLabel">${b.running?(BOOST_PHASES.find(p=>p[0]===b.phase)?.[1]||'BOOST'):pendingOptimization()?'CONSULTAR':'BOOST'}</b>
            <small id="boostSub">${b.running?'':(pendingOptimization()?'mesma execução':b.finishedAt?'aplicar de novo':profileLabel(boostProfile()))}</small>
          </span>
        </button>
      </div>
      <div class="boost-profiles boost-modes" role="radiogroup" aria-label="Modo de desempenho">
        ${Object.entries(PERFORMANCE_MODES).map(([id,item])=>{
          const on = selected === id;
          return `<button type="button" class="boost-profile boost-mode ${id} ${on?'active':''}" data-qprofile="${id}"
            role="radio" aria-checked="${on}" ${b.running?'disabled':''}>
            <b>${item.label}<em>${item.tag}</em></b><small>${item.hint}</small></button>`;
        }).join('')}
      </div>
      <p class="boost-hint" id="boostHint">${b.running
        ? esc(BOOST_PHASES.find(p=>p[0]===b.phase)?.[2]||'')
        : mode
          ? `O AZOR aplica só o que faz sentido neste PC, confere cada item depois de gravar e deixa agendada a reaplicação ao entrar no Windows.`
          : `Perfil avançado em uso: <b>${esc(profileLabel(selected))}</b>. Escolha Máximo ou Agressivo para voltar ao modo simples.`}</p>
    </div>
    <div class="boost-side">
      <div class="boost-side-head"><span class="eyebrow">Sequência</span><h3>O que acontece no BOOST</h3></div>
      <ol class="boost-phases" id="boostPhases">${BOOST_PHASES.map(([key,label,desc],i)=>
        `<li class="boost-phase${at>=0&&i<at?' past':''}${i===at?' active':''}" data-phase="${key}"><i aria-hidden="true">${i+1}</i><span><b>${label}</b><small>${desc}</small></span></li>`).join('')}</ol>
      <div class="boost-result${b.finishedAt?'':' hidden'}" id="boostResult">${b.finishedAt?boostResultHtml():''}</div>
      <details class="boost-details" id="boostDetails" ${b.running?'open':''}>
        <summary>Detalhes da execução</summary>
        <div class="boost-log" id="boostLog" role="log" aria-live="polite">${
          b.log.length?b.log.map(boostLogLine).join(''):'<i class="boost-log-idle">As etapas aparecerão aqui quando você iniciar.</i>'}</div>
      </details>
    </div>
  </div>`;
}

function boostLogLine(entry){
  const cls=entry.level||'ok';
  return `<div class="blog-line ${cls}"><span class="blog-key">${esc(entry.key)}</span><span class="blog-val">${esc(entry.value)}</span>${
    entry.tag?`<span class="blog-tag ${cls}">${esc(entry.tag)}</span>`:''}</div>`;
}

function boostLog(key,value,tag='',level='ok'){
  S.boost.log.push({key,value,tag,level});
  const box=$('#boostLog');
  if(!box)return;
  if(S.boost.log.length===1)box.innerHTML='';
  box.insertAdjacentHTML('beforeend',boostLogLine(S.boost.log[S.boost.log.length-1]));
  box.scrollTop=box.scrollHeight;
}

function boostSetPhase(phase,progress){
  const b=S.boost;
  b.phase=phase;
  if(progress!=null)b.progress=progress;
  const meta=BOOST_PHASES.find(p=>p[0]===phase);
  const label=$('#boostLabel'),hint=$('#boostHint'),ring=$('.ring-progress');
  if(label&&meta)label.textContent=meta[1];
  if(hint&&meta)hint.textContent=meta[2];
  if(ring)ring.style.strokeDashoffset=(603.2*(1-clamp(b.progress,0,1))).toFixed(1);
  $$('.boost-phase').forEach(el=>{
    const order=BOOST_PHASES.findIndex(p=>p[0]===el.dataset.phase);
    const at=BOOST_PHASES.findIndex(p=>p[0]===phase);
    el.classList.toggle('active',order===at);
    el.classList.toggle('past',order<at);
  });
}

const boostSleep=ms=>new Promise(r=>setTimeout(r,ms));

// Partículas só existem enquanto alguém está olhando: no repouso o anel respira
// por CSS, que o compositor resolve sozinho. Um rAF permanente na tela inicial
// seria exatamente o tipo de custo que esta versão passou a limpar.
let boostParticleRaf=null;
function boostParticles(on){
  const canvas=$('#boostParticles');
  if(!canvas)return;
  if(!on||S.settings.animations===false||window.matchMedia?.('(prefers-reduced-motion: reduce)').matches){
    if(boostParticleRaf)cancelAnimationFrame(boostParticleRaf);
    boostParticleRaf=null;
    const ctx=canvas.getContext('2d');
    if(ctx)ctx.clearRect(0,0,canvas.width,canvas.height);
    return;
  }
  if(boostParticleRaf)return;
  const dpr=Math.min(2,window.devicePixelRatio||1);
  const rect=canvas.getBoundingClientRect();
  canvas.width=Math.max(10,rect.width*dpr);canvas.height=Math.max(10,rect.height*dpr);
  const ctx=canvas.getContext('2d');
  ctx.scale(dpr,dpr);
  const w=rect.width,h=rect.height,cx=w/2,cy=h/2;
  const dots=Array.from({length:22},(_,i)=>({
    a:(i/22)*Math.PI*2, r:Math.min(w,h)*(0.36+((i%5)*0.028)),
    speed:0.00022+((i%7)*0.00004), size:i%4===0?2.1:1.3,
  }));
  const accent=getComputedStyle(document.documentElement).getPropertyValue('--accent-rgb').trim()||'255,47,200';
  const step=now=>{
    ctx.clearRect(0,0,w,h);
    const fast=S.boost.running?3.2:1;
    for(const d of dots){
      d.a+=d.speed*16*fast;
      const x=cx+Math.cos(d.a)*d.r, y=cy+Math.sin(d.a)*d.r;
      ctx.beginPath();
      ctx.arc(x,y,d.size,0,Math.PI*2);
      ctx.fillStyle=`rgba(${accent},${S.boost.running?0.85:0.5})`;
      ctx.fill();
    }
    boostParticleRaf=requestAnimationFrame(step);
  };
  boostParticleRaf=requestAnimationFrame(step);
}

function boostCountItems(items){
  const list=Array.isArray(items)?items:[];
  return {
    total:list.length,
    applied:list.filter(resultOK).length,
    recommended:list.filter(x=>x.status==='recommended').length,
    skipped:list.filter(resultPreserved).length,
    pending:list.filter(x=>x.status==='recommended'),
  };
}

// Um número só vira ganho quando ele é maior que o ruído da própria medição.
//
// Duas rodadas do mesmo teste no mesmo PC nunca dão idêntico. Se a diferença
// cabe dentro dessa variação, ela não é ganho: é ruído, e apresentá-la como
// vitória é o tipo de número que qualquer overlay desmente em trinta segundos.
// Piorou também aparece — dizendo que piorou.
function boostDelta(before,after,label,unit=' ms'){
  if(!before||!after||!Number.isFinite(before)||!Number.isFinite(after))return null;
  const delta=before-after;              // positivo = melhorou (menor é melhor)
  const noise=Math.max(Math.abs(before),Math.abs(after))*0.05;
  const state=Math.abs(delta)<=noise?'noise':(delta>0?'gain':'loss');
  return {
    label, state, delta,
    from:Number(before.toFixed(3)), to:Number(after.toFixed(3)), unit,
    pct:before?Math.abs(delta/before*100):0,
  };
}

function boostDeltaCard(d){
  if(!d)return '';
  if(d.state==='noise'){
    return `<div class="boost-metric neutral">
      <small>${esc(d.label)}</small>
      <b>sem mudança</b>
      <span>${d.from}${d.unit} → ${d.to}${d.unit}. A diferença é menor que a variação normal entre duas medições, então o AZOR não chama isso de ganho.</span>
    </div>`;
  }
  const gain=d.state==='gain';
  return `<div class="boost-metric ${gain?'good':'loss'}">
    <small>${esc(d.label)}</small>
    <b data-count="${Math.abs(Number(d.pct.toFixed(1)))}" data-count-prefix="${gain?'−':'+'}" data-count-decimals="1" data-count-suffix="%">${gain?'−':'+'}${Math.abs(d.pct).toFixed(1)}%</b>
    <span>${d.from}${d.unit} → ${d.to}${d.unit}${gain?'':'. Piorou nesta medição — vale repetir com o PC parado antes de concluir.'}</span>
  </div>`;
}

// O que o AZOR encontrou e NAO pode consertar sozinho.
//
// Trocar plano de energia o app faz; ativar XMP no BIOS, nao - ele nao escreve
// firmware, e prometer isso seria mentira. Entao esses itens aparecem separados,
// com o caminho para o usuario resolver e o ganho tipico declarado como tipico.
function boostBottleneckHtml(){
  const bl=S.boost.bottleneck;
  if(!bl)return '';
  const items=(bl.findings||[]).filter(f=>f.severity==='high');
  if(!items.length){
    return `<div class="boost-verdict ok">
      <span class="eyebrow">LIMITES ESTRUTURAIS</span>
      <p><b>Nenhum encontrado.</b> Monitor, memória, disco e temperatura estão dentro do esperado.
      ${esc(bl.live_note||'')}</p>
    </div>`;
  }
  return `<div class="boost-verdict">
    <span class="eyebrow">FORA DO ALCANCE DO APP</span>
    <h4>${items.length} limite${items.length===1?'':'s'} que o AZOR não conserta sozinho</h4>
    <div class="verdict-list">${items.map(f=>`
      <div class="verdict-item">
        <div class="verdict-top"><b>${esc(f.title)}</b><span class="pill off">${esc(f.area)}</span></div>
        <p>${esc(f.detail)}</p>
        ${f.action?`<p class="verdict-action">${esc(f.action)}</p>`:''}
        ${f.gain?`<span class="verdict-gain">Ganho típico: ${esc(f.gain)}</span>`:''}
      </div>`).join('')}</div>
    <p class="verdict-note">${esc(bl.live_note||'')}</p>
  </div>`;
}

// O índice é o único número da tela que resume tudo, e por isso é o mais fácil
// de transformar em mentira. Ele só aparece aqui quando existem DUAS medições
// reais; sem a de antes, mostra apenas o valor atual, sem inventar um delta.
function boostIndexCard(){
  const a=S.boost.indexAfter,before=S.boost.indexBefore;
  if(!a)return '';
  if(!before||before.possible!==a.possible){
    return `<div class="boost-metric neutral">
      <small>ÍNDICE AZOR</small><b data-count="${a.score}">${a.score}</b>
      <span>de ${a.possible} pontos avaliados · ${esc(a.grade)}. Sem uma medição anterior
      comparável, o AZOR mostra o valor de agora e não inventa um "antes".</span></div>`;
  }
  const delta=a.score-before.score;
  const tone=delta>0?'good':delta<0?'loss':'neutral';
  return `<div class="boost-metric ${tone}">
    <small>ÍNDICE AZOR</small>
    <b data-count="${Math.abs(delta)}" data-count-prefix="${delta>0?'+':delta<0?'−':''}">${delta>0?'+':delta<0?'−':''}${Math.abs(delta)}</b>
    <span>${before.score} → ${a.score} de ${a.possible} pontos avaliados${
      delta===0?'. O conjunto não mudou de forma mensurável.':delta<0?'. Caiu nesta medição — vale repetir com o PC parado.':` · ${esc(a.grade)}`}</span></div>`;
}

function boostResultHtml(){
  const b=S.boost;
  const res=b.result||{};
  const rows=Array.isArray(res.results)?res.results:[];
  const verified=rows.filter(x=>resultOK(x)&&!['Hardware profile','Backup / Restore'].includes(x.name)).length;
  const preserved=rows.filter(resultPreserved).length;
  const failed=rows.filter(resultFailed);
  // Consertos contam à parte: não são ajuste de desempenho, são estrago de outro
  // programa desfeito, e é a notícia que o cliente mais precisa ler.
  const repaired=rows.filter(x=>x.module==='repair'&&resultOK(x)&&!x.already_applied);
  if(res.ok===false&&!failed.length)failed.push({name:'Operação',detail:res.detail||res.error||'O motor não confirmou a conclusão.'});
  const unknown=rows.filter(x=>!resultOK(x)&&!resultPreserved(x)&&!resultFailed(x));
  const before=boostCountItems(b.analysisBefore);
  const after=boostCountItems(b.analysisAfter);
  const completeAnalysis=items=>Array.isArray(items)&&items.every(x=>resultOK(x)||resultPreserved(x)||x.status==='recommended');
  const comparable=completeAnalysis(b.analysisBefore)&&completeAnalysis(b.analysisAfter);
  const closed=comparable?Math.max(0,before.recommended-after.recommended):0;

  const lb=b.latencyBefore,la=b.latencyAfter;
  const dLat=lb&&la?boostDelta(lb.avg_ms,la.avg_ms,'LATÊNCIA DO TIMER'):null;
  const dJit=lb&&la?boostDelta(lb.jitter_ms,la.jitter_ms,'OSCILAÇÃO'):null;

  const nothingToDo=comparable&&after.recommended===0&&verified===0&&!failed.length&&!unknown.length;
  const smallGain=!nothingToDo&&closed===0;

  const counters=[
    ...(comparable?[{lab:'PENDÊNCIAS RESOLVIDAS',val:closed,note:`${before.recommended} encontrada(s) antes, ${after.recommended} restante(s)`}]:[]),
    {lab:'AJUSTES VERIFICADOS',val:verified,note:'confirmados por releitura, não por suposição'},
  ];
  if(repaired.length)counters.unshift({lab:'CONSERTOS',val:repaired.length,note:'estragos de outros programas desfeitos'});
  if(preserved)counters.push({lab:'PRESERVADOS',val:preserved,note:'o perfil deixou de propósito'});

  return `
    <div class="boost-result-head">
      <span class="eyebrow">RESUMO DA EXECUÇÃO</span>
      <h3>${failed.length?'Otimização encerrada com pendências':unknown.length?'Execução com resultados não confirmados':nothingToDo?'Perfil conferido':verified?'Ajustes confirmados':'Resultado ainda não confirmado'}</h3>
      <p class="section-sub">${nothingToDo
        ? 'Nenhuma pendência foi encontrada nas configurações avaliadas deste perfil.'
        : comparable?'Os resultados abaixo se referem às configurações conferidas nesta execução.':'Sem duas análises completas, não é possível comparar pendências antes e depois.'}</p>
    </div>
    <div class="boost-metrics">
      ${counters.map(m=>`
      <div class="boost-metric">
        <small>${m.lab}</small>
        <b data-count="${m.val}">${m.val}</b>
        <span>${esc(m.note)}</span>
      </div>`).join('')}
      ${boostDeltaCard(dLat)}
      ${boostDeltaCard(dJit)}
      ${boostIndexCard()}
    </div>
    ${res.logon_autoapply?`<p class="boost-logon ${res.logon_autoapply.ok?'ok':'fail'}">${res.logon_autoapply.ok
      ?'Reaplicação ao entrar no Windows: ativada. O AZOR confere e recoloca o que o Windows desfizer.'
      :'Reaplicação ao entrar no Windows não foi configurada: '+esc(res.logon_autoapply.detail||'sem detalhe')}</p>`:''}
    ${repaired.length?`<div class="boost-repairs"><b>${repaired.length===1?'1 coisa que outro programa tinha quebrado foi consertada':repaired.length+' coisas que outro programa tinha quebrado foram consertadas'}</b>${
      repaired.map(x=>`<div class="blog-line good"><span class="blog-key">${esc(x.name||x.id||'conserto')}</span><span class="blog-val">${esc(x.detail||'confirmado por releitura')}</span></div>`).join('')
    }<small>Consertos não entram no Desfazer: voltar atrás seria religar o defeito.</small></div>`:''}
    ${optimizationReportHtml(res)}
    ${boostBottleneckHtml()}
    ${(dLat&&dLat.state==='noise'&&dJit&&dJit.state==='noise')?`<p class="boost-remaining">O timer não mudou de forma mensurável — normal quando ele já estava bom. Ganho de FPS de verdade se mede com o jogo aberto: use <button class="linklike" data-go="gameDiag">Monitor de Jogo</button> para coletar antes e depois com frametime real.</p>`:''}
    ${failed.length?`<div class="boost-failed"><b>${failed.length} item(ns) para revisar</b>${
      failed.map(x=>`<div class="blog-line bad"><span class="blog-key">${esc(x.name||x.id||'item')}</span><span class="blog-val">${esc(x.detail||'não pôde ser confirmado')}</span></div>`).join('')}</div>`:''}
    ${unknown.length?`<p class="boost-remaining">${unknown.length} resultado(s) não puderam ser confirmados. Confira os detalhes da execução antes de tentar novamente.</p>`:''}
    ${after.recommended?`<p class="boost-remaining">${after.recommended} item(ns) continuam recomendados e dependem de você: abra <button class="linklike" data-go="quick">Otimizar PC</button> para ver quais e por quê.</p>`:''}
  `;
}

function optimizationReportHtml(res){
  const metrics=res.comparison?.metrics||[];
  const table=metrics.length?`<table class="report-table"><thead><tr><th>Métrica</th><th>Antes</th><th>Depois</th></tr></thead><tbody>${metrics.map(m=>`<tr><td>${esc(m.label)}</td><td>${esc(m.before)} ${esc(m.unit)}</td><td>${esc(m.after)} ${esc(m.unit)}</td></tr>`).join('')}</tbody></table>`:'';
  return `<section class="optimization-report">${table}${res.comparison?`<p class="section-sub">${esc(res.comparison.note)} Não é uma medição de FPS nem prova de ganho.</p>`:''}
    ${res.restart_required?'<p class="boost-remaining">Há ajustes que precisam de reinicialização. Salve seu trabalho e reinicie quando puder.</p>':''}
    ${res.report_id?`<button class="btn ghost" data-report="${esc(res.report_id)}">SALVAR RELATÓRIO</button>`:''}</section>`;
}
function pendingOptimization(){
  try{return JSON.parse(localStorage.getItem('azor.pendingOperation')||'null')}catch{return null}
}
async function runBoost(resumeOnly=false){
  const b=S.boost;if(b.running)return;
  let pending=pendingOptimization();
  if(resumeOnly&&!pending?.id)return;
  const profile=pending?.profile||boostProfile();
  b.running=true;b.phase='scan';b.progress=0;b.log=[];b.result=null;b.finishedAt=null;
  b.analysisBefore=null;b.analysisAfter=null;b.latencyBefore=null;b.latencyAfter=null;
  b.indexBefore=null;b.indexAfter=null;b.bottleneck=null;
  render();boostParticles(true);let completed=false;
  try{
    if(!pending){
      pending={key:crypto.randomUUID(),profile};
      // Persist intent before dispatch, so losing the reply never causes a new batch.
      localStorage.setItem('azor.pendingOperation',JSON.stringify(pending));
    }
    let job;
    if(pending.id)job=(await getJSON('/api/operations/'+pending.id)).job;
    else{
      const response=await postJSON('/api/operations',{name:'full_optimize',profile,request_key:pending.key});
      job=response.job;
      if(!job?.id)throw new Error('O início da operação ainda não foi confirmado.');
      pending.id=job.id;localStorage.setItem('azor.pendingOperation',JSON.stringify(pending));
    }
    let seen=0,failures=0;
    while(true){
      if(!job||!Array.isArray(job.events))throw new Error('Resposta de operação inválida. O identificador foi preservado.');
      for(const event of job.events.slice(seen)){
        const status=event.status;
        boostLog(event.name,event.detail||'',resultOK(event)?'CONFIRMADO':resultPreserved(event)?'PRESERVADO':resultFailed(event)?'FALHA':'EM ANDAMENTO',
          resultFailed(event)?'bad':resultPreserved(event)?'muted':resultOK(event)?'ok':'accent');
        boostSetPhase(status==='applying'?'optimize':status==='verifying'?'verify':b.phase,0);
      }
      seen=job.events.length;
      if(!['queued','running'].includes(job.status))break;
      const hint=$('#boostHint');if(hint)hint.textContent=job.phase?'Etapa atual: '+job.phase:'Preparando análise e proteção. Aguarde…';
      await boostSleep(document.hidden?3000:1000);
      try{job=(await getJSON('/api/operations/'+pending.id)).job;failures=0}
      catch(e){if(++failures>=3)throw e;boostLog('Conexão','Tentando consultar a mesma execução; nenhuma ação será repetida.','AGUARDANDO','warn');await boostSleep(failures*1500)}
    }
    completed=true;localStorage.removeItem('azor.pendingOperation');S.autostart=null;
    b.result=job.result||{ok:false,detail:job.detail||'A sessão terminou sem confirmação. Confira o histórico de restauração.',results:[]};
    boostSetPhase('done',1);
    S.restorePoints=null;S.transactions=null;S.analysis=null;S.arsenal=null;S.azorIndex=null;
    toast(b.result.ok?'Execução encerrada. Veja os ajustes confirmados.':'Execução encerrada. Confira o resultado e as opções de restauração.',b.result.ok===true);
  }catch(e){
    b.result={ok:null,detail:'Não foi possível confirmar a conclusão. '+e.message,results:[{name:'Conexão com a execução',status:'unknown',detail:'O identificador foi preservado. Clique em CONSULTAR para conferir, sem criar outro lote. '+e.message}]};
    boostLog('Execução',e.message,'NÃO CONFIRMADO','warn');toast('Resultado não confirmado. A execução pode continuar; consulte antes de repetir.',false);
  }finally{
    b.running=false;b.finishedAt=Date.now();boostParticles(false);render();
    if(!completed){const btn=$('#boostLabel');if(btn)btn.textContent='CONSULTAR';const sub=$('#boostSub');if(sub)sub.textContent='mesma execução'}
    if(completed)refreshSummary(false).catch(()=>{});
  }
}

// ---------------------------------------------------------------------------
// Polling
//
// Three loops used to run unconditionally: summary every 12 s, game diagnostic
// every 2 s and the monitor every 1,5 s. They kept running with the window
// minimised behind a game - measured at 82,5 requisicoes/min with the window
// hidden - and every one of those requests woke a backend that spawns
// processes. An app that exists to give CPU back to the game cannot be the one
// taking it. The loops now stop while the window is hidden and resume with a
// fresh read the moment it comes back.
//
// A failing backend also used to retry at full speed forever; each loop now
// backs off up to 30 s and the sidebar says what is happening.
// ---------------------------------------------------------------------------
const POLL={summary:12000,gameDiag:2000,maxBackoff:30000};
let pollingActive=false,pollGeneration=0;
const pollTimers={summary:null,monitor:null,gameDiag:null};
const pollBackoff={summary:0,monitor:0,gameDiag:0};

function monitorInterval(){return clamp(Number(S.settings.monitor_interval||1.5),1,5)*1000}

function pollLoop(key,base,work){
  const generation=pollGeneration;
  const tick=async()=>{
    if(!pollingActive||generation!==pollGeneration)return;
    try{await work();pollBackoff[key]=0}
    catch(e){pollBackoff[key]=Math.min(POLL.maxBackoff,Math.max(base,(pollBackoff[key]||base)*2));console.warn('poll '+key,e)}
    if(!pollingActive||generation!==pollGeneration)return;
    pollTimers[key]=setTimeout(tick,pollBackoff[key]||(typeof base==='function'?base():base));
  };
  tick();
}

function startPolling(){
  if(pollingActive)return;
  if(document.visibilityState==='hidden')return;
  pollingActive=true;
  const generation=++pollGeneration;
  pollLoop('summary',POLL.summary,()=>refreshSummary(false));
  pollLoop('gameDiag',POLL.gameDiag,async()=>{
    if(S.gameDiag?.running||S.page==='gameDiag'){await loadGameDiag(false);if(S.page==='gameDiag')render()}
  });
  const monitorTick=async()=>{
    if(!pollingActive||generation!==pollGeneration)return;
    try{if(['monitor','home','latency'].includes(S.page))await refreshMonitor(true);pollBackoff.monitor=0}
    catch(e){pollBackoff.monitor=Math.min(POLL.maxBackoff,Math.max(monitorInterval(),(pollBackoff.monitor||monitorInterval())*2))}
    if(!pollingActive||generation!==pollGeneration)return;
    S.monitorTimer=pollTimers.monitor=setTimeout(monitorTick,pollBackoff.monitor||monitorInterval());
  };
  monitorTick();
}

function stopPolling(){
  pollingActive=false;
  pollGeneration++;
  for(const key of Object.keys(pollTimers)){clearTimeout(pollTimers[key]);pollTimers[key]=null}
  clearTimeout(S.monitorTimer);
}
window.addEventListener('blur',stopPolling);
window.addEventListener('focus',startPolling);

document.addEventListener('visibilitychange',()=>{
  if(document.visibilityState==='hidden'){stopPolling();pauseInputVisuals();boostParticles(false);return}
  resumeInputVisuals();
  startPolling();
  // startPolling already performs the first reads; do not duplicate them.
});


// ===========================================================================
// ARSENAL
//
// A tela onde o catálogo inteiro aparece. Ela existe por dois motivos:
//
//   1. O motor passou de 12 para 38 tweaks, e boa parte deles não entra no
//      clique único de propósito — os de risco alto e os experimentais. Sem uma
//      tela que os aplique um a um, eles seriam decoração.
//   2. O cliente precisa VER o trabalho. Uma lista de 38 itens, cada um com
//      fonte, custo e o número que ele move, é mais convincente que qualquer
//      barra de progresso — e continua sendo verdade depois de conferida.
//
// Nada aqui é enfeite de contagem: todo número vem de `/api/arsenal`, que por
// sua vez conta o catálogo em vez de repetir uma constante escrita na tela.
// ===========================================================================

const ARSENAL_FILTERS = [
  ['all',      'TUDO'],
  ['pending',  'PENDENTES'],
  ['applied',  'APLICADOS'],
  ['manual',   'AVANÇADOS'],
  ['skipped',  'PRESERVADOS'],
];

const RISK_TONE = { low:'low', medium:'mid', high:'high', experimental:'exp' };

function arsenalMatches(task, filter){
  if(filter === 'all') return true;
  if(filter === 'applied') return task.state === 'applied';
  if(filter === 'pending') return task.eligible && task.state !== 'applied' && task.automatic;
  if(filter === 'manual') return !task.automatic || task.risk === 'high' || task.risk === 'experimental';
  if(filter === 'skipped') return !task.eligible;
  return true;
}

function arsenalStateBadge(task){
  if(task.state === 'applied') return ['goodpill', 'APLICADO'];
  if(!task.eligible)           return ['off', 'PRESERVADO'];
  if(!task.automatic)          return ['warnpill', 'SOB DEMANDA'];
  return ['', 'PENDENTE'];
}

const RELATION_LABEL = {
  amplia:      ['AMPLIA',      'Este ajuste multiplica o efeito de outro'],
  combina:     ['COMBINA COM', 'Os dois juntos rendem mais que a soma'],
  redundante:  ['ANULA',       'Com o outro aplicado, este deixa de ter efeito'],
  cuidado:     ['ATENÇÃO',     'Interação que vale conhecer antes de aplicar'],
};

// Um arsenal de sessenta itens tem interações reais, e até aqui elas viviam só na
// cabeça de quem escreveu o catálogo. "O timer de sessão quase não alcança o jogo
// sem o timer global" é um fato que o usuário tinha de adivinhar.
function relationHtml(task){
  const rels = task.relations || [];
  if(!rels.length) return '';
  return rels.map(r => {
    const [tag, hint] = RELATION_LABEL[r.kind] || ['RELACIONADO', ''];
    const state = r.applied === true ? 'aplicado' : r.eligible === false ? 'preservado neste PC' : 'ainda não aplicado';
    return `<p class="tweak-rel"><b>${tag}</b> ${esc(r.name || r.id)} <i>(${state})</i> — ${esc(r.note)}</p>`;
  }).join('');
}

// A prova é o único lugar do app que responde "este ajuste específico fez algo
// no MEU PC?" com número. Só aparece onde o AZOR realmente consegue medir.
function proofHtml(task){
  const p = S.proofs[task.id];
  if(!p) return '';
  if(p.running) return '<div class="tweak-proof running"><span class="spinner"></span> medindo antes e depois…</div>';
  if(p.ok === false) return `<div class="tweak-proof neutral">${esc(p.detail || 'Não foi possível medir.')}</div>`;
  const tone = p.verdict === 'gain' ? 'good' : p.verdict === 'loss' ? 'bad' : 'neutral';
  const rows = (p.metrics || []).filter(m => m.state !== 'unknown').map(m =>
    `<span class="proof-metric ${m.state}"><b>${esc(m.key.replace('_us',''))}</b>
      ${m.before} → ${m.after} µs</span>`).join('');
  return `<div class="tweak-proof ${tone}">
    <b>${p.verdict === 'gain' ? 'Ganho medido' : p.verdict === 'loss' ? 'Piorou na medição' : 'Sem efeito claro'}</b>
    <span>${esc(p.detail || '')}</span>
    <div class="proof-metrics">${rows}</div>
    <small>${p.samples} amostras antes e ${p.samples} depois, medidas agora neste PC.${
      p.restart_note ? ' ' + esc(p.restart_note) : ''}</small>
  </div>`;
}

function arsenalRow(task){
  const [pill, label] = arsenalStateBadge(task);
  const tone = RISK_TONE[task.risk] || 'mid';
  const canApply  = task.eligible && task.can_apply!==false && task.state !== 'applied';
  const canRevert = task.state === 'applied' && task.can_revert;
  const why = [
    task.classification ? `<p><b>Classificação:</b> ${esc(task.classification)} · ${esc(task.disposition||'')}.</p>` : '',
    task.audit_reason ? `<p><b>Revisão:</b> ${esc(task.audit_reason)}</p>` : '',
    task.description ? `<p><b>O que faz:</b> ${esc(task.description)}</p>` : '',
    task.trade_off   ? `<p><b>O que custa:</b> ${esc(task.trade_off)}</p>` : '',
    task.metric      ? `<p><b>Número que isso move:</b> ${esc(task.metric)}</p>`
                     : '<p><b>Número que isso move:</b> nenhum. É preferência, não desempenho.</p>',
    task.source      ? `<p><b>Fonte:</b> ${esc(task.source)}</p>` : '',
    task.restart     ? '<p><b>Exige reiniciar</b> o Windows para valer por completo.</p>' : '',
    task.can_revert  ? '' : '<p><b>Não tem desfazer individual.</b> O app diz isso em vez de prometer o contrário.</p>',
    task.state_detail? `<p><b>Leitura agora:</b> ${esc(task.state_detail)}</p>` : '',
    !task.eligible && task.reason ? `<p><b>Por que está preservado:</b> ${esc(task.reason)}</p>` : '',
    relationHtml(task),
    driftHtml(task),
    proofHtml(task),
  ].join('');
  const canProve = task.provable && task.eligible;
  return `<div class="analysis-row arsenal-row" data-tweak="${esc(task.id)}">
    <div>
      <b>${esc(task.name)}
        <span class="module-tag">${esc(task.category || task.module)}</span>
        <span class="risk ${tone}">${esc(String(task.risk_label || task.risk).toUpperCase())}</span>
        ${task.restart ? '<span class="risk restart">REINÍCIO</span>' : ''}
      </b>
      <small>${esc(task.state_detail || task.reason || task.description || '')}</small>
      <details class="tweak-why"><summary>ver fonte, custo e leitura atual</summary>
        <div class="tweak-why-body">${why}</div></details>
    </div>
    <div class="analysis-row-actions">
      <span class="pill ${pill}">${label}</span>
      ${canProve ? `<button class="btn small ghost" data-prove-tweak="${esc(task.id)}" title="Mede a latência antes e depois de aplicar, neste PC">PROVAR</button>` : ''}
      ${canApply  ? `<button class="btn small primary" data-apply-tweak="${esc(task.id)}">APLICAR</button>` : ''}
      ${canRevert ? `<button class="btn small ghost" data-revert="${esc(task.id)}">DESFAZER</button>` : ''}
    </div>
  </div>`;
}

// O bloco de reparo é o argumento mais forte que a tela tem, e por isso é o mais
// fácil de transformar em alarme falso. Ele só aparece com achado CONFIRMADO —
// e quando não há nenhum, diz isso em uma linha em vez de sumir, porque "não
// encontramos nada quebrado" também é um resultado que o cliente pagou para ver.
function arsenalRepairBlock(a){
  const r = a.repair;
  if(!r || !r.total) return '';
  const found = r.found || [];
  const unreadable = r.unreadable || [];
  if(!found.length){
    return `<div class="repair-block card clean">
      <span class="repair-mark">✓</span>
      <div><b>Nada quebrado por outro programa.</b>
      <span>Os ${r.total} itens de reparo foram verificados e não encontraram estrago:
      boot, serviços essenciais, firewall, Proteção do Sistema, TCP e TRIM estão como deveriam.${
        unreadable.length ? ` ${unreadable.length} verificação depende de administrador para ser feita.` : ''}</span></div>
    </div>`;
  }
  return `<div class="repair-block card">
    <div class="repair-head">
      <span class="repair-mark alert">!</span>
      <div><b>${found.length} coisa${found.length === 1 ? '' : 's'} que outro programa quebrou neste PC</b>
      <span>Isto não é otimização: é conserto. Nenhum destes itens existe num Windows de fábrica,
      e nenhum deles dá erro — o sistema só fica pior em silêncio.</span></div>
    </div>
    <div class="repair-list">${found.map(f => `
      <div class="repair-item">
        <div><b>${esc(f.name)}</b><small>${esc(f.detail)}</small></div>
        <button class="btn small primary" data-apply-tweak="${esc(f.id)}">CONSERTAR</button>
      </div>`).join('')}</div>
  </div>`;
}

// O que o Windows mais desfaz neste PC. É a informação mais útil que o ciclo de
// reconciliação produz — mais útil, inclusive, que o próprio conserto.
function driftHtml(task){
  const d = (S.drift?.items || []).find(x => x.id === task.id);
  if(!d || !d.count) return '';
  return `<p class="tweak-drift"><b>O Windows já desfez isto ${d.count}×</b> desde que você aplicou
    — a última em ${esc((d.dates || []).slice(-1)[0] || '?')}. O AZOR devolve ao lugar toda vez que abre.</p>`;
}

function driftBanner(){
  const d = S.drift;
  if(!d || !d.total) return '';
  const top = (d.items || []).slice(0, 3);
  return `<div class="drift-banner card">
    <span class="drift-mark">↺</span>
    <div><b>${d.total} vez${d.total === 1 ? '' : 'es'} que o Windows desfez um ajuste — e o AZOR devolveu</b>
    <span>Mais teimosos: ${top.map(t => `${esc(t.name)} (${t.count}×)`).join(', ')}.
    Não é falha do app: é o Windows, a Game Bar ou o software do fabricante reescrevendo a mesma chave.
    Quanto maior o número, mais esse item depende do AZOR estar aberto.</span></div>
  </div>`;
}

function arsenalStat(value, label, hint){
  return `<div class="arsenal-stat"><strong data-count="${Number(value) || 0}">${value}</strong>
    <span>${esc(label)}</span><small>${esc(hint || '')}</small></div>`;
}

function renderArsenal(){
  const a = S.arsenal;
  if(!a) return `${head('Arsenal AZOR','Carregando o catálogo e lendo o estado de cada item neste PC…')}
    <article class="card pad"><div class="skeleton-list">${'<i></i>'.repeat(7)}</div></article>`;
  if(a.ok === false) return `${head('Arsenal AZOR','O catálogo não pôde ser lido.')}
    <article class="card pad"><p class="section-sub">${esc(a.reason || 'Erro desconhecido.')}</p></article>`;

  const f = a.footprint || {};
  const tasks = a.tasks || [];
  const filter = S.arsenalFilter || 'all';
  // Com 68 linhas, rolar procurando "Nagle" deixou de ser aceitável.
  const q = (S.arsenalQuery || '').trim().toLowerCase();
  const matchQuery = t => !q || [t.name, t.category, t.module, t.id, t.description, t.metric]
    .some(v => String(v || '').toLowerCase().includes(q));
  const shown = tasks.filter(t => arsenalMatches(t, filter) && matchQuery(t));
  const applied = tasks.filter(t => t.state === 'applied').length;
  const groups = {};
  for(const t of shown) (groups[t.module] = groups[t.module] || []).push(t);
  const moduleLabel = id => (a.modules || []).find(m => m.id === id)?.label || id;

  const blocked = tasks.filter(t => !t.eligible && /administrador/i.test(t.reason || '')).length;
  const adminWarning = a.admin ? '' : `<div class="arsenal-warn card">
    <div>
      <b>O AZOR está sem privilégio de administrador.</b>
      <span>Os ajustes que gravam em HKLM — núcleo do Windows, serviços, rede e GPU — aparecem como
      <i>preservados</i> porque o Windows não deixaria gravá-los. São <i>${blocked}</i> item(ns)
      indisponíveis agora.</span>
    </div>
    <button class="btn primary" id="relaunchAdmin">REABRIR COMO ADMINISTRADOR</button></div>`;

  return `${head('Arsenal AZOR',
    'Todo ajuste que este app sabe fazer, com a fonte, o custo e a leitura atual deste PC. Aplique ou desfaça um a um.',
    '<button class="btn ghost" id="refreshArsenal">↻ RELER ESTADO</button>')}
  ${adminWarning}
  ${arsenalRepairBlock(a)}
  ${driftBanner()}
  <section class="arsenal-stats card">
    ${arsenalStat(f.tweaks ?? tasks.length, 'ajustes no catálogo', `${f.modules || 0} módulos`)}
    ${arsenalStat(applied, 'confirmados neste PC', 'por releitura, não por intenção')}
    ${arsenalStat(f.reversible ?? 0, 'com desfazer individual', `de ${f.tweaks ?? tasks.length}`)}
    ${arsenalStat(f.tracked_keys ?? 0, 'chaves sob custódia', 'valor original guardado antes de gravar')}
    ${arsenalStat(f.restart_required ?? 0, 'pedem reinício', 'e dizem isso antes')}
  </section>
  <p class="arsenal-note">O número de chaves sob custódia é contado do próprio catálogo: cada ajuste
  declara o que grava, e essa declaração <b>é</b> a lista que o AZOR captura antes de mexer. Não existe
  segunda lista para ficar desatualizada.</p>
  <div class="arsenal-search">
    <input id="arsenalSearch" class="select" type="search" placeholder="Buscar por nome, categoria ou métrica…"
      value="${esc(S.arsenalQuery || '')}" autocomplete="off">
    ${q ? `<span>${shown.length} de ${tasks.length}</span>` : ''}
  </div>
  <div class="arsenal-filters">${ARSENAL_FILTERS.map(([key, label]) => {
    const n = tasks.filter(t => arsenalMatches(t, key)).length;
    return `<button type="button" class="filter-pill ${filter === key ? 'active' : ''}"
      data-arsenal-filter="${key}" aria-pressed="${filter === key}">${label} <i>${n}</i></button>`;
  }).join('')}</div>
  ${Object.keys(groups).length ? Object.entries(groups).map(([id, rows]) => `
    <article class="card pad arsenal-group">
      <div class="device-head"><div>
        <span class="eyebrow">${esc(moduleLabel(id).toUpperCase())}</span>
        <h3 class="section-title">${rows.length} ajuste${rows.length === 1 ? '' : 's'}</h3>
      </div><span class="pill ${rows.every(r => r.state === 'applied') ? 'goodpill' : ''}">${
        rows.filter(r => r.state === 'applied').length}/${rows.length}</span></div>
      <div class="analysis-list">${rows.map(arsenalRow).join('')}</div>
    </article>`).join('')
    : '<article class="card pad"><div class="empty">Nenhum ajuste neste filtro.</div></article>'}
  ${driverGuideCard()}`;
}

// A reconciliacao roda em thread no backend e leva alguns segundos. A tela
// pergunta algumas vezes, com espacamento, e desiste em silencio - um banner que
// nunca chega e melhor que um erro para algo que e puramente informativo.
async function loadStartupReport(tries = 0){
  try{
    const r = await getJSON('/api/startup-report');
    if(r && r.done){ S.startup = r; if(S.page === 'home') render(); return; }
  }catch(e){ /* backend ainda subindo */ }
  if(tries < 6) setTimeout(() => loadStartupReport(tries + 1), 2500);
}

// "Aplicou = fica" precisa ser visivel, senao o cliente nunca sabe que o app
// consertou algo por ele. So aparece quando houve o que consertar.
// Onze tweaks dizem "só vale depois de reiniciar" e, até aqui, ninguém voltava
// para conferir depois do boot. O cliente reiniciava e ficava sem saber.
function rebootConfirmBanner(){
  const r = S.startup?.reboot;
  if(!r) return '';
  const ok = r.confirmed || [], bad = r.failed || [], waiting = r.waiting || [];
  if(!ok.length && !bad.length && !waiting.length) return '';
  if(!ok.length && !bad.length){
    return `<div class="restored-banner card has-fail">
      <span class="restored-mark">⏻</span>
      <div><b>${waiting.length} ajuste${waiting.length === 1 ? '' : 's'} esperando um reinício</b>
      <span>${esc(waiting.map(x => x.name).join(', '))}. Eles já estão gravados e conferidos no
      Windows, mas só assumem no próximo boot — o AZOR confirma sozinho quando você reiniciar.</span></div>
    </div>`;
  }
  return `<div class="restored-banner card ${bad.length ? 'has-fail' : ''}">
    <span class="restored-mark">${bad.length ? '!' : '✓'}</span>
    <div><b>${ok.length} ajuste${ok.length === 1 ? '' : 's'} confirmado${ok.length === 1 ? '' : 's'} depois do reinício</b>
    <span>${ok.length ? esc(ok.map(x => x.name).join(', ')) + '. ' : ''}${
      bad.length ? `<i>${bad.length} não passaram na releitura pós-boot: ${esc(bad.map(x => x.name).join(', '))}.</i> ` : ''}${
      waiting.length ? `${waiting.length} ainda aguardam um reinício.` : ''}</span></div>
  </div>`;
}

// O banner que faltava: sem administrador, 27 dos 70 ajustes deste catalogo
// sao pulados EM SILENCIO, e o BOOST termina anunciando "39 aplicadas" com cara
// de sucesso. O cliente ficava com 61% do produto achando que tinha 100%.
// O numero vem contado do catalogo (admin_blocked_tweaks), nunca escrito a mao.
function modeCleanupBanner(){
  const items=(S.modeCleanup&&S.modeCleanup.items)||[];
  if(!items.length||S.boost.running)return '';
  const n=items.length;
  return `<section class="card mode-cleanup" aria-label="Ajustes que saíram do modo Agressivo">
    <div><span class="eyebrow">Modo Agressivo atualizado</span>
      <h3>${n===1?'1 ajuste antigo que não aumenta FPS ainda está ligado':n+' ajustes antigos que não aumentam FPS ainda estão ligados'}</h3>
      <p class="section-sub">Eles saíram do Agressivo: a revisão do AZOR os classifica como teste A/B ou placebo, e a CPU sem repouso prende o processador no turbo de todos os núcleos. O login não os reaplica mais. Desfazer devolve cada um ao valor de antes do AZOR.</p>
      <ul class="mode-cleanup-list">${items.map(x=>`<li>${esc(x.name)}</li>`).join('')}</ul></div>
    <button class="btn primary" type="button" id="modeCleanupBtn">DESFAZER ${n===1?'ESTE':'ESTES '+n}</button>
  </section>`;
}

function adminGapBanner(){
  const g=S.summary?.admin_gap;
  if(!g||g.is_admin||!g.blocked)return '';
  return '<article class="card pad"><h3>Permissão apenas quando necessária</h3><p class="section-sub">A interface funciona sem administrador. Se a ação escolhida precisar de permissão, o Windows solicitará autorização somente para essa operação.</p></article>';
}

function startupRestoreBanner(){
  const rec = S.startup?.reconcile;
  if(!rec) return '';
  const restored = rec.restored || [];
  const failed = rec.failed || [];
  if(!restored.length && !failed.length) return '';
  return `<div class="restored-banner card ${failed.length ? 'has-fail' : ''}">
    <span class="restored-mark">${failed.length ? '!' : '↺'}</span>
    <div>
      <b>${restored.length ? `${restored.length} ajuste${restored.length === 1 ? '' : 's'} voltaram ao lugar sozinhos` : 'Ajustes fora do lugar'}</b>
      <span>${restored.length ? 'O Windows tinha desfeito desde a última vez que você abriu o AZOR. Foram reaplicados e reconferidos agora: ' + esc(restored.map(x => x.name).join(', ')) + '.' : ''}
      ${failed.length ? `<i>${failed.length} não puderam ser restaurados: ${esc(failed.map(x => x.name).join(', '))}.</i>` : ''}</span>
    </div>
    <button class="btn ghost small" data-go="arsenal">VER ARSENAL</button>
  </div>`;
}

// O que o AZOR se recusa a escrever, com o caminho para o usuário fazer.
// Mesma postura do BIOS Copiloto: as opções de baixa latência do driver ficam
// atrás de APIs não publicadas, e escrever no registro do driver quebra na
// próxima atualização. Mostrar o caminho vale mais que fingir que aplica.
function driverGuideCard(){
  const d = S.driverGuide;
  if(!d || !d.ok || !d.guide) return '';
  return `<article class="card pad driver-guide">
    <div class="device-head"><div>
      <span class="eyebrow">FORA DO ALCANCE DO APP</span>
      <h3 class="section-title">Painel ${esc(d.guide.label)}: ${d.guide.items.length} ajustes que o AZOR não escreve</h3>
      <p class="section-sub">${esc(d.note)}</p>
    </div><span class="pill off">MANUAL</span></div>
    <div class="driver-path">${esc(d.guide.panel)}</div>
    <div class="driver-list">${d.guide.items.map(([nome, valor, porque]) => `
      <div class="driver-item">
        <div><b>${esc(nome)}</b><small>${esc(porque)}</small></div>
        <span class="driver-value">${esc(valor)}</span>
      </div>`).join('')}</div>
  </article>`;
}

// ===========================================================================
// PLANO DE AÇÃO
//
// O app chegou a 68 tweaks, um índice, um relatório de gargalo e uma prova
// medida — e nenhuma resposta para a única pergunta que o cliente faz: "o que eu
// faço primeiro?". Uma lista de 68 itens não é um plano; é um catálogo.
//
// Esta tela não mede nada novo. Ela ordena o que já foi medido, e cada passo diz
// de onde veio a posição dele.
// ===========================================================================

const PLAN_KIND = {
  estrutural: ['LIMITE DO HARDWARE', 'structural'],
  tweak:      ['AJUSTE PENDENTE',    'tweak'],
  manual:     ['ESCOLHA SUA',        'manual'],
  driver:     ['PAINEL DO DRIVER',   'driver'],
};

function planStep(step, index){
  const [tag, cls] = PLAN_KIND[step.kind] || ['PASSO', 'tweak'];
  return `<article class="card plan-step ${cls}">
    <div class="plan-order">${index}</div>
    <div class="plan-body">
      <div class="plan-top">
        <b>${esc(step.title || '')}</b>
        <span class="plan-tag ${cls}">${tag}</span>
        ${step.area ? `<span class="module-tag">${esc(step.area)}</span>` : ''}
        ${step.restart ? '<span class="risk restart">REINÍCIO</span>' : ''}
      </div>
      ${step.detail ? `<p>${esc(step.detail)}</p>` : ''}
      ${step.action_hint ? `<p class="plan-hint">${esc(step.action_hint)}</p>` : ''}
      ${step.gain ? `<p class="plan-gain">Ganho típico relatado: ${esc(step.gain)}</p>` : ''}
      ${step.trade_off ? `<p class="plan-cost"><b>Custa:</b> ${esc(step.trade_off)}</p>` : ''}
      <small class="plan-why">${esc(step.why || '')}</small>
    </div>
    <div class="plan-actions">
      ${step.task_id ? `<button class="btn small primary" data-apply-tweak="${esc(step.task_id)}">APLICAR</button>` : ''}
      ${step.kind === 'driver' ? '<button class="btn small ghost" data-go="arsenal">VER LISTA</button>' : ''}
    </div>
  </article>`;
}

function renderPlan(){
  const p = S.plan;
  if(!p) return `${head('Plano de Ação','Cruzando o relatório de gargalo, o arsenal e o índice para montar a ordem…')}
    <article class="card pad"><div class="skeleton-list">${'<i></i>'.repeat(6)}</div></article>`;
  if(p.ok === false) return `${head('Plano de Ação','O plano não pôde ser montado.')}
    <article class="card pad"><p class="section-sub">${esc(p.reason || '')}</p></article>`;
  const c = p.counts || {};
  if(!p.steps?.length) return `${head('Plano de Ação','Nada pendente neste perfil.')}
    <article class="card pad"><div class="empty">Sem passos: os limites estruturais estão resolvidos e
    todos os ajustes elegíveis já estão aplicados. Daqui para frente o ganho vem de hardware, e o
    Monitoramento mostra qual peça está segurando.</div></article>`;
  return `${head('Plano de Ação',
    'A ordem do maior retorno para o menor, neste PC. Cada passo diz de onde veio a posição dele.',
    '<button class="btn ghost" id="refreshPlan">↻ REFAZER O PLANO</button>')}
  <section class="arsenal-stats card">
    ${arsenalStat(p.total ?? 0, 'passos no plano', 'ordenados por retorno esperado')}
    ${arsenalStat(c.estrutural ?? 0, 'limites de hardware', 'valem mais que qualquer ajuste')}
    ${arsenalStat(c.tweak ?? 0, 'ajustes pendentes', 'o AZOR aplica sozinho')}
    ${arsenalStat((c.manual ?? 0) + (c.driver ?? 0), 'exigem sua escolha', 'risco alto ou fora do app')}
  </section>
  <p class="arsenal-note">${esc(p.note || '')}</p>
  <div class="plan-list">${p.steps.map((s, i) => planStep(s, i + 1)).join('')}</div>`;
}

async function loadPlan(force = false){
  try{ S.plan = await getJSON('/api/action-plan?profile=' + encodeURIComponent(S.quickProfile || 'auto'), 60000); }
  catch(e){ S.plan = { ok:false, reason:e.message }; }
  if(S.page === 'plan') render();
}

async function loadDriverGuide(){
  try{ S.driverGuide = await getJSON('/api/driver-guide'); if(S.page==='arsenal') render(); }
  catch(e){ console.warn('driver guide', e); }
}

async function loadDrift(){
  try{ S.drift = await getJSON('/api/drift'); }catch(e){ console.warn('drift', e); }
}

async function proveTweak(id, btn){
  if(!id) return;
  S.proofs[id] = { running:true };
  const old = btn?.textContent;
  if(btn){ btn.disabled = true; btn.textContent = 'MEDINDO…'; }
  render();
  try{
    // Medição de verdade: duas passagens de 400 amostras. Timeout folgado porque
    // é para demorar mesmo.
    const r = await postJSON('/api/action', { name:'prove_task', id, samples:400 }, 120000);
    S.proofs[id] = r;
    toast(r.detail || 'Medição concluída.', r.verdict !== 'loss');
    await loadArsenal(true);
  }catch(e){
    S.proofs[id] = { ok:false, detail:e.message };
    toast(e.message, false);
  }finally{
    if(btn){ btn.disabled = false; btn.textContent = old; }
    render();
  }
}

let arsenalRead=null;
async function loadArsenal(force = false){
 const profile=S.quickProfile||'auto';
 if(arsenalRead?.profile===profile)return arsenalRead.promise;
 const request={profile,promise:null};
 arsenalRead=request;
 request.promise=(async()=>{
  let result;
  try{result=await getJSON('/api/arsenal?profile='+encodeURIComponent(profile))}
  catch(e){result={ok:false,reason:e.message||String(e)}}
  if(arsenalRead!==request)return;
  arsenalRead=null;
  if((S.quickProfile||'auto')!==profile)return;
  S.arsenal=result;
  if(['arsenal','declutter'].includes(S.page))render();
 })();
 return request.promise;
}

async function relaunchAsAdmin(btn){
  const old = btn?.textContent;
  if(btn){ btn.disabled = true; btn.textContent = 'PEDINDO PERMISSÃO…'; }
  try{
    const r = await postJSON('/api/action', { name:'relaunch_admin' }, 70000);
    toast(r.detail || (r.ok ? 'Reabrindo…' : 'Não foi possível reabrir.'), !!r.ok);
    // Sucesso aqui significa que o launcher elevado começou a subir, e é ELE quem
    // encerra este backend. A página fica avisando em vez de fingir que segue viva.
    if(r.ok && !r.already){
      const view = $('#view');
      if(view) view.innerHTML = `<article class="card pad"><h2>Reabrindo como administrador…</h2>
        <p class="section-sub">O launcher do AZOR está subindo com privilégio elevado e vai fechar
        esta janela em alguns segundos. Se nada acontecer, abra o AZOR pelo atalho da área de trabalho.</p></article>`;
    }
  }catch(e){ toast(e.message, false); }
  finally{ if(btn){ btn.disabled = false; btn.textContent = old; } }
}

async function applyTweak(id, btn){
  if(!id) return;
  const task = (S.arsenal?.tasks || []).find(t => t.id === id);
  // Risco alto pede uma confirmação com o custo escrito, não um "tem certeza?".
  if(task && (task.risk === 'high'||task.risk === 'medium')){
    const ok = confirm(`${task.name}\n\n${task.trade_off}\n\n` +
      (task.restart ? 'Este ajuste só passa a valer depois de reiniciar o Windows.\n\n' : '') +
      'Aplicar mesmo assim?');
    if(!ok) return;
  }
  const old = btn?.textContent;
  if(btn){ btn.disabled = true; btn.textContent = 'APLICANDO…'; }
  try{
    const r = await postJSON('/api/action', { name:'apply_task', id, profile:S.quickProfile || 'auto' });
    toast(r.detail || (r.ok ? 'Aplicado e confirmado.' : 'Não foi possível aplicar.'), !!r.ok);
    if(r.ok && r.restart) toast('Reinicie o Windows para este ajuste valer por completo.', true);
    await refreshSummary(false);
    await loadArsenal(true);
    S.azorIndex = null;
  }catch(e){ toast(e.message, false); }
  finally{ if(btn){ btn.disabled = false; btn.textContent = old; } }
}

// ===========================================================================
// ÍNDICE AZOR
//
// Um número de 0 a 1000 que serve para o cliente ver progresso de uma olhada.
// A regra que o mantém honesto está no core: componente que não pôde ser medido
// neste PC SAI da conta em vez de virar zero (que baixaria a nota sem motivo) ou
// virar cheio (que a inflaria). Por isso a tela mostra sempre "de N avaliados",
// nunca "de 1000" quando faltou sensor.
// ===========================================================================

function indexTone(pct){
  return pct >= 92 ? 'elite' : pct >= 80 ? 'great' : pct >= 65 ? 'good' : pct >= 45 ? 'fair' : 'poor';
}

function azorIndexCard(compact = false){
  const idx = S.azorIndex;
  if(!idx) return `<article class="card pad azor-index loading">
    <div class="device-head"><div><span class="eyebrow">ÍNDICE AZOR</span>
    <h3 class="section-title">Medindo este PC…</h3></div></div>
    <p class="section-sub">Latência de agendamento, eventos de 7 dias, limites estruturais e temperatura.
    A primeira leitura leva alguns segundos porque é medição de verdade, não estimativa.</p>
    <div class="skeleton-list">${'<i></i>'.repeat(5)}</div></article>`;
  if(idx.ok===false||!Number.isFinite(idx.score)||!Number.isFinite(idx.possible)||idx.possible<=0)
    return '<article class="card pad"><span class="eyebrow">ÍNDICE AZOR</span><h3 class="section-title">Leitura indisponível</h3><p class="section-sub">Ainda não há dados suficientes para exibir uma pontuação. Isso não significa falha no PC.</p><button class="btn ghost" id="refreshIndex">TENTAR LEITURA NOVAMENTE</button></article>';
  const pct = idx.percent ?? 0;
  const tone = indexTone(pct);
  return `<article class="card pad azor-index ${tone}">
    <div class="device-head"><div><span class="eyebrow">ÍNDICE AZOR</span>
      <h3 class="section-title">${idx.score} <small>de ${idx.possible} pontos avaliados</small></h3></div>
      <span class="pill index-grade ${tone}">${esc(idx.grade)}</span></div>
    <div class="index-bar"><span style="width:${clamp(pct, 0, 100)}%"></span></div>
    <div class="index-parts">${(idx.parts || []).map(p => `
      <div class="index-part ${p.measured ? '' : 'unmeasured'}">
        <div class="index-part-head">
          <span>${esc(p.label)}</span>
          <b>${p.measured ? `${p.points}<i>/${p.max}</i>` : 'sem medição'}</b>
        </div>
        <div class="index-part-bar"><span style="width:${p.measured ? clamp(p.points / p.max * 100, 0, 100) : 0}%"></span></div>
        <small>${esc(p.evidence)}</small>
      </div>`).join('')}</div>
    ${idx.unmeasured?.length ? `<p class="index-out">Fora da conta neste PC: ${esc(idx.unmeasured.join(', '))}.
      Um componente sem sensor não vira zero — ele sai do total, e o total diz de quanto está sendo tirado.</p>` : ''}
    <p class="index-note">${esc(idx.note || '')}</p>
    ${compact ? '' : '<button class="btn ghost" id="refreshIndex" style="margin-top:12px">↻ MEDIR DE NOVO</button>'}
  </article>`;
}

async function loadAzorIndex(force = false){
  try{
    S.azorIndex = await getJSON('/api/azor-index' + (force ? '?force=1' : ''), 60000);
  }catch(e){
    S.azorIndex = { ok:false, reason:e.message || String(e) };
  }
  if(S.page === 'home' || S.page === 'arsenal') render();
}

async function boot(){nav();clock();setInterval(clock,30000);
  if(new URLSearchParams(location.search).get('selftest')==='1')uiSelfTest();
  render();
  // Resumo e monitor sao independentes e seguem em paralelo. Saude e manutencao
  // ficaram fora da abertura: so as abas Guardian e Manutencao usam esses dados,
  // e elas ja carregam sob demanda. Buscar os dois aqui custava schtasks,
  // tasklist, powercfg e duas varreduras do TEMP antes de qualquer tela precisar.
  await Promise.allSettled([refreshSummary(false),refreshMonitor(false)]);
  // O relatorio da abertura diz o que o Windows mexeu desde a ultima sessao e o
  // que o AZOR devolveu ao lugar. Chega depois porque a reconciliacao roda numa
  // thread do backend; a tela nao espera por ele.
  loadStartupReport();
  render();
  if(document.visibilityState!=='hidden')startPolling();
}
boot();

window.addEventListener('DOMContentLoaded',markCurrent2DBuild,{once:true});
// The listener must never outlive the page that asked for it.
window.addEventListener('pagehide',pauseInputVisuals);
