@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "BUILD_ROOT=%LOCALAPPDATA%\Temp\PoliigonLibraryOrganizerProBuild"
set "DIST_DIR=%BUILD_ROOT%\dist"
set "WORK_DIR=%BUILD_ROOT%\build"
set "SPEC_FILE=%PROJECT_DIR%PoliigonLibraryOrganizerPRO.spec"
set "OUTPUT_EXE=%PROJECT_DIR%dist\DB9_TextureModelCollectionTool.exe"

cd /d "%PROJECT_DIR%"

echo Installing dependencies...
pip install pyinstaller
pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo Building executable in local temp folder...
python -m PyInstaller --noconfirm --distpath "%DIST_DIR%" --workpath "%WORK_DIR%" "%SPEC_FILE%"
if errorlevel 1 goto :fail

if not exist "%PROJECT_DIR%dist" mkdir "%PROJECT_DIR%dist"

echo.
echo Copying executable back to project folder...
copy /Y "%DIST_DIR%\DB9_TextureModelCollectionTool.exe" "%OUTPUT_EXE%"
if errorlevel 1 goto :fail

echo.
echo Done.
echo EXE: %OUTPUT_EXE%
goto :end

:fail
echo.
echo Build failed.
exit /b 1

:end
endlocal
