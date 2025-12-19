"""测试Choice SDK - 获取A股主板股票50日K线数据"""
import json
import os
import sys
from datetime import datetime, timedelta

from config import CHOICE_PASSWORD, CHOICE_USERNAME


# 修复 WinError 87: 预加载依赖 DLL 并设置正确的加载模式
def setup_choice_dll_path():
    """设置 Choice DLL 路径以避免 WinError 87"""
    import ctypes

    # Choice DLL 在项目根目录的 libs/windows 目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # 从 TradingShared/api 向上两级到达项目根目录
    project_root = os.path.dirname(os.path.dirname(script_dir))
    dll_dir = os.path.join(project_root, "libs", "windows")
    
    if not os.path.exists(dll_dir):
        print(f"警告: Choice DLL 目录不存在: {dll_dir}")
        print(f"  当前脚本目录: {script_dir}")
        print(f"  项目根目录: {project_root}")
        return False
    
    print(f"找到 Choice DLL 目录: {dll_dir}")
    
    # 方法1: 添加到 PATH（适用于所有 Python 版本）
    if dll_dir not in os.environ.get('PATH', ''):
        os.environ['PATH'] = dll_dir + os.pathsep + os.environ.get('PATH', '')
        print(f"✓ 已添加到 PATH: {dll_dir}")
    
    # 方法2: Python 3.8+ 的 DLL 目录（推荐）
    if sys.version_info >= (3, 8):
        try:
            os.add_dll_directory(dll_dir)
            print(f"✓ 已添加 DLL 搜索目录 (Python 3.8+): {dll_dir}")
        except (OSError, AttributeError) as e:
            print(f"! 添加 DLL 搜索目录失败: {e}")
    
    # 方法3: 预加载 Choice DLL 及其依赖项（最可靠）
    try:
        # 确定 DLL 文件名（32位或64位）
        import platform
        is_64bit = platform.architecture()[0] == '64bit'
        dll_name = "EmQuantAPI_x64.dll" if is_64bit else "EmQuantAPI.dll"
        dll_path = os.path.join(dll_dir, dll_name)
        
        if not os.path.exists(dll_path):
            print(f"! DLL 文件不存在: {dll_path}")
            return False
        
        print(f"准备加载: {dll_name}")
        
        # 使用 LOAD_WITH_ALTERED_SEARCH_PATH 模式加载 DLL
        # 这会让系统从 DLL 所在目录搜索依赖项
        if sys.version_info >= (3, 8):
            # Python 3.8+ 使用 winmode 参数
            import ctypes.wintypes
            LOAD_WITH_ALTERED_SEARCH_PATH = 0x00000008
            ctypes.CDLL(dll_path, winmode=LOAD_WITH_ALTERED_SEARCH_PATH)
            print(f"✓ 已预加载 DLL (winmode): {dll_name}")
        else:
            # Python 3.7 及以下
            ctypes.CDLL(dll_path)
            print(f"✓ 已预加载 DLL: {dll_name}")
        
        return True
        
    except Exception as e:
        print(f"! 预加载 DLL 失败: {e}")
        import traceback
        traceback.print_exc()
        return False

print("="*60)
print("正在初始化 Choice SDK 环境...")
print("="*60)

if not setup_choice_dll_path():
    print("\n❌ Choice DLL 环境设置失败")
    print("请确保:")
    print("  1. libs/windows 目录存在")
    print("  2. EmQuantAPI_x64.dll (或 EmQuantAPI.dll) 文件存在")
    print("  3. 所有依赖的 DLL 文件都在 libs/windows 目录中")
    sys.exit(1)

print("\n✓ Choice SDK 环境设置完成，开始导入 EmQuantAPI...")

from EmQuantAPI import c

print("✓ EmQuantAPI 导入成功\n")


def login_callback(msg):
    """捕获Choice登录回调信息"""
    decoded_msg = msg.decode('utf-8', errors='ignore')
    print(f"[登录回调] {decoded_msg}")
    return 1

def check_csd_available():
    """检查CSD接口是否可用（配额是否充足）"""
    print("\n[检测] 测试CSD接口可用性...")
    
    # 测试一个简单的CSD调用
    test_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    data = c.csd("000001.SZ", "CLOSE", test_date, test_date, "")
    
    if data.ErrorCode == 0:
        print("  ✅ CSD接口可用 - 将使用CSD接口（序列数据）")
        return True
    elif data.ErrorCode == 10001012:
        print(f"\n{'='*70}")
        print(f"  ⚠️  ⚠️  ⚠️  CSD接口配额不足 (错误码: {data.ErrorCode})  ⚠️  ⚠️  ⚠️")
        print(f"{'='*70}")
        print(f"  配额类型: 周配额")
        print(f"  当前状态: 已用完")
        print(f"  重置时间: 下周一 00:00")
        print(f"  替代方案: 将使用CSS接口（仅收盘价数据）")
        print(f"")
        print(f"  ⚠️  重要提示：")
        print(f"     CSS接口只能获取CLOSE和PRECLOSE数据")
        print(f"     缺少OPEN/HIGH/LOW/VOLUME，无法计算技术指标")
        print(f"     建议等待配额重置后重新采集数据")
        print(f"{'='*70}\n")
        return False
    else:
        print(f"  ⚠️  CSD接口错误 ({data.ErrorCode}: {data.ErrorMsg}) - 将切换到CSS接口")
        return False

