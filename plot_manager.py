import time
import logging
import threading
import hashlib
import numpy as np
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt

class PlotManager:
    """图表管理器（局部更新，不用每次重绘整个图表）"""
    
    def __init__(self, axes, canvas, plot_bg_color, plot_fg_color):
        self.axes = axes  # [ax1, ax2, ax3, ax4]
        self.canvas = canvas
        self.plot_bg_color = plot_bg_color
        self.plot_fg_color = plot_fg_color
        
        # 保存绘图对象引用用于局部更新
        self._plot_objects = {
            'ax1': {'lines': [], 'scatter': None},
            'ax2': {'patches': []},
            'ax3': {'lines': [], 'hline': None},
            'ax4': {'patches': []}
        }
        
        self._last_data_hash = None
        self.logger = logging.getLogger(__name__)
    
    def should_update(self, df):
        """检查是否需要更新"""
        if df.empty:
            return True
        
        # 使用数据哈希判断是否变化
        data_hash = hashlib.md5(
            pd.util.hash_pandas_object(df, index=True).values
        ).hexdigest()
        
        if data_hash == self._last_data_hash:
            return False
        
        self._last_data_hash = data_hash
        return True
    
    def update_plot_data_only(self, ax_name, x_data, y_data):
        """仅更新数据，不重绘整个图表"""
        ax_idx = int(ax_name[-1]) - 1
        ax = self.axes[ax_idx]
        plot_objs = self._plot_objects[ax_name]
        
        try:
            if plot_objs['lines']:
                # 更新现有线条数据
                line = plot_objs['lines'][0]
                line.set_data(x_data, y_data)
                
                # 更新坐标轴范围
                ax.relim()
                ax.autoscale_view()
            else:
                # 首次绘制
                line, = ax.plot(x_data, y_data, color='blue', linewidth=1.5)
                plot_objs['lines'].append(line)
            
            # 仅重绘该子图
            ax.figure.canvas.draw_idle()
            
        except Exception as e:
            self.logger.error(f"更新图表{ax_name}失败: {e}")

    def update_plots_optimized(self):
        """优化的图表更新"""
        try:
            df = self.get_data_by_time_range()
            
            # 检查是否需要更新
            if not hasattr(self, 'plot_manager'):
                self.plot_manager = PlotManager(
                    [self.ax1, self.ax2, self.ax3, self.ax4],
                    self.canvas,
                    self.plot_bg_color,
                    self.plot_fg_color
                )
            
            if not self.plot_manager.should_update(df):
                self.logger.debug("数据未变化，跳过图表更新")
                return
            
            # 仅更新变化的图表
            if not df.empty:
                # 更新时间序列图（仅更新数据）
                self.plot_manager.update_plot_data_only(
                    'ax1',
                    df['timestamp'],
                    df['uv275_absorbance']
                )
            
            # 完整重绘（降低频率）
            if not hasattr(self, '_full_redraw_counter'):
                self._full_redraw_counter = 0
            
            self._full_redraw_counter += 1
            
            # 每10次更新才完整重绘一次
            if self._full_redraw_counter >= 10:
                self._full_redraw_counter = 0
                self.update_plots()  # 原完整更新方法
                
        except Exception as e:
            self.logger.error(f"优化图表更新失败: {e}")

class PlotDebouncer:
    """图表更新防抖器"""
    
    def __init__(self, delay=0.5):
        self.delay = delay
        self._timer = None
        self._lock = threading.RLock()
        self._cancelled = False
        self.logger = logging.getLogger(__name__)
    
    def debounce(self, func):
        """防抖装饰器"""
        def wrapper(*args, **kwargs):
            # 先在锁外获取timer引用，避免锁内join
            old_timer = None
            
            with self._lock:
                old_timer = self._timer
                self._cancelled = False
                
                def timer_func():
                    if not self._cancelled:
                        try:
                            func(*args, **kwargs)
                        except Exception as e:
                            self.logger.error(f"防抖函数执行失败: {e}", exc_info=True)
                
                self._timer = threading.Timer(self.delay, timer_func)
                self._timer.daemon = True
                self._timer.start()
            
            # 在锁外取消和join旧timer
            if old_timer and old_timer.is_alive():
                try:
                    old_timer.cancel()
                    old_timer.join(timeout=0.1)
                except Exception as e:
                    self.logger.debug(f"取消旧timer失败: {e}")
        
        return wrapper
    
    def cancel(self):
        """取消待执行的函数"""
        timer_to_cancel = None
        
        with self._lock:
            self._cancelled = True
            timer_to_cancel = self._timer
        
        # 在锁外执行取消和join
        if timer_to_cancel and timer_to_cancel.is_alive():
            timer_to_cancel.cancel()
            timer_to_cancel.join(timeout=0.5)


