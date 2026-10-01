# -*- mode: python ; coding: utf-8 -*-
import sys
if sys.platform != 'win32':
    raise SystemExit('This spec builds Windows only. Linux packaging needs its own backend and build validation.')
a=Analysis(['desktop.py'],pathex=[],binaries=[],datas=[('static','static'),('update-portable.ps1','.')],hiddenimports=['webview.platforms.edgechromium'],hookspath=[],hooksconfig={},runtime_hooks=[],excludes=['PyQt5','PyQt6','PySide2','PySide6','cefpython3','webview.platforms.qt','webview.platforms.gtk'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='BackloGame',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,icon='static/app-icon.ico')
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='BackloGame')
