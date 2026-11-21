import sys
from datetime import datetime
import time
import logging
import tkinter as tk
from tkinter import messagebox
import sqlite3
from functools import wraps

def global_exception_handler(exc_type, exc_value, exc_traceback):
    """全局未捕获异常处理器"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    import traceback
    error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    
    try:
        with open('critical_error.log', 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"未捕获的异常:\n{error_msg}\n")
    except Exception as log_err:
        import sys
        print(f"[日志写入失败] {log_err}", file=sys.stderr)
    
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "严重错误 / Critical Error",
            "程序遇到未处理的异常，将退出\n"
            "The program encountered an unhandled exception and will exit\n\n"
            "详情请查看 critical_error.log\n"
            "Please check critical_error.log for details"
        )
        root.destroy()
    except:
        pass
    
    sys.exit(1)


def retry_on_db_error(max_retries=3, delay=0.5, backoff=2.0):
    """数据库操作重试装饰器（指数退避）
    
    Args:
        max_retries: 最大重试次数
        delay: 初始延迟（秒）
        backoff: 退避系数
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            current_delay = delay
            last_error = None
            
            while retries <= max_retries:
                try:
                    return func(*args, **kwargs)
                except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
                    last_error = e
                    retries += 1
                    
                    if retries > max_retries:
                        logging.error(f"数据库操作失败，已重试{max_retries}次: {e}")
                        raise
                    
                    logging.warning(
                        f"数据库操作失败，{current_delay:.1f}秒后重试 "
                        f"({retries}/{max_retries}): {e}"
                    )
                    time.sleep(current_delay)
                    current_delay *= backoff  # 每次失败等待时间翻倍，避免数据库锁的时候一直狂重试
            
            raise last_error
        return wrapper
    return decorator

def safe_gui_operation(error_handler=None):
    """GUI操作安全装饰器（捕获Tkinter异常）"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except tk.TclError as e:
                # GUI组件已销毁或不可用
                logging.error(f"GUI组件不可用: {e}")
                if error_handler:
                    try:
                        error_handler(e)
                    except:
                        pass
            except Exception as e:
                logging.error(f"GUI操作失败: {e}", exc_info=True)
                if error_handler:
                    try:
                        error_handler(e)
                    except:
                        pass
        return wrapper
    return decorator

