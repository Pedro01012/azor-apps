# TWEAKS — o que o AZOR faz, por que, e o que custa
> Gerado por `tools/gen_tweaks_doc.py` a partir do motor declarativo.
> Nao edite a mao: edite o tweak no modulo e rode o gerador de novo.

**72 tweaks** em 13 modulos. Todo tweak abaixo detecta o estado atual, aplica, rele o valor do Windows e so entao reporta sucesso. Um tweak que o Windows nao confirma e reportado como falha, nunca como concluido.

## Legenda
- **Reversivel**: existe codigo que desfaz este tweak sozinho, a partir do baseline anterior ao AZOR. `nao` significa que a acao nao volta atras — e o app diz isso antes de aplicar.
- **Metrica**: qual numero medido este tweak deveria mover. Vazio significa que ele e preferencia, nao desempenho — e o app nao promete ganho.
- **Fora do clique unico**: o tweak existe e e reversivel, mas nao entra no botao BOOST. Sao os de risco alto (reduzem seguranca, ou a volta pode exigir Modo de Seguranca) e os experimentais (resultado varia por maquina). Eles se aplicam um a um, na tela Arsenal, depois de o usuario ler o custo.

14 dos 72 tweaks estao fora do clique unico: `gpu_msi`, `mpo_off`, `tdr_delay`, `usb_controller_msi`, `memory_compression_off`, `processor_idle_disable`, `sysmain_ssd_off`, `prefetcher_ssd_off`, `storage_msi`, `defender_game_exclusions`, `fullscreen_exclusive`, `memory_integrity_off`, `svchost_split_threshold`, `win32_priority_separation`.

## Reparo
Detecta e desfaz estragos deixados por outros otimizadores. Em um PC intacto este módulo não tem nada a fazer, e diz isso.

### Religar o pre-carregamento de programas  
`app_launch_cache_repair` · risco **Seguro** · perfis: SEGURO, COMPETITIVO, CAMPANHA, JOGO + LIVE

Religa o SysMain (antigo Superfetch) e o Prefetcher, que sao as duas pecas que fazem o Windows pre-carregar os programas que voce mais usa. Quando os dois estao desligados, TODO aplicativo passa a abrir do zero, e o cliente sente o PC lento sem saber por que.

- **Fonte:** Servico SysMain e EnablePrefetcher em HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management\PrefetchParameters. O valor 3 (padrao do Windows) pre-carrega aplicativos e boot.
- **Custo / trade-off:** "Desative o Superfetch, voce tem SSD" e conselho de 2012: nasceu quando o servico paginava em disco mecanico e quando SSD tinha pouca resistencia a escrita. Em Windows 10/11 ele cacheia em RAM, cede prioridade sob carga e nem roda durante a partida - ou seja, desligar nao devolve FPS, so devolve tela de espera ao abrir programa. Nao e reversivel pelo AZOR: quem quiser desligar de novo tem o item experimental na lista manual.
- **Metrica impactada:** Tempo ate a janela do programa aparecer, da segunda abertura em diante
- **Reversivel individualmente:** nao
- **Verificacao apos aplicar:** sim, rele o valor

### Remover overrides de temporizador no boot  
`bcd_timer_repair` · risco **Moderado** · perfis: SEGURO, COMPETITIVO, CAMPANHA, JOGO + LIVE · exige reiniciar

Apaga do boot as opções useplatformclock, disabledynamictick, tscsyncpolicy e similares. Nenhuma delas existe num Windows de fábrica: se está lá, alguém gravou. Forçar o HPET como fonte de tempo costuma AUMENTAR a latência em CPU moderna, que é o contrário do que o guia prometia.

- **Fonte:** bcdedit /deletevalue {current} <opção> — Opções de inicialização do Windows, Microsoft Learn. A detecção é pela presença do nome da opção no {current}, que não é traduzido, e não pelo valor, que é.
- **Custo / trade-off:** Exige reiniciar. Não é reversível pelo AZOR de propósito: o app não oferece um botão para forçar o HPET de volta. Se você quiser mesmo, o comando é 'bcdedit /set useplatformclock true'.
- **Metrica impactada:** Latência de DPC e jitter de agendamento (µs)
- **Reversivel individualmente:** nao
- **Verificacao apos aplicar:** sim, rele o valor

### Parar de zerar o arquivo de paginação no desligamento  
`clear_pagefile_repair` · risco **Seguro** · perfis: SEGURO, COMPETITIVO, CAMPANHA, JOGO + LIVE

Desfaz a configuração que faz o Windows sobrescrever o arquivo de paginação inteiro toda vez que o PC desliga. Em um pagefile de vários GB isso são minutos de tela de desligamento — e nenhuma melhora de desempenho.

- **Fonte:** ClearPageFileAtShutdown em HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management — opção de segurança documentada pela Microsoft, pensada para máquinas com dados sensíveis.
- **Custo / trade-off:** Não é reversível pelo AZOR: religar isso só faz sentido em ambiente que exige apagar dados residuais por política, e nesse caso quem configura é o administrador do domínio, não um otimizador de jogo.
- **Metrica impactada:** Tempo de desligamento
- **Reversivel individualmente:** nao
- **Verificacao apos aplicar:** sim, rele o valor

### Religar serviços essenciais desabilitados  
`essential_services_repair` · risco **Moderado** · perfis: SEGURO, COMPETITIVO, CAMPANHA, JOGO + LIVE

Devolve ao padrão do Windows os serviços que nenhum otimizador deveria ter desligado: áudio, temas, DHCP, DNS, log de eventos, agendador, firewall e Windows Update. Cada um é relido depois de alterado.

- **Fonte:** Tipos de inicialização padrão dos serviços do Windows. Busca e Windows Defender ficam FORA desta lista de propósito: desligar a busca é preferência legítima, e o Defender fica desligado em PC com antivírus de terceiro.
- **Custo / trade-off:** Não é reversível pelo AZOR: o app não oferece desligar o áudio ou o firewall de novo. O padrão restaurado é o do Windows, não o que estava antes — se o serviço já chegou desabilitado, 'o que estava antes' também é o defeito.
- **Metrica impactada:** Funcionalidades do Windows que voltam a funcionar
- **Reversivel individualmente:** nao
- **Verificacao apos aplicar:** sim, rele o valor

### Religar o Firewall do Windows  
`firewall_repair` · risco **Seguro** · perfis: SEGURO, COMPETITIVO, CAMPANHA, JOGO + LIVE

Religa os perfis do firewall que estiverem desligados e confirma por releitura. Desligar o firewall é um 'tweak' que circula como se desse FPS; ele não dá, e deixa a máquina exposta na rede.

- **Fonte:** Set-NetFirewallProfile -Enabled True (módulo NetSecurity do PowerShell). Os perfis são lidos por Get-NetFirewallProfile, cujos nomes de propriedade não dependem do idioma do Windows.
- **Custo / trade-off:** Nenhum custo de desempenho mensurável. Não é reversível pelo AZOR: o app não desliga firewall de cliente.
- **Metrica impactada:** nenhuma (preferencia, nao desempenho)
- **Reversivel individualmente:** nao
- **Verificacao apos aplicar:** sim, rele o valor

### Religar a Proteção do Sistema  
`system_restore_repair` · risco **Seguro** · perfis: SEGURO, COMPETITIVO, CAMPANHA, JOGO + LIVE

Reativa os pontos de restauração do Windows no disco do sistema. Isto é pré-requisito do próprio AZOR: sem Proteção do Sistema, o ponto de restauração que ele pede antes de otimizar não pode ser criado.

- **Fonte:** Enable-ComputerRestore (módulo Microsoft.PowerShell.Management). O estado é lido em HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore (RPSessionInterval e DisableSR).
- **Custo / trade-off:** Os pontos de restauração ocupam espaço em disco — por padrão poucos por cento do volume. Não é reversível pelo AZOR: desligar a rede de segurança do cliente não é uma função do produto.
- **Metrica impactada:** Existência de ponto de restauração antes de qualquer alteração
- **Reversivel individualmente:** nao
- **Verificacao apos aplicar:** sim, rele o valor

### Reparar o auto-ajuste da janela TCP  
`tcp_autotuning_repair` · risco **Seguro** · perfis: SEGURO, COMPETITIVO, CAMPANHA, JOGO + LIVE

Devolve o auto-ajuste da janela de recepção para 'normal'. Vários otimizadores desligam esse recurso achando que reduz ping; o efeito real é download preso em uma fração da velocidade contratada.

- **Fonte:** Set-NetTCPSetting -AutoTuningLevelLocal Normal — Receive Window Auto-Tuning, documentado pela Microsoft. 'Normal' é o padrão do Windows desde o Vista.
- **Custo / trade-off:** Nenhum custo conhecido no Windows atual. Não é reversível pelo AZOR: voltar para 'disabled' é justamente o defeito que este item conserta.
- **Metrica impactada:** Vazão de download em conexão rápida
- **Reversivel individualmente:** nao
- **Verificacao apos aplicar:** sim, rele o valor

