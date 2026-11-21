import os
import sys
import time
import json
import shutil
import logging
import calendar
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from tkcalendar import DateEntry
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from datetime import datetime, timedelta
import csv

import warnings
import weakref
import atexit
import sqlite3
import queue
import hashlib
import configparser
from logging.handlers import RotatingFileHandler
from functools import lru_cache, wraps
from contextlib import contextmanager

from constants import LANGUAGES
from utils import retry_on_db_error, safe_gui_operation, global_exception_handler
from resources import resource_tracker
from config import ConfigManager, ConfigValidator
from database import DatabaseManager, DatabaseMaintenance
from data_processing import DataCache, DataArchiver, DataValidator
from system_monitor import MemoryManager, HealthMonitor, SimpleStructuredLogger
from plot_manager import PlotManager, PlotDebouncer
from sensor import SensorRecoveryManager, UV275SensorModbus
from app_managers import PlannedRestartManager, WatchdogTimer
from gui.english_filter import install_english_gui_filter

from gui.recovery import RecoveryMixin
from gui.backup import BackupMixin
from gui.settings import SettingsMixin
from gui.reports import ReportsMixin
from gui.database_ops import DatabaseOpsMixin
from gui.alarms import AlarmsMixin
from gui.display import DisplayMixin
from gui.monitoring import MonitoringMixin
from gui.export import ExportMixin
from gui.ui_builder import UIBuilderMixin
from gui.data_query import DataQueryMixin
from gui.pathogens import PathogensMixin
from waterplant_reader import WaterplantReaderMixin

install_english_gui_filter()

