import os
import time
import logging
import threading
import queue
from datetime import datetime

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

class MemoryManager:
    """内存管理器"""
    
    def __init__(self, check_interval=300):
        self.check_interval = check_interval
        self.logger = logging.getLogger(__name__)
        self._stop_event = threading.Event()
        self._monitor_thread = None
    
    def start(self):
        """启动内存监控"""
        self._monitor_thread = threading.Thread(
            target=self._memory_monitor_loop,
            daemon=True,
            name="MemoryMonitor"
        )
        self._monitor_thread.start()
        self.logger.info("内存监控已启动")
    
    def _memory_monitor_loop(self):
        """内存监控循环"""
        try:
            import psutil
            process = psutil.Process()
        except ImportError:
            self.logger.warning("psutil未安装，内存监控功能不可用")
            return
        except Exception as e:
            self.logger.error(f"初始化psutil失败: {e}")
            return
        
        import gc
        consecutive_errors = 0
        max_errors = 3
        
        while not self._stop_event.is_set():
            try:
                mem_info = process.memory_info()
                mem_mb = mem_info.rss / 1024 / 1024
                
                self.logger.debug(f"内存使用: {mem_mb:.2f} MB")
                
                # 内存超过500MB时触发垃圾回收
                if mem_mb > 500:
                    self.logger.warning(f"内存使用过高: {mem_mb:.2f} MB，触发GC")
                    gc.collect()
                    
                    # 再次检查
                    mem_info = process.memory_info()
                    mem_mb_after = mem_info.rss / 1024 / 1024
                    self.logger.info(f"GC后内存: {mem_mb_after:.2f} MB (释放: {mem_mb - mem_mb_after:.2f} MB)")
                
                consecutive_errors = 0  # 重置错误计数
                self._stop_event.wait(self.check_interval)
                
            except Exception as e:
                consecutive_errors += 1
                self.logger.error(f"内存监控错误 ({consecutive_errors}/{max_errors}): {e}")
                
                if consecutive_errors >= max_errors:
                    self.logger.error("内存监控连续出错，停止监控")
                    break
                
                self._stop_event.wait(60)
        
        self.logger.info("内存监控线程退出")

    def stop(self):
        """停止内存监控"""
        if self._stop_event.is_set():
            self.logger.debug("内存监控已经停止")
            return
        
        self.logger.info("正在停止内存监控...")
        self._stop_event.set()
        
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=10)
            if self._monitor_thread.is_alive():
                self.logger.warning("内存监控线程未能在10秒内退出")
            else:
                self.logger.info("内存监控已成功停止")