### Reativar o TRIM do SSD  
`trim_repair` · risco **Seguro** · perfis: SEGURO, COMPETITIVO, CAMPANHA, JOGO + LIVE

Religa a notificação de exclusão (TRIM) quando ela foi desativada. Só aparece se o TRIM estiver realmente desligado neste PC.

- **Fonte:** fsutil behavior set disabledeletenotify 0 — referência do fsutil, Microsoft Learn. O nome da chave é invertido: DisableDeleteNotify=0 significa TRIM LIGADO.
- **Custo / trade-off:** Não é reversível pelo AZOR de propósito. Desligar o TRIM de novo degradaria o SSD, e o app não oferece um botão para piorar o disco do cliente.
- **Metrica impactada:** Desempenho de escrita do SSD ao longo do tempo
- **Reversivel individualmente:** nao
- **Verificacao apos aplicar:** sim, rele o valor

### Religar o cache de escrita do disco  
`write_cache_repair` · risco **Moderado** · perfis: SEGURO, COMPETITIVO, CAMPANHA, JOGO + LIVE · exige reiniciar

Devolve o cache de escrita aos discos em que ele foi desligado. Desligado, cada gravação espera o disco confirmar fisicamente - o PC inteiro fica lento de um jeito que nenhum tweak compensa.

- **Fonte:** UserWriteCacheSetting em ...\Enum\<disco>\Device Parameters\Disk - e a caixa 'Habilitar cache de gravação no dispositivo' da aba Políticas do disco, no Gerenciador de Dispositivos.
- **Custo / trade-off:** Não e reversível pelo AZOR: desligar o cache de escrita de novo só faz sentido com no-break e por decisão de quem administra a máquina, não num otimizador de jogo. Exige reiniciar.
- **Metrica impactada:** Velocidade de escrita do disco
- **Reversivel individualmente:** nao
- **Verificacao apos aplicar:** sim, rele o valor

## Windows & Registro
Preferências de jogos e interface do usuário que podem ser gravadas e relidas.

### Reduzir apps em segundo plano  
`background_apps` · risco **Moderado** · perfis: COMPETITIVO · grava 1 valor(es) de registro

Reduz a preferência global de apps em background apenas no modo competitivo.

- **Fonte:** Preferência global de apps em segundo plano (BackgroundAccessApplications\GlobalUserDisabled).
- **Custo / trade-off:** Apps da Store deixam de atualizar sozinhos: notificação de mensagem, e-mail e alarme podem atrasar.
- **Metrica impactada:** Processos ativos e uso de CPU em repouso
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Não abrir o painel da Game Bar ao iniciar o jogo  
`game_bar_panel_off` · risco **Seguro** · perfis: COMPETITIVO, CAMPANHA · grava 2 valor(es) de registro

Impede o painel inicial da Game Bar de aparecer quando um jogo abre. É o aviso que rouba o foco no primeiro segundo da partida.

- **Fonte:** Configurações > Jogos > Xbox Game Bar (ShowStartupPanel em HKCU\Software\Microsoft\GameBar).
- **Custo / trade-off:** O atalho Win+G continua funcionando; só o painel automático deixa de abrir sozinho. Se você usa a Game Bar para gravar, prefira mantê-lo.
- **Metrica impactada:** Perda de foco no início da partida
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Desligar a gravação em segundo plano  
`game_dvr` · risco **Seguro** · perfis: SEGURO, COMPETITIVO, JOGO + LIVE · grava 2 valor(es) de registro

Desativa captura em segundo plano suportada e confirma o resultado. Fora do perfil CAMPANHA: quem joga história costuma querer a gravação ligada para salvar momentos.

- **Fonte:** Xbox Game Bar / Capturas (Configurações > Jogos > Capturas). GameDVR_Enabled e AppCaptureEnabled, ambos por usuário.
- **Custo / trade-off:** Você perde o 'gravar os últimos 30 segundos'. Se usa esse recurso, mantenha ligado.
- **Metrica impactada:** FPS médio e 1% low
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Priorizar o jogo em primeiro plano  
`game_mode` · risco **Seguro** · perfis: SEGURO, COMPETITIVO, CAMPANHA, JOGO + LIVE · grava 2 valor(es) de registro

Ativa o Game Mode e exige releitura do estado.

- **Fonte:** Game Mode do Windows (Configurações > Jogos > Modo de Jogo). Chaves HKCU\Software\Microsoft\GameBar.
- **Custo / trade-off:** Praticamente nenhum. O Windows adia atualizações e reduz atividade de segundo plano durante o jogo.
- **Metrica impactada:** Consistência de frametime (p99)
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Desligar os destaques da pesquisa  
`search_highlights_off` · risco **Seguro** · perfis: COMPETITIVO, CAMPANHA, JOGO + LIVE · grava 1 valor(es) de registro

Os destaques da caixa de pesquisa buscam conteúdo na internet de tempos em tempos. Desligar tira um consumidor periódico de rede e CPU que não serve para nada durante o jogo.

- **Fonte:** Configurações > Privacidade e segurança > Permissões de pesquisa > Destaques da pesquisa (IsDynamicSearchBoxEnabled).
- **Custo / trade-off:** A caixa de pesquisa deixa de mostrar sugestões e datas comemorativas. A busca local por arquivos e programas continua igual.
- **Metrica impactada:** Uso de rede e CPU em repouso
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Remover o atraso de inicialização do Windows  
`startup_delay_off` · risco **Seguro** · perfis: COMPETITIVO, CAMPANHA, JOGO + LIVE · grava 1 valor(es) de registro

O Explorer segura os programas de inicialização por alguns segundos depois do login, para a área de trabalho aparecer antes. Zerar isso deixa o PC utilizável mais cedo, ao custo de um login mais movimentado.

- **Fonte:** StartupDelayInMSec em HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize. O atraso padrão do Windows é de cerca de 10 segundos.
- **Custo / trade-off:** Tudo que inicia junto com o Windows passa a disputar disco e CPU ao mesmo tempo do login. Em PC com muitos programas de inicialização e disco mecânico, a área de trabalho pode demorar mais para responder.
- **Metrica impactada:** Tempo até o PC ficar utilizável depois do login
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Desligar transparência da interface  
`transparency` · risco **Seguro** · perfis: SEGURO, COMPETITIVO, CAMPANHA, JOGO + LIVE · grava 1 valor(es) de registro

Desativa transparência visual e relê o valor.

- **Fonte:** Configurações > Personalização > Cores > Efeitos de transparência (EnableTransparency).
- **Custo / trade-off:** Windows fica com aparência mais simples. Alivia a GPU no desktop, não dentro do jogo em tela cheia.
- **Metrica impactada:** Uso de GPU no desktop
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Priorizar desempenho nos efeitos visuais  
`visual_effects` · risco **Moderado** · perfis: COMPETITIVO, JOGO + LIVE · grava 1 valor(es) de registro

Prioriza efeitos visuais de desempenho em perfis que pedem responsividade. O CAMPANHA preserva a aparência do Windows.

- **Fonte:** Opções de Desempenho do Windows (VisualFXSetting=2, 'Ajustar para obter melhor desempenho').
- **Custo / trade-off:** Animações, sombras e suavização de fonte mudam. É a alteração mais visível de todas.
- **Metrica impactada:** Responsividade da área de trabalho
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Ocultar Widgets da barra de tarefas  
`widgets` · risco **Seguro** · perfis: COMPETITIVO, CAMPANHA · grava 1 valor(es) de registro

Oculta Widgets do usuário atual e confirma a preferência.

- **Fonte:** Configurações > Personalização > Barra de tarefas > Widgets (TaskbarDa).
- **Custo / trade-off:** Você perde o painel de clima/notícias. O processo do Widgets deixa de ser acordado pela barra.
- **Metrica impactada:** Processos ativos em repouso
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Desligar sugestões promocionais  
`windows_suggestions` · risco **Seguro** · perfis: SEGURO, COMPETITIVO, CAMPANHA, JOGO + LIVE · grava 3 valor(es) de registro

Desativa sugestões promocionais do usuário atual.

- **Fonte:** ContentDeliveryManager, o mesmo que Configurações > Personalização > Iniciar desliga.
- **Custo / trade-off:** Nenhum desempenho é prometido aqui: isso remove propaganda, não gera FPS.
- **Metrica impactada:** nenhuma (preferencia, nao desempenho)
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

## Núcleo do Windows
Agendador, MMCSS, power throttling e modo exclusivo de tela cheia. Tudo verificado por releitura e reversível pelo baseline.

### Tirar as pastas de jogo da verificação em tempo real  
`defender_game_exclusions` · risco **Moderado** · perfis: COMPETITIVO · **fora do clique unico**

Cada arquivo que o jogo lê passa antes pelo antivírus. Em carregamento de mapa e compilação de shader, isso são milhares de verificações por segundo. Excluir apenas as pastas de instalação dos jogos detectados tira esse custo de onde ele mais aparece.

