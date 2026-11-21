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

from constants import translate_pathogen

class PathogensMixin:
    """病原菌管理、模型参数编辑与加氯量计算相关方法"""

    def create_pathogen_selection(self):
        """创建病原体选择UI组件"""
        for widget in self.pathogen_listbox_frame.winfo_children():
            widget.destroy()
        
        pathogen_list = list(self.inactivation_coefficients.keys())
        
        if self.selected_pathogen.get() not in pathogen_list:
            self.selected_pathogen.set(pathogen_list[0] if pathogen_list else "大肠杆菌")
        
        for pathogen in pathogen_list:
            # 显示文字按当前语言翻译（默认三种病原菌翻译成拉丁学名；
            # 用户自定义病原菌保持原名）
            display_text = translate_pathogen(pathogen, self.current_language)
            rb = ttk.Radiobutton(
                self.pathogen_listbox_frame,
                text=display_text,
                variable=self.selected_pathogen,
                value=pathogen,     # value 保留中文 key，确保数据查询不受影响
                command=self.on_pathogen_change
            )
            rb.pack(anchor=tk.W, pady=2)
        
        self.update_parameter_display()
    
    def add_pathogen(self):
        """添加新病原体"""
        # 创建自定义对话框
        add_dialog = tk.Toplevel(self.root)
        add_dialog.title("添加病原菌 / Add Pathogen")
        add_dialog.geometry("720x580")
        add_dialog.resizable(True, True)
        add_dialog.minsize(680, 550)
        add_dialog.grab_set()
        
        # 居中显示
        add_dialog.update_idletasks()
        x = (add_dialog.winfo_screenwidth() // 2) - (add_dialog.winfo_width() // 2)
        y = (add_dialog.winfo_screenheight() // 2) - (add_dialog.winfo_height() // 2)
        add_dialog.geometry(f"+{x}+{y}")
        
        # 标题区域
        title_frame = ttk.Frame(add_dialog)
        title_frame.pack(pady=15, padx=20, fill=tk.X)
        ttk.Label(title_frame, text="添加新病原菌\nAdd New Pathogen", 
                font=('Arial', 14, 'bold')).pack()
        
        # 说明信息
        info_frame = ttk.LabelFrame(add_dialog, text="说明 / Instructions", padding=10)
        info_frame.pack(pady=10, padx=20, fill=tk.BOTH, expand=True)
        
        info_text = (
            "添加新病原菌后，系统将自动为其设置默认参数（参考大肠杆菌参数）。\n"
            "您可以稍后在'参数编辑'区域修改具体的计算参数。\n\n"
            "After adding a new pathogen, the system will automatically set default\n"
            "parameters (based on E. coli). You can modify the calculation parameters\n"
            "later in the 'Parameter Edit' section.\n\n"
            "默认参数包括：\n"
            "• 四季（春、夏、秋、冬）\n"
            "• 四种灭活率（2 log, 3 log, 4 log, 5 log）\n"
            "• 每种组合的 k（斜率）和 b（截距）值"
        )
        
        info_label = ttk.Label(info_frame, text=info_text, 
                            font=('Arial', 10), justify=tk.LEFT,
                            wraplength=620)
        info_label.pack(pady=5)
        
        # 输入区域
        input_frame = ttk.LabelFrame(add_dialog, text="病原菌名称 / Pathogen Name", padding=10)
        input_frame.pack(pady=10, padx=20, fill=tk.X)
        
        name_var = tk.StringVar()
        
        input_inner = ttk.Frame(input_frame)
        input_inner.pack(fill=tk.X)
        
        ttk.Label(input_inner, text="名称 / Name:", font=('Arial', 11), width=12).pack(side=tk.LEFT, padx=(0, 10))
        name_entry = ttk.Entry(input_inner, textvariable=name_var, width=35, font=('Arial', 11))
        name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        name_entry.focus()
        
        # 提示信息
        hint_label = ttk.Label(input_frame, 
                            text="请输入病原菌中文或英文名称（例如：沙门氏菌、Salmonella）",
                            font=('Arial', 9), foreground='gray',
                            wraplength=600)
        hint_label.pack(pady=(8, 0))
        
        result = {'confirmed': False, 'name': None}
        
        def on_confirm():
            pathogen_name = name_var.get().strip()
            
            if not pathogen_name:
                messagebox.showwarning("警告 / Warning", 
                                    "请输入病原菌名称！\nPlease enter pathogen name!",
                                    parent=add_dialog)
                return
            
            if pathogen_name in self.inactivation_coefficients:
                messagebox.showwarning("警告 / Warning", 
                                    f"病原菌 '{pathogen_name}' 已存在！\nPathogen '{pathogen_name}' already exists!",
                                    parent=add_dialog)
                return
            
            result['confirmed'] = True
            result['name'] = pathogen_name
            add_dialog.destroy()
        
        def on_cancel():
            add_dialog.destroy()
        
        # 按钮区域
        button_frame = ttk.Frame(add_dialog)
        button_frame.pack(pady=20, padx=20, side=tk.BOTTOM)
        
        ttk.Button(button_frame, text="确认添加 / Confirm", 
                command=on_confirm, width=18).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消 / Cancel", 
                command=on_cancel, width=18).pack(side=tk.LEFT, padx=5)
        
        # 绑定回车键
        name_entry.bind('<Return>', lambda e: on_confirm())
        add_dialog.bind('<Escape>', lambda e: on_cancel())
        
        self.root.wait_window(add_dialog)
        
        if not result['confirmed']:
            return
        
        pathogen_name = result['name']
        
        # 添加默认参数
        self.inactivation_coefficients[pathogen_name] = {
            '春季': {
                '2 log': {'a': 8.061, 'b': -0.019},
                '3 log': {'a': 10.639, 'b': -0.023},
                '4 log': {'a': 14.029, 'b': -0.025},
                '5 log': {'a': 18.484, 'b': -0.025}
            },
            '夏季': {
                '2 log': {'a': 7.937, 'b': 0.011},
                '3 log': {'a': 9.874, 'b': 0.003},
                '4 log': {'a': 12.279, 'b': -0.009},
                '5 log': {'a': 15.266, 'b': -0.026}
            },
            '秋季': {
                '2 log': {'a': 8.061, 'b': -0.019},
                '3 log': {'a': 10.639, 'b': -0.023},
                '4 log': {'a': 14.029, 'b': -0.025},
                '5 log': {'a': 18.484, 'b': -0.025}
            },
            '冬季': {
                '2 log': {'a': 9.316, 'b': -0.018},
                '3 log': {'a': 10.633, 'b': 0.005},
                '4 log': {'a': 12.131, 'b': 0.037},
                '5 log': {'a': 13.833, 'b': 0.082}
            }
        }
        
        self.save_coefficients()
        self.selected_pathogen.set(pathogen_name)
        self.create_pathogen_selection()
        self.update_parameter_display()
        
        # 成功提示
        success_msg = (
            f"已成功添加病原菌：{pathogen_name}\n\n"
            f"系统已自动设置默认参数（参考大肠杆菌）：\n"
            f"  • 四个季节的参数配置\n"
            f"  • 四种灭活率（2-5 log）\n\n"
            f"您可以在左侧'参数编辑'区域修改具体参数。\n\n"
            f"Pathogen '{pathogen_name}' added successfully!\n"
            f"Default parameters have been set.\n"
            f"You can modify them in the 'Parameter Edit' section."
        )
        
        messagebox.showinfo("添加成功 / Success", success_msg)
        self.logger.info(f"添加新病原菌: {pathogen_name}")
    
    def delete_pathogen(self):
        """删除选中的病原体"""
        pathogen = self.selected_pathogen.get()
        
        default_pathogens = ['大肠杆菌', '铜绿假单胞菌', '金黄色葡萄球菌']
        if pathogen in default_pathogens:
            messagebox.showwarning("无法删除 / Cannot Delete", 
                                f"注意：无法删除默认病原菌 '{pathogen}'！\n\n"
                                f"默认病原菌包括：\n"
                                f"  • 大肠杆菌\n"
                                f"  • 铜绿假单胞菌\n"
                                f"  • 金黄色葡萄球菌\n\n"
                                f"Cannot delete default pathogen '{pathogen}'!")
            return
        
        if pathogen not in self.inactivation_coefficients:
            messagebox.showwarning("警告 / Warning", 
                                f"病原菌 '{pathogen}' 不存在！\n"
                                f"Pathogen '{pathogen}' does not exist!")
            return
        
        # 创建自定义确认对话框
        confirm_dialog = tk.Toplevel(self.root)
        confirm_dialog.title("确认删除 / Confirm Delete")
        confirm_dialog.geometry("650x580")
        confirm_dialog.resizable(True, True)
        confirm_dialog.minsize(600, 500)
        confirm_dialog.grab_set()
        
        # 居中显示
        confirm_dialog.update_idletasks()
        x = (confirm_dialog.winfo_screenwidth() // 2) - (confirm_dialog.winfo_width() // 2)
        y = (confirm_dialog.winfo_screenheight() // 2) - (confirm_dialog.winfo_height() // 2)
        confirm_dialog.geometry(f"+{x}+{y}")
        
        # 警告图标和标题
        title_frame = ttk.Frame(confirm_dialog)
        title_frame.pack(pady=20, padx=20, fill=tk.X)
        
        warning_label = ttk.Label(title_frame, text="注意", font=('Arial', 36))
        warning_label.pack()
        
        title_label = ttk.Label(title_frame, text="确认删除病原菌\nConfirm Pathogen Deletion", 
                            font=('Arial', 13, 'bold'))
        title_label.pack(pady=(10, 0))
        
        # 信息区域
        info_frame = ttk.Frame(confirm_dialog)
        info_frame.pack(pady=10, padx=20, fill=tk.BOTH, expand=True)
        
        info_text = (
            f"您即将删除病原菌：{pathogen}\n\n"
            f"删除后将：\n"
            f"  • 移除该病原菌的所有参数配置\n"
            f"  • 移除四个季节的所有数据\n"
            f"  • 移除所有灭活率设置\n\n"
            f"注意：此操作无法撤销！\n\n"
            f"You are about to delete pathogen: {pathogen}\n\n"
            f"This will remove:\n"
            f"  • All parameter configurations\n"
            f"  • Data for all four seasons\n"
            f"  • All inactivation rate settings\n\n"
            f"注意：This operation cannot be undone!"
        )
        
        info_label = ttk.Label(info_frame, text=info_text, 
                            font=('Arial', 10), justify=tk.LEFT,
                            wraplength=480)
        info_label.pack()
        
        result = {'confirmed': False}
        
        def on_confirm():
            result['confirmed'] = True
            confirm_dialog.destroy()
        
        def on_cancel():
            confirm_dialog.destroy()
        
        # 按钮区域
        button_frame = ttk.Frame(confirm_dialog)
        button_frame.pack(pady=20, padx=20, side=tk.BOTTOM)
        
        ttk.Button(button_frame, text="确认删除 / Delete", 
                command=on_confirm, width=18).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消 / Cancel", 
                command=on_cancel, width=18).pack(side=tk.LEFT, padx=5)
        
        confirm_dialog.bind('<Escape>', lambda e: on_cancel())
        
        self.root.wait_window(confirm_dialog)
        
        if result['confirmed']:
            del self.inactivation_coefficients[pathogen]
            self.save_coefficients()
            
            available_pathogens = list(self.inactivation_coefficients.keys())
            if available_pathogens:
                self.selected_pathogen.set(available_pathogens[0])
            
            self.create_pathogen_selection()
            self.update_parameter_display()
            self.update_data_display()
            
            messagebox.showinfo("删除成功 / Success", 
                            f"已成功删除病原菌：{pathogen}\n\n"
                            f"Pathogen '{pathogen}' deleted successfully!")
            self.logger.info(f"删除病原菌: {pathogen}")
    
    def save_parameters(self):
        """保存当前病原体的参数"""
        try:
            pathogen = self.selected_pathogen.get()
            season = self.selected_season.get()
            inactivation = self.selected_inactivation.get()
            
            try:
                a_value = float(self.param_a_var.get())
                b_value = float(self.param_b_var.get())
            except ValueError:
                messagebox.showerror("输入错误 / Input Error", 
                                "参数值无效！\n\n"
                                "请输入有效的数字。\n"
                                "示例：k = 8.061, b = -0.019\n\n"
                                "Invalid parameter value!\n"
                                "Please enter valid numbers.")
                return
            
            season_map = {
                self.get_text('spring'): '春季',
                self.get_text('summer'): '夏季',
                self.get_text('autumn'): '秋季',
                self.get_text('winter'): '冬季'
            }
            season_zh = season_map.get(season, season)
            
            if pathogen in self.inactivation_coefficients:
                if season_zh in self.inactivation_coefficients[pathogen]:
                    if inactivation in self.inactivation_coefficients[pathogen][season_zh]:
                        self.inactivation_coefficients[pathogen][season_zh][inactivation] = {
                            'a': a_value,
                            'b': b_value
                        }
                        
                        self.save_coefficients()
                        self.update_parameter_display()
                        self.update_data_display()
                        self.update_plots()
                        
                        # 创建自定义成功对话框
                        success_dialog = tk.Toplevel(self.root)
                        success_dialog.title("保存成功 / Save Successful")
                        success_dialog.geometry("680x600")
                        success_dialog.resizable(True, True)
                        success_dialog.minsize(650, 550)
                        success_dialog.grab_set()
                        
                        # 居中显示
                        success_dialog.update_idletasks()
                        x = (success_dialog.winfo_screenwidth() // 2) - (success_dialog.winfo_width() // 2)
                        y = (success_dialog.winfo_screenheight() // 2) - (success_dialog.winfo_height() // 2)
                        success_dialog.geometry(f"+{x}+{y}")
                        
                        # 成功图标和标题
                        title_frame = ttk.Frame(success_dialog)
                        title_frame.pack(pady=20, padx=20)
                        
                        ttk.Label(title_frame, text="", font=('Arial', 48)).pack()
                        ttk.Label(title_frame, text="参数保存成功！\nParameters Saved Successfully!", 
                                font=('Arial', 13, 'bold')).pack(pady=(10, 0))
                        
                        # 参数信息
                        info_frame = ttk.LabelFrame(success_dialog, text="已保存的参数 / Saved Parameters", padding=15)
                        info_frame.pack(pady=15, padx=20, fill=tk.BOTH, expand=True)
                        
                        param_info = [
                            ("病原菌 / Pathogen:", pathogen),
                            ("季节 / Season:", season),
                            ("灭活率 / Inactivation:", inactivation),
                            ("", ""),
                            ("参数方程 / Equation:", ""),
                            ("  加氯量 = k × UV275 + b", ""),
                            ("  Chlorine = k × UV275 + b", ""),
                            ("", ""),
                            ("斜率 k / Slope k:", f"{a_value:.6f}"),
                            ("截距 b / Intercept b:", f"{b_value:.6f}"),
                            ("", ""),
                            ("完整方程 / Full Equation:", ""),
                            ("  ", f"Cl = {a_value:.3f} × UV275 + {b_value:.3f}")
                        ]
                        
                        for label_text, value_text in param_info:
                            param_frame = ttk.Frame(info_frame)
                            param_frame.pack(fill=tk.X, pady=2)
                            
                            if label_text:
                                ttk.Label(param_frame, text=label_text, 
                                        font=('Arial', 10, 'bold' if value_text else 'normal'),
                                        width=25).pack(side=tk.LEFT)
                            
                            if value_text:
                                ttk.Label(param_frame, text=value_text, 
                                        font=('Arial', 10),
                                        foreground='blue').pack(side=tk.LEFT)
                        
                        # 确定按钮
                        ttk.Button(success_dialog, text="确定 / OK", 
                                command=success_dialog.destroy, 
                                width=20).pack(pady=20)
                        
                        success_dialog.bind('<Return>', lambda e: success_dialog.destroy())
                        success_dialog.bind('<Escape>', lambda e: success_dialog.destroy())
                        
                        self.logger.info(f"参数已保存 - {pathogen}, {season_zh}, {inactivation}: a={a_value}, b={b_value}")
                        
                    else:
                        messagebox.showerror("错误 / Error", "无效的灭活率！\nInvalid inactivation rate!")
                else:
                    messagebox.showerror("错误 / Error", "无效的季节！\nInvalid season!")
            else:
                messagebox.showerror("错误 / Error", "无效的病原菌！\nInvalid pathogen!")
                
        except Exception as e:
            self.logger.error(f"保存参数失败: {e}")
            messagebox.showerror("错误 / Error", 
                            f"保存参数失败！\nFailed to save parameters!\n\n"
                            f"错误信息 / Error message:\n{str(e)}")
    
    def reset_parameters(self):
        """重置所有参数到默认值"""
        # 创建自定义确认对话框
        reset_dialog = tk.Toplevel(self.root)
        reset_dialog.title("重置参数 / Reset Parameters")
        reset_dialog.geometry("680x650")
        reset_dialog.resizable(True, True)
        reset_dialog.minsize(650,600)
        reset_dialog.grab_set()
        
        # 居中显示
        reset_dialog.update_idletasks()
        x = (reset_dialog.winfo_screenwidth() // 2) - (reset_dialog.winfo_width() // 2)
        y = (reset_dialog.winfo_screenheight() // 2) - (reset_dialog.winfo_height() // 2)
        reset_dialog.geometry(f"+{x}+{y}")
        
        # 警告图标和标题
        title_frame = ttk.Frame(reset_dialog)
        title_frame.pack(pady=20, padx=20, fill=tk.X)
        
        ttk.Label(title_frame, text="", font=('Arial', 48)).pack()
        ttk.Label(title_frame, text="重置所有参数\nReset All Parameters", 
                font=('Arial', 14, 'bold')).pack(pady=(10, 0))
        
        # 警告信息
        warning_frame = ttk.LabelFrame(reset_dialog, text="注意：警告 / Warning", padding=15)
        warning_frame.pack(pady=15, padx=20, fill=tk.BOTH, expand=True)
        
        warning_text = (
            "此操作将：\n\n"
            "• 删除所有自定义病原菌（保留默认的3种）\n"
            "• 恢复所有病原菌的默认参数配置\n"
            "• 重置所有季节和灭活率的参数值\n"
            "• 清除所有自定义的修改\n\n"
            "注意：此操作无法撤销！\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "This operation will:\n\n"
            "• Delete all custom pathogens (keep default 3)\n"
            "• Restore default parameter configurations\n"
            "• Reset all season and inactivation rate parameters\n"
            "• Clear all custom modifications\n\n"
            "注意：This operation cannot be undone!"
        )
        
        ttk.Label(warning_frame, text=warning_text, 
                font=('Arial', 10), justify=tk.LEFT,
                wraplength=520).pack()
        
        result = {'confirmed': False}
        
        def on_confirm():
            result['confirmed'] = True
            reset_dialog.destroy()
        
        def on_cancel():
            reset_dialog.destroy()
        
        # 按钮区域
        button_frame = ttk.Frame(reset_dialog)
        button_frame.pack(pady=20, padx=20, side=tk.BOTTOM)
        
        ttk.Button(button_frame, text="确认重置 / Confirm Reset", 
                command=on_confirm, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消 / Cancel", 
                command=on_cancel, width=20).pack(side=tk.LEFT, padx=5)
        
        reset_dialog.bind('<Escape>', lambda e: on_cancel())
        
        self.root.wait_window(reset_dialog)
        
        if not result['confirmed']:
            return
        
        # 执行重置
        self.inactivation_coefficients = {
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
        
        self.save_coefficients()
        self.create_pathogen_selection()
        self.update_parameter_display()
        
        messagebox.showinfo("重置完成 / Reset Completed", 
                        "所有参数已重置为默认值！\n\n"
                        "All parameters have been reset to default values!")
    
    def recheck_historical_anomalies(self):
        """使用连接池重新检查所有历史数据的异常值"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT id, uv275_absorbance, is_anomaly
                    FROM measurements
                    ORDER BY timestamp
                ''')
                
                rows = cursor.fetchall()
                
                if not rows:
                    messagebox.showinfo("信息 / Info", "没有数据 / No data")
                    return
                
                rechecked = 0
                updated_records = []
                
                for record_id, uv275, current_is_anomaly in rows:
                    new_is_anomaly = self.detect_anomaly(uv275)
                    
                    if current_is_anomaly != new_is_anomaly:
                        updated_records.append((int(new_is_anomaly), record_id))
                        rechecked += 1
                
                if updated_records:
                    cursor.executemany('''
                        UPDATE measurements
                        SET is_anomaly = ?
                        WHERE id = ?
                    ''', updated_records)
                    
                    conn.commit()
                
                messagebox.showinfo("成功 / Success", 
                                f"重新检查完成！\n\n"
                                f"总记录数 / Total records: {len(rows)}\n"
                                f"更新记录 / Updated: {rechecked}")
                
                self.update_plots()
                self.update_data_display()
                
                self.logger.info(f"重新检查历史数据完成: 总数{len(rows)}, 更新{rechecked}")
                
        except Exception as e:
            self.logger.error(f"重新检查失败: {e}", exc_info=True)
            messagebox.showerror("错误 / Error", f"重新检查失败 / Failed:\n{str(e)}")
    
    def detect_anomaly(self, value):
        """检测异常值"""
        if self.should_use_empirical_method():
            return self.detect_anomaly_empirical(value)
        else:
            return self.detect_anomaly_statistical(value)
    
    def calculate_chlorine_demand(self, uv275_value):
        """计算推荐加氯量"""
        try:
            pathogen = self.selected_pathogen.get()
            season = self.selected_season.get()
            inactivation = self.selected_inactivation.get()
            
            season_map_zh = {
                self.get_text('spring'): '春季',
                self.get_text('summer'): '夏季',
                self.get_text('autumn'): '秋季',
                self.get_text('winter'): '冬季'
            }
            season_zh = season_map_zh.get(season, season)
            
            # 使用安全的嵌套字典访问，避免常见输入错误
            pathogen_data = self.inactivation_coefficients.get(pathogen)
            if not pathogen_data:
                self.logger.warning(f"未找到病原菌配置: {pathogen}，返回默认值0")
                return 0.0
            
            season_data = pathogen_data.get(season_zh)
            if not season_data:
                self.logger.warning(f"未找到季节配置: {pathogen}/{season_zh}，返回默认值0")
                return 0.0
            
            coeff = season_data.get(inactivation)
            if not coeff:
                self.logger.warning(f"未找到灭活率配置: {pathogen}/{season_zh}/{inactivation}，返回默认值0")
                return 0.0
            
            chlorine_demand = coeff["a"] * uv275_value + coeff["b"]
            # 确保不返回负值（即人为规定加氯量不能为负）
            return max(0.0, chlorine_demand)
        except Exception as e:
            self.logger.error(f"计算加氯量异常: {e}", exc_info=True)
            return 0.0  # 返回安全默认值，避免监控线程崩溃