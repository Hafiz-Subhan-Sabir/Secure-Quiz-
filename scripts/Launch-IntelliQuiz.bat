@echo off
setlocal EnableExtensions

REM OpenCV webcam inside the frozen EXE fails when the install path contains spaces
REM (e.g. "D:\Secure Quiz\..."). Auto-run from %LOCALAPPDATA%\IntelliQuizDesktop instead.
echo %~dp0| findstr /C:" " >nul
if not errorlevel 1 (
  if /I not "%~dp0"=="%LOCALAPPDATA%\IntelliQuizDesktop\" (
    echo.
    echo NOTE: Folder path has spaces — that breaks the PC webcam with this EXE.
    echo Syncing to a safe folder and launching from there:
    echo   %LOCALAPPDATA%\IntelliQuizDesktop
    echo.
    mkdir "%LOCALAPPDATA%\IntelliQuizDesktop" 2>nul
    robocopy "%~dp0." "%LOCALAPPDATA%\IntelliQuizDesktop" /E /XO /R:1 /W:1 /NFL /NDL /NJH /NJS /NP >nul
    start "IntelliQuiz" /D "%LOCALAPPDATA%\IntelliQuizDesktop" "%LOCALAPPDATA%\IntelliQuizDesktop\Launch IntelliQuiz.bat"
    exit /b 0
  )
)

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
echo Close Windows Camera / Zoom / Teams before starting if webcam fails.
echo Running from: %CD%
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
