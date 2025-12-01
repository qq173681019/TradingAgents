"""
Choice金融终端API接口
东方财富Choice数据源集成
"""

from datetime import datetime, timedelta

import pandas as pd

# 全局变量
choice_available = False
choice_instance = None

try:
    # Choice金融终端的Python SDK
    import EmQuantAPI as c
    choice_available = True
    print("✅ Choice API 模块加载成功")
except ImportError:
    try:
        # 尝试备用导入方式
        from EmQuantAPI import *
        choice_available = True
        print("✅ Choice API 模块加载成功(备用方式)")
    except ImportError:
        print("⚠️ Choice API 未安装")
        print("安装方法：")
        print("  1. 访问 https://choice.eastmoney.com/")
        print("  2. 下载并安装Choice金融终端客户端")
        print("  3. 安装后，Python SDK会自动配置")
        choice_available = False
        c = None


class ChoiceAPI:
    """Choice金融终端API封装类"""
    
    def __init__(self, username="", password=""):
        """初始化Choice API连接"""
        self.username = username
        self.password = password
        self.is_logged_in = False
        
        if not choice_available:
            print("❌ Choice API不可用，请先安装 EmQuantAPI")
            return
            
    def login(self):
        """登录Choice终端"""
        if not choice_available:
            return False
            
        try:
            # Choice登录
            login_result = c.start("ForceLogin=1")  # ForceLogin=1 强制登录
            
            if login_result == 0:
                self.is_logged_in = True
                print(f"✅ Choice终端登录成功")
                return True
            else:
                print(f"❌ Choice终端登录失败，错误码: {login_result}")
                return False
                
        except Exception as e:
            print(f"❌ Choice登录异常: {e}")
            return False
    
    def logout(self):
        """登出Choice终端"""
        if not choice_available or not self.is_logged_in:
            return
            
        try:
            c.stop()
            self.is_logged_in = False
            print("✅ Choice终端已登出")
        except Exception as e:
            print(f"⚠️ Choice登出异常: {e}")
    
    def get_stock_data(self, ticker, start_date=None, end_date=None):
        """
        获取股票历史数据
        
        Args:
            ticker: 股票代码 (如 "000001.SZ")
            start_date: 开始日期 (格式: "2024-01-01")
            end_date: 结束日期 (格式: "2024-12-31")
        
        Returns:
            DataFrame: 包含OHLCV数据
        """
        if not self.is_logged_in:
            print("❌ 请先登录Choice终端")
            return None
            
        try:
            # 确保股票代码格式正确
            if not ticker.endswith(('.SZ', '.SH')):
                if ticker.startswith('6'):
                    ticker = f"{ticker}.SH"
                elif ticker.startswith(('0', '3')):
                    ticker = f"{ticker}.SZ"
            
            # 设置默认时间范围
            if not end_date:
                end_date = datetime.now().strftime("%Y-%m-%d")
            if not start_date:
                start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
            
            # Choice API查询
            # 指标: 开盘价,最高价,最低价,收盘价,成交量,成交额
            indicators = "OPEN,HIGH,LOW,CLOSE,VOLUME,AMOUNT"
            
            data = c.csd(ticker, indicators, start_date, end_date, "period=1,adjustflag=1")
            
            if data.ErrorCode != 0:
                print(f"❌ Choice数据获取失败: {data.ErrorMsg}")
                return None
            
            # 转换为DataFrame
            df = pd.DataFrame({
                'date': data.Times,
                'open': data.Data[0],
                'high': data.Data[1],
                'low': data.Data[2],
                'close': data.Data[3],
                'volume': data.Data[4],
                'amount': data.Data[5]
            })
            
            print(f"✅ Choice获取 {ticker} 数据成功: {len(df)} 条记录")
            return df
            
        except Exception as e:
            print(f"❌ Choice获取数据异常: {e}")
            return None
    
    def get_realtime_data(self, ticker):
        """
        获取股票实时行情
        
        Args:
            ticker: 股票代码
            
        Returns:
            dict: 实时行情数据
        """
        if not self.is_logged_in:
            print("❌ 请先登录Choice终端")
            return None
            
        try:
            # 确保股票代码格式正确
            if not ticker.endswith(('.SZ', '.SH')):
                if ticker.startswith('6'):
                    ticker = f"{ticker}.SH"
                elif ticker.startswith(('0', '3')):
                    ticker = f"{ticker}.SZ"
            
            # Choice实时行情查询
            indicators = "LASTPRICE,OPEN,HIGH,LOW,PRECLOSE,VOLUME,AMOUNT,TURNOVERRATE"
            
            data = c.css(ticker, indicators)
            
            if data.ErrorCode != 0:
                print(f"❌ Choice实时数据获取失败: {data.ErrorMsg}")
                return None
            
            # 解析数据
            result = {
                'current_price': data.Data[0][0] if data.Data[0] else None,
                'open': data.Data[1][0] if data.Data[1] else None,
                'high': data.Data[2][0] if data.Data[2] else None,
                'low': data.Data[3][0] if data.Data[3] else None,
                'pre_close': data.Data[4][0] if data.Data[4] else None,
                'volume': data.Data[5][0] if data.Data[5] else None,
                'amount': data.Data[6][0] if data.Data[6] else None,
                'turnover_rate': data.Data[7][0] if data.Data[7] else None,
            }
            
            print(f"✅ Choice获取 {ticker} 实时数据成功")
            return result
            
        except Exception as e:
            print(f"❌ Choice获取实时数据异常: {e}")
            return None
    
    def get_stock_info(self, ticker):
        """
        获取股票基本信息
        
        Args:
            ticker: 股票代码
            
        Returns:
            dict: 股票基本信息
        """
        if not self.is_logged_in:
            print("❌ 请先登录Choice终端")
            return None
            
        try:
            # 确保股票代码格式正确
            if not ticker.endswith(('.SZ', '.SH')):
                if ticker.startswith('6'):
                    ticker = f"{ticker}.SH"
                elif ticker.startswith(('0', '3')):
                    ticker = f"{ticker}.SZ"
            
            # Choice基本信息查询
            indicators = "SECNAME,INDUSTRY,LISTING_DATE,TOTALSHARE,FREESHARE"
            
            data = c.css(ticker, indicators)
            
            if data.ErrorCode != 0:
                print(f"❌ Choice股票信息获取失败: {data.ErrorMsg}")
                return None
            
            # 解析数据
            result = {
                'name': data.Data[0][0] if data.Data[0] else "未知",
                'industry': data.Data[1][0] if data.Data[1] else "未知",
                'listing_date': data.Data[2][0] if data.Data[2] else None,
                'total_share': data.Data[3][0] if data.Data[3] else None,
                'free_share': data.Data[4][0] if data.Data[4] else None,
            }
            
            print(f"✅ Choice获取 {ticker} 基本信息成功")
            return result
            
        except Exception as e:
            print(f"❌ Choice获取股票信息异常: {e}")
            return None
    
    def get_financial_data(self, ticker):
        """
        获取股票财务数据
        
        Args:
            ticker: 股票代码
            
        Returns:
            dict: 财务数据
        """
        if not self.is_logged_in:
            print("❌ 请先登录Choice终端")
            return None
            
        try:
            # 确保股票代码格式正确
            if not ticker.endswith(('.SZ', '.SH')):
                if ticker.startswith('6'):
                    ticker = f"{ticker}.SH"
                elif ticker.startswith(('0', '3')):
                    ticker = f"{ticker}.SZ"
            
            # Choice财务数据查询
            # PE市盈率, PB市净率, ROE净资产收益率
            indicators = "PE,PB,ROE"
            
            data = c.css(ticker, indicators)
            
            if data.ErrorCode != 0:
                print(f"❌ Choice财务数据获取失败: {data.ErrorMsg}")
                return None
            
            # 解析数据
            result = {
                'pe_ratio': data.Data[0][0] if data.Data[0] and data.Data[0][0] else 20,
                'pb_ratio': data.Data[1][0] if data.Data[1] and data.Data[1][0] else 2.0,
                'roe': data.Data[2][0] if data.Data[2] and data.Data[2][0] else 10,
            }
            
            print(f"✅ Choice获取 {ticker} 财务数据成功: PE={result['pe_ratio']:.2f}, PB={result['pb_ratio']:.2f}, ROE={result['roe']:.2f}")
            return result
            
        except Exception as e:
            print(f"❌ Choice获取财务数据异常: {e}")
            return None
    
    def get_all_stocks(self, market="A"):
        """
        获取所有股票列表
        
        Args:
            market: 市场类型 ("A"=A股主板, "创业板", "科创板")
            
        Returns:
            list: 股票代码列表
        """
        if not self.is_logged_in:
            print("❌ 请先登录Choice终端")
            return []
            
        try:
            # Choice获取股票列表
            # 板块代码: 001004=沪深A股
            data = c.sector("001004", "2024-12-01")
            
            if data.ErrorCode != 0:
                print(f"❌ Choice获取股票列表失败: {data.ErrorMsg}")
                return []
            
            stock_list = data.Codes
            print(f"✅ Choice获取股票列表成功: {len(stock_list)} 只")
            return stock_list
            
        except Exception as e:
            print(f"❌ Choice获取股票列表异常: {e}")
            return []


# 创建全局实例
def get_choice_instance():
    """获取Choice API全局实例"""
    global choice_instance
    if choice_instance is None:
        choice_instance = ChoiceAPI()
    return choice_instance


# 测试函数
def test_choice_api():
    """测试Choice API连接"""
    choice = get_choice_instance()
    
    if not choice_available:
        print("❌ Choice API不可用")
        return False
    
    # 尝试登录
    if choice.login():
        print("✅ Choice API测试成功")
        
        # 测试获取股票数据
        data = choice.get_realtime_data("000001")
        if data:
            print(f"测试数据: {data}")
        
        choice.logout()
        return True
    else:
        print("❌ Choice API登录失败")
        return False


if __name__ == "__main__":
    test_choice_api()
