# Tweaks do AZOR

Lista gerada do catálogo real do app (`tools/gen_tweaks_md.py`). Cada ajuste é gravado, relido e só conta como aplicado se o Windows confirmar; o valor de antes fica guardado para desfazer.

Total: **115** ajustes.

| Selo | Significa |
|---|---|
| +FPS | mais quadros por segundo |
| -DELAY | clique/tecla/movimento chegam antes na tela |
| -STUTTER | menos travadinhas e quedas de 1% low |
| PING | conexão mais estável no jogo |
| +LEVE | menos processos e serviços gastando CPU/RAM |

## Mais FPS

Tira do caminho o que segura o desempenho da placa de vídeo e do processador.

| Ajuste | O que dá | BOOST | Reinicia | Desfaz |
|---|---|---|---|---|
| **Jogos na placa de vídeo dedicada**<br>Em notebook e PC com vídeo integrado, força os jogos a usar a placa mais forte. | `+FPS` | Recomendado + Extremo | não | sim |
| **Monitor na taxa máxima (Hz)**<br>Monitor de 144 Hz em 60 Hz só mostra 60 FPS. Coloca na taxa máxima que ele aceita. | `+FPS` `-DELAY` | Recomendado + Extremo | não | sim |
| **Plano de energia AZOR**<br>Deixa o processador subir para o clock máximo na hora que o jogo pede. | `+FPS` `-STUTTER` | Recomendado + Extremo | não | sim |
| **Agendamento de GPU por hardware**<br>A própria placa de vídeo organiza a fila de quadros, aliviando o processador. | `+FPS` `-DELAY` | Recomendado + Extremo | sim | sim |
| **Fortnite na placa de vídeo dedicada**<br>Garante que o Fortnite rode na placa de vídeo mais forte do PC. | `+FPS` | Recomendado + Extremo | não | sim |
| **Modo de Jogo do Windows**<br>Faz o Windows dar prioridade ao jogo e segurar atualizações durante a partida. | `+FPS` `-STUTTER` | Recomendado + Extremo | não | sim |
| **Prioridade alta automática para o jogo**<br>Enquanto o AZOR estiver aberto, o jogo sobe para prioridade Alta sozinho. | `+FPS` `-STUTTER` | — | não | sim |
| **Sem economia forçada de CPU**<br>Impede o Windows de colocar o jogo e o Discord em modo econômico. | `+FPS` | Recomendado + Extremo | não | sim |
| **Sem gravação escondida da Xbox Game Bar**<br>Para a Game Bar de gravar a partida o tempo todo em segundo plano. | `+FPS` | Recomendado + Extremo | não | sim |
| **Windows Update não troca o driver de vídeo**<br>Impede o Windows de instalar por cima um driver de vídeo mais velho que o seu. | `+FPS` `DRIVER` | Só Extremo | não | sim |
| **Bloqueio da gravação para todos os usuários**<br>Garante que a gravação escondida não volte sozinha, nem em outro usuário. | `+FPS` | Recomendado + Extremo | não | sim |
| **Efeitos visuais no modo desempenho**<br>Desliga animações e sombras do Windows. A área de trabalho responde na hora. | `+LEVE` `-DELAY` | Recomendado + Extremo | não | sim |
| **Sem transparência no Windows**<br>Tira o efeito de vidro da barra e do menu. Alivia a placa de vídeo fora do jogo. | `+LEVE` | Recomendado + Extremo | não | sim |

## Menos delay

Clique, tecla e movimento chegam mais rápido na tela (menos input lag).

