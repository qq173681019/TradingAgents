"""
新数据源接入模块 - TradingAgent 增量信号
=========================================
数据源:
  a) 北向资金净流入 (沪深股通)
  b) 个股资金流向 (主力净流入)
  c) 龙虎榜数据
  d) 融资融券余额
  e) 涨停/跌停统计

所有数据通过 akshare 免费接口获取。
"""

import json
import os
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

import akshare as ak
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# 数据缓存目录
DATA_DIR = Path(r"D:\GitHub\TradingAgents\TradingShared\data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

CACHE_FILE = DATA_DIR / "new_factors_cache.json"


# ---------------------------------------------------------------------------
# 辅助工具
# ---------------------------------------------------------------------------

def _date_str(date: str | datetime, fmt: str = "%Y%m%d") -> str:
    """统一日期格式化。"""
    if isinstance(date, datetime):
        return date.strftime(fmt)
    return date.replace("-", "")


def _date_hyphen(date: str | datetime) -> str:
    """返回 YYYY-MM-DD 格式。"""
    if isinstance(date, datetime):
        return date.strftime("%Y-%m-%d")
    if len(date) == 8:
        return f"{date[:4]}-{date[4:6]}-{date[6:8]}"
    return date


def _safe_float(val) -> float | None:
    """安全转换为 float，失败返回 None。"""
    try:
        if pd.isna(val):
            return None
        return float(val)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# a) 北向资金
# ---------------------------------------------------------------------------

def fetch_north_flow(date: str | datetime) -> float | None:
    """
    获取北向资金净流入（亿元）。
    通过 stock_hsgt_fund_flow_summary_em 获取当日汇总。
    """
    date_str = _date_hyphen(date)
    try:
        df = ak.stock_hsgt_fund_flow_summary_em()
        # 筛选北向数据
        north = df[df["资金方向"] == "北向"]
        if north.empty:
            logger.warning(f"[north_flow] 无北向数据: {date_str}")
            return None

        # 汇总沪股通 + 深股通的成交净买额
        total = north["成交净买额"].sum()
        result = _safe_float(total)
        if result is not None:
            result = round(result, 4)
        logger.info(f"[north_flow] {date_str}: {result} 亿")
        return result
    except Exception as e:
        logger.error(f"[north_flow] {date_str} 获取失败: {e}")
        return None


def fetch_north_flow_hist() -> dict:
    """
    获取市场整体主力资金流向历史数据（替代北向资金）。
    stock_hsgt_hist_em 近期数据全为 NaN，改用 stock_market_fund_flow 获取
    全市场主力/超大单/大单净流入数据。

    返回: {date_str: {
        'main_net_inflow': float,  # 主力净流入(亿元)
        'super_large_net': float,  # 超大单净流入
        'large_net': float,        # 大单净流入
        'small_net': float,        # 小单净流入
    }}
    """
    result = {}
    try:
        df = ak.stock_market_fund_flow()
        for _, row in df.iterrows():
            raw_date = row["日期"]
            if hasattr(raw_date, "strftime"):
                d = raw_date.strftime("%Y-%m-%d")
            else:
                d = str(raw_date)
                if len(d) == 8:
                    d = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
            # 主力净流入(元) -> 亿元
            main_net = _safe_float(row.get("主力净流入-净额"))
            super_net = _safe_float(row.get("超大单净流入-净额"))
            large_net = _safe_float(row.get("大单净流入-净额"))
            small_net = _safe_float(row.get("小单净流入-净额"))

            if main_net is not None:
                result[d] = {
                    "main_net_inflow": round(main_net / 1e8, 4),
                    "super_large_net": round(super_net / 1e8, 4) if super_net else None,
                    "large_net": round(large_net / 1e8, 4) if large_net else None,
                    "small_net": round(small_net / 1e8, 4) if small_net else None,
                }
    except Exception as e:
        logger.error(f"[market_fund_flow_hist] 获取失败: {e}")

    logger.info(f"[market_fund_flow_hist] 获取 {len(result)} 天数据")
    return result


# ---------------------------------------------------------------------------
# b) 个股资金流向
# ---------------------------------------------------------------------------

def fetch_money_flow(code: str, date: str | datetime = None) -> dict:
    """
    获取个股资金流向。
    code: 6位股票代码 如 '000001'
    date: 可选，若不传则用 stock_individual_fund_flow 获取历史序列

    返回: {
        'code': str,
        'main_net_inflow': float,  # 主力净流入(元)
        'super_large_net': float,  # 超大单净流入
        'large_net': float,        # 大单净流入
        'date': str
    }
    """
    # 判断市场
    market = "sh" if code.startswith(("6", "5")) else "sz"

    try:
        df = ak.stock_individual_fund_flow(stock=code, market=market)
        if date is not None:
            target = _date_hyphen(date)
            row = df[df["日期"] == target]
            if row.empty:
                # 尝试用 YYYYMMDD 格式匹配
                target2 = _date_str(date)
                row = df[df["日期"] == target2]
            if row.empty:
                logger.warning(f"[money_flow] {code} 无 {target} 数据")
                return {"code": code, "main_net_inflow": None, "date": str(date)}
            row = row.iloc[0]
        else:
            row = df.iloc[-1]  # 最新一天

        result = {
            "code": code,
            "main_net_inflow": _safe_float(row.get("主力净流入-净额")),
            "super_large_net": _safe_float(row.get("超大单净流入-净额")),
            "large_net": _safe_float(row.get("大单净流入-净额")),
            "date": str(row.get("日期", "")),
        }
        return result
    except Exception as e:
        logger.error(f"[money_flow] {code} 获取失败: {e}")
        return {"code": code, "main_net_inflow": None, "error": str(e)}


def fetch_money_flow_rank(indicator: str = "今日") -> pd.DataFrame:
    """
    获取个股资金流向排名。
    indicator: '今日' / '3日' / '5日' / '10日'
    """
    try:
        df = ak.stock_individual_fund_flow_rank(indicator=indicator)
        return df
    except Exception as e:
        logger.error(f"[money_flow_rank] 获取失败: {e}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# c) 龙虎榜
# ---------------------------------------------------------------------------

def fetch_lhb(start_date: str, end_date: str = None) -> list:
    """
    获取龙虎榜数据。
    start_date / end_date: 'YYYYMMDD' 或 'YYYY-MM-DD'
    返回: list of dict
    """
    if end_date is None:
        end_date = start_date

    sd = _date_str(start_date)
    ed = _date_str(end_date)

    try:
        df = ak.stock_lhb_detail_em(start_date=sd, end_date=ed)
        if df.empty:
            return []

        records = []
        for _, row in df.iterrows():
            records.append({
                "code": str(row.get("代码", "")),
                "name": str(row.get("名称", "")),
                "date": str(row.get("上榜日", "")),
                "reason": str(row.get("上榜原因", "")),
                "net_buy": _safe_float(row.get("龙虎榜净买额")),
                "buy_amount": _safe_float(row.get("龙虎榜买入额")),
                "sell_amount": _safe_float(row.get("龙虎榜卖出额")),
                "close_price": _safe_float(row.get("收盘价")),
                "change_pct": _safe_float(row.get("涨跌幅")),
                "interpret": str(row.get("解读", "")),
            })
        logger.info(f"[lhb] {sd}~{ed}: {len(records)} 条记录")
        return records
    except Exception as e:
        logger.error(f"[lhb] {sd}~{ed} 获取失败: {e}")
        return []


# ---------------------------------------------------------------------------
# d) 融资融券
# ---------------------------------------------------------------------------

def fetch_margin(code: str, date: str | datetime) -> dict:
    """
    获取个股融资融券余额。
    自动判断沪市/深市，分别调用对应接口。
    code: 6位股票代码
    date: 日期

    返回: {
        'code': str,
        'margin_balance': float,  # 融资余额
        'margin_buy': float,      # 融资买入额
        'short_balance': float,   # 融券余额/融券余量
        'total_balance': float,   # 融资融券余额
        'date': str
    }
    """
    d = _date_str(date)
    result = {"code": code, "date": str(date)}

    try:
        if code.startswith(("6", "5")):
            # 沪市
            df = ak.stock_margin_detail_sse(date=d)
            row = df[df["标的证券代码"] == code]
            if row.empty:
                logger.warning(f"[margin] 沪市 {code} 无 {d} 数据")
                return result
            row = row.iloc[0]
            result.update({
                "margin_balance": _safe_float(row.get("融资余额")),
                "margin_buy": _safe_float(row.get("融资买入额")),
                "margin_repay": _safe_float(row.get("融资偿还额")),
                "short_volume": _safe_float(row.get("融券余量")),
                "short_sell": _safe_float(row.get("融券卖出量")),
                "total_balance": _safe_float(row.get("融资余额")),  # 沪市无总额字段
            })
        else:
            # 深市
            df = ak.stock_margin_detail_szse(date=d)
            row = df[df["证券代码"] == code]
            if row.empty:
                logger.warning(f"[margin] 深市 {code} 无 {d} 数据")
                return result
            row = row.iloc[0]
            result.update({
                "margin_balance": _safe_float(row.get("融资余额")),
                "margin_buy": _safe_float(row.get("融资买入额")),
                "short_volume": _safe_float(row.get("融券余量")),
                "short_balance": _safe_float(row.get("融券余额")),
                "total_balance": _safe_float(row.get("融资融券余额")),
            })
        return result
    except Exception as e:
        logger.error(f"[margin] {code} {d} 获取失败: {e}")
        result["error"] = str(e)
        return result


def fetch_margin_daily(date: str | datetime) -> dict:
    """
    获取某日全市场融资融券汇总。
    返回: {code: {margin_balance, total_balance, ...}}
    """
    d = _date_str(date)
    result = {}

    # 沪市
    try:
        df = ak.stock_margin_detail_sse(date=d)
        for _, row in df.iterrows():
            code = str(row.get("标的证券代码", ""))
            if not code or len(code) != 6:
                continue
            result[code] = {
                "margin_balance": _safe_float(row.get("融资余额")),
                "margin_buy": _safe_float(row.get("融资买入额")),
            }
    except Exception as e:
        logger.error(f"[margin_daily] 沪市 {d} 失败: {e}")

    time.sleep(0.5)

    # 深市
    try:
        df = ak.stock_margin_detail_szse(date=d)
        for _, row in df.iterrows():
            code = str(row.get("证券代码", ""))
            if not code or len(code) != 6:
                continue
            result[code] = {
                "margin_balance": _safe_float(row.get("融资余额")),
                "margin_buy": _safe_float(row.get("融资买入额")),
                "total_balance": _safe_float(row.get("融资融券余额")),
            }
    except Exception as e:
        logger.error(f"[margin_daily] 深市 {d} 失败: {e}")

    logger.info(f"[margin_daily] {d}: {len(result)} 只股票")
    return result


# ---------------------------------------------------------------------------
# e) 涨停/跌停统计
# ---------------------------------------------------------------------------

def fetch_limit_stats(date: str | datetime) -> dict:
    """
    获取涨停/跌停统计。
    返回: {
        'zt_count': int,          # 涨停数量
        'dt_count': int,          # 跌停数量
        'zt_stocks': [...],       # 涨停股票列表
        'dt_stocks': [...],       # 跌停股票列表
        'zt_industries': {...},   # 涨停行业分布
        'dt_industries': {...},   # 跌停行业分布
        'date': str
    }
    """
    d = _date_str(date)
    result = {"date": str(date), "zt_count": 0, "dt_count": 0, "zt_stocks": [], "dt_stocks": [],
              "zt_industries": {}, "dt_industries": {}}

    # 涨停池
    try:
        df = ak.stock_zt_pool_em(date=d)
        if not df.empty:
            result["zt_count"] = len(df)
            result["zt_stocks"] = [
                {"code": str(r["代码"]), "name": str(r["名称"]),
                 "change_pct": _safe_float(r.get("涨跌幅")),
                 "industry": str(r.get("所属行业", "")),
                 "consecutive": _safe_float(r.get("连板数"))}
                for _, r in df.iterrows()
            ]
            # 行业统计
            if "所属行业" in df.columns:
                ind_counts = df["所属行业"].value_counts().head(10).to_dict()
                result["zt_industries"] = {str(k): int(v) for k, v in ind_counts.items()}
    except Exception as e:
        logger.error(f"[limit_stats] 涨停 {d} 失败: {e}")

    time.sleep(0.3)

    # 跌停池
    try:
        df = ak.stock_zt_pool_dtgc_em(date=d)
        if not df.empty:
            result["dt_count"] = len(df)
            result["dt_stocks"] = [
                {"code": str(r["代码"]), "name": str(r["名称"]),
                 "change_pct": _safe_float(r.get("涨跌幅")),
                 "industry": str(r.get("所属行业", ""))}
                for _, r in df.iterrows()
            ]
            if "所属行业" in df.columns:
                ind_counts = df["所属行业"].value_counts().head(10).to_dict()
                result["dt_industries"] = {str(k): int(v) for k, v in ind_counts.items()}
    except Exception as e:
        logger.error(f"[limit_stats] 跌停 {d} 失败: {e}")

    logger.info(f"[limit_stats] {d}: 涨停 {result['zt_count']}, 跌停 {result['dt_count']}")
    return result


# ---------------------------------------------------------------------------
# 批量采集
# ---------------------------------------------------------------------------

def fetch_all_new_data(start: str, end: str) -> dict:
    """
    批量采集 [start, end] 区间内的所有新数据源数据。
    start / end: 'YYYY-MM-DD' 或 'YYYYMMDD'
    保存到 new_factors_cache.json
    """
    start_dt = datetime.strptime(_date_str(start), "%Y%m%d")
    end_dt = datetime.strptime(_date_str(end), "%Y%m%d")

    all_dates = []
    cur = start_dt
    while cur <= end_dt:
        # 只取工作日（简单排除周末，节假日不处理由 akshare 自动返回空）
        if cur.weekday() < 5:
            all_dates.append(cur)
        cur += timedelta(days=1)

    logger.info(f"开始批量采集 {start_dt.date()} ~ {end_dt.date()}, 共 {len(all_dates)} 个工作日")

    cache = {
        "meta": {
            "start": str(start_dt.date()),
            "end": str(end_dt.date()),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_dates": len(all_dates),
        },
        "north_flow": {},        # date -> net_inflow(亿)
        "lhb": {},               # date -> [records]
        "limit_stats": {},       # date -> {zt_count, dt_count, ...}
        "margin_daily": {},      # date -> {code: {...}}
        "errors": [],
        "stats": {"success": 0, "fail": 0},
    }

    # 1) 市场资金流向（含主力/超大单/大单） - 用历史接口一次性获取
    logger.info(">>> 采集市场整体资金流向历史数据...")
    try:
        fund_hist = fetch_north_flow_hist()
        # 只保留目标区间
        for d in all_dates:
            key = d.strftime("%Y-%m-%d")
            if key in fund_hist:
                cache["north_flow"][key] = fund_hist[key]
        logger.info(f"市场资金流向: 匹配到 {len(cache['north_flow'])} 天")
    except Exception as e:
        cache["errors"].append(f"market_fund_flow_hist: {e}")
        logger.error(f"市场资金流向采集失败: {e}")

    # 2) 按日采集龙虎榜、涨停跌停
    for i, d in enumerate(all_dates):
        ds = d.strftime("%Y%m%d")
        dh = d.strftime("%Y-%m-%d")
        logger.info(f"[{i+1}/{len(all_dates)}] 采集 {dh}...")

        # 龙虎榜
        try:
            lhb_data = fetch_lhb(ds, ds)
            if lhb_data:
                cache["lhb"][dh] = lhb_data
        except Exception as e:
            cache["errors"].append(f"lhb {dh}: {e}")

        time.sleep(0.3)

        # 涨停/跌停
        try:
            limit_data = fetch_limit_stats(d)
            if limit_data["zt_count"] > 0 or limit_data["dt_count"] > 0:
                cache["limit_stats"][dh] = limit_data
        except Exception as e:
            cache["errors"].append(f"limit_stats {dh}: {e}")

        time.sleep(0.3)

        # 每10天保存一次进度
        if (i + 1) % 10 == 0:
            _save_cache(cache)

    # 3) 融资融券 - 采样采集（每天数据量大，选部分关键日期）
    # 采集每周一的融资融券数据作为代表
    margin_dates = [d for d in all_dates if d.weekday() == 0]  # 每周一
    # 同时包含首尾
    if all_dates[0] not in margin_dates:
        margin_dates.insert(0, all_dates[0])
    if all_dates[-1] not in margin_dates:
        margin_dates.append(all_dates[-1])

    logger.info(f">>> 采集融资融券数据 (共 {len(margin_dates)} 个采样日期)...")
    for d in margin_dates:
        ds = d.strftime("%Y%m%d")
        dh = d.strftime("%Y-%m-%d")
        try:
            margin_data = fetch_margin_daily(ds)
            if margin_data:
                cache["margin_daily"][dh] = margin_data
        except Exception as e:
            cache["errors"].append(f"margin {dh}: {e}")
        time.sleep(1)

    # 统计
    cache["stats"]["success"] = (
        len(cache["north_flow"]) +
        sum(len(v) for v in cache["lhb"].values()) +
        len(cache["limit_stats"]) +
        sum(len(v) for v in cache["margin_daily"].values())
    )
    cache["stats"]["fail"] = len(cache["errors"])

    _save_cache(cache)

    logger.info("=" * 50)
    logger.info("采集完成!")
    logger.info(f"  北向资金: {len(cache['north_flow'])} 天")
    logger.info(f"  龙虎榜:   {len(cache['lhb'])} 天, {sum(len(v) for v in cache['lhb'].values())} 条记录")
    logger.info(f"  涨跌停:   {len(cache['limit_stats'])} 天")
    logger.info(f"  融资融券: {len(cache['margin_daily'])} 天")
    logger.info(f"  错误:     {len(cache['errors'])} 条")
    logger.info(f"  缓存文件: {CACHE_FILE}")

    return cache


def _save_cache(cache: dict):
    """保存缓存到 JSON。"""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"缓存已保存: {CACHE_FILE}")


def load_cache() -> dict:
    """加载缓存。"""
    if CACHE_FILE.exists():
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ---------------------------------------------------------------------------
# 单独运行
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] == "test":
        # 快速测试模式
        print("=" * 50)
        print("快速接口测试")
        print("=" * 50)

        test_date = "20260424"

        print("\n1. 北向资金")
        nf = fetch_north_flow(test_date)
        print(f"   净流入: {nf} 亿")

        print("\n2. 个股资金流向 (000001)")
        mf = fetch_money_flow("000001")
        print(f"   {mf}")

        print("\n3. 龙虎榜")
        lhb = fetch_lhb(test_date, test_date)
        print(f"   记录数: {len(lhb)}")
        if lhb:
            print(f"   示例: {lhb[0]['name']} 净买额: {lhb[0]['net_buy']}")

        print("\n4. 融资融券 (000001)")
        mg = fetch_margin("000001", test_date)
        print(f"   {mg}")

        print("\n5. 涨跌停统计")
        ls = fetch_limit_stats(test_date)
        print(f"   涨停: {ls['zt_count']}, 跌停: {ls['dt_count']}")
        if ls["zt_stocks"]:
            print(f"   涨停示例: {ls['zt_stocks'][0]}")

    elif len(sys.argv) >= 2 and sys.argv[1] == "fetch":
        # 批量采集
        start = sys.argv[2] if len(sys.argv) > 2 else "20260301"
        end = sys.argv[3] if len(sys.argv) > 3 else "20260424"
        fetch_all_new_data(start, end)
    else:
        print("用法:")
        print("  python new_data_sources.py test          - 快速接口测试")
        print("  python new_data_sources.py fetch          - 批量采集 (默认 20260301~20260424)")
        print("  python new_data_sources.py fetch START END - 自定义日期范围")
