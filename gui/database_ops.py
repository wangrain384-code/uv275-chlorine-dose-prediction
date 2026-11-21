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

import sqlite3
from utils import retry_on_db_error

class DatabaseOpsMixin:
    """数据库表初始化、历史数据迁移与写入相关方法"""

    def setup_database(self):
        """初始化SQLite数据库（使用连接池 + 添加复合索引 + 增强异常处理 + 字段迁移）"""
        try:
            self.logger.info("开始初始化数据库...")
            
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # 创建数据表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS measurements (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        uv275_absorbance REAL NOT NULL,
                        temperature REAL,
                        cod REAL,
                        turbidity REAL,
                        humidity REAL,
                        visible_absorbance REAL,
                        chlorine_demand REAL,
                        is_anomaly INTEGER DEFAULT 0,
                        UNIQUE(timestamp)
                    )
                ''')
                
                # 创建索引
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_timestamp 
                    ON measurements(timestamp DESC)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_timestamp_anomaly 
                    ON measurements(timestamp DESC, is_anomaly)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_timestamp_uv275 
                    ON measurements(timestamp DESC, uv275_absorbance)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_timestamp_cover 
                    ON measurements(
                        timestamp DESC, 
                        uv275_absorbance, 
                        temperature, 
                        is_anomaly
                    )
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_anomaly 
                    ON measurements(is_anomaly)
                ''')
                
                conn.commit()
                
                # 字段迁移：检查并添加缺失字段
                try:
                    cursor.execute("PRAGMA table_info(measurements)")
                    columns = [col[1] for col in cursor.fetchall()]
                    
                    if 'chlorine_demand' not in columns:
                        self.logger.info("添加缺失的chlorine_demand字段...")
                        cursor.execute("ALTER TABLE measurements ADD COLUMN chlorine_demand REAL")
                        conn.commit()
                        self.logger.info("已添加chlorine_demand字段")
                except Exception as e:
                    self.logger.warning(f"字段检查/添加失败: {e}")
                
                self.logger.info(f"数据库初始化完成（含5个索引）: {self.db_file}")
                
                # 迁移CSV数据
                if os.path.exists(self.csv_file):
                    try:
                        self.migrate_csv_to_db()
                    except Exception as e:
                        self.logger.error(f"CSV迁移失败: {e}")
                
        except sqlite3.OperationalError as e:
            self.logger.error(f"数据库操作错误: {e}", exc_info=True)
            messagebox.showerror(
                "数据库错误 / Database Error",
                f"数据库操作失败，可能文件已损坏\n"
                f"Database operation failed\n\n{str(e)}"
            )
            raise
        except Exception as e:
            self.logger.critical(f"数据库初始化失败: {e}", exc_info=True)
            messagebox.showerror(
                "严重错误 / Critical Error",
                f"数据库初始化失败，程序无法继续\n"
                f"Database initialization failed\n\n{str(e)}"
            )
            raise

    
    def migrate_csv_to_db(self):
        """CSV 迁移使用连接池"""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # 检查数据库是否已有数据
                cursor.execute("SELECT COUNT(*) FROM measurements")
                count = cursor.fetchone()[0]
                
                if count > 0:
                    self.logger.info("数据库已有数据，跳过 CSV 迁移")
                    return
                
                if not os.path.exists(self.csv_file):
                    return
                
                df = pd.read_csv(self.csv_file)
                
                if df.empty:
                    self.logger.info("CSV 文件为空，无需迁移")
                    return
                
                # 数据清洗
                # 1. 去重（按时间戳）
                original_count = len(df)
                df.drop_duplicates(subset=['timestamp'], keep='first', inplace=True)
                duplicates_removed = original_count - len(df)
                
                if duplicates_removed > 0:
                    self.logger.warning(f"注意：移除了 {duplicates_removed} 条重复记录")
                
                # 2. 格式化时间戳
                df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
                
                # 3. 确保 is_anomaly 为整数
                df['is_anomaly'] = df['is_anomaly'].fillna(0).astype(int)
                
                # 4. 按时间排序
                df.sort_values('timestamp', inplace=True)
                
                # 写入数据库
                df.to_sql('measurements', conn, if_exists='append', index=False)
                conn.commit()  # isolation_level=None时是自动提交，但迁移这种批量操作还是手动commit保险
                
                self.logger.info(f"成功迁移 {len(df)} 条有效数据（移除 {duplicates_removed} 条重复）")
                
        except Exception as e:
            self.logger.error(f"CSV 迁移失败: {e}")
    
    @retry_on_db_error(max_retries=3, delay=0.5, backoff=2.0)
    def save_to_db(self, data):
        """保存数据到数据库（使用连接池和验证+重试）"""
        try:
            # 数据验证
            is_valid, error_msg = self.data_validator.validate(data)
            if not is_valid:
                self.logger.error(f"数据验证失败: {error_msg}")
                return
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            # ... 保持原有代码不变 ...
            
            uv275_raw = data['uv275_absorbance']
            uv275_calibrated = self.apply_calibration(uv275_raw, 'uv275_absorbance')
            
            is_anomaly = self.detect_anomaly(uv275_calibrated)
            
            # 准备插入数据
            new_row = {
                'timestamp': timestamp,
                'temperature': self.apply_calibration(data['temperature'], 'temperature'),
                'humidity': data['humidity'],
                'uv275_absorbance': uv275_calibrated,
                'visible_absorbance': self.apply_calibration(data['visible_absorbance'], 'visible_absorbance'),
                'cod': self.apply_calibration(data['cod'], 'cod'),
                'turbidity': self.apply_calibration(data['turbidity'], 'turbidity'),
                'is_anomaly': int(is_anomaly)
            }
            
            # 使用连接池和事务
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO measurements 
                    (timestamp, temperature, humidity, uv275_absorbance, 
                    visible_absorbance, cod, turbidity, is_anomaly)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    new_row['timestamp'],
                    new_row['temperature'],
                    new_row['humidity'],
                    new_row['uv275_absorbance'],
                    new_row['visible_absorbance'],
                    new_row['cod'],
                    new_row['turbidity'],
                    new_row['is_anomaly']
                ))
                # 提交由上下文管理器处理
            
            # 清除缓存
            self.data_cache.clear_old_data_cache()
            
            if not is_anomaly:
                self.last_normal_value = uv275_calibrated
            
            # 异步检查报警
            self._check_alarms_async(uv275_calibrated, data)
            
            self.struct_logger.log_sampling(
                    uv275=uv275_calibrated,
                    temp=new_row['temperature'],
                    status='anomaly' if is_anomaly else 'success'
                )
            
        except Exception as e:
            self.logger.error(f"保存数据失败: {e}", exc_info=True)


