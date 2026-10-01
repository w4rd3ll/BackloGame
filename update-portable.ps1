param([Parameter(Mandatory=$true)][string]$Config,[switch]$NoRestart)
$ErrorActionPreference='Stop'
$job=Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
$appRoot=[IO.Path]::GetFullPath($job.root)
$stagingRoot=[IO.Path]::GetFullPath($job.stage)
$rollback=Join-Path $appRoot '.update-rollback'
$names=@('BackloGame.exe','_internal','licenses','README.txt','THIRD_PARTY.md')
$moved=@(); $installed=@(); $parentExited=$false
function Assert-Child($path,$parent) {
  $full=[IO.Path]::GetFullPath($path)
  if (-not $full.StartsWith($parent.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) {throw 'Unsafe update path'}
  if ((Test-Path -LiteralPath $full) -and ((Get-Item -LiteralPath $full).Attributes -band [IO.FileAttributes]::ReparsePoint)) {throw 'Linked update path'}
}
Assert-Child $rollback $appRoot
if (-not (Test-Path -LiteralPath (Join-Path $stagingRoot 'BackloGame.exe'))) {throw 'Missing new executable'}
if (-not (Test-Path -LiteralPath (Join-Path $stagingRoot '_internal') -PathType Container)) {throw 'Missing new runtime'}
try {
  $process=Get-Process -Id $job.pid -ErrorAction SilentlyContinue
  if ($process) {if (-not $process.WaitForExit(60000)) {throw 'Application is still running'}}
  $parentExited=$true
  if (Test-Path -LiteralPath $rollback) {Remove-Item -LiteralPath $rollback -Recurse -Force}
  New-Item -ItemType Directory -Path $rollback | Out-Null
  foreach ($name in $names) {
    $target=Join-Path $appRoot $name; $source=Join-Path $stagingRoot $name
    Assert-Child $target $appRoot; Assert-Child $source $stagingRoot
    if (Test-Path -LiteralPath $target) {Move-Item -LiteralPath $target -Destination (Join-Path $rollback $name);$moved+=$name}
    if (Test-Path -LiteralPath $source) {$installed+=$name;Copy-Item -LiteralPath $source -Destination $target -Recurse -Force}
  }
  @{status='installed'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $job.data 'update-result.json') -Encoding UTF8
} catch {
  foreach ($name in $installed) {$target=Join-Path $appRoot $name;Assert-Child $target $appRoot;if (Test-Path -LiteralPath $target) {Remove-Item -LiteralPath $target -Recurse -Force}}
  foreach ($name in $moved) {$source=Join-Path $rollback $name;Assert-Child $source $rollback;Move-Item -LiteralPath $source -Destination (Join-Path $appRoot $name)}
  @{status='failed';error=$_.Exception.Message} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $job.data 'update-result.json') -Encoding UTF8
}
if ($parentExited -and -not $NoRestart) {Start-Process -FilePath (Join-Path $appRoot 'BackloGame.exe') -ArgumentList @('--data-dir',('"'+$job.data+'"')) -WorkingDirectory $appRoot}
