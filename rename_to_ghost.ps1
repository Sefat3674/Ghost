# Renames Kaizumi -> GHOST: file contents AND file/folder names.
# DRY RUN by default. Nothing changes until you add -Apply.
param([switch]$Apply)

$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path
$self = $MyInvocation.MyCommand.Path

$skipDirs = @('.venv', '.venv312', 'venv', '.git', '__pycache__', 'node_modules', 'logs', 'models', 'data', '.pytest_cache')
$textExt  = @('.py', '.md', '.txt', '.json', '.toml', '.ps1', '.bat', '.cmd', '.yml', '.yaml',
              '.cfg', '.ini', '.env', '.sh', '.html', '.js', '.css')

# Keep credit / source links pointing at the original repo.
$keepUrl = 'MusayevDoniyor/kaizumi'
$token   = '@@KEEP_ORIGINAL_REPO_URL@@'

function Test-Skipped([string]$fullPath) {
    $rel = $fullPath.Substring($root.Length).TrimStart('\', '/')
    foreach ($part in ($rel -split '[\\/]')) {
        if ($skipDirs -contains $part) { return $true }
    }
    return $false
}

$evaluator = [System.Text.RegularExpressions.MatchEvaluator] {
    param($m)
    if ($m.Value -ceq $m.Value.ToLower()) { 'ghost' } else { 'GHOST' }
}

function Convert-Text([string]$s) {
    $s = $s.Replace($keepUrl, $token)
    $s = [regex]::Replace($s, 'kaizumi', $evaluator, 'IgnoreCase')
    return $s.Replace($token, $keepUrl)
}

$mode = if ($Apply) { 'APPLYING CHANGES' } else { 'DRY RUN (add -Apply to make changes)' }
Write-Host "== $mode ==" -ForegroundColor Cyan
Write-Host "Project folder: $root`n"

# ---- 1. File contents ----
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$utf8Bom   = New-Object System.Text.UTF8Encoding($true)

$files = Get-ChildItem -Path $root -Recurse -File -Force | Where-Object {
    -not (Test-Skipped $_.FullName) -and
    $_.FullName -ne $self -and
    ($textExt -contains $_.Extension.ToLower())
}

$contentChanged = 0
foreach ($f in $files) {
    try { $text = [System.IO.File]::ReadAllText($f.FullName) } catch { continue }
    $new = Convert-Text $text
    if ($new -ne $text) {
        $contentChanged++
        Write-Host ("content: " + $f.FullName.Substring($root.Length + 1))
        if ($Apply) {
            $enc = if ($f.Extension -ieq '.ps1') { $utf8Bom } else { $utf8NoBom }
            [System.IO.File]::WriteAllText($f.FullName, $new, $enc)
        }
    }
}

# ---- 2. File and folder names (deepest first) ----
$items = Get-ChildItem -Path $root -Recurse -Force | Where-Object {
    -not (Test-Skipped $_.FullName) -and
    $_.FullName -ne $self -and
    $_.Name -match '(?i)kaizumi'
} | Sort-Object { $_.FullName.Length } -Descending

$renamed = 0
foreach ($i in $items) {
    $newName = Convert-Text $i.Name
    Write-Host ("rename:  " + $i.FullName.Substring($root.Length + 1) + "  ->  " + $newName)
    $renamed++
    if ($Apply) { Rename-Item -LiteralPath $i.FullName -NewName $newName }
}

# ---- 3. Leftover check ----
if ($Apply) {
    Write-Host "`nChecking for leftovers..." -ForegroundColor Cyan
    $left = Get-ChildItem -Path $root -Recurse -File -Force | Where-Object {
        -not (Test-Skipped $_.FullName) -and $_.FullName -ne $self -and ($textExt -contains $_.Extension.ToLower())
    } | Select-String -Pattern 'kaizumi' | Where-Object { $_.Line -notmatch [regex]::Escape($keepUrl) }
    if ($left) {
        $left | ForEach-Object { Write-Host ("left: " + $_.Path.Substring($root.Length + 1) + ":" + $_.LineNumber) }
    } else {
        Write-Host "None found."
    }
}

Write-Host ("`n{0} file(s) with content changes, {1} file/folder name(s) renamed." -f $contentChanged, $renamed)
if (-not $Apply) { Write-Host "Nothing was changed. Re-run with -Apply to go ahead." -ForegroundColor Yellow }
