import sqlite3
import threading
import queue
import time
import logging
from contextlib import contextmanager

class DatabaseManager:
    """数据库连接池管理器"""
    
    def __init__(self, db_file, pool_size=5):
        self.db_file = db_file
        self.pool_size = pool_size
        self._pool = queue.Queue(maxsize=pool_size)
        self._pool_lock = threading.Lock()
        self._total_connections = 0
        self._max_connections = pool_size * 2
        
        # 添加logger初始化（修复缺失）
        self.logger = logging.getLogger(__name__)
        
        # 使用线程本地存储
        self._local = threading.local()
        
        # 预创建连接池
        for _ in range(pool_size):
            conn = self._create_connection()
            if conn:
                self._pool.put(conn)
    
    def _create_connection(self):
        """创建新的数据库连接"""
        try:
            conn = sqlite3.connect(
                self.db_file, 
                timeout=10.0, 
                check_same_thread=False,
                isolation_level=None  # 自动提交
            )
            
            # WAL模式优化
            conn.execute("PRAGMA journal_mode=WAL")          # WAL模式，读写互不阻塞，5分钟写一次完全可满足
            conn.execute("PRAGMA synchronous=NORMAL")        # 平衡性能和安全
            conn.execute("PRAGMA cache_size=-64000")         # 64MB缓存，本课题电脑内存可满足
            conn.execute("PRAGMA temp_store=MEMORY")         # 临时表在内存
            conn.execute("PRAGMA mmap_size=268435456")       # 256MB内存映射
            conn.execute("PRAGMA page_size=4096")            # 4KB页面大小
            conn.execute("PRAGMA wal_autocheckpoint=1000")   # 1000页后自动检查点
            
            # 针对5分钟采样的优化
            # 因为写入频率低，可以设置更大的WAL文件
            conn.execute("PRAGMA journal_size_limit=67108864")  # 64MB WAL限制
            
            with self._pool_lock:
                self._total_connections += 1
            
            self.logger.debug("创建数据库连接")
            return conn
        except Exception as e:
            self.logger.error(f"创建数据库连接失败: {e}")
            return None

    def get_connection_stats(self):
        """获取连接池统计信息"""
        with self._pool_lock:
            return {
                'total_connections': self._total_connections,
                'pool_size': self._pool.qsize(),
                'max_connections': self._max_connections
            }

    def _get_connection(self):
        """从池中获取连接（while循环替代递归）"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # 尝试从连接池获取
                conn = self._pool.get(timeout=10.0)
                
                try:
                    # 验证连接有效性
                    conn.execute("PRAGMA quick_check(1)")
                    return conn  # 成功返回
                    
                except sqlite3.Error as e:
                    print(f"连接失效(尝试{retry_count + 1}/{max_retries}): {e}")
                    
                    # 关闭失效连接
                    try:
                        conn.close()
                    except:
                        pass
                    
                    # 减少连接计数
                    with self._pool_lock:
                        self._total_connections -= 1
                    
                    retry_count += 1
                    
                    if retry_count >= max_retries:
                        raise sqlite3.Error(f"连接池重试{max_retries}次全部失败")
                    
                    # 等待后继续下一次循环（避免递归）
                    time.sleep(0.5)
                    continue
                    
            except queue.Empty:
                # 连接池为空，检查是否可以创建新连接
                with self._pool_lock:
                    if self._total_connections >= self._max_connections:
                        raise sqlite3.Error(f"数据库连接池已满({self._total_connections}/{self._max_connections})")
                
                return self._create_connection()
        
        # 理论上不会到达这里，但作为安全兜底
        raise sqlite3.Error("无法获取数据库连接：未知错误")
    
    def _return_connection(self, conn):
        """归还连接到池"""
        if not conn:
            return
        
        try:
            conn.rollback()
            
            if self._pool.qsize() < self.pool_size:
                self._pool.put_nowait(conn)
            else:
                try:
                    conn.close()
                except:
                    pass
                finally:
                    with self._pool_lock:
                        self._total_connections -= 1
                        
        except queue.Full:
            try:
                conn.close()
            except:
                pass
            finally:
                with self._pool_lock:
                    self._total_connections -= 1
    
    @contextmanager
    def get_connection(self):
        """上下文管理器获取数据库连接"""
        conn = self._get_connection()
        try:
            yield conn
        except Exception as e:
            try:
                conn.rollback()
            except:
                pass
            raise
        finally:
            self._return_connection(conn)
    
    def close_all(self):
        """关闭所有连接"""
        closed_count = 0
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
                closed_count += 1
            except queue.Empty:
                break
            except Exception as e:
                print(f"关闭连接失败: {e}")
        
        print(f"已关闭 {closed_count} 个数据库连接")

class DatabaseMaintenance:
    """数据库维护管理器"""
    
    def __init__(self, db_manager, maintenance_interval=86400*7):
        self.db_manager = db_manager
        self.maintenance_interval = maintenance_interval
        self.logger = logging.getLogger(__name__)
        self._stop_event = threading.Event()
    
    def start(self):
        """启动维护线程"""
        maintenance_thread = threading.Thread(
            target=self._maintenance_loop,
            daemon=True,
            name="DatabaseMaintenance"
        )
        maintenance_thread.start()
        self.logger.info("数据库维护线程启动")
    
    def _maintenance_loop(self):
        """维护循环"""
        while not self._stop_event.wait(self.maintenance_interval):
            try:
                self._perform_maintenance()
            except Exception as e:
                self.logger.error(f"数据库维护失败: {e}")
    
    def _perform_maintenance(self):
        """执行维护"""
        self.logger.info("开始数据库维护...")
        
        with self.db_manager.get_connection() as conn:
            # 1. WAL检查点
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self.logger.info("  WAL检查点完成")
            
            # 2. 分析查询优化
            conn.execute("ANALYZE")
            self.logger.info("  查询优化完成")
            
            # 3. 完整性检查
            result = conn.execute("PRAGMA integrity_check(10)").fetchone()
            if result[0] == 'ok':
                self.logger.info("  完整性检查通过")
            else:
                self.logger.error(f"  完整性检查失败: {result[0]}")
        
        self.logger.info("数据库维护完成")
    
    def stop(self):
        """停止维护"""
        self._stop_event.set()


