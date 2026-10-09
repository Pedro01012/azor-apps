# Campanha AZOR — "Potência que já era sua."

São 4 filmes de propaganda em 3D, no mesmo universo visual, como uma campanha de agência. Cada um vem pronto para TikTok, Reels e Shorts: 9:16, 1080×1920, 30 fps, H.264 com áudio AAC a −14 LUFS.

| # | Arquivo | Ideia | Duração |
|---|---|---|---|
| 1 | `videos/f1_potencia.mp4` | **Hero.** Começa com uma ventoinha quase apagada: "Seu PC tem mais potência do que ele entrega." A interface real do AZOR aparece flutuando, a câmera vai até o BOOST e clica. O PC desperta numa onda de luz que sobe pelas ventoinhas, e a câmera orbita. Fecha com "Potência que já era sua." | 22 s |
| 2 | `videos/f2_limpeza.mp4` | **Limpeza**, a evolução do vídeo de limpeza que você gostou. Milhares de fragmentos de "lixo" flutuam dentro do gabinete. Um plano de luz varre tudo da frente para trás e cada fragmento atingido acende e é expulso em espiral pela ventoinha traseira. Fecha com "6,7 GB devolvidos ao seu PC." | 18 s |
| 3 | `videos/f3_antes_de_comprar.mp4` | **Antes de comprar.** Abre com uma placa de vídeo em foto de produto: "Antes de gastar milhares numa placa nova, veja o que está segurando a sua." Mostra o Diagnóstico real do AZOR, com 3 problemas destacados (monitor em 60 Hz, XMP desligado, canal único) que não exigem peça nova. Fecha com "Descubra antes de gastar." | 19,6 s |
| 4 | `videos/f4_144hz.mp4` | **144 Hz.** Um monitor em estúdio faz um teste de movimento que engasga em 60 Hz. O AZOR ajusta a taxa, o indicador vai para 144 Hz e o movimento fica liso. Fecha com "Use cada hertz que você pagou." | 14,6 s |

## O que mudou em relação à série anterior

- **Imagem 3D de verdade** em vez de gráficos chapados. O PC foi modelado peça por peça:
  - gabinete com vidro panorâmico e borda serigrafada;
  - ventoinhas com pás e anéis de LED;
  - placa de vídeo com 3 ventoinhas e backplate;
  - memórias RGB;
  - water cooler com o logo do AZOR;
  - "AZOR" retroiluminado na tampa da fonte.
- **Luz de estúdio**, com reflexo no chão, faixas de luz nos vidros e poeira em suspensão.
- **Pós-produção de cinema:** bloom nos LEDs, grão de filme, vinheta e aberração cromática sutil.
- **Tipografia de marca premium:** Geist (sem serifa), com Instrument Serif itálico para a palavra de destaque, e Geist Mono para os rótulos. Poucas palavras por cena, textos revelados por máscara e muito respiro. Sem emoji, sem tremida, sem flash, sem legenda de CapCut.
- **Sem música.** Só desenho de som de cinema:
  - ambiente de sala, grave contínuo e sub-impactos no clique;
  - ventoinhas acelerando e "swish" sutil nos textos;
  - estalinhos e sucção na limpeza;
  - assinatura sonora curta (um acorde de sino) no logo.

  Tudo passa por uma reverberação de sala, e a mixagem deixa espaço para você colocar uma música em alta do TikTok por cima, se quiser.
- **A interface é a do AZOR de verdade**, renderizada a partir do próprio app, e não uma imitação.

## Honestidade (importante para anúncio)

- O PC 3D é uma ilustração do "seu PC". Não é um produto à venda.
- Os números (6,7 GB, nota 41, 60 Hz, 4800 MT/s) vêm de um PC de teste simulado e aparecem com aviso na tela ("valor ilustrativo", "Tela real do AZOR · PC de teste", "simulação").
- O XMP e o canal único aparecem como "o AZOR mostra", porque são ajustes de BIOS e de encaixe dos pentes que o próprio usuário faz. Os textos não prometem que o AZOR muda isso sozinho.

## Como postar

1. Poste o **f1** primeiro e fixe-o no perfil: é o filme de marca.
2. Depois alterne **f2**, **f3** e **f4** como posts de produto.
3. Para anúncio pago, teste o **f2** (o mais criativo) e o **f3** (o argumento de economia) contra o **f1**.
4. Música: os filmes funcionam sem ela. Se quiser seguir uma tendência, adicione um som do TikTok com volume de 15–25%.

## Como gerar de novo

```bash
cd propaganda/campanha/fonte
npm install                                  # three.js + fontes (Geist, Instrument Serif, Geist Mono)
# dependências: Node 18+, Playwright com Chromium, ffmpeg, Python 3 com numpy e scipy
./rfilm.sh f1_hero.html f1_hero 2            # renderiza em 2 processos (WebGL por software, ~3–8 s por quadro)
./finish.sh f1_hero                          # gera o som a partir dos eventos e junta com o vídeo
./stills.sh f1_hero.html 2,6,11 previa.jpg   # prévias rápidas de alguns instantes
```

Onde mexer:

| Arquivo | O que tem |
|---|---|
| `engine.js` | Renderizador, estúdio de luz, pós-produção, tipografia e assinatura final (`lockup`). Os @ estão aqui. |
| `assets.js` | Modelos 3D: PC, ventoinhas, placa de vídeo, monitor e painel de interface. |
| `pcscene.js` | Cena compartilhada do PC e controles de "potência" e de ventoinhas. |
| `f1_hero.html` … `f4_144hz.html` | Um arquivo por filme, com planos de câmera, textos (`headline(...)`) e eventos de som (`sfx(...)`). |
| `sound.py` | Desenho de som. |
