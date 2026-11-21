# -*- coding: utf-8 -*-
"""
start_guard.py —— 饮用水氯消毒剂量精准调控软件 外置守护进程 v3.0

适配当前软件框架：
  - 入口文件 main.py（位于软件根目录）
  - 退出码约定：
      0  = 正常退出（用户主动关闭）→ 守护进程一同结束
      99 = 计划性重启（每日凌晨维护性重启、健康监控触发）→ 守护进程 10 秒后拉起
      其他非零退出码 = 异常崩溃 → 按指数退避策略重启

使用方法:
  # 开发环境（软件是 .py 源码）
  python start_guard.py
  
  # 打包后（软件是 PyInstaller 生成的 exe）
  双击 start_guard.exe 即可
"""

import os
import sys
import time
import signal
import logging
import subprocess
from datetime import datetime

# ─── 日志配置 ────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [守护进程] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('guard.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)


class ProcessGuard:
    """外置看门狗：监控主程序并根据退出码决定重启策略"""

    def __init__(self, max_crashes=5, crash_window_seconds=300):
        """
        Args:
            max_crashes: 时间窗口内容许的最大异常崩溃次数
            crash_window_seconds: 崩溃统计时间窗口（秒）
        """
        # 自动定位主程序：支持 .py 源码运行与 PyInstaller 打包运行
        self.is_frozen = getattr(sys, 'frozen', False)
        
        # 确定工作目录（打包后为 exe 所在目录，源码为脚本所在目录）
        if self.is_frozen:
            self.work_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            self.work_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 按优先级查找主程序入口
        candidates = [
            os.path.join(self.work_dir, 'UV275Monitor.exe'),  # PyInstaller 打包后
            os.path.join(self.work_dir, 'main.exe'),          # 备选打包名
            os.path.join(self.work_dir, 'main.py'),           # 源码运行
        ]
        
        self.main_executable = None
        for path in candidates:
            if os.path.exists(path):
                self.main_executable = path
                logging.info(f"找到主程序: {path}")
                break
        
        if not self.main_executable:
            logging.error("未找到主程序入口！尝试的路径：")
            for path in candidates:
                logging.error(f"   - {path}")
            logging.error(f"当前工作目录: {self.work_dir}")
            logging.error(f"目录内容: {os.listdir(self.work_dir)}")
            sys.exit(1)
        
        self.max_crashes = max_crashes
        self.crash_window = crash_window_seconds
        self.crash_history = []
        self.current_process = None
        self._stop_requested = False

    def signal_handler(self, signum, frame):
        """处理 SIGTERM / SIGINT：优雅终止子进程"""
        logging.info(f"收到信号 {signum}，准备退出...")
        self._stop_requested = True
        
        if self.current_process and self.current_process.poll() is None:
            logging.info("终止子进程...")
            try:
                self.current_process.terminate()
                # 等待 5 秒给主程序清理资源的时间
                for _ in range(50):
                    if self.current_process.poll() is not None:
                        break
                    time.sleep(0.1)
                
                if self.current_process.poll() is None:
                    logging.warning("子进程未响应 terminate，强制 kill...")
                    self.current_process.kill()
            except Exception as e:
                logging.error(f"终止子进程时异常: {e}")
        
        sys.exit(0)

    def run(self):
        """主循环"""
        # 注册信号处理器（仅在平台支持时）
        try:
            if hasattr(signal, 'SIGTERM'):
                signal.signal(signal.SIGTERM, self.signal_handler)
            if hasattr(signal, 'SIGINT'):
                signal.signal(signal.SIGINT, self.signal_handler)
        except Exception as e:
            logging.warning(f"信号处理器注册失败（忽略）: {e}")

        logging.info("=" * 70)
        logging.info("饮用水氯消毒剂量精准调控软件 守护进程启动")
        logging.info(f"工作目录: {self.work_dir}")
        logging.info(f"目标程序: {self.main_executable}")
        logging.info(f"最大崩溃次数: {self.max_crashes} (窗口: {self.crash_window}秒)")
        logging.info("=" * 70)

        while not self._stop_requested:
            try:
                # 构建启动命令
                if self.main_executable.endswith('.py'):
                    cmd = [sys.executable, self.main_executable]
                else:
                    cmd = [self.main_executable]
                
                logging.info(f"启动命令: {' '.join(cmd)}")
                
                # 启动子进程
                # 不捕获 stdout/stderr（让主程序的日志直接进自己的 log 文件）
                # 避免管道被填满时阻塞子进程
                self.current_process = subprocess.Popen(
                    cmd,
                    cwd=self.work_dir,
                    # 在 Windows 上不继承控制台，避免 GUI 程序弹出黑框
                    creationflags=subprocess.CREATE_NO_WINDOW if (
                        os.name == 'nt' and self.is_frozen
                    ) else 0
                )
                
                pid = self.current_process.pid
                logging.info(f"主程序已启动 (PID: {pid})")
                
                # 阻塞等待主程序结束
                exit_code = self.current_process.wait()
                
                logging.info(f"主程序结束 (PID: {pid}, 退出码: {exit_code})")
                
                # 根据退出码决定后续行为
                if exit_code == 0:
                    # 用户主动正常退出 → 守护进程一同结束
                    logging.info("主程序正常退出，守护进程随之结束")
                    break
                
                elif exit_code == 99:
                    # 计划性重启：由 PlannedRestartManager 每日凌晨触发，
                    # 或由 HealthMonitor 触发，属于正常维护动作
                    logging.info("收到计划性重启信号 (Code 99)，10 秒后拉起主程序...")
                    # 清空崩溃历史（计划重启不计入异常）
                    self.crash_history.clear()
                    time.sleep(10)
                
                else:
                    # 任何其他非零退出码 = 异常崩溃
                    self.handle_crash(exit_code)
            
            except KeyboardInterrupt:
                logging.info("收到键盘中断信号，守护进程退出")
                if self.current_process and self.current_process.poll() is None:
                    try:
                        self.current_process.terminate()
                        time.sleep(2)
                        if self.current_process.poll() is None:
                            self.current_process.kill()
                    except Exception:
                        pass
                break
            
            except FileNotFoundError as e:
                logging.critical(f"找不到可执行文件: {e}")
                break
            
            except Exception as e:
                logging.error(f"守护进程循环异常: {e}", exc_info=True)
                time.sleep(30)
        
        logging.info("守护进程结束")

    def handle_crash(self, exit_code):
        """
        处理崩溃：指数退避 + 长等待兜底
        
        策略：
          1. 记录崩溃时间戳
          2. 清理窗口外的过期记录
          3. 若窗口内崩溃次数未达阈值 → 按次数指数退避重启
          4. 若达阈值 → 进入 30 分钟长等待，防止短时间内反复拉起拉挂
        """
        now = datetime.now()
        self.crash_history.append(now)
        
        # 清理过期的崩溃记录
        cutoff = now.timestamp() - self.crash_window
        self.crash_history = [t for t in self.crash_history if t.timestamp() > cutoff]
        
        crash_count = len(self.crash_history)
        logging.warning(
            f"主程序异常退出 | 退出码={exit_code} | "
            f"窗口内崩溃={crash_count}/{self.max_crashes} | "
            f"窗口={self.crash_window}秒"
        )
        
        if crash_count >= self.max_crashes:
            logging.critical("=" * 70)
            logging.critical(f"崩溃频率过高：{self.crash_window}秒内崩溃 {crash_count} 次")
            logging.critical(f"进入长等待模式（30 分钟），避免反复拉起")
            logging.critical("=" * 70)
            logging.critical("排查建议：")
            logging.critical("  1. 查看 uv275_monitor.log 了解主程序运行日志")
            logging.critical("  2. 查看 critical_error.log 了解严重错误")
            logging.critical("  3. 检查 UV275 传感器串口连接是否正常")
            logging.critical("  4. 检查 SQLite 数据库文件是否损坏")
            logging.critical("  5. 检查 MySQL 服务（水厂数据接入）是否正常")
            logging.critical("=" * 70)
            
            time.sleep(1800)  # 长等待 30 分钟
            self.crash_history.clear()
            logging.info("长等待结束，清空崩溃历史，重新开始监控")
            return
        
        # 指数退避（崩溃次数越多等待越长，上限 60 秒）
        wait_time = min(10 * crash_count, 60)
        logging.info(f"{wait_time} 秒后尝试自动重启（指数退避）...")
        time.sleep(wait_time)


if __name__ == "__main__":
    try:
        guard = ProcessGuard(max_crashes=5, crash_window_seconds=300)
        guard.run()
    except Exception as e:
        logging.critical(f"守护进程致命错误: {e}", exc_info=True)
        sys.exit(1)