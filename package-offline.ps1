param(
    [string]$PackageName = ("CrashDog-offline-{0}" -f (Get-Date -Format "yyyyMMdd-HHmmss")),
    [switch]$SkipFrontendBuild,
    [switch]$IncludeProjectData
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$OutputRoot = Join-Path $Root "offline-packages"
$WorkRoot = Join-Path $OutputRoot "_staging"
$PackageRoot = Join-Path $WorkRoot "CrashDog"
$ArchivePath = Join-Path $OutputRoot ("{0}.tar" -f $PackageName)

function Assert-PathExists {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Message
    )

    if (-not (Test-Path $Path)) {
        throw $Message
    }
}

function Invoke-RobocopyChecked {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination,
        [string[]]$ExtraArgs = @()
    )

    $arguments = @($Source, $Destination, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP") + $ExtraArgs
    & robocopy @arguments | Out-Null
    $exitCode = $LASTEXITCODE
    if ($exitCode -ge 8) {
        throw "Robocopy failed with exit code $exitCode while copying $Source"
    }
}

$ExcludedDirectoryNames = @("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache")
$ExcludedFilePatterns = @("*.pyc", "*.pyo", "*.log")

Write-Host "CrashDog offline package"
Write-Host "Root: $Root"

$PythonExe = Join-Path $Root ".venv\Scripts\python.exe"
$PythonBasePrefix = (& $PythonExe -c "import sys; print(sys.base_prefix)").Trim()
$RequirementsFile = Join-Path $Root "backend\requirements.txt"
$FrontendNodeModules = Join-Path $Root "frontend\node_modules"
$ViteCli = Join-Path $Root "frontend\node_modules\vite\bin\vite.js"
$NpmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue

Assert-PathExists $PythonExe "Missing .venv\Scripts\python.exe. Create the backend virtual environment before packaging."
Assert-PathExists (Join-Path $PythonBasePrefix "python.exe") "Missing base Python runtime: $PythonBasePrefix"
Assert-PathExists $RequirementsFile "Missing backend\requirements.txt."
Assert-PathExists $FrontendNodeModules "Missing frontend\node_modules. Run npm install while online before packaging."
Assert-PathExists $ViteCli "Missing Vite CLI under frontend\node_modules. Run npm install while online before packaging."

