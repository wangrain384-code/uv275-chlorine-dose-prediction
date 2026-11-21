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
import csv
import subprocess

class ReportsMixin:
    """报表自动生成、手动导出及图表导出相关方法"""

    def start_report_check_thread(self):
        """启动报告生成检查线程"""
        # 添加停止事件
        if not hasattr(self, 'report_check_stop_event'):
            self.report_check_stop_event = threading.Event()
        
        def check_and_generate_reports():
            self.logger.info("报告检查线程启动")
            last_weekly_check = None
            last_monthly_check = None
            
            while not self.report_check_stop_event.is_set():
                try:
                    current_time = datetime.now()
                    current_date = current_time.date()
                    
                    # 周报检查（周一凌晨1点）
                    if (current_time.weekday() == 0 and 
                        current_time.hour == 1 and 
                        current_date != last_weekly_check):
                        
                        self.auto_generate_weekly_report()
                        last_weekly_check = current_date
                        self.logger.info("已生成周报")
                    
                    # 月报检查（每月1号凌晨2点）
                    if (current_time.day == 1 and 
                        current_time.hour == 2 and 
                        current_date != last_monthly_check):
                        
                        self.auto_generate_monthly_report()
                        last_monthly_check = current_date
                        self.logger.info("已生成月报")
                    
                    # 可中断等待
                    self.report_check_stop_event.wait(60)
                    
                except Exception as e:
                    self.logger.error(f"报告检查线程错误: {e}")
                    self.report_check_stop_event.wait(60)
            
            self.logger.info("报告检查线程退出")
        
        self.report_check_thread = threading.Thread(
            target=check_and_generate_reports, 
            daemon=True,
            name="ReportCheckThread"
        )
        self.report_check_thread.start()
        self.logger.info("报告检查线程已启动")

    def stop_report_check_thread(self):
        """停止报告检查线程"""
        if hasattr(self, 'report_check_stop_event'):
            self.logger.info("正在停止报告检查线程...")
            self.report_check_stop_event.set()
            
            if hasattr(self, 'report_check_thread') and self.report_check_thread.is_alive():
                self.report_check_thread.join(timeout=5.0)
                
                if self.report_check_thread.is_alive():
                    self.logger.warning("报告检查线程未能在5秒内退出")
    
    def auto_generate_weekly_report(self):
        """自动生成周报"""
        try:
            today = datetime.now()
            last_monday = today - timedelta(days=today.weekday() + 7)
            last_sunday = last_monday + timedelta(days=6)
            self.generate_report('weekly', last_monday, last_sunday)
            self.logger.info(f"自动生成周报: {last_monday.date()} 至 {last_sunday.date()}")
        except Exception as e:
            self.logger.error(f"自动生成周报失败: {e}")
    
    def auto_generate_monthly_report(self):
        """自动生成月报"""
        try:
            today = datetime.now()
            first_day_this_month = today.replace(day=1)
            last_day_last_month = first_day_this_month - timedelta(days=1)
            first_day_last_month = last_day_last_month.replace(day=1)
            self.generate_report('monthly', first_day_last_month, last_day_last_month)
            self.logger.info(f"自动生成月报: {first_day_last_month.date()} 至 {last_day_last_month.date()}")
        except Exception as e:
            self.logger.error(f"自动生成月报失败: {e}")
    
    def manual_generate_weekly_report(self):
        """手动生成周报"""
        try:
            today = datetime.now()
            monday = today - timedelta(days=today.weekday())
            sunday = monday + timedelta(days=6)
            
            df = self.get_all_data()
            if df.empty:
                messagebox.showwarning("没有数据", "没有监控数据。请先开始监控。")
                return
            
            success = self.generate_report('weekly', monday, sunday)
            if success:
                messagebox.showinfo(
                    self.get_text('reports'),
                    f"Weekly report generated!\n周报已生成！\n{monday.date()} - {sunday.date()}"
                )
            else:
                messagebox.showwarning("没有数据", f"日期范围内没有数据：\n{monday.date()} - {sunday.date()}")
        except Exception as e:
            self.logger.error(f"手动生成周报失败: {e}")
            messagebox.showerror("错误", f"Failed to generate weekly report:\n{e}")
    
    def manual_generate_monthly_report(self):
        """手动生成月报"""
        try:
            today = datetime.now()
            first_day = today.replace(day=1)
            last_day = today.replace(day=calendar.monthrange(today.year, today.month)[1])
            
            df = self.get_all_data()
            if df.empty:
                messagebox.showwarning("没有数据", "没有监控数据。请先开始监控。")
                return
            
            success = self.generate_report('monthly', first_day, last_day)
            if success:
                messagebox.showinfo(
                    self.get_text('reports'),
                    f"Monthly report generated!\n月报已生成！\n{first_day.date()} - {last_day.date()}"
                )
            else:
                messagebox.showwarning("没有数据", f"日期范围内没有数据：\n{first_day.date()} - {last_day.date()}")
        except Exception as e:
            self.logger.error(f"手动生成月报失败: {e}")
            messagebox.showerror("错误", f"Failed to generate monthly report:\n{e}")
    
    def generate_report(self, report_type, start_date, end_date):
        """生成CSV报告，注意csv写入要用newline=""避免多余空行"""
        try:
            df = self.get_all_data()
            if df.empty:
                self.logger.warning("没有数据可生成报告")
                return False
            
            start_datetime = datetime.combine(start_date, datetime.min.time())
            end_datetime = datetime.combine(end_date, datetime.max.time())
            mask = (df['timestamp'] >= start_datetime) & (df['timestamp'] <= end_datetime)
            df_report = df.loc[mask].copy()
            
            if df_report.empty:
                self.logger.warning(f"日期范围内没有数据: {start_date} 至 {end_date}")
                return False
            
            df_report['processed_uv275'] = df_report['uv275_absorbance'].copy()
            
            if df_report['is_anomaly'].any():
                df_report.loc[df_report['is_anomaly'], 'processed_uv275'] = np.nan
                df_report['processed_uv275'] = df_report['processed_uv275'].ffill().bfill()
            
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
            
            try:
                coeff = self.inactivation_coefficients[pathogen][season_zh][inactivation]
                df_report['chlorine_demand'] = df_report['processed_uv275'].apply(
                    lambda x: coeff["a"] * x + coeff["b"] if pd.notna(x) else None
                )
            except KeyError:
                self.logger.error(f"参数配置错误: {pathogen}-{season_zh}-{inactivation}")
                return False
            
            report_df = pd.DataFrame({
                '监测时间 / Monitoring Time': df_report['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S'),
                'UV275吸光度 / UV275 Absorbance (/cm)': df_report['processed_uv275'].round(6),
                '温度 / Temperature (℃)': df_report['temperature'].round(2) if 'temperature' in df_report.columns else None,
                'COD (mg/L)': df_report['cod'].round(2) if 'cod' in df_report.columns else None,
                '浊度 / Turbidity (NTU)': df_report['turbidity'].round(2) if 'turbidity' in df_report.columns else None,
                '加氯量 / Chlorine Dosage (mg/L)': df_report['chlorine_demand'].round(6)
            })
            
            report_df = report_df.dropna(axis=1, how='all')
            
            summary = {
                '报告类型 / Report Type': '周报 / Weekly Report' if report_type == 'weekly' else '月报 / Monthly Report',
                '起始日期 / Start Date': start_date.strftime('%Y-%m-%d'),
                '结束日期 / End Date': end_date.strftime('%Y-%m-%d'),
                '数据条数 / Data Count': len(df_report),
                '异常值数 / Anomaly Count': len(df_report[df_report['is_anomaly'] == True]),
                '平均UV275 / Avg UV275': f"{df_report['processed_uv275'].mean():.3f}",
                '平均加氯量 / Avg Chlorine': f"{df_report['chlorine_demand'].mean():.3f}",
                '病原菌类型 / Pathogen': pathogen,
                '季节 / Season': season,
                '灭活率 / Inactivation Rate': inactivation,
                '生成时间 / Generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            if report_type == 'weekly':
                week_num = start_date.isocalendar()[1]
                filename = f"周报_Week{week_num}_{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}.csv"
            else:
                filename = f"月报_Monthly_{start_date.strftime('%Y年%m月_%Y-%m')}.csv"
            
            filepath = os.path.join(self.reports_folder, filename)
            
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'a') as test_file:
                        pass
                except IOError:
                    timestamp = datetime.now().strftime('%H%M%S')
                    base, ext = os.path.splitext(filename)
                    filename = f"{base}_{timestamp}{ext}"
                    filepath = os.path.join(self.reports_folder, filename)
                    self.logger.warning(f"原文件被占用，生成新文件: {filename}")

            # 使用 newline='' 和 lineterminator='\n' 防止空白行
            with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                f.write("=" * 80 + "\n")
                f.write("报告摘要 / Report Summary\n")
                f.write("=" * 80 + "\n")
                for key, value in summary.items():
                    f.write(f"{key}: {value}\n")
                f.write("=" * 80 + "\n\n")
                
                # 使用统一换行符
                report_df.to_csv(f, index=False, mode='a', lineterminator='\n')
            
            self.logger.info(f"报告已生成: {filepath}")
            return True
            
        except PermissionError as e:
            self.logger.error(f"文件写入权限错误: {e}")
            messagebox.showerror("权限错误 / Permission Error",
                            f"无法写入文件（可能被其他程序占用）\n\n"
                            f"请关闭 Excel 等程序后重试。")
            return False
        except Exception as e:
            self.logger.error(f"生成报告失败: {e}")
            return False
    
    def open_reports_folder(self):
        """打开报告文件夹"""
        try:
            import sys
            import subprocess
            if sys.platform == 'win32':
                os.startfile(self.reports_folder)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', self.reports_folder])
            else:
                subprocess.Popen(['xdg-open', self.reports_folder])
        except Exception as e:
            self.logger.error(f"打开报告文件夹失败: {e}")
            messagebox.showerror("错误", f"Failed to open reports folder:\n{e}")
    
    def export_charts(self):
        """导出图表"""
        try:
            export_dialog = tk.Toplevel(self.root)
            export_dialog.title("导出图表 / Export Charts")
            export_dialog.geometry("700x650")
            export_dialog.resizable(True, True)
            export_dialog.minsize(650, 600)
            export_dialog.grab_set()
            
            # 居中显示
            export_dialog.update_idletasks()
            x = (export_dialog.winfo_screenwidth() // 2) - (export_dialog.winfo_width() // 2)
            y = (export_dialog.winfo_screenheight() // 2) - (export_dialog.winfo_height() // 2)
            export_dialog.geometry(f"+{x}+{y}")
            
            # 创建主容器框架
            main_container = ttk.Frame(export_dialog)
            main_container.pack(fill=tk.BOTH, expand=True)
            
            # 创建Canvas和滚动条
            canvas = tk.Canvas(main_container, bg=self.bg_color, highlightthickness=0)
            scrollbar = ttk.Scrollbar(main_container, orient="vertical", command=canvas.yview)
            scrollable_frame = ttk.Frame(canvas)
            
            scrollable_frame.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
            )
            
            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", width=680)
            canvas.configure(yscrollcommand=scrollbar.set)
            
            # 鼠标滚轮支持 - 使用局部绑定
            def _on_mousewheel(event):
                canvas.yview_scroll(int(-1*(event.delta/120)), "units")

            # 绑定到对话框而不是全局
            export_dialog.bind("<MouseWheel>", _on_mousewheel)

            # 对话框关闭时自动解绑（通过 grab_set 和 destroy
            
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # 标题
            title_frame = ttk.Frame(scrollable_frame)
            title_frame.pack(pady=15, padx=20, fill=tk.X)
            ttk.Label(title_frame, text="导出图表\nExport Charts", 
                    font=('Arial', 14, 'bold')).pack()
            
            # 说明
            info_frame = ttk.Frame(scrollable_frame)
            info_frame.pack(pady=5, padx=20, fill=tk.X)
            ttk.Label(info_frame, 
                    text="选择要导出的图表、格式和质量设置\nSelect charts, format and quality settings",
                    font=('Arial', 10), foreground='gray',
                    wraplength=580).pack()
            
            # 图表选择
            chart_frame = ttk.LabelFrame(scrollable_frame, text="选择图表 / Select Chart", padding=15)
            chart_frame.pack(pady=10, padx=20, fill=tk.X)
            
            chart_var = tk.StringVar(value='all')
            selected_param_name = self.selected_chart_param.get()
            
            chart_options = [
                ('all', '📈 全部4张图表 / All 4 Charts', 
                '导出当前显示的所有图表'),
                ('chart1', f'图表1: {selected_param_name} 时间序列\nChart 1: {selected_param_name} Time Series', 
                '参数随时间变化趋势'),
                ('chart2', f'📉 图表2: {selected_param_name} 数据分布\nChart 2: {selected_param_name} Distribution', 
                '参数数据分布直方图'),
                ('chart3', '💧 图表3: 加氯量随时间变化\nChart 3: Chlorine Dosage vs Time', 
                '推荐和实际加氯量对比'),
                ('chart4', '图表4: 加氯量分布\nChart 4: Chlorine Distribution', 
                '加氯量数据分布直方图')
            ]
            
            for value, text, desc in chart_options:
                rb_frame = ttk.Frame(chart_frame)
                rb_frame.pack(fill=tk.X, pady=5)
                
                ttk.Radiobutton(rb_frame, text=text, 
                            variable=chart_var, value=value).pack(anchor=tk.W)
                
                if desc:
                    ttk.Label(rb_frame, text=f"    {desc}", 
                            font=('Arial', 9), foreground='gray',
                            wraplength=550).pack(anchor=tk.W, padx=(20, 0))
            
            # 格式选择
            format_frame = ttk.LabelFrame(scrollable_frame, text="文件格式 / Format", padding=15)
            format_frame.pack(pady=10, padx=20, fill=tk.X)
            
            format_var = tk.StringVar(value='png')
            
            format_options = [
                ('png', 'PNG 图片 (推荐)', '通用图片格式，支持透明背景'),
                ('pdf', 'PDF 文档', '矢量格式，适合打印和文档'),
                ('svg', 'SVG 矢量图', '可缩放矢量图形，适合编辑')
            ]
            
            for value, text, desc in format_options:
                rb_frame = ttk.Frame(format_frame)
                rb_frame.pack(fill=tk.X, pady=3)
                
                ttk.Radiobutton(rb_frame, text=text, 
                            variable=format_var, value=value).pack(anchor=tk.W)
                ttk.Label(rb_frame, text=f"    {desc}", 
                        font=('Arial', 9), foreground='gray').pack(anchor=tk.W, padx=(20, 0))
            
            # DPI设置
            dpi_frame = ttk.LabelFrame(scrollable_frame, text="图片质量 / Quality (PNG only)", padding=15)
            dpi_frame.pack(pady=10, padx=20, fill=tk.X)
            
            dpi_var = tk.StringVar(value='300')
            
            dpi_info_frame = ttk.Frame(dpi_frame)
            dpi_info_frame.pack(fill=tk.X, pady=(0, 10))
            
            ttk.Label(dpi_info_frame, text="DPI 设置 / DPI Setting:", 
                    font=('Arial', 10)).pack(side=tk.LEFT)
            
            dpi_combo = ttk.Combobox(dpi_info_frame, textvariable=dpi_var, 
                                    values=['150', '300', '600', '1200'], 
                                    state='readonly', width=12)
            dpi_combo.pack(side=tk.LEFT, padx=10)
            
            dpi_desc = {
                '150': '📱 低质量 - 屏幕预览（文件小）',
                '300': '📄 标准质量 - 文档打印（推荐）',
                '600': '高质量 - 专业打印',
                '1200': '🎨 超高质量 - 出版印刷（文件大）'
            }
            
            dpi_label = ttk.Label(dpi_info_frame, text=dpi_desc['300'], 
                                font=('Arial', 9), foreground='blue')
            dpi_label.pack(side=tk.LEFT, padx=5)
            
            def update_dpi_desc(event=None):
                dpi_label.config(text=dpi_desc.get(dpi_var.get(), ''))
            
            dpi_combo.bind('<<ComboboxSelected>>', update_dpi_desc)
            
            result = {'confirmed': False}
            
            def on_confirm():
                result['confirmed'] = True
                result['format'] = format_var.get()
                result['dpi'] = int(dpi_var.get())
                result['chart'] = chart_var.get()
                export_dialog.destroy()
            
            def on_cancel():
                export_dialog.destroy()
            
            # 按钮区域（固定在底部）
            button_container = ttk.Frame(export_dialog)
            button_container.pack(side=tk.BOTTOM, fill=tk.X, pady=15, padx=20)
            
            button_frame = ttk.Frame(button_container)
            button_frame.pack()
            
            ttk.Button(button_frame, text="💾 导出 / Export", 
                    command=on_confirm, width=15).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_frame, text="取消 / Cancel", 
                    command=on_cancel, width=15).pack(side=tk.LEFT, padx=5)
            
            export_dialog.bind('<Return>', lambda e: on_confirm())
            export_dialog.bind('<Escape>', lambda e: on_cancel())
            
            self.root.wait_window(export_dialog)
            
            if not result['confirmed']:
                return
            
            file_format = result['format']
            chart_selection = result['chart']
            
            if chart_selection == 'all':
                chart_name = "All_Charts"
            else:
                chart_name = f"{chart_selection.capitalize()}"
            
            default_filename = f"UV275_{chart_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file_format}"
            
            filetypes = [(f"{file_format.upper()} files", f"*.{file_format}"), ("All files", "*.*")]
            
            file_path = filedialog.asksaveasfilename(
                title="保存图表 / Save Charts",
                defaultextension=f".{file_format}",
                filetypes=filetypes,
                initialfile=default_filename
            )
            
            if not file_path:
                return
            
            if chart_selection == 'all':
                if file_format == 'png':
                    self.fig.savefig(file_path, dpi=result['dpi'], bbox_inches='tight', 
                                facecolor=self.plot_bg_color)
                else:
                    self.fig.savefig(file_path, bbox_inches='tight', 
                                facecolor=self.plot_bg_color)
            else:
                self.export_single_chart(file_path, chart_selection, file_format, result['dpi'])
            
            messagebox.showinfo("导出成功 / Success", 
                            f"图表导出成功！\nChart(s) exported successfully!\n\n"
                            f"保存位置 / Saved to:\n{file_path}")
            self.logger.info(f"图表已导出: {file_path} (选择: {chart_selection})")
            
        except Exception as e:
            self.logger.error(f"导出图表失败: {e}")
            messagebox.showerror("错误 / Error", 
                            f"导出图表失败！\nFailed to export charts!\n\n{str(e)}")
    
    def export_single_chart(self, file_path, chart_selection, file_format, dpi):
        """导出单张图表，每次导出时时间轴图表需要重新绘制"""
        try:
            from matplotlib.figure import Figure
            import matplotlib.dates as mdates
            import numpy as np
            
            chart_map = {
                'chart1': self.ax1,
                'chart2': self.ax2,
                'chart3': self.ax3,
                'chart4': self.ax4
            }
            
            source_ax = chart_map[chart_selection]
            
            single_fig = Figure(figsize=(10, 6))
            single_ax = single_fig.add_subplot(111)
            
            # 检查是否为时间序列图表
            is_time_series = chart_selection in ['chart1', 'chart3']
            
            # 如果是时间序列，直接从数据源重新绘制
            if is_time_series:
                df = self.get_data_by_time_range()
                
                if not df.empty:
                    if chart_selection == 'chart1':
                        # 重绘图表1
                        selected_param_name = self.selected_chart_param.get()
                        chart_options = self.get_chart_param_options()
                        
                        if selected_param_name in chart_options:
                            param_tuple = chart_options[selected_param_name]
                            param_column, param_unit, param_label = param_tuple
                            
                            if param_column in df.columns:
                                single_ax.plot(df['timestamp'], df[param_column], 
                                            color='blue', linewidth=1.5, label=param_label)
                                
                                # 绘制异常点
                                anomaly_mask = df['is_anomaly'] == True
                                if anomaly_mask.any():
                                    single_ax.scatter(df[anomaly_mask]['timestamp'],
                                                    df[anomaly_mask][param_column],
                                                    color='red', s=50, 
                                                    label=self.get_text('anomaly_replaced'), 
                                                    zorder=5)
                                
                                single_ax.set_ylabel(f'{param_label} ({param_unit})', 
                                                fontsize=11, color=self.plot_fg_color)
                    
                    elif chart_selection == 'chart3':
                        # 重绘图表3
                        df_processed = df.copy()
                        df_processed['processed_uv275'] = df_processed['uv275_absorbance'].copy()
                        
                        if df_processed['is_anomaly'].any():
                            df_processed.loc[df_processed['is_anomaly'], 'processed_uv275'] = np.nan
                            df_processed['processed_uv275'] = df_processed['processed_uv275'].ffill().bfill()
                        
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
                        
                        try:
                            coeff = self.inactivation_coefficients[pathogen][season_zh][inactivation]
                            df_processed['chlorine_demand'] = df_processed['processed_uv275'].apply(
                                lambda x: coeff["a"] * x + coeff["b"] if pd.notna(x) else None
                            )
                            
                            single_ax.plot(df_processed['timestamp'], df_processed['chlorine_demand'],
                                        color='green', linewidth=1.5, 
                                        label=self.get_text('recommended_chlorine'))
                            
                            single_ax.axhline(y=self.current_chlorine_dosage, color='red', 
                                            linestyle='--', linewidth=1.5, 
                                            label=self.get_text('actual_chlorine'))
                            
                            single_ax.set_ylabel(self.get_text('chlorine_ylabel'), 
                                            fontsize=11, color=self.plot_fg_color)
                        except KeyError:
                            pass
                    
                    # 设置时间轴格式
                    single_ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d\n%H:%M'))
                    single_ax.xaxis.set_major_locator(mdates.AutoDateLocator())
                    single_fig.autofmt_xdate()
                    
                    single_ax.set_xlabel(self.get_text('time_label'), 
                                    fontsize=11, color=self.plot_fg_color)
            
            else:
                # 非时间序列图表：直接复制（chart2和chart4是直方图）
                for patch in source_ax.patches:
                    xy = patch.get_xy()
                    width = patch.get_width()
                    height = patch.get_height()
                    single_ax.bar(xy[0] + width/2, height, width=width,
                                color=patch.get_facecolor(),
                                edgecolor=patch.get_edgecolor(),
                                alpha=patch.get_alpha() if patch.get_alpha() else 1.0)
                
                single_ax.set_xlabel(source_ax.get_xlabel(), fontsize=11, color=self.plot_fg_color)
                single_ax.set_ylabel(source_ax.get_ylabel(), fontsize=11, color=self.plot_fg_color)
            
            # 设置标题和样式
            single_ax.set_title(source_ax.get_title(), fontsize=14, fontweight='bold', 
                            color=self.plot_fg_color)
            
            if source_ax.get_legend():
                single_ax.legend(loc='best')
            
            single_ax.grid(True, alpha=0.3)
            single_ax.set_facecolor(self.plot_bg_color)
            single_fig.patch.set_facecolor(self.plot_bg_color)
            single_ax.tick_params(colors=self.plot_fg_color)
            
            for spine in single_ax.spines.values():
                spine.set_edgecolor(self.plot_fg_color)
            
            single_fig.tight_layout()
            
            if file_format == 'png':
                single_fig.savefig(file_path, dpi=dpi, bbox_inches='tight', 
                                facecolor=self.plot_bg_color)
            else:
                single_fig.savefig(file_path, bbox_inches='tight', 
                                facecolor=self.plot_bg_color)
            
            plt.close(single_fig)
            
        except Exception as e:
            self.logger.error(f"导出单张图表失败: {e}")
            raise
    

