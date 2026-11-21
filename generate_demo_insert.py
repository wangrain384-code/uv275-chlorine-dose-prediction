# -*- coding: utf-8 -*-
"""
generate_demo_insert.py —— 动态生成水厂演示数据 INSERT 脚本

用当前时间作为基准，生成 30 条最近的水厂推送数据。
保证 record_time 是"刚刚发生的"，这样截图时水厂数据面板会显示
"已连接"绿色状态而不是"数据过期"。

使用方法：
    python generate_demo_insert.py
    
运行后会在同目录生成 demo_insert.sql 文件，然后：
    mysql -u root -p research_db < demo_insert.sql
"""
import random
from datetime import datetime, timedelta

random.seed(2026)

OUTPUT_FILE = 'demo_insert.sql'

# 基准时间：当前时间向下取整到 5 分钟
now = datetime.now().replace(second=0, microsecond=0)
end_time = now - timedelta(minutes=now.minute % 5)   # 对齐到 5 分钟整点

records = []
for i in range(30, 0, -1):
    ts = end_time - timedelta(minutes=5 * i)
    
    # 加氯量两路（约 1.0 mg/L）
    base_dose = 1.0 + random.uniform(-0.08, 0.08)
    dose1 = round(base_dose + random.uniform(-0.02, 0.02), 4)
    dose2 = round(base_dose * random.uniform(0.92, 1.08), 4)
    
    # 原水浊度两路
    raw_base = 10.5 + random.uniform(-2.5, 2.5)
    raw1 = round(raw_base + random.uniform(-0.5, 0.5), 4)
    raw2 = round(raw_base * random.uniform(0.65, 1.0), 4)
    
    # 砂滤、GAC、出厂水浊度
    sand_base = 0.048 + random.uniform(-0.005, 0.005)
    sand1 = round(sand_base + random.uniform(-0.003, 0.003), 5)
    sand2 = round(sand_base + random.uniform(-0.003, 0.003), 5)
    gac = round(0.040 + random.uniform(-0.005, 0.005), 5)
    eff_base = 0.043 + random.uniform(-0.003, 0.003)
    eff1 = round(eff_base + random.uniform(-0.002, 0.002), 5)
    eff2 = round(eff_base + random.uniform(-0.002, 0.002), 5)
    
    records.append((
        ts.strftime('%Y-%m-%d %H:%M:%S'),
        dose1, dose2, raw1, raw2, sand1, sand2, gac, eff1, eff2
    ))

# 生成 SQL 内容
sql_lines = [
    "-- ============================================================",
    f"-- 水厂演示数据 - 生成于 {now.strftime('%Y-%m-%d %H:%M:%S')}",
    "-- 30 条数据，覆盖当前时间前 2.5 小时",
    "-- 使用方法：mysql -u root -p research_db < demo_insert.sql",
    "-- ============================================================",
    "",
    "USE research_db;",
    "",
    "DELETE FROM waterplant_realtime;",
    "",
    "INSERT INTO waterplant_realtime",
    "    (record_time, chlorine_dose_1, chlorine_dose_2,",
    "     raw_turbidity_1, raw_turbidity_2,",
    "     sand_filter_turbidity_1, sand_filter_turbidity_2,",
    "     gac_turbidity,",
    "     effluent_turbidity_1, effluent_turbidity_2)",
    "VALUES"
]

value_lines = []
for r in records:
    value_lines.append(
        f"    ('{r[0]}', {r[1]}, {r[2]}, {r[3]}, {r[4]}, "
        f"{r[5]}, {r[6]}, {r[7]}, {r[8]}, {r[9]})"
    )
sql_lines.append(",\n".join(value_lines) + ";")
sql_lines += [
    "",
    "SELECT COUNT(*) AS 总记录数 FROM waterplant_realtime;",
    "SELECT * FROM waterplant_realtime ORDER BY record_time DESC LIMIT 3;",
]

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write("\n".join(sql_lines))

# 打印预期效果
last = records[-1]
print(f"✓ 已生成 {OUTPUT_FILE}")
print(f"  最新时间戳: {last[0]}")
print(f"  GAC 浊度: {last[7]} NTU → 隐孢子虫面板亮绿灯")
print(f"\n下一步：")
print(f"  mysql -u root -p research_db < {OUTPUT_FILE}")
