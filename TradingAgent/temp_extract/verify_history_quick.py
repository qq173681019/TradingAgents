"""
历史推荐验证脚本 v2 - 使用本地缓存数据
验证每条推荐的次日表现 vs 上证指数
"""
import json
import os
import glob
import re
from datetime import datetime
from collections import defaultdict

os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

# === 路径 ===
REC_DIR = r'D:\GitHub\TradingAgents\TradingAgent\recommendation_history'
DATA_DIR = r'D:\GitHub\TradingAgents\TradingShared\data'
INDEX_FILE = os.path.join(DATA_DIR, 'index_shanghai_full.json')

def normalize_date(raw):
    """
    将各种日期格式统一为 YYYY-MM-DD
    支持格式: '2026-04-07', '20260407', '2025929' (无前导零)
    """
    raw = str(raw).strip()
    # Already YYYY-MM-DD
    if re.match(r'^\d{4}-\d{2}-\d{2}$', raw):
        return raw
    # YYYYMMDD (8 digits)
    if re.match(r'^\d{8}$', raw):
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    # Broken format like '2025929' (7 digits) or '2026129' (7 digits)
    # Need to figure out month/day split
    m = re.match(r'^(\d{4})(\d{1,2})(\d{1,2})$', raw)
    if m:
        year, month, day = m.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return raw

def load_index_data():
    """加载上证指数数据"""
    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # 建立日期 -> close 的映射 (YYYY-MM-DD)
    index_map = {}
    for item in data:
        d = normalize_date(item['date'])
        index_map[d] = item['close']
    return index_map

def load_kline_data():
    """从分片文件加载所有K线数据"""
    stock_kline = {}  # code -> {YYYY-MM-DD -> close}
    
    part_files = sorted(glob.glob(os.path.join(DATA_DIR, 'comprehensive_stock_data_part_*.json')))
    for pf in part_files:
        try:
            with open(pf, 'r', encoding='utf-8') as f:
                data = json.load(f)
            stocks = data.get('stocks', {})
            for code, stock_data in stocks.items():
                if 'kline_data' in stock_data and 'daily' in stock_data['kline_data']:
                    daily = stock_data['kline_data']['daily']
                    kline_map = {}
                    for entry in daily:
                        d = normalize_date(entry['date'])
                        kline_map[d] = entry['close']
                    stock_kline[code] = kline_map
        except Exception as e:
            print(f"Warning: Failed to load {os.path.basename(pf)}: {e}")
    
    return stock_kline

