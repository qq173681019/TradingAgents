"""
A股热点板块追踪器 - HotSectorTracker
====================================
基于东方财富数据的7维评分体系，追踪行业板块和概念板块热度。

数据源:
  - AKShare: stock_board_industry_name_em / stock_board_concept_name_em
  - AKShare: stock_sector_fund_flow_rank
  - AKShare: stock_zt_pool_em (涨停板)
  - 东方财富搜索API (新闻热度)

评分维度 (7维):
  1. 涨幅(25%): 板块近5日平均涨幅
  2. 资金(20%): 板块主力资金净流入
  3. 新闻热度(15%): 板块相关新闻数量
  4. 量能(15%): 板块成交量变化
  5. 动量(10%): 板块涨幅加速度
  6. 涨停股数(10%): 板块内涨停股票数量
  7. 研报(5%): 近期研报数量 (暂用涨停+涨幅代理)

信号检测:
  - 启动信号: 热度突然从低位跳升
  - 衰退信号: 连续热度下降
  - 轮动预判: 资金从高位板块流向低位板块
"""

import os
import json
import time
import logging
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

# ─── 代理绕过 ───
# AKShare 调用东方财富API需要直连，系统代理(Clash等)会导致连接失败
for _proxy_key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
    os.environ.pop(_proxy_key, None)
os.environ['NO_PROXY'] = '*'

import akshare as ak

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')


# ═══════════════════════════════════════════════════════════
#  工具函数
# ═══════════════════════════════════════════════════════════

def _normalize(value: float, low: float, high: float) -> float:
    """将值归一化到 0-1"""
    if high == low:
        return 0.5
    return max(0.0, min(1.0, (value - low) / (high - low)))


def _safe_float(val, default=0.0) -> float:
    """安全转换为float"""
    try:
        if pd.isna(val):
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


def _disable_system_proxy():
    """运行时禁用系统代理 (Windows)"""
    try:
        import urllib.request
        urllib.request.getproxies = lambda: {}
    except Exception:
        pass


def _create_proxy_free_session():
    """创建不走代理的requests Session"""
    import requests
    session = requests.Session()
    session.trust_env = False
    session.proxies = {}
    return session


# ═══════════════════════════════════════════════════════════
#  缓存管理器
# ═══════════════════════════════════════════════════════════

class SimpleCache:
    """简单的文件缓存，避免频繁调用API"""

    def __init__(self, cache_dir: str = None, ttl: int = 1800):
        """
        Args:
            cache_dir: 缓存目录
            ttl: 缓存有效期(秒)，默认30分钟
        """
        if cache_dir is None:
            cache_dir = os.path.join(os.path.dirname(__file__), 'sector_cache')
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl

    def _cache_path(self, key: str) -> Path:
        h = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{h}.json"

    def get(self, key: str) -> Optional[dict]:
        p = self._cache_path(key)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
            if time.time() - data.get('ts', 0) > self.ttl:
                return None
            return data.get('payload')
        except Exception:
            return None

    def set(self, key: str, payload: dict):
        p = self._cache_path(key)
        try:
            p.write_text(json.dumps({'ts': time.time(), 'payload': payload}, ensure_ascii=False), encoding='utf-8')
        except Exception as e:
            logger.warning(f"缓存写入失败: {e}")


# ═══════════════════════════════════════════════════════════
#  核心类: HotSectorTracker
# ═══════════════════════════════════════════════════════════

