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

class DataQueryMixin:
    """数据库查询、异常值检测与界面事件回调相关方法"""

    def get_all_data(self, days_limit=30):
        # 由于每次查询全表过慢，默认只查30天，导出的时候再传None
        """获取数据"""
        cache_key = f'get_all_data_{days_limit}'
        cached_data = self.data_cache.get(cache_key)
        if cached_data is not None:
            return cached_data
        
        try:
            with self.db_manager.get_connection() as conn:
                if days_limit:
                    cutoff = (datetime.now() - timedelta(days=days_limit)).strftime('%Y-%m-%d')
                    query = f'''
                        SELECT timestamp, temperature, humidity, uv275_absorbance,
                            visible_absorbance, cod, turbidity, is_anomaly
                        FROM measurements
                        WHERE timestamp >= '{cutoff}'
                        ORDER BY timestamp
                    '''
                else:
                    # 仅在导出时查全表
                    query = '''
                        SELECT timestamp, temperature, humidity, uv275_absorbance,
                            visible_absorbance, cod, turbidity, is_anomaly
                        FROM measurements
                        ORDER BY timestamp
                    '''
                
                df = pd.read_sql_query(query, conn, parse_dates=['timestamp'])
                
                if not df.empty:
                    df['is_anomaly'] = df['is_anomaly'].astype(bool)
                    self.data_cache.set(cache_key, df)
                
                return df
                
        except Exception as e:
            self.logger.error(f"读取数据失败: {e}")
            return pd.DataFrame()

    # 导出时才查全表
    def get_all_data_full(self):
        """获取全部历史数据（仅用于导出）"""
        return self.get_all_data(days_limit=None)
    
    def get_recent_data(self, hours=24):
        """获取最近N小时的数据"""
        df = self.get_all_data()
        if df.empty:
            return df
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_df = df[df['timestamp'] >= cutoff_time]
        return recent_df
    
    def get_recent_data_days(self, days=7):
        """获取最近N天的数据"""
        df = self.get_all_data()
        if df.empty:
            return df
        
        cutoff_time = datetime.now() - timedelta(days=days)
        recent_df = df[df['timestamp'] >= cutoff_time]
        return recent_df
    
    def get_data_by_time_range(self):
        """根据选择的时间范围获取数据（带降采样）"""
        time_range = self.selected_time_range.get()
        
        # 获取原始数据
        if time_range == self.get_text('1_day'):
            df = self.get_recent_data(hours=24)
            max_points = 288  # 1天288条，全部显示
        elif time_range == self.get_text('1_week'):
            df = self.get_recent_data_days(days=7)
            max_points = 500  # 1周约2000条，降至500点
        elif time_range == self.get_text('1_month'):
            df = self.get_recent_data_days(days=30)
            max_points = 800  # 1月约8640条，降至800点
        else:
            df = self.get_all_data()
            max_points = 1000  # 全部数据，最多1000点
        
        # 降采样（仅在数据量超过阈值时）
        if len(df) > max_points:
            step = len(df) // max_points
            df_sampled = df.iloc[::step].copy()
            self.logger.debug(f"降采样: {len(df)} → {len(df_sampled)} 点")
            return df_sampled
        
        return df
    
    def detect_anomaly_empirical(self, value):
        """经验值方法检测异常"""
        if value is None or pd.isna(value):
            return True
        return value < self.empirical_range['min'] or value > self.empirical_range['max']
    
    def detect_anomaly_statistical(self, value):
        """统计方法检测异常"""
        if value is None or pd.isna(value):
            return True
        
        df = self.get_all_data()
        if df.empty or len(df) < 30:
            return self.detect_anomaly_empirical(value)
        
        historical_values = df['uv275_absorbance'].dropna()
        if len(historical_values) < 30:
            return self.detect_anomaly_empirical(value)
        
        Q1 = historical_values.quantile(0.25)
        Q3 = historical_values.quantile(0.75)
        IQR = Q3 - Q1
        
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        
        return value < lower_bound or value > upper_bound
    
    def get_days_since_first_record(self):
        """计算自第一条记录以来的天数（使用连接池）"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT MIN(timestamp)
                    FROM measurements
                ''')
                
                result = cursor.fetchone()
                
                if result and result[0]:
                    first_record = pd.to_datetime(result[0])
                    days = (datetime.now() - first_record).days
                    return days
                else:
                    return 0
                    
        except Exception as e:
            self.logger.error(f"获取首条记录时间失败: {e}")
            return 0
    
    def should_use_empirical_method(self):
        """判断是否应该使用经验值方法"""
        days = self.get_days_since_first_record()
        return days < self.initial_period_days
    
    def on_time_range_change(self, event=None):
        """时间范围改变时更新图表"""
        self.plot_debouncer.debounce(self.update_plots)()
    
    def on_pathogen_change(self, event=None):
        """病原体选择改变时更新计算"""
        self.update_parameter_display()
        self.update_data_display()
        self.update_plots()
    
    def on_season_change(self, event=None):
        """季节选择改变时更新计算"""
        self.update_parameter_display()
        self.update_data_display()
        self.update_plots()
    
    def on_inactivation_change(self, event=None):
        """灭活率选择改变时更新计算"""
        self.update_parameter_display()
        self.update_data_display()
        self.update_plots()
    
    def on_chart_param_change(self, event=None):
        """图表参数改变时更新图表"""
        self.update_plots()
    

