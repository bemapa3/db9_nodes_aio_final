@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "BUILD_ROOT=%LOCALAPPDATA%\Temp\PoliigonLibraryOrganizerProNuitka"
set "OUTPUT_DIR=%BUILD_ROOT%\out"
set "OUTPUT_EXE=%PROJECT_DIR%dist\DB9_TextureModelCollectionTool_nuitka.exe"

cd /d "%PROJECT_DIR%"

echo Installing public-build dependencies...
python -m pip install --upgrade pip
python -m pip install nuitka ordered-set zstandard
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail

if not exist "%PROJECT_DIR%dist" mkdir "%PROJECT_DIR%dist"

echo.
echo Building protected executable with Nuitka...
python -m nuitka ^
  --onefile ^
  --windows-console-mode=disable ^
  --enable-plugin=tk-inter ^
  --assume-yes-for-downloads ^
  --windows-icon-from-ico="%PROJECT_DIR%logo.ico" ^
  --onefile-windows-splash-screen-image="%PROJECT_DIR%logo.png" ^
  --company-name="DB9.Visual" ^
  --product-name="DB9_TextureModelCollectionTool" ^
  --file-version="2.0.0.0" ^
  --product-version="2.0.0.0" ^
  --file-description="Made by DB9.Visual And Texture Collect By I8 Studio" ^
  --copyright="DB9.Visual / I8 Studio" ^
  --output-dir="%OUTPUT_DIR%" ^
  --output-filename="DB9_TextureModelCollectionTool_nuitka.exe" ^
  --include-data-files="%PROJECT_DIR%logo.ico=logo.ico" ^
  --include-data-files="%PROJECT_DIR%logo.png=logo.png" ^
  --include-data-files="%PROJECT_DIR%blender_addon.py=blender_addon.py" ^
  --include-data-files="%PROJECT_DIR%max_addon_macroscript.ms=max_addon_macroscript.ms" ^
  app.py
if errorlevel 1 goto :fail

echo.
echo Copying executable back to project folder...
copy /Y "%OUTPUT_DIR%\DB9_TextureModelCollectionTool_nuitka.exe" "%OUTPUT_EXE%"
if errorlevel 1 goto :fail

echo.
echo Done.
echo EXE: %OUTPUT_EXE%
goto :end

:fail
echo.
echo Nuitka build failed.
exit /b 1

:end
endlocal