| Ajuste | O que dá | BOOST | Reinicia | Desfaz |
|---|---|---|---|---|
| **Mouse sem aceleração**<br>A mesma distância do mouse vira sempre a mesma distância na tela. Base da mira. | `MIRA` `-DELAY` | Recomendado + Extremo | não | sim |
| **Jogos em janela otimizados (VRR)**<br>Jogo em janela sem borda passa a ter o mesmo caminho rápido da tela cheia. | `-DELAY` `+FPS` | Recomendado + Extremo | não | sim |
| **Portas USB sem economia de energia**<br>O Windows para de desligar as portas USB da placa-mãe para economizar. | `-DELAY` | Recomendado + Extremo | não | sim |
| **Sem pop-up das Teclas de Aderência**<br>Apertar Shift 5 vezes no jogo não abre mais aquela janela que tira o foco. | `SEM POP-UP` | Recomendado + Extremo | não | sim |
| **Som do jogo não abaixa em call**<br>O Windows para de abaixar em 80% o som do jogo quando você entra no Discord. | `SOM` `CALL` | Recomendado + Extremo | não | sim |
| **Tela cheia exclusiva de verdade**<br>Tira o Windows do meio do caminho entre o quadro pronto e o monitor. Overlays podem sumir. | `-DELAY` `+FPS` | Só Extremo | não | sim |
| **Tela cheia exclusiva só no Fortnite**<br>Mesmo ganho de delay, só dentro do Fortnite. O resto do PC não muda. | `-DELAY` | Recomendado + Extremo | não | sim |
| **Timer do Windows em 0,5 ms**<br>O relógio interno do Windows passa a acordar mais vezes: comandos processados mais rápido. | `-DELAY` | — | não | sim |
| **Timer rápido para o PC inteiro**<br>Faz o timer de 0,5 ms valer para o jogo, não só para o AZOR. Exige reiniciar. | `-DELAY` | Só Extremo | sim | sim |
| **USB sempre acordado**<br>Mouse, teclado e headset não 'dormem' e não demoram para responder depois de parados. | `-DELAY` | Recomendado + Extremo | não | sim |
| **Game Bar não abre ao iniciar o jogo**<br>O painel da Game Bar não rouba mais o foco no primeiro segundo da partida. | `SEM POP-UP` | Recomendado + Extremo | não | sim |
| **Placa de vídeo atendida primeiro**<br>Quando dois aparelhos chamam o processador ao mesmo tempo, a placa de vídeo passa na frente. | `-DELAY` | Só Extremo | sim | sim |

## Sem travadinhas

Frametime estável: menos engasgos, quedas de 1% low e congeladas no meio da partida.

| Ajuste | O que dá | BOOST | Reinicia | Desfaz |
|---|---|---|---|---|
| **Antivírus fora das pastas de jogo**<br>O Defender para de verificar cada arquivo que o jogo carrega. Carregamento e shader mais rápidos. | `-STUTTER` `LOADING` | Só Extremo | não | sim |
| **Mais processador para o jogo**<br>O Windows reserva menos CPU para tarefas de fundo enquanto você joga. | `+FPS` `-STUTTER` | Recomendado + Extremo | não | sim |
| **Motor de memória AZOR**<br>Libera a memória em espera só quando ela está acabando (o que o ISLC faz), sem jogar cache fora à toa. | `-STUTTER` `RAM` | — | não | sim |
| **Windows Update sem reiniciar sozinho**<br>Acabou o 'reiniciando em 15 minutos' no meio da partida. | `ESTÁVEL` | Recomendado + Extremo | não | sim |
| **Desligar de verdade (sem Inicialização Rápida)**<br>Faz o 'reiniciar' e o 'desligar' limparem o Windows de verdade. Ajustes e drivers pegam. | `ESTÁVEL` | Recomendado + Extremo | não | sim |
| **Disco sem anotar cada leitura**<br>Cada arquivo que o jogo lê deixa de gerar uma escrita extra no disco. | `-STUTTER` `DISCO` | Recomendado + Extremo | não | sim |
| **Núcleo do Windows sempre na RAM**<br>Impede o Windows de mandar partes dele para o disco no meio do jogo (só com 16 GB+). | `-STUTTER` | Só Extremo | sim | sim |
| **SSD NVMe sempre pronto**<br>O SSD não entra em economia, então textura carregada no meio do jogo não engasga. | `-STUTTER` `LOADING` | Só Extremo | não | sim |