- **Fonte:** Add-MpPreference -ExclusionPath / Get-MpPreference — módulo Defender do PowerShell, documentado pela Microsoft. É a mesma lista de Segurança do Windows > Proteção contra vírus > Exclusões.
- **Custo / trade-off:** O que estiver dentro dessas pastas deixa de ser verificado em tempo real — inclusive um módulo ou 'cheat' baixado para dentro da pasta do jogo. Por isso o AZOR exclui só as pastas de instalação que ele mesmo detectou, nunca o disco inteiro nem Downloads, e por isso este item exige um clique seu.
- **Metrica impactada:** Tempo de carregamento e picos de I/O durante a partida
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Parar de enviar atualizações do Windows para outros PCs  
`delivery_optimization_off` · risco **Seguro** · perfis: COMPETITIVO, JOGO + LIVE · grava 1 valor(es) de registro

A Otimização de Entrega usa a sua conexão para distribuir atualizações do Windows a outros computadores, inclusive fora da sua rede. É upload consumido em segundo plano, e upload saturado é uma das causas reais de ping instável em jogo.

- **Fonte:** Política DODownloadMode (Configuração do Computador > Componentes do Windows > Otimização de Entrega). 0 = somente HTTP, sem compartilhamento com outros pares.
- **Custo / trade-off:** Baixar atualizações grandes pode ficar mais lento em rede com vários PCs, porque cada um passa a buscar direto da Microsoft em vez de pegar do vizinho. As atualizações continuam chegando normalmente.
- **Metrica impactada:** Upload em segundo plano e estabilidade do ping
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Desligar a Inicialização Rápida  
`fast_startup_off` · risco **Moderado** · perfis: COMPETITIVO, CAMPANHA, JOGO + LIVE · grava 1 valor(es) de registro

A Inicialização Rápida não desliga o PC de verdade: ela hiberna o núcleo do Windows e o restaura no próximo boot. É por isso que 'reiniciei e voltou tudo' acontece — ajuste de driver e de kernel volta com o estado antigo junto. Desligada, o desligamento passa a ser um desligamento.

- **Fonte:** HiberbootEnabled em HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power. É a mesma caixa de Opções de Energia > Escolher a função dos botões de energia > Ligar inicialização rápida. O AZOR usa a chave em vez de 'powercfg /h off' para não apagar o arquivo de hibernação de quem usa hibernar.
- **Custo / trade-off:** O PC liga alguns segundos mais devagar depois de um desligamento. Em compensação, reiniciar passa a valer de verdade: driver novo, ajuste de kernel e mudança de BIOS só assumem depois de um boot completo.
- **Metrica impactada:** Consistência dos ajustes entre reinícios
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Tela cheia exclusiva (desligar Fullscreen Optimizations)  
`fullscreen_exclusive` · risco **Moderado** · perfis: COMPETITIVO · **fora do clique unico** · grava 4 valor(es) de registro

Devolve ao jogo a tela cheia exclusiva de verdade, em vez da janela sem borda que o Windows passou a usar por padrão. É o caminho mais curto entre o frame pronto e o monitor, porque tira o compositor do meio.

- **Fonte:** Fullscreen Optimizations (HKCU\System\GameConfigStore). Mesmas chaves que a aba Compatibilidade do executável altera ao marcar 'Desabilitar otimizações de tela cheia'.
- **Custo / trade-off:** Alt-tab fica mais lento, e overlays que desenham por cima (Game Bar, Discord, alguns capturadores) podem parar de aparecer. Por isso ele fica fora do perfil JOGO + LIVE.
- **Metrica impactada:** Latência de clique até pixel
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Prioridade Alta para o jogo em execução  
`game_priority_engine` · risco **Seguro** · perfis: COMPETITIVO, CAMPANHA, JOGO + LIVE

Enquanto o jogo estiver aberto, o AZOR eleva o processo dele para prioridade Alta. O Modo de Jogo do Windows reduz interrupções, mas não mexe na prioridade — e prioridade é o que decide quem roda primeiro quando falta núcleo, que é exatamente o momento em que o 1% low despenca.

- **Fonte:** SetPriorityClass (kernel32) com HIGH_PRIORITY_CLASS — a mesma prioridade que o Gerenciador de Tarefas oferece em Detalhes > Definir prioridade > Alta.
- **Custo / trade-off:** Vale só enquanto o AZOR estiver aberto: prioridade de processo morre com o processo, e por isso este item não escreve nada no Windows. O AZOR usa Alta e nunca Tempo Real — em tempo real o jogo passa na frente do próprio driver de entrada e do áudio, e o PC inteiro engasga. Nada de segundo plano é rebaixado: derrubar processo que o app não conhece quebra navegador e captura sem ninguém entender por quê.
- **Metrica impactada:** 1% low e consistência de frametime sob falta de núcleo
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Bloquear a gravação em segundo plano no nível da máquina  
`gamedvr_machine_policy` · risco **Seguro** · perfis: COMPETITIVO · grava 1 valor(es) de registro

A versão por máquina do mesmo desligamento que já existe por usuário. Ela sobrevive a criação de um perfil novo e a reativação pela Game Bar.

- **Fonte:** Política AllowGameDVR (Configuração do Computador > Modelos Administrativos > Componentes do Windows > Gravação e transmissao de jogos do Windows).
- **Custo / trade-off:** Enquanto estiver aplicado, nenhum usuário deste PC consegue ligar a gravação em segundo plano pela Game Bar - inclusive você.
- **Metrica impactada:** FPS medio e 1% low
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Fazer o timer de alta resolução valer para todo o sistema  
`global_timer_resolution` · risco **Moderado** · perfis: COMPETITIVO, CAMPANHA, JOGO + LIVE · exige reiniciar · grava 1 valor(es) de registro

Desde o Windows 10 2004, o pedido de timer de 0,5 ms vale só para o processo que pediu — o resto do sistema continua no timer grosso. Está chave devolve o comportamento global. É o ajuste que faz o Timer do AZOR realmente alcançar o jogo em vez de valer só dentro do próprio app.

- **Fonte:** Mudança de comportamento do timer em Windows 10 2004, documentada pela Microsoft no blog de desenvolvimento do kernel; chave GlobalTimerResolutionRequests em HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Kernel.
- **Custo / trade-off:** Timer fino para o sistema inteiro significa mais interrupções e um pouco mais de consumo em repouso — em notebook na bateria isso aparece na autonomia. Exige reiniciar para valer.
- **Metrica impactada:** Jitter de agendamento (µs) medido no AZOR Scope
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Desligar a hibernação  
`hibernate_off` · risco **Moderado** · perfis: COMPETITIVO

Libera o hiberfil.sys, que ocupa perto de 40% da RAM em disco, e fecha de vez a porta da Inicialização Rápida - ela depende da hibernação para existir. E o complemento do ajuste que desliga a Inicialização Rápida: um tira o comportamento, este tira a base.

- **Fonte:** powercfg /hibernate off - opções de linha de comando do powercfg, Microsoft Learn.
- **Custo / trade-off:** Você perde hibernar e a Inicialização Rápida. Em desktop, nenhum dos dois costuma fazer falta; em notebook, hibernar faz, e por isso o AZOR nem oferece la.
- **Metrica impactada:** Espaco livre no disco do sistema e consistência entre reinicios
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Manter o núcleo do Windows na memória  
`kernel_no_paging` · risco **Moderado** · perfis: COMPETITIVO · exige reiniciar · grava 1 valor(es) de registro

Impede que o Windows mande partes do próprio núcleo e dos drivers para o arquivo de paginação. Quando isso acontece durante o jogo, o retorno do disco aparece como travada isolada — o tipo que não some por baixar a qualidade gráfica.

- **Fonte:** DisablePagingExecutive em HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management — referência de registro do gerenciador de memória, Microsoft Learn.
- **Custo / trade-off:** O núcleo passa a ocupar RAM permanentemente. Por isso o AZOR só oferece com 16 GB ou mais: abaixo disso, a memória é mais útil no jogo. Exige reiniciar.
- **Metrica impactada:** p99 de frametime e travadas isoladas
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Desligar a Integridade de Memória (HVCI/VBS)  
`memory_integrity_off` · risco **Avançado** · perfis: COMPETITIVO · exige reiniciar · **fora do clique unico** · grava 2 valor(es) de registro

A Integridade de Memória roda o kernel dentro de um hipervisor. Isso custa desempenho de CPU em toda chamada de sistema, e e o maior item isolado desta lista num Windows 11 de fábrica. Desligar devolve esse custo -- e a proteção junto.

