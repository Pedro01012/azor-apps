# Claude Code turbinado (AZOR)

Instala de uma vez os plugins, MCPs e skills dos vídeos + os mais usados para programar.

## Como usar (Windows)

1. Dê dois cliques em **`INSTALAR-CLAUDE.cmd`**.
2. O script instala Git, Node.js e Claude Code se faltar, e depois todos os plugins/skills.
3. No final ele **abre as telas de login** pra você:
   - **21st.dev**: crie a conta, copie a API key e cole no terminal.
   - **GitHub**: gere o token (a página já abre preenchida) e cole no terminal.
   - **Claude + Figma**: o Claude Code abre; faça login, digite `/mcp`, escolha `figma`, clique em *Authenticate* e depois em *Allow access* no navegador.
4. Feche e abra o terminal de novo para as chaves valerem.

## O que é instalado

### Dos vídeos (design)
| Item | Tipo | Para quê |
|---|---|---|
| frontend-design | plugin/skill (Anthropic) | tira o visual "genérico de IA", usa fontes e layouts bons |
| Web Design Guidelines | skill (Vercel) | revisa UI/acessibilidade (`file:line`) |
| Emil Kowalski (`emil-design-eng`, animações) | skills | polimento e animações de UI |
| Impeccable | plugin | `/impeccable polish`, `audit`, `critique`… |
| Taste Skill (`design-taste-frontend`, redesign, high-end) | skills | design anti-"slop" |
| shadcn/ui MCP | MCP | biblioteca gigante de componentes |
| 21st.dev Magic | plugin + MCP | componentes e estilos de site prontos (**API key**) |
| Figma | plugin + MCP | ler/gerar designs do Figma (**login**) |
| Playwright | plugin + MCP | Claude abre o navegador e testa o site |
| Chrome DevTools | plugin + MCP | Claude "enxerga" console, rede, performance |

### Os mais usados para programar
`context7` (docs atualizadas), `superpowers` (planejamento, TDD, debug), `github` (**token**),
`feature-dev`, `code-review`, `pr-review-toolkit`, `commit-commands`, `security-guidance`,
`code-simplifier`, `claude-md-management`, `skill-creator`, `typescript-lsp`, `pyright-lsp`.

## Neste repositório

- `.claude/settings.json` declara os marketplaces e plugins: ao abrir o Claude Code nesta pasta ele oferece instalar tudo.
- `.claude/skills/` já traz as skills de design (funcionam também no Claude Code na nuvem).
- `.mcp.json` registra o MCP do shadcn/ui.

## Conferir

```
claude plugin list
claude mcp list
```
Dentro do Claude: `/plugin`, `/mcp`, `/skills`.
