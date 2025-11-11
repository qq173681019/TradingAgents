# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['a_share_gui_compatible.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('C:\\Users\\ext.jgu\\.pyenv\\pyenv-win\\versions\\3.11.4\\Lib\\site-packages\\akshare\\file_fold\\*', 'akshare\\file_fold\\'),
    ],
    hiddenimports=[
        'akshare',
        'yfinance',
        'pandas',
        'numpy',
        'requests',
        'urllib3',
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'tkinter.simpledialog',
        'threading',
        'json',
        'datetime',
        'time',
        'hashlib',
        'random',
        'os',
        'sys',
        'csv',
        'socket',
        'urllib.request',
        'urllib.parse',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch',
        'torchvision', 
        'tensorflow',
        'scipy',
        'matplotlib',
        'sympy',
        'IPython',
        'jupyter',
        'notebook',
        'PIL',
        'cv2',
        'sklearn',
        'seaborn',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='A股智能分析系统',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 不显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 可以添加图标文件
)
