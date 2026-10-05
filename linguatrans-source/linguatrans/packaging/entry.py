"""打包入口。

直接双击可执行文件时启动图形界面；
带命令行参数运行时走命令行子命令，便于脚本调用。
"""

import multiprocessing
import sys

from linguatrans.cli import main

if __name__ == "__main__":
    # 打包后多进程与语音识别库需要这一行，否则会重复启动
    multiprocessing.freeze_support()
    raise SystemExit(main(sys.argv[1:]))
