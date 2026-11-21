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

class ExportMixin:
    """数据导出与进度管理相关方法"""

    def export_data(self):
        """导出数据"""
        try:
            # 先查最近30天判断是否有数据
            df_preview = self.get_all_data(days_limit=30)
            
            if df_preview.empty:
                # 如果最近30天没数据，尝试查全表
                df_preview = self.get_all_data(days_limit=None)
                if df_preview.empty:
                    messagebox.showinfo("提示 / Info", 
                        "没有数据可导出！\nNo data to export!")
                    return
            
            # 用于显示日期范围（使用全表数据）
            df_full = self.get_all_data(days_limit=None)

            # 添加空数据检查
            if df_full.empty:
                messagebox.showinfo("提示 / Info", 
                    "没有数据可导出！\nNo data to export!")
                return

            min_date = df_full['timestamp'].min().date()
            max_date = df_full['timestamp'].max().date()
            
            # 创建日期选择对话框
            date_dialog = tk.Toplevel(self.root)
            date_dialog.title("选择导出时间范围 / Select Export Time Range")
            date_dialog.geometry("720x600")
            date_dialog.resizable(True, True)
            date_dialog.minsize(680, 600)
            date_dialog.grab_set()
            
            # 居中显示
            date_dialog.update_idletasks()
            x = (date_dialog.winfo_screenwidth() // 2) - (date_dialog.winfo_width() // 2)
            y = (date_dialog.winfo_screenheight() // 2) - (date_dialog.winfo_height() // 2)
            date_dialog.geometry(f"+{x}+{y}")
            
            # 创建主容器框架
            main_container = ttk.Frame(date_dialog)
            main_container.pack(fill=tk.BOTH, expand=True)
            
            # 创建Canvas和滚动条
            canvas = tk.Canvas(main_container, bg=self.bg_color, highlightthickness=0)
            scrollbar = ttk.Scrollbar(main_container, orient="vertical", command=canvas.yview)
            scrollable_frame = ttk.Frame(canvas)
            
            scrollable_frame.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
            )
            
            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", width=700)
            canvas.configure(yscrollcommand=scrollbar.set)
            
            # 可使用鼠标滚轮滑动
            def _on_mousewheel(event):
                canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            
            # 鼠标滚轮范围限制在文字框而不是全局
            date_dialog.bind("<MouseWheel>", _on_mousewheel)
            
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # 标题
            title_frame = ttk.Frame(scrollable_frame)
            title_frame.pack(pady=15, padx=20, fill=tk.X)
            
            ttk.Label(title_frame, text="📅", font=('Arial', 36)).pack()
            ttk.Label(title_frame, text="选择导出时间范围\nSelect Export Time Range", 
                    font=('Arial', 14, 'bold')).pack(pady=(10, 0))
            
            # 数据范围信息
            info_frame = ttk.Frame(scrollable_frame)
            info_frame.pack(pady=10, padx=20, fill=tk.X)
            
            info_text = (
                f"数据库中共有 {len(df_full)} 条记录\n"
                f"Database contains {len(df_full)} records\n\n"
                f"📅 数据时间范围 / Data time range:\n"
                f"   {min_date} 至 / to {max_date}"
            )
            
            ttk.Label(info_frame, text=info_text, 
                    font=('Arial', 10), justify=tk.CENTER,
                    foreground='blue', wraplength=620).pack()
            
            # 快捷选项
            quick_frame = ttk.LabelFrame(scrollable_frame, text="⚡ 快捷选项 / Quick Options", padding=15)
            quick_frame.pack(pady=10, padx=20, fill=tk.X)
            
            export_option = tk.StringVar(value="custom")
            
            quick_options = [
                ('24h', '最近24小时 / Last 24 Hours', 
                '导出最近一天的数据'),
                ('7d', '📅 最近7天 / Last 7 Days', 
                '导出最近一周的数据'),
                ('30d', '📆 最近30天 / Last 30 Days', 
                '导出最近一个月的数据'),
                ('all', '全部数据 / All Data', 
                f'导出所有 {len(df_full)} 条记录'),
                ('custom', '自定义日期范围 / Custom Range', 
                '自定义起止日期')
            ]
            
            for value, text, desc in quick_options:
                rb_frame = ttk.Frame(quick_frame)
                rb_frame.pack(fill=tk.X, pady=3)
                
                ttk.Radiobutton(rb_frame, text=text, 
                            variable=export_option, value=value).pack(anchor=tk.W)
                ttk.Label(rb_frame, text=f"    {desc}", 
                        font=('Arial', 9), foreground='gray').pack(anchor=tk.W, padx=(25, 0))
            
            # 自定义日期范围
            custom_frame = ttk.LabelFrame(scrollable_frame, text="📅 自定义日期范围 / Custom Date Range", padding=15)
            custom_frame.pack(pady=10, padx=20, fill=tk.X)
            
            # 开始日期
            start_frame = ttk.Frame(custom_frame)
            start_frame.pack(fill=tk.X, pady=8)
            
            ttk.Label(start_frame, text="📅 开始日期 / Start Date:", 
                    font=('Arial', 10, 'bold'), width=20).pack(side=tk.LEFT)
            
            start_date_entry = DateEntry(start_frame, width=20, 
                                        background='darkblue',
                                        foreground='white', 
                                        borderwidth=2,
                                        date_pattern='yyyy-mm-dd',
                                        mindate=min_date,
                                        maxdate=max_date,
                                        font=('Arial', 10))
            start_date_entry.set_date(min_date)
            start_date_entry.pack(side=tk.LEFT, padx=10)
            
            ttk.Label(start_frame, text="(最早 / Earliest)", 
                    font=('Arial', 9), foreground='gray').pack(side=tk.LEFT)
            
            # 结束日期
            end_frame = ttk.Frame(custom_frame)
            end_frame.pack(fill=tk.X, pady=8)
            
            ttk.Label(end_frame, text="📅 结束日期 / End Date:", 
                    font=('Arial', 10, 'bold'), width=20).pack(side=tk.LEFT)
            
            end_date_entry = DateEntry(end_frame, width=20,
                                    background='darkblue',
                                    foreground='white',
                                    borderwidth=2,
                                    date_pattern='yyyy-mm-dd',
                                    mindate=min_date,
                                    maxdate=max_date,
                                    font=('Arial', 10))
            end_date_entry.set_date(max_date)
            end_date_entry.pack(side=tk.LEFT, padx=10)
            
            ttk.Label(end_frame, text="(最晚 / Latest)", 
                    font=('Arial', 9), foreground='gray').pack(side=tk.LEFT)
            
            # 日期范围预览
            preview_frame = ttk.Frame(custom_frame)
            preview_frame.pack(fill=tk.X, pady=(10, 0))
            
            preview_label = ttk.Label(preview_frame, 
                                    text="", 
                                    font=('Arial', 9), 
                                    foreground='green')
            preview_label.pack()
            
            def update_preview(event=None):
                try:
                    start = start_date_entry.get_date()
                    end = end_date_entry.get_date()
                    days = (end - start).days + 1
                    
                    if start > end:
                        preview_label.config(
                            text="注意：开始日期不能晚于结束日期 / Start date cannot be later than end date",
                            foreground='red')
                    else:
                        preview_label.config(
                            text=f"将导出 {days} 天的数据 / Will export {days} days of data",
                            foreground='green')
                except:
                    preview_label.config(text="", foreground='gray')
            
            start_date_entry.bind('<<DateEntrySelected>>', update_preview)
            end_date_entry.bind('<<DateEntrySelected>>', update_preview)
            update_preview()
            
            result = {'confirmed': False, 'option': None, 'start': None, 'end': None}
            
            def on_confirm():
                option = export_option.get()
                
                if option == "custom":
                    start = start_date_entry.get_date()
                    end = end_date_entry.get_date()
                    
                    if start > end:
                        messagebox.showerror("日期错误 / Date Error",
                            "开始日期不能晚于结束日期！\n\n"
                            "Start date cannot be later than end date!",
                            parent=date_dialog)
                        return
                    
                    result['start'] = start
                    result['end'] = end
                
                result['confirmed'] = True
                result['option'] = option
                date_dialog.destroy()
            
            def on_cancel():
                date_dialog.destroy()
            
            # 按钮区域（固定在底部）
            button_container = ttk.Frame(date_dialog)
            button_container.pack(side=tk.BOTTOM, fill=tk.X, pady=15, padx=20)
            
            button_frame = ttk.Frame(button_container)
            button_frame.pack()
            
            ttk.Button(button_frame, text="确定 / Confirm", 
                    command=on_confirm, width=15).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_frame, text="取消 / Cancel", 
                    command=on_cancel, width=15).pack(side=tk.LEFT, padx=5)
            
            date_dialog.bind('<Return>', lambda e: on_confirm())
            date_dialog.bind('<Escape>', lambda e: on_cancel())
            
            self.root.wait_window(date_dialog)
            
            if not result['confirmed']:
                return
            
            option = result['option']
            
            # 根据选项获取数据
            if option == "24h":
                df_to_export = self.get_recent_data(hours=24)
                time_range = "Last_24h" if self.current_language == 'en_US' else "最近24小时"
            elif option == "7d":
                df_to_export = self.get_recent_data_days(days=7)
                time_range = "Last_7d" if self.current_language == 'en_US' else "最近7天"
            elif option == "30d":
                df_to_export = self.get_recent_data_days(days=30)
                time_range = "Last_30d" if self.current_language == 'en_US' else "最近30天"
            elif option == "all":
                df_to_export = self.get_all_data(days_limit=None)  # 这里改了
                time_range = "All" if self.current_language == 'en_US' else "全部"
            else:  # custom
                start_datetime = datetime.combine(result['start'], datetime.min.time())
                end_datetime = datetime.combine(result['end'], datetime.max.time())
                
                df_full = self.get_all_data(days_limit=None)
                mask = (df_full['timestamp'] >= start_datetime) & (df_full['timestamp'] <= end_datetime)
                df_to_export = df_full.loc[mask].copy()
                time_range = f"{result['start']}_to_{result['end']}"
            
            if df_to_export.empty:
                messagebox.showinfo("提示 / Info",
                    f"选择的时间范围内没有数据！\n\n"
                    f"No data in selected range!")
                return
            
            # 处理数据
            df_processed = df_to_export.copy()
            
            df_processed['processed_uv275'] = df_processed['uv275_absorbance'].copy()
            
            if df_processed['is_anomaly'].any():
                df_processed.loc[df_processed['is_anomaly'], 'processed_uv275'] = np.nan
                df_processed['processed_uv275'] = df_processed['processed_uv275'].ffill()
                df_processed['processed_uv275'] = df_processed['processed_uv275'].bfill()
            
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
            except KeyError:
                messagebox.showerror("参数错误 / Parameter Error",
                    f"当前选择的参数配置不存在！\n\n"
                    f"Parameter configuration does not exist!")
                return
            
            export_df = pd.DataFrame({
                'Time / 监测时间': df_processed['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S'),
                'UV275 Absorbance / UV275吸光度 (/cm)': df_processed['processed_uv275'].round(6),
                'Temperature / 温度 (℃)': df_processed['temperature'].round(2) if 'temperature' in df_processed.columns else None,
                'COD (mg/L)': df_processed['cod'].round(2) if 'cod' in df_processed.columns else None,
                'Turbidity / 浊度 (NTU)': df_processed['turbidity'].round(2) if 'turbidity' in df_processed.columns else None,
                'Chlorine Dosage / 加氯量 (mg/L)': df_processed['chlorine_demand'].round(6)
            })
            
            export_df = export_df.dropna(axis=1, how='all')
            
            # 生成文件名
            safe_time_range = time_range.replace(':', '-').replace(' ', '_').replace('&', 'and').replace('/', '-')
            safe_time_range = "".join(c if c.isalnum() or c in ('_', '-', '至', 'to') else '_' for c in safe_time_range)
            default_filename = f"UV275_Data_Export_{safe_time_range}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            file_path = filedialog.asksaveasfilename(
                title="保存导出数据 / Save Exported Data",
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                initialfile=default_filename
            )
            
            if not file_path:
                return
            
            # 导出时显示进度条，供用户查看导出进度
            self.export_with_progress(export_df, file_path, time_range, pathogen, season, inactivation)
            
        except Exception as e:
            self.logger.error(f"导出数据时发生错误: {e}")
            messagebox.showerror("导出错误 / Export Error", 
                            f"导出失败！\nExport failed!\n\n{str(e)}")
    
    def export_with_progress(self, df, file_path, time_range, pathogen, season, inactivation):
        """导出时显示进度条的方法"""
        # 创建进度窗口
        progress_window = tk.Toplevel(self.root)
        progress_window.title("导出中 / Exporting")
        progress_window.geometry("550x280")
        progress_window.resizable(False, False)
        progress_window.minsize(500, 250)
        progress_window.grab_set()
        
        # 居中显示
        progress_window.update_idletasks()
        x = (progress_window.winfo_screenwidth() // 2) - (progress_window.winfo_width() // 2)
        y = (progress_window.winfo_screenheight() // 2) - (progress_window.winfo_height() // 2)
        progress_window.geometry(f"+{x}+{y}")
        
        # 标题
        title_frame = ttk.Frame(progress_window)
        title_frame.pack(pady=20, padx=20, fill=tk.X)
        
        ttk.Label(title_frame, text="💾", font=('Arial', 36)).pack()
        ttk.Label(title_frame, text="正在导出数据...\nExporting data...", 
                font=('Arial', 12, 'bold')).pack(pady=(10, 0))
        
        # 进度条
        progress_bar = ttk.Progressbar(progress_window, length=450, mode='determinate')
        progress_bar.pack(pady=20, padx=20)
        
        # 进度文本
        progress_label = ttk.Label(progress_window, text="0%", font=('Arial', 11, 'bold'))
        progress_label.pack(pady=5)
        
        # 状态文本
        status_label = ttk.Label(progress_window, text="准备中... / Preparing...", 
                                font=('Arial', 10), foreground='gray',
                                wraplength=480)
        status_label.pack(pady=8)
        
        # 数据信息
        info_label = ttk.Label(progress_window, 
                            text=f"数据量 / Data count: {len(df)} 条记录", 
                            font=('Arial', 9), foreground='blue')
        info_label.pack(pady=5)
        
        def export_task():
            """后台导出任务"""
            try:
                total_rows = len(df)
                chunk_size = max(1, total_rows // 10)
                
                # 更新状态
                self.root.after(0, lambda: status_label.config(text="📝 写入文件... / Writing to file..."))
                self.root.after(0, lambda: progress_bar.config(value=10))
                self.root.after(0, lambda: progress_label.config(text="10%"))
                
                # 分块写入文件
                chunks_written = 0
                with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
                    df.iloc[:0].to_csv(f, index=False)
                    
                    for i in range(0, total_rows, chunk_size):
                        chunk = df.iloc[i:i+chunk_size]
                        chunk.to_csv(f, index=False, header=False, mode='a')
                        
                        chunks_written += 1
                        progress_value = 10 + (chunks_written / 10) * 80
                        
                        self.root.after(0, lambda p=progress_value: progress_bar.config(value=p))
                        self.root.after(0, lambda p=progress_value: progress_label.config(text=f"{int(p)}%"))
                        self.root.after(0, lambda i=i, c=chunk_size, t=total_rows: status_label.config(
                            text=f"进度 / Progress: {min(i+c, t)}/{t} 条记录"))
                        
                        time.sleep(0.05)
                
                # 完成
                self.root.after(0, lambda: progress_bar.config(value=100))
                self.root.after(0, lambda: progress_label.config(text="100%"))
                self.root.after(0, lambda: status_label.config(text="导出完成！ / Completed!"))
                
                time.sleep(0.5)
                
                self.root.after(0, progress_window.destroy)
                
                message = (
                    f"数据导出成功！\nData exported successfully!\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📅 导出范围 / Range: {time_range}\n"
                    f"数据条数 / Count: {len(df)}\n"
                    f"🦠 病原菌 / Pathogen: {pathogen}\n"
                    f"季节 / Season: {season}\n"
                    f"💧 灭活率 / Rate: {inactivation}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📁 保存路径 / Path:\n{file_path}"
                )
                
                self.root.after(0, lambda: messagebox.showinfo("导出完成 / Export Completed", message))
                self.logger.info(f"数据导出完成: {file_path}")
                
            except Exception as e:
                self.root.after(0, progress_window.destroy)
                self.root.after(0, lambda: messagebox.showerror("导出错误 / Export Error", 
                                                            f"导出失败！\nExport failed!\n\n{str(e)}"))
                self.logger.error(f"导出失败: {e}")
        
        # 启动后台线程
        export_thread = threading.Thread(target=export_task, daemon=True)
        export_thread.start()
    

