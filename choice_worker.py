"""Choice数据获取工作进程 - 独立运行避免调试器环境污染"""
import json
import sys
from datetime import datetime, timedelta


def get_kline_data(stock_code, start_date, end_date, indicators="OPEN,HIGH,LOW,CLOSE,VOLUME"):
    """
    获取K线数据
    
    参数:
        stock_code: 股票代码，如 "000001.SZ"
        start_date: 开始日期 "YYYY-MM-DD"
        end_date: 结束日期 "YYYY-MM-DD"
        indicators: 指标列表，逗号分隔
    
    返回:
        JSON格式的数据字典
    """
    try:
        # 初始化前先检查是否已初始化，避免KeyError
        # Choice SDK不支持重复调用c.start()
        import time

        from EmQuantAPI import c
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # 尝试调用c.start()
                result = c.start("")
                
                # 检查是否成功
                if result.ErrorCode == 0:
                    break  # 成功则跳出
                elif "online" in result.ErrorMsg.lower():
                    # 已经在线，也算成功
                    break
                else:
                    # 其他错误
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                    
            except KeyError as e:
                # KeyError说明SDK初始化不完整
                # 尝试重置SDK状态后重试
                if attempt < max_retries - 1:
                    try:
                        # 强制重置SDK的初始化标志
                        c._c__InitSucceed = False
                        c._c__QuantFuncDict = {}
                    except:
                        pass
                    time.sleep(1)
                    continue
                else:
                    # 最后一次尝试也失败
                    import sys
                    import traceback
                    return {
                        "success": False,
                        "error": f"KeyError: {str(e)}",
                        "python_exe": sys.executable,
                        "traceback": traceback.format_exc(),
                        "hint": "Choice SDK内部状态损坏，通常是因为重复初始化。请重启应用程序。"
                    }
            except OSError as e:
                last_error = e
                if attempt < max_retries - 1:
                    # 等待一下再重试
                    time.sleep(1)
                    continue
                else:
                    # 最后一次尝试也失败
                    import sys
                    import traceback
                    return {
                        "success": False,
                        "error": f"OSError (尝试{max_retries}次后失败): {str(e)}",
                        "python_exe": sys.executable,
                        "traceback": traceback.format_exc(),
                        "hint": "可能有其他进程正在使用Choice SDK，请关闭其他进程后重试"
                    }
        if result.ErrorCode != 0:
            return {
                "success": False,
                "error": f"Choice初始化失败: {result.ErrorMsg}",
                "error_code": result.ErrorCode
            }
        
        # 获取数据
        data = c.csd(stock_code, indicators, start_date, end_date, "")
        
        if data.ErrorCode != 0:
            return {
                "success": False,
                "error": f"数据获取失败: {data.ErrorMsg}",
                "error_code": data.ErrorCode
            }
        
        # 解析数据
        result_data = {
            "success": True,
            "stock_code": stock_code,
            "dates": data.Dates if hasattr(data, 'Dates') else [],
            "indicators": data.Indicators if hasattr(data, 'Indicators') else [],
            "data": {}
        }
        
        # Choice返回的Data格式: {stock_code: [[open], [high], [low], [close], [volume]]}
        if hasattr(data, 'Data') and isinstance(data.Data, dict):
            stock_data = data.Data.get(stock_code, [])
            if stock_data and result_data["indicators"]:
                # 将数据按指标重组
                for i, indicator in enumerate(result_data["indicators"]):
                    if i < len(stock_data):
                        result_data["data"][indicator] = stock_data[i]
        
        return result_data
        
    except Exception as e:
        return {
            "success": False,
            "error": f"{type(e).__name__}: {str(e)}"
        }

def get_realtime_quote(stock_codes):
    """
    获取实时行情
    
    参数:
        stock_codes: 股票代码列表或单个代码
    
    返回:
        JSON格式的行情数据
    """
    try:
        from EmQuantAPI import c

        # 初始化
        result = c.start("")
        if result.ErrorCode != 0:
            return {
                "success": False,
                "error": f"Choice初始化失败: {result.ErrorMsg}"
            }
        
        # 转换为字符串
        if isinstance(stock_codes, list):
            codes_str = ",".join(stock_codes)
        else:
            codes_str = stock_codes
        
        # 获取实时行情
        indicators = "LASTPRICE,OPEN,HIGH,LOW,VOLUME,AMOUNT,CHANGE,CHANGEPCT"
        data = c.css(codes_str, indicators, "")
        
        if data.ErrorCode != 0:
            return {
                "success": False,
                "error": f"行情获取失败: {data.ErrorMsg}"
            }
        
        # 解析数据
        result_data = {
            "success": True,
            "codes": data.Codes if hasattr(data, 'Codes') else [],
            "data": {}
        }
        
        if hasattr(data, 'Data') and isinstance(data.Data, dict):
            for indicator, values in data.Data.items():
                result_data["data"][indicator] = values
        
        return result_data
        
    except Exception as e:
        return {
            "success": False,
            "error": f"{type(e).__name__}: {str(e)}"
        }

if __name__ == "__main__":
    # 从命令行参数读取请求
    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "error": "缺少命令参数"
        }))
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "kline":
        # 获取K线数据
        # 参数: stock_code start_date end_date [indicators]
        if len(sys.argv) < 5:
            print(json.dumps({
                "success": False,
                "error": "K线参数不足: stock_code start_date end_date"
            }))
            sys.exit(1)
        
        stock_code = sys.argv[2]
        start_date = sys.argv[3]
        end_date = sys.argv[4]
        indicators = sys.argv[5] if len(sys.argv) > 5 else "OPEN,HIGH,LOW,CLOSE,VOLUME"
        
        result = get_kline_data(stock_code, start_date, end_date, indicators)
        # 输出特殊标记，然后是JSON数据（Choice SDK日志会在之前输出）
        print("\n===CHOICE_JSON_START===")
        print(json.dumps(result, ensure_ascii=False))
        print("===CHOICE_JSON_END===")
        
    elif command == "quote":
        # 获取实时行情
        # 参数: stock_codes (逗号分隔)
        if len(sys.argv) < 3:
            print(json.dumps({
                "success": False,
                "error": "行情参数不足: stock_codes"
            }))
            sys.exit(1)
        
        stock_codes = sys.argv[2]
        result = get_realtime_quote(stock_codes)
        # 输出特殊标记，然后是JSON数据
        print("\n===CHOICE_JSON_START===")
        print(json.dumps(result, ensure_ascii=False))
        print("===CHOICE_JSON_END===")
        
    else:
        print(json.dumps({
            "success": False,
            "error": f"未知命令: {command}"
        }))
        sys.exit(1)
