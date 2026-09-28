/* Functional manager screens, sharing AZOR tokens and the existing navigation. */
function performancePages(){return {energy:renderEnergy,services:renderServiceControl,gameMode:renderGameMode}}
function renderGameMode(){
 const state=S.gameModeControl;
 if(!state)return head('Modo de jogo','Sessões temporárias, com estado original preservado.')+'<article class="card pad">Consultando a sessão…</article>';
 const config=state.profiles||{profiles:[],background:[]};
 return head('Modo de jogo','Inicie quando quiser. Nenhum jogo é aberto, encerrado ou modificado pelo AZOR.')+`
 <article class="card pad"><span class="eyebrow">${state.running?'SESSÃO ATIVA':'ATIVAÇÃO MANUAL'}</span><h3 class="section-title">${esc(state.last_status||'Aguardando ativação.')}</h3>
 <p class="section-sub">Prioridade Acima do normal é opcional; Alta exige teste manual. Tempo real não é permitido. Afinidade fica com o Windows, e anti-cheats são protegidos.</p>
 <div style="display:flex;gap:10px;flex-wrap:wrap;margin:16px 0"><button class="btn primary" id="gameModeStart" ${state.running?'disabled':''}>INICIAR MODO DE JOGO</button><button class="btn ghost" id="gameModeStop">PARAR E RESTAURAR</button><button class="btn ghost" id="gameModeRefresh">ATUALIZAR LEITURA</button></div>
 <p class="section-sub">CPU: ${Number.isFinite(state.cpu_percent)?state.cpu_percent.toFixed(1)+'%':'sem amostra de jogo'} · Processos: ${state.process_count??'—'} · Alterações de prioridade na sessão: ${state.raised??0}</p>
 ${(state.games||[]).map(g=>`<p><b>${esc(g.name)}</b> · PID ${esc(g.pid)} · alvo ${esc(g.priority)}</p>`).join('')}
 ${state.recovery_required?'<p class="warn">Há uma restauração pendente. Use Parar e restaurar antes de iniciar outra sessão.</p>':''}</article>
 <article class="card pad" style="margin-top:14px"><h3 class="section-title">Perfis de jogo</h3><p class="section-sub">Feche a sessão para editar. Minecraft Java usa também parte do caminho para não alcançar outros programas Java. Adapte o caminho ao seu launcher.</p>
 ${(config.profiles||[]).map((p,i)=>`<details class="card pad" style="margin-top:10px"><summary>${esc(p.name)} · ${esc(p.exe)}</summary><div class="grid cols-2" style="margin-top:14px">
 <label>Executável<input class="input" data-game-exe="${i}" value="${esc(p.exe)}" ${state.running?'disabled':''}></label>
 <label>Parte do caminho (opcional)<input class="input" data-game-path="${i}" value="${esc(p.path_contains||'')}" ${state.running?'disabled':''}></label>
 <label>Prioridade<select class="select" data-game-priority="${i}" ${state.running?'disabled':''}>${[['normal','Normal'],['above_normal','Acima do normal'],['high','Alta — avançado']].map(([v,n])=>`<option value="${v}" ${p.priority===v?'selected':''}>${n}</option>`).join('')}</select></label>
 <label>Energia temporária<select class="select" data-game-power="${i}" ${state.running?'disabled':''}><option value="">Preservar plano atual</option>${(state.power_plans||[]).map(x=>`<option value="${esc(x.guid)}" ${p.power_guid===x.guid?'selected':''}>${esc(x.name)}</option>`).join('')}</select></label></div></details>`).join('')}
 <h3 class="section-title" style="margin-top:20px">Segundo plano escolhido por você</h3><p class="section-sub">Somente os selecionados podem passar de Normal para Abaixo do normal com CPU ≥ 80% durante jogo. Retorna ao valor original abaixo de 60% ou ao encerrar a sessão. Nenhum processo é fechado.</p>
 <div style="display:flex;gap:16px;flex-wrap:wrap;margin:16px 0">${(state.background_options||[]).map(n=>`<label><input type="checkbox" data-game-background="${esc(n)}" ${(config.background||[]).includes(n)?'checked':''} ${state.running?'disabled':''}> ${esc(n)}</label>`).join('')}</div>
 <button class="btn primary" id="gameModeSave" ${state.running?'disabled':''}>SALVAR PERFIS</button><p class="section-sub">Energia temporária depende da permissão do Windows. Uma recusa não será contornada. Não há promessa de aumento de FPS.</p></article>`;
}
function bindGameMode(){
 const run=async(b,data)=>{b.disabled=true;try{const r=await postJSON('/api/game-mode',data,ACTION_TIMEOUT_MS);toast(r.detail||'Perfis salvos.',r.ok===true);await loadPerformancePage('gameMode')}catch(e){toast(e.message,false)}finally{b.disabled=false}};
 const start=$('#gameModeStart'),stop=$('#gameModeStop'),refresh=$('#gameModeRefresh'),save=$('#gameModeSave');
 if(start)start.onclick=()=>run(start,{operation:'start'});
 if(stop)stop.onclick=()=>run(stop,{operation:'stop'});
 if(refresh)refresh.onclick=()=>loadPerformancePage('gameMode');
 if(save)save.onclick=()=>{
  const profiles=(S.gameModeControl.profiles.profiles||[]).map((p,i)=>({...p,exe:$(`[data-game-exe="${i}"]`).value.trim(),path_contains:$(`[data-game-path="${i}"]`).value.trim(),priority:$(`[data-game-priority="${i}"]`).value,power_guid:$(`[data-game-power="${i}"]`).value||null}));
  if(profiles.some(p=>p.priority==='high')&&!confirm('Prioridade Alta pode prejudicar áudio e responsividade. Salvar essa opção avançada para teste manual?'))return;
  run(save,{operation:'configure',profiles,background:$$('[data-game-background]:checked').map(e=>e.dataset.gameBackground)})
 };
}
function renderEnergy(){
 const state=S.powerControl;
 if(!state)return head('Energia','Planos existentes e política de CPU, com restauração por alteração.')+'<article class="card pad"><p class="section-sub">Consultando os planos do Windows…</p></article>';
 const cpu=state.cpu||{};
 return head('Energia','A política do Windows continua sendo o padrão. Nenhum ajuste é aplicado ao abrir esta tela.')+`
 <section class="grid cols-2">
 <article class="card pad"><span class="eyebrow">PLANO ATIVO</span><h3 class="section-title">Escolha o plano de energia</h3>
 <p class="section-sub">Os planos abaixo foram encontrados neste PC. Trocar de plano guarda o GUID anterior para restauração.</p>
 <select class="select" id="powerScheme" style="width:100%;margin:16px 0">${(state.plans||[]).map(p=>`<option value="${esc(p.guid)}" ${p.guid===state.active?'selected':''}>${esc(p.name)}</option>`).join('')}</select>
 <button class="btn primary" id="applyPowerScheme">APLICAR PLANO</button>
 <button class="btn ghost" data-apply-tweak="power_plan">APLICAR AZOR DESEMPENHO</button>
 <p class="section-sub">AZOR DESEMPENHO usa o Alto desempenho como base, permite repouso da CPU e preserva as políticas de USB, PCIe e armazenamento. Pode alterar consumo e temperatura.</p></article>
 <article class="card pad"><span class="eyebrow">PROCESSADOR • NA TOMADA</span><h3 class="section-title">Política de CPU</h3>
 <p class="section-sub">Deixe os campos vazios para preservar o sistema. Não são controles de overclock. Suporte varia por plataforma.</p>
 ${cpu.ok===false?`<p class="warn">${esc(cpu.detail||'Leitura indisponível.')}</p>`:`
 <div class="grid cols-2" style="margin:16px 0">
 <label>Mínimo (%)<input class="input" id="cpuMinimum" type="number" min="0" max="100" placeholder="Sistema (${esc(cpu.minimum??'—')}%)"></label>
 <label>Máximo (%)<input class="input" id="cpuMaximum" type="number" min="0" max="100" placeholder="Sistema (${esc(cpu.maximum??'—')}%)"></label></div>
 <label>CPU Boost<select class="select" id="cpuBoost" style="width:100%;margin:8px 0 16px">${[['system','Automático — preservar'],['efficiency','Eficiência'],['performance','Desempenho'],['aggressive','Agressivo — teste manual'],['efficient_aggressive','Agressivo eficiente — teste manual'],['disabled','Desativado']].map(([id,label])=>`<option value="${id}">${label}</option>`).join('')}</select></label>
 <button class="btn primary" id="applyCpuPolicy">APLICAR POLÍTICA DE CPU</button>`}
 <p class="section-sub">Boost agressivo é opcional, nunca selecionado automaticamente. Afinidade e estacionamento de núcleos continuam sob o Windows.</p></article>
 </section><article class="card pad" style="margin-top:14px"><h3 class="section-title">Voltar ao estado anterior</h3><p class="section-sub">A aplicação guarda os índices anteriores e confirma a releitura. Se algo falhar, tenta restaurar imediatamente.</p><button class="btn ghost" data-go="restore">ABRIR HISTÓRICO E RESTAURAÇÃO</button></article>`;
}
function renderServiceControl(){
 const state=S.serviceControl;
 const labels={spooler:'Impressão, inclusive PDF',diagtrack:'Diagnóstico e experiências conectadas',bthserv:'Bluetooth',xblgamesave:'Salvamentos Xbox',xboxnetapisvc:'Rede Xbox',xboxgipsvc:'Acessórios Xbox'};
 return head('Serviços opcionais','Nada será desligado automaticamente. Serviços de segurança, atualização, áudio, drivers e anti-cheat são protegidos.')+`
 <article class="card pad"><h3 class="section-title">Revise o recurso antes de alterar</h3><p class="section-sub">Desativar pode impedir impressoras, controles Bluetooth ou Game Pass de funcionar. Uma contagem menor de processos não comprova maior desempenho.</p>
 <div class="recovery-list">${!state?'<p class="section-sub">Consultando estado e dependências…</p>':(state.items||[]).map(s=>`
 <div class="recovery-row"><div><b>${esc(labels[String(s.name).toLowerCase()]||s.name)}</b><p>${esc(s.name)} · ${s.exists===false?'Não instalado':s.exists==null?'Leitura indisponível':s.running?'Em execução':'Parado'} · ${esc(s.start_label||'')}</p>
 <small>${esc(s.detail||((s.dependents||[]).length?'Dependências ativas: '+s.dependents.join(', '):'Nenhuma dependência ativa reportada.'))}</small></div>
 ${s.exists===true?`<div><button class="btn ghost" data-service="${esc(s.name)}" data-start-type="Manual">USAR INÍCIO MANUAL</button><button class="btn danger" data-service="${esc(s.name)}" data-start-type="Disabled" ${s.dependents?.length?'disabled':''}>DESATIVAR</button></div>`:''}</div>`).join('')}</div></article>
 <button class="btn ghost" data-go="restore" style="margin-top:14px">RESTAURAR ALTERAÇÕES</button>`;
}
async function loadPerformancePage(page){
 const key=page==='energy'?'powerControl':page==='gameMode'?'gameModeControl':'serviceControl';
 if(S[key+'Loading'])return;S[key+'Loading']=true;
 try{S[key]=await getJSON(page==='energy'?'/api/power-control':page==='gameMode'?'/api/game-mode':'/api/service-control',60000)}
 catch(e){S[key]={ok:false,last_status:e.message,cpu:{ok:false,detail:e.message},items:[{name:'Consulta',detail:e.message}],plans:[]};toast(e.message,false)}
 finally{S[key+'Loading']=false;if(S.page===page)render()}
}
function bindPerformancePage(){
 bindGameMode();
 const run=async(button,url,data)=>{
  button.disabled=true;const old=button.textContent;button.textContent='AGUARDANDO CONFIRMAÇÃO…';
  try{const result=await postJSON(url,data,ACTION_TIMEOUT_MS);toast(result.detail||'Operação concluída.',result.ok===true);S.restorePoints=null;await loadPerformancePage(S.page)}
  catch(e){toast(e.message,false)}
  finally{button.disabled=false;button.textContent=old}
 };
 const plan=$('#applyPowerScheme');
 if(plan)plan.onclick=()=>run(plan,'/api/power-control',{operation:'power_plan',guid:$('#powerScheme').value});
 const cpu=$('#applyCpuPolicy');
 if(cpu)cpu.onclick=()=>{
  const boost=$('#cpuBoost').value,minimum=$('#cpuMinimum').value,maximum=$('#cpuMaximum').value;
  if((boost.includes('aggressive')||minimum==='100')&&!confirm('Este ajuste pode elevar consumo e temperatura. Aplicar apenas para um teste e poder restaurar depois?'))return;
  run(cpu,'/api/power-control',{operation:'power_cpu',guid:S.powerControl.cpu.guid,minimum:minimum===''?null:Number(minimum),maximum:maximum===''?null:Number(maximum),boost})
 };
 $$('[data-service]').forEach(button=>button.onclick=()=>{
  if(!confirm('Alterar '+button.dataset.service+' para '+button.dataset.startType+'? Confirme que não precisa do recurso. A alteração ficará no histórico para restauração.'))return;
  run(button,'/api/service-control',{name:button.dataset.service,start_type:button.dataset.startType,confirmed:true})
 });
}
