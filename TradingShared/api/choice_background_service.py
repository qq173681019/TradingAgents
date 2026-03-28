"""Choice数据后台服务 - 定期获取数据并保存到文件"""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

# 导入Choice SDK
from EmQuantAPI import c

# 数据保存路径
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
CACHE_FILE = DATA_DIR / "choice_all_stocks.json"  # 全量股票数据
STATUS_FILE = DATA_DIR / "choice_status.json"

def init_choice():
    """初始化Choice连接"""
    print("[服务] 初始化Choice SDK...")
    result = c.start("")
    if result.ErrorCode == 0:
        print("[服务] [OK] Choice连接成功")
        return True
    else:
        print(f"[服务] [FAIL] Choice连接失败: {result.ErrorMsg}")
        return False

def get_kline_data(stock_code, days=5):
    """获取K线数据"""
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    print(f"[服务] 获取 {stock_code} K线数据 ({start_date} ~ {end_date})")
    
    data = c.csd(stock_code, "OPEN,HIGH,LOW,CLOSE,VOLUME", start_date, end_date, "")
    
    if data.ErrorCode == 0:
        # 解析数据
        result = {
            "stock_code": stock_code,
            "dates": data.Dates,
            "indicators": data.Indicators,
            "data": {}
        }
        
        if stock_code in data.Data:
            stock_data = data.Data[stock_code]
            for i, indicator in enumerate(data.Indicators):
                result["data"][indicator] = stock_data[i]
        
        print(f"[服务] [OK] 成功获取 {len(data.Dates)} 条数据")
        return result
    else:
        print(f"[服务] [FAIL] 获取失败: {data.ErrorMsg}")
        return None

def update_status(status, message):
    """更新服务状态"""
    status_data = {
        "status": status,
        "message": message,
        "timestamp": datetime.now().isoformat()
    }
    
    with open(STATUS_FILE, 'w', encoding='utf-8') as f:
        json.dump(status_data, f, ensure_ascii=False, indent=2)

def get_all_stocks():
    """获取所有A股主板股票列表"""
    print("[服务] 获取A股主板股票列表...")
    
    # 自动尝试多种板块代码和参数组合
    from datetime import datetime, timedelta
    block_codes = [
        ("B0010001", "主板"),
        ("B0000001", "全部A股"),
        ("B0010002", "创业板"),
        ("001004", "旧主板代码")
    ]
    param_sets = [
        {"desc": "TradeDate参数为今天", "param": "TradeDate="+datetime.now().strftime("%Y%m%d")},
        {"desc": "TradeDate参数为空", "param": ""},
        {"desc": "无参数", "param": None}
    ]
    for block_code, block_desc in block_codes:
        for param_set in param_sets:
            try:
                param = param_set["param"]
                print(f"[服务] 尝试板块代码: {block_code} ({block_desc}), 参数: {param_set['desc']}")
                if param is None:
                    data = c.cses(block_code, "date,wind_code,sec_name", "", "", "")
                else:
                    data = c.cses(block_code, "date,wind_code,sec_name", "", "", param)
                if data.ErrorCode == 0 and hasattr(data, 'Data'):
                    codes = data.Data.get('wind_code', [])
                    names = data.Data.get('sec_name', [])
                    stocks = []
                    for i, code in enumerate(codes):
                        if code.startswith(('600', '601', '603', '605', '000', '001', '002', '003')):
                            stock_info = {
                                'code': code,
                                'name': names[i] if i < len(names) else ''
                            }
                            stocks.append(stock_info)
                    print(f"[服务] [OK] 获取到 {len(stocks)} 只A股主板股票 (板块: {block_code}, 参数: {param_set['desc']})")
                    return stocks
                else:
                    print(f"[服务] [FAIL] 失败: {data.ErrorMsg if hasattr(data, 'ErrorMsg') else '未知错误'} (板块: {block_code}, 参数: {param_set['desc']})")
            except Exception as e:
                print(f"[服务] 异常: {e} (板块: {block_code}, 参数: {param_set['desc']})")
    print("[服务] [FAIL] 所有板块代码和参数组合均失败，无法获取股票列表")
    # 额外测试：尝试用css和cst接口获取主板股票列表（只用Choice）
    print("[服务] 尝试用css接口获取A股主板股票列表...")
    try:
        # css接口：证券列表
        data = c.css("A股主板", "SECUCODE,SECUNAME", "", "")
        if data.ErrorCode == 0 and hasattr(data, 'Data'):
            codes = data.Data.get('SECUCODE', [])
            names = data.Data.get('SECUNAME', [])
            stocks = []
            for i, code in enumerate(codes):
                if code.startswith(('600', '601', '603', '605', '000', '001', '002', '003')):
                    stock_info = {
                        'code': code,
                        'name': names[i] if i < len(names) else ''
                    }
                    stocks.append(stock_info)
            print(f"[服务] [OK] css接口获取到 {len(stocks)} 只A股主板股票")
            return stocks
        else:
            print(f"[服务] [FAIL] css接口失败: {data.ErrorMsg if hasattr(data, 'ErrorMsg') else '未知错误'}")
    except Exception as e:
        print(f"[服务] [FAIL] css接口异常: {e}")
    print("[服务] 尝试用cst接口获取A股主板股票列表...")
    try:
        # cst接口：板块成分
        data = c.cst("B0010001", "SECUCODE,SECUNAME", "", "")
        if data.ErrorCode == 0 and hasattr(data, 'Data'):
            codes = data.Data.get('SECUCODE', [])
            names = data.Data.get('SECUNAME', [])
            stocks = []
            for i, code in enumerate(codes):
                if code.startswith(('600', '601', '603', '605', '000', '001', '002', '003')):
                    stock_info = {
                        'code': code,
                        'name': names[i] if i < len(names) else ''
                    }
                    stocks.append(stock_info)
            print(f"[服务] [OK] cst接口获取到 {len(stocks)} 只A股主板股票")
            return stocks
        else:
            print(f"[服务] [FAIL] cst接口失败: {data.ErrorMsg if hasattr(data, 'ErrorMsg') else '未知错误'}")
    except Exception as e:
        print(f"[服务] [FAIL] cst接口异常: {e}")
    print("[服务] [FAIL] css/cst接口也无法获取主板股票列表，请检查Choice环境或联系技术支持。")
    return []

