param(
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [Parameter(Mandatory = $true)][string]$ConsoleLog
)

$ErrorActionPreference = "Stop"

Write-Output ("===== Backend stable start {0} =====" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss")) | Tee-Object -FilePath $ConsoleLog -Append

$command = '"{0}" -m uvicorn backend.main:app --host 0.0.0.0 --port 18000 2>&1' -f $PythonExe
& cmd.exe /d /c $command | Tee-Object -FilePath $ConsoleLog -Append
$exitCode = $LASTEXITCODE

Write-Output ("===== Backend stable stopped {0}; exit code {1} =====" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $exitCode) | Tee-Object -FilePath $ConsoleLog -Append
exit $exitCode