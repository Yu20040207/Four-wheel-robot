# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置：在 face_recognition_system 目录下执行 pyinstaller app.spec

import os
import importlib.util

project_dir = SPECPATH

# face_recognition 预训练模型
face_model_datas = []
try:
    spec = importlib.util.find_spec('face_recognition_models')
    if spec and spec.submodule_search_locations:
        models_dir = os.path.join(spec.submodule_search_locations[0], 'models')
        if os.path.isdir(models_dir):
            face_model_datas = [(models_dir, 'face_recognition_models/models')]
except Exception:
    pass

datas = [
    (os.path.join(project_dir, 'templates'), 'templates'),
    (os.path.join(project_dir, 'static'), 'static'),
] + face_model_datas

hiddenimports = [
    'face_recognition_models',
    'paho.mqtt.client',
    'cv2',
    'numpy',
    'PIL',
    'ultralytics',
    'engineio.async_drivers.threading',
]

a = Analysis(
    ['app.py'],
    pathex=[project_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'tkinter', 'pytest', 'IPython', 'jupyter'],
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
    name='OpenMV_FaceSystem',
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
