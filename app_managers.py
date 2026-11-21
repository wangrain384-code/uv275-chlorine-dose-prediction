import os
import sys
import json
import time
import logging
import threading
import subprocess
from datetime import datetime

class PlannedRestartManager:
    """每日重启管理器"""
    
    def __init__(self, 
                 restart_hour=3,
                 restart_minute=7,
                 memory_threshold_mb=800):
        
        # 配置验证，避开采样时刻
        if restart_minute % 5 == 0:
            logger = logging.getLogger(__name__)
            logger.warning("=" * 70)
            logger.warning("注意： 重启时间配置冲突检测")
            logger.warning(f"配置的重启时间: {restart_hour:02d}:{restart_minute:02d}")
            logger.warning("采样时刻: 每5分钟（x:00, x:05, x:10, x:15...）")
            logger.warning("问题: 重启时间与采样时刻重合，将导致重启被永久跳过！")
            
            # 自动调整到非采样时刻
            original_minute = restart_minute
            restart_minute = (restart_minute + 2) % 60
            
            # 处理跨小时情况
            if restart_minute < original_minute:
                restart_hour = (restart_hour + 1) % 24
                logger.warning(f"自动调整: {(restart_hour-1)%24:02d}:{original_minute:02d} → {restart_hour:02d}:{restart_minute:02d}")
            else:
                logger.warning(f"自动调整: {restart_hour:02d}:{original_minute:02d} → {restart_hour:02d}:{restart_minute:02d}")
            
            logger.warning("=" * 70)
        
        self.restart_hour = restart_hour
        self.restart_minute = restart_minute
        self.memory_threshold_mb = memory_threshold_mb
        self.last_restart_date = None
        self.last_check_time = None
        self.logger = logging.getLogger(__name__)
        self.state_file = 'restart_state.json'
    
    def save_monitoring_state(self, is_monitoring, serial_config=None):
        """保存监测状态（原子性写入+格式验证）"""
        try:
            # 验证输入
            if not isinstance(is_monitoring, bool):
                self.logger.error(f"保存失败：is_monitoring类型错误 ({type(is_monitoring)})")
                return
            
            state = {
                'is_monitoring': is_monitoring,
                'save_time': datetime.now().isoformat(),
                'serial_config': serial_config
            }
            
            # 使用临时文件
            temp_file = self.state_file + '.tmp'
            
            try:
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(state, f, ensure_ascii=False, indent=2)
                
                # 验证临时文件
                with open(temp_file, 'r', encoding='utf-8') as f:
                    test_load = json.load(f)
                    if not self._validate_state_format(test_load):
                        raise ValueError("状态文件格式验证失败")
                
                # 原子性替换
                if os.path.exists(self.state_file):
                    os.remove(self.state_file)
                os.rename(temp_file, self.state_file)
                
                self.logger.info(f"保存监测状态: monitoring={is_monitoring}")
                
            except Exception as e:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
                raise
            
        except Exception as e:
            self.logger.error(f"保存状态失败: {e}")
    
    def load_monitoring_state(self):
        """加载监测状态"""
        try:
            if not os.path.exists(self.state_file):
                self.logger.debug("状态文件不存在")
                return None
            
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            # 格式验证
            if not self._validate_state_format(state):
                self.logger.warning("注意：状态文件格式无效，已忽略")
                # 删除损坏的文件
                try:
                    os.remove(self.state_file)
                    self.logger.info("已删除损坏的状态文件")
                except:
                    pass
                return None
            
            self.logger.info(f"加载监测状态: monitoring={state.get('is_monitoring')}")
            return state
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON格式错误: {e}")
            # 删除损坏的文件
            try:
                os.remove(self.state_file)
            except:
                pass
            return None
        except Exception as e:
            self.logger.error(f"加载状态失败: {e}")
            return None
    
    def _validate_state_format(self, state):
        """验证状态文件格式"""
        # 1. 类型检查
        if not isinstance(state, dict):
            self.logger.error("状态不是字典格式")
            return False
        
        # 2. 必需字段检查
        required_fields = {
            'is_monitoring': bool,
            'save_time': str
        }
        
        for field, expected_type in required_fields.items():
            if field not in state:
                self.logger.error(f"缺少必需字段: {field}")
                return False
            
            if not isinstance(state[field], expected_type):
                self.logger.error(
                    f"字段类型错误: {field} "
                    f"(期望: {expected_type.__name__}, "
                    f"实际: {type(state[field]).__name__})"
                )
                return False
        
        # 3. 时间戳格式验证
        try:
            datetime.fromisoformat(state['save_time'])
        except ValueError as e:
            self.logger.error(f"时间戳格式无效: {e}")
            return False
        
        # 4. 可选字段验证
        if 'serial_config' in state and state['serial_config'] is not None:
            if not isinstance(state['serial_config'], dict):
                self.logger.warning("注意：serial_config类型错误，将设为None")
                state['serial_config'] = None
        
        self.logger.debug("状态文件格式验证通过")
        return True
    
    def perform_restart(self, app=None):
        """使用退出码99触发守护进程重启"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("开始执行计划性重启...")
            self.logger.info("=" * 60)
            
            # 保存当前监测状态
            if app:
                with app.monitoring_lock:
                    is_monitoring = app.monitoring
                
                self.save_monitoring_state(
                    is_monitoring=is_monitoring,
                    serial_config=app.serial_config
                )
                
                self.logger.info(f"监测状态已保存: {is_monitoring}")
                
                # 设置重启退出码并退出
                app.exit_code = 99
                app.cleanup_and_exit()
            else:
                # 直接退出（守护进程会重启）
                sys.exit(99)
            
        except Exception as e:
            self.logger.error(f"重启失败: {e}")
            sys.exit(1)

    def check_and_restart(self, process):
        """每日重启检查（避开采样时刻）"""
        try:
            now = datetime.now()
            today = now.date()
            
            # 避开采样时刻（每5分钟的整点）
            if now.minute % 5 == 0:
                self.logger.debug("当前是采样时刻，跳过重启检查")
                return False
            
            # 防止短时间内重复检查
            if self.last_check_time:
                elapsed = (now - self.last_check_time).total_seconds()
                if elapsed < 60:  # 1分钟内不重复检查
                    return False
            
            self.last_check_time = now
            
            # 条件1：每天指定时间重启（避开采样）
            if (now.hour == self.restart_hour and 
                now.minute == self.restart_minute and
                0 <= now.second < 10):  # 10秒的时间窗口

                # 检查今天是否已重启过
                if self.last_restart_date != today:
                    self.logger.warning(
                        f"⏰ 触发每日维护重启 "
                        f"(时间: {now.strftime('%Y-%m-%d %H:%M:%S')})"
                    )
                    self.last_restart_date = today
                    return True
            
            # 条件2：内存超限（紧急重启）
            mem_mb = process.memory_info().rss / 1024 / 1024
            if mem_mb > self.memory_threshold_mb:
                self.logger.warning(
                    f"注意：内存超限触发紧急重启: "
                    f"{mem_mb:.1f}MB > {self.memory_threshold_mb}MB"
                )
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"重启检查失败: {e}")
            return False
        
class WatchdogTimer:
    """看门狗定时器，每隔一段时间检查监控线程是否还正常运行"""
    
    def __init__(self, timeout=600, app=None):
        """
        Args:
            timeout: 超时时间（秒），默认10分钟
            app: 应用实例（用于重启监控）
        """
        self.timeout = timeout
        self.app = app
        self.last_heartbeat = time.time()
        self.is_running = False
        self._stop_event = threading.Event()
        self._watchdog_thread = None
        self.logger = logging.getLogger(__name__)
        self.alarm_triggered = False
    
    def start(self):
        """启动看门狗"""
        if self.is_running:
            return
        
        self.is_running = True
        self._stop_event.clear()
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            daemon=True,
            name="WatchdogTimer"
        )
        self._watchdog_thread.start()
        self.logger.info("看门狗已启动")
    
    def heartbeat(self):
        """更新心跳"""
        self.last_heartbeat = time.time()
        self.alarm_triggered = False  # 重置告警
    
    def _watchdog_loop(self):
        """看门狗主循环，超时后强制退出让守护进程重启"""
        consecutive_timeouts = 0  # 连续超时计数
        max_consecutive_timeouts = 3  # 连续3次超时就强制退出
        
        while not self._stop_event.is_set():
            try:
                elapsed = time.time() - self.last_heartbeat
                
                if elapsed > self.timeout and not self.alarm_triggered:
                    consecutive_timeouts += 1
                    self.logger.critical(
                        f"注意：监控线程可能卡死！已超时 {elapsed:.0f} 秒 "
                        f"(连续超时: {consecutive_timeouts}/{max_consecutive_timeouts})"
                    )
                    self.alarm_triggered = True
                    
                    # 连续超时检测
                    if consecutive_timeouts >= max_consecutive_timeouts:
                        self.logger.critical("=" * 70)
                        self.logger.critical("监控线程连续多次超时，判定为卡死")
                        self.logger.critical("程序将在10秒后强制退出，等待守护进程重启")
                        self.logger.critical("=" * 70)
                        
                        time.sleep(10)  # 给日志系统时间写入
                        os._exit(1)  # 强制退出，让守护进程重启
                    
                    # 尝试自动恢复（如果还有机会）
                    if self.app and hasattr(self.app, 'stop_monitoring'):
                        self.logger.warning("尝试自动重启监控...")
                        try:
                            self.app.stop_monitoring()
                            time.sleep(5)
                            self.app.start_monitoring()
                            self.logger.info("监控已自动重启")
                            consecutive_timeouts = 0  # 重启成功，重置计数
                        except Exception as e:
                            self.logger.error(f"自动重启失败: {e}")
                else:
                    # 如果心跳正常，重置连续超时计数
                    if elapsed <= self.timeout:
                        consecutive_timeouts = 0
                
                self._stop_event.wait(60)  # 每分钟检查一次
                
            except Exception as e:
                self.logger.error(f"看门狗异常: {e}")
                self._stop_event.wait(60)
    
    def stop(self):
        """停止看门狗"""
        self.is_running = False
        self._stop_event.set()
        
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=3.0)