def get_kline_data_css(stock_code, start_date, end_date):
    """使用CSS接口获取历史K线数据（CSD配额不足时的备用方案）
    
    CSS接口限制:
    - 只能获取: CLOSE, PRECLOSE, PE, PB, BPS
    - 不能获取: OPEN, HIGH, LOW, VOLUME (返回None)
    - 需要逐日循环查询，使用 tradeDate 参数
    
    Args:
        stock_code: 股票代码，如 "000001.SZ"
        start_date: 开始日期 "YYYY-MM-DD"
        end_date: 结束日期 "YYYY-MM-DD"
    
    Returns:
        dict: 包含dates、indicators、data的字典，格式与CSD返回相同
        None: 如果获取失败
    """
    import time

    # 生成日期列表（跳过周末）
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    
    date_list = []
    current_dt = start_dt
    while current_dt <= end_dt:
        # 跳过周末
        if current_dt.weekday() < 5:  # 0-4是周一到周五
            date_list.append(current_dt.strftime("%Y-%m-%d"))
        current_dt += timedelta(days=1)
    
    # 收集数据
    dates = []
    close_prices = []
    preclose_prices = []
    
    for date_str in date_list:
        try:
            # CSS查询：只获取CLOSE和PRECLOSE（其他字段CSS不支持）
            data = c.css(stock_code, "CLOSE,PRECLOSE", f"tradeDate={date_str}")
            
            if data.ErrorCode == 0 and stock_code in data.Data:
                stock_data = data.Data[stock_code]
                close = stock_data[0] if len(stock_data) > 0 else None
                preclose = stock_data[1] if len(stock_data) > 1 else None
                
                # 只保存有效数据的日期
                if close is not None:
                    dates.append(date_str)
                    close_prices.append(close)
                    preclose_prices.append(preclose if preclose is not None else close)
            
            # 避免频率限制
            time.sleep(0.05)
            
        except Exception as e:
            continue
    
    # 如果没有获取到任何数据，返回None
    if not dates:
        return None
    
    # 构造与CSD相同的返回格式
    result = {
        "dates": dates,
        "indicators": ["CLOSE", "PRECLOSE"],
        "data": {
            "CLOSE": close_prices,
            "PRECLOSE": preclose_prices
        }
    }
    
    return result

def calculate_technical_indicators_from_kline(kline_data):
    """从K线数据计算技术指标
    
    Args:
        kline_data: K线数据列表，每项包含 {date, open, high, low, close, volume}
    
    Returns:
        dict: 技术指标数据 {current_price, ma5, ma10, ma20, ma60, rsi, macd, signal, volume_ratio}
    """
    try:
        import pandas as pd
        
        if not kline_data or len(kline_data) < 5:
            return None
        
        # 转换为DataFrame
        df = pd.DataFrame(kline_data)
        
        # 检查是否有close数据
        if 'close' not in df.columns:
            return None
        
        # 确保数值类型
        for col in ['close', 'volume', 'open', 'high', 'low']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 按日期升序排序
        if 'date' in df.columns:
            df = df.sort_values('date')
        
        if df.empty or len(df) < 5:
            return None
        
        # 当前价格
        current_price = float(df['close'].iloc[-1])
        
        # 检查数据质量：如果只有1条数据，无法计算技术指标
        if len(df) < 5:
            print(f"    ⚠️  数据不足（只有{len(df)}条），无法计算技术指标")
            return None
        
        # 计算均线
        ma5 = float(df['close'].rolling(window=5).mean().iloc[-1]) if len(df) >= 5 else current_price
        ma10 = float(df['close'].rolling(window=10).mean().iloc[-1]) if len(df) >= 10 else current_price
        ma20 = float(df['close'].rolling(window=20).mean().iloc[-1]) if len(df) >= 20 else current_price
        ma60 = float(df['close'].rolling(window=60).mean().iloc[-1]) if len(df) >= 60 else current_price
        
        # 计算RSI (14日)
        if len(df) >= 14:
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs.iloc[-1]))
        else:
            rsi = 50
        
        # 计算MACD
        if len(df) >= 26:
            ema12 = df['close'].ewm(span=12, adjust=False).mean()
            ema26 = df['close'].ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            macd = float(macd_line.iloc[-1])
            signal = float(signal_line.iloc[-1])
        else:
            macd = 0
            signal = 0
        
        # 计算量比
        if len(df) >= 5:
            vol_ma5 = df['volume'].rolling(window=5).mean().iloc[-1]
            volume_ratio = float(df['volume'].iloc[-1] / vol_ma5) if vol_ma5 > 0 else 1.0
        else:
            volume_ratio = 1.0
        
        return {
            'current_price': current_price,
            'ma5': ma5,
            'ma10': ma10,
            'ma20': ma20,
            'ma60': ma60,
            'rsi': float(rsi) if not pd.isna(rsi) else 50,
            'macd': macd,
            'signal': signal,
            'volume_ratio': volume_ratio,
            'data_source': 'choice_calculated'
        }
        
    except Exception as e:
        print(f"    ⚠️  计算技术指标失败: {e}")
        return None