class HealthMonitor:
    """系统健康监控器（精简版 - 针对5分钟采样）"""
    
    def __init__(self, app, check_interval=300):  # 改为5分钟检查一次
        """
        Args:
            app: 应用实例
            check_interval: 检查间隔（秒），默认300秒=5分钟
        """
        self.app = app
        self.check_interval = check_interval
        self.logger = logging.getLogger(__name__)
        self._stop_event = threading.Event()
        self._monitor_thread = None
        
        # 简化的阈值（针对低频采样）
        self.thresholds = {
            'memory_mb': 500,           # 内存阈值500MB（降低）
            'db_connections': 8,        # 连接池阈值8个（降低）
            'gui_queue_size': 30,       # GUI队列30个（降低）
            'sensor_failures': 3        # 传感器失败3次
        }
        
        # 健康历史（最近20次检查）
        self.health_history = []
        self.max_history = 20
    
    def start(self):
        """启动健康监控"""
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="HealthMonitor"
        )
        self._monitor_thread.start()
        self.logger.info(f"健康监控已启动（每{self.check_interval}秒检查）")
    
    def _monitor_loop(self):
        """健康监控循环（简化版）"""
        try:
            import psutil
            process = psutil.Process()
        except ImportError:
            self.logger.warning("psutil未安装，健康监控功能受限")
            self._stop_event.wait()
            return
        
        while not self._stop_event.is_set():
            try:
                health = self._check_health(process)
                
                # 记录健康历史
                self.health_history.append(health)
                if len(self.health_history) > self.max_history:
                    self.health_history.pop(0)
                
                # 仅在有问题时记录警告
                if health['status'] != 'healthy':
                    self.logger.warning(
                        f"健康检查: {health['status']} - "
                        f"{', '.join(health['issues'])}"
                    )
                
                # 自动恢复（仅在critical时）
                if health['status'] == 'critical':
                    self._auto_recover(health)
                
                self._stop_event.wait(self.check_interval)
                
            except Exception as e:
                self.logger.error(f"健康检查失败: {e}")
                self._stop_event.wait(self.check_interval)
    
    def _check_health(self, process):
        """检查系统健康状态（简化版）"""
        health = {
            'status': 'healthy',
            'issues': [],
            'timestamp': datetime.now()
        }
        
        try:
            # 1. 检查内存
            mem_mb = process.memory_info().rss / 1024 / 1024
            if mem_mb > self.thresholds['memory_mb']:
                health['status'] = 'warning'
                health['issues'].append(f'内存: {mem_mb:.0f}MB')
            
            # 2. 检查数据库连接
            if hasattr(self.app, 'db_manager'):
                stats = self.app.db_manager.get_connection_stats()
                if stats['total_connections'] > self.thresholds['db_connections']:
                    health['status'] = 'critical'
                    health['issues'].append(f'连接: {stats["total_connections"]}')
            
            # 3. 检查GUI队列
            queue_size = self.app.gui_update_queue.qsize()
            if queue_size > self.thresholds['gui_queue_size']:
                health['status'] = 'warning'
                health['issues'].append(f'队列: {queue_size}')
            
            # 4. 检查传感器状态
            if hasattr(self.app, 'sensor_recovery'):
                failures = self.app.sensor_recovery.consecutive_failures
                if failures >= self.thresholds['sensor_failures']:
                    health['status'] = 'critical'
                    health['issues'].append(f'传感器: {failures}次失败')
        
        except Exception as e:
            self.logger.error(f"健康检查执行失败: {e}")
            health['status'] = 'error'
        
        return health
    
    def _auto_recover(self, health_status):
        """自动恢复措施（简化版）"""
        self.logger.warning(f"触发自动恢复: {health_status['issues']}")
        
        # 清理缓存
        if '内存' in str(health_status['issues']):
            try:
                self.app.data_cache.clear()
                import gc
                gc.collect()
                self.logger.info("已清理缓存和执行GC")
            except:
                pass
        
        # 清空GUI队列
        if '队列' in str(health_status['issues']):
            try:
                cleared = 0
                while not self.app.gui_update_queue.empty():
                    try:
                        self.app.gui_update_queue.get_nowait()
                        cleared += 1
                    except queue.Empty:
                        break
                self.logger.info(f"清空GUI队列，清除{cleared}个任务")
            except:
                pass

    def get_health_summary(self):
        """获取健康摘要（供UI显示）"""
        if not self.health_history:
            return "暂无健康数据"
        
        recent = self.health_history[-5:]  # 最近5次
        status_counts = {}
        
        for h in recent:
            status = h['status']
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # 生成简单摘要
        if 'critical' in status_counts:
            return f"注意：严重问题 ({status_counts['critical']}次)"
        elif 'warning' in status_counts:
            return f"注意：警告 ({status_counts['warning']}次)"
        else:
            return "健康"
    
    def stop(self):
        """停止健康监控"""
        self.logger.info("正在停止健康监控...")
        self._stop_event.set()
        
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5)

class SimpleStructuredLogger:
    """精简的结构化日志记录器（针对5分钟采样）"""
    
    def __init__(self, logger_name):
        self.logger = logging.getLogger(logger_name)
    
    def log_sampling(self, uv275, temp, status='success'):
        """记录采样事件（专用方法）"""
        try:
            msg = (
                f"采样 | UV275:{uv275:.3f} | "
                f"温度:{temp:.1f}℃ | {status}"
            )
            if status == 'success':
                self.logger.info(msg)
            else:
                self.logger.warning(msg)
        except:
            pass
    
    def log_alarm(self, alarm_type, value, threshold):
        """记录报警事件"""
        try:
            msg = (
                f"报警 | 类型:{alarm_type} | "
                f"值:{value:.3f} | 阈值:{threshold:.3f}"
            )
            self.logger.warning(msg)
        except:
            pass
    
    def log_recovery(self, component, success=True):
        """记录恢复事件"""
        try:
            status = "成功" if success else "失败"
            msg = f"恢复 | 组件:{component} | {status}"
            self.logger.info(msg)
        except:
            pass


