# 本文件为 UV275MonitorGUI 的 Mixin，通过多继承组合到主类中

import os
import sys
import time
import json
import shutil
import logging
import calendar
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from tkcalendar import DateEntry
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from datetime import datetime, timedelta
from sensor import UV275SensorModbus

class MonitoringMixin:
    """监控主循环、启动/停止监控及故障处理相关方法"""

    def monitoring_loop(self):
        """监控循环（带自动恢复和看门狗+数据库失败检测）"""
        measurement_interval = self.config_manager.getint('Sensor', 'measurement_interval', 300)
        
        self.logger.info(f"监控线程启动 (线程ID: {threading.get_ident()})")
        
        pending_gui_updates = 0
        max_pending_updates = 10

        # 数据库失败计数器
        db_failure_count = 0  # 数据库连续失败次数，超过上限就退出让守护进程重启
        max_db_failures = 10

        # 归档检查时间戳
        last_archive_check = time.time()

        # 连续严重错误计数器（用于极端异常情况）
        consecutive_critical_errors = 0
        max_critical_errors = 10
        
        while not self.stop_event.is_set():
            try:
                # 更新看门狗心跳
                if hasattr(self, 'watchdog'):
                    self.watchdog.heartbeat()
                
                # 检查是否需要恢复传感器
                with self.sensor_lock:
                    if not self.sensor:
                        self.logger.warning("传感器对象不存在，退出监控")
                        break
                    
                    # 如果在恢复模式，尝试恢复
                    if self.sensor_recovery.recovery_mode:
                        if self.sensor_recovery.attempt_recovery(self.sensor):
                            self.sensor_recovery.record_success()
                            consecutive_critical_errors = 0  # 重置计数
                        else:
                            self.logger.info("恢复失败，等待后重试...")
                            for _ in range(6):
                                if self.stop_event.wait(10):
                                    self.logger.info("收到停止信号，退出恢复等待")
                                    break
                            continue
                    
                    # 读取数据
                    all_data = self.sensor.read_all_data_with_retry(max_retries=3)
                
                if all_data:
                    # 记录成功
                    self.sensor_recovery.record_success()
                    consecutive_critical_errors = 0  # 重置计数
                    
                    # 修改：分离数据库保存逻辑，单独处理异常
                    try:
                        self.save_to_db(all_data)
                        db_failure_count = 0  # 数据库连续失败次数，超过上限就退出让守护进程重启  # 保存成功，重置计数
                        
                    except Exception as db_error:
                        db_failure_count += 1
                        self.logger.error(
                            f"数据库保存失败 ({db_failure_count}/{max_db_failures}): {db_error}",
                            exc_info=True
                        )
                        
                        # 数据库持续失败检测
                        if db_failure_count >= max_db_failures:
                            self.logger.critical(
                                f"数据库连续失败{max_db_failures}次，程序退出等待守护进程重启"
                            )
                            self.logger.critical("建议检查：")
                            self.logger.critical("  1. 数据库文件是否损坏")
                            self.logger.critical("  2. 磁盘空间是否充足")
                            self.logger.critical("  3. 文件权限是否正确")
                            
                            # 退出程序，让守护进程重启
                            self.exit_code = 1
                            self._cleanup_monitoring_resources()
                            os._exit(1)  # 强制退出
                    
                    # GUI更新
                    if pending_gui_updates < max_pending_updates:
                        def safe_gui_update():
                            nonlocal pending_gui_updates
                            try:
                                self.update_data_display()
                                self.update_plots_debounced()
                                self.status_label.config(
                                    text=self.get_text('status_monitoring'), 
                                    foreground='green'
                                )
                            except Exception as e:
                                self.logger.error(f"GUI更新失败: {e}", exc_info=True)
                            finally:
                                pending_gui_updates -= 1
                        
                        try:
                            self.gui_update_queue.put_nowait(safe_gui_update)
                            pending_gui_updates += 1
                        except queue.Full:
                            self.logger.warning("GUI更新队列已满，跳过本次更新")
                    else:
                        self.logger.debug(f"待处理GUI更新过多({pending_gui_updates})，跳过")
                else:
                    # 记录失败
                    self.sensor_recovery.record_failure()
                    
                    # 记录严重错误
                    if self.sensor_recovery.recovery_mode:
                        consecutive_critical_errors += 1
                        self.logger.error(
                            f"连续严重错误: {consecutive_critical_errors}/{max_critical_errors}"
                        )
                        
                        # 极端情况处理 - 传感器长期离线
                        if consecutive_critical_errors >= max_critical_errors:
                            self.logger.critical("注意：连续严重错误次数过多，尝试自动扫描传感器")
                            
                            # 尝试自动扫描并切换端口
                            new_port = self.auto_scan_sensor_port()
                            
                            if new_port:
                                with self.sensor_lock:
                                    try:
                                        # 断开旧连接
                                        if self.sensor:
                                            self.sensor.disconnect()
                                        time.sleep(2)
                                        
                                        # 更新配置
                                        self.serial_config['port'] = new_port
                                        self.save_serial_config()
                                        
                                        self.logger.info(f"已更新串口配置: {new_port}")
                                        
                                        # 创建新传感器对象（使用新端口）
                                        self.sensor = UV275SensorModbus(
                                            port=new_port,
                                            baudrate=self.serial_config['baudrate'],
                                            slave_address=self.serial_config['slave_address']
                                        )
                                        
                                        # 尝试连接
                                        if self.sensor.connect():
                                            self.logger.info(f"传感器已切换到端口 {new_port}")
                                            self.sensor_recovery.record_success()
                                            consecutive_critical_errors = 0
                                        else:
                                            self.logger.error(f"端口 {new_port} 连接失败")
                                            
                                    except Exception as e:
                                        self.logger.error(f"重新初始化异常: {e}")
                            else:
                                # 找不到传感器时的退出机制
                                self.logger.error("未找到有效传感器，等待5分钟后退出程序")
                                self.logger.error("建议检查：")
                                self.logger.error("  1. 传感器是否通电")
                                self.logger.error("  2. USB/串口线是否连接")
                                self.logger.error("  3. DTU模块是否工作")
                                self.logger.error("  4. 串口驱动是否正常")
                                
                                # 等待5分钟让用户有时间介入
                                for i in range(30):  # 5分钟 = 30 * 10秒
                                    if self.stop_event.wait(10):
                                        self.logger.info("收到停止信号，取消退出")
                                        break
                                    if i % 6 == 0:  # 每分钟提示一次
                                        self.logger.warning(f"等待中... ({(i//6)+1}/5 分钟)")
                                
                                # 如果不是用户主动停止
                                if not self.stop_event.is_set():
                                    self.logger.critical("传感器长期离线，程序退出等待守护进程重启")
                                    self.exit_code = 1  # 异常退出
                                    self._cleanup_monitoring_resources()
                                    os._exit(1)  # 强制退出
                    
                    # 如果刚进入恢复模式，提示用户
                    if self.sensor_recovery.recovery_mode:
                        def notify_recovery():
                            try:
                                self.status_label.config(
                                    text="注意：传感器故障，正在尝试恢复...", 
                                    foreground='orange'
                                )
                            except:
                                pass
                        
                        try:
                            self.gui_update_queue.put_nowait(notify_recovery)
                        except queue.Full:
                            pass

                # 每小时检查一次归档
                if time.time() - last_archive_check > 3600:
                    self.data_archiver.check_and_auto_archive()
                    last_archive_check = time.time()                
                
                # 可中断等待（分段检查）
                for _ in range(measurement_interval // 10):
                    if self.stop_event.wait(10):
                        self.logger.info("收到停止信号，退出监控循环")
                        break
                    
            except Exception as e:
                self.logger.error(f"监控循环异常: {e}", exc_info=True)
                self.sensor_recovery.record_failure()
                consecutive_critical_errors += 1
                
                # 异常后也使用分段等待
                for _ in range(3):
                    if self.stop_event.wait(10):
                        break
        
        # 清理资源
        self._cleanup_monitoring_resources()
        self.logger.info("监控线程退出")

    def _handle_monitoring_failure(self):
        """处理监控失败"""
        self.logger.error("连续读取失败次数过多，停止监控")
        
        def stop_with_error():
            try:
                with self.monitoring_lock:
                    self.monitoring = False
                
                self.stop_event.set()
                
                with self.sensor_lock:
                    if self.sensor:
                        try:
                            self.sensor.disconnect()
                        except Exception as e:
                            self.logger.error(f"断开传感器失败: {e}")
                        finally:
                            self.sensor = None
                
                self.start_button.config(state=tk.NORMAL)
                self.stop_button.config(state=tk.DISABLED)
                self.status_label.config(text=self.get_text('status_ready'), foreground='red')
                
                messagebox.showerror(
                    "连接错误 / Connection Error",
                    "连续读取失败！监控已自动停止。"
                )
            except Exception as e:
                self.logger.error(f"处理监控失败时出错: {e}", exc_info=True)
        
        try:
            self.gui_update_queue.put_nowait(stop_with_error)
        except queue.Full:
            self.logger.error("GUI更新队列已满，无法发送停止通知")

    def _cleanup_monitoring_resources(self):
        """清理监控资源"""
        self.logger.info("清理监控资源...")
        
        with self.sensor_lock:
            if self.sensor:
                try:
                    self.sensor.disconnect()
                except Exception as e:
                    self.logger.error(f"清理传感器连接失败: {e}")
                finally:
                    self.sensor = None
    
    def start_monitoring(self, silent=False):
        """启动监控
        
        Args:
            silent: 是否静默模式（自动恢复时使用，不显示弹窗）
        """
        # 检查监控状态
        with self.monitoring_lock:
            if self.monitoring:
                if not silent:  # 只有非静默模式才显示警告
                    messagebox.showwarning("警告", "监控已在运行中！")
                return
        
        try:
            self.status_label.config(text=self.get_text('status_starting'), foreground='orange')
            self.root.update()
            
            # 重置停止事件
            self.stop_event.clear()
            
            # 创建传感器对象
            with self.sensor_lock:
                self.sensor = UV275SensorModbus(
                    port=self.serial_config['port'],
                    baudrate=self.serial_config['baudrate'],
                    slave_address=self.serial_config['slave_address']
                )
                
                if not self.sensor.connect():
                    # 连接失败时总是显示错误（即使静默模式）
                    messagebox.showerror("连接错误",
                        "无法连接到传感器！\n\n请检查：\n1. 串口设置\n2. 传感器连接\n3. DTU模块状态")
                    self.sensor = None
                    self.status_label.config(text=self.get_text('status_ready'), foreground='red')
                    return
            
            # 设置监控标志
            with self.monitoring_lock:
                self.monitoring = True

                # 保存状态为“正在监控”
                self.restart_manager.save_monitoring_state(True, self.serial_config)
                self.logger.info("监控已启动并记录状态")

            self.monitor_thread = threading.Thread(target=self.monitoring_loop, daemon=True, name="MonitoringThread")
            self.monitor_thread.start()

            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            
            self.status_label.config(text=self.get_text('status_monitoring'), foreground='green')
            
            # 根据模式决定是否显示消息
            if not silent:
                messagebox.showinfo("成功", "监控已启动！")
                self.logger.info("监控已启动")
            else:
                self.logger.info("监控已自动恢复（静默模式）")
            
        except Exception as e:
            self.logger.error(f"启动监控失败: {e}", exc_info=True)
            
            # 清理状态
            with self.monitoring_lock:
                self.monitoring = False
            self.stop_event.set()
            
            with self.sensor_lock:
                if self.sensor:
                    self.sensor.disconnect()
                    self.sensor = None
            
            # 错误时总是显示消息
            messagebox.showerror("错误", f"启动监控失败: {e}")
            self.status_label.config(text=self.get_text('status_ready'), foreground='red')
    
    # 修复5: 改进 stop_monitoring 方法
    def stop_monitoring(self):
        """停止监控"""
        # 检查监控状态
        with self.monitoring_lock:
            if not self.monitoring:
                messagebox.showwarning("警告", "监控未在运行中！")
                return
        
        try:
            self.status_label.config(text=self.get_text('status_stopping'), foreground='orange')
            self.root.update()
            
            # 设置停止标志
            with self.monitoring_lock:
                self.monitoring = False
            self.stop_event.set()
            
            # 立即清除监控状态
            self.restart_manager.save_monitoring_state(False, self.serial_config)
            self.logger.info("监控已停止并更新状态")

            # 等待线程退出
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.logger.info("等待监控线程退出...")
                self.monitor_thread.join(timeout=5.0)
                
                if self.monitor_thread.is_alive():
                    self.logger.warning("监控线程未能在5秒内退出")
                    messagebox.showwarning(
                        "警告 / Warning",
                        "注意：监控线程可能未完全停止\n\n"
                        "建议重启程序以确保系统状态正常。\n\n"
                        "Monitoring thread may not have stopped completely.\n"
                        "Recommend restarting the program."
                    )
                else:
                    self.logger.info("监控线程已成功退出")
            
            # 断开传感器
            with self.sensor_lock:
                if self.sensor:
                    try:
                        self.sensor.disconnect()
                    except Exception as e:
                        self.logger.error(f"断开传感器连接失败: {e}")
                    finally:
                        self.sensor = None
                        # 等待串口驱动层完全释放资源
                        # 解决manual_zero_calibration时串口占用问题
                        time.sleep(1.5)
                        self.logger.info("串口已释放，等待1.5秒缓冲完成")
            
            self.root.after(100, self.reset_buttons_after_stop)
            
            messagebox.showinfo("成功", "监控已停止！")
            self.logger.info("监控已停止")
            
        except Exception as e:
            self.logger.error(f"停止监控失败: {e}", exc_info=True)
            messagebox.showerror("错误", f"停止监控失败: {e}")
            self.status_label.config(text=self.get_text('status_ready'), foreground='green')
    
    def reset_buttons_after_stop(self):
        """重置按钮状态"""
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.status_label.config(text=self.get_text('status_ready'), foreground='green')
    

