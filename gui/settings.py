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
import serial
import serial.tools.list_ports

from constants import LANGUAGES
from sensor import UV275SensorModbus

class SettingsMixin:
    """用户设置、主题切换、串口配置与传感器校准相关方法"""

    def load_preferences(self):
        """加载用户偏好设置"""
        default_preferences = {'theme': 'light', 'language': 'en_US'}
        try:
            if os.path.exists(self.preferences_file):
                with open(self.preferences_file, 'r', encoding='utf-8') as f:
                    self.preferences = json.load(f)
                self.logger.info("加载用户偏好设置")
            else:
                self.preferences = default_preferences
                self.save_preferences()
                self.logger.info("使用默认偏好设置")
        except Exception as e:
            self.logger.error(f"加载偏好设置失败: {e}")
            self.preferences = default_preferences
        
        self.current_theme = self.preferences.get('theme', 'light')
        self.current_language = 'en_US'
        self.preferences['language'] = 'en_US'
    
    def save_preferences(self):
        """保存用户偏好设置"""
        try:
            with open(self.preferences_file, 'w', encoding='utf-8') as f:
                json.dump(self.preferences, f, ensure_ascii=False, indent=2)
            self.logger.info("用户偏好设置已保存")
        except Exception as e:
            self.logger.error(f"保存偏好设置失败: {e}")
    
    def get_text(self, key):
        """获取当前语言的文本"""
        return LANGUAGES.get('en_US', {}).get(key, key)
    
    def apply_theme(self):
        """应用主题"""
        if self.current_theme == 'dark':
            self.root.configure(bg='#2b2b2b')
            self.bg_color = '#2b2b2b'
            self.fg_color = '#ffffff'
            self.plot_bg_color = '#1e1e1e'
            self.plot_fg_color = '#ffffff'
            
            self.style.theme_use('clam')
            
            self.style.configure('.', 
                background='#2b2b2b',
                foreground='#ffffff',
                fieldbackground='#3c3c3c',
                selectbackground='#4a4a4a',
                selectforeground='#ffffff')
            
            self.style.configure('TFrame', background='#2b2b2b')
            self.style.configure('TLabelframe', background='#2b2b2b', foreground='#ffffff', bordercolor='#4a4a4a')
            self.style.configure('TLabelframe.Label', background='#2b2b2b', foreground='#ffffff')
            self.style.configure('TLabel', background='#2b2b2b', foreground='#ffffff')
            self.style.configure('TButton', background='#3c3c3c', foreground='#ffffff', bordercolor='#4a4a4a')
            self.style.map('TButton', background=[('active', '#4a4a4a'), ('pressed', '#1e1e1e')])
            
            if hasattr(self, 'indicator_canvas'):
                self.indicator_canvas.configure(bg='#3c3c3c', highlightbackground='#5a5a5a')
            if hasattr(self, 'scroll_canvas'):
                self.scroll_canvas.configure(bg='#2b2b2b')
            
        else:
            self.root.configure(bg='#f0f0f0')
            self.bg_color = '#f0f0f0'
            self.fg_color = '#000000'
            self.plot_bg_color = 'white'
            self.plot_fg_color = '#000000'
            
            try:
                self.style.theme_use('vista')
            except:
                try:
                    self.style.theme_use('aqua')
                except:
                    self.style.theme_use('default')
            
            self.style.configure('.', background='#f0f0f0', foreground='#000000')
            
            if hasattr(self, 'indicator_canvas'):
                self.indicator_canvas.configure(bg=self.bg_color, highlightbackground='#d0d0d0')
            if hasattr(self, 'scroll_canvas'):
                self.scroll_canvas.configure(bg=self.bg_color)
    
    def switch_theme(self):
        """切换主题"""
        self.current_theme = 'dark' if self.current_theme == 'light' else 'light'
        self.preferences['theme'] = self.current_theme
        self.save_preferences()
        
        theme_name = "Dark Theme" if self.current_theme == 'dark' else "Light Theme"
        messagebox.showinfo(
            self.get_text('appearance'),
            f"Theme changed to {theme_name}.\n\n"
            f"Please restart the program for the change to take effect."
        )
    
    def switch_language(self):
        """切换语言"""
        self.current_language = 'en_US'
        self.preferences['language'] = 'en_US'
        self.save_preferences()
        plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial']
        
        messagebox.showinfo(
            "Language",
            "The interface language is English. Please restart the program if needed."
        )
    
    def bind_shortcuts(self):
        """绑定快捷键"""
        self.root.bind('<Control-s>', lambda e: self.export_data())
        self.root.bind('<Control-r>', lambda e: self.refresh_data())
        self.root.bind('<F5>', lambda e: self.refresh_data())
        self.root.bind('<Control-q>', lambda e: self.root.quit())
        self.root.bind('<Control-e>', lambda e: self.export_charts())
    
    def load_calibration_offsets(self):
        """加载校零偏移值"""
        try:
            if os.path.exists(self.calibration_file):
                with open(self.calibration_file, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                    self.calibration_offsets = loaded_data.get('offsets', self.calibration_offsets)
                    self.calibration_enabled = loaded_data.get('enabled', True)
                self.logger.info("加载已保存的校零配置")
            else:
                self.save_calibration_offsets()
                self.logger.info("创建默认校零配置")
        except Exception as e:
            self.logger.error(f"加载校零配置失败: {e}")
    
    def save_calibration_offsets(self):
        """保存校零偏移值"""
        try:
            data = {
                'offsets': self.calibration_offsets,
                'enabled': self.calibration_enabled,
                'last_calibration_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            with open(self.calibration_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.logger.info("校零配置已保存")
        except Exception as e:
            self.logger.error(f"保存校零配置失败: {e}")
    
    def apply_calibration(self, value, parameter_name):
        """应用校零偏移值"""
        if value is None:
            return None
        if self.calibration_enabled and parameter_name in self.calibration_offsets:
            return value - self.calibration_offsets[parameter_name]
        return value
    
    def manual_zero_calibration(self):
        """手动校零（优化版 - 增大窗口）"""
        with self.monitoring_lock:
            if self.monitoring:
                messagebox.showwarning("警告 / Warning", 
                                    "注意：请先停止监控后再进行校零操作！\n\n"
                                    "Please stop monitoring before calibration!")
                return
        
        calibration_dialog = tk.Toplevel(self.root)
        calibration_dialog.title("手动校零 / Manual Zero Calibration")
        calibration_dialog.geometry("650x700")
        calibration_dialog.resizable(True, True)
        calibration_dialog.minsize(600, 650)
        calibration_dialog.grab_set()
        
        # 居中显示
        calibration_dialog.update_idletasks()
        x = (calibration_dialog.winfo_screenwidth() // 2) - (calibration_dialog.winfo_width() // 2)
        y = (calibration_dialog.winfo_screenheight() // 2) - (calibration_dialog.winfo_height() // 2)
        calibration_dialog.geometry(f"+{x}+{y}")
        
        # 标题
        title_frame = ttk.Frame(calibration_dialog)
        title_frame.pack(pady=12, padx=20, fill=tk.X)
        ttk.Label(title_frame, text="手动校零 / Manual Zero Calibration", 
                font=('Arial', 14, 'bold')).pack()
        
        # 说明信息
        info_frame = ttk.LabelFrame(calibration_dialog, text="操作说明 / Instructions", padding=12)
        info_frame.pack(pady=10, padx=20, fill=tk.X)
        
        info_text = (
            "校零操作将读取当前传感器数值作为新的零点基准。\n"
            "所有后续测量值将基于此基准进行调整。\n\n"
            "Calibration will read current sensor values as new zero point.\n"
            "All subsequent measurements will be adjusted based on this baseline.\n\n"
            "操作步骤 / Steps:\n"
            "1. 确保传感器处于标准环境\n"
            "2. 点击'读取当前值'按钮\n"
            "3. 检查读取的数值是否正常\n"
            "4. 点击'确认'完成校零"
        )
        ttk.Label(info_frame, text=info_text, 
                font=('Arial', 10), justify=tk.LEFT,
                wraplength=570).pack()
        
        # 读取按钮
        read_frame = ttk.Frame(calibration_dialog)
        read_frame.pack(pady=12, padx=20, fill=tk.X)
        
        current_values = {}
        value_labels = {}
        
        def read_current_values():
            if not self.sensor:
                temp_sensor = UV275SensorModbus(
                    port=self.serial_config['port'],
                    baudrate=self.serial_config['baudrate'],
                    slave_address=self.serial_config['slave_address']
                )
                
                if not temp_sensor.connect():
                    messagebox.showerror("连接错误 / Connection Error", 
                                    "无法连接到传感器！\n\n"
                                    "请检查：\n"
                                    "  • 串口连接\n"
                                    "  • 传感器电源\n"
                                    "  • DTU模块状态\n\n"
                                    "Cannot connect to sensor!", 
                                    parent=calibration_dialog)
                    return
                
                try:
                    # 显示读取中状态
                    for label in value_labels.values():
                        label.config(text="读取中... / Reading...", foreground='orange')
                    calibration_dialog.update()
                    
                    all_data = temp_sensor.read_all_data_with_retry(max_retries=3)
                    if all_data:
                        current_values['temperature'] = all_data['temperature']
                        current_values['uv275_absorbance'] = all_data['uv275_absorbance']
                        current_values['visible_absorbance'] = all_data['visible_absorbance']
                        current_values['cod'] = all_data['cod']
                        current_values['turbidity'] = all_data['turbidity']
                        
                        for param, value in current_values.items():
                            if value is not None:
                                value_labels[param].config(text=f"{value:.3f}", foreground='green')
                            else:
                                value_labels[param].config(text="读取失败 / Failed", foreground='red')
                        
                        messagebox.showinfo("成功 / Success", 
                                        "当前值读取成功！\n\n"
                                        "Current values read successfully!\n\n"
                                        "请检查数值是否正常，然后点击'确认'完成校零。",
                                        parent=calibration_dialog)
                    else:
                        for label in value_labels.values():
                            label.config(text="读取失败 / Failed", foreground='red')
                        messagebox.showerror("错误 / Error", 
                                        "读取传感器数据失败！\n\n"
                                        "Failed to read sensor data!", 
                                        parent=calibration_dialog)
                finally:
                    temp_sensor.disconnect()
            else:
                messagebox.showwarning("警告 / Warning", 
                                    "注意：请先停止监控后再读取当前值！\n\n"
                                    "Please stop monitoring first!", 
                                    parent=calibration_dialog)
        
        ttk.Button(read_frame, text="读取当前值 / Read Current Values", 
                command=read_current_values, width=40).pack(pady=5)
        
        # 当前读数显示
        values_frame = ttk.LabelFrame(calibration_dialog, text="当前传感器读数 / Current Sensor Readings", 
                                    padding=12)
        values_frame.pack(pady=10, padx=20, fill=tk.BOTH, expand=True)
        
        parameters = [
            ('uv275_absorbance', 'UV275 吸光度 / UV275 Absorbance', '/cm'),
            ('temperature', '温度 / Temperature', '℃'),
            ('visible_absorbance', '可见光吸光度 / Visible Abs.', '/cm'),
            ('cod', 'COD 化学需氧量', 'mg/L'),
            ('turbidity', '浊度 / Turbidity', 'NTU')
        ]
        
        for param, label, unit in parameters:
            param_frame = ttk.Frame(values_frame)
            param_frame.pack(fill=tk.X, pady=5)
            
            ttk.Label(param_frame, text=f"{label}:", 
                    font=('Arial', 10), width=28).pack(side=tk.LEFT)
            
            value_label = ttk.Label(param_frame, text="--", 
                                font=('Arial', 10, 'bold'), 
                                width=12, foreground='gray')
            value_label.pack(side=tk.LEFT, padx=5)
            value_labels[param] = value_label
            
            ttk.Label(param_frame, text=unit, 
                    font=('Arial', 9), foreground='gray').pack(side=tk.LEFT)
        
        # 按钮区域
        button_frame = ttk.Frame(calibration_dialog)
        button_frame.pack(pady=20, padx=20, side=tk.BOTTOM)
        
        def confirm_calibration():
            if not current_values:
                messagebox.showwarning("警告 / Warning", 
                                    "注意：请先读取当前传感器值！\n\n"
                                    "Please read current sensor values first!", 
                                    parent=calibration_dialog)
                return
            
            invalid_values = [k for k, v in current_values.items() if v is None]
            if invalid_values:
                result = messagebox.askyesno("确认 / Confirm", 
                    f"注意：以下参数读取失败：\n{', '.join(invalid_values)}\n\n"
                    f"是否继续校零操作？\n\n"
                    f"Some parameters failed to read.\n"
                    f"Continue with calibration?",
                    parent=calibration_dialog)
                if not result:
                    return
            
            for param, value in current_values.items():
                if value is not None:
                    self.calibration_offsets[param] = self.calibration_offsets.get(param, 0.0) + value
            
            self.calibration_enabled = True
            self.save_calibration_offsets()
            
            messagebox.showinfo("成功 / Success", 
                            "校零完成！\n\n"
                            "所有传感器已重新校准。\n"
                            "后续测量将基于新的零点基准。\n\n"
                            "Calibration completed!\n"
                            "All sensors have been recalibrated.", 
                            parent=calibration_dialog)
            calibration_dialog.destroy()
            self.refresh_data()
        
        def cancel_calibration():
            calibration_dialog.destroy()
        
        ttk.Button(button_frame, text="确认校零 / Confirm", 
                command=confirm_calibration, width=18).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消 / Cancel", 
                command=cancel_calibration, width=18).pack(side=tk.LEFT, padx=5)
        
        calibration_dialog.bind('<Escape>', lambda e: cancel_calibration())

    def reset_calibration(self):
        """恢复默认基准值"""
        result = messagebox.askyesno("确认恢复", "确定要恢复默认基准值吗？")
        
        if result:
            self.calibration_offsets = {
                'uv275_absorbance': 0.0,
                'temperature': 0.0,
                'visible_absorbance': 0.0,
                'cod': 0.0,
                'turbidity': 0.0
            }
            self.calibration_enabled = True
            self.save_calibration_offsets()
            messagebox.showinfo("成功", "已恢复默认基准值！")
            self.refresh_data()
    
    def load_serial_config(self):
        """读取串口配置，顺便检查一下端口是不是还在"""
        default_config = {
            'port': self.config_manager.get('Sensor', 'default_port', 'COM3'),
            'baudrate': self.config_manager.getint('Sensor', 'default_baudrate', 9600),
            'slave_address': self.config_manager.getint('Sensor', 'default_slave_address', 1),
            'timeout': self.config_manager.getint('Sensor', 'timeout', 3)
        }
        
        try:
            if os.path.exists(self.serial_config_file):
                with open(self.serial_config_file, 'r', encoding='utf-8') as f:
                    self.serial_config = json.load(f)
                self.logger.info("加载已保存的串口配置")
            else:
                self.serial_config = default_config
                self.save_serial_config()
                self.logger.info("使用默认串口配置")
            
            # 验证配置的端口是否存在
            available_ports = [p.device for p in serial.tools.list_ports.comports()]
            
            if self.serial_config['port'] not in available_ports:
                self.logger.warning(
                    f"注意：配置的端口 {self.serial_config['port']} 不存在！\n"
                    f"可用端口: {', '.join(available_ports) if available_ports else '无'}"
                )
                
                # 自动选择第一个可用端口
                if available_ports:
                    old_port = self.serial_config['port']
                    self.serial_config['port'] = available_ports[0]
                    self.logger.info(f"已自动切换到: {available_ports[0]}")
                    self.save_serial_config()
                    
                    # 可选：通知用户
                    self.root.after(1000, lambda: messagebox.showinfo(
                        "串口自动切换",
                        f"配置的端口 {old_port} 不可用\n\n"
                        f"已自动切换到: {self.serial_config['port']}\n\n"
                        f"如需修改，请在控制面板中手动配置"
                    ))
        
        except Exception as e:
            self.logger.error(f"加载串口配置失败: {e}")
            self.serial_config = default_config
    
    def save_serial_config(self):
        """保存串口配置"""
        try:
            with open(self.serial_config_file, 'w', encoding='utf-8') as f:
                json.dump(self.serial_config, f, ensure_ascii=False, indent=2)
            self.logger.info("串口配置已保存")
        except Exception as e:
            self.logger.error(f"保存串口配置失败: {e}")
    
    def load_coefficients(self):
        """加载或初始化系数配置"""
        default_coefficients = {
            "大肠杆菌": {
                "春季": {"2 log": {"a": 8.061, "b": -0.019}, "3 log": {"a": 10.639, "b": -0.023}, 
                        "4 log": {"a": 14.029, "b": -0.025}, "5 log": {"a": 18.484, "b": -0.025}},
                "夏季": {"2 log": {"a": 7.937, "b": 0.011}, "3 log": {"a": 9.874, "b": 0.003}, 
                        "4 log": {"a": 12.279, "b": -0.009}, "5 log": {"a": 15.266, "b": -0.026}},
                "秋季": {"2 log": {"a": 8.061, "b": -0.019}, "3 log": {"a": 10.639, "b": -0.023}, 
                        "4 log": {"a": 14.029, "b": -0.025}, "5 log": {"a": 18.484, "b": -0.025}},
                "冬季": {"2 log": {"a": 9.316, "b": -0.018}, "3 log": {"a": 10.633, "b": 0.005}, 
                        "4 log": {"a": 12.131, "b": 0.037}, "5 log": {"a": 13.833, "b": 0.082}}
            },
            "铜绿假单胞菌": {
                "春季": {"2 log": {"a": 7.961, "b": 0.079}, "3 log": {"a": 10.159, "b": 0.076}, 
                        "4 log": {"a": 12.933, "b": 0.070}, "5 log": {"a": 16.424, "b": 0.061}},
                "夏季": {"2 log": {"a": 7.961, "b": 0.079}, "3 log": {"a": 10.159, "b": 0.076}, 
                        "4 log": {"a": 12.933, "b": 0.070}, "5 log": {"a": 16.424, "b": 0.061}},
                "秋季": {"2 log": {"a": 7.961, "b": 0.079}, "3 log": {"a": 10.159, "b": 0.076}, 
                        "4 log": {"a": 12.933, "b": 0.070}, "5 log": {"a": 16.424, "b": 0.061}},
                "冬季": {"2 log": {"a": 7.961, "b": 0.079}, "3 log": {"a": 10.159, "b": 0.076}, 
                        "4 log": {"a": 12.933, "b": 0.070}, "5 log": {"a": 16.424, "b": 0.061}}
            },
            "金黄色葡萄球菌": {
                "春季": {"2 log": {"a": 9.217, "b": 0.067}, "3 log": {"a": 10.599, "b": 0.111}, 
                        "4 log": {"a": 12.163, "b": 0.172}, "5 log": {"a": 13.923, "b": 0.255}},
                "夏季": {"2 log": {"a": 9.217, "b": 0.067}, "3 log": {"a": 10.599, "b": 0.111}, 
                        "4 log": {"a": 12.163, "b": 0.172}, "5 log": {"a": 13.923, "b": 0.255}},
                "秋季": {"2 log": {"a": 9.217, "b": 0.067}, "3 log": {"a": 10.599, "b": 0.111}, 
                        "4 log": {"a": 12.163, "b": 0.172}, "5 log": {"a": 13.923, "b": 0.255}},
                "冬季": {"2 log": {"a": 9.217, "b": 0.067}, "3 log": {"a": 10.599, "b": 0.111}, 
                        "4 log": {"a": 12.163, "b": 0.172}, "5 log": {"a": 13.923, "b": 0.255}}
            }
        }
        
        try:
            if os.path.exists(self.coefficients_file):
                with open(self.coefficients_file, 'r', encoding='utf-8') as f:
                    self.inactivation_coefficients = json.load(f)
                if "菌落总数" in self.inactivation_coefficients:
                    del self.inactivation_coefficients["菌落总数"]
                    self.save_coefficients()
                self.logger.info("加载已保存的系数配置")
            else:
                self.inactivation_coefficients = default_coefficients
                self.save_coefficients()
                self.logger.info("使用默认系数配置")
        except Exception as e:
            self.logger.error(f"加载系数配置失败: {e}")
            self.inactivation_coefficients = default_coefficients
    
    def save_coefficients(self):
        """保存系数配置到文件"""
        try:
            with open(self.coefficients_file, 'w', encoding='utf-8') as f:
                json.dump(self.inactivation_coefficients, f, ensure_ascii=False, indent=2)
            self.logger.info("系数配置已保存")
        except Exception as e:
            self.logger.error(f"保存系数配置失败: {e}")
    
