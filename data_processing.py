import os
import json
import shutil
import logging
import hashlib
import threading
from datetime import datetime, timedelta
import pandas as pd

class DataCache:
    """数据缓存管理器"""
    
    def __init__(self, ttl_seconds=60):
        self.ttl_seconds = ttl_seconds
        self._cache = {}
        self._timestamps = {}
        self._access_count = {}
        self._lock = threading.RLock()
        self.logger = logging.getLogger(__name__)
        self._max_cache_size = 100  # 最多缓存100条，超过就淘汰最少用的
        self._stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'expirations': 0
        }
    
    def _generate_key(self, func_name, *args, **kwargs):
        """生成缓存键"""
        key_data = f"{func_name}:{str(args)}:{str(sorted(kwargs.items()))}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def get(self, key):
        """获取缓存"""
        with self._lock:
            if key in self._cache:
                timestamp = self._timestamps.get(key)
                if timestamp and (datetime.now() - timestamp).total_seconds() < self.ttl_seconds:
                    self._access_count[key] = self._access_count.get(key, 0) + 1
                    self._stats['hits'] += 1
                    return self._cache[key]
                else:
                    self._remove_key(key)
                    self._stats['expirations'] += 1
            
            self._stats['misses'] += 1
            return None
    
    def set(self, key, value):
        """设置缓存"""
        with self._lock:
            if len(self._cache) >= self._max_cache_size:
                self._evict_lru()
            
            self._cache[key] = value
            self._timestamps[key] = datetime.now()
            self._access_count[key] = 0
    
    def _remove_key(self, key):
        """删除指定键"""
        self._cache.pop(key, None)
        self._timestamps.pop(key, None)
        self._access_count.pop(key, None)
    
    def _evict_lru(self):
        """驱逐最少使用的缓存项"""
        if not self._access_count:
            return
        
        try:
            # 先创建快照，避免 "dictionary changed size during iteration"
            access_snapshot = list(self._access_count.items())
            
            if not access_snapshot:
                return
            
            # 找到访问次数最少的键
            lru_key = min(access_snapshot, key=lambda x: x[1])[0]
            
            # 双重检查：确保键仍然存在（可能已被其他线程删除）
            if lru_key in self._cache:
                self.logger.debug(f"驱逐LRU缓存: {lru_key[:8]}...")
                self._remove_key(lru_key)
                self._stats['evictions'] += 1
            else:
                self.logger.debug(f"LRU键{lru_key[:8]}已被其他线程删除，跳过")
                
        except (ValueError, KeyError) as e:
            self.logger.warning(f"LRU驱逐失败（已捕获）: {e}")
        except Exception as e:
            self.logger.error(f"LRU驱逐发生未预期错误: {e}", exc_info=True)
    
    def _cleanup_expired(self):
        """惰性清理过期缓存（限制每次清理数量）"""
        now = datetime.now()
        expired_keys = []
        
        # 只检查前10个，不然数据多了每次清理太慢
        for i, (k, t) in enumerate(self._timestamps.items()):
            if i >= 10:
                break
            if (now - t).total_seconds() >= self.ttl_seconds:
                expired_keys.append(k)
        
        for key in expired_keys:
            self._remove_key(key)
        
        if expired_keys:
            self.logger.debug(f"清理了 {len(expired_keys)} 个过期缓存")
    
    def clear(self):
        """清空缓存"""
        with self._lock:
            size = len(self._cache)
            self._cache.clear()
            self._timestamps.clear()
            self._access_count.clear()
            self.logger.info(f"已清空缓存 ({size} 项)")
    
    def get_stats(self):
        """获取缓存统计"""
        with self._lock:
            total_requests = self._stats['hits'] + self._stats['misses']
            hit_rate = (self._stats['hits'] / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'size': len(self._cache),
                'max_size': self._max_cache_size,
                'hits': self._stats['hits'],
                'misses': self._stats['misses'],
                'hit_rate': f"{hit_rate:.2f}%",
                'evictions': self._stats['evictions'],
                'expirations': self._stats['expirations']
            }
        
    def invalidate_by_pattern(self, pattern):
        """按模式清除缓存"""
        with self._lock:
            keys_to_remove = [
                k for k in self._cache.keys() 
                if pattern in k
            ]
            
            for key in keys_to_remove:
                self._remove_key(key)
            
            if keys_to_remove:
                self.logger.debug(f"按模式'{pattern}'清除了{len(keys_to_remove)}个缓存")
    
    def clear_old_data_cache(self):
        """清除旧数据相关的缓存（每次保存后调用）"""
        # 清除所有get_all_data和get_recent_data的缓存
        self.invalidate_by_pattern('get_all_data')
        self.invalidate_by_pattern('get_recent')