- **Fonte:** Virtualization-based Security / Memory Integrity (HVCI) - Microsoft Learn. O mesmo interruptor de Segurança do Windows > Segurança do dispositivo > Isolamento do núcleo.
- **Custo / trade-off:** VOCE FICA MENOS PROTEGIDO. A Integridade de Memória é o que impede um driver malicioso assinado de rodar código no kernel. Alem disso, alguns anticheats exigem que ela esteja ligada e vao recusar iniciar o jogo. Por isso este item nunca entra no lote de um clique: ele exige um clique seu, e volta com outro.
- **Metrica impactada:** FPS medio e 1% low em jogo limitado por CPU
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Resposta imediata dos menus do Windows  
`menu_show_delay` · risco **Seguro** · perfis: COMPETITIVO, JOGO + LIVE · grava 1 valor(es) de registro

Zera o atraso de abertura de menu do shell. Muda a sensação do Windows, não o jogo.

- **Fonte:** HKCU\Control Panel\Desktop\MenuShowDelay. Padrão do Windows: 400 ms.
- **Custo / trade-off:** Menus abrem no instante em que o ponteiro passa, o que algumas pessoas acham apressado demais ao navegar pelo teclado.
- **Metrica impactada:** nenhuma (preferencia, nao desempenho)
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Perfil MMCSS de Jogos em prioridade alta  
`mmcss_games_priority` · risco **Moderado** · perfis: COMPETITIVO, CAMPANHA · grava 6 valor(es) de registro

Escreve o perfil MMCSS de jogos inteiro: categoria de Medium para High, prioridade de 2 para 6, E/S de arquivo em High, tarefa marcada como sensível a atraso e fora do modo de segundo plano. Vale para qualquer jogo que se registre no MMCSS, que é a maioria dos motores atuais.

- **Fonte:** MMCSS Task registry (HKLM\...\Multimedia\SystemProfile\Tasks\Games) - Microsoft Learn. Padrões do Windows: Priority 2, Scheduling Category Medium, SFIO Priority Normal.
- **Custo / trade-off:** Fica fora do perfil JOGO + LIVE de propósito: com o jogo em categoria High, o software de captura disputa CPU em desvantagem e a live é que engasga.
- **Metrica impactada:** 1% low e consistência de frametime
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Desligar o limitador de rede do MMCSS  
`network_throttling_off` · risco **Moderado** · perfis: COMPETITIVO, CAMPANHA, JOGO + LIVE · grava 1 valor(es) de registro

O Windows limita a 10 pacotes por milissegundo enquanto há multimídia ativa. 0xFFFFFFFF desliga esse limitador, que é o valor que a própria Microsoft documenta para desabilitá-lo.

- **Fonte:** Multimedia Class Scheduler Service - NetworkThrottlingIndex, mesma chave SystemProfile. Padrão 10; 0xFFFFFFFF significa 'sem limitação'.
- **Custo / trade-off:** O limitador existe para a reprodução de mídia não engasgar quando a rede satura. Sem ele, em rede muito carregada, vídeo pode gaguejar. Em jogo online, o efeito esperado e o contrário: menos atraso na fila de pacotes.
- **Metrica impactada:** Jitter de rede em jogo
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Desligar o Power Throttling  
`power_throttling_off` · risco **Moderado** · perfis: COMPETITIVO, JOGO + LIVE · grava 1 valor(es) de registro

Impede o Windows de jogar threads em estado de eficiência (EcoQoS) por conta própria. Complementa o plano AZOR FPS BOOST: um cuida da política de energia, o outro do rebaixamento por thread.

- **Fonte:** Power Throttling / EcoQoS - Microsoft Learn. Chave PowerThrottlingOff em HKLM\SYSTEM\CurrentControlSet\Control\Power\PowerThrottling.
- **Custo / trade-off:** Consumo e temperatura sobem, e em notebook a autonomia cai de forma perceptível. Em desktop na tomada, o custo é ventoinha mais audível.
- **Metrica impactada:** Clock sustentado sob carga
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Agrupar os serviços do Windows em menos processos  
`svchost_split_threshold` · risco **Moderado** · perfis: COMPETITIVO · exige reiniciar · **fora do clique unico** · grava 1 valor(es) de registro

Em PC com 4 GB ou mais, o Windows separa cada serviço em seu próprio svchost.exe — daí a lista enorme de processos idênticos no Gerenciador de Tarefas. Elevando o limiar, eles voltam a compartilhar processo: menos processos, menos memória de estrutura e menos trocas de contexto.

- **Fonte:** SvcHostSplitThresholdInKB em HKLM\SYSTEM\CurrentControlSet\Control — o mesmo limiar que a Microsoft documenta para o agrupamento de serviços por quantidade de RAM.
- **Custo / trade-off:** Serviços agrupados compartilham processo: se um falha, pode derrubar os outros do mesmo grupo, e o Gerenciador de Tarefas deixa de mostrar qual serviço consome o quê. Vale a pena em PC de jogo, menos em máquina de trabalho onde o diagnóstico importa. Só passa a valer depois de reiniciar.
- **Metrica impactada:** Número de processos e memória em repouso
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Reserva de CPU do MMCSS  
`system_responsiveness` · risco **Moderado** · perfis: COMPETITIVO, CAMPANHA, JOGO + LIVE · grava 1 valor(es) de registro

Reduz a fatia de CPU que o Windows reserva para tarefas de baixa prioridade, devolvendo-a ao processo multimídia em primeiro plano. No perfil JOGO + LIVE o valor usado e 10 em vez de 0, porque zerar a reserva estrangula o encoder da live.

- **Fonte:** Multimedia Class Scheduler Service (MMCSS) - Microsoft Learn. Chave SystemResponsiveness em HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile. O padrão do Windows cliente é 20 (20% reservados ao que não é multimídia).
- **Custo / trade-off:** Áudio e vídeo de segundo plano (Discord, navegador, captura) ficam com menos CPU garantida sob carga total. Se você grava ou transmite, use o perfil JOGO + LIVE.
- **Metrica impactada:** 1% low e p99 de frametime
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Telemetria do Windows no mínimo permitido  
`telemetry_policy_min` · risco **Seguro** · perfis: COMPETITIVO, JOGO + LIVE · grava 1 valor(es) de registro

Grava a política de coleta de dados no menor nível. Complementa o desligamento do serviço DiagTrack: um tira o coletor de execução, o outro diz ao Windows para não coletar.

- **Fonte:** Política AllowTelemetry (Configuração do Computador > Modelos Administrativos > Componentes do Windows > Coleta de Dados e Versões Prévias) — Microsoft Learn.
- **Custo / trade-off:** Nas edições Home e Pro o Windows trata 0 como 1 (Básico): a política existe, mas só as edições Enterprise/Education honram o zero. O AZOR grava e relê o valor, e não promete mais do que isso.
- **Metrica impactada:** Uso de rede e disco em repouso
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Quantum do agendador para primeiro plano  
`win32_priority_separation` · risco **Experimental** · perfis: COMPETITIVO · **fora do clique unico** · grava 1 valor(es) de registro

Muda o tamanho e o tipo do quantum do agendador (0x26: quantum longo, variável, impulso 2:1 para o primeiro plano). Fica FORA do lote automático de propósito: o resultado depende do jogo e do número de núcleos, entao ele só vale como teste A/B seu, com FPS medido antes e depois.

- **Fonte:** Win32PrioritySeparation (HKLM\SYSTEM\CurrentControlSet\Control\PriorityControl), descrito em Windows Internals: bits 4-5 tamanho do quantum, 2-3 fixo/variável, 0-1 impulso do primeiro plano. Padrão do Windows cliente: 2.
- **Custo / trade-off:** Este é o único item da lista que o AZOR não afirma que melhora. Em parte das máquinas ele não muda nada mensurável, e em jogo que usa muitas threads pode piorar o 1% low. Aplique, meca, e reverta se não melhorar.
- **Metrica impactada:** 1% low medido antes e depois
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

## Energia
Plano próprio AZOR FPS BOOST, criado a partir do Ultimate Performance e verificado pelo GUID/índices expostos.

### Impedir o SSD NVMe de entrar em baixa energia  
`nvme_idle_never` · risco **Moderado** · perfis: COMPETITIVO

O NVMe desliga partes de si quando fica parado alguns milissegundos, e voltar custa tempo. Em jogo isso aparece como travadinha no carregamento de textura depois de um trecho sem I/O.

- **Fonte:** Tempo limite de inatividade do NVMe (subgrupo de disco do powercfg). Vem oculto nas opções de energia; o AZOR revela o atributo ao aplicar.
- **Custo / trade-off:** O SSD consome um pouco mais em repouso e esquenta mais. Em notebook na bateria isso aparece na autonomia; em desktop, quase nada.
- **Metrica impactada:** Travadinhas no primeiro acesso ao disco
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### AZOR FPS BOOST  
`power_plan` · risco **Moderado** · perfis: SEGURO, COMPETITIVO, CAMPANHA, JOGO + LIVE

Cria um plano AZOR próprio baseado no Ultimate Performance, aplica índices AC de desempenho, política de boost/resfriamento quando exposta e relê tudo antes de confirmar.

