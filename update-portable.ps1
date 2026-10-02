param([Parameter(Mandatory=$true)][string]$Config,[switch]$NoRestart,[ValidateRange(0,120)][int]$WaitSeconds=60)
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
function Move-Whole($source,$destination) {
  # Move-Item walks directories and can leave half of a runtime moved on error.
  if (Test-Path -LiteralPath $source -PathType Container) {[IO.Directory]::Move($source,$destination)}
  else {[IO.File]::Move($source,$destination)}
}
function Get-AppProcesses {
  $executable=Join-Path $appRoot 'BackloGame.exe'
  @(Get-Process -Name BackloGame -ErrorAction SilentlyContinue | Where-Object {
    # Fail closed if a process with our name cannot be inspected.
    $path=$_.Path
    if (-not $path) {throw 'Cannot inspect a running BackloGame process. Close all BackloGame windows and try again.'}
    [string]::Equals($path,$executable,[StringComparison]::OrdinalIgnoreCase)
  })
}
Assert-Child $rollback $appRoot
if (-not (Test-Path -LiteralPath (Join-Path $stagingRoot 'BackloGame.exe'))) {throw 'Missing new executable'}
if (-not (Test-Path -LiteralPath (Join-Path $stagingRoot '_internal') -PathType Container)) {throw 'Missing new runtime'}
try {
  $process=Get-Process -Id $job.pid -ErrorAction SilentlyContinue
  if ($process) {if (-not $process.WaitForExit($WaitSeconds*1000)) {throw 'Application is still running'}}
  $deadline=[DateTime]::UtcNow.AddSeconds($WaitSeconds)
  while (@(Get-AppProcesses).Count -gt 0) {
    if ([DateTime]::UtcNow -ge $deadline) {throw 'Close all BackloGame windows before installing an update.'}
    Start-Sleep -Milliseconds 250
  }
  $parentExited=$true
  if (Test-Path -LiteralPath $rollback) {Remove-Item -LiteralPath $rollback -Recurse -Force}
  New-Item -ItemType Directory -Path $rollback | Out-Null
  foreach ($name in $names) {
    $target=Join-Path $appRoot $name; $source=Join-Path $stagingRoot $name
    Assert-Child $target $appRoot; Assert-Child $source $stagingRoot
    if (Test-Path -LiteralPath $target) {Move-Whole $target (Join-Path $rollback $name);$moved+=$name}
    if (Test-Path -LiteralPath $source) {$installed+=$name;Copy-Item -LiteralPath $source -Destination $target -Recurse -Force}
  }
  @{status='installed'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $job.data 'update-result.json') -Encoding UTF8
} catch {
  $failure=$_.Exception.Message
  try {
    foreach ($name in $installed) {$target=Join-Path $appRoot $name;Assert-Child $target $appRoot;if (Test-Path -LiteralPath $target) {Remove-Item -LiteralPath $target -Recurse -Force}}
    foreach ($name in $moved) {$source=Join-Path $rollback $name;Assert-Child $source $rollback;Move-Whole $source (Join-Path $appRoot $name)}
  } catch {$failure+=' Rollback incomplete; preserved files are in .update-rollback. '+$_.Exception.Message;$parentExited=$false}
  @{status='failed';error=$failure} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $job.data 'update-result.json') -Encoding UTF8
}
if ($parentExited -and -not $NoRestart -and @(Get-AppProcesses).Count -eq 0) {Start-Process -FilePath (Join-Path $appRoot 'BackloGame.exe') -ArgumentList @('--data-dir',('"'+$job.data+'"')) -WorkingDirectory $appRoot}