class DataArchiver:
    """数据归档管理器"""
    
    def __init__(self, db_manager, config_manager):
        self.db_manager = db_manager
        self.config = config_manager
        self.logger = logging.getLogger(__name__)
        self.archive_folder = 'archives'
        
        # 自动归档阈值（100万条）
        self.auto_archive_threshold = 1_000_000
        
        if not os.path.exists(self.archive_folder):
            os.makedirs(self.archive_folder)
    
    def archive_old_data(self, days_to_keep=365):
        """归档旧数据"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            cutoff_str = cutoff_date.strftime('%Y-%m-%d')
            
            self.logger.info(f"开始归档 {cutoff_str} 之前的数据...")
            
            with self.db_manager.get_connection() as conn:
                # 1. 统计要归档的数据
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT COUNT(*) FROM measurements 
                    WHERE timestamp < '{cutoff_str}'
                """)
                count = cursor.fetchone()[0]
                
                if count == 0:
                    self.logger.info("没有需要归档的数据")
                    return
                
                self.logger.info(f"找到 {count} 条数据需要归档")
                
                # 2. 导出到CSV
                query = f"""
                    SELECT * FROM measurements 
                    WHERE timestamp < '{cutoff_str}'
                    ORDER BY timestamp
                """
                df = pd.read_sql_query(query, conn)
                
                archive_file = os.path.join(
                    self.archive_folder,
                    f"archive_{cutoff_date.year}.csv.gz"
                )
                
                df.to_csv(archive_file, index=False, compression='gzip')
                self.logger.info(f"💾 已导出到 {archive_file}")
                
                # 3. 删除已归档数据
                cursor.execute(f"""
                    DELETE FROM measurements 
                    WHERE timestamp < '{cutoff_str}'
                """)
                deleted = cursor.rowcount
                
                # 4. 优化数据库
                cursor.execute("VACUUM")
                
                self.logger.info(f"归档完成！删除 {deleted} 条记录")
                
        except Exception as e:
            self.logger.error(f"归档失败: {e}")
    
    def auto_archive_check(self):
        """自动归档检查（每月1号执行）"""
        now = datetime.now()
        
        if now.day == 1 and now.hour == 2:  # 每月1号凌晨2点
            self.archive_old_data(days_to_keep=365)

    def check_and_auto_archive(self):
            """检查数据量并自动归档"""
            try:
                with self.db_manager.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM measurements")
                    total_count = cursor.fetchone()[0]
                    
                    if total_count > self.auto_archive_threshold:
                        self.logger.warning(
                            f"数据量达到阈值 ({total_count}/{self.auto_archive_threshold})，"
                            f"自动触发归档"
                        )
                        # 归档1年前的数据
                        self.archive_old_data(days_to_keep=365)
            
            except Exception as e:
                self.logger.error(f"自动归档检查失败: {e}")

class DataValidator:
    """数据验证器（责任链模式）"""
    
    def __init__(self, config_manager):
        self.config = config_manager
        self.logger = logging.getLogger(__name__)
        
        # 极端值检测阈值
        self.extreme_thresholds = {
            'uv275_absorbance': (0.0, 10.0),  # UV275不可能<=0或>10
            'temperature': (0, 50),             # 水温范围0-50℃
            'cod': (0, 1000),                   # COD上限1000
            'turbidity': (0.0, 500)            # 浊度范围：允许0值，上限500
        }
        
        self.validators = [
            self._validate_required_fields,
            self._validate_ranges,
            self._validate_types,
            self._validate_extreme_values  # 新增验证器
        ]
    
    def validate(self, data):
        """验证数据"""
        for validator in self.validators:
            is_valid, error_msg = validator(data)
            if not is_valid:
                self.logger.warning(f"数据验证失败: {error_msg}")
                return False, error_msg
        
        return True, None
    
    def _validate_required_fields(self, data):
        """验证必需字段"""
        required = ['temperature', 'humidity', 'uv275_absorbance',
                   'visible_absorbance', 'cod', 'turbidity']
        
        missing = [k for k in required if k not in data or data[k] is None]
        
        if missing:
            return False, f"缺少字段: {', '.join(missing)}"
        
        return True, None
    
    def _validate_ranges(self, data):
        """验证数值范围"""
        ranges = {
            'temperature': (
                self.config.getfloat('DataValidation', 'temp_min', 4),
                self.config.getfloat('DataValidation', 'temp_max', 40)
            ),
            'uv275_absorbance': (
                self.config.getfloat('DataValidation', 'uv275_min', 0),
                self.config.getfloat('DataValidation', 'uv275_max', 5)
            ),
            'cod': (
                self.config.getfloat('DataValidation', 'cod_min', 0),
                self.config.getfloat('DataValidation', 'cod_max', 500)
            )
        }
        
        for key, (min_val, max_val) in ranges.items():
            if key in data and not (min_val <= data[key] <= max_val):
                return False, f"{key} 超出范围: {data[key]} (范围: {min_val}-{max_val})"
        
        return True, None
    
    def _validate_types(self, data):
        """验证数据类型"""
        for key, value in data.items():
            if value is not None and not isinstance(value, (int, float)):
                try:
                    float(value)
                except (ValueError, TypeError):
                    return False, f"{key} 类型错误: {type(value)}"
        
        return True, None

    def _validate_extreme_values(self, data):
            """验证极端值"""
            for key, (min_val, max_val) in self.extreme_thresholds.items():
                if key in data:
                    value = data[key]
                    if value is not None:
                        if value < min_val or value > max_val:  # 使用 < 和 > 替代 <= 和 >=
                            self.logger.error(
                                f"注意：检测到极端值: {key}={value} "
                                f"(合理范围: {min_val}-{max_val})"
                            )
                            return False, f"{key}值异常: {value}"
            
            return True, None