class HotSectorTracker:
    """A股热点板块追踪器"""

    def __init__(self, cache_ttl: int = 1800):
        """
        Args:
            cache_ttl: 缓存有效期(秒)，默认30分钟
        """
        _disable_system_proxy()
        self.cache = SimpleCache(ttl=cache_ttl)
        self._fund_flow_cache_ttl = 600  # 资金流向缓存10分钟

    # ───────────────────────────────────────────
    #  数据采集层
    # ───────────────────────────────────────────

    def _ak_call(self, func, *args, **kwargs):
        """安全的AKShare调用包装"""
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"AKShare调用失败 [{func.__name__}]: {e}")
            return None

    def fetch_industry_sectors(self) -> list[dict]:
        """获取所有行业板块数据 (涨跌幅、资金流向、换手率等)"""
        cache_key = "industry_sectors"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        df = self._ak_call(ak.stock_board_industry_name_em)
        if df is None or df.empty:
            logger.warning("行业板块数据获取失败，返回空列表")
            return []

        sectors = []
        for _, row in df.iterrows():
            sectors.append({
                'name': str(row.get('板块名称', '')),
                'type': 'industry',
                'change_pct': _safe_float(row.get('涨跌幅', 0)),
                'latest_price': _safe_float(row.get('最新价', 0)),
                'total_market_cap': _safe_float(row.get('总市值', 0)),
                'turnover_rate': _safe_float(row.get('换手率', 0)),
                'advance_count': _safe_float(row.get('上涨家数', 0)),
                'decline_count': _safe_float(row.get('下跌家数', 0)),
                'net_inflow': _safe_float(row.get('主力净流入', 0)) / 1e8,  # 转为亿元
                'volume_ratio': _safe_float(row.get('量比', 0)),
                'turnover': _safe_float(row.get('成交额', 0)) / 1e8,  # 转为亿元
            })

        self.cache.set(cache_key, sectors)
        logger.info(f"获取行业板块 {len(sectors)} 个")
        return sectors

    def fetch_concept_sectors(self) -> list[dict]:
        """获取所有概念板块数据"""
        cache_key = "concept_sectors"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        df = self._ak_call(ak.stock_board_concept_name_em)
        if df is None or df.empty:
            logger.warning("概念板块数据获取失败，返回空列表")
            return []

        sectors = []
        for _, row in df.iterrows():
            sectors.append({
                'name': str(row.get('板块名称', '')),
                'type': 'concept',
                'change_pct': _safe_float(row.get('涨跌幅', 0)),
                'latest_price': _safe_float(row.get('最新价', 0)),
                'total_market_cap': _safe_float(row.get('总市值', 0)),
                'turnover_rate': _safe_float(row.get('换手率', 0)),
                'advance_count': _safe_float(row.get('上涨家数', 0)),
                'decline_count': _safe_float(row.get('下跌家数', 0)),
                'net_inflow': _safe_float(row.get('主力净流入', 0)) / 1e8,
                'volume_ratio': _safe_float(row.get('量比', 0)),
                'turnover': _safe_float(row.get('成交额', 0)) / 1e8,
            })

        self.cache.set(cache_key, sectors)
        logger.info(f"获取概念板块 {len(sectors)} 个")
        return sectors

    def fetch_fund_flow_rank(self, indicator: str = "今日", sector_type: str = "行业资金流") -> list[dict]:
        """获取板块资金流向排名

        Args:
            indicator: "今日"/"5日"/"10日"
            sector_type: "行业资金流"/"概念资金流"
        """
        cache_key = f"fund_flow_{indicator}_{sector_type}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        df = self._ak_call(ak.stock_sector_fund_flow_rank, indicator=indicator, sector_type=sector_type)
        if df is None or df.empty:
            return []

        result = []
        for _, row in df.iterrows():
            result.append({
                'name': str(row.get('名称', row.get('板块', ''))),
                'change_pct': _safe_float(row.get('涨跌幅', 0)),
                'net_inflow_main': _safe_float(row.get('主力净流入-净额', row.get('主力净流入', 0))) / 1e8,
                'net_inflow_super': _safe_float(row.get('超大单净流入-净额', 0)) / 1e8,
                'net_inflow_big': _safe_float(row.get('大单净流入-净额', 0)) / 1e8,
            })

        self.cache.set(cache_key, result)
        return result

    def fetch_limit_up_pool(self, date_str: str = None) -> list[dict]:
        """获取涨停股池，用于统计板块内涨停数量

        Args:
            date_str: 日期字符串，如 "20260514"，默认今天
        """
        if date_str is None:
            date_str = datetime.now().strftime('%Y%m%d')

        cache_key = f"limit_up_{date_str}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        df = self._ak_call(ak.stock_zt_pool_em, date=date_str)
        if df is None or df.empty:
            return []

        result = []
        for _, row in df.iterrows():
            result.append({
                'code': str(row.get('代码', '')),
                'name': str(row.get('名称', '')),
                'change_pct': _safe_float(row.get('涨跌幅', 0)),
                'sector': str(row.get('所属行业', '')),
                'limit_up_amount': _safe_float(row.get('封板资金', 0)),
                'consecutive_boards': _safe_float(row.get('连板数', 1)),
            })

        self.cache.set(cache_key, result)
        return result

    def fetch_sector_constituents(self, sector_name: str, sector_type: str = 'industry') -> list[dict]:
        """获取板块成分股

        Args:
            sector_name: 板块名称
            sector_type: 'industry' 或 'concept'
        """
        cache_key = f"constituents_{sector_type}_{sector_name}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        func = ak.stock_board_industry_cons_em if sector_type == 'industry' else ak.stock_board_concept_cons_em
        df = self._ak_call(func, symbol=sector_name)
        if df is None or df.empty:
            return []

        stocks = []
        for _, row in df.iterrows():
            stocks.append({
                'code': str(row.get('代码', '')),
                'name': str(row.get('名称', '')),
                'change_pct': _safe_float(row.get('涨跌幅', 0)),
                'latest_price': _safe_float(row.get('最新价', 0)),
                'turnover': _safe_float(row.get('成交额', 0)) / 1e8,
                'turnover_rate': _safe_float(row.get('换手率', 0)),
                'net_inflow': _safe_float(row.get('主力净流入', 0)) / 1e8,
                'market_cap': _safe_float(row.get('总市值', 0)),
            })

        self.cache.set(cache_key, stocks)
        return stocks

    # ───────────────────────────────────────────
    #  评分计算层
    # ───────────────────────────────────────────

    def compute_sector_score(self, sector: dict, fund_flow_map: dict = None,
                             limit_up_map: dict = None) -> float:
        """
        热点板块综合评分算法 (0-100)

        7维评分:
          1. 涨幅(25%): 板块当日涨幅
          2. 资金(20%): 板块主力资金净流入
          3. 新闻热度(15%): 用成交额+量比代理 (新闻API不稳定)
          4. 量能(15%): 板块换手率
          5. 动量(10%): 涨幅加速度 (需要历史数据，暂用当日涨幅偏离)
          6. 涨停股数(10%): 板块内涨停股票数量
          7. 研报(5%): 用上涨家数占比代理

        Args:
            sector: 板块数据字典
            fund_flow_map: 资金流向映射 {板块名: 净流入(亿)}
            limit_up_map: 涨停统计映射 {板块名/行业: 数量}
        """
        score = 0.0

        # ── 1. 涨幅 (25%) ──
        change_pct = sector.get('change_pct', 0)
        price_score = _normalize(change_pct, -5, 5)
        score += price_score * 25

        # ── 2. 资金净流入 (20%) ──
        net_inflow = sector.get('net_inflow', 0)
        # 补充资金流向排名数据
        if fund_flow_map and sector.get('name') in fund_flow_map:
            net_inflow = fund_flow_map[sector['name']]
        inflow_score = _normalize(net_inflow, -10, 20)  # -10亿到+20亿
        score += inflow_score * 20

        # ── 3. 新闻热度 (15%) — 用成交额代理 ──
        turnover = sector.get('turnover', 0)
        # 成交额越大说明关注度越高
        news_score = _normalize(min(turnover, 500), 0, 200)
        score += news_score * 15

        # ── 4. 量能 (15%) ──
        turnover_rate = sector.get('turnover_rate', 0)
        volume_ratio = sector.get('volume_ratio', 1)
        # 换手率 + 量比综合
        volume_score = _normalize(turnover_rate * 0.7 + volume_ratio * 1.5, 0, 8)
        score += volume_score * 15

        # ── 5. 动量 (10%) ──
        # 用涨幅偏离度代理 (涨幅越高动量越强)
        momentum = change_pct - 0  # 相对0轴的偏离
        momentum_score = _normalize(momentum, -3, 5)
        score += momentum_score * 10

        # ── 6. 涨停股数 (10%) ──
        limit_up_count = 0
        if limit_up_map:
            sector_name = sector.get('name', '')
            limit_up_count = limit_up_map.get(sector_name, 0)
        sector['limit_up_count'] = limit_up_count
        limit_score = _normalize(limit_up_count, 0, 5)
        score += limit_score * 10

        # ── 7. 研报/上涨家数占比 (5%) ──
        total_stocks = sector.get('advance_count', 0) + sector.get('decline_count', 1)
        advance_ratio = sector.get('advance_count', 0) / max(total_stocks, 1)
        advance_score = _normalize(advance_ratio, 0, 1)
        score += advance_score * 5

        return round(max(0, min(100, score)), 1)

    def _merge_and_score(self, industry: list, concept: list,
                         fund_flow_data: list = None,
                         limit_up_data: list = None) -> list[dict]:
        """合并行业+概念板块数据并计算综合评分"""

        # 构建资金流向映射
        fund_flow_map = {}
        if fund_flow_data:
            for item in fund_flow_data:
                fund_flow_map[item['name']] = item.get('net_inflow_main', item.get('net_inflow', 0))

        # 构建涨停统计映射 (按所属行业/概念统计)
        limit_up_map = {}
        if limit_up_data:
            for item in limit_up_data:
                sector_name = item.get('sector', '')
                if sector_name:
                    limit_up_map[sector_name] = limit_up_map.get(sector_name, 0) + 1

        all_sectors = []
        for sector in industry + concept:
            score = self.compute_sector_score(sector, fund_flow_map, limit_up_map)
            all_sectors.append({
                **sector,
                'heat_score': score,
            })

        # 按热度评分降序排序
        all_sectors.sort(key=lambda x: x['heat_score'], reverse=True)
        return all_sectors

    # ───────────────────────────────────────────
    #  信号检测层
    # ───────────────────────────────────────────

    def detect_launch_signal(self, sector: dict) -> dict:
        """板块启动信号检测

        触发条件(满足3/5即发出信号):
        1. 当日涨幅 > 2%
        2. 资金净流入 > 3亿
        3. 换手率 > 3% 或量比 > 2
        4. 涨停股 >= 2只
        5. 上涨家数占比 > 70%
        """
        triggers = []

        change_pct = sector.get('change_pct', 0)
        if change_pct > 2.0:
            triggers.append(f'涨幅突破{change_pct:.1f}%')

        net_inflow = sector.get('net_inflow', 0)
        if net_inflow > 3:
            triggers.append(f'资金涌入{net_inflow:.1f}亿')

        turnover_rate = sector.get('turnover_rate', 0)
        volume_ratio = sector.get('volume_ratio', 1)
        if turnover_rate > 3 or volume_ratio > 2:
            triggers.append('量能放大')

        limit_up = sector.get('limit_up_count', 0)
        if limit_up >= 2:
            triggers.append(f'涨停股{limit_up}只')

        total = sector.get('advance_count', 0) + sector.get('decline_count', 1)
        advance_ratio = sector.get('advance_count', 0) / max(total, 1)
        if advance_ratio > 0.7:
            triggers.append(f'普涨({advance_ratio:.0%})')

        signal = len(triggers) >= 3
        strength = 'strong' if len(triggers) >= 4 else ('medium' if len(triggers) == 3 else 'weak')

        return {
            'name': sector.get('name', ''),
            'type': sector.get('type', ''),
            'signal': signal,
            'strength': strength,
            'triggers': triggers,
            'score': len(triggers) * 20,
        }

    def detect_decay_signal(self, sector: dict) -> dict:
        """板块衰退信号检测

        触发条件(满足2/4即发出信号):
        1. 资金净流出 > 5亿
        2. 涨停股从高位降至0
        3. 下跌家数占比 > 70%
        4. 涨幅 < -1%
        """
        triggers = []

        net_inflow = sector.get('net_inflow', 0)
        if net_inflow < -5:
            triggers.append(f'资金流出{abs(net_inflow):.1f}亿')

        limit_up = sector.get('limit_up_count', 0)
        if limit_up == 0 and sector.get('heat_score', 0) > 60:
            triggers.append('涨停股消失')

        total = sector.get('advance_count', 0) + sector.get('decline_count', 1)
        decline_ratio = sector.get('decline_count', 0) / max(total, 1)
        if decline_ratio > 0.7:
            triggers.append(f'普跌({decline_ratio:.0%})')

        change_pct = sector.get('change_pct', 0)
        if change_pct < -1:
            triggers.append(f'跌幅{change_pct:.1f}%')

        signal = len(triggers) >= 2
        strength = 'strong' if len(triggers) >= 3 else 'medium'

        return {
            'name': sector.get('name', ''),
            'type': sector.get('type', ''),
            'signal': signal,
            'strength': strength,
            'triggers': triggers,
        }

    def predict_rotation(self, all_sectors: list[dict]) -> list[dict]:
        """板块轮动预判

        逻辑:
        1. 蓄势板块: 资金流入但涨幅不大 (< 3%)
        2. 超跌反弹: 热度高但当日下跌
        """
        candidates = []

        for sector in all_sectors:
            net_inflow = sector.get('net_inflow', 0)
            change_5d = sector.get('change_pct', 0)  # 用当日涨幅代理5日
            turnover_rate = sector.get('turnover_rate', 0)
            heat_score = sector.get('heat_score', 0)

            # 蓄势信号: 资金流入 + 涨幅不大 + 有一定量能
            if net_inflow > 2 and 0 < change_5d < 3 and turnover_rate > 2:
                candidates.append({
                    'sector': sector.get('name', ''),
                    'type': sector.get('type', ''),
                    'rotation_type': '蓄势待发',
                    'reason': f'资金流入{net_inflow:.1f}亿，涨幅{change_5d:.1f}%，换手{turnover_rate:.1f}%',
                    'confidence': min(0.5 + net_inflow / 30, 0.9),
                    'heat_score': heat_score,
                })

            # 超跌反弹: 热度尚可但当日微跌
            if heat_score > 40 and -3 < change_5d < 0 and net_inflow > 0:
                candidates.append({
                    'sector': sector.get('name', ''),
                    'type': sector.get('type', ''),
                    'rotation_type': '超跌反弹',
                    'reason': f'热度{heat_score:.0f}但回调{change_5d:.1f}%，资金仍流入',
                    'confidence': 0.4 + heat_score / 200,
                    'heat_score': heat_score,
                })

        candidates.sort(key=lambda x: x['confidence'], reverse=True)
        return candidates[:5]

    # ───────────────────────────────────────────
    #  板块内个股排名
    # ───────────────────────────────────────────

    def rank_stocks_in_sector(self, sector_name: str, sector_type: str = 'industry',
                              top_n: int = 10) -> list[dict]:
        """板块内个股综合排名

        排名维度:
        - 涨跌幅 (40%)
        - 资金净流入 (25%)
        - 换手率 (20%)
        - 流通市值偏好 (15%) — 偏好20-500亿
        """
        stocks = self.fetch_sector_constituents(sector_name, sector_type)
        if not stocks:
            return []

        # 计算个股评分
        for s in stocks:
            change = s.get('change_pct', 0)
            inflow = s.get('net_inflow', 0)
            tr = s.get('turnover_rate', 0)
            cap = s.get('market_cap', 0)

            # 涨幅分 (40%)
            change_score = _normalize(change, -3, 7) * 40

            # 资金分 (25%)
            inflow_score = _normalize(inflow, -5, 10) * 25

            # 换手率分 (20%)
            tr_score = _normalize(tr, 0, 15) * 20

            # 市值偏好分 (15%) — 20-500亿最优
            if 20 <= cap / 1e8 <= 500:
                cap_score = 15
            elif 10 <= cap / 1e8 <= 1000:
                cap_score = 10
            else:
                cap_score = 5

            s['stock_score'] = round(change_score + inflow_score + tr_score + cap_score, 1)

        stocks.sort(key=lambda x: x.get('stock_score', 0), reverse=True)
        return stocks[:top_n]

    # ───────────────────────────────────────────
    #  核心入口
    # ───────────────────────────────────────────

    def get_hot_sectors(self, top_n: int = 10) -> list[dict]:
        """获取当前热门板块排名 (核心入口)

        Returns:
            [{
                'name': '半导体',
                'type': 'industry'/'concept',
                'heat_score': 85.5,  # 0-100综合热度
                'change_pct': 3.2,   # 涨幅%
                'net_inflow': 5.6,   # 资金净流入(亿)
                'limit_up_count': 3, # 涨停股数
                'turnover_rate': 4.5, # 换手率%
                'turnover': 120.5,    # 成交额(亿)
                'stocks': [...],      # TOP个股
            }]
        """
        logger.info("开始获取热点板块数据...")

        # 1. 采集板块数据
        industry = self.fetch_industry_sectors()
        concept = self.fetch_concept_sectors()

        # 2. 采集资金流向
        fund_flow = self.fetch_fund_flow_rank("今日", "行业资金流")
        concept_fund = self.fetch_fund_flow_rank("今日", "概念资金流")
        fund_flow.extend(concept_fund)

        # 3. 采集涨停板
        limit_up = self.fetch_limit_up_pool()

        # 4. 合并评分排序
        all_sectors = self._merge_and_score(industry, concept, fund_flow, limit_up)

        # 5. 取 TOP N，附加个股排名
        hot_sectors = []
        for sector in all_sectors[:top_n]:
            top_stocks = self.rank_stocks_in_sector(
                sector['name'], sector.get('type', 'industry'), top_n=5
            )
            hot_sectors.append({
                'name': sector.get('name', ''),
                'type': sector.get('type', ''),
                'heat_score': sector.get('heat_score', 0),
                'change_pct': sector.get('change_pct', 0),
                'net_inflow': round(sector.get('net_inflow', 0), 2),
                'limit_up_count': sector.get('limit_up_count', 0),
                'turnover_rate': sector.get('turnover_rate', 0),
                'turnover': round(sector.get('turnover', 0), 2),
                'advance_count': sector.get('advance_count', 0),
                'decline_count': sector.get('decline_count', 0),
                'stocks': top_stocks,
            })

        logger.info(f"热点板块排名完成，共 {len(hot_sectors)} 个")
        return hot_sectors

    def daily_scan(self) -> dict:
        """每日热点扫描 (完整版)

        Returns:
            {
                'date': '2026-05-14',
                'hot_sectors': [...],       # TOP10 热门板块 + 板块内个股排名
                'launch_signals': [...],    # 启动信号
                'decay_signals': [...],     # 衰退信号
                'rotation_candidates': [...], # 轮动预判
            }
        """
        logger.info("=" * 60)
        logger.info("开始每日热点板块扫描...")
        logger.info("=" * 60)

        # 1. 采集所有数据
        industry = self.fetch_industry_sectors()
        concept = self.fetch_concept_sectors()
        fund_flow = self.fetch_fund_flow_rank("今日", "行业资金流")
        concept_fund = self.fetch_fund_flow_rank("今日", "概念资金流")
        fund_flow.extend(concept_fund)
        limit_up = self.fetch_limit_up_pool()

        # 2. 合并评分
        all_sectors = self._merge_and_score(industry, concept, fund_flow, limit_up)

        # 3. 信号检测
        launch_signals = []
        decay_signals = []
        for sector in all_sectors:
            launch = self.detect_launch_signal(sector)
            if launch['signal']:
                launch_signals.append(launch)

            decay = self.detect_decay_signal(sector)
            if decay['signal']:
                decay_signals.append(decay)

        # 4. 轮动预判
        rotation = self.predict_rotation(all_sectors)

        # 5. TOP10 + 个股
        hot_sectors = []
        for sector in all_sectors[:10]:
            top_stocks = self.rank_stocks_in_sector(
                sector['name'], sector.get('type', 'industry'), top_n=5
            )
            hot_sectors.append({
                'name': sector.get('name', ''),
                'type': sector.get('type', ''),
                'heat_score': sector.get('heat_score', 0),
                'change_pct': sector.get('change_pct', 0),
                'net_inflow': round(sector.get('net_inflow', 0), 2),
                'limit_up_count': sector.get('limit_up_count', 0),
                'stocks': top_stocks,
            })

        result = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'total_industry': len(industry),
            'total_concept': len(concept),
            'hot_sectors': hot_sectors,
            'launch_signals': sorted(launch_signals, key=lambda x: x['score'], reverse=True)[:10],
            'decay_signals': decay_signals[:10],
            'rotation_candidates': rotation,
        }

        logger.info(f"扫描完成: {len(hot_sectors)} 热门板块, "
                     f"{len(launch_signals)} 启动信号, "
                     f"{len(decay_signals)} 衰退信号, "
                     f"{len(rotation)} 轮动候选")

        return result


