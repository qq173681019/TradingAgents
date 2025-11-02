# -*- mode: python ; coding: utf-8 -*-
import sys
import os

# 添加tkinter相关路径
tkinter_path = os.path.join(sys.prefix, 'tcl')
tk_path = os.path.join(sys.prefix, 'tk')

a = Analysis(
    ['a_share_gui_compatible.py'],
    pathex=[],
    binaries=[],
    datas=[
        (os.path.join(sys.prefix, 'DLLs', 'tcl86t.dll'), '.'),
        (os.path.join(sys.prefix, 'DLLs', 'tk86t.dll'), '.'),
        (os.path.join(sys.prefix, 'DLLs', '_tkinter.pyd'), '.'),
    ],
    hiddenimports=[
        'tkinter', 
        'tkinter.ttk', 
        'tkinter.messagebox', 
        'tkinter.filedialog',
        'tkinter.scrolledtext',
        '_tkinter'
    ],
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
    name='A股智能分析系统',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 改为True以便看到错误信息
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)