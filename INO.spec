# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files
import os

datas = [
    ('assets', 'assets'),
    ('ufo', 'ufo'),
    ('google-key.json', '.'),
]

datas += collect_data_files('gradio_client', include_py_files=False)

#    원본: ./ufo/config/*, 대상: ufo/config/*
config_src = os.path.join('ufo', 'config')
if os.path.isdir(config_src):
    # collect_data_files 로 간편하게 가져올 수도 있지만, 명시적으로 추가
    for root, _, files in os.walk(config_src):
        for fname in files:
            src = os.path.join(root, fname)
            # 상대경로로 ufo/config/... 형태를 유지
            rel_path = os.path.relpath(root, '.')  
            datas.append((src, rel_path))


a = Analysis(
    ['gui.py'],
    pathex=[],
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
    name='INO',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
