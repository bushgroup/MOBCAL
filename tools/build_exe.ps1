<#
.SYNOPSIS
    Build the mobcal folder and its Windows installer.
.DESCRIPTION
    Runs tools/build_bundle.py (PyInstaller on packaging/mobcal.spec, then the Fortran binaries,
    their build.json and the examples beside mobcal.exe, then the built program's self-check
    with PATH cut to the Windows directories) with PATH cut to the Windows directories and uv's
    own, and then compiles packaging/mobcal.iss with Inno Setup 6's ISCC.exe into
    dist\installer\mobcal-<version>-setup.exe.

    PATH is cut because PyInstaller resolves DLL dependencies through PATH as a last resort, so
    a PATH carrying another toolchain or Python distribution makes the build depend on the shell
    it ran from; packaging/mobcal.spec refuses to build when anything gets through anyway.
.PARAMETER BinDir
    Where the binaries and build.json are: build\fortran\ (the default) after `mobcal build` or
    after downloading CI's mobcal-Windows-X64 artifact there.
.PARAMETER SkipPyInstaller
    Reuse dist\mobcal\ and redo only the binaries, examples, self-check and installer.
.PARAMETER NoInstaller
    Stop after the folder; do not run ISCC.
#>
param(
    [string]$BinDir = "build\fortran",
    [switch]$SkipPyInstaller,
    [switch]$NoInstaller
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$bundleArgs = @("tools/build_bundle.py", "--bin-dir", $BinDir)
if ($SkipPyInstaller) { $bundleArgs += "--skip-pyinstaller" }

$savedPath = $env:PATH
$uvDir = Split-Path -Parent (Get-Command uv).Source
$env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\Wbem;$uvDir"
try {
    uv run @bundleArgs
    if ($LASTEXITCODE -ne 0) { throw "tools/build_bundle.py failed (exit $LASTEXITCODE)." }
} finally {
    $env:PATH = $savedPath
}

if ($NoInstaller) { return }

$iscc = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    $found = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($found) { $iscc = $found.Source }
}
if (-not $iscc) {
    throw "No ISCC.exe: install Inno Setup 6 (winget install JRSoftware.InnoSetup --scope user), or pass -NoInstaller."
}

Write-Host "Compiling the installer with $iscc..." -ForegroundColor Cyan
$t0 = Get-Date
& $iscc /Q (Join-Path $root "packaging\mobcal.iss")
if ($LASTEXITCODE -ne 0) { throw "ISCC failed (exit $LASTEXITCODE)." }
$setup = Get-ChildItem (Join-Path $root "dist\installer\mobcal-*-setup.exe") |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host ("installer: {0}, {1:N1} MB, compiled in {2:N0} s" -f $setup.FullName,
    ($setup.Length / 1MB), ((Get-Date) - $t0).TotalSeconds) -ForegroundColor Green