## Internet e ping

Conexão mais estável no jogo: menos picos de ping e menos quedas.

| Ajuste | O que dá | BOOST | Reinicia | Desfaz |
|---|---|---|---|---|
| **Cabo de rede sem modo econômico**<br>Desliga o 'Ethernet verde', que causa picos isolados de ping. | `PING` | Recomendado + Extremo | não | sim |
| **Placa de rede sem economia de energia**<br>O Windows não desliga mais a placa de rede para economizar: acabam as quedas de alguns segundos. | `PING` `SEM QUEDA` | Recomendado + Extremo | não | sim |
| **Placa de rede sem espera**<br>Cada pacote chega ao sistema na hora, em vez de esperar um grupo. Usa um pouco mais de CPU. | `PING` `-DELAY` | Só Extremo | não | sim |
| **Sem limite de pacotes de rede**<br>Tira um freio que o Windows põe na rede enquanto toca som ou vídeo. | `PING` `-STUTTER` | Recomendado + Extremo | não | sim |
| **Windows sem usar sua internet para outros PCs**<br>O Windows para de enviar atualizações para computadores de estranhos pela sua conexão. | `PING` `UPLOAD` | Recomendado + Extremo | não | sim |
| **Preferir IPv4**<br>Resolve internet instável quando o IPv6 do provedor está mal configurado. | `INTERNET` | — | sim | sim |
| **Rede dividida entre os núcleos**<br>O trabalho da placa de rede se espalha pelos núcleos e para de disputar com o jogo. | `PING` `+FPS` | Recomendado + Extremo | não | sim |
| **Rede sem agrupar pacotes (Nagle)**<br>A placa de rede para de segurar pacotes pequenos esperando juntar. Ajuda jogos que usam TCP. | `PING` `-DELAY` | Só Extremo | não | sim |

## Windows leve

Menos processos, serviços e tarefas rodando escondidos gastando CPU, RAM e disco.

