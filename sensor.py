import time
import logging
import threading
import serial
import serial.tools.list_ports
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException

# pymodbus 3.x+ 版本不再需要在 read_input_registers 中传递 slave/unit 参数
# 从站地址在 ModbusSerialClient 初始化时设置
try:
    import pymodbus
    print(f"pymodbus 版本: {pymodbus.__version__}")
except Exception as e:
    print(f"无法检测 pymodbus 版本: {e}")

from datetime import datetime

class SensorRecoveryManager:
    """传感器恢复管理器"""
    
    def __init__(self, max_failures=3, recovery_delay=60):
        """
        Args:
            max_failures: 连续失败多少次进入恢复模式
            recovery_delay: 恢复尝试间隔（秒）
        """
        self.consecutive_failures = 0
        self.max_failures = max_failures
        self.recovery_delay = recovery_delay
        self.last_recovery_attempt = None
        self.recovery_mode = False
        self.logger = logging.getLogger(__name__)
    
    def record_failure(self):
        """记录一次失败"""
        self.consecutive_failures += 1
        self.logger.warning(f"传感器读取失败 ({self.consecutive_failures}/{self.max_failures})")
        
        if self.consecutive_failures >= self.max_failures:
            self.enter_recovery_mode()
    
    def record_success(self):
        """记录成功"""
        if self.recovery_mode:
            self.logger.info("传感器恢复正常")
        
        self.consecutive_failures = 0
        self.recovery_mode = False
    
    def enter_recovery_mode(self):
        """进入恢复模式"""
        if not self.recovery_mode:
            self.logger.error(f"注意：进入恢复模式，连续失败{self.consecutive_failures}次")
            self.recovery_mode = True
            self.last_recovery_attempt = time.time()
    
    def should_attempt_recovery(self):
        """判断是否应该尝试恢复"""
        if not self.recovery_mode:
            return True
        
        if self.last_recovery_attempt is None:
            return True
        
        elapsed = time.time() - self.last_recovery_attempt
        return elapsed >= self.recovery_delay
    
    def attempt_recovery(self, sensor):
        """尝试恢复传感器连接"""
        if not self.should_attempt_recovery():
            return False
        
        self.logger.info("尝试重新连接传感器...")
        self.last_recovery_attempt = time.time()
        
        try:
            sensor.disconnect()
            time.sleep(2)
            
            if sensor.connect():
                self.logger.info("传感器重新连接成功")
                return True
            else:
                self.logger.warning("传感器重新连接失败")
                return False
        except Exception as e:
            self.logger.error(f"恢复过程出错: {e}")
            return False

# pymodbus 3.x+ 不再需要在调用时传递参数
# 从站地址将在ModbusSerialClient初始化后通过 client.slave 设置


