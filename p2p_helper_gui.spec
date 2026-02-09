# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# List all your icon files here.
# PyInstaller will bundle them into the executable's temporary directory at runtime.
# The format is ('source_path', 'destination_folder_in_bundle')
# Using '.' for the destination folder places them in the root of the bundle.
icon_files = [
    ('p2p.ico', '.'),
    ('Cabos.ico', '.'),
    ('DexterWire.ico', '.'),
    ('eDonkey.ico', '.'),
    ('eMule.ico', '.'),
    ('FileNavigator.ico', '.'),
    ('FrostWire.ico', '.'),
    ('Gnucleus.ico', '.'),
    ('Gnutella.ico', '.'),
    ('Gnutella2.ico', '.'),
    ('KCeasy.ico', '.'),
    ('LemonWire.ico', '.'),
    ('Lphant.ico', '.'),
    ('LimeWire.ico', '.'),
    ('LuckyWire.ico', '.'),
    ('Morpheus.ico', '.'),
    ('MyNapster.ico', '.'),
    ('Napigator.ico', '.'),
    ('Napster.ico', '.'),
    ('NeoNapster.ico', '.'),
    ('OpenNapster.ico', '.'),
    ('Phex.ico', '.'),
    ('Swaptor.ico', '.'),
    ('TurboWire.ico', '.'),
    ('WinMX.ico', '.'),
    ('WireShare.ico', '.'),
    ('XNap.ico', '.'),
    ('XoloX.ico', '.')
]

a = Analysis(
    ['p2p_helper_gui.py'],
    pathex=[],
    binaries=[],
    datas=icon_files,  # This tells PyInstaller to bundle the icons
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='P2P Connection Helper', # This will be the name of the .exe file
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,         # This makes it a GUI application
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='p2p.ico',        # This sets the icon for the .exe file itself
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='p2p_helper_gui',
)