| Ajuste | O que dá | BOOST | Reinicia | Desfaz |
|---|---|---|---|---|
| **Desligar tarefas de telemetria**<br>Acaba com o 'disco em 100% do nada' do CompatTelRunner e das tarefas de relatório. | `+LEVE` `-STUTTER` | Recomendado + Extremo | não | sim |
| **Apps da loja sem rodar escondidos**<br>Apps como Fotos, Clima e Mensagens param de funcionar em segundo plano. | `+LEVE` `RAM` | Recomendado + Extremo | não | sim |
| **Bloquear apps que o Windows instala sozinho**<br>Candy Crush, TikTok e outros apps de propaganda param de aparecer sozinhos. | `+LEVE` `SEM LIXO` | Recomendado + Extremo | não | sim |
| **Desligar Copilot e Recall**<br>O Recall para de tirar print da tela o tempo todo e o Copilot sai da memória. | `+LEVE` `RAM` | Recomendado + Extremo | não | sim |
| **Desligar o serviço de telemetria**<br>O serviço que coleta e envia dados de uso para a Microsoft para de rodar. | `+LEVE` | Recomendado + Extremo | não | sim |
| **Edge sem rodar escondido**<br>O Edge para de abrir sozinho no boot e de ficar na memória depois de fechado. | `+LEVE` `RAM` | Recomendado + Extremo | não | sim |
| **Menu Iniciar sem Bing**<br>Pesquisar no menu Iniciar fica só no PC: mais rápido e sem internet. | `+LEVE` | Recomendado + Extremo | não | sim |
| **Tirar do boot diagnóstico, telefonia e NFC**<br>Mais serviços que um PC de jogo não usa saem da memória. | `+LEVE` `RAM` | Só Extremo | não | sim |
| **Tirar serviços inúteis do boot**<br>Mapas, atualizadores do Edge/Google/Adobe, arquivos offline e outros saem do boot. | `+LEVE` `RAM` | Recomendado + Extremo | não | sim |
| **Assistência Remota desligada**<br>Uma porta a menos aberta. AnyDesk e TeamViewer continuam funcionando. | `+LEVE` `SEGURANÇA` | Recomendado + Extremo | não | sim |
| **Desligar a hibernação**<br>Libera vários GB no disco (arquivo hiberfil.sys). Só em desktop. | `+ESPAÇO` | Recomendado + Extremo | não | sim |
| **Desligar indexador de pesquisa**<br>O indexador para de ler o disco inteiro de tempos em tempos. A busca fica mais lenta. | `+LEVE` `DISCO` | Só Extremo | não | sim |
| **Desligar o serviço de impressão**<br>Só aparece se o PC não tem nenhuma impressora. Um processo a menos. | `+LEVE` | Só Extremo | não | sim |
| **Esconder Widgets**<br>Tira o painel de notícias e clima da barra, que ficava carregando conteúdo. | `+LEVE` | Recomendado + Extremo | não | sim |
| **Explorador sem propaganda**<br>Some a propaganda do OneDrive e do Microsoft 365 no Explorador e no Iniciar. | `SEM LIXO` | Recomendado + Extremo | não | sim |
| **Pesquisa sem destaques da internet**<br>A caixa de pesquisa para de buscar desenhos e notícias na internet. | `+LEVE` | Recomendado + Extremo | não | sim |
| **Programas do boot sem espera**<br>O Windows para de esperar 10 segundos antes de abrir os programas de inicialização. | `BOOT` | Recomendado + Extremo | não | sim |
| **Sem 'Termine de configurar seu PC'**<br>Some a tela cheia que aparece depois das atualizações empurrando OneDrive e Microsoft 365. | `+LEVE` `POP-UP` | Recomendado + Extremo | não | sim |
| **Sem Spotlight na tela de bloqueio**<br>O Windows para de baixar imagens e propaganda para a tela de bloqueio. | `+LEVE` `SEM LIXO` | Recomendado + Extremo | não | sim |
| **Sem apps de fabricante automáticos**<br>Conectar um aparelho novo não baixa mais programas de propaganda. | `SEM LIXO` | Recomendado + Extremo | não | sim |
| **Sem nomes curtos antigos (8.3)**<br>O disco para de criar um segundo nome estilo DOS para cada arquivo novo. | `DISCO` | Só Extremo | não | sim |
| **Sem procurar aparelhos por perto**<br>O Windows para de varrer Bluetooth e Wi-Fi atrás de celular para 'continuar no PC'. | `+LEVE` | Recomendado + Extremo | não | sim |
| **Sem relatório de erros do Windows**<br>Depois de um crash o Windows não fica juntando e enviando relatório em segundo plano. | `+LEVE` `DISCO` | Recomendado + Extremo | não | sim |
| **Sem sugestões e propagandas do Windows**<br>Tira anúncios e 'dicas' do menu Iniciar e das Configurações. | `SEM LIXO` | Recomendado + Extremo | não | sim |

## Privacidade

Menos dados enviados para a Microsoft e menos propaganda.

| Ajuste | O que dá | BOOST | Reinicia | Desfaz |
|---|---|---|---|---|
| **Desligar localização**<br>Nenhum app sabe onde o PC está. | `PRIVACIDADE` | — | não | sim |
| **Sem ID de anúncios e rastreio**<br>Desliga o ID de propaganda, o envio de digitação e voz e os pedidos de avaliação. | `PRIVACIDADE` | Recomendado + Extremo | não | sim |
| **Sem histórico de atividades**<br>O Windows para de anotar cada programa e arquivo que você abre. | `PRIVACIDADE` `+LEVE` | Recomendado + Extremo | não | sim |
| **Telemetria no mínimo**<br>Diz ao Windows para coletar o mínimo de dados de diagnóstico. | `PRIVACIDADE` | Recomendado + Extremo | não | sim |

## Visual e conforto

Preferências de aparência e de uso do Windows. Não mudam o FPS.

