"""
Choice SDK - A股竞价排行
获取当前A股主板股票的竞价数据并进行排行
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta

import pandas as pd

# 添加 TradingShared 到路径，以便导入 config
script_dir = os.path.dirname(os.path.abspath(__file__))
tradingshared_root = os.path.dirname(script_dir)
if tradingshared_root not in sys.path:
    sys.path.insert(0, tradingshared_root)

try:
    from config import CHOICE_PASSWORD, CHOICE_USERNAME
except ImportError:
    try:
        from TradingShared.config import CHOICE_PASSWORD, CHOICE_USERNAME
    except ImportError:
        print("无法导入 config，请检查路径")
        sys.exit(1)

from EmQuantAPI import c


def setup_choice_dll_path():
    """设置 Choice DLL 路径以避免 WinError 87"""
    import ctypes
    dll_dir = os.path.join(tradingshared_root, "libs", "windows")
    
    if not os.path.exists(dll_dir):
        return False
    
    if dll_dir not in os.environ.get('PATH', ''):
        os.environ['PATH'] = dll_dir + os.pathsep + os.environ.get('PATH', '')
    
    if sys.version_info >= (3, 8):
        try:
            os.add_dll_directory(dll_dir)
        except (OSError, AttributeError):
            pass
    
    try:
        import platform
        is_64bit = platform.architecture()[0] == '64bit'
        dll_name = "EmQuantAPI_x64.dll" if is_64bit else "EmQuantAPI.dll"
        dll_path = os.path.join(dll_dir, dll_name)
        
        if not os.path.exists(dll_path):
            return False
        
        if sys.version_info >= (3, 8):
            LOAD_WITH_ALTERED_SEARCH_PATH = 0x00000008
            ctypes.CDLL(dll_path, winmode=LOAD_WITH_ALTERED_SEARCH_PATH)
        else:
            ctypes.CDLL(dll_path)
        return True
    except Exception:
        return False

def login_callback(msg):
    decoded_msg = msg.decode('utf-8', errors='ignore')
    print(f"[登录回调] {decoded_msg}")
    return 1

def get_mainboard_stocks():
    """获取主板股票列表"""
    print("正在获取主板股票列表...")
    end_date = datetime.now().strftime("%Y-%m-%d")
    mainboard_stocks = []
    stock_names = {}
    
    try:
        sector_data = c.sector("001004", end_date)
        if sector_data.ErrorCode == 0 and hasattr(sector_data, 'Data'):
            raw_data = sector_data.Data
            for i in range(0, len(raw_data), 2):
                if i + 1 < len(raw_data):
                    code = raw_data[i]
                    name = raw_data[i + 1]
                    if '.' in code and (code.endswith('.SH') or code.endswith('.SZ')):
                        # 过滤主板
                        code_part = code.split('.')[0]
                        code_prefix = code_part[:3]
                        if code_prefix in ['600', '601', '603', '605', '000', '001', '002'] and 'ST' not in name:
                            mainboard_stocks.append(code)
                            stock_names[code] = name
    except Exception as e:
        print(f"获取股票列表异常: {e}")
    
    return mainboard_stocks, stock_names

def main():
    print("="*60)
    print("Choice SDK - A股竞价排行工具")
    print("="*60)
    
    if not setup_choice_dll_path():
        print("❌ Choice DLL 环境设置失败")
        return

    login_options = f"username={CHOICE_USERNAME},password={CHOICE_PASSWORD}"
    result = c.start(login_options, logcallback=login_callback)
    if result.ErrorCode != 0:
        print(f"❌ Choice连接失败: {result.ErrorMsg}")
        return
    print("✅ Choice连接成功")

    try:
        # 1. 获取股票列表
        stocks, names = get_mainboard_stocks()
        if not stocks:
            print("❌ 未获取到股票列表")
            return
        print(f"✅ 获取到 {len(stocks)} 只主板股票")

        # 2. 获取竞价快照数据
        # 竞价期间关键指标：
        # OPEN: 虚拟开盘价 (竞价期间的匹配价)
        # PRECLOSE: 昨收价
        # VOLUME: 虚拟成交量 (竞价期间的匹配量)
        # AMOUNT: 虚拟成交额
        # CHGPCT: 涨跌幅
        # TURNOVER: 换手率
        indicators = "NAME,PRECLOSE,OPEN,VOLUME,AMOUNT,CHGPCT,TURNOVER"
        
        print(f"\n正在获取竞价快照数据 (共 {len(stocks)} 只)...")
        
        all_data = []
        batch_size = 400 # csqsnapshot 限制每次请求数量
        
        for i in range(0, len(stocks), batch_size):
            batch_stocks = stocks[i:i+batch_size]
            batch_str = ",".join(batch_stocks)
            
            print(f"  进度: {i}/{len(stocks)}...")
            snapshot = c.csqsnapshot(batch_str, indicators)
            
            if snapshot.ErrorCode == 0 and hasattr(snapshot, 'Data'):
                for code in batch_stocks:
                    if code in snapshot.Data:
                        vals = snapshot.Data[code]
                        # 过滤掉没有竞价数据的股票 (OPEN为0或None)
                        if vals[2] and vals[2] > 0:
                            data_row = {
                                "代码": code,
                                "名称": names.get(code, vals[0]),
                                "昨收": vals[1],
                                "竞价价": vals[2],
                                "竞价量(手)": vals[3] / 100 if vals[3] else 0,
                                "竞价额(万)": vals[4] / 10000 if vals[4] else 0,
                                "涨幅(%)": vals[5] * 100 if vals[5] else 0,
                                "换手(%)": vals[6] if vals[6] else 0
                            }
                            all_data.append(data_row)
            
            time.sleep(0.1) # 避免频率限制

        if not all_data:
            print("\n⚠️ 未获取到有效的竞价数据。请确保在交易日 9:15 - 9:30 之间运行。")
            return

        # 3. 排序并展示
        df = pd.DataFrame(all_data)
        
        # 按涨幅排序
        df_sorted = df.sort_values(by="涨幅(%)", ascending=False)
        
        print("\n" + "="*80)
        print(f"🔥 A股竞价涨幅排行 (前20名) - {datetime.now().strftime('%H:%M:%S')}")
        print("="*80)
        print(df_sorted.head(20).to_string(index=False))
        
        # 按竞价额排序
        df_volume = df.sort_values(by="竞价额(万)", ascending=False)
        print("\n" + "="*80)
        print(f"💰 A股竞价成交额排行 (前20名) - {datetime.now().strftime('%H:%M:%S')}")
        print("="*80)
        print(df_volume.head(20).to_string(index=False))

        # 4. 保存结果
        output_dir = os.path.join(tradingshared_root, "data")
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f"call_auction_ranking_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        df_sorted.to_csv(output_file, index=False, encoding='utf_8_sig')
        print(f"\n✅ 排行数据已保存至: {output_file}")

    finally:
        c.stop()
        print("\nChoice SDK 已断开连接")

if __name__ == "__main__":
    main()
