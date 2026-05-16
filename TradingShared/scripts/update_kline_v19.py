"""
增量更新 V19 股票池 K 线数据 (2026-05-06 ~ 2026-05-09)
直接使用 EmQuantAPI，不通过 Choice Worker
"""
import json
import sys
import os
import time

# 路径设置
sys.path.insert(0, r'D:\GitHub\TradingAgents\TradingShared')
sys.path.insert(0, r'D:\GitHub\TradingAgents\TradingShared\api')

PYTHON_EXE = r'C:\veighna_studio\python.exe'

KLINE_FILE = r'D:\GitHub\TradingAgents\TradingShared\data\kline_cache\kline_full_latest.json'
V19_FILE = r'C:\Users\admin\.openclaw\workspace\v19_final_pool.json'

START_DATE = '2026-05-06'
END_DATE = '2026-05-09'
BATCH_SIZE = 50
SLEEP_BETWEEN_BATCHES = 1.5  # seconds

# 指标：增加涨跌幅和换手率
INDICATORS = 'OPEN,HIGH,LOW,CLOSE,VOLUME,PCTCHG,TURN'


def code_to_choice(code: str) -> str:
    """纯数字代码转 Choice 格式"""
    if code.startswith('6') or code.startswith('9'):
        return f'{code}.SH'
    elif code.startswith('8') or code.startswith('4'):
        # 北交所 8/4 开头也用 .BJ，但 Choice 可能用 .SH
        # 实际上 Choice 对北交所用 .BJ
        return f'{code}.BJ'
    else:
        # 0, 1, 2, 3 开头 = 深交所
        return f'{code}.SZ'


def choice_to_data_key(choice_code: str) -> str:
    """Choice 格式转数据 dict key，如 000001.SZ → sz000001"""
    parts = choice_code.split('.')
    code = parts[0]
    exchange = parts[1].lower() if len(parts) > 1 else 'sz'
    return f'{exchange}{code}'