class UV275MonitorGUI(
    RecoveryMixin, BackupMixin, SettingsMixin, ReportsMixin,
    DatabaseOpsMixin, AlarmsMixin, DisplayMixin, MonitoringMixin,
    ExportMixin, UIBuilderMixin, DataQueryMixin, PathogensMixin,
    WaterplantReaderMixin
):
    """UV275水质监控系统主应用类"""

    def __init__(self, root):
        """初始化方法"""
        self.root = root
        self.logger = logging.getLogger(__name__)
        # 退出码管理
        self.exit_code = 0  # 0=正常退出，99=计划重启，1=异常退出

        # ========================================
        # 初始化所有线程同步对象
        # ========================================
        self.stop_event = threading.Event()
        self.sensor_lock = threading.RLock()
        self.alarm_lock = threading.RLock()
        self.monitoring_lock = threading.RLock()
        self.report_check_stop_event = threading.Event()
        
        # ========================================
        # 初始化基础属性
        # ========================================
        # 监控相关
        self.sensor = None
        self.monitoring = False
        self.monitor_thread = None
        self.last_normal_value = None
        
        # 报警系统
        self.alarm_history = []
        self.alarm_window = None
        self.last_alarm_time = None
        
        # 当前加氯量
        self.current_chlorine_dosage = 1.0
        
        # 经验值范围设置
        self.empirical_range = {'min': 0.0085, 'max': 0.0925}
        self.initial_period_days = 365

        # ========================================
        # 初始化日志和配置
        # ========================================
        self.struct_logger = SimpleStructuredLogger('uv275_monitor')
        self.config_manager = ConfigManager()

        # ========================================
        # 初始化管理器组件
        # ========================================
        # 传感器恢复管理器
        self.sensor_recovery = SensorRecoveryManager(
            max_failures=3,
            recovery_delay=60
        )

        # 数据库连接池
        self.db_manager = DatabaseManager(
            'uv275_data.db',
            pool_size=5
        )

        # 数据库维护
        self.db_maintenance = DatabaseMaintenance(
            self.db_manager,
            maintenance_interval=86400*7
        )
        self.db_maintenance.start()

        # 数据缓存
        self.data_cache = DataCache(ttl_seconds=60)

        # 数据归档器
        self.data_archiver = DataArchiver(self.db_manager, self.config_manager)
        
        # 现在可以安全启动归档线程（stop_event已存在）
        self.start_archive_check_thread()

        # 内存管理器
        self.memory_manager = MemoryManager(check_interval=300)

        # 健康监控器
        self.health_monitor = HealthMonitor(self, check_interval=60)

        # 看门狗定时器（防止监控线程卡死）
        self.watchdog = WatchdogTimer(timeout=600, app=self)
        self.watchdog.start()

        # ========================================
        # 注册资源
        # ========================================
        resource_tracker.register(self.db_manager, 'DatabaseManager')
        resource_tracker.register(self.memory_manager, 'MemoryManager')
        resource_tracker.register(self.health_monitor, 'HealthMonitor')
        resource_tracker.register(self, 'UV275MonitorGUI')

        # ========================================
        # 初始化工具类
        # ========================================
        self.data_validator = DataValidator(self.config_manager)
        self.plot_debouncer = PlotDebouncer(delay=0.3)
        self.gui_update_queue = queue.Queue(maxsize=100)

        # ========================================
        # 启动监控服务
        # ========================================
        self.health_monitor.start()
        self.memory_manager.start()
        
        # ========================================
        # 初始化文件路径
        # ========================================
        self.csv_file = 'uv275_data.csv'
        self.db_file = 'uv275_data.db'
        self.coefficients_file = 'pathogen_coefficients.json'
        self.serial_config_file = 'serial_config.json'
        self.calibration_file = 'calibration_offsets.json'
        self.preferences_file = 'user_preferences.json'
        self.reports_folder = 'reports'
        
        # 创建报告文件夹
        if not os.path.exists(self.reports_folder):
            os.makedirs(self.reports_folder)
            self.logger.info(f"创建报告文件夹: {self.reports_folder}")
        
        # 备份文件夹
        self.backup_folder = 'backups'
        if not os.path.exists(self.backup_folder):
            os.makedirs(self.backup_folder)
            self.logger.info(f"创建备份文件夹: {self.backup_folder}")
        
        # ========================================
        # 校零相关变量
        # ========================================
        self.calibration_offsets = {
            'uv275_absorbance': 0.0,
            'temperature': 0.0,
            'visible_absorbance': 0.0,
            'cod': 0.0,
            'turbidity': 0.0
        }
        self.calibration_enabled = True
        
        # ========================================
        # 加载配置
        # ========================================
        self.load_serial_config()
        self.load_calibration_offsets()
        self.load_coefficients()
        self.load_preferences()
        
        # ========================================
        # 初始化GUI相关变量
        # ========================================
        # 根据当前月份自动确定季节
        current_month = datetime.now().month
        if current_month in [12, 1, 2]:
            default_season = self.get_text('winter')
        elif current_month in [3, 4, 5]:
            default_season = self.get_text('spring')
        elif current_month in [6, 7, 8]:
            default_season = self.get_text('summer')
        else:
            default_season = self.get_text('autumn')
        
        # 当前选择的病原菌类型、季节和灭活率
        self.selected_pathogen = tk.StringVar(value="大肠杆菌")
        self.selected_season = tk.StringVar(value=default_season)
        self.selected_inactivation = tk.StringVar(value="4 log")
        
        # 图表显示参数选择
        chart_options = self.get_chart_param_options()
        first_key = list(chart_options.keys())[0]
        self.selected_chart_param = tk.StringVar(value=first_key)
        
        # 时间范围选择
        self.selected_time_range = tk.StringVar(value=self.get_text('1_day'))
        
        # 参数编辑相关变量
        self.param_a_var = tk.StringVar()
        self.param_b_var = tk.StringVar()
        
        # ========================================
        # 设置窗口和主题
        # ========================================
        self.root.title(self.get_text('title'))
        self.root.geometry("1600x900")
        
        # 初始化ttk样式
        self.style = ttk.Style()
        
        # 应用主题
        self.apply_theme()
        
        # ========================================
        # 初始化数据库
        # ========================================
        self.setup_database()
        
        # ========================================
        # 创建GUI界面
        # ========================================
        self.create_widgets()
        
        # ========================================
        # 绑定快捷键
        # ========================================
        self.bind_shortcuts()
        
        # ========================================
        # 延迟初始化显示
        # ========================================
        self.root.after(100, self._initialize_displays)
        
        # ========================================
        # 启动后台服务
        # ========================================
        # 启动自动备份线程
        if self.config_manager.getboolean('Database', 'backup_enabled', True):
            self.start_auto_backup_thread()

        # 启动报告生成检查线程
        self.start_report_check_thread()

        # 启动GUI更新队列检查
        self.check_gui_update_queue()

        # 修改此处：启动重启检查线程
        self.restart_manager = PlannedRestartManager(
            restart_hour=3,           # 每天凌晨3点重启
            memory_threshold_mb=800   # 内存阈值 800MB
        )
        self.start_restart_check_thread()
        
        # ========================================
        # 配置验证
        # ========================================
        validation_errors = []
        
        # 验证串口配置
        serial_errors = ConfigValidator.validate_serial_config(self.serial_config)
        validation_errors.extend([f"[串口] {e}" for e in serial_errors])
        
        # 验证数据库
        db_errors = ConfigValidator.validate_database(self.db_file)
        validation_errors.extend([f"[数据库] {e}" for e in db_errors])
        
        # 验证文件夹
        folders = {
            '报告': self.reports_folder,
            '备份': self.backup_folder
        }
        folder_errors = ConfigValidator.validate_folders(folders)
        validation_errors.extend([f"[文件夹] {e}" for e in folder_errors])
        
        # 显示验证结果
        if validation_errors:
            error_msg = "注意：配置验证发现问题:\n" + "\n".join(validation_errors)
            self.logger.warning(error_msg)
            messagebox.showwarning(
                "配置警告 / Configuration Warning",
                error_msg + "\n\n注意：系统可能无法正常工作！"
            )
        else:
            self.logger.info("配置验证通过")
        
        self.logger.info("UV275监控系统初始化完成")

        # 在窗口完全加载后自动开始监控
        self.root.after(2000, self.auto_restore_monitoring)
        self.init_waterplant_reader()
        # 恢复监测状态
        # ========================================
        self.root.after(3000, self.restore_monitoring_state)

    def __del__(self):
        """清理资源（由资源追踪器自动调用）"""
        try:
            self.logger.info("清理UV275MonitorGUI资源...")
            
            # 停止监控
            if hasattr(self, 'monitoring') and self.monitoring:
                self.stop_event.set()
                if self.monitor_thread and self.monitor_thread.is_alive():
                    self.monitor_thread.join(timeout=3.0)
            
            # 停止各种管理器
            if hasattr(self, 'health_monitor'):
                self.health_monitor.stop()
            
            if hasattr(self, 'memory_manager'):
                self.memory_manager.stop()
            
            if hasattr(self, 'watchdog'):
                self.watchdog.stop()

            if hasattr(self, 'stop_waterplant_reader'):
                self.stop_waterplant_reader()

            # 关闭数据库
            if hasattr(self, 'db_manager'):
                self.db_manager.close_all()
            
            self.logger.info("资源清理完成")
        except Exception as e:
            self.logger.error(f"清理资源失败: {e}")

    def _initialize_displays(self):
        """延迟初始化显示（确保所有widget已创建）"""
        try:
            self.update_parameter_display()
            self.update_data_display()
            self.update_waterplant_display()   # 新增：初始化水厂数据面板
            self.update_plots()
            self.logger.info("数据显示初始化完成")
        except Exception as e:
            self.logger.error(f"初始化显示失败: {e}", exc_info=True)
    
    def check_gui_update_queue(self):
        """定期检查并处理GUI更新队列"""
        try:
            processed = 0
            max_batch = 10  # 每次最多处理10个更新任务
            
            while processed < max_batch and not self.gui_update_queue.empty():
                try:
                    update_func = self.gui_update_queue.get_nowait()
                    update_func()
                    processed += 1
                except queue.Empty:
                    break
                except Exception as e:
                    self.logger.error(f"处理GUI更新任务失败: {e}", exc_info=True)
            
            if processed > 0:
                self.logger.debug(f"处理了{processed}个GUI更新任务")
                
        except Exception as e:
            self.logger.error(f"检查GUI更新队列失败: {e}")
        finally:
            # 根据队列状态调整检查间隔
            interval = 50 if not self.gui_update_queue.empty() else 100
            self.root.after(interval, self.check_gui_update_queue)

    def on_closing(self):
        """根据情况设置不同退出码"""
        with self.monitoring_lock:
            is_monitoring = self.monitoring
        
        if is_monitoring:
            confirm_msg = (
                "注意：监控正在运行中\n\n"
                "确认退出将：\n"
                "• 停止数据采集\n"
                "• 关闭所有连接\n"
                "• 守护进程不会自动重启\n\n"
                "是否确认退出？"
            )
            
            if not messagebox.askokcancel("确认退出 / Confirm Exit", confirm_msg):
                # 用户取消，直接返回，不退出
                return
            
            self.logger.info("用户确认退出，停止监控...")
            
            # 停止监控
            with self.monitoring_lock:
                self.monitoring = False
            self.stop_event.set()
            # 保存状态为False
            self.restart_manager.save_monitoring_state(False, self.serial_config)
            self.logger.info("已清除监控状态（用户手动退出）")                        
            self.exit_code = 0
            self.cleanup_and_exit()
        else:
            # 未在监控中，直接退出
            self.exit_code = 0
            self.cleanup_and_exit()

    def cleanup_and_exit(self):
            """退出前保存状态，设置退出码供守护进程判断是否需要重启"""
            try:
                self.logger.info("执行程序清理...")
                #self.stop_monitor() # 已注释
                
                if hasattr(self, 'restart_manager'):
                    self.restart_manager.stop()
                
                if hasattr(self, 'db'):
                    self.db.close()
                    
            except Exception as e:
                self.logger.error(f"清理异常: {e}")
            finally:
                # 获取 exit_code
                # 如果是正常点击退出，代码会设为 0
                # 如果是计划重启，代码会设为 99
                code = getattr(self, 'exit_code', 0)
                self.logger.info(f"进程即将结束，退出码: {code}")
                
                try:
                    self.root.destroy()
                except:
                    pass
                
                # 使用 os._exit 确保在多线程环境下能干净利落地退出
                import os
                os._exit(code)

    # 数据验证方法