| Ajuste | O que dá | BOOST | Reinicia | Desfaz |
|---|---|---|---|---|
| **Barra de tarefas à esquerda**<br>Botão Iniciar no canto, como no Windows 10. | `VISUAL` | — | não | sim |
| **Barra sem Visão de Tarefas**<br>Tira o botão de áreas de trabalho. | `VISUAL` | — | não | sim |
| **Barra sem caixa de pesquisa**<br>Mais espaço na barra de tarefas. | `VISUAL` | — | não | sim |
| **Explorador direto em Este Computador**<br>Sem Início e Galeria na lateral. | `VISUAL` | — | não | sim |
| **Explorador mais rápido**<br>Pastas grandes abrem sem esperar. | `+LEVE` | — | sim | sim |
| **Fechar jogo travado pela barra de tarefas**<br>Botão direito no jogo travado > Finalizar tarefa. Sem abrir o Gerenciador. | `CONFORTO` | Recomendado + Extremo | não | sim |
| **Login sem desfoque**<br>Papel de parede nítido na senha. | `VISUAL` | — | não | sim |
| **Menu Iniciar limpo**<br>Sem recomendações e arquivos recentes. | `VISUAL` | — | não | sim |
| **Menu do botão direito completo**<br>Sem 'Mostrar mais opções'. | `VISUAL` | — | não | sim |
| **Menus do Windows instantâneos**<br>Menus abrem na hora em vez de esperar 400 ms. | `-DELAY` | Recomendado + Extremo | não | sim |
| **Mostrar arquivos ocultos**<br>Aparecem pastas como AppData. | `VISUAL` | — | não | sim |
| **Mostrar extensões**<br>Mostra .exe, .zip, .png no nome dos arquivos. | `SEGURANÇA+` | — | não | sim |
| **Num Lock ligado**<br>O teclado numérico já começa ligado. | `TECLADO` | — | não | sim |
| **Pular tela de bloqueio**<br>Vai direto para a senha. | `BOOT` | — | não | sim |
| **Repetição de tecla no máximo**<br>Segurar uma tecla repete mais rápido. Não muda o delay dentro do jogo. | `TECLADO` | — | não | sim |
| **Sem encaixe de janelas**<br>Janelas não grudam nas bordas. | `VISUAL` | — | não | sim |
| **Sem limpeza automática do Windows**<br>O Windows não apaga arquivos sozinho. | `ARQUIVOS` | — | não | sim |
| **Sem notificações**<br>Nenhum aviso aparece na tela. | `SEM POP-UP` | — | não | sim |
| **Tela azul detalhada**<br>Mostra o código do erro se o PC der tela azul. | `DIAGNÓSTICO` | — | não | sim |
| **Tema escuro**<br>Windows e apps no modo escuro. | `VISUAL` | — | não | sim |

## Consertos

Desfaz estragos de outros otimizadores. Num PC saudável não há nada a fazer aqui.

| Ajuste | O que dá | BOOST | Reinicia | Desfaz |
|---|---|---|---|---|
| **Consertar a velocidade de download**<br>Um 'tweak de ping' famoso trava o download. Volta ao normal. | `REPARO` `DOWNLOAD` | — | não | não |
| **Memória virtual automática**<br>Religa o arquivo de paginação se alguém desligou. Sem ele, jogos fecham do nada. | `-STUTTER` `REPARO` | Recomendado + Extremo | sim | sim |
| **Programas abrindo rápido de novo**<br>Religa o SysMain e o Prefetcher, que outro otimizador desligou. | `REPARO` | — | não | não |
| **Religar o Firewall**<br>Firewall desligado não dá FPS e deixa o PC exposto. Religa. | `REPARO` | — | não | não |
| **Religar o TRIM do SSD**<br>O SSD perde velocidade com o tempo sem TRIM. Religa se estiver desligado. | `REPARO` `SSD` | — | não | não |
| **Religar o cache de escrita do disco**<br>Sem ele o PC inteiro fica lento. Religa se estiver desligado. | `REPARO` `DISCO` | — | sim | não |
| **Religar pontos de restauração**<br>Volta a rede de segurança do Windows se alguém desligou. | `REPARO` | — | não | não |
| **Religar serviços essenciais**<br>Som, rede, Windows Update e outros que outro otimizador desligou. | `REPARO` | — | não | não |
| **Tirar HPET forçado do boot**<br>HPET forçado por outro otimizador AUMENTA o delay em CPU moderna. Remove. | `REPARO` `-DELAY` | — | sim | não |
| **Desligamento rápido de novo**<br>Para o Windows de apagar a memória virtual inteira a cada desligamento. | `REPARO` | — | não | não |

