# Build a standalone Windows Desktop bundle (PyInstaller)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Desktop = Join-Path $Root "desktop"
$Dist = Join-Path $Desktop "dist"
$Build = Join-Path $Desktop "build"

Set-Location $Desktop

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
  --collect-all mediapipe `
  intelliQuiz_desktop/cli.py

Write-Host ""
Write-Host "Build complete:"
Write-Host "  $Dist\IntelliQuizDesktop\IntelliQuizDesktop.exe"
Write-Host ""
Write-Host "Zip the IntelliQuizDesktop folder and share with students."
Write-Host "Set IQ_DESKTOP_API_BASE_URL to your server before running."
