param(
    [string]$HhcPath
)

$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $PSScriptRoot
$helpDir = Join-Path $projectDir "docs\help"
$projectFile = Join-Path $helpDir "eLib.hhp"
$outputFile = Join-Path $projectDir "docs\eLib.chm"

if (-not $HhcPath) {
    $candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "HTML Help Workshop\hhc.exe"),
        (Join-Path $env:ProgramFiles "HTML Help Workshop\hhc.exe")
    )
    $HhcPath = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}

if (-not $HhcPath -or -not (Test-Path $HhcPath)) {
    throw "HTML Help Workshop hhc.exe is required. Install it, then run: .\tools\build_chm.ps1 -HhcPath 'C:\...\hhc.exe'"
}

Push-Location $helpDir
try {
    & $HhcPath $projectFile
    if ($LASTEXITCODE -ne 0) {
        throw "HTML Help Workshop failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}

if (-not (Test-Path $outputFile)) {
    throw "The compiler reported success but did not create $outputFile."
}

Write-Output "CHM help created: $outputFile"
