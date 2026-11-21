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

class AlarmsMixin:
    """报警检测、数据收集与报警界面触发相关方法"""

    def _check_alarms_async(self, uv275_value, all_data):
        """异步报警检查（避免阻塞主线程）"""
        def alarm_check():
            try:
                pathogen = self.selected_pathogen.get()
                season = self.selected_season.get()
                inactivation = self.selected_inactivation.get()
                current_chlorine = self.current_chlorine_dosage
                
                alarm_data = self.collect_alarm_data(
                    uv275_value, all_data, pathogen, 
                    season, inactivation, current_chlorine
                )
                
                if alarm_data:
                    for alarm in alarm_data:
                        # 使用队列传递到主线程
                        self.gui_update_queue.put(lambda a=alarm: self.trigger_alarm_gui(a))
            
            except Exception as e:
                self.logger.error(f"报警检查失败: {e}", exc_info=True)
        
        # 在单独线程中执行
        threading.Thread(target=alarm_check, daemon=True, name="AlarmCheck").start()

    def collect_alarm_data(self, uv275_value, all_data, pathogen, season, inactivation, current_chlorine):
        """收集报警数据（但不创建GUI）"""
        try:
            alarms = []
            
            season_map_zh = {
                self.get_text('spring'): '春季',
                self.get_text('summer'): '夏季',
                self.get_text('autumn'): '秋季',
                self.get_text('winter'): '冬季'
            }
            season_zh = season_map_zh.get(season, season)
            
            try:
                coeff = self.inactivation_coefficients[pathogen][season_zh][inactivation]
                recommended_chlorine = coeff["a"] * uv275_value + coeff["b"]
                
                # 只要推荐值大于当前值就报警
                if recommended_chlorine > current_chlorine:
                    deficit = recommended_chlorine - current_chlorine
                    alarms.append({
                        'type': 'critical',
                        'message': '加氯量不足，微生物风险增加 / Insufficient chlorine',
                        'recommended': recommended_chlorine,
                        'actual': current_chlorine,
                        'deficit': deficit
                    })
            except KeyError:
                pass
            
            return alarms
                
        except Exception as e:
            self.logger.error(f"收集报警数据失败: {e}")
            return []


    
    def trigger_alarm_gui(self, alarm):
        """在主线程触发报警弹窗"""
        try:
            alarm['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 使用锁保护alarm_history
            with self.alarm_lock:
                self.alarm_history.append(alarm)
                if len(self.alarm_history) > 100:
                    self.alarm_history = self.alarm_history[-100:]
                    self.logger.debug("清理旧报警历史，保留最近100条")
            
            if alarm['type'] == 'critical':
                self.logger.warning(f"CRITICAL ALARM: {alarm['message']}")
            else:
                self.logger.warning(f"ALARM: {alarm['message']}")
            
            now = datetime.now()
            if self.last_alarm_time:
                if (now - self.last_alarm_time).total_seconds() < 300:
                    return
            
            self.last_alarm_time = now
            
            if self.alarm_window and self.alarm_window.winfo_exists():
                self.alarm_window.destroy()
            
            self.alarm_window = tk.Toplevel(self.root)
            self.alarm_window.title("系统报警 / System Alarm")
            self.alarm_window.geometry("700x600")
            self.alarm_window.resizable(True, True)
            self.alarm_window.minsize(650, 550)
            
            self.alarm_window.update_idletasks()
            x = (self.alarm_window.winfo_screenwidth() // 2) - (self.alarm_window.winfo_width() // 2)
            y = (self.alarm_window.winfo_screenheight() // 2) - (self.alarm_window.winfo_height() // 2)
            self.alarm_window.geometry(f"+{x}+{y}")
            
            title_frame = ttk.Frame(self.alarm_window)
            title_frame.pack(pady=20, padx=20, fill=tk.X)
            
            alarm_icon = "注意" if alarm['type'] == 'warning' else ""
            alarm_title = "警告 / Warning" if alarm['type'] == 'warning' else "严重警报 / Critical Alarm"
            
            ttk.Label(title_frame, text=alarm_icon, 
                    font=('Arial', 48)).pack()
            ttk.Label(title_frame, text=alarm_title, 
                    font=('Arial', 16, 'bold'), 
                    foreground='red').pack(pady=(10, 0))
            
            message_frame = ttk.LabelFrame(self.alarm_window, text="报警信息 / Alarm Message", padding=15)
            message_frame.pack(pady=15, padx=20, fill=tk.BOTH, expand=True)
            
            ttk.Label(message_frame, text=alarm['message'], 
                    font=('Arial', 12, 'bold'), wraplength=600,
                    foreground='red').pack(pady=10)
            
            if 'value' in alarm or 'deficit' in alarm:
                details_frame = ttk.Frame(message_frame)
                details_frame.pack(pady=10, fill=tk.X)
                
                if 'value' in alarm:
                    detail_line = ttk.Frame(details_frame)
                    detail_line.pack(fill=tk.X, pady=3)
                    ttk.Label(detail_line, text="当前值 / Current Value:", 
                            font=('Arial', 11), width=25).pack(side=tk.LEFT)
                    ttk.Label(detail_line, text=f"{alarm['value']:.3f}", 
                            font=('Arial', 11, 'bold'),
                            foreground='blue').pack(side=tk.LEFT)
                
                if 'deficit' in alarm:
                    ttk.Separator(details_frame, orient='horizontal').pack(fill=tk.X, pady=10)
                    
                    items = [
                        (" 推荐加氯量 / Recommended:", f"{alarm['recommended']:.3f} mg/L", 'green'),
                        (" 实际加氯量 / Actual:", f"{alarm['actual']:.3f} mg/L", 'blue'),
                        ("注意：加氯不足 / Deficit:", f"{alarm['deficit']:.3f} mg/L", 'red')
                    ]
                    
                    for label, value, color in items:
                        line = ttk.Frame(details_frame)
                        line.pack(fill=tk.X, pady=3)
                        ttk.Label(line, text=label, 
                                font=('Arial', 11), width=25).pack(side=tk.LEFT)
                        ttk.Label(line, text=value, 
                                font=('Arial', 11, 'bold'),
                                foreground=color).pack(side=tk.LEFT)
            
            time_frame = ttk.Frame(self.alarm_window)
            time_frame.pack(pady=10, padx=20, fill=tk.X)
            
            ttk.Label(time_frame, text=f" 报警时间 / Alarm Time: {alarm['timestamp']}", 
                    font=('Arial', 10), foreground='gray').pack()
            
            if alarm['type'] == 'critical':
                advice_frame = ttk.LabelFrame(self.alarm_window, text="建议措施 / Recommendations", padding=12)
                advice_frame.pack(pady=10, padx=20, fill=tk.X)
                
                advice_text = (
                    "• 立即增加加氯量至推荐值\n"
                    "• 检查加氯设备运行状态\n"
                    "• 加强水质监测频率\n"
                    "• 必要时采取应急消毒措施\n\n"
                    "• Increase chlorine dosage immediately\n"
                    "• Check chlorination equipment\n"
                    "• Increase monitoring frequency\n"
                    "• Take emergency measures if necessary"
                )
                
                ttk.Label(advice_frame, text=advice_text, 
                        font=('Arial', 10), justify=tk.LEFT,
                        wraplength=600).pack()
            
            ttk.Button(self.alarm_window, text="知道了 / Close", 
                    command=self.alarm_window.destroy, 
                    width=20).pack(pady=20)
            
            self.alarm_window.bind('<Return>', lambda e: self.alarm_window.destroy())
            self.alarm_window.bind('<Escape>', lambda e: self.alarm_window.destroy())
            
            self.alarm_window.after(60000, lambda: self.alarm_window.destroy() 
                                if self.alarm_window and self.alarm_window.winfo_exists() else None)
            
        except Exception as e:
            self.logger.error(f"触发报警失败: {e}")
    