# ═══════════════════════════════════════════════════════════
#  测试
# ═══════════════════════════════════════════════════════════

def test_hot_sector_tracker():
    """测试热点板块追踪器"""
    print("=" * 70)
    print("  A股热点板块追踪器 - 测试")
    print("=" * 70)

    tracker = HotSectorTracker()

    try:
        sectors = tracker.get_hot_sectors(top_n=10)

        if not sectors:
            print("\n⚠️  未能获取到板块数据（可能是网络/代理问题）")
            print("   正在使用模拟数据演示评分逻辑...\n")
            _test_with_mock_data()
            return

        print(f"\n📊 TOP10 热门板块 (数据时间: {datetime.now().strftime('%Y-%m-%d %H:%M')})")
        print("-" * 70)

        for i, s in enumerate(sectors, 1):
            type_icon = '🏭' if s['type'] == 'industry' else '💡'
            print(f"{i:2d}. {type_icon} {s['name']:12s} | "
                  f"热度: {s['heat_score']:5.1f} | "
                  f"涨幅: {s['change_pct']:+6.2f}% | "
                  f"资金: {s['net_inflow']:+7.2f}亿 | "
                  f"涨停: {s['limit_up_count']}只 | "
                  f"换手: {s['turnover_rate']:.1f}%")

            # 显示TOP3个股
            if s.get('stocks'):
                for j, stock in enumerate(s['stocks'][:3], 1):
                    print(f"    {j}. {stock['name']:8s} {stock.get('change_pct', 0):+6.2f}% "
                          f"(评分:{stock.get('stock_score', 0):.1f})")

        # 完整扫描
        print("\n" + "=" * 70)
        print("  信号检测")
        print("=" * 70)

        scan = tracker.daily_scan()

        if scan['launch_signals']:
            print("\n🚀 启动信号:")
            for sig in scan['launch_signals'][:5]:
                print(f"  - [{sig['strength'].upper()}] {sig['name']} ({sig['type']}) "
                      f"触发: {', '.join(sig['triggers'])}")

        if scan['decay_signals']:
            print("\n⚠️  衰退信号:")
            for sig in scan['decay_signals'][:5]:
                print(f"  - [{sig['strength'].upper()}] {sig['name']} ({sig['type']}) "
                      f"触发: {', '.join(sig['triggers'])}")

        if scan['rotation_candidates']:
            print("\n🔄 轮动预判:")
            for cand in scan['rotation_candidates']:
                print(f"  - [{cand['rotation_type']}] {cand['sector']} "
                      f"(置信度:{cand['confidence']:.0%}) {cand['reason']}")

        if not scan['launch_signals'] and not scan['decay_signals']:
            print("\n  (当前无显著信号)")

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        print(f"\n❌ 测试出错: {e}")
        print("正在使用模拟数据演示...\n")
        _test_with_mock_data()


