import os
import sqlite3
import logging
import configparser

class ConfigManager:
    """配置文件管理器"""
    
    def __init__(self, config_file='config.ini'):
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self.load_config()
    
    def load_config(self):
        """加载配置文件"""
        if os.path.exists(self.config_file):
            self.config.read(self.config_file, encoding='utf-8')
        else:
            self.create_default_config()
    
    def create_default_config(self):
        """创建默认配置"""
        self.config['Sensor'] = {
            'default_port': 'COM3',
            'default_baudrate': '9600',
            'default_slave_address': '1',
            'measurement_interval': '300',  # 5分钟采一次，和传感器采样周期对齐
            'timeout': '3'
        }
        
        self.config['Database'] = {
            'db_file': 'uv275_data.db',
            'backup_enabled': 'true',
            'backup_interval': '86400',  # 24小时
            'backup_retention_days': '7'  # 只保留7天的备份，够了
        }
        
        self.config['Monitoring'] = {
            'max_consecutive_failures': '3',
            'retry_delay': '0.5',
            'enable_alarm': 'true'
        }
        
        self.config['DataValidation'] = {
            'temp_min': '4',
            'temp_max': '40',
            'uv275_min': '0',
            'uv275_max': '5',
            'cod_min': '0',
            'cod_max': '500'
        }

        self.config['Cache'] = {
            'ttl_seconds': '60',
            'enabled': 'true'
        }

        self.config['Waterplant'] = {
            'enabled':              'true',               # 默认关闭，正式部署时改为 true
            'host':                 '127.0.0.1',           # MySQL 所在主机（本地部署填 127.0.0.1）
            'port':                 '3306',
            'database':             'research_db',
            'user':                 'waterplant_reader',
            'password':             'tsinghua_yuepuwater',                     # 部署时填入本地 MySQL 密码
            'table_name':           'waterplant_realtime',
            'poll_interval':        '30',                   # 轮询周期（秒），建议 30-60 秒
            'max_data_age_minutes': '15',                   # 数据新鲜度阈值（分钟）
        }

        self.save_config()
    
    def save_config(self):
        """保存配置文件"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            self.config.write(f)
    
    def get(self, section, key, fallback=None):
        """获取配置值"""
        return self.config.get(section, key, fallback=fallback)
    
    def getint(self, section, key, fallback=0):
        """获取整数配置值"""
        return self.config.getint(section, key, fallback=fallback)
    
    def getfloat(self, section, key, fallback=0.0):
        """获取浮点数配置值"""
        return self.config.getfloat(section, key, fallback=fallback)
    
    def getboolean(self, section, key, fallback=False):
        """获取布尔值配置"""
        return self.config.getboolean(section, key, fallback=fallback)
    
    def set(self, section, key, value):
        """设置配置值"""
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, str(value))
        self.save_config()

class ConfigValidator:
    """配置验证器（精简版）"""
    
    @staticmethod
    def validate_serial_config(config):
        """验证串口配置"""
        errors = []
        
        # 检查必需字段
        if 'port' not in config or not config['port']:
            errors.append("未配置串口端口")
        
        # 检查波特率
        valid_baudrates = [2400, 9600, 19200, 38400, 57600, 115200]
        baudrate = config.get('baudrate')
        if baudrate not in valid_baudrates:
            errors.append(f"无效的波特率: {baudrate}（有效值: {valid_baudrates}）")
        
        # 检查从站地址
        slave = config.get('slave_address', 0)
        if not (1 <= slave <= 247):
            errors.append(f"无效的从站地址: {slave}（范围: 1-247）")
        
        return errors
    
    @staticmethod
    def validate_database(db_file):
        """验证数据库配置"""
        errors = []
        
        # 检查数据库目录写权限
        db_dir = os.path.dirname(db_file) or '.'
        if not os.access(db_dir, os.W_OK):
            errors.append(f"数据库目录无写权限: {db_dir}")
        
        # 检查现有数据库是否损坏
        if os.path.exists(db_file):
            try:
                conn = sqlite3.connect(db_file, timeout=5)
                cursor = conn.cursor()
                cursor.execute("PRAGMA integrity_check(10)")
                result = cursor.fetchone()
                if result[0] != 'ok':
                    errors.append(f"注意：数据库可能损坏: {result[0]}")
                conn.close()
            except sqlite3.Error as e:
                errors.append(f"数据库错误: {e}")
        
        return errors
    
    @staticmethod
    def validate_folders(folders):
        """验证文件夹配置"""
        errors = []
        
        for name, path in folders.items():
            if not os.path.exists(path):
                try:
                    os.makedirs(path)
                except OSError as e:
                    errors.append(f"无法创建{name}文件夹 {path}: {e}")
        
        return errors

