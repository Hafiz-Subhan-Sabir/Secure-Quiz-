# Build a standalone Windows Desktop bundle (PyInstaller)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Desktop = Join-Path $Root "desktop"
$Dist = Join-Path $Desktop "dist"
$Build = Join-Path $Desktop "build"

Set-Location $Desktop

# Stamp Git SHA + build time into the package so we can prove which source was shipped.
$Sha = "unknown"
try { $Sha = (git -C $Root rev-parse --short HEAD).Trim() } catch { }
$Stamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"
$BuildInfo = Join-Path $Desktop "intelliQuiz_desktop\build_info.py"
@"
"""Build provenance stamped at package time."""

BUILD_SHA = "$Sha"
BUILD_TIME = "$Stamp"
"@ | Set-Content -Path $BuildInfo -Encoding UTF8
Write-Host "Build stamp: $Sha @ $Stamp"

Write-Host "Installing desktop package..."
pip install -e . | Out-Null
pip install pyinstaller | Out-Null

Write-Host "Building IntelliQuiz Desktop executable..."
if (Test-Path $Dist) { Remove-Item -Recurse -Force $Dist }
if (Test-Path $Build) { Remove-Item -Recurse -Force $Build }

$ModelSrc = Join-Path $Root "ml\artifacts\models\best_model.joblib"
$UiDir = Join-Path $Desktop "intelliQuiz_desktop\ui"
$ModelsDir = Join-Path $Desktop "intelliQuiz_desktop\models"

pyinstaller `
  --noconfirm `
  --onedir `
  --name IntelliQuizDesktop `
  --console `
  --add-data "$UiDir;intelliQuiz_desktop/ui" `
  --add-data "$ModelsDir;intelliQuiz_desktop/models" `
  --add-data "$ModelSrc;ml/artifacts/models" `
  --hidden-import mediapipe `
  --hidden-import cv2 `
  --hidden-import sklearn `
  --hidden-import sklearn.ensemble `
  --hidden-import sklearn.ensemble._forest `
  --hidden-import intelliQuiz_desktop.build_info `
  --collect-all mediapipe `
  --collect-all sklearn `
  --collect-all joblib `
  intelliQuiz_desktop/cli.py

Write-Host ""
Write-Host "Build complete:"
Write-Host "  $Dist\IntelliQuizDesktop\IntelliQuizDesktop.exe"
Write-Host ""

# Friendly launcher so students don't run a lone .exe without _internal
$LaunchSrc = Join-Path $Root "scripts\Launch-IntelliQuiz.bat"
$LaunchDst = Join-Path $Dist "IntelliQuizDesktop\Launch IntelliQuiz.bat"
if (Test-Path $LaunchSrc) {
  Copy-Item $LaunchSrc $LaunchDst -Force
  Write-Host "Launcher: $LaunchDst"
}

# Ship Railway/API settings next to the EXE when present
$EnvSrc = Join-Path $Desktop ".env"
$EnvDst = Join-Path $Dist "IntelliQuizDesktop\.env"
if (Test-Path $EnvSrc) {
  Copy-Item $EnvSrc $EnvDst -Force
  Write-Host "Env:     $EnvDst"
}

$Readme = @"
IntelliQuiz Desktop
===================
1. Unzip this WHOLE folder (keep _internal next to the .exe).
2. Double-click "Launch IntelliQuiz.bat" (recommended), or IntelliQuizDesktop.exe.
3. Keep the console window open during the exam.
4. Optional: edit .env next to the EXE:
   IQ_DESKTOP_API_BASE_URL=https://YOUR-SERVER/api/v1
   IQ_DESKTOP_API_VERIFY_SSL=true
"@
Set-Content -Path (Join-Path $Dist "IntelliQuizDesktop\README.txt") -Value $Readme -Encoding UTF8

Write-Host "Zip the IntelliQuizDesktop folder and share with students."
Write-Host "Set IQ_DESKTOP_API_BASE_URL to your server before running."
