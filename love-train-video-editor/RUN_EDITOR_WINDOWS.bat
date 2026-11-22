@echo off
setlocal
cd /d "%~dp0"
echo ===========================================
echo THE LOVE TRAIN NATION - VIDEO EDITOR
echo ===========================================
echo.
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher not found. Install Python 3.10+ and add it to PATH.
  pause
  exit /b 1
)
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo FFmpeg not found. Install FFmpeg and add its bin directory to PATH.
  pause
  exit /b 1
)
where ffprobe >nul 2>nul
if errorlevel 1 (
  echo FFprobe not found. Install a full FFmpeg build.
  pause
  exit /b 1
)
py -m pip show faster-whisper >nul 2>nul
if errorlevel 1 (
  echo Installing local transcription package...
  py -m pip install faster-whisper
  if errorlevel 1 (
    echo Package installation failed.
    pause
    exit /b 1
  )
)
set /p "VIDEO=Full path to source MP4 (drag file here, then Enter): "
set "VIDEO=%VIDEO:"=%"
if not exist "%VIDEO%" (
 echo Video file not found: %VIDEO%
 pause
 exit /b 1
)
echo.
echo [1] Malate Market - ALL 4 Shorts
echo [2] Malate Market - Short 1 only (recommended first test)
echo [3] Generic long-form edit (landscape)
set /p "CHOICE=Choose 1, 2 or 3: "
if "%CHOICE%"=="1" (
 py "%~dp0lovetrain_editor.py" --input "%VIDEO%" --short all --threads 4 --out "%~dp0LoveTrain_Exports"
) else if "%CHOICE%"=="2" (
 py "%~dp0lovetrain_editor.py" --input "%VIDEO%" --short 1 --threads 4 --out "%~dp0LoveTrain_Exports"
) else if "%CHOICE%"=="3" (
 py "%~dp0lovetrain_editor.py" --mode long --input "%VIDEO%" --threads 4 --out "%~dp0LoveTrain_Exports"
) else (
 echo Invalid choice.
 pause
 exit /b 1
)
echo.
echo Finished. Check the LoveTrain_Exports folder and the messages above.
pause
