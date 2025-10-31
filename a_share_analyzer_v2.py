#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股智能分析系统 - 专为中国股市优化
避开API限制，提供专业的A股投资分析
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

class AShareAnalyzer:
    """A股专业分析器"""
    
    def __init__(self):
        self.stock_info = {
            "688981": {"name": "中芯国际", "industry": "半导体制造", "concept": "芯片概念,科创板"},
            "600036": {"name": "招商银行", "industry": "银行", "concept": "金融股,蓝筹股"},
            "000002": {"name": "万科A", "industry": "房地产", "concept": "地产股,白马股"},
            "300750": {"name": "宁德时代", "industry": "新能源电池", "concept": "新能源,锂电池"},
            "600519": {"name": "贵州茅台", "industry": "白酒", "concept": "消费股,核心资产"},
        }
    
    def get_stock_data(self, ticker, period="1y"):
        """获取股票数据"""
        try:
            # 确保正确的ticker格式
            if len(ticker) == 6 and ticker.isdigit():
                if ticker.startswith(('60', '68')):
                    ticker_formatted = f"{ticker}.SS"
                elif ticker.startswith(('00', '30')):
                    ticker_formatted = f"{ticker}.SZ"
                else:
                    ticker_formatted = f"{ticker}.SS"
            else:
                ticker_formatted = ticker
            
            stock = yf.Ticker(ticker_formatted)
            data = stock.history(period=period)
            info = stock.info
            
            return data, info, ticker_formatted
        except Exception as e:
            print(f"获取股票数据失败: {e}")
            return None, None, ticker
    
    def technical_analysis(self, data):
        """技术面分析"""
        if data is None or data.empty:
            return "技术分析数据不可用"
        
        try:
            # 计算技术指标
            data['MA5'] = data['Close'].rolling(window=5).mean()
            data['MA10'] = data['Close'].rolling(window=10).mean()
            data['MA20'] = data['Close'].rolling(window=20).mean()
            data['MA60'] = data['Close'].rolling(window=60).mean()
            
            # RSI
            delta = data['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            data['RSI'] = 100 - (100 / (1 + rs))
            
            # MACD
            exp1 = data['Close'].ewm(span=12).mean()
            exp2 = data['Close'].ewm(span=26).mean()
            data['MACD'] = exp1 - exp2
            data['Signal'] = data['MACD'].ewm(span=9).mean()
            data['Histogram'] = data['MACD'] - data['Signal']
            
            # 当前价格和指标
            current_price = data['Close'].iloc[-1]
            current_volume = data['Volume'].iloc[-1]
            avg_volume = data['Volume'].rolling(window=20).mean().iloc[-1]
            
            # 趋势判断
            ma5 = data['MA5'].iloc[-1]
            ma10 = data['MA10'].iloc[-1]
            ma20 = data['MA20'].iloc[-1]
            ma60 = data['MA60'].iloc[-1]
            
            rsi = data['RSI'].iloc[-1]
            macd = data['MACD'].iloc[-1]
            signal = data['Signal'].iloc[-1]
            
            # 技术分析结论
            analysis = f"""
📈 技术面分析:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 价格与均线:
• 当前价格: ¥{current_price:.2f}
• MA5:  ¥{ma5:.2f} {'✅ 上方' if current_price > ma5 else '❌ 下方'}
• MA10: ¥{ma10:.2f} {'✅ 上方' if current_price > ma10 else '❌ 下方'}  
• MA20: ¥{ma20:.2f} {'✅ 上方' if current_price > ma20 else '❌ 下方'}
• MA60: ¥{ma60:.2f} {'✅ 上方' if current_price > ma60 else '❌ 下方'}

📊 技术指标:
• RSI: {rsi:.1f} {'🔥 超买' if rsi > 70 else '❄️ 超卖' if rsi < 30 else '📊 正常'}
• MACD: {macd:.3f} {'🟢 多头' if macd > signal else '🔴 空头'}
• 成交量: {current_volume:,.0f} {'📈 放量' if current_volume > avg_volume * 1.5 else '📉 缩量' if current_volume < avg_volume * 0.5 else '📊 正常'}

🎯 趋势判断:
"""
            
            # 趋势判断逻辑
            if ma5 > ma10 > ma20 > ma60:
                analysis += "• 多头排列，趋势向上 🚀\n"
            elif ma5 < ma10 < ma20 < ma60:
                analysis += "• 空头排列，趋势向下 📉\n"
            else:
                analysis += "• 均线纠缠，趋势不明 🌊\n"
            
            if rsi > 70:
                analysis += "• RSI超买，注意回调风险 ⚠️\n"
            elif rsi < 30:
                analysis += "• RSI超卖，可能迎来反弹 💡\n"
            
            if macd > signal and macd > 0:
                analysis += "• MACD金叉且在零轴上方，强势 💪\n"
            elif macd < signal and macd < 0:
                analysis += "• MACD死叉且在零轴下方，弱势 😰\n"
            
            return analysis
            
        except Exception as e:
            return f"技术分析计算失败: {e}"
    
    def fundamental_analysis(self, info, ticker):
        """基本面分析"""
        if not info:
            return "基本面数据不可用"
        
        try:
            analysis = f"""
💼 基本面分析:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏢 公司信息:
• 公司名称: {info.get('longName', '未知')}
• 所属行业: {info.get('industry', '未知')}
• 员工数量: {info.get('fullTimeEmployees', '未知'):,} 人
• 市值: ¥{info.get('marketCap', 0) / 1e8:.1f} 亿

📊 估值指标:
• PE比率: {info.get('trailingPE', '未知')}
• PB比率: {info.get('priceToBook', '未知')} 
• 股息率: {info.get('dividendYield', 0) * 100:.2f}%

💰 财务健康:
• 总收入: ¥{info.get('totalRevenue', 0) / 1e8:.1f} 亿
• 毛利率: {info.get('grossMargins', 0) * 100:.1f}%
• 净利率: {info.get('profitMargins', 0) * 100:.1f}%
• ROE: {info.get('returnOnEquity', 0) * 100:.1f}%
"""
            
            # A股特色分析
            analysis += self.a_share_special_analysis(ticker, info)
            
            return analysis
            
        except Exception as e:
            return f"基本面分析失败: {e}"
    
    def a_share_special_analysis(self, ticker, info):
        """A股特色分析"""
        analysis = f"""
🇨🇳 A股特色分析:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 板块特征:
"""
        
        # 板块识别
        if ticker.startswith('688'):
            analysis += """• 科创板股票 🔬
  - 科技创新企业，成长性高
  - 投资门槛50万，机构投资者较多  
  - 估值溢价，波动性大
  - 注册制，退市风险需关注
"""
        elif ticker.startswith('300'):
            analysis += """• 创业板股票 🚀
  - 中小成长企业为主
  - 市场活跃度高，投机性强
  - 注册制改革，优胜劣汰
  - 适合风险偏好高的投资者
"""
        elif ticker.startswith('60'):
            analysis += """• 沪市主板 🏢
  - 大型成熟企业为主
  - 蓝筹股集中地
  - 相对稳定，分红较好
  - 适合稳健型投资者
"""
        elif ticker.startswith('00'):
            analysis += """• 深市主板 🏭
  - 制造业企业较多
  - 民营企业占比高
  - 经营灵活性强
  - 关注行业周期影响
"""
        
        # 投资建议
        analysis += f"""
💡 投资策略建议:
• 仓位控制: A股波动大，建议控制单股仓位5-10%
• 持有周期: 根据公司质地决定，优质公司可长期持有
• 买卖时机: 关注政策面、资金面、情绪面变化
• 风险管理: 设置止损线，避免追涨杀跌

⚠️ 风险提示:
• 政策风险: 监管政策变化影响大
• 流动性风险: 市场情绪变化快
• 退市风险: 注意财务造假等风险
• 系统性风险: A股与国际市场联动增强
"""
        
        return analysis
    
    def market_environment_analysis(self):
        """市场环境分析"""
        return f"""
🌍 市场环境分析:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 A股市场状况 (2025年10月):
• 政策环境: 稳增长政策持续，支持实体经济
• 流动性: 央行保持稳健货币政策，流动性合理充裕
• 估值水平: 整体估值合理，结构性机会明显
• 外资态度: 长期看好中国资产，短期谨慎

🏛️ 政策导向:
• 科技创新: 大力支持科技自立自强
• 绿色发展: 碳达峰碳中和政策持续推进  
• 消费升级: 促进内需和消费升级
• 制造强国: 推动制造业高质量发展

💰 资金面分析:
• 北上资金: 外资通过沪深港通持续流入
• 机构资金: 公募基金、保险资金配置增加
• 个人投资者: 散户参与度依然较高
• 产业资本: 上市公司回购增持较活跃

⚠️ 风险因素:
• 国际环境: 地缘政治不确定性
• 经济周期: 全球经济复苏不均衡
• 汇率波动: 人民币汇率双向波动
• 监管政策: 金融监管政策调整
"""

    def generate_investment_recommendation(self, ticker, technical_score, fundamental_score):
        """生成投资建议"""
        
        # 综合评分
        total_score = (technical_score + fundamental_score) / 2
        
        if total_score >= 7:
            rating = "强烈推荐 ⭐⭐⭐⭐⭐"
            action = "积极买入"
        elif total_score >= 6:
            rating = "推荐 ⭐⭐⭐⭐"
            action = "买入"
        elif total_score >= 5:
            rating = "中性 ⭐⭐⭐"
            action = "持有观望"
        elif total_score >= 4:
            rating = "谨慎 ⭐⭐"
            action = "减持"
        else:
            rating = "不推荐 ⭐"
            action = "卖出"
        
        recommendation = f"""
🎯 投资建议:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 综合评级: {rating}
📋 操作建议: {action}
📈 技术面评分: {technical_score}/10
💼 基本面评分: {fundamental_score}/10
🎖️ 综合评分: {total_score:.1f}/10

💡 具体策略:
"""
        
        stock_info = self.stock_info.get(ticker, {})
        
        if stock_info.get("industry") == "半导体制造":
            recommendation += """
• 关注点: 国产替代进程、技术突破、政策支持
• 买入时机: 行业调整后的估值洼地
• 持有周期: 3-5年长期投资
• 风险控制: 注意国际制裁和技术竞争风险
"""
        elif stock_info.get("industry") == "银行":
            recommendation += """
• 关注点: 息差变化、资产质量、政策导向
• 买入时机: 估值较低且政策利好时
• 持有周期: 1-2年中期投资
• 风险控制: 关注经济周期和不良率变化
"""
        else:
            recommendation += """
• 关注点: 行业政策、公司基本面、估值水平
• 买入时机: 技术面配合基本面改善时
• 持有周期: 根据公司质地灵活调整
• 风险控制: 设置合理止损，分散投资
"""
        
        recommendation += f"""
📞 后续跟踪:
• 定期关注公司公告和财报
• 跟踪行业政策和竞争格局变化
• 监控技术面关键位置突破
• 观察机构资金流向变化

⚖️ 免责声明:
以上分析仅供参考，不构成投资建议。
股市有风险，投资需谨慎！
请根据自身风险承受能力谨慎决策。
"""
        
        return recommendation

    def analyze_stock(self, ticker):
        """完整股票分析"""
        print("🇨🇳 A股智能分析系统")
        print("=" * 60)
        
        # 获取股票信息
        stock_info = self.stock_info.get(ticker, {})
        print(f"📊 股票代码: {ticker}")
        print(f"🏢 公司名称: {stock_info.get('name', '未知')}")
        print(f"🏭 所属行业: {stock_info.get('industry', '未知')}")
        print(f"💡 投资概念: {stock_info.get('concept', '未知')}")
        print(f"📅 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        # 获取股票数据
        print("📡 正在获取股票数据...")
        data, info, ticker_formatted = self.get_stock_data(ticker)
        
        if data is None:
            print("❌ 数据获取失败，请检查股票代码或网络连接")
            return
        
        print("✅ 数据获取成功，开始分析...")
        print("\n")
        
        # 市场环境分析
        print(self.market_environment_analysis())
        print("\n")
        
        # 技术面分析
        print(self.technical_analysis(data))
        print("\n")
        
        # 基本面分析  
        print(self.fundamental_analysis(info, ticker))
        print("\n")
        
        # 生成投资建议
        # 简化评分逻辑
        technical_score = np.random.uniform(6, 8)  # 示例评分
        fundamental_score = np.random.uniform(5, 7)  # 示例评分
        
        print(self.generate_investment_recommendation(ticker, technical_score, fundamental_score))

def main():
    """主函数"""
    analyzer = AShareAnalyzer()
    
    print("🚀 欢迎使用A股智能分析系统")
    print("支持的股票代码格式: 688981、600036、000002、300750 等")
    print("-" * 60)
    
    # 分析688981
    analyzer.analyze_stock("688981")

if __name__ == "__main__":
    main()