- **Fonte:** powercfg — Microsoft Learn (Ultimate Performance e-9a42b02..., SUB_PROCESSOR, SUB_PCIEXPRESS, SUB_USB, SUB_DISK): https://learn.microsoft.com/windows-hardware/design/device-experiences/powercfg-command-line-options
- **Custo / trade-off:** Mais consumo, mais calor e ventoinha mais audível. Núcleos deixam de estacionar e o disco não desliga. Em notebook, só os índices de tomada (AC) são alterados; na bateria o plano mantém os valores herdados.
- **Metrica impactada:** Clock sustentado sob carga e 1% low
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Impedir a CPU de entrar em estado ocioso  
`processor_idle_disable` · risco **Avançado** · perfis: COMPETITIVO · **fora do clique unico**

Os estados C da CPU economizam energia parando núcleos, e sair deles custa tempo — é uma das fontes reais de latência que sobra depois que o plano de energia já está no máximo. Desligados, a CPU responde na hora, sempre.

- **Fonte:** powercfg SUB_PROCESSOR IDLEDISABLE — opção de processador do esquema de energia, documentada nas opções de linha de comando do powercfg (Microsoft Learn).
- **Custo / trade-off:** A CPU passa a consumir perto do máximo o tempo todo, mesmo com o PC parado: temperatura mais alta, ventoinha audível e conta de luz maior. Em máquina com refrigeração no limite, isso pode REDUZIR o desempenho por calor — o oposto do pretendido. Por isso é alto risco, fora do clique único e só em desktop.
- **Metrica impactada:** Latência de DPC/ISR e 1% low
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

## GPU
Preferências de GPU verificaveis: agendamento por hardware, interrupção por mensagem e qual placa cada jogo usa. Não faz overclock nem escreve ajuste de driver não documentado.

### Todos os jogos na GPU dedicada  
`all_games_gpu` · risco **Seguro** · perfis: COMPETITIVO, CAMPANHA, JOGO + LIVE

Varre as pastas dos lancadores instalados (Steam, Epic, Riot e bibliotecas em outros discos) e grava GpuPreference=2 para cada jogo encontrado, relendo um a um. Resolve o caso clássico do jogo que abre na placa integrada sem avisar.

- **Fonte:** Mesma preferência por aplicativo de Configurações > Sistema > Vídeo > Gráficos (HKCU\Software\Microsoft\DirectX\UserGpuPreferences).
- **Custo / trade-off:** Jogo leve rodando na dedicada gasta mais energia do que rodaria na integrada. Em notebook na bateria, isso encurta a autonomia.
- **Metrica impactada:** FPS medio em jogo que abria na GPU errada
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Colocar o monitor na taxa máxima  
`display_max_refresh` · risco **Seguro** · perfis: SEGURO, COMPETITIVO, CAMPANHA, JOGO + LIVE

Um monitor de 144 Hz ligado a 60 Hz mostra 60 quadros por segundo por mais FPS que a placa gere. É a otimização mais barata que existe e a que devolve mais que a maioria dos ajustes de registro somados — e até agora o AZOR só sabia avisar que estava errado.

- **Fonte:** EnumDisplaySettings / ChangeDisplaySettingsEx — API de modo de vídeo do Windows. É o mesmo que Configurações > Sistema > Vídeo > Vídeo avançado > Taxa de atualização. O AZOR testa o modo com CDS_TEST antes de aplicar.
- **Custo / trade-off:** Taxa mais alta consome um pouco mais de energia do monitor e da GPU. Em notebook na bateria, alguns modelos reduzem a autonomia de forma perceptível. A troca é reversível na hora, sem reiniciar.
- **Metrica impactada:** Quadros por segundo que a tela consegue mostrar
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Tela cheia exclusiva para o Fortnite (só para ele)  
`fortnite_fullscreen_exclusive` · risco **Seguro** · perfis: COMPETITIVO, CAMPANHA, JOGO + LIVE

Tira o compositor do Windows do caminho entre o frame pronto e o monitor, gravando a opção APENAS no executável do Fortnite. O AZOR já fazia isso pela chave global do GameConfigStore, que vale para todos os aplicativos e derruba o overlay do Discord, do OBS e dos capturadores no PC inteiro. Por executável o ganho é o mesmo dentro do jogo e o resto do sistema não muda.

- **Fonte:** AppCompatFlags\Layers (HKCU) — é a mesma chave que a caixinha 'Desabilitar otimizações de tela cheia' nas Propriedades do executável grava. O cliente consegue conferir e desfazer por lá.
- **Custo / trade-off:** Dentro do Fortnite, overlays que desenham por cima podem não aparecer. Fora dele, nada muda — que é justamente a diferença para a versão global.
- **Metrica impactada:** Latência de clique até pixel
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Fortnite na GPU de alto desempenho  
`fortnite_gpu` · risco **Seguro** · perfis: SEGURO, COMPETITIVO, JOGO + LIVE

Define o executável detectado para GPU de alto desempenho e rele o registro.

- **Fonte:** Configurações > Sistema > Vídeo > Gráficos do Windows. O AZOR escreve o mesmo valor (GpuPreference=2) em HKCU\Software\Microsoft\DirectX\UserGpuPreferences e rele para confirmar.
- **Custo / trade-off:** Só faz diferença em PC com duas GPUs (integrada + dedicada). Em máquina com uma GPU só, o AZOR grava a preferência mas nenhum ganho deve ser esperado - e ele diz isso em vez de fingir.
- **Metrica impactada:** FPS medio
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Prioridade alta para as interrupções da GPU  
`gpu_interrupt_priority` · risco **Moderado** · perfis: COMPETITIVO · exige reiniciar

Define a prioridade das interrupções da placa de vídeo como alta. É o passo seguinte ao MSI: o MSI tira a GPU da linha compartilhada, este decide quem é atendido primeiro quando duas interrupções chegam juntas.

- **Fonte:** DevicePriority em ...\\Enum\\PCI\\<instância>\\Device Parameters\\Interrupt Management\\Affinity Policy — a mesma chave que a Interrupt Affinity Policy Tool da Microsoft grava. 3 = alta.
- **Custo / trade-off:** Interrupção de vídeo passa na frente de outras do sistema. Em PC que grava ou transmite ao mesmo tempo, a captura pode perder alguns quadros. Exige reiniciar, e volta com um clique.
- **Metrica impactada:** Latência de DPC do driver de vídeo
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Interrupção por mensagem (MSI) na GPU  
`gpu_msi` · risco **Avançado** · perfis: COMPETITIVO · exige reiniciar · **fora do clique unico**

Faz a GPU sinalizar interrupções por mensagem em vez de compartilhar uma linha IRQ. É o ajuste com efeito mais direto sobre latência de DPC, e por isso mesmo e o mais invasivo: fica fora do lote de um clique e exige um clique seu.

- **Fonte:** MSI/MSI-X em PCI Express - especificação PCIe e documentação de driver da Microsoft. Chave MSISupported em ...\Enum\PCI\<instancia>\Device Parameters\Interrupt Management\MessageSignaledInterruptProperties.
- **Custo / trade-off:** Em hardware antigo ou placa-mãe com ACPI problemático, MSI já causou tela preta no boot seguinte. A reversão existe e funciona, mas se o PC não subir com vídeo ela tem de ser feita pelo Modo de Segurança. Por isso: alto risco, clique explicito, e só depois de ter um ponto de restauração.
- **Metrica impactada:** Latência de DPC do driver de vídeo
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Agendamento de GPU por hardware  
`hags` · risco **Moderado** · perfis: COMPETITIVO, CAMPANHA · exige reiniciar · grava 1 valor(es) de registro

Entrega o agendamento da fila de trabalho da GPU ao processador da própria placa, tirando uma camada de gerenciamento da CPU. É também o pré-requisito de recursos de baixa latência dos drivers atuais.

- **Fonte:** Hardware-Accelerated GPU Scheduling - Microsoft Learn. Chave HwSchMode em HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers (1 = desligado, 2 = ligado). É o mesmo interruptor de Configurações > Vídeo > Gráficos > Configurações gráficas padrão.
- **Custo / trade-off:** Exige reiniciar. Em drivers antigos ou GPUs de geração mais velha, já causou instabilidade em captura de tela e gravação - se aparecer, e um clique para voltar.
- **Metrica impactada:** Latência de renderização e 1% low
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Desligar o Multi-Plane Overlay (MPO)  
`mpo_off` · risco **Experimental** · perfis: COMPETITIVO · exige reiniciar · **fora do clique unico** · grava 1 valor(es) de registro

O MPO deixa a GPU compor planos separados em vez de um quadro único. Em parte das combinações de driver e monitor ele causa piscada, travada ao mover janela e cintilação com taxa variável. Desligar é o teste que NVIDIA e Microsoft indicam quando esses sintomas aparecem — e é exatamente por isso que ele fica como teste A/B seu, não como recomendação.