def main():
    print('=' * 60)
    print('V19 股票池 K 线增量更新')
    print(f'日期范围: {START_DATE} ~ {END_DATE}')
    print('=' * 60)

    # 1. 加载 V19 股票池
    with open(V19_FILE, 'r', encoding='utf-8') as f:
        v19_codes = json.load(f)
    print(f'V19 股票池: {len(v19_codes)} 只')

    # 2. 加载现有 K 线数据
    print(f'加载现有 K 线数据: {KLINE_FILE}')
    with open(KLINE_FILE, 'r', encoding='utf-8') as f:
        kline_data = json.load(f)
    print(f'现有数据: {len(kline_data)} 只股票')

    # 3. 初始化 Choice API
    print('初始化 Choice API...')
    from EmQuantAPI import c
    from config import CHOICE_USERNAME, CHOICE_PASSWORD

    login_result = c.start(f'USERNAME={CHOICE_USERNAME},PASSWORD={CHOICE_PASSWORD}')
    if login_result.ErrorCode != 0 and 'online' not in login_result.ErrorMsg.lower():
        print(f'[ERROR] Choice 登录失败: {login_result.ErrorMsg}')
        sys.exit(1)
    print('Choice API 连接成功')

    # 4. 分批获取数据
    choice_codes = [code_to_choice(code) for code in v19_codes]
    total_batches = (len(choice_codes) + BATCH_SIZE - 1) // BATCH_SIZE
    updated_count = 0
    error_count = 0
    new_records_total = 0

    for batch_idx in range(total_batches):
        start_i = batch_idx * BATCH_SIZE
        end_i = min(start_i + BATCH_SIZE, len(choice_codes))
        batch = choice_codes[start_i:end_i]

        batch_str = ','.join(batch)

        print(f'\n[Batch {batch_idx + 1}/{total_batches}] '
              f'股票 {start_i + 1}-{end_i}/{len(choice_codes)} '
              f'({len(batch)} 只)')

        try:
            data = c.csd(batch_str, INDICATORS, START_DATE, END_DATE, '')

            if data.ErrorCode != 0:
                print(f'  [ERROR] CSD 返回错误: {data.ErrorMsg}')
                error_count += len(batch)
                time.sleep(2)
                continue

            dates = data.Dates if hasattr(data, 'Dates') else []
            indicators_list = data.Indicators if hasattr(data, 'Indicators') else []

            if not dates:
                print(f'  [WARN] 无日期数据（可能非交易日）')
                continue

            # 解析每只股票的数据
            # data.Data 格式: {stock_code: [[val_per_date], [val_per_date], ...]}
            # 每个子列表对应一个指标，里面是每个日期的值
            batch_updated = 0
            for cc in batch:
                data_key = choice_to_data_key(cc)
                stock_raw = data.Data.get(cc, []) if hasattr(data, 'Data') and isinstance(data.Data, dict) else []

                if not stock_raw or len(stock_raw) < 5:
                    # 可能这只股票没有数据
                    continue

                # 指标顺序与 INDICATORS 一致: OPEN,HIGH,LOW,CLOSE,VOLUME,PCTCHG,TURN
                try:
                    opens = stock_raw[0]  # OPEN
                    highs = stock_raw[1]  # HIGH
                    lows = stock_raw[2]   # LOW
                    closes = stock_raw[3] # CLOSE
                    volumes = stock_raw[4] # VOLUME
                    pctchgs = stock_raw[5] if len(stock_raw) > 5 else [None] * len(dates)
                    turns = stock_raw[6] if len(stock_raw) > 6 else [None] * len(dates)
                except IndexError:
                    continue

                # 构建 K 线记录
                new_records = []
                for i, date_str in enumerate(dates):
                    # Choice 日期格式可能是 "2026-05-07" 或 "/Date(...)/"
                    if isinstance(date_str, str) and len(date_str) >= 10:
                        d = date_str[:10]
                    else:
                        continue

                    vol = volumes[i] if i < len(volumes) else 0
                    # 跳过成交量为 0 或 None 的日期（停牌）
                    if vol is None or vol == 0:
                        continue

                    record = {
                        'date': d,
                        'open': round(float(opens[i]), 2) if i < len(opens) and opens[i] is not None else None,
                        'high': round(float(highs[i]), 2) if i < len(highs) and highs[i] is not None else None,
                        'low': round(float(lows[i]), 2) if i < len(lows) and lows[i] is not None else None,
                        'close': round(float(closes[i]), 2) if i < len(closes) and closes[i] is not None else None,
                        'volume': float(vol),
                    }
                    # 添加涨跌幅和换手率
                    if i < len(pctchgs) and pctchgs[i] is not None:
                        record['pctChg'] = round(float(pctchgs[i]), 2)
                    if i < len(turns) and turns[i] is not None:
                        record['turn'] = round(float(turns[i]), 4)

                    new_records.append(record)

                if not new_records:
                    continue

                # 合并到现有数据
                if data_key not in kline_data:
                    kline_data[data_key] = []

                # 用日期去重合并
                existing_dates = {r['date'] for r in kline_data[data_key]}
                added = [r for r in new_records if r['date'] not in existing_dates]
                if added:
                    kline_data[data_key].extend(added)
                    # 按日期排序
                    kline_data[data_key].sort(key=lambda x: x['date'])
                    batch_updated += 1
                    new_records_total += len(added)

            updated_count += batch_updated
            print(f'  本批更新: {batch_updated} 只, 新增 {sum(1 for cc in batch if choice_to_data_key(cc) in kline_data)} 条记录')

        except Exception as e:
            print(f'  [ERROR] 批次异常: {e}')
            error_count += len(batch)

        # 频率限制
        if batch_idx < total_batches - 1:
            time.sleep(SLEEP_BETWEEN_BATCHES)

    # 5. 保存
    print(f'\n保存更新后的 K 线数据...')
    with open(KLINE_FILE, 'w', encoding='utf-8') as f:
        json.dump(kline_data, f, ensure_ascii=False)
    print(f'已保存到: {KLINE_FILE}')

    # 6. 汇总
    print('\n' + '=' * 60)
    print('更新完成！')
    print(f'  总股票数: {len(kline_data)}')
    print(f'  本次更新: {updated_count} 只')
    print(f'  新增记录: {new_records_total} 条')
    print(f'  错误/跳过: {error_count} 只')
    print(f'  日期范围: {START_DATE} ~ {END_DATE}')

    # 验证最新日期
    sample_key = list(kline_data.keys())[0]
    if kline_data[sample_key]:
        last_date = kline_data[sample_key][-1]['date']
        print(f'  验证 - 第一只股票最新日期: {last_date}')

    # 停止 Choice 连接
    try:
        c.stop()
    except:
        pass


if __name__ == '__main__':
    main()
