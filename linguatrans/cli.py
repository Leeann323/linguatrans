"""命令行入口：既能启动界面，也能在无界面环境下跑完整流程。

图形界面：  linguatrans
导入识别：  linguatrans extract <文件> [-o 项目目录]
导出 Word： linguatrans word <项目目录> -o 输出.docx
导出字幕：  linguatrans subs <项目目录> -o 输出目录
烧录硬字幕：linguatrans burn <项目目录> --video 视频.mp4 -o 输出.mp4
环境自检：  linguatrans doctor
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _load_store(dir_path: str):
    from .core.store import ProjectStore

    store = ProjectStore(dir_path)
    if not store.exists:
        print(f"错误：目录中没有项目文件：{dir_path}", file=sys.stderr)
        raise SystemExit(2)
    return store


def cmd_gui(args) -> int:
    from PySide6.QtWidgets import QApplication

    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


def cmd_extract(args) -> int:
    from .core.store import ProjectStore
    from .io import document

    src = Path(args.source)
    if not src.exists():
        print(f"错误：文件不存在：{src}", file=sys.stderr)
        return 2

    kind = document.detect_kind(src)
    if kind == document.MediaKind.VIDEO:
        from .io.asr import captions_to_segments, transcribe

        caps, lang = transcribe(src, args.model)
        from .core.model import MediaKind, Project

        proj = Project(name=src.stem, kind=MediaKind.VIDEO, source_path=str(src))
        for seg in captions_to_segments(caps):
            proj.add_segment(seg.source, seg.kind, seg.start, seg.end)
        print(f"识别语言 {lang}，共 {proj.total} 句")
    else:
        proj = document.import_auto(src, args.lang, not args.no_split)

    out_dir = Path(args.output) if args.output else src.parent / f"{src.stem}_linguatrans"
    store = ProjectStore(out_dir)
    store.save(proj)
    print(f"已提取 {proj.total} 句 -> {out_dir}")
    return 0


def cmd_word(args) -> int:
    from .io import word

    store = _load_store(args.project)
    proj = store.load()
    out = args.output or f"{proj.name}.docx"
    path = word.export_word(proj, out, style=args.style, asset_dir=store.asset_dir)
    print(f"已导出 {path}（{proj.done}/{proj.total} 句已译）")
    return 0


def cmd_subs(args) -> int:
    from .io import video

    store = _load_store(args.project)
    proj = store.load()
    out = args.output or str(Path(args.project) / "subtitles")
    res = video.export_soft_subtitles(proj.source_path, proj, out,
                                      bilingual=not args.mono)
    print(f"已导出 {res['srt']}\n已导出 {res['ass']}")
    return 0


def cmd_burn(args) -> int:
    from .io import video

    store = _load_store(args.project)
    proj = store.load()
    video_path = args.video or proj.source_path
    out = args.output or str(Path(video_path).with_name(Path(video_path).stem + "_sub.mp4"))
    print("开始烧录，需重新编码，请稍候……")
    path = video.burn_subtitles(video_path, proj, out, bilingual=not args.mono)
    print(f"已输出 {path}")
    return 0


def cmd_doctor(args) -> int:
    """检查运行环境，把缺失项列出来。"""
    import platform
    import shutil

    print("LinguaTrans 环境自检")
    print(f"  系统      {platform.system()} {platform.release()}")
    print(f"  Python    {platform.python_version()}")

    ok = True
    for tool, hint in [
        ("ffmpeg", "视频与音频功能需要 ffmpeg"),
        ("ffprobe", "读取媒体时长需要 ffprobe"),
    ]:
        found = shutil.which(tool)
        print(f"  {tool:<9} {'已安装 ' + found if found else '缺失   ' + hint}")
        ok = ok and bool(found)

    for mod, hint in [
        ("PySide6", "图形界面"),
        ("rapidocr_onnxruntime", "屏幕取词"),
        ("faster_whisper", "语音识别"),
        ("pymupdf", "PDF 导入"),
        ("docx", "Word 导出"),
    ]:
        try:
            __import__(mod)
            print(f"  {mod:<20} 可用")
        except Exception:
            print(f"  {mod:<20} 缺失   {hint}")
            ok = False

    print("自检结果：", "全部就绪" if ok else "存在缺失，请按上面提示安装")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="linguatrans",
        description="面向人工翻译者的原文提取与逐句翻译工具",
    )
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("gui", help="启动图形界面（默认）")

    e = sub.add_parser("extract", help="从文件提取原文并生成项目")
    e.add_argument("source")
    e.add_argument("-o", "--output")
    e.add_argument("--lang", default="en")
    e.add_argument("--model", default="small", help="语音识别模型档位")
    e.add_argument("--no-split", action="store_true", help="不按句切分，保留整段")
    e.set_defaults(func=cmd_extract)

    w = sub.add_parser("word", help="导出译文 Word")
    w.add_argument("project")
    w.add_argument("-o", "--output")
    w.add_argument("--style", default="bilingual",
                   choices=["bilingual", "target", "source"])
    w.set_defaults(func=cmd_word)

    s = sub.add_parser("subs", help="导出软字幕 srt 与 ass")
    s.add_argument("project")
    s.add_argument("-o", "--output")
    s.add_argument("--mono", action="store_true", help="只输出原文，不输出译文")
    s.set_defaults(func=cmd_subs)

    b = sub.add_parser("burn", help="烧录硬字幕到视频")
    b.add_argument("project")
    b.add_argument("--video", help="视频路径，默认用项目记录的源文件")
    b.add_argument("-o", "--output")
    b.add_argument("--mono", action="store_true")
    b.set_defaults(func=cmd_burn)

    d = sub.add_parser("doctor", help="检查运行环境")
    d.set_defaults(func=cmd_doctor)

    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not argv:
        return cmd_gui(None)
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        return cmd_gui(args)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