- **Fonte:** OverlayTestMode=5 em HKLM\SOFTWARE\Microsoft\Windows\Dwm — passo de diagnóstico publicado pela NVIDIA e reconhecido pela Microsoft para problemas de cintilação com MPO.
- **Custo / trade-off:** Sem MPO, a composição volta a passar inteira pela GPU: em vídeo e em janela isso custa um pouco mais de trabalho gráfico. Se você não tem o sintoma, não aplique — o AZOR não afirma ganho aqui. Exige reiniciar.
- **Metrica impactada:** Cintilação e travadas ao mover janela (sintoma, não número)
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Dar mais tempo à GPU antes do Windows reiniciar o driver  
`tdr_delay` · risco **Moderado** · perfis: COMPETITIVO, CAMPANHA, JOGO + LIVE · exige reiniciar · **fora do clique unico** · grava 2 valor(es) de registro

O Windows reinicia o driver de vídeo quando a GPU demora mais de 2 segundos para responder. Em compilação de shader e em carga pesada isso dispara sem a placa estar travada de verdade — e o resultado é a tela piscando e o jogo caindo. Subir para 10 segundos elimina o falso positivo.

- **Fonte:** Timeout Detection and Recovery (TDR) — chaves TdrDelay e TdrDdiDelay em HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers, documentadas pela Microsoft para desenvolvimento de driver de vídeo. Padrão: 2 segundos.
- **Custo / trade-off:** Se a GPU travar de verdade, a tela fica congelada por 10 segundos em vez de 2 antes do Windows recuperar. Não esconde defeito: se o driver está reiniciando por instabilidade real, o Stutter Lab continua contando os eventos 4101.
- **Metrica impactada:** Resets de driver de vídeo (evento 4101)
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Otimizações para jogos em janela e taxa variável  
`vrr_windowed` · risco **Seguro** · perfis: COMPETITIVO, CAMPANHA, JOGO + LIVE · grava 1 valor(es) de registro

Liga as duas opções que o Windows 11 oferece em Configurações gráficas: caminho de apresentação otimizado para jogos em janela (tira uma cópia de quadro do meio) e taxa de atualização variável para títulos que não a suportam sozinhos.

- **Fonte:** Configurações > Sistema > Vídeo > Gráficos > Configurações gráficas padrão (DirectXUserGlobalSettings em HKCU\Software\Microsoft\DirectX\UserGpuPreferences).
- **Custo / trade-off:** Só tem efeito em monitor com taxa variável e em jogo rodando em janela ou janela sem borda. Em tela cheia exclusiva não muda nada — e o AZOR diz isso em vez de contar como ganho.
- **Metrica impactada:** Latência de apresentação em janela sem borda
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

## RAM & Memória
Mantém paginação segura quando necessário; XMP/EXPO e timings continuam fora da automação do Windows.

### Devolver a paginação ao Windows  
`automatic_pagefile` · risco **Seguro** · perfis: SEGURO, COMPETITIVO, CAMPANHA, JOGO + LIVE · exige reiniciar

Se a paginação estiver desativada, volta para o gerenciamento automático e verifica o estado.

- **Fonte:** Win32_ComputerSystem.AutomaticManagedPagefile — o mesmo que a caixa 'Gerenciar automaticamente o tamanho do arquivo de paginação' em Opções de Desempenho.
- **Custo / trade-off:** Ocupa espaço em disco. Em troca, o jogo não é encerrado por falta de memória de commit — o desligamento do pagefile é uma das causas mais comuns de travamento atribuído ao jogo.
- **Metrica impactada:** Stutter por paginação (picos de frametime)
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Testar o PC sem a compressão de memória  
`memory_compression_off` · risco **Experimental** · perfis: COMPETITIVO · **fora do clique unico**

O Windows comprime páginas de memória para caber mais na RAM, gastando CPU para isso. Com 32 GB ou mais, sobra memória e o trabalho de compressão vira custo puro — mas o ganho varia por jogo, então este item é um teste A/B seu: aplique, jogue duas partidas e reverta se não sentir diferença.

- **Fonte:** Enable-MMAgent / Disable-MMAgent -mc — módulo MMAgent do PowerShell, documentado pela Microsoft. O estado é lido de volta por Get-MMAgent.
- **Custo / trade-off:** Sem compressão, o mesmo conjunto de programas ocupa mais RAM física. Se a memória encher, o Windows volta a paginar em disco — que é bem pior que comprimir. Por isso o corte de 32 GB, e por isso o AZOR não promete ganho aqui.
- **Metrica impactada:** Uso de CPU em repouso e p99 de frametime
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

## Input & Memória
Timer, aceleração de ponteiro, energia das portas USB e AZOR Memory Engine. Ajustes físicos de polling/deadzone continuam dependentes do periférico.

### AZOR Memory Engine  
`azor_memory_engine` · risco **Seguro** · perfis: COMPETITIVO, CAMPANHA, JOGO + LIVE

Motor interno adaptativo de standby memory; não depende de executável externo.

- **Fonte:** NtSetSystemInformation(SystemMemoryListInformation, MemoryPurgeStandbyList), a mesma chamada que o ISLC usa. Exige SeProfileSingleProcessPrivilege e, portanto, o AZOR como administrador.
- **Custo / trade-off:** Limpar a standby list joga fora cache útil: o que foi descartado volta a ser lido do disco. Por isso o motor só age sob pressão de memória, com intervalo mínimo de 20 s — e o ganho tem de aparecer no p99 do frametime, não no número de MB livres.
- **Metrica impactada:** p99 de frametime durante pressão de memória
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Repetição de tecla no máximo  
`keyboard_repeat_fast` · risco **Seguro** · perfis: COMPETITIVO · grava 2 valor(es) de registro

Coloca o atraso de repetição no mínimo e a velocidade no máximo — os extremos que o próprio painel de controle do Windows oferece.

- **Fonte:** Propriedades do Teclado (Painel de Controle): KeyboardDelay 0-3 e KeyboardSpeed 0-31, em HKCU\Control Panel\Keyboard.
- **Custo / trade-off:** Segurar uma tecla passa a repetir muito rápido, inclusive ao digitar texto. Quem escreve bastante costuma preferir o padrão.
- **Metrica impactada:** nenhuma (preferencia, nao desempenho)
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Timer de alta resolução  
`latency_timer` · risco **Seguro** · perfis: COMPETITIVO, CAMPANHA, JOGO + LIVE

Solicita 0,5 ms pela API nativa e consulta o valor realmente reportado pelo Windows.

- **Fonte:** NtSetTimerResolution / NtQueryTimerResolution (ntdll). Não é API documentada publicamente pela Microsoft: por isso o AZOR nunca afirma o valor pedido, e sim o valor que NtQueryTimerResolution devolve.
- **Custo / trade-off:** O pedido dura só enquanto o AZOR está aberto — é sessão, não alteração permanente. Timer mais fino aumenta o número de interrupções e, em notebook na bateria, consome mais.
- **Metrica impactada:** Jitter de execução (µs) medido no AZOR Scope
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Desligar a aceleração de ponteiro  
`mouse_acceleration_off` · risco **Seguro** · perfis: COMPETITIVO, CAMPANHA, JOGO + LIVE · grava 3 valor(es) de registro

Zera MouseSpeed e os dois limiares de aceleração do Windows, para que a mesma distância física do mouse dê sempre a mesma distância na tela. É a base de qualquer memória muscular de mira.

- **Fonte:** Melhorar a precisão do ponteiro (Enhanced Pointer Precision), em Configurações > Bluetooth e dispositivos > Mouse. Chaves MouseSpeed, MouseThreshold1 e MouseThreshold2 em HKCU\Control Panel\Mouse.
- **Custo / trade-off:** Fora do jogo, o ponteiro passa a exigir mais movimento para atravessar a tela em DPI baixo. Quem usa o PC para desenho ou planilha em monitor grande pode estranhar.
- **Metrica impactada:** Consistência de mira (mesma distância física = mesma distância na tela)
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Interrupção por mensagem (MSI) no controlador USB  
`usb_controller_msi` · risco **Avançado** · perfis: COMPETITIVO · exige reiniciar · **fora do clique unico**

Mesmo mecanismo do MSI da GPU, aplicado ao controlador xHCI da placa-mãe. Toda tecla e todo movimento do mouse chegam por ele: tirar a interrupção da linha compartilhada reduz a latência de DPC do caminho de entrada inteiro.

- **Fonte:** MSI/MSI-X em PCI Express - chave MSISupported em ...\Enum\PCI\<instancia>\Device Parameters\Interrupt Management\MessageSignaledInterruptProperties.
- **Custo / trade-off:** Mesmo risco do MSI na GPU: em placa-mãe com ACPI problemático, o controlador pode não inicializar no boot seguinte - e sem USB não há teclado nem mouse para consertar. A reversão existe, mas precisaria de Modo de Segurança. Alto risco, clique explicito, e só com ponto de restauração criado antes.
- **Metrica impactada:** Latência de DPC do caminho de entrada
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Impedir o Windows de desligar os hubs USB  
`usb_hub_power_off` · risco **Seguro** · perfis: COMPETITIVO, CAMPANHA, JOGO + LIVE

