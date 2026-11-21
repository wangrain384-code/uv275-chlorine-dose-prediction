# -*- coding: utf-8 -*-
"""
waterplant_reader.py — 水厂数据读取模块（MySQL）

本模块为 UV275MonitorGUI 的 Mixin，提供从本地MySQL接收数据库
读取水厂推送数据的功能。该数据库由水厂电脑B通过推送方式写入，
本软件仅执行 SELECT 只读访问。

设计原则：
1. 与 SQLite 传感器数据库完全独立，互不影响
2. 连接失败时优雅降级，不影响主软件任何功能
3. 独立后台线程轮询，不阻塞监测主循环
4. 所有配置项可通过 config.ini 调整
"""

import threading
from datetime import datetime

try:
    import pymysql
    PYMYSQL_AVAILABLE = True
except ImportError:
    PYMYSQL_AVAILABLE = False


class WaterplantReaderMixin:
    """水厂推送数据读取Mixin（从MySQL接收端读取）"""

    # ────────────────────────────────────────────────
    # 初始化
    # ────────────────────────────────────────────────
    def init_waterplant_reader(self):
        """初始化水厂数据读取模块

        在 UV275MonitorGUI.__init__ 末尾调用一次，若配置未启用或pymysql未安装则静默跳过。
        """
        self.waterplant_enabled = False
        self.waterplant_latest = None   # 最近一次成功读取到的数据 dict
        self.waterplant_last_success_time = None
        self.waterplant_consecutive_failures = 0
        self._waterplant_stop_event = threading.Event()
        self._waterplant_thread = None

        # 从 config.ini 读取配置（若不存在则 Section 为空）
        try:
            enabled = self.config_manager.getboolean(
                'Waterplant', 'enabled', fallback=False
            )
        except Exception:
            enabled = False

        if not enabled:
            self.logger.info("水厂数据接入未启用（config.ini 中 [Waterplant] enabled=false）")
            return

        if not PYMYSQL_AVAILABLE:
            self.logger.warning(
                "检测到 [Waterplant] 已启用，但 pymysql 未安装；"
                "请执行 pip install pymysql 后重启软件，水厂数据读取功能将被禁用"
            )
            return

        # 读取连接参数
        self.waterplant_config = {
            'host':     self.config_manager.get('Waterplant', 'host',     fallback='127.0.0.1'),
            'port':     self.config_manager.getint('Waterplant', 'port',  fallback=3306),
            'database': self.config_manager.get('Waterplant', 'database', fallback='research_db'),
            'user':     self.config_manager.get('Waterplant', 'user',     fallback='waterplant_reader'),
            'password': self.config_manager.get('Waterplant', 'password', fallback=''),
            'charset':  'utf8mb4',
            'connect_timeout': 10,
        }
        self.waterplant_table = self.config_manager.get(
            'Waterplant', 'table_name', fallback='waterplant_realtime'
        )
        self.waterplant_poll_interval = self.config_manager.getint(
            'Waterplant', 'poll_interval', fallback=30   # 默认30秒轮询一次
        )
        self.waterplant_max_age_minutes = self.config_manager.getint(
            'Waterplant', 'max_data_age_minutes', fallback=15   # 超过15分钟视为过期
        )

        # 先做一次连接测试
        if not self._waterplant_test_connection():
            self.logger.error(
                "水厂MySQL接收端连接测试失败，水厂数据读取功能将被禁用。"
                "请检查 config.ini 中 [Waterplant] 配置以及 MySQL 服务状态。"
            )
            return

        self.waterplant_enabled = True
        self.logger.info(
            f"水厂数据读取模块已启用 "
            f"(host={self.waterplant_config['host']}:{self.waterplant_config['port']}, "
            f"table={self.waterplant_table}, poll={self.waterplant_poll_interval}s)"
        )

        # 启动后台轮询线程
        self._start_waterplant_polling()

    def _waterplant_test_connection(self):
        """测试一次MySQL连接是否可用"""
        try:
            conn = pymysql.connect(**self.waterplant_config)
            with conn.cursor() as cur:
                cur.execute(f"SELECT 1 FROM {self.waterplant_table} LIMIT 1")
            conn.close()
            return True
        except Exception as e:
            self.logger.error(f"水厂MySQL连接测试失败: {e}")
            return False

    # ────────────────────────────────────────────────
    # 轮询线程
    # ────────────────────────────────────────────────
    def _start_waterplant_polling(self):
        """启动后台轮询线程"""
        self._waterplant_thread = threading.Thread(
            target=self._waterplant_poll_loop,
            daemon=True,
            name='WaterplantPoller'
        )
        self._waterplant_thread.start()

    def _waterplant_poll_loop(self):
        """轮询循环（每 poll_interval 秒执行一次）"""
        self.logger.info("水厂数据轮询线程已启动")
        while not self._waterplant_stop_event.is_set():
            try:
                self._waterplant_fetch_once()
            except Exception as e:
                self.logger.error(f"水厂数据轮询异常: {e}", exc_info=True)
                self.waterplant_consecutive_failures += 1

            # 可中断等待
            self._waterplant_stop_event.wait(self.waterplant_poll_interval)
        self.logger.info("水厂数据轮询线程已退出")

    def _waterplant_fetch_once(self):
        """执行一次数据读取"""
        # ── 第一阶段：连接 + 查询 ──────────────────────────
        conn = None
        row = None
        try:
            conn = pymysql.connect(**self.waterplant_config)
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(f"""
                    SELECT
                        record_time,
                        -- 加氯量：两路取平均（若一路为 NULL 则取另一路）
                        COALESCE(
                            (chlorine_dose_1 + chlorine_dose_2) / 2.0,
                            chlorine_dose_1,
                            chlorine_dose_2
                        ) AS chlorine_dose,
                        -- 原水浊度：两路取平均
                        COALESCE(
                            (raw_turbidity_1 + raw_turbidity_2) / 2.0,
                            raw_turbidity_1,
                            raw_turbidity_2
                        ) AS raw_turbidity,
                        -- 砂滤出水浊度：两路取平均
                        COALESCE(
                            (sand_filter_turbidity_1 + sand_filter_turbidity_2) / 2.0,
                            sand_filter_turbidity_1,
                            sand_filter_turbidity_2
                        ) AS sand_filter_turbidity,
                        -- GAC 出水浊度：仅一路仪表
                        gac_turbidity,
                        -- 出厂水浊度：两路取平均
                        COALESCE(
                            (effluent_turbidity_1 + effluent_turbidity_2) / 2.0,
                            effluent_turbidity_1,
                            effluent_turbidity_2
                        ) AS effluent_turbidity
                    FROM {self.waterplant_table}
                    ORDER BY record_time DESC
                    LIMIT 1
                """)
                row = cur.fetchone()
        except (pymysql.err.OperationalError, pymysql.err.InterfaceError) as e:
            # 连接类错误（MySQL 重启、网络抖动、空闲被服务器主动断开等），走降频日志
            self.waterplant_consecutive_failures += 1
            if self.waterplant_consecutive_failures <= 3:
                self.logger.error(f"水厂MySQL连接失败: {e}")
            elif self.waterplant_consecutive_failures % 20 == 0:
                self.logger.error(
                    f"水厂MySQL已连续 {self.waterplant_consecutive_failures} 次连接失败"
                )
            return
        except Exception as e:
            # 非连接类错误（SQL 语法错、字段不存在等），记一次完整日志即可
            self.waterplant_consecutive_failures += 1
            self.logger.error(f"水厂数据读取异常: {e}", exc_info=True)
            return
        finally:
            # 无论成功失败都确保连接关闭，避免连接泄漏
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

        # ── 第二阶段：数据处理 ────────────────────────────
        if row is None:
            self.logger.debug("水厂接收表中暂无数据")
            self.waterplant_consecutive_failures = 0   # 连接成功，清零失败计数
            return

        try:
            # 检查数据新鲜度（兼容字符串时间戳，并防御时钟差异导致的负值）
            record_time = row['record_time']
            if isinstance(record_time, str):
                record_time = datetime.strptime(record_time, '%Y-%m-%d %H:%M:%S')
            age_seconds = (datetime.now() - record_time).total_seconds()
            age_minutes = max(0.0, age_seconds / 60)   # 时钟差异保护
            row['_is_stale'] = age_minutes > self.waterplant_max_age_minutes
            if row['_is_stale']:
                self.logger.warning(
                    f"水厂数据过期: 最新记录 {record_time}，已过 {age_minutes:.1f} 分钟"
                )

            # 更新软件状态
            self.waterplant_latest = row
            self.waterplant_last_success_time = datetime.now()
            self.waterplant_consecutive_failures = 0

            # 核心：更新 current_chlorine_dosage 供报警逻辑使用
            new_dosage = row.get('chlorine_dose')
            if new_dosage is not None and not row['_is_stale']:
                self.current_chlorine_dosage = float(new_dosage)
                self.logger.debug(
                    f"已更新实际加氯量: {self.current_chlorine_dosage:.3f} mg/L "
                    f"(record_time={record_time})"
                )

            # 触发GUI刷新（通过队列安全地更新主线程UI）
            if hasattr(self, 'gui_update_queue'):
                self.gui_update_queue.put(self._update_actual_chlorine_label)
                if hasattr(self, 'update_waterplant_display'):
                    self.gui_update_queue.put(self.update_waterplant_display)

        except Exception as e:
            # 数据处理阶段的异常不影响连接状态，不计入连续失败
            self.logger.error(f"水厂数据处理异常: {e}", exc_info=True)

    def _update_actual_chlorine_label(self):
        """更新GUI上的'当前加氯量'标签（必须在主线程调用）"""
        try:
            if hasattr(self, 'actual_chlorine_label') and self.actual_chlorine_label.winfo_exists():
                label_text = self.get_text('actual_chlorine')
                is_stale = self.waterplant_latest and self.waterplant_latest.get('_is_stale')
                suffix = ' (⚠ 数据过期)' if is_stale else ''
                self.actual_chlorine_label.config(
                    text=f"{label_text}: {self.current_chlorine_dosage:.3f} mg/L{suffix}"
                )
        except Exception as e:
            self.logger.error(f"更新实际加氯量标签失败: {e}")

    # ────────────────────────────────────────────────
    # 对外查询接口（供其他模块调用）
    # ────────────────────────────────────────────────
    def get_waterplant_latest(self):
        """获取最近一次成功读取到的水厂数据（全部字段）

        Returns:
            dict or None: 包含 record_time, chlorine_dose, 各工艺浊度等字段；
                         若无可用数据或未启用本模块则返回None
        """
        if not self.waterplant_enabled:
            return None
        return self.waterplant_latest

    def get_waterplant_status(self):
        """获取水厂数据连接状态（供健康监控与UI展示）

        Returns:
            dict: 包含 enabled, last_success_time, consecutive_failures,
                  latest_dose, is_stale 五个字段。当尚无数据时，
                  latest_dose 为 None、is_stale 统一为 False。
        """
        latest = self.waterplant_latest
        return {
            'enabled': self.waterplant_enabled,
            'last_success_time': self.waterplant_last_success_time,
            'consecutive_failures': self.waterplant_consecutive_failures,
            'latest_dose': latest.get('chlorine_dose') if latest else None,
            'is_stale': bool(latest.get('_is_stale')) if latest else False,
        }

    def get_turbidity_removal_rates(self):
        """计算各工艺浊度去除率（基于最新水厂数据）

        Returns:
            dict or None: 如
                {
                    'sand_filter_removal': 85.2,  # 原水→砂滤出水 去除率(%)
                    'gac_removal':         92.1,  # 原水→GAC出水
                    'effluent_removal':    95.3,  # 原水→出厂水
                }
        """
        latest = self.get_waterplant_latest()
        if not latest:
            return None
        try:
            raw = latest.get('raw_turbidity')
            if raw is None or raw == 0:
                return None
            def removal(out):
                if out is None:
                    return None
                return max(0.0, min(100.0, (1 - out / raw) * 100))
            return {
                'sand_filter_removal': removal(latest.get('sand_filter_turbidity')),
                'gac_removal':         removal(latest.get('gac_turbidity')),
                'effluent_removal':    removal(latest.get('effluent_turbidity')),
            }
        except Exception as e:
            self.logger.error(f"浊度去除率计算失败: {e}")
            return None

    # ────────────────────────────────────────────────
    # 清理
    # ────────────────────────────────────────────────
    def stop_waterplant_reader(self):
        """停止水厂数据轮询（供 cleanup 流程调用）。
        
        对 init_waterplant_reader() 因配置问题提前 return 的情况做了健壮性保护，
        即使某些属性未被初始化也不会抛 AttributeError。
        """
        # 置位停止事件（若存在）
        stop_event = getattr(self, '_waterplant_stop_event', None)
        if stop_event is not None:
            stop_event.set()
        # 等待线程退出（若存在且在运行）
        thread = getattr(self, '_waterplant_thread', None)
        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)
            if hasattr(self, 'logger'):
                self.logger.info("水厂数据轮询线程已停止")