def check_cache_date():
    """检查缓存数据日期，如果是今天的数据则返回True"""
    cache_file = "data/choice_all_stocks.json"
    if not os.path.exists(cache_file):
        return False
    
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        # 检查元数据中的采集日期
        if 'metadata' in cache_data and 'collection_date' in cache_data['metadata']:
            cache_date = cache_data['metadata']['collection_date']
            today = datetime.now().strftime("%Y-%m-%d")
            
            if cache_date == today:
                print(f"✅ 检测到今日缓存数据 ({cache_date})，跳过数据采集")
                return True
        return False
    except Exception as e:
        print(f"⚠️  缓存检查失败: {e}")
        return False

def main():
    print("="*60)
    print("Choice SDK - A股主板股票数据采集（智能模式）")
    print("="*60)
    
    # 检查缓存
    if check_cache_date():
        print("\n数据已是最新，无需重复采集")
        return
    
    # 1. 初始化Choice SDK
    print("\n[1/6] 初始化Choice SDK...")
    print(f"使用账号密码登录: {CHOICE_USERNAME}")
    login_options = f"username={CHOICE_USERNAME},password={CHOICE_PASSWORD}"
    result = c.start(login_options, logcallback=login_callback)
    if result.ErrorCode != 0:
        print(f"❌ Choice连接失败: {result.ErrorMsg}")
        return
    print("✅ Choice连接成功")
    
    # ==================== K线数据获取策略 ====================
    # 获取：150个交易日（约180自然日）- 确保有足够数据计算MA120等长期指标
    # 使用：根据具体需求使用不同长度
    #   - 短期指标(RSI/MACD/MA5/MA10/MA20): 使用最近30-60天
    #   - 中期指标(MA60): 使用最近90天
    #   - 长期指标(MA120): 使用全部150天
    #   - 筹码健康度: 使用最近30-60天
    # 更新：增量更新 - 只获取最后更新日期到今天的新数据
    # =========================================================
    
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")  # 150个交易日约180个自然日
    
    # 2. 获取A股全部主板股票代码列表（排除ST和创业板）
    print("\n[2/5] 获取主板股票列表...")
    
    mainboard_stocks = []
    
    # 方法1：尝试使用板块API获取
    print("  方法1: 尝试从板块API获取...")
    try:
        sector_data = c.sector("001004", end_date)
        print(f"  sector() 返回: ErrorCode={sector_data.ErrorCode}")
        
        if sector_data.ErrorCode == 0 and hasattr(sector_data, 'Data') and sector_data.Data:
            raw_data = sector_data.Data
            print(f"  获取到 {len(raw_data)} 个数据项")
            print(f"  示例数据: {raw_data[:5]}")
            
            # sector()返回的是 [代码1, 名称1, 代码2, 名称2, ...] 的格式
            # 需要提取偶数索引的股票代码
            all_codes = []
            stock_names = {}  # 同时建立代码到名称的映射
            
            for i in range(0, len(raw_data), 2):
                if i + 1 < len(raw_data):
                    code = raw_data[i]
                    name = raw_data[i + 1]
                    # 验证是股票代码（包含.SH或.SZ）
                    if '.' in code and (code.endswith('.SH') or code.endswith('.SZ')):
                        all_codes.append(code)
                        stock_names[code] = name
            
            print(f"  解析出 {len(all_codes)} 只股票代码")
            print(f"  股票代码示例: {all_codes[:3]}")
            
            mainboard_stocks = []
            mainboard_stock_names = {}  # 保存主板股票的名称映射
            filtered_st = 0
            filtered_board = 0
            invalid_format = 0
            
            for stock_code in all_codes:
                # 验证股票代码格式（已经在解析时验证过了，这里再次确认）
                if '.' not in stock_code or len(stock_code.split('.')) != 2:
                    invalid_format += 1
                    continue
                
                code_part, exchange = stock_code.split('.')
                if exchange not in ['SH', 'SZ'] or len(code_part) != 6:
                    invalid_format += 1
                    continue
                
                # 检查代码前缀（只保留主板）
                code_prefix = code_part[:3]
                
                # 排除创业板（300）、科创板（688）、北交所（8开头、4开头）
                if code_prefix in ['300', '688'] or code_part[0] in ['8', '4']:
                    filtered_board += 1
                    continue
                
                # 只保留主板代码
                if code_prefix not in ['600', '601', '603', '605', '000', '001', '002']:
                    filtered_board += 1
                    continue
                
                # 检查是否ST股票（使用之前解析的名称）
                stock_name = stock_names.get(stock_code, "")
                if 'ST' in stock_name:
                    filtered_st += 1
                    continue
                
                mainboard_stocks.append(stock_code)
                mainboard_stock_names[stock_code] = stock_name  # 保存名称
            
            print(f"✅ 方法1成功: 获取到 {len(mainboard_stocks)} 只主板股票（已排除ST）")
            print(f"   已排除: {filtered_st} 只ST股票, {filtered_board} 只非主板股票, {invalid_format} 只格式错误")
        else:
            print(f"⚠️  板块数据获取失败")
            
    except Exception as e:
        print(f"⚠️  方法1异常: {e}")
    
    # 如果方法1失败，使用方法2：边获取边过滤
    mainboard_stock_names = {}  # 初始化名称映射
    if not mainboard_stocks:
        print("\n  方法2: 边获取边过滤（智能代码生成 + 实时ST过滤）...")
        candidate_codes = []
        
        # 沪市主板：只生成常见的前缀段
        # 600000-600999 (老主板)
        for i in range(1000):
            candidate_codes.append(f"600{i:03d}.SH")
        # 601000-601999 (大盘蓝筹)  
        for i in range(1000):
            candidate_codes.append(f"601{i:03d}.SH")
        
        # 深市主板：000000-002999
        for prefix in ['000', '001', '002']:
            for i in range(1000):
                candidate_codes.append(f"{prefix}{i:03d}.SZ")
        
        print(f"  生成 {len(candidate_codes)} 个候选代码")
        print(f"  将在获取K线数据时自动过滤:")
        print(f"    ✓ 不存在的股票代码")
        print(f"    ✓ ST股票（通过股票名称识别）")
        print(f"    ✓ 无交易数据的股票")
        print(f"  预计最终有效股票: ~1800-2500 只\n")
        mainboard_stocks = candidate_codes
        
        # 批量获取股票名称（用于ST过滤和保存）
        print("  正在批量获取股票名称...")
        batch_size = 100
        names_fetched = 0
        for batch_start in range(0, len(candidate_codes), batch_size):
            batch_end = min(batch_start + batch_size, len(candidate_codes))
            batch_codes = candidate_codes[batch_start:batch_end]
            batch_codes_str = ",".join(batch_codes)
            
            try:
                name_data = c.css(batch_codes_str, "SEC_NAME", "")
                if name_data.ErrorCode == 0 and hasattr(name_data, 'Data'):
                    for code in batch_codes:
                        if code in name_data.Data and name_data.Data[code]:
                            name = name_data.Data[code][0] if isinstance(name_data.Data[code], list) else name_data.Data[code]
                            if name:
                                mainboard_stock_names[code] = name
                                names_fetched += 1
            except Exception as e:
                pass
            
            import time
            time.sleep(0.05)  # 避免频率限制
        
        print(f"  ✅ 获取到 {names_fetched} 只股票名称")
    
    # 3. 预过滤股票（排除新股、退市股）并获取基础信息（上市日期、行业）
    print(f"\n[3/5] 预过滤股票并获取基础信息...")
    print(f"  原始候选: {len(mainboard_stocks)} 只（ST股票已在第2步排除）")
    
    filtered_stocks = []
    stock_basic_infos = {}  # 存储基础信息：上市日期、行业
    
    filter_stats = {
        'new_stocks': 0,
        'delisted': 0,
        'no_data': 0,
        'valid': 0
    }
    
    # 批量获取股票基本信息（每次100只）
    batch_size = 100
    for batch_start in range(0, len(mainboard_stocks), batch_size):
        batch_end = min(batch_start + batch_size, len(mainboard_stocks))
        batch_codes = mainboard_stocks[batch_start:batch_end]
        batch_codes_str = ",".join(batch_codes)
        
        if (batch_start // batch_size) % 10 == 0:
            progress = (batch_start / len(mainboard_stocks)) * 100
            print(f"  检查进度: {batch_start}/{len(mainboard_stocks)} ({progress:.1f}%)")
        
        try:
            # 获取上市日期、退市日期
            # 注意：SW1等行业指标可能需要额外权限或不同接口，暂时移除以避免10000013错误
            info_data = c.css(batch_codes_str, "LISTDATE,DELISTDATE", "")
            
            if info_data.ErrorCode == 0 and hasattr(info_data, 'Data'):
                for stock_code in batch_codes:
                    if stock_code not in info_data.Data:
                        filter_stats['no_data'] += 1
                        continue
                    
                    stock_info = info_data.Data[stock_code]
                    
                    # 检查上市日期（排除新股：上市不足70天）
                    list_date_str = stock_info[0] if len(stock_info) > 0 and stock_info[0] else None
                    formatted_list_date = None
                    
                    if list_date_str:
                        try:
                            # 处理日期格式：可能是 "1991/4/3" 或 "1991-04-03"
                            if '/' in list_date_str:
                                list_date = datetime.strptime(list_date_str, "%Y/%m/%d")
                                formatted_list_date = list_date.strftime("%Y-%m-%d")
                            else:
                                list_date = datetime.strptime(list_date_str, "%Y-%m-%d")
                                formatted_list_date = list_date_str
                            
                            days_listed = (datetime.now() - list_date).days
                            if days_listed < 70:  # 不足70天（约50个交易日）
                                filter_stats['new_stocks'] += 1
                                continue
                        except Exception as e:
                            # 日期解析失败，保留该股票
                            pass
                    
                    # 检查是否退市
                    delist_date = stock_info[1] if len(stock_info) > 1 and stock_info[1] else None
                    if delist_date:
                        filter_stats['delisted'] += 1
                        continue
                    
                    # 获取行业信息 (暂时设为未知)
                    industry = "未知"
                    
                    # 保存基础信息
                    stock_basic_infos[stock_code] = {
                        "listing_date": formatted_list_date,
                        "industry": industry
                    }
                    
                    # 通过所有过滤条件
                    filtered_stocks.append(stock_code)
                    filter_stats['valid'] += 1
            else:
                # 如果批量查询失败，保留所有代码（后续K线获取时会自然过滤）
                print(f"  ⚠️ 批次 {batch_start}-{batch_end} 查询失败 (ErrorCode: {info_data.ErrorCode})")
                filtered_stocks.extend(batch_codes)
                filter_stats['valid'] += len(batch_codes)
                
        except Exception as e:
            # 异常时保留所有代码
            print(f"  ⚠️ 批次 {batch_start}-{batch_end} 异常: {e}")
            filtered_stocks.extend(batch_codes)
            filter_stats['valid'] += len(batch_codes)
        
        # 添加延迟避免频率限制
        import time
        time.sleep(0.1)
    
    print(f"\n  过滤结果:")
    print(f"    ✓ 有效股票: {filter_stats['valid']} 只")
    print(f"    ✗ 新股(<70天): {filter_stats['new_stocks']} 只")
    print(f"    ✗ 已退市: {filter_stats['delisted']} 只")
    print(f"    ✗ 无数据: {filter_stats['no_data']} 只")
    
    # 更新主板股票列表为过滤后的列表
    mainboard_stocks = filtered_stocks
    
    # 调整日期范围：60天（约60个交易日，用于计算MA60等指标）
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")  # 60个交易日约90个自然日
    
    # 检查CSD接口可用性，决定使用哪种数据获取方式
    use_csd = check_csd_available()
    
    print(f"\n[4/6] 逐个获取 {len(mainboard_stocks)} 只股票的60日K线数据...")
    if use_csd:
        print("💡 使用CSD接口（序列数据）- 完整OHLCV数据")
    else:
        print("💡 使用CSS接口（截面数据）- 仅收盘价数据")
        print("   提示: CSS接口限制只能获取 CLOSE, PRECLOSE")
        print("   提示: 需要逐日查询，速度较慢但不消耗CSD配额")
    print(f"日期范围: {start_date} ~ {end_date}")
    print()
    
    # 4. 批量获取K线数据
    stocks_data = {}
    success_count = 0
    skip_count = 0
    failed_stocks = []
    total = len(mainboard_stocks)
    
    import time
    
    retry_after_error = False
    consecutive_errors = 0
    max_consecutive_errors = 10  # 连续错误超过10次则暂停
    
    # 使用批量模式（CSD和CSS都支持批量）
    batch_size = 100
    
    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch_codes = mainboard_stocks[batch_start:batch_end]
        batch_codes_str = ",".join(batch_codes)
        
        # 显示进度
        progress = (batch_start / total) * 100
        print(f"  进度: {batch_start}/{total} ({progress:.1f}%) - 成功: {success_count}, 跳过: {skip_count}")
        
        try:
            # 检测权限错误后的等待
            if retry_after_error:
                print(f"  ⏸️  检测到权限/频率限制，等待60秒...")
                time.sleep(60)
                retry_after_error = False
                consecutive_errors = 0
            
            # 根据接口可用性选择不同的数据获取方式
            if use_csd:
                # 使用CSD接口批量获取（完整OHLCV数据）
                data = c.csd(batch_codes_str, "OPEN,HIGH,LOW,CLOSE,VOLUME", start_date, end_date, "")
                
                # 检查权限错误
                if data.ErrorCode == 10001012:  # insufficient user access
                    consecutive_errors += 1
                    skip_count += len(batch_codes)
                    if consecutive_errors >= max_consecutive_errors:
                        retry_after_error = True
                    continue
                elif data.ErrorCode != 0:
                    skip_count += len(batch_codes)
                    consecutive_errors = 0
                    continue
                
                # 重置连续错误计数
                consecutive_errors = 0
                
                # 处理批量返回的数据
                if data.ErrorCode == 0 and hasattr(data, 'Data') and len(data.Dates) > 0:
                    for stock_code in batch_codes:
                        if stock_code in data.Data:
                            stock_values = data.Data[stock_code]
                            has_data = any(len(values) > 0 for values in stock_values)
                            
                            if has_data:
                                # 构建K线数据
                                kline_raw = {
                                    "stock_code": stock_code,
                                    "dates": data.Dates,
                                    "indicators": data.Indicators,
                                    "data": {}
                                }
                                for i, indicator in enumerate(data.Indicators):
                                    kline_raw["data"][indicator] = stock_values[i]
                                
                                # 转换为系统兼容格式
                                daily_data = []
                                ind_map = {ind: idx for idx, ind in enumerate(data.Indicators)}
                                
                                for i, date in enumerate(data.Dates):
                                    day_record = {'date': date}
                                    for indicator in data.Indicators:
                                        ind_idx = ind_map[indicator]
                                        if ind_idx < len(stock_values) and i < len(stock_values[ind_idx]):
                                            day_record[indicator.lower()] = stock_values[ind_idx][i]
                                    daily_data.append(day_record)
                                
                                stocks_data[stock_code] = {
                                    "name": "",
                                    "kline": kline_raw,
                                    "daily_data": daily_data
                                }
                                success_count += 1
                            else:
                                skip_count += 1
                        else:
                            # 该股票无数据
                            skip_count += 1
                else:
                    # 批次失败，整批跳过
                    skip_count += len(batch_codes)
            else:
                # 使用CSS接口批量获取（仅收盘价数据）
                # 注意：CSS接口不支持日期范围查询，只能查询截面数据
                # 这里使用最近交易日的数据
                try:
                    css_data = c.css(batch_codes_str, "CLOSE,PRECLOSE", "")
                    
                    if css_data.ErrorCode == 0 and hasattr(css_data, 'Data'):
                        for stock_code in batch_codes:
                            if stock_code in css_data.Data:
                                stock_data = css_data.Data[stock_code]
                                if len(stock_data) >= 2:
                                    # CSS返回当前截面数据
                                    close_val = stock_data[0]
                                    preclose_val = stock_data[1]
                                    
                                    # 构建简化的K线数据
                                    kline_raw = {
                                        "stock_code": stock_code,
                                        "dates": [end_date],
                                        "indicators": ["CLOSE", "PRECLOSE"],
                                        "data": {
                                            "CLOSE": [close_val],
                                            "PRECLOSE": [preclose_val]
                                        }
                                    }
                                    
                                    daily_data = [{
                                        'date': end_date,
                                        'close': close_val,
                                        'preclose': preclose_val
                                    }]
                                    
                                    stocks_data[stock_code] = {
                                        "name": "",
                                        "kline": kline_raw,
                                        "daily_data": daily_data
                                    }
                                    success_count += 1
                                else:
                                    skip_count += 1
                            else:
                                skip_count += 1
                    else:
                        skip_count += len(batch_codes)
                except Exception as e:
                    skip_count += len(batch_codes)
                    
        except Exception as e:
            skip_count += len(batch_codes)
    
    print(f"\n\nK线数据获取完成:")
    print(f"  成功: {success_count}")
    print(f"  跳过: {skip_count} (不存在或无数据)")
    print(f"  总计: {total}")
    if not use_csd:
        print(f"  💡 提示: 使用CSS接口，只有CLOSE和PRECLOSE数据")
    
    # 只对成功获取K线的股票获取基本面数据
    valid_stocks = list(stocks_data.keys())
    print(f"\n[5/6] 获取 {len(valid_stocks)} 只股票的基本面数据...")
    
    # 5.1 获取估值数据
    print(f"  获取估值指标 (PE, PB)...")
    print(f"  💡 使用CSS接口批量获取（PE/PB是截面数据，不是时序数据）")
    valuation_success = 0
    
    # 估值指标 - PE和PB是截面数据，必须用CSS接口
    indicators_str = "PE,PB"
    
    # 强制使用CSS接口批量查询（更高效且正确）
    batch_size = 100
    for batch_start in range(0, len(valid_stocks), batch_size):
        batch_end = min(batch_start + batch_size, len(valid_stocks))
        batch_codes = valid_stocks[batch_start:batch_end]
        batch_codes_str = ",".join(batch_codes)
        
        progress = (batch_start / len(valid_stocks)) * 100
        print(f"    进度: {batch_start}/{len(valid_stocks)} ({progress:.1f}%)")
        
        try:
            val_data = c.css(batch_codes_str, indicators_str, "")
            
            if val_data.ErrorCode == 0 and hasattr(val_data, 'Data'):
                for stock_code in batch_codes:
                    if stock_code in val_data.Data:
                        val_values = val_data.Data[stock_code]
                        fund_dict = {}
                        
                        # CSS返回格式: 按照请求字符串顺序 [PE, PB]
                        if len(val_values) >= 2:
                            fund_dict["pe_ratio"] = val_values[0]
                            fund_dict["pb_ratio"] = val_values[1]
                            # 其他字段设为None
                            fund_dict["roe"] = None
                            fund_dict["eps"] = None
                            fund_dict["market_cap"] = None
                            fund_dict["revenue_growth"] = None
                            fund_dict["net_profit_growth"] = None
                            fund_dict["debt_ratio"] = None
                        
                        stocks_data[stock_code]["fund_data"] = fund_dict
                        valuation_success += 1
                    else:
                        stocks_data[stock_code]["fund_data"] = {}
            else:
                for stock_code in batch_codes:
                    stocks_data[stock_code]["fund_data"] = {}
                    
        except Exception as e:
            for stock_code in batch_codes:
                stocks_data[stock_code]["fund_data"] = {}
        
        time.sleep(0.1)  # 避免频率限制
    
    print(f"  ✅ 估值数据获取完成: {valuation_success}/{len(valid_stocks)}")
    
    fundamental_success = valuation_success
    fundamental_fail = len(valid_stocks) - valuation_success
    
    # 6. 数据获取完成汇总
    # 统计ST股票数量
    st_count = sum(1 for item in failed_stocks if 'ST股票' in item.get('error', ''))
    invalid_count = len(failed_stocks) - st_count
    
    print(f"\n{'='*60}")
    print(f"数据获取完成汇总:")
    print(f"  候选股票: {total} 只")
    print(f"  ✅ K线数据成功: {success_count} 只")
    print(f"  ✅ 基本面数据成功: {fundamental_success} 只")
    print(f"  ❌ 跳过: {skip_count} 只")
    print(f"     - ST股票: {st_count} 只")
    print(f"     - 无效/不存在: {invalid_count} 只")
    print(f"  最终有效股票: {success_count} 只主板非ST股票")
    print(f"{'='*60}")
    
    # 6. 显示第一只股票的详细数据
    if stocks_data:
        print("\n示例数据:")
        first_code, first_obj = next(iter(stocks_data.items()))
        kline = first_obj.get("kline", {})
        fund_data = first_obj.get("fund_data", {})
        print(f"  股票代码: {first_code}")
        dates = kline.get("dates", [])
        print(f"  K线数据: {len(dates)} 条")
        if dates:
            print(f"  日期范围: {dates[0]} ~ {dates[-1]}")
            print(f"  最新收盘价: {kline.get('data', {}).get('CLOSE', [None])[-1]}")
        
        if fund_data:
            print(f"  基本面数据:")
            for key, value in fund_data.items():
                print(f"    {key}: {value}")
    
    # 7. 保存到文件，格式与全量数据保持一致
    # 使用相对于脚本位置的共享数据目录
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    shared_data_dir = os.path.join(os.path.dirname(script_dir), 'data')
    os.makedirs(shared_data_dir, exist_ok=True)
    output_file = os.path.join(shared_data_dir, "comprehensive_stock_data.json")
    
    # 转换数据格式为系统标准格式（与comprehensive_stock_data.json一致）
    compatible_stocks_data = {}
    for stock_code, data in stocks_data.items():
        # 去除后缀 (000001.SZ -> 000001)
        simple_code = stock_code.split('.')[0]
        
        # 获取股票名称（如果为空则使用代码）
        stock_name = mainboard_stock_names.get(stock_code, "")
        if not stock_name:
            # 名称为空，使用股票代码作为名称
            stock_name = simple_code
        
        # 获取基础信息
        basic_info = stock_basic_infos.get(stock_code, {})
        industry = basic_info.get("industry", "未知")
        listing_date = basic_info.get("listing_date", "")
        
        # K线数据转换：Choice格式 -> 标准格式
        # Choice: {date: "YYYY-MM-DD" or "YYYY/MM/DD", open: x, high: x, low: x, close: x, volume: x}
        # 标准: {date: "YYYYMMDD", open: x, high: x, low: x, close: x, volume: x}
        daily_data = data.get("daily_data", [])
        formatted_kline = []
        for day in daily_data:
            date_str = day.get("date", "")
            # 处理多种日期格式：YYYY-MM-DD, YYYY/MM/DD, YYYYMMDD
            date_str = date_str.replace("-", "").replace("/", "")
            formatted_day = {
                "date": date_str,
                "open": day.get("open"),
                "high": day.get("high"),
                "low": day.get("low"),
                "close": day.get("close"),
                "volume": day.get("volume")
            }
            formatted_kline.append(formatted_day)
        
        # 计算技术指标（从K线数据）
        tech_data = calculate_technical_indicators_from_kline(formatted_kline)
        
        # 重构数据结构（完全符合标准格式）
        compatible_stocks_data[simple_code] = {
            "code": simple_code,
            "timestamp": datetime.now().isoformat(),
            "collection_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_source": "choice_api",
            "basic_info": {
                "code": simple_code,
                "name": stock_name,
                "type": "1",  # 1=股票
                "status": "1",  # 1=正常
                "industry": industry,
                "listing_date": listing_date,
                "source": "choice"
            },
            "kline_data": {
                "daily": formatted_kline
            },
            "financial_data": data.get("fund_data", {}),
            "tech_data": tech_data  # 添加计算好的技术指标
        }
    
    # 完全符合标准格式的数据结构
    cache_data = {
        "stocks": compatible_stocks_data,
        "metadata": {
            "collection_date": datetime.now().strftime("%Y-%m-%d"),  # 采集日期（用于缓存判断）
            "collection_time": datetime.now().isoformat(),           # 采集时间
            "data_source": "choice_api",
            "kline_start_date": start_date,                          # K线数据开始日期
            "kline_end_date": end_date,                              # K线数据结束日期
            "total_stocks": total,
            "success_count": success_count,
            "skip_count": skip_count,
            "version": "2.0"
        }
    }
    
    print(f"\n正在保存数据到文件...")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)
    
    # 获取文件大小
    file_size = os.path.getsize(output_file)
    print(f"\n✅ 数据已保存到: {output_file}")
    print(f"   文件大小: {file_size / 1024 / 1024:.2f} MB")
    
    # 检查tech_data是否正常生成
    tech_data_success = sum(1 for s in compatible_stocks_data.values() if s.get('tech_data'))
    tech_data_total = len(compatible_stocks_data)
    
    if tech_data_success == 0:
        print(f"\n{'='*70}")
        print(f"  ⚠️  警告：未能生成技术指标数据")
        print(f"{'='*70}")
        print(f"  原因：使用CSS接口，数据不完整（仅有收盘价）")
        print(f"  影响：无法计算RSI/MACD/MA等技术指标")
        print(f"  建议：")
        print(f"     1. 等待下周一00:00配额重置后重新运行")
        print(f"     2. 或使用'获取全部数据'按钮使用Tushare等数据源")
        print(f"{'='*70}")
    elif tech_data_success < tech_data_total:
        print(f"\n  ⚠️  部分股票技术指标计算失败: {tech_data_success}/{tech_data_total}")
    else:
        print(f"\n  ✅ 技术指标计算完成: {tech_data_success}/{tech_data_total}")
    
    # 保存失败记录
    if failed_stocks:
        failed_file = "data/choice_failed_stocks.json"
        failed_data = {
            "total_failed": len(failed_stocks),
            "timestamp": datetime.now().isoformat(),
            "failed_stocks": failed_stocks
        }
        
        with open(failed_file, 'w', encoding='utf-8') as f:
            json.dump(failed_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n⚠️  失败记录已保存到: {failed_file}")
        print(f"   失败数量: {len(failed_stocks)}")
        print(f"   失败率: {len(failed_stocks)/total*100:.1f}%")
        
        # 显示前10个失败的例子
        print(f"\n   失败示例 (前10个):")
        for item in failed_stocks[:10]:
            print(f"     {item['code']}: {item['error']}")
    
    # 8. 断开连接
    c.stop()
    print("\n✅✅✅ 全部主板数据获取完成！")

if __name__ == "__main__":
    main()