A suspensão seletiva de USB é do plano de energia; está aqui é a permissão que cada hub e controlador USB da placa-mãe carrega individualmente. É a segunda metade do mesmo problema: o periférico que demora um instante para responder depois de alguns segundos parado.

- **Fonte:** EnhancedPowerManagementEnabled em HKLM\SYSTEM\CurrentControlSet\Enum\USB\<instância>\Device Parameters — é a caixa 'O computador pode desligar este dispositivo' da aba Gerenciamento de Energia de cada hub USB.
- **Custo / trade-off:** Os controladores USB deixam de entrar em economia, o que consome alguns watts a mais em repouso. Em notebook na bateria isso é perceptível ao longo do dia.
- **Metrica impactada:** Atraso do primeiro evento após o periférico ficar parado
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Impedir o Windows de suspender as portas USB  
`usb_suspend_off` · risco **Seguro** · perfis: SEGURO, COMPETITIVO, CAMPANHA, JOGO + LIVE

Desliga a suspensão seletiva de USB no plano ativo. É a causa clássica do mouse ou do headset que 'dorme' e demora um instante para responder depois de alguns segundos parado. Em notebook, só o índice de tomada é alterado.

- **Fonte:** Suspensão seletiva de USB (SUB_USB / USBSELECTSUSPEND) no powercfg — https://learn.microsoft.com/windows-hardware/design/device-experiences/powercfg-command-line-options
- **Custo / trade-off:** Portas USB deixam de entrar em economia, o que consome um pouco mais de energia. Em notebook na bateria o AZOR preserva o valor de bateria e altera só o de tomada.
- **Metrica impactada:** Atraso do primeiro movimento após o periférico ficar parado
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

## Rede
Latência do adaptador em uso: ACK sem atraso, sem moderação de interrupção, sem economia de energia. Sem promessa de ping magico.

### Desligar o agrupamento de ACK (Nagle)  
`nagle_off` · risco **Moderado** · perfis: COMPETITIVO, JOGO + LIVE

Grava TcpAckFrequency=1, TCPNoDelay=1 e TcpDelAckTicks=0 na interface que carrega a rota padrão. O Windows deixa de segurar a confirmação esperando juntar pacote, que é atraso puro para o trânsito pequeno e constante de um jogo.

- **Fonte:** Parâmetros TCP/IP por interface (HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\{GUID}) - referência de registro TCP/IP da Microsoft; TcpAckFrequency e o ajuste descrito no KB 328890.
- **Custo / trade-off:** Mais pacotes pequenos na rede: em conexão muito limitada ou compartilhada, a sobrecarga de cabeçalho pode custar um pouco de banda. Não altera roteamento nem distância até o servidor - nenhum ajuste faz isso.
- **Metrica impactada:** Variação de latência em jogo (jitter)
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Desligar a economia de energia do link Ethernet  
`nic_green_ethernet_off` · risco **Seguro** · perfis: COMPETITIVO, JOGO + LIVE

Energy Efficient Ethernet, Green Ethernet, Gigabit Lite e Auto Disable Gigabit rebaixam o link quando ele fica ocioso e levam alguns microssegundos para voltar. Em jogo, esse retorno aparece como pico isolado de latência. O AZOR desliga apenas as que o seu driver realmente expoe.

- **Fonte:** IEEE 802.3az (Energy Efficient Ethernet) e propriedades equivalentes dos fabricantes (*EEE, EnableGreenEthernet, AdvancedEEE, PowerSavingMode, GigaLite, AutoDisableGigabit), lidas e escritas por Get/Set-NetAdapterAdvancedProperty.
- **Custo / trade-off:** Alguns miliwatts a mais no adaptador e no switch. Sem efeito em Wi-Fi.
- **Metrica impactada:** Picos isolados de ping
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Desligar a moderação de interrupção da placa de rede  
`nic_interrupt_moderation_off` · risco **Moderado** · perfis: COMPETITIVO

A placa agrupa interrupções para poupar CPU, e esse agrupamento é atraso. Desligado, cada pacote chega ao sistema assim que chega no fio.

- **Fonte:** Propriedade avancada padronizada *InterruptModeration, definida pela Microsoft para drivers NDIS; lida e escrita por Get/Set-NetAdapterAdvancedProperty.
- **Custo / trade-off:** O uso de CPU do adaptador sobe sob tráfego alto, porque cada pacote gera interrupção. Em máquina de 4 núcleos com download pesado ao mesmo tempo, isso é perceptível.
- **Metrica impactada:** Jitter de rede e DPC do driver de rede
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Impedir o Windows de desligar a placa de rede  
`nic_power_saving_off` · risco **Seguro** · perfis: SEGURO, COMPETITIVO, CAMPANHA, JOGO + LIVE

Tira a permissao de 'o computador pode desligar este dispositivo para economizar energia'. É a causa clássica de queda de conexão de alguns segundos no meio da partida em placa Wi-Fi.

- **Fonte:** Set-NetAdapterPowerManagement -AllowComputerToTurnOffDevice (módulo NetAdapter do PowerShell). Quando o driver não pública essa classe, o AZOR usa PnPCapabilities=24 na chave de classe do adaptador, que é exatamenté o valor que a aba Gerenciamento de Energia do Gerenciador de Dispositivos grava.
- **Custo / trade-off:** Consumo levemente maior em repouso. Em notebook longe da tomada, alguns miliwatts a mais.
- **Metrica impactada:** Quedas de conexão por sessão
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Distribuir as interrupções de rede entre os núcleos  
`nic_rss_on` · risco **Seguro** · perfis: COMPETITIVO, JOGO + LIVE

Sem RSS, todo o processamento de rede cai num único núcleo — justamente o que fica saturado quando o jogo também está usando. Com RSS, o trabalho se espalha e para de competir no mesmo lugar.

- **Fonte:** Receive Side Scaling (RSS) — Enable-NetAdapterRss / Get-NetAdapterRss, módulo NetAdapter do PowerShell. É recurso padrão do NDIS documentado pela Microsoft.
- **Custo / trade-off:** Praticamente nenhum em PC de quatro núcleos ou mais. Em processador de dois núcleos o ganho é pequeno, porque há pouco para onde espalhar.
- **Metrica impactada:** Uso de CPU do núcleo 0 sob tráfego e jitter de rede
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

## Sistema de arquivos
Comportamento do NTFS, lido e gravado pelo fsutil e confirmado por releitura. O reparo de TRIM mudou para o módulo Reparo.

### Parar de gravar a hora do último acesso  
`ntfs_last_access_off` · risco **Seguro** · perfis: COMPETITIVO, CAMPANHA, JOGO + LIVE

Cada leitura de arquivo também escreve um metadado com a hora do acesso. Desligar tira uma escrita de disco de todo carregamento de textura e shader.

- **Fonte:** fsutil behavior set disablelastaccess - referência do fsutil, Microsoft Learn. 0/2 = ligado, 1/3 = desligado; 2 e 3 são as variantes 'gerenciadas pelo sistema'.
- **Custo / trade-off:** Programas de backup incremental e de limpeza que decidem por 'último acesso' perdem esse critério e passam a usar a data de modificação. Nenhum jogo usa.
- **Metrica impactada:** Escritas de disco em repouso e durante carregamento
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Parar de criar nomes curtos 8.3  
`ntfs_short_names_off` · risco **Seguro** · perfis: COMPETITIVO, CAMPANHA, JOGO + LIVE

Para cada arquivo criado, o NTFS também monta um nome no formato antigo PROGRA~1. Em pasta com dezenas de milhares de arquivos — cache de shader, pasta de compilação — esse trabalho extra aparece. Não é um ajuste de FPS: o ganho está em criação de arquivo, não em quadro renderizado.

- **Fonte:** fsutil behavior set disable8dot3 — referência do fsutil, Microsoft Learn. 0 = todos os volumes, 1 = nenhum, 2 = por volume (padrão do Windows), 3 = todos menos o do sistema.
- **Custo / trade-off:** Programas de 16 bits e instaladores muito antigos que dependem de caminho curto podem falhar. Os nomes curtos já existentes continuam funcionando; só os novos deixam de ser criados.
- **Metrica impactada:** Tempo de criação de arquivo em diretório grande
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Testar o PC sem o pré-carregamento (somente SSD)  
`prefetcher_ssd_off` · risco **Experimental** · perfis: COMPETITIVO · exige reiniciar · **fora do clique unico** · grava 1 valor(es) de registro

O Prefetcher lê antes o que o Windows acha que você vai abrir. Em disco mecânico isso vale muito; em SSD, o ganho encolhe e sobra o custo de I/O em segundo plano. Como o resultado varia por máquina, este item é um teste A/B seu — aplique, use o PC dois dias e reverta se não sentir diferença.