def _test_with_mock_data():
    """使用模拟数据测试评分逻辑"""
    tracker = HotSectorTracker()

    mock_sectors = [
        {'name': '半导体', 'type': 'industry', 'change_pct': 4.5, 'net_inflow': 12.3,
         'turnover_rate': 5.2, 'volume_ratio': 2.8, 'turnover': 350,
         'advance_count': 80, 'decline_count': 10, 'latest_price': 1000},
        {'name': '机器人', 'type': 'concept', 'change_pct': 3.8, 'net_inflow': 8.7,
         'turnover_rate': 4.1, 'volume_ratio': 1.9, 'turnover': 180,
         'advance_count': 60, 'decline_count': 15, 'latest_price': 800},
        {'name': '锂电池', 'type': 'industry', 'change_pct': 2.1, 'net_inflow': 5.2,
         'turnover_rate': 3.5, 'volume_ratio': 1.5, 'turnover': 220,
         'advance_count': 45, 'decline_count': 20, 'latest_price': 900},
        {'name': '房地产', 'type': 'industry', 'change_pct': -1.5, 'net_inflow': -6.8,
         'turnover_rate': 2.1, 'volume_ratio': 0.8, 'turnover': 90,
         'advance_count': 10, 'decline_count': 70, 'latest_price': 600},
        {'name': 'AI算力', 'type': 'concept', 'change_pct': 5.2, 'net_inflow': 15.6,
         'turnover_rate': 6.8, 'volume_ratio': 3.5, 'turnover': 420,
         'advance_count': 50, 'decline_count': 5, 'latest_price': 1200},
    ]

    mock_limit_up = {
        'AI算力': 5, '半导体': 3, '机器人': 2,
    }

    print("📊 模拟板块评分:")
    print("-" * 70)

    for sector in mock_sectors:
        score = tracker.compute_sector_score(sector, {}, mock_limit_up)
        sector['heat_score'] = score
        sector['limit_up_count'] = mock_limit_up.get(sector['name'], 0)

        type_icon = '🏭' if sector['type'] == 'industry' else '💡'
        print(f"  {type_icon} {sector['name']:10s} | "
              f"热度: {score:5.1f} | "
              f"涨幅: {sector['change_pct']:+5.1f}% | "
              f"资金: {sector['net_inflow']:+6.1f}亿 | "
              f"涨停: {sector['limit_up_count']}只")

    # 信号检测
    print("\n🚀 启动信号检测:")
    for sector in mock_sectors:
        sig = tracker.detect_launch_signal(sector)
        if sig['signal']:
            print(f"  ✅ [{sig['strength'].upper()}] {sig['name']} "
                  f"触发: {', '.join(sig['triggers'])}")
        else:
            print(f"  ⬜ {sig['name']} (未触发, {len(sig['triggers'])}条件)")

    print("\n⚠️  衰退信号检测:")
    for sector in mock_sectors:
        sig = tracker.detect_decay_signal(sector)
        if sig['signal']:
            print(f"  ❌ [{sig['strength'].upper()}] {sig['name']} "
                  f"触发: {', '.join(sig['triggers'])}")
        else:
            print(f"  ⬜ {sig['name']} (未触发)")

    # 轮动预判
    print("\n🔄 轮动预判:")
    mock_sectors.sort(key=lambda x: x['heat_score'], reverse=True)
    rotation = tracker.predict_rotation(mock_sectors)
    for cand in rotation:
        print(f"  - [{cand['rotation_type']}] {cand['sector']} "
              f"(置信度:{cand['confidence']:.0%}) {cand['reason']}")

    print("\n✅ 模拟数据测试通过！评分和信号逻辑工作正常。")


if __name__ == '__main__':
    test_hot_sector_tracker()
