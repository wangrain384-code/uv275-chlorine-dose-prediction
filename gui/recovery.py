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
from sensor import UV275SensorModbus

class RecoveryMixin:
    """监控状态恢复与自动重启相关方法"""

    def auto_restore_monitoring(self):
        """检查上次状态：如果上次在监控，重启后自动开始；如果是第一次运行（之前没运行记录），则什么都不做，等待用户点击开始监控"""
        try:
            state = self.restart_manager.load_monitoring_state()
            # 只有当记录显示上次是在监控中时，才自动触发
            if state and state.get('is_monitoring') is True:
                self.logger.info("检测到非正常关闭或重启，正在自动恢复监控状态...")
                if not self.monitoring:
                    self.toggle_monitoring()
            else:
                self.logger.info("上次为停止状态或首次运行，不自动开启。")
        except Exception as e:
            self.logger.error(f"恢复监控状态失败: {e}")

    def auto_start_monitoring(self):
            """自动启动监控逻辑"""
            if not self.monitoring:
                self.logger.info("检测到自动启动请求，正在开启监控...")
                self.toggle_monitoring()

    def auto_scan_sensor_port(self):
            """自动扫描并找到传感器端口"""
            self.logger.info("开始自动扫描传感器...")
            
            try:
                available_ports = [p.device for p in serial.tools.list_ports.comports()]
                
                if not available_ports:
                    self.logger.error("未发现任何串口设备")
                    return None
                
                self.logger.info(f"发现可用端口: {', '.join(available_ports)}")
                
                for port in available_ports:
                    try:
                        self.logger.info(f"正在测试端口: {port}")
                        
                        # 创建临时传感器对象
                        temp_sensor = UV275SensorModbus(
                            port=port,
                            baudrate=self.serial_config['baudrate'],
                            slave_address=self.serial_config['slave_address'],
                            timeout=2  # 短超时
                        )
                        
                        if temp_sensor.connect():
                            # 尝试读取数据验证
                            data = temp_sensor.read_all_data()
                            temp_sensor.disconnect()
                            
                            if data and 'uv275_absorbance' in data:
                                uv275 = data.get('uv275_absorbance', 0)
                                self.logger.info(
                                    f"在端口 {port} 找到传感器！"
                                    f"(UV275: {uv275:.3f})"
                                )
                                return port
                            else:
                                self.logger.debug(f"端口 {port}: 数据无效")
                        else:
                            self.logger.debug(f"端口 {port}: 无法连接")
                            
                    except Exception as e:
                        self.logger.debug(f"端口 {port} 测试失败: {e}")
                        continue
                
                self.logger.error("所有端口测试完毕，未找到有效传感器")
                return None
                
            except Exception as e:
                self.logger.error(f"扫描过程失败: {e}", exc_info=True)
                return None

    def start_restart_check_thread(self):
        """启动重启检查线程"""
        def restart_check_loop():
            import psutil
            process = psutil.Process()
            
            while not self.stop_event.is_set():
                try:
                    if self.restart_manager.check_and_restart(process):
                        # 停止监控
                        with self.monitoring_lock:
                            if self.monitoring:
                                self.stop_event.set()
                        
                        # 等待线程退出
                        time.sleep(5)
                        
                        # 传递app参数
                        self.restart_manager.perform_restart(app=self)  # 这里修改
                    
                    time.sleep(3600)
                    
                except Exception as e:
                    self.logger.error(f"重启检查失败: {e}")
                    time.sleep(3600)
        
        restart_thread = threading.Thread(
            target=restart_check_loop, 
            daemon=True,
            name="RestartCheckThread"
        )
        restart_thread.start()
        self.logger.info("重启检查线程已启动")

    def restore_monitoring_state(self):
        """移除时间限制，增强鲁棒性"""
        try:
            state = self.restart_manager.load_monitoring_state()
            
            if not state:
                self.logger.info("无保存状态，正常启动")
                return
            
            was_monitoring = state.get('is_monitoring', False)
            
            if was_monitoring:
                save_time_str = state.get('save_time', '')
                self.logger.info(
                    f"检测到上次处于监控状态 (保存时间: {save_time_str})"
                )
                self.logger.info("准备自动恢复监控...")
                
                # 创建恢复记录
                recovery_log = {
                    'time': datetime.now().isoformat(),
                    'previous_state': was_monitoring,
                    'recovery_successful': None,  # 稍后更新
                    'error': None
                }
                
                # 在GUI上显示恢复信息
                def show_recovery_info():
                    self.status_label.config(
                        text="检测到计划重启，正在准备恢复监控...", 
                        foreground='orange'
                    )
                
                self.root.after(100, show_recovery_info)
                
                # 定义恢复函数
                def auto_resume():
                    try:
                        self.status_label.config(
                            text="正在连接传感器并恢复监控...", 
                            foreground='orange'
                        )
                        self.root.update()
                        
                        time.sleep(1)
                        
                        self.logger.info("开始恢复监控...")
                        self.start_monitoring(silent=True)
                        
                        self.logger.info("监控已成功恢复")
                        
                        # 更新恢复记录为成功
                        recovery_log['recovery_successful'] = True
                        self._save_recovery_log(recovery_log)
                        
                        # 显示恢复成功提示
                        self.status_label.config(
                            text="监控已自动恢复 | " + self.get_text('status_monitoring'), 
                            foreground='green'
                        )
                        
                        def reset_status():
                            if self.monitoring:
                                self.status_label.config(
                                    text=self.get_text('status_monitoring'), 
                                    foreground='green'
                                )
                        
                        self.root.after(5000, reset_status)
                        
                    except Exception as e:
                        self.logger.error(f"自动恢复失败: {e}", exc_info=True)
                        
                        # 更新恢复记录为失败
                        recovery_log['recovery_successful'] = False
                        recovery_log['error'] = str(e)
                        self._save_recovery_log(recovery_log)
                        
                        # 显示错误提示
                        def show_error():
                            messagebox.showerror(
                                "恢复失败 / Recovery Failed",
                                f"无法自动恢复监控\n\n"
                                f"错误信息: {str(e)}\n\n"
                                f"请检查：\n"
                                f"• 串口连接是否正常\n"
                                f"• 传感器是否通电\n"
                                f"• DTU模块是否工作\n\n"
                                f"然后手动点击'开始监控'"
                            )
                        
                        self.root.after(100, show_error)
                        
                        self.status_label.config(
                            text=self.get_text('status_ready'), 
                            foreground='red'
                        )
                
                self.root.after(3000, auto_resume)
                
            else:
                self.logger.info("上次已正常停止，无需恢复")
                # 清除状态文件
                try:
                    if os.path.exists(self.restart_manager.state_file):
                        os.remove(self.restart_manager.state_file)
                except:
                    pass
                
        except Exception as e:
            self.logger.error(f"状态恢复过程失败: {e}", exc_info=True)

    def restore_monitoring_state(self):
        """移除时间限制，增强鲁棒性"""
        try:
            state = self.restart_manager.load_monitoring_state()
            
            if not state:
                self.logger.info("无保存状态，正常启动")
                return
            
            was_monitoring = state.get('is_monitoring', False)
            
            if was_monitoring:
                save_time_str = state.get('save_time', '')
                self.logger.info(
                    f"检测到上次处于监控状态 (保存时间: {save_time_str})"
                )
                self.logger.info("准备自动恢复监控...")
                
                # 创建恢复记录
                recovery_log = {
                    'time': datetime.now().isoformat(),
                    'previous_state': was_monitoring,
                    'recovery_successful': None,
                    'error': None
                }
                
                # 在GUI上显示恢复信息
                def show_recovery_info():
                    self.status_label.config(
                        text="检测到计划重启，正在准备恢复监控...", 
                        foreground='orange'
                    )
                
                self.root.after(100, show_recovery_info)
                
                # 定义恢复函数
                def auto_resume():
                    try:
                        self.status_label.config(
                            text="正在连接传感器并恢复监控...", 
                            foreground='orange'
                        )
                        self.root.update()
                        
                        time.sleep(1)
                        
                        self.logger.info("开始恢复监控...")
                        self.start_monitoring(silent=True)
                        
                        self.logger.info("监控已成功恢复")
                        
                        # 更新恢复记录为成功
                        recovery_log['recovery_successful'] = True
                        self._save_recovery_log(recovery_log)
                        
                        # 显示恢复成功提示
                        self.status_label.config(
                            text="监控已自动恢复 | " + self.get_text('status_monitoring'), 
                            foreground='green'
                        )
                        
                        def reset_status():
                            if self.monitoring:
                                self.status_label.config(
                                    text=self.get_text('status_monitoring'), 
                                    foreground='green'
                                )
                        
                        self.root.after(5000, reset_status)
                        
                    except Exception as e:
                        self.logger.error(f"自动恢复失败: {e}", exc_info=True)
                        
                        # 更新恢复记录为失败
                        recovery_log['recovery_successful'] = False
                        recovery_log['error'] = str(e)
                        self._save_recovery_log(recovery_log)
                        
                        # 显示错误提示
                        def show_error():
                            messagebox.showerror(
                                "恢复失败 / Recovery Failed",
                                f"无法自动恢复监控\n\n"
                                f"错误信息: {str(e)}\n\n"
                                f"请检查：\n"
                                f"• 串口连接是否正常\n"
                                f"• 传感器是否通电\n"
                                f"• DTU模块是否工作\n\n"
                                f"然后手动点击'开始监控'"
                            )
                        
                        self.root.after(100, show_error)
                        
                        self.status_label.config(
                            text=self.get_text('status_ready'), 
                            foreground='red'
                        )
                
                self.root.after(3000, auto_resume)
                
            else:
                self.logger.info("上次已正常停止，无需恢复")
                # 清除状态文件
                try:
                    if os.path.exists(self.restart_manager.state_file):
                        os.remove(self.restart_manager.state_file)
                except:
                    pass
                
        except Exception as e:
            self.logger.error(f"状态恢复过程失败: {e}", exc_info=True)
    
    
    
    def _save_recovery_log(self, log_entry):
        """保存恢复历史记录
        
        Args:
            log_entry: 恢复记录字典，包含time, previous_state, recovery_successful等
        """
        try:
            log_file = 'recovery_history.json'
            history = []
            
            # 读取现有历史
            if os.path.exists(log_file):
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        history = json.load(f)
                except json.JSONDecodeError:
                    self.logger.warning("历史记录文件损坏，创建新文件")
                    history = []
            
            # 添加新记录
            history.append(log_entry)
            
            # 只保留最近30次记录
            history = history[-30:]
            
            # 保存
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
            
            self.logger.debug(f"恢复历史已保存 (总计{len(history)}条)")
                
        except Exception as e:
            self.logger.error(f"保存恢复历史失败: {e}")
    
    def get_recovery_history(self):
        """获取恢复历史记录
        
        Returns:
            list: 恢复历史记录列表
        """
        try:
            log_file = 'recovery_history.json'
            
            if not os.path.exists(log_file):
                return []
            
            with open(log_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            
            return history
            
        except Exception as e:
            self.logger.error(f"读取恢复历史失败: {e}")
            return []
    
    def show_recovery_history(self):
        """显示恢复历史记录"""
        history = self.get_recovery_history()
        
        if not history:
            messagebox.showinfo("恢复历史", "暂无恢复历史记录")
            return
        
        # 创建历史窗口
        history_window = tk.Toplevel(self.root)
        history_window.title("恢复历史 / Recovery History")
        history_window.geometry("800x600")
        
        # 创建文本框
        text_widget = tk.Text(history_window, wrap=tk.WORD, font=('Consolas', 10))
        scrollbar = ttk.Scrollbar(history_window, command=text_widget.yview)
        text_widget.config(yscrollcommand=scrollbar.set)
        
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=10)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=10)
        
        # 格式化显示历史
        content = "═══════════════════════════════════════════════════════\n"
        content += "           重启恢复历史记录\n"
        content += "           Restart Recovery History\n"
        content += "═══════════════════════════════════════════════════════\n\n"
        
        for i, record in enumerate(reversed(history), 1):
            time_str = record.get('time', 'Unknown')
            success = record.get('recovery_successful')
            previous = record.get('previous_state', False)
            error = record.get('error', '')
            
            status_icon = "" if success else ""
            status_text = "成功" if success else "失败"
            
            content += f"【记录 #{len(history) - i + 1}】\n"
            content += f"  时间: {time_str}\n"
            content += f"  之前状态: {'监控中' if previous else '已停止'}\n"
            content += f"  恢复结果: {status_icon} {status_text}\n"
            
            if error:
                content += f"  错误信息: {error}\n"
            
            content += "\n" + "─" * 55 + "\n\n"
        
        content += f"\n总计: {len(history)} 条记录\n"
        
        text_widget.insert('1.0', content)
        text_widget.config(state=tk.DISABLED)
        
        # 关闭按钮
        close_btn = ttk.Button(history_window, text="关闭", command=history_window.destroy)
        close_btn.pack(pady=5)


