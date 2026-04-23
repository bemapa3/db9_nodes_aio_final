# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

project_dir = Path(SPEC).resolve().parent
app_script = project_dir / "app.py"
icon_file = project_dir / "logo.ico"

datas = []
for name in ("logo.ico", "logo.png", "blender_addon.py", "max_addon_macroscript.ms"):
    path = project_dir / name
    if path.exists():
        datas.append((str(path), "."))


a = Analysis(
    [str(app_script)],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DB9_TextureModelCollectionTool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_file) if icon_file.exists() else None,
)
