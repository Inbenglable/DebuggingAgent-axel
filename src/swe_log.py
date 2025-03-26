import re
import time
from collections.abc import Callable
from os import get_terminal_size

from loguru import logger
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

# magenta 紫色
# blue 蓝色
# yellow 黄色
# green 绿色
# red 红色

logger_instance = logger
CONSOLE = Console()
PRINT_STDOUT = True



def remove_ansi_escape_sequences(text):
    # Regular expression to match ANSI escape sequences
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    # Substitute the ANSI escape sequences with an empty string
    return ansi_escape.sub('', text)


def init_logger(logger_path):
    logger.remove()
    logger.add(f"{logger_path}", mode='w', enqueue=True)



def terminal_width():
    try:
        return get_terminal_size().columns
    except OSError:
        return 80


WIDTH = min(120, terminal_width() - 10)


def log_exception(exception):
    logger_instance.exception(exception)


def print_banner(msg: str) -> None:
    if not PRINT_STDOUT:
        return

    banner = f" {msg} ".center(WIDTH, "=")
    CONSOLE.print()
    CONSOLE.print(banner, style="bold")
    CONSOLE.print()


def print_block(msg: str, block_title="", color='blue') -> None:
    # msg = remove_ansi_escape_sequences(msg)
    markdown = Markdown(msg)

    panel = Panel(
        markdown, title=block_title, title_align="left", border_style=color, width=WIDTH
    )
    CONSOLE.print(panel)



def log_msg(msg):
    logger_instance.info(msg)
    # logger_instance.info(remove_ansi_escape_sequences(msg))
    

def log_and_print(msg):
    logger_instance.info(msg)
    # logger_instance.info(remove_ansi_escape_sequences(msg))
    if PRINT_STDOUT:
        print(msg)

def log_and_cprint(msg, **kwargs):
    logger_instance.info(msg)
    if PRINT_STDOUT:
        CONSOLE.print(msg, **kwargs)


def log_and_always_print(msg):
    """
    A mode which always print to stdout, no matter what.
    Useful when running multiple tasks and we just want to see the important information.
    """
    logger_instance.info(msg)
    # always include time for important messages
    t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    CONSOLE.print(f"\n[{t}] {msg}")


def print_with_time(msg):
    """
    Print a msg to console with timestamp.
    """
    t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    CONSOLE.print(f"\n[{t}] {msg}")

def main():
    # 设置日志格式（可选）
    logger.remove()  # 移除默认的日志处理器
    logger.add("demo.log", rotation="1 MB")  # 添加一个文件日志处理器

    # 打印横幅
    print_banner("欢迎使用日志与控制台输出演示")

    # 打印不同类型的信息面板
    print_block("发现了一个关键问题：[file]函数A[/file]在处理输入时出现异常。需要<patched>修复函数A</patched>以确保稳定性。", "初始化123", color='blue')


    # 使用日志与打印结合的函数
    log_msg("这是一个普通的日志信息。")
    log_and_cprint("这是一个带有样式的控制台输出。", style="underline green")

    # 使用始终打印的函数
    log_and_always_print("这是一个重要的信息，始终显示在控制台。")

    # 仅在控制台打印带时间戳的信息
    print_with_time("这是一个带时间戳的消息。")

    # 模拟一个异常并记录
    try:
        1 / 0
    except Exception as e:
        log_exception(e)
        print_block(f"异常发生：{e}")


if __name__ == "__main__":
    main()