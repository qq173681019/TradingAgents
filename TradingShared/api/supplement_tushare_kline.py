"""用 Tushare 补充 Choice 采集的股票数据（完整K线 + 技术指标）"""
import json
import os
import time
from datetime import datetime, timedelta

import pandas as pd
import tushare as ts

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SHARED_DIR, 'data')
DATA_FILE = os.path.join(DATA_DIR, 'comprehensive_stock_data.json')

TUSHARE_TOKEN = "4a1bd8dea786a5525663fafcf729a2b081f9f66145a0671c8adf2f28"

KLINE_DAYS = 90
RATE_LIMIT = 45  # tushare限制50次/分钟，安全起见用45


def calculate_technical_indicators(df):
    """从K线DataFrame计算技术指标（tushare列名: open/high/low/close/vol）"""
    if df is None or len(df) < 5:
        return None
    try:
        # 统一列名：vol -> volume
        if 'vol' in df.columns:
            df = df.rename(columns={'vol': 'volume'})

        current_price = float(df['close'].iloc[-1])

        ma5 = float(df['close'].rolling(5).mean().iloc[-1]) if len(df) >= 5 else current_price
        ma10 = float(df['close'].rolling(10).mean().iloc[-1]) if len(df) >= 10 else current_price
        ma20 = float(df['close'].rolling(20).mean().iloc[-1]) if len(df) >= 20 else current_price
        ma60 = float(df['close'].rolling(60).mean().iloc[-1]) if len(df) >= 60 else current_price

        # RSI 14
        if len(df) >= 14:
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = float((100 - (100 / (1 + rs))).iloc[-1])
        else:
            rsi = 50.0

        # MACD
        if len(df) >= 26:
            ema12 = df['close'].ewm(span=12, adjust=False).mean()
            ema26 = df['close'].ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            macd = float(macd_line.iloc[-1])
            signal = float(signal_line.iloc[-1])
        else:
            macd = 0.0
            signal = 0.0

        # 量比
        volume_ratio = 1.0
        if len(df) >= 5:
            vol_ma5 = df['volume'].rolling(5).mean().iloc[-1]
            if vol_ma5 > 0:
                volume_ratio = float(df['volume'].iloc[-1] / vol_ma5)

        return {
            'current_price': current_price,
            'ma5': ma5,
            'ma10': ma10,
            'ma20': ma20,
            'ma60': ma60,
            'rsi': rsi if not pd.isna(rsi) else 50.0,
            'macd': macd,
            'signal': signal,
            'volume_ratio': volume_ratio,
            'data_source': 'tushare_calculated'
        }
    except Exception as e:
        print(f"    [WARN] tech calc failed: {e}")
        return None


def main():
    print("=" * 60)
    print("Tushare K-line supplement")
    print("=" * 60)

    if not os.path.exists(DATA_FILE):
        print(f"[FAIL] data file not found: {DATA_FILE}")
        return

    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        cache_data = json.load(f)

    stocks = cache_data.get('stocks', {})
    total = len(stocks)
    print(f"Loaded {total} stocks")

    # 找出缺少K线的股票
    need_supplement = []
    for code, info in stocks.items():
        kline = info.get('kline_data', {}).get('daily', [])
        if len(kline) < 5:
            need_supplement.append(code)

    print(f"Need supplement: {len(need_supplement)}")
    if not need_supplement:
        print("Nothing to do.")
        return

    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()

    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=KLINE_DAYS)).strftime('%Y%m%d')

    def to_ts_code(code):
        if code.startswith(('000', '001', '002', '300', '301')):
            return f"{code}.SZ"
        elif code.startswith(('4', '8')):
            return f"{code}.BJ"
        else:
            return f"{code}.SH"

    success = 0
    fail = 0
    request_count = 0

    for idx, code in enumerate(need_supplement):
        ts_code = to_ts_code(code)

        # 频率控制：每45次休息65秒
        if request_count > 0 and request_count % RATE_LIMIT == 0:
            print(f"  [INFO] Rate limit ({request_count} requests), waiting 65s...")
            time.sleep(65)

        try:
            df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            request_count += 1

            if df is not None and not df.empty:
                df = df.sort_values('trade_date')

                kline_list = []
                for _, row in df.iterrows():
                    kline_list.append({
                        'date': row['trade_date'],
                        'open': float(row['open']) if pd.notna(row.get('open')) else None,
                        'high': float(row['high']) if pd.notna(row.get('high')) else None,
                        'low': float(row['low']) if pd.notna(row.get('low')) else None,
                        'close': float(row['close']) if pd.notna(row.get('close')) else None,
                        'volume': float(row['vol']) if pd.notna(row.get('vol')) else None
                    })

                stocks[code]['kline_data']['daily'] = kline_list

                tech = calculate_technical_indicators(df)
                if tech:
                    stocks[code]['tech_data'] = tech

                stocks[code]['data_source'] = 'choice_tushare'
                success += 1
            else:
                fail += 1

        except Exception as e:
            fail += 1
            # 如果是频率限制错误，等待后重试一次
            if 'freq' in str(e).lower() or 'rate' in str(e).lower() or '50' in str(e):
                print(f"  [INFO] Rate limit hit, waiting 65s...")
                time.sleep(65)

        # 每100只打印进度
        if (idx + 1) % 100 == 0:
            progress = (idx + 1) / len(need_supplement) * 100
            print(f"  [{idx+1}/{len(need_supplement)}] ({progress:.0f}%) success={success} fail={fail}")

    print(f"\n{'=' * 60}")
    print(f"Done: {success} success, {fail} fail, {total} total")

    cache_data['metadata']['supplement_source'] = 'tushare'
    cache_data['metadata']['supplement_time'] = datetime.now().isoformat()
    cache_data['metadata']['supplement_kline_days'] = KLINE_DAYS

    tech_ok = sum(1 for s in stocks.values() if s.get('tech_data'))
    print(f"Tech indicators: {tech_ok}/{total}")

    print(f"Saving...")
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)

    file_size = os.path.getsize(DATA_FILE)
    print(f"[OK] Saved: {file_size / 1024 / 1024:.2f} MB")


if __name__ == '__main__':
    main()
