#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
收盘自动验证脚本 (V2 - 本地缓存优先)

读取 recommendation_history/*.json 中的历史推荐，
获取每只推荐股次日涨跌，与指数对比，计算 beat_idx。

数据策略：
1. 优先从本地K线缓存获取（无需网络）
2. 缓存中没有的再用AKShare网络获取（带重试）
3. 指数数据同理

使用方法：
    python verify_recommendation.py
    python verify_recommendation.py --date 20260428  # 验证单日
"""

import json
import os
import sys
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# 禁用代理
for k in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    os.environ[k] = ''

# Monkey-patch requests to disable proxy
import requests as _requests
_orig_init = _requests.Session.__init__
def _no_proxy_init(self, *a, **kw):
    _orig_init(self, *a, **kw)
    self.trust_env = False
    self.proxies = {'http': None, 'https': None}
_requests.Session.__init__ = _no_proxy_init

import akshare as ak

# ============================================================================
# Config
# ============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REC_DIR = os.path.join(BASE_DIR, 'recommendation_history')
VER_DIR = os.path.join(REC_DIR, 'verification_history')
SUMMARY_PATH = os.path.join(REC_DIR, 'verification_summary.json')

# 本地K线缓存目录
KLINE_CACHE = os.path.join(BASE_DIR, '..', 'TradingShared', 'data', 'kline_cache')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ============================================================================
# Local cache loaders
# ============================================================================
_kline_cache = {}  # code -> {date: close}
_index_cache_local = {}  # date -> close

def load_local_kline():
    """从本地K线缓存加载数据"""
    global _kline_cache, _index_cache_local
    
    # 尝试加载合并后的全量K线
    for fname in ['kline_full_latest.json', 'kline_full_20250901_20260424.json']:
        fp = os.path.join(KLINE_CACHE, fname)
        if os.path.exists(fp):
            logger.info(f"加载本地K线: {fname}")
            try:
                with open(fp, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                count = 0
                for code, klines in data.items():
                    if not isinstance(klines, list):
                        continue
                    _kline_cache[code] = {}
                    for k in klines:
                        d = str(k.get('date', ''))[:10]
                        c = float(k.get('close', 0))
                        if d and c > 0:
                            _kline_cache[code][d] = c
                            count += 1
                logger.info(f"  加载 {len(_kline_cache)} 只股票, {count} 条K线")
            except Exception as e:
                logger.warning(f"  加载失败: {e}")
    
    # 加载指数数据
    for fname in ['index_full_latest.json', 'index_full_20251001_20260425.json']:
        fp = os.path.join(KLINE_CACHE, fname)
        if os.path.exists(fp):
            logger.info(f"加载本地指数: {fname}")
            try:
                with open(fp, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        d = str(item.get('date', ''))[:10]
                        c = float(item.get('close', 0))
                        if d and c > 0:
                            _index_cache_local[d] = c
                elif isinstance(data, dict):
                    # 格式: {"date": {"0": "2026-01-05", ...}, "close": {"0": 3986.972, ...}}
                    date_col = data.get('date', {})
                    close_col = data.get('close', {})
                    if isinstance(date_col, dict) and isinstance(close_col, dict):
                        for idx_key in date_col:
                            if idx_key in close_col:
                                d = str(date_col[idx_key])[:10]
                                c = float(close_col[idx_key])
                                if d and c > 0:
                                    _index_cache_local[d] = c
                logger.info(f"  加载 {len(_index_cache_local)} 天指数数据")
            except Exception as e:
                logger.warning(f"  加载失败: {e}")


def _normalize_code(code: str) -> list:
    """生成股票代码的多种可能格式用于查找"""
    variants = [code]
    # 如果没有前缀，添加 sh/sz
    if not code.startswith(('sh', 'sz', 'SH', 'SZ')):
        if code.startswith(('6', '9')):
            variants.append(f'sh{code}')
            variants.append(f'SH{code}')
        else:
            variants.append(f'sz{code}')
            variants.append(f'SZ{code}')
    else:
        # 如果有前缀，也生成无前缀版本
        variants.append(code[2:])
    return variants


def get_stock_close_local(code: str, date_str: str) -> Optional[float]:
    """从本地缓存获取股票收盘价"""
    for variant in _normalize_code(code):
        if variant in _kline_cache:
            return _kline_cache[variant].get(date_str)
    return None


def get_index_close_local(date_str: str) -> Optional[float]:
    """从本地缓存获取指数收盘价"""
    return _index_cache_local.get(date_str)


# ============================================================================
# Network fetchers (with retry)
# ============================================================================
def get_stock_close_net(code: str, date_str: str, retries: int = 3) -> Optional[float]:
    """从网络获取股票收盘价（带重试）"""
    start_dt = datetime.strptime(date_str, '%Y-%m-%d') - timedelta(days=2)
    end_dt = datetime.strptime(date_str, '%Y-%m-%d') + timedelta(days=10)
    
    for attempt in range(retries):
        try:
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start_dt.strftime('%Y%m%d'),
                end_date=end_dt.strftime('%Y%m%d'),
                adjust="qfq"
            )
            if df is not None and not df.empty:
                df['date'] = df['日期'].astype(str).str[:10]
                row = df[df['date'] == date_str]
                if not row.empty:
                    close = float(row.iloc[0]['收盘'])
                    # 缓存到本地
                    if code not in _kline_cache:
                        _kline_cache[code] = {}
                    _kline_cache[code][date_str] = close
                    return close
        except Exception as e:
            logger.debug(f"  {code} 网络请求失败 (attempt {attempt+1}/{retries}): {e}")
            time.sleep(2 * (attempt + 1))
    
    return None


def get_index_close_net(date_str: str, retries: int = 3) -> Optional[float]:
    """从网络获取指数收盘价（带重试）"""
    for attempt in range(retries):
        try:
            df = ak.stock_zh_index_daily(symbol="sh000001")
            if df is not None and not df.empty:
                df['date'] = df['date'].astype(str).str[:10]
                row = df[df['date'] == date_str]
                if not row.empty:
                    close = float(row.iloc[0]['close'])
                    _index_cache_local[date_str] = close
                    return close
        except Exception as e:
            logger.debug(f"  指数网络请求失败 (attempt {attempt+1}): {e}")
            time.sleep(2 * (attempt + 1))
    return None


# ============================================================================
# Core functions
# ============================================================================
def get_stock_return(code: str, rec_date: str) -> Optional[float]:
    """获取股票推荐次日收益率(%)"""
    # 如果推荐日不是交易日，找最近的前一个交易日
    actual_date = rec_date
    if rec_date not in _index_cache_local:
        nearest = _find_nearest_trading_day(rec_date, 'before')
        if nearest:
            actual_date = nearest
    
    # 获取推荐日收盘价
    rec_close = get_stock_close_local(code, actual_date)
    if rec_close is None:
        rec_close = get_stock_close_net(code, actual_date)
    if rec_close is None:
        logger.warning(f"  {code}: 推荐日 {actual_date} 无收盘价")
        return None
    
    # 获取次日收盘价（推荐日之后第一个有数据的交易日）
    # 先从本地缓存找
    next_close = None
    next_date = None
    
    # 尝试多种代码格式查找本地缓存
    cached_code = None
    for variant in _normalize_code(code):
        if variant in _kline_cache:
            cached_code = variant
            break
    
    if cached_code:
        dates = sorted([d for d in _kline_cache[cached_code].keys() if d > actual_date])
        if dates:
            next_date = dates[0]
            next_close = _kline_cache[cached_code][next_date]
    
    # 本地没有则网络获取
    if next_close is None:
        try:
            start_dt = datetime.strptime(actual_date, '%Y-%m-%d') + timedelta(days=1)
            end_dt = start_dt + timedelta(days=10)
            df = ak.stock_zh_a_hist(
                symbol=code, period="daily",
                start_date=start_dt.strftime('%Y%m%d'),
                end_date=end_dt.strftime('%Y%m%d'),
                adjust="qfq"
            )
            if df is not None and not df.empty:
                df['date'] = df['日期'].astype(str).str[:10]
                df = df.sort_values('date')
                next_date = df.iloc[0]['date']
                next_close = float(df.iloc[0]['收盘'])
        except Exception:
            pass
    
    if next_close is None:
        logger.warning(f"  {code}: 次日无数据")
        return None
    
    ret = round((next_close - rec_close) / rec_close * 100, 2)
    logger.info(f"  {code}: {actual_date} → {next_date} = {ret:+.2f}%")
    return ret


def _find_nearest_trading_day(date_str: str, direction: str = 'before') -> Optional[str]:
    """找到最近的交易日"""
    all_dates = sorted(_index_cache_local.keys())
    if direction == 'before':
        candidates = [d for d in all_dates if d <= date_str]
    else:
        candidates = [d for d in all_dates if d >= date_str]
    return candidates[-1] if candidates else None

def get_index_return(rec_date: str) -> Optional[float]:
    """获取指数推荐次日收益率(%)"""
    # 如果推荐日不是交易日，找最近的前一个交易日
    actual_date = rec_date
    if rec_date not in _index_cache_local:
        nearest = _find_nearest_trading_day(rec_date, 'before')
        if nearest:
            actual_date = nearest
    
    rec_close = get_index_close_local(actual_date)
    if rec_close is None:
        rec_close = get_index_close_net(actual_date)
    if rec_close is None:
        return None
    
    # 找下一个交易日
    next_close = None
    next_date = None
    
    dates = sorted([d for d in _index_cache_local.keys() if d > rec_date])
    if dates:
        next_date = dates[0]
        next_close = _index_cache_local[next_date]
    
    if next_close is None:
        try:
            start_dt = datetime.strptime(rec_date, '%Y-%m-%d') + timedelta(days=1)
            end_dt = start_dt + timedelta(days=10)
            df = ak.stock_zh_index_daily(symbol="sh000001")
            if df is not None and not df.empty:
                df['date'] = df['date'].astype(str).str[:10]
                after = df[(df['date'] > rec_date) & (df['date'] <= end_dt.strftime('%Y-%m-%d'))].sort_values('date')
                if not after.empty:
                    next_date = after.iloc[0]['date']
                    next_close = float(after.iloc[0]['close'])
                    _index_cache_local[next_date] = next_close
        except Exception:
            pass
    
    if next_close is None:
        return None
    
    ret = round((next_close - rec_close) / rec_close * 100, 2)
    logger.info(f"  指数: {rec_date} → {next_date} = {ret:+.2f}%")
    return ret


def verify_single_recommendation(rec_date: str, stocks: List[Dict]) -> Dict:
    """验证单日推荐"""
    if rec_date == datetime.now().strftime('%Y-%m-%d'):
        return {'date': rec_date, 'status': 'skipped', 'reason': '今日推荐尚未收盘', 'stocks': []}
    
    idx_ret = get_index_return(rec_date)
    if idx_ret is None:
        return {'date': rec_date, 'status': 'error', 'reason': '无法获取指数数据', 'stocks': []}
    
    stock_results = []
    for s in stocks:
        code = s.get('stock_code', '')
        name = s.get('stock_name', '')
        score = s.get('total_score', 0)
        stock_ret = get_stock_return(code, rec_date)
        
        if stock_ret is None:
            stock_results.append({'code': code, 'name': name, 'score': score, 'return': None, 'beat_idx': None, 'status': 'no_data'})
            continue
        
        beat = stock_ret > idx_ret
        stock_results.append({'code': code, 'name': name, 'score': score, 'return': stock_ret, 'beat_idx': beat, 'status': 'ok'})
    
    valid_rets = [r['return'] for r in stock_results if r['return'] is not None]
    avg_ret = round(sum(valid_rets) / len(valid_rets), 2) if valid_rets else None
    day_beat = avg_ret > idx_ret if avg_ret is not None else None
    
    return {
        'date': rec_date, 'status': 'verified',
        'index_return': idx_ret, 'avg_stock_return': avg_ret,
        'beat_idx': day_beat,
        'beat_idx_count': sum(1 for r in stock_results if r.get('beat_idx')),
        'total_stocks': len(valid_rets),
        'stocks': stock_results
    }


def load_recommendations() -> List[Tuple[str, List[Dict]]]:
    """加载所有推荐记录"""
    results = []
    if not os.path.exists(REC_DIR):
        return results
    for f in sorted(os.listdir(REC_DIR)):
        if not f.startswith('recommendation_') or not f.endswith('.json'):
            continue
        try:
            data = json.load(open(os.path.join(REC_DIR, f), 'r', encoding='utf-8'))
            rec = data.get('recommended', [])
            stocks = rec if isinstance(rec, list) else [rec]
            date = data.get('date', '')
            if not date:
                date = f"{f[15:19]}-{f[19:21]}-{f[21:23]}"
            results.append((date, stocks))
        except Exception as e:
            logger.warning(f"读取 {f} 失败: {e}")
    return results


def run_all_verifications() -> List[Dict]:
    """验证所有历史推荐"""
    recommendations = load_recommendations()
    if not recommendations:
        logger.warning("没有找到推荐记录")
        return []
    logger.info(f"找到 {len(recommendations)} 条推荐记录")
    logger.info("=" * 60)
    
    all_results = []
    for i, (date, stocks) in enumerate(recommendations, 1):
        logger.info(f"\n[{i}/{len(recommendations)}] 验证 {date} ({len(stocks)} 只)...")
        result = verify_single_recommendation(date, stocks)
        all_results.append(result)
        time.sleep(0.3)
    return all_results


def print_summary(results: List[Dict]) -> Dict:
    """输出汇总统计"""
    verified = [r for r in results if r['status'] == 'verified']
    skipped = [r for r in results if r['status'] == 'skipped']
    errors = [r for r in results if r['status'] == 'error']
    
    print("\n" + "=" * 60)
    print("  推荐验证汇总报告")
    print("=" * 60)
    
    if not verified:
        print("  没有可验证的推荐记录")
        return {}
    
    total_days = len(verified)
    beat_idx_days = sum(1 for r in verified if r.get('beat_idx'))
    beat_idx_pct = round(beat_idx_days / total_days * 100, 1) if total_days > 0 else 0
    
    all_stocks = []
    for r in verified:
        all_stocks.extend(r['stocks'])
    valid_stocks = [s for s in all_stocks if s['status'] == 'ok']
    
    stock_wins = sum(1 for s in valid_stocks if s['return'] > 0)
    stock_beat_idx = sum(1 for s in valid_stocks if s.get('beat_idx'))
    stock_total = len(valid_stocks)
    
    rets = [s['return'] for s in valid_stocks if s['return'] is not None]
    avg_ret = round(sum(rets) / len(rets), 2) if rets else None
    
    print(f"\n  总推荐天数: {total_days}")
    print(f"  Beat指数天数: {beat_idx_days}/{total_days} = {beat_idx_pct}%")
    print(f"  跳过(今日): {len(skipped)} | 错误: {len(errors)}")
    print(f"\n  总推荐股票: {stock_total}")
    print(f"  上涨股票: {stock_wins}/{stock_total} = {round(stock_wins/stock_total*100,1) if stock_total else 0}%")
    print(f"  Beat指数股票: {stock_beat_idx}/{stock_total} = {round(stock_beat_idx/stock_total*100,1) if stock_total else 0}%")
    print(f"  平均收益: {avg_ret:+.2f}%" if avg_ret is not None else "  平均收益: N/A")
    
    print(f"\n  每日明细:")
    print(f"  {'日期':<12} {'指数':>8} {'平均':>8} {'Beat':>6} {'详情'}")
    print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*6} {'-'*40}")
    
    for r in verified:
        idx_ret = r.get('index_return', 0)
        avg = r.get('avg_stock_return')
        beat = 'YES' if r.get('beat_idx') else 'NO'
        avg_str = f"{avg:>+7.2f}%" if avg is not None else "  N/A  "
        
        details = []
        for s in r['stocks']:
            if s['status'] == 'ok':
                mark = 'Y' if s.get('beat_idx') else 'N'
                details.append(f"{s['code']}({s['return']:+.1f}%){mark}")
            else:
                details.append(f"{s['code']}(N/A)")
        detail_str = ', '.join(details)
        if len(detail_str) > 45:
            detail_str = detail_str[:42] + "..."
        
        print(f"  {r['date']:<12} {idx_ret:>+7.2f}% {avg_str} {beat:>6} {detail_str}")
    
    if rets:
        best = max(valid_stocks, key=lambda s: s['return'] if s['return'] is not None else -999)
        worst = min(valid_stocks, key=lambda s: s['return'] if s['return'] is not None else 999)
        print(f"\n  最佳: {best['name']}({best['code']}) {best['return']:+.2f}%")
        print(f"  最差: {worst['name']}({worst['code']}) {worst['return']:+.2f}%")
    
    # 评分 vs 表现
    score_groups = {}
    for s in valid_stocks:
        score = s.get('score', 0)
        bucket = '>=8.0' if score >= 8.0 else ('7.0-8.0' if score >= 7.0 else '<7.0')
        if bucket not in score_groups:
            score_groups[bucket] = {'rets': [], 'beat': 0, 'total': 0}
        score_groups[bucket]['rets'].append(s['return'])
        score_groups[bucket]['total'] += 1
        if s.get('beat_idx'):
            score_groups[bucket]['beat'] += 1
    
    print(f"\n  评分 vs 表现:")
    for bucket in ['>=8.0', '7.0-8.0', '<7.0']:
        if bucket in score_groups:
            g = score_groups[bucket]
            g_avg = round(sum(g['rets'])/len(g['rets']), 2) if g['rets'] else 0
            g_bi = round(g['beat']/g['total']*100, 1)
            print(f"    评分{bucket}: {g['total']}只, 平均{g_avg:+.2f}%, beat={g_bi}%")
    
    print(f"\n  {'='*60}")
    print(f"  核心: Beat指数率 = {beat_idx_pct}% ({beat_idx_days}/{total_days}天)")
    print(f"  {'='*60}")
    
    summary = {
        'total_days': total_days,
        'beat_idx_days': beat_idx_days,
        'beat_idx_pct': beat_idx_pct,
        'total_stocks': stock_total,
        'stock_wins': stock_wins,
        'stock_win_rate': round(stock_wins/stock_total*100, 1) if stock_total else 0,
        'stock_beat_idx': stock_beat_idx,
        'stock_beat_idx_rate': round(stock_beat_idx/stock_total*100, 1) if stock_total else 0,
        'avg_return': avg_ret,
    }
    if rets:
        summary['best_stock'] = {'code': best['code'], 'name': best['name'], 'return': best['return']}
        summary['worst_stock'] = {'code': worst['code'], 'name': worst['name'], 'return': worst['return']}
    return summary


def save_results(results: List[Dict], summary: Dict):
    """保存验证结果"""
    os.makedirs(VER_DIR, exist_ok=True)
    
    for r in results:
        if r['status'] == 'verified':
            fp = os.path.join(VER_DIR, r['date'].replace('-', '') + '.json')
            with open(fp, 'w', encoding='utf-8') as f:
                json.dump(r, f, ensure_ascii=False, indent=2)
    
    output = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'summary': summary,
        'daily_results': results,
    }
    with open(SUMMARY_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info(f"结果已保存: {SUMMARY_PATH}")


def main():
    logger.info("=" * 60)
    logger.info("  收盘自动验证系统 V2 (本地缓存优先)")
    logger.info(f"  运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    target_date = None
    if '--date' in sys.argv:
        idx = sys.argv.index('--date')
        if idx + 1 < len(sys.argv):
            target_date = sys.argv[idx + 1]
    
    # 加载本地缓存
    load_local_kline()
    
    if target_date:
        date_fmt = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:8]}"
        for date, stocks in load_recommendations():
            if date == date_fmt:
                result = verify_single_recommendation(date_fmt, stocks)
                summary = print_summary([result])
                save_results([result], summary or {})
                return
        logger.error(f"未找到 {date_fmt} 的推荐记录")
        return
    
    results = run_all_verifications()
    summary = print_summary(results)
    if summary:
        save_results(results, summary)


if __name__ == '__main__':
    main()
