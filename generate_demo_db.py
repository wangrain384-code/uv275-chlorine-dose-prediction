# -*- coding: utf-8 -*-
"""
generate_demo_db.py —— UV275 软件演示数据库一键生成工具

功能：
  1. 生成一个全新的 uv275_data.db（覆盖现有的）
  2. 写入 22 天 × 每 5 分钟 = 约 6300 条 UV275 监测数据
  3. 时间戳基于"当前时间"动态生成，确保数据"刚刚新鲜"
  4. 约 0.5% 异常值散布其间，可演示软件的异常检测/标记功能

使用方法：
  1. 关闭软件（确保 uv275_data.db 文件没被占用）
  2. 把本脚本和你想要的目标位置的 uv275_data.db 放在同一目录
  3. 命令行运行：python generate_demo_db.py
  4. 跑完后启动软件，主图应有 22 天的完整数据

可重复执行：每次都用当前时间为基准重新生成。
"""
import sqlite3
import random
import math
import os
import shutil
from datetime import datetime, timedelta

DB_FILE = 'uv275_data.db'
DAYS = 22                    # 历史数据跨度
INTERVAL_MINUTES = 5         # 采样间隔
ANOMALY_RATE = 0.005         # 异常值比例（0.5%）

random.seed(42)

# ─── 备份现有数据库（如果有） ─────────────────────────
if os.path.exists(DB_FILE):
    backup = DB_FILE + '.before_demo'
    shutil.copy(DB_FILE, backup)
    print(f"✓ 已备份原数据库到 {backup}")
    os.remove(DB_FILE)

# ─── 创建数据库与表结构 ────────────────────────────────
conn = sqlite3.connect(DB_FILE)
cur = conn.cursor()

cur.execute("""
    CREATE TABLE measurements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        uv275_absorbance REAL,
        temperature REAL,
        cod REAL,
        turbidity REAL,
        humidity REAL,
        visible_absorbance REAL,
        chlorine_demand REAL,
        is_anomaly INTEGER DEFAULT 0
    )
""")
cur.execute("CREATE INDEX idx_timestamp ON measurements(timestamp)")
print(f"✓ 已创建 measurements 表")

# ─── 计算时间范围 ──────────────────────────────────────
# 终点：当前时间向下取整到 5 分钟整点（更像真实采样数据）
now = datetime.now().replace(second=0, microsecond=0)
end_time = now - timedelta(minutes=now.minute % INTERVAL_MINUTES + INTERVAL_MINUTES)
start_time = end_time - timedelta(days=DAYS)

print(f"  数据范围: {start_time} ~ {end_time}")

# ─── 生成数据 ──────────────────────────────────────────
# 推荐加氯量公式（和软件内置模型一致）
def predict_chlorine(uv275):
    return 12.131 * uv275 + 0.037

rows = []
current = start_time
anomaly_count = 0

while current <= end_time:
    hour = current.hour + current.minute / 60
    days_since_start = (current - start_time).total_seconds() / 86400
    day_of_year = current.timetuple().tm_yday
    
    # 温度：基线随季节缓慢漂移 + 日内波动
    temp_base = 18.0 + days_since_start * 0.15   # 22 天升约 3.3℃
    temp_diurnal = 2.0 * math.sin((hour - 6) * math.pi / 12)
    temperature = round(temp_base + temp_diurnal + random.uniform(-0.5, 0.5), 2)
    
    # UV275 吸光度：基线 0.050，轻微波动 ± 0.005
    uv275_base = 0.0500 + 0.0005 * math.sin(day_of_year * 0.3)
    uv275 = round(uv275_base + random.uniform(-0.003, 0.003), 4)
    
    # 偶尔的异常值（0.5% 概率）
    is_anomaly = 0
    if random.random() < ANOMALY_RATE:
        if random.random() < 0.5:
            uv275 = round(random.uniform(0.005, 0.008), 4)   # 异常低
        else:
            uv275 = round(random.uniform(0.10, 0.13), 4)     # 异常高
        is_anomaly = 1
        anomaly_count += 1
    
    # COD：和 UV275 弱相关，2.5-3.5 范围
    cod = round(2.7 + (uv275 - 0.050) * 30 + random.uniform(-0.3, 0.3), 3)
    
    # 浊度：稳定 0.09-0.13
    turbidity = round(0.105 + random.uniform(-0.018, 0.018), 3)
    
    # 湿度：65-75%，日内波动
    humidity = round(70 + 5 * math.sin(hour * math.pi / 12) + random.uniform(-2, 2), 1)
    
    # 可见光吸光度：很小
    visible_abs = round(0.008 + random.uniform(-0.003, 0.003), 4)
    
    # 推荐加氯量：异常值用基线值
    if is_anomaly:
        chlorine = round(predict_chlorine(0.0500), 4)
    else:
        chlorine = round(predict_chlorine(uv275), 4)
    
    rows.append((
        current.strftime('%Y-%m-%d %H:%M:%S'),
        uv275, temperature, cod, turbidity, humidity, visible_abs,
        chlorine, is_anomaly
    ))
    current += timedelta(minutes=INTERVAL_MINUTES)

# ─── 批量插入 ──────────────────────────────────────────
cur.executemany("""
    INSERT INTO measurements 
        (timestamp, uv275_absorbance, temperature, cod, turbidity, 
         humidity, visible_absorbance, chlorine_demand, is_anomaly)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
""", rows)
conn.commit()

# ─── 验证结果 ──────────────────────────────────────────
cur.execute("SELECT COUNT(*) FROM measurements")
total = cur.fetchone()[0]

cur.execute("SELECT MIN(timestamp), MAX(timestamp) FROM measurements")
earliest, latest = cur.fetchone()

print(f"\n✓ 演示数据生成完成！")
print(f"  总记录数: {total}")
print(f"  异常值: {anomaly_count} 条（约 {anomaly_count/total*100:.2f}%）")
print(f"  时间范围: {earliest} ~ {latest}")

# 显示最新 3 条预览
print(f"\n最新 3 条数据预览：")
cur.execute("""
    SELECT timestamp, uv275_absorbance, temperature, cod, 
           turbidity, chlorine_demand, is_anomaly
    FROM measurements ORDER BY id DESC LIMIT 3
""")
for row in cur.fetchall():
    print(f"  {row}")

conn.close()

print(f"\n下一步：启动软件，主图应有完整 22 天数据。")
print(f"如需恢复原数据：把 {DB_FILE}.before_demo 重命名为 {DB_FILE}。")
