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

class UIBuilderMixin:
    """主界面、左右面板控件创建相关方法"""

    def create_widgets(self):
        """创建GUI组件"""
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.create_left_panel(main_frame)
        self.create_right_panel(main_frame)
        
        # 监听窗口大小变化，按 1:3 比例动态调整左侧面板宽度
        # 这样窗口放大/最大化时左右面板都会按比例变宽
        self._main_frame_ref = main_frame
        self.root.bind("<Configure>", self._on_window_resize)
    
    def _on_window_resize(self, event):
        """窗口大小变化时，按比例重新分配左右面板宽度"""
        # 只响应 root 窗口本身的 resize 事件
        if event.widget is not self.root:
            return
        try:
            # 主框架可用总宽度（去掉 padding）
            total_width = self._main_frame_ref.winfo_width()
            if total_width < 100:
                return   # 初始化阶段，跳过
            # 左 1 : 右 3 比例分配
            new_left_width = max(440, int(total_width * 0.25))
            self.scroll_canvas.config(width=new_left_width)
        except Exception:
            pass

    def _on_mousewheel(self, event):
        """处理鼠标滚轮事件"""
        self.scroll_canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def _refresh_left_panel_scrollregion(self):
        """Refresh the left-panel scroll area after accordion changes."""
        try:
            self.root.update_idletasks()
            self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all"))
        except Exception:
            pass

    def _set_collapsible_section_state(self, section, expanded):
        """Show or hide one left-panel section body."""
        section['expanded'] = expanded
        section['title_var'].set(("[ - ] " if expanded else "[ + ] ") + section['title'])

        if expanded:
            if not section['content'].winfo_ismapped():
                section['content'].pack(fill=tk.X, pady=(2, 0))
        else:
            section['content'].pack_forget()

    def _toggle_collapsible_section(self, section):
        """Toggle a left-panel section and collapse the others."""
        expanded = not section['expanded']
        if expanded:
            for other_section in getattr(self, '_left_panel_sections', []):
                if other_section is not section:
                    self._set_collapsible_section_state(other_section, False)

        self._set_collapsible_section_state(section, expanded)
        self._refresh_left_panel_scrollregion()

    def _create_collapsible_section(self, parent, title):
        """Create a compact left-panel section with a clickable title."""
        if not hasattr(self, '_left_panel_sections'):
            self._left_panel_sections = []

        outer_frame = ttk.Frame(parent)
        outer_frame.pack(fill=tk.X, pady=(0, 8))

        title_var = tk.StringVar()
        content_frame = ttk.Frame(outer_frame, padding=8)
        section = {
            'title': title,
            'title_var': title_var,
            'content': content_frame,
            'expanded': False,
        }

        ttk.Button(
            outer_frame,
            textvariable=title_var,
            command=lambda current_section=section: self._toggle_collapsible_section(current_section),
            style='Sidebar.TButton'
        ).pack(fill=tk.X)

        self._left_panel_sections.append(section)
        self._set_collapsible_section_state(section, False)
        return content_frame
    
    def create_left_panel(self, parent):
        """创建左侧控制面板"""
        left_frame = ttk.Frame(parent)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        
        # 根据语言动态调整面板宽度（英文按钮文字更长，需要更宽的面板）
        panel_width = 480 if self.current_language == 'en_US' else 440
        
        self.scroll_canvas = tk.Canvas(left_frame, width=panel_width, bg=self.bg_color, highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=self.scroll_canvas.yview)
        scrollable_frame = ttk.Frame(self.scroll_canvas)
        
        scrollable_frame.bind("<Configure>",
            lambda e: self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all")))
        
        # 将 scrollable_frame 作为 canvas 的内嵌窗口，并显式指定宽度，
        # 避免子组件（尤其是英文按钮文字较长时）撑开 frame 导致右侧溢出
        scrollable_window_id = self.scroll_canvas.create_window(
            (0, 0), window=scrollable_frame, anchor="nw", width=panel_width
        )
        # 当 canvas 本身宽度变化时，同步调整内嵌 frame 宽度
        self.scroll_canvas.bind(
            "<Configure>",
            lambda e: self.scroll_canvas.itemconfig(scrollable_window_id, width=e.width)
        )
        self.scroll_canvas.configure(yscrollcommand=scrollbar.set)

        
        # 鼠标在整个左侧面板区域时都能滚动
        def on_enter(event):
            # 只在左侧面板范围内绑定
            left_frame.bind_all("<MouseWheel>", self._on_mousewheel)

        def on_leave(event):
            # 使用 unbind_all 而不是 unbind
            left_frame.unbind_all("<MouseWheel>")
        
        # 在整个left_frame上绑定进入/离开事件
        left_frame.bind("<Enter>", on_enter)
        left_frame.bind("<Leave>", on_leave)
        
        self.scroll_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        font_normal = ('Arial', 10)
        font_current_data = ('Arial', 12)
        font_current_chlorine = ('Arial', 12, 'bold')

        try:
            self.style.configure('Sidebar.TButton', anchor=tk.W, font=('Arial', 10, 'bold'))
        except Exception:
            pass
        
        # 标题（使用短版本标题，并设置 wraplength 在极端情况下自动换行）
        title_label = ttk.Label(
            scrollable_frame,
            text=self.get_text('title_short'),
            font=('Arial', 14, 'bold'),
            wraplength=panel_width - 20,
            justify=tk.CENTER,
            anchor=tk.CENTER
        )
        title_label.pack(pady=(0, 15), fill=tk.X)
        
        # 当前数据显示
        data_frame = self._create_collapsible_section(scrollable_frame, self.get_text('current_data'))
        
        status_indicator_frame = ttk.Frame(data_frame)
        status_indicator_frame.pack(fill=tk.X, pady=(0, 5))
        
        canvas_bg = self.bg_color if self.current_theme == 'light' else '#3c3c3c'
        canvas_border = '#d0d0d0' if self.current_theme == 'light' else '#5a5a5a'
        
        self.indicator_canvas = tk.Canvas(status_indicator_frame, width=80, height=30, 
                                         bg=canvas_bg, highlightthickness=1, highlightbackground=canvas_border)
        self.indicator_canvas.pack(side=tk.LEFT, padx=(0, 10))
        
        self.green_light = self.indicator_canvas.create_oval(5, 5, 25, 25, 
                                                             fill='lightgray', outline='green', width=2)
        self.red_light = self.indicator_canvas.create_oval(45, 5, 65, 25, 
                                                           fill='lightgray', outline='red', width=2)
        
        status_label = ttk.Label(status_indicator_frame, text=self.get_text('status_indicator'), font=('Arial', 9))
        status_label.pack(side=tk.LEFT)
        
        self.current_uv275_label = ttk.Label(data_frame, text=f"{self.get_text('current_uv275')}: --", font=font_current_data)
        self.current_uv275_label.pack(anchor=tk.W, pady=1)
        
        self.current_temp_label = ttk.Label(data_frame, text=f"{self.get_text('current_temp')}: --", font=font_current_data)
        self.current_temp_label.pack(anchor=tk.W, pady=1)
        
        self.current_cod_label = ttk.Label(data_frame, text=f"{self.get_text('current_cod')}: --", font=font_current_data)
        self.current_cod_label.pack(anchor=tk.W, pady=1)
        
        self.current_turbidity_label = ttk.Label(data_frame, text=f"{self.get_text('current_turbidity')}: --", font=font_current_data)
        self.current_turbidity_label.pack(anchor=tk.W, pady=1)
        
        ttk.Separator(data_frame, orient='horizontal').pack(fill=tk.X, pady=5)
        
        self.current_chlorine_label = ttk.Label(data_frame, text=f"{self.get_text('recommended_chlorine')}: --", font=font_current_chlorine)
        self.current_chlorine_label.pack(anchor=tk.W, pady=1)
        
        self.actual_chlorine_label = ttk.Label(data_frame, 
                                              text=f"{self.get_text('actual_chlorine')}: {self.current_chlorine_dosage:.3f} mg/L", 
                                              font=font_current_data)
        self.actual_chlorine_label.pack(anchor=tk.W, pady=1)
        
        self.avg_chlorine_label = ttk.Label(data_frame, text=f"{self.get_text('avg_24h_chlorine')}: --", font=font_current_data)
        self.avg_chlorine_label.pack(anchor=tk.W, pady=1)
        
        self.avg_30d_chlorine_label = ttk.Label(data_frame, text=f"{self.get_text('avg_30d_chlorine')}: --", font=font_current_data)
        self.avg_30d_chlorine_label.pack(anchor=tk.W, pady=1)
        
        # ====================================================================
        # 水厂数据面板（新增）
        # ====================================================================
        waterplant_frame = self._create_collapsible_section(scrollable_frame, self.get_text('waterplant_status'))
        
        # 连接状态行
        self.waterplant_status_label = ttk.Label(
            waterplant_frame,
            text=f"{self.get_text('waterplant_offline')}",
            font=('Arial', 10, 'italic'),
            foreground='gray'
        )
        self.waterplant_status_label.pack(anchor=tk.W, pady=1)
        
        # 最近推送时间
        self.waterplant_last_update_label = ttk.Label(
            waterplant_frame,
            text=f"{self.get_text('waterplant_last_update')}: --",
            font=font_current_data
        )
        self.waterplant_last_update_label.pack(anchor=tk.W, pady=1)
        
        ttk.Separator(waterplant_frame, orient='horizontal').pack(fill=tk.X, pady=4)
        
        # 各工艺浊度显示
        self.waterplant_raw_turb_label = ttk.Label(
            waterplant_frame, text=f"{self.get_text('waterplant_raw_turb')}: --", font=font_current_data)
        self.waterplant_raw_turb_label.pack(anchor=tk.W, pady=1)
        
        self.waterplant_sand_turb_label = ttk.Label(
            waterplant_frame, text=f"{self.get_text('waterplant_sand_turb')}: --", font=font_current_data)
        self.waterplant_sand_turb_label.pack(anchor=tk.W, pady=1)
        
        self.waterplant_gac_turb_label = ttk.Label(
            waterplant_frame, text=f"{self.get_text('waterplant_gac_turb')}: --", font=font_current_data)
        self.waterplant_gac_turb_label.pack(anchor=tk.W, pady=1)
        
        self.waterplant_effluent_turb_label = ttk.Label(
            waterplant_frame, text=f"{self.get_text('waterplant_effluent_turb')}: --", font=font_current_data)
        self.waterplant_effluent_turb_label.pack(anchor=tk.W, pady=1)
        
        ttk.Separator(waterplant_frame, orient='horizontal').pack(fill=tk.X, pady=4)
        
        # 各工艺浊度去除率显示
        self.waterplant_sand_removal_label = ttk.Label(
            waterplant_frame, text=f"{self.get_text('waterplant_sand_removal')}: --", font=font_current_data)
        self.waterplant_sand_removal_label.pack(anchor=tk.W, pady=1)
        
        self.waterplant_gac_removal_label = ttk.Label(
            waterplant_frame, text=f"{self.get_text('waterplant_gac_removal')}: --", font=font_current_data)
        self.waterplant_gac_removal_label.pack(anchor=tk.W, pady=1)
        
        self.waterplant_effluent_removal_label = ttk.Label(
            waterplant_frame, text=f"{self.get_text('waterplant_effluent_removal')}: --", font=font_current_data)
        self.waterplant_effluent_removal_label.pack(anchor=tk.W, pady=1)
        
        # ====================================================================
        # 隐孢子虫风险评估面板（新增）
        # ====================================================================
        crypto_frame = self._create_collapsible_section(scrollable_frame, self.get_text('crypto_risk_title'))
        
        # 红绿灯状态指示
        crypto_indicator_frame = ttk.Frame(crypto_frame)
        crypto_indicator_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.crypto_indicator_canvas = tk.Canvas(
            crypto_indicator_frame, width=80, height=30,
            bg=canvas_bg, highlightthickness=1, highlightbackground=canvas_border
        )
        self.crypto_indicator_canvas.pack(side=tk.LEFT, padx=(0, 10))
        
        self.crypto_green_light = self.crypto_indicator_canvas.create_oval(
            5, 5, 25, 25, fill='lightgray', outline='green', width=2)
        self.crypto_red_light = self.crypto_indicator_canvas.create_oval(
            45, 5, 65, 25, fill='lightgray', outline='red', width=2)
        
        crypto_status_label = ttk.Label(
            crypto_indicator_frame,
            text=self.get_text('crypto_status_indicator'),
            font=('Arial', 9)
        )
        crypto_status_label.pack(side=tk.LEFT)
        
        # 隐孢子虫去除率评估等级
        self.crypto_level_label = ttk.Label(
            crypto_frame,
            text=f"{self.get_text('crypto_level_unknown')}",
            font=('Arial', 11, 'bold')
        )
        self.crypto_level_label.pack(anchor=tk.W, pady=3)
        
        # 判据说明（小字灰色，帮助操作人员理解判据）
        self.crypto_criteria_label = ttk.Label(
            crypto_frame, text=self.get_text('crypto_criteria_text'),
            font=('Arial', 8), foreground='gray', justify=tk.LEFT
        )
        self.crypto_criteria_label.pack(anchor=tk.W, pady=(3, 0))
        # ====================================================================
        
        # 时间范围选择
        time_range_frame = self._create_collapsible_section(scrollable_frame, self.get_text('time_range'))
        
        time_range_inner = ttk.Frame(time_range_frame)
        time_range_inner.pack(fill=tk.X)
        
        for time_range_key in ['1_day', '1_week', '1_month']:
            ttk.Radiobutton(time_range_inner, text=self.get_text(time_range_key), 
                           variable=self.selected_time_range, 
                           value=self.get_text(time_range_key),
                           command=self.on_time_range_change).pack(side=tk.LEFT, padx=5)
        
        # 图表显示参数选择
        chart_param_frame = self._create_collapsible_section(scrollable_frame, self.get_text('chart_param'))
        
        ttk.Label(chart_param_frame, text=self.get_text('select_param'), font=font_normal).pack(anchor=tk.W, pady=(0, 5))
        
        chart_param_options = self.get_chart_param_options()
        chart_param_combo = ttk.Combobox(chart_param_frame, 
                                         textvariable=self.selected_chart_param,
                                         values=list(chart_param_options.keys()),
                                         state='readonly',
                                         width=18)
        chart_param_combo.pack(fill=tk.X)
        chart_param_combo.bind('<<ComboboxSelected>>', lambda e: self.on_chart_param_change())
        
        param_info_frame = ttk.Frame(chart_param_frame)
        param_info_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.param_info_label = ttk.Label(param_info_frame, 
                                         text=self.get_text('param_info_uv275'), 
                                         font=('Arial', 9), foreground='blue')
        self.param_info_label.pack(anchor=tk.W)
        
        # 病原菌管理
        pathogen_mgmt_frame = self._create_collapsible_section(scrollable_frame, self.get_text('pathogen_mgmt'))
        
        self.pathogen_listbox_frame = ttk.Frame(pathogen_mgmt_frame)
        self.pathogen_listbox_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.create_pathogen_selection()
        
        pathogen_btn_frame = ttk.Frame(pathogen_mgmt_frame)
        pathogen_btn_frame.pack(fill=tk.X)
        
        ttk.Button(pathogen_btn_frame, text=self.get_text('add_pathogen'), 
                  command=self.add_pathogen).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(pathogen_btn_frame, text=self.get_text('delete_pathogen'), 
                  command=self.delete_pathogen).pack(side=tk.LEFT)
        
        # 季节选择
        season_frame = self._create_collapsible_section(scrollable_frame, self.get_text('season_setting'))
        
        season_inner_frame = ttk.Frame(season_frame)
        season_inner_frame.pack(fill=tk.X)
        
        for season_key in ['spring', 'summer', 'autumn', 'winter']:
            season_text = self.get_text(season_key)
            ttk.Radiobutton(season_inner_frame, text=season_text, 
                           variable=self.selected_season, 
                           value=season_text,
                           command=self.on_season_change).pack(side=tk.LEFT, padx=5)
        
        # 灭活率选择
        inactivation_frame = self._create_collapsible_section(scrollable_frame, self.get_text('inactivation_setting'))
        
        inactivation_inner_frame = ttk.Frame(inactivation_frame)
        inactivation_inner_frame.pack(fill=tk.X)
        
        rates = ["2 log", "3 log", "4 log", "5 log"]
        for rate in rates:
            ttk.Radiobutton(inactivation_inner_frame, text=rate, 
                           variable=self.selected_inactivation, 
                           value=rate,
                           command=self.on_inactivation_change).pack(side=tk.LEFT, padx=5)
        
        # 参数编辑
        param_frame = self._create_collapsible_section(scrollable_frame, self.get_text('param_edit'))
        
        self.equation_label = ttk.Label(param_frame, text=f"{self.get_text('current_equation')}: --", font=font_normal)
        self.equation_label.pack(anchor=tk.W, pady=(0, 5))
        
        param_input_frame = ttk.Frame(param_frame)
        param_input_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(param_input_frame, text=self.get_text('slope_a'), width=8).pack(side=tk.LEFT)
        self.param_a_entry = ttk.Entry(param_input_frame, textvariable=self.param_a_var, width=10)
        self.param_a_entry.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Label(param_input_frame, text=self.get_text('intercept_b'), width=8).pack(side=tk.LEFT)
        self.param_b_entry = ttk.Entry(param_input_frame, textvariable=self.param_b_var, width=10)
        self.param_b_entry.pack(side=tk.LEFT)
        
        param_btn_frame = ttk.Frame(param_frame)
        param_btn_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Button(param_btn_frame, text=self.get_text('save_param'), 
                  command=self.save_parameters).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(param_btn_frame, text=self.get_text('reset_param'), 
                  command=self.reset_parameters).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(param_btn_frame, text=self.get_text('param_manual'), 
                  command=self.open_parameter_manual).pack(side=tk.LEFT)
        
        # 统计信息
        stats_frame = self._create_collapsible_section(scrollable_frame, self.get_text('statistics'))
        
        self.total_count_label = ttk.Label(stats_frame, text=f"{self.get_text('total_count')}: --", font=font_normal)
        self.total_count_label.pack(anchor=tk.W, pady=1)
        
        self.anomaly_rate_label = ttk.Label(stats_frame, text=f"{self.get_text('anomaly_rate')}: --", font=font_normal)
        self.anomaly_rate_label.pack(anchor=tk.W, pady=1)
        
        self.detection_method_label = ttk.Label(stats_frame, text=f"{self.get_text('detection_method')}: --", font=font_normal)
        self.detection_method_label.pack(anchor=tk.W, pady=1)
        
        self.last_update_label = ttk.Label(stats_frame, text=f"{self.get_text('last_update')}: --", font=font_normal)
        self.last_update_label.pack(anchor=tk.W, pady=1)
        
        # 控制按钮
        control_frame = self._create_collapsible_section(scrollable_frame, self.get_text('control_panel'))
        
        self.start_button = ttk.Button(control_frame, text=self.get_text('start_monitor'), 
                                     command=self.start_monitoring)
        self.start_button.pack(fill=tk.X, pady=1)
        
        self.stop_button = ttk.Button(control_frame, text=self.get_text('stop_monitor'), 
                                    command=self.stop_monitoring, state=tk.DISABLED)
        self.stop_button.pack(fill=tk.X, pady=1)
        
        self.refresh_button = ttk.Button(control_frame, text=self.get_text('refresh_data'), 
                                       command=self.refresh_data)
        self.refresh_button.pack(fill=tk.X, pady=1)
        
        self.recheck_button = ttk.Button(control_frame, text=self.get_text('recheck_data'), 
                                       command=self.recheck_historical_anomalies)
        self.recheck_button.pack(fill=tk.X, pady=1)
        
        self.zero_calib_button = ttk.Button(control_frame, text=self.get_text('manual_zero'), 
                                           command=self.manual_zero_calibration)
        self.zero_calib_button.pack(fill=tk.X, pady=1)
        
        self.reset_calib_button = ttk.Button(control_frame, text=self.get_text('reset_calibration'), 
                                            command=self.reset_calibration)
        self.reset_calib_button.pack(fill=tk.X, pady=1)
        
        self.export_button = ttk.Button(control_frame, text=self.get_text('export_data'), 
                                      command=self.export_data)
        self.export_button.pack(fill=tk.X, pady=1)
        
        self.export_charts_button = ttk.Button(control_frame, text=self.get_text('export_charts'), 
                                             command=self.export_charts)
        self.export_charts_button.pack(fill=tk.X, pady=1)
        
        # 数据库备份按钮
        ttk.Button(control_frame, text=self.get_text('backup_db'), 
                  command=lambda: messagebox.showinfo("成功", f"备份已保存: {self.backup_database()}")
                  ).pack(fill=tk.X, pady=1)
        
        ttk.Button(control_frame, text=self.get_text('restore_db'), 
                  command=self.restore_database).pack(fill=tk.X, pady=1)
        
        # 恢复历史按钮
        ttk.Button(control_frame, text=self.get_text('restore_history'), 
                  command=self.show_recovery_history).pack(fill=tk.X, pady=1)  
              
        # 报告管理
        reports_frame = self._create_collapsible_section(scrollable_frame, self.get_text('reports'))
        
        ttk.Button(reports_frame, text=self.get_text('generate_weekly'), 
                  command=self.manual_generate_weekly_report).pack(fill=tk.X, pady=1)
        ttk.Button(reports_frame, text=self.get_text('generate_monthly'), 
                  command=self.manual_generate_monthly_report).pack(fill=tk.X, pady=1)
        ttk.Button(reports_frame, text=self.get_text('open_reports_folder'), 
                  command=self.open_reports_folder).pack(fill=tk.X, pady=1)
        
        # 串口配置
        serial_frame = self._create_collapsible_section(scrollable_frame, self.get_text('serial_config'))
        
        port_frame = ttk.Frame(serial_frame)
        port_frame.pack(fill=tk.X, pady=2)
        ttk.Label(port_frame, text=self.get_text('port'), width=12).pack(side=tk.LEFT)
        self.port_var = tk.StringVar(value=self.serial_config.get('port', 'COM3'))
        port_combo = ttk.Combobox(port_frame, textvariable=self.port_var, width=15)
        port_combo['values'] = self.get_available_ports()
        port_combo.pack(side=tk.LEFT, padx=5)
        ttk.Button(port_frame, text=self.get_text('refresh_ports'), command=self.refresh_ports, width=6).pack(side=tk.LEFT)
        
        baud_frame = ttk.Frame(serial_frame)
        baud_frame.pack(fill=tk.X, pady=2)
        ttk.Label(baud_frame, text=self.get_text('baudrate'), width=12).pack(side=tk.LEFT)
        self.baudrate_var = tk.StringVar(value=str(self.serial_config.get('baudrate', 9600)))
        baud_combo = ttk.Combobox(baud_frame, textvariable=self.baudrate_var, width=15)
        baud_combo['values'] = ['2400', '9600', '19200', '38400', '57600', '115200']
        baud_combo.pack(side=tk.LEFT, padx=5)
        
        addr_frame = ttk.Frame(serial_frame)
        addr_frame.pack(fill=tk.X, pady=2)
        ttk.Label(addr_frame, text=self.get_text('slave_address'), width=12).pack(side=tk.LEFT)
        self.slave_addr_var = tk.StringVar(value=str(self.serial_config.get('slave_address', 1)))
        ttk.Entry(addr_frame, textvariable=self.slave_addr_var, width=15).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(serial_frame, text=self.get_text('save_serial_config'), 
                  command=self.save_serial_settings).pack(fill=tk.X, pady=(5, 0))
        
        # 外观设置
        appearance_frame = self._create_collapsible_section(scrollable_frame, self.get_text('appearance'))
        
        theme_frame = ttk.Frame(appearance_frame)
        theme_frame.pack(fill=tk.X, pady=2)
        ttk.Label(theme_frame, text=self.get_text('theme'), width=12).pack(side=tk.LEFT)
        
        theme_btn_text = self.get_text('dark_theme') if self.current_theme == 'light' else self.get_text('light_theme')
        ttk.Button(theme_frame, text=theme_btn_text, 
                  command=self.switch_theme, width=15).pack(side=tk.LEFT, padx=5)
        
        lang_frame = ttk.Frame(appearance_frame)
        lang_frame.pack(fill=tk.X, pady=2)
        ttk.Label(lang_frame, text=self.get_text('language'), width=12).pack(side=tk.LEFT)
        
        lang_btn_text = self.get_text('english')
        ttk.Button(lang_frame, text=lang_btn_text, 
                  command=self.switch_language, width=15).pack(side=tk.LEFT, padx=5)
        
        # 状态显示
        status_frame = self._create_collapsible_section(scrollable_frame, self.get_text('system_status'))
        
        self.status_label = ttk.Label(status_frame, text=self.get_text('status_ready'), 
                                    foreground='green', font=font_normal)
        self.status_label.pack(anchor=tk.W)
    
    def create_right_panel(self, parent):
        """创建右侧图表面板"""
        right_frame = ttk.Frame(parent)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        self.fig = Figure(figsize=(12, 9), facecolor=self.plot_bg_color)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        self.ax1 = self.fig.add_subplot(2, 2, 1)
        self.ax2 = self.fig.add_subplot(2, 2, 2)
        self.ax3 = self.fig.add_subplot(2, 2, 3)
        self.ax4 = self.fig.add_subplot(2, 2, 4)
        
        for ax in [self.ax1, self.ax2, self.ax3, self.ax4]:
            ax.set_facecolor(self.plot_bg_color)
            for spine in ax.spines.values():
                spine.set_edgecolor(self.plot_fg_color)
            ax.tick_params(colors=self.plot_fg_color)
            ax.xaxis.label.set_color(self.plot_fg_color)
            ax.yaxis.label.set_color(self.plot_fg_color)
        
        self.fig.tight_layout(pad=3.0)
