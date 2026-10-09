# AZOR — campanha em animação 2D

Três filmes 9:16 (1080×1920, 30 fps) feitos em ilustração vetorial animada, no lugar da versão 3D.

| Arquivo | Ideia | Duração |
|---|---|---|
| `videos/a1_potencia.mp4` | O PC começa "apagado". O cartão com a interface real do AZOR vem para a frente e o cursor clica no BOOST. O PC acende com ondas de energia saindo da bomba, neon correndo pelas trilhas da placa-mãe, ventoinhas acelerando e brilhos. | 20,4 s |
| `videos/a2_limpeza.mp4` | Fragmentos de "lixo" enchem o gabinete. Um feixe de luz varre o vidro e cada fragmento acende e é puxado em espiral pela ventoinha traseira. Depois aparece "6,7 GB devolvidos ao seu PC" (valor ilustrativo). | 18 s |
| `videos/a3_antes_de_comprar.mp4` | Uma placa de vídeo ilustrada gira em 2.5D. Em seguida, o Diagnóstico real do AZOR destaca XMP, canal único e apps inúteis: "3 problemas. Nenhuma peça nova." | 19 s |

## O que mudou

- **Ilustração em vez de 3D.** O PC foi desenhado em vetor com bastante detalhe:
  - placa-mãe com trilhas, capacitores, indutores, áudio e portas SATA;
  - VRM com aletas e tampa de I/O com faixa de LED;
  - water cooler com o logo do AZOR e mangueiras;
  - radiador com ventoinhas;
  - 4 memórias RGB com a cor correndo;
  - placa de vídeo com o logo e LED;
  - cabos trançados e passa-cabos;
  - tampa da fonte com "AZOR" e furação;
  - frente em perspectiva com 3 ventoinhas e vidro com reflexo.
- **Efeitos:**
  - energia em neon correndo pelas trilhas;
  - ondas de energia e brilhos no BOOST;
  - luz varrendo o vidro;
  - borrão de movimento nas ventoinhas;
  - profundidade de campo quando a interface vem para a frente;
  - bokeh com parallax e partículas de energia;
  - grão de filme e vinheta.
- **Som leve e limpo.** Tirei o grave, o zumbido e o impacto. Agora o som é:
  - um pad ambiente suave e claro;
  - "ar" nos textos e whooshes suaves;
  - toque de vidro e clique;
  - um acorde brilhante quando o PC acende;
  - brilhos na limpeza;
  - um sino na assinatura.

  A mixagem corta tudo abaixo de 110 Hz.
- **O filme do monitor 144 Hz saiu**, e o item do monitor também saiu do Diagnóstico mostrado.

## Como gerar de novo

```bash
cd propaganda/animacao/fonte        # usa as fontes já instaladas em ../../campanha/fonte/node_modules
./rfilm.sh a_f1.html a_f1 2 && ./finish.sh a_f1
./stills.sh a_f1.html 2,9,12 previa.jpg
```

Arquivos:

- `pc2d.js`: a ilustração (PC e placa de vídeo).
- `kit.js`: fundo, tipografia, efeitos e assinatura com os @.
- `a_f1.html` a `a_f3.html`: os filmes.
- `sound2.py`: o som.