## Avançado

Itens com custo real ou resultado que varia por PC. Aplique, teste e desfaça se não gostar.

| Ajuste | O que dá | BOOST | Reinicia | Desfaz |
|---|---|---|---|---|
| **Desligar a Integridade de Memória (VBS)**<br>Tira uma camada de virtualização que pesa no processador. Alguns anti-cheats exigem ela ligada. | `+FPS` `SEGURANÇA-` | — | sim | sim |
| **Agrupar serviços em menos processos**<br>Menos linhas no Gerenciador de Tarefas. Não dá FPS e reduz a estabilidade. | `TESTE` `RAM` | Teste manual | sim | sim |
| **CPU sem repouso**<br>Todos os núcleos ficam acordados. Medido: derruba o turbo do núcleo que roda o jogo. | `TESTE` `CALOR` | Teste manual | não | sim |
| **Desligar a criptografia do disco**<br>O SSD para de criptografar cada leitura e escrita. Arquivos ficam desprotegidos se o PC for roubado. | `DISCO` `SEGURANÇA-` | — | não | não |
| **Desligar o MPO**<br>Só para quem tem tela piscando ou cintilando. Em alguns jogos trava a imagem. | `TESTE` | Teste manual | sim | sim |
| **Liberar espaço reservado do Windows**<br>Devolve de 7 a 10 GB que o Windows guarda para atualizações. | `+ESPAÇO` | — | não | sim |
| **MSI na controladora do SSD**<br>Pode impedir o PC de ligar no próximo boot. | `RISCO` | — | sim | sim |
| **MSI na placa de vídeo**<br>Drivers atuais já fazem isso sozinhos. Em PC antigo pode deixar sem imagem. | `RISCO` | — | sim | sim |
| **MSI no controlador USB**<br>Pode deixar o PC sem mouse e teclado no próximo boot. | `RISCO` | — | sim | sim |
| **Mais tempo antes de reiniciar o driver de vídeo**<br>Para quem vê 'o driver de vídeo parou de responder' em overclock. Não dá FPS. | `ESTÁVEL` | Teste manual | sim | sim |
| **Perfil MMCSS de jogos em prioridade alta**<br>Muito divulgado, pouco efeito: a maioria dos campos nem é usada pelo Windows. | `TESTE` | Teste manual | não | sim |
| **Quantum do agendador (Win32PrioritySeparation)**<br>Muda como o Windows divide o tempo de CPU. Em alguns PCs piora o jogo: teste. | `TESTE` | Teste manual | não | sim |
| **Sem compressão de memória (32 GB+)**<br>Com muita RAM, a compressão vira trabalho extra para o processador. | `-STUTTER` | Só Extremo | não | sim |
| **Testar sem o Prefetcher (só SSD)**<br>Desliga a leitura antecipada de programas. Programas podem abrir mais devagar. | `TESTE` | Teste manual | sim | sim |
| **Testar sem o SysMain (só SSD)**<br>Desliga o pré-carregamento de programas. Programas podem abrir mais devagar. | `TESTE` | Teste manual | não | sim |
| **USB do controle nos núcleos E**<br>Para controle ou mouse de 4K/8K Hz em CPU Intel 12ª geração+: tira as interrupções do núcleo do jogo. | `-DELAY` `CONTROLE` | — | sim | sim |
