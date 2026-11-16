# Builds dist\LocalSub.exe (portable) and installer\LocalSub-Setup.exe (if Inno Setup is installed)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) {
    python -m venv .venv
    .\.venv\Scripts\python -m pip install -r requirements.txt
}
$py = ".\.venv\Scripts\python.exe"

& $py make_icon.py

& $py -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name LocalSub `
    --icon assets\icon.ico `
    --add-data "assets;assets" `
    --collect-data customtkinter `
    --collect-submodules av `
    --exclude-module numpy --exclude-module setuptools --exclude-module PIL `
    --version-file version_info.txt `
    LocalSub.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
Write-Host "`nPortable app: $PSScriptRoot\dist\LocalSub.exe" -ForegroundColor Green

$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (Test-Path $iscc) {
    & $iscc /Q installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
    Write-Host "Installer:    $PSScriptRoot\installer\LocalSub-Setup.exe" -ForegroundColor Green
} else {
    Write-Host "Inno Setup not found - skipping installer (portable exe still works)." -ForegroundColor Yellow
}
