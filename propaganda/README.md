# Propaganda do AZOR Optimization

Vídeos para TikTok, Reels e Shorts (9:16, 1080×1920) e YouTube (16:9, 1920×1080). Foram feitos com a interface **real** do AZOR 3.2, renderizada em alta resolução.

## Vídeos (`videos/`)

| Arquivo | Estilo | Duração |
|---|---|---|
| `AZOR_v2_motion_design.mp4` | Motion design minimalista no estilo do vídeo de referência: barra de vidro digitando, menu, seletor deslizando até o BOOST, app real, palavras com brilho, logo letra por letra. 60 fps. | 23 s |
| `AZOR_v2_15s.mp4` | Corte curto da v2 para anúncio pago: gancho, BOOST no app, palavras, chamada e logo. 60 fps. | 15,7 s |
| `AZOR_v2_horizontal_16x9.mp4` | A v2 em 1920×1080 para YouTube e site, com o conteúdo 1,3× maior. 60 fps. | 23 s |
| `AZOR_v3_notebook_filmado.mp4` | A mesma animação "filmada" na tela de um notebook num quarto escuro com neon roxo, com câmera na mão e legenda branca no topo, igual à referência. 30 fps. | 23 s |
| `AZOR_v1_estilo_agressivo.mp4` | Alternativa de anúncio direto: gancho "SEU PC TÁ TRAVANDO?", problemas reais do Windows, BOOST, nota 41 → 97 e "LINK NA BIO". 60 fps. | 32 s |

A trilha e todos os efeitos sonoros (digitação, cliques, whooshes) foram sintetizados do zero. Não há música de terceiros, então não tem problema de direitos autorais.

> Os números da tela de resultado (71 ajustes, 23 apps, 6,7 GB, nota 41 → 97) são **ilustrativos**, de um PC de teste simulado (i5-13400F + GTX 1660 SUPER). Para usar números de um cliente real, troque os valores em `fonte/capture.js` (constantes `RESULT` e `plan`) e gere de novo.

## Como mudar textos e gerar de novo

Requisitos: Node 18+, Playwright com Chromium, ffmpeg e Python 3 com `numpy` e `scipy`.

```bash
cd propaganda/fonte
npm install                      # fontes (Anton, Montserrat, Orbitron, Inter)
# Só se for recapturar as telas do app: extraia o AZOR_Optimization_3.2.zip e copie app/web para fonte/web
node capture.js "<pasta do AZOR>/TWEAKS.md"   # gera shots/*.png com a interface do app (backend simulado)

# v2 — motion design 9:16
node render2.js comp2.html 1080 1920 60 v2_video.mp4        # também grava v2_video.sfx.json (tempos dos efeitos)
python3 music2.py v2_video.sfx.json music2.wav 23.2
ffmpeg -i v2_video.mp4 -i music2.wav -c:v copy -c:a aac -b:a 256k -af loudnorm=I=-13:TP=-1 -shortest AZOR_v2.mp4

# v2 em 16:9 (YouTube): mesma trilha, conteúdo 1,3× maior
Z=1.3 node render2.js comp2.html 1920 1080 60 v2h_video.mp4

# v2 de 15 s: CUT lista os trechos (início_fim, em segundos) da linha do tempo completa
CUT=0.45_2.95,5.62_14.2,17.75_19.3,20.15_23.2 node render2.js comp2.html 1080 1920 60 v2c_video.mp4
python3 music2.py v2c_video.sfx.json music2c.wav 15.68   # a trilha é refeita no tamanho do corte

# v3 — notebook filmado (usa a mesma animação em 1920×1200)
node render2.js comp2.html 1920 1200 30 lap_frames
sh lap_meta.sh                   # mede o brilho de cada quadro (luz da tela no teclado)
node render2.js laptop.html 1080 1920 30 v3_video.mp4

# v1 — estilo agressivo
node render.js 60 v1_video.mp4 && python3 music.py music.wav
```

Onde mudar o quê:

- **Textos digitados, palavras e linha do tempo:** em `comp2.html`, as constantes `TXT1`, `TXT2`, `WORDS` e `T`.
- **Chamada final (CTA):** em `comp2.html`, `#ctat` ("OTIMIZE COM AZOR"), `#ctas` (TikTok @azorwrld e Instagram @azortweaks) e `#ctab` ("LINK NA BIO"). Os @ também aparecem na tela do logo (`#lgh`).
- **@ na v1:** em `comp.html`, `#s9`.
- **Legenda branca do vídeo no notebook:** em `laptop.html`, `#cap`.
- **Textos da v1:** direto no HTML de `comp.html`.
