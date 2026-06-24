@echo off
chcp 65001 >nul
echo ========================================
echo   CardRead2 Nuitka Build Script
echo ========================================
echo.

set ENTRY=src\web\main.py
set ICON=src\icon.ico
set OUTPUT_DIR=dist
set APP_NAME=CardRead2
set VENV=.venv

if not exist %ENTRY% (
    echo [ERROR] Entry file not found: %ENTRY%
    pause
    exit /b 1
)

if not exist %ICON% (
    echo [WARNING] Icon file not found: %ICON%, building without icon
    set ICON_FLAG=
) else (
    set ICON_FLAG=--windows-icon-from-ico=%ICON%
)

echo [0/3] Adding build folders to Windows Defender exclusions...
powershell -Command "try { Add-MpExclusion -Path '%CD%\dist' -ErrorAction Stop; Add-MpExclusion -Path '%CD%\build' -ErrorAction Stop; echo '  Defender exclusions added.' } catch { echo '  Skipped (run as Admin to add exclusions).' }"
echo.

echo [1/3] Activate venv and install build dependencies...
call %VENV%\Scripts\activate.bat
pip install nuitka ordered-set zstandard pythonnet pywebview --quiet
echo Done.
echo.

echo [2/3] Cleaning previous build...
if exist build rd /s /q build
if exist %OUTPUT_DIR% rd /s /q %OUTPUT_DIR%
if exist %APP_NAME%.dist rd /s /q %APP_NAME%.dist
if exist %APP_NAME%.onefile-build rd /s /q %APP_NAME%.onefile-build
if exist %APP_NAME%.exe del /f %APP_NAME%.exe
echo Done.
echo.

echo [3/3] Building with Nuitka (onefile mode)...
python -m nuitka ^
    --standalone ^
    --onefile ^
    --jobs=4 ^
    --output-dir=%OUTPUT_DIR% ^
    --output-filename=%APP_NAME%.exe ^
    %ICON_FLAG% ^
    --windows-console-mode=disable ^
    --no-prefer-source-code ^
    --include-package=src ^
    --include-package=confull ^
    --include-package=chardet ^
    --include-package=loguru ^
    --include-package=ebooklib ^
    --include-package=bs4 ^
    --include-package=lxml ^
    --include-package=mistune ^
    --include-package=pypinyin ^
    --include-package-data=pypinyin ^
    --include-module=clr ^
    --include-package=clr_loader ^
    --include-package=pythonnet ^
    --include-package=bottle ^
    --include-package=proxy_tools ^
    --include-package=webview ^
    --include-module=webview.platforms.winforms ^
    --include-module=webview.platforms.edgechromium ^
    --include-package-data=pythonnet ^
    --include-package-data=clr_loader ^
    --include-package-data=webview ^
    --include-data-dir=src/web/static=static ^
    --include-data-files=src/icon.ico=icon.ico ^
    --nofollow-import-to=tkinter ^
    --nofollow-import-to=unittest ^
    --nofollow-import-to=test ^
    --disable-plugin=pywebview ^
    --assume-yes-for-downloads ^
    --remove-output ^
    %ENTRY%

if not exist "%OUTPUT_DIR%\%APP_NAME%.exe" (
    echo.
    echo [ERROR] Build failed! Output exe not found.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Build SUCCESS!
echo   Output: %OUTPUT_DIR%\%APP_NAME%.exe
echo ========================================
pause