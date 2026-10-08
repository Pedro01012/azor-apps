# AZOR - Instalador do Claude Code turbinado (plugins, MCPs e skills)
# Rode com dois cliques em "INSTALAR-CLAUDE.cmd" (mesma pasta).
# Tudo e instalado no escopo do USUARIO, entao vale para qualquer projeto.

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Titulo($t) { Write-Host ""; Write-Host "=== $t ===" -ForegroundColor Cyan }
function Ok($t)     { Write-Host "  [OK] $t" -ForegroundColor Green }
function Aviso($t)  { Write-Host "  [!]  $t" -ForegroundColor Yellow }
function Tem($cmd)  { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function AtualizaPath {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [Environment]::GetEnvironmentVariable('Path', 'User') + ';' +
                "$env:USERPROFILE\.local\bin"
}

# ---------------------------------------------------------------- 1. Pre-requisitos
Titulo "1/6  Pre-requisitos (Git, Node.js, Claude Code)"
AtualizaPath
if (-not (Tem git)) {
    Aviso "Git nao encontrado - instalando via winget..."
    winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
    AtualizaPath
}
if (Tem git) { Ok "Git" } else { Aviso "Instale o Git manualmente: https://git-scm.com/download/win" }

if (-not (Tem node)) {
    Aviso "Node.js nao encontrado - instalando via winget..."
    winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
    AtualizaPath
}
if (Tem node) { Ok "Node.js $(node --version)" } else { Aviso "Instale o Node.js LTS manualmente: https://nodejs.org" }

if (-not (Tem claude)) {
    Aviso "Claude Code nao encontrado - instalando..."
    Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression
    AtualizaPath
}
if (-not (Tem claude)) {
    Aviso "Nao consegui instalar o Claude Code. Veja: https://code.claude.com/docs/en/setup"
    Read-Host "Enter para sair"; exit 1
}
Ok "Claude Code $(claude --version)"

# ---------------------------------------------------------------- 2. Marketplaces
Titulo "2/6  Marketplaces de plugins"
$marketplaces = @('anthropics/claude-plugins-official', 'pbakaus/impeccable', '21st-dev/magic-mcp')
foreach ($m in $marketplaces) {
    claude plugin marketplace add $m 2>&1 | Out-Null
    Ok $m
}
claude plugin marketplace update 2>&1 | Out-Null

# ---------------------------------------------------------------- 3. Plugins
Titulo "3/6  Plugins (cada um ja traz seus MCPs/skills/comandos)"
$plugins = @(
    # --- Design / frontend (dos videos)
    'frontend-design@claude-plugins-official',     # skill oficial de design da Anthropic
    'figma@claude-plugins-official',               # Figma MCP (precisa login)
    'playwright@claude-plugins-official',          # Playwright MCP - Claude navega e testa sites
    'chrome-devtools-mcp@claude-plugins-official', # Chrome DevTools MCP - Claude "enxerga" o site
    'impeccable@impeccable',                       # Impeccable skill (/impeccable polish, audit...)
    '21st@21st-dev',                               # 21st.dev Magic MCP - componentes prontos (precisa API key)
    # --- Os mais usados para programar
    'context7@claude-plugins-official',            # documentacao atualizada de qualquer biblioteca
    'superpowers@claude-plugins-official',         # brainstorm, planos, TDD, debug sistematico
    'github@claude-plugins-official',              # GitHub MCP (precisa token)
    'feature-dev@claude-plugins-official',         # fluxo guiado para criar features
    'code-review@claude-plugins-official',
    'pr-review-toolkit@claude-plugins-official',
    'commit-commands@claude-plugins-official',     # /commit, /commit-push-pr
    'security-guidance@claude-plugins-official',   # avisa sobre codigo inseguro
    'code-simplifier@claude-plugins-official',
    'claude-md-management@claude-plugins-official',
    'skill-creator@claude-plugins-official',       # cria suas proprias skills
    'typescript-lsp@claude-plugins-official',
    'pyright-lsp@claude-plugins-official'
)
foreach ($p in $plugins) {
    $out = claude plugin install $p --scope user 2>&1 | Out-String
    if ($LASTEXITCODE -eq 0) { Ok $p } else { Aviso "$p -> $($out.Trim())" }
}

# ---------------------------------------------------------------- 4. MCP extra
Titulo "4/6  MCP extra: shadcn/ui"
claude mcp remove shadcn --scope user 2>&1 | Out-Null
claude mcp add --scope user shadcn -- cmd /c npx -y @jpisnice/shadcn-ui-mcp-server 2>&1 | Out-Null
Ok "shadcn-ui-mcp-server"

# ---------------------------------------------------------------- 5. Skills
Titulo "5/6  Skills de design (Vercel, Emil Kowalski, Taste)"
$skills = @(
    @{ repo = 'vercel-labs/agent-skills';  nomes = @('web-design-guidelines', 'vercel-react-best-practices', 'vercel-composition-patterns') },
    @{ repo = 'emilkowalski/skills';       nomes = @('emil-design-eng', 'review-animations', 'improve-animations') },
    @{ repo = 'Leonxlnx/taste-skill';      nomes = @('design-taste-frontend', 'redesign-existing-projects', 'high-end-visual-design') }
)
foreach ($s in $skills) {
    $a = @('-y', 'skills@latest', 'add', $s.repo, '-g', '-a', 'claude-code', '-y', '--copy')
    foreach ($n in $s.nomes) { $a += @('-s', $n) }
    npx @a 2>&1 | Out-Null
    Ok "$($s.repo): $($s.nomes -join ', ')"
}

# ---------------------------------------------------------------- 6. Logins
Titulo "6/6  Logins (vou abrir as telas pra voce)"

Write-Host ""
Write-Host "  a) 21st.dev (componentes de UI). Crie a conta / faca login e copie a API key." -ForegroundColor White
Start-Process 'https://21st.dev/mcp'
$k = Read-Host "     Cole a API key do 21st.dev (ou Enter para pular)"
if ($k) { [Environment]::SetEnvironmentVariable('API_KEY_21ST', $k.Trim(), 'User'); Ok "API_KEY_21ST salva" }

Write-Host ""
Write-Host "  b) GitHub (para o Claude mexer em repos, PRs e issues). Gere um token 'classic'." -ForegroundColor White
Start-Process 'https://github.com/settings/tokens/new?description=Claude%20Code&scopes=repo,read:org,workflow'
$g = Read-Host "     Cole o token do GitHub (ou Enter para pular)"
if ($g) { [Environment]::SetEnvironmentVariable('GITHUB_PERSONAL_ACCESS_TOKEN', $g.Trim(), 'User'); Ok "GITHUB_PERSONAL_ACCESS_TOKEN salvo" }

Write-Host ""
Write-Host "  c) Conta Anthropic + Figma: vou abrir o Claude Code agora." -ForegroundColor White
Write-Host "     1. Se pedir login, entre com sua conta Claude (abre no navegador)." -ForegroundColor Gray
Write-Host "     2. Dentro do Claude, digite  /mcp  -> escolha 'figma' -> Authenticate" -ForegroundColor Gray
Write-Host "        (abre o navegador; clique em 'Allow access' na tela do Figma)." -ForegroundColor Gray
Write-Host "     3. Digite  /mcp  de novo para ver tudo conectado (bolinha verde)." -ForegroundColor Gray
Write-Host ""
Read-Host "  Enter para abrir o Claude Code"

AtualizaPath
$env:API_KEY_21ST = [Environment]::GetEnvironmentVariable('API_KEY_21ST', 'User')
$env:GITHUB_PERSONAL_ACCESS_TOKEN = [Environment]::GetEnvironmentVariable('GITHUB_PERSONAL_ACCESS_TOKEN', 'User')
Set-Location $env:USERPROFILE
claude
