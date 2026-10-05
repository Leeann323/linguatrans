# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

打包要点：
    - rapidocr 与 faster-whisper 都有数据文件，必须整包收集
    - 语音模型不打进包里，首次使用时由程序自行下载，避免体积过大
    - 界面用 PySide6，需要收集 Qt 插件
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = []
binaries = []
hiddenimports = []

# OCR 引擎的模型与配置文件
datas += collect_data_files("rapidocr_onnxruntime")
hiddenimports += collect_submodules("rapidocr_onnxruntime")

# onnxruntime 的动态库
datas += collect_data_files("onnxruntime")

# 语音识别
hiddenimports += collect_submodules("faster_whisper")
hiddenimports += collect_submodules("ctranslate2")
# faster_whisper 自带 assets 目录，里面有静音检测用的 onnx 模型，
# 不收集的话打包后运行会报模型文件不存在
datas += collect_data_files("faster_whisper")

# PDF 与 Word
hiddenimports += ["pymupdf", "fitz", "docx"]
hiddenimports += collect_submodules("pymupdf")

a = Analysis(
    ["entry.py"],
    pathex=[".."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter", "matplotlib", "pandas", "scipy", "IPython",
        # 界面用 PySide6，OpenCV 只做图像处理，headless 版不带 Qt
        "PyQt5", "PyQt6", "PySide2",
        # 注意：不能排除 av。faster_whisper 在包初始化时就 import av，
        # 即使我们绕开它自带的解码器，导入仍会失败。
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="linguatrans",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="linguatrans",
)
