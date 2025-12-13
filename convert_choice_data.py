"""Choice数据格式转换器 - 将Choice原生数据转换为系统标准格式"""
import json
import os
from datetime import datetime


def convert_choice_to_standard_format(input_file="data/choice_all_stocks.json", 
                                      output_file="data/comprehensive_stock_data.json"):
    """
    将Choice原生数据转换为系统标准格式
    
    输入格式 (Choice原生):
        {
            "stocks": {
                "000001": {
                    "code": "000001",
                    "name": "",  # 可能为空
                    "kline": {...},
                    "daily_data": [...],
                    "fund_data": {...}
                }
            }
        }
    
    输出格式 (系统标准):
        {
            "stocks": {
                "000001": {
                    "code": "000001",
                    "basic_info": {
                        "code": "000001",
                        "name": "平安银行",
                        "type": "1",
                        "status": "1",
                        "industry": "银行",
                        "listing_date": "1991-04-03"
                    },
                    "kline_data": {
                        "daily": [
                            {"date": "20251213", "open": x, ...}
                        ]
                    },
                    "financial_data": {...}
                }
            }
        }
    """
    
    print("="*60)
    print("Choice数据格式转换器")
    print("="*60)
    
    # 检查输入文件
    if not os.path.exists(input_file):
        print(f"❌ 输入文件不存在: {input_file}")
        return False
    
    print(f"📂 读取原始数据: {input_file}")
    with open(input_file, 'r', encoding='utf-8') as f:
        source_data = json.load(f)
    
    source_stocks = source_data.get("stocks", {})
    print(f"✅ 读取到 {len(source_stocks)} 只股票")
    
    # 加载股票名称映射（从其他数据源）
    name_mapping = _load_stock_names()
    print(f"📋 加载股票名称映射: {len(name_mapping)} 条")
    
    # 转换数据
    print("\n🔄 开始转换数据...")
    converted_stocks = {}
    success_count = 0
    skip_count = 0
    
    for code, stock_data in source_stocks.items():
        try:
            # 获取股票名称
            stock_name = stock_data.get("name", "")
            if not stock_name and code in name_mapping:
                stock_name = name_mapping[code]
            
            # K线数据处理
            daily_data = stock_data.get("daily_data", [])
            if not daily_data:
                # 尝试从kline字段提取
                kline = stock_data.get("kline", {})
                kline_data = kline.get("data", {})
                dates = kline.get("dates", [])
                
                if kline_data and dates:
                    daily_data = _convert_kline_to_daily(kline_data, dates)
            
            if not daily_data:
                skip_count += 1
                continue
            
            # 格式化日线数据
            formatted_daily = []
            for day in daily_data:
                date_str = str(day.get("date", ""))
                # 处理多种日期格式
                date_str = date_str.replace("-", "").replace("/", "").replace(" ", "")
                
                formatted_day = {
                    "date": date_str,
                    "open": day.get("open"),
                    "high": day.get("high"),
                    "low": day.get("low"),
                    "close": day.get("close"),
                    "volume": day.get("volume")
                }
                formatted_daily.append(formatted_day)
            
            # 基本信息
            basic_info = stock_data.get("basic_info", {})
            if not basic_info:
                basic_info = {
                    "code": code,
                    "name": stock_name,
                    "type": "1",
                    "status": "1",
                    "industry": stock_data.get("industry", "未知"),
                    "listing_date": stock_data.get("listing_date", ""),
                    "source": "choice"
                }
            else:
                # 确保name字段有值
                if not basic_info.get("name") and stock_name:
                    basic_info["name"] = stock_name
            
            # 财务数据
            financial_data = stock_data.get("fund_data", stock_data.get("financial_data", {}))
            
            # 构建标准格式
            converted_stocks[code] = {
                "code": code,
                "timestamp": datetime.now().isoformat(),
                "collection_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "data_source": "choice_api_converted",
                "basic_info": basic_info,
                "kline_data": {
                    "daily": formatted_daily
                },
                "financial_data": financial_data
            }
            
            success_count += 1
            
            if success_count % 500 == 0:
                print(f"  进度: {success_count}/{len(source_stocks)}")
        
        except Exception as e:
            print(f"⚠️  转换股票 {code} 失败: {e}")
            skip_count += 1
            continue
    
    print(f"\n✅ 转换完成:")
    print(f"  成功: {success_count}")
    print(f"  跳过: {skip_count}")
    
    # 保存转换后的数据
    output_data = {
        "stocks": converted_stocks,
        "metadata": {
            "conversion_date": datetime.now().strftime("%Y-%m-%d"),
            "conversion_time": datetime.now().isoformat(),
            "source": "choice_api",
            "converter_version": "1.0",
            "total_stocks": len(converted_stocks),
            "original_file": input_file
        }
    }
    
    print(f"\n💾 保存数据到: {output_file}")
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    file_size = os.path.getsize(output_file)
    print(f"✅ 保存完成: {file_size / 1024 / 1024:.2f} MB")
    
    return True


def _load_stock_names():
    """从现有数据文件加载股票名称映射"""
    name_map = {}
    
    # 尝试从多个数据源加载
    potential_files = [
        "stock_info_fallback.json",
        "data/comprehensive_stock_data_part_1.json",
        "batch_stock_scores_optimized_主板_*.json"
    ]
    
    for file_pattern in potential_files:
        import glob
        for file_path in glob.glob(file_pattern):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 提取股票名称
                if "stocks" in data:
                    for code, stock_info in data["stocks"].items():
                        if isinstance(stock_info, dict):
                            name = stock_info.get("name") or stock_info.get("basic_info", {}).get("name")
                            if name and code not in name_map:
                                name_map[code] = name
                
                elif isinstance(data, dict):
                    for code, stock_info in data.items():
                        if isinstance(stock_info, dict):
                            name = stock_info.get("name") or stock_info.get("stock_name")
                            if name and code not in name_map:
                                name_map[code] = name
            
            except Exception:
                continue
    
    return name_map


def _convert_kline_to_daily(kline_data, dates):
    """将kline原始格式转换为daily_data格式"""
    daily_data = []
    
    closes = kline_data.get("CLOSE", [])
    opens = kline_data.get("OPEN", [])
    highs = kline_data.get("HIGH", [])
    lows = kline_data.get("LOW", [])
    volumes = kline_data.get("VOLUME", [])
    
    for i, date in enumerate(dates):
        day_record = {"date": date}
        if i < len(opens): day_record["open"] = opens[i]
        if i < len(highs): day_record["high"] = highs[i]
        if i < len(lows): day_record["low"] = lows[i]
        if i < len(closes): day_record["close"] = closes[i]
        if i < len(volumes): day_record["volume"] = volumes[i]
        
        daily_data.append(day_record)
    
    return daily_data


if __name__ == "__main__":
    # 自动检测文件
    import sys
    
    input_file = "data/choice_all_stocks.json"
    output_file = "data/comprehensive_stock_data.json"
    
    # 如果已经存在comprehensive_stock_data.json，备份它
    if os.path.exists(output_file):
        backup_file = output_file.replace(".json", f"_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        print(f"📦 备份现有文件到: {backup_file}")
        import shutil
        shutil.copy2(output_file, backup_file)
    
    # 执行转换
    success = convert_choice_to_standard_format(input_file, output_file)
    
    if success:
        print("\n" + "="*60)
        print("🎉 转换成功！")
        print("="*60)
        print(f"\n现在可以在程序中使用: {output_file}")
    else:
        print("\n❌ 转换失败")
        sys.exit(1)
