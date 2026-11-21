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
from utils import safe_gui_operation

class DisplayMixin:
    """界面显示更新、参数手册、状态指示与图表刷新相关方法"""

    def get_chart_param_options(self):
        """获取图表参数选项"""
        if self.current_language == 'zh_CN':
            return {
                "UV275吸光度": ("uv275_absorbance", "/cm", "紫外吸光度"),
                "温度": ("temperature", "℃", "温度"),
                "COD": ("cod", "mg/L", "COD浓度"),
                "浊度": ("turbidity", "NTU", "浊度"),
                "湿度": ("humidity", "%RH", "湿度"),
                "可见光吸光度": ("visible_absorbance", "/cm", "可见光吸光度")
            }
        else:
            return {
                "UV275 Absorbance": ("uv275_absorbance", "/cm", "UV275 Absorbance"),
                "Temperature": ("temperature", "℃", "Temperature"),
                "COD": ("cod", "mg/L", "COD"),
                "Turbidity": ("turbidity", "NTU", "Turbidity"),
                "Humidity": ("humidity", "%RH", "Humidity"),
                "Visible Absorbance": ("visible_absorbance", "/cm", "Visible Absorbance")
            }
    
    def get_available_ports(self):
        """获取可用串口列表"""
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]
    
    def refresh_ports(self):
        """刷新串口列表"""
        try:
            for widget in self.root.winfo_children():
                self.update_port_combobox(widget)
            messagebox.showinfo("成功", "Port list refreshed!\n串口列表已刷新！")
        except Exception as e:
            messagebox.showerror("错误", f"Failed to refresh ports:\n刷新串口列表失败: {e}")
    
    def update_port_combobox(self, widget):
        """递归更新串口下拉框"""
        if isinstance(widget, ttk.Combobox) and widget.cget('textvariable') == str(self.port_var):
            widget['values'] = self.get_available_ports()
        for child in widget.winfo_children():
            self.update_port_combobox(child)
    
    def save_serial_settings(self):
        """保存串口设置"""
        try:
            self.serial_config['port'] = self.port_var.get()
            self.serial_config['baudrate'] = int(self.baudrate_var.get())
            self.serial_config['slave_address'] = int(self.slave_addr_var.get())
            self.save_serial_config()
            messagebox.showinfo("成功", "Serial config saved!\n串口配置已保存！")
        except Exception as e:
            messagebox.showerror("错误", f"Failed to save config:\n保存串口配置失败: {e}")
    
    def open_parameter_manual(self):
        """打开参数手册"""
        manual_file = 'parameter_manual.txt'
        if not os.path.exists(manual_file):
            self.create_parameter_manual()
        try:
            import sys
            if sys.platform == 'win32':
                os.startfile(manual_file)
            elif sys.platform == 'darwin':
                os.system(f'open "{manual_file}"')
            else:
                os.system(f'xdg-open "{manual_file}"')
            messagebox.showinfo("提示", f"Parameter manual opened!\n已打开参数手册: {manual_file}")
        except Exception as e:
            messagebox.showerror("错误", f"Cannot open manual:\n无法打开参数手册: {e}")
    
    def create_parameter_manual(self):
        """创建参数手册文件"""
        try:
            lines = []
            lines.append("=" * 80)
            lines.append("UV275水质监控系统 - 参数手册")
            lines.append("UV275 Water Quality Monitoring System - Parameter Manual")
            lines.append("=" * 80)
            lines.append("")
            lines.append(f"创建时间 / Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append("")
            
            lines.append("-" * 80)
            lines.append("📐 参数方程 / Equation")
            lines.append("-" * 80)
            lines.append("")
            lines.append("  加氯量 (mg/L) = k × UV275吸光度 (/cm) + b")
            lines.append("  Chlorine Dosage (mg/L) = k × UV275 Absorbance (/cm) + b")
            lines.append("")
            
            lines.append("=" * 80)
            lines.append("详细参数表 / Detailed Parameters")
            lines.append("=" * 80)
            lines.append("")
            
            for pathogen, seasons_data in sorted(self.inactivation_coefficients.items()):
                lines.append("+" + "-" * 78 + "+")
                lines.append(f"| 病原菌 / Pathogen: {pathogen:<60} |")
                lines.append("+" + "-" * 78 + "+")
                lines.append("")
                
                for season, inactivation_data in sorted(seasons_data.items()):
                    lines.append(f"  季节 / Season: {season}")
                    lines.append("  " + "─" * 74)
                    lines.append("")
                    
                    for inactivation, coeffs in sorted(inactivation_data.items()):
                        a = coeffs.get('a', 0)
                        b = coeffs.get('b', 0)
                        lines.append(f"    灭活率 / Inactivation Rate: {inactivation}")
                        lines.append(f"      斜率 k  / Slope k     : {a:>10.3f}")
                        lines.append(f"      截距 b  / Intercept b: {b:>10.3f}")
                        lines.append(f"      方程 / Equation      : Cl = {a:.3f} × UV275 + {b:.3f}")
                        lines.append("")
                    
                    lines.append("")
                
                lines.append("")
            
            with open('parameter_manual.txt', 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            
            self.logger.info("参数手册已创建")
            
        except Exception as e:
            self.logger.error(f"创建参数手册失败: {e}")
    
    def update_parameter_display(self):
        """更新参数显示区域"""
        try:
            if not hasattr(self, 'equation_label') or not hasattr(self, 'param_a_var') or not hasattr(self, 'param_b_var'):
                return
            
            pathogen = self.selected_pathogen.get()
            season = self.selected_season.get()
            inactivation = self.selected_inactivation.get()
            
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
                        coeff = self.inactivation_coefficients[pathogen][season_zh][inactivation]
                        
                        equation_text = f"{self.get_text('current_equation')}: Cl = {coeff['a']:.3f} × UV275 + {coeff['b']:.3f}"
                        self.equation_label.config(text=equation_text)
                        
                        self.param_a_var.set(f"{coeff['a']:.3f}")
                        self.param_b_var.set(f"{coeff['b']:.3f}")
                        
                        self.logger.info(f"当前参数 - {pathogen}, {season_zh}, {inactivation}: a={coeff['a']}, b={coeff['b']}")
                    else:
                        self.equation_label.config(text=f"{self.get_text('current_equation')}: --")
                        self.param_a_var.set("")
                        self.param_b_var.set("")
                else:
                    self.equation_label.config(text=f"{self.get_text('current_equation')}: --")
                    self.param_a_var.set("")
                    self.param_b_var.set("")
            else:
                self.equation_label.config(text=f"{self.get_text('current_equation')}: --")
                self.param_a_var.set("")
                self.param_b_var.set("")
                
        except Exception as e:
            self.logger.error(f"更新参数显示失败: {e}")
            if hasattr(self, 'equation_label'):
                self.equation_label.config(text=f"{self.get_text('current_equation')}: Error")
            if hasattr(self, 'param_a_var'):
                self.param_a_var.set("")
            if hasattr(self, 'param_b_var'):
                self.param_b_var.set("")
    
    def update_status_indicator(self, status='ready', color='green'):
        """更新状态指示器"""
        try:
            status_text = {
                'ready': self.get_text('status_ready'),
                'monitoring': 'Monitoring / 监控中',
                'stopped': 'Stopped / 已停止',
                'error': 'Error / 错误'
            }
            
            text = status_text.get(status, status)
            
            if hasattr(self, 'status_label'):
                self.status_label.config(text=text, foreground=color)
        except Exception as e:
            self.logger.error(f"更新状态指示器失败: {e}")
    
    @safe_gui_operation()
    def update_data_display(self):
        """更新数据显示"""
        try:
            df = self.get_all_data()
            
            if df.empty:
                self.current_uv275_label.config(text=f"{self.get_text('current_uv275')}: --")
                self.current_temp_label.config(text=f"{self.get_text('current_temp')}: --")
                self.current_cod_label.config(text=f"{self.get_text('current_cod')}: --")
                self.current_turbidity_label.config(text=f"{self.get_text('current_turbidity')}: --")
                self.current_chlorine_label.config(text=f"{self.get_text('recommended_chlorine')}: --")
                self.avg_chlorine_label.config(text=f"{self.get_text('avg_24h_chlorine')}: --")
                self.avg_30d_chlorine_label.config(text=f"{self.get_text('avg_30d_chlorine')}: --")
                
                self.total_count_label.config(text=f"{self.get_text('total_count')}: 0")
                self.anomaly_rate_label.config(text=f"{self.get_text('anomaly_rate')}: 0%")
                self.detection_method_label.config(text=f"{self.get_text('detection_method')}: --")
                self.last_update_label.config(text=f"{self.get_text('last_update')}: --")
                return
            
            latest = df.iloc[-1]
            
            uv275 = latest['uv275_absorbance']
            temp = latest.get('temperature', None)
            cod = latest.get('cod', None)
            turbidity = latest.get('turbidity', None)
            
            self.current_uv275_label.config(
                text=f"{self.get_text('current_uv275')}: {uv275:.3f} /cm" if pd.notna(uv275) else f"{self.get_text('current_uv275')}: --"
            )
            self.current_temp_label.config(
                text=f"{self.get_text('current_temp')}: {temp:.2f} ℃" if pd.notna(temp) else f"{self.get_text('current_temp')}: --"
            )
            self.current_cod_label.config(
                text=f"{self.get_text('current_cod')}: {cod:.2f} mg/L" if pd.notna(cod) else f"{self.get_text('current_cod')}: --"
            )
            self.current_turbidity_label.config(
                text=f"{self.get_text('current_turbidity')}: {turbidity:.2f} NTU" if pd.notna(turbidity) else f"{self.get_text('current_turbidity')}: --"
            )
            
            if pd.notna(uv275) and not latest['is_anomaly']:
                chlorine_demand = self.calculate_chlorine_demand(uv275)
                if chlorine_demand is not None:
                    self.current_chlorine_label.config(
                        text=f"{self.get_text('recommended_chlorine')}: {chlorine_demand:.3f} mg/L"
                    )
                    
                    # 根据加氯量是否充足更新指示灯颜色（红绿灯）
                    is_sufficient = self.current_chlorine_dosage >= chlorine_demand
                    if is_sufficient:
                        self.indicator_canvas.itemconfig(self.green_light, fill='green')
                        self.indicator_canvas.itemconfig(self.red_light, fill='lightgray')
                    else:
                        self.indicator_canvas.itemconfig(self.green_light, fill='lightgray')
                        self.indicator_canvas.itemconfig(self.red_light, fill='red')
                else:
                    self.current_chlorine_label.config(text=f"{self.get_text('recommended_chlorine')}: --")
            else:
                self.current_chlorine_label.config(text=f"{self.get_text('recommended_chlorine')}: -- (异常值)")
            
            recent_24h = self.get_recent_data(hours=24)
            if not recent_24h.empty:
                normal_data_24h = recent_24h[recent_24h['is_anomaly'] == False]
                if not normal_data_24h.empty:
                    avg_chlorine_24h = normal_data_24h['uv275_absorbance'].apply(self.calculate_chlorine_demand).mean()
                    self.avg_chlorine_label.config(
                        text=f"{self.get_text('avg_24h_chlorine')}: {avg_chlorine_24h:.3f} mg/L"
                    )
                else:
                    self.avg_chlorine_label.config(text=f"{self.get_text('avg_24h_chlorine')}: --")
            else:
                self.avg_chlorine_label.config(text=f"{self.get_text('avg_24h_chlorine')}: --")
            
            recent_30d = self.get_recent_data_days(days=30)
            if not recent_30d.empty:
                normal_data_30d = recent_30d[recent_30d['is_anomaly'] == False]
                if not normal_data_30d.empty:
                    avg_chlorine_30d = normal_data_30d['uv275_absorbance'].apply(self.calculate_chlorine_demand).mean()
                    self.avg_30d_chlorine_label.config(
                        text=f"{self.get_text('avg_30d_chlorine')}: {avg_chlorine_30d:.3f} mg/L"
                    )
                else:
                    self.avg_30d_chlorine_label.config(text=f"{self.get_text('avg_30d_chlorine')}: --")
            else:
                self.avg_30d_chlorine_label.config(text=f"{self.get_text('avg_30d_chlorine')}: --")
            
            total_count = len(df)
            anomaly_count = df['is_anomaly'].sum()
            anomaly_rate = (anomaly_count / total_count * 100) if total_count > 0 else 0
            
            method = "Empirical / 经验值" if self.should_use_empirical_method() else "Statistical / 统计"
            
            self.total_count_label.config(text=f"{self.get_text('total_count')}: {total_count}")
            self.anomaly_rate_label.config(text=f"{self.get_text('anomaly_rate')}: {anomaly_rate:.2f}%")
            self.detection_method_label.config(text=f"{self.get_text('detection_method')}: {method}")
            self.last_update_label.config(
                text=f"{self.get_text('last_update')}: {latest['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
        except Exception as e:
            self.logger.error(f"更新数据显示失败: {e}")

    @safe_gui_operation()
    def update_waterplant_display(self):
        """更新水厂数据面板显示（新增）

        从 WaterplantReaderMixin 提供的接口读取最新数据，更新以下内容：
        - 连接状态 (已连接/未连接/数据过期)
        - 最近推送时间戳
        - 4 路浊度实时值
        - 3 路工艺浊度去除率
        - 隐孢子虫风险等级（基于 GAC 出水浊度）
        - 隐孢子虫风险红绿灯
        """
        try:
            # 检查水厂模块是否存在且启用
            if not hasattr(self, 'waterplant_enabled') or not self.waterplant_enabled:
                self._set_waterplant_labels_offline()
                return
            
            status = self.get_waterplant_status()
            latest = self.get_waterplant_latest()
            
            # ── 连接状态 ──────────────────────────────
            if latest is None:
                # 模块已启用但从未读到数据
                self.waterplant_status_label.config(
                    text=self.get_text('waterplant_offline'), foreground='red'
                )
                self._set_waterplant_labels_offline()
                return
            
            is_stale = status.get('is_stale', False)
            if is_stale:
                self.waterplant_status_label.config(
                    text=self.get_text('waterplant_stale'), foreground='orange'
                )
            else:
                self.waterplant_status_label.config(
                    text=self.get_text('waterplant_online'), foreground='green'
                )
            
            # ── 最近推送时间 ──────────────────────────
            record_time = latest.get('record_time')
            if record_time:
                time_str = record_time.strftime('%Y-%m-%d %H:%M:%S') \
                    if hasattr(record_time, 'strftime') else str(record_time)
                self.waterplant_last_update_label.config(
                    text=f"{self.get_text('waterplant_last_update')}: {time_str}"
                )
            
            # ── 4 路浊度 ──────────────────────────────
            def fmt_turb(value, label_key):
                if value is None:
                    return f"{self.get_text(label_key)}: --"
                return f"{self.get_text(label_key)}: {value:.3f} NTU"
            
            self.waterplant_raw_turb_label.config(
                text=fmt_turb(latest.get('raw_turbidity'), 'waterplant_raw_turb'))
            self.waterplant_sand_turb_label.config(
                text=fmt_turb(latest.get('sand_filter_turbidity'), 'waterplant_sand_turb'))
            self.waterplant_gac_turb_label.config(
                text=fmt_turb(latest.get('gac_turbidity'), 'waterplant_gac_turb'))
            self.waterplant_effluent_turb_label.config(
                text=fmt_turb(latest.get('effluent_turbidity'), 'waterplant_effluent_turb'))
            
            # ── 3 路浊度去除率 ────────────────────────
            removals = self.get_turbidity_removal_rates() or {}
            def fmt_removal(value, label_key):
                if value is None:
                    return f"{self.get_text(label_key)}: --"
                return f"{self.get_text(label_key)}: {value:.1f}%"
            
            self.waterplant_sand_removal_label.config(
                text=fmt_removal(removals.get('sand_filter_removal'), 'waterplant_sand_removal'))
            self.waterplant_gac_removal_label.config(
                text=fmt_removal(removals.get('gac_removal'), 'waterplant_gac_removal'))
            self.waterplant_effluent_removal_label.config(
                text=fmt_removal(removals.get('effluent_removal'), 'waterplant_effluent_removal'))
            
            # ── 隐孢子虫风险评估 ──────────────────────
            gac_turb = latest.get('gac_turbidity')
            self._update_cryptosporidium_risk(gac_turb)
            
        except Exception as e:
            self.logger.error(f"更新水厂数据显示失败: {e}", exc_info=True)

    def _set_waterplant_labels_offline(self):
        """将全部水厂数据标签重置为未连接状态"""
        try:
            self.waterplant_status_label.config(
                text=self.get_text('waterplant_offline'), foreground='gray'
            )
            self.waterplant_last_update_label.config(
                text=f"{self.get_text('waterplant_last_update')}: --")
            self.waterplant_raw_turb_label.config(
                text=f"{self.get_text('waterplant_raw_turb')}: --")
            self.waterplant_sand_turb_label.config(
                text=f"{self.get_text('waterplant_sand_turb')}: --")
            self.waterplant_gac_turb_label.config(
                text=f"{self.get_text('waterplant_gac_turb')}: --")
            self.waterplant_effluent_turb_label.config(
                text=f"{self.get_text('waterplant_effluent_turb')}: --")
            self.waterplant_sand_removal_label.config(
                text=f"{self.get_text('waterplant_sand_removal')}: --")
            self.waterplant_gac_removal_label.config(
                text=f"{self.get_text('waterplant_gac_removal')}: --")
            self.waterplant_effluent_removal_label.config(
                text=f"{self.get_text('waterplant_effluent_removal')}: --")
            self._update_cryptosporidium_risk(None)
        except Exception as e:
            self.logger.error(f"重置水厂标签失败: {e}")

    def _update_cryptosporidium_risk(self, gac_turbidity):
        """根据 GAC 出水浊度评估隐孢子虫去除风险等级并更新UI

        Args:
            gac_turbidity: GAC 出水浊度 (NTU)，None 表示无数据

        判据（滤后水浊度）：
            ≤ 0.1 NTU → 优秀 (>4-log 去除) → 绿灯
            ≤ 0.3 NTU → 良好 (≥3-log 去除) → 绿灯
            ≤ 0.5 NTU → 警告 → 红灯（为安全起见严于表述）
            > 0.5 NTU → 警告 (可能<3-log) → 红灯
            > 1.0 NTU → 危险 → 红灯
            None      → 未知 → 两灯均灰
        """
        try:
            if gac_turbidity is None:
                # 无数据
                self.crypto_indicator_canvas.itemconfig(self.crypto_green_light, fill='lightgray')
                self.crypto_indicator_canvas.itemconfig(self.crypto_red_light, fill='lightgray')
                self.crypto_level_label.config(
                    text=self.get_text('crypto_level_unknown'), foreground='gray'
                )
                return
            
            # 按用户要求：GAC ≤ 0.3 → 绿灯；> 0.3 → 红灯
            if gac_turbidity <= 0.1:
                level_text = self.get_text('crypto_level_excellent')
                color = 'green'
                light_on = 'green'
            elif gac_turbidity <= 0.3:
                level_text = self.get_text('crypto_level_good')
                color = 'green'
                light_on = 'green'
            elif gac_turbidity <= 0.5:
                level_text = self.get_text('crypto_level_warning')
                color = 'orange'
                light_on = 'red'
            elif gac_turbidity <= 1.0:
                level_text = self.get_text('crypto_level_warning')
                color = 'red'
                light_on = 'red'
            else:
                level_text = self.get_text('crypto_level_danger')
                color = 'red'
                light_on = 'red'
            
            # 追加实时浊度到等级文字
            level_text_with_value = f"{level_text}  (GAC: {gac_turbidity:.3f} NTU)"
            self.crypto_level_label.config(text=level_text_with_value, foreground=color)
            
            # 更新红绿灯
            if light_on == 'green':
                self.crypto_indicator_canvas.itemconfig(self.crypto_green_light, fill='green')
                self.crypto_indicator_canvas.itemconfig(self.crypto_red_light, fill='lightgray')
            else:
                self.crypto_indicator_canvas.itemconfig(self.crypto_green_light, fill='lightgray')
                self.crypto_indicator_canvas.itemconfig(self.crypto_red_light, fill='red')
        except Exception as e:
            self.logger.error(f"更新隐孢子虫风险评估失败: {e}")

    def update_plots_debounced(self):
        """防抖的图表更新（避免频繁刷新）"""
        self.plot_debouncer.debounce(self.update_plots)()

    # 优化2: 图表更新（使用draw_idle）
    @safe_gui_operation()
    def update_plots(self):
        """更新图表"""
        try:
            # 清理旧图表
            for ax in [self.ax1, self.ax2, self.ax3, self.ax4]:
                # 移除所有Artist对象
                for artist in ax.lines + ax.patches + ax.collections:
                    artist.remove()
                ax.clear()
                ax.set_facecolor(self.plot_bg_color)
            
            df = self.get_data_by_time_range()
            
            if df.empty:
                for ax in [self.ax1, self.ax2, self.ax3, self.ax4]:
                    ax.text(0.5, 0.5, self.get_text('no_data'), 
                        ha='center', va='center', fontsize=14, color=self.plot_fg_color)
                    ax.set_xlabel(self.get_text('time_label'), color=self.plot_fg_color)
                    ax.set_ylabel(self.get_text('value_label'), color=self.plot_fg_color)
                self.canvas.draw()
                return
            
            df_processed = df.copy()
            
            # 处理异常值
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
            except KeyError:
                df_processed['chlorine_demand'] = None
            
            time_range = self.selected_time_range.get()
            
            selected_param_name = self.selected_chart_param.get()
            chart_options = self.get_chart_param_options()
            
            if selected_param_name in chart_options:
                param_tuple = chart_options[selected_param_name]
                param_column, param_unit, param_label = param_tuple
                
                if param_column in df_processed.columns:
                    param_data = df_processed[param_column].dropna()
                    
                    if not param_data.empty:
                        self.ax1.plot(df_processed['timestamp'], df_processed[param_column], 
                                    color='blue', linewidth=1.5, label=param_label)
                        self.ax1.scatter(df_processed[df_processed['is_anomaly'] == True]['timestamp'],
                                    df_processed[df_processed['is_anomaly'] == True][param_column],
                                    color='red', s=50, label=self.get_text('anomaly_replaced'), zorder=5)
                        self.ax1.set_title(f'{param_label} vs {self.get_text("time_label")} ({time_range})',
                                        fontsize=16, fontweight='bold', color=self.plot_fg_color)
                        self.ax1.set_xlabel(self.get_text('time_label'), fontsize=12, color=self.plot_fg_color)
                        self.ax1.set_ylabel(f'{param_label} ({param_unit})', fontsize=12, color=self.plot_fg_color)
                        self.ax1.legend(loc='best')
                        self.ax1.grid(True, alpha=0.3)
                        self.ax1.tick_params(axis='x', rotation=45, colors=self.plot_fg_color)
                        self.ax1.tick_params(axis='y', colors=self.plot_fg_color)
                        
                        self.ax2.hist(param_data, bins=30, color='skyblue', edgecolor='black', alpha=0.7)
                        self.ax2.set_title(f'{param_label} {self.get_text("frequency")}',
                                        fontsize=16, fontweight='bold', color=self.plot_fg_color)
                        self.ax2.set_xlabel(f'{param_label} ({param_unit})', fontsize=12, color=self.plot_fg_color)
                        self.ax2.set_ylabel(self.get_text('frequency'), fontsize=12, color=self.plot_fg_color)
                        self.ax2.grid(True, alpha=0.3, axis='y')
                        self.ax2.tick_params(colors=self.plot_fg_color)
            
            chlorine_data = df_processed['chlorine_demand'].dropna()
            if not chlorine_data.empty:
                self.ax3.plot(df_processed['timestamp'], df_processed['chlorine_demand'],
                            color='green', linewidth=1.5, label=self.get_text('recommended_chlorine'))
                self.ax3.axhline(y=self.current_chlorine_dosage, color='red', linestyle='--',
                            linewidth=1.5, label=self.get_text('actual_chlorine'))
                self.ax3.set_title(f'{self.get_text("chlorine_time")} ({time_range})',
                                fontsize=16, fontweight='bold', color=self.plot_fg_color)
                self.ax3.set_xlabel(self.get_text('time_label'), fontsize=12, color=self.plot_fg_color)
                self.ax3.set_ylabel(self.get_text('chlorine_ylabel'), fontsize=12, color=self.plot_fg_color)
                self.ax3.legend(loc='best')
                self.ax3.grid(True, alpha=0.3)
                self.ax3.tick_params(axis='x', rotation=45, colors=self.plot_fg_color)
                self.ax3.tick_params(axis='y', colors=self.plot_fg_color)
                
                self.ax4.hist(chlorine_data, bins=30, color='lightgreen', edgecolor='black', alpha=0.7)
                self.ax4.set_title(self.get_text('chlorine_dist'),
                                fontsize=16, fontweight='bold', color=self.plot_fg_color)
                self.ax4.set_xlabel(self.get_text('chlorine_ylabel'), fontsize=12, color=self.plot_fg_color)
                self.ax4.set_ylabel(self.get_text('frequency'), fontsize=12, color=self.plot_fg_color)
                self.ax4.grid(True, alpha=0.3, axis='y')
                self.ax4.tick_params(colors=self.plot_fg_color)
            
            for ax in [self.ax1, self.ax2, self.ax3, self.ax4]:
                for spine in ax.spines.values():
                    spine.set_edgecolor(self.plot_fg_color)
            
            self.fig.tight_layout(pad=3.0)
            self.canvas.draw_idle()
            
            # 定期垃圾回收，防止缓存过多卡屏
            if not hasattr(self, '_plot_update_count'):
                self._plot_update_count = 0
                self._last_gc_time = time.time()
            
            self._plot_update_count += 1
            current_time = time.time()
            should_gc = (
                self._plot_update_count % 50 == 0 or 
                (current_time - self._last_gc_time) > 1800
            )
            
            if should_gc:
                import gc
                collected = gc.collect()
                self._last_gc_time = current_time
                self.logger.debug(f"执行GC，回收{collected}个对象")
            
        except Exception as e:
            self.logger.error(f"更新图表失败: {e}")
            # 只记录错误，不重复执行绘图逻辑
    
    def refresh_data(self):
        """刷新数据显示"""
        self.update_data_display()
        self.update_plots()