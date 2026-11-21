import sys
import warnings
import logging
import tkinter as tk
from tkinter import messagebox
from logging.handlers import RotatingFileHandler
import matplotlib.pyplot as plt

# ============================================================
# Windows 高 DPI 感知（让 GUI 在高分屏上锐利显示）
# 必须在创建任何 Tk 窗口之前调用，否则不生效
# ============================================================
if sys.platform == 'win32':
    try:
        from ctypes import windll
        # Per-Monitor v2 DPI 感知（Windows 10 1703+，最佳）
        windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            # System DPI 感知（Windows 8.1+）
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                # 兜底：Windows 7 旧 API
                windll.user32.SetProcessDPIAware()
            except Exception:
                pass

from utils import global_exception_handler
from gui import UV275MonitorGUI
from gui.splash import StartupPage

# matplotlib 中文字体与警告设置
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['xtick.direction'] = 'in'
plt.rcParams['ytick.direction'] = 'in'
warnings.filterwarnings('ignore')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(threadName)-10s] %(levelname)-8s: %(message)s',
    handlers=[
        RotatingFileHandler(
            'uv275_monitor.log',
            maxBytes=10*1024*1024,
            backupCount=5,
            encoding='utf-8'
        )
    ]
)

if __name__ == "__main__":
    sys.excepthook = global_exception_handler

    try:
        root = tk.Tk()
        # ─── Tk 缩放因子调整（与 DPI 感知配合，让字体按系统缩放渲染）───
        try:
            # 读取 Windows 当前 DPI（96 为 100% 缩放的基准值）
            from ctypes import windll
            dpi = windll.user32.GetDpiForSystem()
            scaling = dpi / 72.0   # tk 内部使用 72 DPI 作为字体基准
            root.tk.call('tk', 'scaling', scaling)
        except Exception:
            pass

        def launch_monitor():
            """Replace the startup page with the existing monitoring interface."""
            try:
                startup_page.destroy()
                root.update_idletasks()
                # Keep a reference on the root for the complete Tk lifecycle.
                root.uv275_app = UV275MonitorGUI(root)
            except Exception as startup_error:
                logging.critical(
                    f"监控界面初始化失败: {startup_error}",
                    exc_info=True,
                )
                messagebox.showerror(
                    "启动失败",
                    f"监控界面初始化失败:\n{startup_error}",
                )
                root.destroy()

        startup_page = StartupPage(root, launch_monitor)
        root.mainloop()
    except Exception as e:
        logging.critical(f"程序启动失败: {e}", exc_info=True)
        try:
            messagebox.showerror("启动失败", f"软件启动时发生严重错误:\n{e}")
        except Exception:
            pass
        sys.exit(1)
