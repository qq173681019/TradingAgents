#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推荐验证脚本 V3 - T+3 窗口验证

新规则 (2026-05-09):
1. T+3窗口：推荐日(D)起，看D+1、D+2、D+3共3个交易日的表现
2. Win条件（3天内任意一天满足即可）：
   - 牛市日（指数涨或平）：股票涨幅 > 指数涨幅
   - 熊市日（指数跌）：股票涨幅 > 0 即算win
3. 最终结果：3天内只要有1天win，该推荐就是win
4. 避险机制：预判大盘大跌时可跳过推送

使用方法：
    python -X utf8 verify_recommendation_v3.py
    python -X utf8 verify_recommendation_v3.py --date 20260508  # 验证单日
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
SUMMARY_PATH = os.path.join(REC_DIR, 'verification_summary_v3.json')
KLINE_CACHE = os.path.join(BASE_DIR, '..', 'TradingShared', 'data', 'kline_cache')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# T+3 窗口大小
T3_WINDOW = 3

# ============================================================================
# Local cache
# ============================================================================
_kline_cache = {}       # code -> {date_str: close}
_index_cache_local = {} # date_str -> close
_trading_days = []      # sorted list of trading day strings


def load_local_kline():
    """从本地K线缓存加载数据"""
    global _trading_days
    
    for fname in ['kline_full_latest.json']:
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
    
    for fname in ['index_full_latest.json']:
        fp = os.path.join(KLINE_CACHE, fname)
        if os.path.exists(fp):
            logger.info(f"加载本地指数: {fname}")
            try:
                with open(fp, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
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
    
    _trading_days = sorted(_index_cache_local.keys())
    logger.info(f"  交易日历: {len(_trading_days)} 天, "
                f"{_trading_days[0] if _trading_days else 'N/A'} ~ "
                f"{_trading_days[-1] if _trading_days else 'N/A'}")


def _normalize_code(code: str) -> list:
    """生成股票代码的多种可能格式"""
    variants = [code]
    if not code.startswith(('sh', 'sz', 'SH', 'SZ')):
        if code.startswith(('6', '9')):
            variants.append(f'sh{code}')
            variants.append(f'SH{code}')
        else:
            variants.append(f'sz{code}')
            variants.append(f'SZ{code}')
    else:
        variants.append(code[2:])
    return variants


def get_trading_days_after(date_str: str, n: int = 3) -> List[str]:
    """获取指定日期之后的 n 个交易日"""
    return [d for d in _trading_days if d > date_str][:n]


def get_prev_trading_day(date_str: str) -> Optional[str]:
    """获取指定日期之前的最近交易日"""
    before = [d for d in _trading_days if d <= date_str]
    return before[-1] if before else None


def _find_cached_code(code: str) -> Optional[str]:
    """在缓存中找到匹配的code"""
    for variant in _normalize_code(code):
        if variant in _kline_cache:
            return variant
    return None


def get_stock_close(code: str, date_str: str) -> Optional[float]:
    """获取股票收盘价（本地优先，网络fallback）"""
    # 本地
    cached = _find_cached_code(code)
    if cached and date_str in _kline_cache[cached]:
        return _kline_cache[cached][date_str]
    
    # 网络
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        df = ak.stock_zh_a_hist(
            symbol=code, period="daily",
            start_date=dt.strftime('%Y%m%d'),
            end_date=(dt + timedelta(days=1)).strftime('%Y%m%d'),
            adjust="qfq"
        )
        if df is not None and not df.empty:
            close = float(df.iloc[0]['收盘'])
            if code not in _kline_cache:
                _kline_cache[code] = {}
            _kline_cache[code][date_str] = close
            return close
    except Exception:
        pass
    return None


def get_index_close(date_str: str) -> Optional[float]:
    """获取指数收盘价（本地优先，网络fallback）"""
    if date_str in _index_cache_local:
        return _index_cache_local[date_str]
    
    try:
        df = ak.stock_zh_index_daily(symbol="sh000001")
        if df is not None and not df.empty:
            df['date'] = df['date'].astype(str).str[:10]
            row = df[df['date'] == date_str]
            if not row.empty:
                close = float(row.iloc[0]['close'])
                _index_cache_local[date_str] = close
                return close
    except Exception:
        pass
    return None


# ============================================================================
# T+3 窗口验证核心逻辑
# ============================================================================

def calc_daily_return(code: str, date_str: str, base_close: float) -> Optional[float]:
    """计算股票在指定日期相对 base_close 的收益率"""
    close = get_stock_close(code, date_str)
    if close is None:
        return None
    return round((close - base_close) / base_close * 100, 2)


def calc_index_daily_return(date_str: str, base_close: float) -> Optional[float]:
    """计算指数在指定日期相对 base_close 的收益率"""
    close = get_index_close(date_str)
    if close is None:
        return None
    return round((close - base_close) / base_close * 100, 2)


def is_bear_day(index_ret: float) -> bool:
    """判断是否为熊市日（指数跌）"""
    return index_ret < 0


def check_day_win(stock_ret: float, index_ret: float) -> bool:
    """
    检查单日是否win：
    - 熊市日（指数跌）：股票涨（>0）就算win
    - 牛市日（指数涨或平）：股票涨幅 > 指数涨幅
    """
    if is_bear_day(index_ret):
        return stock_ret > 0
    else:
        return stock_ret > index_ret


def verify_stock_t3(code: str, name: str, rec_date: str) -> Dict:
    """验证单只股票的 T+3 窗口表现"""
    # 找推荐日的最近交易日（可能是推荐日本身或之前）
    actual_rec_date = get_prev_trading_day(rec_date)
    if actual_rec_date is None:
        return {'code': code, 'name': name, 'status': 'no_rec_date'}
    
    # 获取推荐日收盘价（作为基准）
    base_close = get_stock_close(code, actual_rec_date)
    if base_close is None:
        return {'code': code, 'name': name, 'status': 'no_base_price'}
    
    # 获取推荐日指数收盘价
    idx_base_close = get_index_close(actual_rec_date)
    if idx_base_close is None:
        return {'code': code, 'name': name, 'status': 'no_idx_base'}
    
    # 找后续3个交易日
    next_days = get_trading_days_after(actual_rec_date, T3_WINDOW)
    if not next_days:
        return {'code': code, 'name': name, 'status': 'no_future_data',
                'note': '推荐日之后无交易日数据'}
    
    # 逐日计算
    daily_results = []
    best_day = None
    best_day_ret = -999
    win = False
    win_day = None
    
    for i, day in enumerate(next_days):
        s_ret = calc_daily_return(code, day, base_close)
        i_ret = calc_index_daily_return(day, idx_base_close)
        
        day_result = {
            'day_offset': i + 1,
            'date': day,
            'stock_return': s_ret,
            'index_return': i_ret,
            'is_bear_day': is_bear_day(i_ret) if i_ret is not None else None,
        }
        
        if s_ret is not None and i_ret is not None:
            day_win = check_day_win(s_ret, i_ret)
            day_result['win'] = day_win
            if day_win and not win:
                win = True
                win_day = i + 1
            if s_ret > best_day_ret:
                best_day_ret = s_ret
                best_day = day_result
        else:
            day_result['win'] = None
        
        daily_results.append(day_result)
    
    return {
        'code': code,
        'name': name,
        'status': 'verified',
        'rec_date': actual_rec_date,
        'base_close': base_close,
        't3_days': len(next_days),
        'daily': daily_results,
        'win': win,
        'win_day': win_day,  # T+? day won
        'best_return': best_day_ret if best_day_ret > -999 else None,
    }


def verify_single_recommendation_t3(rec_date: str, stocks: List[Dict]) -> Dict:
    """验证单日推荐的 T+3 窗口表现"""
    today = datetime.now().strftime('%Y-%m-%d')
    if rec_date >= today:
        return {'date': rec_date, 'status': 'skipped', 
                'reason': '推荐日尚未有后续交易日数据', 'stocks': []}
    
    stock_results = []
    for s in stocks:
        code = s.get('stock_code', '')
        name = s.get('stock_name', '')
        score = s.get('total_score', 0)
        result = verify_stock_t3(code, name, rec_date)
        result['score'] = score
        stock_results.append(result)
        logger.info(f"  {name}({code}): win={result.get('win', 'N/A')}"
                    f' (T+' + str(result['win_day']) + ')' if result.get('win_day') else ''
                    f" best={result.get('best_return', 'N/A')}%")
    
    # 汇总
    verified = [r for r in stock_results if r['status'] == 'verified']
    wins = [r for r in verified if r.get('win')]
    no_data = [r for r in stock_results if r['status'] != 'verified']
    
    # 计算每个T+N日的表现
    day_stats = {}
    for offset in range(1, T3_WINDOW + 1):
        day_wins = 0
        day_total = 0
        for r in verified:
            for d in r.get('daily', []):
                if d.get('day_offset') == offset and d.get('win') is not None:
                    day_total += 1
                    if d.get('win'):
                        day_wins += 1
        if day_total > 0:
            day_stats[f'T+{offset}'] = {
                'win': day_wins,
                'total': day_total,
                'rate': round(day_wins / day_total * 100, 1),
            }
    
    return {
        'date': rec_date,
        'status': 'verified' if verified else 'no_data',
        'total_stocks': len(stocks),
        'verified_stocks': len(verified),
        'win_stocks': len(wins),
        'no_data_stocks': len(no_data),
        'win_rate': round(len(wins) / len(verified) * 100, 1) if verified else 0,
        'day_stats': day_stats,
        'stocks': stock_results,
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
            with open(os.path.join(REC_DIR, f), 'r', encoding='utf-8') as fobj:
                data = json.load(fobj)
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
        logger.info(f"\n[{i}/{len(recommendations)}] 验证 {date} ({len(stocks)} 只) - T+{T3_WINDOW}窗口...")
        result = verify_single_recommendation_t3(date, stocks)
        all_results.append(result)
        time.sleep(0.3)
    return all_results


def print_summary(results: List[Dict]) -> Dict:
    """输出 T+3 窗口汇总报告"""
    verified = [r for r in results if r['status'] == 'verified']
    skipped = [r for r in results if r['status'] == 'skipped']
    
    print("\n" + "=" * 70)
    print("  T+3 窗口推荐验证汇总报告 (V3)")
    print("=" * 70)
    
    if not verified:
        print("  没有可验证的推荐记录")
        return {}
    
    # 整体统计
    total_days = len(verified)
    total_verified_stocks = sum(r['verified_stocks'] for r in verified)
    total_win_stocks = sum(r['win_stocks'] for r in verified)
    
    # 按天计算 beat_rate（该天推荐股 win 比例 > 50% 算 beat）
    day_beats = sum(1 for r in verified if r['win_rate'] >= 50)
    
    # T+1/T+2/T+3 逐日统计
    all_day_stats = {}
    for r in verified:
        for key, val in r.get('day_stats', {}).items():
            if key not in all_day_stats:
                all_day_stats[key] = {'win': 0, 'total': 0}
            all_day_stats[key]['win'] += val['win']
            all_day_stats[key]['total'] += val['total']
    
    overall_win_rate = round(total_win_stocks / total_verified_stocks * 100, 1) if total_verified_stocks else 0
    
    print(f"\n  总推荐天数: {total_days}")
    print(f"  日级别胜率: {day_beats}/{total_days} = {round(day_beats/total_days*100,1)}% (该天>=50%推荐股win)")
    print(f"\n  总推荐股票: {total_verified_stocks}")
    print(f"  T+3 窗口Win: {total_win_stocks}/{total_verified_stocks} = {overall_win_rate}%")
    
    print(f"\n  逐T+N日统计:")
    for key in ['T+1', 'T+2', 'T+3']:
        if key in all_day_stats:
            s = all_day_stats[key]
            rate = round(s['win'] / s['total'] * 100, 1)
            print(f"    {key}: {s['win']}/{s['total']} = {rate}%")
    
    # 每日明细
    print(f"\n  每日明细:")
    print(f"  {'日期':<12} {'推荐':>4} {'Win':>4} {'胜率':>7} {'详情'}")
    print(f"  {'-'*12} {'-'*4} {'-'*4} {'-'*7} {'-'*50}")
    
    for r in verified:
        detail_parts = []
        for s in r.get('stocks', []):
            if s.get('status') != 'verified':
                detail_parts.append(f"{s.get('code','')}({s.get('status','')})")
                continue
            mark = 'W' if s.get('win') else 'L'
            best = s.get('best_return')
            best_str = f"{best:+.1f}%" if best is not None else "N/A"
            win_info = f"T+{s['win_day']}" if s.get('win_day') else ""
            detail_parts.append(f"{s['name']}({best_str}{win_info}){mark}")
        
        detail_str = ', '.join(detail_parts)
        if len(detail_str) > 50:
            detail_str = detail_str[:47] + "..."
        
        print(f"  {r['date']:<12} {r['verified_stocks']:>4} {r['win_stocks']:>4} "
              f"{r['win_rate']:>6.1f}% {detail_str}")
    
    # 评分 vs Win率
    score_bins = {'>=7.5': [], '7.0-7.5': [], '<7.0': []}
    for r in verified:
        for s in r.get('stocks', []):
            if s.get('status') != 'verified':
                continue
            score = s.get('score', 0)
            if score >= 7.5:
                score_bins['>=7.5'].append(s)
            elif score >= 7.0:
                score_bins['7.0-7.5'].append(s)
            else:
                score_bins['<7.0'].append(s)
    
    print(f"\n  评分 vs T+3 Win率:")
    for bucket, stocks_list in score_bins.items():
        if stocks_list:
            wins = sum(1 for s in stocks_list if s.get('win'))
            total = len(stocks_list)
            print(f"    评分{bucket}: {wins}/{total} = {round(wins/total*100,1)}% win")
    
    print(f"\n  {'='*70}")
    print(f"  核心: T+3 Win率 = {overall_win_rate}% ({total_win_stocks}/{total_verified_stocks}只)")
    print(f"  {'='*70}")
    
    summary = {
        'version': 'v3-t3-window',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        't3_window': T3_WINDOW,
        'total_days': total_days,
        'day_beat_rate': round(day_beats / total_days * 100, 1) if total_days else 0,
        'total_stocks': total_verified_stocks,
        'win_stocks': total_win_stocks,
        'win_rate': overall_win_rate,
        'day_stats': {k: {'win': v['win'], 'total': v['total'],
                          'rate': round(v['win']/v['total']*100, 1)}
                      for k, v in all_day_stats.items()},
        'score_bins': {k: {'win': sum(1 for s in v if s.get('win')),
                           'total': len(v),
                           'rate': round(sum(1 for s in v if s.get('win'))/len(v)*100, 1) if v else 0}
                       for k, v in score_bins.items() if v},
    }
    return summary


def save_results(results: List[Dict], summary: Dict):
    """保存验证结果"""
    os.makedirs(VER_DIR, exist_ok=True)
    
    for r in results:
        if r['status'] == 'verified':
            fp = os.path.join(VER_DIR, f"t3_{r['date'].replace('-', '')}.json")
            with open(fp, 'w', encoding='utf-8') as f:
                json.dump(r, f, ensure_ascii=False, indent=2)
    
    output = {
        'summary': summary,
        'daily_results': results,
    }
    with open(SUMMARY_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info(f"结果已保存: {SUMMARY_PATH}")


def main():
    logger.info("=" * 70)
    logger.info(f"  T+3 窗口推荐验证系统 V3")
    logger.info(f"  运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)
    
    target_date = None
    if '--date' in sys.argv:
        idx = sys.argv.index('--date')
        if idx + 1 < len(sys.argv):
            target_date = sys.argv[idx + 1]
    
    load_local_kline()
    
    if target_date:
        date_fmt = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:8]}"
        for date, stocks in load_recommendations():
            if date == date_fmt:
                logger.info(f"验证单日: {date_fmt}")
                result = verify_single_recommendation_t3(date_fmt, stocks)
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