def load_recommendations():
    """加载所有推荐记录"""
    recs = []
    files = sorted(glob.glob(os.path.join(REC_DIR, 'recommendation_*.json')))
    for f in files:
        with open(f, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        
        rec_date = normalize_date(data.get('date', ''))
        rec = data.get('recommended')
        
        if isinstance(rec, list):
            for item in rec:
                recs.append({
                    'date': rec_date,
                    'code': item.get('stock_code', ''),
                    'name': item.get('stock_name', ''),
                    'score': item.get('total_score', 0),
                    'source_file': os.path.basename(f)
                })
        elif isinstance(rec, dict):
            recs.append({
                'date': rec_date,
                'code': rec.get('stock_code', ''),
                'name': rec.get('stock_name', ''),
                'score': rec.get('total_score', 0),
                'source_file': os.path.basename(f)
            })
    
    return recs

def get_next_trading_day(date_str, trading_dates_sorted):
    """获取下一个交易日 (trading_dates_sorted 是排序后的列表)"""
    for d in trading_dates_sorted:
        if d > date_str:
            return d
    return None

def main():
    print("=" * 70)
    print("历史推荐验证报告 v2 - 本地数据验证")
    print("=" * 70)
    
    # 1. 加载数据
    print("\n[1] 加载数据...")
    index_map = load_index_data()
    trading_dates_sorted = sorted(index_map.keys())
    print(f"  上证指数数据: {len(index_map)} 个交易日")
    print(f"  范围: {trading_dates_sorted[0]} ~ {trading_dates_sorted[-1]}")
    
    stock_kline = load_kline_data()
    print(f"  K线数据: {len(stock_kline)} 只股票")
    
    # 用K线数据补充交易日（取所有股票都出现的日期作为交易日）
    # 统计每个日期出现的股票数
    date_counts = defaultdict(int)
    for code, kmap in stock_kline.items():
        for d in kmap.keys():
            date_counts[d] += 1
    # 只保留出现次数>100的日期（大部分股票都交易的日子）
    kline_trading_dates = set(d for d, c in date_counts.items() if c > len(stock_kline) * 0.5)
    
    # 合并交易日：指数 + K线
    all_trading_dates = set(trading_dates_sorted) | kline_trading_dates
    trading_dates_sorted = sorted(all_trading_dates)
    
    # 检查数据覆盖范围
    sample_code = list(stock_kline.keys())[0]
    sample_dates = sorted(stock_kline[sample_code].keys())
    print(f"  K线日期范围({sample_code}): {sample_dates[0]} ~ {sample_dates[-1]}, 共{len(sample_dates)}天")
    
    recs = load_recommendations()
    print(f"  推荐记录: {len(recs)} 条")
    
    # 2. 验证每条推荐
    print("\n[2] 逐条验证...")
    print("-" * 100)
    
    results = []
    details = []
    
    for rec in recs:
        date_str = rec['date']  # YYYY-MM-DD
        code = rec['code']
        name = rec['name']
        score = rec['score']
        
        # 查找推荐日收盘价
        if code not in stock_kline:
            details.append({
                **rec, 'status': 'NO_KLINE',
                'rec_close': None, 'next_date': None, 'next_close': None,
                'return_pct': None, 'idx_return_pct': None, 'excess': None
            })
            continue
        
        kline = stock_kline[code]
        
        # 如果推荐日不在交易日列表中（如节假日生成的推荐），
        # 找下一个交易日作为买入基准日
        if date_str in index_map:
            buy_date = date_str  # 推荐日是交易日
        else:
            # 推荐日不是交易日，找下一个交易日
            buy_date = get_next_trading_day(date_str, trading_dates_sorted)
            if buy_date is None:
                details.append({
                    **rec, 'status': 'NO_NEXT_TRADING_DAY',
                    'rec_close': None, 'next_date': None, 'next_close': None,
                    'return_pct': None, 'idx_return_pct': None, 'excess': None
                })
                continue
        
        rec_close = kline.get(buy_date)
        
        if rec_close is None:
            details.append({
                **rec, 'status': 'NO_REC_PRICE',
                'buy_date': buy_date,
                'rec_close': None, 'next_date': None, 'next_close': None,
                'return_pct': None, 'idx_return_pct': None, 'excess': None
            })
            continue
        
        # 查找下一个交易日（卖出日）
        next_date = get_next_trading_day(buy_date, trading_dates_sorted)
        if next_date is None:
            details.append({
                **rec, 'status': 'NO_NEXT_DAY',
                'buy_date': buy_date,
                'rec_close': rec_close, 'next_date': None, 'next_close': None,
                'return_pct': None, 'idx_return_pct': None, 'excess': None
            })
            continue
        
        next_close = kline.get(next_date)
        if next_close is None:
            details.append({
                **rec, 'status': 'NO_NEXT_PRICE',
                'buy_date': buy_date,
                'rec_close': rec_close, 'next_date': next_date, 'next_close': None,
                'return_pct': None, 'idx_return_pct': None, 'excess': None
            })
            continue
        
        # 计算收益率
        return_pct = (next_close - rec_close) / rec_close * 100
        
        # 指数收益率
        idx_rec = index_map.get(buy_date)
        idx_next = index_map.get(next_date)
        idx_return_pct = None
        excess = None
        if idx_rec and idx_next:
            idx_return_pct = (idx_next - idx_rec) / idx_rec * 100
            excess = return_pct - idx_return_pct
        
        entry = {
            **rec, 'status': 'VERIFIED',
            'rec_close': rec_close, 'next_date': next_date, 'next_close': next_close,
            'return_pct': return_pct, 'idx_return_pct': idx_return_pct, 'excess': excess
        }
        details.append(entry)
        results.append(entry)
    
    # 3. 打印详细结果
    header = f"{'日期':<12} {'代码':<8} {'名称':<10} {'推荐价':>8} {'次日价':>8} {'收益%':>8} {'指数%':>8} {'超额%':>8} 状态"
    print(header)
    print("-" * len(header))
    
    for d in details:
        date_fmt = d['date']  # already YYYY-MM-DD
        buy_info = ''
        if d.get('buy_date') and d['buy_date'] != date_fmt:
            buy_info = f" (buy:{d['buy_date']})"
        
        if d['status'] == 'VERIFIED':
            ret = f"{d['return_pct']:+.2f}"
            idx = f"{d['idx_return_pct']:+.2f}" if d['idx_return_pct'] is not None else "N/A"
            exc = f"{d['excess']:+.2f}" if d['excess'] is not None else "N/A"
            print(f"{date_fmt:<12} {d['code']:<8} {d['name']:<10} {d['rec_close']:>8.2f} {d['next_close']:>8.2f} {ret:>8} {idx:>8} {exc:>8} OK{buy_info}")
        else:
            rec_close_str = f"{d['rec_close']:>8.2f}" if d.get('rec_close') is not None else '---'
            next_close_str = f"{d['next_close']:>8.2f}" if d.get('next_close') is not None else '---'
            print(f"{date_fmt:<12} {d['code']:<8} {d['name']:<10} {rec_close_str:>8} {next_close_str:>8} {'---':>8} {'---':>8} {'---':>8} X {d['status']}{buy_info}")
    
    # 4. 统计汇总
    print("\n" + "=" * 70)
    print("统计汇总")
    print("=" * 70)
    
    total = len(recs)
    verified = len(results)
    status_counts = defaultdict(int)
    for d in details:
        status_counts[d['status']] += 1
    
    print(f"\n总推荐数:     {total}")
    print(f"成功验证:     {verified}")
    for status, count in sorted(status_counts.items()):
        if status != 'VERIFIED':
            print(f"  {status}: {count}")
    
    if verified > 0:
        returns = [d['return_pct'] for d in results]
        excesses = [d['excess'] for d in results if d['excess'] is not None]
        wins = sum(1 for r in returns if r > 0)
        beat_idx = sum(1 for e in excesses if e > 0)
        
        avg_return = sum(returns) / len(returns)
        avg_excess = sum(excesses) / len(excesses) if excesses else 0
        max_return = max(returns)
        min_return = min(returns)
        median_return = sorted(returns)[len(returns) // 2]
        
        print(f"\n--- 收益率统计 (基于 {verified} 条验证) ---")
        print(f"胜率(涨):       {wins}/{verified} = {wins/verified*100:.1f}%")
        if excesses:
            print(f"跑赢指数:       {beat_idx}/{len(excesses)} = {beat_idx/len(excesses)*100:.1f}%")
        print(f"平均收益率:     {avg_return:+.2f}%")
        print(f"中位收益率:     {median_return:+.2f}%")
        print(f"最大收益:       {max_return:+.2f}%")
        print(f"最大亏损:       {min_return:+.2f}%")
        print(f"平均超额收益:   {avg_excess:+.2f}%")
        
        profits = [r for r in returns if r > 0]
        losses = [r for r in returns if r < 0]
        avg_profit = sum(profits) / len(profits) if profits else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        profit_loss_ratio = abs(avg_profit / avg_loss) if avg_loss != 0 else float('inf')
        print(f"平均盈利:       {avg_profit:+.2f}%")
        print(f"平均亏损:       {avg_loss:+.2f}%")
        print(f"盈亏比:         {profit_loss_ratio:.2f}")
        
        # 按月分组
        print(f"\n--- 按月统计 ---")
        monthly = defaultdict(list)
        for d in results:
            month_key = d['date'][:7]  # '2026-04'
            monthly[month_key].append(d)
        
        print(f"{'月份':<10} {'数量':>4} {'胜率':>10} {'平均收益':>10} {'平均超额':>10} {'跑赢指数':>10}")
        print("-" * 60)
        for month in sorted(monthly.keys()):
            items = monthly[month]
            m_returns = [i['return_pct'] for i in items]
            m_excesses = [i['excess'] for i in items if i['excess'] is not None]
            m_wins = sum(1 for r in m_returns if r > 0)
            m_beat = sum(1 for e in m_excesses if e > 0)
            m_avg_ret = sum(m_returns) / len(m_returns)
            m_avg_exc = sum(m_excesses) / len(m_excesses) if m_excesses else 0
            win_rate = f"{m_wins}/{len(items)}={m_wins/len(items)*100:.0f}%"
            beat_rate = f"{m_beat}/{len(m_excesses)}" if m_excesses else "N/A"
            print(f"{month:<10} {len(items):>4} {win_rate:>10} {m_avg_ret:>+9.2f}% {m_avg_exc:>+9.2f}% {beat_rate:>10}")
        
        # 累计收益模拟 (等权重每日再平衡)
        print(f"\n--- 累计收益模拟 (等权重每日再平衡) ---")
        daily_groups = defaultdict(list)
        for d in results:
            key = d.get('buy_date', d['date'])  # use buy_date for grouping
            daily_groups[key].append(d['return_pct'])
        
        cumulative = 100.0
        cum_idx = 100.0
        print(f"{'日期':<12} {'推荐数':>4} {'当日组合收益':>12} {'累计净值':>10} {'指数累计':>10}")
        print("-" * 55)
        for date in sorted(daily_groups.keys()):
            rets = daily_groups[date]
            avg_ret = sum(rets) / len(rets)
            cumulative *= (1 + avg_ret / 100)
            
            next_d = get_next_trading_day(date, trading_dates_sorted)
            if next_d and date in index_map and next_d in index_map:
                idx_ret = (index_map[next_d] - index_map[date]) / index_map[date] * 100
                cum_idx *= (1 + idx_ret / 100)
            
            print(f"{date:<12} {len(rets):>4} {avg_ret:>+11.2f}% {cumulative:>10.2f} {cum_idx:>10.2f}")
        
        total_return = (cumulative - 100) / 100 * 100
        total_idx_return = (cum_idx - 100) / 100 * 100
        print(f"\n累计总收益:   {total_return:+.2f}%")
        print(f"指数同期收益: {total_idx_return:+.2f}%")
        print(f"超额收益:     {total_return - total_idx_return:+.2f}%")
    
    # 5. 未验证推荐详情
    unverifiable = [d for d in details if d['status'] != 'VERIFIED']
    if unverifiable:
        print(f"\n--- 未验证的推荐 ({len(unverifiable)} 条) ---")
        for d in unverifiable:
            print(f"  {d['date']} {d['code']} {d['name']} - 原因: {d['status']}")
    
    print("\n" + "=" * 70)
    print("验证完成")
    print("=" * 70)

if __name__ == '__main__':
    main()
