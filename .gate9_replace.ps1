$ErrorActionPreference='"'"'Stop'"'"'
$root = Get-Location
$exts = @('"'"'*.py'"'"','"'"'*.ts'"'"','"'"'*.tsx'"'"','"'"'*.yml'"'"','"'"'*.yaml'"'"','"'"'*.json'"'"','"'"'*.sh'"'"','"'"'*.md'"'"','"'"'*.cfg'"'"','"'"'*.toml'"'"','"'"'*.ini'"'"','"'"'*.conf'"'"','"'"'*.txt'"'"','"'"'*.c'"'"','"'"'*.h'"'"','"'"'*.inf'"'"')
$exclude = '"'"'node_modules|\.git|CHANGELOG|__pycache__'"'"'
$replacements = @(
  @('"'"'Prady OS'"'"','"'"'Prady OS'"'"'),
  @('"'"'prady-os-v2'"'"','"'"'prady-os'"'"'),
  @('"'"'PradyOS'"'"','"'"'PradyOS'"'"'),
  @('"'"'Vyrex'"'"','"'"'Vyrex'"'"'),
  @('"'"'vyrex-proxy'"'"','"'"'vyrex-proxy'"'"'),
  @('"'"'vyrex_proxy'"'"','"'"'vyrex_proxy'"'"'),
  @('"'"'VYREX_PROXY'"'"','"'"'VYREX_PROXY'"'"'),
  @('"'"'VYREX_URL'"'"','"'"'VYREX_URL'"'"'),
  @('"'"'VYREX'"'"','"'"'VYREX'"'"'),
  @('"'"'vyrex'"'"','"'"'vyrex'"'"'),
  @('"'"'Lumyn'"'"','"'"'Lumyn Agent'"'"'),
  @('"'"'lumyn'"'"','"'"'lumyn-agent'"'"'),
  @('"'"'lumyn_agent'"'"','"'"'lumyn_agent'"'"'),
  @('"'"'Lumyn'"'"','"'"'LumynAgent'"'"'),
  @('"'"'Prax Agent'"'"','"'"'Prax Agent'"'"'),
  @('"'"'prax-agent'"'"','"'"'prax-agent'"'"'),
  @('"'"'prady_agent'"'"','"'"'prax_agent'"'"'),
  @('"'"'PradyAgent'"'"','"'"'PraxAgent'"'"'),
  @('"'"'PRAX_AGENT'"'"','"'"'PRAX_AGENT'"'"'),
  @('"'"'Prady'"'"','"'"'Kryos'"'"'),
  @('"'"'prady'"'"','"'"'kryos'"'"'),
  @('"'"'PRADY'"'"','"'"'KRYOS'"'"')
)
$files = Get-ChildItem -Recurse -File -Include $exts | Where-Object { $_.FullName -notmatch $exclude }
$affected = New-Object System.Collections.Generic.HashSet[string]
foreach($f in $files){
  $txt = Get-Content -LiteralPath $f.FullName -Raw
  foreach($pair in $replacements){
    if($txt.Contains($pair[0])) { $null = $affected.Add($f.FullName); break }
  }
}
"'"'AFFECTED_FILES=$($affected.Count)'"'"'
$report = @()
foreach($path in $affected){
  $txt = Get-Content -LiteralPath $path -Raw
  $orig = $txt
  foreach($pair in $replacements){
    $txt = $txt.Replace($pair[0], $pair[1])
  }
  if($txt -ne $orig){
    [System.IO.File]::WriteAllText($path, $txt)
    $report += $path.Replace($root.Path+'"'"'\\'"'"','"'"''"'"')
  }
}
$report | Sort-Object | Set-Content -Path .gate9_edited_files.txt
"'"'EDITED_FILES=$($report.Count)'"'"'
Get-Content .gate9_edited_files.txt -First 120
