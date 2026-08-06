# Start IntelliQuiz API (Windows PowerShell)
Set-Location (Join-Path $PSScriptRoot "..\backend")
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