if (-not $SkipFrontendBuild) {
    Write-Host "Building frontend..."
    if ($null -eq $NpmCommand) {
        throw "npm.cmd was not found on PATH. Install Node.js once on this machine, then rebuild the offline package."
    }
    Push-Location (Join-Path $Root "frontend")
    try {
        & $NpmCommand.Source run build
        if ($LASTEXITCODE -ne 0) {
            throw "Frontend build failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

$NodeCommand = Get-Command node -ErrorAction SilentlyContinue
if ($null -eq $NodeCommand) {
    throw "Node.js was not found on PATH. Install Node.js once on this machine, then rebuild the offline package."
}
$TarCommand = Get-Command tar.exe -ErrorAction SilentlyContinue
if ($null -eq $TarCommand) {
    throw "tar.exe was not found. This script requires the Windows built-in tar.exe to create large offline packages."
}

Remove-Item $WorkRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $PackageRoot -Force | Out-Null
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null

Write-Host "Copying application files..."
foreach ($file in @("start.bat", "start-backend.bat", "start-backend.ps1", "start-backend-dev.bat", "start-frontend.bat")) {
    Copy-Item -Path (Join-Path $Root $file) -Destination (Join-Path $PackageRoot $file) -Force
}

New-Item -ItemType Directory -Path (Join-Path $PackageRoot "backend") -Force | Out-Null
Invoke-RobocopyChecked -Source (Join-Path $Root "backend") -Destination (Join-Path $PackageRoot "backend") -ExtraArgs @(
    "/XD",
    (Join-Path $Root "backend\uploads"),
    (Join-Path $Root "backend\crashes"),
    (Join-Path $Root "backend\symbols"),
    (Join-Path $Root "backend\logs"),
    (Join-Path $Root "backend\__pycache__"),
    (Join-Path $Root "backend\.pytest_cache"),
    "/XF",
    $ExcludedFilePatterns
)

New-Item -ItemType Directory -Path (Join-Path $PackageRoot "frontend") -Force | Out-Null
foreach ($item in @("index.html", "package.json", "package-lock.json", "vite.config.js", "README.md", "src", "public", "node_modules", "dist")) {
    $source = Join-Path $Root "frontend\$item"
    if (Test-Path $source) {
        Copy-Item -Path $source -Destination (Join-Path $PackageRoot "frontend") -Recurse -Force
    }
}

foreach ($dir in @("Doc", "docs")) {
    $source = Join-Path $Root $dir
    if (Test-Path $source) {
        Copy-Item -Path $source -Destination $PackageRoot -Recurse -Force
    }
}

if ($IncludeProjectData) {
    foreach ($dir in @("QingCheng", "bin")) {
        $source = Join-Path $Root $dir
        if (Test-Path $source) {
            Invoke-RobocopyChecked -Source $source -Destination (Join-Path $PackageRoot $dir) -ExtraArgs @(
                "/XD",
                $ExcludedDirectoryNames,
                "/XF",
                $ExcludedFilePatterns
            )
        }
    }
    foreach ($dir in @("backend\uploads", "backend\crashes", "backend\symbols")) {
        $source = Join-Path $Root $dir
        if (Test-Path $source) {
            Copy-Item -Path $source -Destination (Join-Path $PackageRoot $dir) -Recurse -Force
        }
    }
    $database = Join-Path $Root "crashdog.db"
    if (Test-Path $database) {
        Copy-Item -Path $database -Destination (Join-Path $PackageRoot "crashdog.db") -Force
    }
}

$RuntimeNodeDir = Join-Path $PackageRoot "runtime\node"
New-Item -ItemType Directory -Path $RuntimeNodeDir -Force | Out-Null
Copy-Item -Path $NodeCommand.Source -Destination (Join-Path $RuntimeNodeDir "node.exe") -Force

Write-Host "Preparing packaged Python runtime..."
$RuntimePythonDir = Join-Path $PackageRoot "runtime\python"
Invoke-RobocopyChecked -Source $PythonBasePrefix -Destination $RuntimePythonDir -ExtraArgs @("/XD", (Join-Path $PythonBasePrefix "Doc"), (Join-Path $PythonBasePrefix "tcl"), "/XF", "*.pyc", "*.pyo")
Invoke-RobocopyChecked -Source (Join-Path $Root ".venv\Lib\site-packages") -Destination (Join-Path $RuntimePythonDir "Lib\site-packages") -ExtraArgs @("/XF", "*.pyc", "*.pyo")

foreach ($dir in @("logs", "tmp", "backend\uploads", "backend\crashes", "backend\symbols")) {
    New-Item -ItemType Directory -Path (Join-Path $PackageRoot $dir) -Force | Out-Null
}

Write-Host "Validating package layout..."
$checks = @(
    "runtime\python\python.exe",
    "runtime\node\node.exe",
    "frontend\node_modules\vite\bin\vite.js",
    "backend\main.py",
    "start.bat",
    "start-backend.bat",
    "start-backend.ps1",
    "start-frontend.bat"
)
foreach ($relativePath in $checks) {
    Assert-PathExists (Join-Path $PackageRoot $relativePath) "Packaged file missing: $relativePath"
}

& (Join-Path $PackageRoot "runtime\python\python.exe") -c "import fastapi, sqlalchemy, uvicorn; print('backend deps ok')"
if ($LASTEXITCODE -ne 0) {
    throw "Backend dependency check failed."
}

& (Join-Path $PackageRoot "runtime\node\node.exe") (Join-Path $PackageRoot "frontend\node_modules\vite\bin\vite.js") --version
if ($LASTEXITCODE -ne 0) {
    throw "Frontend dependency check failed."
}

Remove-Item $ArchivePath -Force -ErrorAction SilentlyContinue
Write-Host "Creating archive: $ArchivePath"
Push-Location $WorkRoot
try {
    & $TarCommand.Source -cf $ArchivePath "CrashDog"
    if ($LASTEXITCODE -ne 0) {
        throw "Archive creation failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

$ArchiveItem = Get-Item $ArchivePath -ErrorAction SilentlyContinue
if ($null -eq $ArchiveItem -or $ArchiveItem.Length -le 0) {
    throw "Archive creation failed: $ArchivePath was not created."
}

Write-Host "Offline package created: $ArchivePath"
Write-Host "To use it on an offline Windows machine: extract the tar archive, then run start.bat."