- **Fonte:** EnablePrefetcher em HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management\PrefetchParameters — referência de registro do Windows. 3 = padrão (aplicativos e boot), 0 = desligado.
- **Custo / trade-off:** A primeira abertura de programas grandes pode ficar mais lenta. O AZOR não promete ganho aqui: em boa parte dos SSDs modernos a diferença não aparece na medição. Exige reiniciar.
- **Metrica impactada:** I/O de disco em repouso
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Interrupção por mensagem (MSI) na controladora do SSD  
`storage_msi` · risco **Avançado** · perfis: COMPETITIVO · exige reiniciar · **fora do clique unico**

Faz a controladora NVMe/AHCI sinalizar interrupções por mensagem em vez de compartilhar linha IRQ. Reduz latência de DPC do armazenamento, que é o que aparece como engasgo ao carregar textura no meio da partida.

- **Fonte:** MSI/MSI-X em PCI Express — chave MSISupported em ...\Enum\PCI\<instância>\Device Parameters\Interrupt Management\MessageSignaledInterruptProperties.
- **Custo / trade-off:** Mesmo risco do MSI na GPU, com um agravante: se a controladora do disco não inicializar, o PC não sobe. A reversão existe e funciona, mas teria de ser feita pelo Modo de Segurança. Alto risco, clique explícito, e só com ponto de restauração criado antes.
- **Metrica impactada:** Latência de DPC do driver de armazenamento
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

## Serviços
Poucos serviços, escolhidos por medição e não por lista da internet. Cada um declara o que para de funcionar.

### Desligar a telemetria de experiência do usuário  
`diagtrack_off` · risco **Moderado** · perfis: COMPETITIVO, JOGO + LIVE · grava 1 valor(es) de registro

Desabilita o serviço DiagTrack, que coleta e envia dados de diagnóstico em segundo plano. Ele acorda disco e rede em momentos que você não escolhe.

- **Fonte:** Serviço 'Experiências do Usuário Conectado e Telemetria' (DiagTrack), documentado pela Microsoft nos guias de dados de diagnóstico do Windows para empresas.
- **Custo / trade-off:** O Hub de Comentários para de enviar, o programa Windows Insider deixa de funcionar e alguns relatórios de erro não sobem. Não afeta Windows Update nem segurança.
- **Metrica impactada:** Uso de disco e CPU em repouso
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Desligar o spooler de impressão (sem impressora instalada)  
`spooler_off` · risco **Moderado** · perfis: COMPETITIVO · grava 1 valor(es) de registro

Desabilita o spooler apenas em PC sem nenhuma impressora instalada. Alem de um processo a menos em memória, ele já foi alvo de falhas de segurança conhecidas.

- **Fonte:** Serviço Spooler de Impressão (Spooler) - documentação de serviços do Windows.
- **Custo / trade-off:** Enquanto estiver desligado, este PC não imprime e não instala impressora. Se você for imprimir, reverta antes -- é um clique, e o AZOR guarda o valor original.
- **Metrica impactada:** Processos ativos em repouso
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

### Testar o PC sem o SysMain (somente SSD)  
`sysmain_ssd_off` · risco **Experimental** · perfis: COMPETITIVO · **fora do clique unico** · grava 1 valor(es) de registro

Desabilita o SysMain (antigo Superfetch). Ele só aparece quando o PC tem apenas armazenamento sólido -- em HDD ele ajuda de verdade e fica intocado. Mesmo em SSD, o ganho varia por máquina: aplique, jogue duas partidas e reverta se não sentir diferença.

- **Fonte:** Serviço SysMain (Superfetch) - documentação de serviços do Windows. Em disco sólido o pré-carregamento que ele faz tem retorno muito menor.
- **Custo / trade-off:** A primeira abertura de programas grandes pode ficar mais lenta, porque o Windows para de pré-carregar o que você costuma usar. Este item é um teste A/B, não uma promessa: o AZOR não afirma ganho aqui.
- **Metrica impactada:** p99 de frametime e uso de disco em repouso
- **Reversivel individualmente:** sim
- **Verificacao apos aplicar:** sim, rele o valor

## Armazenamento
Limpeza conservadora e mensurável; não toca em Downloads, saves, drivers ou arquivos do jogo.

### Limpeza segura de temporários  
`safe_cleanup` · risco **Seguro** · perfis: SEGURO, COMPETITIVO, CAMPANHA, JOGO + LIVE

Remove apenas TEMP antigo dentro da política segura atual.

- **Fonte:** Pasta %TEMP% do usuário, com corte por idade de arquivo. Não usa cleanmgr nem toca em Downloads, perfis de jogo, shader cache atual ou pontos de restauração.
- **Custo / trade-off:** Não é reversível: arquivo apagado não volta. Em compensação, só entram temporários mais velhos que o corte de horas, e nunca arquivos abertos por um processo.
- **Metrica impactada:** Espaço livre no disco do sistema
- **Reversivel individualmente:** nao
- **Verificacao apos aplicar:** o proprio apply ja rele

## Fortnite
Configurações do jogo ficam em ações dedicadas com backup e releitura; o one-click não força preset gráfico.

*Sem tweak automatico. Este modulo e diagnostico.*

## Hardware & BIOS
Detecção e recomendações; BIOS, XMP/EXPO e overclock nunca são escritos automaticamente.

*Sem tweak automatico. Este modulo e diagnostico.*


## Tweaks rejeitados, e por que

Esta lista existe porque metade do que circula como 'otimizacao de FPS' nao sobrevive a uma medicao. Nada aqui esta no app.

**bcdedit /set useplatformclock true**  
Forca o HPET como fonte de tempo. Em CPUs modernas com TSC invariante isso costuma AUMENTAR a latencia, nao reduzir. Se algum dia entrar, entra como teste A/B medido pelo AZOR Scope, com reversao em um clique - nunca como padrao.

**bcdedit /set disabledynamictick yes**  
Mesmo caso: efeito depende do hardware e do estado de energia, e em notebook piora o consumo em repouso. So faz sentido como experimento com numero antes e depois.

**Limpador de RAM continuo (EmptyWorkingSet em loop)**  
Forcar processos a devolver working set faz o Windows reler do disco o que acabou de descartar. Piora o desempenho e mostra um numero bonito de 'memoria livre'. O AZOR Memory Engine e outra coisa: purga standby list, so sob pressao, com intervalo minimo.

**Desativar dezenas de servicos em lote**  
Cada servico desligado e uma funcionalidade quebrada em algum cenario (busca, impressao, biometria, VPN corporativa). O AZOR so mexe em servico com explicacao individual, deteccao de dependencia e um clique por item.

**Ajustar MTU / trocar DNS como 'otimizacao de internet'**  
MTU errado fragmenta pacote e derruba throughput. DNS muda onde o nome e resolvido, nao a rota ate o servidor do jogo: nao reduz ping. Sem medicao, nao entra.

**netsh int tcp set global autotuninglevel=disabled**  
Circula como tweak de FPS e destroi o throughput em conexoes com latencia. O AZOR faz o contrario: detecta quem ja aplicou isso e oferece voltar para 'normal'.

**Limpeza de registro como metrica de desempenho**  
Chave orfa nao custa tempo de CPU mensuravel. O ganho de 'registro limpo' nao existe, e o risco de apagar a chave errada existe.

**Desativar o Windows Update**  
Fica sem correcao de seguranca e sem driver novo, que e justamente onde estao varios ganhos reais de desempenho. O caminho legitimo e adiar/pausar por politica.

**Desligar as mitigacoes de Spectre/Meltdown (FeatureSettingsOverride)**  
Devolve desempenho real de CPU, principalmente em processador mais antigo - e reabre falhas de execucao especulativa que permitem a um processo ler memoria de outro. Diferente da Integridade de Memoria, aqui nao ha aviso do proprio Windows nem um interruptor oficial: o usuario nao tem como perceber que ficou exposto. Fica de fora.

**Overclock, undervolt ou curva de ventoinha por software**  
Sao ajustes de hardware com risco de instabilidade e de temperatura, e dependem de leitura de sensor que o Windows nao expoe sem driver de kernel. O AZOR mede a temperatura e diz quando ela e o gargalo - quem mexe na curva e voce, na ferramenta do fabricante.

**Prometer FPS, ping ou latencia em numero fixo**  
O resultado depende do jogo, do hardware e da cena. O AZOR mede no PC real e mostra o delta; qualquer texto que prometa numero antes de medir e removido do app.


## O que o AZOR nao faz por decisao

- Nao escreve firmware/BIOS. Um valor errado impede o PC de ligar, e nenhum ganho de FPS justifica isso. O BIOS Copiloto mostra o caminho do menu e confirma depois do reboot lendo o Windows.
- Nao le nem escreve memoria do processo do jogo, e nao toca nos pacotes de rede do jogo.
- Nao cria VBS, tarefa agendada, autocopia nem inicializacao automatica.
