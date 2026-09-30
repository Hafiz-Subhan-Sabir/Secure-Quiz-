@echo off
setlocal
cd /d "%~dp0"

if not exist "IntelliQuizDesktop.exe" (
  echo ERROR: IntelliQuizDesktop.exe not found in this folder.
  echo Unzip the FULL IntelliQuizDesktop folder, then run this file again.
  pause
  exit /b 1
)

if not exist "_internal\" (
  echo ERROR: Missing _internal folder next to the EXE.
  echo Do not copy only the .exe — unzip the whole IntelliQuizDesktop folder.
  pause
  exit /b 1
)

echo Starting IntelliQuiz Desktop...
echo Keep this window open while you take the exam.
echo.
"IntelliQuizDesktop.exe"
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo.
  echo IntelliQuiz exited with code %EXITCODE%.
  pause
)
endlocal
exit /b %EXITCODE%
