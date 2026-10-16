# Build Windows em pasta: interface, ponte local e extensão do Edge.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata

raiz = Path(SPECPATH)
dados = collect_data_files("playwright", excludes=["driver/package/.local-browsers/**"])
dados += copy_metadata("google-generativeai", recursive=True)
dados += copy_metadata("groq", recursive=True)
dados += copy_metadata("winrt-runtime")
dados += [(str(raiz / ".env.example"), ".")]
dados += [(str(raiz / "edge_extension"), "edge_extension")]

analise = Analysis(
    [str(raiz / "app_noc.py")],
    pathex=[str(raiz)],
    binaries=collect_dynamic_libs("winrt"),
    datas=dados,
    hiddenimports=collect_submodules("google.ai.generativelanguage") + collect_submodules("groq") + collect_submodules("winrt"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
# O hook do Playwright também coleta dados: exclui navegadores antigos do venv.
analise.datas = [item for item in analise.datas if ".local-browsers" not in item[0].replace("\\", "/").split("/")]
analise.binaries = [item for item in analise.binaries if ".local-browsers" not in item[0].replace("\\", "/").split("/")]
pyz = PYZ(analise.pure)
exe = EXE(
    pyz,
    analise.scripts,
    [],
    exclude_binaries=True,
    name="OrquestradorNOC",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coleta = COLLECT(
    exe,
    analise.binaries,
    analise.datas,
    strip=False,
    upx=False,
    name="OrquestradorNOC",
)
