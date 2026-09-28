<#
.NOTES
    Projeto        : Azor WinUtil - otimização do Windows no estilo Rosé
    Fork           : azor
    Baseado em     : WinUtil de Chris Titus Tech (@christitustech) - licença MIT
    Runspace Author: @DeveloperDurp
    GitHub original: https://github.com/ChrisTitusTech/winutil
    Version        : 26.09.24
#>

param (
    [string]$Config,
    [ValidateSet("Standard", "Gaming", "")]
    [string]$Preset,
    [switch]$Offline
)

$PARAM_OFFLINE = $false
if ($Offline) {
    $PARAM_OFFLINE = $true
}

if ($ExecutionContext.SessionState.LanguageMode -ne 'FullLanguage') {
    Write-Host "O Azor WinUtil não pode ser executado neste sistema: a execução do PowerShell está restrita por políticas de segurança." -ForegroundColor Red
    return
}

if (!([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Output "O Azor WinUtil precisa ser executado como Administrador. Tentando reabrir com permissão elevada..."
    $argList = @()

    $PSBoundParameters.GetEnumerator() | ForEach-Object {
        $argList += if ($_.Value -is [switch] -and $_.Value) {
            "-$($_.Key)"
        } elseif ($_.Value -is [array]) {
            "-$($_.Key) $($_.Value -join ',')"
        } elseif ($_.Value) {
            "-$($_.Key) '$($_.Value)'"
        }
    }

    $elevatedScriptPath = $PSCommandPath
    if (-not $elevatedScriptPath) {
        # Running from memory, e.g. & ([ScriptBlock]::Create(...)): save this script to a temp file for the elevated process.
        # Remove-WinUtilTempScript deletes that copy when the elevated window closes.
        $scriptDefinition = $MyInvocation.MyCommand.Definition
        if ($scriptDefinition -and $scriptDefinition.Contains('function Invoke-WPFButton')) {
            $elevatedScriptPath = Join-Path ([IO.Path]::GetTempPath()) "azorwinutil-$([guid]::NewGuid().ToString('N')).ps1"
            [System.IO.File]::WriteAllText($elevatedScriptPath, $scriptDefinition, (New-Object System.Text.UTF8Encoding $true))
        }
    }

    if (-not $elevatedScriptPath) {
        Write-Host "Não foi possível reabrir automaticamente. Abra o PowerShell como Administrador e execute o Azor WinUtil novamente." -ForegroundColor Yellow
        return
    }

    $script = "& { & `'$($elevatedScriptPath)`' $($argList -join ' ') }"

    $powershellCmd = if (Get-Command pwsh -ErrorAction SilentlyContinue) { "pwsh" } else { "powershell" }
    $processCmd = if (Get-Command wt.exe -ErrorAction SilentlyContinue) { "wt.exe" } else { "$powershellCmd" }

    if ($processCmd -eq "wt.exe") {
        Start-Process $processCmd -ArgumentList "$powershellCmd -ExecutionPolicy Bypass -NoProfile -Command `"$script`"" -Verb RunAs
    } else {
        Start-Process $processCmd -ArgumentList "-ExecutionPolicy Bypass -NoProfile -Command `"$script`"" -Verb RunAs
    }

    break
}

# Variable to sync between runspaces
$sync = [Hashtable]::Synchronized(@{})
$sync.version = "26.09.24"
$sync.configs = @{}
$sync.Buttons = [System.Collections.Generic.List[PSObject]]::new()
$sync.preferences = @{}
$sync.ProcessRunning = $false
$sync.selectedAppx = [System.Collections.Generic.List[string]]::new()
$sync.selectedApps = [System.Collections.Generic.List[string]]::new()
$sync.selectedTweaks = [System.Collections.Generic.List[string]]::new()
$sync.selectedToggles = [System.Collections.Generic.List[string]]::new()
$sync.selectedFeatures = [System.Collections.Generic.List[string]]::new()
$sync.currentTab = "Dashboard"

$dateTime = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$winutildir = "$env:LocalAppData\azorwinutil"
$sync.winutildir = $winutildir

$logdir = "$winutildir\logs"
$sync.logPath = "$logdir\azorwinutil_$dateTime.log"
$sync.transcriptPath = $sync.logPath
Start-Transcript -Path $sync.logPath -Append -NoClobber | Out-Null

$Host.UI.RawUI.WindowTitle = "Azor WinUtil"
Clear-Host

# ============================ AZOR COMPANION ============================
# A familia Azor tem dois apps que conversam por recados em
# %LOCALAPPDATA%\Azor\companion. O AzorOptimization e o simples (um clique,
# para o cliente); o AzorWinUtil e o avancado (instalar apps, remover bloatware,
# tweaks profundos). Cada um le o que o outro fez para nao brigar
# pelo mesmo ajuste, e publica o que ele mesmo aplicou. Tudo em melhor esforco:
# uma falha aqui nunca impede o WinUtil de funcionar.
# Read-AzorOptimization e Write-AzorWinUtilState ficam em functions/private, que o
# Compile.ps1 cola depois deste arquivo; o aviso e o primeiro recado saem no inicio de scripts/main.ps1.
$sync.azorCompanionDir  = Join-Path $env:LocalAppData "Azor\companion"
$sync.azorOptStatePath  = Join-Path $sync.azorCompanionDir "optimization.json"
$sync.azorWinUtilPath   = Join-Path $sync.azorCompanionDir "winutil.json"
function Add-SelectedAppsMenuItem {
    <#
    .SYNOPSIS
        This is a helper function that generates and adds the Menu Items to the Selected Apps Popup.

    .Parameter name
        The actual Name of an App like "Chrome" or "Brave"
        This name is contained in the "Content" property inside the applications.json
    .PARAMETER key
        The key which identifies an app object in applications.json
        For Chrome this would be "WPFInstallchrome" because "WPFInstall" is prepended automatically for each key in applications.json
    #>

    param ([string]$name, [string]$key)

    $selectedAppGrid = New-Object Windows.Controls.Grid

    $selectedAppGrid.ColumnDefinitions.Add((New-Object System.Windows.Controls.ColumnDefinition -Property @{Width = "*"}))
    $selectedAppGrid.ColumnDefinitions.Add((New-Object System.Windows.Controls.ColumnDefinition -Property @{Width = "30"}))

    # Sets the name to the Content as well as the Tooltip, because the parent Popup Border has a fixed width and text could "overflow".
    # With the tooltip, you can still read the whole entry on hover
    $selectedAppLabel = New-Object Windows.Controls.Label
    $selectedAppLabel.Content = $name
    $selectedAppLabel.ToolTip = $name
    $selectedAppLabel.HorizontalAlignment = "Left"
    $selectedAppLabel.SetResourceReference([Windows.Controls.Control]::ForegroundProperty, "MainForegroundColor")
    [System.Windows.Controls.Grid]::SetColumn($selectedAppLabel, 0)
    $selectedAppGrid.Children.Add($selectedAppLabel)

    $selectedAppRemoveButton = New-Object Windows.Controls.Button
    $selectedAppRemoveButton.FontFamily = "Segoe MDL2 Assets"
    $selectedAppRemoveButton.Content = [string]([char]0xE711)
    $selectedAppRemoveButton.HorizontalAlignment = "Center"
    $selectedAppRemoveButton.Tag = $key
    $selectedAppRemoveButton.ToolTip = "Remover o programa da seleção"
    $selectedAppRemoveButton.SetResourceReference([Windows.Controls.Control]::ForegroundProperty, "MainForegroundColor")
    $selectedAppRemoveButton.SetResourceReference([Windows.Controls.Control]::StyleProperty, "HoverButtonStyle")

    # Highlight the Remove icon on Hover
    $selectedAppRemoveButton.Add_MouseEnter({ $this.SetResourceReference([Windows.Controls.Control]::ForegroundProperty, "WarningColor") })
    $selectedAppRemoveButton.Add_MouseLeave({ $this.SetResourceReference([Windows.Controls.Control]::ForegroundProperty, "MainForegroundColor") })
    $selectedAppRemoveButton.Add_Click({
            $sync.($this.Tag).isChecked = $false # On click of the remove button, we only have to uncheck the corresponding checkbox. This will kick of all necessary changes to update the UI
    })
    [System.Windows.Controls.Grid]::SetColumn($selectedAppRemoveButton, 1)
    $selectedAppGrid.Children.Add($selectedAppRemoveButton)
    # Add new Element to Popup
    $sync.selectedAppsstackPanel.Children.Add($selectedAppGrid)
}

function Close-WinUtilRunspacePool {
    if ($null -eq $sync -or -not $sync.ContainsKey("runspace") -or $null -eq $sync.runspace) {
        return
    }

    try {
        if ($sync.runspace.RunspacePoolStateInfo.State -notin @(
            [System.Management.Automation.Runspaces.RunspacePoolState]::Closed,
            [System.Management.Automation.Runspaces.RunspacePoolState]::Closing,
            [System.Management.Automation.Runspaces.RunspacePoolState]::Broken
        )) {
            $sync.runspace.Close()
        }
    } finally {
        $sync.runspace.Dispose()
        $sync.Remove("runspace")
    }
}

function Find-AppsByNameOrDescription {
    <#
        .SYNOPSIS
            Filters the Install tab entries by search text and by category

        .DESCRIPTION
            Search text and categories are independent filters that both have to pass. An entry is
            shown when its name, description, or application preset key matches the search text, and
            when its category is in the selected set. An empty search matches everything, and an empty
            category set matches every category.

            While either filter is active the matching categories are expanded, since a collapsed
            category would otherwise hide the very results that were asked for. With no filter at
            all the collapsed state the user set is restored.

        .PARAMETER SearchString
            The string to search for. Wildcards are treated as literal characters.

        .PARAMETER Categories
            The categories to show. An empty or missing array shows all of them.

        .NOTES
            - Uses module-scope $sync (no parameter needed; inherits from caller's scope)
            - Safely handles missing hashtable keys and null UI elements
            - Protected by try/catch to prevent UI thread crashes
    #>
    param(
        [Parameter(Mandatory = $false)]
        [string]$SearchString = "",

        [Parameter(Mandatory = $false)]
        [string[]]$Categories = @()
    )

    # Validate that $sync exists and has required structure
    if ($null -eq $sync) {
        Write-Warning "Find-AppsByNameOrDescription: Global `$sync not found. Aborting search."
        return
    }

    if ($null -eq $sync.ItemsControl) {
        Write-Warning "Find-AppsByNameOrDescription: `$sync.ItemsControl not initialized. Aborting search."
        return
    }

    if ($null -eq $sync.configs -or $null -eq $sync.configs.applicationsHashtable) {
        Write-Warning "Find-AppsByNameOrDescription: `$sync.configs.applicationsHashtable not initialized. Aborting search."
        return
    }

    # Categories that filtering expanded on the user's behalf, so clearing the filter can undo it
    if ($null -eq $sync.AppCategoryAutoExpanded) {
        $sync.AppCategoryAutoExpanded = @{}
    }

    try {
        $activeCategories = @($Categories | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
        $hasSearch = -not [string]::IsNullOrWhiteSpace($SearchString)
        $hasCategories = $activeCategories.Count -gt 0

        # Nothing is filtered, so put every entry back and leave the collapsed categories collapsed
        if (-not $hasSearch -and -not $hasCategories) {
            $sync.ItemsControl.Items | ForEach-Object {
                $_.Visibility = [Windows.Visibility]::Visible

                if ($_.Children.Count -ge 2) {
                    $categoryLabel = $_.Children[0]
                    $wrapPanel = $_.Children[1]

                    $categoryLabel.Visibility = [Windows.Visibility]::Visible

                    # A category that filtering expanded goes back to how the user left it
                    $categoryName = $categoryLabel.Content -replace '^[+-] ', ''
                    if ($sync.AppCategoryAutoExpanded.ContainsKey($categoryName)) {
                        $categoryLabel.Content = $categoryLabel.Content -replace "^- ", "+ "
                        $sync.AppCategoryAutoExpanded.Remove($categoryName)
                    }

                    if ($categoryLabel.Content -like "+*") {
                        $wrapPanel.Visibility = [Windows.Visibility]::Collapsed
                    }
                    else {
                        $wrapPanel.Visibility = [Windows.Visibility]::Visible
                    }

                    $wrapPanel.Children | ForEach-Object {
                        $_.Visibility = [Windows.Visibility]::Visible
                    }
                }
            }
            return
        }

        # Escape wildcard characters for literal matching
        $escapedSearchString = [System.Management.Automation.WildcardPattern]::Escape($SearchString)

        $sync.ItemsControl.Items | ForEach-Object {
            # Each item is a StackPanel container with Children[0] = label, Children[1] = WrapPanel
            if ($_.Children.Count -ge 2) {
                $categoryLabel = $_.Children[0]
                $wrapPanel = $_.Children[1]
                $categoryHasMatch = $false

                $categoryLabel.Visibility = [Windows.Visibility]::Visible

                foreach ($appControl in $wrapPanel.Children) {
                    $appTag = $appControl.Tag
                    $appEntry = $null

                    if (-not [string]::IsNullOrWhiteSpace($appTag) -and $sync.configs.applicationsHashtable.ContainsKey($appTag)) {
                        $appEntry = $sync.configs.applicationsHashtable[$appTag]
                    }

                    if ($null -ne $appEntry) {
                        $categoryMatch = -not $hasCategories -or $activeCategories -contains $appEntry.Category
                        $textMatch = -not $hasSearch -or
                            $appEntry.Content -like "*$escapedSearchString*" -or
                            $appEntry.Description -like "*$escapedSearchString*" -or
                            $appTag -like "*$escapedSearchString*"

                        if ($categoryMatch -and $textMatch) {
                            $appControl.Visibility = [Windows.Visibility]::Visible
                            $categoryHasMatch = $true
                        }
                        else {
                            $appControl.Visibility = [Windows.Visibility]::Collapsed
                        }
                    }
                    else {
                        # Hide app if no entry found (data integrity issue)
                        $appControl.Visibility = [Windows.Visibility]::Collapsed
                    }
                }

                if ($categoryHasMatch) {
                    $wrapPanel.Visibility = [Windows.Visibility]::Visible
                    $_.Visibility = [Windows.Visibility]::Visible
                    # Expand it, otherwise the matches stay hidden behind a collapsed header.
                    # Remember that it was collapsed so clearing the filter can put it back.
                    if ($categoryLabel.Content -like "+*") {
                        $categoryLabel.Content = $categoryLabel.Content -replace "^\+ ", "- "
                        $sync.AppCategoryAutoExpanded[($categoryLabel.Content -replace '^- ', '')] = $true
                    }
                }
                else {
                    $_.Visibility = [Windows.Visibility]::Collapsed
                }
            }
        }
    }
    catch {
        Write-Warning "Find-AppsByNameOrDescription: An error occurred during search: $_"
        # Fail gracefully - do not crash the UI thread
        return
    }
}

function Find-TweaksByNameOrDescription {
    <#
        .SYNOPSIS
            Searches through the Tweaks on the Tweaks Tab and hides all entries that do not match the search string

        .DESCRIPTION
            Filters tweak entries by name or description using literal string matching (no wildcard expansion).
            Respects collapsed category state and handles null $sync gracefully.
            Safe for rapid keystroke events; no terminal spam on error conditions.

        .PARAMETER SearchString
            The string to be searched for. Wildcards are treated as literal characters.

        .NOTES
            - Uses module-scope $sync (resolved via global/script fallback if needed)
            - Performs literal matching (no wildcard expansion)
            - Safely handles missing UI elements and null properties
            - Protected by try/catch to prevent UI thread crashes
            - PowerShell 5.1 compatible (no ternary operators, no advanced language features)
    #>
    param(
        [Parameter(Mandatory = $false)]
        [string]$SearchString = ""
    )

    # ------------------------------------------------------------------------------
    # 1. RESOLVE $SYNC WITH MULTI-LEVEL FALLBACK
    # ------------------------------------------------------------------------------

    if ($null -eq $Sync) {
        $Sync = $global:sync
        if ($null -eq $Sync) {
            $Sync = $script:sync
        }
    }

    # Validate that $Sync exists and has required structure
    if ($null -eq $Sync) {
        # Silent return - function called on every keystroke; no warning spam
        return
    }

    if ($null -eq $Sync.Form) {
        # Silent return - form not yet initialized
        return
    }

    # ------------------------------------------------------------------------------
    # 2. GET REFERENCE TO TWEAKS OR APPX PANEL
    # ------------------------------------------------------------------------------

    $panelName = "tweakspanel"
    if ($null -ne $Sync.currentTab -and $Sync.currentTab -eq "AppX") {
        $panelName = "appxpanel"
    }

    $tweaksPanel = $null
    try {
        $tweaksPanel = $Sync.Form.FindName($panelName)
    }
    catch {
        # Silent return - panel not found or disposed
        return
    }

    if ($null -eq $tweaksPanel) {
        # Silent return - panel doesn't exist
        return
    }

    # ------------------------------------------------------------------------------
    # 3. HANDLE EMPTY/WHITESPACE SEARCH STRING - RESET TO DEFAULT STATE
    # ------------------------------------------------------------------------------

    if ([string]::IsNullOrWhiteSpace($SearchString)) {
        try {
            $tweaksPanel.Children | ForEach-Object {
                $categoryBorder = $_

                # Safely set visibility
                if ($null -ne $categoryBorder) {
                    $categoryBorder.Visibility = [Windows.Visibility]::Visible
                }

                # Process each category
                if ($categoryBorder -is [Windows.Controls.Border]) {
                    $dockPanel = $null
                    if ($null -ne $categoryBorder.Child) {
                        $dockPanel = $categoryBorder.Child
                    }

                    if ($dockPanel -is [Windows.Controls.DockPanel]) {
                        $container = $dockPanel.Children | Where-Object { $_ -is [Windows.Controls.ItemsControl] -or $_ -is [Windows.Controls.StackPanel] -or $_ -is [Windows.Controls.ScrollViewer] -or $_.GetType().Name -eq "ItemsControl" } | Select-Object -First 1

                        if ($null -ne $container) {
                            $targetPanel = if ($container.PSObject.Properties['Content'] -and $null -ne $container.Content) { $container.Content } else { $container }
                            $items = $null
                            if ($targetPanel -is [Windows.Controls.ItemsControl] -or $targetPanel.GetType().Name -eq "ItemsControl") {
                                $items = $targetPanel.Items
                            }
                            else {
                                $items = $targetPanel.Children
                            }
                            # Show all items in the category
                            foreach ($item in $items) {
                                if ($null -ne $item) {
                                    # Check if it's a category label (first Label in the container)
                                    if ($item -is [Windows.Controls.Label] -or $item.GetType().Name -eq "Label") {
                                        $item.Visibility = [Windows.Visibility]::Visible
                                    }
                                    elseif ($item -is [Windows.Controls.DockPanel] -or $item -is [Windows.Controls.StackPanel] -or $item.GetType().Name -eq "DockPanel" -or $item.GetType().Name -eq "StackPanel") {
                                        # Show all checkbox containers
                                        $item.Visibility = [Windows.Visibility]::Visible
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        catch {
            # Silent catch - UI element may be disposed
            $null = $_
        }

        return
    }

    # ------------------------------------------------------------------------------
    # 4. PERFORM LITERAL SEARCH (NO WILDCARD EXPANSION)
    # ------------------------------------------------------------------------------

    try {
        # Normalize search term once for the entire operation
        $searchTerm = $SearchString
        if ($null -eq $searchTerm) {
            $searchTerm = ""
        }

        # Iterate through all categories
        $tweaksPanel.Children | ForEach-Object {
            $categoryBorder = $_
            $categoryHasMatch = $false

            if ($categoryBorder -is [Windows.Controls.Border]) {
                $dockPanel = $null
                if ($null -ne $categoryBorder.Child) {
                    $dockPanel = $categoryBorder.Child
                }

                if ($dockPanel -is [Windows.Controls.DockPanel]) {
                    $container = $dockPanel.Children | Where-Object { $_ -is [Windows.Controls.ItemsControl] -or $_ -is [Windows.Controls.StackPanel] -or $_ -is [Windows.Controls.ScrollViewer] -or $_.GetType().Name -eq "ItemsControl" } | Select-Object -First 1

                    if ($null -ne $container) {
                        $categoryLabel = $null

                        $targetPanel = if ($container.PSObject.Properties['Content'] -and $null -ne $container.Content) { $container.Content } else { $container }
                        $items = $null
                        if ($targetPanel -is [Windows.Controls.ItemsControl] -or $targetPanel.GetType().Name -eq "ItemsControl") {
                            $items = $targetPanel.Items
                        }
                        else {
                            $items = $targetPanel.Children
                        }
                        # Process all items (checkboxes, labels, panels) in the container
                        foreach ($item in $items) {
                            if ($null -eq $item) {
                                continue
                            }

                            # ------------------------------------------------------------
                            # Check if this is a category label (usually first Label)
                            # ------------------------------------------------------------

                            if ($item -is [Windows.Controls.Label] -or $item.GetType().Name -eq "Label") {
                                $categoryLabel = $item
                                # Initially hide category label; show it only if matches found
                                $item.Visibility = [Windows.Visibility]::Collapsed
                            }

                            # ------------------------------------------------------------
                            # Check if this is a DockPanel containing a tweak checkbox
                            # ------------------------------------------------------------

                            elseif ($item -is [Windows.Controls.DockPanel] -or $item.GetType().Name -eq "DockPanel") {
                                $checkbox = $null
                                $label = $null

                                # Safely extract checkbox and label
                                $checkbox = $item.Children | Where-Object { $_ -is [Windows.Controls.CheckBox] -or $_.GetType().Name -eq "CheckBox" } | Select-Object -First 1
                                $label = $item.Children | Where-Object { $_ -is [Windows.Controls.Label] -or $_.GetType().Name -eq "Label" } | Select-Object -First 1

                                # Check if tweak matches search criteria
                                $itemMatches = $false

                                if ($null -ne $label) {
                                    $labelContent = $label.Content
                                    $labelToolTip = $label.ToolTip

                                    # Safely null-check properties
                                    if ($null -eq $labelContent) {
                                        $labelContent = ""
                                    }
                                    if ($null -eq $labelToolTip) {
                                        $labelToolTip = ""
                                    }

                                    # Convert to string and perform LITERAL matching
                                    $labelContentStr = [string]$labelContent
                                    $labelToolTipStr = [string]$labelToolTip

                                    # Use IndexOf for literal matching (no wildcard interpretation)
                                    $contentMatch = $labelContentStr.IndexOf($searchTerm, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
                                    $toolTipMatch = $labelToolTipStr.IndexOf($searchTerm, [System.StringComparison]::OrdinalIgnoreCase) -ge 0

                                    if ($contentMatch -or $toolTipMatch) {
                                        $itemMatches = $true
                                    }
                                }

                                # Set visibility based on match result
                                if ($itemMatches) {
                                    $item.Visibility = [Windows.Visibility]::Visible
                                    $categoryHasMatch = $true
                                }
                                else {
                                    $item.Visibility = [Windows.Visibility]::Collapsed
                                }
                            }

                            # ------------------------------------------------------------
                            # Check if this is a StackPanel containing a tweak checkbox
                            # ------------------------------------------------------------

                            elseif ($item -is [Windows.Controls.StackPanel] -or $item.GetType().Name -eq "StackPanel") {
                                $checkbox = $null
                                $checkbox = $item.Children | Where-Object { $_ -is [Windows.Controls.CheckBox] -or $_.GetType().Name -eq "CheckBox" } | Select-Object -First 1

                                $itemMatches = $false

                                if ($null -ne $checkbox) {
                                    $checkboxContent = $checkbox.Content
                                    $checkboxToolTip = $checkbox.ToolTip

                                    # Safely null-check properties
                                    if ($null -eq $checkboxContent) {
                                        $checkboxContent = ""
                                    }
                                    if ($null -eq $checkboxToolTip) {
                                        $checkboxToolTip = ""
                                    }

                                    # Convert to string and perform LITERAL matching
                                    $checkboxContentStr = [string]$checkboxContent
                                    $checkboxToolTipStr = [string]$checkboxToolTip

                                    # Use IndexOf for literal matching (no wildcard interpretation)
                                    $contentMatch = $checkboxContentStr.IndexOf($searchTerm, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
                                    $toolTipMatch = $checkboxToolTipStr.IndexOf($searchTerm, [System.StringComparison]::OrdinalIgnoreCase) -ge 0

                                    if ($contentMatch -or $toolTipMatch) {
                                        $itemMatches = $true
                                    }
                                }

                                # Set visibility based on match result
                                if ($itemMatches) {
                                    $item.Visibility = [Windows.Visibility]::Visible
                                    $categoryHasMatch = $true
                                }
                                else {
                                    $item.Visibility = [Windows.Visibility]::Collapsed
                                }
                            }
                        }

                        # ------------------------------------------------------------
                        # Update category label visibility and expanded/collapsed state
                        # ------------------------------------------------------------

                        if ($categoryHasMatch) {
                            # Show category label
                            if ($null -ne $categoryLabel) {
                                $categoryLabel.Visibility = [Windows.Visibility]::Visible

                                # Update category label to expanded state (change "+" to "-")
                                $labelContent = $categoryLabel.Content
                                if ($null -ne $labelContent) {
                                    $labelStr = [string]$labelContent

                                    # Safe string replacement without -replace regex
                                    if ($labelStr.StartsWith("+ ")) {
                                        $expandedLabel = "- " + $labelStr.Substring(2)
                                        $categoryLabel.Content = $expandedLabel
                                    }
                                }
                            }
                        }
                    }
                }

                # ----------------------------------------------------------------
                # Set category border visibility based on whether it has matches
                # ----------------------------------------------------------------

                if ($categoryHasMatch) {
                    $categoryBorder.Visibility = [Windows.Visibility]::Visible
                }
                else {
                    $categoryBorder.Visibility = [Windows.Visibility]::Collapsed
                }
            }
        }
    }
    catch {
        # Silent catch - UI elements may be disposed or in unexpected state
        # Do not log to terminal as this function is called on every keystroke
        $null = $_
    }
}

function Format-WinUtilSize {
    <#
    .SYNOPSIS
        Formats a byte count as GB, MB or KB for pt-BR messages.
    #>
    param(
        [double]$Bytes
    )

    if ($Bytes -ge 1GB) {
        return "{0:N2} GB" -f ($Bytes / 1GB)
    }
    if ($Bytes -ge 1MB) {
        return "{0:N0} MB" -f ($Bytes / 1MB)
    }
    return "{0:N0} KB" -f ($Bytes / 1KB)
}

function Get-WinUtilAdobeHostsBlock {
    <#
    .SYNOPSIS
        Counts the entries of the Adobe URL block list in the hosts file, without changing it.

    .DESCRIPTION
        Older Azor builds offered "Lista de Bloqueio de URLs da Adobe", which appended a downloaded list to the
        hosts file: a "#New Ver" line followed by entries that send Adobe addresses to 0.0.0.0. Returns how many
        0.0.0.0 entries follow that line, or 0 when there is no such line or none of the entries is an Adobe
        address, so a similar marker from another tool is not mistaken for this list.

    .PARAMETER Path
        The hosts file to read.
    #>
    param(
        [string]$Path = (Join-Path $env:SystemRoot "System32\drivers\etc\hosts")
    )

    try {
        $lines = @(Get-Content -LiteralPath $Path -Encoding Default -ErrorAction Stop)
    } catch {
        return 0
    }

    $markerIndex = -1
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -like "#New Ver*") {
            $markerIndex = $index
            break
        }
    }
    if ($markerIndex -lt 0 -or $markerIndex -eq $lines.Count - 1) {
        return 0
    }

    $entries = @($lines[($markerIndex + 1)..($lines.Count - 1)] | Where-Object { $_ -match '^\s*0\.0\.0\.0\s+\S' })
    if (@($entries | Where-Object { $_ -match 'adobe' }).Count -eq 0) {
        return 0
    }

    return $entries.Count
}

function Get-WinUtilAzorAppPath {
    <#
    .SYNOPSIS
        Finds another AZOR app shipped next to Azor WinUtil in the AZOR delivery folder.

    .DESCRIPTION
        Looks in the folder of the running script, then in its sibling folders (the numbered app
        folders of the delivery), then one level below those, and finally in the app's install
        folder. Within a level the most recently written copy wins, so an old copy left in another
        folder does not shadow the current one. The temp copy used by in-memory launches has no
        delivery folder around it, so only the install folder is checked for it.
        Returns $null when the app is not found.

    .PARAMETER App
        Rate (AZOR Rate) or Optimization (AZOR Optimization Obsidian, then the one-click build).

    .PARAMETER ScriptPath
        Path of the running azorwinutil.ps1.
    #>
    param (
        [Parameter(Mandatory)]
        [ValidateSet("Rate", "Optimization")]
        [string]$App,
        [string]$ScriptPath
    )

    $fileNames = if ($App -eq "Rate") { @("AZOR Rate.exe") } else { @("AZOR Optimization.bat", "AZOR Optimization.exe") }
    $installedPath = if ($App -eq "Rate" -and $env:ProgramFiles) { Join-Path $env:ProgramFiles "AZOR\Rate\AzorRate.exe" } else { $null }

    $levels = [System.Collections.Generic.List[string[]]]::new()
    $scriptDir = if ([string]::IsNullOrWhiteSpace($ScriptPath)) { $null } else { Split-Path -Parent $ScriptPath }
    $tempDir = [IO.Path]::GetTempPath().TrimEnd('\')
    if ($scriptDir -and $scriptDir.TrimEnd('\') -ne $tempDir) {
        $levels.Add([string[]]@($scriptDir))
        $parentDir = Split-Path -Parent $scriptDir
        if ($parentDir) {
            $siblings = @(Get-ChildItem -LiteralPath $parentDir -Directory -ErrorAction SilentlyContinue)
            $levels.Add([string[]]@($siblings | ForEach-Object { $_.FullName }))
            $levels.Add([string[]]@($siblings | ForEach-Object {
                Get-ChildItem -LiteralPath $_.FullName -Directory -ErrorAction SilentlyContinue
            } | ForEach-Object { $_.FullName }))
        }
    }

    foreach ($fileName in $fileNames) {
        foreach ($level in $levels) {
            $found = @($level | ForEach-Object {
                $candidate = Join-Path $_ $fileName
                if (Test-Path -LiteralPath $candidate -PathType Leaf) { Get-Item -LiteralPath $candidate }
            } | Sort-Object -Property LastWriteTime -Descending)
            if ($found.Count -gt 0) {
                return $found[0].FullName
            }
        }
    }

    if ($installedPath -and (Test-Path -LiteralPath $installedPath -PathType Leaf)) {
        return $installedPath
    }
    return $null
}

function Get-WinUtilAzorOneClickState {
    <#
    .SYNOPSIS
        Reads, without changing anything, which tweaks the one-click AZOR Optimization keeps active.

    .DESCRIPTION
        The one-click AZOR Optimization (a single AZOR Optimization.exe) writes optimization.json to
        %LocalAppData%\Azor\companion after every optimization, undo and start. Its activeTweaks lists the
        tweaks whose values are applied right now. Returns those ids, or nothing when the note is missing or
        can't be read.

    .PARAMETER NotePath
        The one-click app's companion note.
    #>
    param(
        [string]$NotePath = (Join-Path $env:LOCALAPPDATA "Azor\companion\optimization.json")
    )

    try {
        $note = Get-Content -LiteralPath $NotePath -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
    } catch {
        return
    }
    @($note.activeTweaks) | Where-Object { $_ } | ForEach-Object { [string]$_ }
}

function Get-WinUtilAzorOptimizationState {
    <#
    .SYNOPSIS
        Reads, without changing anything, what the AZOR Optimization app keeps applied for the current user.

    .DESCRIPTION
        AZOR Optimization stores its state under %LocalAppData%\AzorOptimization\user\data: desired_state.json
        lists the tasks it keeps applied, logon_autoapply.json says whether it applies them again every time
        the user signs in, and each file in transactions records one change with the task's own risk
        classification. Returns $null when that folder or desired_state.json doesn't exist. Otherwise returns
        Tasks (Id, Name and, when a change was recorded, Classification), AutoApply and Profile. Files that
        can't be read are skipped.

    .PARAMETER DataPath
        AZOR Optimization's data folder.
    #>
    param(
        [string]$DataPath = (Join-Path $env:LOCALAPPDATA "AzorOptimization\user\data")
    )

    $desiredPath = Join-Path $DataPath "desired_state.json"
    try {
        $desired = Get-Content -LiteralPath $desiredPath -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
    } catch {
        return $null
    }

    $autoApply = $false
    $profileName = ""
    try {
        $logonApply = Get-Content -LiteralPath (Join-Path $DataPath "logon_autoapply.json") -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        $autoApply = [bool]$logonApply.enabled
        $profileName = [string]$logonApply.profile
    } catch {
        $autoApply = $false
    }

    # The most recent change recorded for each task carries the classification AZOR Optimization gave it.
    $latestChange = @{}
    foreach ($changeFile in @(Get-ChildItem -LiteralPath (Join-Path $DataPath "transactions") -Filter "*.json" -File -ErrorAction SilentlyContinue)) {
        try {
            $change = Get-Content -LiteralPath $changeFile.FullName -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        } catch {
            continue
        }
        $taskId = [string]$change.task_id
        if (-not $taskId) {
            continue
        }
        if (-not $latestChange.ContainsKey($taskId) -or [double]$change.order_ns -gt [double]$latestChange[$taskId].order_ns) {
            $latestChange[$taskId] = $change
        }
    }

    $tasks = @(foreach ($task in @($desired.tasks.PSObject.Properties)) {
        $change = $latestChange[$task.Name]
        if (-not $profileName -and $task.Value.profile) {
            $profileName = [string]$task.Value.profile
        }
        [pscustomobject]@{
            Id             = $task.Name
            Name           = [string]$task.Value.name
            Classification = if ($change -and $change.status -eq "applied") { [string]$change.classification } else { "" }
        }
    })

    [pscustomobject]@{
        Tasks     = $tasks
        AutoApply = $autoApply
        Profile   = $profileName
    }
}

function Get-WinUtilCheckupView {
    <#
    .SYNOPSIS
        Organizes a Get-WinUtilGameCompatReport result for the Checkup para Jogos window.

    .DESCRIPTION
        Issues are the checks that are not OK, failures first, then what the app can fix, then what only the
        user can change; checks keep their report order inside each group. Also returns the OK checks, the
        fixable ones, the summary line, the fix button label and a note when TPM, Secure Boot or VBS need the
        user. Nothing is shown or changed here.

    .PARAMETER Report
        The objects returned by Get-WinUtilGameCompatReport.
    #>
    param(
        [object[]]$Report = @()
    )

    $checks = @($Report | Where-Object { $null -ne $_ })
    $ranked = for ($index = 0; $index -lt $checks.Count; $index++) {
        $check = $checks[$index]
        $rank = if ($check.Status -eq "OK") { 3 } elseif ($check.Status -eq "FALHA") { 0 } elseif ($check.CanFix) { 1 } else { 2 }
        [pscustomobject]@{ Check = $check; Rank = $rank; Index = $index }
    }

    $issues = @($ranked | Where-Object { $_.Rank -lt 3 } | Sort-Object -Property Rank, Index | ForEach-Object { $_.Check })
    $ok = @($checks | Where-Object { $_.Status -eq "OK" })
    $fixable = @($issues | Where-Object { $_.CanFix })

    $summary = if ($issues.Count -eq 0) {
        "Tudo em ordem: os $($checks.Count) itens estão OK."
    } else {
        "$($ok.Count) de $($checks.Count) itens OK  •  $($issues.Count) para revisar"
    }

    $fixLabel = if ($fixable.Count -eq 1) { "Corrigir 1 item" } else { "Corrigir $($fixable.Count) itens" }

    $firmwareNote = ""
    if (@($issues | Where-Object { $_.Id -in @("SecureBoot", "Tpm", "Vbs") }).Count -gt 0) {
        $firmwareNote = "TPM, Secure Boot e VBS ficam com você (BIOS e Segurança do Windows)."
    }

    [pscustomobject]@{
        Issues       = $issues
        Ok           = $ok
        Fixable      = $fixable
        Summary      = $summary
        FixLabel     = $fixLabel
        FirmwareNote = $firmwareNote
    }
}

function Get-WinUtilCleanupItem {
    <#
    .SYNOPSIS
        Lists the top-level entries of a cleanup target that Invoke-WPFQuickCleanup may delete.

    .DESCRIPTION
        Only entries whose name matches the target's Filter are returned. The elevated relaunch copy of this
        script (azorwinutil-*.ps1) is never returned, and a target that resolves to a drive root or to a system
        or profile folder returns nothing, even if an environment variable points there.

    .PARAMETER Target
        An object from Get-WinUtilCleanupTarget, or any object with Path and Filter.
    #>
    param(
        [Parameter(Mandatory)]
        $Target
    )

    # A folder the current user can't read counts as missing instead of printing an access error.
    if ([string]::IsNullOrWhiteSpace($Target.Path) -or -not (Test-Path -LiteralPath $Target.Path -ErrorAction SilentlyContinue)) {
        return
    }

    $fullPath = [IO.Path]::GetFullPath($Target.Path).TrimEnd('\')
    $protectedPaths = @(
        [IO.Path]::GetPathRoot($env:SystemRoot)
        $env:SystemRoot
        $env:USERPROFILE
        $env:ProgramData
        $env:LOCALAPPDATA
        $env:APPDATA
        [Environment]::GetFolderPath("Desktop")
        [Environment]::GetFolderPath("MyDocuments")
    ) | Where-Object { $_ } | ForEach-Object { $_.TrimEnd('\') }

    if ($fullPath.Length -le 3 -or $protectedPaths -contains $fullPath) {
        Write-WinUtilLog -Level "WARN" -Component "Cleanup" -Message "Skipped $fullPath because it is not a cache folder."
        return
    }

    $filter = if ([string]::IsNullOrWhiteSpace($Target.Filter)) { "*" } else { [string]$Target.Filter }

    # -Filter uses Win32 wildcards, which can also match longer extensions; -like keeps the match exact.
    Get-ChildItem -LiteralPath $fullPath -Filter $filter -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like $filter -and $_.Name -notlike "azorwinutil-*.ps1" }
}

function Get-WinUtilCleanupTarget {
    <#
    .SYNOPSIS
        Lists the folders the quick cleanup measures and cleans.

    .DESCRIPTION
        Each target has Id, Label, Path, Filter (matched against the folder's top-level entries) and the
        Services that must be stopped while the folder is emptied. Left out on purpose: personal files, games,
        the Recycle Bin (a separate question in Invoke-WPFQuickCleanup), the content Fortnite downloads again
        (Saved\PersistentDownloadDir), the Epic Games Launcher web cache (it keeps the sign-in) and GPU shader
        caches (NVIDIA DXCache/GLCache, D3DSCache), whose removal makes games stutter while shaders recompile.
        The current Fortnite log stays: only the rotated *-backup-*.log files are removed.
    #>

    $systemRoot = $env:SystemRoot
    $localAppData = $env:LOCALAPPDATA

    @(
        [pscustomobject]@{ Id = "UserTemp"; Label = "Temporários do usuário"; Path = $env:TEMP; Filter = "*"; Services = @() }
        [pscustomobject]@{ Id = "WindowsTemp"; Label = "Temporários do Windows"; Path = (Join-Path $systemRoot "Temp"); Filter = "*"; Services = @() }
        [pscustomobject]@{ Id = "WindowsUpdate"; Label = "Cache do Windows Update"; Path = (Join-Path $systemRoot "SoftwareDistribution\Download"); Filter = "*"; Services = @("wuauserv", "bits") }
        [pscustomobject]@{ Id = "DeliveryOptimization"; Label = "Cache da Otimização de Entrega"; Path = (Join-Path $systemRoot "ServiceProfiles\NetworkService\AppData\Local\Microsoft\Windows\DeliveryOptimization\Cache"); Filter = "*"; Services = @("dosvc") }
        [pscustomobject]@{ Id = "ErrorReportArchive"; Label = "Relatórios de erro do Windows"; Path = (Join-Path $env:ProgramData "Microsoft\Windows\WER\ReportArchive"); Filter = "*"; Services = @() }
        [pscustomobject]@{ Id = "ErrorReportQueue"; Label = "Fila de relatórios de erro"; Path = (Join-Path $env:ProgramData "Microsoft\Windows\WER\ReportQueue"); Filter = "*"; Services = @() }
        [pscustomobject]@{ Id = "FortniteLogs"; Label = "Logs antigos do Fortnite"; Path = (Join-Path $localAppData "FortniteGame\Saved\Logs"); Filter = "*-backup-*.log"; Services = @() }
        [pscustomobject]@{ Id = "FortniteCrashes"; Label = "Relatórios de travamento do Fortnite"; Path = (Join-Path $localAppData "FortniteGame\Saved\Crashes"); Filter = "*"; Services = @() }
    )
}

function Get-WinUtilDisplayRefreshRate {
    <#
    .SYNOPSIS
        Lists each active display with its current refresh rate and the highest one Windows offers at the same
        resolution, without changing anything.

    .DESCRIPTION
        Reads the display modes the same way the "Choose a refresh rate" list in Windows Settings gets them
        (EnumDisplaySettings): Current is the rate in use and Max the highest non-interlaced rate at the current
        resolution and color depth. Returns one object per display attached to the desktop with Index (1 for
        the first display), Device, Width, Height, Current and Max. Returns nothing when no display can be read,
        for example in a session without a desktop.
    #>

    if (-not ("AzorWinUtil.DisplayModes" -as [type])) {
        Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

namespace AzorWinUtil
{
    public static class DisplayModes
    {
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        public struct DEVMODE
        {
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string dmDeviceName;
            public short dmSpecVersion;
            public short dmDriverVersion;
            public short dmSize;
            public short dmDriverExtra;
            public int dmFields;
            public int dmPositionX;
            public int dmPositionY;
            public int dmDisplayOrientation;
            public int dmDisplayFixedOutput;
            public short dmColor;
            public short dmDuplex;
            public short dmYResolution;
            public short dmTTOption;
            public short dmCollate;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string dmFormName;
            public short dmLogPixels;
            public int dmBitsPerPel;
            public int dmPelsWidth;
            public int dmPelsHeight;
            public int dmDisplayFlags;
            public int dmDisplayFrequency;
            public int dmICMMethod;
            public int dmICMIntent;
            public int dmMediaType;
            public int dmDitherType;
            public int dmReserved1;
            public int dmReserved2;
            public int dmPanningWidth;
            public int dmPanningHeight;
        }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        public struct DISPLAY_DEVICE
        {
            public int cb;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string DeviceName;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string DeviceString;
            public int StateFlags;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string DeviceID;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string DeviceKey;
        }

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        public static extern bool EnumDisplayDevices(string lpDevice, int iDevNum, ref DISPLAY_DEVICE lpDisplayDevice, int dwFlags);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        public static extern bool EnumDisplaySettings(string lpszDeviceName, int iModeNum, ref DEVMODE lpDevMode);

        public static DEVMODE NewMode()
        {
            DEVMODE mode = new DEVMODE();
            mode.dmSize = (short)Marshal.SizeOf(typeof(DEVMODE));
            return mode;
        }

        public static DISPLAY_DEVICE NewDevice()
        {
            DISPLAY_DEVICE device = new DISPLAY_DEVICE();
            device.cb = Marshal.SizeOf(typeof(DISPLAY_DEVICE));
            return device;
        }
    }
}
"@
    }

    $attachedToDesktop = 0x1
    $interlaced = 0x2
    $currentSettings = -1
    $displayIndex = 0

    for ($deviceNumber = 0; $deviceNumber -lt 16; $deviceNumber++) {
        $device = [AzorWinUtil.DisplayModes]::NewDevice()
        # [NullString]::Value, because PowerShell turns $null into "" for a string argument and Windows then
        # looks for a display named "" instead of listing all of them.
        if (-not [AzorWinUtil.DisplayModes]::EnumDisplayDevices([NullString]::Value, $deviceNumber, [ref]$device, 0)) {
            break
        }
        if (($device.StateFlags -band $attachedToDesktop) -eq 0) {
            continue
        }

        $current = [AzorWinUtil.DisplayModes]::NewMode()
        if (-not [AzorWinUtil.DisplayModes]::EnumDisplaySettings($device.DeviceName, $currentSettings, [ref]$current)) {
            continue
        }

        $maxRate = [int]$current.dmDisplayFrequency
        $mode = [AzorWinUtil.DisplayModes]::NewMode()
        for ($modeNumber = 0; [AzorWinUtil.DisplayModes]::EnumDisplaySettings($device.DeviceName, $modeNumber, [ref]$mode); $modeNumber++) {
            if ($mode.dmPelsWidth -eq $current.dmPelsWidth -and
                $mode.dmPelsHeight -eq $current.dmPelsHeight -and
                $mode.dmBitsPerPel -eq $current.dmBitsPerPel -and
                ($mode.dmDisplayFlags -band $interlaced) -eq 0 -and
                $mode.dmDisplayFrequency -gt $maxRate) {
                $maxRate = [int]$mode.dmDisplayFrequency
            }
            $mode = [AzorWinUtil.DisplayModes]::NewMode()
        }

        $displayIndex++
        [pscustomobject]@{
            Index   = $displayIndex
            Device  = $device.DeviceName
            Width   = [int]$current.dmPelsWidth
            Height  = [int]$current.dmPelsHeight
            Current = [int]$current.dmDisplayFrequency
            Max     = $maxRate
        }
    }
}

function Get-WinUtilEntryToolTip {
    <#
        .SYNOPSIS
            Builds the tooltip string for an app/tweak/feature entry: its description plus its preset JSON key

        .PARAMETER Description
            The entry's description from the config JSON. May be null or empty.

        .PARAMETER Key
            The entry's JSON key as used in preset files (e.g. WPFInstallbrave, WPFTweaksTele).
    #>
    param(
        [Parameter(Mandatory = $false)]
        [string]$Description,

        [Parameter(Mandatory = $true)]
        [string]$Key
    )

    if ([string]::IsNullOrWhiteSpace($Description)) {
        return "Chave de preset: $Key"
    }

    return "$Description`n`nChave de preset: $Key"
}

function Get-WinUtilGameCompatReport {
    <#
    .SYNOPSIS
        Reads, without changing anything, the Windows settings that competitive-game anti-cheats depend on.

    .DESCRIPTION
        Returns one object per check: Id, Name, Status ("OK", "FALHA" or "ATENÇÃO"), Games, Detail, Fix,
        CanFix and Data. FALHA means a game refuses to run or restricts matchmaking; ATENÇÃO means a feature
        breaks, or that a setting could not be read. Requirements come from the publishers' support pages:
        Riot Vanguard (Valorant, League of Legends), Activision RICOCHET (Call of Duty), FACEIT
        (Counter-Strike 2), Epic (Fortnite tournaments) and Xbox network troubleshooting (Teredo).
        The AzorLegacy check also lists what tweaks removed from Azor left behind: MMCSS and priority values,
        the driver-install block and the Adobe block list in the hosts file. The last checks cover settings that
        hold any game back: a display below its highest refresh rate, a missing or old graphics driver,
        background recording, Game Mode turned off and a nearly full Windows drive.
        CanFix is only set for software-side settings.
    #>

    $checks = New-Object System.Collections.Generic.List[object]

    function Add-GameCompatCheck {
        param(
            [string]$Id,
            [string]$Name,
            [string]$Status,
            [string]$Games,
            [string]$Detail,
            [string]$Fix = "",
            [bool]$CanFix = $false,
            $Data = $null
        )

        $checks.Add([pscustomobject]@{
            Id     = $Id
            Name   = $Name
            Status = $Status
            Games  = $Games
            Detail = $Detail
            Fix    = $Fix
            CanFix = $CanFix
            Data   = $Data
        })
    }

    function Get-GameCompatRegistryValue {
        param([string]$Path, [string]$Name)

        try {
            # SilentlyContinue: an absent value is expected, and Stop filled the transcript
            # with TerminatingError lines that read like crashes.
            $item = Get-ItemProperty -Path $Path -Name $Name -ErrorAction SilentlyContinue
            if ($null -eq $item) { return $null }
            return $item.$Name
        } catch {
            return $null
        }
    }

    # What the AZOR Optimization app keeps applied. Its tasks are left to it, so the two apps never undo
    # each other: the checks below report them without offering a fix.
    $azorOptimization = $null
    try {
        $azorOptimization = Get-WinUtilAzorOptimizationState
    } catch {
        $azorOptimization = $null
    }
    $optimizationTaskIds = @(if ($azorOptimization) { $azorOptimization.Tasks | ForEach-Object { $_.Id } })
    # The one-click AZOR Optimization keeps its own tweaks and publishes the active ones in its companion note.
    $oneClickTweakIds = @(try { Get-WinUtilAzorOneClickState } catch { })

    $firmwareGames = "Valorant, League of Legends, CoD Warzone, CS2 no FACEIT e torneios do Fortnite"

    $secureBoot = Get-GameCompatRegistryValue -Path "HKLM:\SYSTEM\CurrentControlSet\Control\SecureBoot\State" -Name "UEFISecureBootEnabled"
    if ($null -ne $secureBoot -and [int]$secureBoot -eq 1) {
        Add-GameCompatCheck -Id "SecureBoot" -Name "Secure Boot" -Status "OK" -Games $firmwareGames -Detail "Ativado."
    } else {
        $detail = if ($null -eq $secureBoot) { "Não foi possível ler o estado: o PC pode estar em modo de BIOS legado (CSM)." } else { "Desativado." }
        Add-GameCompatCheck -Id "SecureBoot" -Name "Secure Boot" -Status "FALHA" -Games $firmwareGames -Detail $detail -Fix "Ative o Secure Boot na BIOS/UEFI da placa-mãe (o Windows não consegue ligar isso)."
    }

    # Win32_Tpm needs administrator rights, so a read error is reported as unknown, never as a missing TPM.
    $tpm = $null
    $tpmReadError = $null
    try {
        $tpm = Get-CimInstance -Namespace "root\cimv2\Security\MicrosoftTpm" -ClassName "Win32_Tpm" -ErrorAction Stop
    } catch {
        $tpmReadError = $_.Exception.Message
    }
    $tpmVersion = if ($tpm) { ([string]$tpm.SpecVersion -split ",")[0].Trim() } else { "" }
    if ($tpmReadError) {
        Add-GameCompatCheck -Id "Tpm" -Name "TPM 2.0" -Status "ATENÇÃO" -Games $firmwareGames -Detail "Não foi possível ler o TPM ($tpmReadError)." -Fix "Abra o Azor WinUtil como administrador, ou confira em tpm.msc se aparece 'O TPM está pronto para uso' com versão 2.0."
    } elseif ($tpm -and $tpmVersion -eq "2.0" -and $tpm.IsEnabled_InitialValue -and $tpm.IsActivated_InitialValue) {
        Add-GameCompatCheck -Id "Tpm" -Name "TPM 2.0" -Status "OK" -Games $firmwareGames -Detail "Presente e ativado."
    } elseif ($tpm -and $tpmVersion -and $tpmVersion -ne "2.0") {
        Add-GameCompatCheck -Id "Tpm" -Name "TPM 2.0" -Status "FALHA" -Games $firmwareGames -Detail "O TPM é da versão $tpmVersion; os jogos exigem a 2.0." -Fix "Veja na BIOS se há opção de TPM 2.0 (Intel PTT ou AMD fTPM)."
    } else {
        Add-GameCompatCheck -Id "Tpm" -Name "TPM 2.0" -Status "FALHA" -Games $firmwareGames -Detail "TPM não encontrado ou desativado." -Fix "Ative o TPM na BIOS/UEFI (Intel PTT ou AMD fTPM)."
    }

    $deviceGuard = $null
    $deviceGuardReadError = $null
    try {
        $deviceGuard = Get-CimInstance -Namespace "root\Microsoft\Windows\DeviceGuard" -ClassName "Win32_DeviceGuard" -ErrorAction Stop
    } catch {
        $deviceGuardReadError = $_.Exception.Message
    }
    $vbsGames = "Vanguard Pre-Check (Valorant, LoL) e FACEIT (CS2)"
    $vbsFix = "Ative a virtualização (Intel VT-x / AMD SVM) na BIOS e ligue a Integridade de Memória em Segurança do Windows > Segurança do dispositivo > Isolamento de núcleo. Reinicie."
    if ($deviceGuardReadError) {
        Add-GameCompatCheck -Id "Vbs" -Name "Segurança Baseada em Virtualização (VBS)" -Status "ATENÇÃO" -Games $vbsGames -Detail "Não foi possível ler o estado da VBS ($deviceGuardReadError)." -Fix "Confira em msinfo32, na linha 'Segurança Baseada em Virtualização'."
    } elseif ($deviceGuard -and [int]$deviceGuard.VirtualizationBasedSecurityStatus -eq 2) {
        Add-GameCompatCheck -Id "Vbs" -Name "Segurança Baseada em Virtualização (VBS)" -Status "OK" -Games $vbsGames -Detail "Em execução."
    } else {
        Add-GameCompatCheck -Id "Vbs" -Name "Segurança Baseada em Virtualização (VBS)" -Status "ATENÇÃO" -Games $vbsGames -Detail "A VBS não está em execução." -Fix $vbsFix
    }

    $disabledComponents = Get-GameCompatRegistryValue -Path "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters" -Name "DisabledComponents"
    $disabledComponentsValue = if ($null -eq $disabledComponents) { [int64]0 } else { [int64]$disabledComponents }
    if (($disabledComponentsValue -band 0x01) -ne 0) {
        Add-GameCompatCheck -Id "Teredo" -Name "Túnel Teredo (rede Xbox)" -Status "ATENÇÃO" -Games "CoD pelo app Xbox (Game Pass), chat de festa e multiplayer da rede Xbox" -Detail ("As interfaces de túnel do IPv6 estão desativadas (DisabledComponents = 0x{0:X})." -f $disabledComponentsValue) -Fix "Voltar DisabledComponents para 0 e o Teredo ao padrão do Windows (precisa reiniciar)." -CanFix $true -Data $disabledComponentsValue
    } else {
        Add-GameCompatCheck -Id "Teredo" -Name "Túnel Teredo (rede Xbox)" -Status "OK" -Games "CoD pelo app Xbox (Game Pass), chat de festa e multiplayer da rede Xbox" -Detail "Não está bloqueado."
    }

    $antiCheatServices = @("vgc", "EasyAntiCheat", "EasyAntiCheat_EOS", "BEService", "FACEIT")
    $disabledAntiCheat = @(foreach ($serviceName in $antiCheatServices) {
        $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if ($service -and [string]$service.StartType -eq "Disabled") {
            [pscustomobject]@{ Name = $serviceName; Target = "Manual" }
        }
    })
    if ($disabledAntiCheat.Count -gt 0) {
        Add-GameCompatCheck -Id "AntiCheatServices" -Name "Serviços de anti-cheat" -Status "FALHA" -Games "Valorant e LoL (vgc), Fortnite (EasyAntiCheat), jogos com BattlEye, CS2 no FACEIT" -Detail ("Desativados: {0}." -f (($disabledAntiCheat | ForEach-Object { $_.Name }) -join ", ")) -Fix "Voltar esses serviços para Manual, que é como os anti-cheats os iniciam." -CanFix $true -Data $disabledAntiCheat
    } else {
        Add-GameCompatCheck -Id "AntiCheatServices" -Name "Serviços de anti-cheat" -Status "OK" -Games "Valorant e LoL (vgc), Fortnite (EasyAntiCheat), jogos com BattlEye, CS2 no FACEIT" -Detail "Nenhum serviço de anti-cheat instalado está desativado."
    }

    $xboxServices = [ordered]@{
        XblAuthManager    = "Manual"
        XblGameSave       = "Manual"
        XboxNetApiSvc     = "Manual"
        GamingServices    = "Automatic"
        GamingServicesNet = "Automatic"
    }
    $disabledXbox = @(foreach ($serviceName in $xboxServices.Keys) {
        $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if ($service -and [string]$service.StartType -eq "Disabled") {
            [pscustomobject]@{ Name = $serviceName; Target = $xboxServices[$serviceName] }
        }
    })
    if ($disabledXbox.Count -gt 0) {
        Add-GameCompatCheck -Id "XboxServices" -Name "Serviços da rede Xbox" -Status "ATENÇÃO" -Games "CoD pelo app Xbox (Game Pass), login com conta Microsoft em jogos e chat de festa" -Detail ("Desativados: {0}." -f (($disabledXbox | ForEach-Object { $_.Name }) -join ", ")) -Fix "Voltar os serviços Xbox para o tipo de inicialização padrão do Windows." -CanFix $true -Data $disabledXbox
    } else {
        Add-GameCompatCheck -Id "XboxServices" -Name "Serviços da rede Xbox" -Status "OK" -Games "CoD pelo app Xbox (Game Pass), login com conta Microsoft em jogos e chat de festa" -Detail "Nenhum serviço Xbox está desativado."
    }

    $gameBar = Get-AppxPackage -Name "Microsoft.XboxGamingOverlay" -ErrorAction SilentlyContinue
    if ($gameBar) {
        Add-GameCompatCheck -Id "GameBar" -Name "Xbox Game Bar" -Status "OK" -Games "Fortnite e outros jogos que chamam o overlay do Xbox" -Detail "Instalada."
    } else {
        Add-GameCompatCheck -Id "GameBar" -Name "Xbox Game Bar" -Status "ATENÇÃO" -Games "Fortnite e outros jogos que chamam o overlay do Xbox" -Detail "Não está instalada, então alguns jogos mostram o aviso ms-gamingoverlay ao abrir." -Fix "Abrir a Xbox Game Bar na Microsoft Store para reinstalar." -CanFix $true
    }

    # Changes left by tweaks that older Azor builds offered and the current app no longer has. An absent registry
    # value means Windows uses its default, so only present, non-default values are reported. Group tells the
    # detail text what each change affects.
    $multimediaProfile = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
    # OptimizationTask is the AZOR Optimization task that sets the same value, and OneClickTweak the one-click
    # app's tweak that does; while either app keeps it, the value is its choice and not a leftover.
    $legacyValues = @(
        [pscustomobject]@{ Group = "Scheduling"; Label = "Categoria da tarefa Games (MMCSS)"; Path = "$multimediaProfile\Tasks\Games"; Name = "Scheduling Category"; Type = "String"; Default = "Medium"; OptimizationTask = "mmcss_games_priority"; OneClickTweak = "mmcss_games_task" }
        [pscustomobject]@{ Group = "Scheduling"; Label = "Reserva de CPU do MMCSS"; Path = $multimediaProfile; Name = "SystemResponsiveness"; Type = "DWord"; Default = "20"; OptimizationTask = "system_responsiveness"; OneClickTweak = "mmcss_system_profile" }
        [pscustomobject]@{ Group = "Scheduling"; Label = "Limitação de rede do MMCSS"; Path = $multimediaProfile; Name = "NetworkThrottlingIndex"; Type = "DWord"; Default = "10"; OptimizationTask = "network_throttling_off"; OneClickTweak = "mmcss_system_profile" }
        [pscustomobject]@{ Group = "Scheduling"; Label = "Prioridade do programa em primeiro plano"; Path = "HKLM:\SYSTEM\CurrentControlSet\Control\PriorityControl"; Name = "Win32PrioritySeparation"; Type = "DWord"; Default = "2"; OptimizationTask = "win32_priority_separation" }
        [pscustomobject]@{ Group = "Drivers"; Label = "Download automático de drivers"; Path = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\DriverSearching"; Name = "SearchOrderConfig"; Type = "DWord"; Default = "1"; OptimizationTask = "" }
        [pscustomobject]@{ Group = "Drivers"; Label = "Instaladores dos fabricantes de dispositivos"; Path = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Device Installer"; Name = "DisableCoInstallers"; Type = "DWord"; Default = "0"; OptimizationTask = "" }
    )
    $changedLegacyValues = @(foreach ($legacyValue in $legacyValues) {
        if ($legacyValue.OptimizationTask -and $optimizationTaskIds -contains $legacyValue.OptimizationTask) {
            continue
        }
        if ($legacyValue.OneClickTweak -and $oneClickTweakIds -contains $legacyValue.OneClickTweak) {
            continue
        }
        $currentValue = Get-GameCompatRegistryValue -Path $legacyValue.Path -Name $legacyValue.Name
        if ($null -ne $currentValue -and [string]$currentValue -ne $legacyValue.Default) {
            [pscustomobject]@{
                Kind    = "Registry"
                Group   = $legacyValue.Group
                Label   = $legacyValue.Label
                Path    = $legacyValue.Path
                Name    = $legacyValue.Name
                Type    = $legacyValue.Type
                Default = $legacyValue.Default
                Current = [string]$currentValue
            }
        }
    })
    $adobeBlockEntries = Get-WinUtilAdobeHostsBlock
    if ($adobeBlockEntries -gt 0) {
        $changedLegacyValues += [pscustomobject]@{
            Kind    = "Hosts"
            Group   = "Adobe"
            Label   = "Bloqueio da Adobe no arquivo hosts"
            Path    = Join-Path $env:SystemRoot "System32\drivers\etc\hosts"
            Name    = ""
            Type    = ""
            Default = ""
            Current = "$adobeBlockEntries endereços"
        }
    }
    if ($changedLegacyValues.Count -gt 0) {
        $legacyGroups = @($changedLegacyValues | ForEach-Object { $_.Group } | Select-Object -Unique)
        $legacyDetail = "Fora do padrão do Windows: {0}. Vêm de ajustes que o Azor não oferece mais." -f (($changedLegacyValues | ForEach-Object { "$($_.Label) = $($_.Current)" }) -join "; ")
        $legacyAffects = New-Object System.Collections.Generic.List[string]
        if ($legacyGroups -contains "Scheduling") {
            $legacyDetail += " Os de MMCSS e prioridade não têm ganho comprovado."
            $legacyAffects.Add("Todos os jogos")
        }
        $legacyFix = "Voltar tudo ao padrão do Windows."
        if ($legacyGroups -contains "Drivers") {
            $legacyDetail += " O bloqueio de drivers impede que periféricos novos, como controles e headsets, baixem driver pelo Windows Update ou instalem o programa do fabricante."
            $legacyAffects.Add("periféricos novos")
        }
        if ($legacyGroups -contains "Adobe") {
            $legacyDetail += " O bloqueio da Adobe corta a ativação e a telemetria dos programas da Adobe."
            $legacyAffects.Add("programas da Adobe")
            $legacyFix = "Voltar tudo ao padrão do Windows (antes, o arquivo hosts ganha uma cópia de segurança)."
        }
        Add-GameCompatCheck -Id "AzorLegacy" -Name "Ajustes antigos do Azor" -Status "ATENÇÃO" -Games ($legacyAffects -join ", ") -Detail $legacyDetail -Fix $legacyFix -CanFix $true -Data $changedLegacyValues
    } else {
        Add-GameCompatCheck -Id "AzorLegacy" -Name "Ajustes antigos do Azor" -Status "OK" -Games "Todos os jogos" -Detail "Nenhum valor de versões antigas do Azor fora do padrão."
    }

    # AZOR Optimization: what it keeps applied, quoting the risk classification it gives its own tasks.
    $optimizationFix = "Esses ajustes se mudam no próprio AZOR Optimization. O Azor WinUtil não mexe no que ele mantém, para os dois apps não desfazerem o trabalho um do outro."
    $oneClickDetail = ""
    if ($oneClickTweakIds.Count -gt 0) {
        $oneClickShared = @($legacyValues | Where-Object { $_.OneClickTweak -and $oneClickTweakIds -contains $_.OneClickTweak } | ForEach-Object { $_.Label })
        $oneClickDetail = "AZOR Optimization de 1 clique: $($oneClickTweakIds.Count) ajustes ativos."
        if ($oneClickShared.Count -gt 0) {
            $oneClickDetail += " O Azor WinUtil deixa com ele: " + ($oneClickShared -join "; ") + "."
        }
    }
    if ($null -eq $azorOptimization -and $oneClickDetail) {
        Add-GameCompatCheck -Id "AzorOptimization" -Name "AZOR Optimization" -Status "OK" -Games "Todos os jogos" -Detail $oneClickDetail -Fix $optimizationFix
    } elseif ($null -eq $azorOptimization) {
        Add-GameCompatCheck -Id "AzorOptimization" -Name "AZOR Optimization" -Status "OK" -Games "Todos os jogos" -Detail "Não foi usado neste usuário."
    } else {
        $optimizationTasks = @($azorOptimization.Tasks)
        $profileText = if ($azorOptimization.Profile) { "Perfil $($azorOptimization.Profile)" } else { "Perfil do AZOR Optimization" }
        $reapplyText = if ($azorOptimization.AutoApply) { "reaplicados toda vez que você entra no Windows" } else { "aplicados; a reaplicação ao entrar no Windows está desligada" }
        $optimizationDetail = "${profileText}: $($optimizationTasks.Count) ajustes, $reapplyText."
        $riskyTasks = @($optimizationTasks | Where-Object { $_.Classification -eq "ARRISCADA" })
        $placeboTasks = @($optimizationTasks | Where-Object { $_.Classification -eq "PLACEBO" })
        $sharedTasks = @($optimizationTasks | Where-Object { $_.Id -in @(@($legacyValues | ForEach-Object { $_.OptimizationTask }) + "mpo_off") })
        if ($riskyTasks.Count -gt 0) {
            $optimizationDetail += " Ele mesmo classifica como ARRISCADA: " + (($riskyTasks | ForEach-Object { $_.Name }) -join "; ") + "."
        }
        if ($placeboTasks.Count -gt 0) {
            $optimizationDetail += " E como PLACEBO: " + (($placeboTasks | ForEach-Object { $_.Name }) -join "; ") + "."
        }
        if ($sharedTasks.Count -gt 0) {
            $optimizationDetail += " O Azor WinUtil deixa com ele: " + (($sharedTasks | ForEach-Object { $_.Name }) -join "; ") + "."
        }
        if ($oneClickDetail) {
            $optimizationDetail += " $oneClickDetail"
        }
        $optimizationStatus = if ($riskyTasks.Count -gt 0) { "ATENÇÃO" } else { "OK" }
        Add-GameCompatCheck -Id "AzorOptimization" -Name "AZOR Optimization" -Status $optimizationStatus -Games "Todos os jogos" -Detail $optimizationDetail -Fix $optimizationFix -Data $optimizationTasks
    }

    $overlayTestMode = Get-GameCompatRegistryValue -Path "HKLM:\SOFTWARE\Microsoft\Windows\Dwm" -Name "OverlayTestMode"
    if ($null -ne $overlayTestMode -and [int]$overlayTestMode -eq 5 -and $optimizationTaskIds -contains "mpo_off") {
        Add-GameCompatCheck -Id "Mpo" -Name "Multiplane Overlay (MPO)" -Status "ATENÇÃO" -Games "Jogos em tela cheia" -Detail "O AZOR Optimization desligou o MPO com a tarefa 'Desligar o Multi-Plane Overlay (MPO)' (OverlayTestMode = 5)." -Fix "Se algum jogo travar ou a tela piscar, desmarque 'Desligar o Multi-Plane Overlay (MPO)' no AZOR Optimization e reinicie o PC."
    } elseif ($null -ne $overlayTestMode -and [int]$overlayTestMode -eq 5) {
        Add-GameCompatCheck -Id "Mpo" -Name "Multiplane Overlay (MPO)" -Status "ATENÇÃO" -Games "Jogos em tela cheia" -Detail "O MPO está desativado (OverlayTestMode = 5)." -Fix "Voltar o MPO ao padrão do Windows (precisa reiniciar)." -CanFix $true
    } else {
        Add-GameCompatCheck -Id "Mpo" -Name "Multiplane Overlay (MPO)" -Status "OK" -Games "Jogos em tela cheia" -Detail "No padrão do Windows."
    }

    # Refresh rate: Windows Settings lists the rates each display accepts at its current resolution, and a
    # display left below its highest rate shows fewer frames per second than the game renders.
    $displays = @()
    try {
        $displays = @(Get-WinUtilDisplayRefreshRate)
    } catch {
        $displays = @()
    }
    $refreshGames = "Todos os jogos: a tela só atualiza tantas vezes por segundo quanto a taxa escolhida"
    $slowDisplays = @($displays | Where-Object { $_.Max - $_.Current -ge 5 })
    if ($displays.Count -eq 0) {
        Add-GameCompatCheck -Id "RefreshRate" -Name "Taxa de atualização do monitor" -Status "ATENÇÃO" -Games $refreshGames -Detail "Não foi possível ler os monitores." -Fix "Confira em Configurações > Sistema > Tela > Tela avançada."
    } elseif ($slowDisplays.Count -gt 0) {
        $refreshDetail = ($slowDisplays | ForEach-Object { "Monitor $($_.Index) está em $($_.Current) Hz, mas aceita até $($_.Max) Hz em $($_.Width)x$($_.Height)" }) -join "; "
        Add-GameCompatCheck -Id "RefreshRate" -Name "Taxa de atualização do monitor" -Status "ATENÇÃO" -Games $refreshGames -Detail "$refreshDetail." -Fix "Em Configurações > Sistema > Tela > Tela avançada, escolha a maior taxa em 'Escolher uma taxa de atualização'." -CanFix $true -Data $slowDisplays
    } else {
        $refreshDetail = ($displays | ForEach-Object { "Monitor $($_.Index): $($_.Current) Hz em $($_.Width)x$($_.Height)" }) -join "; "
        Add-GameCompatCheck -Id "RefreshRate" -Name "Taxa de atualização do monitor" -Status "OK" -Games $refreshGames -Detail "$refreshDetail, a maior taxa em cada resolução."
    }

    # Graphics driver: Epic recommends installing the latest driver for the video card. PCI vendor IDs keep
    # virtual adapters out; a vendor card on the Basic Display driver has no driver installed at all.
    $gpuVendors = @{
        "10DE" = [pscustomobject]@{ Name = "NVIDIA"; Url = "https://www.nvidia.com/pt-br/drivers/"; Tool = "pelo NVIDIA App ou pelo site da NVIDIA" }
        "1002" = [pscustomobject]@{ Name = "AMD"; Url = "https://www.amd.com/pt/support/download/drivers.html"; Tool = "pelo AMD Software: Adrenalin Edition ou pelo site da AMD" }
        "8086" = [pscustomobject]@{ Name = "Intel"; Url = "https://www.intel.com.br/content/www/br/pt/support/detect.html"; Tool = "pelo Assistente de Driver e Suporte Intel" }
    }
    $videoControllers = @()
    try {
        $videoControllers = @(Get-CimInstance -ClassName "Win32_VideoController" -ErrorAction Stop)
    } catch {
        $videoControllers = @()
    }
    $gpuDrivers = @(foreach ($controller in $videoControllers) {
        $vendorId = [regex]::Match([string]$controller.PNPDeviceID, 'VEN_([0-9A-Fa-f]{4})').Groups[1].Value.ToUpperInvariant()
        if (-not $gpuVendors.ContainsKey($vendorId)) {
            continue
        }

        $vendor = $gpuVendors[$vendorId]
        $version = [string]$controller.DriverVersion
        $versionParts = $version.Split(".")
        if ($vendorId -eq "10DE" -and $versionParts.Count -eq 4) {
            # NVIDIA shows its driver as the last five digits of the Windows version: 32.0.16.1692 is 616.92.
            $digits = $versionParts[2] + $versionParts[3].PadLeft(4, "0")
            $digits = $digits.Substring([Math]::Max(0, $digits.Length - 5))
            $version = "{0}.{1}" -f $digits.Substring(0, $digits.Length - 2), $digits.Substring($digits.Length - 2)
        }
        $driverDate = $controller.DriverDate
        [pscustomobject]@{
            Name     = [string]$controller.Name
            Vendor   = $vendor
            Version  = $version
            # WMI stores the driver date as midnight UTC, so the UTC date is the one the vendor published.
            DateText = if ($driverDate) { ", de " + $driverDate.ToUniversalTime().ToString("dd/MM/yyyy") } else { "" }
            AgeDays  = if ($driverDate) { [int]((Get-Date) - $driverDate).TotalDays } else { $null }
            NoDriver = [string]$controller.Name -match 'Basic Display|Vídeo Básico'
        }
    })
    $driverGames = "Fortnite e os outros jogos: a Epic recomenda o driver de vídeo mais recente"
    $missingDrivers = @($gpuDrivers | Where-Object { $_.NoDriver })
    $oldDrivers = @($gpuDrivers | Where-Object { -not $_.NoDriver -and $null -ne $_.AgeDays -and $_.AgeDays -gt 180 })
    if ($gpuDrivers.Count -eq 0) {
        Add-GameCompatCheck -Id "GpuDriver" -Name "Driver da placa de vídeo" -Status "ATENÇÃO" -Games $driverGames -Detail "Nenhuma placa de vídeo NVIDIA, AMD ou Intel encontrada." -Fix "Confira a placa de vídeo no Gerenciador de Dispositivos."
    } elseif ($missingDrivers.Count -gt 0 -or $oldDrivers.Count -gt 0) {
        $driverLines = @(
            $missingDrivers | ForEach-Object { "A placa $($_.Vendor.Name) está sem driver (usando o driver básico do Windows)" }
            $oldDrivers | ForEach-Object { "$($_.Name): driver $($_.Version)$($_.DateText) ($([int]($_.AgeDays / 30)) meses)" }
        )
        $driverVendors = @(@($missingDrivers) + @($oldDrivers) | ForEach-Object { $_.Vendor } | Sort-Object -Property Name -Unique)
        $driverStatus = if ($missingDrivers.Count -gt 0) { "FALHA" } else { "ATENÇÃO" }
        Add-GameCompatCheck -Id "GpuDriver" -Name "Driver da placa de vídeo" -Status $driverStatus -Games $driverGames -Detail (($driverLines -join "; ") + ".") -Fix ("Instalar o driver mais recente " + (($driverVendors | ForEach-Object { $_.Tool }) -join " e ") + ".") -CanFix $true -Data @($driverVendors | ForEach-Object { $_.Url })
    } else {
        $driverDetail = ($gpuDrivers | ForEach-Object { "$($_.Name): driver $($_.Version)$($_.DateText)" }) -join "; "
        Add-GameCompatCheck -Id "GpuDriver" -Name "Driver da placa de vídeo" -Status "OK" -Games $driverGames -Detail "$driverDetail."
    }

    # Background recording ("Record what happened") is off by default; Xbox support notes that it can affect
    # game performance because it uses some of the PC's resources. A policy that turns off Game DVR wins.
    $gameDvrPolicy = Get-GameCompatRegistryValue -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\GameDVR" -Name "AllowGameDVR"
    $historicalCapture = Get-GameCompatRegistryValue -Path "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\GameDVR" -Name "HistoricalCaptureEnabled"
    $recordingGames = "Todos os jogos"
    if (($null -eq $gameDvrPolicy -or [int]$gameDvrPolicy -ne 0) -and $null -ne $historicalCapture -and [int]$historicalCapture -eq 1) {
        Add-GameCompatCheck -Id "BackgroundRecording" -Name "Gravação em segundo plano" -Status "ATENÇÃO" -Games $recordingGames -Detail "A Game Bar grava os últimos momentos do jogo o tempo todo ('Gravar o que aconteceu'). O suporte do Xbox avisa que isso pode afetar o desempenho do jogo." -Fix "Desligar só a gravação em segundo plano; gravar clipes pela Game Bar (Win+Alt+R) continua funcionando." -CanFix $true
    } else {
        Add-GameCompatCheck -Id "BackgroundRecording" -Name "Gravação em segundo plano" -Status "OK" -Games $recordingGames -Detail "Desligada."
    }

    # Game Mode is on by default and gives the game priority access to hardware resources.
    $autoGameMode = Get-GameCompatRegistryValue -Path "HKCU:\Software\Microsoft\GameBar" -Name "AutoGameModeEnabled"
    if ($null -ne $autoGameMode -and [int]$autoGameMode -eq 0) {
        Add-GameCompatCheck -Id "GameMode" -Name "Modo de Jogo" -Status "ATENÇÃO" -Games "Todos os jogos" -Detail "Desligado. O Modo de Jogo dá ao jogo prioridade no acesso ao hardware e vem ligado por padrão no Windows." -Fix "Ligar o Modo de Jogo." -CanFix $true
    } else {
        Add-GameCompatCheck -Id "GameMode" -Name "Modo de Jogo" -Status "OK" -Games "Todos os jogos" -Detail "Ligado."
    }

    # Free space on the Windows drive, which Windows and game updates need to download and install.
    $diskGames = "Atualizações do Windows e dos jogos instalados nessa unidade"
    try {
        $systemDrive = Get-PSDrive -Name $env:SystemDrive.TrimEnd(":") -PSProvider FileSystem -ErrorAction Stop
        $freeBytes = [double]$systemDrive.Free
        $totalBytes = [double]$systemDrive.Free + [double]$systemDrive.Used
        if ($totalBytes -le 0) {
            throw "The size of $($env:SystemDrive) is unknown."
        }
        $freePercent = [int][Math]::Floor($freeBytes / $totalBytes * 100)
        $diskDetail = "$($env:SystemDrive) tem $(Format-WinUtilSize $freeBytes) livres de $(Format-WinUtilSize $totalBytes) ($freePercent%)."
        if ($freeBytes / $totalBytes -lt 0.10) {
            Add-GameCompatCheck -Id "DiskSpace" -Name "Espaço livre no disco do Windows" -Status "ATENÇÃO" -Games $diskGames -Detail "$diskDetail Atualizações precisam de espaço livre para baixar e instalar." -Fix "Abrir a Limpeza Rápida, que mede antes de apagar e pergunta cada item." -CanFix $true
        } else {
            Add-GameCompatCheck -Id "DiskSpace" -Name "Espaço livre no disco do Windows" -Status "OK" -Games $diskGames -Detail $diskDetail
        }
    } catch {
        Add-GameCompatCheck -Id "DiskSpace" -Name "Espaço livre no disco do Windows" -Status "ATENÇÃO" -Games $diskGames -Detail "Não foi possível ler o espaço livre de $($env:SystemDrive)."
    }

    return $checks.ToArray()
}

function Get-WinUtilInstalledAPPX {
    <#

    .SYNOPSIS
        Gets the names of AppX packages installed for all users

    #>

    # AppX module auto-loading can leave PowerShell 7 dependent on a temporary Windows PowerShell
    # compatibility proxy. Run the query in Windows PowerShell 5.1 so it remains available after
    # those temporary proxy files are removed.
    $ps5Command = {
        Get-AppxPackage -AllUsers -ErrorAction Stop | Select-Object -ExpandProperty Name
    }

    $packageOutput = powershell.exe -NoProfile -NonInteractive -Command $ps5Command 2>&1
    if ($LASTEXITCODE -ne 0) {
        $failureDetails = ($packageOutput | Out-String).Trim()
        Write-WinUtilLog -Level "ERROR" -Component "AppX" -Message "Failed to get installed AppX packages: $failureDetails"
        return @()
    }

    return @($packageOutput)
}

function Get-WinUtilOrphanGameCopy {
    <#
    .SYNOPSIS
        Finds old copies of Epic Games Launcher games that the launcher no longer uses, without changing anything.

    .DESCRIPTION
        The Epic Games Launcher can't move an installed game, so moving one to another drive usually means copying
        its folder and installing again at the new place, which leaves the old folder behind. For each game in the
        launcher's .item manifests, the folder with the same name in the default library is reported only when:
        the launcher has that game installed in another folder that exists; the old folder has no .egstore (the
        launcher's data for an installed game); neither folder is inside the other; neither the library, the old
        folder nor the installed game is a junction or symbolic link; and no running process was started from the
        old folder. Each result has Name, Path, InstalledAt and Bytes.

    .PARAMETER ManifestPath
        Folder with the launcher's .item manifests.

    .PARAMETER LibraryRoot
        Folder where the launcher installs games by default.
    #>
    param(
        [string]$ManifestPath = (Join-Path $env:ProgramData "Epic\EpicGamesLauncher\Data\Manifests"),
        [string]$LibraryRoot = (Join-Path $env:ProgramFiles "Epic Games")
    )

    $library = Get-Item -LiteralPath $LibraryRoot -Force -ErrorAction SilentlyContinue
    if ($null -eq $library -or -not $library.PSIsContainer -or ($library.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        return
    }
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Container -ErrorAction SilentlyContinue)) {
        return
    }

    $installs = @(foreach ($manifestFile in @(Get-ChildItem -LiteralPath $ManifestPath -Filter "*.item" -File -Force -ErrorAction SilentlyContinue)) {
        try {
            $manifest = Get-Content -LiteralPath $manifestFile.FullName -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
            if ([string]::IsNullOrWhiteSpace([string]$manifest.InstallLocation)) {
                continue
            }
            [pscustomobject]@{
                Name     = if ($manifest.DisplayName) { [string]$manifest.DisplayName } else { [string]$manifest.AppName }
                Location = [IO.Path]::GetFullPath([string]$manifest.InstallLocation).TrimEnd('\')
            }
        } catch {
            continue
        }
    })
    if ($installs.Count -eq 0) {
        return
    }

    $installedLocations = @($installs | ForEach-Object { $_.Location })
    $runningPaths = @(Get-Process -ErrorAction SilentlyContinue | ForEach-Object { $_.Path } | Where-Object { $_ })
    $libraryPath = $library.FullName.TrimEnd('\')

    foreach ($install in $installs) {
        $copyPath = Join-Path $libraryPath (Split-Path -Path $install.Location -Leaf)

        $isInstallFolder = $false
        foreach ($location in $installedLocations) {
            if ($location -eq $copyPath -or
                $location.StartsWith($copyPath + '\', [StringComparison]::OrdinalIgnoreCase) -or
                $copyPath.StartsWith($location + '\', [StringComparison]::OrdinalIgnoreCase)) {
                $isInstallFolder = $true
            }
        }
        if ($isInstallFolder) {
            continue
        }

        $copy = Get-Item -LiteralPath $copyPath -Force -ErrorAction SilentlyContinue
        $installed = Get-Item -LiteralPath $install.Location -Force -ErrorAction SilentlyContinue
        if ($null -eq $copy -or -not $copy.PSIsContainer -or $null -eq $installed -or -not $installed.PSIsContainer) {
            continue
        }
        if (($copy.Attributes -band [IO.FileAttributes]::ReparsePoint) -or ($installed.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            continue
        }
        if (Test-Path -LiteralPath (Join-Path $copyPath ".egstore")) {
            continue
        }
        if (@($runningPaths | Where-Object { ([string]$_).StartsWith($copyPath + '\', [StringComparison]::OrdinalIgnoreCase) }).Count -gt 0) {
            continue
        }

        [pscustomobject]@{
            Name        = $install.Name
            Path        = $copyPath
            InstalledAt = $install.Location
            Bytes       = Measure-WinUtilCleanupItem -Item @($copy)
        }
    }
}

function Get-WinUtilPackageLogSummary {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Packages,

        [Parameter(Mandatory = $true)]
        [string]$Preference
    )

    @($Packages | ForEach-Object {
        $package = $_
        $packageName = @($package.Name, $package.Description, $package.winget, $package.choco) |
            Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) -and $_ -ne "na" } |
            Select-Object -First 1

        if ([string]::IsNullOrWhiteSpace([string]$packageName)) {
            $packageName = "Unknown package"
        }

        if ($Preference -eq "Choco" -and -not [string]::IsNullOrWhiteSpace([string]$package.choco) -and $package.choco -ne "na") {
            "$packageName (choco: $($package.choco))"
        } elseif (-not [string]::IsNullOrWhiteSpace([string]$package.winget) -and $package.winget -ne "na") {
            "$packageName (winget: $($package.winget))"
        } else {
            "$packageName (no package id)"
        }
    })
}

function Get-WinUtilRecycleBinInfo {
    <#
    .SYNOPSIS
        Measures the Recycle Bin of one drive without changing it.

    .DESCRIPTION
        Windows keeps each deleted item as a $R file or folder, next to a small $I file that records where it
        came from, inside one folder per user under <drive>\$Recycle.Bin. Items counts the $R entries of every
        user and Bytes is their total size. Reading other users' folders needs administrator rights; folders
        that can't be read are skipped.

    .PARAMETER Root
        The $Recycle.Bin folder to measure. Defaults to the one on the Windows drive.
    #>
    param(
        [string]$Root = (Join-Path ([IO.Path]::GetPathRoot($env:SystemRoot)) '$Recycle.Bin')
    )

    $info = [pscustomobject]@{ Bytes = 0.0; Items = 0 }
    if (-not (Test-Path -LiteralPath $Root -ErrorAction SilentlyContinue)) {
        return $info
    }

    foreach ($userFolder in @(Get-ChildItem -LiteralPath $Root -Directory -Force -ErrorAction SilentlyContinue)) {
        $deletedItems = @(Get-ChildItem -LiteralPath $userFolder.FullName -Force -ErrorAction SilentlyContinue | Where-Object { $_.Name -like '$R*' })
        $info.Items += $deletedItems.Count
        $info.Bytes += Measure-WinUtilCleanupItem -Item $deletedItems
    }

    return $info
}

function Get-WinUtilRegistryComboState {
    <#
    .SYNOPSIS
        Finds the configured combo-box state matching the current registry values.

    .PARAMETER Registry
        Registry settings containing a value mapping for each supported state.

    .OUTPUTS
        The name of the matching state.
    #>
    param(
        [Parameter(Mandatory)]
        $Registry
    )

    foreach ($state in $Registry[0].Values.PSObject.Properties) {
        $stateMatches = $true
        foreach ($setting in @($Registry)) {
            $currentValue = Get-WinUtilRegistryComboValue -Setting $setting
            $actualValue = if ($currentValue.Exists -and $null -ne $currentValue.Value) { $currentValue.Value } else { $setting.DefaultValue }
            $configuredValue = $setting.Values.PSObject.Properties[$state.Name].Value
            # Removal represents the effective Windows default when matching the current state.
            $expectedValue = if ($configuredValue -eq "<RemoveEntry>") { $setting.DefaultValue } else { $configuredValue }
            if ([string]$actualValue -ne [string]$expectedValue) {
                $stateMatches = $false
                break
            }
        }
        if ($stateMatches) {
            return $state.Name
        }
    }

    throw "Os valores do registro não correspondem a nenhum estado suportado."
}

function Get-WinUtilRegistryComboValue {
    <#
    .SYNOPSIS
        Reads one registry value for a registry-backed combo-box state.

    .PARAMETER Setting
        The registry setting from the combo-box configuration.
    #>
    param(
        [Parameter(Mandatory)]
        $Setting
    )

    try {
        # SilentlyContinue, not Stop: an absent value is the normal case here, and with
        # Stop the transcript logged a TerminatingError for it on every startup.
        $readErrors = $null
        $item = Get-ItemProperty -Path $Setting.Path -Name $Setting.Name -ErrorAction SilentlyContinue -ErrorVariable readErrors
        $unexpected = @($readErrors | Where-Object {
            $_.Exception -isnot [System.Management.Automation.PSArgumentException] -and
                $_.Exception -isnot [System.Management.Automation.ItemNotFoundException]
        })
        if ($unexpected.Count -gt 0) { throw $unexpected[0].Exception }
        if ($null -eq $item) { return [pscustomobject]@{ Exists = $false; Value = $null } }
        $property = $item.PSObject.Properties[$Setting.Name]
        return [pscustomobject]@{ Exists = $null -ne $property; Value = $property.Value }
    } catch [System.Management.Automation.PSArgumentException] {
        # The registry provider uses PSArgumentException when a named value is absent.
        return [pscustomobject]@{ Exists = $false; Value = $null }
    } catch [System.Management.Automation.ItemNotFoundException] {
        return [pscustomobject]@{ Exists = $false; Value = $null }
    }
}

function Get-WinUtilSelectedPackages {

     param(
         [Parameter(Mandatory = $true)]
         [object] $PackageList,

         [Parameter(Mandatory = $true)]
         [string] $Preference
     )

    if ($PackageList.count -eq 1) {
        Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "Indeterminate" -value 0.01 -overlay "logo" }
    } else {
        Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "Normal" -value 0.01 -overlay "logo" }
    }

    $packagesWinget = [System.Collections.ArrayList]::new()
    $packagesChoco = [System.Collections.ArrayList]::new()
    $packages = @{
        Winget = $packagesWinget
        Choco = $packagesChoco
    }

    function Add-PackageId {
        param(
            [System.Collections.ArrayList]$Target,
            $PackageId
        )

        if ([string]::IsNullOrWhiteSpace([string]$PackageId) -or $PackageId -eq "na") {
            return
        }

        if (-not $Target.Contains($PackageId)) {
            $null = $Target.Add($PackageId)
        }
    }

    foreach ($package in $PackageList) {
        switch ($Preference) {
            "Choco" {
                if ([string]::IsNullOrWhiteSpace([string]$package.choco) -or $package.choco -eq "na") {
                    Add-PackageId -Target $packagesWinget -PackageId $package.winget
                } else {
                    Add-PackageId -Target $packagesChoco -PackageId $package.choco
                }
            }
            "Winget" {
                Add-PackageId -Target $packagesWinget -PackageId $package.winget
            }
        }
    }

    return $packages
}

function Get-WinUtilStartupItem {
    <#
    .SYNOPSIS
        Lists the programs that start with Windows, with their enabled state.

    .DESCRIPTION
        Reads the same sources Task Manager shows on its Startup apps page: the Run keys (current user,
        machine and 32-bit machine) and both Startup folders. The enabled state comes from the
        StartupApproved keys, where the first byte of the binary value is odd when the item is disabled.
        A missing StartupApproved value means the item is enabled.
    #>

    $approvedRoot = "Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"

    $registrySources = @(
        @{ Path = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"; Approved = "HKCU:\$approvedRoot\Run"; Source = "Registro do usuário" }
        @{ Path = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"; Approved = "HKLM:\$approvedRoot\Run"; Source = "Registro (todos os usuários)" }
        @{ Path = "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"; Approved = "HKLM:\$approvedRoot\Run32"; Source = "Registro 32 bits (todos os usuários)" }
    )

    $folderSources = @(
        @{ Path = [Environment]::GetFolderPath("Startup"); Approved = "HKCU:\$approvedRoot\StartupFolder"; Source = "Pasta Inicializar do usuário" }
        @{ Path = [Environment]::GetFolderPath("CommonStartup"); Approved = "HKLM:\$approvedRoot\StartupFolder"; Source = "Pasta Inicializar (todos os usuários)" }
    )

    $testEnabled = {
        param([string]$ApprovedPath, [string]$ValueName)

        $approvedKey = Get-Item -LiteralPath $ApprovedPath -ErrorAction SilentlyContinue
        if ($null -eq $approvedKey) {
            return $true
        }

        $state = $approvedKey.GetValue($ValueName)
        if ($state -is [byte[]] -and $state.Length -gt 0) {
            return (($state[0] -band 1) -eq 0)
        }

        return $true
    }

    foreach ($source in $registrySources) {
        $runKey = Get-Item -LiteralPath $source.Path -ErrorAction SilentlyContinue
        if ($null -eq $runKey) {
            continue
        }

        foreach ($valueName in $runKey.GetValueNames()) {
            if ([string]::IsNullOrWhiteSpace($valueName)) {
                continue
            }

            [pscustomobject]@{
                Name         = $valueName
                Command      = [string]$runKey.GetValue($valueName)
                Source       = $source.Source
                ApprovedPath = $source.Approved
                ValueName    = $valueName
                Enabled      = [bool](& $testEnabled $source.Approved $valueName)
            }
        }
    }

    foreach ($source in $folderSources) {
        if ([string]::IsNullOrWhiteSpace($source.Path) -or -not (Test-Path -LiteralPath $source.Path)) {
            continue
        }

        Get-ChildItem -LiteralPath $source.Path -File -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -ne "desktop.ini" } |
            ForEach-Object {
                [pscustomobject]@{
                    Name         = $_.BaseName
                    Command      = $_.FullName
                    Source       = $source.Source
                    ApprovedPath = $source.Approved
                    ValueName    = $_.Name
                    Enabled      = [bool](& $testEnabled $source.Approved $_.Name)
                }
            }
    }
}

function Get-WinUtilSystemSnapshot {
    <#
    .SYNOPSIS
        Collects the hardware and Windows details shown on the Dashboard tab.

    .DESCRIPTION
        Uses CIM queries, so call it from a background runspace. Every field has a readable
        fallback, so a failed query never shows a raw error on the dashboard.
    #>

    $snapshot = [ordered]@{
        OsName     = "Windows"
        OsVersion  = ""
        OsBuild    = ""
        BootTime   = $null
        CpuName    = "Processador não identificado"
        CpuCores   = 0
        CpuThreads = 0
        GpuNames   = @()
    }

    try {
        $os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
        $snapshot.OsName = ([string]$os.Caption -replace '^Microsoft\s+', '').Trim()
        $snapshot.OsBuild = [string]$os.BuildNumber
        $snapshot.BootTime = $os.LastBootUpTime
    } catch {
        Write-WinUtilLog -Level "WARN" -Component "Dashboard" -Message "Unable to read Windows details: $($_.Exception.Message)"
    }

    try {
        $currentVersion = Get-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' -ErrorAction Stop
        $snapshot.OsVersion = [string]$currentVersion.DisplayVersion
        if ($snapshot.OsBuild -and $null -ne $currentVersion.UBR) {
            $snapshot.OsBuild = "$($snapshot.OsBuild).$($currentVersion.UBR)"
        }
    } catch {
        Write-WinUtilLog -Level "WARN" -Component "Dashboard" -Message "Unable to read the Windows version: $($_.Exception.Message)"
    }

    try {
        $processors = @(Get-CimInstance -ClassName Win32_Processor -ErrorAction Stop)
        if ($processors.Count -gt 0) {
            $snapshot.CpuName = (([string]$processors[0].Name -replace '\((R|TM)\)', '') -replace '\s+', ' ').Trim()
            $snapshot.CpuCores = [int](($processors | Measure-Object -Property NumberOfCores -Sum).Sum)
            $snapshot.CpuThreads = [int](($processors | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum)
        }
    } catch {
        Write-WinUtilLog -Level "WARN" -Component "Dashboard" -Message "Unable to read processor details: $($_.Exception.Message)"
    }

    try {
        $snapshot.GpuNames = @(
            Get-CimInstance -ClassName Win32_VideoController -ErrorAction Stop |
                Where-Object { $_.Name -and $_.Name -notmatch 'Microsoft Basic|Remote Display' } |
                ForEach-Object { ([string]$_.Name).Trim() } |
                Select-Object -Unique
        )
    } catch {
        Write-WinUtilLog -Level "WARN" -Component "Dashboard" -Message "Unable to read graphics adapters: $($_.Exception.Message)"
    }

    return [pscustomobject]$snapshot
}

Function Get-WinUtilToggleStatus ($ToggleSwitch) {

    $ToggleSwitchReg = $sync.configs.tweaks.$ToggleSwitch.registry

    if ($null -eq $sync.ToggleStatusCache) {
        $sync.ToggleStatusCache = @{}
    }

    if ($sync.ToggleStatusCache.ContainsKey($ToggleSwitch)) {
        return [bool]$sync.ToggleStatusCache[$ToggleSwitch]
    }

    if (-not (Get-PSDrive -Name HKU -ErrorAction SilentlyContinue)) {
        New-PSDrive -PSProvider Registry -Name HKU -Root HKEY_USERS | Out-Null
    }

    foreach ($regentry in $ToggleSwitchReg) {

        if (Test-Path $regentry.Path) {
            $regstate = (Get-ItemProperty -Path $regentry.Path).$($regentry.Name)
        } else {
            $regstate = $null
        }

        if ($null -eq $regstate) {
            switch ([string]$regentry.DefaultState) {
                "true"  { $regstate = $regentry.Value }
                "false" { $regstate = $regentry.OriginalValue }
            }
        }

        if ($regstate -ne $regentry.Value) {
            $sync.ToggleStatusCache[$ToggleSwitch] = $false
            return $false
        }
    }

    $sync.ToggleStatusCache[$ToggleSwitch] = $true
    return $true
}

function Get-WinUtilVariables {

    <#
    .SYNOPSIS
        Gets every form object of the provided type

    .OUTPUTS
        List containing every object that matches the provided type
    #>
    param (
        [Parameter()]
        [string[]]$Type
    )
    $keys = ($sync.keys).where{ $_ -like "WPF*" }
    if ($Type) {
        $output = $keys | ForEach-Object {
            try {
                $objType = $sync["$psitem"].GetType().Name
                if ($Type -contains $objType) {
                    Write-Output $psitem
                }
            }
            catch {
                $null = $_
            }
        }
        return $output
    }
    return $keys
}

    function Initialize-InstallAppArea {
        <#
            .SYNOPSIS
                Creates a [Windows.Controls.ScrollViewer] containing a [Windows.Controls.ItemsControl] which is setup to use Virtualization to only load the visible elements for performance reasons.
                This is used as the parent object for all category and app entries on the install tab
                Used to as part of the Install Tab UI generation

            .PARAMETER TargetElement
                The element to which the AppArea should be added

        #>
        param($TargetElement)
        $targetGrid = $sync.Form.FindName($TargetElement)
        $null = $targetGrid.Children.Clear()

        # Create the outer Border for the aren where the apps will be placed
        $Border = New-Object Windows.Controls.Border
        $Border.VerticalAlignment = "Stretch"
        $Border.SetResourceReference([Windows.Controls.Control]::StyleProperty, "BorderStyle")
        # Add a ScrollViewer, because the ItemsControl does not support scrolling by itself
        $scrollViewer = New-Object Windows.Controls.ScrollViewer
        $scrollViewer.VerticalScrollBarVisibility = 'Auto'
        $scrollViewer.HorizontalAlignment = 'Stretch'
        $scrollViewer.VerticalAlignment = 'Stretch'
        $scrollViewer.CanContentScroll = $true
        $Border.Child = $scrollViewer

        ## Create the ItemsControl, which will be the parent of all the app entries
        $itemsControl = New-Object Windows.Controls.ItemsControl
        $itemsControl.HorizontalAlignment = 'Stretch'
        $itemsControl.VerticalAlignment = 'Stretch'
        $scrollViewer.Content = $itemsControl

        # Use WrapPanel to create dynamic columns based on AppEntryWidth and window width
        $itemsPanelTemplate = New-Object Windows.Controls.ItemsPanelTemplate
        $factory = New-Object Windows.FrameworkElementFactory ([Windows.Controls.WrapPanel])
        $factory.SetValue([Windows.Controls.WrapPanel]::OrientationProperty, [Windows.Controls.Orientation]::Horizontal)
        $factory.SetValue([Windows.Controls.WrapPanel]::HorizontalAlignmentProperty, [Windows.HorizontalAlignment]::Left)
        $itemsPanelTemplate.VisualTree = $factory
        $itemsControl.ItemsPanel = $itemsPanelTemplate

        # Add the Border containing the App Area to the target Grid
        $targetGrid.Children.Add($Border) | Out-Null

        return $itemsControl
    }

function Initialize-InstallAppEntry {
    <#
        .SYNOPSIS
            Creates the app entry to be placed on the install tab for a given app
            Used to as part of the Install Tab UI generation
        .PARAMETER TargetElement
            The Element into which the Apps should be placed
        .PARAMETER appKey
            The Key of the app inside the $sync.configs.applicationsHashtable
    #>
        param(
            [Windows.Controls.WrapPanel]$TargetElement,
            $appKey
        )

        $app = $sync.configs.applicationsHashtable.$appKey

        # Create the outer Border for the application type
        $border = New-Object Windows.Controls.Border
        $border.Style = $sync.Form.Resources.AppEntryBorderStyle
        $border.Tag = $appKey
        $border.ToolTip = Get-WinUtilEntryToolTip -Description $app.description -Key $appKey
        $border.Add_MouseLeftButtonUp({
            # Resolve through $sync because the border's child is a layout Grid for FOSS entries
            $childCheckbox = $sync.$($this.Tag)
            $childCheckbox.IsChecked = -not $childCheckbox.IsChecked
        })
        $border.Add_MouseEnter({
            if (($sync.$($this.Tag).IsChecked) -eq $false) {
                $this.SetResourceReference([Windows.Controls.Control]::BackgroundProperty, "AppInstallHighlightedColor")
            }
        })
        $border.Add_MouseLeave({
            if (($sync.$($this.Tag).IsChecked) -eq $false) {
                $this.SetResourceReference([Windows.Controls.Control]::BackgroundProperty, "AppInstallUnselectedColor")
            }
        })
        $border.Add_MouseRightButtonUp({
            # Store the selected app in a global variable so it can be used in the popup
            $sync.appPopupSelectedApp = $this.Tag
            # Set the popup position to the current mouse position
            $sync.appPopup.PlacementTarget = $this
            $sync.appPopup.IsOpen = $true
        })

        $checkBox = New-Object Windows.Controls.CheckBox
        # Sanitize the name for WPF
        $checkBox.Name = $appKey -replace '-', '_'
        # Store the original appKey in Tag
        $checkBox.Tag = $appKey
        $checkbox.Style = $sync.Form.Resources.AppEntryCheckboxStyle
        # The checkbox sits inside the entry layout Grid, so the border is one level further up
        $checkbox.Add_Checked({
            Invoke-WPFSelectedCheckboxesUpdate -type "Add" -checkboxName $this.Tag
            $borderElement = $this.Parent.Parent
            $borderElement.SetResourceReference([Windows.Controls.Control]::BackgroundProperty, "AppInstallSelectedColor")
        })

        $checkbox.Add_Unchecked({
            Invoke-WPFSelectedCheckboxesUpdate -type "Remove" -checkboxName $this.Tag
            $borderElement = $this.Parent.Parent
            $borderElement.SetResourceReference([Windows.Controls.Control]::BackgroundProperty, "AppInstallUnselectedColor")
        })

        $contentPanel = New-Object Windows.Controls.StackPanel
        $contentPanel.Orientation = "Horizontal"
        $contentPanel.VerticalAlignment = [Windows.VerticalAlignment]::Center

        $icon = New-Object Windows.Controls.Grid
        $icon.SetResourceReference([Windows.FrameworkElement]::WidthProperty, "AppEntryIconSize")
        $icon.SetResourceReference([Windows.FrameworkElement]::HeightProperty, "AppEntryIconSize")
        $icon.Margin = New-Object Windows.Thickness(0, 0, 8, 0)
        $fallback = New-Object Windows.Controls.TextBlock
        $fallback.Text = $app.content.TrimStart(".").Substring(0, 1).ToUpper()
        $fallback.FontWeight = "Bold"; $fallback.HorizontalAlignment = "Center"; $fallback.VerticalAlignment = "Center"
        if ($app.link) { $fallback.Visibility = "Collapsed" }
        $fallback.SetResourceReference([Windows.Controls.TextBlock]::FontSizeProperty, "AppEntryFontSize")
        $fallback.SetResourceReference([Windows.Controls.TextBlock]::ForegroundProperty, "ToggleButtonOnColor")
        [void]$icon.Children.Add($fallback)
        if ($app.link) {
            $logo = New-Object Windows.Controls.Image
            $logo.Stretch = [Windows.Media.Stretch]::Uniform
            $logo.Source = "https://www.google.com/s2/favicons?sz=64&domain_url=$([uri]::EscapeDataString($app.link))"
            $logo.Add_ImageFailed({ $this.Visibility = "Collapsed"; $this.Parent.Children[0].Visibility = "Visible" })
            [void]$icon.Children.Add($logo)
        }
        [void]$contentPanel.Children.Add($icon)

        # Create the TextBlock for the application name
        $appName = New-Object Windows.Controls.TextBlock
        $appName.Style = $sync.Form.Resources.AppEntryNameStyle
        $appName.Text = $app.content
        [void]$contentPanel.Children.Add($appName)
        $checkBox.Content = $contentPanel

        # Add accessibility properties to make the elements screen reader friendly
        $checkBox.SetValue([Windows.Automation.AutomationProperties]::NameProperty, $app.content)
        $border.SetValue([Windows.Automation.AutomationProperties]::NameProperty, $app.content)

        # Keep the same layout for every entry so the checkbox handlers can reach the border
        $entryLayout = New-Object Windows.Controls.Grid
        [void]$entryLayout.Children.Add($checkBox)

        # Mark FOSS apps with a corner badge, bled into the border padding so it sits on the edge
        if ($app.foss -eq $true) {
            $fossBadge = New-WinUtilFossBadge
            $fossBadge.HorizontalAlignment = "Right"
            $fossBadge.VerticalAlignment = "Top"
            $fossBadge.Margin = New-Object Windows.Thickness(0, -4, -6, 0)

            [void]$entryLayout.Children.Add($fossBadge)
        }
        $border.Child = $entryLayout
        if ($sync.selectedApps -contains $appKey) {
            $checkBox.IsChecked = $true
        }
        # Add the border to the corresponding Category
        $TargetElement.Children.Add($border) | Out-Null
        return $checkbox
    }

function Initialize-InstallCategoryAppList {
    <#
        .SYNOPSIS
            Clears the Target Element and sets up a "Loading" message. This is done, because loading of all apps can take a bit of time in some scenarios
            Iterates through all Categories and Apps and adds them to the UI
            Used to as part of the Install Tab UI generation
        .PARAMETER TargetElement
            The Element into which the Categories and Apps should be placed
        .PARAMETER Apps
            The Hashtable of Apps to be added to the UI
            The Categories are also extracted from the Apps Hashtable

    #>
        param(
            $TargetElement,
            $Apps
        )

        # Pre-group apps by category before creating WPF controls.
        $appsByCategory = @{}
        foreach ($appKey in $Apps.Keys) {
            $category = $Apps.$appKey.Category
            if (-not $appsByCategory.ContainsKey($category)) {
                $appsByCategory[$category] = @()
            }
            $appsByCategory[$category] += $appKey
        }
        $sync.InstallAppRenderQueue = [System.Collections.Queue]::new()

        foreach ($category in $($appsByCategory.Keys | Sort-Object)) {
            # Create a container for category label + apps
            $categoryContainer = New-Object Windows.Controls.StackPanel
            $categoryContainer.Orientation = "Vertical"
            $categoryContainer.Margin = New-Object Windows.Thickness(0, 0, 0, 0)
            $categoryContainer.HorizontalAlignment = [Windows.HorizontalAlignment]::Stretch
            [System.Windows.Automation.AutomationProperties]::SetName($categoryContainer, $Category)

            # Bind Width to the ItemsControl's ActualWidth to force full-row layout in WrapPanel
            $binding = New-Object Windows.Data.Binding
            $binding.Path = New-Object Windows.PropertyPath("ActualWidth")
            $binding.RelativeSource = New-Object Windows.Data.RelativeSource([Windows.Data.RelativeSourceMode]::FindAncestor, [Windows.Controls.ItemsControl], 1)
            [void][Windows.Data.BindingOperations]::SetBinding($categoryContainer, [Windows.FrameworkElement]::WidthProperty, $binding)

            # Add category label to container
            $toggleButton = New-Object Windows.Controls.Label
            $toggleButton.Content = "- $Category"
            $toggleButton.Tag = "CategoryToggleButton"
            $toggleButton.SetResourceReference([Windows.Controls.Control]::FontSizeProperty, "HeaderFontSize")
            $toggleButton.SetResourceReference([Windows.Controls.Control]::FontFamilyProperty, "HeaderFontFamily")
            $toggleButton.SetResourceReference([Windows.Controls.Control]::ForegroundProperty, "LabelboxForegroundColor")
            $toggleButton.Cursor = [System.Windows.Input.Cursors]::Hand
            $toggleButton.HorizontalAlignment = [Windows.HorizontalAlignment]::Stretch
            $sync.$Category = $toggleButton

            # Add click handler to toggle category visibility
            $toggleButton.Add_MouseLeftButtonUp({
                param($categoryToggle)

                # Find the parent StackPanel (categoryContainer)
                $categoryContainer = $categoryToggle.Parent
                if ($categoryContainer -and $categoryContainer.Children.Count -ge 2) {
                    # The WrapPanel is the second child
                    $wrapPanel = $categoryContainer.Children[1]

                    # An explicit click wins over anything filtering expanded automatically
                    if ($sync.AppCategoryAutoExpanded) {
                        $sync.AppCategoryAutoExpanded.Remove(($categoryToggle.Content -replace '^[+-] ', ''))
                    }

                    # Toggle visibility
                    if ($wrapPanel.Visibility -eq [Windows.Visibility]::Visible) {
                        $wrapPanel.Visibility = [Windows.Visibility]::Collapsed
                        # Change - to +
                        $categoryToggle.Content = $categoryToggle.Content -replace "^- ", "+ "
                    } else {
                        $wrapPanel.Visibility = [Windows.Visibility]::Visible
                        # Change + to -
                        $categoryToggle.Content = $categoryToggle.Content -replace "^\+ ", "- "
                    }
                }
            })

            $null = $categoryContainer.Children.Add($toggleButton)

            # Add wrap panel for apps to container
            $wrapPanel = New-Object Windows.Controls.WrapPanel
            $wrapPanel.Orientation = "Horizontal"
            $wrapPanel.HorizontalAlignment = "Left"
            $wrapPanel.VerticalAlignment = "Top"
            $wrapPanel.Margin = New-Object Windows.Thickness(0, 0, 0, 0)
            $wrapPanel.Visibility = [Windows.Visibility]::Visible
            $wrapPanel.Tag = "CategoryWrapPanel_$category"

            $null = $categoryContainer.Children.Add($wrapPanel)

            # Add the entire category container to the target element
            $null = $TargetElement.Items.Add($categoryContainer)

            $sync.InstallAppRenderQueue.Enqueue([pscustomobject]@{
                Category = $category
                TargetElement = $wrapPanel
                AppKeys = @($appsByCategory[$category] | Sort-Object)
            })
        }

        Start-WinUtilInstallAppRendering
    }

function Initialize-WinUtilDashboard {
    <#
    .SYNOPSIS
        Builds the Dashboard tab: logo, greeting, badges, live metrics, system details, the startup item list
        and the game compatibility alert.

    .DESCRIPTION
        Runs once, on the first activation of the tab. The administrator and network badges come from cheap
        in-process calls, so they show up right away. The live CPU, memory and disk values refresh on a
        DispatcherTimer that only does work while the Dashboard is the current tab. The hardware details and
        the game compatibility check need CIM queries that take a second or two, so they run in a background
        runspace. The runspace hands its results over through a queue that the timer drains on the UI thread,
        because writing $sync from another thread breaks enumerations of $sync running on the UI thread.
    #>

    if ($null -eq $sync.Form -or $null -eq $sync.WPFDashboardCpuValue) {
        return
    }

    if ($null -eq $sync.WPFDashboardLogo.Child) {
        $sync.WPFDashboardLogo.Child = Invoke-WinUtilAssets -Type "logo" -Size 92
    }

    $hour = (Get-Date).Hour
    $greeting = if ($hour -ge 5 -and $hour -lt 12) { "Bom dia" } elseif ($hour -ge 12 -and $hour -lt 18) { "Boa tarde" } else { "Boa noite" }
    $sync.WPFDashboardGreeting.Text = "$greeting, $env:USERNAME"
    $sync.WPFDashboardVersion.Text = "Versão $($sync.version)"
    $sync.WPFDashboardMachineBadge.Text = $env:COMPUTERNAME

    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    $sync.WPFDashboardAdminBadge.Text = if ($isAdmin) { "Administrador" } else { "Sem permissão de administrador" }

    $isOnline = $false
    try {
        $isOnline = [System.Net.NetworkInformation.NetworkInterface]::GetIsNetworkAvailable()
    } catch {
        $isOnline = $false
    }
    $sync.WPFDashboardNetBadge.Text = if ($PARAM_OFFLINE) { "Modo offline" } elseif ($isOnline) { "Rede conectada" } else { "Sem rede" }

    Add-Type -AssemblyName Microsoft.VisualBasic
    Update-WinUtilDashboardMetrics

    if ($null -eq $sync.DashboardResults) {
        $sync.DashboardResults = New-Object 'System.Collections.Concurrent.ConcurrentQueue[object]'
    }

    if ($null -eq $sync.DashboardTimer) {
        $sync.DashboardTimer = New-Object System.Windows.Threading.DispatcherTimer
        $sync.DashboardTimer.Interval = [TimeSpan]::FromSeconds(2)
        $sync.DashboardTimer.Add_Tick({
            $result = $null
            while ($sync.DashboardResults.TryDequeue([ref]$result)) {
                switch ($result.Kind) {
                    "Snapshot" {
                        if ($null -ne $result.CpuCounter) {
                            $sync.DashboardCpuCounter = $result.CpuCounter
                        }
                        Set-WinUtilDashboardSnapshot -Snapshot $result.Snapshot
                    }
                    "GameCompat" {
                        Set-WinUtilDashboardCompatAlert -Report $result.Report
                    }
                }
            }

            if ($sync.currentTab -eq "Dashboard") {
                Update-WinUtilDashboardMetrics
            }
        })
        $sync.DashboardTimer.Start()
    }

    Update-WinUtilStartupItemList

    Invoke-WPFRunspace -ScriptBlock {
        $snapshot = Get-WinUtilSystemSnapshot
        $cpuCounter = $null

        try {
            # English counter names work on every Windows display language
            $cpuCounter = New-Object System.Diagnostics.PerformanceCounter("Processor", "% Processor Time", "_Total")
            [void]$cpuCounter.NextValue()
        } catch {
            $cpuCounter = $null
            Write-WinUtilLog -Level "WARN" -Component "Dashboard" -Message "CPU performance counter unavailable: $($_.Exception.Message)"
        }

        $sync.DashboardResults.Enqueue([pscustomobject]@{
            Kind       = "Snapshot"
            Snapshot   = $snapshot
            CpuCounter = $cpuCounter
        })

        $compatReport = @()
        try {
            $compatReport = @(Get-WinUtilGameCompatReport)
        } catch {
            Write-WinUtilLog -Level "WARN" -Component "Dashboard" -Message "Game compatibility check failed: $($_.Exception.Message)"
        }

        $sync.DashboardResults.Enqueue([pscustomobject]@{
            Kind   = "GameCompat"
            Report = $compatReport
        })
    } | Out-Null
}

function Initialize-WinUtilRunspacePool {
    if ($sync.runspace -and $sync.runspace.RunspacePoolStateInfo.State -eq [System.Management.Automation.Runspaces.RunspacePoolState]::Opened) {
        return $sync.runspace
    }

    if ($sync.runspace) {
        Close-WinUtilRunspacePool
    }

    # Set the maximum number of threads for the RunspacePool to the number of threads on the machine.
    $maxthreads = [Math]::Max([int]$env:NUMBER_OF_PROCESSORS, 1)

    # Create a new session state for parsing variables into our runspace.
    $hashVars = New-Object System.Management.Automation.Runspaces.SessionStateVariableEntry -ArgumentList 'sync', $sync, $null
    $offlineVar = New-Object System.Management.Automation.Runspaces.SessionStateVariableEntry -ArgumentList 'PARAM_OFFLINE', $PARAM_OFFLINE, $null
    $initialSessionState = [System.Management.Automation.Runspaces.InitialSessionState]::CreateDefault()

    $initialSessionState.Variables.Add($hashVars)
    $initialSessionState.Variables.Add($offlineVar)

    # Get every WinUtil/WPF function and add it to the session state.
    $functions = Get-ChildItem function:\ | Where-Object { $_.Name -imatch 'winutil|WPF' }
    foreach ($function in $functions) {
        $functionDefinition = Get-Content function:\$($function.Name)
        $functionEntry = New-Object System.Management.Automation.Runspaces.SessionStateFunctionEntry -ArgumentList $function.Name, $functionDefinition
        $initialSessionState.Commands.Add($functionEntry)
    }

    $sync.runspace = [runspacefactory]::CreateRunspacePool(
        1,                      # Minimum thread count
        $maxthreads,            # Maximum thread count
        $initialSessionState,   # Initial session state
        $Host                   # Machine to create runspaces on
    )

    $sync.runspace.Open()
    return $sync.runspace
}

function Initialize-WinUtilTabContent {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TabName
    )

    if ($null -eq $sync.InitializedTabs) {
        $sync.InitializedTabs = @{}
    }

    if ($sync.InitializedTabs[$TabName]) {
        return
    }

    switch ($TabName) {
        "Install" {
            Initialize-WPFUI -targetGridName "appscategory"

            Initialize-WPFUI -targetGridName "appspanel"
        }
        "Tweaks" {
            Invoke-WPFUIElements -configVariable $sync.configs.tweaks -targetGridName "tweakspanel" -columncount 2
        }
        "Config" {
            Invoke-WPFUIElements -configVariable $sync.configs.feature -targetGridName "featurespanel" -columncount 2
        }
        "AppX" {
            Invoke-WPFUIElements -configVariable $sync.configs.appx -targetGridName "appxpanel" -columncount 2
        }
        "Dashboard" {
            Initialize-WinUtilDashboard
        }
    }

    $sync.InitializedTabs[$TabName] = $true

    # Sync freshly built controls to any selections already in $sync.selected* (import/preset).
    Reset-WPFCheckBoxes -doToggles $true
}

function Initialize-WinUtilTaskbarOverlayAssets {
    param(
        [bool]$IncludeLogo = $true,
        [bool]$IncludeStatusAssets = $true
    )

    if ($IncludeLogo -and -not $sync["logorender"]) {
        $sync["logorender"] = (Invoke-WinUtilAssets -Type "Logo" -Size 90 -Render)
    }

    if ($IncludeStatusAssets -and -not $sync["checkmarkrender"]) {
        $sync["checkmarkrender"] = (Invoke-WinUtilAssets -Type "checkmark" -Size 512 -Render)
    }

    if ($IncludeStatusAssets -and -not $sync["warningrender"]) {
        $sync["warningrender"] = (Invoke-WinUtilAssets -Type "warning" -Size 512 -Render)
    }
}

function Install-WinUtilAPPX {
    <#

    .SYNOPSIS
        Registers a local AppX package or installs it from the Microsoft Store

    .PARAMETER Name
        The AppX package name to install

    .PARAMETER StoreId
        The optional Microsoft Store product ID used when no local manifest is available

    #>
    param (
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [string]$StoreId
    )

    Write-WinUtilLog -Component "AppX" -Message "Installing AppX package: $Name"

    # AppX and DISM cmdlets are more reliable in Windows PowerShell 5.1. Query both installed and
    # provisioned package metadata because either can expose a local manifest that can be registered.
    $ps5Command = {
        $packageName = $args[0]
        $manifestPaths = [System.Collections.Generic.List[string]]::new()

        Get-AppxPackage -AllUsers -Name $packageName -ErrorAction SilentlyContinue |
            Sort-Object -Property Version -Descending |
            ForEach-Object {
                if (-not [string]::IsNullOrWhiteSpace($_.InstallLocation)) {
                    $manifestPaths.Add((Join-Path $_.InstallLocation "AppxManifest.xml"))
                }
            }

        Get-AppxProvisionedPackage -Online -ErrorAction SilentlyContinue |
            Where-Object DisplayName -EQ $packageName |
            ForEach-Object {
                if (-not [string]::IsNullOrWhiteSpace($_.InstallLocation)) {
                    $manifestPaths.Add((Join-Path $_.InstallLocation "AppxManifest.xml"))
                }
            }

        $manifestPath = $manifestPaths |
            Select-Object -Unique |
            Where-Object { Test-Path -LiteralPath $_ } |
            Select-Object -First 1

        if ($null -ne $manifestPath) {
            Add-AppxPackage -Register $manifestPath -DisableDevelopmentMode -ErrorAction Stop
            Write-Output $manifestPath
        }
    }

    $manifestOutput = powershell.exe -NoProfile -NonInteractive -Command $ps5Command -args $Name 2>&1
    if ($LASTEXITCODE -eq 0 -and $null -ne $manifestOutput) {
        $manifestPath = ($manifestOutput | Select-Object -Last 1).ToString().Trim()
        if (-not [string]::IsNullOrWhiteSpace($manifestPath)) {
            Write-WinUtilLog -Component "AppX" -Message "Registered local AppX manifest for $Name`: $manifestPath"
            return
        }
    }

    if ($LASTEXITCODE -ne 0) {
        $failureDetails = ($manifestOutput | Out-String).Trim()
        Write-WinUtilLog -Level "WARN" -Component "AppX" -Message "Local AppX registration failed for $Name`: $failureDetails"
    }

    if ([string]::IsNullOrWhiteSpace($StoreId)) {
        $errorMessage = "Unable to install $Name because no local manifest or Microsoft Store ID is available."
        Write-WinUtilLog -Level "ERROR" -Component "AppX" -Message $errorMessage
        throw $errorMessage
    }

    Write-WinUtilLog -Component "AppX" -Message "No usable local manifest found for $Name. Installing Microsoft Store product $StoreId."
    Install-WinUtilWinget
    Install-WinUtilProgramWinget -Action Install -Programs @("msstore:$StoreId")
}

function Install-WinUtilChoco {
    if (-not (Get-Command -Name choco)) {
      Write-Host "Chocolatey is not installed. Installing now..."
      $installScript = Invoke-WebRequest -Uri https://community.chocolatey.org/install.ps1 -UseBasicParsing
      Invoke-Command -ScriptBlock ([scriptblock]::Create($installScript.Content))
    }
}

function Install-WinUtilProgramChoco {
    param (
        [Parameter(Mandatory=$true)]
        [ValidateSet("Install", "Uninstall")]
        [string]$Action,

        [Parameter(Mandatory=$true)]
        [string[]]$Programs
    )

    if ($Action -eq 'Install') {
        $arguments = "install $Programs -y"
    } else {
        $arguments = "uninstall $Programs -y"
    }

    Write-WinUtilLog -Component "Package" -Message "$Action choco package(s): $($Programs -join ', ')"
    $process = Start-Process -FilePath choco -ArgumentList $arguments -NoNewWindow -Wait -PassThru
    Write-WinUtilLog -Component "Package" -Message "$Action choco package(s) completed: $($Programs -join ', ') (exit code: $($process.ExitCode))"
}

Function Install-WinUtilProgramWinget {
    param (
        [Parameter(Mandatory=$true)]
        [ValidateSet("Install", "Uninstall")]
        [string]$Action,

        [Parameter(Mandatory=$true)]
        [string[]]$Programs
    )

    foreach ($program in $Programs) {
        if ([string]::IsNullOrWhiteSpace($program) -or $program -eq "na") {
            continue
        }

        $source = "winget"
        if ($program.StartsWith("msstore:", [System.StringComparison]::OrdinalIgnoreCase)) {
            $source = "msstore"
            $program = $program.Substring("msstore:".Length)
        }

        if ($Action -eq 'Install') {
            $arguments = @("install", "--id", $program, "--accept-package-agreements", "--accept-source-agreements", "--source", $source, "--silent")
        } else {
            $arguments = @("uninstall", "--id", $program, "--source", $source, "--silent")
        }

        Write-WinUtilLog -Component "Package" -Message "$Action winget package: $program (source: $source)"
        $process = Start-Process -FilePath winget -ArgumentList $arguments -NoNewWindow -Wait -PassThru
        Write-WinUtilLog -Component "Package" -Message "$Action winget package completed: $program (exit code: $($process.ExitCode))"
    }
}

function Install-WinUtilWinget {
    <#

    .SYNOPSIS
        Installs WinGet if not already installed.

    .DESCRIPTION
        installs winGet if needed
    #>
    if ((Test-WinUtilPackageManager -winget) -eq "installed") {
        return
    }

    Write-Host "WinGet is not installed. Installing now..." -ForegroundColor Red

    Install-PackageProvider -Name NuGet -Force
    Install-Module -Name Microsoft.WinGet.Client -Force
    Repair-WinGetPackageManager -AllUsers
}

function Invoke-WinUtilAppCategoryChip {
    <#
        .SYNOPSIS
            Handles a click on an Install tab category chip

        .DESCRIPTION
            The chip carries its category in Tag, so every chip shares this handler. Holding ctrl
            adds the category to the current selection instead of replacing it.

        .PARAMETER Chip
            The chip that was clicked
    #>
    param(
        [Parameter(Mandatory)]
        $Chip
    )

    $ctrlDown = [bool]([System.Windows.Input.Keyboard]::Modifiers -band [System.Windows.Input.ModifierKeys]::Control)
    Set-WinUtilAppCategoryFilter -Category $Chip.Tag -Additive:$ctrlDown
}

function Invoke-WinUtilAssets {
  param (
      $type,
      $Size,
      [switch]$render
  )

  if ($render -and $null -ne $sync) {
      if ($null -eq $sync.RenderedAssetCache) {
          $sync.RenderedAssetCache = @{}
      }

      $cacheKey = "$(([string]$type).ToLowerInvariant())|$Size"
      if ($sync.RenderedAssetCache.ContainsKey($cacheKey)) {
          return $sync.RenderedAssetCache[$cacheKey]
      }
  }

  # Create the Viewbox and set its size
  $LogoViewbox = New-Object Windows.Controls.Viewbox
  $LogoViewbox.Width = $Size
  $LogoViewbox.Height = $Size

  # Create a Canvas to hold the paths
  $canvas = New-Object Windows.Controls.Canvas
  $canvas.Width = 100
  $canvas.Height = 100

  # Define a scale factor for the content inside the Canvas
  $scaleFactor = $Size / 100

  # Apply a scale transform to the Canvas content
  $scaleTransform = New-Object Windows.Media.ScaleTransform($scaleFactor, $scaleFactor)
  $canvas.LayoutTransform = $scaleTransform

  switch ($type) {
      'logo' {
          # Azor mark: a rose "Time Ring", a dark core, a ki scythe, the blade-cut "A" and a Potara-green gem
          $newGradient = {
              param([string[]]$Colors, [Windows.Point]$Start, [Windows.Point]$End)

              $gradient = New-Object Windows.Media.LinearGradientBrush
              $gradient.StartPoint = $Start
              $gradient.EndPoint = $End
              for ($i = 0; $i -lt $Colors.Count; $i++) {
                  $offset = if ($Colors.Count -gt 1) { $i / ($Colors.Count - 1) } else { 0 }
                  $stopColor = [Windows.Media.ColorConverter]::ConvertFromString($Colors[$i])
                  $gradient.GradientStops.Add((New-Object Windows.Media.GradientStop($stopColor, $offset)))
              }
              return $gradient
          }

          $core = New-Object Windows.Shapes.Path
          $core.Data = New-Object Windows.Media.EllipseGeometry([Windows.Point]::new(50, 50), 42, 42)
          $coreBrush = New-Object Windows.Media.RadialGradientBrush
          $coreBrush.GradientOrigin = [Windows.Point]::new(0.35, 0.3)
          $coreBrush.GradientStops.Add((New-Object Windows.Media.GradientStop([Windows.Media.ColorConverter]::ConvertFromString("#3D1233"), 0)))
          $coreBrush.GradientStops.Add((New-Object Windows.Media.GradientStop([Windows.Media.ColorConverter]::ConvertFromString("#0B0709"), 1)))
          $core.Fill = $coreBrush

          $scythe = New-Object Windows.Shapes.Path
          $scythe.Data = [Windows.Media.Geometry]::Parse("M 14,66 C 30,90 68,92 90,40 C 74,74 42,80 14,66 Z")
          $scythe.Fill = & $newGradient @("#B23CFD", "#FF2E93", "#FF8FC8") ([Windows.Point]::new(0, 1)) ([Windows.Point]::new(1, 0))

          $ring = New-Object Windows.Shapes.Path
          $ring.Data = New-Object Windows.Media.EllipseGeometry([Windows.Point]::new(50, 50), 44, 44)
          $ring.Stroke = & $newGradient @("#FFC2E3", "#FF4DA6", "#A64DFF") ([Windows.Point]::new(0, 0)) ([Windows.Point]::new(1, 1))
          $ring.StrokeThickness = 6

          $letter = New-Object Windows.Shapes.Path
          $letter.Data = [Windows.Media.Geometry]::Parse("M 50,14 L 76,80 L 66,80 L 60.4,66 L 39.6,66 L 34,80 L 24,80 Z M 50,40 L 56.8,57 L 43.2,57 Z")
          $letter.Fill = & $newGradient @("#FFFFFF", "#FFD6EA", "#FF7CC2") ([Windows.Point]::new(0.5, 0)) ([Windows.Point]::new(0.5, 1))

          $gem = New-Object Windows.Shapes.Path
          $gem.Data = New-Object Windows.Media.EllipseGeometry([Windows.Point]::new(81, 19), 6, 6)
          $gem.Fill = [System.Windows.Media.BrushConverter]::new().ConvertFromString("#3DDC97")
          $gem.Stroke = [System.Windows.Media.BrushConverter]::new().ConvertFromString("#0B0709")
          $gem.StrokeThickness = 2

          foreach ($shape in @($core, $scythe, $ring, $letter, $gem)) {
              $canvas.Children.Add($shape) | Out-Null
          }
      }
      'checkmark' {
          $canvas.Width = 512
          $canvas.Height = 512

          $scaleFactor = $Size / 2.54
          $scaleTransform = New-Object Windows.Media.ScaleTransform($scaleFactor, $scaleFactor)
          $canvas.LayoutTransform = $scaleTransform

          # Define the circle path
          $circlePathData = "M 1.27,0 A 1.27,1.27 0 1,0 1.27,2.54 A 1.27,1.27 0 1,0 1.27,0"
          $circlePath = New-Object Windows.Shapes.Path
          $circlePath.Data = [Windows.Media.Geometry]::Parse($circlePathData)
          $circlePath.Fill = [System.Windows.Media.BrushConverter]::new().ConvertFromString("#2FBF7F")

          # Define the checkmark path
          $checkmarkPathData = "M 0.873 1.89 L 0.41 1.391 A 0.17 0.17 0 0 1 0.418 1.151 A 0.17 0.17 0 0 1 0.658 1.16 L 1.016 1.543 L 1.583 1.013 A 0.17 0.17 0 0 1 1.599 1 L 1.865 0.751 A 0.17 0.17 0 0 1 2.105 0.759 A 0.17 0.17 0 0 1 2.097 0.999 L 1.282 1.759 L 0.999 2.022 L 0.874 1.888 Z"
          $checkmarkPath = New-Object Windows.Shapes.Path
          $checkmarkPath.Data = [Windows.Media.Geometry]::Parse($checkmarkPathData)
          $checkmarkPath.Fill = [Windows.Media.Brushes]::White

          # Add the paths to the Canvas
          $canvas.Children.Add($circlePath) | Out-Null
          $canvas.Children.Add($checkmarkPath) | Out-Null
      }
      'warning' {
          $canvas.Width = 512
          $canvas.Height = 512

          # Define a scale factor for the content inside the Canvas
          $scaleFactor = $Size / 512  # Adjust scaling based on the canvas size
          $scaleTransform = New-Object Windows.Media.ScaleTransform($scaleFactor, $scaleFactor)
          $canvas.LayoutTransform = $scaleTransform

          # Define the circle path
          $circlePathData = "M 256,0 A 256,256 0 1,0 256,512 A 256,256 0 1,0 256,0"
          $circlePath = New-Object Windows.Shapes.Path
          $circlePath.Data = [Windows.Media.Geometry]::Parse($circlePathData)
          $circlePath.Fill = [System.Windows.Media.BrushConverter]::new().ConvertFromString("#FF3D6A")

          # Define the exclamation mark path
          $exclamationPathData = "M 256 307.2 A 35.89 35.89 0 0 1 220.14 272.74 L 215.41 153.3 A 35.89 35.89 0 0 1 251.27 116 H 260.73 A 35.89 35.89 0 0 1 296.59 153.3 L 291.86 272.74 A 35.89 35.89 0 0 1 256 307.2 Z"
          $exclamationPath = New-Object Windows.Shapes.Path
          $exclamationPath.Data = [Windows.Media.Geometry]::Parse($exclamationPathData)
          $exclamationPath.Fill = [Windows.Media.Brushes]::White

          # Get the bounds of the exclamation mark path
          $exclamationBounds = $exclamationPath.Data.Bounds

          # Calculate the center position for the exclamation mark path
          $exclamationCenterX = ($canvas.Width - $exclamationBounds.Width) / 2 - $exclamationBounds.X
          $exclamationPath.SetValue([Windows.Controls.Canvas]::LeftProperty, $exclamationCenterX)

          # Define the rounded rectangle at the bottom (dot of exclamation mark)
          $roundedRectangle = New-Object Windows.Shapes.Rectangle
          $roundedRectangle.Width = 80
          $roundedRectangle.Height = 80
          $roundedRectangle.RadiusX = 30
          $roundedRectangle.RadiusY = 30
          $roundedRectangle.Fill = [Windows.Media.Brushes]::White

          # Calculate the center position for the rounded rectangle
          $centerX = ($canvas.Width - $roundedRectangle.Width) / 2
          $roundedRectangle.SetValue([Windows.Controls.Canvas]::LeftProperty, $centerX)
          $roundedRectangle.SetValue([Windows.Controls.Canvas]::TopProperty, 324.34)

          # Add the paths to the Canvas
          $canvas.Children.Add($circlePath) | Out-Null
          $canvas.Children.Add($exclamationPath) | Out-Null
          $canvas.Children.Add($roundedRectangle) | Out-Null
      }
      default {
          Write-Host "Invalid type: $type"
      }
  }

  # Add the Canvas to the Viewbox
  $LogoViewbox.Child = $canvas

  if ($render) {
      # Measure and arrange the canvas to ensure proper rendering
      $canvas.Measure([Windows.Size]::new($canvas.Width, $canvas.Height))
      $canvas.Arrange([Windows.Rect]::new(0, 0, $canvas.Width, $canvas.Height))
      $canvas.UpdateLayout()

      # Initialize RenderTargetBitmap correctly with dimensions
      $renderTargetBitmap = New-Object Windows.Media.Imaging.RenderTargetBitmap($canvas.Width, $canvas.Height, 96, 96, [Windows.Media.PixelFormats]::Pbgra32)

      # Render the canvas to the bitmap
      $renderTargetBitmap.Render($canvas)

      # Create a BitmapFrame from the RenderTargetBitmap
      $bitmapFrame = [Windows.Media.Imaging.BitmapFrame]::Create($renderTargetBitmap)

      # Create a PngBitmapEncoder and add the frame
      $bitmapEncoder = [Windows.Media.Imaging.PngBitmapEncoder]::new()
      $bitmapEncoder.Frames.Add($bitmapFrame)

      # Save to a memory stream
      $imageStream = New-Object System.IO.MemoryStream
      $bitmapEncoder.Save($imageStream)
      $imageStream.Position = 0

      # Load the stream into a BitmapImage
      $bitmapImage = [Windows.Media.Imaging.BitmapImage]::new()
      $bitmapImage.BeginInit()
      $bitmapImage.StreamSource = $imageStream
      $bitmapImage.CacheOption = [Windows.Media.Imaging.BitmapCacheOption]::OnLoad
      $bitmapImage.EndInit()
      if ($bitmapImage.CanFreeze) {
          $bitmapImage.Freeze()
      }

      if ($null -ne $sync -and $sync.ContainsKey("RenderedAssetCache")) {
          $sync.RenderedAssetCache[$cacheKey] = $bitmapImage
      }

      return $bitmapImage
  } else {
      return $LogoViewbox
  }
}

Function Invoke-WinUtilCurrentSystem {

    <#

    .SYNOPSIS
        Checks to see what tweaks have already been applied and what programs are installed, and checks the according boxes

    .EXAMPLE
        InvokeWinUtilCurrentSystem -Checkbox "winget"

    #>

    param(
        $CheckBox
    )
    if ($CheckBox -eq "choco") {
        $apps = (choco list | Select-String -Pattern "^\S+").Matches.Value
        $sync.configs.applicationsHashtable.GetEnumerator() | ForEach-Object {
            $packageId = ($_.Value.choco -split ";")[-1].Trim()
            if ($packageId -ne "na" -and $packageId -in $apps) {
                Write-Output $_.Key
            }
        }
    }

    if ($checkbox -eq "winget") {
        $originalEncoding = [Console]::OutputEncoding
        try {
            [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
            $installedProgramOutput = @(winget list --accept-source-agreements --disable-interactivity 2>&1)
            if ($LASTEXITCODE -ne 0) {
                throw "winget list failed with exit code $LASTEXITCODE."
            }
        } finally {
            [Console]::OutputEncoding = $originalEncoding
        }
        $installedProgramText = $installedProgramOutput -join "`n"

        $sync.configs.applicationsHashtable.GetEnumerator() | ForEach-Object {
            $packageId = (($_.Value.winget -split ";")[-1] -replace "^msstore:", "").Trim()
            if ([string]::IsNullOrWhiteSpace($packageId) -or $packageId -eq "na") {
                return
            }

            $packagePattern = "(?im)[^\S\r\n]{2,}$([regex]::Escape($packageId))(?=[^\S\r\n]{2,}|$)"
            if ($installedProgramText -match $packagePattern) {
                Write-Output $_.Key
            }
        }
    }

    if ($CheckBox -eq "tweaks") {

        if (!(Test-Path 'HKU:\')) {$null = (New-PSDrive -PSProvider Registry -Name HKU -Root HKEY_USERS)}

        $sync.configs.tweaks | Get-Member -MemberType NoteProperty | ForEach-Object {

            $Config = $psitem.Name
            $entry = $sync.configs.tweaks.$Config
            $registryKeys = $entry.registry
            $serviceKeys = $entry.service
            $entryType = $entry.Type

            if (($registryKeys -or $serviceKeys) -and $entryType -ne "Combobox") {
                $Values = @()

                if ($entryType -eq "Toggle") {
                    if (-not (Get-WinUtilToggleStatus $Config)) {
                        $values += $False
                    }
                } else {
                    $registryMatchCount = 0
                    $registryTotal = 0

                    Foreach ($tweaks in $registryKeys) {
                        Foreach ($tweak in $tweaks) {
                            $registryTotal++
                            $regstate = $null

                            if (Test-Path $tweak.Path) {
                                $regstate = Get-ItemProperty -Name $tweak.Name -Path $tweak.Path -ErrorAction SilentlyContinue | Select-Object -ExpandProperty $($tweak.Name)
                            }

                            if ($null -eq $regstate) {
                                switch ($tweak.DefaultState) {
                                    "true" {
                                        $regstate = $tweak.Value
                                    }
                                    "false" {
                                        $regstate = $tweak.OriginalValue
                                    }
                                    default {
                                        $regstate = $tweak.OriginalValue
                                    }
                                }
                            }

                            if ($regstate -eq $tweak.Value) {
                                $registryMatchCount++
                            }
                        }
                    }

                    if ($registryTotal -gt 0 -and $registryMatchCount -ne $registryTotal) {
                        $values += $False
                    }
                }

                Foreach ($tweaks in $serviceKeys) {
                    Foreach ($tweak in $tweaks) {
                        $Service = Get-Service -Name $tweak.Name

                        if ($Service) {
                            $actualValue = $Service.StartType
                            $expectedValue = $tweak.StartupType
                            if ($expectedValue -ne $actualValue) {
                                $values += $False
                            }
                        }
                    }
                }

                if ($values -notcontains $false) {
                    Write-Output $Config
                }
            }
        }
    }
}

function Invoke-WinUtilExplorerUpdate {
     <#
    .SYNOPSIS
        Refreshes the Windows Explorer
    #>
    param (
        [string]$action = "refresh"
    )

    if ($action -eq "refresh") {
        Invoke-WPFRunspace -ScriptBlock {
            # Define the Win32 type only if it doesn't exist
            if (-not ([System.Management.Automation.PSTypeName]'Win32').Type) {
                Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = false)]
    public static extern IntPtr SendMessageTimeout(
        IntPtr hWnd, uint Msg, IntPtr wParam, string lParam,
        uint fuFlags, uint uTimeout, out IntPtr lpdwResult);
}
"@
            }

            $HWND_BROADCAST = [IntPtr]0xffff
            $WM_SETTINGCHANGE = 0x1A
            $SMTO_ABORTIFHUNG = 0x2

            [Win32]::SendMessageTimeout($HWND_BROADCAST, $WM_SETTINGCHANGE,
                [IntPtr]::Zero, "ImmersiveColorSet", $SMTO_ABORTIFHUNG, 100,
                [ref]([IntPtr]::Zero))
        }
    } elseif ($action -eq "restart") {
        taskkill.exe /F /IM "explorer.exe"
        Start-Process "explorer.exe"
    }
}

function Invoke-WinUtilFeatureInstall ($CheckBox) {
    Write-WinUtilLog -Component "Feature" -Message "Applying feature action: $CheckBox"

    if ($sync.configs.feature.$CheckBox.feature) {
        foreach ($feature in $sync.configs.feature.$CheckBox.feature) {
            Write-Host "Installing $feature"
            Write-WinUtilLog -Component "Feature" -Message "Enabling Windows optional feature: $feature"
            Enable-WindowsOptionalFeature -Online -FeatureName $feature -All -NoRestart -ErrorAction Stop
            Write-WinUtilLog -Component "Feature" -Message "Enabled Windows optional feature: $feature"
        }
    }

    if ($sync.configs.feature.$CheckBox.InvokeScript) {
        foreach ($script in $sync.configs.feature.$CheckBox.InvokeScript) {
            Write-Host "Running Script for $CheckBox"
            Write-WinUtilLog -Component "Feature" -Message "Running feature script for: $CheckBox"
            Invoke-Command -ScriptBlock ([scriptblock]::Create($script)) -ErrorAction Stop
            Write-WinUtilLog -Component "Feature" -Message "Completed feature script for: $CheckBox"
        }
    }
    Write-WinUtilLog -Component "Feature" -Message "Feature action completed: $CheckBox"
}

function Invoke-WinUtilFontScaling {
    <#

    .SYNOPSIS
        Applies UI and font scaling for accessibility

    .PARAMETER ScaleFactor
        Sets the scaling from 0.75 and 2.0.
        Default is 1.0 (100% - no scaling)

    .EXAMPLE
        Invoke-WinUtilFontScaling -ScaleFactor 1.25
        # Applies 125% scaling
    #>

    param (
        [double]$ScaleFactor = 1.0
    )

    # Validate if scale factor is within the range
    if ($ScaleFactor -lt 0.75 -or $ScaleFactor -gt 2.0) {
        Write-Warning "Scale factor must be between 0.75 and 2.0. Using 1.0 instead."
        $ScaleFactor = 1.0
    }

    # Define an array for resources to be scaled
    $fontResources = @(
        # Fonts
        "FontSize",
        "ButtonFontSize",
        "HeaderFontSize",
        "TabButtonFontSize",
        "ConfigTabButtonFontSize",
        "IconFontSize",
        "SettingsIconFontSize",
        "CloseIconFontSize",
        "AppEntryFontSize",
        "SearchBarTextBoxFontSize",
        "SearchBarClearButtonFontSize",
        "CustomDialogFontSize",
        "CustomDialogFontSizeHeader",
        "ConfigUpdateButtonFontSize",
        # Buttons and UI
        "CheckBoxBulletDecoratorSize",
        "ButtonWidth",
        "ButtonHeight",
        "TabButtonWidth",
        "TabButtonHeight",
        "IconButtonSize",
        "AppEntryWidth",
        "SearchBarWidth",
        "SearchBarHeight",
        "CustomDialogWidth",
        "CustomDialogHeight",
        "CustomDialogLogoSize",
        "ToolTipWidth",
        "DashboardTitleFontSize",
        "DashboardValueFontSize"
    )

    # Apply scaling to each resource
    foreach ($resourceName in $fontResources) {
        try {
            # Get the default font size from the theme configuration
            $originalValue = $sync.configs.themes.shared.$resourceName
            if ($originalValue) {
                # Convert string to double since values are stored as strings
                $originalValue = [double]$originalValue
                # Calculates and applies the new font size
                $newValue = [math]::Round($originalValue * $ScaleFactor, 1)
                $sync.Form.Resources[$resourceName] = $newValue
            }
        }
        catch {
            Write-Warning "Failed to scale resource $resourceName : $_"
        }
    }

    # Store the scale factor so it can be reapplied after theme changes
    $sync.FontScaleFactor = $ScaleFactor

    # Update the font scaling percentage displayed on the UI
    if ($sync.FontScalingValue) {
        $percentage = [math]::Round($ScaleFactor * 100)
        $sync.FontScalingValue.Text = "$percentage%"
    }
}

function Invoke-WinUtilScript {
    <#

    .SYNOPSIS
        Invokes the provided scriptblock. Intended for things that can't be handled with the other functions.

    .PARAMETER Name
        The name of the scriptblock being invoked

    .PARAMETER scriptblock
        The scriptblock to be invoked

    .EXAMPLE
        $Scriptblock = [scriptblock]::Create({"Write-output 'Hello World'"})
        Invoke-WinUtilScript -ScriptBlock $scriptblock -Name "Hello World"

    #>
    param (
        $Name,
        [scriptblock]$scriptblock
    )

    try {
        Write-Host "Running Script for $Name"
        Write-WinUtilLog -Component "Script" -Message "Running script for $Name"
        Invoke-Command $scriptblock -ErrorAction Stop
        Write-WinUtilLog -Component "Script" -Message "Completed script for $Name"
    } catch [System.Management.Automation.CommandNotFoundException] {
        Write-Warning "The specified command was not found."
        Write-Warning $PSItem.Exception.message
        Write-WinUtilLog -Level "ERROR" -Component "Script" -Message "Command not found while running script for $Name`: $($PSItem.Exception.Message)"
    } catch [System.Management.Automation.RuntimeException] {
        Write-Warning "A runtime exception occurred."
        Write-Warning $PSItem.Exception.message
        Write-WinUtilLog -Level "ERROR" -Component "Script" -Message "Runtime exception while running script for $Name`: $($PSItem.Exception.Message)"
    } catch [System.Security.SecurityException] {
        Write-Warning "A security exception occurred."
        Write-Warning $PSItem.Exception.message
        Write-WinUtilLog -Level "ERROR" -Component "Script" -Message "Security exception while running script for $Name`: $($PSItem.Exception.Message)"
    } catch [System.UnauthorizedAccessException] {
        Write-Warning "Access denied. You do not have permission to perform this operation."
        Write-Warning $PSItem.Exception.message
        Write-WinUtilLog -Level "ERROR" -Component "Script" -Message "Access denied while running script for $Name`: $($PSItem.Exception.Message)"
    } catch {
        # Generic catch block to handle any other type of exception
        Write-Warning "Unable to run script for $Name due to unhandled exception."
        # StackTrace is often null here, and a null Write-Warning threw a second error.
        Write-Warning $psitem.Exception.Message
        Write-WinUtilLog -Level "ERROR" -Component "Script" -Message "Unhandled exception while running script for $Name`: $($psitem.Exception.Message)"
    }

}

function Invoke-WinutilThemeChange {
    <#
    .SYNOPSIS
        Toggles between light and dark themes for a Windows utility application.

    .DESCRIPTION
        This function toggles the theme of the user interface between 'Light' and 'Dark' modes,
        modifying various UI elements such as colors, margins, corner radii, font families, etc.
        If the '-init' switch is used, it initializes the theme based on the system's current dark mode setting.
        In Azor WinUtil, 'Dark' is the Goku Black Rosé theme and 'Light' is the Rosé light theme.

    .EXAMPLE
        Invoke-WinutilThemeChange
        # Toggles the theme between 'Light' and 'Dark'.


    #>
    param (
        [string]$theme = "Auto"
    )

    function Set-WinutilTheme {
        <#
        .SYNOPSIS
            Applies the specified theme to the application's user interface.

        .DESCRIPTION
            This internal function applies the given theme by setting the relevant properties
            like colors, font families, corner radii, etc., in the UI. It uses the
            'Set-ThemeResourceProperty' helper function to modify the application's resources.

        .PARAMETER currentTheme
            The name of the theme to be applied. Common values are "Light", "Dark", or "shared".
        #>
        param (
            [string]$currentTheme
        )

        function Set-ThemeResourceProperty {
            <#
            .SYNOPSIS
                Sets a specific UI property in the application's resources.

            .DESCRIPTION
                This helper function sets a property (e.g., color, margin, corner radius) in the
                application's resources, based on the provided type and value. It includes
                error handling to manage potential issues while setting a property.

            .PARAMETER Name
                The name of the resource property to modify (e.g., "MainBackgroundColor", "ButtonBackgroundMouseoverColor").

            .PARAMETER Value
                The value to assign to the resource property (e.g., "#FFFFFF" for a color).

            .PARAMETER Type
                The type of the resource, such as "ColorBrush", "CornerRadius", "GridLength", or "FontFamily".
            #>
            param($Name, $Value, $Type)
            try {
                # Set the resource property based on its type
                $sync.Form.Resources[$Name] = switch ($Type) {
                    "ColorBrush" { [Windows.Media.SolidColorBrush]::new($Value) }
                    "Color" {
                        # Convert hex string to RGB values
                        $hexColor = $Value.TrimStart("#")
                        $r = [Convert]::ToInt32($hexColor.Substring(0,2), 16)
                        $g = [Convert]::ToInt32($hexColor.Substring(2,2), 16)
                        $b = [Convert]::ToInt32($hexColor.Substring(4,2), 16)
                        [Windows.Media.Color]::FromRgb($r, $g, $b)
                    }
                    "CornerRadius" { [System.Windows.CornerRadius]::new($Value) }
                    "GridLength" { [System.Windows.GridLength]::new($Value) }
                    "Thickness" {
                        # Parse the Thickness value (supports 1, 2, or 4 inputs)
                        $values = $Value -split ","
                        switch ($values.Count) {
                            1 { [System.Windows.Thickness]::new([double]$values[0]) }
                            2 { [System.Windows.Thickness]::new([double]$values[0], [double]$values[1]) }
                            4 { [System.Windows.Thickness]::new([double]$values[0], [double]$values[1], [double]$values[2], [double]$values[3]) }
                        }
                    }
                    "FontFamily" { [Windows.Media.FontFamily]::new($Value) }
                    "Double" { [double]$Value }
                    default { $Value }
                }
            }
            catch {
                # Log a warning if there's an issue setting the property
                Write-Warning "Failed to set property $($Name): $_"
            }
        }

        # Retrieve all theme properties from the theme configuration
        $themeProperties = $sync.configs.themes.$currentTheme.PSObject.Properties
        foreach ($themeProperty in $themeProperties) {
            # Apply properties that deal with colors
            if ($themeProperty.Name -like "*color*") {
                Set-ThemeResourceProperty -Name $themeProperty.Name -Value $themeProperty.Value -Type "ColorBrush"
                # Every hex color also gets a C-prefixed <Color> resource (e.g. AccentColor -> CAccentColor).
                # GradientStop and DropShadowEffect require a <Color> and not a <SolidColorBrush> object
                if ([string]$themeProperty.Value -match '^#[0-9A-Fa-f]{6}$') {
                    Set-ThemeResourceProperty -Name "C$($themeProperty.Name)" -Value $themeProperty.Value -Type "Color"
                }
            }
            # Apply corner radius properties
            elseif ($themeProperty.Name -like "*Radius*") {
                Set-ThemeResourceProperty -Name $themeProperty.Name -Value $themeProperty.Value -Type "CornerRadius"
            }
            # Apply row height properties
            elseif ($themeProperty.Name -like "*RowHeight*") {
                Set-ThemeResourceProperty -Name $themeProperty.Name -Value $themeProperty.Value -Type "GridLength"
            }
            # Apply thickness or margin properties
            elseif (($themeProperty.Name -like "*Thickness*") -or ($themeProperty.Name -like "*margin")) {
                Set-ThemeResourceProperty -Name $themeProperty.Name -Value $themeProperty.Value -Type "Thickness"
            }
            # Apply font family properties
            elseif ($themeProperty.Name -like "*FontFamily*") {
                Set-ThemeResourceProperty -Name $themeProperty.Name -Value $themeProperty.Value -Type "FontFamily"
            }
            # Apply any other properties as doubles (numerical values)
            else {
                Set-ThemeResourceProperty -Name $themeProperty.Name -Value $themeProperty.Value -Type "Double"
            }
        }
    }

    $sync.preferences.theme = $theme
    Set-WinutilTheme -currentTheme "shared"

    switch ($sync.preferences.theme) {
        "Auto" {
            $systemUsesDarkMode = Get-WinUtilToggleStatus WPFToggleDarkMode
            if ($systemUsesDarkMode) {
                $theme = "Dark"
            }
            else{
                $theme = "Light"
            }

            Set-WinutilTheme -currentTheme $theme
            $themeButtonIcon = [char]0xF08C
        }
        "Dark" {
            Set-WinutilTheme -currentTheme $sync.preferences.theme
            $themeButtonIcon = [char]0xE708
           }
        "Light" {
            Set-WinutilTheme -currentTheme $sync.preferences.theme
            $themeButtonIcon = [char]0xE706
        }
    }

    # Reapply font scaling if it was previously set (theme change resets shared resources)
    if ($sync.ContainsKey("FontScaleFactor") -and $sync.FontScaleFactor -ne 1.0) {
        Invoke-WinUtilFontScaling -ScaleFactor $sync.FontScaleFactor
    }

    # Update the theme selector button with the appropriate icon
    $ThemeButton = $sync.Form.FindName("ThemeButton")
    $ThemeButton.Content = [string]$themeButtonIcon
}

function Invoke-WinUtilTweaks {
    <#

    .SYNOPSIS
        Invokes the function associated with each provided checkbox

    .PARAMETER CheckBox
        The checkbox to invoke

    .PARAMETER undo
        Indicates whether to undo the operation contained in the checkbox

    .PARAMETER KeepServiceStartup
        Indicates whether to override the startup of a service with the one given from WinUtil,
        or to keep the startup of said service, if it was changed by the user, or another program, from its default value.
    #>

    param(
        $CheckBox,
        $undo = $false,
        $KeepServiceStartup = $true
    )

    $action = if ($undo) { "Undo" } else { "Apply" }
    Write-WinUtilLog -Component "Tweaks" -Message "$action tweak: $CheckBox"

    if ($undo) {
        $Values = @{
            Registry = "OriginalValue"
            Service = "OriginalType"
            ScriptType = "UndoScript"
        }

    } else {
        $Values = @{
            Registry = "Value"
            Service = "StartupType"
            OriginalService = "OriginalType"
            ScriptType = "InvokeScript"
        }
    }
    if ($sync.configs.tweaks.$CheckBox.service) {
        $sync.configs.tweaks.$CheckBox.service | ForEach-Object {
            $changeservice = $true

        # The check for !($undo) is required, without it the script will throw an error for accessing unavailable member, which's the 'OriginalService' Property
            if ($KeepServiceStartup -AND !($undo)) {
                try {
                    # Check if the service exists
                    $service = Get-Service -Name $psitem.Name -ErrorAction Stop
                    if(!($service.StartType.ToString() -eq $psitem.$($values.OriginalService))) {
                        $changeservice = $false
                    }
                } catch [System.ServiceProcess.ServiceNotFoundException] {
                    Write-Warning "Service $($psitem.Name) was not found."
                }
            }

            if ($changeservice) {
                Set-WinUtilService -Name $psitem.Name -StartupType $psitem.$($values.Service)
            }
        }
    }
    if ($sync.configs.tweaks.$CheckBox.registry) {
        $sync.configs.tweaks.$CheckBox.registry | Where-Object { -not $psitem.Values } | ForEach-Object {
            Set-WinUtilRegistry -Name $psitem.Name -Path $psitem.Path -Type $psitem.Type -Value $psitem.$($values.registry)
        }
    }
    if ($sync.configs.tweaks.$CheckBox.$($values.ScriptType)) {
        $sync.configs.tweaks.$CheckBox.$($values.ScriptType) | ForEach-Object {
            $Scriptblock = [scriptblock]::Create($psitem)
            Invoke-WinUtilScript -ScriptBlock $scriptblock -Name $CheckBox
        }
    }

    if (!$undo) {
        if($sync.configs.tweaks.$CheckBox.appx) {
            $sync.configs.tweaks.$CheckBox.appx | ForEach-Object {
                Remove-WinUtilAPPX -Name $psitem
            }
            Remove-WinUtilProvisionedAPPX -PackageList $sync.configs.tweaks.$CheckBox.appx
        }
    }
    Write-WinUtilLog -Component "Tweaks" -Message "$action tweak completed: $CheckBox"

    # Azor Companion: conta ao AzorOptimization o que o WinUtil acabou de mexer.
    if (Get-Command Write-AzorWinUtilState -ErrorAction SilentlyContinue) {
        if ($undo) { Write-AzorWinUtilState -LastAction "Desfez tweak: $CheckBox" }
        else { Write-AzorWinUtilState -LastAction "Aplicou tweak: $CheckBox" -AppliedTweaks @([string]$CheckBox) }
    }
}

function Measure-WinUtilCleanupItem {
    <#
    .SYNOPSIS
        Returns the total size in bytes of the files and folders passed in.

    .DESCRIPTION
        Folders are measured recursively. Junctions and symbolic links are not followed, because deleting a
        folder removes the link and never the files it points to, so counting them would promise space that
        the cleanup doesn't free.

    .PARAMETER Item
        File and folder objects, for example from Get-WinUtilCleanupItem.
    #>
    param(
        [object[]]$Item = @()
    )

    $total = 0.0
    foreach ($entry in $Item) {
        if ($null -eq $entry) {
            continue
        }

        if (-not $entry.PSIsContainer) {
            if ($entry.Length) {
                $total += [double]$entry.Length
            }
            continue
        }

        if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            continue
        }

        $folders = New-Object System.Collections.Generic.Stack[string]
        $folders.Push($entry.FullName)
        while ($folders.Count -gt 0) {
            try {
                $children = ([IO.DirectoryInfo]::new($folders.Pop())).GetFileSystemInfos()
            } catch {
                # A folder the current user can't read is skipped, like Get-ChildItem -ErrorAction SilentlyContinue.
                continue
            }

            foreach ($child in $children) {
                if ($child.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                    continue
                }

                if ($child.Attributes -band [IO.FileAttributes]::Directory) {
                    $folders.Push($child.FullName)
                } else {
                    $total += [double]$child.Length
                }
            }
        }
    }

    return $total
}

function New-WinUtilCheckupWindow {
    <#
    .SYNOPSIS
        Builds, without showing it, the Checkup para Jogos window for a Get-WinUtilGameCompatReport result.

    .DESCRIPTION
        The window lists what needs attention first, each item with its status, what it affects and how it is
        fixed, then the checks that are OK in one compact block. The list scrolls and the window never grows
        taller than the work area, so the buttons stay on screen on small displays such as 1280x720. When the
        user clicks the fix button, the window's Tag becomes "Fix" before it closes. Uses the main window's
        resources when it exists, so the dialog follows the current theme.

    .PARAMETER Report
        The objects returned by Get-WinUtilGameCompatReport.
    #>
    param(
        [object[]]$Report = @()
    )

    $view = Get-WinUtilCheckupView -Report $Report
    $brushConverter = New-Object Windows.Media.BrushConverter
    $themeResources = if ($sync.Form) { $sync.Form.Resources } else { $null }
    $resolveBrush = {
        param([string]$Key, [string]$Fallback)
        if ($themeResources -and $themeResources.Contains($Key)) {
            return $themeResources[$Key]
        }
        return $brushConverter.ConvertFromString($Fallback)
    }

    $cardBrush = & $resolveBrush "CardBackgroundColor" "#140D12"
    $itemBrush = & $resolveBrush "InputBackgroundColor" "#100A0E"
    $borderBrush = & $resolveBrush "BorderColor" "#33202D"
    $accentBrush = & $resolveBrush "AccentColor" "#FF4DA6"
    $textBrush = & $resolveBrush "MainForegroundColor" "#F7E9F1"
    $mutedBrush = & $resolveBrush "MutedForegroundColor" "#B394A8"
    $successBrush = & $resolveBrush "SuccessColor" "#3DDC97"
    $warningBrush = & $resolveBrush "WarningColor" "#FF4D6D"

    $window = New-Object Windows.Window
    $window.Title = "Azor WinUtil - Checkup para Jogos"
    $window.Width = 640
    $window.SizeToContent = [Windows.SizeToContent]::Height
    $window.MaxHeight = [Math]::Max(360, [Windows.SystemParameters]::WorkArea.Height - 40)
    $window.WindowStyle = [Windows.WindowStyle]::None
    $window.AllowsTransparency = $true
    $window.Background = [Windows.Media.Brushes]::Transparent
    $window.ResizeMode = [Windows.ResizeMode]::NoResize
    $window.ShowInTaskbar = $false
    $window.WindowStartupLocation = [Windows.WindowStartupLocation]::CenterScreen
    $window.Foreground = $textBrush
    if ($themeResources) {
        # Share the main window resources so buttons and scroll bars use the Azor styles
        foreach ($resourceKey in @($themeResources.Keys)) {
            $window.Resources[$resourceKey] = $themeResources[$resourceKey]
        }
        if ($themeResources.Contains("FontFamily")) {
            $window.FontFamily = $themeResources["FontFamily"]
        }
        if ($sync.Form.IsVisible) {
            $window.Owner = $sync.Form
            $window.WindowStartupLocation = [Windows.WindowStartupLocation]::CenterOwner
        }
    }

    # The glow is a separate layer, so the text on the card is not rendered through the effect
    $glow = New-Object Windows.Controls.Border
    $glow.CornerRadius = New-Object Windows.CornerRadius(14)
    $glow.Background = $cardBrush
    $glow.Margin = New-Object Windows.Thickness(12)
    $dropShadow = New-Object Windows.Media.Effects.DropShadowEffect
    $dropShadow.Color = if ($themeResources -and $themeResources.Contains("CAccentColor")) { $themeResources["CAccentColor"] } else { [Windows.Media.Colors]::HotPink }
    $dropShadow.ShadowDepth = 0
    $dropShadow.BlurRadius = 18
    $dropShadow.Opacity = 0.55
    $glow.Effect = $dropShadow

    $card = New-Object Windows.Controls.Border
    $card.CornerRadius = New-Object Windows.CornerRadius(14)
    $card.Background = $cardBrush
    $card.BorderBrush = $accentBrush
    $card.BorderThickness = New-Object Windows.Thickness(1)
    $card.Margin = New-Object Windows.Thickness(12)

    $layers = New-Object Windows.Controls.Grid
    [void]$layers.Children.Add($glow)
    [void]$layers.Children.Add($card)
    $window.Content = $layers

    $grid = New-Object Windows.Controls.Grid
    foreach ($rowHeight in @("Auto", "Auto", "Star", "Auto")) {
        $row = New-Object Windows.Controls.RowDefinition
        $row.Height = if ($rowHeight -eq "Star") { [Windows.GridLength]::new(1, [Windows.GridUnitType]::Star) } else { [Windows.GridLength]::Auto }
        $grid.RowDefinitions.Add($row)
    }
    $card.Child = $grid

    # Header; dragging it moves the window
    $header = New-Object Windows.Controls.StackPanel
    $header.Orientation = [Windows.Controls.Orientation]::Horizontal
    $header.Margin = New-Object Windows.Thickness(18, 14, 18, 2)
    $header.Background = [Windows.Media.Brushes]::Transparent
    $header.Cursor = [Windows.Input.Cursors]::SizeAll
    $header.Add_MouseLeftButtonDown({
        param($eventSender, $eventArgs)
        $null = $eventArgs
        [Windows.Window]::GetWindow($eventSender).DragMove()
    })
    if (Get-Command -Name Invoke-WinUtilAssets -ErrorAction SilentlyContinue) {
        [void]$header.Children.Add((Invoke-WinUtilAssets -Type "logo" -Size 30))
    }
    $titleStack = New-Object Windows.Controls.StackPanel
    $titleStack.Margin = New-Object Windows.Thickness(10, 0, 0, 0)
    $titleStack.VerticalAlignment = [Windows.VerticalAlignment]::Center
    $titleText = New-Object Windows.Controls.TextBlock
    $titleText.Text = "Checkup para Jogos"
    $titleText.FontSize = 17
    $titleText.Foreground = if ($themeResources -and $themeResources.Contains("AzorRoseGradientBrush")) { $themeResources["AzorRoseGradientBrush"] } else { $accentBrush }
    if ($themeResources -and $themeResources.Contains("HeaderFontFamily")) {
        $titleText.FontFamily = $themeResources["HeaderFontFamily"]
    }
    $subtitleText = New-Object Windows.Controls.TextBlock
    $subtitleText.Text = "Anti-cheat de Valorant, LoL, Fortnite, CS2 e CoD Warzone, monitor, driver e Windows"
    $subtitleText.FontSize = 11
    $subtitleText.Foreground = $mutedBrush
    [void]$titleStack.Children.Add($titleText)
    [void]$titleStack.Children.Add($subtitleText)
    [void]$header.Children.Add($titleStack)
    [void]$grid.Children.Add($header)
    [Windows.Controls.Grid]::SetRow($header, 0)

    $summaryText = New-Object Windows.Controls.TextBlock
    $summaryText.Text = $view.Summary
    $summaryText.FontSize = 12
    $summaryText.FontWeight = [Windows.FontWeights]::SemiBold
    $summaryText.Foreground = if ($view.Issues.Count -eq 0) { $successBrush } else { $textBrush }
    $summaryText.Margin = New-Object Windows.Thickness(18, 8, 18, 8)
    [void]$grid.Children.Add($summaryText)
    [Windows.Controls.Grid]::SetRow($summaryText, 1)

    $list = New-Object Windows.Controls.StackPanel
    $list.Margin = New-Object Windows.Thickness(18, 0, 14, 0)
    foreach ($issue in $view.Issues) {
        $statusBrush = if ($issue.Status -eq "FALHA") { $warningBrush } else { $accentBrush }

        $item = New-Object Windows.Controls.Border
        $item.CornerRadius = New-Object Windows.CornerRadius(10)
        $item.BorderThickness = New-Object Windows.Thickness(1)
        $item.BorderBrush = $borderBrush
        $item.Background = $itemBrush
        $item.Padding = New-Object Windows.Thickness(12, 10, 12, 10)
        $item.Margin = New-Object Windows.Thickness(0, 0, 0, 8)

        $itemGrid = New-Object Windows.Controls.Grid
        $pillColumn = New-Object Windows.Controls.ColumnDefinition
        $pillColumn.Width = [Windows.GridLength]::Auto
        $textColumn = New-Object Windows.Controls.ColumnDefinition
        $textColumn.Width = [Windows.GridLength]::new(1, [Windows.GridUnitType]::Star)
        $itemGrid.ColumnDefinitions.Add($pillColumn)
        $itemGrid.ColumnDefinitions.Add($textColumn)

        $pill = New-Object Windows.Controls.Border
        $pill.CornerRadius = New-Object Windows.CornerRadius(9)
        $pill.BorderThickness = New-Object Windows.Thickness(1)
        $pill.BorderBrush = $statusBrush
        $pill.Padding = New-Object Windows.Thickness(8, 1, 8, 2)
        $pill.Margin = New-Object Windows.Thickness(0, 1, 12, 0)
        $pill.VerticalAlignment = [Windows.VerticalAlignment]::Top
        $pillText = New-Object Windows.Controls.TextBlock
        $pillText.Text = $issue.Status
        $pillText.FontSize = 10
        $pillText.FontWeight = [Windows.FontWeights]::Bold
        $pillText.Foreground = $statusBrush
        $pill.Child = $pillText
        [void]$itemGrid.Children.Add($pill)

        $texts = New-Object Windows.Controls.StackPanel
        [Windows.Controls.Grid]::SetColumn($texts, 1)
        $lines = @(
            @{ Text = $issue.Name; Size = 13; Weight = "SemiBold"; Brush = $textBrush; Top = 0 }
            @{ Text = $issue.Detail; Size = 12; Weight = "Normal"; Brush = $textBrush; Top = 3 }
            @{ Text = "Afeta: $($issue.Games)"; Size = 11; Weight = "Normal"; Brush = $mutedBrush; Top = 5 }
        )
        foreach ($line in $lines) {
            $lineText = New-Object Windows.Controls.TextBlock
            $lineText.Text = $line.Text
            $lineText.FontSize = $line.Size
            $lineText.FontWeight = [Windows.FontWeights]::($line.Weight)
            $lineText.Foreground = $line.Brush
            $lineText.TextWrapping = [Windows.TextWrapping]::Wrap
            $lineText.Margin = New-Object Windows.Thickness(0, $line.Top, 0, 0)
            [void]$texts.Children.Add($lineText)
        }
        if ($issue.Fix) {
            $fixText = New-Object Windows.Controls.TextBlock
            $fixText.FontSize = 11
            $fixText.TextWrapping = [Windows.TextWrapping]::Wrap
            $fixText.Margin = New-Object Windows.Thickness(0, 2, 0, 0)
            $fixLead = New-Object Windows.Documents.Run(($(if ($issue.CanFix) { "Corrijo aqui: " } else { "Com você: " })))
            $fixLead.FontWeight = [Windows.FontWeights]::SemiBold
            $fixLead.Foreground = if ($issue.CanFix) { $accentBrush } else { $textBrush }
            $fixBody = New-Object Windows.Documents.Run($issue.Fix)
            $fixBody.Foreground = $mutedBrush
            [void]$fixText.Inlines.Add($fixLead)
            [void]$fixText.Inlines.Add($fixBody)
            [void]$texts.Children.Add($fixText)
        }
        [void]$itemGrid.Children.Add($texts)

        $item.Child = $itemGrid
        [void]$list.Children.Add($item)
    }

    if ($view.Ok.Count -gt 0) {
        $okHeader = New-Object Windows.Controls.TextBlock
        $okHeader.Text = "Em ordem ($($view.Ok.Count))"
        $okHeader.FontSize = 12
        $okHeader.FontWeight = [Windows.FontWeights]::SemiBold
        $okHeader.Foreground = $successBrush
        $okHeader.Margin = New-Object Windows.Thickness(2, 4, 0, 3)
        [void]$list.Children.Add($okHeader)

        $okNames = New-Object Windows.Controls.TextBlock
        $okNames.Text = ($view.Ok | ForEach-Object { $_.Name }) -join "  •  "
        $okNames.FontSize = 12
        $okNames.Foreground = $mutedBrush
        $okNames.TextWrapping = [Windows.TextWrapping]::Wrap
        $okNames.Margin = New-Object Windows.Thickness(2, 0, 0, 6)
        [void]$list.Children.Add($okNames)
    }

    $scroll = New-Object Windows.Controls.ScrollViewer
    $scroll.VerticalScrollBarVisibility = [Windows.Controls.ScrollBarVisibility]::Auto
    $scroll.HorizontalScrollBarVisibility = [Windows.Controls.ScrollBarVisibility]::Disabled
    $scroll.Content = $list
    [void]$grid.Children.Add($scroll)
    [Windows.Controls.Grid]::SetRow($scroll, 2)

    $footer = New-Object Windows.Controls.Grid
    $footer.Margin = New-Object Windows.Thickness(18, 10, 18, 16)
    $noteColumn = New-Object Windows.Controls.ColumnDefinition
    $noteColumn.Width = [Windows.GridLength]::new(1, [Windows.GridUnitType]::Star)
    $buttonColumn = New-Object Windows.Controls.ColumnDefinition
    $buttonColumn.Width = [Windows.GridLength]::Auto
    $footer.ColumnDefinitions.Add($noteColumn)
    $footer.ColumnDefinitions.Add($buttonColumn)

    if ($view.FirmwareNote) {
        $noteText = New-Object Windows.Controls.TextBlock
        $noteText.Text = $view.FirmwareNote
        $noteText.FontSize = 11
        $noteText.Foreground = $mutedBrush
        $noteText.TextWrapping = [Windows.TextWrapping]::Wrap
        $noteText.VerticalAlignment = [Windows.VerticalAlignment]::Center
        $noteText.Margin = New-Object Windows.Thickness(0, 0, 12, 0)
        [void]$footer.Children.Add($noteText)
    }

    $buttons = New-Object Windows.Controls.StackPanel
    $buttons.Orientation = [Windows.Controls.Orientation]::Horizontal
    $buttons.VerticalAlignment = [Windows.VerticalAlignment]::Center
    [Windows.Controls.Grid]::SetColumn($buttons, 1)
    $hasAccentStyle = $window.Resources.Contains("AccentButtonStyle")

    if ($view.Fixable.Count -gt 0) {
        $fixButton = New-Object Windows.Controls.Button
        $fixButton.Name = "CheckupFixButton"
        $fixButton.Content = $view.FixLabel
        $fixButton.Height = 34
        $fixButton.Padding = New-Object Windows.Thickness(18, 0, 18, 0)
        $fixButton.Margin = New-Object Windows.Thickness(0, 0, 8, 0)
        if ($hasAccentStyle) {
            $fixButton.Style = $window.Resources["AccentButtonStyle"]
        }
        $fixButton.Add_Click({
            param($eventSender, $eventArgs)
            $null = $eventArgs
            $owner = [Windows.Window]::GetWindow($eventSender)
            $owner.Tag = "Fix"
            $owner.Close()
        })
        [void]$buttons.Children.Add($fixButton)
    }

    $closeButton = New-Object Windows.Controls.Button
    $closeButton.Name = "CheckupCloseButton"
    $closeButton.Content = if ($view.Fixable.Count -gt 0) { "Fechar" } else { "OK" }
    $closeButton.Height = 34
    $closeButton.MinWidth = 96
    $closeButton.Padding = New-Object Windows.Thickness(18, 0, 18, 0)
    $closeButton.IsCancel = $true
    if ($view.Fixable.Count -eq 0 -and $hasAccentStyle) {
        $closeButton.Style = $window.Resources["AccentButtonStyle"]
    }
    $closeButton.Add_Click({
        param($eventSender, $eventArgs)
        $null = $eventArgs
        [Windows.Window]::GetWindow($eventSender).Close()
    })
    [void]$buttons.Children.Add($closeButton)
    [void]$footer.Children.Add($buttons)
    [void]$grid.Children.Add($footer)
    [Windows.Controls.Grid]::SetRow($footer, 3)

    return $window
}

function New-WinUtilFossBadge {
    <#
        .SYNOPSIS
            Creates the FOSS marker: the open source keyhole on a green backdrop
        .DESCRIPTION
            Returns a fresh element on every call, because a WPF element can only have one parent.
            The artwork is authored in a 22x22 box and scaled by the Viewbox, so callers only pick a size.
        .PARAMETER Size
            Edge length of the badge in pixels
        .PARAMETER Round
            Use a full circle instead of the corner triangle, for the legend rather than an app entry
    #>
    param(
        [double]$Size = 24,
        [switch]$Round
    )

    $artwork = New-Object Windows.Controls.Grid
    $artwork.Width = 22
    $artwork.Height = 22

    $backdrop = New-Object Windows.Shapes.Path
    $backdrop.Fill = [Windows.Media.SolidColorBrush]::new([Windows.Media.Color]::FromRgb(19, 143, 83))
    $keyhole = New-Object Windows.Shapes.Path
    $keyhole.Stroke = [Windows.Media.SolidColorBrush]::new([Windows.Media.Color]::FromRgb(247, 247, 247))

    if ($Round) {
        $backdrop.Data = [Windows.Media.EllipseGeometry]::new([Windows.Point]::new(11, 11), 11, 11)
        # Keyhole centred in the circle, which has room for a larger ring than the triangle does
        $keyhole.Data = [Windows.Media.Geometry]::Parse("M 7.673,15.751 A 5.8,5.8 0 1 1 14.327,15.751")
        $keyhole.StrokeThickness = 3.4
    } else {
        # Triangle filling the top right corner, its outer corner rounded to match AppEntryBorderStyle
        $backdrop.Data = [Windows.Media.Geometry]::Parse("M 0,0 L 17,0 A 5,5 0 0 1 22,5 L 22,22 Z")
        # Keyhole centred on the triangle's incentre (15.56, 6.44) so it keeps the same
        # 1.8 clearance from all three edges
        $keyhole.Data = [Windows.Media.Geometry]::Parse("M 13.61,9.225 A 3.4,3.4 0 1 1 17.51,9.225")
        $keyhole.StrokeThickness = 2.4
    }

    $keyhole.StrokeStartLineCap = [Windows.Media.PenLineCap]::Round
    $keyhole.StrokeEndLineCap = [Windows.Media.PenLineCap]::Round
    [void]$artwork.Children.Add($backdrop)
    [void]$artwork.Children.Add($keyhole)

    $badge = New-Object Windows.Controls.Viewbox
    $badge.Width = $Size
    $badge.Height = $Size
    $badge.Child = $artwork
    $badge.ToolTip = "Software livre e de código aberto (FOSS)"

    return $badge
}

function Read-AzorOptimization {
    <#
    .SYNOPSIS
        Returns what AZOR Optimization reports about this PC, or $null when it has never run here.

    .DESCRIPTION
        Older AZOR Optimization builds leave optimization.json in the companion folder. Current builds keep
        their state in %LocalAppData%\AzorOptimization\user\data instead, so when there is no companion note,
        the tasks it keeps applied become activeTweaks, which is what the startup message counts.
    #>
    try {
        if (Test-Path -LiteralPath $sync.azorOptStatePath) {
            return (Get-Content -LiteralPath $sync.azorOptStatePath -Raw -ErrorAction Stop | ConvertFrom-Json)
        }
    } catch { }

    try {
        $state = Get-WinUtilAzorOptimizationState
        if ($state) {
            return [pscustomobject]@{
                activeTweaks = @($state.Tasks | ForEach-Object { $_.Id })
                profile      = $state.Profile
                autoApply    = $state.AutoApply
            }
        }
    } catch { }
    return $null
}

function Remove-WinUtilAdobeHostsBlock {
    <#
    .SYNOPSIS
        Removes the Adobe URL block list from the hosts file and keeps every other entry.

    .DESCRIPTION
        Saves a copy of the file as hosts.azor-backup first. From the "#New Ver" line that starts the list, the
        0.0.0.0 entries, comments and blank lines are removed; any other entry after that line stays, and nothing
        before it changes. The DNS cache is flushed so the addresses resolve again right away. Returns the number
        of 0.0.0.0 entries removed; 0 means the list was not found and the file was not touched.

    .PARAMETER Path
        The hosts file to change.
    #>
    param(
        [string]$Path = (Join-Path $env:SystemRoot "System32\drivers\etc\hosts")
    )

    if ((Get-WinUtilAdobeHostsBlock -Path $Path) -eq 0) {
        return 0
    }

    $lines = @(Get-Content -LiteralPath $Path -Encoding Default -ErrorAction Stop)
    $markerIndex = -1
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -like "#New Ver*") {
            $markerIndex = $index
            break
        }
    }

    Copy-Item -LiteralPath $Path -Destination "$Path.azor-backup" -Force -ErrorAction Stop

    $kept = New-Object System.Collections.Generic.List[string]
    $removed = 0
    for ($index = 0; $index -lt $lines.Count; $index++) {
        $line = $lines[$index]
        if ($index -ge $markerIndex) {
            if ($line -match '^\s*0\.0\.0\.0\s+\S') {
                $removed++
                continue
            }
            if ($line -match '^\s*(#.*)?$') {
                continue
            }
        }
        $kept.Add($line)
    }

    [IO.File]::WriteAllLines($Path, $kept.ToArray(), [Text.Encoding]::Default)
    Clear-DnsClientCache -ErrorAction SilentlyContinue
    Write-WinUtilLog -Component "GameCompat" -Message "Removed $removed Adobe block list entries from $Path (copy saved as $Path.azor-backup)."

    return $removed
}

function Remove-WinUtilAPPX {
    <#

    .SYNOPSIS
        Removes all APPX packages that match the given name

    .PARAMETER Name
        The name of the APPX package to remove

    .EXAMPLE
        Remove-WinUtilAPPX -Name "Microsoft.Microsoft3DViewer"

    #>
    param (
        $Name
    )

    Write-Host "Removing $Name"
    Write-WinUtilLog -Component "AppX" -Message "Removing AppX package pattern: $Name"

    # We explicitly loop through packages instead of using the pipeline because PowerShell 7 pipeline binding
    # for Remove-AppxPackage fails silently, and Get-AppxPackage -AllUsers returns duplicate objects for each user profile.
    $pkgs = Get-AppxPackage "*$Name*" -AllUsers | Sort-Object -Property PackageFullName -Unique
    if ($null -ne $pkgs) {
        foreach ($pkg in $pkgs) {
            try {
                Remove-AppxPackage -Package $pkg.PackageFullName -AllUsers -ErrorAction Stop
            }
            catch {
                Write-WinUtilLog -Level "ERROR" -Component "AppX" -Message "Failed to remove AppX package $($pkg.PackageFullName): $($_.Exception.Message)"
            }
        }
    }

    Write-WinUtilLog -Component "AppX" -Message "AppX removal completed for package pattern: $Name"
}

function Remove-WinUtilProvisionedAPPX {
    <#

    .SYNOPSIS
        Removes all AppX provisioned packages that match the given names

    .PARAMETER PackageList
        An array of names of the APPX packages to remove

    .EXAMPLE
        Remove-WinUtilProvisionedAPPX -PackageList @("Microsoft.Microsoft3DViewer", "Microsoft.WindowsCalculator")

    #>
    param (
        [string[]]$PackageList
    )

    if ($null -eq $PackageList -or $PackageList.Count -eq 0) {
        return
    }

    Write-Host "`nRemoving provisioned packages..."
    Write-WinUtilLog -Component "AppX" -Message "Removing AppX provisioned packages: $($PackageList -join ', ')"

    # DISM cmdlets like Get-AppxProvisionedPackage often fail with "Class not registered" or hang in PowerShell 7.
    # We shell out to Windows PowerShell 5.1 (powershell.exe) to reliably remove the provisioned packages.
    $ps5Command = {
        $pkgs = $args
        $provisionedPackages = Get-AppxProvisionedPackage -Online -ErrorAction SilentlyContinue
        $failures = [System.Collections.Generic.List[string]]::new()

        foreach ($Package in $pkgs) {
            $provs = $provisionedPackages |
                Where-Object DisplayName -Like "*$Package*"

            if ($null -ne $provs) {
                foreach ($prov in $provs) {
                    try {
                        Remove-AppxProvisionedPackage -Online -PackageName $prov.PackageName -ErrorAction Stop | Out-Null
                    }
                    catch {
                        $failures.Add("Failed to remove provisioned AppX package $($prov.PackageName): $($_.Exception.Message)")
                    }
                }
            }
        }

        if ($failures.Count -gt 0) {
            throw ($failures -join [Environment]::NewLine)
        }
    }

    $removalOutput = powershell.exe -NoProfile -NonInteractive -Command $ps5Command -args $PackageList 2>&1
    if ($LASTEXITCODE -ne 0 -or $null -ne $removalOutput) {
        $failureDetails = ($removalOutput | Out-String).Trim()
        $errorMessage = "AppX provisioned package removal failed: $failureDetails"
        Write-WinUtilLog -Level "ERROR" -Component "AppX" -Message $errorMessage
        throw $errorMessage
    }

    Write-WinUtilLog -Component "AppX" -Message "AppX provisioned package removal completed."
}

function Repair-WinUtilGameCompat {
    <#
    .SYNOPSIS
        Fixes the software-side checks returned by Get-WinUtilGameCompatReport.

    .DESCRIPTION
        Handles only checks with CanFix set and returns one pt-BR line per check describing what was done.
        Registry and service changes go through Set-WinUtilRegistry and Set-WinUtilService, which log them.
        Firmware settings (TPM, Secure Boot) and VBS are never changed here.
    #>
    param(
        [Parameter(Mandatory)]
        [object[]]$Checks
    )

    foreach ($check in $Checks) {
        if (-not $check.CanFix) {
            continue
        }

        switch ($check.Id) {
            "Teredo" {
                # Xbox support's documented fix: DisabledComponents back to 0, then Teredo back to its default state.
                Set-WinUtilRegistry -Name "DisabledComponents" -Path "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters" -Type "DWord" -Value "0"
                netsh interface teredo set state default | Out-Null
                "Teredo: DisabledComponents voltou para 0 e o túnel voltou ao padrão do Windows."
            }
            "AntiCheatServices" {
                foreach ($service in @($check.Data)) {
                    Set-WinUtilService -Name $service.Name -StartupType $service.Target
                }
                "Anti-cheat: {0} voltaram para Manual." -f ((@($check.Data) | ForEach-Object { $_.Name }) -join ", ")
            }
            "XboxServices" {
                foreach ($service in @($check.Data)) {
                    Set-WinUtilService -Name $service.Name -StartupType $service.Target
                }
                "Rede Xbox: {0} voltaram ao tipo de inicialização padrão." -f ((@($check.Data) | ForEach-Object { $_.Name }) -join ", ")
            }
            "AzorLegacy" {
                $restored = New-Object System.Collections.Generic.List[string]
                foreach ($legacyValue in @($check.Data)) {
                    if ($legacyValue.Kind -eq "Hosts") {
                        try {
                            $removedEntries = Remove-WinUtilAdobeHostsBlock -Path $legacyValue.Path
                            $restored.Add("$($legacyValue.Label) ($removedEntries endereços removidos; cópia em hosts.azor-backup)")
                        } catch {
                            "Ajustes antigos do Azor: não foi possível mudar o arquivo hosts ($($_.Exception.Message))."
                        }
                    } else {
                        Set-WinUtilRegistry -Name $legacyValue.Name -Path $legacyValue.Path -Type $legacyValue.Type -Value $legacyValue.Default
                        $restored.Add($legacyValue.Label)
                    }
                }
                if ($restored.Count -gt 0) {
                    "Ajustes antigos do Azor: {0} voltaram ao padrão do Windows." -f ($restored -join ", ")
                }
            }
            "Mpo" {
                Set-WinUtilRegistry -Name "OverlayTestMode" -Path "HKLM:\SOFTWARE\Microsoft\Windows\Dwm" -Type "DWord" -Value "<RemoveEntry>"
                $disableOverlays = $null
                try {
                    $disableOverlays = (Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers" -Name "DisableOverlays" -ErrorAction SilentlyContinue).DisableOverlays
                } catch {
                    $disableOverlays = $null
                }
                if ($null -ne $disableOverlays) {
                    Set-WinUtilRegistry -Name "DisableOverlays" -Path "HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers" -Type "DWord" -Value "<RemoveEntry>"
                }
                "MPO: voltou ao padrão do Windows."
            }
            "GameBar" {
                Start-Process "ms-windows-store://pdp/?productid=9NZKPSTSNW4P"
                "Xbox Game Bar: abri a página dela na Microsoft Store; clique em Instalar."
            }
            "RefreshRate" {
                # A wrong rate can blank the screen, so the user picks it in Settings, which reverts if it isn't confirmed.
                Start-Process "ms-settings:display-advanced"
                "Taxa de atualização: abri Configurações > Sistema > Tela. Em Tela avançada, escolha a maior taxa em 'Escolher uma taxa de atualização'."
            }
            "GpuDriver" {
                foreach ($driverPage in @($check.Data)) {
                    Start-Process $driverPage
                }
                "Driver de vídeo: abri a página de drivers do fabricante. Baixe e instale o driver mais recente para a sua placa."
            }
            "BackgroundRecording" {
                Set-WinUtilRegistry -Name "HistoricalCaptureEnabled" -Path "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\GameDVR" -Type "DWord" -Value "0"
                "Gravação em segundo plano: desligada. Gravar clipes pela Game Bar (Win+Alt+R) continua funcionando."
            }
            "GameMode" {
                Set-WinUtilRegistry -Name "AllowAutoGameMode" -Path "HKCU:\Software\Microsoft\GameBar" -Type "DWord" -Value "1"
                Set-WinUtilRegistry -Name "AutoGameModeEnabled" -Path "HKCU:\Software\Microsoft\GameBar" -Type "DWord" -Value "1"
                "Modo de Jogo: ligado."
            }
            "DiskSpace" {
                "Espaço em disco: a Limpeza Rápida abre em seguida e pergunta antes de apagar cada item."
            }
        }
    }
}

function Reset-WPFCheckBoxes {
    <#

    .SYNOPSIS
        Set winutil checkboxs to match $sync.selected values.
        Should only need to be run if $sync.selected updated outside of UI (i.e. presets or import)

    .PARAMETER doToggles
        Whether or not to set UI toggles. WARNING: they will trigger if altered

    .PARAMETER checkboxfilterpattern
        The Pattern to use when filtering through CheckBoxes, defaults to "**"
        Used to make reset blazingly fast.
    #>

    param (
        [Parameter(position=0)]
        [bool]$doToggles = $false,

        [Parameter(position=1)]
        [string]$checkboxfilterpattern = "**"
    )
    $selectedSet = [System.Collections.Generic.HashSet[string]]::new([string[]]@($sync.selectedApps + $sync.selectedTweaks + $sync.selectedFeatures + $sync.selectedAppx), [StringComparer]::OrdinalIgnoreCase)

    foreach ($syncEntry in $sync.GetEnumerator()) {
        if ($syncEntry.Value -is [System.Windows.Controls.CheckBox] -and $syncEntry.Name -notlike "WPFToggle*" -and $syncEntry.Name -like $checkboxfilterpattern) {
            $checkboxName = $syncEntry.Key
            $sync.$checkboxName.IsChecked = $selectedSet.Contains($checkboxName)
        }
    }

    # Update Installs tab UI values
    $count = $sync.SelectedApps.Count
    $sync.WPFselectedAppsButton.Content = "Programas selecionados: $count"
    # On every change, remove all entries inside the Popup Menu. This is done, so we can keep the alphabetical order even if elements are selected in a random way
    $sync.selectedAppsstackPanel.Children.Clear()
    $sync.selectedApps | Foreach-Object { Add-SelectedAppsMenuItem -name $($sync.configs.applicationsHashtable.$_.Content) -key $_ }

    if($doToggles) {
        # Restore toggle switch states from imported config.
        # Only act on toggles that are explicitly listed in the import - toggles absent
        # from the export file were not part of the saved config and should keep whatever
        # state the live system already has (set during UI initialisation via Get-WinUtilToggleStatus).
        $importedToggles = [System.Collections.Generic.HashSet[string]]::new([string[]]@($sync.selectedToggles), [StringComparer]::OrdinalIgnoreCase)
        foreach ($toggle in $sync.GetEnumerator()) {
            if ($toggle.Key -like "WPFToggle*" -and $toggle.Value -is [System.Windows.Controls.CheckBox] -and $importedToggles.Contains($toggle.Key)) {
                $sync[$toggle.Key].IsChecked = $true
            }
            # Toggles not present in the import are intentionally left untouched;
            # their current UI state already reflects the real system state.
        }
    }
}

function Set-WinUtilAppCategoryFilter {
    <#
        .SYNOPSIS
            Applies the Install tab category filter and syncs the chip states to it

        .DESCRIPTION
            The selection lives in $sync.SelectedAppCategories. An empty selection means every
            category is shown, which is what the All chip represents. The category filter and the
            search box are independent: this only touches categories, and the current search text
            is reapplied on top.

        .PARAMETER Category
            The category to act on. An empty value clears the filter back to All.

        .PARAMETER Additive
            Toggles this category in or out of the current selection instead of replacing it.
            Bound to ctrl click.
    #>
    param(
        [Parameter(Mandatory = $false)]
        [string]$Category = "",

        [Parameter(Mandatory = $false)]
        [switch]$Additive
    )

    if ($null -eq $sync.SelectedAppCategories) {
        $sync.SelectedAppCategories = [System.Collections.Generic.List[string]]::new()
    }
    $selected = $sync.SelectedAppCategories

    if ([string]::IsNullOrWhiteSpace($Category)) {
        $selected.Clear()
    } elseif ($Additive) {
        if ($selected.Contains($Category)) {
            [void]$selected.Remove($Category)
        } else {
            $selected.Add($Category)
        }
    } elseif ($selected.Count -eq 1 -and $selected.Contains($Category)) {
        # Clicking the only active category again clears the filter
        $selected.Clear()
    } else {
        $selected.Clear()
        $selected.Add($Category)
    }

    Update-WinUtilAppCategoryChip
    Find-AppsByNameOrDescription -SearchString $sync.SearchBar.Text -Categories $selected.ToArray()
}

function Set-WinUtilDashboardCompatAlert {
    <#
    .SYNOPSIS
        Shows or hides the Checkup para Jogos alert on the Dashboard tab.

    .DESCRIPTION
        The alert lists the checks from Get-WinUtilGameCompatReport that the user can act on: every FALHA,
        and every other non-OK check that the app can fix. Checks that are only informative for specific game
        modes (for example VBS, or a TPM that could not be read) do not raise it. Touches WPF controls, so call
        it on the UI thread.

    .PARAMETER Report
        The objects returned by Get-WinUtilGameCompatReport.
    #>
    param(
        [object[]]$Report = @()
    )

    if ($null -eq $sync.WPFDashboardAlert) {
        return
    }

    $issues = @($Report | Where-Object { $null -ne $_ -and ($_.Status -eq "FALHA" -or ($_.Status -ne "OK" -and $_.CanFix)) })
    if ($issues.Count -eq 0) {
        $sync.WPFDashboardAlert.Visibility = "Collapsed"
        return
    }

    $sync.WPFDashboardAlertTitle.Text = if ($issues.Count -eq 1) {
        "1 item do Checkup para Jogos para revisar"
    } else {
        "$($issues.Count) itens do Checkup para Jogos para revisar"
    }
    $issueNames = ($issues | ForEach-Object { $_.Name }) -join "  •  "
    $sync.WPFDashboardAlertText.Text = $issueNames
    $sync.WPFDashboardAlertText.ToolTip = $issueNames
    $sync.WPFDashboardAlert.Visibility = "Visible"
}

function Set-WinUtilDashboardSnapshot {
    <#
    .SYNOPSIS
        Shows a snapshot from Get-WinUtilSystemSnapshot on the Dashboard tab.

    .DESCRIPTION
        Touches WPF controls, so call it on the UI thread (for example through Invoke-WPFUIThread).

    .PARAMETER Snapshot
        The object returned by Get-WinUtilSystemSnapshot.
    #>
    param(
        [Parameter(Mandatory)]
        $Snapshot
    )

    if ($null -eq $sync.WPFDashboardCpuDetail) {
        return
    }

    $sync.DashboardBootTime = $Snapshot.BootTime

    $sync.WPFDashboardCpuDetail.Text = $Snapshot.CpuName
    $sync.WPFDashboardCpuDetail.ToolTip = $Snapshot.CpuName
    $sync.WPFDashboardCpuCoresDetail.Text = if ($Snapshot.CpuCores -gt 0) {
        "$($Snapshot.CpuCores) núcleos  •  $($Snapshot.CpuThreads) threads"
    } else {
        ""
    }

    $sync.WPFDashboardOsValue.Text = $Snapshot.OsName
    $osDetails = @()
    if ($Snapshot.OsVersion) { $osDetails += "Versão $($Snapshot.OsVersion)" }
    if ($Snapshot.OsBuild) { $osDetails += "build $($Snapshot.OsBuild)" }
    $sync.WPFDashboardOsDetail.Text = $osDetails -join " • "

    $gpuNames = @($Snapshot.GpuNames)
    $gpuText = if ($gpuNames.Count -gt 0) { "GPU: $($gpuNames -join ', ')" } else { "GPU: não identificada" }
    $sync.WPFDashboardGpuDetail.Text = $gpuText
    $sync.WPFDashboardGpuDetail.ToolTip = $gpuText

    Update-WinUtilDashboardMetrics
}

function Set-WinUtilDNS {
    <#

    .SYNOPSIS
        Sets the DNS of all interfaces that are in the "Up" state. It will lookup the values from the DNS.Json file

    .PARAMETER DNSProvider
        The DNS provider to set the DNS server to

    .EXAMPLE
        Set-WinUtilDNS -DNSProvider "google"

    #>
    param($DNSProvider)

    if($DNSProvider -eq "Default") {
        Write-WinUtilLog -Component "DNS" -Message "DNS provider is Default; no DNS changes applied."
        return $true
    }

    try {
        $Adapters = Get-NetAdapter | Where-Object {$_.Status -eq "Up"}
        Write-Host "Ensuring DNS is set to $DNSProvider on the following interfaces:"
        Write-Host $($Adapters | Out-String)
        Write-WinUtilLog -Component "DNS" -Message "Setting DNS provider to $DNSProvider for $(@($Adapters).Count) active adapter(s)."

        if($DNSProvider -ne "DHCP") {
            $dns = $sync.configs.dns.$DNSProvider
            if($null -eq $dns) {
                Write-Warning "DNS provider $DNSProvider was not found in configuration."
                Write-WinUtilLog -Level "ERROR" -Component "DNS" -Message "DNS provider $DNSProvider was not found in configuration."
                return $false
            }
        }

        $dohSupported = [bool](Get-Command Add-DnsClientDohServerAddress -ErrorAction SilentlyContinue)
        if ($DNSProvider -ne "DHCP" -and $dns.DohOnly -and -not $dohSupported) {
            Write-Warning "DNS provider $DNSProvider requires DNS over HTTPS, which is not supported on this system."
            Write-WinUtilLog -Level "ERROR" -Component "DNS" -Message "DNS provider $DNSProvider requires DNS over HTTPS, which is not supported on this system."
            return $false
        }

        $dnscacheBase = "HKLM:\System\CurrentControlSet\Services\Dnscache\InterfaceSpecificParameters"

        Foreach ($Adapter in $Adapters) {
            $interfaceParams = "$dnscacheBase\$($Adapter.InterfaceGuid)"

            if($DNSProvider -eq "DHCP") {
                Write-WinUtilLog -Component "DNS" -Message "Resetting DNS to DHCP on adapter $($Adapter.Name) (ifIndex: $($Adapter.ifIndex))."
                Set-DnsClientServerAddress -InterfaceIndex $Adapter.ifIndex -ResetServerAddresses
                netsh interface ip set dnsservers name="$($Adapter.Name)" source=dhcp
                netsh interface ipv6 set dnsservers name="$($Adapter.Name)" source=dhcp

                $dohInterfaceSettings = "$interfaceParams\DohInterfaceSettings"
                if (Test-Path $dohInterfaceSettings) {
                    if ($dohSupported) {
                        $dohServerAddresses = @(
                            Get-ChildItem -Path "$dohInterfaceSettings\Doh" -ErrorAction SilentlyContinue
                            Get-ChildItem -Path "$dohInterfaceSettings\Doh6" -ErrorAction SilentlyContinue
                        ) | Select-Object -ExpandProperty PSChildName -Unique

                        foreach ($ip in $dohServerAddresses) {
                            if (Get-DnsClientDohServerAddress -ServerAddress $ip -ErrorAction SilentlyContinue) {
                                Write-WinUtilLog -Component "DNS" -Message "Removing DoH registration for $ip."
                                Remove-DnsClientDohServerAddress -ServerAddress $ip -Confirm:$false -ErrorAction Stop
                            }
                        }
                    }

                    Remove-Item -Path $dohInterfaceSettings -Recurse -Force -ErrorAction SilentlyContinue
                }
            } else {
                $ipv4Addresses = @(@($dns.Primary, $dns.Secondary) | Where-Object { $_ })
                $ipv6Addresses = @(@($dns.Primary6, $dns.Secondary6) | Where-Object { $_ })

                if ($dohSupported -and $dns.DohTemplate) {
                    try {
                        $ips = @($dns.Primary, $dns.Secondary, $dns.Primary6, $dns.Secondary6) | Where-Object { $_ }
                        foreach ($ip in $ips) {
                            $dohTemplate = if ($dns.SecondaryDohTemplate -and @($dns.Secondary, $dns.Secondary6) -contains $ip) {
                                $dns.SecondaryDohTemplate
                            } else {
                                $dns.DohTemplate
                            }
                            $existing = Get-DnsClientDohServerAddress -ServerAddress $ip -ErrorAction SilentlyContinue
                            if ($existing) {
                                Set-DnsClientDohServerAddress -ServerAddress $ip -DohTemplate $dohTemplate -AllowFallbackToUdp $false -AutoUpgrade $true -ErrorAction Stop
                            } else {
                                Write-WinUtilLog -Component "DNS" -Message "Registering DoH template for $ip."
                                Add-DnsClientDohServerAddress -ServerAddress $ip -DohTemplate $dohTemplate -AllowFallbackToUdp $false -AutoUpgrade $true -ErrorAction Stop
                            }

                            $leaf = if ($ip.Contains(':')) { 'Doh6' } else { 'Doh' }
                            $regPath = "$interfaceParams\DohInterfaceSettings\$leaf\$ip"

                            if (-not (Test-Path $regPath)) {
                                New-Item -Path $regPath -Force -ErrorAction Stop | Out-Null
                            }
                            New-ItemProperty -Path $regPath -Name "DohFlags" -Value 1 -PropertyType QWord -Force -ErrorAction Stop | Out-Null
                        }
                    } catch {
                        if ($dns.DohOnly) {
                            throw
                        }

                        Write-Warning "DNS over HTTPS setup for provider $DNSProvider failed; continuing with plain DNS."
                        Write-WinUtilLog -Level "WARN" -Component "DNS" -Message "DNS over HTTPS setup for provider $DNSProvider failed; continuing with plain DNS: $($psitem.Exception.Message)"
                    }
                }

                Write-WinUtilLog -Component "DNS" -Message "Setting IPv4 DNS on adapter $($Adapter.Name) (ifIndex: $($Adapter.ifIndex)) to $($dns.Primary), $($dns.Secondary)."
                Set-DnsClientServerAddress -InterfaceIndex $Adapter.ifIndex -ServerAddresses $ipv4Addresses -ErrorAction Stop
                Write-WinUtilLog -Component "DNS" -Message "Setting IPv6 DNS on adapter $($Adapter.Name) (ifIndex: $($Adapter.ifIndex)) to $($dns.Primary6), $($dns.Secondary6)."
                Set-DnsClientServerAddress -InterfaceIndex $Adapter.ifIndex -ServerAddresses $ipv6Addresses -ErrorAction Stop
            }
        }
        if ($DNSProvider -ne "DHCP" -and $dohSupported -and $dns.DohTemplate) {
            Clear-DnsClientCache
        }
        Write-WinUtilLog -Component "DNS" -Message "DNS provider change completed: $DNSProvider"
        return $true
    } catch {
        Write-Warning "DNS provider $DNSProvider was not completed because an error occurred."
        Write-Warning $psitem.Exception.Message
        Write-WinUtilLog -Level "ERROR" -Component "DNS" -Message "DNS provider $DNSProvider was not completed: $($psitem.Exception.Message)"
        return $false
    }
}

function Set-WinUtilRegistry {
    <#

    .SYNOPSIS
        Modifies the registry based on the given inputs

    .PARAMETER Name
        The name of the key to modify

    .PARAMETER Path
        The path to the key

    .PARAMETER Type
        The type of value to set the key to

    .PARAMETER Value
        The value to set the key to

    .EXAMPLE
        Set-WinUtilRegistry -Name "PublishUserActivities" -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\System" -Type "DWord" -Value "0"

    #>
    param (
        $Name,
        $Path,
        $Type,
        $Value
    )

    try {
        if(!(Test-Path 'HKU:\')) {New-PSDrive -PSProvider Registry -Name HKU -Root HKEY_USERS | Out-Null}

        if ($Value -eq "<RemoveEntry>") {
            # Removing from a key that does not exist is already done. Creating the
            # key first left an empty key behind as a side effect of an undo.
            if (!(Test-Path $Path)) {
                Write-WinUtilLog -Component "Registry" -Message "Nothing to remove: $Path does not exist"
                return
            }
            Write-Host "Remove $Path\$Name"
            Write-WinUtilLog -Component "Registry" -Message "Removing $Path\$Name"
            try {
                Remove-ItemProperty -Path $Path -Name $Name -Force -ErrorAction Stop | Out-Null
            } catch [System.Management.Automation.PSArgumentException] {
                # The value was already absent, which is the requested state. This used
                # to be logged as an unhandled exception on every undo of such a tweak.
                Write-WinUtilLog -Component "Registry" -Message "Nothing to remove: $Path\$Name was already absent"
            }
            return
        }

        If (!(Test-Path $Path)) {
            Write-Host "$Path was not found. Creating..."
            Write-WinUtilLog -Component "Registry" -Message "Creating registry path: $Path"
            New-Item -Path $Path -Force -ErrorAction Stop | Out-Null
        }

        Write-Host "Set $Path\$Name to $Value"
        Write-WinUtilLog -Component "Registry" -Message "Setting $Path\$Name ($Type) to $Value"
        Set-ItemProperty -Path $Path -Name $Name -Type $Type -Value $Value -Force -ErrorAction Stop | Out-Null
    } catch [System.Security.SecurityException] {
        Write-Warning "Unable to set $Path\$Name to $Value due to a Security Exception."
        Write-WinUtilLog -Level "ERROR" -Component "Registry" -Message "Security exception while changing $Path\$Name to $Value`: $($psitem.Exception.Message)"
    } catch [System.Management.Automation.ItemNotFoundException] {
        Write-Warning $psitem.Exception.ErrorRecord
        Write-WinUtilLog -Level "ERROR" -Component "Registry" -Message "Registry item not found while changing $Path\$Name`: $($psitem.Exception.Message)"
    } catch [System.UnauthorizedAccessException] {
       Write-Warning $psitem.Exception.Message
       Write-WinUtilLog -Level "ERROR" -Component "Registry" -Message "Unauthorized while changing $Path\$Name`: $($psitem.Exception.Message)"
    } catch {
        Write-Warning "Unable to set $Name due to unhandled exception."
        # StackTrace is often null here, and a null Write-Warning threw a second error.
        Write-Warning $psitem.Exception.Message
        Write-WinUtilLog -Level "ERROR" -Component "Registry" -Message "Unhandled exception while changing $Path\$Name`: $($psitem.Exception.Message)"
    }
}

function Set-WinUtilRegistryComboState {
    <#
    .SYNOPSIS
        Applies and verifies a config-defined registry combo-box state.

    .PARAMETER Registry
        Registry settings containing a value mapping for each supported state.

    .PARAMETER State
        The state name to apply.
    #>
    param(
        [Parameter(Mandatory)]
        $Registry,

        [Parameter(Mandatory)]
        [string]$State
    )

    if ($Registry[0].Values.PSObject.Properties.Name -notcontains $State) {
        throw "Estado de registro desconhecido: '$State'."
    }

    # Preserve exact prior values so a partial update can be rolled back.
    $previousValues = foreach ($setting in @($Registry)) {
        $currentValue = Get-WinUtilRegistryComboValue -Setting $setting
        [pscustomobject]@{ Setting = $setting; Exists = $currentValue.Exists; Value = $currentValue.Value }
    }

    try {
        foreach ($setting in @($Registry)) {
            $configuredValue = $setting.Values.PSObject.Properties[$State].Value
            $previousValue = $previousValues | Where-Object Setting -EQ $setting
            if ($configuredValue -ne "<RemoveEntry>" -or $previousValue.Exists) {
                Set-WinUtilRegistry -Name $setting.Name -Path $setting.Path -Type $setting.Type -Value $configuredValue
            }
        }

        # Set-WinUtilRegistry reports write errors without throwing, so verify each result explicitly.
        foreach ($setting in @($Registry)) {
            $configuredValue = $setting.Values.PSObject.Properties[$State].Value
            $currentValue = Get-WinUtilRegistryComboValue -Setting $setting
            $writeMatches = if ($configuredValue -eq "<RemoveEntry>") {
                -not $currentValue.Exists
            } else {
                $currentValue.Exists -and [string]$currentValue.Value -eq [string]$configuredValue
            }
            if (-not $writeMatches) {
                throw "Os valores do registro não correspondem ao estado solicitado."
            }
        }
    } catch {
        $applyError = $_.Exception.Message
        if ([string]::IsNullOrWhiteSpace($applyError)) {
            $applyError = "The registry values did not match the requested state."
        }
        $rollbackFailed = $false
        foreach ($previousValue in $previousValues) {
            try {
                $currentValue = Get-WinUtilRegistryComboValue -Setting $previousValue.Setting
                if ($previousValue.Exists -or $currentValue.Exists) {
                    $rollbackValue = if ($previousValue.Exists) { $previousValue.Value } else { "<RemoveEntry>" }
                    Set-WinUtilRegistry -Name $previousValue.Setting.Name -Path $previousValue.Setting.Path -Type $previousValue.Setting.Type -Value $rollbackValue
                }
                $restoredValue = Get-WinUtilRegistryComboValue -Setting $previousValue.Setting
                if ($restoredValue.Exists -ne $previousValue.Exists -or ($restoredValue.Exists -and [string]$restoredValue.Value -ne [string]$previousValue.Value)) {
                    $rollbackFailed = $true
                }
            } catch {
                $rollbackFailed = $true
            }
        }
        if ($rollbackFailed) {
            throw "Não foi possível aplicar o estado de registro '$State': $applyError. Não foi possível restaurar o estado anterior do registro."
        }
        throw "Não foi possível aplicar o estado de registro '$State': $applyError"
    }
}

Function Set-WinUtilService {
    <#

    .SYNOPSIS
        Changes the startup type of the given service

    .PARAMETER Name
        The name of the service to modify

    .PARAMETER StartupType
        The startup type to set the service to

    .EXAMPLE
        Set-WinUtilService -Name "HomeGroupListener" -StartupType "Manual"

    #>
    param (
        $Name,
        $StartupType
    )
    try {
        Write-Host "Setting Service $Name to $StartupType"
        Write-WinUtilLog -Component "Service" -Message "Setting service $Name startup type to $StartupType"

        # Check if the service exists
        $service = Get-Service -Name $Name -ErrorAction Stop

        if (($service.PSObject.Properties.Name -contains "StartType") -and ([string]$service.StartType -eq [string]$StartupType) ) {
            Write-Host "Service $Name is already set to $StartupType"
            Write-WinUtilLog -Component "Service" -Message "Service $Name startup type is already $StartupType; no change needed."
            return
        }

        # Service exists, proceed with changing properties -- while handling auto delayed start for PWSH 5
        if (($PSVersionTable.PSVersion.Major -lt 7) -and ($StartupType -eq "AutomaticDelayedStart")) {
            sc.exe config $Name start= delayed-auto
            if ($LASTEXITCODE -ne 0) {
                throw "sc.exe config failed with exit code $LASTEXITCODE"
            }
        } else {
            $service | Set-Service -StartupType $StartupType -ErrorAction Stop
        }
        Write-WinUtilLog -Component "Service" -Message "Service $Name startup type set to $StartupType"
    } catch {
        if ($_.FullyQualifiedErrorId -like "NoServiceFoundForGivenName,*") {
            Write-Warning "Service $Name was not found."
            Write-WinUtilLog -Level "WARN" -Component "Service" -Message "Service $Name was not found."
        } else {
            Write-Warning "Unable to set $Name due to unhandled exception."
            Write-Warning $_.Exception.Message
            Write-WinUtilLog -Level "ERROR" -Component "Service" -Message "Unable to set service $Name to $StartupType`: $($_.Exception.Message)"
        }
    }

}

function Set-WinUtilStartupItemState {
    <#
    .SYNOPSIS
        Enables or disables a startup item the same way Task Manager does.

    .DESCRIPTION
        Writes the item's StartupApproved value: 02 00 00 00 plus eight zero bytes when enabled, or
        03 00 00 00 followed by the current FILETIME when disabled. The Run value or shortcut itself is
        never touched, so the change is fully reversible.

    .PARAMETER ApprovedPath
        The StartupApproved key for the item's source, for example HKCU:\...\StartupApproved\Run.

    .PARAMETER ValueName
        The Run value name, or the file name for Startup folder items.

    .PARAMETER Enabled
        $true to let the item start with Windows, $false to keep it from starting.
    #>
    param(
        [Parameter(Mandatory)]
        [string]$ApprovedPath,

        [Parameter(Mandatory)]
        [string]$ValueName,

        [Parameter(Mandatory)]
        [bool]$Enabled
    )

    if (-not (Test-Path -LiteralPath $ApprovedPath)) {
        New-Item -Path $ApprovedPath -Force -ErrorAction Stop | Out-Null
    }

    if ($Enabled) {
        [byte[]]$state = 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
    } else {
        [byte[]]$state = @(3, 0, 0, 0) + [BitConverter]::GetBytes([DateTime]::Now.ToFileTime())
    }

    New-ItemProperty -LiteralPath $ApprovedPath -Name $ValueName -PropertyType Binary -Value $state -Force -ErrorAction Stop | Out-Null

    $stateName = if ($Enabled) { "enabled" } else { "disabled" }
    Write-WinUtilLog -Component "Startup" -Message "Startup item '$ValueName' ($ApprovedPath) $stateName."
}

function Set-WinUtilTaskbaritem {
    <#

    .SYNOPSIS
        Modifies the Taskbaritem of the WPF Form

    .PARAMETER value
        Value can be between 0 and 1, 0 being no progress done yet and 1 being fully completed
        Value does not affect item without setting the state to 'Normal', 'Error' or 'Paused'
        Set-WinUtilTaskbaritem -value 0.5

    .PARAMETER state
        State can be 'None' > No progress, 'Indeterminate' > inf. loading gray, 'Normal' > Gray, 'Error' > Red, 'Paused' > Yellow
        no value needed:
        - Set-WinUtilTaskbaritem -state "None"
        - Set-WinUtilTaskbaritem -state "Indeterminate"
        value needed:
        - Set-WinUtilTaskbaritem -state "Error"
        - Set-WinUtilTaskbaritem -state "Normal"
        - Set-WinUtilTaskbaritem -state "Paused"

    .PARAMETER overlay
        Overlay icon to display on the taskbar item, there are the presets 'None', 'logo' and 'checkmark' or you can specify a path/link to an image file.
        CTT logo preset:
        - Set-WinUtilTaskbaritem -overlay "logo"
        Checkmark preset:
        - Set-WinUtilTaskbaritem -overlay "checkmark"
        Warning preset:
        - Set-WinUtilTaskbaritem -overlay "warning"
        No overlay:
        - Set-WinUtilTaskbaritem -overlay "None"
        Custom icon (needs to be supported by WPF):
        - Set-WinUtilTaskbaritem -overlay "C:\path\to\icon.png"

    .PARAMETER description
        Description to display on the taskbar item preview
        Set-WinUtilTaskbaritem -description "This is a description"
    #>
    param (
        [string]$state,
        [double]$value,
        [string]$overlay,
        [string]$description
    )

    if ($value) {
        $sync["Form"].taskbarItemInfo.ProgressValue = $value
    }

    if ($state) {
        switch ($state) {
            'None' { $sync["Form"].taskbarItemInfo.ProgressState = "None" }
            'Indeterminate' { $sync["Form"].taskbarItemInfo.ProgressState = "Indeterminate" }
            'Normal' { $sync["Form"].taskbarItemInfo.ProgressState = "Normal" }
            'Error' { $sync["Form"].taskbarItemInfo.ProgressState = "Error" }
            'Paused' { $sync["Form"].taskbarItemInfo.ProgressState = "Paused" }
            default { throw "[Set-WinUtilTaskbarItem] Invalid state" }
        }
    }

    if ($overlay) {
        switch ($overlay) {
            'logo' {
                if (-not $sync["logorender"]) {
                    Initialize-WinUtilTaskbarOverlayAssets -IncludeLogo $true -IncludeStatusAssets $false
                }
                $sync["Form"].taskbarItemInfo.Overlay = $sync["logorender"]
            }
            'checkmark' {
                if (-not $sync["checkmarkrender"]) {
                    Initialize-WinUtilTaskbarOverlayAssets -IncludeLogo $false -IncludeStatusAssets $true
                }
                $sync["Form"].taskbarItemInfo.Overlay = $sync["checkmarkrender"]
            }
            'warning' {
                if (-not $sync["warningrender"]) {
                    Initialize-WinUtilTaskbarOverlayAssets -IncludeLogo $false -IncludeStatusAssets $true
                }
                $sync["Form"].taskbarItemInfo.Overlay = $sync["warningrender"]
            }
            'None' {
                $sync["Form"].taskbarItemInfo.Overlay = $null
            }
            default {
                if (Test-Path $overlay) {
                    $sync["Form"].taskbarItemInfo.Overlay = $overlay
                }
            }
        }
    }

    if ($description) {
        $sync["Form"].taskbarItemInfo.Description = $description
    }
}

function Set-WinUtilTweaksProgressIndicator {
    <#
    .SYNOPSIS
        Shows, updates, or hides the window-level progress indicator used by long-running
        workflows such as app management, Tweaks, AppX management, and Win11 Creator.
        It lives outside the TabControl, so it stays visible no matter which tab is active.
    .PARAMETER Visible
        Whether the indicator should be shown or hidden.
    .PARAMETER Label
        The text to display above the progress bar.
    .PARAMETER Percent
        The percentage of the progress bar that should be filled (0-100).
    #>
    param(
        [bool]$Visible,
        [string]$Label,
        [ValidateRange(0,100)]
        [int]$Percent
    )

    if ($null -eq $sync.form -or $null -eq $sync.form.Dispatcher) {
        return
    }

    $indicatorVisible = if ($Visible) { [Windows.Visibility]::Visible } else { [Windows.Visibility]::Collapsed }
    $indicatorLabel = $Label
    $hasLabel = $PSBoundParameters.ContainsKey('Label')
    $hasPercent = $PSBoundParameters.ContainsKey('Percent')

    Invoke-WPFUIThread -ScriptBlock {
        $sync.WPFTweaksProgressBar.Visibility = $indicatorVisible
        if ($hasLabel) {
            $sync.WPFTweaksProgressLabel.Text = $indicatorLabel
        }
        if ($hasPercent) {
            $sync.WPFTweaksProgressValue.Value = $Percent
        }
    }
}

function Show-CustomDialog {
    <#
    .SYNOPSIS
    Displays a custom dialog box with an image, heading, message, and an OK button.

    .DESCRIPTION
    This function creates a custom dialog box with the specified message and additional elements such as an image, heading, and an OK button. The dialog uses the Azor WinUtil look: a rounded card with a rose border and glow that shares the styles of the main window.

    .PARAMETER Title
    The Title to use for the dialog window's Title Bar, this will not be visible by the user, as window styling is set to None.

    .PARAMETER Message
    The message to be displayed in the dialog box. Links written as <a href="url">text</a> become clickable.

    .PARAMETER Width
    The width of the custom dialog window.

    .PARAMETER Height
    The height of the custom dialog window.

    .PARAMETER FontSize
    The Font Size of message shown inside custom dialog window.

    .PARAMETER HeaderFontSize
    The Font Size for the Header of custom dialog window.

    .PARAMETER LogoSize
    The Size of the Logo used inside the custom dialog window.

    .PARAMETER ForegroundColor
    The Foreground Color of dialog window title & message.

    .PARAMETER BackgroundColor
    The Background Color of dialog window.

    .PARAMETER BorderColor
    The Color for dialog window border.

    .PARAMETER ShadowColor
    The Color used for the glow around the dialog window.

    .PARAMETER LogoColor
    The brush of the Azor WinUtil text found next to the logo inside dialog window.

    .PARAMETER LinkForegroundColor
    The Foreground Color for Links inside dialog window.

    .PARAMETER LinkHoverForegroundColor
    The Foreground Color for Links when the mouse pointer hovers over them inside dialog window.

    .PARAMETER EnableScroll
    A flag indicating whether to enable scrolling if the content exceeds the window size.

    .EXAMPLE
    Show-CustomDialog -Title "Sobre" -Message "Uma mensagem com um <a href=""https://github.com"">link</a>." -Width 300 -Height 200

    Makes a new Custom Dialog with the title 'Sobre' and a message containing a clickable link, with dimensions of 300 by 200 pixels.
    Other styling options are grabbed from '$sync.Form.Resources' global variable.

    #>
    param(
        [string]$Title,
        [string]$Message,
        [int]$Width = $sync.Form.Resources.CustomDialogWidth,
        [int]$Height = $sync.Form.Resources.CustomDialogHeight,

        [System.Windows.Media.FontFamily]$FontFamily = $sync.Form.Resources.FontFamily,
        [int]$FontSize = $sync.Form.Resources.CustomDialogFontSize,
        [int]$HeaderFontSize = $sync.Form.Resources.CustomDialogFontSizeHeader,
        [int]$LogoSize = $sync.Form.Resources.CustomDialogLogoSize,

        $ShadowColor = $sync.Form.Resources.CAccentColor,
        [System.Windows.Media.Brush]$LogoColor = $sync.Form.Resources.AzorRoseGradientBrush,
        [System.Windows.Media.SolidColorBrush]$BorderColor = $sync.Form.Resources.AccentColor,
        [System.Windows.Media.SolidColorBrush]$ForegroundColor = $sync.Form.Resources.MainForegroundColor,
        [System.Windows.Media.SolidColorBrush]$BackgroundColor = $sync.Form.Resources.CardBackgroundColor,
        [System.Windows.Media.SolidColorBrush]$LinkForegroundColor = $sync.Form.Resources.LinkForegroundColor,
        [System.Windows.Media.SolidColorBrush]$LinkHoverForegroundColor = $sync.Form.Resources.LinkHoverForegroundColor,

        [bool]$EnableScroll = $false
    )

    if ($null -eq $ShadowColor) {
        $ShadowColor = [Windows.Media.Colors]::HotPink
    }

    # Create a custom dialog window
    $dialog = New-Object Windows.Window
    $dialog.Title = $Title
    $dialog.Width = $Width + 24
    $dialog.Height = $Height + 24
    $dialog.WindowStyle = [Windows.WindowStyle]::None  # Remove title bar and window controls
    $dialog.AllowsTransparency = $true  # Needed for the rounded card and its glow
    $dialog.Background = [Windows.Media.Brushes]::Transparent
    $dialog.ResizeMode = [Windows.ResizeMode]::NoResize  # Disable resizing
    $dialog.WindowStartupLocation = [Windows.WindowStartupLocation]::CenterScreen  # Center the window
    $dialog.ShowInTaskbar = $false
    $dialog.Foreground = $ForegroundColor
    $dialog.FontFamily = $FontFamily
    $dialog.FontSize = $FontSize

    if ($sync.Form) {
        # Share the main window resources so the dialog uses the same Azor styles
        foreach ($resourceKey in @($sync.Form.Resources.Keys)) {
            $dialog.Resources[$resourceKey] = $sync.Form.Resources[$resourceKey]
        }

        if ($sync.Form.IsVisible) {
            $dialog.Owner = $sync.Form
            $dialog.WindowStartupLocation = [Windows.WindowStartupLocation]::CenterOwner
        }
    }

    # The glow is a separate layer, so the text on the card is not rendered through the effect
    $glow = New-Object Windows.Controls.Border
    $glow.CornerRadius = New-Object Windows.CornerRadius(14)
    $glow.Background = $BackgroundColor
    $glow.Margin = New-Object Windows.Thickness(12)

    $dropShadow = New-Object Windows.Media.Effects.DropShadowEffect
    $dropShadow.Color = $ShadowColor
    $dropShadow.ShadowDepth = 0
    $dropShadow.BlurRadius = 18
    $dropShadow.Opacity = 0.55
    $glow.Effect = $dropShadow

    # Create a Border for the rose edge with rounded corners
    $border = New-Object Windows.Controls.Border
    $border.BorderBrush = $BorderColor
    $border.BorderThickness = New-Object Windows.Thickness(1)
    $border.CornerRadius = New-Object Windows.CornerRadius(14)
    $border.Background = $BackgroundColor
    $border.Margin = New-Object Windows.Thickness(12)
    $border.HorizontalAlignment = [Windows.HorizontalAlignment]::Stretch
    $border.VerticalAlignment = [Windows.VerticalAlignment]::Stretch

    $layers = New-Object Windows.Controls.Grid
    [void]$layers.Children.Add($glow)
    [void]$layers.Children.Add($border)
    $dialog.Content = $layers

    # Create a grid for layout inside the Border
    $grid = New-Object Windows.Controls.Grid
    $border.Child = $grid
    $grid.Background = [Windows.Media.Brushes]::Transparent
    $grid.HorizontalAlignment = [Windows.HorizontalAlignment]::Stretch
    $grid.VerticalAlignment = [Windows.VerticalAlignment]::Stretch

    # Set up Row Definitions
    $row0 = New-Object Windows.Controls.RowDefinition
    $row0.Height = [Windows.GridLength]::Auto

    $row1 = New-Object Windows.Controls.RowDefinition
    $row1.Height = [Windows.GridLength]::new(1, [Windows.GridUnitType]::Star)

    $row2 = New-Object Windows.Controls.RowDefinition
    $row2.Height = [Windows.GridLength]::Auto

    # Add Row Definitions to Grid
    $grid.RowDefinitions.Add($row0)
    $grid.RowDefinitions.Add($row1)
    $grid.RowDefinitions.Add($row2)

    # Header with the logo; dragging it moves the dialog
    $stackPanel = New-Object Windows.Controls.StackPanel
    $stackPanel.Margin = New-Object Windows.Thickness(16, 14, 16, 4)
    $stackPanel.Orientation = [Windows.Controls.Orientation]::Horizontal
    $stackPanel.HorizontalAlignment = [Windows.HorizontalAlignment]::Stretch
    $stackPanel.VerticalAlignment = [Windows.VerticalAlignment]::Top
    $stackPanel.Background = [Windows.Media.Brushes]::Transparent
    $stackPanel.Cursor = [System.Windows.Input.Cursors]::SizeAll
    $stackPanel.Add_MouseLeftButtonDown({ $dialog.DragMove() })

    [void]$grid.Children.Add($stackPanel)
    [Windows.Controls.Grid]::SetRow($stackPanel, 0)

    # Add the logo to the stack panel
    [void]$stackPanel.Children.Add((Invoke-WinUtilAssets -Type "logo" -Size $LogoSize))

    # Add "Azor WinUtil" text
    $winutilTextBlock = New-Object Windows.Controls.TextBlock
    $winutilTextBlock.Text = "Azor WinUtil"
    $winutilTextBlock.FontSize = $HeaderFontSize
    if ($sync.Form.Resources.HeaderFontFamily) {
        $winutilTextBlock.FontFamily = $sync.Form.Resources.HeaderFontFamily
    }
    $winutilTextBlock.Foreground = $LogoColor
    $winutilTextBlock.Background = [Windows.Media.Brushes]::Transparent
    $winutilTextBlock.VerticalAlignment = [Windows.VerticalAlignment]::Center
    $winutilTextBlock.Margin = New-Object Windows.Thickness(10, 0, 10, 0)
    [void]$stackPanel.Children.Add($winutilTextBlock)

    # Add TextBlock for information with text wrapping and margins
    $messageTextBlock = New-Object Windows.Controls.TextBlock
    $messageTextBlock.FontSize = $FontSize
    $messageTextBlock.Foreground = $ForegroundColor
    $messageTextBlock.Background = [Windows.Media.Brushes]::Transparent
    $messageTextBlock.TextWrapping = [Windows.TextWrapping]::Wrap  # Enable text wrapping
    $messageTextBlock.HorizontalAlignment = [Windows.HorizontalAlignment]::Left
    $messageTextBlock.VerticalAlignment = [Windows.VerticalAlignment]::Top
    $messageTextBlock.Margin = New-Object Windows.Thickness(18, 8, 18, 8)

    # Define the Regex to find hyperlinks formatted as HTML <a> tags
    $regex = [regex]::new('<a href="([^"]+)">([^<]+)</a>')
    $lastPos = 0
    $linkHoverBrush = $LinkHoverForegroundColor

    # Iterate through each match and add regular text and hyperlinks
    foreach ($match in $regex.Matches($Message)) {
        # Add the text before the hyperlink, if any
        $textBefore = $Message.Substring($lastPos, $match.Index - $lastPos)
        if ($textBefore.Length -gt 0) {
            $messageTextBlock.Inlines.Add((New-Object Windows.Documents.Run($textBefore)))
        }

        # Create and add the hyperlink
        $hyperlink = New-Object Windows.Documents.Hyperlink
        $hyperlink.NavigateUri = New-Object System.Uri($match.Groups[1].Value)
        $hyperlink.Inlines.Add($match.Groups[2].Value)
        $hyperlink.TextDecorations = [Windows.TextDecorations]::None  # Remove underline
        $hyperlink.Foreground = $LinkForegroundColor

        $hyperlink.Add_Click({
            param($eventSender, $routedEvent)
            $null = $routedEvent
            Start-Process $eventSender.NavigateUri.AbsoluteUri
        })
        $hyperlink.Add_MouseEnter({
            param($eventSender, $routedEvent)
            $null = $routedEvent
            $eventSender.Foreground = $linkHoverBrush
            $eventSender.TextDecorations = [Windows.TextDecorations]::Underline
        })
        $hyperlink.Add_MouseLeave({
            param($eventSender, $routedEvent)
            $null = $routedEvent
            $eventSender.Foreground = $LinkForegroundColor
            $eventSender.TextDecorations = [Windows.TextDecorations]::None
        })

        $messageTextBlock.Inlines.Add($hyperlink)

        # Update the last position
        $lastPos = $match.Index + $match.Length
    }

    # Add any remaining text after the last hyperlink
    if ($lastPos -lt $Message.Length) {
        $textAfter = $Message.Substring($lastPos)
        $messageTextBlock.Inlines.Add((New-Object Windows.Documents.Run($textAfter)))
    }

    # If no matches, add the entire message as a run
    if ($regex.Matches($Message).Count -eq 0) {
        $messageTextBlock.Inlines.Add((New-Object Windows.Documents.Run($Message)))
    }

    # Create a ScrollViewer if EnableScroll is true
    if ($EnableScroll) {
        $scrollViewer = New-Object System.Windows.Controls.ScrollViewer
        $scrollViewer.VerticalScrollBarVisibility = 'Auto'
        $scrollViewer.HorizontalScrollBarVisibility = 'Disabled'
        $scrollViewer.Content = $messageTextBlock
        [void]$grid.Children.Add($scrollViewer)
        [Windows.Controls.Grid]::SetRow($scrollViewer, 1)  # Set the row to the second row (0-based index)
    } else {
        [void]$grid.Children.Add($messageTextBlock)
        [Windows.Controls.Grid]::SetRow($messageTextBlock, 1)  # Set the row to the second row (0-based index)
    }

    # Add OK button
    $okButton = New-Object Windows.Controls.Button
    $okButton.Content = "OK"
    $okButton.FontSize = $FontSize
    $okButton.Width = 96
    $okButton.Height = 32
    if ($dialog.Resources.Contains("AccentButtonStyle")) {
        $okButton.Style = $dialog.Resources["AccentButtonStyle"]
    }
    $okButton.HorizontalAlignment = [Windows.HorizontalAlignment]::Center
    $okButton.VerticalAlignment = [Windows.VerticalAlignment]::Bottom
    $okButton.Margin = New-Object Windows.Thickness(0, 4, 0, 14)
    $okButton.Add_Click({
        $dialog.Close()
    })
    [void]$grid.Children.Add($okButton)
    [Windows.Controls.Grid]::SetRow($okButton, 2)  # Set the row to the third row (0-based index)

    # Handle Escape key press to close the dialog
    $dialog.Add_KeyDown({
        if ($_.Key -eq 'Escape') {
            $dialog.Close()
        }
    })

    # Set the OK button as the default button (activated on Enter)
    $okButton.IsDefault = $true

    # Show the custom dialog
    $dialog.ShowDialog()
}

function Show-WinUtilCheckupDialog {
    <#
    .SYNOPSIS
        Shows the Checkup para Jogos window and returns $true when the user asks to fix the listed items.

    .PARAMETER Report
        The objects returned by Get-WinUtilGameCompatReport.
    #>
    param(
        [object[]]$Report = @()
    )

    $window = New-WinUtilCheckupWindow -Report $Report
    [void]$window.ShowDialog()
    return ([string]$window.Tag -eq "Fix")
}

function Show-WinUtilMessage {
    <#
    .SYNOPSIS
        Shows an Azor WinUtil message box and returns the selected result.
    #>
    param (
        [string]$Message,
        [string]$Title = "Azor WinUtil",
        $Button = "OK",
        $Icon = "Information"
    )

    [System.Windows.MessageBox]::Show($Message, $Title, $Button, $Icon)
}

function Invoke-WinUtilInstallAppRenderBatch {
    param(
        [Parameter(Mandatory = $true)]
        $CategoryBatch
    )

    foreach ($appKey in $CategoryBatch.AppKeys) {
        $sync.$appKey = Initialize-InstallAppEntry -TargetElement $CategoryBatch.TargetElement -AppKey $appKey
    }

    # Entries render in batches, so a filter that is already active has to be applied to each new
    # batch. Categories count as an active filter just like search text does.
    if ($sync.currentTab -eq "Install" -and $sync.SearchBar) {
        $selectedCategories = if ($sync.SelectedAppCategories) { $sync.SelectedAppCategories.ToArray() } else { @() }

        if (-not [string]::IsNullOrWhiteSpace($sync.SearchBar.Text) -or $selectedCategories.Count -gt 0) {
            Find-AppsByNameOrDescription -SearchString $sync.SearchBar.Text -Categories $selectedCategories
        }
    }
}

function Complete-WinUtilInstallAppRendering {
    $sync.InstallAppEntriesRendered = $true
}

function Invoke-WinUtilInstallAppRenderNextBatch {
    if ($sync.InstallAppRenderQueue.Count -gt 0) {
        $categoryBatch = $sync.InstallAppRenderQueue.Dequeue()
        Invoke-WinUtilInstallAppRenderBatch -CategoryBatch $categoryBatch
    }

    if ($sync.InstallAppRenderQueue.Count -gt 0) {
        $sync.Form.Dispatcher.BeginInvoke(
            [System.Windows.Threading.DispatcherPriority]::Background,
            [action]{ Invoke-WinUtilInstallAppRenderNextBatch }
        ) | Out-Null
        return
    }

    Complete-WinUtilInstallAppRendering
}

function Start-WinUtilInstallAppRendering {
    if ($null -eq $sync.InstallAppRenderQueue) {
        return
    }

    $sync.InstallAppEntriesRendered = $false

    if ($sync.Form -and $sync.Form.Dispatcher) {
        $sync.Form.Dispatcher.BeginInvoke(
            [System.Windows.Threading.DispatcherPriority]::Background,
            [action]{ Invoke-WinUtilInstallAppRenderNextBatch }
        ) | Out-Null
        return
    }

    while ($sync.InstallAppRenderQueue.Count -gt 0) {
        $categoryBatch = $sync.InstallAppRenderQueue.Dequeue()
        Invoke-WinUtilInstallAppRenderBatch -CategoryBatch $categoryBatch
    }

    Complete-WinUtilInstallAppRendering
}

function Test-WinUtilPackageManager {
    <#

    .SYNOPSIS
        Checks if WinGet and/or Choco are installed

    .PARAMETER winget
        Check if WinGet is installed

    .PARAMETER choco
        Check if Chocolatey is installed

    #>

    Param(
        [System.Management.Automation.SwitchParameter]$winget,
        [System.Management.Automation.SwitchParameter]$choco
    )

    if ($winget) {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Write-Host "===========================================" -ForegroundColor Green
            Write-Host "---        WinGet is installed          ---" -ForegroundColor Green
            Write-Host "===========================================" -ForegroundColor Green
            $status = "installed"
        } else {
            Write-Host "===========================================" -ForegroundColor Red
            Write-Host "---      WinGet is not installed        ---" -ForegroundColor Red
            Write-Host "===========================================" -ForegroundColor Red
            $status = "not-installed"
        }
    }

    if ($choco) {
        if (Get-Command choco -ErrorAction SilentlyContinue) {
            Write-Host "===========================================" -ForegroundColor Green
            Write-Host "---      Chocolatey is installed        ---" -ForegroundColor Green
            Write-Host "===========================================" -ForegroundColor Green
            $status = "installed"
        } else {
            Write-Host "===========================================" -ForegroundColor Red
            Write-Host "---    Chocolatey is not installed      ---" -ForegroundColor Red
            Write-Host "===========================================" -ForegroundColor Red
            $status = "not-installed"
        }
    }

    return $status
}

function Update-WinUtilAppCategoryChip {
    <#
        .SYNOPSIS
            Pushes the current category selection onto the Install tab filter chips

        .DESCRIPTION
            The chips are toggle buttons, so their checked state has to follow the selection
            rather than whatever the last click did to them. The All chip is checked when no
            category is selected.
    #>
    $selected = $sync.SelectedAppCategories
    if ($null -eq $selected) { return }

    foreach ($chip in $sync.AppCategoryChips) {
        $control = $sync[$chip.Name]
        if ($null -eq $control) { continue }
        $control.IsChecked = if ($chip.Category) { $selected.Contains($chip.Category) } else { $selected.Count -eq 0 }
    }
}

function Update-WinUtilDashboardMetrics {
    <#
    .SYNOPSIS
        Refreshes the live CPU, memory, disk and uptime values on the Dashboard tab.

    .DESCRIPTION
        Called on the UI thread by the dashboard timer. Every source here is a cheap in-process call
        (a performance counter, VisualBasic ComputerInfo and DriveInfo), so a refresh never stalls the window.
    #>

    if ($null -eq $sync.WPFDashboardCpuValue) {
        return
    }

    if ($sync.DashboardCpuCounter) {
        try {
            $cpuPercent = [math]::Max(0, [math]::Min(100, [math]::Round([double]$sync.DashboardCpuCounter.NextValue())))
            $sync.WPFDashboardCpuValue.Text = "$cpuPercent%"
            $sync.WPFDashboardCpuBar.Value = $cpuPercent
        } catch {
            $sync.WPFDashboardCpuValue.Text = "--"
        }
    }

    try {
        if ($null -eq $sync.DashboardComputerInfo) {
            $sync.DashboardComputerInfo = New-Object Microsoft.VisualBasic.Devices.ComputerInfo
        }
        $totalMemory = [double]$sync.DashboardComputerInfo.TotalPhysicalMemory
        $availableMemory = [double]$sync.DashboardComputerInfo.AvailablePhysicalMemory
        if ($totalMemory -gt 0) {
            $usedMemory = $totalMemory - $availableMemory
            $memoryPercent = [math]::Round($usedMemory / $totalMemory * 100)
            $sync.WPFDashboardRamValue.Text = "$memoryPercent%"
            $sync.WPFDashboardRamBar.Value = $memoryPercent
            $sync.WPFDashboardRamDetail.Text = "{0:N1} GB de {1:N1} GB em uso" -f ($usedMemory / 1GB), ($totalMemory / 1GB)
        }
    } catch {
        $sync.WPFDashboardRamDetail.Text = "Memória indisponível"
    }

    try {
        $systemDrive = [System.IO.DriveInfo]::new($env:SystemDrive)
        if ($systemDrive.IsReady -and $systemDrive.TotalSize -gt 0) {
            $usedSpace = $systemDrive.TotalSize - $systemDrive.AvailableFreeSpace
            $diskPercent = [math]::Round($usedSpace / $systemDrive.TotalSize * 100)
            $sync.WPFDashboardDiskValue.Text = "$diskPercent%"
            $sync.WPFDashboardDiskBar.Value = $diskPercent
            $sync.WPFDashboardDiskDetail.Text = "{0} {1:N0} GB livres de {2:N0} GB" -f $env:SystemDrive, ($systemDrive.AvailableFreeSpace / 1GB), ($systemDrive.TotalSize / 1GB)
        }
    } catch {
        $sync.WPFDashboardDiskDetail.Text = "Disco indisponível"
    }

    if ($sync.DashboardBootTime) {
        $uptime = (Get-Date) - $sync.DashboardBootTime
        $uptimeText = if ($uptime.TotalDays -ge 1) {
            "{0}d {1}h {2}min" -f [math]::Floor($uptime.TotalDays), $uptime.Hours, $uptime.Minutes
        } elseif ($uptime.TotalHours -ge 1) {
            "{0}h {1}min" -f $uptime.Hours, $uptime.Minutes
        } else {
            "{0}min" -f $uptime.Minutes
        }
        $sync.WPFDashboardUptimeDetail.Text = "Ligado há $uptimeText"
    }
}

function Update-WinUtilSelections {
    param(
        [Parameter(Mandatory)]
        [string[]]$flatJson,

        [switch]$Replace,

        [switch]$SkipUnknown
    )

    $nextSelections = @{
        selectedApps     = [System.Collections.Generic.List[string]]::new()
        selectedTweaks   = [System.Collections.Generic.List[string]]::new()
        selectedToggles  = [System.Collections.Generic.List[string]]::new()
        selectedFeatures = [System.Collections.Generic.List[string]]::new()
        selectedAppx     = [System.Collections.Generic.List[string]]::new()
    }

    foreach ($cbkey in $flatJson) {

        $listName = switch -Regex ($cbkey) {
            '^WPFInstall' { 'selectedApps' }
            '^WPFTweaks'  { 'selectedTweaks' }
            '^WPFToggle'  { 'selectedToggles' }
            '^WPFFeature' { 'selectedFeatures' }
            '^WPFAppx'    { 'selectedAppx' }
        }

        if (-not $listName) {
            if ($SkipUnknown) {
                $cbkey
                continue
            }
            throw "Unsupported selection key '$cbkey'."
        }

        $isKnownSelection = switch ($listName) {
            'selectedApps' {
                $sync.configs.applicationsHashtable.ContainsKey($cbkey)
            }
            'selectedTweaks' {
                $null -ne $sync.configs.tweaks.PSObject.Properties[$cbkey]
            }
            'selectedToggles' {
                $null -ne $sync.configs.tweaks.PSObject.Properties[$cbkey]
            }
            'selectedFeatures' {
                $null -ne $sync.configs.feature.PSObject.Properties[$cbkey]
            }
            'selectedAppx' {
                $sync.configs.appxHashtable.ContainsKey($cbkey)
            }
        }

        if (-not $isKnownSelection) {
            if ($SkipUnknown) {
                $cbkey
                continue
            }
            throw "Unknown selection key '$cbkey'."
        }

        $nextSelections[$listName].Add($cbkey)
    }

    $validSelectionCount = ($nextSelections.Values | ForEach-Object { $_.Count } | Measure-Object -Sum).Sum
    if ($SkipUnknown -and $validSelectionCount -eq 0) {
        return
    }

    if ($Replace) {
        foreach ($listName in $nextSelections.Keys) {
            $sync[$listName] = $nextSelections[$listName]
        }
        return
    }

    foreach ($listName in $nextSelections.Keys) {
        foreach ($cbkey in $nextSelections[$listName]) {
            $sync.$listName.Add($cbkey)
        }
    }
}

function Update-WinUtilStartupItemList {
    <#
    .SYNOPSIS
        Rebuilds the startup programs list on the Dashboard tab.

    .DESCRIPTION
        Each row has a toggle that enables or disables the item through Set-WinUtilStartupItemState.
        The toggle reacts to Click rather than Checked/Unchecked, so showing the current state never
        writes anything to the registry.
    #>

    if ($null -eq $sync.WPFStartupAppsList) {
        return
    }

    $list = $sync.WPFStartupAppsList
    $list.Children.Clear()

    $items = @(Get-WinUtilStartupItem | Sort-Object -Property Name)
    $toggleStyle = $sync.Form.FindResource("ColorfulToggleSwitchStyle")

    foreach ($item in $items) {
        $row = New-Object Windows.Controls.Grid
        $row.Margin = New-Object Windows.Thickness(0, 4, 0, 4)
        $row.Background = [Windows.Media.Brushes]::Transparent
        $row.ToolTip = "$($item.Command)`n`nOrigem: $($item.Source)"
        [void]$row.ColumnDefinitions.Add((New-Object Windows.Controls.ColumnDefinition -Property @{ Width = [Windows.GridLength]::new(1, [Windows.GridUnitType]::Star) }))
        [void]$row.ColumnDefinitions.Add((New-Object Windows.Controls.ColumnDefinition -Property @{ Width = [Windows.GridLength]::Auto }))

        $textPanel = New-Object Windows.Controls.StackPanel
        $textPanel.VerticalAlignment = [Windows.VerticalAlignment]::Center
        $textPanel.Margin = New-Object Windows.Thickness(0, 0, 10, 0)

        $nameText = New-Object Windows.Controls.TextBlock
        $nameText.Text = $item.Name
        $nameText.FontWeight = [Windows.FontWeights]::SemiBold
        $nameText.TextTrimming = [Windows.TextTrimming]::CharacterEllipsis
        $nameText.SetResourceReference([Windows.Controls.TextBlock]::ForegroundProperty, "MainForegroundColor")
        [void]$textPanel.Children.Add($nameText)

        $sourceText = New-Object Windows.Controls.TextBlock
        $sourceText.Text = $item.Source
        $sourceText.FontSize = 11
        $sourceText.TextTrimming = [Windows.TextTrimming]::CharacterEllipsis
        $sourceText.SetResourceReference([Windows.Controls.TextBlock]::ForegroundProperty, "MutedForegroundColor")
        [void]$textPanel.Children.Add($sourceText)
        [void]$row.Children.Add($textPanel)

        $toggle = New-Object Windows.Controls.CheckBox
        $toggle.Style = $toggleStyle
        $toggle.VerticalAlignment = [Windows.VerticalAlignment]::Center
        $toggle.IsChecked = $item.Enabled
        $toggle.Tag = $item
        [System.Windows.Automation.AutomationProperties]::SetName($toggle, $item.Name)
        [Windows.Controls.Grid]::SetColumn($toggle, 1)
        $toggle.Add_Click({
            $startupItem = $this.Tag
            $enable = [bool]$this.IsChecked
            try {
                Set-WinUtilStartupItemState -ApprovedPath $startupItem.ApprovedPath -ValueName $startupItem.ValueName -Enabled $enable
                $startupItem.Enabled = $enable
            } catch {
                $this.IsChecked = -not $enable
                Write-WinUtilLog -Level "ERROR" -Component "Startup" -Message "Unable to change startup item '$($startupItem.ValueName)': $($_.Exception.Message)"
                Show-WinUtilMessage -Message "Não foi possível alterar ""$($startupItem.Name)"":`n$($_.Exception.Message)" -Title "Azor WinUtil" -Button "OK" -Icon "Warning" | Out-Null
            }
            Update-WinUtilStartupItemSummary
        })
        [void]$row.Children.Add($toggle)

        [void]$list.Children.Add($row)
    }

    Update-WinUtilStartupItemSummary
}

function Update-WinUtilStartupItemSummary {
    <#
    .SYNOPSIS
        Updates the enabled/disabled count above the Dashboard startup list.
    #>

    if ($null -eq $sync.WPFStartupAppsSummary -or $null -eq $sync.WPFStartupAppsList) {
        return
    }

    $items = @($sync.WPFStartupAppsList.Children | ForEach-Object { $_.Children[1].Tag })
    if ($items.Count -eq 0) {
        $sync.WPFStartupAppsSummary.Text = "Nenhum programa configurado para iniciar com o Windows."
        return
    }

    $disabledCount = @($items | Where-Object { -not $_.Enabled }).Count
    $enabledCount = $items.Count - $disabledCount
    $sync.WPFStartupAppsSummary.Text = "$enabledCount ativos • $disabledCount desativados"
}

function Write-AzorWinUtilState {
    param([string]$LastAction = "Aberto", [string[]]$AppliedTweaks = @())
    try {
        New-Item -ItemType Directory -Force -Path $sync.azorCompanionDir -ErrorAction SilentlyContinue | Out-Null
        $existing = $null
        if (Test-Path -LiteralPath $sync.azorWinUtilPath) {
            try { $existing = Get-Content -LiteralPath $sync.azorWinUtilPath -Raw | ConvertFrom-Json } catch { }
        }
        $tweaks = New-Object System.Collections.Generic.List[string]
        if ($existing -and $existing.appliedTweaks) { foreach ($t in $existing.appliedTweaks) { if ($tweaks -notcontains [string]$t) { [void]$tweaks.Add([string]$t) } } }
        foreach ($t in $AppliedTweaks) { if ($t -and ($tweaks -notcontains [string]$t)) { [void]$tweaks.Add([string]$t) } }
        $apps = 0; if ($existing -and $null -ne $existing.installedApps) { $apps = [int]$existing.installedApps }
        $payload = [ordered]@{
            app           = "AzorWinUtil"
            version       = [string]$sync.version
            updatedAt     = (Get-Date).ToString("o")
            lastAction    = $LastAction
            appliedTweaks = @($tweaks)
            installedApps = $apps
        }
        $tmp = "$($sync.azorWinUtilPath).tmp"
        ($payload | ConvertTo-Json -Depth 5) | Set-Content -LiteralPath $tmp -Encoding UTF8
        Move-Item -LiteralPath $tmp -Destination $sync.azorWinUtilPath -Force
    } catch { }
}

function Write-WinUtilLog {
    <#

    .SYNOPSIS
        Writes a timestamped Azor WinUtil log entry to the active session log.

    .PARAMETER Message
        The message to write.

    .PARAMETER Level
        The severity level for the log entry.

    .PARAMETER Component
        The WinUtil component producing the log entry.

    #>
    param (
        [Parameter(Mandatory = $true)]
        [string]$Message,

        [ValidateSet("INFO", "WARN", "ERROR", "DEBUG")]
        [string]$Level = "INFO",

        [string]$Component = "WinUtil"
    )

    try {
        $logPath = $null
        $transcriptPath = $null
        if ($null -ne $sync -and $sync.ContainsKey("logPath")) {
            $logPath = $sync.logPath
        }

        if ($null -ne $sync -and $sync.ContainsKey("transcriptPath")) {
            $transcriptPath = $sync.transcriptPath
        }

        if ([string]::IsNullOrWhiteSpace($logPath) -and -not [string]::IsNullOrWhiteSpace($transcriptPath)) {
            $logPath = $transcriptPath
        }

        if ([string]::IsNullOrWhiteSpace($logPath) -and $null -ne $sync -and $sync.ContainsKey("winutildir")) {
            $logDirectory = Join-Path $sync.winutildir "logs"
            $logPath = Join-Path $logDirectory "azorwinutil_$(Get-Date -Format "yyyy-MM-dd_HH-mm-ss").log"
            $sync.logPath = $logPath
        }

        if ([string]::IsNullOrWhiteSpace($logPath) -and -not [string]::IsNullOrWhiteSpace($env:LocalAppData)) {
            if ([string]::IsNullOrWhiteSpace($script:WinUtilLogPath)) {
                $logDirectory = Join-Path (Join-Path $env:LocalAppData "azorwinutil") "logs"
                $script:WinUtilLogPath = Join-Path $logDirectory "azorwinutil_$(Get-Date -Format "yyyy-MM-dd_HH-mm-ss").log"
            }
            $logPath = $script:WinUtilLogPath
        }

        if ([string]::IsNullOrWhiteSpace($logPath)) {
            return
        }

        $logDirectory = Split-Path -Path $logPath -Parent
        if (-not (Test-Path $logDirectory)) {
            New-Item -Path $logDirectory -ItemType Directory -Force | Out-Null
        }

        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"
        $line = "[$timestamp] [$Level] [$Component] $Message"

        if (-not [string]::IsNullOrWhiteSpace($transcriptPath) -and $logPath -eq $transcriptPath) {
            Write-Host $line
            return
        }

        try {
            Add-Content -Path $logPath -Value $line -Encoding UTF8 -ErrorAction Stop
        } catch [System.IO.IOException] {
            Write-Host $line
        }
    } catch {
        Write-Warning "Unable to write WinUtil log entry: $($_.Exception.Message)"
    }
}

function Initialize-WPFUI {
    [OutputType([void])]
    param(
        [Parameter(Mandatory)]
        [string]$TargetGridName
    )

    switch ($TargetGridName) {
        "appscategory"{
            Invoke-WPFUIElements -configVariable $sync.configs.appnavigation -targetGridName "appscategory" -columncount 1

            # Create and configure a popup for displaying selected apps
            $selectedAppsPopup = New-Object Windows.Controls.Primitives.Popup
            $selectedAppsPopup.IsOpen = $false
            $selectedAppsPopup.PlacementTarget = $sync.WPFselectedAppsButton
            $selectedAppsPopup.Placement = [System.Windows.Controls.Primitives.PlacementMode]::Bottom
            $selectedAppsPopup.AllowsTransparency = $true

            # Style the popup with a border and background
            $selectedAppsBorder = New-Object Windows.Controls.Border
            $selectedAppsBorder.SetResourceReference([Windows.Controls.Control]::BackgroundProperty, "MainBackgroundColor")
            $selectedAppsBorder.SetResourceReference([Windows.Controls.Control]::BorderBrushProperty, "MainForegroundColor")
            $selectedAppsBorder.SetResourceReference([Windows.Controls.Control]::BorderThicknessProperty, "ButtonBorderThickness")
            $selectedAppsBorder.Width = 200
            $selectedAppsBorder.Padding = 5
            $selectedAppsPopup.Child = $selectedAppsBorder
            $sync.selectedAppsPopup = $selectedAppsPopup

            # Add a stack panel inside the popup's border to organize its child elements
            $sync.selectedAppsstackPanel = New-Object Windows.Controls.StackPanel
            $selectedAppsBorder.Child = $sync.selectedAppsstackPanel

            # Close selectedAppsPopup when mouse leaves both button and selectedAppsPopup
            $sync.WPFselectedAppsButton.Add_MouseLeave({
                if (-not $sync.selectedAppsPopup.IsMouseOver) {
                    $sync.selectedAppsPopup.IsOpen = $false
                }
            })
            $selectedAppsPopup.Add_MouseLeave({
                if (-not $sync.WPFselectedAppsButton.IsMouseOver) {
                    $sync.selectedAppsPopup.IsOpen = $false
                }
            })

            # Creates the popup that is displayed when the user right-clicks on an app entry
            # This popup contains buttons for installing, uninstalling, and viewing app information

            $appPopup = New-Object Windows.Controls.Primitives.Popup
            $appPopup.StaysOpen = $false
            $appPopup.Placement = [System.Windows.Controls.Primitives.PlacementMode]::Bottom
            $appPopup.AllowsTransparency = $true
            # Store the popup globally so the position can be set later
            $sync.appPopup = $appPopup

            $appPopupStackPanel = New-Object Windows.Controls.StackPanel
            $appPopupStackPanel.Orientation = "Horizontal"
            $appPopupStackPanel.Add_MouseLeave({
                $sync.appPopup.IsOpen = $false
            })
            $appPopup.Child = $appPopupStackPanel

            $appButtons = @(
            [PSCustomObject]@{ Name = "Install";    Icon = [char]0xE118 },
            [PSCustomObject]@{ Name = "Uninstall";  Icon = [char]0xE74D },
            [PSCustomObject]@{ Name = "Info";       Icon = [char]0xE946 }
            )
            foreach ($button in $appButtons) {
                $newButton = New-Object Windows.Controls.Button
                $newButton.Style = $sync.Form.Resources.AppEntryButtonStyle
                $newButton.Content = $button.Icon
                $appPopupStackPanel.Children.Add($newButton) | Out-Null

                # Dynamically load the selected app object so the buttons can be reused and do not need to be created for each app
                switch ($button.Name) {
                    "Install" {
                        $newButton.Add_MouseEnter({
                            $appObject = $sync.configs.applicationsHashtable.$($sync.appPopupSelectedApp)
                            $this.ToolTip = "Instalar ou atualizar $($appObject.content)"
                        })
                        $newButton.Add_Click({
                            $appObject = $sync.configs.applicationsHashtable.$($sync.appPopupSelectedApp)
                            Invoke-WPFInstall -PackagesToInstall $appObject
                        })
                    }
                    "Uninstall" {
                        $newButton.Add_MouseEnter({
                            $appObject = $sync.configs.applicationsHashtable.$($sync.appPopupSelectedApp)
                            $this.ToolTip = "Desinstalar $($appObject.content)"
                        })
                        $newButton.Add_Click({
                            $appObject = $sync.configs.applicationsHashtable.$($sync.appPopupSelectedApp)
                            Invoke-WPFUnInstall -PackagesToUninstall $appObject
                        })
                    }
                    "Info" {
                        $newButton.Add_MouseEnter({
                            $appObject = $sync.configs.applicationsHashtable.$($sync.appPopupSelectedApp)
                            $this.ToolTip = "Abrir o site do programa no navegador padrão`n$($appObject.link)"
                        })
                        $newButton.Add_Click({
                            $appObject = $sync.configs.applicationsHashtable.$($sync.appPopupSelectedApp)
                            Start-Process $appObject.link
                        })
                    }
                }
            }
        }
        "appspanel" {
            $sync.ItemsControl = Initialize-InstallAppArea -TargetElement $TargetGridName
            Initialize-InstallCategoryAppList -TargetElement $sync.ItemsControl -Apps $sync.configs.applicationsHashtable
        }
        default {
            Write-Output "$TargetGridName not yet implemented"
        }
    }
}


function Invoke-WinUtilAutoRun {
    <#

    .SYNOPSIS
        Runs Install, Tweaks, and Features with optional UI invocation.
    #>

    function BusyWait {
        Start-Sleep -Milliseconds 100
        while ($sync.ProcessRunning) {
            Start-Sleep -Milliseconds 100
        }
    }

    if ($sync.selectedTweaks.Count -gt 0) {
        Write-Host "Aplicando ajustes..."
        Invoke-WPFtweaksbutton
        BusyWait
    }

    if ($sync.selectedFeatures.Count -gt 0) {
        Write-Host "Aplicando recursos..."
        Invoke-WPFFeatureInstall
        BusyWait
    }

    if ($sync.selectedApps.Count -gt 0) {
        Write-Host "Instalando programas..."
        Invoke-WPFInstall
        BusyWait
    }

    if ($sync.selectedAppx.Count -gt 0) {
        Write-Host "Removendo pacotes AppX..."
        Invoke-WPFAppxRemoval
        BusyWait
    }

    Write-Host "Concluído."
}

function Invoke-WPFAppxInstall {
    if ($sync.ProcessRunning) {
        Show-WinUtilMessage -Message "Já existe um processo de AppX em andamento." -Title "Azor WinUtil" -Button "OK" -Icon "Warning"
        return
    }

    if ($null -eq $sync.selectedAppx -or $sync.selectedAppx.Count -eq 0) {
        Show-WinUtilMessage -Message "Nenhum pacote AppX selecionado." -Title "Erro" -Button "OK" -Icon "Error"
        return
    }

    $selected = @($sync.selectedAppx)
    $apps = $sync.configs.appxHashtable

    $sync.ProcessRunning = $true
    Invoke-WPFRunspace -ParameterList @(("selected", $selected), ("apps", $apps)) -ScriptBlock {
        param($selected, $apps)

        $totalPackages = @($selected).Count
        $hasUI = $null -ne $sync.Form -and $null -ne $sync.Form.Dispatcher

        try {
            Write-WinUtilLog -Component "AppX" -Message "Starting AppX install for $totalPackages selected package(s)."
            if ($hasUI) {
                Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Preparando a instalação de AppX (0/$totalPackages)" -Percent 0
                Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "Normal" -value 0.01 -overlay "logo" }
            }

            for ($index = 0; $index -lt $totalPackages; $index++) {
                $key = $selected[$index]
                $app = $apps[$key]
                $position = $index + 1
                $startPercent = [int](($index / $totalPackages) * 100)

                if ($hasUI) {
                    Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Instalando $($app.Content) ($position/$totalPackages)" -Percent $startPercent
                }
                Write-Host "Instalando $($app.Content)"
                Install-WinUtilAPPX -Name $app.PackageId -StoreId $app.StoreId

                $completedPercent = [int](($position / $totalPackages) * 100)
                if ($hasUI) {
                    Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Instalado: $($app.Content) ($position/$totalPackages)" -Percent $completedPercent
                    Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -value ($completedPercent / 100) }
                }
            }

            Write-Host "================================="
            Write-Host "-- Instalação de AppX concluída --"
            Write-Host "================================="
            Write-WinUtilLog -Component "AppX" -Message "AppX install finished."
            if ($hasUI) {
                Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Instalação de AppX concluída" -Percent 100
                Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "None" -overlay "checkmark" }
            }
        }
        catch {
            Write-WinUtilLog -Level "ERROR" -Component "AppX" -Message "AppX install failed: $($_.Exception.Message)"
            if ($hasUI) {
                Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Falha na instalação de AppX" -Percent 100
                Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "Error" -overlay "warning" }
            }
        }
        finally {
            $sync.ProcessRunning = $false
        }
    }
}

function Invoke-WPFAppxRemoval {
    if ($sync.ProcessRunning) {
        Show-WinUtilMessage -Message "Já existe um processo de AppX em andamento." -Title "Azor WinUtil" -Button "OK" -Icon "Warning"
        return
    }

    if ($null -eq $sync.selectedAppx -or $sync.selectedAppx.Count -eq 0) {
        Show-WinUtilMessage -Message "Nenhum pacote AppX selecionado." -Title "Erro" -Button "OK" -Icon "Error"
        return
    }

    $selected = @($sync.selectedAppx)
    $apps = $sync.configs.appxHashtable

    $sync.ProcessRunning = $true
    Invoke-WPFRunspace -ParameterList @(("selected", $selected), ("apps", $apps)) -ScriptBlock {
        param($selected, $apps)

        $totalPackages = @($selected).Count
        $hasUI = $null -ne $sync.Form -and $null -ne $sync.Form.Dispatcher
        $packageList = [System.Collections.Generic.List[string]]::new()

        try {
            Write-WinUtilLog -Component "AppX" -Message "Starting AppX removal for $totalPackages selected package(s)."
            if ($hasUI) {
                Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Preparando a remoção de AppX (0/$totalPackages)" -Percent 0
                Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "Normal" -value 0.01 -overlay "logo" }
            }

            for ($index = 0; $index -lt $totalPackages; $index++) {
                $key = $selected[$index]
                $app = $apps[$key]
                $position = $index + 1
                $startPercent = [int](($index / $totalPackages) * 90)
                if ($hasUI) {
                    Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Removendo $($app.Content) ($position/$totalPackages)" -Percent $startPercent
                }

                if ($key -eq "WPFAppxMicrosoft_WindowsNotepad") {
                    Write-WinUtilLog -Component "AppX" -Message "Stopping dllhost before removing Notepad."
                    Stop-Process -Name dllhost -Force -Confirm:$false -ErrorAction SilentlyContinue
                }

                Write-Host "Removendo $($app.Content)"
                Write-WinUtilLog -Component "AppX" -Message "Removing $($app.Content) ($($app.PackageId))."
                Remove-WinUtilAPPX -Name $app.PackageId
                $packageList.Add($app.PackageId)

                if ($key -eq "WPFAppxMSTeams") {
                    # Uninstalls Microsoft Teams Meeting Add-in for Microsoft Office
                    Write-WinUtilLog -Component "AppX" -Message "Uninstalling Microsoft Teams meeting add-in package."
                    Get-Package -Name "Microsoft Teams*" -ErrorAction SilentlyContinue | Uninstall-Package -Force
                }

                $completedPercent = [int](($position / $totalPackages) * 90)
                if ($hasUI) {
                    Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Removido: $($app.Content) ($position/$totalPackages)" -Percent $completedPercent
                    Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -value ($completedPercent / 100) }
                }
            }

            if ($packageList.Count -gt 0) {
                if ($hasUI) {
                    Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Removendo pacotes AppX provisionados" -Percent 90
                }
                Remove-WinUtilProvisionedAPPX -PackageList $packageList.ToArray()
            }

            Write-Host "================================="
            Write-Host "--  Remoção de AppX concluída  --"
            Write-Host "================================="
            Write-WinUtilLog -Component "AppX" -Message "AppX removal finished."
            if ($hasUI) {
                Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Remoção de AppX concluída" -Percent 100
                Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "None" -overlay "checkmark" }
            }
        }
        catch {
            Write-WinUtilLog -Level "ERROR" -Component "AppX" -Message "AppX removal failed: $($_.Exception.Message)"
            if ($hasUI) {
                Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Falha na remoção de AppX" -Percent 100
                Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "Error" -overlay "warning" }
            }
        }
        finally {
            $sync.ProcessRunning = $false
        }

    } | Out-Null
}

function Invoke-WPFAzorUltra {
    <#
    .SYNOPSIS
        Selects the "Super Agressivo" preset: debloat tweaks plus the AppX packages to remove.

    .DESCRIPTION
        Only selects the checkboxes, in both the Tweaks and the AppX Removal tabs. Nothing is applied
        here: the user still clicks "Executar Ajustes" and, for the packages, "Remover Selecionados".
    #>

    $preset = @($sync.configs.preset.SuperAgressivo)
    if ($preset.Count -eq 0) {
        Show-WinUtilMessage -Message "A seleção Super Agressivo não foi encontrada na configuração." -Title "Erro" -Button "OK" -Icon "Error" | Out-Null
        return
    }

    $tweakCount = @($preset | Where-Object { $_ -like "WPFTweaks*" }).Count
    $appxCount = @($preset | Where-Object { $_ -like "WPFAppx*" }).Count

    $message = @"
Este modo MARCA $tweakCount ajustes e $appxCount aplicativos para remoção. Nada é aplicado agora.

O que ele faz:
- Desliga e remove o Copilot, o Recall e a IA do Windows, e ainda bloqueia por política oficial
- Corta telemetria, histórico de atividades, recursos de consumidor e apps em segundo plano
- Remove widgets, sugestões da Store, notificações, Início e Galeria do Explorador
- Marca os apps de bloatware (Bing, Teams, Outlook, Clipchamp, Copilot e companhia)
- Aplica os ajustes de desempenho e jogos do Azor

O que deixei de fora de propósito:
- Remover o Edge e o OneDrive (risco de perder arquivos e quebrar apps que usam o WebView)
- Desativar o BitLocker (é proteção dos seus dados)
- Remover Calculadora, Paint, Bloco de Notas, Fotos, Câmera e Captura
- Qualquer coisa que os anti-cheats de Valorant, LoL, Fortnite, CS2 e CoD Warzone exigem: TPM, Secure Boot, serviços de anti-cheat, rede Xbox (Teredo), Game Bar e login Xbox continuam intocados. Para conferir o PC, use o Checkup para Jogos no Painel

Continuar e marcar tudo?
"@

    $confirm = Show-WinUtilMessage -Message $message -Title "Azor WinUtil - Super Agressivo" -Button "YesNo" -Icon "Warning"
    if ($confirm -ne "Yes") {
        return
    }

    Invoke-WPFPresets "SuperAgressivo" -checkboxfilterpattern "WPFTweak*"
    Invoke-WPFPresets "SuperAgressivo" -checkboxfilterpattern "WPFAppx*"
    Write-WinUtilLog -Component "Tweaks" -Message "Super Agressivo preset selected: $tweakCount tweaks, $appxCount AppX packages."

    Show-WinUtilMessage -Message @"
Marquei $tweakCount ajustes aqui na aba Otimizar e $appxCount aplicativos na aba Remover AppX.

Para aplicar:
1) Clique em Executar Ajustes
2) Depois clique em Remover AppX e em Remover Selecionados

Os ajustes de registro e serviços podem ser revertidos em Desfazer Ajustes Selecionados. Aplicativos removidos só voltam pela Microsoft Store, e reiniciar o PC no fim é recomendado.
"@ -Title "Azor WinUtil - Super Agressivo" -Button "OK" -Icon "Information" | Out-Null
}

function Invoke-WPFButton {

    <#

    .SYNOPSIS
        Invokes the function associated with the clicked button

    .PARAMETER Button
        The name of the button that was clicked

    #>

    Param ([string]$Button)

    # Use this to get the name of the button
    #[System.Windows.MessageBox]::Show("$Button","Azor WinUtil","OK","Info")
    if (-not $sync.ProcessRunning) {
        Set-WinUtilTweaksProgressIndicator -Visible $false
    }

    # Check if button is defined in feature config with function or InvokeScript
    if ($sync.configs.feature.$Button) {
        $buttonConfig = $sync.configs.feature.$Button

        # If button has a function defined, call it
        if ($buttonConfig.function) {
            $functionName = $buttonConfig.function
            if (Get-Command $functionName -ErrorAction SilentlyContinue) {
                & $functionName
                return
            }
        }

        # If button has InvokeScript defined, execute the scripts
        if ($buttonConfig.InvokeScript -and $buttonConfig.InvokeScript.Count -gt 0) {
            foreach ($script in $buttonConfig.InvokeScript) {
                if (-not [string]::IsNullOrWhiteSpace($script)) {
                    Invoke-Command -ScriptBlock ([scriptblock]::Create($script)) -ErrorAction Stop
                }
            }
            return
        }
    }

    # Fallback to hard-coded switch for buttons not in feature.json
    Switch -Wildcard ($Button) {
        "WPFTab?BT" {Invoke-WPFTab $Button}
        "WPFInstall" {Invoke-WPFInstall}
        "WPFUninstall" {Invoke-WPFUnInstall}
        "WPFInstallUpgrade" {Invoke-WPFInstallUpgrade}
        "WPFCollapseAllCategories" {Invoke-WPFToggleAllCategories -Action "Collapse"}
        "WPFExpandAllCategories" {Invoke-WPFToggleAllCategories -Action "Expand"}
        "WPFStandard" {Invoke-WPFPresets "Standard" -checkboxfilterpattern "WPFTweak*"}
        "WPFGaming" {Invoke-WPFPresets "Gaming" -checkboxfilterpattern "WPFTweak*"}
        "WPFAzorUltra" {Invoke-WPFAzorUltra}
        "WPFClearTweaksSelection" {Invoke-WPFPresets -imported $true -checkboxfilterpattern "WPFTweak*"}
        "WPFClearInstallSelection" {Invoke-WPFPresets -imported $true -checkboxfilterpattern "WPFInstall*"}
        "WPFtweaksbutton" {Invoke-WPFtweaksbutton}
        "WPFAddUltPerf" {Invoke-WPFUltimatePerformance -Enable}
        "WPFRemoveUltPerf" {Invoke-WPFUltimatePerformance}
        "WPFundoall" {Invoke-WPFundoall}
        "WPFGetInstalled" {Invoke-WPFGetInstalled -CheckBox "winget"}
        "WPFGetInstalledTweaks" {Invoke-WPFGetInstalled -CheckBox "tweaks"}
        "WPFAppxRemoval" {Invoke-WPFTab "WPFTab6BT"}
        "WPFBackToTweaks" {Invoke-WPFTab "WPFTab2BT"}
        "WPFInstallSelectedAppx" {Invoke-WPFAppxInstall}
        "WPFRemoveSelectedAppx" {Invoke-WPFAppxRemoval}
        "WPFDefaultAppxSelection" {Invoke-WPFPresets "AppxDefault" -checkboxfilterpattern "WPFAppx*"}
        "WPFSelectAllAppx" {
            $sync.configs.appxHashtable.Keys | ForEach-Object {$sync.$_.IsChecked = $true}
        }
        "WPFClearAppxSelection" {
            $sync.configs.appxHashtable.Keys | ForEach-Object {$sync.$_.IsChecked = $false}
        }
        "WPFGetInstalledAppx" {
            $installedAppxPackages = Get-WinUtilInstalledAPPX
            foreach ($appx in $sync.configs.appxHashtable.GetEnumerator()) {
                if ($appx.Value.PackageId -in $installedAppxPackages) {
                    $sync.$($appx.Key).IsChecked = $true
                }
            }
        }
        "WPFQuickOptimize" {Invoke-WPFQuickOptimize}
        "WPFQuickCleanup" {Invoke-WPFQuickCleanup}
        "WPFQuickRestorePoint" {Invoke-WPFQuickRestorePoint}
        "WPFQuickGamingPreset" {Invoke-WPFQuickGamingPreset}
        "WPFQuickUltimatePower" {Invoke-WPFUltimatePerformance -Enable}
        "WPFQuickUpgradeApps" {Invoke-WPFInstallUpgrade}
        "WPFQuickRepair" {Invoke-WPFSystemRepair}
        "WPFQuickGameCompat" {Invoke-WPFQuickGameCompat}
        "WPFDashboardAlertFix" {Invoke-WPFQuickGameCompat}
        "WPFQuickOpenLogs" {Start-Process -FilePath (Join-Path $sync.winutildir "logs")}
        "WPFQuickAzorRate" {Invoke-WPFQuickAzorApp -App "Rate"}
        "WPFQuickAzorOptimization" {Invoke-WPFQuickAzorApp -App "Optimization"}
        "WPFStartupAppsRefresh" {Update-WinUtilStartupItemList}
        "WPFCloseButton" {$sync.Form.Close(); Write-Host "Até mais!"}
        "WPFMinimizeButton" {[Windows.SystemCommands]::MinimizeWindow($sync.Form)}
        "WPFMaximizeButton" {
            if ($sync.Form.WindowState -eq [Windows.WindowState]::Normal) {
                [Windows.SystemCommands]::MaximizeWindow($sync.Form)
            } else {
                [Windows.SystemCommands]::RestoreWindow($sync.Form)
            }
        }
        "WPFselectedAppsButton" {$sync.selectedAppsPopup.IsOpen = -not $sync.selectedAppsPopup.IsOpen}
    }
}

function Invoke-WPFFeatureInstall {
    <#

    .SYNOPSIS
        Installs selected Windows Features

    #>

    if($sync.ProcessRunning) {
        $msg = "Já existe um processo em andamento. Aguarde a conclusão."
        [System.Windows.MessageBox]::Show($msg, "Azor WinUtil", [System.Windows.MessageBoxButton]::OK, [System.Windows.MessageBoxImage]::Warning)
        return
    }

    Invoke-WPFRunspace -ScriptBlock {
        $Features = $sync.selectedFeatures
        $sync.ProcessRunning = $true
        if ($Features.count -eq 1) {
            Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "Indeterminate" -value 0.01 -overlay "logo" }
        } else {
            Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "Normal" -value 0.01 -overlay "logo" }
        }

        $x = 0

        $Features | ForEach-Object {
            Invoke-WinUtilFeatureInstall $_
            $X++
            Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -value ($x/$Features.Count) }
        }

        $sync.ProcessRunning = $false
        Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "None" -overlay "checkmark" }

        Write-Host "==================================="
        Write-Host "---     Recursos instalados     ---"
        Write-Host "---  Pode ser preciso reiniciar ---"
        Write-Host "==================================="
    } | Out-Null
}

function Invoke-WPFFixesNetwork {
    netsh winsock reset
    netsh int ip reset
    Write-Host "Network Configuration has been Reset. Please restart your computer."
}

function Invoke-WPFFixesUpdate {

    <#

    .SYNOPSIS
        Performs various tasks in an attempt to repair Windows Update

    .DESCRIPTION
        1. (Aggressive Only) Scans the system for corruption using the Invoke-WPFSystemRepair function
        2. Stops Windows Update Services
        3. Remove the QMGR Data file, which stores BITS jobs
        4. (Aggressive Only) Renames the DataStore and CatRoot2 folders
            DataStore - Contains the Windows Update History and Log Files
            CatRoot2 - Contains the Signatures for Windows Update Packages
        5. Renames the Windows Update Download Folder
        6. Deletes the Windows Update Log
        7. (Aggressive Only) Resets the Security Descriptors on the Windows Update Services
        8. Reregisters the BITS and Windows Update DLLs
        9. Removes the WSUS client settings
        10. Resets WinSock
        11. Gets and deletes all BITS jobs
        12. Sets the startup type of the Windows Update Services then starts them
        13. Forces Windows Update to check for updates

    .PARAMETER Aggressive
        If specified, the script will take additional steps to repair Windows Update that are more dangerous, take a significant amount of time, or are generally unnecessary

    #>

    param($Aggressive = $false)

    Write-Progress -Id 0 -Activity "Repairing Windows Update" -PercentComplete 0
    Set-WinUtilTaskbaritem -state "Indeterminate" -overlay "logo"
    Write-Host "Starting Windows Update Repair..."
    # Wait for the first progress bar to show, otherwise the second one won't show
    Start-Sleep -Milliseconds 200

    if ($Aggressive) {
        Invoke-WPFSystemRepair
    }


    Write-Progress -Id 0 -Activity "Repairing Windows Update" -Status "Stopping Windows Update Services..." -PercentComplete 10
    # Stop the Windows Update Services
    Write-Progress -Id 2 -ParentId 0 -Activity "Stopping Services" -Status "Stopping BITS..." -PercentComplete 0
    Stop-Service -Name BITS -Force
    Write-Progress -Id 2 -ParentId 0 -Activity "Stopping Services" -Status "Stopping wuauserv..." -PercentComplete 20
    Stop-Service -Name wuauserv -Force
    Write-Progress -Id 2 -ParentId 0 -Activity "Stopping Services" -Status "Stopping appidsvc..." -PercentComplete 40
    Stop-Service -Name appidsvc -Force
    Write-Progress -Id 2 -ParentId 0 -Activity "Stopping Services" -Status "Stopping cryptsvc..." -PercentComplete 60
    Stop-Service -Name cryptsvc -Force
    Write-Progress -Id 2 -ParentId 0 -Activity "Stopping Services" -Status "Completed" -PercentComplete 100


    # Remove the QMGR Data file
    Write-Progress -Id 0 -Activity "Repairing Windows Update" -Status "Renaming/Removing Files..." -PercentComplete 20
    Write-Progress -Id 3 -ParentId 0 -Activity "Renaming/Removing Files" -Status "Removing QMGR Data files..." -PercentComplete 0
    Remove-Item "$env:allusersprofile\Application Data\Microsoft\Network\Downloader\qmgr*.dat" -ErrorAction SilentlyContinue


    if ($Aggressive) {
        # Rename the Windows Update Log and Signature Folders
        Write-Progress -Id 3 -ParentId 0 -Activity "Renaming/Removing Files" -Status "Renaming the Windows Update Log, Download, and Signature Folder..." -PercentComplete 20
        Rename-Item $env:systemroot\SoftwareDistribution\DataStore DataStore.bak -ErrorAction SilentlyContinue
        Rename-Item $env:systemroot\System32\Catroot2 catroot2.bak -ErrorAction SilentlyContinue
    }

    # Rename the Windows Update Download Folder
    Write-Progress -Id 3 -ParentId 0 -Activity "Renaming/Removing Files" -Status "Renaming the Windows Update Download Folder..." -PercentComplete 20
    Rename-Item $env:systemroot\SoftwareDistribution\Download Download.bak -ErrorAction SilentlyContinue

    # Delete the legacy Windows Update Log
    Write-Progress -Id 3 -ParentId 0 -Activity "Renaming/Removing Files" -Status "Removing the old Windows Update log..." -PercentComplete 80
    Remove-Item $env:systemroot\WindowsUpdate.log -ErrorAction SilentlyContinue
    Write-Progress -Id 3 -ParentId 0 -Activity "Renaming/Removing Files" -Status "Completed" -PercentComplete 100


    if ($Aggressive) {
        # Reset the Security Descriptors on the Windows Update Services
        Write-Progress -Id 0 -Activity "Repairing Windows Update" -Status "Resetting the WU Service Security Descriptors..." -PercentComplete 25
        Write-Progress -Id 4 -ParentId 0 -Activity "Resetting the WU Service Security Descriptors" -Status "Resetting the BITS Security Descriptor..." -PercentComplete 0
        Start-Process -NoNewWindow -FilePath "sc.exe" -ArgumentList "sdset", "bits", "D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)(A;;CCLCSWLOCRRC;;;AU)(A;;CCLCSWRPWPDTLOCRRC;;;PU)" -Wait
        Write-Progress -Id 4 -ParentId 0 -Activity "Resetting the WU Service Security Descriptors" -Status "Resetting the wuauserv Security Descriptor..." -PercentComplete 50
        Start-Process -NoNewWindow -FilePath "sc.exe" -ArgumentList "sdset", "wuauserv", "D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)(A;;CCLCSWLOCRRC;;;AU)(A;;CCLCSWRPWPDTLOCRRC;;;PU)" -Wait
        Write-Progress -Id 4 -ParentId 0 -Activity "Resetting the WU Service Security Descriptors" -Status "Completed" -PercentComplete 100
    }


    # Reregister the BITS and Windows Update DLLs
    Write-Progress -Id 0 -Activity "Repairing Windows Update" -Status "Reregistering DLLs..." -PercentComplete 40
    $oldLocation = Get-Location
    Set-Location $env:systemroot\system32
    $i = 0
    $DLLs = @(
        "atl.dll", "urlmon.dll", "mshtml.dll", "shdocvw.dll", "browseui.dll",
        "jscript.dll", "vbscript.dll", "scrrun.dll", "msxml.dll", "msxml3.dll",
        "msxml6.dll", "actxprxy.dll", "softpub.dll", "wintrust.dll", "dssenh.dll",
        "rsaenh.dll", "gpkcsp.dll", "sccbase.dll", "slbcsp.dll", "cryptdlg.dll",
        "oleaut32.dll", "ole32.dll", "shell32.dll", "initpki.dll", "wuapi.dll",
        "wuaueng.dll", "wuaueng1.dll", "wucltui.dll", "wups.dll", "wups2.dll",
        "wuweb.dll", "qmgr.dll", "qmgrprxy.dll", "wucltux.dll", "muweb.dll", "wuwebv.dll"
    )
    foreach ($dll in $DLLs) {
        Write-Progress -Id 5 -ParentId 0 -Activity "Reregistering DLLs" -Status "Registering $dll..." -PercentComplete ($i / $DLLs.Count * 100)
        $i++
        Start-Process -NoNewWindow -FilePath "regsvr32.exe" -ArgumentList "/s", $dll
    }
    Set-Location $oldLocation
    Write-Progress -Id 5 -ParentId 0 -Activity "Reregistering DLLs" -Status "Completed" -PercentComplete 100


    # Remove the WSUS client settings
    if (Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate") {
        Write-Progress -Id 0 -Activity "Repairing Windows Update" -Status "Removing WSUS client settings..." -PercentComplete 60
        Write-Progress -Id 6 -ParentId 0 -Activity "Removing WSUS client settings" -PercentComplete 0
        Remove-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate" -Name "AccountDomainSid" -ErrorAction SilentlyContinue
        Remove-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate" -Name "PingID" -ErrorAction SilentlyContinue
        Remove-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate" -Name "SusClientId" -ErrorAction SilentlyContinue
        Write-Progress -Id 6 -ParentId 0 -Activity "Removing WSUS client settings" -Status "Completed" -PercentComplete 100
    }

    # Remove Group Policy Windows Update settings
    Write-Progress -Id 0 -Activity "Repairing Windows Update" -Status "Removing Group Policy Windows Update settings..." -PercentComplete 60
    Write-Progress -Id 7 -ParentId 0 -Activity "Removing Group Policy Windows Update settings" -PercentComplete 0
    Remove-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate" -Name "ExcludeWUDriversInQualityUpdate" -ErrorAction SilentlyContinue
    Write-Host "Defaulting driver offering through Windows Update..."
    Remove-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\Device Metadata" -Name "PreventDeviceMetadataFromNetwork" -ErrorAction SilentlyContinue
    Remove-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\DriverSearching" -Name "DontPromptForWindowsUpdate" -ErrorAction SilentlyContinue
    Remove-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\DriverSearching" -Name "DontSearchWindowsUpdate" -ErrorAction SilentlyContinue
    Remove-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\DriverSearching" -Name "DriverUpdateWizardWuSearchEnabled" -ErrorAction SilentlyContinue
    Remove-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate" -Name "ExcludeWUDriversInQualityUpdate" -ErrorAction SilentlyContinue
    Write-Host "Defaulting Windows Update automatic restart..."
    Remove-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" -Name "NoAutoRebootWithLoggedOnUsers" -ErrorAction SilentlyContinue
    Remove-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" -Name "AUPowerManagement" -ErrorAction SilentlyContinue
    Write-Host "Clearing ANY Windows Update Policy settings..."
    Remove-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" -Name "BranchReadinessLevel" -ErrorAction SilentlyContinue
    Remove-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" -Name "DeferFeatureUpdatesPeriodInDays" -ErrorAction SilentlyContinue
    Remove-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" -Name "DeferQualityUpdatesPeriodInDays" -ErrorAction SilentlyContinue
    Remove-Item -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "HKCU:\Software\Microsoft\WindowsSelfHost" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "HKCU:\Software\Policies" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "HKLM:\Software\Microsoft\Policies" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "HKLM:\Software\Microsoft\Windows\CurrentVersion\Policies" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "HKLM:\Software\Microsoft\Windows\CurrentVersion\WindowsStore\WindowsUpdate" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "HKLM:\Software\Microsoft\WindowsSelfHost" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "HKLM:\Software\Policies" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "HKLM:\Software\WOW6432Node\Microsoft\Policies" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Policies" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\WindowsStore\WindowsUpdate" -Recurse -Force -ErrorAction SilentlyContinue
    Start-Process -NoNewWindow -FilePath "secedit" -ArgumentList "/configure", "/cfg", "$env:windir\inf\defltbase.inf", "/db", "defltbase.sdb", "/verbose" -Wait
    Start-Process -NoNewWindow -FilePath "cmd.exe" -ArgumentList "/c RD /S /Q $env:WinDir\System32\GroupPolicyUsers" -Wait
    Start-Process -NoNewWindow -FilePath "cmd.exe" -ArgumentList "/c RD /S /Q $env:WinDir\System32\GroupPolicy" -Wait
    Start-Process -NoNewWindow -FilePath "gpupdate" -ArgumentList "/force" -Wait
    Write-Progress -Id 7 -ParentId 0 -Activity "Removing Group Policy Windows Update settings" -Status "Completed" -PercentComplete 100


    # Reset WinSock
    Write-Progress -Id 0 -Activity "Repairing Windows Update" -Status "Resetting WinSock..." -PercentComplete 65
    Write-Progress -Id 7 -ParentId 0 -Activity "Resetting WinSock" -Status "Resetting WinSock..." -PercentComplete 0
    Start-Process -NoNewWindow -FilePath "netsh" -ArgumentList "winsock", "reset"
    Start-Process -NoNewWindow -FilePath "netsh" -ArgumentList "winhttp", "reset", "proxy"
    Start-Process -NoNewWindow -FilePath "netsh" -ArgumentList "int", "ip", "reset"
    Write-Progress -Id 7 -ParentId 0 -Activity "Resetting WinSock" -Status "Completed" -PercentComplete 100


    # Get and delete all BITS jobs
    Write-Progress -Id 0 -Activity "Repairing Windows Update" -Status "Deleting BITS jobs..." -PercentComplete 75
    Write-Progress -Id 8 -ParentId 0 -Activity "Deleting BITS jobs" -Status "Deleting BITS jobs..." -PercentComplete 0
    Get-BitsTransfer | Remove-BitsTransfer
    Write-Progress -Id 8 -ParentId 0 -Activity "Deleting BITS jobs" -Status "Completed" -PercentComplete 100


    # Change the startup type of the Windows Update Services and start them
    Write-Progress -Id 0 -Activity "Repairing Windows Update" -Status "Starting Windows Update Services..." -PercentComplete 90
    Write-Progress -Id 9 -ParentId 0 -Activity "Starting Windows Update Services" -Status "Starting BITS..." -PercentComplete 0
    Get-Service BITS | Set-Service -StartupType Manual -PassThru | Start-Service
    Write-Progress -Id 9 -ParentId 0 -Activity "Starting Windows Update Services" -Status "Starting wuauserv..." -PercentComplete 25
    Get-Service wuauserv | Set-Service -StartupType Manual -PassThru | Start-Service
    Write-Progress -Id 9 -ParentId 0 -Activity "Starting Windows Update Services" -Status "Starting AppIDSvc..." -PercentComplete 50
    # The AppIDSvc service is protected, so the startup type has to be changed in the registry
    Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\AppIDSvc" -Name "Start" -Value "3" # Manual
    Start-Service AppIDSvc
    Write-Progress -Id 9 -ParentId 0 -Activity "Starting Windows Update Services" -Status "Starting CryptSvc..." -PercentComplete 75
    Get-Service CryptSvc | Set-Service -StartupType Manual -PassThru | Start-Service
    Write-Progress -Id 9 -ParentId 0 -Activity "Starting Windows Update Services" -Status "Completed" -PercentComplete 100


    # Force Windows Update to check for updates
    Write-Progress -Id 0 -Activity "Repairing Windows Update" -Status "Forcing discovery..." -PercentComplete 95
    Write-Progress -Id 10 -ParentId 0 -Activity "Forcing discovery" -Status "Forcing discovery..." -PercentComplete 0
    try {
        (New-Object -ComObject Microsoft.Update.AutoUpdate).DetectNow()
    } catch {
        Set-WinUtilTaskbaritem -state "Error" -overlay "warning"
        Write-Warning "Failed to create Windows Update COM object: $_"
    }
    Start-Process -NoNewWindow -FilePath "wuauclt" -ArgumentList "/resetauthorization", "/detectnow"
    Write-Progress -Id 10 -ParentId 0 -Activity "Forcing discovery" -Status "Completed" -PercentComplete 100
    Write-Progress -Id 0 -Activity "Repairing Windows Update" -Status "Completed" -PercentComplete 100

    Set-WinUtilTaskbaritem -state "None" -overlay "checkmark"

    $ButtonType = [System.Windows.MessageBoxButton]::OK
    $MessageboxTitle = "Redefinir o Windows Update"
    $Messageboxbody = ("As configurações padrão do Windows Update foram restauradas.`nReinicie o computador.")
    $MessageIcon = [System.Windows.MessageBoxImage]::Information

    [System.Windows.MessageBox]::Show($Messageboxbody, $MessageboxTitle, $ButtonType, $MessageIcon)
    Write-Host "==============================================="
    Write-Host "--  Windows Update redefinido para o padrão  --"
    Write-Host "==============================================="

    # Remove the progress bars
    Write-Progress -Id 0 -Activity "Repairing Windows Update" -Completed
    Write-Progress -Id 1 -Activity "Scanning for corruption" -Completed
    Write-Progress -Id 2 -Activity "Stopping Services" -Completed
    Write-Progress -Id 3 -Activity "Renaming/Removing Files" -Completed
    Write-Progress -Id 4 -Activity "Resetting the WU Service Security Descriptors" -Completed
    Write-Progress -Id 5 -Activity "Reregistering DLLs" -Completed
    Write-Progress -Id 6 -Activity "Removing Group Policy Windows Update settings" -Completed
    Write-Progress -Id 7 -Activity "Resetting WinSock" -Completed
    Write-Progress -Id 8 -Activity "Deleting BITS jobs" -Completed
    Write-Progress -Id 9 -Activity "Starting Windows Update Services" -Completed
    Write-Progress -Id 10 -Activity "Forcing discovery" -Completed
}

function Invoke-WPFFixesWinget {

    <#

    .SYNOPSIS
        Fixes WinGet by running `choco install winget`
    .DESCRIPTION
        BravoNorris for the fantastic idea of a button to reinstall WinGet
    #>
    # Install Choco if not already present
    try {
        Set-WinUtilTaskbaritem -state "Indeterminate" -overlay "logo"
        Write-Host "==> Starting WinGet Repair"
        Install-WinUtilWinget
    } catch {
        Write-Error "Failed to install WinGet: $_"
        Set-WinUtilTaskbaritem -state "Error" -overlay "warning"
    } finally {
        Write-Host "==> Finished WinGet Repair"
        Set-WinUtilTaskbaritem -state "None" -overlay "checkmark"
    }

}

function Invoke-WPFGetInstalled {
    <#
    .SYNOPSIS
        Invokes the function that gets the checkboxes to check in a new runspace

    .PARAMETER checkbox
        Indicates whether to check for installed 'winget' programs or applied 'tweaks'

    #>
    param($checkbox)
    if ($sync.ProcessRunning) {
        $msg = "Já existe um processo em andamento. Aguarde a conclusão."
        [System.Windows.MessageBox]::Show($msg, "Azor WinUtil", [System.Windows.MessageBoxButton]::OK, [System.Windows.MessageBoxImage]::Warning)
        return
    }

    if (($sync.ChocoRadioButton.IsChecked -eq $false) -and ((Test-WinUtilPackageManager -winget) -eq "not-installed") -and $checkbox -eq "winget") {
        return
    }
    $managerPreference = $sync.preferences.packagemanager
    $operation = [Hashtable]::Synchronized(@{
        Checkboxes = @()
        Error = $null
    })
    $completeAction = [Action[hashtable, string]]{
        param(
            [hashtable]$completedOperation,
            [string]$completedCheckbox
        )
        try {
            if ($completedOperation.Error) {
                Write-WinUtilLog -Level "ERROR" -Component "Install" -Message "Get installed state failed: $($completedOperation.Error)"
                Write-Warning "Unable to get installed state: $($completedOperation.Error)"
                return
            }

            if ($completedCheckbox -eq "winget") {
                foreach ($checkboxName in $completedOperation.Checkboxes) {
                    if (-not $sync.selectedApps.Contains($checkboxName)) {
                        $sync.selectedApps.Add($checkboxName)
                    }
                }
                Reset-WPFCheckBoxes -checkboxfilterpattern "WPFInstall*"
            } else {
                foreach ($checkboxName in $completedOperation.Checkboxes) {
                    $sync.$checkboxName.ischecked = $True
                }
            }
        } finally {
            $sync.ProcessRunning = $false
            Set-WinUtilTaskbaritem -state "None"
        }
    }

    $sync.ProcessRunning = $true
    Set-WinUtilTaskbaritem -state "Indeterminate"
    try {
        Invoke-WPFRunspace -ParameterList @(
            ("managerPreference", $managerPreference),
            ("checkbox", $checkbox),
            ("operation", $operation),
            ("completeAction", $completeAction)
        ) -ScriptBlock {
            param (
                [string]$checkbox,
                [string]$managerPreference,
                [hashtable]$operation,
                [Action[hashtable, string]]$completeAction
            )
            try {
                if ($checkbox -eq "winget") {
                    switch ($managerPreference) {
                        "Choco" { $operation.Checkboxes = @(Invoke-WinUtilCurrentSystem -CheckBox "choco"); break }
                        "Winget" { $operation.Checkboxes = @(Invoke-WinUtilCurrentSystem -CheckBox $checkbox); break }
                    }
                } elseif ($checkbox -eq "tweaks") {
                    $operation.Checkboxes = @(Invoke-WinUtilCurrentSystem -CheckBox $checkbox)
                }
            } catch {
                $operation.Error = $_.Exception.Message
            } finally {
                $sync.Form.Dispatcher.BeginInvoke($completeAction, [object[]]@($operation, $checkbox)) | Out-Null
            }
        }
    } catch {
        $operation.Error = $_.Exception.Message
        $completeAction.Invoke($operation, $checkbox)
    }
}

function Invoke-WPFImpex {
    <#

    .SYNOPSIS
        Handles importing and exporting of the checkboxes checked for the tweaks section

    .PARAMETER type
        Indicates whether to 'import' or 'export'

    .PARAMETER checkbox
        The checkbox to export to a file or apply the imported file to

    .EXAMPLE
        Invoke-WPFImpex -type "export"

    #>
    param(
        $type,
        $Config = $null
    )

    function ConfigDialog {
        if (!$Config) {
            switch ($type) {
                "export" { $FileBrowser = New-Object System.Windows.Forms.SaveFileDialog }
                "import" { $FileBrowser = New-Object System.Windows.Forms.OpenFileDialog }
            }
            $FileBrowser.InitialDirectory = [Environment]::GetFolderPath('Desktop')
            $FileBrowser.Filter = "Arquivos JSON (*.json)|*.json"
            $FileBrowser.ShowDialog() | Out-Null

            if ($FileBrowser.FileName -eq "") {
                return $null
            } else {
                return $FileBrowser.FileName
            }
        } else {
            return $Config
        }
    }

    switch ($type) {
        "export" {
            try {
                $Config = ConfigDialog
                if ($Config) {
                    $allConfs = ($sync.selectedApps + $sync.selectedTweaks + $sync.selectedToggles + $sync.selectedFeatures + $sync.selectedAppx) | ForEach-Object { [string]$_ }
                    if (-not $allConfs) {
                        [System.Windows.MessageBox]::Show(
                            "Nenhuma configuração selecionada para exportar. Selecione pelo menos um programa, ajuste, opção, recurso ou pacote AppX antes de exportar.",
                            "Nada para exportar", "OK", "Warning")
                        return
                    }
                    $jsonFile = $allConfs | ConvertTo-Json
                    $jsonFile | Out-File $Config -Force
                    # Copy a command that runs this same script with the exported file
                    $scriptPath = if ($PSCommandPath) { $PSCommandPath } else { "azorwinutil.ps1" }
                    "& '$scriptPath' -Config '$Config'" | Set-Clipboard
                }
            } catch {
                Write-Error "Ocorreu um erro ao exportar: $_"
            }
        }
        "import" {
            try {
                $Config = ConfigDialog
                if ($Config) {
                    try {
                        if ($Config -match '^https?://') {
                            $jsonFile = (Invoke-WebRequest "$Config").Content | ConvertFrom-Json
                        } else {
                            $jsonFile = Get-Content $Config | ConvertFrom-Json
                        }
                    } catch {
                        Write-Error "Não foi possível carregar o arquivo JSON do caminho ou URL informado: $_"
                        return
                    }
                    $isLegacyConfig = $jsonFile -is [System.Management.Automation.PSCustomObject] -and
                        $null -ne $jsonFile.PSObject.Properties["Install"] -and
                        $null -ne $jsonFile.PSObject.Properties["WPFInstall"]
                    if ($isLegacyConfig) {
                        Write-WinUtilLog -Component "Impex" -Message "Detected legacy WinUtil config structure; flattening import object."
                        # Legacy exports stored checkbox keys in WPFInstall and duplicated package
                        # source metadata in Install. Current package IDs come from the app catalog,
                        # so only the selection-key properties are restored.
                        $flattenedJson = @(
                            foreach ($property in $jsonFile.PSObject.Properties) {
                                if ($property.Name -notmatch '^WPF(?:Install|Tweaks|Toggle|Feature|Appx)') {
                                    continue
                                }

                                foreach ($selection in @($property.Value)) {
                                    if ($selection -is [string] -and -not [string]::IsNullOrWhiteSpace($selection)) {
                                        $selection
                                    }
                                }
                            }
                        )
                    } else {
                        # New style config: flat array of strings
                        $flattenedJson = $jsonFile
                    }

                    if (-not $flattenedJson) {
                        [System.Windows.MessageBox]::Show(
                            "O arquivo selecionado não contém configurações para importar. Nada foi alterado.",
                            "Configuração vazia", "OK", "Warning")
                        return
                    }

                    # Modern configs stay strict. Legacy configs can reference entries that no
                    # longer exist, so restore supported selections and report the retired keys.
                    if ($isLegacyConfig) {
                        $skippedSelections = @(Update-WinUtilSelections -flatJson $flattenedJson -Replace -SkipUnknown)

                        if ($skippedSelections.Count -gt 0) {
                            $skippedSummary = $skippedSelections -join ", "
                            Write-WinUtilLog -Component "Impex" -Level "WARN" -Message "Skipped unsupported legacy selections: $skippedSummary"
                        }

                        if ($skippedSelections.Count -eq @($flattenedJson).Count) {
                            if ($sync.Form) {
                                Show-WinUtilMessage -Message "Esta configuração antiga não contém nenhuma opção suportada por esta versão do Azor WinUtil. Nada foi alterado." -Title "Configuração antiga não suportada" -Icon "Warning" | Out-Null
                            }
                            return
                        }

                        if ($skippedSelections.Count -gt 0) {
                            $skippedDisplay = @($skippedSelections | Select-Object -First 10) -join ", "
                            if ($skippedSelections.Count -gt 10) {
                                $skippedDisplay += "`n...e mais $($skippedSelections.Count - 10). Veja o log do Azor WinUtil para detalhes."
                            }
                            if ($sync.Form) {
                                Show-WinUtilMessage -Message "As configurações suportadas foram importadas. Estas opções descontinuadas foram ignoradas:`n`n$skippedDisplay" -Title "Configuração antiga importada parcialmente" -Icon "Warning" | Out-Null
                            }
                        }
                    } else {
                        # Options this version removed (config/retired.json) are skipped and reported, so a config
                        # exported by an older build still imports.
                        $retiredOptions = $sync.configs.retired
                        $retiredSelections = @($flattenedJson | Where-Object { $retiredOptions -and $null -ne $retiredOptions.PSObject.Properties[[string]$_] })
                        if ($retiredSelections.Count -gt 0) {
                            $flattenedJson = @($flattenedJson | Where-Object { $retiredSelections -notcontains $_ })
                            Write-WinUtilLog -Component "Impex" -Level "WARN" -Message "Skipped selections removed from Azor WinUtil: $($retiredSelections -join ', ')"

                            if ($flattenedJson.Count -eq 0) {
                                if ($sync.Form) {
                                    Show-WinUtilMessage -Message "Todas as opções deste arquivo saíram do Azor WinUtil. Nada foi alterado." -Title "Nada para importar" -Icon "Warning" | Out-Null
                                }
                                return
                            }
                        }

                        # Build and validate every other selection before replacing the current state. An unknown
                        # key still fails, which keeps a malformed config from leaving partial selections behind.
                        Update-WinUtilSelections -flatJson $flattenedJson -Replace

                        if ($retiredSelections.Count -gt 0 -and $sync.Form) {
                            $retiredNames = @($retiredSelections | ForEach-Object { $retiredOptions.$_ }) -join "`n- "
                            Show-WinUtilMessage -Message "Configuração importada. Estas opções saíram do Azor WinUtil e foram ignoradas:`n`n- $retiredNames" -Title "Configuração importada" -Icon "Information" | Out-Null
                        }
                    }

                    if ($sync.Form) {
                        Reset-WPFCheckBoxes -doToggles $true
                    }
                }
            } catch {
                Write-Error "Ocorreu um erro ao importar: $_"
            }
        }
    }
}

function Invoke-WPFInstall {
    <#
    .SYNOPSIS
        Installs the selected programs using winget, if one or more of the selected programs are already installed on the system, winget will try and perform an upgrade if there's a newer version to install.
    #>
    param(
        [Parameter(Mandatory = $false)]
        [PSObject[]]$PackagesToInstall = $($sync.selectedApps | Foreach-Object { $sync.configs.applicationsHashtable.$_ })
    )


    if($sync.ProcessRunning) {
        $msg = "Já existe uma instalação em andamento. Aguarde a conclusão."
        Show-WinUtilMessage -Message $msg -Title "Azor WinUtil" -Button "OK" -Icon "Warning"
        return
    }

    if ($PackagesToInstall.Count -eq 0) {
        $WarningMsg = "Selecione os programas que deseja instalar ou atualizar."
        Show-WinUtilMessage -Message $WarningMsg -Title "Azor WinUtil" -Button "OK" -Icon "Warning"
        return
    }

    $ManagerPreference = $sync.preferences.packagemanager
    Write-WinUtilLog -Component "Install" -Message "Install requested for $(@($PackagesToInstall).Count) selected package(s) using preference: $ManagerPreference"
    $packageSummary = Get-WinUtilPackageLogSummary -Packages $PackagesToInstall -Preference $ManagerPreference
    Write-WinUtilLog -Component "Install" -Message "Install selected package(s): $($packageSummary -join '; ')"

    Invoke-WPFRunspace -ParameterList @(("PackagesToInstall", $PackagesToInstall),("ManagerPreference", $ManagerPreference)) -ScriptBlock {
        param($PackagesToInstall, $ManagerPreference)

        $packagesSorted = Get-WinUtilSelectedPackages -PackageList $PackagesToInstall -Preference $ManagerPreference

        $packagesWinget = $packagesSorted['Winget']
        $packagesChoco = $packagesSorted['Choco']
        $totalPackages = @($packagesWinget).Count + @($packagesChoco).Count
        $completedPackages = 0
        $hasUI = $null -ne $sync.Form -and $null -ne $sync.Form.Dispatcher
        Write-WinUtilLog -Component "Install" -Message "Install package manager split: winget=$(@($packagesWinget).Count), choco=$(@($packagesChoco).Count)"

        try {
            $sync.ProcessRunning = $true
            if ($hasUI) {
                Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Preparando a instalação de programas (0/$totalPackages)" -Percent 0
                Invoke-WPFUIThread -ScriptBlock {
                    if ($null -ne $sync.ItemsControl) {
                        $sync.ItemsControl.IsEnabled = $false
                    }
                }
            }

            if($packagesWinget.Count -gt 0 -and $packagesWinget -ne "0") {
                Install-WinUtilWinget
                foreach ($program in $packagesWinget) {
                    $position = $completedPackages + 1
                    $startPercent = [int](($completedPackages / $totalPackages) * 100)
                    if ($hasUI) {
                        Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Instalando $program ($position/$totalPackages)" -Percent $startPercent
                    }

                    Install-WinUtilProgramWinget -Action Install -Programs @($program)
                    $completedPackages++
                    $completedPercent = [int](($completedPackages / $totalPackages) * 100)
                    if ($hasUI) {
                        Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Instalado: $program ($completedPackages/$totalPackages)" -Percent $completedPercent
                        Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -value ($completedPercent / 100) }
                    }
                }
            }
            if($packagesChoco.Count -gt 0) {
                $position = $completedPackages + 1
                $startPercent = [int](($completedPackages / $totalPackages) * 100)
                if ($hasUI) {
                    Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Instalando pacotes do Chocolatey ($position/$totalPackages)" -Percent $startPercent
                }

                Install-WinUtilChoco
                Install-WinUtilProgramChoco -Action Install -Programs $packagesChoco
                $completedPackages += @($packagesChoco).Count
                $completedPercent = [int](($completedPackages / $totalPackages) * 100)
                if ($hasUI) {
                    Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Pacotes do Chocolatey instalados ($completedPackages/$totalPackages)" -Percent $completedPercent
                    Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -value ($completedPercent / 100) }
                }
            }
            Write-Host "==========================================="
            Write-Host "--         Instalações concluídas        --"
            Write-Host "==========================================="
            Write-WinUtilLog -Component "Install" -Message "Install workflow completed."
            if ($hasUI) {
                Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Instalação de programas concluída" -Percent 100
                Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "None" -overlay "checkmark" }
            }
        } catch {
            Write-Host "==========================================="
            Write-Host "Erro: $_"
            Write-Host "==========================================="
            Write-WinUtilLog -Level "ERROR" -Component "Install" -Message "Install workflow failed: $($_.Exception.Message)"
            if ($hasUI) {
                Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Falha na instalação de programas" -Percent 100
                Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "Error" -overlay "warning" }
            }
        } finally {
            if ($hasUI) {
                Invoke-WPFUIThread -ScriptBlock {
                    if ($null -ne $sync.ItemsControl) {
                        $sync.ItemsControl.IsEnabled = $true
                    }
                }
            }
            $sync.ProcessRunning = $False
        }
    } | Out-Null
}

function Invoke-WPFInstallUpgrade {
    if ($sync.ChocoRadioButton.IsChecked) {
        Install-WinUtilChoco # Ensure Chocolatey is installed before upgrading

        Write-Host "==========================================="
        Write-Host "--        Atualizações iniciadas         --"
        Write-Host "-- Você pode fechar esta janela se quiser --"
        Write-Host "==========================================="

        Start-Process -FilePath powershell.exe -ArgumentList 'choco upgrade all -y'
    } else {
        Install-WinUtilWinget # Ensure WinGet is installed before upgrading

        Write-Host "==========================================="
        Write-Host "--        Atualizações iniciadas         --"
        Write-Host "-- Você pode fechar esta janela se quiser --"
        Write-Host "==========================================="

        Start-Process -FilePath powershell.exe -ArgumentList '-NoExit winget upgrade --all --include-unknown --silent --accept-source-agreements --accept-package-agreements'
    }
}

function Invoke-WPFPopup {
    param (
        [ValidateSet("Show", "Hide", "Toggle")]
        [string]$Action = "",

        [string[]]$Popups = @(),

        [ValidateScript({
            $invalid = $_.GetEnumerator() | Where-Object { $_.Value -notin @("Show", "Hide", "Toggle") }
            if ($invalid) {
                throw "Found invalid Popup-Action pair(s): " + ($invalid | ForEach-Object { "$($_.Key) = $($_.Value)" } -join "; ")
            }
            $true
        })]
        [hashtable]$PopupActionTable = @{}
    )

    if (-not $PopupActionTable.Count -and (-not $Action -or -not $Popups.Count)) {
        throw "Provide either 'PopupActionTable' or both 'Action' and 'Popups'."
    }

    if ($PopupActionTable.Count -and ($Action -or $Popups.Count)) {
        throw "Use 'PopupActionTable' on its own, or 'Action' with 'Popups'."
    }

    # Collect popups and actions
    $PopupsToProcess = if ($PopupActionTable.Count) {
        $PopupActionTable.GetEnumerator() | ForEach-Object { [PSCustomObject]@{ Name = "$($_.Key)Popup"; Action = $_.Value } }
    } else {
        $Popups | ForEach-Object { [PSCustomObject]@{ Name = "$_`Popup"; Action = $Action } }
    }

    $PopupsNotFound = @()

    # Apply actions
    foreach ($popupEntry in $PopupsToProcess) {
        $popupName = $popupEntry.Name

        if (-not $sync.$popupName) {
            $PopupsNotFound += $popupName
            continue
        }

        $sync.$popupName.IsOpen = switch ($popupEntry.Action) {
            "Show" { $true }
            "Hide" { $false }
            "Toggle" { -not $sync.$popupName.IsOpen }
        }
    }

    if ($PopupsNotFound.Count -gt 0) {
        throw "Could not find the following popups: $($PopupsNotFound -join ', ')"
    }
}

function Invoke-WPFPresets {
    <#

    .SYNOPSIS
        Sets the checkboxes in winutil to the given preset

    .PARAMETER preset
        The preset to set the checkboxes to

    .PARAMETER imported
        If the preset is imported from a file, defaults to false

    .PARAMETER checkboxfilterpattern
        The Pattern to use when filtering through CheckBoxes, defaults to "**"

    #>

    param (
        [Parameter(position=0)]
        [Array]$preset = $null,

        [Parameter(position=1)]
        [bool]$imported = $false,

        [Parameter(position=2)]
        [string]$checkboxfilterpattern = "**"
    )

    if ($imported -eq $true) {
        $CheckBoxesToCheck = $preset
    } else {
        $CheckBoxesToCheck = $sync.configs.preset.$preset
    }

    # clear out the filtered pattern so applying a preset replaces the current
    # state rather than merging with it
    switch ($checkboxfilterpattern) {
        "WPFTweak*" { $sync.selectedTweaks = [System.Collections.Generic.List[string]]::new() }
        "WPFInstall*" { $sync.selectedApps = [System.Collections.Generic.List[string]]::new() }
        "WPFAppx*" { $sync.selectedAppx = [System.Collections.Generic.List[string]]::new() }
        "WPFFeature*" { $sync.selectedFeatures = [System.Collections.Generic.List[string]]::new() }
        "WPFToggle*" { $sync.selectedToggles = [System.Collections.Generic.List[string]]::new() }
        default {}
    }

    if ($preset) {
        Update-WinUtilSelections -flatJson $CheckBoxesToCheck
    }

    Reset-WPFCheckBoxes -doToggles $false -checkboxfilterpattern $checkboxfilterpattern
}

function Invoke-WPFQuickAzorApp {
    <#
    .SYNOPSIS
        Opens AZOR Rate or AZOR Optimization from the AZOR delivery folder.

    .DESCRIPTION
        The app is found by Get-WinUtilAzorAppPath next to the running script. When it is not
        there, the message says which folder to put beside Azor WinUtil instead of failing silently.

    .PARAMETER App
        Rate or Optimization.
    #>
    param (
        [Parameter(Mandatory)]
        [ValidateSet("Rate", "Optimization")]
        [string]$App
    )

    $displayName = if ($App -eq "Rate") { "AZOR Rate" } else { "AZOR Optimization" }
    $appFolder = if ($App -eq "Rate") { "4 - AZOR Rate" } else { "2 - AZOR Optimization Obsidian (completo)" }
    $appPath = Get-WinUtilAzorAppPath -App $App -ScriptPath $PSCommandPath

    if (-not $appPath) {
        Write-WinUtilLog -Level "WARN" -Component "Dashboard" -Message "$displayName not found next to '$PSCommandPath'."
        Show-WinUtilMessage -Message "O $displayName não foi encontrado.`n`nDeixe a pasta ""$appFolder"" ao lado da pasta do Azor WinUtil, do jeito que ela vem na pasta de entrega AZOR, e clique de novo." -Title "Azor WinUtil - $displayName" -Button "OK" -Icon "Warning" | Out-Null
        return
    }

    Write-WinUtilLog -Component "Dashboard" -Message "Opening $displayName from '$appPath'."
    try {
        Start-Process -FilePath $appPath -WorkingDirectory (Split-Path -Parent $appPath) -ErrorAction Stop
    } catch {
        Write-WinUtilLog -Level "ERROR" -Component "Dashboard" -Message "Unable to open ${displayName}: $($_.Exception.Message)"
        Show-WinUtilMessage -Message "O Windows não abriu o $displayName.`n`n$appPath`n$($_.Exception.Message)" -Title "Azor WinUtil - $displayName" -Button "OK" -Icon "Warning" | Out-Null
    }
}

function Invoke-WPFQuickCleanup {
    <#
    .SYNOPSIS
        Measures what the quick cleanup can free, asks the user, cleans, and offers to delete old game copies and
        to empty the Recycle Bin.

    .DESCRIPTION
        Runs in one background runspace. The questions and the result run on the UI thread through
        Invoke-WPFUIThread, which blocks the runspace until the user answers; each answer comes back in
        $sync.CleanupDecision, written on the UI thread. Targets come from Get-WinUtilCleanupTarget, which leaves
        out personal files, games, the content Fortnite downloads again and GPU shader caches. Each old game copy
        from Get-WinUtilOrphanGameCopy and the Recycle Bin get their own question, because deleting them is
        permanent.
    #>

    if ($sync.ProcessRunning) {
        Show-WinUtilMessage -Message "Já existe um processo em andamento. Aguarde a conclusão." -Title "Azor WinUtil" -Button "OK" -Icon "Warning" | Out-Null
        return
    }

    $sync.ProcessRunning = $true
    Write-WinUtilLog -Component "Cleanup" -Message "Quick cleanup started: measuring cleanup targets."
    Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Analisando o que dá para limpar..." -Percent 0
    Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "Indeterminate" -overlay "logo" }

    try {
        Invoke-WPFRunspace -ScriptBlock {
            $title = "Azor WinUtil - Limpeza Rápida"
            try {
                $targets = @(Get-WinUtilCleanupTarget)
                $plan = New-Object System.Collections.Generic.List[object]
                for ($index = 0; $index -lt $targets.Count; $index++) {
                    $target = $targets[$index]
                    Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Analisando: $($target.Label) ($($index + 1)/$($targets.Count))" -Percent ([int]($index / $targets.Count * 40))
                    $bytes = Measure-WinUtilCleanupItem -Item @(Get-WinUtilCleanupItem -Target $target)
                    if ($bytes -gt 0) {
                        $plan.Add([pscustomobject]@{ Target = $target; Bytes = $bytes })
                    }
                }

                Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Analisando: cópias antigas de jogos" -Percent 38
                $gameCopies = @(Get-WinUtilOrphanGameCopy | Where-Object { $_.Bytes -gt 0 })
                $recycleBin = Get-WinUtilRecycleBinInfo
                $plannedBytes = 0.0
                foreach ($entry in $plan) { $plannedBytes += $entry.Bytes }
                Write-WinUtilLog -Component "Cleanup" -Message ("Cleanup analysis: {0} bytes in {1} target(s); {2} old game copy(ies); Recycle Bin {3} item(s), {4} bytes." -f $plannedBytes, $plan.Count, $gameCopies.Count, $recycleBin.Items, $recycleBin.Bytes)
                foreach ($gameCopy in $gameCopies) {
                    Write-WinUtilLog -Component "Cleanup" -Message "Old copy of $($gameCopy.Name) at $($gameCopy.Path) ($($gameCopy.Bytes) bytes); the launcher uses $($gameCopy.InstalledAt)."
                }

                $freedLines = New-Object System.Collections.Generic.List[string]
                $totalFreed = 0.0
                $askFollowUps = $true

                if ($plan.Count -gt 0) {
                    $planLines = ($plan | Sort-Object -Property Bytes -Descending | ForEach-Object { "- $($_.Target.Label): $(Format-WinUtilSize $_.Bytes)" }) -join "`n"
                    $question = "Encontrei $(Format-WinUtilSize $plannedBytes) para liberar:`n`n$planLines`n- Cache de DNS (limpo junto)`n`nNão mexo em: seus arquivos pessoais, jogos, conteúdo que o Fortnite baixa de novo e o cache de shaders da placa de vídeo (apagar faz os jogos engasgarem enquanto recompilam).`n`nLimpar agora?"
                    Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Aguardando sua confirmação..." -Percent 40
                    Invoke-WPFUIThread -ScriptBlock {
                        $sync.CleanupDecision = [string](Show-WinUtilMessage -Message $question -Title $title -Button "YesNo" -Icon "Question")
                    }

                    if ([string]$sync.CleanupDecision -eq "Yes") {
                        $cleanIndex = 0
                        foreach ($entry in $plan) {
                            $cleanIndex++
                            $target = $entry.Target
                            Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Limpando: $($target.Label) ($cleanIndex/$($plan.Count))" -Percent ([int](40 + ($cleanIndex / $plan.Count) * 50))

                            $stoppedServices = @()
                            $canClean = $true
                            foreach ($serviceName in @($target.Services)) {
                                $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
                                if ($service -and $service.Status -eq "Running") {
                                    try {
                                        Stop-Service -Name $serviceName -Force -ErrorAction Stop
                                        $stoppedServices += $serviceName
                                    } catch {
                                        $canClean = $false
                                        Write-WinUtilLog -Level "WARN" -Component "Cleanup" -Message "Skipped $($target.Path) because $serviceName could not be stopped: $($_.Exception.Message)"
                                    }
                                }
                            }

                            if ($canClean) {
                                foreach ($item in @(Get-WinUtilCleanupItem -Target $target)) {
                                    Remove-Item -LiteralPath $item.FullName -Recurse -Force -ErrorAction SilentlyContinue
                                }
                            }

                            foreach ($serviceName in $stoppedServices) {
                                Start-Service -Name $serviceName -ErrorAction SilentlyContinue
                            }

                            $freed = [math]::Max(0, $entry.Bytes - (Measure-WinUtilCleanupItem -Item @(Get-WinUtilCleanupItem -Target $target)))
                            $totalFreed += $freed
                            if ($freed -gt 0) {
                                $freedLines.Add("- $($target.Label): $(Format-WinUtilSize $freed)")
                            }
                            Write-WinUtilLog -Component "Cleanup" -Message "Cleaned $($target.Path) ($freed bytes freed)."
                        }

                        try {
                            Clear-DnsClientCache -ErrorAction Stop
                            $freedLines.Add("- Cache de DNS limpo")
                        } catch {
                            Write-WinUtilLog -Level "WARN" -Component "Cleanup" -Message "Unable to flush the DNS cache: $($_.Exception.Message)"
                        }
                    } else {
                        # The user declined the cleanup, so stop here instead of asking about game copies and the Recycle Bin too.
                        $askFollowUps = $false
                        Write-WinUtilLog -Component "Cleanup" -Message "Quick cleanup declined by the user."
                    }
                }

                if ($askFollowUps) {
                    foreach ($gameCopy in $gameCopies) {
                        $copyQuestion = "Encontrei uma cópia antiga do $($gameCopy.Name) que o Epic Games Launcher não usa:`n`n$($gameCopy.Path)`n$(Format-WinUtilSize $gameCopy.Bytes)`n`nO $($gameCopy.Name) que você joga fica em $($gameCopy.InstalledAt) e não é afetado.`n`nApagar a cópia antiga libera esse espaço, mas é definitivo: não vai para a Lixeira.`n`nApagar agora?"
                        Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Aguardando sua confirmação..." -Percent 91
                        Invoke-WPFUIThread -ScriptBlock {
                            $sync.CleanupDecision = [string](Show-WinUtilMessage -Message $copyQuestion -Title $title -Button "YesNo" -Icon "Warning")
                        }

                        if ([string]$sync.CleanupDecision -ne "Yes") {
                            Write-WinUtilLog -Component "Cleanup" -Message "Kept the old copy of $($gameCopy.Name) at $($gameCopy.Path)."
                            continue
                        }

                        Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Apagando a cópia antiga do $($gameCopy.Name)..." -Percent 91
                        Remove-Item -LiteralPath $gameCopy.Path -Recurse -Force -ErrorAction SilentlyContinue
                        $leftBytes = 0.0
                        $leftover = Get-Item -LiteralPath $gameCopy.Path -Force -ErrorAction SilentlyContinue
                        if ($leftover) {
                            $leftBytes = Measure-WinUtilCleanupItem -Item @($leftover)
                            Write-WinUtilLog -Level "WARN" -Component "Cleanup" -Message "Part of $($gameCopy.Path) could not be deleted ($leftBytes bytes left)."
                        }
                        $copyFreed = [math]::Max(0, $gameCopy.Bytes - $leftBytes)
                        $totalFreed += $copyFreed
                        $freedLines.Add("- Cópia antiga do $($gameCopy.Name): $(Format-WinUtilSize $copyFreed)")
                        Write-WinUtilLog -Component "Cleanup" -Message "Deleted the old copy of $($gameCopy.Name) at $($gameCopy.Path) ($copyFreed bytes freed)."
                    }
                }

                if ($askFollowUps -and $recycleBin.Items -gt 0) {
                    $drive = ([IO.Path]::GetPathRoot($env:SystemRoot)).TrimEnd('\')
                    $binQuestion = "A Lixeira da unidade $drive tem $(Format-WinUtilSize $recycleBin.Bytes) em $($recycleBin.Items) item(ns).`n`nEsvaziar apaga esses arquivos para sempre: depois não dá para recuperar. Se quiser conferir antes, responda Não e abra a Lixeira na Área de Trabalho.`n`nEsvaziar a Lixeira agora?"
                    Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Aguardando sua confirmação..." -Percent 92
                    Invoke-WPFUIThread -ScriptBlock {
                        $sync.CleanupDecision = [string](Show-WinUtilMessage -Message $binQuestion -Title $title -Button "YesNo" -Icon "Warning")
                    }

                    if ([string]$sync.CleanupDecision -eq "Yes") {
                        try {
                            Clear-RecycleBin -DriveLetter $drive.Substring(0, 1) -Force -ErrorAction Stop
                            $binFreed = [math]::Max(0, $recycleBin.Bytes - (Get-WinUtilRecycleBinInfo).Bytes)
                            $totalFreed += $binFreed
                            $freedLines.Add("- Lixeira da unidade ${drive}: $(Format-WinUtilSize $binFreed)")
                            Write-WinUtilLog -Component "Cleanup" -Message "Recycle Bin on $drive emptied ($binFreed bytes freed)."
                        } catch {
                            $freedLines.Add("- Não foi possível esvaziar a Lixeira: $($_.Exception.Message)")
                            Write-WinUtilLog -Level "WARN" -Component "Cleanup" -Message "Unable to empty the Recycle Bin: $($_.Exception.Message)"
                        }
                    }
                }

                if ($freedLines.Count -eq 0) {
                    Set-WinUtilTweaksProgressIndicator -Visible $false
                    $nothingMessage = if ($plan.Count -eq 0 -and $gameCopies.Count -eq 0 -and $recycleBin.Items -eq 0) {
                        "Nada para limpar: temporários, caches e logs já estão em ordem, e a Lixeira está vazia."
                    } else {
                        ""
                    }
                    Invoke-WPFUIThread -ScriptBlock {
                        Set-WinUtilTaskbaritem -state "None"
                        if ($nothingMessage) {
                            Show-WinUtilMessage -Message $nothingMessage -Title $title -Button "OK" -Icon "Information" | Out-Null
                        }
                    }
                    return
                }

                $freeSpaceText = ""
                try {
                    $systemDrive = [System.IO.DriveInfo]::new($env:SystemDrive)
                    $freeSpaceText = "`n`nEspaço livre agora em $($env:SystemDrive): $(Format-WinUtilSize $systemDrive.AvailableFreeSpace)"
                } catch {
                    $freeSpaceText = ""
                }

                $summary = "Limpeza concluída! Espaço liberado: $(Format-WinUtilSize $totalFreed)"
                $details = ($freedLines -join "`n") + $freeSpaceText
                Write-WinUtilLog -Component "Cleanup" -Message "Quick cleanup finished ($totalFreed bytes freed)."
                Set-WinUtilTweaksProgressIndicator -Visible $true -Label $summary -Percent 100
                Invoke-WPFUIThread -ScriptBlock {
                    Set-WinUtilTaskbaritem -state "None" -overlay "checkmark"
                    Update-WinUtilDashboardMetrics
                    Show-WinUtilMessage -Message "$summary`n`n$details" -Title $title -Button "OK" -Icon "Information" | Out-Null
                }
            } catch {
                Write-WinUtilLog -Level "ERROR" -Component "Cleanup" -Message "Quick cleanup failed: $($_.Exception.Message)"
                Set-WinUtilTweaksProgressIndicator -Visible $true -Label "A limpeza falhou. Veja o log para detalhes." -Percent 100
                Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "Error" -overlay "warning" }
            } finally {
                $sync.ProcessRunning = $false
            }
        } | Out-Null
    } catch {
        $sync.ProcessRunning = $false
        Set-WinUtilTweaksProgressIndicator -Visible $false
        Write-WinUtilLog -Level "ERROR" -Component "Cleanup" -Message "Unable to queue quick cleanup: $($_.Exception.Message)"
    }
}

function Invoke-WPFQuickGameCompat {
    <#
    .SYNOPSIS
        Shows the Checkup para Jogos and offers to fix the software-side problems it finds.

    .DESCRIPTION
        The report only reads the system and is shown in the scrollable checkup window. Fixes run only after
        the user clicks the fix button, and never touch firmware settings (TPM, Secure Boot) or VBS, which the
        user has to turn on. The Dashboard alert is updated with the report, and checked again after a repair.
        When low disk space was among the fixes, the Limpeza Rápida opens after the summary.
    #>

    if ($sync.ProcessRunning) {
        Show-WinUtilMessage -Message "Já existe um processo em andamento. Aguarde a conclusão." -Title "Azor WinUtil" -Button "OK" -Icon "Warning" | Out-Null
        return
    }

    $title = "Azor WinUtil - Checkup para Jogos"
    $previousCursor = $sync.Form.Cursor
    $sync.Form.Cursor = [System.Windows.Input.Cursors]::Wait
    try {
        $checks = @(Get-WinUtilGameCompatReport)
    } finally {
        $sync.Form.Cursor = $previousCursor
    }

    Write-WinUtilLog -Component "GameCompat" -Message ("Game checkup report: " + (($checks | ForEach-Object { "$($_.Id)=$($_.Status)" }) -join ", "))
    Set-WinUtilDashboardCompatAlert -Report $checks

    if (-not (Show-WinUtilCheckupDialog -Report $checks)) {
        return
    }

    $fixable = @((Get-WinUtilCheckupView -Report $checks).Fixable)
    $results = @(Repair-WinUtilGameCompat -Checks $fixable)
    $fixedIds = @($fixable | ForEach-Object { $_.Id })
    Write-WinUtilLog -Component "GameCompat" -Message ("Game checkup repair: " + ($fixedIds -join ", "))

    $sync.Form.Cursor = [System.Windows.Input.Cursors]::Wait
    try {
        Set-WinUtilDashboardCompatAlert -Report @(Get-WinUtilGameCompatReport)
    } finally {
        $sync.Form.Cursor = $previousCursor
    }

    $summary = $results -join "`n"
    if (@($fixedIds | Where-Object { $_ -in @("Teredo", "XboxServices", "AzorLegacy", "Mpo") }).Count -gt 0) {
        $summary += "`n`nReinicie o PC para as mudanças de rede, serviços e vídeo valerem."
    }
    Show-WinUtilMessage -Message $summary -Title $title -Button "OK" -Icon "Information" | Out-Null

    if ($fixedIds -contains "DiskSpace") {
        Invoke-WPFQuickCleanup
    }
}

function Invoke-WPFQuickGamingPreset {
    <#
    .SYNOPSIS
        Selects the Gaming tweak preset and opens the Tweaks tab so the user can review it before running.
    #>

    Invoke-WPFPresets "Gaming" -checkboxfilterpattern "WPFTweak*"
    Invoke-WPFTab "WPFTab2BT"
    Show-WinUtilMessage -Message "A seleção ""Jogos (Azor)"" foi marcada na aba Otimizar.`n`nRevise os itens e clique em ""Executar Ajustes"" para aplicar. Tudo pode ser revertido com ""Desfazer Ajustes Selecionados""." -Title "Azor WinUtil - Modo Jogo" -Button "OK" -Icon "Information" | Out-Null
}

function Invoke-WPFQuickOptimize {
    <#
    .SYNOPSIS
        Applies the Standard tweak preset from the Dashboard after the user confirms the list.

    .DESCRIPTION
        Selects the Standard preset, which includes a restore point, and runs it through the normal
        Run Tweaks workflow, so progress, logging and undo work exactly like on the Tweaks tab.
    #>

    if ($sync.ProcessRunning) {
        Show-WinUtilMessage -Message "Já existe um processo em andamento. Aguarde a conclusão." -Title "Azor WinUtil" -Button "OK" -Icon "Warning" | Out-Null
        return
    }

    $presetTweaks = @($sync.configs.preset.Standard)
    $tweakNames = @($presetTweaks | ForEach-Object { $sync.configs.tweaks.$_.Content })
    $message = "A Otimização Rápida vai aplicar $($presetTweaks.Count) ajustes recomendados (seleção Padrão):`n`n- $($tweakNames -join "`n- ")`n`nUm ponto de restauração é criado antes, e os ajustes podem ser desfeitos na aba Otimizar. Deseja continuar?"

    $confirmation = Show-WinUtilMessage -Message $message -Title "Azor WinUtil - Otimização Rápida" -Button "YesNo" -Icon "Question"
    if ($confirmation -ne "Yes") {
        return
    }

    Write-WinUtilLog -Component "Dashboard" -Message "Quick optimize confirmed; applying the Standard preset."
    Invoke-WPFPresets "Standard" -checkboxfilterpattern "WPFTweak*"
    Invoke-WPFtweaksbutton
}

function Invoke-WPFQuickRestorePoint {
    <#
    .SYNOPSIS
        Creates a System Restore point from the Dashboard without blocking the window.

    .DESCRIPTION
        Reuses the WPFTweaksRestorePoint tweak in a background runspace, then compares the newest
        restore point before and after, so the result reflects what Windows actually created.
    #>

    if ($sync.ProcessRunning) {
        Show-WinUtilMessage -Message "Já existe um processo em andamento. Aguarde a conclusão." -Title "Azor WinUtil" -Button "OK" -Icon "Warning" | Out-Null
        return
    }

    $sync.ProcessRunning = $true
    Write-WinUtilLog -Component "Dashboard" -Message "Restore point requested from the Dashboard."
    Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Criando ponto de restauração..." -Percent 10
    Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "Indeterminate" -overlay "logo" }

    try {
        Invoke-WPFRunspace -ScriptBlock {
            try {
                $newestBefore = (@(Get-ComputerRestorePoint -ErrorAction SilentlyContinue) | Sort-Object -Property SequenceNumber | Select-Object -Last 1).SequenceNumber
                Invoke-WinUtilTweaks "WPFTweaksRestorePoint"
                $newestAfter = (@(Get-ComputerRestorePoint -ErrorAction SilentlyContinue) | Sort-Object -Property SequenceNumber | Select-Object -Last 1).SequenceNumber

                if ($null -ne $newestAfter -and $newestAfter -ne $newestBefore) {
                    Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Ponto de restauração criado" -Percent 100
                    Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "None" -overlay "checkmark" }
                    Write-WinUtilLog -Component "Dashboard" -Message "Restore point $newestAfter created."
                } else {
                    $sync.ProcessRunning = $false
                    Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Não foi possível criar o ponto de restauração" -Percent 100
                    Write-WinUtilLog -Level "WARN" -Component "Dashboard" -Message "No new restore point was created."
                    Invoke-WPFUIThread -ScriptBlock {
                        Set-WinUtilTaskbaritem -state "Error" -overlay "warning"
                        Show-WinUtilMessage -Message "O Windows não criou um novo ponto de restauração.`n`nVerifique se a Proteção do Sistema está ativada na unidade $env:SystemDrive e se ela não está bloqueada por política. Os detalhes estão no console e no log do Azor WinUtil." -Title "Azor WinUtil - Ponto de Restauração" -Button "OK" -Icon "Warning" | Out-Null
                    }
                }
            } catch {
                Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Não foi possível criar o ponto de restauração" -Percent 100
                Write-WinUtilLog -Level "ERROR" -Component "Dashboard" -Message "Restore point creation failed: $($_.Exception.Message)"
                Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "Error" -overlay "warning" }
            } finally {
                $sync.ProcessRunning = $false
            }
        } | Out-Null
    } catch {
        $sync.ProcessRunning = $false
        Set-WinUtilTweaksProgressIndicator -Visible $false
        Write-WinUtilLog -Level "ERROR" -Component "Dashboard" -Message "Unable to queue restore point creation: $($_.Exception.Message)"
    }
}

function Invoke-WPFRunspace {

    <#

    .SYNOPSIS
        Creates and invokes a runspace using the given scriptblock and argumentlist

    .PARAMETER ScriptBlock
        The scriptblock to invoke in the runspace

    .PARAMETER ArgumentList
        A list of arguments to pass to the runspace

    .PARAMETER ParameterList
        A list of named parameters that should be provided.
    .EXAMPLE
        Invoke-WPFRunspace `
            -ScriptBlock $sync.ScriptsInstallPrograms `
            -ArgumentList "Installadvancedip,Installbitwarden" `

        Invoke-WPFRunspace`
            -ScriptBlock $sync.ScriptsInstallPrograms `
            -ParameterList @(("PackagesToInstall", @("Installadvancedip,Installbitwarden")),("ChocoPreference", $true))
    #>

    [CmdletBinding()]
    [OutputType([System.IAsyncResult])]
    Param (
        $ScriptBlock,
        $ArgumentList,
        $ParameterList
    )

    if (-not ("WinUtilRunspaceCleanup" -as [type])) {
        Add-Type @"
using System;
using System.Management.Automation;

public sealed class WinUtilRunspaceCleanupState
{
    public PowerShell PowerShell { get; set; }
    public IAsyncResult Handle { get; set; }
}

public static class WinUtilRunspaceCleanup
{
    public static readonly System.Threading.WaitOrTimerCallback Callback = Cleanup;

    public static void Cleanup(object state, bool timedOut)
    {
        var cleanupState = state as WinUtilRunspaceCleanupState;
        if (cleanupState == null || cleanupState.PowerShell == null || cleanupState.Handle == null)
        {
            return;
        }

        try
        {
            cleanupState.PowerShell.EndInvoke(cleanupState.Handle);
        }
        catch
        {
        }
        finally
        {
            cleanupState.PowerShell.Dispose();
        }
    }
}
"@
    }

    Initialize-WinUtilRunspacePool | Out-Null

    # Create a PowerShell instance
    $powershell = [powershell]::Create()

    # Add Scriptblock and Arguments to runspace
    [void]$powershell.AddScript($ScriptBlock)
    [void]$powershell.AddArgument($ArgumentList)

    foreach ($parameter in $ParameterList) {
        [void]$powershell.AddParameter($parameter[0], $parameter[1])
    }

    $powershell.RunspacePool = $sync.runspace

    # Execute the RunspacePool
    $handle = $powershell.BeginInvoke()

    $cleanupState = [WinUtilRunspaceCleanupState]::new()
    $cleanupState.PowerShell = $powershell
    $cleanupState.Handle = $handle
    [System.Threading.ThreadPool]::RegisterWaitForSingleObject($handle.AsyncWaitHandle, [WinUtilRunspaceCleanup]::Callback, $cleanupState, -1, $true) | Out-Null

    # Return the handle
    return $handle
}

function Invoke-WPFSelectedCheckboxesUpdate ($type, $checkboxName) {
    $listName = switch -Regex ($checkboxName) {
        '^WPFInstall' { 'selectedApps' }
        '^WPFTweaks'  { 'selectedTweaks' }
        '^WPFToggle'  { 'selectedToggles' }
        '^WPFFeature' { 'selectedFeatures' }
        '^WPFAppx'    { 'selectedAppx' }
    }

    $selectionChanged = $false
    if ($type -eq "Add") {
        if (-not $sync.$listName.Contains($checkboxName)) {
            $sync.$listName.Add($checkboxName)
            $selectionChanged = $true
        }
    } else {
        $selectionChanged = $sync.$listName.Remove($checkboxName)
    }

    if ($listName -eq "selectedApps" -and $selectionChanged) {
        $sync.WPFselectedAppsButton.Content = "Programas selecionados: $($sync.selectedApps.Count)"
        $sync.selectedAppsstackPanel.Children.Clear()
        $sync.selectedApps | Sort-Object | ForEach-Object {
            Add-SelectedAppsMenuItem -name $sync.configs.applicationsHashtable.$_.Content -key $_
        }
    }
}

function Invoke-WPFSystemRepair {
    <#
    .SYNOPSIS
        Checks for system corruption using SFC, and DISM
        Checks for disk failure using Chkdsk

    .DESCRIPTION
        1. Chkdsk - Checks for disk errors, which can cause system file corruption and notifies of early disk failure
        2. SFC - scans protected system files for corruption and fixes them
        3. DISM - Repair a corrupted Windows operating system image
        The tools run in a background runspace, so the window stays responsive; they print their progress to the console.
    #>

    if ($sync.ProcessRunning) {
        Show-WinUtilMessage -Message "Já existe um processo em andamento. Aguarde a conclusão." -Title "Azor WinUtil" -Button "OK" -Icon "Warning" | Out-Null
        return
    }

    $sync.ProcessRunning = $true
    Write-WinUtilLog -Component "Repair" -Message "System repair started (chkdsk, sfc, dism)."

    try {
        Invoke-WPFRunspace -ScriptBlock {
            try {
                Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "Indeterminate" -overlay "logo" }

                Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Reparo 1/3: verificando o disco (CHKDSK)..." -Percent 5
                Start-Process cmd.exe -ArgumentList "/c chkdsk /scan /perf" -NoNewWindow -Wait

                Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Reparo 2/3: verificando os arquivos do sistema (SFC)..." -Percent 35
                Start-Process cmd.exe -ArgumentList "/c sfc /scannow" -NoNewWindow -Wait

                Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Reparo 3/3: reparando a imagem do Windows (DISM)..." -Percent 70
                Start-Process cmd.exe -ArgumentList "/c dism /online /cleanup-image /restorehealth" -NoNewWindow -Wait

                Write-Host "==> Reparo do sistema concluído"
                Write-WinUtilLog -Component "Repair" -Message "System repair finished."
                Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Reparo do sistema concluído. Veja os detalhes no console." -Percent 100
                Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "None" -overlay "checkmark" }
            } catch {
                Write-WinUtilLog -Level "ERROR" -Component "Repair" -Message "System repair failed: $($_.Exception.Message)"
                Set-WinUtilTweaksProgressIndicator -Visible $true -Label "O reparo do sistema falhou. Veja o log para detalhes." -Percent 100
                Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "Error" -overlay "warning" }
            } finally {
                $sync.ProcessRunning = $false
            }
        } | Out-Null
    } catch {
        $sync.ProcessRunning = $false
        Write-WinUtilLog -Level "ERROR" -Component "Repair" -Message "Unable to queue system repair: $($_.Exception.Message)"
    }
}

function Invoke-WPFTab {

    <#

    .SYNOPSIS
        Sets the selected tab to the tab that was clicked

    .PARAMETER ClickedTab
        The name of the tab that was clicked

    #>

    Param (
        [Parameter(Mandatory,position=0)]
        [string]$ClickedTab
    )

    $tabNav = Get-WinUtilVariables | Where-Object {$psitem -like "WPFTabNav"}
    # WPFTab<N>BT selects the TabItem named WPFTab<N>. Look it up by name, not by position, because tab
    # numbers have gaps where tabs were removed.
    $tabName = $ClickedTab -replace "BT$", ""
    $tabItem = @($sync.$tabNav.Items | Where-Object { $_.Name -eq $tabName })[0]
    if ($null -eq $tabItem) {
        return
    }

    $filter = Get-WinUtilVariables -Type ToggleButton | Where-Object {$psitem -like "WPFTab?BT"}
    $tabItem.IsSelected = $true
    ($sync.GetEnumerator()).where{$psitem.Key -in $filter} | ForEach-Object {
        if ($ClickedTab -ne $PSItem.name) {
            $sync[$PSItem.Name].IsChecked = $false
        } else {
            $sync["$ClickedTab"].IsChecked = $true
        }
    }
    $sync.currentTab = $tabItem.Header
    Initialize-WinUtilTabContent -TabName $sync.currentTab

    # Always reset the filter for the current tab
    if ($sync.currentTab -eq "Install") {
        # Reset the search text, but keep the categories the chips are still showing as selected
        $selectedCategories = if ($sync.SelectedAppCategories) { $sync.SelectedAppCategories.ToArray() } else { @() }
        Find-AppsByNameOrDescription -SearchString "" -Categories $selectedCategories
    } elseif ($sync.currentTab -eq "Tweaks") {
        # Reset Tweaks tab filter
        Find-TweaksByNameOrDescription -SearchString ""
    } elseif ($sync.currentTab -eq "AppX") {
        # Reset AppX tab filter
        Find-TweaksByNameOrDescription -SearchString ""
    }

    # Show search bar in Install, Tweaks, and AppX tabs
    if ($sync.currentTab -in @("Install", "Tweaks", "AppX")) {
        $sync.SearchBar.Visibility = "Visible"
        $searchIcon = ($sync.Form.FindName("SearchBar").Parent.Children | Where-Object { $_ -is [System.Windows.Controls.TextBlock] -and $_.Text -eq [char]0xE721 })[0]
        if ($searchIcon) {
            $searchIcon.Visibility = "Visible"
        }
    } else {
        $sync.SearchBar.Visibility = "Collapsed"
        $searchIcon = ($sync.Form.FindName("SearchBar").Parent.Children | Where-Object { $_ -is [System.Windows.Controls.TextBlock] -and $_.Text -eq [char]0xE721 })[0]
        if ($searchIcon) {
            $searchIcon.Visibility = "Collapsed"
        }
        # Hide the clear button if it's visible
        $sync.SearchBarClearButton.Visibility = "Collapsed"
    }
}

function Invoke-WPFToggleAllCategories {
    <#
        .SYNOPSIS
            Expands or collapses all categories in the Install tab

        .PARAMETER Action
            The action to perform: "Expand" or "Collapse"

        .DESCRIPTION
            This function iterates through all category containers in the Install tab
            and expands or collapses their WrapPanels while updating the toggle button labels
    #>

    param(
        [Parameter(Mandatory=$true)]
        [ValidateSet("Expand", "Collapse")]
        [string]$Action
    )

    try {
        if ($null -eq $sync.ItemsControl) {
            Write-Warning "ItemsControl not initialized"
            return
        }

        $targetVisibility = if ($Action -eq "Expand") { [Windows.Visibility]::Visible } else { [Windows.Visibility]::Collapsed }
        $targetPrefix = if ($Action -eq "Expand") { "-" } else { "+" }
        $sourcePrefix = if ($Action -eq "Expand") { "+" } else { "-" }

        # Iterate through all items in the ItemsControl
        $sync.ItemsControl.Items | ForEach-Object {
            $categoryContainer = $_

            # Check if this is a category container (StackPanel with children)
            if ($categoryContainer -is [System.Windows.Controls.StackPanel] -and $categoryContainer.Children.Count -ge 2) {
                # Get the WrapPanel (second child)
                $wrapPanel = $categoryContainer.Children[1]
                $wrapPanel.Visibility = $targetVisibility

                # Update the label to show the correct state
                $categoryLabel = $categoryContainer.Children[0]
                if ($categoryLabel.Content -like "$sourcePrefix*") {
                    $escapedSourcePrefix = [regex]::Escape($sourcePrefix)
                    $categoryLabel.Content = $categoryLabel.Content -replace "^$escapedSourcePrefix ", "$targetPrefix "
                }
            }
        }
    }
    catch {
        Write-Error "Error toggling categories: $_"
    }
}

function Invoke-WPFtweaksbutton {
  <#

    .SYNOPSIS
        Invokes the functions associated with each group of checkboxes

  #>

  if($sync.ProcessRunning) {
    $msg = "Já existe um processo em andamento. Aguarde a conclusão."
    [System.Windows.MessageBox]::Show($msg, "Azor WinUtil", [System.Windows.MessageBoxButton]::OK, [System.Windows.MessageBoxImage]::Warning)
    return
  }

  $Tweaks = $sync.selectedTweaks
  $dnsProvider = $sync["WPFchangedns"].text
  if (-not ($dnsProvider)) {
    $dnsProvider = "Default"
  }
  $restorePointTweak = "WPFTweaksRestorePoint"
  $restorePointSelected = $Tweaks -contains $restorePointTweak
  $tweaksToRun = @($Tweaks | Where-Object { $_ -ne $restorePointTweak })
  $totalSteps = [Math]::Max($Tweaks.Count, 1)
  $completedSteps = 0
  Write-WinUtilLog -Component "Tweaks" -Message "Tweaks requested: $(@($Tweaks).Count) selected tweak(s), DNS provider: $dnsProvider"
  # Logged from the UI thread: the per-tweak lines below run in a runspace, whose host output
  # never reaches this session's transcript, so this is the only record of what was requested.
  Write-WinUtilLog -Component "Tweaks" -Message "Selected tweaks: $(@($Tweaks) -join ', ')"

  if ($tweaks.count -eq 0 -and $dnsProvider -eq "Default") {
    $msg = "Marque os ajustes que deseja aplicar."
    [System.Windows.MessageBox]::Show($msg, "Azor WinUtil", [System.Windows.MessageBoxButton]::OK, [System.Windows.MessageBoxImage]::Warning)
    return
  }

  if ($restorePointSelected) {
    $sync.ProcessRunning = $true

    if ($Tweaks.Count -eq 1) {
        Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "Indeterminate" -value 0.01 -overlay "logo" }
    } else {
        Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "Normal" -value 0.01 -overlay "logo" }
    }

    Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Criando ponto de restauração" -Percent 0
    Write-WinUtilLog -Component "Tweaks" -Message "Creating restore point before applying selected tweaks."
    Invoke-WinUtilTweaks $restorePointTweak
    $completedSteps = 1

    if ($tweaksToRun.Count -eq 0 -and $dnsProvider -eq "Default") {
      Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Ajustes concluídos" -Percent 100
      $sync.ProcessRunning = $false
      Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "None" -overlay "checkmark" }
      Write-Host "================================="
      Write-Host "--      Ajustes concluídos      --"
      Write-Host "================================="
      Write-WinUtilLog -Component "Tweaks" -Message "Tweaks workflow completed after restore point."
      return
    }
  }

  # The leading "," in the ParameterList is necessary because we only provide one argument and powershell cannot be convinced that we want a nested loop with only one argument otherwise
  Invoke-WPFRunspace -ParameterList @(("tweaks", $tweaksToRun), ("dnsProvider", $dnsProvider), ("completedSteps", $completedSteps), ("totalSteps", $totalSteps)) -ScriptBlock {
    param($tweaks, $dnsProvider, $completedSteps, $totalSteps)

    $sync.ProcessRunning = $true

    if ($completedSteps -eq 0) {
      if ($Tweaks.count -eq 1) {
        Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "Indeterminate" -value 0.01 -overlay "logo" }
      } else {
        Invoke-WPFUIThread -ScriptBlock{ Set-WinUtilTaskbaritem -state "Normal" -value 0.01 -overlay "logo" }
      }
    }

    if ($dnsProvider -ne "Default") {
      $dnsResult = @(Set-WinUtilDNS -DNSProvider $dnsProvider)
      if ($dnsResult[-1] -ne $true) {
        Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Falha ao alterar o DNS" -Percent 100
        $sync.ProcessRunning = $false
        Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "Error" -overlay "warning" }
        Write-WinUtilLog -Level "ERROR" -Component "Tweaks" -Message "Tweaks workflow stopped because the DNS change failed."
        return
      }
    }

    for ($i = 0; $i -lt $tweaks.Count; $i++) {
      $tweakName = $sync.configs.tweaks.$($tweaks[$i]).Content
      if (-not $tweakName) {
        $tweakName = $tweaks[$i]
      }
      Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Aplicando: $tweakName ($($completedSteps + 1)/$totalSteps)" -Percent ($completedSteps / $totalSteps * 100)
      Invoke-WinUtilTweaks $tweaks[$i]
      $completedSteps++
      $progress = $completedSteps / $totalSteps
      Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -value $progress }
    }
    Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Ajustes concluídos" -Percent 100
    $sync.ProcessRunning = $false
    Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "None" -overlay "checkmark" }
    Write-Host "================================="
    Write-Host "--      Ajustes concluídos      --"
    Write-Host "================================="
    Write-WinUtilLog -Component "Tweaks" -Message "Tweaks workflow completed."
  } | Out-Null
}

function Invoke-WPFUIElements {
    <#
    .SYNOPSIS
        Adds UI elements to a specified Grid in the WinUtil GUI based on a JSON configuration.
    .PARAMETER configVariable
        The variable/link containing the JSON configuration.
    .PARAMETER targetGridName
        The name of the grid to which the UI elements should be added.
    .PARAMETER columncount
        The number of columns to be used in the Grid. If not provided, a default value is used based on the panel.
    .EXAMPLE
        Invoke-WPFUIElements -configVariable $sync.configs.applications -targetGridName "install" -columncount 5
    .NOTES
        Future me/contributor: If possible, please wrap this into a runspace to make it load all panels at the same time.
    #>

    param(
        [Parameter(Mandatory, Position = 0)]
        [PSCustomObject]$configVariable,

        [Parameter(Mandatory, Position = 1)]
        [string]$targetGridName,

        [Parameter(Mandatory, Position = 2)]
        [int]$columncount
    )

    $window = $sync.form

    $borderstyle = $window.FindResource("BorderStyle")
    $HoverTextBlockStyle = $window.FindResource("HoverTextBlockStyle")
    $ColorfulToggleSwitchStyle = $window.FindResource("ColorfulToggleSwitchStyle")
    $ToggleButtonStyle = $window.FindResource("ToggleButtonStyle")

    if (!$borderstyle -or !$HoverTextBlockStyle -or !$ColorfulToggleSwitchStyle) {
        throw "Failed to retrieve Styles using 'FindResource' from main window element."
    }

    $targetGrid = $window.FindName($targetGridName)

    if (!$targetGrid) {
        throw "Failed to retrieve Target Grid by name, provided name: $targetGrid"
    }

    # Clear existing ColumnDefinitions and Children
    $targetGrid.ColumnDefinitions.Clear() | Out-Null
    $targetGrid.Children.Clear() | Out-Null

    # Add ColumnDefinitions to the target Grid
    for ($i = 0; $i -lt $columncount; $i++) {
        $colDef = New-Object Windows.Controls.ColumnDefinition
        $colDef.Width = New-Object System.Windows.GridLength([double]1, [System.Windows.GridUnitType]::Star)
        $targetGrid.ColumnDefinitions.Add($colDef) | Out-Null
    }

    # Convert PSCustomObject to Hashtable
    $configHashtable = @{}
    $configVariable.PSObject.Properties.Name | ForEach-Object {
        $configHashtable[$_] = $configVariable.$_
    }

    $radioButtonGroups = @{}

    $organizedData = @{}
    # Iterate through JSON data and organize by panel and category
    foreach ($entry in $configHashtable.Keys) {
        $entryInfo = $configHashtable[$entry]

        # Create an object for the application
        $entryObject = [PSCustomObject]@{
            Name        = $entry
            Category    = $entryInfo.Category
            Content     = $entryInfo.Content
            Panel       = if ($entryInfo.Panel) { $entryInfo.Panel } else { "0" }
            Link        = $entryInfo.link
            Description = $entryInfo.description
            Type        = $entryInfo.type
            ComboItems  = $entryInfo.ComboItems
            ComboDescriptions = $entryInfo.ComboDescriptions
            Registry    = $entryInfo.registry
            Checked     = $entryInfo.Checked
            ButtonWidth = $entryInfo.ButtonWidth
            GroupName   = $entryInfo.GroupName  # Added for RadioButton groupings
        }

        if (-not $organizedData.ContainsKey($entryObject.Panel)) {
            $organizedData[$entryObject.Panel] = @{}
        }

        if (-not $organizedData[$entryObject.Panel].ContainsKey($entryObject.Category)) {
            $organizedData[$entryObject.Panel][$entryObject.Category] = @()
        }

        # Store application data in an array under the category
        $organizedData[$entryObject.Panel][$entryObject.Category] += $entryObject

    }

    # Initialize panel count
    $panelcount = 0

    # Iterate through 'organizedData' by panel, category, and application
    $count = 0
    foreach ($panelKey in ($organizedData.Keys | Sort-Object)) {
        # Create a Border for each column
        $border = New-Object Windows.Controls.Border
        $border.VerticalAlignment = "Stretch"
        [System.Windows.Controls.Grid]::SetColumn($border, $panelcount)
        $border.style = $borderstyle
        $targetGrid.Children.Add($border) | Out-Null

        # Use a DockPanel to contain the content
        $dockPanelContainer = New-Object Windows.Controls.DockPanel
        $border.Child = $dockPanelContainer

        # Create a StackPanel for application content controls
        $stackPanelContainer = New-Object Windows.Controls.StackPanel
        $stackPanelContainer.HorizontalAlignment = 'Stretch'
        $stackPanelContainer.VerticalAlignment = 'Stretch'

        # Check if the target grid (or any ancestor) is already inside a ScrollViewer
        $hasOuterScrollViewer = $false
        $currentElement = $targetGrid
        while ($null -ne $currentElement) {
            if ($currentElement -is [System.Windows.Controls.ScrollViewer] -or $currentElement.GetType().Name -eq "ScrollViewer") {
                $hasOuterScrollViewer = $true
                break
            }
            $currentElement = $currentElement.Parent
        }

        if ($hasOuterScrollViewer) {
            # Add StackPanel directly to DockPanel without nesting a ScrollViewer
            [Windows.Controls.DockPanel]::SetDock($stackPanelContainer, [Windows.Controls.Dock]::Bottom)
            $dockPanelContainer.Children.Add($stackPanelContainer) | Out-Null
        }
        else {
            # Create a ScrollViewer for targets that do not already have an outer ScrollViewer
            $scrollViewer = New-Object Windows.Controls.ScrollViewer
            $scrollViewer.VerticalScrollBarVisibility = "Auto"
            $scrollViewer.HorizontalScrollBarVisibility = "Disabled"
            $scrollViewer.HorizontalAlignment = 'Stretch'
            $scrollViewer.VerticalAlignment = 'Stretch'
            $scrollViewer.Content = $stackPanelContainer

            [Windows.Controls.DockPanel]::SetDock($scrollViewer, [Windows.Controls.Dock]::Bottom)
            $dockPanelContainer.Children.Add($scrollViewer) | Out-Null
        }
        $panelcount++

        # Now proceed with adding category labels and entries to $stackPanelContainer
        foreach ($category in ($organizedData[$panelKey].Keys | Sort-Object)) {
            $count++

            $label = New-Object Windows.Controls.Label
            $categoryCleanName = $category -replace ".*__", ""
            $label.Content = $categoryCleanName
            $label.Focusable = $true
            $label.IsTabStop = $true
            [System.Windows.Automation.AutomationProperties]::SetName($label, $categoryCleanName)
            $label.SetResourceReference([Windows.Controls.Control]::FontSizeProperty, "HeaderFontSize")
            $label.SetResourceReference([Windows.Controls.Control]::FontFamilyProperty, "HeaderFontFamily")
            $label.UseLayoutRounding = $true
            $stackPanelContainer.Children.Add($label) | Out-Null
            $sync[$category] = $label

            # Sort entries by type (checkboxes first, then buttons, then comboboxes, notes last) and then alphabetically by Content
            $entries = $organizedData[$panelKey][$category] | Sort-Object @{Expression = {
                switch ($_.Type) {
                    'Button' { 1 }
                    'Combobox' { 2 }
                    'Note' { 3 }
                    default { 0 }
                }
            }}, Content
            foreach ($entryInfo in $entries) {
                $count++
                # Create the UI elements based on the entry type
                switch ($entryInfo.Type) {
                    "Toggle" {
                        $dockPanel = New-Object Windows.Controls.DockPanel
                        [System.Windows.Automation.AutomationProperties]::SetName($dockPanel, $entryInfo.Content)
                        $checkBox = New-Object Windows.Controls.CheckBox
                        $checkBox.Name = $entryInfo.Name
                        $checkBox.HorizontalAlignment = "Right"
                        $checkBox.UseLayoutRounding = $true
                        [System.Windows.Automation.AutomationProperties]::SetName($checkBox, $entryInfo.Content)
                        $dockPanel.Children.Add($checkBox) | Out-Null
                        $checkBox.Style = $ColorfulToggleSwitchStyle

                        $label = New-Object Windows.Controls.Label
                        $label.Content = $entryInfo.Content
                        $label.ToolTip = $entryInfo.Description
                        $label.HorizontalAlignment = "Left"
                        $label.SetResourceReference([Windows.Controls.Control]::FontSizeProperty, "FontSize")
                        $label.SetResourceReference([Windows.Controls.Control]::ForegroundProperty, "MainForegroundColor")
                        $label.UseLayoutRounding = $true
                        $dockPanel.Children.Add($label) | Out-Null
                        $stackPanelContainer.Children.Add($dockPanel) | Out-Null

                        $sync[$entryInfo.Name] = $checkBox
                        $sync[$entryInfo.Name].IsChecked = (Get-WinUtilToggleStatus $entryInfo.Name)

                        $sync[$entryInfo.Name].Add_Checked({
                            [System.Object]$Sender = $args[0]
                            Invoke-WPFSelectedCheckboxesUpdate -type "Add" -checkboxName $Sender.name
                            # Skip applying tweaks while an import is restoring toggle states
                            if (-not $sync.ImportInProgress) {
                                Invoke-WinUtilTweaks $Sender.name
                            }
                        })

                        $sync[$entryInfo.Name].Add_Unchecked({
                            [System.Object]$Sender = $args[0]
                            Invoke-WPFSelectedCheckboxesUpdate -type "Remove" -checkboxName $Sender.name
                            # Skip undoing tweaks while an import is restoring toggle states
                            if (-not $sync.ImportInProgress) {
                                Invoke-WinUtiltweaks $Sender.name -undo $true
                            }
                        })
                    }

                    "ToggleButton" {
                        $toggleButton = New-Object Windows.Controls.Primitives.ToggleButton
                        $toggleButton.Name = $entryInfo.Name
                        $toggleButton.Content = $entryInfo.Content[1]
                        $toggleButton.ToolTip = Get-WinUtilEntryToolTip -Description $entryInfo.Description -Key $entryInfo.Name
                        $toggleButton.HorizontalAlignment = "Left"
                        $toggleButton.Style = $ToggleButtonStyle
                        [System.Windows.Automation.AutomationProperties]::SetName($toggleButton, $entryInfo.Content[0])

                        $toggleButton.Tag = @{
                            contentOn = if ($entryInfo.Content.Count -ge 1) { $entryInfo.Content[0] } else { "" }
                            contentOff = if ($entryInfo.Content.Count -ge 2) { $entryInfo.Content[1] } else { $contentOn }
                        }

                        $stackPanelContainer.Children.Add($toggleButton) | Out-Null

                        $sync[$entryInfo.Name] = $toggleButton

                        $sync[$entryInfo.Name].Add_Checked({
                            $this.Content = $this.Tag.contentOn
                        })

                        $sync[$entryInfo.Name].Add_Unchecked({
                            $this.Content = $this.Tag.contentOff
                        })

                        if ($null -eq $sync.Buttons) {
                            $sync.Buttons = [System.Collections.Generic.List[PSObject]]::new()
                        }

                        if ($sync.Buttons -notcontains $toggleButton.Name) {
                            $toggleButton.Add_Click({
                                [System.Object]$Sender = $args[0]
                                Invoke-WPFButton $Sender.name
                            })
                            $sync.Buttons.Add($toggleButton.Name) | Out-Null
                        }
                    }

                    "Combobox" {
                        $horizontalStackPanel = New-Object Windows.Controls.StackPanel
                        $horizontalStackPanel.Orientation = "Horizontal"
                        $horizontalStackPanel.Margin = "0,5,0,0"
                        [System.Windows.Automation.AutomationProperties]::SetName($horizontalStackPanel, $entryInfo.Content)

                        $label = New-Object Windows.Controls.Label
                        $label.Content = $entryInfo.Content
                        $label.HorizontalAlignment = "Left"
                        $label.ToolTip = $entryInfo.Description
                        $label.VerticalAlignment = "Center"
                        $label.SetResourceReference([Windows.Controls.Control]::FontSizeProperty, "ButtonFontSize")
                        $label.UseLayoutRounding = $true
                        $horizontalStackPanel.Children.Add($label) | Out-Null

                        $comboBox = New-Object Windows.Controls.ComboBox
                        $comboBox.Name = $entryInfo.Name
                        $comboBox.SetResourceReference([Windows.Controls.Control]::HeightProperty, "ButtonHeight")
                        $comboBox.SetResourceReference([Windows.Controls.Control]::WidthProperty, "ButtonWidth")
                        $comboBox.HorizontalAlignment = "Left"
                        $comboBox.VerticalAlignment = "Center"
                        $comboBox.SetResourceReference([Windows.Controls.Control]::MarginProperty, "ButtonMargin")
                        $comboBox.SetResourceReference([Windows.Controls.Control]::FontSizeProperty, "ButtonFontSize")
                        $comboBox.UseLayoutRounding = $true
                        $comboBox.Tag = [pscustomobject]@{
                            Registry = $entryInfo.Registry
                            State = $null
                        }
                        [System.Windows.Automation.AutomationProperties]::SetName($comboBox, $entryInfo.Content)

                        $comboItems = if ($entryInfo.ComboItems -is [string]) {
                            if ($entryInfo.ComboItems.Contains("|")) {
                                $entryInfo.ComboItems -split "\|"
                            } else {
                                $entryInfo.ComboItems -split " "
                            }
                        } else {
                            @($entryInfo.ComboItems)
                        }

                        foreach ($comboitem in $comboItems) {
                            $comboBoxItem = New-Object Windows.Controls.ComboBoxItem
                            $comboBoxItem.Content = $comboitem
                            if ($entryInfo.ComboDescriptions) {
                                $comboDescription = $entryInfo.ComboDescriptions.PSObject.Properties[$comboitem].Value
                                if ($comboDescription) {
                                    $comboBoxItem.ToolTip = $comboDescription
                                }
                            }
                            $comboBoxItem.SetResourceReference([Windows.Controls.Control]::FontSizeProperty, "ButtonFontSize")
                            $comboBoxItem.UseLayoutRounding = $true
                            $comboBox.Items.Add($comboBoxItem) | Out-Null
                        }

                        $horizontalStackPanel.Children.Add($comboBox) | Out-Null
                        $stackPanelContainer.Children.Add($horizontalStackPanel) | Out-Null

                        if ($entryInfo.Registry -and @($entryInfo.Registry)[0].Values) {
                            try {
                                $comboBox.Tag.State = Get-WinUtilRegistryComboState -Registry $entryInfo.Registry
                                $comboBox.SelectedIndex = @($comboBox.Items.Content).IndexOf([string]$comboBox.Tag.State)
                            } catch {
                                $unknownStateItem = New-Object Windows.Controls.ComboBoxItem
                                $unknownStateItem.Content = "Personalizado / desconhecido - selecione um estado"
                                $unknownStateItem.IsEnabled = $false
                                $unknownStateItem.ToolTip = "$($_.Exception.Message) Selecione um dos estados suportados para substituir esses valores."
                                $comboBox.Items.Add($unknownStateItem) | Out-Null
                                $comboBox.SelectedItem = $unknownStateItem
                                $comboBox.ToolTip = $unknownStateItem.ToolTip
                            }
                        } else {
                            $comboBox.SelectedIndex = 0
                        }

                        # Set initial text
                        if ($comboBox.Items.Count -gt 0) {
                            $comboBox.Text = $comboBox.SelectedItem.Content
                        }

                        $sync[$entryInfo.Name] = $comboBox

                        # Add SelectionChanged event handler to update the text property
                        $comboBox.Add_SelectionChanged({
                            $selectedItem = $this.SelectedItem
                            if ($selectedItem) {
                                $this.Text = $selectedItem.Content
                                $registry = $this.Tag.Registry
                                if ($registry -and $selectedItem.IsEnabled -and $selectedItem.Content -ne $this.Tag.State) {
                                    try {
                                        Set-WinUtilRegistryComboState -Registry $registry -State $selectedItem.Content
                                        $this.Tag.State = $selectedItem.Content
                                        $this.ToolTip = $null
                                        $unknownStateItem = @($this.Items) | Where-Object Content -EQ "Personalizado / desconhecido - selecione um estado" | Select-Object -First 1
                                        if ($unknownStateItem) {
                                            $this.Items.Remove($unknownStateItem)
                                        }
                                    } catch {
                                        $applyError = $_.Exception.Message
                                        if ([string]::IsNullOrWhiteSpace($applyError)) {
                                            $applyError = "Não foi possível aplicar o estado de registro '$($selectedItem.Content)'."
                                        }
                                        $previousState = if ($this.Tag.State) { $this.Tag.State } else { "Personalizado / desconhecido - selecione um estado" }
                                        $this.SelectedItem = @($this.Items) | Where-Object Content -EQ $previousState | Select-Object -First 1
                                        [System.Windows.MessageBox]::Show(
                                            $applyError,
                                            "Azor WinUtil",
                                            [System.Windows.MessageBoxButton]::OK,
                                            [System.Windows.MessageBoxImage]::Warning
                                        ) | Out-Null
                                    }
                                }
                            }
                        })

                        if ($entryInfo.Registry -and @($entryInfo.Registry)[0].Values -and $entryInfo.Link) {
                            $textBlock = New-Object Windows.Controls.TextBlock
                            $textBlock.Name = $comboBox.Name + "Link"
                            $textBlock.Text = "(?)"
                            $textBlock.ToolTip = $entryInfo.Link
                            $textBlock.Style = $HoverTextBlockStyle
                            $textBlock.UseLayoutRounding = $true
                            $textBlock.VerticalAlignment = "Center"
                            $textBlock.SetResourceReference([Windows.Controls.Control]::FontSizeProperty, "FontSize")
                            $textBlock.Tag = $comboBox

                            $textBlock.Add_MouseUp({
                                [System.Object]$Sender = $args[0]
                                Start-Process $Sender.ToolTip -ErrorAction Stop
                            })

                            $horizontalStackPanel.Children.Add($textBlock) | Out-Null
                            $sync[$textBlock.Name] = $textBlock
                        }
                    }

                    "Button" {
                        $button = New-Object Windows.Controls.Button
                        $button.Name = $entryInfo.Name
                        $button.Content = $entryInfo.Content
                        $button.HorizontalAlignment = "Left"
                        $button.SetResourceReference([Windows.Controls.Control]::MarginProperty, "ButtonMargin")
                        $button.SetResourceReference([Windows.Controls.Control]::FontSizeProperty, "ButtonFontSize")
                        if ($entryInfo.ButtonWidth) {
                            $baseWidth = [int]$entryInfo.ButtonWidth
                            $button.Width = [math]::Max($baseWidth, 350)
                        }
                        [System.Windows.Automation.AutomationProperties]::SetName($button, $entryInfo.Content)
                        $stackPanelContainer.Children.Add($button) | Out-Null

                        $sync[$entryInfo.Name] = $button

                        if ($null -eq $sync.Buttons) {
                            $sync.Buttons = [System.Collections.Generic.List[PSObject]]::new()
                        }

                        if ($sync.Buttons -notcontains $button.Name) {
                            $button.Add_Click({
                                [System.Object]$Sender = $args[0]
                                Invoke-WPFButton $Sender.name
                            })
                            $sync.Buttons.Add($button.Name) | Out-Null
                        }
                    }

                    "RadioButton" {
                        # Check if a container for this GroupName already exists
                        if (-not $radioButtonGroups.ContainsKey($entryInfo.GroupName)) {
                            # Create a StackPanel for this group
                            $groupStackPanel = New-Object Windows.Controls.StackPanel
                            $groupStackPanel.Orientation = "Vertical"
                            [System.Windows.Automation.AutomationProperties]::SetName($groupStackPanel, $entryInfo.GroupName)
                            $radioButtonGroups[$entryInfo.GroupName] = $groupStackPanel

                            # Add the group container to the ItemsControl
                            $stackPanelContainer.Children.Add($groupStackPanel) | Out-Null
                        }
                        else {
                            # Retrieve the existing group container
                            $groupStackPanel = $radioButtonGroups[$entryInfo.GroupName]
                        }

                        # Create the RadioButton
                        $radioButton = New-Object Windows.Controls.RadioButton
                        $radioButton.Name = $entryInfo.Name
                        $radioButton.GroupName = $entryInfo.GroupName
                        $radioButton.Content = $entryInfo.Content
                        $radioButton.HorizontalAlignment = "Left"
                        $radioButton.SetResourceReference([Windows.Controls.Control]::MarginProperty, "CheckBoxMargin")
                        $radioButton.SetResourceReference([Windows.Controls.Control]::FontSizeProperty, "ButtonFontSize")
                        $radioButton.ToolTip = $entryInfo.Description
                        $radioButton.UseLayoutRounding = $true
                        [System.Windows.Automation.AutomationProperties]::SetName($radioButton, $entryInfo.Content)

                        if ($entryInfo.Checked -eq $true) {
                            $radioButton.IsChecked = $true
                        }

                        # Add the RadioButton to the group container
                        $groupStackPanel.Children.Add($radioButton) | Out-Null
                        $sync[$entryInfo.Name] = $radioButton
                    }

                    "Note" {
                        $textBlock = New-Object Windows.Controls.TextBlock
                        $textBlock.TextWrapping = "Wrap"
                        $textBlock.Margin = "5,5,5,5"
                        $textBlock.UseLayoutRounding = $true

                        $bulletBadge = [Windows.Documents.InlineUIContainer]::new((New-WinUtilFossBadge -Size 18 -Round))
                        $bulletBadge.BaselineAlignment = [Windows.BaselineAlignment]::Center

                        $textRun = New-Object Windows.Documents.Run
                        $textRun.Text = " $($entryInfo.Content)"
                        $textRun.SetResourceReference([Windows.Controls.Control]::FontSizeProperty, "FontSize")
                        $textRun.SetResourceReference([Windows.Controls.Control]::ForegroundProperty, "SuccessColor")

                        $textBlock.Inlines.Add($bulletBadge)
                        $textBlock.Inlines.Add($textRun)

                        $stackPanelContainer.Children.Add($textBlock) | Out-Null
                    }

                    default {
                        $horizontalStackPanel = New-Object Windows.Controls.StackPanel
                        $horizontalStackPanel.Orientation = "Horizontal"
                        [System.Windows.Automation.AutomationProperties]::SetName($horizontalStackPanel, $entryInfo.Content)

                        $checkBox = New-Object Windows.Controls.CheckBox
                        $checkBox.Name = $entryInfo.Name
                        $checkBox.Content = $entryInfo.Content
                        $checkBox.SetResourceReference([Windows.Controls.Control]::FontSizeProperty, "FontSize")
                        $checkBox.ToolTip = Get-WinUtilEntryToolTip -Description $entryInfo.Description -Key $entryInfo.Name
                        $checkBox.SetResourceReference([Windows.Controls.Control]::MarginProperty, "CheckBoxMargin")
                        $checkBox.UseLayoutRounding = $true
                        [System.Windows.Automation.AutomationProperties]::SetName($checkBox, $entryInfo.Content)
                        if ($entryInfo.Checked -eq $true) {
                            $checkBox.IsChecked = $entryInfo.Checked
                        }
                        $horizontalStackPanel.Children.Add($checkBox) | Out-Null

                        if ($entryInfo.Link) {
                            $textBlock = New-Object Windows.Controls.TextBlock
                            $textBlock.Name = $checkBox.Name + "Link"
                            $textBlock.Text = "(?)"
                            $textBlock.ToolTip = $entryInfo.Link
                            $textBlock.Style = $HoverTextBlockStyle
                            $textBlock.UseLayoutRounding = $true

                            $textBlock.VerticalAlignment = "Center"
                            $textBlock.SetResourceReference([Windows.Controls.Control]::FontSizeProperty, "FontSize")
                            $textBlock.Tag = $checkBox

                            $textBlock.Add_MouseUp({
                                [System.Object]$Sender = $args[0]
                                Start-Process $Sender.ToolTip -ErrorAction Stop
                            })

                            $updateLinkMargin = {
                                [System.Object]$Sender = $args[0]
                                $linkedCheckBox = $Sender.Tag
                                $MarginTopBase = if ($linkedCheckBox) { $linkedCheckBox.Margin.Top } else { 0 }
                                $Sender.Margin = New-Object Windows.Thickness(
                                    [math]::Round($Sender.FontSize * 0.5),
                                    ($MarginTopBase - [math]::Round($Sender.FontSize / 2)),
                                    0, 0
                                )
                            }
                            $textBlock.Add_Loaded($updateLinkMargin)
                            $fontSizeDescriptor = [System.ComponentModel.DependencyPropertyDescriptor]::FromProperty(
                                [Windows.Controls.Control]::FontSizeProperty,
                                [Windows.Controls.TextBlock]
                            )
                            $fontSizeDescriptor.AddValueChanged($textBlock, $updateLinkMargin)

                            $horizontalStackPanel.Children.Add($textBlock) | Out-Null

                            $sync[$textBlock.Name] = $textBlock
                        }

                        $stackPanelContainer.Children.Add($horizontalStackPanel) | Out-Null
                        $sync[$entryInfo.Name] = $checkBox

                        $sync[$entryInfo.Name].Add_Checked({
                            [System.Object]$Sender = $args[0]
                            Invoke-WPFSelectedCheckboxesUpdate -type "Add" -checkboxName $Sender.name
                        })

                        $sync[$entryInfo.Name].Add_Unchecked({
                            [System.Object]$Sender = $args[0]
                            Invoke-WPFSelectedCheckboxesUpdate -type "Remove" -checkboxName $Sender.name
                        })
                    }
                }
            }
        }
    }
}

function Invoke-WPFUIThread ($ScriptBlock) {
    if ($null -eq $sync.form -or $null -eq $sync.form.Dispatcher) {
        return
    }

    $sync.form.Dispatcher.Invoke([action]$ScriptBlock)
}

function Invoke-WPFUltimatePerformance ([switch]$Enable) {
    if ($Enable) {
        # Reuse an Ultimate Performance plan that already exists instead of adding a duplicate on every click
        $existingPlan = powercfg /list | Select-String -Pattern '([A-Fa-f0-9]{8}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{12})\s+\((Ultimate Performance|Desempenho M.ximo)\)' | Select-Object -First 1
        if ($existingPlan) {
            powercfg /setactive $existingPlan.Matches[0].Groups[1].Value
        } else {
            powercfg /setactive (powercfg /duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61 | Select-String -Pattern '[A-Fa-f0-9-]{36}').Matches.Value
        }
        [System.Windows.MessageBox]::Show("Plano de energia Desempenho Máximo ativado.","Azor WinUtil","OK","Information")
    } else {
        powercfg /restoredefaultschemes
        [System.Windows.MessageBox]::Show("Os planos de energia foram restaurados para o padrão do Windows.","Azor WinUtil","OK","Information")
    }
}

function Invoke-WPFundoall {
    <#

    .SYNOPSIS
        Undoes every selected tweak

    #>

    if($sync.ProcessRunning) {
        $msg = "Já existe um processo em andamento. Aguarde a conclusão."
        [System.Windows.MessageBox]::Show($msg, "Azor WinUtil", [System.Windows.MessageBoxButton]::OK, [System.Windows.MessageBoxImage]::Warning)
        return
    }

    $tweaks = $sync.selectedTweaks

    if ($tweaks.count -eq 0) {
        $msg = "Marque os ajustes que deseja desfazer."
        [System.Windows.MessageBox]::Show($msg, "Azor WinUtil", [System.Windows.MessageBoxButton]::OK, [System.Windows.MessageBoxImage]::Warning)
        return
    }

    Invoke-WPFRunspace -ArgumentList $tweaks -ScriptBlock {
        param($tweaks)

        $sync.ProcessRunning = $true
        Write-WinUtilLog -Component "Tweaks" -Message "Undo tweaks requested: $(@($tweaks).Count) selected tweak(s)."
        if ($tweaks.count -eq 1) {
            Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "Indeterminate" -value 0.01 -overlay "logo" }
        } else {
            Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "Normal" -value 0.01 -overlay "logo" }
        }


        for ($i = 0; $i -lt $tweaks.Count; $i++) {
            $tweakName = $sync.configs.tweaks.$($tweaks[$i]).Content
            if (-not $tweakName) {
                $tweakName = $tweaks[$i]
            }
            Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Desfazendo: $tweakName ($($i + 1)/$($tweaks.Count))" -Percent ($i / $tweaks.Count * 100)
            Invoke-WinUtiltweaks $tweaks[$i] -undo $true
            Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -value ($i/$tweaks.Count) }
        }

        Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Ajustes desfeitos" -Percent 100
        $sync.ProcessRunning = $false
        Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "None" -overlay "checkmark" }
        Write-Host "=================================="
        Write-Host "---      Ajustes desfeitos     ---"
        Write-Host "=================================="
        Write-WinUtilLog -Component "Tweaks" -Message "Undo tweaks workflow completed."

    }
}

function Invoke-WPFUnInstall {
    param(
        [Parameter(Mandatory=$false)]
        [PSObject[]]$PackagesToUninstall = $($sync.selectedApps | Foreach-Object { $sync.configs.applicationsHashtable.$_ })
    )
    <#

    .SYNOPSIS
        Uninstalls the selected programs
    #>

    if($sync.ProcessRunning) {
        $msg = "Já existe uma instalação em andamento. Aguarde a conclusão."
        Show-WinUtilMessage -Message $msg -Title "Azor WinUtil" -Button "OK" -Icon "Warning"
        return
    }

    if ($PackagesToUninstall.Count -eq 0) {
        $WarningMsg = "Selecione os programas que deseja desinstalar."
        Show-WinUtilMessage -Message $WarningMsg -Title "Azor WinUtil" -Button "OK" -Icon "Warning"
        return
    }

    $ButtonType = "YesNo"
    $MessageboxTitle = "Tem certeza?"
    $Messageboxbody = ("Isto vai desinstalar os seguintes programas: `n $($PackagesToUninstall | Select-Object Name, Description| Out-String)")
    $MessageIcon = "Information"

    $confirm = Show-WinUtilMessage -Message $Messageboxbody -Title $MessageboxTitle -Button $ButtonType -Icon $MessageIcon

    if($confirm -eq "No") {return}

    $ManagerPreference = $sync.preferences.packagemanager
    Write-WinUtilLog -Component "Uninstall" -Message "Uninstall requested for $(@($PackagesToUninstall).Count) selected package(s) using preference: $ManagerPreference"
    $packageSummary = Get-WinUtilPackageLogSummary -Packages $PackagesToUninstall -Preference $ManagerPreference
    Write-WinUtilLog -Component "Uninstall" -Message "Uninstall selected package(s): $($packageSummary -join '; ')"

    Invoke-WPFRunspace -ParameterList @(("PackagesToUninstall", $PackagesToUninstall),("ManagerPreference", $ManagerPreference)) -ScriptBlock {
        param($PackagesToUninstall, $ManagerPreference)

        $packagesSorted = Get-WinUtilSelectedPackages -PackageList $PackagesToUninstall -Preference $ManagerPreference

        $packagesWinget = $packagesSorted['Winget']
        $packagesChoco = $packagesSorted['Choco']
        $totalPackages = @($packagesWinget).Count + @($packagesChoco).Count
        $completedPackages = 0
        $hasUI = $null -ne $sync.Form -and $null -ne $sync.Form.Dispatcher
        Write-WinUtilLog -Component "Uninstall" -Message "Uninstall package manager split: winget=$(@($packagesWinget).Count), choco=$(@($packagesChoco).Count)"

        try {
            $sync.ProcessRunning = $true
            if ($hasUI) {
                Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Preparando a desinstalação de programas (0/$totalPackages)" -Percent 0
                Invoke-WPFUIThread -ScriptBlock {
                    if ($null -ne $sync.ItemsControl) {
                        $sync.ItemsControl.IsEnabled = $false
                    }
                }
            }

            if ($packagesWinget -contains "Microsoft.Edge") {
                New-Item -Path "$Env:SystemRoot\SystemApps\Microsoft.MicrosoftEdge_8wekyb3d8bbwe\MicrosoftEdge.exe" -Force
            }

            # Uninstall all selected programs in new window
            if($packagesWinget.Count -gt 0) {
                foreach ($program in $packagesWinget) {
                    $position = $completedPackages + 1
                    $startPercent = [int](($completedPackages / $totalPackages) * 100)
                    if ($hasUI) {
                        Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Desinstalando $program ($position/$totalPackages)" -Percent $startPercent
                    }

                    Install-WinUtilProgramWinget -Action Uninstall -Programs @($program)
                    $completedPackages++
                    $completedPercent = [int](($completedPackages / $totalPackages) * 100)
                    if ($hasUI) {
                        Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Desinstalado: $program ($completedPackages/$totalPackages)" -Percent $completedPercent
                        Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -value ($completedPercent / 100) }
                    }
                }
            }
            if($packagesChoco.Count -gt 0) {
                $position = $completedPackages + 1
                $startPercent = [int](($completedPackages / $totalPackages) * 100)
                if ($hasUI) {
                    Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Desinstalando pacotes do Chocolatey ($position/$totalPackages)" -Percent $startPercent
                }

                Install-WinUtilProgramChoco -Action Uninstall -Programs $packagesChoco
                $completedPackages += @($packagesChoco).Count
                $completedPercent = [int](($completedPackages / $totalPackages) * 100)
                if ($hasUI) {
                    Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Pacotes do Chocolatey desinstalados ($completedPackages/$totalPackages)" -Percent $completedPercent
                    Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -value ($completedPercent / 100) }
                }
            }
            Write-Host "==========================================="
            Write-Host "--       Desinstalações concluídas       --"
            Write-Host "==========================================="
            Write-WinUtilLog -Component "Uninstall" -Message "Uninstall workflow completed."
            if ($hasUI) {
                Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Desinstalação de programas concluída" -Percent 100
                Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "None" -overlay "checkmark" }
            }
        } catch {
            Write-Host "==========================================="
            Write-Host "Erro: $_"
            Write-Host "==========================================="
            Write-WinUtilLog -Level "ERROR" -Component "Uninstall" -Message "Uninstall workflow failed: $($_.Exception.Message)"
            if ($hasUI) {
                Set-WinUtilTweaksProgressIndicator -Visible $true -Label "Falha na desinstalação de programas" -Percent 100
                Invoke-WPFUIThread -ScriptBlock { Set-WinUtilTaskbaritem -state "Error" -overlay "warning" }
            }
        } finally {
            if ($hasUI) {
                Invoke-WPFUIThread -ScriptBlock {
                    if ($null -ne $sync.ItemsControl) {
                        $sync.ItemsControl.IsEnabled = $true
                    }
                }
            }
            $sync.ProcessRunning = $False
        }

    }
}

function Invoke-WPFUpdatesdefault {
    <#

    .SYNOPSIS
        Resets Windows Update settings to default

    #>
    Write-WinUtilLog -Component "Updates" -Message "Resetting Windows Update settings to default."

    Write-Host "Removing Windows Update settings managed by WinUtil..." -ForegroundColor Green
    Write-WinUtilLog -Component "Updates" -Message "Removing Windows Update registry values managed by WinUtil."

    $registryValues = @(
        @{
            Path = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU"
            Names = @("NoAutoUpdate", "AUOptions", "NoAutoRebootWithLoggedOnUsers", "AUPowerManagement")
        },
        @{
            Path = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate"
            Names = @("ExcludeWUDriversInQualityUpdate", "DeferFeatureUpdates", "DeferFeatureUpdatesPeriodInDays", "DeferQualityUpdates", "DeferQualityUpdatesPeriodInDays")
        },
        @{
            Path = "HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings"
            Names = @("BranchReadinessLevel", "DeferFeatureUpdatesPeriodInDays", "DeferQualityUpdatesPeriodInDays")
        },
        @{
            Path = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\Device Metadata"
            Names = @("PreventDeviceMetadataFromNetwork")
        },
        @{
            Path = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\DriverSearching"
            Names = @("DontPromptForWindowsUpdate", "DontSearchWindowsUpdate", "DriverUpdateWizardWuSearchEnabled")
        },
        @{
            Path = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\DeliveryOptimization\Config"
            Names = @("DODownloadMode")
        }
    )

    foreach ($registryEntry in $registryValues) {
        foreach ($valueName in $registryEntry.Names) {
            Remove-ItemProperty -Path $registryEntry.Path -Name $valueName -ErrorAction SilentlyContinue
        }
    }

    $explorerPolicyPath = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer"
    $settingsPageVisibility = (Get-ItemProperty -Path $explorerPolicyPath -Name "SettingsPageVisibility" -ErrorAction SilentlyContinue).SettingsPageVisibility
    if ($settingsPageVisibility -eq "hide:windowsupdate") {
        Write-Host "Removing WinUtil's legacy Windows Update page restriction..."
        Write-WinUtilLog -Component "Updates" -Message "Removing the legacy Windows Update settings page restriction."
        Remove-ItemProperty -Path $explorerPolicyPath -Name "SettingsPageVisibility" -ErrorAction SilentlyContinue
    }

    Write-Host "Reenabling Windows Update Services..." -ForegroundColor Green
    Write-WinUtilLog -Component "Updates" -Message "Restoring Windows Update service startup types."

    Write-Host "Restored BITS to Manual."
    Write-WinUtilLog -Component "Updates" -Message "Restoring BITS service to Manual."
    Set-Service -Name BITS -StartupType Manual

    Write-Host "Restored wuauserv to Manual."
    Write-WinUtilLog -Component "Updates" -Message "Restoring wuauserv service to Manual."
    Set-Service -Name wuauserv -StartupType Manual

    Write-Host "Restored UsoSvc to Automatic."
    Write-WinUtilLog -Component "Updates" -Message "Starting UsoSvc service and restoring startup type to Automatic."
    Set-Service -Name UsoSvc -StartupType Automatic
    Start-Service -Name UsoSvc

    Write-Host "Enabling update related scheduled tasks..." -ForegroundColor Green
    Write-WinUtilLog -Component "Updates" -Message "Enabling update related scheduled tasks."

    $Tasks =
        '\Microsoft\Windows\InstallService\*',
        '\Microsoft\Windows\UpdateOrchestrator\*',
        '\Microsoft\Windows\UpdateAssistant\*',
        '\Microsoft\Windows\WaaSMedic\*',
        '\Microsoft\Windows\WindowsUpdate\*',
        '\Microsoft\WindowsUpdate\*'

    foreach ($Task in $Tasks) {
        Get-ScheduledTask -TaskPath $Task -ErrorAction SilentlyContinue | Enable-ScheduledTask -ErrorAction SilentlyContinue
    }

    Write-Host "===================================================" -ForegroundColor Green
    Write-Host "---  Windows Update Settings Reset to Default   ---" -ForegroundColor Green
    Write-Host "===================================================" -ForegroundColor Green

    Write-Host "Note: You must restart your system in order for all changes to take effect." -ForegroundColor Yellow
    Write-WinUtilLog -Component "Updates" -Message "Windows Update default workflow completed. Restart required."

    if ($sync.Form) {
        Show-WinUtilMessage -Message "O Windows Update voltou ao padrão: as políticas criadas pelo Azor WinUtil foram removidas e os serviços e tarefas de atualização foram reativados.`n`nReinicie o PC para concluir." -Title "Azor WinUtil - Windows Update" -Button "OK" -Icon "Information" | Out-Null
    }
}

$sync.configs.applications = @'
{
    "WPFInstall1password":  {
                                "category":  "Utilitários",
                                "choco":  "1password",
                                "content":  "1Password",
                                "description":  "1Password is a password manager that allows you to store and manage your passwords securely.",
                                "link":  "https://1password.com/",
                                "winget":  "AgileBits.1Password",
                                "foss":  false
                            },
    "WPFInstall7zip":  {
                           "category":  "Utilitários",
                           "choco":  "7zip",
                           "content":  "7-Zip",
                           "description":  "7-Zip is a free and open-source file archiver utility. It supports several compression formats and provides a high compression ratio, making it a popular choice for file compression.",
                           "link":  "https://www.7-zip.org/",
                           "winget":  "7zip.7zip",
                           "foss":  true
                       },
    "WPFInstalladobe":  {
                            "category":  "Documentos",
                            "choco":  "adobereader",
                            "content":  "Adobe Acrobat Reader",
                            "description":  "Adobe Acrobat Reader is a free PDF viewer with essential features for viewing, printing, and annotating PDF documents.",
                            "link":  "https://www.adobe.com/acrobat/pdf-reader.html",
                            "winget":  "Adobe.Acrobat.Reader.64-bit",
                            "foss":  false
                        },
    "WPFInstallaimp":  {
                           "category":  "Multimídia",
                           "choco":  "aimp",
                           "content":  "AIMP (Music Player)",
                           "description":  "AIMP is a feature-rich music player with support for various audio formats, playlists, and customizable user interface.",
                           "link":  "https://www.aimp.ru/",
                           "winget":  "AIMP.AIMP",
                           "foss":  false
                       },
    "WPFInstallanydesk":  {
                              "category":  "Utilitários",
                              "choco":  "anydesk",
                              "content":  "AnyDesk",
                              "description":  "AnyDesk is a remote desktop software that enables users to access and control computers remotely. It is known for its fast connection and low latency.",
                              "link":  "https://anydesk.com/",
                              "winget":  "AnyDesk.AnyDesk",
                              "foss":  false
                          },
    "WPFInstallaudacity":  {
                               "category":  "Multimídia",
                               "choco":  "audacity",
                               "content":  "Audacity",
                               "description":  "Audacity is a free and open-source audio editing software known for its powerful recording and editing capabilities.",
                               "link":  "https://www.audacityteam.org/",
                               "winget":  "Audacity.Audacity",
                               "foss":  true
                           },
    "WPFInstallautoruns":  {
                               "category":  "Ferramentas Microsoft",
                               "choco":  "autoruns",
                               "content":  "Autoruns",
                               "description":  "This utility shows you what programs are configured to run during system bootup or login.",
                               "link":  "https://learn.microsoft.com/en-us/sysinternals/downloads/autoruns",
                               "winget":  "Microsoft.Sysinternals.Autoruns",
                               "foss":  false
                           },
    "WPFInstallautohotkey":  {
                                 "category":  "Utilitários",
                                 "choco":  "autohotkey",
                                 "content":  "AutoHotkey",
                                 "description":  "AutoHotkey is a scripting language for Windows that allows users to create custom automation scripts and macros. It is often used for automating repetitive tasks and customizing keyboard shortcuts.",
                                 "link":  "https://www.autohotkey.com/",
                                 "winget":  "AutoHotkey.AutoHotkey",
                                 "foss":  true
                             },
    "WPFInstallbattlenet":  {
                                "category":  "Jogos",
                                "choco":  "na",
                                "winget":  "Blizzard.BattleNet",
                                "content":  "Battle.net",
                                "description":  "Battle.net is a launcher for games created and developed by Activision Blizzard",
                                "link":  "https://battle.net",
                                "foss":  false
                            },
    "WPFInstallbitwarden":  {
                                "category":  "Utilitários",
                                "choco":  "bitwarden",
                                "content":  "Bitwarden",
                                "description":  "Bitwarden is an open-source password management solution. It allows users to store and manage their passwords in a secure and encrypted vault, accessible across multiple devices.",
                                "link":  "https://bitwarden.com/",
                                "winget":  "Bitwarden.Bitwarden",
                                "foss":  true
                            },
    "WPFInstallblender":  {
                              "category":  "Multimídia",
                              "choco":  "blender",
                              "content":  "Blender (3D Graphics)",
                              "description":  "Blender is a powerful open-source 3D creation suite, offering modeling, sculpting, animation, and rendering tools.",
                              "link":  "https://www.blender.org/",
                              "winget":  "BlenderFoundation.Blender",
                              "foss":  true
                          },
    "WPFInstallbrave":  {
                            "category":  "Navegadores",
                            "choco":  "brave",
                            "content":  "Brave",
                            "description":  "Brave is a privacy-focused web browser that blocks ads and trackers, offering a faster and safer browsing experience.",
                            "link":  "https://www.brave.com",
                            "winget":  "Brave.Brave",
                            "foss":  true
                        },
    "WPFInstallbulkcrapuninstaller":  {
                                          "category":  "Utilitários",
                                          "choco":  "bulk-crap-uninstaller",
                                          "content":  "Bulk Crap Uninstaller",
                                          "description":  "Bulk Crap Uninstaller is a free and open-source uninstaller utility for Windows. It helps users remove unwanted programs and clean up their system by uninstalling multiple applications at once.",
                                          "link":  "https://www.bcuninstaller.com/",
                                          "winget":  "Klocman.BulkCrapUninstaller",
                                          "foss":  true
                                      },
    "WPFInstallblurautoclicker":  {
                                      "category":  "Utilitários",
                                      "choco":  "na",
                                      "content":  "BlurAutoClicker",
                                      "description":  "An Auto-clicker with a few advanced features and generally better performance than popular alternatives.",
                                      "link":  "https://blur009.vercel.app/projects/blur-autoclicker/",
                                      "winget":  "Blur009.BlurAutoClicker",
                                      "foss":  true
                                  },
    "WPFInstallcalibre":  {
                              "category":  "Multimídia",
                              "choco":  "calibre",
                              "content":  "Calibre",
                              "description":  "Calibre is a powerful and easy-to-use e-book manager, viewer, and converter.",
                              "link":  "https://calibre-ebook.com/",
                              "winget":  "calibre.calibre",
                              "foss":  true
                          },
    "WPFInstallcemu":  {
                           "category":  "Jogos",
                           "choco":  "cemu",
                           "content":  "Cemu",
                           "description":  "Cemu is a highly experimental software to emulate Wii U applications on PC.",
                           "link":  "https://cemu.info/",
                           "winget":  "Cemu.Cemu",
                           "foss":  true
                       },
    "WPFInstallchatgpt":  {
                              "category":  "Utilitários",
                              "choco":  "na",
                              "content":  "ChatGPT Desktop",
                              "description":  "The official ChatGPT desktop app for Windows, distributed through the Microsoft Store.",
                              "link":  "https://openai.com/chatgpt/download/",
                              "winget":  "msstore:9NT1R1C2HH7J",
                              "foss":  false
                          },
    "WPFInstallchatterino":  {
                                 "category":  "Comunicação",
                                 "choco":  "chatterino",
                                 "content":  "Chatterino",
                                 "description":  "Chatterino is a chat client for Twitch chat that offers a clean and customizable interface for a better streaming experience.",
                                 "link":  "https://www.chatterino.com/",
                                 "winget":  "ChatterinoTeam.Chatterino",
                                 "foss":  true
                             },
    "WPFInstallchrome":  {
                             "category":  "Navegadores",
                             "choco":  "googlechrome",
                             "content":  "Chrome",
                             "description":  "Google Chrome is a widely used web browser known for its speed, simplicity, and seamless integration with Google services.",
                             "link":  "https://www.google.com/chrome/",
                             "winget":  "Google.Chrome",
                             "foss":  false
                         },
    "WPFInstallchromium":  {
                               "category":  "Navegadores",
                               "choco":  "chromium",
                               "content":  "Chromium",
                               "description":  "Chromium is the open-source project that serves as the foundation for various web browsers, including Chrome.",
                               "link":  "https://www.chromium.org/",
                               "winget":  "Hibbiki.Chromium",
                               "foss":  true
                           },
    "WPFInstallcinebenchr23":  {
                                   "category":  "Ferramentas Pro",
                                   "choco":  "na",
                                   "content":  "Cinebench R23",
                                   "description":  "Cinebench R23 is a benchmark tool for comparing CPU rendering performance across systems.",
                                   "link":  "https://www.maxon.net/en/cinebench",
                                   "winget":  "Maxon.CinebenchR23",
                                   "foss":  false
                               },
    "WPFInstallclaude":  {
                             "category":  "Utilitários",
                             "choco":  "claude",
                             "content":  "Claude Desktop",
                             "description":  "Anthropic\u0027s Claude desktop application for focused AI-assisted work and chat.",
                             "link":  "https://claude.ai/download",
                             "winget":  "Anthropic.Claude",
                             "foss":  false
                         },
    "WPFInstallcpuz":  {
                           "category":  "Ferramentas Pro",
                           "choco":  "cpu-z",
                           "content":  "CPU-Z",
                           "description":  "CPU-Z is a system monitoring and diagnostic tool for Windows. It provides detailed information about the computer\u0027s hardware components, including the CPU, memory, and motherboard.",
                           "link":  "https://www.cpuid.com/softwares/cpu-z.html",
                           "winget":  "CPUID.CPU-Z",
                           "foss":  false
                       },
    "WPFInstallcrystaldiskinfo":  {
                                      "category":  "Utilitários",
                                      "choco":  "crystaldiskinfo",
                                      "content":  "Crystal Disk Info",
                                      "description":  "Crystal Disk Info is a disk health monitoring tool that provides information about the status and performance of hard drives. It helps users anticipate potential issues and monitor drive health.",
                                      "link":  "https://crystalmark.info/en/software/crystaldiskinfo/",
                                      "winget":  "CrystalDewWorld.CrystalDiskInfo",
                                      "foss":  true
                                  },
    "WPFInstallcrystaldiskmark":  {
                                      "category":  "Utilitários",
                                      "choco":  "crystaldiskmark",
                                      "content":  "Crystal Disk Mark",
                                      "description":  "Crystal Disk Mark is a disk benchmarking tool that measures the read and write speeds of storage devices. It helps users assess the performance of their hard drives and SSDs.",
                                      "link":  "https://crystalmark.info/en/software/crystaldiskmark/",
                                      "winget":  "CrystalDewWorld.CrystalDiskMark",
                                      "foss":  true
                                  },
    "WPFInstallddu":  {
                          "category":  "Ferramentas Pro",
                          "choco":  "ddu",
                          "content":  "Display Driver Uninstaller",
                          "description":  "Display Driver Uninstaller (DDU) is a tool for completely uninstalling graphics drivers from NVIDIA, AMD, and Intel. It is useful for troubleshooting graphics driver-related issues.",
                          "link":  "https://www.wagnardsoft.com/display-driver-uninstaller-DDU-",
                          "winget":  "Wagnardsoft.DisplayDriverUninstaller",
                          "foss":  true
                      },
    "WPFInstalldiscord":  {
                              "category":  "Comunicação",
                              "choco":  "discord",
                              "content":  "Discord",
                              "description":  "Discord is a popular communication platform with voice, video, and text chat, designed for gamers but used by a wide range of communities.",
                              "link":  "https://discord.com/",
                              "winget":  "Discord.Discord",
                              "foss":  false
                          },
    "WPFInstalldorion":  {
                             "category":  "Comunicação",
                             "choco":  "dorion",
                             "content":  "Dorion",
                             "description":  "Tiny alternative Discord client with a smaller footprint, snappier startup, themes, plugins and more!",
                             "link":  "https://spikehd.dev/projects/dorion/",
                             "winget":  "SpikeHD.Dorion",
                             "foss":  true
                         },
    "WPFInstalldotnet6":  {
                              "category":  "Ferramentas Microsoft",
                              "choco":  "dotnet-6.0-runtime",
                              "content":  ".NET Desktop Runtime 6",
                              "description":  ".NET Desktop Runtime 6 is a runtime environment required for running applications developed with .NET 6.",
                              "link":  "https://dotnet.microsoft.com/download/dotnet/6.0",
                              "winget":  "Microsoft.DotNet.DesktopRuntime.6",
                              "foss":  true
                          },
    "WPFInstalldotnet8":  {
                              "category":  "Ferramentas Microsoft",
                              "choco":  "dotnet-8.0-runtime",
                              "content":  ".NET Desktop Runtime 8",
                              "description":  ".NET Desktop Runtime 8 is a runtime environment required for running applications developed with .NET 8.",
                              "link":  "https://dotnet.microsoft.com/download/dotnet/8.0",
                              "winget":  "Microsoft.DotNet.DesktopRuntime.8",
                              "foss":  true
                          },
    "WPFInstalldotnet9":  {
                              "category":  "Ferramentas Microsoft",
                              "choco":  "dotnet-9.0-runtime",
                              "content":  ".NET Desktop Runtime 9",
                              "description":  ".NET Desktop Runtime 9 is a runtime environment required for running applications developed with .NET 9.",
                              "link":  "https://dotnet.microsoft.com/download/dotnet/9.0",
                              "winget":  "Microsoft.DotNet.DesktopRuntime.9",
                              "foss":  true
                          },
    "WPFInstalldotnet10":  {
                               "category":  "Ferramentas Microsoft",
                               "choco":  "dotnet-10.0-runtime",
                               "content":  ".NET Desktop Runtime 10",
                               "description":  ".NET Desktop Runtime 10 is a runtime environment required for running applications developed with .NET 10.",
                               "link":  "https://dotnet.microsoft.com/download/dotnet/10.0",
                               "winget":  "Microsoft.DotNet.DesktopRuntime.10",
                               "foss":  true
                           },
    "WPFInstalldropbox":  {
                              "category":  "Utilitários",
                              "choco":  "dropbox",
                              "content":  "Dropbox",
                              "description":  "Dropbox is a cloud storage client for syncing files, sharing content, and keeping documents available across devices.",
                              "link":  "https://www.dropbox.com/desktop",
                              "winget":  "Dropbox.Dropbox",
                              "foss":  false
                          },
    "WPFInstalleaapp":  {
                            "category":  "Jogos",
                            "choco":  "ea-app",
                            "content":  "EA App",
                            "description":  "EA App is a platform for accessing and playing Electronic Arts games.",
                            "link":  "https://www.ea.com/ea-app",
                            "winget":  "ElectronicArts.EADesktop",
                            "foss":  false
                        },
    "WPFInstalleartrumpet":  {
                                 "category":  "Multimídia",
                                 "choco":  "eartrumpet",
                                 "content":  "EarTrumpet (Audio)",
                                 "description":  "EarTrumpet is an audio control app for Windows, providing a simple and intuitive interface for managing sound settings.",
                                 "link":  "https://eartrumpet.app/",
                                 "winget":  "File-New-Project.EarTrumpet",
                                 "foss":  true
                             },
    "WPFInstalledge":  {
                           "category":  "Navegadores",
                           "choco":  "microsoft-edge",
                           "content":  "Edge",
                           "description":  "Microsoft Edge is a modern web browser built on Chromium, offering performance, security, and integration with Microsoft services.",
                           "link":  "https://www.microsoft.com/edge",
                           "winget":  "Microsoft.Edge",
                           "foss":  false
                       },
    "WPFInstalles-de":  {
                            "category":  "Jogos",
                            "choco":  "",
                            "content":  "EmulationStation Desktop Edition",
                            "_comment":  "This and emulationstation are two completely different things. ES-DE is your frontend for everything and has its own set of emulators. Emulationstation is a graphical frontend for RetroArch.",
                            "description":  "EmulationStation Desktop Edition is a frontend for browsing and launching games from your multi-platform game collection.",
                            "link":  "https://es-de.org/",
                            "winget":  "ES-DE.EmulationStation-DE",
                            "foss":  true
                        },
    "WPFInstallenteauth":  {
                               "category":  "Utilitários",
                               "choco":  "ente-auth",
                               "content":  "Ente Auth",
                               "description":  "Ente Auth is a free, cross-platform, end-to-end encrypted authenticator app.",
                               "link":  "https://ente.io/auth/",
                               "winget":  "ente-io.auth-desktop",
                               "foss":  true
                           },
    "WPFInstallepicgames":  {
                                "category":  "Jogos",
                                "choco":  "epicgameslauncher",
                                "content":  "Epic Games Launcher",
                                "description":  "Epic Games Launcher is the client for accessing and playing games from the Epic Games Store.",
                                "link":  "https://www.epicgames.com/store/en-US/",
                                "winget":  "EpicGames.EpicGamesLauncher",
                                "foss":  false
                            },
    "WPFInstallfiles":  {
                            "category":  "Utilitários",
                            "choco":  "files",
                            "content":  "Files",
                            "description":  "Alternative file explorer.",
                            "link":  "https://files.community",
                            "winget":  "FilesCommunity.Files",
                            "foss":  true
                        },
    "WPFInstallfirefox":  {
                              "category":  "Navegadores",
                              "choco":  "firefox",
                              "content":  "Firefox",
                              "description":  "Mozilla Firefox is an open-source web browser known for its customization options, privacy features, and extensions.",
                              "link":  "https://www.mozilla.org/en-US/firefox/new/",
                              "winget":  "Mozilla.Firefox",
                              "foss":  true
                          },
    "WPFInstallfirefoxesr":  {
                                 "category":  "Navegadores",
                                 "choco":  "FirefoxESR",
                                 "content":  "Firefox ESR",
                                 "description":  "Mozilla Firefox is an open-source web browser known for its customization options, privacy features, and extensions. Firefox ESR (Extended Support Release) receives major updates every 42 weeks with minor updates such as crash fixes, security fixes and policy updates as needed, but at least every four weeks.",
                                 "link":  "https://www.mozilla.org/en-US/firefox/enterprise/",
                                 "winget":  "Mozilla.Firefox.ESR",
                                 "foss":  true
                             },
    "WPFInstallfloorp":  {
                             "category":  "Navegadores",
                             "choco":  "floorp",
                             "content":  "Floorp",
                             "description":  "Floorp is an open-source web browser project that aims to provide a simple and fast browsing experience.",
                             "link":  "https://floorp.app/",
                             "winget":  "Ablaze.Floorp",
                             "foss":  true
                         },
    "WPFInstallflux":  {
                           "category":  "Utilitários",
                           "choco":  "flux",
                           "content":  "F.lux",
                           "description":  "f.lux adjusts the color temperature of your screen to reduce eye strain during nighttime use.",
                           "link":  "https://justgetflux.com/",
                           "winget":  "flux.flux",
                           "foss":  false
                       },
    "WPFInstallfoobar":  {
                             "category":  "Multimídia",
                             "choco":  "foobar2000",
                             "content":  "foobar2000 (Music Player)",
                             "description":  "foobar2000 is a highly customizable and extensible music player for Windows, known for its modular design and advanced features.",
                             "link":  "https://www.foobar2000.org/",
                             "winget":  "PeterPawlowski.foobar2000",
                             "foss":  false
                         },
    "WPFInstallfoxpdfreader":  {
                                   "category":  "Documentos",
                                   "choco":  "foxitreader",
                                   "content":  "Foxit PDF Reader",
                                   "description":  "Foxit PDF Reader is a free PDF viewer with a familiar ribbon-style interface.",
                                   "link":  "https://www.foxit.com/pdf-reader/",
                                   "winget":  "Foxit.FoxitReader",
                                   "foss":  false
                               },
    "WPFInstallgeforcenow":  {
                                 "category":  "Jogos",
                                 "choco":  "nvidia-geforce-now",
                                 "content":  "GeForce NOW",
                                 "description":  "GeForce NOW is a cloud gaming service that allows you to play high-quality PC games on your device.",
                                 "link":  "https://www.nvidia.com/en-us/geforce-now/",
                                 "winget":  "Nvidia.GeForceNow",
                                 "foss":  false
                             },
    "WPFInstallgimp":  {
                           "category":  "Multimídia",
                           "choco":  "gimp",
                           "content":  "GIMP (Image Editor)",
                           "description":  "GIMP is a versatile open-source raster graphics editor used for tasks such as photo retouching, image editing, and image composition.",
                           "link":  "https://www.gimp.org/",
                           "winget":  "GIMP.GIMP.3",
                           "foss":  true
                       },
    "WPFInstallgog":  {
                          "category":  "Jogos",
                          "choco":  "goggalaxy",
                          "content":  "GOG Galaxy",
                          "description":  "GOG Galaxy is a gaming client that offers DRM-free games, additional content, and more.",
                          "link":  "https://www.gog.com/galaxy",
                          "winget":  "GOG.Galaxy",
                          "foss":  false
                      },
    "WPFInstallgoogledrive":  {
                                  "category":  "Utilitários",
                                  "choco":  "googledrive",
                                  "content":  "Google Drive",
                                  "description":  "File syncing across devices all tied to your Google account.",
                                  "link":  "https://www.google.com/drive/",
                                  "winget":  "Google.GoogleDrive",
                                  "foss":  false
                              },
    "WPFInstallgpuz":  {
                           "category":  "Ferramentas Pro",
                           "choco":  "gpu-z",
                           "content":  "GPU-Z",
                           "description":  "GPU-Z provides detailed information about your graphics card and GPU.",
                           "link":  "https://www.techpowerup.com/gpuz/",
                           "winget":  "TechPowerUp.GPU-Z",
                           "foss":  false
                       },
    "WPFInstallhelium":  {
                             "category":  "Navegadores",
                             "choco":  "helium",
                             "content":  "Helium",
                             "description":  "Private, fast, and honest web browser.",
                             "link":  "https://helium.computer",
                             "winget":  "ImputNet.Helium",
                             "foss":  true
                         },
    "WPFInstallhandbrake":  {
                                "category":  "Multimídia",
                                "choco":  "handbrake",
                                "content":  "HandBrake",
                                "description":  "HandBrake is an open-source video transcoder, allowing you to convert video from nearly any format to a selection of widely supported codecs.",
                                "link":  "https://handbrake.fr/",
                                "winget":  "HandBrake.HandBrake",
                                "foss":  true
                            },
    "WPFInstallheroiclauncher":  {
                                     "category":  "Jogos",
                                     "choco":  "heroic-games-launcher",
                                     "content":  "Heroic Games Launcher",
                                     "description":  "Heroic Games Launcher is an open-source alternative game launcher for Epic Games Store.",
                                     "link":  "https://heroicgameslauncher.com/",
                                     "winget":  "HeroicGamesLauncher.HeroicGamesLauncher",
                                     "foss":  true
                                 },
    "WPFInstallhwinfo":  {
                             "category":  "Ferramentas Pro",
                             "choco":  "hwinfo",
                             "content":  "HWiNFO",
                             "description":  "HWiNFO provides comprehensive hardware information and diagnostics for Windows.",
                             "link":  "https://www.hwinfo.com/",
                             "winget":  "REALiX.HWiNFO",
                             "foss":  false
                         },
    "WPFInstallhwmonitor":  {
                                "category":  "Ferramentas Pro",
                                "choco":  "hwmonitor",
                                "content":  "HWMonitor",
                                "description":  "HWMonitor is a hardware monitoring program that reads PC systems main health sensors.",
                                "link":  "https://www.cpuid.com/softwares/hwmonitor.html",
                                "winget":  "CPUID.HWMonitor",
                                "foss":  false
                            },
    "WPFInstallimageglass":  {
                                 "category":  "Multimídia",
                                 "choco":  "imageglass",
                                 "content":  "ImageGlass (Image Viewer)",
                                 "description":  "ImageGlass is a versatile image viewer with support for various image formats and a focus on simplicity and speed.",
                                 "link":  "https://imageglass.org/",
                                 "winget":  "DuongDieuPhap.ImageGlass",
                                 "foss":  true
                             },
    "WPFInstallinternetdownloadmanager":  {
                                              "category":  "Utilitários",
                                              "choco":  "internet-download-manager",
                                              "content":  "Internet Download Manager",
                                              "description":  "Internet Download Manager is a download manager for accelerating, resuming, and scheduling file downloads.",
                                              "link":  "https://www.internetdownloadmanager.com/",
                                              "winget":  "Tonec.InternetDownloadManager",
                                              "foss":  false
                                          },
    "WPFInstallirfanview":  {
                                "category":  "Multimídia",
                                "choco":  "irfanview",
                                "content":  "IrfanView",
                                "description":  "IrfanView is a lightweight, fast, and free image viewer and editor. Supports multiple formats, batch processing, and powerful plugins.",
                                "link":  "https://irfanview.com/",
                                "winget":  "IrfanSkiljan.IrfanView",
                                "foss":  false
                            },
    "WPFInstallitch":  {
                           "category":  "Jogos",
                           "choco":  "itch",
                           "content":  "Itch.io",
                           "description":  "Itch.io is a digital distribution platform for indie games and creative projects.",
                           "link":  "https://itch.io/",
                           "winget":  "ItchIo.Itch",
                           "foss":  true
                       },
    "WPFInstallitunes":  {
                             "category":  "Multimídia",
                             "choco":  "itunes",
                             "content":  "iTunes",
                             "description":  "iTunes is a media player, media library, and online radio broadcaster application developed by Apple Inc.",
                             "link":  "https://www.apple.com/itunes/",
                             "winget":  "Apple.iTunes",
                             "foss":  false
                         },
    "WPFInstalljpegview":  {
                               "category":  "Utilitários",
                               "choco":  "jpegview",
                               "content":  "JPEG View",
                               "description":  "JPEGView is a lean, fast and highly configurable viewer/editor for JPEG, BMP, PNG, WEBP, TGA, GIF, JXL, HEIC, HEIF, AVIF, and TIFF images with a minimal GUI.",
                               "link":  "https://github.com/sylikc/jpegview",
                               "winget":  "sylikc.JPEGView",
                               "foss":  true
                           },
    "WPFInstalljoplin":  {
                             "category":  "Documentos",
                             "choco":  "joplin",
                             "content":  "Joplin",
                             "description":  "Joplin is an open-source note-taking and to-do application with synchronization capabilities.",
                             "link":  "https://joplinapp.org/",
                             "winget":  "Joplin.Joplin",
                             "foss":  true
                         },
    "WPFInstallkeepassxc":  {
                                "category":  "Utilitários",
                                "choco":  "keepassxc",
                                "content":  "KeePassXC",
                                "description":  "KeePassXC is a modern, secure, and open-source password manager that stores and manages your most sensitive information. You can run KeePassXC on Windows, macOS, and Linux systems. KeePassXC is for people with extremely high demands of secure personal data management. It saves many different types of information, such as usernames, passwords, URLs, attachments, and notes in an offline, encrypted file that can be stored in any location, including private and public cloud solutions. For easy identification and management, user-defined titles and icons can be specified for entries. In addition, entries are sorted into customizable groups. An integrated search function allows you to use advanced patterns to easily find any entry in your database. A customizable, fast, and easy-to-use password generator utility allows you to create passwords with any combination of characters or easy to remember passphrases.",
                                "link":  "https://keepassxc.org/",
                                "winget":  "KeePassXCTeam.KeePassXC",
                                "foss":  true
                            },
    "WPFInstallklite":  {
                            "category":  "Multimídia",
                            "choco":  "k-litecodecpack-standard",
                            "content":  "K-Lite Codec Standard",
                            "description":  "K-Lite Codec Pack Standard is a collection of audio and video codecs and related tools, providing essential components for media playback.",
                            "link":  "https://www.codecguide.com/",
                            "winget":  "CodecGuide.K-LiteCodecPack.Standard",
                            "foss":  false
                        },
    "WPFInstalllibreoffice":  {
                                  "category":  "Documentos",
                                  "choco":  "libreoffice-fresh",
                                  "content":  "LibreOffice",
                                  "description":  "LibreOffice is a powerful and free office suite, compatible with other major office suites.",
                                  "link":  "https://www.libreoffice.org/",
                                  "winget":  "TheDocumentFoundation.LibreOffice",
                                  "foss":  true
                              },
    "WPFInstalllibrewolf":  {
                                "category":  "Navegadores",
                                "choco":  "librewolf",
                                "content":  "LibreWolf",
                                "description":  "LibreWolf is a privacy-focused web browser based on Firefox, with additional privacy and security enhancements.",
                                "link":  "https://librewolf.net/",
                                "winget":  "LibreWolf.LibreWolf",
                                "foss":  true
                            },
    "WPFInstalllocalsend":  {
                                "category":  "Utilitários",
                                "choco":  "localsend.install",
                                "content":  "LocalSend",
                                "description":  "An open-source cross-platform alternative to AirDrop.",
                                "link":  "https://localsend.org/",
                                "winget":  "LocalSend.LocalSend",
                                "foss":  true
                            },
    "WPFInstallmpc-qt":  {
                             "category":  "Multimídia",
                             "choco":  "mediainfo",
                             "content":  "mpc-qt",
                             "description":  "Media Player Classic Qute Theater",
                             "link":  "https://mpc-qt.github.io",
                             "winget":  "mpc-qt.mpc-qt",
                             "foss":  true
                         },
    "WPFInstallmpv":  {
                          "category":  "Multimídia",
                          "content":  "mpv",
                          "description":  "mpv is a free, open source, and cross-platform media player supporting a wide variety of media formats, codecs, and subtitle types.",
                          "link":  "https://mpv.io/",
                          "winget":  "shinchiro.mpv",
                          "foss":  true
                      },
    "WPFInstallmatrix":  {
                             "category":  "Comunicação",
                             "choco":  "element-desktop",
                             "content":  "Element",
                             "description":  "Element is a client for Matrix; an open network for secure, decentralized communication.",
                             "link":  "https://element.io/",
                             "winget":  "Element.Element",
                             "foss":  true
                         },
    "WPFInstallminitoolpartitionwizard":  {
                                              "category":  "Utilitários",
                                              "choco":  "minitoolpartitionwizard",
                                              "content":  "MiniTool Partition Wizard",
                                              "description":  "Comprehensive free partition manager that performs advanced operations Windows natively cannot, such as merging partitions, converting file systems, and organizing disk capacity.",
                                              "link":  "https://www.partitionwizard.com/",
                                              "winget":  "MiniTool.PartitionWizard.Free",
                                              "foss":  false
                                          },
    "WPFInstallmodrinth":  {
                               "category":  "Jogos",
                               "choco":  "modrinth-app",
                               "content":  "Modrinth App",
                               "description":  "Modrinth App is a desktop application for managing Minecraft mods and modpacks.",
                               "link":  "https://modrinth.com/app",
                               "winget":  "Modrinth.ModrinthApp",
                               "foss":  true
                           },
    "WPFInstallmoonlight":  {
                                "category":  "Jogos",
                                "choco":  "moonlight-qt",
                                "content":  "Moonlight/GameStream Client",
                                "description":  "Moonlight/GameStream Client allows you to stream PC games to other devices over your local network.",
                                "link":  "https://moonlight-stream.org/",
                                "winget":  "MoonlightGameStreamingProject.Moonlight",
                                "foss":  true
                            },
    "WPFInstallmpchc":  {
                            "category":  "Multimídia",
                            "choco":  "mpc-hc-clsid2",
                            "content":  "Media Player Classic - Home Cinema",
                            "description":  "Media Player Classic - Home Cinema (MPC-HC) is a free and open-source video and audio player for Windows. MPC-HC is based on the original Guliverkli project and contains many additional features and bug fixes.",
                            "link":  "https://mpc-hc.org/",
                            "winget":  "clsid2.mpc-hc",
                            "foss":  true
                        },
    "WPFInstallmsedgeredirect":  {
                                     "category":  "Utilitários",
                                     "choco":  "msedgeredirect",
                                     "content":  "MSEdgeRedirect",
                                     "description":  "A Tool to Redirect News, Search, Widgets, Weather, and More to your default browser.",
                                     "link":  "https://github.com/rcmaehl/MSEdgeRedirect",
                                     "winget":  "rcmaehl.MSEdgeRedirect",
                                     "foss":  true
                                 },
    "WPFInstallmsiafterburner":  {
                                     "category":  "Utilitários",
                                     "choco":  "msiafterburner",
                                     "content":  "MSI Afterburner",
                                     "description":  "MSI Afterburner is a graphics card overclocking utility with advanced features.",
                                     "link":  "https://www.msi.com/Landing/afterburner",
                                     "winget":  "Guru3D.Afterburner",
                                     "foss":  false
                                 },
    "WPFInstallmullvadvpn":  {
                                 "category":  "Ferramentas Pro",
                                 "choco":  "mullvad-app",
                                 "content":  "Mullvad VPN",
                                 "description":  "This is the VPN client software for the Mullvad VPN service.",
                                 "link":  "https://mullvad.net/",
                                 "winget":  "MullvadVPN.MullvadVPN",
                                 "foss":  true
                             },
    "WPFInstallmullvadbrowser":  {
                                     "category":  "Navegadores",
                                     "choco":  "na",
                                     "content":  "Mullvad Browser",
                                     "description":  "Mullvad Browser is a privacy-focused web browser, developed in partnership with the Tor Project.",
                                     "link":  "https://mullvad.net/browser",
                                     "winget":  "MullvadVPN.MullvadBrowser",
                                     "foss":  true
                                 },
    "WPFInstallnomacs":  {
                             "category":  "Multimídia",
                             "choco":  "nomacs",
                             "content":  "nomacs",
                             "description":  "nomacs is a free, open-source image viewer, which supports multiple platforms. You can use it for viewing all common image formats, including RAW and .psd images.",
                             "link":  "https://nomacs.org/",
                             "winget":  "nomacs.nomacs",
                             "foss":  true
                         },
    "WPFInstallnanazip":  {
                              "category":  "Utilitários",
                              "choco":  "nanazip",
                              "content":  "NanaZip",
                              "description":  "NanaZip is a fast and efficient file compression and decompression tool.",
                              "link":  "https://nanazip.org",
                              "winget":  "M2Team.NanaZip",
                              "foss":  true
                          },
    "WPFInstalltailscale":  {
                                "category":  "Utilitários",
                                "choco":  "tailscale",
                                "content":  "Tailscale",
                                "description":  "The Tailscale client allows you to connect all your devices using WireGuard®, without the hassle. Tailscale makes it as easy as installing an app and signing in.",
                                "link":  "https://tailscale.com/",
                                "winget":  "Tailscale.Tailscale",
                                "foss":  false
                            },
    "WPFInstallnaps2":  {
                            "category":  "Documentos",
                            "choco":  "naps2",
                            "content":  "NAPS2 (Scanner)",
                            "description":  "NAPS2 is a document scanning application that simplifies the process of creating electronic documents.",
                            "link":  "https://www.naps2.com/",
                            "winget":  "Cyanfish.NAPS2",
                            "foss":  true
                        },
    "WPFInstallnotepadplus":  {
                                  "category":  "Multimídia",
                                  "choco":  "notepadplusplus",
                                  "content":  "Notepad++",
                                  "description":  "Notepad++ is a free, open-source code editor and Notepad replacement with support for multiple languages.",
                                  "link":  "https://notepad-plus-plus.org/",
                                  "winget":  "Notepad++.Notepad++",
                                  "foss":  true
                              },
    "WPFInstallnvclean":  {
                              "category":  "Utilitários",
                              "choco":  "na",
                              "content":  "NVCleanstall",
                              "description":  "NVCleanstall is a tool designed to customize NVIDIA driver installations, allowing advanced users to control more aspects of the installation process.",
                              "link":  "https://www.techpowerup.com/nvcleanstall/",
                              "winget":  "TechPowerUp.NVCleanstall",
                              "foss":  false
                          },
    "WPFInstallobs":  {
                          "category":  "Multimídia",
                          "choco":  "obs-studio",
                          "content":  "OBS Studio",
                          "description":  "OBS Studio is a free and open-source software for video recording and live streaming. It supports real-time video/audio capturing and mixing, making it popular among content creators.",
                          "link":  "https://obsproject.com/",
                          "winget":  "OBSProject.OBSStudio",
                          "foss":  true
                      },
    "WPFInstallobsidian":  {
                               "category":  "Documentos",
                               "choco":  "obsidian",
                               "content":  "Obsidian",
                               "description":  "Obsidian is a powerful note-taking and knowledge management application.",
                               "link":  "https://obsidian.md/",
                               "winget":  "Obsidian.Obsidian",
                               "foss":  false
                           },
    "WPFInstallokular":  {
                             "category":  "Documentos",
                             "choco":  "okular",
                             "content":  "Okular",
                             "description":  "Okular is a versatile document viewer with advanced features.",
                             "link":  "https://okular.kde.org/",
                             "winget":  "KDE.Okular",
                             "foss":  true
                         },
    "WPFInstallonedrive":  {
                               "category":  "Ferramentas Microsoft",
                               "choco":  "onedrive",
                               "content":  "OneDrive",
                               "description":  "OneDrive is a cloud storage service provided by Microsoft, allowing users to store and share files securely across devices.",
                               "link":  "https://onedrive.live.com/",
                               "winget":  "Microsoft.OneDrive",
                               "foss":  false
                           },
    "WPFInstallonlyoffice":  {
                                 "category":  "Documentos",
                                 "choco":  "onlyoffice",
                                 "content":  "ONLYOFFICE Desktop",
                                 "description":  "ONLYOFFICE Desktop is a comprehensive office suite for document editing and collaboration.",
                                 "link":  "https://www.onlyoffice.com/desktop.aspx",
                                 "winget":  "ONLYOFFICE.DesktopEditors",
                                 "foss":  true
                             },
    "WPFInstallOPAutoClicker":  {
                                    "category":  "Utilitários",
                                    "choco":  "autoclicker",
                                    "content":  "OPAutoClicker",
                                    "description":  "A full-fledged autoclicker with two modes of autoclicking, at your dynamic cursor location or at a prespecified location.",
                                    "link":  "https://www.opautoclicker.com",
                                    "winget":  "OPAutoClicker.OPAutoClicker",
                                    "foss":  false
                                },
    "WPFInstallopenrgb":  {
                              "category":  "Utilitários",
                              "choco":  "openrgb",
                              "content":  "OpenRGB",
                              "description":  "OpenRGB is an open-source RGB lighting control software designed to manage and control RGB lighting for various components and peripherals.",
                              "link":  "https://openrgb.org/",
                              "winget":  "OpenRGB.OpenRGB",
                              "foss":  true
                          },
    "WPFInstallOpenVPN":  {
                              "category":  "Ferramentas Pro",
                              "choco":  "openvpn-connect",
                              "content":  "OpenVPN Connect",
                              "description":  "OpenVPN Connect is a VPN client that allows you to connect securely to a VPN server. It provides a secure and encrypted connection for protecting your online privacy.",
                              "link":  "https://openvpn.net/",
                              "winget":  "OpenVPNTechnologies.OpenVPNConnect",
                              "foss":  false
                          },
    "WPFInstallOVirtualBox":  {
                                  "category":  "Utilitários",
                                  "choco":  "virtualbox",
                                  "content":  "Oracle VirtualBox",
                                  "description":  "Oracle VirtualBox is a powerful and free open-source virtualization tool for x86 and AMD64/Intel64 architectures.",
                                  "link":  "https://www.virtualbox.org/",
                                  "winget":  "Oracle.VirtualBox",
                                  "foss":  true
                              },
    "WPFInstallpolicyplus":  {
                                 "category":  "Utilitários",
                                 "choco":  "na",
                                 "content":  "Policy Plus",
                                 "description":  "Local Group Policy Editor plus more, for all Windows editions.",
                                 "link":  "https://github.com/Fleex255/PolicyPlus",
                                 "winget":  "Fleex255.PolicyPlus",
                                 "foss":  true
                             },
    "WPFInstallprocessexplorer":  {
                                      "category":  "Ferramentas Microsoft",
                                      "choco":  "procexp",
                                      "content":  "Process Explorer",
                                      "description":  "Process Explorer is a task manager and system monitor.",
                                      "link":  "https://learn.microsoft.com/sysinternals/downloads/process-explorer",
                                      "winget":  "Microsoft.Sysinternals.ProcessExplorer",
                                      "foss":  false
                                  },
    "WPFInstallPaintdotnet":  {
                                  "category":  "Multimídia",
                                  "choco":  "paint.net",
                                  "content":  "Paint.NET",
                                  "description":  "Paint.NET is a free image and photo editing software for Windows. It features an intuitive user interface and supports a wide range of powerful editing tools.",
                                  "link":  "https://www.getpaint.net/",
                                  "winget":  "dotPDN.PaintDotNet",
                                  "foss":  false
                              },
    "WPFInstallparsec":  {
                             "category":  "Utilitários",
                             "choco":  "parsec",
                             "content":  "Parsec",
                             "description":  "Parsec is a low-latency, high-quality remote desktop sharing application for collaborating and gaming across devices.",
                             "link":  "https://parsec.app/",
                             "winget":  "Parsec.Parsec",
                             "foss":  false
                         },
    "WPFInstallpeazip":  {
                             "category":  "Utilitários",
                             "choco":  "peazip",
                             "content":  "PeaZip",
                             "description":  "PeaZip is a free, open-source file archiver utility that supports multiple archive formats and provides encryption features.",
                             "link":  "https://peazip.github.io/",
                             "winget":  "Giorgiotani.Peazip",
                             "foss":  true
                         },
    "WPFInstallpdf-xchange":  {
                                  "category":  "Documentos",
                                  "choco":  "pdfxchangeeditor",
                                  "content":  "PDF-XChange Editor",
                                  "description":  "A comprehensive Windows-based software suite and editor for creating, viewing, editing, annotating, and signing PDF files.",
                                  "link":  "https://www.pdf-xchange.com/",
                                  "winget":  "TrackerSoftware.PDF-XChangeEditor",
                                  "foss":  false
                              },
    "WPFInstallpdf24creator":  {
                                   "category":  "Documentos",
                                   "choco":  "pdf24",
                                   "content":  "PDF24 Creator",
                                   "description":  "Free and easy-to-use online/desktop PDF tools that make you more productive",
                                   "link":  "https://tools.pdf24.org/en/creator",
                                   "winget":  "geeksoftwareGmbH.PDF24Creator",
                                   "foss":  false
                               },
    "WPFInstallpdfgear":  {
                              "category":  "Documentos",
                              "choco":  "pdfgear",
                              "content":  "PDFgear",
                              "description":  "PDFgear is a piece of full-featured PDF management software for Windows, macOS, and mobile, and it\u0027s completely free to use.",
                              "link":  "https://www.pdfgear.com/",
                              "winget":  "PDFgear.PDFgear",
                              "foss":  false
                          },
    "WPFInstallpdfsam":  {
                             "category":  "Documentos",
                             "choco":  "pdfsam",
                             "content":  "PDFsam Basic",
                             "description":  "PDFsam Basic is a free and open-source tool for splitting, merging, and rotating PDF files.",
                             "link":  "https://pdfsam.org/",
                             "winget":  "PDFsam.PDFsam",
                             "foss":  true
                         },
    "WPFInstallplaynite":  {
                               "category":  "Jogos",
                               "choco":  "playnite",
                               "content":  "Playnite",
                               "description":  "Playnite is an open-source video game library manager with one simple goal: To provide a unified interface for all of your games.",
                               "link":  "https://playnite.link/",
                               "winget":  "Playnite.Playnite",
                               "foss":  true
                           },
    "WPFInstallpowershell":  {
                                 "category":  "Ferramentas Microsoft",
                                 "choco":  "powershell-core",
                                 "content":  "PowerShell",
                                 "description":  "PowerShell is a task automation framework and scripting language designed for system administrators, offering powerful command-line capabilities.",
                                 "link":  "https://github.com/PowerShell/PowerShell",
                                 "winget":  "Microsoft.PowerShell",
                                 "foss":  true
                             },
    "WPFInstallpowertoys":  {
                                "category":  "Ferramentas Microsoft",
                                "choco":  "powertoys",
                                "content":  "PowerToys",
                                "description":  "PowerToys is a set of utilities for power users to enhance productivity, featuring tools like FancyZones, PowerRename, and more.",
                                "link":  "https://github.com/microsoft/PowerToys",
                                "winget":  "Microsoft.PowerToys",
                                "foss":  true
                            },
    "WPFInstallprismlauncher":  {
                                    "category":  "Jogos",
                                    "choco":  "prismlauncher",
                                    "content":  "Prism Launcher",
                                    "description":  "Prism Launcher is an open-source Minecraft launcher with the ability to manage multiple instances, accounts, and mods.",
                                    "link":  "https://prismlauncher.org/",
                                    "winget":  "PrismLauncher.PrismLauncher",
                                    "foss":  true
                                },
    "WPFInstallprocesslasso":  {
                                   "category":  "Utilitários",
                                   "choco":  "plasso",
                                   "content":  "Process Lasso",
                                   "description":  "Process Lasso is a system optimization and automation tool that improves system responsiveness and stability by adjusting process priorities and CPU affinities.",
                                   "link":  "https://bitsum.com/",
                                   "winget":  "BitSum.ProcessLasso",
                                   "foss":  false
                               },
    "WPFInstallprotonauth":  {
                                 "category":  "Utilitários",
                                 "choco":  "protonauth",
                                 "content":  "Proton Authenticator",
                                 "description":  "2FA app from Proton to securely sync and backup 2FA codes.",
                                 "link":  "https://proton.me/authenticator",
                                 "winget":  "Proton.ProtonAuthenticator",
                                 "foss":  true
                             },
    "WPFInstallprotonmail":  {
                                 "category":  "Comunicação",
                                 "choco":  "protonmail",
                                 "content":  "Proton Mail",
                                 "description":  "Proton Mail is an end-to-end encrypted email service by Proton, protecting your privacy with zero-access encryption.",
                                 "link":  "https://proton.me/mail",
                                 "winget":  "Proton.ProtonMail",
                                 "foss":  true
                             },
    "WPFInstallprotondrive":  {
                                  "category":  "Utilitários",
                                  "choco":  "protondrive",
                                  "content":  "Proton Drive",
                                  "description":  "Proton Drive is an end-to-end encrypted Swiss vault for your files that protects your data.",
                                  "link":  "https://proton.me/drive",
                                  "winget":  "Proton.ProtonDrive",
                                  "foss":  true
                              },
    "WPFInstallprotonpass":  {
                                 "category":  "Utilitários",
                                 "choco":  "protonpass",
                                 "content":  "Proton Pass",
                                 "description":  "Proton Pass is a cloud-based password manager with end-to-end encryption and unique email aliases.",
                                 "link":  "https://proton.me/pass",
                                 "winget":  "Proton.ProtonPass",
                                 "foss":  true
                             },
    "WPFInstallprotonvpn":  {
                                "category":  "Ferramentas Pro",
                                "choco":  "protonvpn",
                                "content":  "Proton VPN",
                                "description":  "Proton VPN is a no-logs VPN service that protects your privacy online with features like Secure Core and Tor over VPN.",
                                "link":  "https://protonvpn.com/",
                                "winget":  "Proton.ProtonVPN",
                                "foss":  true
                            },
    "WPFInstallprocessmonitor":  {
                                     "category":  "Ferramentas Microsoft",
                                     "choco":  "procexp",
                                     "content":  "Process Monitor",
                                     "description":  "SysInternals Process Monitor is an advanced monitoring tool that shows real-time file system, registry, and process/thread activity.",
                                     "link":  "https://docs.microsoft.com/en-us/sysinternals/downloads/procmon",
                                     "winget":  "Microsoft.Sysinternals.ProcessMonitor",
                                     "foss":  false
                                 },
    "WPFInstallqbittorrent":  {
                                  "category":  "Utilitários",
                                  "choco":  "qbittorrent",
                                  "content":  "qBittorrent",
                                  "description":  "qBittorrent is a free and open-source BitTorrent client that aims to provide a feature-rich and lightweight alternative to other torrent clients.",
                                  "link":  "https://www.qbittorrent.org/",
                                  "winget":  "qBittorrent.qBittorrent",
                                  "foss":  true
                              },
    "WPFInstallqownnotes":  {
                                "category":  "Documentos",
                                "choco":  "qownnotes",
                                "content":  "QOwnNotes",
                                "description":  "QOwnNotes is a free open-source note taking app with Nextcloud/ownCloud integration.",
                                "link":  "https://www.qownnotes.org/",
                                "winget":  "pbek.QOwnNotes",
                                "foss":  true
                            },
    "WPFInstallqtox":  {
                           "category":  "Comunicação",
                           "choco":  "qtox",
                           "content":  "QTox",
                           "description":  "QTox is a free and open-source messaging app that prioritizes user privacy and security in its design.",
                           "link":  "https://qtox.github.io/",
                           "winget":  "Tox.qTox",
                           "foss":  true
                       },
    "WPFInstallrevo":  {
                           "category":  "Utilitários",
                           "choco":  "revo-uninstaller",
                           "content":  "Revo Uninstaller",
                           "description":  "Revo Uninstaller is an advanced uninstaller tool that helps you remove unwanted software and clean up your system.",
                           "link":  "https://www.revouninstaller.com/",
                           "winget":  "RevoUninstaller.RevoUninstaller",
                           "foss":  false
                       },
    "WPFInstallWiseProgramUninstaller":  {
                                             "category":  "Utilitários",
                                             "choco":  "na",
                                             "content":  "Wise Program Uninstaller (WiseCleaner)",
                                             "description":  "Wise Program Uninstaller is the perfect solution for uninstalling Windows programs, allowing you to uninstall applications quickly and completely using its simple and user-friendly interface.",
                                             "link":  "https://www.wisecleaner.com/wise-program-uninstaller.html",
                                             "winget":  "WiseCleaner.WiseProgramUninstaller",
                                             "foss":  false
                                         },
    "WPFInstallrufus":  {
                            "category":  "Utilitários",
                            "choco":  "rufus",
                            "content":  "Rufus Imager",
                            "description":  "Rufus is a utility that helps format and create bootable USB drives, such as USB keys or pen drives.",
                            "link":  "https://rufus.ie/",
                            "winget":  "Rufus.Rufus",
                            "foss":  true
                        },
    "WPFInstallsdio":  {
                           "category":  "Utilitários",
                           "choco":  "sdio",
                           "content":  "Snappy Driver Installer Origin",
                           "description":  "Snappy Driver Installer Origin is a free and open-source driver updater with a vast driver database for Windows.",
                           "link":  "https://www.glenn.delahoy.com/snappy-driver-installer-origin/",
                           "winget":  "GlennDelahoy.SnappyDriverInstallerOrigin",
                           "foss":  true
                       },
    "WPFInstallsharex":  {
                             "category":  "Multimídia",
                             "choco":  "sharex",
                             "content":  "ShareX (Screenshots)",
                             "description":  "ShareX is a free and open-source screen capture and file sharing tool. It supports various capture methods and offers advanced features for editing and sharing screenshots.",
                             "link":  "https://getsharex.com/",
                             "winget":  "ShareX.ShareX",
                             "foss":  true
                         },
    "WPFInstallnilesoftShell":  {
                                    "category":  "Utilitários",
                                    "choco":  "nilesoft-shell",
                                    "content":  "Nilesoft Shell",
                                    "description":  "Shell is an expanded context menu tool that adds extra functionality and customization options to the Windows context menu.",
                                    "link":  "https://nilesoft.org/",
                                    "winget":  "Nilesoft.Shell",
                                    "foss":  false
                                },
    "WPFInstallsysteminformer":  {
                                     "category":  "Ferramentas Pro",
                                     "choco":  "systeminformer",
                                     "content":  "System Informer",
                                     "description":  "A free, powerful, multi-purpose tool that helps you monitor system resources, debug software and detect malware.",
                                     "link":  "https://systeminformer.com/",
                                     "winget":  "WinsiderSS.SystemInformer",
                                     "foss":  true
                                 },
    "WPFInstallsignal":  {
                             "category":  "Comunicação",
                             "choco":  "signal",
                             "content":  "Signal",
                             "description":  "Signal is a privacy-focused messaging app that offers end-to-end encryption for secure and private communication.",
                             "link":  "https://signal.org/",
                             "winget":  "OpenWhisperSystems.Signal",
                             "foss":  true
                         },
    "WPFInstallsignalrgb":  {
                                "category":  "Utilitários",
                                "choco":  "na",
                                "content":  "SignalRGB",
                                "description":  "SignalRGB lets you control and sync your favorite RGB devices with one free application.",
                                "link":  "https://www.signalrgb.com/",
                                "winget":  "WhirlwindFX.SignalRgb",
                                "foss":  false
                            },
    "WPFInstallsimplenote":  {
                                 "category":  "Documentos",
                                 "choco":  "simplenote",
                                 "content":  "Simplenote",
                                 "description":  "Simplenote is an easy way to keep notes, lists, ideas and more.",
                                 "link":  "https://simplenote.com/",
                                 "winget":  "Automattic.Simplenote",
                                 "foss":  true
                             },
    "WPFInstallsimplewall":  {
                                 "category":  "Ferramentas Pro",
                                 "choco":  "simplewall",
                                 "content":  "Simplewall",
                                 "description":  "Simplewall is a free and open-source firewall application for Windows. It allows users to control and manage the inbound and outbound network traffic of applications.",
                                 "link":  "https://github.com/henrypp/simplewall",
                                 "winget":  "Henry++.simplewall",
                                 "foss":  true
                             },
    "WPFInstallslack":  {
                            "category":  "Comunicação",
                            "choco":  "slack",
                            "content":  "Slack",
                            "description":  "Slack is a collaboration hub that connects teams and facilitates communication through channels, messaging, and file sharing.",
                            "link":  "https://slack.com/",
                            "winget":  "SlackTechnologies.Slack",
                            "foss":  false
                        },
    "WPFInstallstartallback":  {
                                   "category":  "Utilitários",
                                   "choco":  "StartAllBack",
                                   "content":  "StartAllBack",
                                   "description":  "StartAllBack restores and improves Windows taskbar, Start menu, File Explorer, and shell UI behavior.",
                                   "link":  "https://www.startallback.com/",
                                   "winget":  "StartIsBack.StartAllBack",
                                   "foss":  false
                               },
    "WPFInstallsteam":  {
                            "category":  "Jogos",
                            "choco":  "steam-client",
                            "content":  "Steam",
                            "description":  "Steam is a digital distribution platform for purchasing and playing video games, offering multiplayer gaming, video streaming, and more.",
                            "link":  "https://store.steampowered.com/about/",
                            "winget":  "Valve.Steam",
                            "foss":  false
                        },
    "WPFInstallroblox":  {
                             "category":  "Jogos",
                             "choco":  "na",
                             "content":  "Roblox",
                             "description":  "Roblox is a platform and game creation system that allows users to create and play games developed by the community.",
                             "link":  "https://www.roblox.com/",
                             "winget":  "Roblox.Roblox",
                             "foss":  false
                         },
    "WPFInstallsumatra":  {
                              "category":  "Documentos",
                              "choco":  "sumatrapdf",
                              "content":  "Sumatra PDF",
                              "description":  "Sumatra PDF is a lightweight and fast PDF viewer with minimalistic design.",
                              "link":  "https://www.sumatrapdfreader.org/free-pdf-reader.html",
                              "winget":  "SumatraPDF.SumatraPDF",
                              "foss":  true
                          },
    "WPFInstallsunshine":  {
                               "category":  "Jogos",
                               "choco":  "sunshine",
                               "content":  "Sunshine/GameStream Server",
                               "description":  "Sunshine is a GameStream server that allows you to remotely play PC games on Android devices, offering low-latency streaming.",
                               "link":  "https://app.lizardbyte.dev/Sunshine/",
                               "winget":  "LizardByte.Sunshine",
                               "foss":  true
                           },
    "WPFInstalltcpview":  {
                              "category":  "Ferramentas Microsoft",
                              "choco":  "tcpview",
                              "content":  "TCPView",
                              "description":  "SysInternals TCPView is a network monitoring tool that displays a detailed list of all TCP and UDP endpoints on your system.",
                              "link":  "https://docs.microsoft.com/en-us/sysinternals/downloads/tcpview",
                              "winget":  "Microsoft.Sysinternals.TCPView",
                              "foss":  false
                          },
    "WPFInstallteams":  {
                            "category":  "Comunicação",
                            "choco":  "microsoft-teams",
                            "content":  "Teams",
                            "description":  "Microsoft Teams is a collaboration platform that integrates with Office 365 and offers chat, video conferencing, file sharing, and more.",
                            "link":  "https://www.microsoft.com/en-us/microsoft-teams/group-chat-software",
                            "winget":  "Microsoft.Teams",
                            "foss":  false
                        },
    "WPFInstallteamviewer":  {
                                 "category":  "Utilitários",
                                 "choco":  "teamviewer9",
                                 "content":  "TeamViewer",
                                 "description":  "TeamViewer is a popular remote access and support software that allows you to connect to and control remote devices.",
                                 "link":  "https://www.teamviewer.com/",
                                 "winget":  "TeamViewer.TeamViewer",
                                 "foss":  false
                             },
    "WPFInstallteamspeak3":  {
                                 "category":  "Comunicação",
                                 "choco":  "teamspeak",
                                 "content":  "TeamSpeak 3",
                                 "description":  "TEAMSPEAK. YOUR TEAM. YOUR RULES. Use crystal clear sound to communicate with your teammates cross-platform with military-grade security, lag-free performance \u0026 unparalleled reliability and uptime.",
                                 "link":  "https://www.teamspeak.com/",
                                 "winget":  "TeamSpeakSystems.TeamSpeakClient",
                                 "foss":  false
                             },
    "WPFInstallteamspeak6":  {
                                 "category":  "Comunicação",
                                 "choco":  "na",
                                 "content":  "TeamSpeak 6",
                                 "description":  "TEAMSPEAK. YOUR TEAM. YOUR RULES. Use crystal clear sound to communicate with your teammates cross-platform with military-grade security, lag-free performance \u0026 unparalleled reliability and uptime.",
                                 "link":  "https://www.teamspeak.com/",
                                 "winget":  "TeamSpeakSystems.TeamSpeakClient.Beta.6",
                                 "foss":  false
                             },
    "WPFInstalltelegram":  {
                               "category":  "Comunicação",
                               "choco":  "telegram",
                               "content":  "Telegram",
                               "description":  "Telegram is a cloud-based instant messaging app known for its security features, speed, and simplicity.",
                               "link":  "https://telegram.org/",
                               "winget":  "Telegram.TelegramDesktop",
                               "foss":  true
                           },
    "WPFInstallterminal":  {
                               "category":  "Ferramentas Microsoft",
                               "choco":  "microsoft-windows-terminal",
                               "content":  "Windows Terminal",
                               "description":  "Windows Terminal is a modern, fast, and efficient terminal application for command-line users, supporting multiple tabs, panes, and more.",
                               "link":  "https://aka.ms/terminal",
                               "winget":  "Microsoft.WindowsTerminal",
                               "foss":  true
                           },
    "WPFInstallthunderbird":  {
                                  "category":  "Comunicação",
                                  "choco":  "thunderbird",
                                  "content":  "Thunderbird",
                                  "description":  "Mozilla Thunderbird is a free and open-source email client, news client, and chat client with advanced features.",
                                  "link":  "https://www.thunderbird.net/",
                                  "winget":  "Mozilla.Thunderbird",
                                  "foss":  true
                              },
    "WPFInstallbetterbird":  {
                                 "category":  "Comunicação",
                                 "choco":  "betterbird",
                                 "content":  "Betterbird",
                                 "description":  "Betterbird is a fork of Mozilla Thunderbird with additional features and bugfixes.",
                                 "link":  "https://www.betterbird.eu/",
                                 "winget":  "Betterbird.Betterbird",
                                 "foss":  true
                             },
    "WPFInstalltor":  {
                          "category":  "Navegadores",
                          "choco":  "tor-browser",
                          "content":  "Tor Browser",
                          "description":  "Tor Browser is designed for anonymous web browsing, utilizing the Tor network to protect user privacy and security.",
                          "link":  "https://www.torproject.org/",
                          "winget":  "TorProject.TorBrowser",
                          "foss":  true
                      },
    "WPFInstalltotalcommander":  {
                                     "category":  "Utilitários",
                                     "choco":  "TotalCommander",
                                     "content":  "Total Commander",
                                     "description":  "Total Commander is a file manager for Windows that provides a powerful and intuitive interface for file management.",
                                     "link":  "https://www.ghisler.com/",
                                     "winget":  "Ghisler.TotalCommander",
                                     "foss":  false
                                 },
    "WPFInstalltreesize":  {
                               "category":  "Utilitários",
                               "choco":  "treesizefree",
                               "content":  "TreeSize Free",
                               "description":  "TreeSize Free is a disk space manager that helps you analyze and visualize the space usage on your drives.",
                               "link":  "https://www.jam-software.com/treesize_free/",
                               "winget":  "JAMSoftware.TreeSize.Free",
                               "foss":  false
                           },
    "WPFInstallttaskbar":  {
                               "category":  "Utilitários",
                               "choco":  "translucenttb",
                               "content":  "TranslucentTB",
                               "description":  "TranslucentTB is a tool that allows you to customize the transparency of the Windows Taskbar.",
                               "link":  "https://translucenttb.github.io",
                               "winget":  "CharlesMilette.TranslucentTB",
                               "foss":  true
                           },
    "WPFInstallubisoft":  {
                              "category":  "Jogos",
                              "choco":  "ubisoft-connect",
                              "content":  "Ubisoft Connect",
                              "description":  "Ubisoft Connect is Ubisoft\u0027s digital distribution and online gaming service, providing access to Ubisoft\u0027s games and services.",
                              "link":  "https://ubisoftconnect.com/",
                              "winget":  "Ubisoft.Connect",
                              "foss":  false
                          },
    "WPFInstallungoogled":  {
                                "category":  "Navegadores",
                                "choco":  "ungoogled-chromium",
                                "content":  "Ungoogled Chromium",
                                "description":  "Ungoogled Chromium is a version of Chromium without Google\u0027s integration for enhanced privacy and control.",
                                "link":  "https://github.com/Eloston/ungoogled-chromium",
                                "winget":  "eloston.ungoogled-chromium",
                                "foss":  true
                            },
    "WPFInstalleverything":  {
                                 "category":  "Utilitários",
                                 "choco":  "everything",
                                 "content":  "Everything",
                                 "description":  "Everything is a search engine that locates files and folders by filename instantly for Windows. Unlike Windows search Everything initially displays every file and folder on your computer (hence the name Everything). You type in a search filter to limit what files and folders are displayed.",
                                 "link":  "https://www.voidtools.com/",
                                 "winget":  "voidtools.Everything",
                                 "foss":  false
                             },
    "WPFInstallvc2015_32":  {
                                "category":  "Ferramentas Microsoft",
                                "choco":  "vcredist2015",
                                "content":  "Visual C++ 2015-2022 32-bit",
                                "description":  "Visual C++ 2015-2022 32-bit redistributable package installs runtime components of Visual C++ libraries required to run 32-bit applications.",
                                "link":  "https://support.microsoft.com/en-us/help/2977003/the-latest-supported-visual-c-downloads",
                                "winget":  "Microsoft.VCRedist.2015+.x86",
                                "foss":  false
                            },
    "WPFInstallvc2015_64":  {
                                "category":  "Ferramentas Microsoft",
                                "choco":  "vcredist2015",
                                "content":  "Visual C++ 2015-2022 64-bit",
                                "description":  "Visual C++ 2015-2022 64-bit redistributable package installs runtime components of Visual C++ libraries required to run 64-bit applications.",
                                "link":  "https://support.microsoft.com/en-us/help/2977003/the-latest-supported-visual-c-downloads",
                                "winget":  "Microsoft.VCRedist.2015+.x64",
                                "foss":  false
                            },
    "WPFInstallventoy":  {
                             "category":  "Ferramentas Pro",
                             "choco":  "ventoy",
                             "content":  "Ventoy",
                             "description":  "Ventoy is an open-source tool for creating bootable USB drives. It supports multiple ISO files on a single USB drive, making it a versatile solution for installing operating systems.",
                             "link":  "https://www.ventoy.net/",
                             "winget":  "Ventoy.Ventoy",
                             "foss":  true
                         },
    "WPFInstallvesktop":  {
                              "category":  "Comunicação",
                              "choco":  "na",
                              "content":  "Vesktop",
                              "description":  "A cross platform electron-based desktop app aiming to give you a snappier Discord experience with Vencord pre-installed.",
                              "link":  "https://vesktop.dev",
                              "winget":  "Vencord.Vesktop",
                              "foss":  true
                          },
    "WPFInstallviber":  {
                            "category":  "Comunicação",
                            "choco":  "viber",
                            "content":  "Viber",
                            "description":  "Viber is a free messaging and calling app with features like group chats, video calls, and more.",
                            "link":  "https://www.viber.com/",
                            "winget":  "Rakuten.Viber",
                            "foss":  false
                        },
    "WPFInstallvivaldi":  {
                              "category":  "Navegadores",
                              "choco":  "vivaldi",
                              "content":  "Vivaldi",
                              "description":  "Vivaldi is a highly customizable web browser with a focus on user personalization and productivity features.",
                              "link":  "https://vivaldi.com/",
                              "winget":  "Vivaldi.Vivaldi",
                              "foss":  false
                          },
    "WPFInstallvlc":  {
                          "category":  "Multimídia",
                          "choco":  "vlc",
                          "content":  "VLC (Video Player)",
                          "description":  "VLC Media Player is a free and open-source multimedia player that supports a wide range of audio and video formats. It is known for its versatility and cross-platform compatibility.",
                          "link":  "https://www.videolan.org/vlc/",
                          "winget":  "VideoLAN.VLC",
                          "foss":  true
                      },
    "WPFInstallvrdesktopstreamer":  {
                                        "category":  "Jogos",
                                        "choco":  "na",
                                        "content":  "Virtual Desktop Streamer",
                                        "description":  "Virtual Desktop Streamer is a tool that allows you to stream your desktop screen to VR devices.",
                                        "link":  "https://www.vrdesktop.net/",
                                        "winget":  "VirtualDesktop.Streamer",
                                        "foss":  false
                                    },
    "WPFInstallwaterfox":  {
                               "category":  "Navegadores",
                               "choco":  "waterfox",
                               "content":  "Waterfox",
                               "description":  "Waterfox is a fast, privacy-focused web browser based on Firefox, designed to preserve user choice and privacy.",
                               "link":  "https://www.waterfox.net/",
                               "winget":  "Waterfox.Waterfox",
                               "foss":  true
                           },
    "WPFInstallwhatsapp":  {
                               "category":  "Comunicação",
                               "choco":  "na",
                               "content":  "WhatsApp Desktop",
                               "description":  "WhatsApp Desktop is the official Windows desktop messaging app from Meta, distributed through the Microsoft Store.",
                               "link":  "https://www.whatsapp.com/download",
                               "winget":  "msstore:9NKSQGP7F2NH",
                               "foss":  false
                           },
    "WPFInstallwingetui":  {
                               "category":  "Utilitários",
                               "choco":  "wingetui",
                               "content":  "UniGetUI",
                               "description":  "UniGetUI is a GUI for WinGet, Chocolatey, and other Windows CLI package managers.",
                               "link":  "https://devolutions.net/unigetui/",
                               "winget":  "Devolutions.UniGetUI",
                               "foss":  true
                           },
    "WPFInstallwinrar":  {
                             "category":  "Utilitários",
                             "choco":  "winrar",
                             "content":  "WinRAR",
                             "description":  "WinRAR is a powerful archive manager that allows you to create, manage, and extract compressed files.",
                             "link":  "https://www.win-rar.com/",
                             "winget":  "RARLab.WinRAR",
                             "foss":  false
                         },
    "WPFInstallwireguard":  {
                                "category":  "Ferramentas Pro",
                                "choco":  "wireguard",
                                "content":  "WireGuard",
                                "description":  "WireGuard is a fast and modern VPN (Virtual Private Network) protocol. It aims to be simpler and more efficient than other VPN protocols, providing secure and reliable connections.",
                                "link":  "https://www.wireguard.com/",
                                "winget":  "WireGuard.WireGuard",
                                "foss":  true
                            },
    "WPFInstallwiztree":  {
                              "category":  "Utilitários",
                              "choco":  "wiztree",
                              "content":  "WizTree",
                              "description":  "WizTree is a fast disk space analyzer that helps you quickly find the files and folders consuming the most space on your hard drive.",
                              "link":  "https://wiztreefree.com/",
                              "winget":  "AntibodySoftware.WizTree",
                              "foss":  false
                          },
    "WPFInstallxeheditor":  {
                                "category":  "Utilitários",
                                "choco":  "HxD",
                                "content":  "HxD Hex Editor",
                                "description":  "HxD is a free hex editor that allows you to edit, view, search, and analyze binary files.",
                                "link":  "https://mh-nexus.de/en/hxd/",
                                "winget":  "MHNexus.HxD",
                                "foss":  false
                            },
    "WPFInstallxournal":  {
                              "category":  "Documentos",
                              "choco":  "xournalplusplus",
                              "content":  "Xournal++",
                              "description":  "Xournal++ is an open-source handwriting notetaking software with PDF annotation capabilities.",
                              "link":  "https://xournalpp.github.io/",
                              "winget":  "Xournal++.Xournal++",
                              "foss":  true
                          },
    "WPFInstallzoom":  {
                           "category":  "Comunicação",
                           "choco":  "zoom",
                           "content":  "Zoom",
                           "description":  "Zoom is a popular video conferencing and web conferencing service for online meetings, webinars, and collaborative projects.",
                           "link":  "https://zoom.us/",
                           "winget":  "Zoom.Zoom",
                           "foss":  false
                       },
    "WPFInstalltightvnc":  {
                               "category":  "Utilitários",
                               "choco":  "TightVNC",
                               "content":  "TightVNC",
                               "description":  "TightVNC is a free and open-source remote desktop software that lets you access and control a computer over the network. With its intuitive interface, you can interact with the remote screen as if you were sitting in front of it. You can open files, launch applications, and perform other actions on the remote desktop almost as if you were physically there.",
                               "link":  "https://www.tightvnc.com/",
                               "winget":  "GlavSoft.TightVNC",
                               "foss":  true
                           },
    "WPFInstallglazewm":  {
                              "category":  "Utilitários",
                              "choco":  "glazewm",
                              "content":  "GlazeWM",
                              "description":  "GlazeWM is a tiling window manager for Windows inspired by i3 and Polybar.",
                              "link":  "https://github.com/glzr-io/glazewm",
                              "winget":  "glzr-io.glazewm",
                              "foss":  true
                          },
    "WPFInstallOverwolf":  {
                               "category":  "Jogos",
                               "choco":  "overwolf",
                               "content":  "Overwolf",
                               "description":  "Popular platform for game overlays and companion apps (mod managers, trackers, etc.), widely used by gamers.",
                               "link":  "https://www.overwolf.com/app/overwolf-curseforge",
                               "winget":  "Overwolf.CurseForge",
                               "foss":  false
                           },
    "WPFInstallOFGB":  {
                           "category":  "Utilitários",
                           "choco":  "ofgb",
                           "content":  "OFGB (Oh Frick Go Back)",
                           "description":  "GUI Tool to remove ads from various places around Windows 11",
                           "link":  "https://github.com/xM4ddy/OFGB",
                           "winget":  "xM4ddy.OFGB",
                           "foss":  true
                       },
    "WPFInstallZenBrowser":  {
                                 "category":  "Navegadores",
                                 "choco":  "zen-browser",
                                 "content":  "Zen Browser",
                                 "description":  "The modern, privacy-focused, performance-driven browser built on Firefox.",
                                 "link":  "https://zen-browser.app/",
                                 "winget":  "Zen-Team.Zen-Browser",
                                 "foss":  true
                             },
    "WPFInstallzotero":  {
                             "category":  "Documentos",
                             "choco":  "zotero",
                             "content":  "Zotero",
                             "description":  "Zotero is a free, easy-to-use tool to help you collect, organize, cite, and share your research materials.",
                             "link":  "https://www.zotero.org/",
                             "winget":  "DigitalScholar.Zotero",
                             "foss":  true
                         },
    "WPFInstalldeskflow":  {
                               "category":  "Utilitários",
                               "choco":  "deskflow",
                               "content":  "Deskflow",
                               "description":  "Deskflow is a free and open-source software KVM that lets you share a single keyboard and mouse across multiple computers.",
                               "link":  "https://github.com/deskflow/deskflow",
                               "winget":  "Deskflow.Deskflow",
                               "foss":  true
                           },
    "WPFInstallCloudflareWARP":  {
                                     "category":  "Utilitários",
                                     "choco":  "warp",
                                     "winget":  "Cloudflare.Warp",
                                     "description":  "WARP is a freemium VPN service provided by Cloudflare. Includes usage of Cloudflare\u0027s DNS",
                                     "content":  "Cloudflare WARP",
                                     "link":  "https://one.one.one.one",
                                     "foss":  false
                                 }
}
'@ | ConvertFrom-Json
$sync.configs.appnavigation = @'
{
    "WPFInstall":  {
                       "Content":  "Instalar/Atualizar Programas",
                       "Category":  "____Ações",
                       "Type":  "Button",
                       "Order":  "1",
                       "Description":  "Instala ou atualiza os programas selecionados"
                   },
    "WPFUninstall":  {
                         "Content":  "Desinstalar Programas",
                         "Category":  "____Ações",
                         "Type":  "Button",
                         "Order":  "2",
                         "Description":  "Desinstala os programas selecionados"
                     },
    "WPFInstallUpgrade":  {
                              "Content":  "Atualizar Todos os Programas",
                              "Category":  "____Ações",
                              "Type":  "Button",
                              "Order":  "3",
                              "Description":  "Atualiza todos os programas para a versão mais recente"
                          },
    "WingetRadioButton":  {
                              "Content":  "WinGet",
                              "Category":  "__Gerenciador de Pacotes",
                              "Type":  "RadioButton",
                              "GroupName":  "PackageManagerGroup",
                              "Checked":  true,
                              "Order":  "1",
                              "Description":  "Usar o WinGet para gerenciar os pacotes"
                          },
    "ChocoRadioButton":  {
                             "Content":  "Chocolatey",
                             "Category":  "__Gerenciador de Pacotes",
                             "Type":  "RadioButton",
                             "GroupName":  "PackageManagerGroup",
                             "Checked":  false,
                             "Order":  "2",
                             "Description":  "Usar o Chocolatey para gerenciar os pacotes"
                         },
    "WPFCollapseAllCategories":  {
                                     "Content":  "Recolher Todas as Categorias",
                                     "Category":  "__Seleção",
                                     "Type":  "Button",
                                     "Order":  "1",
                                     "Description":  "Recolhe todas as categorias de programas"
                                 },
    "WPFExpandAllCategories":  {
                                   "Content":  "Expandir Todas as Categorias",
                                   "Category":  "__Seleção",
                                   "Type":  "Button",
                                   "Order":  "2",
                                   "Description":  "Expande todas as categorias de programas"
                               },
    "WPFClearInstallSelection":  {
                                     "Content":  "Limpar Seleção",
                                     "Category":  "__Seleção",
                                     "Type":  "Button",
                                     "Order":  "3",
                                     "Description":  "Limpa a seleção de programas"
                                 },
    "WPFGetInstalled":  {
                            "Content":  "Mostrar Programas Instalados",
                            "Category":  "__Seleção",
                            "Type":  "Button",
                            "Order":  "4",
                            "Description":  "Marca os programas que já estão instalados"
                        },
    "WPFselectedAppsButton":  {
                                  "Content":  "Programas selecionados: 0",
                                  "Category":  "__Seleção",
                                  "Type":  "Button",
                                  "Order":  "5",
                                  "Description":  "Mostra os programas selecionados"
                              },
    "WPFInstallFOSSInfo":  {
                               "Content":  "Software Livre e de Código Aberto",
                               "Category":  "__Seleção",
                               "Type":  "Note",
                               "Order":  "0",
                               "Description":  "Informação sobre o selo FOSS nas entradas de programas"
                           }
}
'@ | ConvertFrom-Json
$sync.configs.appx = @'
{
    "WPFAppxMicrosoft_WindowsFeedbackHub":  {
                                                "Category":  "Apps da Microsoft",
                                                "Content":  "Hub de Feedback",
                                                "Description":  "Permite enviar relatórios de bugs, sugestões de recursos e dados de diagnóstico diretamente para a Microsoft.",
                                                "Panel":  "0",
                                                "PackageId":  "Microsoft.WindowsFeedbackHub",
                                                "StoreId":  "9NBLGGH4R32N"
                                            },
    "WPFAppxMicrosoft_GetHelp":  {
                                     "Category":  "Apps da Microsoft",
                                     "Content":  "Obter Ajuda",
                                     "Description":  "Dá acesso a guias automáticos de solução de problemas, documentação de suporte e atendimento direto da Microsoft.",
                                     "Panel":  "0",
                                     "PackageId":  "Microsoft.GetHelp",
                                     "StoreId":  "9PKDZBMV1H3T"
                                 },
    "WPFAppxMicrosoft_OutlookForWindows":  {
                                               "Category":  "Apps da Microsoft",
                                               "Content":  "Outlook para Windows",
                                               "Description":  "Oferece gerenciamento moderno de e-mails, agenda e organização de contatos.",
                                               "Panel":  "0",
                                               "PackageId":  "Microsoft.OutlookForWindows",
                                               "StoreId":  "9NRX63209R7B"
                                           },
    "WPFAppxMSTeams":  {
                           "Category":  "Apps da Microsoft",
                           "Content":  "Microsoft Teams",
                           "Description":  "Reúne mensagens instantâneas, videoconferências, compartilhamento de arquivos e colaboração em equipe.",
                           "Panel":  "0",
                           "PackageId":  "MSTeams",
                           "StoreId":  "XP8BT8DW290MPQ"
                       },
    "WPFAppxClipchamp_Clipchamp":  {
                                       "Category":  "Utilitários e Produtividade",
                                       "Content":  "Clipchamp",
                                       "Description":  "Editor de vídeo fácil de usar, com modelos prontos, efeitos e edição em linha do tempo.",
                                       "Panel":  "0",
                                       "PackageId":  "Clipchamp.Clipchamp",
                                       "StoreId":  "9P1J8S7CCWWT"
                                   },
    "WPFAppxMicrosoft_MicrosoftOfficeHub":  {
                                                "Category":  "Apps da Microsoft",
                                                "Content":  "Microsoft 365",
                                                "Description":  "Central para abrir os apps do Microsoft 365 na nuvem e os documentos recentes.",
                                                "Panel":  "0",
                                                "PackageId":  "Microsoft.MicrosoftOfficeHub",
                                                "StoreId":  "9WZDNCRD29V9"
                                            },
    "WPFAppxMicrosoft_ZuneMusic":  {
                                       "Category":  "Utilitários e Produtividade",
                                       "Content":  "Media Player",
                                       "Description":  "Reproduz arquivos locais de áudio e vídeo, com gerenciamento de playlists e transmissão para outros dispositivos.",
                                       "Panel":  "0",
                                       "PackageId":  "Microsoft.ZuneMusic",
                                       "StoreId":  "9WZDNCRFJ3PT"
                                   },
    "WPFAppxMicrosoft_BingSearch":  {
                                        "Category":  "Bing e Serviços Web",
                                        "Content":  "Pesquisa Bing",
                                        "Description":  "Integra a pesquisa e os serviços web do Microsoft Bing diretamente ao sistema.",
                                        "Panel":  "1",
                                        "PackageId":  "Microsoft.BingSearch",
                                        "StoreId":  "9NZBF4GT040C"
                                    },
    "WPFAppxMicrosoftCorporationII_QuickAssist":  {
                                                      "Category":  "Utilitários e Produtividade",
                                                      "Content":  "Assistência Rápida",
                                                      "Description":  "Permite suporte técnico remoto e compartilhamento de tela com segurança pela internet.",
                                                      "Panel":  "0",
                                                      "PackageId":  "MicrosoftCorporationII.QuickAssist",
                                                      "StoreId":  "9P7BP5VNWKX5"
                                                  },
    "WPFAppxMicrosoft_WindowsDevHome":  {
                                            "Category":  "Ferramentas de Desenvolvedor",
                                            "Content":  "Dev Home",
                                            "Description":  "Painel para configurar ambientes de desenvolvimento, sincronizar repositórios e acompanhar widgets de hardware.",
                                            "Panel":  "1",
                                            "PackageId":  "Microsoft.Windows.DevHome",
                                            "StoreId":  "9N8MHTPHNGVV"
                                        },
    "WPFAppxMicrosoft_WindowsCrossDevice":  {
                                                "Category":  "Ecossistema Microsoft",
                                                "Content":  "Dispositivos Móveis",
                                                "Description":  "Gerencia a conexão em segundo plano com celulares pareados. Removê-lo pode desativar recursos entre dispositivos integrados às Configurações do Windows, como espelhamento da tela do celular, transferência de arquivos e ponto de acesso móvel.",
                                                "Panel":  "0",
                                                "PackageId":  "MicrosoftWindows.CrossDevice",
                                                "StoreId":  "9NTXGKQ8P7N0"
                                            },
    "WPFAppxMicrosoft_Todos":  {
                                   "Category":  "Utilitários e Produtividade",
                                   "Content":  "Microsoft To Do",
                                   "Description":  "Cria, acompanha e sincroniza tarefas pessoais, listas inteligentes e lembretes diários.",
                                   "Panel":  "0",
                                   "PackageId":  "Microsoft.Todos",
                                   "StoreId":  "9NBLGGH5R558"
                               },
    "WPFAppxMicrosoft_PowerAutomateDesktop":  {
                                                  "Category":  "Ferramentas de Desenvolvedor",
                                                  "Content":  "Power Automate",
                                                  "Description":  "Automatiza fluxos de trabalho e tarefas repetitivas da área de trabalho com scripts visuais de pouco código.",
                                                  "Panel":  "1",
                                                  "PackageId":  "Microsoft.PowerAutomateDesktop",
                                                  "StoreId":  "9NFTCH6J7FHV"
                                              },
    "WPFAppxMicrosoft_YourPhone":  {
                                       "Category":  "Ecossistema Microsoft",
                                       "Content":  "Vincular ao Celular",
                                       "Description":  "Sincroniza mensagens de texto, notificações, fotos e chamadas do celular com o computador.",
                                       "Panel":  "0",
                                       "PackageId":  "Microsoft.YourPhone",
                                       "StoreId":  "9NMPJ99VJBWV"
                                   },
    "WPFAppxMicrosoft_MicrosoftStickyNotes":  {
                                                  "Category":  "Utilitários e Produtividade",
                                                  "Content":  "Notas Autoadesivas",
                                                  "Description":  "Cria notas rápidas flutuantes na área de trabalho, sincronizadas automaticamente entre dispositivos.",
                                                  "Panel":  "0",
                                                  "PackageId":  "Microsoft.MicrosoftStickyNotes",
                                                  "StoreId":  "9NBLGGH4QGHW"
                                              },
    "WPFAppxMicrosoft_WindowsSoundRecorder":  {
                                                  "Category":  "Utilitários e Produtividade",
                                                  "Content":  "Gravador de Som",
                                                  "Description":  "Grava e corta áudio ao vivo, com controles simples de ajuste do microfone.",
                                                  "Panel":  "0",
                                                  "PackageId":  "Microsoft.WindowsSoundRecorder",
                                                  "StoreId":  "9WZDNCRFHWKN"
                                              },
    "WPFAppxMicrosoft_WindowsAlarms":  {
                                           "Category":  "Utilitários e Produtividade",
                                           "Content":  "Relógio",
                                           "Description":  "Traz relógios mundiais, alarmes, temporizadores, cronômetro e sessões de foco.",
                                           "Panel":  "0",
                                           "PackageId":  "Microsoft.WindowsAlarms",
                                           "StoreId":  "9WZDNCRFJ3PR"
                                       },
    "WPFAppxMicrosoft_Paint":  {
                                   "Category":  "Utilitários e Produtividade",
                                   "Content":  "Paint",
                                   "Description":  "Ferramentas integradas de desenho digital, edição básica de imagens e manipulação de pixels.",
                                   "Panel":  "0",
                                   "PackageId":  "Microsoft.Paint",
                                   "StoreId":  "9PCFS5B6T72H"
                               },
    "WPFAppxMicrosoft_WindowsNotepad":  {
                                            "Category":  "Utilitários e Produtividade",
                                            "Content":  "Bloco de Notas",
                                            "Description":  "Editor de texto leve, com suporte a várias abas, para arquivos de texto simples e trechos de código.",
                                            "Panel":  "0",
                                            "PackageId":  "Microsoft.WindowsNotepad",
                                            "StoreId":  "9MSMLRH6LZF3"
                                        },
    "WPFAppxMicrosoft_ScreenSketch":  {
                                          "Category":  "Utilitários e Produtividade",
                                          "Content":  "Ferramenta de Captura",
                                          "Description":  "Tira capturas ou grava a tela, com anotações, recorte de imagem e reconhecimento de texto (OCR) integrados.",
                                          "Panel":  "0",
                                          "PackageId":  "Microsoft.ScreenSketch",
                                          "StoreId":  "9MZ95KL8MR0L"
                                      },
    "WPFAppxMicrosoft_Copilot":  {
                                     "Category":  "Bing e Serviços Web",
                                     "Content":  "Copilot",
                                     "Description":  "Abre o assistente de IA da Microsoft para respostas contextuais, ajuda com escrita criativa e pesquisa inteligente na web.",
                                     "Panel":  "1",
                                     "PackageId":  "Microsoft.Copilot",
                                     "StoreId":  "9NHT9RB2F4HD"
                                 },
    "WPFAppxMicrosoft_WindowsCalculator":  {
                                               "Category":  "Utilitários e Produtividade",
                                               "Content":  "Calculadora",
                                               "Description":  "Faz contas básicas, operações científicas, cálculos de programação e conversões de unidades.",
                                               "Panel":  "0",
                                               "PackageId":  "Microsoft.WindowsCalculator",
                                               "StoreId":  "9WZDNCRFHVN5"
                                           },
    "WPFAppxMicrosoft_WindowsCamera":  {
                                           "Category":  "Utilitários e Produtividade",
                                           "Content":  "Câmera",
                                           "Description":  "Tira fotos e grava vídeos com webcams ou outros dispositivos de imagem conectados.",
                                           "Panel":  "0",
                                           "PackageId":  "Microsoft.WindowsCamera",
                                           "StoreId":  "9WZDNCRFJBBG"
                                       },
    "WPFAppxMicrosoft_WindowsPhotos":  {
                                           "Category":  "Utilitários e Produtividade",
                                           "Content":  "Fotos",
                                           "Description":  "Organiza, exibe e recorta imagens locais, com ajustes básicos de cor e criação de álbuns.",
                                           "Panel":  "0",
                                           "PackageId":  "Microsoft.Windows.Photos",
                                           "StoreId":  "9WZDNCRFJBH4"
                                       },
    "WPFAppxMicrosoft_BingNews":  {
                                      "Category":  "Bing e Serviços Web",
                                      "Content":  "Notícias",
                                      "Description":  "Reúne as principais manchetes, feeds personalizados de artigos e os acontecimentos do mundo.",
                                      "Panel":  "1",
                                      "PackageId":  "Microsoft.BingNews",
                                      "StoreId":  "9WZDNCRFHVFW"
                                  },
    "WPFAppxMicrosoft_BingWeather":  {
                                         "Category":  "Bing e Serviços Web",
                                         "Content":  "Clima",
                                         "Description":  "Mostra a previsão do tempo local em tempo real, mapas de radar e o histórico meteorológico.",
                                         "Panel":  "1",
                                         "PackageId":  "Microsoft.BingWeather",
                                         "StoreId":  "9WZDNCRFJ3Q2"
                                     },
    "WPFAppxMicrosoft_XboxSpeechToTextOverlay":  {
                                                     "Category":  "Xbox e Jogos",
                                                     "Content":  "Xbox Speech To Text Overlay",
                                                     "Description":  "Fornece legendas de acessibilidade ao vivo e conversão de voz em texto para chats de jogos.",
                                                     "Panel":  "1",
                                                     "PackageId":  "Microsoft.XboxSpeechToTextOverlay"
                                                 },
    "WPFAppxMicrosoft_StartExperiencesApp":  {
                                                 "Category":  "Bing e Serviços Web",
                                                 "Content":  "Start Experiences App",
                                                 "Description":  "Alimenta o painel de Widgets do Windows com um feed personalizado de notícias, clima, esportes e finanças.",
                                                 "Panel":  "1",
                                                 "PackageId":  "Microsoft.StartExperiencesApp",
                                                 "StoreId":  "9PC1H9VN18CM"
                                             },
    "WPFAppxMicrosoft_MicrosoftSolitaireCollection":  {
                                                          "Category":  "Xbox e Jogos",
                                                          "Content":  "Microsoft Solitaire Collection",
                                                          "Description":  "Reúne jogos de cartas como Klondike, Spider, FreeCell, Pyramid e TriPeaks, além de desafios diários.",
                                                          "Panel":  "1",
                                                          "PackageId":  "Microsoft.MicrosoftSolitaireCollection"
                                                      }
}
'@ | ConvertFrom-Json
$sync.configs.dns = @'
{
    "Google":  {
                   "Primary":  "8.8.8.8",
                   "Secondary":  "8.8.4.4",
                   "Primary6":  "2001:4860:4860::8888",
                   "Secondary6":  "2001:4860:4860::8844",
                   "DohTemplate":  "https://dns.google/dns-query"
               },
    "Cloudflare":  {
                       "Primary":  "1.1.1.1",
                       "Secondary":  "1.0.0.1",
                       "Primary6":  "2606:4700:4700::1111",
                       "Secondary6":  "2606:4700:4700::1001",
                       "DohTemplate":  "https://cloudflare-dns.com/dns-query"
                   },
    "Cloudflare_Malware":  {
                               "Primary":  "1.1.1.2",
                               "Secondary":  "1.0.0.2",
                               "Primary6":  "2606:4700:4700::1112",
                               "Secondary6":  "2606:4700:4700::1002",
                               "DohTemplate":  "https://security.cloudflare-dns.com/dns-query"
                           },
    "Cloudflare_Malware_Adult":  {
                                     "Primary":  "1.1.1.3",
                                     "Secondary":  "1.0.0.3",
                                     "Primary6":  "2606:4700:4700::1113",
                                     "Secondary6":  "2606:4700:4700::1003",
                                     "DohTemplate":  "https://family.cloudflare-dns.com/dns-query"
                                 },
    "Open_DNS":  {
                     "Primary":  "208.67.222.222",
                     "Secondary":  "208.67.220.220",
                     "Primary6":  "2620:119:35::35",
                     "Secondary6":  "2620:119:53::53",
                     "DohTemplate":  "https://doh.opendns.com/dns-query"
                 },
    "Quad9":  {
                  "Primary":  "9.9.9.9",
                  "Secondary":  "149.112.112.112",
                  "Primary6":  "2620:fe::fe",
                  "Secondary6":  "2620:fe::9",
                  "DohTemplate":  "https://dns.quad9.net/dns-query"
              },
    "AdGuard_Ads_Trackers":  {
                                 "Primary":  "94.140.14.14",
                                 "Secondary":  "94.140.15.15",
                                 "Primary6":  "2a10:50c0::ad1:ff",
                                 "Secondary6":  "2a10:50c0::ad2:ff",
                                 "DohTemplate":  "https://dns.adguard-dns.com/dns-query"
                             },
    "AdGuard_Ads_Trackers_Malware_Adult":  {
                                               "Primary":  "94.140.14.15",
                                               "Secondary":  "94.140.15.16",
                                               "Primary6":  "2a10:50c0::bad1:ff",
                                               "Secondary6":  "2a10:50c0::bad2:ff",
                                               "DohTemplate":  "https://family.adguard-dns.com/dns-query"
                                           },
    "Mullvad":  {
                    "Primary":  "194.242.2.2",
                    "Secondary":  "194.242.2.3",
                    "Primary6":  "2a07:e340::2",
                    "Secondary6":  "2a07:e340::3",
                    "DohOnly":  true,
                    "DohTemplate":  "https://dns.mullvad.net/dns-query",
                    "SecondaryDohTemplate":  "https://adblock.dns.mullvad.net/dns-query"
                },
    "Mullvad_Ads_Trackers":  {
                                 "Primary":  "194.242.2.3",
                                 "Secondary":  "194.242.2.2",
                                 "Primary6":  "2a07:e340::3",
                                 "Secondary6":  "2a07:e340::2",
                                 "DohOnly":  true,
                                 "DohTemplate":  "https://adblock.dns.mullvad.net/dns-query",
                                 "SecondaryDohTemplate":  "https://dns.mullvad.net/dns-query"
                             },
    "Mullvad_Ads_Trackers_Malware":  {
                                         "Primary":  "194.242.2.4",
                                         "Secondary":  "194.242.2.3",
                                         "Primary6":  "2a07:e340::4",
                                         "Secondary6":  "2a07:e340::3",
                                         "DohOnly":  true,
                                         "DohTemplate":  "https://base.dns.mullvad.net/dns-query",
                                         "SecondaryDohTemplate":  "https://adblock.dns.mullvad.net/dns-query"
                                     },
    "Mullvad_Ads_Trackers_Malware_Social":  {
                                                "Primary":  "194.242.2.5",
                                                "Secondary":  "194.242.2.4",
                                                "Primary6":  "2a07:e340::5",
                                                "Secondary6":  "2a07:e340::4",
                                                "DohOnly":  true,
                                                "DohTemplate":  "https://extended.dns.mullvad.net/dns-query",
                                                "SecondaryDohTemplate":  "https://base.dns.mullvad.net/dns-query"
                                            },
    "Mullvad_Ads_Trackers_Malware_Adult_Gambling":  {
                                                        "Primary":  "194.242.2.6",
                                                        "Secondary":  "194.242.2.5",
                                                        "Primary6":  "2a07:e340::6",
                                                        "Secondary6":  "2a07:e340::5",
                                                        "DohOnly":  true,
                                                        "DohTemplate":  "https://family.dns.mullvad.net/dns-query",
                                                        "SecondaryDohTemplate":  "https://extended.dns.mullvad.net/dns-query"
                                                    },
    "Mullvad_Ads_Trackers_Malware_Adult_Gambling_Social":  {
                                                               "Primary":  "194.242.2.9",
                                                               "Secondary":  "194.242.2.6",
                                                               "Primary6":  "2a07:e340::9",
                                                               "Secondary6":  "2a07:e340::6",
                                                               "DohOnly":  true,
                                                               "DohTemplate":  "https://all.dns.mullvad.net/dns-query",
                                                               "SecondaryDohTemplate":  "https://family.dns.mullvad.net/dns-query"
                                                           }
}
'@ | ConvertFrom-Json
$sync.configs.feature = @'
{
    "WPFFeaturesdotnet":  {
                              "Content":  ".NET Framework (versões 2, 3 e 4) - Ativar",
                              "Description":  "O .NET e o .NET Framework formam uma plataforma de desenvolvimento com ferramentas, linguagens de programação e bibliotecas para criar muitos tipos diferentes de aplicativos.",
                              "category":  "a__Recursos do Windows",
                              "panel":  "1",
                              "feature":  [
                                              "NetFx4-AdvSrvs",
                                              "NetFx3"
                                          ],
                              "InvokeScript":  [

                                               ],
                              "link":  "https://winutil.christitus.com/code-reference/features/features/dotnet"
                          },
    "WPFFeatureslegacymedia":  {
                                   "Content":  "Componentes de Mídia Legados (WMP, DirectPlay) - Ativar",
                                   "Description":  "Ativa componentes de versões anteriores do Windows usados por programas antigos.",
                                   "category":  "a__Recursos do Windows",
                                   "panel":  "1",
                                   "feature":  [
                                                   "WindowsMediaPlayer",
                                                   "MediaPlayback",
                                                   "DirectPlay",
                                                   "LegacyComponents"
                                               ],
                                   "InvokeScript":  [

                                                    ],
                                   "link":  "https://winutil.christitus.com/code-reference/features/features/legacymedia"
                               },
    "WPFFeatureRegBackup":  {
                                "Content":  "Backup do Registro (tarefa diária às 00h30) - Ativar",
                                "Description":  "Ativa o backup diário do registro, que a Microsoft desativou no Windows 10 1803.",
                                "category":  "a__Recursos do Windows",
                                "panel":  "1",
                                "feature":  [

                                            ],
                                "InvokeScript":  [
                                                     "\r\n      New-ItemProperty -Path \u0027HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Configuration Manager\u0027 -Name \u0027EnablePeriodicBackup\u0027 -Type DWord -Value 1 -Force\r\n      New-ItemProperty -Path \u0027HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Configuration Manager\u0027 -Name \u0027BackupCount\u0027 -Type DWord -Value 2 -Force\r\n      $action = New-ScheduledTaskAction -Execute \u0027schtasks\u0027 -Argument \u0027/run /i /tn \"\\Microsoft\\Windows\\Registry\\RegIdleBackup\"\u0027\r\n      $trigger = New-ScheduledTaskTrigger -Daily -At 00:30\r\n      Register-ScheduledTask -Action $action -Trigger $trigger -TaskName \u0027AutoRegBackup\u0027 -Description \u0027Create System Registry Backups\u0027 -User \u0027System\u0027\r\n      "
                                                 ],
                                "link":  "https://winutil.christitus.com/code-reference/features/features/regbackup"
                            },
    "WPFFeatureEnableLegacyRecovery":  {
                                           "Content":  "Recuperação Clássica no Boot (F8) - Ativar",
                                           "Description":  "Ativa a tela de Opções Avançadas de Inicialização, que permite iniciar o Windows em modos avançados de solução de problemas.",
                                           "category":  "a__Recursos do Windows",
                                           "panel":  "1",
                                           "feature":  [

                                                       ],
                                           "InvokeScript":  [
                                                                "bcdedit /set bootmenupolicy legacy"
                                                            ],
                                           "link":  "https://winutil.christitus.com/code-reference/features/features/enablelegacyrecovery"
                                       },
    "WPFFeatureDisableLegacyRecovery":  {
                                            "Content":  "Recuperação Clássica no Boot (F8) - Desativar",
                                            "Description":  "Desativa a tela de Opções Avançadas de Inicialização, que permite iniciar o Windows em modos avançados de solução de problemas.",
                                            "category":  "a__Recursos do Windows",
                                            "panel":  "1",
                                            "feature":  [

                                                        ],
                                            "InvokeScript":  [
                                                                 "bcdedit /set bootmenupolicy standard"
                                                             ],
                                            "link":  "https://winutil.christitus.com/code-reference/features/features/disablelegacyrecovery"
                                        },
    "WPFFeatureInstall":  {
                              "Content":  "Instalar Recursos Selecionados",
                              "category":  "a__Recursos do Windows",
                              "panel":  "1",
                              "Type":  "Button",
                              "ButtonWidth":  "300",
                              "function":  "Invoke-WPFFeatureInstall",
                              "link":  "https://winutil.christitus.com/code-reference/features/features/install"
                          },
    "WPFFixesUpdate":  {
                           "Content":  "Windows Update - Redefinir",
                           "category":  "b__Correções",
                           "panel":  "1",
                           "Type":  "Button",
                           "ButtonWidth":  "300",
                           "function":  "Invoke-WPFFixesUpdate",
                           "link":  "https://winutil.christitus.com/code-reference/features/fixes/update"
                       },
    "WPFUpdatesdefault":  {
                              "Content":  "Windows Update - Voltar ao Padrão",
                              "Description":  "Desfaz os perfis de atualização de versões antigas do Azor WinUtil: remove as políticas do Windows Update que ele criou, volta os serviços de atualização ao padrão e reativa as tarefas agendadas. Reinicie o PC depois.",
                              "category":  "b__Correções",
                              "panel":  "1",
                              "Type":  "Button",
                              "ButtonWidth":  "300",
                              "function":  "Invoke-WPFUpdatesdefault",
                              "link":  "https://learn.microsoft.com/windows/deployment/update/waas-wu-settings"
                          },
    "WPFFixesNetwork":  {
                            "Content":  "Rede - Redefinir",
                            "category":  "b__Correções",
                            "panel":  "1",
                            "Type":  "Button",
                            "ButtonWidth":  "300",
                            "function":  "Invoke-WPFFixesNetwork",
                            "link":  "https://winutil.christitus.com/code-reference/features/fixes/network"
                        },
    "WPFFixesWinget":  {
                           "Content":  "WinGet - Reinstalar",
                           "category":  "b__Correções",
                           "panel":  "1",
                           "Type":  "Button",
                           "ButtonWidth":  "300",
                           "function":  "Invoke-WPFFixesWinget",
                           "link":  "https://winutil.christitus.com/code-reference/features/fixes/winget"
                       },
    "WPFPanelComputer":  {
                             "Content":  "Gerenciamento do Computador",
                             "category":  "a__Painéis Clássicos do Windows",
                             "panel":  "2",
                             "Type":  "Button",
                             "ButtonWidth":  "300",
                             "InvokeScript":  [
                                                  "compmgmt.msc"
                                              ],
                             "link":  "https://winutil.christitus.com/code-reference/features/legacy-windows-panels/computer"
                         },
    "WPFPanelControl":  {
                            "Content":  "Painel de Controle",
                            "category":  "a__Painéis Clássicos do Windows",
                            "panel":  "2",
                            "Type":  "Button",
                            "ButtonWidth":  "300",
                            "InvokeScript":  [
                                                 "control"
                                             ],
                            "link":  "https://winutil.christitus.com/code-reference/features/legacy-windows-panels/control"
                        },
    "WPFPanelMouse":  {
                          "Content":  "Propriedades do Mouse",
                          "category":  "a__Painéis Clássicos do Windows",
                          "panel":  "2",
                          "Type":  "Button",
                          "ButtonWidth":  "300",
                          "InvokeScript":  [
                                               "main.cpl"
                                           ],
                          "link":  "https://winutil.christitus.com/code-reference/features/legacy-windows-panels/mouse"
                      },
    "WPFPanelNetwork":  {
                            "Content":  "Conexões de Rede",
                            "category":  "a__Painéis Clássicos do Windows",
                            "panel":  "2",
                            "Type":  "Button",
                            "ButtonWidth":  "300",
                            "InvokeScript":  [
                                                 "ncpa.cpl"
                                             ],
                            "link":  "https://winutil.christitus.com/code-reference/features/legacy-windows-panels/network"
                        },
    "WPFPanelPower":  {
                          "Content":  "Opções de Energia",
                          "category":  "a__Painéis Clássicos do Windows",
                          "panel":  "2",
                          "Type":  "Button",
                          "ButtonWidth":  "300",
                          "InvokeScript":  [
                                               "powercfg.cpl"
                                           ],
                          "link":  "https://winutil.christitus.com/code-reference/features/legacy-windows-panels/power"
                      },
    "WPFPanelPrograms":  {
                             "Content":  "Programas e Recursos",
                             "category":  "a__Painéis Clássicos do Windows",
                             "panel":  "2",
                             "Type":  "Button",
                             "ButtonWidth":  "300",
                             "InvokeScript":  [
                                                  "appwiz.cpl"
                                              ],
                             "link":  "https://winutil.christitus.com/code-reference/features/legacy-windows-panels/programs"
                         },
    "WPFPanelSound":  {
                          "Content":  "Som",
                          "category":  "a__Painéis Clássicos do Windows",
                          "panel":  "2",
                          "Type":  "Button",
                          "ButtonWidth":  "300",
                          "InvokeScript":  [
                                               "mmsys.cpl"
                                           ],
                          "link":  "https://winutil.christitus.com/code-reference/features/legacy-windows-panels/sound"
                      },
    "WPFPanelSystem":  {
                           "Content":  "Propriedades do Sistema",
                           "category":  "a__Painéis Clássicos do Windows",
                           "panel":  "2",
                           "Type":  "Button",
                           "ButtonWidth":  "300",
                           "InvokeScript":  [
                                                "sysdm.cpl"
                                            ],
                           "link":  "https://winutil.christitus.com/code-reference/features/legacy-windows-panels/system"
                       },
    "WPFPanelFirewall":  {
                             "Content":  "Firewall do Windows Defender",
                             "category":  "a__Painéis Clássicos do Windows",
                             "panel":  "2",
                             "Type":  "Button",
                             "ButtonWidth":  "300",
                             "InvokeScript":  [
                                                  "firewall.cpl"
                                              ],
                             "link":  "https://winutil.christitus.com/code-reference/features/legacy-windows-panels/firewall"
                         },
    "WPFPanelRestore":  {
                            "Content":  "Restauração do Sistema",
                            "category":  "a__Painéis Clássicos do Windows",
                            "panel":  "2",
                            "Type":  "Button",
                            "ButtonWidth":  "300",
                            "InvokeScript":  [
                                                 "rstrui.exe"
                                             ],
                            "link":  "https://winutil.christitus.com/code-reference/features/legacy-windows-panels/restore"
                        }
}
'@ | ConvertFrom-Json
$sync.configs.preset = @'
{
    "Standard":  [
                     "WPFTweaksActivity",
                     "WPFTweaksConsumerFeatures",
                     "WPFTweaksDisableExplorerAutoDiscovery",
                     "WPFTweaksWPBT",
                     "WPFTweaksLocation",
                     "WPFTweaksServices",
                     "WPFTweaksTelemetry",
                     "WPFTweaksDeliveryOptimization",
                     "WPFTweaksDiskCleanup",
                     "WPFTweaksEndTaskOnTaskbar",
                     "WPFTweaksRestorePoint"
                 ],
    "Gaming":  [
                   "WPFTweaksRestorePoint",
                   "WPFTweaksConsumerFeatures",
                   "WPFTweaksTelemetry",
                   "WPFTweaksServices",
                   "WPFTweaksEndTaskOnTaskbar",
                   "WPFTweaksDisableBGapps",
                   "WPFTweaksAzorGameDVR"
               ],
    "SuperAgressivo":  [
                           "WPFTweaksRestorePoint",
                           "WPFTweaksActivity",
                           "WPFTweaksConsumerFeatures",
                           "WPFTweaksDeliveryOptimization",
                           "WPFTweaksDisableExplorerAutoDiscovery",
                           "WPFTweaksDisableStoreSearch",
                           "WPFTweaksDiskCleanup",
                           "WPFTweaksEndTaskOnTaskbar",
                           "WPFTweaksHiber",
                           "WPFTweaksLocation",
                           "WPFTweaksPreventDeviceMetadataFromNetwork",
                           "WPFTweaksServices",
                           "WPFTweaksTelemetry",
                           "WPFTweaksWidget",
                           "WPFTweaksWPBT",
                           "WPFTweaksWindowsAI",
                           "WPFTweaksAzorNoCopilot",
                           "WPFTweaksDisableBGapps",
                           "WPFTweaksDisableNotifications",
                           "WPFTweaksDisplay",
                           "WPFTweaksEdgeDebloat",
                           "WPFTweaksRemoveHomeAndGallery",
                           "WPFTweaksReservedStorage",
                           "WPFTweaksRightClickMenu",
                           "WPFTweaksStorage",
                           "WPFTweaksAzorGameDVR",
                           "WPFTweaksAzorStartupDelay",
                           "WPFTweaksAzorTransparency",
                           "WPFAppxMicrosoft_Copilot",
                           "WPFAppxMicrosoft_BingSearch",
                           "WPFAppxMicrosoft_BingNews",
                           "WPFAppxMicrosoft_BingWeather",
                           "WPFAppxMicrosoft_StartExperiencesApp",
                           "WPFAppxMicrosoft_WindowsFeedbackHub",
                           "WPFAppxMicrosoft_GetHelp",
                           "WPFAppxMicrosoft_MicrosoftOfficeHub",
                           "WPFAppxMicrosoft_OutlookForWindows",
                           "WPFAppxMSTeams",
                           "WPFAppxClipchamp_Clipchamp",
                           "WPFAppxMicrosoft_ZuneMusic",
                           "WPFAppxMicrosoftCorporationII_QuickAssist",
                           "WPFAppxMicrosoft_WindowsDevHome",
                           "WPFAppxMicrosoft_PowerAutomateDesktop",
                           "WPFAppxMicrosoft_Todos",
                           "WPFAppxMicrosoft_MicrosoftStickyNotes",
                           "WPFAppxMicrosoft_MicrosoftSolitaireCollection",
                           "WPFAppxMicrosoft_WindowsAlarms",
                           "WPFAppxMicrosoft_WindowsSoundRecorder",
                           "WPFAppxMicrosoft_YourPhone"
                       ],
    "AppxDefault":  [
                        "WPFAppxMicrosoft_WindowsFeedbackHub",
                        "WPFAppxMicrosoft_GetHelp",
                        "WPFAppxMicrosoft_MicrosoftOfficeHub",
                        "WPFAppxMicrosoft_WindowsCalculator",
                        "WPFAppxClipchamp_Clipchamp",
                        "WPFAppxMicrosoft_WindowsAlarms",
                        "WPFAppxMicrosoftCorporationII_QuickAssist",
                        "WPFAppxMicrosoft_WindowsSoundRecorder",
                        "WPFAppxMicrosoft_MicrosoftStickyNotes",
                        "WPFAppxMicrosoft_Todos",
                        "WPFAppxMicrosoft_MicrosoftSolitaireCollection",
                        "WPFAppxMicrosoft_PowerAutomateDesktop",
                        "WPFAppxMicrosoft_WindowsDevHome",
                        "WPFAppxMicrosoft_BingWeather",
                        "WPFAppxMicrosoft_StartExperiencesApp",
                        "WPFAppxMicrosoft_BingNews",
                        "WPFAppxMicrosoft_Copilot",
                        "WPFAppxMicrosoft_BingSearch"
                    ]
}
'@ | ConvertFrom-Json
$sync.configs.retired = @'
{
    "WPFTweaksRevertStartMenu":  "Layout Antigo do Menu Iniciar - Ativar",
    "WPFTweaksBraveDebloat":  "Navegador Brave - Enxugar",
    "WPFTweaksDisableWarningForUnsignedRdp":  "Avisos de Arquivos RDP Não Assinados - Desativar",
    "WPFTweaksUTC":  "Data e Hora - Usar Horário UTC",
    "WPFTweaksRazerBlock":  "Instalação Automática de Software Razer - Desativar",
    "WPFTweaksBlockAdobeNet":  "Lista de Bloqueio de URLs da Adobe - Ativar",
    "WPFTweaksDeleteTempFiles":  "Arquivos Temporários - Remover",
    "WPFToggleBatteryPercentage":  "Porcentagem da Bateria na Bandeja",
    "WPFToggleVerboseLogon":  "Mensagens Detalhadas de Logon",
    "WPFToggleNewOutlook":  "Novo Microsoft Outlook",
    "WPFToggleLongPaths":  "Caminhos Longos",
    "WPFFeatureshyperv":  "Hyper-V - Ativar",
    "WPFFeaturewsl":  "Subsistema do Windows para Linux (WSL) - Ativar",
    "WPFFeaturenfs":  "Network File System (NFS) - Ativar",
    "WPFFeaturesSandbox":  "Área Restrita do Windows (Sandbox) - Ativar",
    "WPFInstalladvancedip":  "Advanced IP Scanner",
    "WPFInstallangryipscanner":  "Angry IP Scanner",
    "WPFInstallrdcman":  "RDCMan",
    "WPFInstallbruno":  "Bruno",
    "WPFInstallclaude-code":  "Claude Code",
    "WPFInstallcmake":  "CMake",
    "WPFInstallcodex":  "Codex",
    "WPFInstallcursor":  "Cursor",
    "WPFInstalldismtools":  "DISMTools",
    "WPFInstallntlite":  "NTLite",
    "WPFInstalldockerdesktop":  "Docker Desktop",
    "WPFInstallfnm":  "Fast Node Manager",
    "WPFInstallgit":  "Git",
    "WPFInstallgitextensions":  "Git Extensions",
    "WPFInstallgithubcli":  "GitHub CLI",
    "WPFInstallgithubdesktop":  "GitHub Desktop",
    "WPFInstallgolang":  "Go",
    "WPFInstallgsudo":  "gsudo",
    "WPFInstallhugo":  "Hugo",
    "WPFInstalljava8":  "Amazon Corretto 8 (LTS)",
    "WPFInstalljava21":  "Amazon Corretto 21 (LTS)",
    "WPFInstalljava25":  "Amazon Corretto 25 (LTS)",
    "WPFInstalljellyfinmediaplayer":  "Jellyfin Media Player",
    "WPFInstalljellyfinserver":  "Jellyfin Server",
    "WPFInstalljetbrains":  "Jetbrains Toolbox",
    "WPFInstallkodi":  "Kodi Media Center",
    "WPFInstalllazygit":  "Lazygit",
    "WPFInstallnetbird":  "NetBird",
    "WPFInstallneovim":  "Neovim",
    "WPFInstallnextclouddesktop":  "Nextcloud Desktop",
    "WPFInstallnmap":  "Nmap",
    "WPFInstallnodejs":  "NodeJS",
    "WPFInstallnodejslts":  "NodeJS LTS",
    "WPFInstallpnpm":  "pnpm",
    "WPFInstallnuget":  "NuGet",
    "WPFInstallplex":  "Plex Media Server",
    "WPFInstallplexdesktop":  "Plex Desktop",
    "WPFInstallposh":  "Oh My Posh (Prompt)",
    "WPFInstallpostman":  "Postman",
    "WPFInstallputty":  "PuTTY",
    "WPFInstallpython3":  "Python3",
    "WPFInstallrustlang":  "Rust",
    "WPFInstallstarship":  "Starship (Shell Prompt)",
    "WPFInstallsublimetext":  "Sublime Text",
    "WPFInstallunity":  "Unity Game Engine",
    "WPFInstallvagrant":  "Vagrant",
    "WPFInstallvisualstudio2022":  "Visual Studio 2022",
    "WPFInstallvisualstudio2026":  "Visual Studio 2026",
    "WPFInstallvscode":  "VS Code",
    "WPFInstallvscodium":  "VS Codium",
    "WPFInstallwinscp":  "WinSCP",
    "WPFInstallwireshark":  "Wireshark",
    "WPFInstallyarn":  "Yarn",
    "WPFInstalluv":  "uv",
    "WPFInstallZed":  "Zed",
    "WPFInstallRuby":  "Ruby",
    "WPFInstallLua":  "Lua"
}
'@ | ConvertFrom-Json
$sync.configs.themes = @'
{
    "shared":  {
                   "AppEntryWidth":  "220",
                   "AppEntryFontSize":  "13.2",
                   "AppEntryIconSize":  "28",
                   "AppEntryMargin":  "3",
                   "AppEntryBorderThickness":  "1",
                   "CustomDialogFontSize":  "12",
                   "CustomDialogFontSizeHeader":  "15",
                   "CustomDialogLogoSize":  "30",
                   "CustomDialogWidth":  "440",
                   "CustomDialogHeight":  "250",
                   "FontSize":  "12",
                   "FontFamily":  "Segoe UI",
                   "HeaderFontSize":  "16",
                   "HeaderFontFamily":  "Bahnschrift SemiBold, Segoe UI Semibold",
                   "CheckBoxBulletDecoratorSize":  "16",
                   "CheckBoxMargin":  "15,0,0,3",
                   "TabContentMargin":  "5",
                   "TabButtonFontSize":  "13",
                   "TabButtonWidth":  "96",
                   "TabButtonHeight":  "32",
                   "TabRowHeightInPixels":  "50",
                   "ToolTipWidth":  "340",
                   "IconFontSize":  "14",
                   "IconButtonSize":  "35",
                   "SettingsIconFontSize":  "17",
                   "CloseIconFontSize":  "11",
                   "ButtonFontSize":  "12",
                   "ButtonFontFamily":  "Segoe UI Semibold",
                   "ButtonWidth":  "200",
                   "ButtonHeight":  "30",
                   "ConfigTabButtonFontSize":  "14",
                   "ConfigUpdateButtonFontSize":  "14",
                   "SearchBarWidth":  "200",
                   "SearchBarHeight":  "32",
                   "SearchBarTextBoxFontSize":  "12",
                   "SearchBarClearButtonFontSize":  "14",
                   "ButtonBorderThickness":  "1",
                   "ButtonMargin":  "1",
                   "ButtonCornerRadius":  "7",
                   "CardCornerRadius":  "12",
                   "DashboardTitleFontSize":  "30",
                   "DashboardValueFontSize":  "26"
               },
    "Light":  {
                  "AppInstallUnselectedColor":  "#FFFFFF",
                  "AppInstallHighlightedColor":  "#FCE4F0",
                  "AppInstallSelectedColor":  "#F7C6DE",
                  "ComboBoxForegroundColor":  "#2A1522",
                  "ComboBoxBackgroundColor":  "#FFFFFF",
                  "LabelboxForegroundColor":  "#C2185B",
                  "MainForegroundColor":  "#2A1522",
                  "MutedForegroundColor":  "#7D6272",
                  "MainBackgroundColor":  "#FBF3F7",
                  "CardBackgroundColor":  "#FFFFFF",
                  "InputBackgroundColor":  "#FFFFFF",
                  "LabelBackgroundColor":  "Transparent",
                  "LinkForegroundColor":  "#B81E6E",
                  "LinkHoverForegroundColor":  "#2A1522",
                  "ScrollBarBackgroundColor":  "#E2BCD0",
                  "ScrollBarHoverColor":  "#E0348E",
                  "ScrollBarDraggingColor":  "#B81E6E",
                  "ProgressBarForegroundColor":  "#E0348E",
                  "ProgressBarBackgroundColor":  "Transparent",
                  "ButtonBackgroundColor":  "#FFFFFF",
                  "ButtonBackgroundPressedColor":  "#E0348E",
                  "ButtonBackgroundMouseoverColor":  "#FCE4F0",
                  "ButtonBackgroundSelectedColor":  "#F9D2E6",
                  "ButtonForegroundColor":  "#2A1522",
                  "ToggleButtonOnColor":  "#E0348E",
                  "ToggleButtonOffColor":  "#A08A96",
                  "ToolTipBackgroundColor":  "#FFFFFF",
                  "BorderColor":  "#EACAD9",
                  "BorderOpacity":  "0.25",
                  "AccentColor":  "#E0348E",
                  "AccentSecondaryColor":  "#8B3FD9",
                  "AccentForegroundColor":  "#FFFFFF",
                  "SuccessColor":  "#12935C",
                  "WarningColor":  "#D1244B",
                  "HeroStartColor":  "#FFD6E9",
                  "HeroEndColor":  "#FFFFFF"
              },
    "Dark":  {
                 "AppInstallUnselectedColor":  "#170F15",
                 "AppInstallHighlightedColor":  "#2A1624",
                 "AppInstallSelectedColor":  "#4A1840",
                 "ComboBoxForegroundColor":  "#F7E9F1",
                 "ComboBoxBackgroundColor":  "#1D1219",
                 "LabelboxForegroundColor":  "#FF7CC2",
                 "MainForegroundColor":  "#F7E9F1",
                 "MutedForegroundColor":  "#B394A8",
                 "MainBackgroundColor":  "#0B0709",
                 "CardBackgroundColor":  "#140D12",
                 "InputBackgroundColor":  "#100A0E",
                 "LabelBackgroundColor":  "Transparent",
                 "LinkForegroundColor":  "#FF8CC8",
                 "LinkHoverForegroundColor":  "#FFFFFF",
                 "ScrollBarBackgroundColor":  "#3A2233",
                 "ScrollBarHoverColor":  "#FF4DA6",
                 "ScrollBarDraggingColor":  "#D6337F",
                 "ProgressBarForegroundColor":  "#FF4DA6",
                 "ProgressBarBackgroundColor":  "Transparent",
                 "ButtonBackgroundColor":  "#1D1219",
                 "ButtonBackgroundPressedColor":  "#FF4DA6",
                 "ButtonBackgroundMouseoverColor":  "#33172B",
                 "ButtonBackgroundSelectedColor":  "#45193A",
                 "ButtonForegroundColor":  "#F7E9F1",
                 "ToggleButtonOnColor":  "#FF4DA6",
                 "ToggleButtonOffColor":  "#6E5566",
                 "ToolTipBackgroundColor":  "#1D1219",
                 "BorderColor":  "#33202D",
                 "BorderOpacity":  "0.35",
                 "AccentColor":  "#FF4DA6",
                 "AccentSecondaryColor":  "#A64DFF",
                 "AccentForegroundColor":  "#FFFFFF",
                 "SuccessColor":  "#3DDC97",
                 "WarningColor":  "#FF4D6D",
                 "HeroStartColor":  "#3A1030",
                 "HeroEndColor":  "#0F0A0E"
             }
}
'@ | ConvertFrom-Json
$sync.configs.tweaks = @'
{
    "WPFTweaksActivity":  {
                              "Content":  "Histórico de Atividades - Desativar",
                              "Description":  "Apaga documentos recentes, área de transferência e histórico de execução.",
                              "category":  "Ajustes Essenciais",
                              "panel":  "1",
                              "registry":  [
                                               {
                                                   "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\System",
                                                   "Name":  "EnableActivityFeed",
                                                   "Value":  "0",
                                                   "Type":  "DWord",
                                                   "OriginalValue":  "\u003cRemoveEntry\u003e"
                                               },
                                               {
                                                   "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\System",
                                                   "Name":  "PublishUserActivities",
                                                   "Value":  "0",
                                                   "Type":  "DWord",
                                                   "OriginalValue":  "\u003cRemoveEntry\u003e"
                                               },
                                               {
                                                   "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\System",
                                                   "Name":  "UploadUserActivities",
                                                   "Value":  "0",
                                                   "Type":  "DWord",
                                                   "OriginalValue":  "\u003cRemoveEntry\u003e"
                                               }
                                           ],
                              "link":  "https://winutil.christitus.com/code-reference/tweaks/essential-tweaks/activity"
                          },
    "WPFTweaksHiber":  {
                           "Content":  "Hibernação - Desativar",
                           "Description":  "A hibernação foi pensada para notebooks: ela salva o conteúdo da memória antes de desligar o PC. Em desktops, praticamente nunca deveria ser usada.",
                           "category":  "Ajustes Essenciais",
                           "panel":  "1",
                           "registry":  [
                                            {
                                                "Path":  "HKLM:\\System\\CurrentControlSet\\Control\\Session Manager\\Power",
                                                "Name":  "HibernateEnabled",
                                                "Value":  "0",
                                                "Type":  "DWord",
                                                "OriginalValue":  "1"
                                            },
                                            {
                                                "Path":  "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\FlyoutMenuSettings",
                                                "Name":  "ShowHibernateOption",
                                                "Value":  "0",
                                                "Type":  "DWord",
                                                "OriginalValue":  "1"
                                            }
                                        ],
                           "InvokeScript":  [
                                                "powercfg.exe /hibernate off"
                                            ],
                           "UndoScript":  [
                                              "powercfg.exe /hibernate on"
                                          ],
                           "link":  "https://winutil.christitus.com/code-reference/tweaks/essential-tweaks/hiber"
                       },
    "WPFTweaksWidget":  {
                            "Content":  "Widgets - Remover",
                            "Description":  "Remove os widgets incômodos do canto inferior esquerdo da barra de tarefas.",
                            "category":  "Ajustes Essenciais",
                            "panel":  "1",
                            "InvokeScript":  [
                                                 "\r\n      # Sometimes if you dont stop the Widgets process the removal may fail\r\n\r\n      Get-Process *Widget* | Stop-Process\r\n      Get-AppxPackage Microsoft.WidgetsPlatformRuntime -AllUsers | Remove-AppxPackage -AllUsers\r\n      Get-AppxPackage MicrosoftWindows.Client.WebExperience -AllUsers | Remove-AppxPackage -AllUsers\r\n\r\n      Invoke-WinUtilExplorerUpdate -action \"restart\"\r\n      Write-Host \"Removed widgets\"\r\n      "
                                             ],
                            "link":  "https://winutil.christitus.com/code-reference/tweaks/essential-tweaks/widget"
                        },
    "WPFTweaksDisableStoreSearch":  {
                                        "Content":  "Resultados Recomendados da Microsoft Store na Pesquisa - Desativar",
                                        "Description":  "Deixa de exibir apps recomendados da Microsoft Store ao pesquisar apps no Menu Iniciar.",
                                        "category":  "Ajustes Essenciais",
                                        "panel":  "1",
                                        "InvokeScript":  [
                                                             "icacls \"$Env:LocalAppData\\Packages\\Microsoft.WindowsStore_8wekyb3d8bbwe\\LocalState\\store.db\" /deny Everyone:F"
                                                         ],
                                        "UndoScript":  [
                                                           "icacls \"$Env:LocalAppData\\Packages\\Microsoft.WindowsStore_8wekyb3d8bbwe\\LocalState\\store.db\" /grant Everyone:F"
                                                       ],
                                        "link":  "https://winutil.christitus.com/code-reference/tweaks/essential-tweaks/disablestoresearch"
                                    },
    "WPFTweaksLocation":  {
                              "Content":  "Rastreamento de Localização - Desativar",
                              "Description":  "Desativa o rastreamento de localização.",
                              "category":  "Ajustes Essenciais",
                              "panel":  "1",
                              "service":  [
                                              {
                                                  "Name":  "lfsvc",
                                                  "StartupType":  "Disabled",
                                                  "OriginalType":  "Manual"
                                              }
                                          ],
                              "registry":  [
                                               {
                                                   "Path":  "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\location",
                                                   "Name":  "Value",
                                                   "Value":  "Deny",
                                                   "Type":  "String",
                                                   "OriginalValue":  "Allow"
                                               },
                                               {
                                                   "Path":  "HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Sensor\\Overrides\\{BFA794E4-F964-4FDB-90F6-51056BFE4B44}",
                                                   "Name":  "SensorPermissionState",
                                                   "Value":  "0",
                                                   "Type":  "DWord",
                                                   "OriginalValue":  "1"
                                               },
                                               {
                                                   "Path":  "HKLM:\\SYSTEM\\Maps",
                                                   "Name":  "AutoUpdateEnabled",
                                                   "Value":  "0",
                                                   "Type":  "DWord",
                                                   "OriginalValue":  "1"
                                               }
                                           ],
                              "link":  "https://winutil.christitus.com/code-reference/tweaks/essential-tweaks/location"
                          },
    "WPFTweaksServices":  {
                              "Content":  "Serviços - Definir como Manual",
                              "Description":  "Define alguns serviços com inicialização Manual e ajusta o valor SvcHostSplitThresholdInKB do registro de acordo com a memória do sistema, o que pode reduzir bastante o número de processos svchost.exe.",
                              "category":  "Ajustes Essenciais",
                              "panel":  "1",
                              "service":  [
                                              {
                                                  "Name":  "CscService",
                                                  "StartupType":  "Disabled",
                                                  "OriginalType":  "Manual"
                                              },
                                              {
                                                  "Name":  "DiagTrack",
                                                  "StartupType":  "Disabled",
                                                  "OriginalType":  "Automatic"
                                              },
                                              {
                                                  "Name":  "MapsBroker",
                                                  "StartupType":  "Manual",
                                                  "OriginalType":  "Automatic"
                                              },
                                              {
                                                  "Name":  "StorSvc",
                                                  "StartupType":  "Manual",
                                                  "OriginalType":  "Automatic"
                                              },
                                              {
                                                  "Name":  "SharedAccess",
                                                  "StartupType":  "Disabled",
                                                  "OriginalType":  "Automatic"
                                              }
                                          ],
                              "InvokeScript":  [
                                                   "\r\n      $Memory = (Get-CimInstance Win32_PhysicalMemory | Measure-Object Capacity -Sum).Sum / 1KB\r\n      Set-ItemProperty -Path \"HKLM:\\SYSTEM\\CurrentControlSet\\Control\" -Name SvcHostSplitThresholdInKB -Value $Memory\r\n      "
                                               ],
                              "link":  "https://winutil.christitus.com/code-reference/tweaks/essential-tweaks/services"
                          },
    "WPFTweaksEdgeDebloat":  {
                                 "Content":  "Microsoft Edge - Enxugar",
                                 "Description":  "Desativa várias opções de telemetria, pop-ups e outros incômodos do Edge.",
                                 "category":  "z__Ajustes Avançados - CUIDADO",
                                 "panel":  "1",
                                 "registry":  [
                                                  {
                                                      "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\EdgeUpdate",
                                                      "Name":  "CreateDesktopShortcutDefault",
                                                      "Value":  "0",
                                                      "Type":  "DWord",
                                                      "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                  },
                                                  {
                                                      "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Edge",
                                                      "Name":  "PersonalizationReportingEnabled",
                                                      "Value":  "0",
                                                      "Type":  "DWord",
                                                      "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                  },
                                                  {
                                                      "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Edge\\ExtensionInstallBlocklist",
                                                      "Name":  "1",
                                                      "Value":  "ofefcgjbeghpigppfmkologfjadafddi",
                                                      "Type":  "String",
                                                      "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                  },
                                                  {
                                                      "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Edge",
                                                      "Name":  "ShowRecommendationsEnabled",
                                                      "Value":  "0",
                                                      "Type":  "DWord",
                                                      "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                  },
                                                  {
                                                      "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Edge",
                                                      "Name":  "HideFirstRunExperience",
                                                      "Value":  "1",
                                                      "Type":  "DWord",
                                                      "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                  },
                                                  {
                                                      "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Edge",
                                                      "Name":  "UserFeedbackAllowed",
                                                      "Value":  "0",
                                                      "Type":  "DWord",
                                                      "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                  },
                                                  {
                                                      "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Edge",
                                                      "Name":  "ConfigureDoNotTrack",
                                                      "Value":  "1",
                                                      "Type":  "DWord",
                                                      "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                  },
                                                  {
                                                      "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Edge",
                                                      "Name":  "AlternateErrorPagesEnabled",
                                                      "Value":  "0",
                                                      "Type":  "DWord",
                                                      "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                  },
                                                  {
                                                      "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Edge",
                                                      "Name":  "EdgeCollectionsEnabled",
                                                      "Value":  "0",
                                                      "Type":  "DWord",
                                                      "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                  },
                                                  {
                                                      "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Edge",
                                                      "Name":  "EdgeShoppingAssistantEnabled",
                                                      "Value":  "0",
                                                      "Type":  "DWord",
                                                      "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                  },
                                                  {
                                                      "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Edge",
                                                      "Name":  "MicrosoftEdgeInsiderPromotionEnabled",
                                                      "Value":  "0",
                                                      "Type":  "DWord",
                                                      "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                  },
                                                  {
                                                      "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Edge",
                                                      "Name":  "ShowMicrosoftRewards",
                                                      "Value":  "0",
                                                      "Type":  "DWord",
                                                      "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                  },
                                                  {
                                                      "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Edge",
                                                      "Name":  "WebWidgetAllowed",
                                                      "Value":  "0",
                                                      "Type":  "DWord",
                                                      "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                  },
                                                  {
                                                      "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Edge",
                                                      "Name":  "DiagnosticData",
                                                      "Value":  "0",
                                                      "Type":  "DWord",
                                                      "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                  },
                                                  {
                                                      "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Edge",
                                                      "Name":  "EdgeAssetDeliveryServiceEnabled",
                                                      "Value":  "0",
                                                      "Type":  "DWord",
                                                      "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                  },
                                                  {
                                                      "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Edge",
                                                      "Name":  "WalletDonationEnabled",
                                                      "Value":  "0",
                                                      "Type":  "DWord",
                                                      "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                  },
                                                  {
                                                      "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Edge",
                                                      "Name":  "DefaultBrowserSettingsCampaignEnabled",
                                                      "Value":  "0",
                                                      "Type":  "DWord",
                                                      "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                  }
                                              ],
                                 "link":  "https://winutil.christitus.com/code-reference/tweaks/z--advanced-tweaks---caution/edgedebloat"
                             },
    "WPFTweaksConsumerFeatures":  {
                                      "Content":  "Recursos de Consumidor (ConsumerFeatures) - Desativar",
                                      "Description":  "Impede a instalação de apps promovidos e reduz as sugestões de apps da Microsoft Store.",
                                      "category":  "Ajustes Essenciais",
                                      "panel":  "1",
                                      "registry":  [
                                                       {
                                                           "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\CloudContent",
                                                           "Name":  "DisableWindowsConsumerFeatures",
                                                           "Value":  "1",
                                                           "Type":  "DWord",
                                                           "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                       }
                                                   ],
                                      "link":  "https://winutil.christitus.com/code-reference/tweaks/essential-tweaks/consumerfeatures"
                                  },
    "WPFTweaksTelemetry":  {
                               "Content":  "Telemetria - Desativar",
                               "Description":  "Desativa a telemetria da Microsoft.",
                               "category":  "Ajustes Essenciais",
                               "panel":  "1",
                               "registry":  [
                                                {
                                                    "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\AdvertisingInfo",
                                                    "Name":  "Enabled",
                                                    "Value":  "0",
                                                    "Type":  "DWord",
                                                    "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                },
                                                {
                                                    "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Privacy",
                                                    "Name":  "TailoredExperiencesWithDiagnosticDataEnabled",
                                                    "Value":  "0",
                                                    "Type":  "DWord",
                                                    "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                },
                                                {
                                                    "Path":  "HKCU:\\Software\\Microsoft\\Speech_OneCore\\Settings\\OnlineSpeechPrivacy",
                                                    "Name":  "HasAccepted",
                                                    "Value":  "0",
                                                    "Type":  "DWord",
                                                    "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                },
                                                {
                                                    "Path":  "HKCU:\\Software\\Microsoft\\Input\\TIPC",
                                                    "Name":  "Enabled",
                                                    "Value":  "0",
                                                    "Type":  "DWord",
                                                    "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                },
                                                {
                                                    "Path":  "HKCU:\\Software\\Microsoft\\InputPersonalization",
                                                    "Name":  "RestrictImplicitInkCollection",
                                                    "Value":  "1",
                                                    "Type":  "DWord",
                                                    "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                },
                                                {
                                                    "Path":  "HKCU:\\Software\\Microsoft\\InputPersonalization",
                                                    "Name":  "RestrictImplicitTextCollection",
                                                    "Value":  "1",
                                                    "Type":  "DWord",
                                                    "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                },
                                                {
                                                    "Path":  "HKCU:\\Software\\Microsoft\\InputPersonalization\\TrainedDataStore",
                                                    "Name":  "HarvestContacts",
                                                    "Value":  "0",
                                                    "Type":  "DWord",
                                                    "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                },
                                                {
                                                    "Path":  "HKCU:\\Software\\Microsoft\\Personalization\\Settings",
                                                    "Name":  "AcceptedPrivacyPolicy",
                                                    "Value":  "0",
                                                    "Type":  "DWord",
                                                    "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                },
                                                {
                                                    "Path":  "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\DataCollection",
                                                    "Name":  "AllowTelemetry",
                                                    "Value":  "0",
                                                    "Type":  "DWord",
                                                    "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                },
                                                {
                                                    "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced",
                                                    "Name":  "Start_TrackProgs",
                                                    "Value":  "0",
                                                    "Type":  "DWord",
                                                    "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                },
                                                {
                                                    "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\System",
                                                    "Name":  "PublishUserActivities",
                                                    "Value":  "0",
                                                    "Type":  "DWord",
                                                    "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                },
                                                {
                                                    "Path":  "HKCU:\\Software\\Microsoft\\Siuf\\Rules",
                                                    "Name":  "NumberOfSIUFInPeriod",
                                                    "Value":  "0",
                                                    "Type":  "DWord",
                                                    "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                }
                                            ],
                               "InvokeScript":  [
                                                    "\r\n      # Disable Defender Auto Sample Submission\r\n      Set-MpPreference -SubmitSamplesConsent 2\r\n\r\n      # Disable (Connected User Experiences and Telemetry) Service\r\n      Set-Service -Name diagtrack -StartupType Disabled\r\n\r\n      # Disable (Windows Error Reporting Manager) Service\r\n      Set-Service -Name wermgr -StartupType Disabled\r\n\r\n      # Disable PowerShell 7 telemetry\r\n      [Environment]::SetEnvironmentVariable(\u0027POWERSHELL_TELEMETRY_OPTOUT\u0027, \u00271\u0027, \u0027Machine\u0027)\r\n\r\n      Remove-ItemProperty -Path \"HKCU:\\Software\\Microsoft\\Siuf\\Rules\" -Name PeriodInNanoSeconds\r\n      "
                                                ],
                               "UndoScript":  [
                                                  "\r\n      # Enable Defender Auto Sample Submission\r\n      Set-MpPreference -SubmitSamplesConsent 1\r\n\r\n      # Enable (Connected User Experiences and Telemetry) Service\r\n      Set-Service -Name diagtrack -StartupType Automatic\r\n\r\n      # Enable (Windows Error Reporting Manager) Service\r\n      Set-Service -Name wermgr -StartupType Automatic\r\n\r\n      # Enable PowerShell 7 telemetry\r\n      [Environment]::SetEnvironmentVariable(\u0027POWERSHELL_TELEMETRY_OPTOUT\u0027, \u0027\u0027, \u0027Machine\u0027)\r\n      "
                                              ],
                               "link":  "https://winutil.christitus.com/code-reference/tweaks/essential-tweaks/telemetry"
                           },
    "WPFTweaksDeliveryOptimization":  {
                                          "Content":  "Otimização de Entrega - Desativar",
                                          "Description":  "Impede que o Windows use a sua banda para enviar atualizações a outros PCs na internet ou na rede local.",
                                          "category":  "Ajustes Essenciais",
                                          "panel":  "1",
                                          "registry":  [
                                                           {
                                                               "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\DeliveryOptimization",
                                                               "Name":  "DODownloadMode",
                                                               "Value":  "0",
                                                               "Type":  "DWord",
                                                               "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                           }
                                                       ],
                                          "link":  "https://winutil.christitus.com/code-reference/tweaks/essential-tweaks/deliveryoptimization"
                                      },
    "WPFTweaksRemoveEdge":  {
                                "Content":  "Microsoft Edge - Remover",
                                "Description":  "Desinstala o Microsoft Edge criando um arquivo MicrosoftEdge.exe falso na pasta legada do Edge. Isso faz o Windows liberar o desinstalador oficial do Edge, permitindo a remoção em nível de sistema.",
                                "category":  "z__Ajustes Avançados - CUIDADO",
                                "panel":  "1",
                                "InvokeScript":  [
                                                     "\r\n      $Path = Resolve-Path -Path \"$Env:ProgramFiles (x86)\\Microsoft\\Edge\\Application\\*\\Installer\\setup.exe\" | Select-Object -Last 1\r\n\r\n      if (Test-Path $Path) {\r\n          New-Item -Path \"$Env:SystemRoot\\SystemApps\\Microsoft.MicrosoftEdge_8wekyb3d8bbwe\\MicrosoftEdge.exe\" -Force\r\n          Start-Process -FilePath $Path -ArgumentList \"--uninstall --system-level --force-uninstall --delete-profile\" -Wait\r\n          Write-Host \"Microsoft Edge was removed\"\r\n      } else {\r\n          Write-Host \"Microsoft Edge is not installed\"\r\n      }\r\n      "
                                                 ],
                                "UndoScript":  [
                                                   "\r\n      Write-Host \"Installing Microsoft Edge...\"\r\n      winget install Microsoft.Edge --source winget\r\n      "
                                               ],
                                "link":  "https://winutil.christitus.com/code-reference/tweaks/z--advanced-tweaks---caution/removeedge"
                            },
    "WPFTweaksDisableBitLocker":  {
                                      "Content":  "BitLocker - Desativar",
                                      "Description":  "Desativa o BitLocker.",
                                      "category":  "Ajustes Essenciais",
                                      "panel":  "1",
                                      "InvokeScript":  [
                                                           "Disable-BitLocker -MountPoint $Env:SystemDrive"
                                                       ],
                                      "UndoScript":  [
                                                         "Enable-BitLocker -MountPoint $Env:SystemDrive"
                                                     ],
                                      "link":  "https://winutil.christitus.com/code-reference/tweaks/essential-tweaks/disablebitlocker"
                                  },
    "WPFTweaksRemoveOneDrive":  {
                                    "Content":  "Microsoft OneDrive - Remover",
                                    "Description":  "Bloqueia temporariamente a exclusão dos arquivos do usuário no OneDrive, usa o próprio desinstalador para removê-lo e depois restaura a permissão original.",
                                    "category":  "z__Ajustes Avançados - CUIDADO",
                                    "panel":  "1",
                                    "InvokeScript":  [
                                                         "\r\n      # Deny permission to remove OneDrive folder\r\n      icacls $Env:OneDrive /deny \"Administrators:(D,DC)\"\r\n\r\n      Write-Host \"Uninstalling OneDrive...\"\r\n      Start-Process -FilePath (Join-Path $Env:SystemRoot \"System32\\OneDriveSetup.exe\") -ArgumentList \u0027/uninstall\u0027 -Wait\r\n\r\n      # Some of OneDrive files use explorer, and OneDrive uses FileCoAuth\r\n      Write-Host \"Removing leftover OneDrive Files...\"\r\n\r\n      Stop-Process -Name FileCoAuth,Explorer\r\n\r\n      Remove-Item \"$Env:LocalAppData\\Microsoft\\OneDrive\" -Recurse -Force\r\n      Remove-Item \"$Env:ProgramData\\Microsoft OneDrive\" -Recurse -Force\r\n\r\n      # Grant back permission to access OneDrive folder\r\n      icacls $Env:OneDrive /grant \"Administrators:(D,DC)\"\r\n\r\n      if (-not (Get-ChildItem -Path $Env:OneDrive)) {\r\n          Remove-Item -Path $Env:OneDrive -Recurse\r\n          [Environment]::SetEnvironmentVariable(\u0027OneDrive\u0027, $null, \u0027User\u0027)\r\n      }\r\n\r\n      # Disable OneSyncSvc\r\n      Set-Service -Name OneSyncSvc -StartupType Disabled\r\n      "
                                                     ],
                                    "UndoScript":  [
                                                       "\r\n      Write-Host \"Installing OneDrive\"\r\n      winget install Microsoft.Onedrive --source winget\r\n\r\n      # Enabled OneSyncSvc\r\n      Set-Service -Name OneSyncSvc -StartupType Automatic\r\n      "
                                                   ],
                                    "link":  "https://winutil.christitus.com/code-reference/tweaks/z--advanced-tweaks---caution/removeonedrive"
                                },
    "WPFTweaksRemoveHomeAndGallery":  {
                                          "Content":  "Início e Galeria do Explorador de Arquivos - Desativar",
                                          "Description":  "Remove Início e Galeria do Explorador de Arquivos e define Este Computador como padrão.",
                                          "category":  "z__Ajustes Avançados - CUIDADO",
                                          "panel":  "1",
                                          "registry":  [
                                                           {
                                                               "Path":  "HKCU:\\Software\\Classes\\CLSID\\{f874310e-b6b7-47dc-bc84-b9e6b38f5903}",
                                                               "Name":  "System.IsPinnedToNameSpaceTree",
                                                               "Value":  "0",
                                                               "Type":  "DWord",
                                                               "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                           },
                                                           {
                                                               "Path":  "HKCU:\\Software\\Classes\\CLSID\\{e88865ea-0e1c-4e20-9aa6-edcd0212c87c}",
                                                               "Name":  "System.IsPinnedToNameSpaceTree",
                                                               "Value":  "0",
                                                               "Type":  "DWord",
                                                               "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                           },
                                                           {
                                                               "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced",
                                                               "Name":  "LaunchTo",
                                                               "Value":  "1",
                                                               "Type":  "DWord",
                                                               "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                           }
                                                       ],
                                          "link":  "https://winutil.christitus.com/code-reference/tweaks/z--advanced-tweaks---caution/removehomeandgallery"
                                      },
    "WPFTweaksDisplay":  {
                             "Content":  "Efeitos Visuais - Melhor Desempenho",
                             "Description":  "Ajusta as preferências visuais do sistema para desempenho. Também dá para fazer isso manualmente pelo sysdm.cpl.",
                             "category":  "z__Ajustes Avançados - CUIDADO",
                             "panel":  "1",
                             "registry":  [
                                              {
                                                  "Path":  "HKCU:\\Control Panel\\Desktop",
                                                  "Name":  "DragFullWindows",
                                                  "Value":  "0",
                                                  "Type":  "String",
                                                  "OriginalValue":  "1"
                                              },
                                              {
                                                  "Path":  "HKCU:\\Control Panel\\Desktop",
                                                  "Name":  "MenuShowDelay",
                                                  "Value":  "200",
                                                  "Type":  "String",
                                                  "OriginalValue":  "400"
                                              },
                                              {
                                                  "Path":  "HKCU:\\Control Panel\\Desktop\\WindowMetrics",
                                                  "Name":  "MinAnimate",
                                                  "Value":  "0",
                                                  "Type":  "String",
                                                  "OriginalValue":  "1"
                                              },
                                              {
                                                  "Path":  "HKCU:\\Control Panel\\Keyboard",
                                                  "Name":  "KeyboardDelay",
                                                  "Value":  "0",
                                                  "Type":  "DWord",
                                                  "OriginalValue":  "1"
                                              },
                                              {
                                                  "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced",
                                                  "Name":  "ListviewAlphaSelect",
                                                  "Value":  "0",
                                                  "Type":  "DWord",
                                                  "OriginalValue":  "1"
                                              },
                                              {
                                                  "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced",
                                                  "Name":  "ListviewShadow",
                                                  "Value":  "0",
                                                  "Type":  "DWord",
                                                  "OriginalValue":  "1"
                                              },
                                              {
                                                  "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced",
                                                  "Name":  "TaskbarAnimations",
                                                  "Value":  "0",
                                                  "Type":  "DWord",
                                                  "OriginalValue":  "1"
                                              },
                                              {
                                                  "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VisualEffects",
                                                  "Name":  "VisualFXSetting",
                                                  "Value":  "3",
                                                  "Type":  "DWord",
                                                  "OriginalValue":  "1"
                                              },
                                              {
                                                  "Path":  "HKCU:\\Software\\Microsoft\\Windows\\DWM",
                                                  "Name":  "EnableAeroPeek",
                                                  "Value":  "0",
                                                  "Type":  "DWord",
                                                  "OriginalValue":  "1"
                                              },
                                              {
                                                  "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced",
                                                  "Name":  "TaskbarMn",
                                                  "Value":  "0",
                                                  "Type":  "DWord",
                                                  "OriginalValue":  "1"
                                              },
                                              {
                                                  "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced",
                                                  "Name":  "ShowTaskViewButton",
                                                  "Value":  "0",
                                                  "Type":  "DWord",
                                                  "OriginalValue":  "1"
                                              },
                                              {
                                                  "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Search",
                                                  "Name":  "SearchboxTaskbarMode",
                                                  "Value":  "0",
                                                  "Type":  "DWord",
                                                  "OriginalValue":  "1"
                                              }
                                          ],
                             "InvokeScript":  [
                                                  "Set-ItemProperty -Path \"HKCU:\\Control Panel\\Desktop\" -Name \"UserPreferencesMask\" -Type Binary -Value ([byte[]](144,18,3,128,16,0,0,0))"
                                              ],
                             "UndoScript":  [
                                                "Remove-ItemProperty -Path \"HKCU:\\Control Panel\\Desktop\" -Name \"UserPreferencesMask\""
                                            ],
                             "link":  "https://winutil.christitus.com/code-reference/tweaks/z--advanced-tweaks---caution/display"
                         },
    "WPFTweaksReservedStorage":  {
                                     "Content":  "Armazenamento Reservado - Desativar",
                                     "Description":  "Desativa o Armazenamento Reservado do Windows (7 a 10 GB guardados para atualizações e arquivos temporários). Recomendado apenas em discos pequenos. Reative antes de grandes atualizações de recursos do Windows para evitar falhas na instalação.",
                                     "category":  "z__Ajustes Avançados - CUIDADO",
                                     "panel":  "1",
                                     "InvokeScript":  [
                                                          "DISM /Online /Set-ReservedStorageState /State:Disabled"
                                                      ],
                                     "UndoScript":  [
                                                        "DISM /Online /Set-ReservedStorageState /State:Enabled"
                                                    ],
                                     "link":  "https://winutil.christitus.com/code-reference/tweaks/z--advanced-tweaks---caution/reservedstorage"
                                 },
    "WPFTweaksRestorePoint":  {
                                  "Content":  "Ponto de Restauração - Criar",
                                  "Description":  "Cria um ponto de restauração na hora, caso seja preciso reverter as modificações feitas pelo Azor WinUtil.",
                                  "category":  "Ajustes Essenciais",
                                  "panel":  "1",
                                  "Checked":  "False",
                                  "registry":  [
                                                   {
                                                       "Path":  "HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\SystemRestore",
                                                       "Name":  "SystemRestorePointCreationFrequency",
                                                       "Value":  "0",
                                                       "Type":  "DWord",
                                                       "OriginalValue":  "1440"
                                                   }
                                               ],
                                  "InvokeScript":  [
                                                       "\r\n      if (-not (Get-ComputerRestorePoint)) {\r\n          Enable-ComputerRestore -Drive $Env:SystemDrive\r\n      }\r\n\r\n      Checkpoint-Computer -Description \"System Restore Point created by WinUtil\" -RestorePointType MODIFY_SETTINGS\r\n      Write-Host \"System Restore Point Created Successfully\" -ForegroundColor Green\r\n      "
                                                   ],
                                  "link":  "https://winutil.christitus.com/code-reference/tweaks/essential-tweaks/restorepoint"
                              },
    "WPFTweaksEndTaskOnTaskbar":  {
                                      "Content":  "Finalizar Tarefa com Clique Direito - Ativar",
                                      "Description":  "Ativa a opção de finalizar a tarefa ao clicar com o botão direito em um programa na barra de tarefas.",
                                      "category":  "Ajustes Essenciais",
                                      "panel":  "1",
                                      "registry":  [
                                                       {
                                                           "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced\\TaskbarDeveloperSettings",
                                                           "Name":  "TaskbarEndTask",
                                                           "Value":  "1",
                                                           "Type":  "DWord",
                                                           "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                       }
                                                   ],
                                      "link":  "https://winutil.christitus.com/code-reference/tweaks/essential-tweaks/endtaskontaskbar"
                                  },
    "WPFTweaksStorage":  {
                             "Content":  "Sensor de Armazenamento - Desativar",
                             "Description":  "O Sensor de Armazenamento apaga arquivos temporários automaticamente.",
                             "category":  "z__Ajustes Avançados - CUIDADO",
                             "panel":  "1",
                             "registry":  [
                                              {
                                                  "Path":  "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\StorageSense\\Parameters\\StoragePolicy",
                                                  "Name":  "01",
                                                  "Value":  "0",
                                                  "Type":  "DWord",
                                                  "OriginalValue":  "1"
                                              }
                                          ],
                             "link":  "https://winutil.christitus.com/code-reference/tweaks/z--advanced-tweaks---caution/storage"
                         },
    "WPFTweaksWindowsAI":  {
                               "Content":  "IA do Windows - Desativar e Remover",
                               "Description":  "Remove e desativa todos os recursos e pacotes de IA, como o Copilot e o Recall.",
                               "category":  "z__Ajustes Avançados - CUIDADO",
                               "panel":  "1",
                               "registry":  [
                                                {
                                                    "Path":  "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer",
                                                    "Name":  "SettingsPageVisibility",
                                                    "Value":  "hide:aicomponents",
                                                    "Type":  "String",
                                                    "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                },
                                                {
                                                    "Path":  "HKLM:\\SOFTWARE\\Policies\\WindowsNotepad",
                                                    "Name":  "DisableAIFeatures",
                                                    "Value":  "1",
                                                    "Type":  "DWord",
                                                    "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                }
                                            ],
                               "InvokeScript":  [
                                                    "\r\n      $Appx = (Get-AppxPackage MicrosoftWindows.Client.CoreAI).PackageFullName\r\n      $Sid = (Get-LocalUser $Env:UserName).Sid.Value\r\n\r\n      New-Item \"HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Appx\\AppxAllUserStore\\EndOfLife\\$Sid\\$Appx\" -Force\r\n\r\n      Get-AppxPackage -AllUsers \"*Copilot*\" | Remove-AppxPackage -AllUsers\r\n      winget uninstall -e --name \"Copilot\" --silent --force --accept-source-agreements 2\u003e$null\r\n      Get-AppxPackage -AllUsers Microsoft.MicrosoftOfficeHub | Remove-AppxPackage -AllUsers\r\n\r\n      if ($Appx) {\r\n          Remove-AppxPackage $Appx\r\n      }\r\n\r\n      Set-Service -Name WSAIFabricSvc -StartupType Disabled\r\n      Disable-WindowsOptionalFeature -FeatureName Recall -Online -NoRestart\r\n\r\n      Write-Host \"Windows AI Disabled\"\r\n      "
                                                ],
                               "link":  "https://winutil.christitus.com/code-reference/tweaks/z--advanced-tweaks---caution/windowsai"
                           },
    "WPFTweaksAzorNoCopilot":  {
                                   "Content":  "Copilot, Recall e IA - Bloquear por Política",
                                   "Description":  "Aplica as políticas oficiais do Windows que desligam o Copilot (TurnOffWindowsCopilot), tornam o Recall indisponível e apagam os snapshots já salvos (AllowRecallEnablement e DisableAIDataAnalysis), desligam o Click to Do e a IA do Paint (Cocreator, preenchimento generativo e criador de imagens). Complementa o ajuste \u0027IA do Windows - Desativar e Remover\u0027, que apaga os pacotes: este aqui impede que a IA volte. A Microsoft documenta estas políticas para as edições Pro, Enterprise e Education, então no Windows Home elas podem não ter efeito. Reinicie o PC depois de aplicar.",
                                   "category":  "z__Ajustes Avançados - CUIDADO",
                                   "panel":  "1",
                                   "registry":  [
                                                    {
                                                        "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsAI",
                                                        "Name":  "AllowRecallEnablement",
                                                        "Value":  "0",
                                                        "Type":  "DWord",
                                                        "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                    },
                                                    {
                                                        "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsAI",
                                                        "Name":  "DisableAIDataAnalysis",
                                                        "Value":  "1",
                                                        "Type":  "DWord",
                                                        "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                    },
                                                    {
                                                        "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsAI",
                                                        "Name":  "DisableClickToDo",
                                                        "Value":  "1",
                                                        "Type":  "DWord",
                                                        "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                    },
                                                    {
                                                        "Path":  "HKCU:\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsCopilot",
                                                        "Name":  "TurnOffWindowsCopilot",
                                                        "Value":  "1",
                                                        "Type":  "DWord",
                                                        "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                    },
                                                    {
                                                        "Path":  "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\Paint",
                                                        "Name":  "DisableCocreator",
                                                        "Value":  "1",
                                                        "Type":  "DWord",
                                                        "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                    },
                                                    {
                                                        "Path":  "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\Paint",
                                                        "Name":  "DisableGenerativeFill",
                                                        "Value":  "1",
                                                        "Type":  "DWord",
                                                        "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                    },
                                                    {
                                                        "Path":  "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\Paint",
                                                        "Name":  "DisableImageCreator",
                                                        "Value":  "1",
                                                        "Type":  "DWord",
                                                        "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                    }
                                                ],
                                   "link":  "https://learn.microsoft.com/en-us/windows/client-management/mdm/policy-csp-windowsai"
                               },
    "WPFTweaksWPBT":  {
                          "Content":  "Windows Platform Binary Table (WPBT) - Desativar",
                          "Description":  "Quando ativado, o WPBT permite que o fabricante do computador execute programas na inicialização, como antirroubo e drivers, e até force a instalação de software sem o seu consentimento. Representa um risco potencial de segurança.",
                          "category":  "Ajustes Essenciais",
                          "panel":  "1",
                          "registry":  [
                                           {
                                               "Path":  "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Session Manager",
                                               "Name":  "DisableWpbtExecution",
                                               "Value":  "1",
                                               "Type":  "DWord",
                                               "OriginalValue":  "\u003cRemoveEntry\u003e"
                                           }
                                       ],
                          "link":  "https://winutil.christitus.com/code-reference/tweaks/essential-tweaks/wpbt"
                      },
    "WPFTweaksPreventDeviceMetadataFromNetwork":  {
                                                      "Content":  "Apps Complementares de Dispositivos - Bloquear",
                                                      "Description":  "Impede a instalação de software adicional ao conectar dispositivos (por exemplo, anúncios ao conectar um monitor). Esses apps representam um risco potencial de segurança.",
                                                      "category":  "Ajustes Essenciais",
                                                      "panel":  "1",
                                                      "registry":  [
                                                                       {
                                                                           "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\Device Metadata",
                                                                           "Name":  "PreventDeviceMetadataFromNetwork",
                                                                           "Value":  "1",
                                                                           "Type":  "DWord",
                                                                           "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                                       }
                                                                   ],
                                                      "link":  "https://winutil.christitus.com/code-reference/tweaks/essential-tweaks/preventdevicemetadatafromnetwork"
                                                  },
    "WPFTweaksDisableNotifications":  {
                                          "Content":  "Notificações e Calendário da Bandeja - Desativar",
                                          "Description":  "Desativa todas as notificações, INCLUSIVE o calendário.",
                                          "category":  "z__Ajustes Avançados - CUIDADO",
                                          "panel":  "1",
                                          "registry":  [
                                                           {
                                                               "Path":  "HKCU:\\Software\\Policies\\Microsoft\\Windows\\Explorer",
                                                               "Name":  "DisableNotificationCenter",
                                                               "Value":  "1",
                                                               "Type":  "DWord",
                                                               "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                           },
                                                           {
                                                               "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\PushNotifications",
                                                               "Name":  "ToastEnabled",
                                                               "Value":  "0",
                                                               "Type":  "DWord",
                                                               "OriginalValue":  "1"
                                                           }
                                                       ],
                                          "link":  "https://winutil.christitus.com/code-reference/tweaks/z--advanced-tweaks---caution/disablenotifications"
                                      },
    "WPFTweaksRightClickMenu":  {
                                    "Content":  "Menu de Contexto Clássico - Ativar",
                                    "Description":  "Restaura o menu de contexto clássico ao clicar com o botão direito no Explorador de Arquivos, substituindo a versão simplificada do Windows 11.",
                                    "category":  "z__Ajustes Avançados - CUIDADO",
                                    "panel":  "1",
                                    "InvokeScript":  [
                                                         "\r\n      New-Item -Path \"HKCU:\\Software\\Classes\\CLSID\\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\" -Name InprocServer32 -Value \"\" -Force\r\n      Stop-Process -Name explorer\r\n      "
                                                     ],
                                    "UndoScript":  [
                                                       "Remove-Item -Path \"HKCU:\\Software\\Classes\\CLSID\\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\" -Recurse"
                                                   ],
                                    "link":  "https://winutil.christitus.com/code-reference/tweaks/z--advanced-tweaks---caution/rightclickmenu"
                                },
    "WPFTweaksDiskCleanup":  {
                                 "Content":  "Limpeza de Disco - Executar",
                                 "Description":  "Executa a Limpeza de Disco na unidade C: e remove atualizações antigas do Windows.",
                                 "category":  "Ajustes Essenciais",
                                 "panel":  "1",
                                 "InvokeScript":  [
                                                      "\r\n      cleanmgr.exe /d C: /VERYLOWDISK\r\n      Dism.exe /online /Cleanup-Image /StartComponentCleanup /ResetBase\r\n      "
                                                  ],
                                 "link":  "https://winutil.christitus.com/code-reference/tweaks/essential-tweaks/diskcleanup"
                             },
    "WPFTweaksIPv46":  {
                           "Content":  "IPv6 - Preferir IPv4",
                           "Description":  "Dar preferência ao IPv4 pode trazer benefícios de latência e segurança em redes privadas onde o IPv6 não está configurado.",
                           "category":  "z__Ajustes Avançados - CUIDADO",
                           "panel":  "1",
                           "registry":  [
                                            {
                                                "Path":  "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip6\\Parameters",
                                                "Name":  "DisabledComponents",
                                                "Value":  "32",
                                                "Type":  "DWord",
                                                "OriginalValue":  "0"
                                            }
                                        ],
                           "link":  "https://winutil.christitus.com/code-reference/tweaks/z--advanced-tweaks---caution/ipv46"
                       },
    "WPFTweaksDisableBGapps":  {
                                   "Content":  "Apps em Segundo Plano - Desativar",
                                   "Description":  "Impede que todos os apps da Microsoft Store rodem em segundo plano, algo que desde o Windows 11 precisa ser feito app por app.",
                                   "category":  "z__Ajustes Avançados - CUIDADO",
                                   "panel":  "1",
                                   "registry":  [
                                                    {
                                                        "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\BackgroundAccessApplications",
                                                        "Name":  "GlobalUserDisabled",
                                                        "Value":  "1",
                                                        "Type":  "DWord",
                                                        "OriginalValue":  "0"
                                                    }
                                                ],
                                   "link":  "https://winutil.christitus.com/code-reference/tweaks/z--advanced-tweaks---caution/disablebgapps"
                               },
    "WPFTweaksDisableExplorerAutoDiscovery":  {
                                                  "Content":  "Detecção Automática de Pastas do Explorador - Desativar",
                                                  "Description":  "O Explorador de Arquivos tenta adivinhar o tipo de cada pasta pelo conteúdo, o que deixa a navegação mais lenta. ATENÇÃO! Também desativa o agrupamento do Explorador de Arquivos.",
                                                  "category":  "Ajustes Essenciais",
                                                  "panel":  "1",
                                                  "InvokeScript":  [
                                                                       "\r\n      # Previously detected folders\r\n      $bags = \"HKCU:\\Software\\Classes\\Local Settings\\Software\\Microsoft\\Windows\\Shell\\Bags\"\r\n\r\n      # Folder types lookup table\r\n      $bagMRU = \"HKCU:\\Software\\Classes\\Local Settings\\Software\\Microsoft\\Windows\\Shell\\BagMRU\"\r\n\r\n      # Flush Explorer view database\r\n      Remove-Item -Path $bags -Recurse -Force\r\n      Write-Host \"Removed $bags\"\r\n\r\n      Remove-Item -Path $bagMRU -Recurse -Force\r\n      Write-Host \"Removed $bagMRU\"\r\n\r\n      # Every folder\r\n      $allFolders = \"HKCU:\\Software\\Classes\\Local Settings\\Software\\Microsoft\\Windows\\Shell\\Bags\\AllFolders\\Shell\"\r\n\r\n      if (!(Test-Path $allFolders)) {\r\n        New-Item -Path $allFolders -Force\r\n        Write-Host \"Created $allFolders\"\r\n      }\r\n\r\n      # Generic view\r\n      New-ItemProperty -Path $allFolders -Name \"FolderType\" -Value \"NotSpecified\" -PropertyType String -Force\r\n      Write-Host \"Set FolderType to NotSpecified\"\r\n\r\n      Write-Host Please sign out and back in, or restart your computer to apply the changes!\r\n      "
                                                                   ],
                                                  "UndoScript":  [
                                                                     "\r\n      # Previously detected folders\r\n      $bags = \"HKCU:\\Software\\Classes\\Local Settings\\Software\\Microsoft\\Windows\\Shell\\Bags\"\r\n\r\n      # Folder types lookup table\r\n      $bagMRU = \"HKCU:\\Software\\Classes\\Local Settings\\Software\\Microsoft\\Windows\\Shell\\BagMRU\"\r\n\r\n      # Flush Explorer view database\r\n      Remove-Item -Path $bags -Recurse -Force\r\n      Write-Host \"Removed $bags\"\r\n\r\n      Remove-Item -Path $bagMRU -Recurse -Force\r\n      Write-Host \"Removed $bagMRU\"\r\n\r\n      Write-Host Please sign out and back in, or restart your computer to apply the changes!\r\n      "
                                                                 ],
                                                  "link":  "https://winutil.christitus.com/code-reference/tweaks/essential-tweaks/disableexplorerautodiscovery"
                                              },
    "WPFToggleDetailedBSoD":  {
                                  "Content":  "Tela Azul Detalhada (BSoD)",
                                  "Description":  "Mostra mais informações quando ocorre uma tela azul.",
                                  "category":  "a__Preferências do Windows",
                                  "panel":  "2",
                                  "Type":  "Toggle",
                                  "registry":  [
                                                   {
                                                       "Path":  "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\CrashControl",
                                                       "Name":  "DisplayParameters",
                                                       "Value":  "1",
                                                       "Type":  "DWord",
                                                       "OriginalValue":  "0",
                                                       "DefaultState":  "false"
                                                   },
                                                   {
                                                       "Path":  "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\CrashControl",
                                                       "Name":  "DisableEmoticon",
                                                       "Value":  "1",
                                                       "Type":  "DWord",
                                                       "OriginalValue":  "0",
                                                       "DefaultState":  "false"
                                                   }
                                               ],
                                  "link":  "https://winutil.christitus.com/code-reference/tweaks/customize-preferences/detailedbsod"
                              },
    "WPFToggleDarkMode":  {
                              "Content":  "Tema Escuro do Windows",
                              "Description":  "Modo escuro para o sistema e os aplicativos.",
                              "category":  "a__Preferências do Windows",
                              "panel":  "2",
                              "Type":  "Toggle",
                              "registry":  [
                                               {
                                                   "Path":  "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize",
                                                   "Name":  "AppsUseLightTheme",
                                                   "Value":  "0",
                                                   "Type":  "DWord",
                                                   "OriginalValue":  "1",
                                                   "DefaultState":  "false"
                                               },
                                               {
                                                   "Path":  "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize",
                                                   "Name":  "SystemUsesLightTheme",
                                                   "Value":  "0",
                                                   "Type":  "DWord",
                                                   "OriginalValue":  "1",
                                                   "DefaultState":  "false"
                                               }
                                           ],
                              "InvokeScript":  [
                                                   "\r\n      Invoke-WinUtilExplorerUpdate\r\n      if ($sync.ThemeButton.Content -eq [char]0xF08C) {\r\n        Invoke-WinutilThemeChange -theme \"Auto\"\r\n      }\r\n      "
                                               ],
                              "UndoScript":  [
                                                 "\r\n      Invoke-WinUtilExplorerUpdate\r\n      if ($sync.ThemeButton.Content -eq [char]0xF08C) {\r\n        Invoke-WinutilThemeChange -theme \"Auto\"\r\n      }\r\n      "
                                             ],
                              "link":  "https://winutil.christitus.com/code-reference/tweaks/customize-preferences/darkmode"
                          },
    "WPFToggleShowExt":  {
                             "Content":  "Extensões de Arquivo no Explorador",
                             "Description":  "Mostra as extensões dos arquivos no Explorador (.exe, .png etc.).",
                             "category":  "a__Preferências do Windows",
                             "panel":  "2",
                             "Type":  "Toggle",
                             "registry":  [
                                              {
                                                  "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced",
                                                  "Name":  "HideFileExt",
                                                  "Value":  "0",
                                                  "Type":  "DWord",
                                                  "OriginalValue":  "1",
                                                  "DefaultState":  "false"
                                              }
                                          ],
                             "InvokeScript":  [
                                                  "\r\n      Invoke-WinUtilExplorerUpdate -action \"restart\"\r\n      "
                                              ],
                             "UndoScript":  [
                                                "\r\n      Invoke-WinUtilExplorerUpdate -action \"restart\"\r\n      "
                                            ],
                             "link":  "https://winutil.christitus.com/code-reference/tweaks/customize-preferences/showext"
                         },
    "WPFToggleHiddenFiles":  {
                                 "Content":  "Arquivos Ocultos no Explorador",
                                 "Description":  "Exibe os arquivos ocultos no Explorador.",
                                 "category":  "a__Preferências do Windows",
                                 "panel":  "2",
                                 "Type":  "Toggle",
                                 "registry":  [
                                                  {
                                                      "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced",
                                                      "Name":  "Hidden",
                                                      "Value":  "1",
                                                      "Type":  "DWord",
                                                      "OriginalValue":  "0",
                                                      "DefaultState":  "false"
                                                  }
                                              ],
                                 "InvokeScript":  [
                                                      "\r\n      Invoke-WinUtilExplorerUpdate -action \"restart\"\r\n      "
                                                  ],
                                 "UndoScript":  [
                                                    "\r\n      Invoke-WinUtilExplorerUpdate -action \"restart\"\r\n      "
                                                ],
                                 "link":  "https://winutil.christitus.com/code-reference/tweaks/customize-preferences/hiddenfiles"
                             },
    "WPFToggleScrollbars":  {
                                "Content":  "Barras de Rolagem Sempre Visíveis",
                                "Description":  "Quando ativado, as barras de rolagem ficam sempre visíveis. Quando desativado, o Windows as esconde automaticamente quando não estão em uso.",
                                "category":  "a__Preferências do Windows",
                                "panel":  "2",
                                "Type":  "Toggle",
                                "registry":  [
                                                 {
                                                     "Path":  "HKCU:\\Control Panel\\Accessibility",
                                                     "Name":  "DynamicScrollbars",
                                                     "Value":  "0",
                                                     "Type":  "DWord",
                                                     "OriginalValue":  "1",
                                                     "DefaultState":  "false"
                                                 }
                                             ],
                                "link":  "https://winutil.christitus.com/code-reference/tweaks/customize-preferences/scrollbars"
                            },
    "WPFMultiplaneOverlay":  {
                                 "Content":  "Multiplane Overlay (MPO)",
                                 "Description":  "O Multiplane Overlay compõe várias camadas de imagem, o que às vezes causa problemas com placas de vídeo. As mudanças nesta opção são aplicadas na hora. CUIDADO: desativar pode resolver piscadas de tela, mas também pode travar a renderização de jogos em tela cheia; se o jogo congelar depois de mexer aqui, volte para Ativado.",
                                 "category":  "a__Preferências do Windows",
                                 "panel":  "2",
                                 "Type":  "Combobox",
                                 "ComboItems":  "Ativado|Desativado (Compatibilidade)|Totalmente Desativado",
                                 "ComboDescriptions":  {
                                                           "Ativado":  "Usa o comportamento padrão de overlay do Windows.",
                                                           "Desativado (Compatibilidade)":  "Desativa o MPO com OverlayTestMode=5, o método de compatibilidade menos agressivo.",
                                                           "Totalmente Desativado":  "Desativa o MPO com OverlayTestMode=5 e DisableOverlays=1, o método mais agressivo."
                                                       },
                                 "registry":  [
                                                  {
                                                      "Path":  "HKLM:\\SOFTWARE\\Microsoft\\Windows\\Dwm",
                                                      "Name":  "OverlayTestMode",
                                                      "Type":  "DWord",
                                                      "DefaultValue":  "0",
                                                      "Values":  {
                                                                     "Ativado":  "\u003cRemoveEntry\u003e",
                                                                     "Desativado (Compatibilidade)":  "5",
                                                                     "Totalmente Desativado":  "5"
                                                                 }
                                                  },
                                                  {
                                                      "Path":  "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers",
                                                      "Name":  "DisableOverlays",
                                                      "Type":  "DWord",
                                                      "DefaultValue":  "0",
                                                      "Values":  {
                                                                     "Ativado":  "\u003cRemoveEntry\u003e",
                                                                     "Desativado (Compatibilidade)":  "\u003cRemoveEntry\u003e",
                                                                     "Totalmente Desativado":  "1"
                                                                 }
                                                  }
                                              ],
                                 "link":  "https://winutil.christitus.com/code-reference/tweaks/customize-preferences/multiplaneoverlay"
                             },
    "WPFToggleMouseAcceleration":  {
                                       "Content":  "Aceleração do Mouse",
                                       "Description":  "Faz o movimento do cursor depender da velocidade com que você move o mouse físico. Para jogos competitivos, o normal é deixar desativado.",
                                       "category":  "a__Preferências do Windows",
                                       "panel":  "2",
                                       "Type":  "Toggle",
                                       "registry":  [
                                                        {
                                                            "Path":  "HKCU:\\Control Panel\\Mouse",
                                                            "Name":  "MouseSpeed",
                                                            "Value":  "1",
                                                            "Type":  "DWord",
                                                            "OriginalValue":  "0",
                                                            "DefaultState":  "true"
                                                        },
                                                        {
                                                            "Path":  "HKCU:\\Control Panel\\Mouse",
                                                            "Name":  "MouseThreshold1",
                                                            "Value":  "6",
                                                            "Type":  "DWord",
                                                            "OriginalValue":  "0",
                                                            "DefaultState":  "true"
                                                        },
                                                        {
                                                            "Path":  "HKCU:\\Control Panel\\Mouse",
                                                            "Name":  "MouseThreshold2",
                                                            "Value":  "10",
                                                            "Type":  "DWord",
                                                            "OriginalValue":  "0",
                                                            "DefaultState":  "true"
                                                        }
                                                    ],
                                       "link":  "https://winutil.christitus.com/code-reference/tweaks/customize-preferences/mouseacceleration"
                                   },
    "WPFToggleNumLock":  {
                             "Content":  "Num Lock Ligado na Inicialização",
                             "Description":  "Define o estado da tecla Num Lock quando o computador liga.",
                             "category":  "a__Preferências do Windows",
                             "panel":  "2",
                             "Type":  "Toggle",
                             "registry":  [
                                              {
                                                  "Path":  "HKU:\\.Default\\Control Panel\\Keyboard",
                                                  "Name":  "InitialKeyboardIndicators",
                                                  "Value":  "2",
                                                  "Type":  "String",
                                                  "OriginalValue":  "0",
                                                  "DefaultState":  "false"
                                              },
                                              {
                                                  "Path":  "HKCU:\\Control Panel\\Keyboard",
                                                  "Name":  "InitialKeyboardIndicators",
                                                  "Value":  "2",
                                                  "Type":  "String",
                                                  "OriginalValue":  "0",
                                                  "DefaultState":  "false"
                                              }
                                          ],
                             "link":  "https://winutil.christitus.com/code-reference/tweaks/customize-preferences/numlock"
                         },
    "WPFToggleWindowSnapping":  {
                                    "Content":  "Ajuste de Janelas (Snap)",
                                    "Description":  "Liga ou desliga o encaixe automático ao arrastar janelas.",
                                    "category":  "a__Preferências do Windows",
                                    "panel":  "2",
                                    "Type":  "Toggle",
                                    "registry":  [
                                                     {
                                                         "Path":  "HKCU:\\Control Panel\\Desktop",
                                                         "Name":  "WindowArrangementActive",
                                                         "Value":  "1",
                                                         "Type":  "String",
                                                         "OriginalValue":  "0",
                                                         "DefaultState":  "true"
                                                     }
                                                 ],
                                    "link":  "https://winutil.christitus.com/code-reference/tweaks/customize-preferences/windowsnapping"
                                },
    "WPFToggleStandbyFix":  {
                                "Content":  "Rede Durante a Suspensão S0",
                                "Description":  "Liga ou desliga a conexão de rede durante a suspensão S0, o modo ocioso de baixo consumo dos notebooks modernos.",
                                "category":  "a__Preferências do Windows",
                                "panel":  "2",
                                "Type":  "Toggle",
                                "registry":  [
                                                 {
                                                     "Path":  "HKCU:\\SOFTWARE\\Policies\\Microsoft\\Power\\PowerSettings\\f15576e8-98b7-4186-b944-eafa664402d9",
                                                     "Name":  "ACSettingIndex",
                                                     "Value":  "1",
                                                     "Type":  "DWord",
                                                     "OriginalValue":  "0",
                                                     "DefaultState":  "true"
                                                 }
                                             ],
                                "link":  "https://winutil.christitus.com/code-reference/tweaks/customize-preferences/standbyfix"
                            },
    "WPFToggleS3Sleep":  {
                             "Content":  "Suspensão S3",
                             "Description":  "Alterna entre o Modern Standby e a suspensão S3, que corta a energia da CPU mas continua mantendo a memória.",
                             "category":  "a__Preferências do Windows",
                             "panel":  "2",
                             "Type":  "Toggle",
                             "registry":  [
                                              {
                                                  "Path":  "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Power",
                                                  "Name":  "PlatformAoAcOverride",
                                                  "Value":  "0",
                                                  "Type":  "DWord",
                                                  "OriginalValue":  "\u003cRemoveEntry\u003e",
                                                  "DefaultState":  "false"
                                              }
                                          ],
                             "link":  "https://winutil.christitus.com/code-reference/tweaks/customize-preferences/s3sleep"
                         },
    "WPFToggleHideSettingsHome":  {
                                      "Content":  "Página Inicial das Configurações",
                                      "Description":  "Mostra ou esconde a página Início do app Configurações do Windows.",
                                      "category":  "a__Preferências do Windows",
                                      "panel":  "2",
                                      "Type":  "Toggle",
                                      "registry":  [
                                                       {
                                                           "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer",
                                                           "Name":  "SettingsPageVisibility",
                                                           "Value":  "show:home",
                                                           "Type":  "String",
                                                           "OriginalValue":  "hide:home",
                                                           "DefaultState":  "true"
                                                       }
                                                   ],
                                      "link":  "https://winutil.christitus.com/code-reference/tweaks/customize-preferences/hidesettingshome"
                                  },
    "WPFToggleBingSearch":  {
                                "Content":  "Pesquisa Bing no Menu Iniciar",
                                "Description":  "Mostra ou esconde resultados da web do Bing na Pesquisa do Windows.",
                                "category":  "a__Preferências do Windows",
                                "panel":  "2",
                                "Type":  "Toggle",
                                "registry":  [
                                                 {
                                                     "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Search",
                                                     "Name":  "BingSearchEnabled",
                                                     "Value":  "1",
                                                     "Type":  "DWord",
                                                     "OriginalValue":  "0",
                                                     "DefaultState":  "true"
                                                 }
                                             ],
                                "link":  "https://winutil.christitus.com/code-reference/tweaks/customize-preferences/bingsearch"
                            },
    "WPFToggleLoginBlur":  {
                               "Content":  "Desfoque Acrílico na Tela de Login",
                               "Description":  "Liga ou desliga o efeito de desfoque acrílico no fundo da tela de login.",
                               "category":  "a__Preferências do Windows",
                               "panel":  "2",
                               "Type":  "Toggle",
                               "registry":  [
                                                {
                                                    "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\System",
                                                    "Name":  "DisableAcrylicBackgroundOnLogon",
                                                    "Value":  "0",
                                                    "Type":  "DWord",
                                                    "OriginalValue":  "1",
                                                    "DefaultState":  "true"
                                                }
                                            ],
                               "link":  "https://winutil.christitus.com/code-reference/tweaks/customize-preferences/loginblur"
                           },
    "WPFTweaksDisableLockscreen":  {
                                       "Content":  "Tela de Bloqueio - Desativar",
                                       "Description":  "Pula completamente a tela de bloqueio e vai direto para a tela de entrada ao ligar o PC e ao sair da suspensão.",
                                       "category":  "a__Preferências do Windows",
                                       "panel":  "2",
                                       "Type":  "Toggle",
                                       "registry":  [
                                                        {
                                                            "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\Personalization",
                                                            "Name":  "NoLockScreen",
                                                            "Value":  "1",
                                                            "Type":  "DWord",
                                                            "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                        }
                                                    ],
                                       "link":  "https://winutil.christitus.com/code-reference/tweaks/customize-preferences/disablelockscreen"
                                   },
    "WPFToggleStartMenuRecommendations":  {
                                              "Content":  "Recomendações no Menu Iniciar",
                                              "Description":  "Mostra ou esconde a seção de recomendações do Menu Iniciar. ATENÇÃO: como efeito colateral, também desativa o Windows Spotlight na tela de bloqueio.",
                                              "category":  "a__Preferências do Windows",
                                              "panel":  "2",
                                              "Type":  "Toggle",
                                              "registry":  [
                                                               {
                                                                   "Path":  "HKLM:\\SOFTWARE\\Microsoft\\PolicyManager\\current\\device\\Start",
                                                                   "Name":  "HideRecommendedSection",
                                                                   "Value":  "0",
                                                                   "Type":  "DWord",
                                                                   "OriginalValue":  "1",
                                                                   "DefaultState":  "true"
                                                               },
                                                               {
                                                                   "Path":  "HKLM:\\SOFTWARE\\Microsoft\\PolicyManager\\current\\device\\Education",
                                                                   "Name":  "IsEducationEnvironment",
                                                                   "Value":  "0",
                                                                   "Type":  "DWord",
                                                                   "OriginalValue":  "1",
                                                                   "DefaultState":  "true"
                                                               },
                                                               {
                                                                   "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\Explorer",
                                                                   "Name":  "HideRecommendedSection",
                                                                   "Value":  "0",
                                                                   "Type":  "DWord",
                                                                   "OriginalValue":  "1",
                                                                   "DefaultState":  "true"
                                                               }
                                                           ],
                                              "InvokeScript":  [
                                                                   "\r\n      Invoke-WinUtilExplorerUpdate -action \"restart\"\r\n      "
                                                               ],
                                              "UndoScript":  [
                                                                 "\r\n      Invoke-WinUtilExplorerUpdate -action \"restart\"\r\n      "
                                                             ],
                                              "link":  "https://winutil.christitus.com/code-reference/tweaks/customize-preferences/startmenurecommendations"
                                          },
    "WPFToggleStickyKeys":  {
                                "Content":  "Teclas de Aderência",
                                "Description":  "Liga ou desliga as Teclas de Aderência, que ativam ao pressionar Shift várias vezes seguidas.",
                                "category":  "a__Preferências do Windows",
                                "panel":  "2",
                                "Type":  "Toggle",
                                "registry":  [
                                                 {
                                                     "Path":  "HKCU:\\Control Panel\\Accessibility\\StickyKeys",
                                                     "Name":  "Flags",
                                                     "Value":  "506",
                                                     "Type":  "String",
                                                     "OriginalValue":  "58",
                                                     "DefaultState":  "true"
                                                 }
                                             ],
                                "link":  "https://winutil.christitus.com/code-reference/tweaks/customize-preferences/stickykeys"
                            },
    "WPFToggleTaskbarAlignment":  {
                                      "Content":  "Ícones Centralizados na Barra de Tarefas",
                                      "Description":  "Alterna o alinhamento da barra de tarefas entre esquerda e centro.",
                                      "category":  "a__Preferências do Windows",
                                      "panel":  "2",
                                      "Type":  "Toggle",
                                      "registry":  [
                                                       {
                                                           "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced",
                                                           "Name":  "TaskbarAl",
                                                           "Value":  "1",
                                                           "Type":  "DWord",
                                                           "OriginalValue":  "0",
                                                           "DefaultState":  "true"
                                                       }
                                                   ],
                                      "InvokeScript":  [
                                                           "\r\n      Invoke-WinUtilExplorerUpdate -action \"restart\"\r\n      "
                                                       ],
                                      "UndoScript":  [
                                                         "\r\n      Invoke-WinUtilExplorerUpdate -action \"restart\"\r\n      "
                                                     ],
                                      "link":  "https://winutil.christitus.com/code-reference/tweaks/customize-preferences/taskbaralignment"
                                  },
    "WPFToggleTaskbarSearch":  {
                                   "Content":  "Ícone de Pesquisa na Barra de Tarefas",
                                   "Description":  "Mostra ou esconde o botão de Pesquisa na barra de tarefas.",
                                   "category":  "a__Preferências do Windows",
                                   "panel":  "2",
                                   "Type":  "Toggle",
                                   "registry":  [
                                                    {
                                                        "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Search",
                                                        "Name":  "SearchboxTaskbarMode",
                                                        "Value":  "1",
                                                        "Type":  "DWord",
                                                        "OriginalValue":  "0",
                                                        "DefaultState":  "true"
                                                    }
                                                ],
                                   "link":  "https://winutil.christitus.com/code-reference/tweaks/customize-preferences/taskbarsearch"
                               },
    "WPFToggleTaskView":  {
                              "Content":  "Ícone da Visão de Tarefas",
                              "Description":  "Mostra ou esconde o botão Visão de Tarefas na barra de tarefas.",
                              "category":  "a__Preferências do Windows",
                              "panel":  "2",
                              "Type":  "Toggle",
                              "registry":  [
                                               {
                                                   "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced",
                                                   "Name":  "ShowTaskViewButton",
                                                   "Value":  "1",
                                                   "Type":  "DWord",
                                                   "OriginalValue":  "0",
                                                   "DefaultState":  "true"
                                               }
                                           ],
                              "link":  "https://winutil.christitus.com/code-reference/tweaks/customize-preferences/taskview"
                          },
    "WPFToggleGameMode":  {
                              "Content":  "Modo de Jogo",
                              "Description":  "Faz o Windows priorizar o desempenho nos jogos, direcionando recursos do sistema para eles.",
                              "category":  "a__Preferências do Windows",
                              "panel":  "2",
                              "Type":  "Toggle",
                              "registry":  [
                                               {
                                                   "Path":  "HKCU:\\Software\\Microsoft\\GameBar",
                                                   "Name":  "AllowAutoGameMode",
                                                   "Value":  "1",
                                                   "Type":  "DWord",
                                                   "OriginalValue":  "0",
                                                   "DefaultState":  "true"
                                               },
                                               {
                                                   "Path":  "HKCU:\\Software\\Microsoft\\GameBar",
                                                   "Name":  "AutoGameModeEnabled",
                                                   "Value":  "1",
                                                   "Type":  "DWord",
                                                   "OriginalValue":  "0",
                                                   "DefaultState":  "true"
                                               }
                                           ],
                              "link":  "https://winutil.christitus.com/code-reference/tweaks/customize-preferences/gamemode"
                          },
    "WPFchangedns":  {
                         "Content":  "DNS - Definir como:",
                         "category":  "z__Ajustes Avançados - CUIDADO",
                         "panel":  "1",
                         "Type":  "Combobox",
                         "ComboItems":  "Default DHCP Google Cloudflare Cloudflare_Malware Cloudflare_Malware_Adult Open_DNS Quad9 AdGuard_Ads_Trackers AdGuard_Ads_Trackers_Malware_Adult Mullvad Mullvad_Ads_Trackers Mullvad_Ads_Trackers_Malware Mullvad_Ads_Trackers_Malware_Social Mullvad_Ads_Trackers_Malware_Adult_Gambling Mullvad_Ads_Trackers_Malware_Adult_Gambling_Social",
                         "link":  "https://winutil.christitus.com/code-reference/tweaks/z--advanced-tweaks---caution/changedns"
                     },
    "WPFAddUltPerf":  {
                          "Content":  "Plano Desempenho Máximo - Ativar",
                          "category":  "c__Planos de Energia - NÃO USE EM NOTEBOOKS",
                          "panel":  "2",
                          "Type":  "Button",
                          "ButtonWidth":  "300",
                          "link":  "https://winutil.christitus.com/code-reference/tweaks/performance-plans---not-for-laptops/addultperf"
                      },
    "WPFRemoveUltPerf":  {
                             "Content":  "Plano Desempenho Máximo - Desativar",
                             "category":  "c__Planos de Energia - NÃO USE EM NOTEBOOKS",
                             "panel":  "2",
                             "Type":  "Button",
                             "ButtonWidth":  "300",
                             "link":  "https://winutil.christitus.com/code-reference/tweaks/performance-plans---not-for-laptops/removeultperf"
                         },
    "WPFTweaksAzorGameDVR":  {
                                 "Content":  "Gravação em Segundo Plano do Xbox (Game DVR) - Desativar",
                                 "Description":  "Desliga a gravação e a transmissão de jogos do Windows (Xbox Game Bar), que capturam a partida em segundo plano e consomem CPU, GPU e disco enquanto você joga. Enquanto o ajuste estiver ativo, a gravação de clipes pela Game Bar fica indisponível.",
                                 "category":  "b__Desempenho e Jogos",
                                 "panel":  "2",
                                 "registry":  [
                                                  {
                                                      "Path":  "HKCU:\\System\\GameConfigStore",
                                                      "Name":  "GameDVR_Enabled",
                                                      "Value":  "0",
                                                      "Type":  "DWord",
                                                      "OriginalValue":  "1"
                                                  },
                                                  {
                                                      "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\GameDVR",
                                                      "Name":  "AppCaptureEnabled",
                                                      "Value":  "0",
                                                      "Type":  "DWord",
                                                      "OriginalValue":  "1"
                                                  },
                                                  {
                                                      "Path":  "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\GameDVR",
                                                      "Name":  "AllowGameDVR",
                                                      "Value":  "0",
                                                      "Type":  "DWord",
                                                      "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                  }
                                              ],
                                 "link":  "https://learn.microsoft.com/windows/client-management/mdm/policy-csp-applicationmanagement#allowgamedvr"
                             },
    "WPFTweaksAzorStartupDelay":  {
                                      "Content":  "Atraso dos Apps de Inicialização - Remover",
                                      "Description":  "Cria o valor StartupDelayInMSec = 0, que reduz a espera do Windows antes de abrir os programas de inicialização depois do login. Eles passam a abrir mais cedo, disputando recursos com o próprio login. Não altera o desempenho durante os jogos.",
                                      "link":  "https://learn.microsoft.com/en-us/answers/questions/4059183/startup-apps-artificially-delayed-on-windows-11",
                                      "category":  "b__Desempenho e Jogos",
                                      "panel":  "2",
                                      "registry":  [
                                                       {
                                                           "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Serialize",
                                                           "Name":  "StartupDelayInMSec",
                                                           "Value":  "0",
                                                           "Type":  "DWord",
                                                           "OriginalValue":  "\u003cRemoveEntry\u003e"
                                                       }
                                                   ]
                                  },
    "WPFTweaksAzorTransparency":  {
                                      "Content":  "Efeitos de Transparência - Desativar",
                                      "Description":  "Desliga os efeitos de transparência (desfoque acrílico) da barra de tarefas, do Menu Iniciar e de janelas do sistema, o mesmo que desativar Efeitos de transparência em Configurações \u003e Personalização \u003e Cores. Alivia um pouco a GPU na área de trabalho; em jogos em tela cheia a diferença é mínima.",
                                      "link":  "https://support.microsoft.com/en-us/windows/experience/personalization/personalize-your-colors-in-windows",
                                      "category":  "b__Desempenho e Jogos",
                                      "panel":  "2",
                                      "registry":  [
                                                       {
                                                           "Path":  "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize",
                                                           "Name":  "EnableTransparency",
                                                           "Value":  "0",
                                                           "Type":  "DWord",
                                                           "OriginalValue":  "1"
                                                       }
                                                   ]
                                  },
    "WPFToggleAzorHAGS":  {
                              "Content":  "Agendamento de GPU Acelerado por Hardware (HAGS)",
                              "Description":  "Passa o agendamento da GPU para a própria placa de vídeo, o que pode reduzir a latência. Requer placa e driver compatíveis e só vale depois de reiniciar o PC.",
                              "category":  "a__Preferências do Windows",
                              "panel":  "2",
                              "Type":  "Toggle",
                              "registry":  [
                                               {
                                                   "Path":  "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers",
                                                   "Name":  "HwSchMode",
                                                   "Value":  "2",
                                                   "Type":  "DWord",
                                                   "OriginalValue":  "1",
                                                   "DefaultState":  "false"
                                               }
                                           ],
                              "link":  "https://devblogs.microsoft.com/directx/hardware-accelerated-gpu-scheduling/"
                          }
}
'@ | ConvertFrom-Json
$inputXML = @'
<Window
        xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        xmlns:d="http://schemas.microsoft.com/expression/blend/2008"
        xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
        xmlns:local="clr-namespace:WinUtility"
        WindowStartupLocation="CenterScreen"
        UseLayoutRounding="True"
        WindowStyle="SingleBorderWindow"
        Width="Auto"
        Height="Auto"
        MinWidth="800"
        MinHeight="600"
        Title="Azor WinUtil">
    <WindowChrome.WindowChrome>
        <WindowChrome CaptionHeight="0" CornerRadius="10" UseAeroCaptionButtons="False"/>
    </WindowChrome.WindowChrome>
    <Window.Resources>
    <!-- Azor brand brushes. They stay the same in every theme. -->
    <!-- Theme colors, so the wordmark and the dashboard title stay readable on the light background too -->
    <LinearGradientBrush x:Key="AzorRoseGradientBrush" StartPoint="0,0" EndPoint="1,0">
        <GradientStop Color="{DynamicResource CLabelboxForegroundColor}" Offset="0"/>
        <GradientStop Color="{DynamicResource CAccentColor}" Offset="0.5"/>
        <GradientStop Color="{DynamicResource CAccentSecondaryColor}" Offset="1"/>
    </LinearGradientBrush>
    <LinearGradientBrush x:Key="AzorAccentButtonBrush" StartPoint="0,0" EndPoint="1,1">
        <GradientStop Color="#FFF23D98" Offset="0"/>
        <GradientStop Color="#FFA0176C" Offset="1"/>
    </LinearGradientBrush>
    <LinearGradientBrush x:Key="AzorAccentButtonHoverBrush" StartPoint="0,0" EndPoint="1,1">
        <GradientStop Color="#FFFF5FB0" Offset="0"/>
        <GradientStop Color="#FFBD2285" Offset="1"/>
    </LinearGradientBrush>
    <LinearGradientBrush x:Key="AzorProgressBrush" StartPoint="0,0" EndPoint="1,0">
        <GradientStop Color="#FFFF8FC8" Offset="0"/>
        <GradientStop Color="#FFFF4DA6" Offset="0.55"/>
        <GradientStop Color="#FFA64DFF" Offset="1"/>
    </LinearGradientBrush>

    <Style TargetType="ToolTip">
        <Setter Property="Background" Value="{DynamicResource ToolTipBackgroundColor}"/>
        <Setter Property="Foreground" Value="{DynamicResource MainForegroundColor}"/>
        <Setter Property="BorderBrush" Value="{DynamicResource AccentColor}"/>
        <Setter Property="MaxWidth" Value="{DynamicResource ToolTipWidth}"/>
        <Setter Property="BorderThickness" Value="1"/>
        <Setter Property="Padding" Value="8,5"/>
        <Setter Property="FontSize" Value="{DynamicResource FontSize}"/>
        <Setter Property="FontFamily" Value="{DynamicResource FontFamily}"/>
        <!-- This ContentTemplate ensures that the content of the ToolTip wraps text properly for better readability -->
        <Setter Property="ContentTemplate">
            <Setter.Value>
                <DataTemplate>
                    <ContentPresenter Content="{TemplateBinding Content}">
                        <ContentPresenter.Resources>
                            <Style TargetType="TextBlock">
                                <Setter Property="TextWrapping" Value="Wrap"/>
                            </Style>
                        </ContentPresenter.Resources>
                    </ContentPresenter>
                </DataTemplate>
            </Setter.Value>
        </Setter>
    </Style>

    <Style TargetType="{x:Type MenuItem}">
        <Setter Property="Background" Value="Transparent"/>
        <Setter Property="Foreground" Value="{DynamicResource MainForegroundColor}"/>
        <Setter Property="FontSize" Value="{DynamicResource FontSize}"/>
        <Setter Property="FontFamily" Value="{DynamicResource FontFamily}"/>
        <Setter Property="Cursor" Value="Hand"/>
        <Setter Property="Template">
            <Setter.Value>
                <ControlTemplate TargetType="{x:Type MenuItem}">
                    <Border Name="MenuItemBorder" Background="{TemplateBinding Background}" CornerRadius="6" Padding="12,7,24,7" Margin="2,1">
                        <ContentPresenter ContentSource="Header" RecognizesAccessKey="True" VerticalAlignment="Center"/>
                    </Border>
                    <ControlTemplate.Triggers>
                        <Trigger Property="IsHighlighted" Value="True">
                            <Setter TargetName="MenuItemBorder" Property="Background" Value="{DynamicResource ButtonBackgroundMouseoverColor}"/>
                            <Setter Property="Foreground" Value="{DynamicResource LinkForegroundColor}"/>
                        </Trigger>
                    </ControlTemplate.Triggers>
                </ControlTemplate>
            </Setter.Value>
        </Setter>
    </Style>

    <Style TargetType="Separator">
        <Setter Property="Background" Value="{DynamicResource BorderColor}"/>
        <Setter Property="Margin" Value="8,4"/>
    </Style>

    <!--Scrollbar Thumbs-->
    <Style x:Key="ScrollThumbs" TargetType="{x:Type Thumb}">
        <Setter Property="Template">
            <Setter.Value>
                <ControlTemplate TargetType="{x:Type Thumb}">
                    <Grid Name="Grid">
                        <Rectangle HorizontalAlignment="Stretch" VerticalAlignment="Stretch" Width="Auto" Height="Auto" Fill="Transparent" />
                        <Border Name="Rectangle1" CornerRadius="5" HorizontalAlignment="Stretch" VerticalAlignment="Stretch" Width="Auto" Height="Auto"  Background="{TemplateBinding Background}" />
                    </Grid>
                    <ControlTemplate.Triggers>
                        <Trigger Property="Tag" Value="Horizontal">
                            <Setter TargetName="Rectangle1" Property="Width" Value="Auto" />
                            <Setter TargetName="Rectangle1" Property="Height" Value="7" />
                        </Trigger>
                    </ControlTemplate.Triggers>
                </ControlTemplate>
            </Setter.Value>
        </Setter>
    </Style>

    <Style TargetType="TextBlock" x:Key="HoverTextBlockStyle">
        <Setter Property="Foreground" Value="{DynamicResource LinkForegroundColor}" />
        <Setter Property="TextDecorations" Value="Underline" />
        <Style.Triggers>
            <Trigger Property="IsMouseOver" Value="True">
                <Setter Property="Foreground" Value="{DynamicResource LinkHoverForegroundColor}" />
                <Setter Property="TextDecorations" Value="Underline" />
                <Setter Property="Cursor" Value="Hand" />
            </Trigger>
        </Style.Triggers>
    </Style>
    <Style x:Key="AppEntryBorderStyle" TargetType="Border">
        <Setter Property="BorderBrush" Value="{DynamicResource BorderColor}"/>
        <Setter Property="BorderThickness" Value="{DynamicResource AppEntryBorderThickness}"/>
        <Setter Property="CornerRadius" Value="8"/>
        <Setter Property="Padding" Value="6,4"/>
        <Setter Property="Width" Value="{DynamicResource AppEntryWidth}"/>
        <Setter Property="VerticalAlignment" Value="Top"/>
        <Setter Property="Margin" Value="{DynamicResource AppEntryMargin}"/>
        <Setter Property="Cursor" Value="Hand"/>
        <Setter Property="Background" Value="{DynamicResource AppInstallUnselectedColor}"/>
    </Style>
    <Style x:Key="AppEntryCheckboxStyle" TargetType="CheckBox">
        <Setter Property="Background" Value="Transparent"/>
        <Setter Property="HorizontalAlignment" Value="Left"/>
        <Setter Property="VerticalAlignment" Value="Center"/>
        <Setter Property="Margin" Value="{DynamicResource AppEntryMargin}"/>
        <Setter Property="Template">
            <Setter.Value>
                <ControlTemplate TargetType="CheckBox">
                    <ContentPresenter Content="{TemplateBinding Content}"
                                      VerticalAlignment="Center"
                                      HorizontalAlignment="Left"/>
                </ControlTemplate>
            </Setter.Value>
        </Setter>
    </Style>
    <Style x:Key="AppEntryNameStyle" TargetType="TextBlock">
        <Setter Property="FontSize" Value="{DynamicResource AppEntryFontSize}"/>
        <Setter Property="FontWeight" Value="SemiBold"/>
        <Setter Property="Foreground" Value="{DynamicResource MainForegroundColor}"/>
        <Setter Property="VerticalAlignment" Value="Center"/>
        <Setter Property="Margin" Value="{DynamicResource AppEntryMargin}"/>
        <Setter Property="Background" Value="Transparent"/>
    </Style>
    <Style x:Key="AppEntryButtonStyle" TargetType="Button">
        <Setter Property="Width" Value="{DynamicResource IconButtonSize}"/>
        <Setter Property="Height" Value="{DynamicResource IconButtonSize}"/>
        <Setter Property="Margin" Value="{DynamicResource AppEntryMargin}"/>
        <Setter Property="Foreground" Value="{DynamicResource ButtonForegroundColor}"/>
        <Setter Property="Background" Value="{DynamicResource ButtonBackgroundColor}"/>
        <Setter Property="BorderBrush" Value="{DynamicResource AccentColor}"/>
        <Setter Property="HorizontalAlignment" Value="Center"/>
        <Setter Property="VerticalAlignment" Value="Center"/>
        <Setter Property="Cursor" Value="Hand"/>
        <Setter Property="ContentTemplate">
            <Setter.Value>
                <DataTemplate>
                    <TextBlock  Text="{Binding}"
                                FontFamily="Segoe MDL2 Assets"
                                FontSize="{DynamicResource IconFontSize}"
                                Background="Transparent"/>
                </DataTemplate>
            </Setter.Value>
        </Setter>
        <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="Button">
                        <Grid>
                            <Border Name="BackgroundBorder"
                                    Background="{TemplateBinding Background}"
                                    BorderBrush="{TemplateBinding BorderBrush}"
                                    BorderThickness="{DynamicResource ButtonBorderThickness}"
                                    CornerRadius="{DynamicResource ButtonCornerRadius}">
                                <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
                            </Border>
                        </Grid>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter Property="Cursor" Value="Hand"/>
                                <Setter TargetName="BackgroundBorder" Property="Background" Value="{DynamicResource ButtonBackgroundMouseoverColor}"/>
                            </Trigger>
                            <Trigger Property="IsPressed" Value="True">
                                <Setter TargetName="BackgroundBorder" Property="Background" Value="{DynamicResource ButtonBackgroundPressedColor}"/>
                            </Trigger>
                            <Trigger Property="IsEnabled" Value="False">
                                <Setter TargetName="BackgroundBorder" Property="Background" Value="{DynamicResource ButtonBackgroundSelectedColor}"/>
                                <Setter Property="Foreground" Value="{DynamicResource MutedForegroundColor}"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
    </Style>
    <Style TargetType="Button" x:Key="HoverButtonStyle">
        <Setter Property="Foreground" Value="{DynamicResource MainForegroundColor}" />
        <Setter Property="FontWeight" Value="Normal" />
        <Setter Property="FontSize" Value="{DynamicResource ButtonFontSize}" />
        <Setter Property="TextElement.FontFamily" Value="{DynamicResource ButtonFontFamily}"/>
        <Setter Property="Background" Value="Transparent" />
        <Setter Property="Template">
            <Setter.Value>
                <ControlTemplate TargetType="Button">
                    <Border Name="HoverBorder" Background="{TemplateBinding Background}" CornerRadius="7">
                        <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
                    </Border>
                    <ControlTemplate.Triggers>
                        <Trigger Property="IsMouseOver" Value="True">
                            <Setter TargetName="HoverBorder" Property="Background" Value="{DynamicResource ButtonBackgroundMouseoverColor}" />
                            <Setter Property="Foreground" Value="{DynamicResource LinkForegroundColor}" />
                            <Setter Property="Cursor" Value="Hand" />
                        </Trigger>
                        <Trigger Property="IsPressed" Value="True">
                            <Setter TargetName="HoverBorder" Property="Background" Value="{DynamicResource ButtonBackgroundSelectedColor}" />
                        </Trigger>
                    </ControlTemplate.Triggers>
                </ControlTemplate>
            </Setter.Value>
        </Setter>
    </Style>
    <Style TargetType="Button" x:Key="CloseButtonStyle" BasedOn="{StaticResource HoverButtonStyle}">
        <Setter Property="Template">
            <Setter.Value>
                <ControlTemplate TargetType="Button">
                    <Border Name="HoverBorder" Background="{TemplateBinding Background}" CornerRadius="7">
                        <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
                    </Border>
                    <ControlTemplate.Triggers>
                        <Trigger Property="IsMouseOver" Value="True">
                            <Setter TargetName="HoverBorder" Property="Background" Value="{DynamicResource WarningColor}" />
                            <Setter Property="Foreground" Value="White" />
                            <Setter Property="Cursor" Value="Hand" />
                        </Trigger>
                    </ControlTemplate.Triggers>
                </ControlTemplate>
            </Setter.Value>
        </Setter>
    </Style>

    <!--ScrollBars-->
    <Style x:Key="{x:Type ScrollBar}" TargetType="{x:Type ScrollBar}">
        <Setter Property="Stylus.IsFlicksEnabled" Value="false" />
        <Setter Property="Foreground" Value="{DynamicResource ScrollBarBackgroundColor}" />
        <Setter Property="Background" Value="Transparent" />
        <Setter Property="Width" Value="6" />
        <Setter Property="Template">
            <Setter.Value>
                <ControlTemplate TargetType="{x:Type ScrollBar}">
                    <Grid Name="GridRoot" Width="7" Background="{TemplateBinding Background}" >
                        <Grid.RowDefinitions>
                            <RowDefinition Height="0.00001*" />
                        </Grid.RowDefinitions>

                        <Track Name="PART_Track" Grid.Row="0" IsDirectionReversed="true" Focusable="false">
                            <Track.Thumb>
                                <Thumb Name="Thumb" Background="{TemplateBinding Foreground}" Style="{DynamicResource ScrollThumbs}" />
                            </Track.Thumb>
                            <Track.IncreaseRepeatButton>
                                <RepeatButton Name="PageUp" Command="ScrollBar.PageDownCommand" Opacity="0" Focusable="false" />
                            </Track.IncreaseRepeatButton>
                            <Track.DecreaseRepeatButton>
                                <RepeatButton Name="PageDown" Command="ScrollBar.PageUpCommand" Opacity="0" Focusable="false" />
                            </Track.DecreaseRepeatButton>
                        </Track>
                    </Grid>

                    <ControlTemplate.Triggers>
                        <Trigger SourceName="Thumb" Property="IsMouseOver" Value="true">
                            <Setter Value="{DynamicResource ScrollBarHoverColor}" TargetName="Thumb" Property="Background" />
                        </Trigger>
                        <Trigger SourceName="Thumb" Property="IsDragging" Value="true">
                            <Setter Value="{DynamicResource ScrollBarDraggingColor}" TargetName="Thumb" Property="Background" />
                        </Trigger>

                        <Trigger Property="IsEnabled" Value="false">
                            <Setter TargetName="Thumb" Property="Visibility" Value="Collapsed" />
                        </Trigger>
                        <Trigger Property="Orientation" Value="Horizontal">
                            <Setter TargetName="GridRoot" Property="LayoutTransform">
                                <Setter.Value>
                                    <RotateTransform Angle="-90" />
                                </Setter.Value>
                            </Setter>
                            <Setter TargetName="PART_Track" Property="LayoutTransform">
                                <Setter.Value>
                                    <RotateTransform Angle="-90" />
                                </Setter.Value>
                            </Setter>
                            <Setter Property="Width" Value="Auto" />
                            <Setter Property="Height" Value="8" />
                            <Setter TargetName="Thumb" Property="Tag" Value="Horizontal" />
                            <Setter TargetName="PageDown" Property="Command" Value="ScrollBar.PageLeftCommand" />
                            <Setter TargetName="PageUp" Property="Command" Value="ScrollBar.PageRightCommand" />
                        </Trigger>
                    </ControlTemplate.Triggers>
                </ControlTemplate>
            </Setter.Value>
        </Setter>
        </Style>
        <Style x:Key="ComboBoxToggleButtonStyle" TargetType="ToggleButton">
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="ToggleButton">
                        <Border Background="{TemplateBinding Background}" BorderThickness="0">
                            <ContentPresenter/>
                        </Border>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>
        <Style TargetType="ComboBox">
            <Setter Property="Foreground" Value="{DynamicResource ComboBoxForegroundColor}" />
            <Setter Property="Background" Value="{DynamicResource ComboBoxBackgroundColor}" />
            <Setter Property="MinWidth"   Value="{DynamicResource ButtonWidth}" />
            <Setter Property="Cursor" Value="Hand"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="ComboBox">
                        <Grid>
                            <Border Name="OuterBorder"
                                    BorderBrush="{DynamicResource BorderColor}"
                                    BorderThickness="1"
                                    CornerRadius="{DynamicResource ButtonCornerRadius}"
                                    Background="{TemplateBinding Background}">
                                <ToggleButton Name="ToggleButton"
                                              Style="{StaticResource ComboBoxToggleButtonStyle}"
                                              Background="Transparent"
                                              BorderThickness="0"
                                              IsChecked="{Binding IsDropDownOpen, Mode=TwoWay, RelativeSource={RelativeSource TemplatedParent}}"
                                              ClickMode="Press">
                                    <Grid>
                                        <Grid.ColumnDefinitions>
                                            <ColumnDefinition Width="*"/>
                                            <ColumnDefinition Width="Auto"/>
                                        </Grid.ColumnDefinitions>
                                        <TextBlock Grid.Column="0"
                                                   Text="{TemplateBinding SelectionBoxItem}"
                                                   Foreground="{TemplateBinding Foreground}"
                                                   Background="Transparent"
                                                   HorizontalAlignment="Left" VerticalAlignment="Center"
                                                   Margin="8,3,2,3"/>
                                        <Path Grid.Column="1"
                                              Data="M 0,0 L 8,0 L 4,5 Z"
                                              Fill="{DynamicResource AccentColor}"
                                              Width="8" Height="5"
                                              VerticalAlignment="Center"
                                              HorizontalAlignment="Center"
                                              Stretch="Uniform"
                                              Margin="4,0,8,0"/>
                                    </Grid>
                                </ToggleButton>
                            </Border>
                            <Popup Name="Popup"
                                   IsOpen="{TemplateBinding IsDropDownOpen}"
                                   Placement="Bottom"
                                   Focusable="False"
                                   AllowsTransparency="True"
                                   PopupAnimation="Slide">
                                <Border Name="DropDownBorder"
                                        Background="{TemplateBinding Background}"
                                        BorderBrush="{DynamicResource AccentColor}"
                                        BorderThickness="1"
                                        CornerRadius="8"
                                        Margin="0,2,0,0">
                                    <ScrollViewer MaxHeight="360">
                                        <ItemsPresenter HorizontalAlignment="Stretch" VerticalAlignment="Center" Margin="4"/>
                                    </ScrollViewer>
                                </Border>
                            </Popup>
                        </Grid>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="OuterBorder" Property="BorderBrush" Value="{DynamicResource AccentColor}"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>
        <Style TargetType="ComboBoxItem">
            <Setter Property="Background" Value="{DynamicResource ComboBoxBackgroundColor}"/>
            <Setter Property="Foreground" Value="{DynamicResource ComboBoxForegroundColor}"/>
            <Setter Property="Padding" Value="8,4"/>
            <Setter Property="ContentTemplate">
                <Setter.Value>
                    <DataTemplate>
                        <TextBlock Text="{Binding}" Background="Transparent"
                                   Foreground="{Binding Foreground, RelativeSource={RelativeSource AncestorType=ComboBoxItem}}"/>
                    </DataTemplate>
                </Setter.Value>
            </Setter>
            <Style.Triggers>
                <Trigger Property="IsHighlighted" Value="True">
                    <Setter Property="Background" Value="{DynamicResource ButtonBackgroundMouseoverColor}"/>
                </Trigger>
                <Trigger Property="IsSelected" Value="True">
                    <Setter Property="Background" Value="{DynamicResource ButtonBackgroundSelectedColor}"/>
                </Trigger>
            </Style.Triggers>
        </Style>
        <Style TargetType="Label">
            <Setter Property="Foreground" Value="{DynamicResource LabelboxForegroundColor}"/>
            <Setter Property="Background" Value="{DynamicResource LabelBackgroundColor}"/>
            <Setter Property="FontFamily" Value="{DynamicResource FontFamily}"/>
        </Style>

        <!-- TextBlock template -->
        <Style TargetType="TextBlock">
            <Setter Property="FontSize" Value="{DynamicResource FontSize}"/>
            <Setter Property="Foreground" Value="{DynamicResource LabelboxForegroundColor}"/>
            <Setter Property="Background" Value="{DynamicResource LabelBackgroundColor}"/>
        </Style>

        <!-- Top navigation tabs: rose outline, glow and gradient underline on the active tab -->
        <Style x:Key="TabToggleButton" TargetType="{x:Type ToggleButton}">
            <Setter Property="Margin" Value="0,0,4,0"/>
            <Setter Property="Content" Value=""/>
            <Setter Property="FontFamily" Value="{DynamicResource ButtonFontFamily}"/>
            <Setter Property="Foreground" Value="{DynamicResource MutedForegroundColor}"/>
            <Setter Property="Background" Value="Transparent"/>
            <Setter Property="Cursor" Value="Hand"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="ToggleButton">
                        <Grid>
                            <Border Name="ButtonGlow"
                                    Background="{DynamicResource ButtonBackgroundSelectedColor}"
                                    CornerRadius="8"
                                    Opacity="0">
                                <Border.Effect>
                                    <DropShadowEffect Color="{DynamicResource CAccentColor}" BlurRadius="16" ShadowDepth="0" Opacity="0.7"/>
                                </Border.Effect>
                            </Border>
                            <Border Name="BackgroundBorder"
                                    Background="{TemplateBinding Background}"
                                    BorderBrush="Transparent"
                                    BorderThickness="1"
                                    CornerRadius="8">
                                <ContentPresenter
                                    HorizontalAlignment="Center"
                                    VerticalAlignment="Center"
                                    Margin="12,2,12,2"/>
                            </Border>
                            <Border Name="ActiveBar"
                                    Height="3"
                                    CornerRadius="1.5"
                                    VerticalAlignment="Bottom"
                                    Margin="18,0,18,1"
                                    Background="{StaticResource AzorRoseGradientBrush}"
                                    Opacity="0"/>
                        </Grid>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="BackgroundBorder" Property="Background" Value="{DynamicResource ButtonBackgroundMouseoverColor}"/>
                                <Setter Property="Foreground" Value="{DynamicResource MainForegroundColor}"/>
                            </Trigger>
                            <Trigger Property="IsChecked" Value="True">
                                <Setter TargetName="ButtonGlow" Property="Opacity" Value="0.55"/>
                                <Setter TargetName="BackgroundBorder" Property="Background" Value="{DynamicResource ButtonBackgroundSelectedColor}"/>
                                <Setter TargetName="BackgroundBorder" Property="BorderBrush" Value="{DynamicResource AccentColor}"/>
                                <Setter TargetName="ActiveBar" Property="Opacity" Value="1"/>
                                <Setter Property="Foreground" Value="{DynamicResource MainForegroundColor}"/>
                            </Trigger>
                            <Trigger Property="IsEnabled" Value="False">
                                <Setter Property="Opacity" Value="0.45"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>
        <!-- Button Template -->
        <Style TargetType="Button">
            <Setter Property="Margin" Value="{DynamicResource ButtonMargin}"/>
            <Setter Property="Foreground" Value="{DynamicResource ButtonForegroundColor}"/>
            <Setter Property="Background" Value="{DynamicResource ButtonBackgroundColor}"/>
            <Setter Property="BorderBrush" Value="{DynamicResource BorderColor}"/>
            <Setter Property="Height" Value="{DynamicResource ButtonHeight}"/>
            <Setter Property="Width" Value="{DynamicResource ButtonWidth}"/>
            <Setter Property="FontSize" Value="{DynamicResource ButtonFontSize}"/>
            <Setter Property="FontFamily" Value="{DynamicResource ButtonFontFamily}"/>
            <Setter Property="Cursor" Value="Hand"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="Button">
                        <Grid>
                            <Border Name="BackgroundBorder"
                                    Background="{TemplateBinding Background}"
                                    BorderBrush="{TemplateBinding BorderBrush}"
                                    BorderThickness="{DynamicResource ButtonBorderThickness}"
                                    CornerRadius="{DynamicResource ButtonCornerRadius}">
                                <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center" Margin="10,2,10,2"/>
                            </Border>
                        </Grid>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="BackgroundBorder" Property="Background" Value="{DynamicResource ButtonBackgroundMouseoverColor}"/>
                                <Setter TargetName="BackgroundBorder" Property="BorderBrush" Value="{DynamicResource AccentColor}"/>
                            </Trigger>
                            <Trigger Property="IsPressed" Value="True">
                                <Setter TargetName="BackgroundBorder" Property="Background" Value="{DynamicResource ButtonBackgroundPressedColor}"/>
                                <Setter Property="Foreground" Value="{DynamicResource AccentForegroundColor}"/>
                            </Trigger>
                            <Trigger Property="IsEnabled" Value="False">
                                <Setter TargetName="BackgroundBorder" Property="Background" Value="{DynamicResource ButtonBackgroundSelectedColor}"/>
                                <Setter TargetName="BackgroundBorder" Property="Opacity" Value="0.6"/>
                                <Setter Property="Foreground" Value="{DynamicResource MutedForegroundColor}"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>

        <!-- Primary action button: rose gradient with a ki glow on hover -->
        <Style x:Key="AccentButtonStyle" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
            <Setter Property="Foreground" Value="White"/>
            <Setter Property="Background" Value="{StaticResource AzorAccentButtonBrush}"/>
            <Setter Property="BorderBrush" Value="Transparent"/>
            <Setter Property="FontWeight" Value="SemiBold"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="Button">
                        <Grid>
                            <Border Name="Glow" CornerRadius="{DynamicResource ButtonCornerRadius}" Background="{TemplateBinding Background}" Opacity="0">
                                <Border.Effect>
                                    <DropShadowEffect Color="{DynamicResource CAccentColor}" BlurRadius="20" ShadowDepth="0" Opacity="0.9"/>
                                </Border.Effect>
                            </Border>
                            <Border Name="BackgroundBorder" Background="{TemplateBinding Background}" CornerRadius="{DynamicResource ButtonCornerRadius}">
                                <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center" Margin="12,2,12,2"/>
                            </Border>
                        </Grid>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="Glow" Property="Opacity" Value="0.8"/>
                                <Setter TargetName="BackgroundBorder" Property="Background" Value="{StaticResource AzorAccentButtonHoverBrush}"/>
                            </Trigger>
                            <Trigger Property="IsPressed" Value="True">
                                <Setter TargetName="BackgroundBorder" Property="Opacity" Value="0.85"/>
                            </Trigger>
                            <Trigger Property="IsEnabled" Value="False">
                                <Setter Property="Opacity" Value="0.5"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>

        <Style x:Key="ToggleButtonStyle" TargetType="ToggleButton">
            <Setter Property="Margin" Value="{DynamicResource ButtonMargin}"/>
            <Setter Property="Foreground" Value="{DynamicResource ButtonForegroundColor}"/>
            <Setter Property="Background" Value="{DynamicResource ButtonBackgroundColor}"/>
            <Setter Property="BorderBrush" Value="{DynamicResource BorderColor}"/>
            <Setter Property="Height" Value="{DynamicResource ButtonHeight}"/>
            <Setter Property="Width" Value="{DynamicResource ButtonWidth}"/>
            <Setter Property="FontSize" Value="{DynamicResource ButtonFontSize}"/>
            <Setter Property="FontFamily" Value="{DynamicResource FontFamily}"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="ToggleButton">
                        <Grid>
                            <Border Name="BackgroundBorder"
                                    Background="{TemplateBinding Background}"
                                    BorderBrush="{TemplateBinding BorderBrush}"
                                    BorderThickness="{DynamicResource ButtonBorderThickness}"
                                    CornerRadius="{DynamicResource ButtonCornerRadius}">
                                <Grid>
                                    <!-- Toggle Dot Background -->
                                    <Ellipse Width="8" Height="16"
                                            Fill="{DynamicResource ToggleButtonOnColor}"
                                            HorizontalAlignment="Right"
                                            VerticalAlignment="Top"
                                            Margin="0,3,5,0" />

                                    <!-- Toggle Dot with hover grow effect -->
                                    <Ellipse Name="ToggleDot"
                                            Width="8" Height="8"
                                            Fill="{DynamicResource ButtonForegroundColor}"
                                            HorizontalAlignment="Right"
                                            VerticalAlignment="Top"
                                            Margin="0,3,5,0"
                                            RenderTransformOrigin="0.5,0.5">
                                        <Ellipse.RenderTransform>
                                            <ScaleTransform ScaleX="1" ScaleY="1"/>
                                        </Ellipse.RenderTransform>
                                    </Ellipse>

                                    <!-- Content Presenter -->
                                    <ContentPresenter HorizontalAlignment="Center"
                                                    VerticalAlignment="Center"
                                                    Margin="10,2,10,2"/>
                                </Grid>
                            </Border>
                        </Grid>

                        <!-- Triggers for ToggleButton states -->
                        <ControlTemplate.Triggers>
                            <!-- Hover effect -->
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="BackgroundBorder" Property="Background" Value="{DynamicResource ButtonBackgroundMouseoverColor}"/>
                                <Trigger.EnterActions>
                                    <BeginStoryboard>
                                        <Storyboard>
                                            <!-- Animation to grow the dot when hovered -->
                                            <DoubleAnimation Storyboard.TargetName="ToggleDot"
                                                            Storyboard.TargetProperty="(UIElement.RenderTransform).(ScaleTransform.ScaleX)"
                                                            To="1.2" Duration="0:0:0.1"/>
                                            <DoubleAnimation Storyboard.TargetName="ToggleDot"
                                                            Storyboard.TargetProperty="(UIElement.RenderTransform).(ScaleTransform.ScaleY)"
                                                            To="1.2" Duration="0:0:0.1"/>
                                        </Storyboard>
                                    </BeginStoryboard>
                                </Trigger.EnterActions>
                                <Trigger.ExitActions>
                                    <BeginStoryboard>
                                        <Storyboard>
                                            <!-- Animation to shrink the dot back to original size when not hovered -->
                                            <DoubleAnimation Storyboard.TargetName="ToggleDot"
                                                            Storyboard.TargetProperty="(UIElement.RenderTransform).(ScaleTransform.ScaleX)"
                                                            To="1.0" Duration="0:0:0.1"/>
                                            <DoubleAnimation Storyboard.TargetName="ToggleDot"
                                                            Storyboard.TargetProperty="(UIElement.RenderTransform).(ScaleTransform.ScaleY)"
                                                            To="1.0" Duration="0:0:0.1"/>
                                        </Storyboard>
                                    </BeginStoryboard>
                                </Trigger.ExitActions>
                            </Trigger>

                            <!-- IsChecked state -->
                            <Trigger Property="IsChecked" Value="True">
                                <Setter TargetName="ToggleDot" Property="VerticalAlignment" Value="Bottom"/>
                                <Setter TargetName="ToggleDot" Property="Margin" Value="0,0,5,3"/>
                            </Trigger>

                            <!-- IsEnabled state -->
                            <Trigger Property="IsEnabled" Value="False">
                                <Setter TargetName="BackgroundBorder" Property="Background" Value="{DynamicResource ButtonBackgroundSelectedColor}"/>
                                <Setter Property="Foreground" Value="{DynamicResource MutedForegroundColor}"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>

        <Style x:Key="SearchBarClearButtonStyle" TargetType="Button">
            <Setter Property="FontFamily" Value="{DynamicResource FontFamily}"/>
            <Setter Property="FontSize" Value="{DynamicResource SearchBarClearButtonFontSize}"/>
            <Setter Property="Content" Value="X"/>
            <Setter Property="Height" Value="{DynamicResource SearchBarClearButtonFontSize}"/>
            <Setter Property="Width" Value="{DynamicResource SearchBarClearButtonFontSize}"/>
            <Setter Property="Background" Value="Transparent"/>
            <Setter Property="Foreground" Value="{DynamicResource MutedForegroundColor}"/>
            <Setter Property="Padding" Value="0"/>
            <Setter Property="BorderBrush" Value="Transparent"/>
            <Setter Property="BorderThickness" Value="0"/>
            <Style.Triggers>
                <Trigger Property="IsMouseOver" Value="True">
                    <Setter Property="Foreground" Value="{DynamicResource WarningColor}"/>
                    <Setter Property="Background" Value="Transparent"/>
                    <Setter Property="BorderThickness" Value="10"/>
                    <Setter Property="Cursor" Value="Hand"/>
                </Trigger>
            </Style.Triggers>
        </Style>
        <!-- Checkbox template -->
        <Style TargetType="CheckBox">
            <Setter Property="Foreground" Value="{DynamicResource MainForegroundColor}"/>
            <Setter Property="Background" Value="Transparent"/>
            <Setter Property="FontSize" Value="{DynamicResource FontSize}" />
            <Setter Property="FontFamily" Value="{DynamicResource FontFamily}"/>
            <Setter Property="TextElement.FontFamily" Value="{DynamicResource FontFamily}"/>
            <Setter Property="Cursor" Value="Hand"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="CheckBox">
                        <Grid Background="{TemplateBinding Background}" Margin="{DynamicResource CheckBoxMargin}">
                            <BulletDecorator Background="Transparent">
                                <BulletDecorator.Bullet>
                                    <Grid Width="{DynamicResource CheckBoxBulletDecoratorSize}" Height="{DynamicResource CheckBoxBulletDecoratorSize}">
                                        <Border Name="Border"
                                                Background="{DynamicResource InputBackgroundColor}"
                                                BorderBrush="{DynamicResource ToggleButtonOffColor}"
                                                BorderThickness="1.5"
                                                CornerRadius="4"
                                                SnapsToDevicePixels="True"/>
                                        <Viewbox Name="CheckMarkContainer"
                                                Margin="3.5"
                                                HorizontalAlignment="Center"
                                                VerticalAlignment="Center"
                                                Visibility="Collapsed">
                                            <Path Name="CheckMark"
                                                  Stroke="{DynamicResource AccentForegroundColor}"
                                                  StrokeThickness="2.4"
                                                  StrokeStartLineCap="Round"
                                                  StrokeEndLineCap="Round"
                                                  StrokeLineJoin="Round"
                                                  Data="M 0 5 L 4.5 9.5 L 12 1"
                                                  Stretch="Uniform"/>
                                        </Viewbox>
                                    </Grid>
                                </BulletDecorator.Bullet>
                                <ContentPresenter Margin="7,0,0,0"
                                                  HorizontalAlignment="Left"
                                                  VerticalAlignment="Center"
                                                  RecognizesAccessKey="True"/>
                            </BulletDecorator>
                        </Grid>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsChecked" Value="True">
                                <Setter TargetName="CheckMarkContainer" Property="Visibility" Value="Visible"/>
                                <Setter TargetName="Border" Property="Background" Value="{DynamicResource AccentColor}"/>
                                <Setter TargetName="Border" Property="BorderBrush" Value="{DynamicResource AccentColor}"/>
                            </Trigger>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="Border" Property="BorderBrush" Value="{DynamicResource AccentColor}"/>
                                <Setter Property="Foreground" Value="{DynamicResource LinkForegroundColor}"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                 </Setter.Value>
            </Setter>
        </Style>
        <Style TargetType="RadioButton">
            <Setter Property="Foreground" Value="{DynamicResource MainForegroundColor}"/>
            <Setter Property="Background" Value="Transparent"/>
            <Setter Property="FontSize" Value="{DynamicResource FontSize}" />
            <Setter Property="FontFamily" Value="{DynamicResource FontFamily}"/>
            <Setter Property="Cursor" Value="Hand"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="RadioButton">
                        <StackPanel Orientation="Horizontal" Margin="{DynamicResource CheckBoxMargin}">
                            <Viewbox Width="{DynamicResource CheckBoxBulletDecoratorSize}" Height="{DynamicResource CheckBoxBulletDecoratorSize}">
                                <Grid Width="14" Height="14">
                                    <Ellipse Name="OuterCircle"
                                            Stroke="{DynamicResource ToggleButtonOffColor}"
                                            Fill="{DynamicResource InputBackgroundColor}"
                                            StrokeThickness="1.3"
                                            Width="14"
                                            Height="14"
                                            SnapsToDevicePixels="True"/>
                                    <Ellipse Name="InnerCircle"
                                            Fill="{DynamicResource AccentColor}"
                                            Width="7"
                                            Height="7"
                                            Visibility="Collapsed"
                                            HorizontalAlignment="Center"
                                            VerticalAlignment="Center"/>
                                </Grid>
                            </Viewbox>
                            <ContentPresenter Margin="7,0,0,0"
                                            VerticalAlignment="Center"
                                            RecognizesAccessKey="True"/>
                        </StackPanel>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsChecked" Value="True">
                                <Setter TargetName="InnerCircle" Property="Visibility" Value="Visible"/>
                                <Setter TargetName="OuterCircle" Property="Stroke" Value="{DynamicResource AccentColor}"/>
                            </Trigger>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="OuterCircle" Property="Stroke" Value="{DynamicResource AccentColor}"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>

        <Style x:Key="ColorfulToggleSwitchStyle" TargetType="{x:Type CheckBox}">
            <Setter Property="Cursor" Value="Hand"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="{x:Type ToggleButton}">
                        <Grid Name="toggleSwitch">

                        <Grid.ColumnDefinitions>
                            <ColumnDefinition Width="Auto"/>
                            <ColumnDefinition Width="Auto"/>
                        </Grid.ColumnDefinitions>

                        <Border Grid.Column="1" Name="Border" CornerRadius="9"
                                BorderThickness="1.5"
                                Width="38" Height="19">
                            <Ellipse Name="Ellipse" Fill="{DynamicResource MainForegroundColor}" Stretch="Uniform"
                                    Margin="2.5,2.5,2.5,2.5"
                                    HorizontalAlignment="Left" Width="11"
                                    RenderTransformOrigin="0.5, 0.5">
                                <Ellipse.RenderTransform>
                                    <ScaleTransform ScaleX="1" ScaleY="1" />
                                </Ellipse.RenderTransform>
                            </Ellipse>
                        </Border>
                        </Grid>

                        <ControlTemplate.Triggers>
                            <Trigger Property="ToggleButton.IsChecked" Value="False">
                                <Setter TargetName="Border" Property="Background" Value="{DynamicResource InputBackgroundColor}" />
                                <Setter TargetName="Border" Property="BorderBrush" Value="{DynamicResource ToggleButtonOffColor}" />
                                <Setter TargetName="Ellipse" Property="Fill" Value="{DynamicResource ToggleButtonOffColor}" />
                            </Trigger>

                            <Trigger Property="ToggleButton.IsChecked" Value="True">
                                <Setter TargetName="Border" Property="Background" Value="{DynamicResource ToggleButtonOnColor}" />
                                <Setter TargetName="Border" Property="BorderBrush" Value="{DynamicResource ToggleButtonOnColor}" />
                                <Setter TargetName="Ellipse" Property="Fill" Value="White" />

                                <Trigger.EnterActions>
                                    <BeginStoryboard>
                                        <Storyboard>
                                            <ThicknessAnimation Storyboard.TargetName="Ellipse"
                                                    Storyboard.TargetProperty="Margin"
                                                    To="21,2.5,2.5,2.5" Duration="0:0:0.12" />
                                        </Storyboard>
                                    </BeginStoryboard>
                                </Trigger.EnterActions>
                                <Trigger.ExitActions>
                                    <BeginStoryboard>
                                        <Storyboard>
                                            <ThicknessAnimation Storyboard.TargetName="Ellipse"
                                                    Storyboard.TargetProperty="Margin"
                                                    To="2.5,2.5,2.5,2.5" Duration="0:0:0.12" />
                                        </Storyboard>
                                    </BeginStoryboard>
                                </Trigger.ExitActions>
                            </Trigger>

                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="Border" Property="BorderBrush" Value="{DynamicResource AccentColor}" />
                                <Setter Property="Panel.ZIndex" Value="1000"/>
                                <Trigger.EnterActions>
                                    <BeginStoryboard>
                                        <Storyboard>
                                            <DoubleAnimation Storyboard.TargetName="Ellipse"
                                                            Storyboard.TargetProperty="(UIElement.RenderTransform).(ScaleTransform.ScaleX)"
                                                            To="1.12" Duration="0:0:0.1" />
                                            <DoubleAnimation Storyboard.TargetName="Ellipse"
                                                            Storyboard.TargetProperty="(UIElement.RenderTransform).(ScaleTransform.ScaleY)"
                                                            To="1.12" Duration="0:0:0.1" />
                                        </Storyboard>
                                    </BeginStoryboard>
                                </Trigger.EnterActions>
                                <Trigger.ExitActions>
                                    <BeginStoryboard>
                                        <Storyboard>
                                            <DoubleAnimation Storyboard.TargetName="Ellipse"
                                                            Storyboard.TargetProperty="(UIElement.RenderTransform).(ScaleTransform.ScaleX)"
                                                            To="1.0" Duration="0:0:0.1" />
                                            <DoubleAnimation Storyboard.TargetName="Ellipse"
                                                            Storyboard.TargetProperty="(UIElement.RenderTransform).(ScaleTransform.ScaleY)"
                                                            To="1.0" Duration="0:0:0.1" />
                                        </Storyboard>
                                    </BeginStoryboard>
                                </Trigger.ExitActions>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
            <Setter Property="VerticalContentAlignment" Value="Center" />
        </Style>

        <Style x:Key="BorderStyle" TargetType="Border">
            <Setter Property="Background" Value="{DynamicResource CardBackgroundColor}"/>
            <Setter Property="BorderBrush" Value="{DynamicResource BorderColor}"/>
            <Setter Property="BorderThickness" Value="1"/>
            <Setter Property="CornerRadius" Value="{DynamicResource CardCornerRadius}"/>
            <Setter Property="Padding" Value="8"/>
            <Setter Property="Margin" Value="5"/>
        </Style>

        <Style TargetType="TextBox">
            <Setter Property="Background" Value="{DynamicResource InputBackgroundColor}"/>
            <Setter Property="BorderBrush" Value="{DynamicResource BorderColor}"/>
            <Setter Property="BorderThickness" Value="1"/>
            <Setter Property="Foreground" Value="{DynamicResource MainForegroundColor}"/>
            <Setter Property="FontSize" Value="{DynamicResource FontSize}"/>
            <Setter Property="FontFamily" Value="{DynamicResource FontFamily}"/>
            <Setter Property="Padding" Value="5"/>
            <Setter Property="HorizontalAlignment" Value="Stretch"/>
            <Setter Property="VerticalAlignment" Value="Center"/>
            <Setter Property="HorizontalContentAlignment" Value="Stretch"/>
            <Setter Property="VerticalContentAlignment" Value="Center"/>
            <Setter Property="CaretBrush" Value="{DynamicResource AccentColor}"/>
            <Setter Property="SelectionBrush" Value="{DynamicResource AccentColor}"/>
            <Setter Property="ContextMenu">
                <Setter.Value>
                    <ContextMenu>
                        <ContextMenu.Style>
                            <Style TargetType="ContextMenu">
                                <Setter Property="Template">
                                    <Setter.Value>
                                        <ControlTemplate TargetType="ContextMenu">
                                            <Border Background="{DynamicResource CardBackgroundColor}" BorderBrush="{DynamicResource AccentColor}" BorderThickness="1" CornerRadius="8" Padding="4">
                                                <StackPanel>
                                                    <MenuItem Command="Cut" Header="Recortar"/>
                                                    <MenuItem Command="Copy" Header="Copiar"/>
                                                    <MenuItem Command="Paste" Header="Colar"/>
                                                </StackPanel>
                                            </Border>
                                        </ControlTemplate>
                                    </Setter.Value>
                                </Setter>
                            </Style>
                        </ContextMenu.Style>
                    </ContextMenu>
                </Setter.Value>
            </Setter>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="TextBox">
                        <Border Name="TextBoxBorder"
                                Background="{TemplateBinding Background}"
                                BorderBrush="{TemplateBinding BorderBrush}"
                                BorderThickness="{TemplateBinding BorderThickness}"
                                CornerRadius="8">
                            <Grid>
                                <ScrollViewer Name="PART_ContentHost" Margin="{TemplateBinding Padding}" VerticalAlignment="{TemplateBinding VerticalContentAlignment}"/>
                            </Grid>
                        </Border>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="TextBoxBorder" Property="BorderBrush" Value="{DynamicResource ToggleButtonOffColor}"/>
                            </Trigger>
                            <Trigger Property="IsKeyboardFocused" Value="True">
                                <Setter TargetName="TextBoxBorder" Property="BorderBrush" Value="{DynamicResource AccentColor}"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>
        <Style TargetType="PasswordBox">
            <Setter Property="Background" Value="{DynamicResource InputBackgroundColor}"/>
            <Setter Property="BorderBrush" Value="{DynamicResource BorderColor}"/>
            <Setter Property="BorderThickness" Value="1"/>
            <Setter Property="Foreground" Value="{DynamicResource MainForegroundColor}"/>
            <Setter Property="FontSize" Value="{DynamicResource FontSize}"/>
            <Setter Property="FontFamily" Value="{DynamicResource FontFamily}"/>
            <Setter Property="Padding" Value="5"/>
            <Setter Property="HorizontalAlignment" Value="Stretch"/>
            <Setter Property="VerticalAlignment" Value="Center"/>
            <Setter Property="HorizontalContentAlignment" Value="Stretch"/>
            <Setter Property="CaretBrush" Value="{DynamicResource AccentColor}"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="PasswordBox">
                        <Border Background="{TemplateBinding Background}"
                                BorderBrush="{TemplateBinding BorderBrush}"
                                BorderThickness="{TemplateBinding BorderThickness}"
                                CornerRadius="8">
                            <Grid>
                                <ScrollViewer Name="PART_ContentHost" Margin="{TemplateBinding Padding}"/>
                            </Grid>
                        </Border>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>
        <Style x:Key="RoundedProgressBarStyle" TargetType="ProgressBar">
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="ProgressBar">
                        <Border CornerRadius="4" Background="{DynamicResource InputBackgroundColor}" BorderBrush="{DynamicResource BorderColor}" BorderThickness="1">
                            <Grid ClipToBounds="True">
                                <Border Name="PART_Track" CornerRadius="4" Background="Transparent"/>
                                <Border Name="PART_Indicator" CornerRadius="4" Background="{StaticResource AzorProgressBrush}" HorizontalAlignment="Left"/>
                            </Grid>
                        </Border>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>
        <!-- Category filter chips. A toggle rather than a button, so the active filter is visible
             on the chip itself instead of only in the results below. -->
        <Style x:Key="FilterChipToggleStyle" TargetType="ToggleButton">
            <Setter Property="Margin" Value="2"/>
            <Setter Property="Padding" Value="13,5,13,5"/>
            <Setter Property="Cursor" Value="Hand"/>
            <Setter Property="FontSize" Value="{DynamicResource ButtonFontSize}"/>
            <Setter Property="FontFamily" Value="{DynamicResource ButtonFontFamily}"/>
            <Setter Property="Foreground" Value="{DynamicResource ButtonForegroundColor}"/>
            <Setter Property="Background" Value="{DynamicResource ButtonBackgroundColor}"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="ToggleButton">
                        <Border Name="ChipBorder"
                                Background="{TemplateBinding Background}"
                                BorderBrush="{DynamicResource BorderColor}"
                                BorderThickness="1"
                                CornerRadius="14"
                                Padding="{TemplateBinding Padding}">
                            <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"
                                              TextBlock.Foreground="{TemplateBinding Foreground}"
                                              TextBlock.FontSize="{TemplateBinding FontSize}"/>
                        </Border>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="ChipBorder" Property="Background" Value="{DynamicResource ButtonBackgroundMouseoverColor}"/>
                            </Trigger>
                            <!-- Only colours change on check. Anything affecting text width, bold for
                                 instance, would resize the chip and shift every chip after it. -->
                            <Trigger Property="IsChecked" Value="True">
                                <Setter TargetName="ChipBorder" Property="Background" Value="{DynamicResource ButtonBackgroundSelectedColor}"/>
                                <Setter TargetName="ChipBorder" Property="BorderBrush" Value="{DynamicResource AccentColor}"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>

        <!-- Dashboard building blocks -->
        <Style x:Key="DashboardCardStyle" TargetType="Border">
            <Setter Property="Background" Value="{DynamicResource CardBackgroundColor}"/>
            <Setter Property="BorderBrush" Value="{DynamicResource BorderColor}"/>
            <Setter Property="BorderThickness" Value="1"/>
            <Setter Property="CornerRadius" Value="{DynamicResource CardCornerRadius}"/>
            <Setter Property="Padding" Value="16,14"/>
            <Setter Property="Margin" Value="6"/>
        </Style>
        <Style x:Key="DashboardBadgeStyle" TargetType="Border">
            <Setter Property="Background" Value="{DynamicResource ButtonBackgroundColor}"/>
            <Setter Property="BorderBrush" Value="{DynamicResource BorderColor}"/>
            <Setter Property="BorderThickness" Value="1"/>
            <Setter Property="CornerRadius" Value="11"/>
            <Setter Property="Padding" Value="10,3"/>
            <Setter Property="Margin" Value="0,0,8,6"/>
        </Style>
        <Style x:Key="CardIconStyle" TargetType="TextBlock">
            <Setter Property="FontFamily" Value="Segoe MDL2 Assets"/>
            <Setter Property="FontSize" Value="16"/>
            <Setter Property="Foreground" Value="{DynamicResource AccentColor}"/>
            <Setter Property="Background" Value="Transparent"/>
            <Setter Property="VerticalAlignment" Value="Center"/>
        </Style>
        <Style x:Key="CardTitleStyle" TargetType="TextBlock">
            <Setter Property="FontFamily" Value="{DynamicResource HeaderFontFamily}"/>
            <Setter Property="FontSize" Value="13"/>
            <Setter Property="Foreground" Value="{DynamicResource MutedForegroundColor}"/>
            <Setter Property="Background" Value="Transparent"/>
            <Setter Property="VerticalAlignment" Value="Center"/>
        </Style>
        <Style x:Key="CardHeaderStyle" TargetType="TextBlock">
            <Setter Property="FontFamily" Value="{DynamicResource HeaderFontFamily}"/>
            <Setter Property="FontSize" Value="17"/>
            <Setter Property="Foreground" Value="{DynamicResource MainForegroundColor}"/>
            <Setter Property="Background" Value="Transparent"/>
            <Setter Property="VerticalAlignment" Value="Center"/>
        </Style>
        <Style x:Key="CardValueStyle" TargetType="TextBlock">
            <Setter Property="FontFamily" Value="{DynamicResource HeaderFontFamily}"/>
            <Setter Property="FontSize" Value="{DynamicResource DashboardValueFontSize}"/>
            <Setter Property="Foreground" Value="{DynamicResource MainForegroundColor}"/>
            <Setter Property="Background" Value="Transparent"/>
            <Setter Property="TextTrimming" Value="CharacterEllipsis"/>
        </Style>
        <Style x:Key="CardDetailStyle" TargetType="TextBlock">
            <Setter Property="FontSize" Value="{DynamicResource FontSize}"/>
            <Setter Property="Foreground" Value="{DynamicResource MutedForegroundColor}"/>
            <Setter Property="Background" Value="Transparent"/>
            <Setter Property="TextTrimming" Value="CharacterEllipsis"/>
        </Style>
        <Style x:Key="QuickActionButtonStyle" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
            <Setter Property="Width" Value="Auto"/>
            <Setter Property="Height" Value="Auto"/>
            <Setter Property="MinHeight" Value="58"/>
            <Setter Property="Margin" Value="4"/>
            <Setter Property="HorizontalAlignment" Value="Stretch"/>
            <Setter Property="HorizontalContentAlignment" Value="Left"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="Button">
                        <Border Name="ActionBorder"
                                Background="{TemplateBinding Background}"
                                BorderBrush="{TemplateBinding BorderBrush}"
                                BorderThickness="1"
                                CornerRadius="10"
                                Padding="12,8">
                            <ContentPresenter HorizontalAlignment="Left" VerticalAlignment="Center"/>
                        </Border>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="ActionBorder" Property="Background" Value="{DynamicResource ButtonBackgroundMouseoverColor}"/>
                                <Setter TargetName="ActionBorder" Property="BorderBrush" Value="{DynamicResource AccentColor}"/>
                            </Trigger>
                            <Trigger Property="IsPressed" Value="True">
                                <Setter TargetName="ActionBorder" Property="Background" Value="{DynamicResource ButtonBackgroundSelectedColor}"/>
                            </Trigger>
                            <Trigger Property="IsEnabled" Value="False">
                                <Setter TargetName="ActionBorder" Property="Opacity" Value="0.5"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>
        <Style x:Key="QuickActionIconStyle" TargetType="TextBlock">
            <Setter Property="FontFamily" Value="Segoe MDL2 Assets"/>
            <Setter Property="FontSize" Value="20"/>
            <Setter Property="Width" Value="30"/>
            <Setter Property="Foreground" Value="{DynamicResource AccentColor}"/>
            <Setter Property="Background" Value="Transparent"/>
            <Setter Property="VerticalAlignment" Value="Center"/>
            <Setter Property="TextAlignment" Value="Center"/>
        </Style>
        <Style x:Key="QuickActionTitleStyle" TargetType="TextBlock">
            <Setter Property="FontFamily" Value="{DynamicResource ButtonFontFamily}"/>
            <Setter Property="FontSize" Value="13"/>
            <Setter Property="Foreground" Value="{DynamicResource MainForegroundColor}"/>
            <Setter Property="Background" Value="Transparent"/>
        </Style>
        <Style x:Key="QuickActionSubtitleStyle" TargetType="TextBlock">
            <Setter Property="FontSize" Value="11"/>
            <Setter Property="Foreground" Value="{DynamicResource MutedForegroundColor}"/>
            <Setter Property="Background" Value="Transparent"/>
            <Setter Property="TextTrimming" Value="CharacterEllipsis"/>
        </Style>
        <Style x:Key="NavIconStyle" TargetType="TextBlock">
            <Setter Property="FontFamily" Value="Segoe MDL2 Assets"/>
            <Setter Property="FontSize" Value="{DynamicResource IconFontSize}"/>
            <Setter Property="VerticalAlignment" Value="Center"/>
            <Setter Property="Margin" Value="0,1,7,0"/>
            <Setter Property="Background" Value="Transparent"/>
        </Style>
        <Style x:Key="PopupBorderStyle" TargetType="Border">
            <Setter Property="Background" Value="{DynamicResource CardBackgroundColor}"/>
            <Setter Property="BorderBrush" Value="{DynamicResource AccentColor}"/>
            <Setter Property="BorderThickness" Value="1"/>
            <Setter Property="CornerRadius" Value="10"/>
            <Setter Property="Padding" Value="4"/>
            <Setter Property="Margin" Value="0,4,0,0"/>
        </Style>
    </Window.Resources>
    <Grid Background="{DynamicResource MainBackgroundColor}" ShowGridLines="False" Name="WPFMainGrid" Width="Auto" Height="Auto" HorizontalAlignment="Stretch">
        <Grid.RowDefinitions>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="*"/>
            <RowDefinition Height="Auto"/>
        </Grid.RowDefinitions>
        <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
        </Grid.ColumnDefinitions>
        <!-- Offline banner -->
        <Border Name="WPFOfflineBanner" Grid.Row="0" Background="{DynamicResource WarningColor}" Visibility="Collapsed" Padding="6,4">
            <TextBlock Text="&#x26A0; Modo offline - sem conexão com a internet" Foreground="White" FontWeight="Bold"
                HorizontalAlignment="Center" FontSize="13" Background="Transparent"/>
        </Border>
        <Grid Grid.Row="1" Background="{DynamicResource MainBackgroundColor}">
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="Auto"/> <!-- Navigation buttons -->
                <ColumnDefinition Width="*"/> <!-- Search bar and buttons -->
            </Grid.ColumnDefinitions>

            <!-- Navigation Buttons Panel -->
            <StackPanel Name="NavDockPanel" Orientation="Horizontal" Grid.Column="0" VerticalAlignment="Center" Margin="5,6,8,6">
                <StackPanel Name="NavLogoPanel" Orientation="Horizontal" HorizontalAlignment="Left" VerticalAlignment="Center" Background="Transparent" SnapsToDevicePixels="True" Margin="8,0,16,0">
                    <StackPanel Orientation="Vertical" VerticalAlignment="Center" Margin="8,0,0,0">
                        <TextBlock Text="AZOR" FontFamily="{DynamicResource HeaderFontFamily}" FontSize="19" Foreground="{StaticResource AzorRoseGradientBrush}" Margin="0,-3,0,-4"/>
                        <TextBlock Text="WINUTIL" FontFamily="{DynamicResource HeaderFontFamily}" FontSize="9" Foreground="{DynamicResource MutedForegroundColor}" Margin="1,0,0,0"/>
                    </StackPanel>
                </StackPanel>
                <ToggleButton Style="{StaticResource TabToggleButton}" Height="{DynamicResource TabButtonHeight}" MinWidth="{DynamicResource TabButtonWidth}"
                    Name="WPFTab7BT" IsChecked="True" ToolTip="Visão geral do PC e ações rápidas (Alt+P)">
                    <ToggleButton.Content>
                        <StackPanel Orientation="Horizontal">
                            <TextBlock Text="&#xE80F;" Style="{StaticResource NavIconStyle}" Foreground="{Binding Foreground, RelativeSource={RelativeSource AncestorType=ToggleButton}}"/>
                            <TextBlock FontSize="{DynamicResource TabButtonFontSize}" VerticalAlignment="Center" Background="Transparent" Foreground="{Binding Foreground, RelativeSource={RelativeSource AncestorType=ToggleButton}}"><Underline>P</Underline>ainel</TextBlock>
                        </StackPanel>
                    </ToggleButton.Content>
                </ToggleButton>
                <ToggleButton Style="{StaticResource TabToggleButton}" Height="{DynamicResource TabButtonHeight}" MinWidth="{DynamicResource TabButtonWidth}"
                    Name="WPFTab1BT" ToolTip="Instalar e atualizar programas (Alt+I)">
                    <ToggleButton.Content>
                        <StackPanel Orientation="Horizontal">
                            <TextBlock Text="&#xF0E2;" Style="{StaticResource NavIconStyle}" Foreground="{Binding Foreground, RelativeSource={RelativeSource AncestorType=ToggleButton}}"/>
                            <TextBlock FontSize="{DynamicResource TabButtonFontSize}" VerticalAlignment="Center" Background="Transparent" Foreground="{Binding Foreground, RelativeSource={RelativeSource AncestorType=ToggleButton}}"><Underline>I</Underline>nstalar</TextBlock>
                        </StackPanel>
                    </ToggleButton.Content>
                </ToggleButton>
                <ToggleButton Style="{StaticResource TabToggleButton}" Height="{DynamicResource TabButtonHeight}" MinWidth="{DynamicResource TabButtonWidth}"
                    Name="WPFTab2BT" ToolTip="Ajustes de desempenho, privacidade e jogos (Alt+O)">
                    <ToggleButton.Content>
                        <StackPanel Orientation="Horizontal">
                            <TextBlock Text="&#xEC4A;" Style="{StaticResource NavIconStyle}" Foreground="{Binding Foreground, RelativeSource={RelativeSource AncestorType=ToggleButton}}"/>
                            <TextBlock FontSize="{DynamicResource TabButtonFontSize}" VerticalAlignment="Center" Background="Transparent" Foreground="{Binding Foreground, RelativeSource={RelativeSource AncestorType=ToggleButton}}"><Underline>O</Underline>timizar</TextBlock>
                        </StackPanel>
                    </ToggleButton.Content>
                </ToggleButton>
                <ToggleButton Style="{StaticResource TabToggleButton}" Height="{DynamicResource TabButtonHeight}" MinWidth="{DynamicResource TabButtonWidth}"
                    Name="WPFTab3BT" ToolTip="Recursos do Windows, correções e painéis clássicos (Alt+R)">
                    <ToggleButton.Content>
                        <StackPanel Orientation="Horizontal">
                            <TextBlock Text="&#xEC7A;" Style="{StaticResource NavIconStyle}" Foreground="{Binding Foreground, RelativeSource={RelativeSource AncestorType=ToggleButton}}"/>
                            <TextBlock FontSize="{DynamicResource TabButtonFontSize}" VerticalAlignment="Center" Background="Transparent" Foreground="{Binding Foreground, RelativeSource={RelativeSource AncestorType=ToggleButton}}"><Underline>R</Underline>ecursos</TextBlock>
                        </StackPanel>
                    </ToggleButton.Content>
                </ToggleButton>
            </StackPanel>

            <!-- Search Bar and Action Buttons -->
            <Grid Name="GridBesideNavDockPanel" Grid.Column="1" Background="{DynamicResource MainBackgroundColor}" ShowGridLines="False" Height="Auto">
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="2*"/> <!-- Search bar area - priority space -->
                    <ColumnDefinition Width="Auto"/><!-- Buttons area -->
                </Grid.ColumnDefinitions>

                <Border Grid.Column="0" Margin="5,0,10,0" MinWidth="120" Height="{DynamicResource SearchBarHeight}" VerticalAlignment="Center" HorizontalAlignment="Stretch">
                    <Grid>
                        <TextBox
                            Height="{DynamicResource SearchBarHeight}"
                            FontSize="{DynamicResource SearchBarTextBoxFontSize}"
                            VerticalAlignment="Center" HorizontalAlignment="Stretch"
                            BorderThickness="1"
                            Name="SearchBar"
                            Foreground="{DynamicResource MainForegroundColor}" Background="{DynamicResource InputBackgroundColor}"
                            Padding="10,0,30,0"
                            ToolTip="Pressione Ctrl+F e digite para filtrar a lista abaixo. Esc limpa o filtro."
                            AutomationProperties.Name="Pesquisar">
                        </TextBox>
                        <TextBlock
                            Name="SearchBarIcon"
                            VerticalAlignment="Center" HorizontalAlignment="Right"
                            FontFamily="Segoe MDL2 Assets"
                            Foreground="{DynamicResource AccentColor}"
                            FontSize="{DynamicResource IconFontSize}"
                            IsHitTestVisible="False"
                            Margin="0,0,10,0" Width="Auto" Height="Auto">&#xE721;
                        </TextBlock>
                    </Grid>
                </Border>
                <Button Grid.Column="0"
                    VerticalAlignment="Center" HorizontalAlignment="Right"
                    Name="SearchBarClearButton"
                    Style="{StaticResource SearchBarClearButtonStyle}"
                    AutomationProperties.Name="Limpar pesquisa"
                    Margin="0,0,20,0" Visibility="Collapsed">
                </Button>

                <!-- Buttons Container -->
                <StackPanel Grid.Column="1" Orientation="Horizontal" HorizontalAlignment="Right" VerticalAlignment="Center" Margin="5,5,6,5">
                    <Button Name="ThemeButton"
                        Style="{StaticResource HoverButtonStyle}"
                        BorderBrush="Transparent"
                    Background="Transparent"
                    Foreground="{DynamicResource MainForegroundColor}"
                    FontSize="{DynamicResource SettingsIconFontSize}"
                    Width="{DynamicResource IconButtonSize}" Height="{DynamicResource IconButtonSize}"
                    HorizontalAlignment="Right" VerticalAlignment="Center"
                    Margin="0,0,2,0"
                    FontFamily="Segoe MDL2 Assets"
                    Content="N/A"
                    ToolTip="Mudar o tema do Azor WinUtil"
                    AutomationProperties.Name="Tema"
                />
                    <Popup Name="ThemePopup"
                    IsOpen="False"
                    AllowsTransparency="True"
                    PopupAnimation="Fade"
                    PlacementTarget="{Binding ElementName=ThemeButton}" Placement="Bottom"
                    HorizontalAlignment="Right" VerticalAlignment="Top">
                    <Border Style="{StaticResource PopupBorderStyle}">
                        <StackPanel Background="Transparent" HorizontalAlignment="Stretch" VerticalAlignment="Stretch" MinWidth="190">
                            <MenuItem FontSize="{DynamicResource ButtonFontSize}" Header="Automático (tema do Windows)" Name="AutoThemeMenuItem" Foreground="{DynamicResource MainForegroundColor}">
                                <MenuItem.ToolTip>
                                    <ToolTip Content="Segue o tema claro/escuro do Windows"/>
                                </MenuItem.ToolTip>
                            </MenuItem>
                            <MenuItem FontSize="{DynamicResource ButtonFontSize}" Header="Goku Black (escuro)" Name="DarkThemeMenuItem" Foreground="{DynamicResource MainForegroundColor}">
                                <MenuItem.ToolTip>
                                    <ToolTip Content="Preto profundo com detalhes em rosé"/>
                                </MenuItem.ToolTip>
                            </MenuItem>
                            <MenuItem FontSize="{DynamicResource ButtonFontSize}" Header="Rosé (claro)" Name="LightThemeMenuItem" Foreground="{DynamicResource MainForegroundColor}">
                                <MenuItem.ToolTip>
                                    <ToolTip Content="Fundo claro com detalhes em rosé"/>
                                </MenuItem.ToolTip>
                            </MenuItem>
                        </StackPanel>
                    </Border>
                </Popup>

                    <Button Name="FontScalingButton"
                        Style="{StaticResource HoverButtonStyle}"
                        BorderBrush="Transparent"
                    Background="Transparent"
                    Foreground="{DynamicResource MainForegroundColor}"
                    FontSize="{DynamicResource SettingsIconFontSize}"
                    Width="{DynamicResource IconButtonSize}" Height="{DynamicResource IconButtonSize}"
                    HorizontalAlignment="Right" VerticalAlignment="Center"
                    Margin="0,0,2,0"
                    FontFamily="Segoe MDL2 Assets"
                    Content="&#xE8D3;"
                    ToolTip="Ajustar a escala da fonte (acessibilidade)"
                    AutomationProperties.Name="Escala da fonte"
                />
                    <Popup Name="FontScalingPopup"
                    IsOpen="False"
                    AllowsTransparency="True"
                    PopupAnimation="Fade"
                    PlacementTarget="{Binding ElementName=FontScalingButton}" Placement="Bottom"
                    HorizontalAlignment="Right" VerticalAlignment="Top">
                    <Border Style="{StaticResource PopupBorderStyle}">
                        <StackPanel Background="Transparent" HorizontalAlignment="Stretch" VerticalAlignment="Stretch" MinWidth="220">
                            <TextBlock Text="Escala da fonte"
                                       FontSize="{DynamicResource ButtonFontSize}"
                                       Foreground="{DynamicResource MainForegroundColor}"
                                       HorizontalAlignment="Center"
                                       Margin="10,8,10,5"
                                       FontWeight="Bold"/>
                            <Separator Margin="5,0,5,5"/>
                            <StackPanel Orientation="Horizontal" Margin="10,5,10,10">
                                <TextBlock Text="Menor"
                                           FontSize="{DynamicResource ButtonFontSize}"
                                           Foreground="{DynamicResource MainForegroundColor}"
                                           VerticalAlignment="Center"
                                           Margin="0,0,10,0"/>
                                <Slider Name="FontScalingSlider"
                                        Minimum="0.75" Maximum="2.0"
                                        Value="1.0"
                                        TickFrequency="0.25"
                                        TickPlacement="BottomRight"
                                        IsSnapToTickEnabled="True"
                                        Width="120"
                                        VerticalAlignment="Center"
                                        AutomationProperties.Name="Escala da fonte"/>
                                <TextBlock Text="Maior"
                                           FontSize="{DynamicResource ButtonFontSize}"
                                           Foreground="{DynamicResource MainForegroundColor}"
                                           VerticalAlignment="Center"
                                           Margin="10,0,0,0"/>
                            </StackPanel>
                            <TextBlock Name="FontScalingValue"
                                       Text="100%"
                                       FontSize="{DynamicResource ButtonFontSize}"
                                       Foreground="{DynamicResource AccentColor}"
                                       HorizontalAlignment="Center"
                                       Margin="10,0,10,5"/>
                            <StackPanel Orientation="Horizontal" HorizontalAlignment="Center" Margin="10,0,10,10">
                                <Button Name="FontScalingResetButton"
                                        Content="Redefinir"
                                        Style="{StaticResource HoverButtonStyle}"
                                        Width="80" Height="28"
                                        Margin="5,0,5,0"/>
                                <Button Name="FontScalingApplyButton"
                                        Content="Aplicar"
                                        Style="{StaticResource HoverButtonStyle}"
                                        Width="80" Height="28"
                                        Margin="5,0,5,0"/>
                            </StackPanel>
                        </StackPanel>
                    </Border>
                </Popup>

                    <Button Name="SettingsButton"
                        Style="{StaticResource HoverButtonStyle}"
                        BorderBrush="Transparent"
                    Background="Transparent"
                    Foreground="{DynamicResource MainForegroundColor}"
                    FontSize="{DynamicResource SettingsIconFontSize}"
                    Width="{DynamicResource IconButtonSize}" Height="{DynamicResource IconButtonSize}"
                    HorizontalAlignment="Right" VerticalAlignment="Center"
                    Margin="0,0,2,0"
                    FontFamily="Segoe MDL2 Assets"
                    ToolTip="Configurações"
                    AutomationProperties.Name="Configurações"
                    Content="&#xE713;"/>
                    <Popup Name="SettingsPopup"
                    IsOpen="False"
                    AllowsTransparency="True"
                    PopupAnimation="Fade"
                    PlacementTarget="{Binding ElementName=SettingsButton}" Placement="Bottom"
                    HorizontalAlignment="Right" VerticalAlignment="Top">
                    <Border Style="{StaticResource PopupBorderStyle}">
                        <StackPanel Background="Transparent" HorizontalAlignment="Stretch" VerticalAlignment="Stretch" MinWidth="210">
                            <MenuItem FontSize="{DynamicResource ButtonFontSize}" Header="Importar configuração" Name="ImportMenuItem" Foreground="{DynamicResource MainForegroundColor}">
                                <MenuItem.ToolTip>
                                    <ToolTip Content="Importa uma configuração de um arquivo exportado."/>
                                </MenuItem.ToolTip>
                            </MenuItem>
                            <MenuItem FontSize="{DynamicResource ButtonFontSize}" Header="Exportar configuração" Name="ExportMenuItem" Foreground="{DynamicResource MainForegroundColor}">
                                <MenuItem.ToolTip>
                                    <ToolTip Content="Exporta os itens selecionados e copia o comando de execução para a área de transferência."/>
                                </MenuItem.ToolTip>
                            </MenuItem>
                            <Separator/>
                            <MenuItem FontSize="{DynamicResource ButtonFontSize}" Header="Sobre o Azor WinUtil" Name="AboutMenuItem" Foreground="{DynamicResource MainForegroundColor}"/>
                            <MenuItem FontSize="{DynamicResource ButtonFontSize}" Header="Documentação dos ajustes" Name="DocumentationMenuItem" Foreground="{DynamicResource MainForegroundColor}"/>
                            <MenuItem FontSize="{DynamicResource ButtonFontSize}" Header="Créditos" Name="SponsorMenuItem" Foreground="{DynamicResource MainForegroundColor}"/>
                        </StackPanel>
                    </Border>
                </Popup>

                    <Button
                        Content="&#xE921;"
                        Style="{StaticResource HoverButtonStyle}"
                        BorderThickness="0"
                        BorderBrush="Transparent"
                        Background="Transparent"
                        Width="{DynamicResource IconButtonSize}" Height="{DynamicResource IconButtonSize}"
                        HorizontalAlignment="Right" VerticalAlignment="Center"
                        Margin="0"
                        FontFamily="Segoe MDL2 Assets"
                        Foreground="{DynamicResource MainForegroundColor}"
                        FontSize="{DynamicResource CloseIconFontSize}"
                        ToolTip="Minimizar"
                        AutomationProperties.Name="Minimizar"
                        Name="WPFMinimizeButton" />
                    <Button
                        BorderThickness="0"
                        BorderBrush="Transparent"
                        Background="Transparent"
                        Width="{DynamicResource IconButtonSize}" Height="{DynamicResource IconButtonSize}"
                        HorizontalAlignment="Right" VerticalAlignment="Center"
                        Margin="0,0,0,0"
                        FontFamily="Segoe MDL2 Assets"
                        Foreground="{DynamicResource MainForegroundColor}"
                        FontSize="{DynamicResource CloseIconFontSize}"
                        Name="WPFMaximizeButton">
                        <Button.Style>
                            <Style TargetType="Button" BasedOn="{StaticResource HoverButtonStyle}">
                                <Setter Property="Content" Value="&#xE922;"/>
                                <Setter Property="ToolTip" Value="Maximizar"/>
                                <Setter Property="AutomationProperties.Name" Value="Maximizar"/>
                                <Style.Triggers>
                                    <DataTrigger Binding="{Binding WindowState, RelativeSource={RelativeSource AncestorType={x:Type Window}}}" Value="Maximized">
                                        <Setter Property="Content" Value="&#xE923;"/>
                                        <Setter Property="ToolTip" Value="Restaurar"/>
                                        <Setter Property="AutomationProperties.Name" Value="Restaurar"/>
                                    </DataTrigger>
                                </Style.Triggers>
                            </Style>
                        </Button.Style>
                    </Button>

                    <Button
                        Content="&#xE8BB;"
                        Style="{StaticResource CloseButtonStyle}"
                        BorderThickness="0"
                        BorderBrush="Transparent"
                        Background="Transparent"
                        Width="{DynamicResource IconButtonSize}" Height="{DynamicResource IconButtonSize}"
                        HorizontalAlignment="Right" VerticalAlignment="Center"
                        Margin="0"
                        FontFamily="Segoe MDL2 Assets"
                        Foreground="{DynamicResource MainForegroundColor}"
                        FontSize="{DynamicResource CloseIconFontSize}"
                        ToolTip="Fechar"
                        AutomationProperties.Name="Fechar"
                        Name="WPFCloseButton" />
                </StackPanel>
            </Grid>
        </Grid>

        <TabControl Name="WPFTabNav" Background="Transparent" Width="Auto" Height="Auto" BorderBrush="Transparent" BorderThickness="0" Grid.Row="2" Grid.Column="0" Padding="-1">
            <TabItem Header="Install" Visibility="Collapsed" Name="WPFTab1">
                <Grid Background="Transparent" >
                    <Grid.RowDefinitions>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="*"/>
                    </Grid.RowDefinitions>

                    <!-- Category filters. Click one to filter, ctrl click to combine several. -->
                    <WrapPanel Grid.Row="0" Orientation="Horizontal" Margin="5,5,5,5" Name="WPFSearchChips">
                        <TextBlock Text="&#xE71C;"
                                   FontFamily="Segoe MDL2 Assets"
                                   FontSize="{DynamicResource IconFontSize}"
                                   Foreground="{DynamicResource AccentColor}"
                                   Background="Transparent"
                                   VerticalAlignment="Center"
                                   Margin="10,0,10,0"
                                   ToolTip="Filtrar por categoria. Ctrl+clique para selecionar mais de uma."/>
                        <ToggleButton Name="WPFSearchChipAll"             Content="Todos"                 Style="{StaticResource FilterChipToggleStyle}" IsChecked="True"/>
                        <ToggleButton Name="WPFSearchChipBrowsers"        Content="Navegadores"           Style="{StaticResource FilterChipToggleStyle}"/>
                        <ToggleButton Name="WPFSearchChipCommunications"  Content="Comunicação"           Style="{StaticResource FilterChipToggleStyle}"/>
                        <ToggleButton Name="WPFSearchChipDocument"        Content="Documentos"            Style="{StaticResource FilterChipToggleStyle}"/>
                        <ToggleButton Name="WPFSearchChipGames"           Content="Jogos"                 Style="{StaticResource FilterChipToggleStyle}"/>
                        <ToggleButton Name="WPFSearchChipMicrosoftTools"  Content="Ferramentas Microsoft" Style="{StaticResource FilterChipToggleStyle}"/>
                        <ToggleButton Name="WPFSearchChipMultimediaTools" Content="Multimídia"            Style="{StaticResource FilterChipToggleStyle}"/>
                        <ToggleButton Name="WPFSearchChipProTools"        Content="Ferramentas Pro"       Style="{StaticResource FilterChipToggleStyle}"/>
                        <ToggleButton Name="WPFSearchChipUtilities"       Content="Utilitários"           Style="{StaticResource FilterChipToggleStyle}"/>
                    </WrapPanel>

                    <Grid Grid.Row="1" Margin="{DynamicResource TabContentMargin}">
                        <Grid.ColumnDefinitions>
                            <ColumnDefinition Width="Auto" />
                            <ColumnDefinition Width="*" />
                        </Grid.ColumnDefinitions>

                        <Grid Name="appscategory" Grid.Column="0" HorizontalAlignment="Stretch" VerticalAlignment="Stretch">
                        </Grid>

                        <Grid Name="appspanel" Grid.Column="1" HorizontalAlignment="Stretch" VerticalAlignment="Stretch">
                        </Grid>
                    </Grid>
                </Grid>
            </TabItem>
            <TabItem Header="Tweaks" Visibility="Collapsed" Name="WPFTab2">
                <Grid>
                    <!-- Main content area with a ScrollViewer -->
                    <Grid.RowDefinitions>
                        <RowDefinition Height="*" />
                        <RowDefinition Height="Auto" />
                    </Grid.RowDefinitions>

                    <ScrollViewer VerticalScrollBarVisibility="Auto" HorizontalScrollBarVisibility="Disabled" Grid.Row="0" Margin="{DynamicResource TabContentMargin}">
                        <Grid Background="Transparent">
                            <Grid.RowDefinitions>
                                <RowDefinition Height="Auto"/>
                                <RowDefinition Height="*"/>
                                <RowDefinition Height="Auto"/>
                            </Grid.RowDefinitions>

                            <StackPanel Background="Transparent" Orientation="Vertical" Grid.Row="0" Grid.Column="0" Grid.ColumnSpan="2" Margin="5">
                                <Label Content="Seleções recomendadas:" FontSize="{DynamicResource FontSize}" VerticalAlignment="Center" Margin="2"/>
                                <WrapPanel Orientation="Horizontal" HorizontalAlignment="Left" Margin="0,2,0,0">
                                    <Button Name="WPFstandard" Content=" Padrão " Margin="2" Width="Auto" MinWidth="140" Height="{DynamicResource ButtonHeight}" ToolTip="Ajustes equilibrados para a maioria dos usuários"/>
                                    <Button Name="WPFGaming" Content=" Jogos (Azor) " Margin="2" Width="Auto" MinWidth="140" Height="{DynamicResource ButtonHeight}" ToolTip="Seleção focada em jogos: desliga a gravação em segundo plano (Game DVR) e reduz apps, serviços e telemetria em segundo plano, sem mexer em nada que os anti-cheats exigem"/>
                                    <Button Name="WPFAzorUltra" Content=" Super Agressivo " Margin="2" Width="Auto" MinWidth="140" Height="{DynamicResource ButtonHeight}" Foreground="{DynamicResource WarningColor}" ToolTip="Marca tudo de uma vez: desliga e remove Copilot, Recall e IA do Windows, corta telemetria e marca os apps de bloatware. Pede confirmação e nada é aplicado antes de você clicar em Executar Ajustes"/>
                                    <Button Name="WPFClearTweaksSelection" Content=" Limpar " Margin="2" Width="Auto" MinWidth="140" Height="{DynamicResource ButtonHeight}"/>
                                    <Button Name="WPFGetInstalledTweaks" Content=" Detectar Ajustes Aplicados " Margin="2" Width="Auto" MinWidth="140" Height="{DynamicResource ButtonHeight}"/>
                                    <Button Name="WPFAppxRemoval" Content=" Remover AppX " Margin="2" Width="Auto" MinWidth="140" Height="{DynamicResource ButtonHeight}"/>
                                </WrapPanel>
                            </StackPanel>

                            <Grid Name="tweakspanel" Grid.Row="1">
                                <!-- Your tweakspanel content goes here -->
                            </Grid>

                            <Border Grid.ColumnSpan="2" Grid.Row="2" Grid.Column="0" Style="{StaticResource BorderStyle}">
                                <StackPanel Background="Transparent" Orientation="Horizontal" HorizontalAlignment="Left">
                                    <TextBlock Padding="10" TextWrapping="Wrap" Foreground="{DynamicResource MutedForegroundColor}">
                                        Dica: passe o mouse sobre os itens para ver a descrição. Muitos destes ajustes modificam o sistema profundamente, então tenha cuidado.
                                        <LineBreak/>As seleções recomendadas são para usuários comuns. Se estiver em dúvida, NÃO marque mais nada!
                                    </TextBlock>
                                </StackPanel>
                            </Border>
                        </Grid>
                    </ScrollViewer>
                    <Border Grid.Row="1" Background="{DynamicResource CardBackgroundColor}" BorderBrush="{DynamicResource BorderColor}" BorderThickness="1" CornerRadius="10" HorizontalAlignment="Stretch" Padding="10" Margin="5,0,5,5">
                        <WrapPanel Orientation="Horizontal" HorizontalAlignment="Left" VerticalAlignment="Center" Grid.Column="0">
                            <Button Name="WPFTweaksbutton" Content="Executar Ajustes" Style="{StaticResource AccentButtonStyle}" Margin="5" Width="{DynamicResource ButtonWidth}" Height="{DynamicResource ButtonHeight}"/>
                            <Button Name="WPFUndoall" Content="Desfazer Ajustes Selecionados" Margin="5" Width="{DynamicResource ButtonWidth}" Height="{DynamicResource ButtonHeight}"/>
                        </WrapPanel>
                    </Border>
                </Grid>
            </TabItem>
            <TabItem Header="Config" Visibility="Collapsed" Name="WPFTab3">
                <ScrollViewer VerticalScrollBarVisibility="Auto" HorizontalScrollBarVisibility="Auto" Margin="{DynamicResource TabContentMargin}">
                    <Grid Name="featurespanel" Grid.Row="1" Background="Transparent">
                    </Grid>
                </ScrollViewer>
            </TabItem>
            <TabItem Header="AppX" Visibility="Collapsed" Name="WPFTab6">
                <Grid>
                    <Grid.RowDefinitions>
                        <RowDefinition Height="*" />
                        <RowDefinition Height="Auto" />
                    </Grid.RowDefinitions>

                    <ScrollViewer VerticalScrollBarVisibility="Auto" HorizontalScrollBarVisibility="Disabled" Grid.Row="0" Margin="{DynamicResource TabContentMargin}">
                        <Grid Background="Transparent">
                            <Grid.RowDefinitions>
                                <RowDefinition Height="Auto"/>
                                <RowDefinition Height="*"/>
                                <RowDefinition Height="Auto"/>
                            </Grid.RowDefinitions>

                            <StackPanel Background="Transparent" Orientation="Vertical" Grid.Row="0" Grid.Column="0" Margin="5">
                                <Label Content="Seleções:" FontSize="{DynamicResource FontSize}" VerticalAlignment="Center" Margin="2"/>
                                <StackPanel Orientation="Horizontal" HorizontalAlignment="Left" Margin="0,2,0,0">
                                    <Button Name="WPFDefaultAppxSelection" Content=" Padrão " Margin="2" Width="{DynamicResource ButtonWidth}" Height="{DynamicResource ButtonHeight}"/>
                                    <Button Name="WPFGetInstalledAppx" Content=" Detectar Instalados " Margin="2" Width="{DynamicResource ButtonWidth}" Height="{DynamicResource ButtonHeight}"/>
                                    <Button Name="WPFSelectAllAppx" Content=" Selecionar Tudo " Margin="2" Width="{DynamicResource ButtonWidth}" Height="{DynamicResource ButtonHeight}"/>
                                    <Button Name="WPFClearAppxSelection" Content=" Limpar Seleção " Margin="2" Width="{DynamicResource ButtonWidth}" Height="{DynamicResource ButtonHeight}"/>
                                </StackPanel>
                            </StackPanel>

                            <Grid Name="appxpanel" Grid.Row="1">
                            </Grid>

                            <Border Grid.Row="2" Style="{StaticResource BorderStyle}" Margin="5,15,5,5">
                                <StackPanel Background="Transparent" Orientation="Horizontal" HorizontalAlignment="Left">
                                    <TextBlock Padding="10" TextWrapping="Wrap" Foreground="{DynamicResource MutedForegroundColor}">
                                        Observação: selecione os pacotes AppX do Windows que deseja instalar ou remover.
                                        <LineBreak/>Instalar Selecionados registra um manifesto local quando disponível e, se não houver, recorre à Microsoft Store.
                                        <LineBreak/>Remover Selecionados remove os pacotes do usuário atual e de todos os novos perfis de usuário.
                                    </TextBlock>
                                </StackPanel>
                            </Border>
                        </Grid>
                    </ScrollViewer>

                    <Border Grid.Row="1" Background="{DynamicResource CardBackgroundColor}" BorderBrush="{DynamicResource BorderColor}" BorderThickness="1" CornerRadius="10" HorizontalAlignment="Stretch" Padding="10" Margin="5,0,5,5">
                        <WrapPanel Orientation="Horizontal" HorizontalAlignment="Left" VerticalAlignment="Center">
                            <Button Name="WPFBackToTweaks" Content="Voltar aos Ajustes" Margin="5" Width="{DynamicResource ButtonWidth}" Height="{DynamicResource ButtonHeight}"/>
                            <Button Name="WPFInstallSelectedAppx" Content="Instalar Selecionados" Margin="5" Width="{DynamicResource ButtonWidth}" Height="{DynamicResource ButtonHeight}"/>
                            <Button Name="WPFRemoveSelectedAppx" Content="Remover Selecionados" Style="{StaticResource AccentButtonStyle}" Margin="5" Width="{DynamicResource ButtonWidth}" Height="{DynamicResource ButtonHeight}"/>
                        </WrapPanel>
                    </Border>
                </Grid>
            </TabItem>
            <TabItem Header="Dashboard" Visibility="Collapsed" Name="WPFTab7" IsSelected="True">
                <ScrollViewer VerticalScrollBarVisibility="Auto" HorizontalScrollBarVisibility="Disabled" Margin="{DynamicResource TabContentMargin}">
                    <Grid Name="dashboardpanel" Background="Transparent" Margin="2,0,2,4">
                        <Grid.RowDefinitions>
                            <RowDefinition Height="Auto"/>
                            <RowDefinition Height="Auto"/>
                            <RowDefinition Height="Auto"/>
                            <RowDefinition Height="Auto"/>
                            <RowDefinition Height="Auto"/>
                        </Grid.RowDefinitions>

                        <!-- Hero -->
                        <Border Grid.Row="0" CornerRadius="16" Margin="6,4,6,6" Padding="24,20" BorderThickness="1" BorderBrush="{DynamicResource BorderColor}">
                            <Border.Background>
                                <LinearGradientBrush StartPoint="0,0" EndPoint="1,1">
                                    <GradientStop Color="{DynamicResource CHeroStartColor}" Offset="0"/>
                                    <GradientStop Color="{DynamicResource CHeroEndColor}" Offset="0.8"/>
                                </LinearGradientBrush>
                            </Border.Background>
                            <Grid>
                                <Grid.ColumnDefinitions>
                                    <ColumnDefinition Width="Auto"/>
                                    <ColumnDefinition Width="*"/>
                                    <ColumnDefinition Width="Auto"/>
                                </Grid.ColumnDefinitions>
                                <Border Name="WPFDashboardLogo" Grid.Column="0" Width="92" Height="92" VerticalAlignment="Center">
                                    <Border.Effect>
                                        <DropShadowEffect Color="{DynamicResource CAccentColor}" BlurRadius="30" ShadowDepth="0" Opacity="0.6"/>
                                    </Border.Effect>
                                </Border>
                                <StackPanel Grid.Column="1" Margin="22,0,16,0" VerticalAlignment="Center">
                                    <TextBlock Name="WPFDashboardGreeting" Text="Bem-vindo" FontSize="13" Foreground="{DynamicResource MutedForegroundColor}"/>
                                    <TextBlock Text="AZOR WINUTIL" FontFamily="{DynamicResource HeaderFontFamily}" FontSize="{DynamicResource DashboardTitleFontSize}" Foreground="{StaticResource AzorRoseGradientBrush}" Margin="0,0,0,2"/>
                                    <TextBlock Text="Desempenho divino. Estilo Rosé." FontSize="15" Foreground="{DynamicResource MainForegroundColor}"/>
                                    <WrapPanel Margin="0,12,0,0">
                                        <Border Style="{StaticResource DashboardBadgeStyle}">
                                            <StackPanel Orientation="Horizontal">
                                                <TextBlock Text="&#xEA18;" FontFamily="Segoe MDL2 Assets" FontSize="11" VerticalAlignment="Center" Margin="0,0,6,0" Foreground="{DynamicResource SuccessColor}"/>
                                                <TextBlock Name="WPFDashboardAdminBadge" Text="Verificando..." FontSize="11" VerticalAlignment="Center" Foreground="{DynamicResource MainForegroundColor}"/>
                                            </StackPanel>
                                        </Border>
                                        <Border Style="{StaticResource DashboardBadgeStyle}">
                                            <StackPanel Orientation="Horizontal">
                                                <TextBlock Text="&#xE774;" FontFamily="Segoe MDL2 Assets" FontSize="11" VerticalAlignment="Center" Margin="0,0,6,0" Foreground="{DynamicResource AccentColor}"/>
                                                <TextBlock Name="WPFDashboardNetBadge" Text="Verificando..." FontSize="11" VerticalAlignment="Center" Foreground="{DynamicResource MainForegroundColor}"/>
                                            </StackPanel>
                                        </Border>
                                        <Border Style="{StaticResource DashboardBadgeStyle}">
                                            <StackPanel Orientation="Horizontal">
                                                <TextBlock Text="&#xE7F4;" FontFamily="Segoe MDL2 Assets" FontSize="11" VerticalAlignment="Center" Margin="0,0,6,0" Foreground="{DynamicResource AccentColor}"/>
                                                <TextBlock Name="WPFDashboardMachineBadge" Text="..." FontSize="11" VerticalAlignment="Center" Foreground="{DynamicResource MainForegroundColor}"/>
                                            </StackPanel>
                                        </Border>
                                        <Border Style="{StaticResource DashboardBadgeStyle}">
                                            <StackPanel Orientation="Horizontal">
                                                <TextBlock Text="&#xECAD;" FontFamily="Segoe MDL2 Assets" FontSize="11" VerticalAlignment="Center" Margin="0,0,6,0" Foreground="{DynamicResource AccentColor}"/>
                                                <TextBlock Name="WPFDashboardVersion" Text="Versão" FontSize="11" VerticalAlignment="Center" Foreground="{DynamicResource MainForegroundColor}"/>
                                            </StackPanel>
                                        </Border>
                                    </WrapPanel>
                                </StackPanel>
                                <StackPanel Grid.Column="2" VerticalAlignment="Center" Width="250">
                                    <Button Name="WPFQuickOptimize" Style="{StaticResource AccentButtonStyle}" Width="250" Height="48" FontSize="15"
                                            ToolTip="Aplica a seleção recomendada (Padrão) após criar um ponto de restauração">
                                        <StackPanel Orientation="Horizontal">
                                            <TextBlock Text="&#xE945;" FontFamily="Segoe MDL2 Assets" FontSize="17" VerticalAlignment="Center" Margin="0,0,10,0" Foreground="White" Background="Transparent"/>
                                            <TextBlock Text="Otimização Rápida" FontSize="15" VerticalAlignment="Center" Foreground="White" Background="Transparent"/>
                                        </StackPanel>
                                    </Button>
                                    <TextBlock Text="Seleção Padrão + ponto de restauração" HorizontalAlignment="Center" Margin="0,8,0,0" FontSize="11" Foreground="{DynamicResource MutedForegroundColor}"/>
                                </StackPanel>
                            </Grid>
                        </Border>

                        <!-- Game compatibility alert: shown only when the check finds something the user can act on -->
                        <Border Name="WPFDashboardAlert" Grid.Row="1" Visibility="Collapsed" Style="{StaticResource DashboardCardStyle}" BorderBrush="{DynamicResource WarningColor}" Padding="16,10">
                            <DockPanel LastChildFill="True">
                                <Button Name="WPFDashboardAlertFix" DockPanel.Dock="Right" Style="{StaticResource AccentButtonStyle}" Content="Ver e corrigir" Width="Auto" Height="34" Padding="18,0" VerticalAlignment="Center" ToolTip="Abre o Checkup para Jogos, que mostra cada item e corrige o que é de software"/>
                                <TextBlock DockPanel.Dock="Left" Text="&#xE7BA;" FontFamily="Segoe MDL2 Assets" FontSize="18" Foreground="{DynamicResource WarningColor}" VerticalAlignment="Center" Margin="0,0,12,0"/>
                                <StackPanel VerticalAlignment="Center" Margin="0,0,12,0">
                                    <TextBlock Name="WPFDashboardAlertTitle" Text="" Style="{StaticResource CardHeaderStyle}" FontSize="14"/>
                                    <TextBlock Name="WPFDashboardAlertText" Text="" Style="{StaticResource CardDetailStyle}" Margin="0,2,0,0"/>
                                </StackPanel>
                            </DockPanel>
                        </Border>

                        <!-- Live metrics -->
                        <UniformGrid Grid.Row="2" Columns="4">
                            <Border Style="{StaticResource DashboardCardStyle}">
                                <StackPanel>
                                    <StackPanel Orientation="Horizontal">
                                        <TextBlock Text="&#xE950;" Style="{StaticResource CardIconStyle}"/>
                                        <TextBlock Text="Processador" Style="{StaticResource CardTitleStyle}" Margin="8,0,0,0"/>
                                    </StackPanel>
                                    <TextBlock Name="WPFDashboardCpuValue" Text="--" Style="{StaticResource CardValueStyle}" Margin="0,10,0,8"/>
                                    <ProgressBar Name="WPFDashboardCpuBar" Height="8" Minimum="0" Maximum="100" Value="0" Style="{StaticResource RoundedProgressBarStyle}"/>
                                    <TextBlock Name="WPFDashboardCpuDetail" Text="Carregando..." Style="{StaticResource CardDetailStyle}" Margin="0,9,0,0"/>
                                    <TextBlock Name="WPFDashboardCpuCoresDetail" Text="" Style="{StaticResource CardDetailStyle}" Margin="0,3,0,0"/>
                                </StackPanel>
                            </Border>
                            <Border Style="{StaticResource DashboardCardStyle}">
                                <StackPanel>
                                    <StackPanel Orientation="Horizontal">
                                        <TextBlock Text="&#xE964;" Style="{StaticResource CardIconStyle}"/>
                                        <TextBlock Text="Memória" Style="{StaticResource CardTitleStyle}" Margin="8,0,0,0"/>
                                    </StackPanel>
                                    <TextBlock Name="WPFDashboardRamValue" Text="--" Style="{StaticResource CardValueStyle}" Margin="0,10,0,8"/>
                                    <ProgressBar Name="WPFDashboardRamBar" Height="8" Minimum="0" Maximum="100" Value="0" Style="{StaticResource RoundedProgressBarStyle}"/>
                                    <TextBlock Name="WPFDashboardRamDetail" Text="Carregando..." Style="{StaticResource CardDetailStyle}" Margin="0,9,0,0"/>
                                </StackPanel>
                            </Border>
                            <Border Style="{StaticResource DashboardCardStyle}">
                                <StackPanel>
                                    <StackPanel Orientation="Horizontal">
                                        <TextBlock Text="&#xEDA2;" Style="{StaticResource CardIconStyle}"/>
                                        <TextBlock Text="Disco do sistema" Style="{StaticResource CardTitleStyle}" Margin="8,0,0,0"/>
                                    </StackPanel>
                                    <TextBlock Name="WPFDashboardDiskValue" Text="--" Style="{StaticResource CardValueStyle}" Margin="0,10,0,8"/>
                                    <ProgressBar Name="WPFDashboardDiskBar" Height="8" Minimum="0" Maximum="100" Value="0" Style="{StaticResource RoundedProgressBarStyle}"/>
                                    <TextBlock Name="WPFDashboardDiskDetail" Text="Carregando..." Style="{StaticResource CardDetailStyle}" Margin="0,9,0,0"/>
                                </StackPanel>
                            </Border>
                            <Border Style="{StaticResource DashboardCardStyle}">
                                <StackPanel>
                                    <StackPanel Orientation="Horizontal">
                                        <TextBlock Text="&#xE7F4;" Style="{StaticResource CardIconStyle}"/>
                                        <TextBlock Text="Sistema" Style="{StaticResource CardTitleStyle}" Margin="8,0,0,0"/>
                                    </StackPanel>
                                    <TextBlock Name="WPFDashboardOsValue" Text="Windows" Style="{StaticResource CardValueStyle}" FontSize="20" Margin="0,13,0,4"/>
                                    <TextBlock Name="WPFDashboardOsDetail" Text="Carregando..." Style="{StaticResource CardDetailStyle}"/>
                                    <TextBlock Name="WPFDashboardGpuDetail" Text="" Style="{StaticResource CardDetailStyle}" Margin="0,3,0,0"/>
                                    <TextBlock Name="WPFDashboardUptimeDetail" Text="" Style="{StaticResource CardDetailStyle}" Margin="0,3,0,0"/>
                                </StackPanel>
                            </Border>
                        </UniformGrid>

                        <!-- Quick actions and startup apps -->
                        <Grid Grid.Row="3">
                            <Grid.ColumnDefinitions>
                                <ColumnDefinition Width="11*"/>
                                <ColumnDefinition Width="10*"/>
                            </Grid.ColumnDefinitions>

                            <Border Grid.Column="0" Style="{StaticResource DashboardCardStyle}">
                                <StackPanel>
                                    <TextBlock Text="Ações rápidas" Style="{StaticResource CardHeaderStyle}"/>
                                    <TextBlock Text="Ferramentas de um clique para deixar o PC afiado." Style="{StaticResource CardDetailStyle}" Margin="0,2,0,10"/>
                                    <UniformGrid Columns="2">
                                        <Button Name="WPFQuickCleanup" Style="{StaticResource QuickActionButtonStyle}">
                                            <StackPanel Orientation="Horizontal">
                                                <TextBlock Text="&#xE74D;" Style="{StaticResource QuickActionIconStyle}"/>
                                                <StackPanel Margin="10,0,0,0" VerticalAlignment="Center">
                                                    <TextBlock Text="Limpeza Rápida" Style="{StaticResource QuickActionTitleStyle}"/>
                                                    <TextBlock Text="Temporários, caches e relatórios" Style="{StaticResource QuickActionSubtitleStyle}"/>
                                                </StackPanel>
                                            </StackPanel>
                                        </Button>
                                        <Button Name="WPFQuickRestorePoint" Style="{StaticResource QuickActionButtonStyle}">
                                            <StackPanel Orientation="Horizontal">
                                                <TextBlock Text="&#xE777;" Style="{StaticResource QuickActionIconStyle}"/>
                                                <StackPanel Margin="10,0,0,0" VerticalAlignment="Center">
                                                    <TextBlock Text="Ponto de Restauração" Style="{StaticResource QuickActionTitleStyle}"/>
                                                    <TextBlock Text="Crie um backup antes de mudar" Style="{StaticResource QuickActionSubtitleStyle}"/>
                                                </StackPanel>
                                            </StackPanel>
                                        </Button>
                                        <Button Name="WPFQuickGamingPreset" Style="{StaticResource QuickActionButtonStyle}">
                                            <StackPanel Orientation="Horizontal">
                                                <TextBlock Text="&#xE7FC;" Style="{StaticResource QuickActionIconStyle}"/>
                                                <StackPanel Margin="10,0,0,0" VerticalAlignment="Center">
                                                    <TextBlock Text="Modo Jogo Azor" Style="{StaticResource QuickActionTitleStyle}"/>
                                                    <TextBlock Text="Seleciona os ajustes para jogos" Style="{StaticResource QuickActionSubtitleStyle}"/>
                                                </StackPanel>
                                            </StackPanel>
                                        </Button>
                                        <Button Name="WPFQuickUltimatePower" Style="{StaticResource QuickActionButtonStyle}">
                                            <StackPanel Orientation="Horizontal">
                                                <TextBlock Text="&#xE7E8;" Style="{StaticResource QuickActionIconStyle}"/>
                                                <StackPanel Margin="10,0,0,0" VerticalAlignment="Center">
                                                    <TextBlock Text="Desempenho Máximo" Style="{StaticResource QuickActionTitleStyle}"/>
                                                    <TextBlock Text="Plano de energia Ultimate (desktop)" Style="{StaticResource QuickActionSubtitleStyle}"/>
                                                </StackPanel>
                                            </StackPanel>
                                        </Button>
                                        <Button Name="WPFQuickUpgradeApps" Style="{StaticResource QuickActionButtonStyle}">
                                            <StackPanel Orientation="Horizontal">
                                                <TextBlock Text="&#xE896;" Style="{StaticResource QuickActionIconStyle}"/>
                                                <StackPanel Margin="10,0,0,0" VerticalAlignment="Center">
                                                    <TextBlock Text="Atualizar Programas" Style="{StaticResource QuickActionTitleStyle}"/>
                                                    <TextBlock Text="Atualiza todos os apps via WinGet" Style="{StaticResource QuickActionSubtitleStyle}"/>
                                                </StackPanel>
                                            </StackPanel>
                                        </Button>
                                        <Button Name="WPFQuickRepair" Style="{StaticResource QuickActionButtonStyle}">
                                            <StackPanel Orientation="Horizontal">
                                                <TextBlock Text="&#xE90F;" Style="{StaticResource QuickActionIconStyle}"/>
                                                <StackPanel Margin="10,0,0,0" VerticalAlignment="Center">
                                                    <TextBlock Text="Reparar Windows" Style="{StaticResource QuickActionTitleStyle}"/>
                                                    <TextBlock Text="CHKDSK, SFC e DISM" Style="{StaticResource QuickActionSubtitleStyle}"/>
                                                </StackPanel>
                                            </StackPanel>
                                        </Button>
                                        <Button Name="WPFQuickGameCompat" Style="{StaticResource QuickActionButtonStyle}">
                                            <StackPanel Orientation="Horizontal">
                                                <TextBlock Text="&#xE83D;" Style="{StaticResource QuickActionIconStyle}"/>
                                                <StackPanel Margin="10,0,0,0" VerticalAlignment="Center">
                                                    <TextBlock Text="Checkup para Jogos" Style="{StaticResource QuickActionTitleStyle}"/>
                                                    <TextBlock Text="Anti-cheat, monitor, driver e Windows" Style="{StaticResource QuickActionSubtitleStyle}"/>
                                                </StackPanel>
                                            </StackPanel>
                                        </Button>
                                        <Button Name="WPFQuickOpenLogs" Style="{StaticResource QuickActionButtonStyle}">
                                            <StackPanel Orientation="Horizontal">
                                                <TextBlock Text="&#xE838;" Style="{StaticResource QuickActionIconStyle}"/>
                                                <StackPanel Margin="10,0,0,0" VerticalAlignment="Center">
                                                    <TextBlock Text="Registros do Azor" Style="{StaticResource QuickActionTitleStyle}"/>
                                                    <TextBlock Text="Abre a pasta de logs" Style="{StaticResource QuickActionSubtitleStyle}"/>
                                                </StackPanel>
                                            </StackPanel>
                                        </Button>
                                        <Button Name="WPFQuickAzorRate" Style="{StaticResource QuickActionButtonStyle}">
                                            <StackPanel Orientation="Horizontal">
                                                <TextBlock Text="&#xE962;" Style="{StaticResource QuickActionIconStyle}"/>
                                                <StackPanel Margin="10,0,0,0" VerticalAlignment="Center">
                                                    <TextBlock Text="AZOR Rate" Style="{StaticResource QuickActionTitleStyle}"/>
                                                    <TextBlock Text="Hz real de mouse, teclado e controle" Style="{StaticResource QuickActionSubtitleStyle}"/>
                                                </StackPanel>
                                            </StackPanel>
                                        </Button>
                                        <Button Name="WPFQuickAzorOptimization" Style="{StaticResource QuickActionButtonStyle}">
                                            <StackPanel Orientation="Horizontal">
                                                <TextBlock Text="&#xE945;" Style="{StaticResource QuickActionIconStyle}"/>
                                                <StackPanel Margin="10,0,0,0" VerticalAlignment="Center">
                                                    <TextBlock Text="AZOR Optimization" Style="{StaticResource QuickActionTitleStyle}"/>
                                                    <TextBlock Text="BOOST, Input Lab e BIOS Copiloto" Style="{StaticResource QuickActionSubtitleStyle}"/>
                                                </StackPanel>
                                            </StackPanel>
                                        </Button>
                                    </UniformGrid>
                                </StackPanel>
                            </Border>

                            <Border Grid.Column="1" Style="{StaticResource DashboardCardStyle}">
                                <Grid>
                                    <Grid.RowDefinitions>
                                        <RowDefinition Height="Auto"/>
                                        <RowDefinition Height="Auto"/>
                                        <RowDefinition Height="*"/>
                                        <RowDefinition Height="Auto"/>
                                    </Grid.RowDefinitions>
                                    <DockPanel Grid.Row="0" LastChildFill="True">
                                        <Button Name="WPFStartupAppsRefresh" DockPanel.Dock="Right"
                                                Style="{StaticResource HoverButtonStyle}"
                                                FontFamily="Segoe MDL2 Assets" FontSize="14"
                                                Content="&#xE72C;" Width="32" Height="32"
                                                ToolTip="Atualizar a lista"
                                                AutomationProperties.Name="Atualizar a lista de inicialização"/>
                                        <TextBlock Text="Inicialização do Windows" Style="{StaticResource CardHeaderStyle}"/>
                                    </DockPanel>
                                    <TextBlock Grid.Row="1" Name="WPFStartupAppsSummary" Text="Carregando programas..." Style="{StaticResource CardDetailStyle}" Margin="0,0,0,10"/>
                                    <ScrollViewer Grid.Row="2" VerticalScrollBarVisibility="Auto" HorizontalScrollBarVisibility="Disabled" MaxHeight="268">
                                        <StackPanel Name="WPFStartupAppsList" Margin="0,0,6,0"/>
                                    </ScrollViewer>
                                    <TextBlock Grid.Row="3" TextWrapping="Wrap" TextTrimming="None" Style="{StaticResource CardDetailStyle}" Margin="0,10,0,0"
                                               Text="Desativar um item só impede que ele abra junto com o Windows. Nada é desinstalado (é o mesmo método do Gerenciador de Tarefas)."/>
                                </Grid>
                            </Border>
                        </Grid>

                        <TextBlock Grid.Row="4" HorizontalAlignment="Center" Margin="0,4,0,8" Style="{StaticResource CardDetailStyle}"
                                   Text="Azor WinUtil  •  baseado no WinUtil de Chris Titus Tech (licença MIT)"/>
                    </Grid>
                </ScrollViewer>
            </TabItem>
        </TabControl>

        <!-- Window-level progress indicator - visible regardless of active tab -->
        <Border Name="WPFTweaksProgressBar" Grid.Row="3" Background="{DynamicResource CardBackgroundColor}" BorderBrush="{DynamicResource BorderColor}" BorderThickness="0,1,0,0" Visibility="Collapsed" Padding="12,7">
            <StackPanel Orientation="Vertical">
                <TextBlock Name="WPFTweaksProgressLabel" Text="" Foreground="{DynamicResource MainForegroundColor}" FontSize="13" Background="Transparent" Margin="0,0,0,5"/>
                <ProgressBar Name="WPFTweaksProgressValue" Height="7" Minimum="0" Maximum="100" Value="0" Style="{StaticResource RoundedProgressBarStyle}"/>
            </StackPanel>
        </Border>
    </Grid>
</Window>

'@
# Azor Companion: aviso de deteccao do AzorOptimization e primeiro recado para ele.
$sync.azorOptimization = Read-AzorOptimization
if ($sync.azorOptimization) {
    $azorN = 0; try { $azorN = @($sync.azorOptimization.activeTweaks).Count } catch { }
    Write-Host ""
    Write-Host "  AZOR OPTIMIZATION detectado: $azorN ajuste(s) ja aplicado(s) por ele nesta maquina." -ForegroundColor Magenta
    Write-Host "  O WinUtil respeita o que ele fez. Aqui e o lado avancado: instalar programas," -ForegroundColor DarkGray
    Write-Host "  remover bloatware e tweaks profundos." -ForegroundColor DarkGray
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "  Dica: o AzorOptimization faz o ajuste seguro de um clique. Rode ele primeiro;" -ForegroundColor DarkGray
    Write-Host "  o WinUtil complementa com o que e avancado." -ForegroundColor DarkGray
    Write-Host ""
}
Write-AzorWinUtilState -LastAction "Aberto"

Write-Host @"
    _      _____   ___    ____
   / \    |__  /  / _ \  |  _ \
  / _ \     / /  | | | | | |_) |
 / ___ \   / /_  | |_| | |  _ <
/_/   \_\ /____|  \___/  |_| \_\

========== Azor WinUtil ==========
 Otimização do Windows no estilo Rosé
 Baseado no WinUtil de Chris Titus Tech
"@ -ForegroundColor Magenta

# Load the configuration files

$sync.configs.applicationsHashtable = @{}
$sync.configs.applications.PSObject.Properties | ForEach-Object {
    $sync.configs.applicationsHashtable[$_.Name] = $_.Value
}

$sync.configs.appxHashtable = @{}
$sync.configs.appx.PSObject.Properties | ForEach-Object {
    $sync.configs.appxHashtable[$_.Name] = $_.Value
}
$sync.preferences.theme = "Dark"
$sync.preferences.packagemanager = "Winget"

if ($Preset) {
    Initialize-WinUtilRunspacePool | Out-Null

    # Selects the tweaks from $Preset varible
    Update-WinUtilSelections -flatJson $sync.configs.preset.$Preset

    # Run tweaks that were selected by Update-WinUtilSelections
    Invoke-WinUtilAutoRun

    # Cleanup and exit
    Close-WinUtilRunspacePool
    [System.GC]::Collect()
    Stop-Transcript
    return
}

if ($Config) {
    Initialize-WinUtilRunspacePool | Out-Null

    Invoke-WPFImpex -type "import" -Config $Config

    Invoke-WinUtilAutoRun

    # Cleanup and exit
    Close-WinUtilRunspacePool
    [System.GC]::Collect()
    Stop-Transcript
    return
}

[void][System.Reflection.Assembly]::LoadWithPartialName('presentationframework')
[xml]$XAML = $inputXML

# Read the XAML file
$readerOperationSuccessful = $false # There's more cases of failure then success.
$reader = (New-Object System.Xml.XmlNodeReader $xaml)
try {
    $sync["Form"] = [Windows.Markup.XamlReader]::Load( $reader )
    $readerOperationSuccessful = $true
} catch [System.Management.Automation.MethodInvocationException] {
    Write-Host "Encontramos um problema no código XAML. Verifique a sintaxe deste controle..." -ForegroundColor Red
    Write-Host $error[0].Exception.Message -ForegroundColor Red

    If ($error[0].Exception.Message -like "*button*") {
        write-Host "Garanta que o &lt;button no `$inputXML NÃO tenha a propriedade Click=ButtonClick. O PowerShell não consegue lidar com isso`n`n`n`n" -ForegroundColor Red
    }
} catch {
    Write-Host "Não foi possível carregar o Windows.Markup.XamlReader. Verifique a sintaxe e se o .NET está instalado." -ForegroundColor Red
}

if (-NOT ($readerOperationSuccessful)) {
    Write-Host "Falha ao interpretar o XAML com o método Load do Windows.Markup.XamlReader." -ForegroundColor Red
    Write-Host "Encerrando o Azor WinUtil..." -ForegroundColor Red
    Close-WinUtilRunspacePool
    [System.GC]::Collect()
    exit 1
}

# Setup the Window to follow listen for windows Theme Change events and update the winutil theme
# throttle logic needed, because windows seems to send more than one theme change event per change
$lastThemeChangeTime = [datetime]::MinValue
$debounceInterval = [timespan]::FromSeconds(2)
$sync.Form.Add_Loaded({
    $interopHelper = New-Object System.Windows.Interop.WindowInteropHelper $sync.Form
    $hwndSource = [System.Windows.Interop.HwndSource]::FromHwnd($interopHelper.Handle)
    $hwndSource.AddHook({
        param (
            [System.IntPtr]$hwnd,
            [int]$msg,
            [System.IntPtr]$wParam,
            [System.IntPtr]$lParam,
            [ref]$handled
        )
        $null = $hwnd, $wParam, $lParam
        # Check for the Event WM_SETTINGCHANGE (0x1001A) and validate that Button shows the icon for "Auto" => [char]0xF08C
        if (($msg -eq 0x001A) -and $sync.ThemeButton.Content -eq [char]0xF08C) {
            $currentTime = [datetime]::Now
            if ($currentTime - $lastThemeChangeTime -gt $debounceInterval) {
                Invoke-WinutilThemeChange -theme "Auto"
                $script:lastThemeChangeTime = $currentTime
                $handled = $true
            }
        }
        return 0
    })
})

Invoke-WinutilThemeChange -theme $sync.preferences.theme


# Build the Install tab before first paint (its app entries render in background batches).
# Every other tab, including the Dashboard shown at startup, initializes on first activation.
$sync.InitializedTabs = @{}
Initialize-WinUtilTabContent -TabName "Install"

#===========================================================================
# Store Form Objects In PowerShell
#===========================================================================

$xaml.SelectNodes("//*[@Name]") | ForEach-Object {$sync["$("$($psitem.Name)")"] = $sync["Form"].FindName($psitem.Name)}

$sync.ChocoRadioButton.Add_Checked({
    $sync.preferences.packagemanager = "Choco"
})
$sync.WingetRadioButton.Add_Checked({
    $sync.preferences.packagemanager = "Winget"
})

switch ($sync.preferences.packagemanager) {
    "Choco" {$sync.ChocoRadioButton.IsChecked = $true; break}
    "Winget" {$sync.WingetRadioButton.IsChecked = $true; break}
}

$sync.keys | ForEach-Object {
    if($sync.$psitem) {
        if($($sync["$psitem"].GetType() | Select-Object -ExpandProperty Name) -eq "ToggleButton") {
            if ($sync.Buttons -notcontains $psitem) {
                $sync["$psitem"].Add_Click({
                    [System.Object]$Sender = $args[0]
                    Invoke-WPFButton $Sender.name
                })
                $sync.Buttons.Add($psitem) | Out-Null
            }
        }

        if($($sync["$psitem"].GetType() | Select-Object -ExpandProperty Name) -eq "Button") {
            if ($sync.Buttons -notcontains $psitem) {
                $sync["$psitem"].Add_Click({
                    [System.Object]$Sender = $args[0]
                    Invoke-WPFButton $Sender.name
                })
                $sync.Buttons.Add($psitem) | Out-Null
            }
        }

    }
}

#===========================================================================
# Setup and Show the Form
#===========================================================================

# Progress bar in taskbaritem > Set-WinUtilProgressbar
$sync["Form"].TaskbarItemInfo = New-Object System.Windows.Shell.TaskbarItemInfo
Set-WinUtilTaskbaritem -state "None"

# Set the titlebar
$sync["Form"].title = $sync["Form"].title + " " + $sync.version
# Set the commands that will run when the form is closed
$sync["Form"].Add_Closing({
    if ($sync.DashboardTimer) {
        $sync.DashboardTimer.Stop()
    }
    Close-WinUtilRunspacePool
    [System.GC]::Collect()
})

# Attach the event handler to the Click event
$sync.SearchBarClearButton.Add_Click({
    $sync.SearchBar.Text = ""
    $sync.SearchBarClearButton.Visibility = "Collapsed"

    # Focus the search bar after clearing the text
    $sync.SearchBar.Focus()
    $sync.SearchBar.SelectAll()
})

# add some shortcuts for people that don't like clicking
function Invoke-WinUtilFontScaleStep([double]$Step) { $sync.FontScalingSlider.Value = [math]::Max(0.75, [math]::Min(2.0, $sync.FontScalingSlider.Value + $Step)); Invoke-WinUtilFontScaling -ScaleFactor $sync.FontScalingSlider.Value }

$commonKeyEvents = {
    # Prevent shortcuts from executing if a process is already running
    if ($sync.ProcessRunning -eq $true) {
        return
    }

    # Handle key presses of single keys
    switch ($_.Key) {
        "Escape" { $sync.SearchBar.Text = "" }
    }
    # Handle Alt key combinations for navigation
    if ($_.KeyboardDevice.Modifiers -eq "Alt") {
        $keyEventArgs = $_
        switch ($_.SystemKey) {
            "P" { Invoke-WPFButton "WPFTab7BT"; $keyEventArgs.Handled = $true } # Navigate to Dashboard (Painel) tab and suppress Windows Warning Sound
            "I" { Invoke-WPFButton "WPFTab1BT"; $keyEventArgs.Handled = $true } # Navigate to Install tab
            "O" { Invoke-WPFButton "WPFTab2BT"; $keyEventArgs.Handled = $true } # Navigate to Tweaks (Otimizar) tab
            "R" { Invoke-WPFButton "WPFTab3BT"; $keyEventArgs.Handled = $true } # Navigate to Config (Recursos) tab
        }
    }
    # Handle Ctrl key combinations for specific actions
    if ($_.KeyboardDevice.Modifiers -eq "Ctrl") {
        $keyEventArgs = $_
        switch ($_.Key) {
            "F" { $sync.SearchBar.Focus() } # Focus on the search bar
            "Q" { $this.Close() } # Close the application
        }
    }
    $ctrlShiftModifiers = [Windows.Input.ModifierKeys]::Control -bor [Windows.Input.ModifierKeys]::Shift
    if ($_.KeyboardDevice.Modifiers -eq "Ctrl" -or $_.KeyboardDevice.Modifiers -eq $ctrlShiftModifiers) {
        $keyEventArgs = $_
        switch ($_.Key) {
            { $_ -in "OemPlus", "Add" } { Invoke-WinUtilFontScaleStep 0.05; $keyEventArgs.Handled = $true }
            { $_ -in "OemMinus", "Subtract" } { Invoke-WinUtilFontScaleStep -0.05; $keyEventArgs.Handled = $true }
        }
    }
}
$sync["Form"].Add_PreViewKeyDown($commonKeyEvents)
$sync["Form"].Add_PreviewMouseWheel({
    if ([Windows.Input.Keyboard]::Modifiers -eq "Ctrl") { Invoke-WinUtilFontScaleStep $(if ($_.Delta -gt 0) { 0.05 } else { -0.05 }); $_.Handled = $true }
})

$sync["Form"].Add_MouseLeftButtonDown({
    Invoke-WPFPopup -Action "Hide" -Popups @("Settings", "Theme", "FontScaling")
    $sync["Form"].DragMove()
})

$sync["Form"].Add_MouseDoubleClick({
    if ($_.OriginalSource.Name -eq "NavDockPanel" -or
        $_.OriginalSource.Name -eq "GridBesideNavDockPanel") {
            if ($sync["Form"].WindowState -eq [Windows.WindowState]::Normal) {
                [Windows.SystemCommands]::MaximizeWindow($sync.Form)
            }
            else{
                [Windows.SystemCommands]::RestoreWindow($sync.Form)
            }
    }
})

$sync["Form"].Add_Deactivated({
    Invoke-WPFPopup -Action "Hide" -Popups @("Settings", "Theme", "FontScaling")
})

$sync["Form"].Add_ContentRendered({
    # Load the Windows Forms assembly
    Add-Type -AssemblyName System.Windows.Forms
    $primaryScreen = [System.Windows.Forms.Screen]::PrimaryScreen
    # Check if the primary screen is found
    if ($primaryScreen) {
        # Extract screen width and height for the primary monitor
        $screenWidth = $primaryScreen.Bounds.Width
        $screenHeight = $primaryScreen.Bounds.Height
        $sync.Form.MinWidth = [Math]::Min([double]$sync.Form.MinWidth, [double]$screenWidth)

        # Compare with the primary monitor size
        if ($sync.Form.ActualWidth -gt $screenWidth -or $sync.Form.ActualHeight -gt $screenHeight) {
            $sync.Form.Left = 0
            $sync.Form.Top = 0
            $sync.Form.Width = $screenWidth
            $sync.Form.Height = $screenHeight
        }
    }

    if ($PARAM_OFFLINE) {
        # Show offline banner
        $sync.WPFOfflineBanner.Visibility = [System.Windows.Visibility]::Visible

        # Disable the install tab
        $sync.WPFTab1BT.IsEnabled = $false
        $sync.WPFTab1BT.Opacity = 0.5
        $sync.WPFTab1BT.ToolTip = "É preciso estar conectado à internet para instalar programas."

        # Disable install-related buttons
        $sync.WPFInstall.IsEnabled = $false
        $sync.WPFUninstall.IsEnabled = $false
        $sync.WPFInstallUpgrade.IsEnabled = $false
        $sync.WPFGetInstalled.IsEnabled = $false
        $sync.WPFQuickUpgradeApps.IsEnabled = $false

        # Show offline indicator
        Write-Host "Modo offline detectado - aba Instalar desativada." -ForegroundColor Yellow
    }
    else {
        # Online - ensure install tab is enabled
        $sync.WPFTab1BT.IsEnabled = $true
        $sync.WPFTab1BT.Opacity = 1.0
    }

    # The Dashboard is the start tab, online or offline
    Invoke-WPFTab "WPFTab7BT"

    $sync["Form"].Focus()
    $sync["Form"].Dispatcher.BeginInvoke([System.Windows.Threading.DispatcherPriority]::Background, [action]{ Initialize-WinUtilRunspacePool | Out-Null }) | Out-Null
    $sync["Form"].Dispatcher.BeginInvoke([System.Windows.Threading.DispatcherPriority]::Background, [action]{ Initialize-WinUtilTaskbarOverlayAssets -IncludeLogo $false -IncludeStatusAssets $true }) | Out-Null
})

# The SearchBarTimer is used to delay the search operation until the user has stopped typing for a short period
# This prevents the ui from stuttering when the user types quickly as it dosnt need to update the ui for every keystroke

$searchBarTimer = New-Object System.Windows.Threading.DispatcherTimer
$searchBarTimer.Interval = [TimeSpan]::FromMilliseconds(300)
$searchBarTimer.IsEnabled = $false

$searchBarTimer.add_Tick({
    $searchBarTimer.Stop()
    switch ($sync.currentTab) {
        "Install" {
            Find-AppsByNameOrDescription -SearchString $sync.SearchBar.Text -Categories $sync.SelectedAppCategories.ToArray()
        }
        "Tweaks" {
            Find-TweaksByNameOrDescription -SearchString $sync.SearchBar.Text
        }
        "AppX" {
            Find-TweaksByNameOrDescription -SearchString $sync.SearchBar.Text
        }
    }
})
$sync["SearchBar"].Add_TextChanged({
    if ($sync.SearchBar.Text -ne "") {
        $sync.SearchBarClearButton.Visibility = "Visible"
        $sync.SearchBarIcon.Visibility = "Collapsed"
    } else {
        $sync.SearchBarClearButton.Visibility = "Collapsed"
        $sync.SearchBarIcon.Visibility = "Visible"
    }

    if ($searchBarTimer.IsEnabled) {
        $searchBarTimer.Stop()
    }
    $searchBarTimer.Start()
})

# Category filter chips. The chip carries its category in Tag, so one handler covers all of them.
$sync.AppCategoryChips = @(
    @{ Name = "WPFSearchChipAll";             Category = "" }
    @{ Name = "WPFSearchChipBrowsers";        Category = "Navegadores" }
    @{ Name = "WPFSearchChipCommunications";  Category = "Comunicação" }
    @{ Name = "WPFSearchChipDocument";        Category = "Documentos" }
    @{ Name = "WPFSearchChipGames";           Category = "Jogos" }
    @{ Name = "WPFSearchChipMicrosoftTools";  Category = "Ferramentas Microsoft" }
    @{ Name = "WPFSearchChipMultimediaTools"; Category = "Multimídia" }
    @{ Name = "WPFSearchChipProTools";        Category = "Ferramentas Pro" }
    @{ Name = "WPFSearchChipUtilities";       Category = "Utilitários" }
)
$sync.SelectedAppCategories = [System.Collections.Generic.List[string]]::new()

foreach ($appCategoryChip in $sync.AppCategoryChips) {
    $sync[$appCategoryChip.Name].Tag = $appCategoryChip.Category
}

$sync["WPFSearchChipAll"].Add_Click({ Invoke-WinUtilAppCategoryChip -Chip $this })
$sync["WPFSearchChipBrowsers"].Add_Click({ Invoke-WinUtilAppCategoryChip -Chip $this })
$sync["WPFSearchChipCommunications"].Add_Click({ Invoke-WinUtilAppCategoryChip -Chip $this })
$sync["WPFSearchChipDocument"].Add_Click({ Invoke-WinUtilAppCategoryChip -Chip $this })
$sync["WPFSearchChipGames"].Add_Click({ Invoke-WinUtilAppCategoryChip -Chip $this })
$sync["WPFSearchChipMicrosoftTools"].Add_Click({ Invoke-WinUtilAppCategoryChip -Chip $this })
$sync["WPFSearchChipMultimediaTools"].Add_Click({ Invoke-WinUtilAppCategoryChip -Chip $this })
$sync["WPFSearchChipProTools"].Add_Click({ Invoke-WinUtilAppCategoryChip -Chip $this })
$sync["WPFSearchChipUtilities"].Add_Click({ Invoke-WinUtilAppCategoryChip -Chip $this })

$sync["Form"].Add_Loaded({
    param($e)
    $null = $e
    $sync.Form.MinWidth = "1200"
    $sync["Form"].MaxWidth = [Double]::PositiveInfinity
    $sync["Form"].MaxHeight = [Double]::PositiveInfinity
})

$NavLogoPanel = $sync["Form"].FindName("NavLogoPanel")
$NavLogoPanel.Children.Insert(0, (Invoke-WinUtilAssets -Type "logo" -Size 30))
Initialize-WinUtilTaskbarOverlayAssets -IncludeLogo $true -IncludeStatusAssets $false
$sync["Form"].Icon = $sync["logorender"]

Set-WinUtilTaskbaritem -overlay "logo"

$sync["Form"].Add_Activated({
    Set-WinUtilTaskbaritem -overlay "logo"
})

$sync["ThemeButton"].Add_Click({
    Invoke-WPFPopup -PopupActionTable @{ "Settings" = "Hide"; "Theme" = "Toggle"; "FontScaling" = "Hide" }
})
$sync["AutoThemeMenuItem"].Add_Click({
    Invoke-WPFPopup -Action "Hide" -Popups @("Theme")
    Invoke-WinutilThemeChange -theme "Auto"
})
$sync["DarkThemeMenuItem"].Add_Click({
    Invoke-WPFPopup -Action "Hide" -Popups @("Theme")
    Invoke-WinutilThemeChange -theme "Dark"
})
$sync["LightThemeMenuItem"].Add_Click({
    Invoke-WPFPopup -Action "Hide" -Popups @("Theme")
    Invoke-WinutilThemeChange -theme "Light"
})

$sync["SettingsButton"].Add_Click({
    Invoke-WPFPopup -PopupActionTable @{ "Settings" = "Toggle"; "Theme" = "Hide"; "FontScaling" = "Hide" }
})
$sync["ImportMenuItem"].Add_Click({
    Invoke-WPFPopup -Action "Hide" -Popups @("Settings")
    Invoke-WPFImpex -type "import"
})
$sync["ExportMenuItem"].Add_Click({
    Invoke-WPFPopup -Action "Hide" -Popups @("Settings")
    Invoke-WPFImpex -type "export"
})
$sync["AboutMenuItem"].Add_Click({
    Invoke-WPFPopup -Action "Hide" -Popups @("Settings")

    $authorInfo = @"
Otimização do Windows no estilo Rosé.

Versão   : $($sync.version)
Fork     : azor
Base     : <a href="https://github.com/ChrisTitusTech/winutil">WinUtil de Chris Titus Tech</a> (licença MIT)
UI       : <a href="https://github.com/MyDrift-user">@MyDrift-user</a>, <a href="https://github.com/Marterich">@Marterich</a>
Runspace : <a href="https://github.com/DeveloperDurp">@DeveloperDurp</a>, <a href="https://github.com/Marterich">@Marterich</a>
"@
    Show-CustomDialog -Title "Sobre" -Message $authorInfo
})
$sync["DocumentationMenuItem"].Add_Click({
    Invoke-WPFPopup -Action "Hide" -Popups @("Settings")
    Start-Process "https://winutil.christitus.com/"
})
$sync["SponsorMenuItem"].Add_Click({
    Invoke-WPFPopup -Action "Hide" -Popups @("Settings")

    $creditsInfo = @"
O Azor WinUtil é um fork do WinUtil, criado por Chris Titus Tech e mantido por uma comunidade de contribuidores.

Projeto original : <a href="https://github.com/ChrisTitusTech/winutil">github.com/ChrisTitusTech/winutil</a>
Contribuidores   : <a href="https://github.com/ChrisTitusTech/winutil/graphs/contributors">lista no GitHub</a>
Apoie o autor    : <a href="https://github.com/sponsors/ChrisTitusTech">GitHub Sponsors</a>

Licença MIT - Copyright (c) 2022 CT Tech Group LLC.
Tema Rosé, Painel e ferramentas extras por azor.
"@
    Show-CustomDialog -Title "Créditos" -Message $creditsInfo -EnableScroll $true
})

# Font Scaling Event Handlers
$sync["FontScalingButton"].Add_Click({
    Invoke-WPFPopup -PopupActionTable @{ "Settings" = "Hide"; "Theme" = "Hide"; "FontScaling" = "Toggle" }
})

$sync["FontScalingSlider"].Add_ValueChanged({
    param($slider)
    $percentage = [math]::Round($slider.Value * 100)
    $sync.FontScalingValue.Text = "$percentage%"
})

$sync["FontScalingResetButton"].Add_Click({
    $sync.FontScalingSlider.Value = 1.0
    $sync.FontScalingValue.Text = "100%"
})

$sync["FontScalingApplyButton"].Add_Click({
    $scaleFactor = $sync.FontScalingSlider.Value
    Invoke-WinUtilFontScaling -ScaleFactor $scaleFactor
    Invoke-WPFPopup -Action "Hide" -Popups @("FontScaling")
})

function Remove-WinUtilTempScript {
    <#
    .SYNOPSIS
        Removes the temporary copy of the script used to relaunch as administrator.

    .DESCRIPTION
        Deletes the current script only when it is an azorwinutil-*.ps1 file in
        the system temporary directory. This preserves normal file-backed
        and in-memory Azor WinUtil launches.
    #>

    $scriptPath = $PSCommandPath
    $tempPath = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')

    if (
        $scriptPath -and
        [IO.Path]::GetDirectoryName($scriptPath) -eq $tempPath -and
        [IO.Path]::GetFileName($scriptPath) -like 'azorwinutil-*.ps1'
    ) {
        Remove-Item -LiteralPath $scriptPath -Force -ErrorAction SilentlyContinue
    }
}

# ──────────────────────────────────────────────────────────────────────────────

$sync["Form"].ShowDialog() | out-null
Remove-WinUtilTempScript
Stop-Transcript

