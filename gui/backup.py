# 本文件为 UV275MonitorGUI 的 Mixin，通过多继承组合到主类中

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
from database import DatabaseManager
import sqlite3

class BackupMixin:
    """数据库备份、恢复与归档相关方法"""

    def validate_sensor_data(self, data):
        """验证UV275传感器数据有效性"""
        required_keys = [
            'temperature', 'humidity', 'uv275_absorbance',
            'visible_absorbance', 'cod', 'turbidity'
        ]
        
        # 检查必需字段
        for key in required_keys:
            if key not in data or data[key] is None:
                self.logger.warning(f"缺少必需字段: {key}")
                return False
        
        # 从配置文件读取验证范围
        temp_min = self.config_manager.getfloat('DataValidation', 'temp_min', 4)
        temp_max = self.config_manager.getfloat('DataValidation', 'temp_max', 40)
        uv275_min = self.config_manager.getfloat('DataValidation', 'uv275_min', 0)
        uv275_max = self.config_manager.getfloat('DataValidation', 'uv275_max', 5)
        
        # 检查数值范围
        if not (temp_min <= data['temperature'] <= temp_max):
            self.logger.warning(f"温度超出范围: {data['temperature']}")
            return False
        
        if not (uv275_min <= data['uv275_absorbance'] <= uv275_max):
            self.logger.warning(f"UV275超出范围: {data['uv275_absorbance']}")
            return False
        
        return True
    
    # 自动备份线程
    def start_auto_backup_thread(self):
        """启动自动备份线程"""
        def auto_backup_loop():
            backup_interval = self.config_manager.getint('Database', 'backup_interval', 86400)
            while True:
                try:
                    time.sleep(backup_interval)
                    self.backup_database()
                    self.clean_old_backups()
                except Exception as e:
                    self.logger.error(f"自动备份失败: {e}")
        
        backup_thread = threading.Thread(target=auto_backup_loop, daemon=True)
        backup_thread.start()
        self.logger.info("自动备份线程已启动")
    
    # 数据库备份方法
    def backup_database(self):
        """使用 SQLite API 的安全备份"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = f"backup_{timestamp}.db"
            backup_path = os.path.join(self.backup_folder, backup_file)
            
            # 使用 SQLite 备份 API
            with self.db_manager.get_connection() as source_conn:
                # 强制执行 Checkpoint，确保 WAL 数据写入主文件
                source_conn.execute("PRAGMA wal_checkpoint(FULL)")
                
                # 创建目标连接
                dest_conn = sqlite3.connect(backup_path)
                try:
                    # 使用 backup API 进行在线备份
                    with dest_conn:
                        source_conn.backup(dest_conn)
                    self.logger.info(f"数据库安全备份完成: {backup_path}")
                finally:
                    dest_conn.close()
            
            return backup_path
            
        except Exception as e:
            self.logger.error(f"数据库备份失败: {e}")
            return None
    
    # 清理旧备份
    def clean_old_backups(self):
        """清理旧备份文件"""
        try:
            retention_days = self.config_manager.getint('Database', 'backup_retention_days', 7)
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            
            for filename in os.listdir(self.backup_folder):
                if filename.startswith('backup_') and filename.endswith('.db'):
                    filepath = os.path.join(self.backup_folder, filename)
                    file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                    
                    if file_time < cutoff_date:
                        os.remove(filepath)
                        self.logger.info(f"已删除旧备份: {filename}")
            
        except Exception as e:
            self.logger.error(f"清理旧备份失败: {e}")
    
    # 恢复数据库
    def restore_database(self):
        """从备份恢复数据库"""
        try:
            # 获取所有备份文件
            backups = []
            for filename in os.listdir(self.backup_folder):
                if filename.startswith('backup_') and filename.endswith('.db'):
                    filepath = os.path.join(self.backup_folder, filename)
                    backups.append((filename, filepath, os.path.getmtime(filepath)))
            
            if not backups:
                messagebox.showinfo("提示 / Info", 
                                "📁 没有可用的备份文件\n\n"
                                "No backup files available")
                return
            
            # 按时间排序（最新的在前）
            backups.sort(key=lambda x: x[2], reverse=True)
            
            # 创建选择对话框
            restore_dialog = tk.Toplevel(self.root)
            restore_dialog.title("恢复数据库 / Restore Database")
            restore_dialog.geometry("700x650")
            restore_dialog.resizable(True, True)
            restore_dialog.minsize(650, 600)
            restore_dialog.grab_set()
            
            # 居中显示
            restore_dialog.update_idletasks()
            x = (restore_dialog.winfo_screenwidth() // 2) - (restore_dialog.winfo_width() // 2)
            y = (restore_dialog.winfo_screenheight() // 2) - (restore_dialog.winfo_height() // 2)
            restore_dialog.geometry(f"+{x}+{y}")
            
            # 标题
            title_frame = ttk.Frame(restore_dialog)
            title_frame.pack(pady=15, padx=20, fill=tk.X)
            
            ttk.Label(title_frame, text="💾", font=('Arial', 36)).pack()
            ttk.Label(title_frame, text="恢复数据库\nRestore Database", 
                    font=('Arial', 14, 'bold')).pack(pady=(10, 0))
            
            # 说明信息
            info_frame = ttk.Frame(restore_dialog)
            info_frame.pack(pady=10, padx=20, fill=tk.X)
            
            info_text = (
                "注意：恢复数据库将覆盖当前数据，请谨慎操作！\n"
                "Restoring database will overwrite current data. Please proceed with caution!\n\n"
                f"找到 {len(backups)} 个备份文件 / Found {len(backups)} backup files"
            )
            
            ttk.Label(info_frame, text=info_text, 
                    font=('Arial', 10), justify=tk.LEFT,
                    foreground='blue', wraplength=620).pack()
            
            # 备份列表
            list_frame = ttk.LabelFrame(restore_dialog, text="选择备份文件 / Select Backup File", padding=15)
            list_frame.pack(pady=10, padx=20, fill=tk.BOTH, expand=True)
            
            # 创建列表框和滚动条
            list_scroll_frame = ttk.Frame(list_frame)
            list_scroll_frame.pack(fill=tk.BOTH, expand=True)
            
            scrollbar = ttk.Scrollbar(list_scroll_frame)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            listbox = tk.Listbox(list_scroll_frame, 
                                height=12, 
                                font=('Courier', 10),
                                yscrollcommand=scrollbar.set)
            listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.config(command=listbox.yview)
            
            # 填充列表
            for idx, (filename, filepath, mtime) in enumerate(backups):
                timestamp = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                size_mb = os.path.getsize(filepath) / (1024 * 1024)
                
                # 格式化显示
                display_text = f"[{idx+1:2d}] {timestamp}  |  {size_mb:.2f} MB  |  {filename}"
                listbox.insert(tk.END, display_text)
            
            # 默认选中最新的备份
            listbox.select_set(0)
            listbox.see(0)
            
            # 文件信息显示
            info_detail_frame = ttk.Frame(restore_dialog)
            info_detail_frame.pack(pady=10, padx=20, fill=tk.X)
            
            detail_label = ttk.Label(info_detail_frame, 
                                    text="提示：双击或选中后点击「恢复」按钮\nDouble-click or select and click 'Restore'", 
                                    font=('Arial', 9), foreground='gray',
                                    wraplength=620)
            detail_label.pack()
            
            selected_backup = [None]
            
            def on_select(event=None):
                selection = listbox.curselection()
                if selection:
                    idx = selection[0]
                    filename, filepath, mtime = backups[idx]
                    timestamp = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                    size_mb = os.path.getsize(filepath) / (1024 * 1024)
                    
                    detail_text = (
                        f"📁 文件名 / Filename: {filename}\n"
                        f"🕐 备份时间 / Time: {timestamp}\n"
                        f"💾 文件大小 / Size: {size_mb:.2f} MB"
                    )
                    detail_label.config(text=detail_text, foreground='blue')
            
            def on_double_click(event):
                on_select()
                on_confirm()
            
            def on_confirm():
                selection = listbox.curselection()
                if selection:
                    selected_backup[0] = backups[selection[0]][1]
                    restore_dialog.destroy()
                else:
                    messagebox.showwarning("警告 / Warning", 
                                        "注意：请选择要恢复的备份文件！\n\n"
                                        "Please select a backup file to restore!",
                                        parent=restore_dialog)
            
            def on_cancel():
                restore_dialog.destroy()
            
            listbox.bind('<<ListboxSelect>>', on_select)
            listbox.bind('<Double-Button-1>', on_double_click)
            
            # 触发初始选择显示
            on_select()
            
            # 按钮区域
            button_frame = ttk.Frame(restore_dialog)
            button_frame.pack(pady=20, padx=20)
            
            ttk.Button(button_frame, text="💾 恢复 / Restore", 
                    command=on_confirm, width=18).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_frame, text="取消 / Cancel", 
                    command=on_cancel, width=18).pack(side=tk.LEFT, padx=5)
            
            restore_dialog.bind('<Return>', lambda e: on_confirm())
            restore_dialog.bind('<Escape>', lambda e: on_cancel())
            
            self.root.wait_window(restore_dialog)
            
            if selected_backup[0]:
                # 线程安全检查（添加在这里）
                with self.monitoring_lock:
                    if self.monitoring:
                        messagebox.showwarning("警告 / Warning", 
                                            "注意：请先停止监控！\n\n"
                                            "Please stop monitoring first!")
                        return
                
                # 二次确认
                confirm_msg = (
                    "注意：确认恢复数据库？\n\n"
                    "此操作将：\n"
                    "• 覆盖当前所有数据\n"
                    "• 无法撤销\n\n"
                    "Confirm database restoration?\n"
                    "This will:\n"
                    "• Overwrite all current data\n"
                    "• Cannot be undone\n\n"
                    "是否继续？ / Continue?"
                )
                
                if messagebox.askyesno("最终确认 / Final Confirmation", confirm_msg):
                    try:
                        # 备份当前数据库
                        current_backup = self.backup_database()
                        if current_backup:
                            self.logger.info(f"当前数据库已备份: {current_backup}")
                        
                        # 先关闭所有数据库连接
                        self.logger.info("正在关闭数据库连接...")
                        self.db_manager.close_all()
                        
                        # 等待连接完全关闭
                        import time
                        time.sleep(1)
                        
                        # 恢复选定的备份
                        shutil.copy2(selected_backup[0], self.db_file)
                        
                        # 重新创建连接池
                        self.db_manager = DatabaseManager('uv275_data.db', pool_size=5)
                        
                        self.logger.info(f"数据库已从备份恢复: {selected_backup[0]}")
                        
                        # 刷新显示
                        self.refresh_data()
                        
                        success_msg = (
                            "数据库恢复成功！\n\n"
                            "Database restored successfully!\n\n"
                            f"恢复源 / Restored from:\n{os.path.basename(selected_backup[0])}\n\n"
                            f"{'当前数据库已自动备份' if current_backup else ''}"
                        )
                        
                        messagebox.showinfo("恢复成功 / Success", success_msg)
                        
                    except Exception as e:
                        self.logger.error(f"恢复数据库失败: {e}")
                        messagebox.showerror("错误 / Error", 
                                        f"恢复数据库失败！\n\n"
                                        f"Failed to restore database!\n\n"
                                        f"错误信息 / Error:\n{str(e)}")
            
        except Exception as e:
            self.logger.error(f"恢复数据库过程失败: {e}")
            messagebox.showerror("错误 / Error", 
                            f"恢复数据库失败！\n\n{str(e)}")

    def start_archive_check_thread(self):
        """启动归档检查线程"""
        def archive_check_loop():
            while not self.stop_event.is_set():
                try:
                    self.data_archiver.auto_archive_check()
                    time.sleep(3600)  # 每小时检查一次
                except Exception as e:
                    self.logger.error(f"归档检查失败: {e}")
                    time.sleep(3600)
        
        archive_thread = threading.Thread(
            target=archive_check_loop,
            daemon=True,
            name="ArchiveCheckThread"
        )
        archive_thread.start()