class UV275SensorModbus:
    """UV275传感器Modbus RTU通信类"""
    
    def __init__(self, port='COM3', baudrate=9600, slave_address=1, timeout=3, 
                 auto_scan=True, config_file='serial_config.json'):
        """
        初始化传感器对象
        
        Args:
            port: 串口号
            baudrate: 波特率
            slave_address: 从站地址
            timeout: 超时时间（秒）
            auto_scan: 是否启用自动扫描（默认True）
            config_file: 配置文件路径（用于保存自动识别的端口）
        """
        self.port = port
        self.baudrate = baudrate
        self.slave_address = slave_address  # Modbus从站地址，本课题采用传感器默认值为1
        self.timeout = timeout  # 超时时间不能太短，传感器有时候反应慢
        self.auto_scan = auto_scan
        self.config_file = config_file
        self.client = None
        self.logger = logging.getLogger(__name__)
    
    def connect(self):
        """
        连接传感器，如果配置端口失败会自动扫描其他端口
        
        Returns:
            bool: 连接是否成功
        """
        available_ports = [p.device for p in serial.tools.list_ports.comports()]
        
        if not available_ports:
            self.logger.error("系统中没有可用串口！")
            return False
        
        self.logger.info(f"可用串口: {', '.join(available_ports)}")
        
        # 策略1：优先尝试配置的端口
        if self.port in available_ports:
            self.logger.info(f"尝试连接配置端口: {self.port}")
            if self._try_connect_and_verify(self.port):
                return True
        
        # 策略2：如果启用自动扫描且配置端口失败，扫描所有可用端口
        if self.auto_scan:
            self.logger.warning(
                f"配置端口 {self.port} 不可用或连接失败，"
                f"开始自动扫描 {len(available_ports)} 个可用端口..."
            )
            
            for idx, port in enumerate(available_ports, 1):
                self.logger.info(f"  [{idx}/{len(available_ports)}] 正在尝试: {port}")
                
                if self._try_connect_and_verify(port):
                    old_port = self.port
                    self.port = port  # 更新成功的端口
                    self.logger.info(f"自动切换: {old_port} → {port}")
                    
                    # 可选：保存新配置到文件
                    try:
                        self._save_port_to_config(port)
                    except Exception as e:
                        self.logger.warning(f"保存端口配置失败: {e}")
                    
                    return True
        
        # 策略3：所有尝试均失败
        self.logger.error(
            f"所有串口 ({', '.join(available_ports)}) 均连接失败！\n"
            f"请检查：\n"
            f"  1. 传感器是否正确连接\n"
            f"  2. 波特率设置是否正确（当前: {self.baudrate}）\n"
            f"  3. 从站地址是否正确（当前: {self.slave_address}）\n"
            f"  4. USB驱动是否已安装"
        )
        return False
    
    def _try_connect_and_verify(self, port):
        """
        尝试连接指定端口，连上之后读一次数据验证通信是否正常
        
        Args:
            port: 要尝试的串口号
            
        Returns:
            bool: 连接和验证是否成功
        """
        test_client = None
        try:
            # 步骤1：创建Modbus客户端
            test_client = ModbusSerialClient(
                port=port,
                baudrate=self.baudrate,
                bytesize=8,
                parity='N',
                stopbits=1,
                timeout=self.timeout
            )
            
            # 步骤2：尝试连接
            if not test_client.connect():
                self.logger.debug(f"    端口 {port} 无法打开")
                return False
            
            # 设置从站地址
            test_client.slave = self.slave_address
            
            self.logger.debug(f"    端口 {port} 已打开，正在验证通信...")
            
            # 步骤3：验证通信（读取寄存器1测试）
            # 尝试多种方式调用（兼容不同pymodbus版本）
            try:
                # 方式1：不传递任何slave参数（推荐用于pymodbus 3.6+）
                result = test_client.read_input_registers(address=0x0001, count=1)
            except TypeError:
                try:
                    # 方式2：传递slave参数
                    result = test_client.read_input_registers(address=0x0001, count=1, slave=self.slave_address)
                except TypeError:
                    # 方式3：传递unit参数
                    result = test_client.read_input_registers(address=0x0001, count=1, unit=self.slave_address)
            
            if result.isError():
                self.logger.error(f"    端口 {port} Modbus通信失败: {result}")
                test_client.close()
                return False
            
            # 步骤4：成功，保存客户端
            self.client = test_client
            self.logger.info(f"    端口 {port} 通信验证成功！")
            return True
            
        except Exception as e:
            self.logger.debug(f"    端口 {port} 异常: {e}")
            if test_client:
                try:
                    test_client.close()
                except:
                    pass
            return False
    
    def _save_port_to_config(self, port):
        """
        把成功连接的端口记到配置文件里，下次启动直接用
        
        Args:
            port: 要保存的端口号
        """
        import json
        import os
        
        try:
            # 读取现有配置
            config = {}
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            
            # 更新端口
            config['port'] = port
            config['auto_detected'] = True
            config['detection_time'] = time.strftime('%Y-%m-%d %H:%M:%S')
            
            # 保存配置
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"已保存端口配置: {port}")
            
        except Exception as e:
            self.logger.error(f"保存端口配置失败: {e}")
    
    def disconnect(self):
        """断开连接"""
        if self.client:
            try:
                self.client.close()
                self.logger.info(f"串口 {self.port} 连接已关闭")
            except Exception as e:
                self.logger.error(f"断开连接时出错: {e}")
            finally:
                self.client = None
    
    def read_all_data(self):
        """
        读取传感器全部寄存器，一共13个，之前漏掉了采样计数寄存器
        
        根据说明书第8页，浮动寄存器地址范围: 0x0001-0x000D (共13个)
        
        Returns:
            dict: 包含所有传感器数据的字典，失败返回None
        """
        try:
            # 确保client.slave已设置（冗余保护）
            if self.client and hasattr(self.client, 'slave'):
                self.client.slave = self.slave_address
            
            # 使用健壮的多重尝试方式
            # 读取完整的13个寄存器
            try:
                # 方式1：不传递slave参数（pymodbus 3.6+）
                result = self.client.read_input_registers(address=0x0001, count=13)
            except TypeError:
                try:
                    # 方式2：传递slave参数（pymodbus 3.0-3.5）
                    result = self.client.read_input_registers(address=0x0001, count=13, slave=self.slave_address)
                except TypeError:
                    # 方式3：传递unit参数（pymodbus 2.x）
                    result = self.client.read_input_registers(address=0x0001, count=13, unit=self.slave_address)
            
            if not result.isError():
                # 按照说明书定义解析数据
                data = {
                    # 寄存器 1-2: 温湿度
                    'temperature': result.registers[0] / 10.0,           # 寄存器1 (真实值的10倍)
                    'humidity': result.registers[1] / 10.0,              # 寄存器2 (真实值的10倍)
                    
                    # 寄存器 3-6: 光强测量值 (mV)
                    'uv275_light': result.registers[2],                  # 寄存器3 (275nm测量时)
                    'visible_light': result.registers[3],                # 寄存器4 (520nm测量时)
                    'uv275_light_zero': result.registers[4],             # 寄存器5 (275nm校零时)
                    'visible_light_zero': result.registers[5],           # 寄存器6 (520nm校零时)
                    
                    # 寄存器 7-10: 计算值
                    'uv275_absorbance': result.registers[6] / 1000.0,    # 寄存器7 (真实值的1000倍)
                    'visible_absorbance': result.registers[7] / 1000.0,  # 寄存器8 (真实值的1000倍)
                    'cod': result.registers[8] / 10.0,                   # 寄存器9 (COD, mg/L, 真实值的10倍)
                    'turbidity': max(0.0, result.registers[9] / 10.0),   # 寄存器10 (浊度, NTU, 真实值的10倍)
                    
                    # 寄存器 12-13 (采样计数) - 之前缺失
                    'measurement_count_current': result.registers[11],   # 寄存器12 (实时CT: 0-500, 超过归零)
                    'measurement_count_total': result.registers[12]      # 寄存器13 (累计CT: 0-65535, 超过不再增加)
                }
                
                # 添加详细的调试日志
                self.logger.debug(
                    f"数据读取成功 | "
                    f"UV275={data['uv275_absorbance']:.4f} /cm | "
                    f"COD={data['cod']:.1f} mg/L | "
                    f"浊度={data['turbidity']:.1f} NTU | "
                    f"温度={data['temperature']:.1f}°C | "
                    f"湿度={data['humidity']:.1f}% | "
                    f"计数={data['measurement_count_current']}/{data['measurement_count_total']}"
                )
                
                return data
            else:
                self.logger.error(f"读取寄存器错误: {result}")
                return None
                
        except Exception as e:
            self.logger.error(f"读取数据异常: {e}", exc_info=True)
            return None
    
    def read_all_data_with_retry(self, max_retries=3, retry_delay=0.5):
        """
        带重试机制的数据读取
        
        Args:
            max_retries: 最大重试次数
            retry_delay: 重试间隔（秒）
            
        Returns:
            dict: 传感器数据，失败返回None
        """
        for attempt in range(max_retries):
            try:
                data = self.read_all_data()
                if data is not None:
                    if attempt > 0:
                        self.logger.info(f"第{attempt+1}次尝试读取成功")
                    return data
                
                if attempt < max_retries - 1:
                    self.logger.warning(
                        f"读取失败，{retry_delay}秒后重试... "
                        f"(尝试 {attempt + 1}/{max_retries})"
                    )
                    time.sleep(retry_delay)
                    
            except Exception as e:
                self.logger.error(f"读取异常 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
        
        self.logger.error(f"{max_retries}次尝试均失败！")
        return None
    
    def check_communication_health(self, test_count=3):
        """
        连续发几次请求看看成功率，判断通信是否稳定
        
        Args:
            test_count: 测试次数
            
        Returns:
            tuple: (健康度百分比, 成功次数, 总次数)
        """
        success_count = 0
        
        for i in range(test_count):
            data = self.read_all_data()
            if data:
                success_count += 1
            time.sleep(0.1)
        
        health_percentage = (success_count / test_count) * 100
        
        self.logger.info(
            f"通信健康检查: {success_count}/{test_count} 成功 "
            f"({health_percentage:.1f}%)"
        )
        
        return health_percentage, success_count, test_count
    
    def get_sensor_info(self):
        """
        读传感器基本信息，主要用于调试和日志
        
        根据说明书第11页，信息寄存器地址: 0x003C-0x0043
        
        Returns:
            dict: 传感器信息，失败返回None
        """
        try:
            # 确保client.slave已设置（冗余保护）
            if self.client and hasattr(self.client, 'slave'):
                self.client.slave = self.slave_address
            
            # 使用健壮的多重尝试方式
            try:
                # 方式1：不传递slave参数（pymodbus 3.6+）
                result = self.client.read_holding_registers(address=0x003C, count=8)
            except TypeError:
                try:
                    # 方式2：传递slave参数（pymodbus 3.0-3.5）
                    result = self.client.read_holding_registers(address=0x003C, count=8, slave=self.slave_address)
                except TypeError:
                    # 方式3：传递unit参数（pymodbus 2.x）
                    result = self.client.read_holding_registers(address=0x003C, count=8, unit=self.slave_address)
            
            if not result.isError():
                info = {
                    'hardware_version': result.registers[0],     # 探头硬件版本
                    'software_version': result.registers[1],     # 探头软件版本
                    'production_batch': result.registers[2],     # 传感器生产批次
                    'unique_id': result.registers[3],            # 设备唯一地址编码
                    'path_length': result.registers[4] / 10.0,   # 光程系数 (实际值的10倍)
                    'cod_coefficient': result.registers[5],      # COD系数 K1'
                    'turbidity_coefficient': result.registers[6], # 浊度系数 K2'
                    'motor_time': result.registers[7]            # 电机单向转动时间参数 (ms)
                }
                
                self.logger.info(
                    f"📋 传感器信息 | "
                    f"硬件版本={info['hardware_version']} | "
                    f"软件版本={info['software_version']} | "
                    f"光程={info['path_length']}mm"
                )
                
                return info
            else:
                self.logger.error(f"读取传感器信息错误: {result}")
                return None
                
        except Exception as e:
            self.logger.error(f"读取传感器信息异常: {e}")
            return None