def main():
    """主循环"""
    print("="*60)
    print("Choice数据后台服务 - A股主板全量更新")
    print("="*60)
    
    # 初始化
    if not init_choice():
        update_status("error", "Choice SDK初始化失败")
        return
    
    update_status("running", "服务运行中")
    
    # 获取所有股票列表
    print("\n[1/3] 获取股票列表...")
    stocks = get_all_stocks()
    
    if not stocks:
        print("[FAIL] 未能获取股票列表")
        update_status("error", "股票列表获取失败")
        return
    
    # 获取K线数据
    print(f"\n[2/3] 开始获取 {len(stocks)} 只股票的K线数据...")
    print("提示: 这可能需要几分钟时间...\n")
    
    all_stock_data = {}
    success_count = 0
    fail_count = 0
    error_list = []
    for i, stock in enumerate(stocks, 1):
        code = stock['code']
        name = stock['name']
        if i % 100 == 0:
            print(f"进度: {i}/{len(stocks)} ({i*100//len(stocks)}%)")
        try:
            kline_data = get_kline_data(code, days=30)  # 获取30天数据
            if kline_data:
                all_stock_data[code] = {
                    'name': name,
                    'kline': kline_data
                }
                success_count += 1
            else:
                fail_count += 1
                error_list.append({"code": code, "name": name, "reason": "K线数据获取失败"})
                if fail_count <= 10:
                    print(f"  [WARN]  {code} {name} 获取失败")
        except Exception as e:
            fail_count += 1
            error_list.append({"code": code, "name": name, "reason": str(e)})
            print(f"  [FAIL] {code} {name} 异常: {e}")
    # 保存到缓存
    print(f"\n[3/3] 保存数据...")
    cache_data = {
        "last_update": datetime.now().isoformat(),
        "total_stocks": len(stocks),
        "success_count": success_count,
        "fail_count": fail_count,
        "stocks": all_stock_data,
        "test_stock": all_stock_data.get("000001.SZ", {}).get('kline') if "000001.SZ" in all_stock_data else None
    }
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)
    if error_list:
        error_file = DATA_DIR / "choice_failed_stocks.json"
        with open(error_file, 'w', encoding='utf-8') as f:
            json.dump(error_list, f, ensure_ascii=False, indent=2)
        print(f"[FAIL] 有 {len(error_list)} 只股票获取失败，详情见 {error_file}")
    print(f"\n" + "="*60)
    print(f"[OK] 数据更新完成")
    print(f"   成功: {success_count} 只")
    print(f"   失败: {fail_count} 只")
    print(f"   缓存文件: {CACHE_FILE}")
    print(f"   文件大小: {CACHE_FILE.stat().st_size / 1024 / 1024:.2f} MB")
    print("="*60)
    update_status("success", f"数据更新成功 ({success_count}/{len(stocks)})")
    print("\n[IDEA] 提示：可以将此脚本设置为定时任务，定期更新数据。")

if __name__ == "__main__":
    main()
