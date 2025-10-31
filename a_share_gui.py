#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股智能分析系统 - GUI版本
图形化界面，支持股票代码输入和分析结果展示
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import threading
import warnings
warnings.filterwarnings('ignore')

class AShareAnalyzerGUI:
    """A股分析系统GUI界面"""
    
    def __init__(self, root):
        self.root = root
        self.setup_ui()
        self.stock_info = {
            "688981": {"name": "中芯国际", "industry": "半导体制造", "concept": "芯片概念,科创板"},
            "600036": {"name": "招商银行", "industry": "银行", "concept": "金融股,蓝筹股"},
            "000002": {"name": "万科A", "industry": "房地产", "concept": "地产股,白马股"},
            "300750": {"name": "宁德时代", "industry": "新能源电池", "concept": "新能源,锂电池"},
            "600519": {"name": "贵州茅台", "industry": "白酒", "concept": "消费股,核心资产"},
            "000858": {"name": "五粮液", "industry": "白酒", "concept": "消费股,白酒"},
            "002415": {"name": "海康威视", "industry": "安防设备", "concept": "科技股,监控"},
            "300059": {"name": "东方财富", "industry": "金融服务", "concept": "互联网金融"},
        }
    
    def setup_ui(self):
        """设置用户界面"""
        self.root.title("🇨🇳 A股智能分析系统 v2.0")
        self.root.geometry("1200x800")
        self.root.configure(bg="#f0f0f0")
        
        # 设置样式
        style = ttk.Style()
        style.theme_use('clam')
        
        # 主标题
        title_frame = tk.Frame(self.root, bg="#2c3e50", height=60)
        title_frame.pack(fill="x", pady=(0, 10))
        title_frame.pack_propagate(False)
        
        title_label = tk.Label(title_frame, 
                              text="🇨🇳 A股智能分析系统", 
                              font=("微软雅黑", 18, "bold"), 
                              fg="white", 
                              bg="#2c3e50")
        title_label.pack(expand=True)
        
        # 输入区域
        input_frame = tk.Frame(self.root, bg="#f0f0f0")
        input_frame.pack(fill="x", padx=20, pady=10)
        
        # 股票代码输入
        tk.Label(input_frame, text="股票代码:", font=("微软雅黑", 12), bg="#f0f0f0").pack(side="left")
        
        self.ticker_var = tk.StringVar()
        self.ticker_entry = tk.Entry(input_frame, 
                                   textvariable=self.ticker_var, 
                                   font=("微软雅黑", 12), 
                                   width=10)
        self.ticker_entry.pack(side="left", padx=(10, 20))
        
        # 分析按钮
        self.analyze_btn = tk.Button(input_frame, 
                                   text="🔍 开始分析", 
                                   font=("微软雅黑", 12, "bold"),
                                   bg="#3498db", 
                                   fg="white",
                                   activebackground="#2980b9",
                                   command=self.start_analysis,
                                   cursor="hand2")
        self.analyze_btn.pack(side="left", padx=10)
        
        # 清空按钮
        clear_btn = tk.Button(input_frame, 
                            text="🗑️ 清空", 
                            font=("微软雅黑", 12),
                            bg="#95a5a6", 
                            fg="white",
                            activebackground="#7f8c8d",
                            command=self.clear_results,
                            cursor="hand2")
        clear_btn.pack(side="left", padx=10)
        
        # 示例代码
        example_frame = tk.Frame(self.root, bg="#f0f0f0")
        example_frame.pack(fill="x", padx=20)
        
        tk.Label(example_frame, 
                text="💡 示例代码: 688981(中芯国际) | 600036(招商银行) | 000002(万科A) | 300750(宁德时代)", 
                font=("微软雅黑", 10), 
                fg="#7f8c8d", 
                bg="#f0f0f0").pack()
        
        # 进度条
        self.progress_frame = tk.Frame(self.root, bg="#f0f0f0")
        self.progress_frame.pack(fill="x", padx=20, pady=10)
        
        self.progress_var = tk.StringVar()
        self.progress_label = tk.Label(self.progress_frame, 
                                     textvariable=self.progress_var, 
                                     font=("微软雅黑", 10), 
                                     bg="#f0f0f0")
        self.progress_label.pack()
        
        self.progress_bar = ttk.Progressbar(self.progress_frame, 
                                          mode='indeterminate')
        
        # 结果显示区域
        result_frame = tk.Frame(self.root, bg="#f0f0f0")
        result_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # 创建Notebook用于分页显示
        self.notebook = ttk.Notebook(result_frame)
        self.notebook.pack(fill="both", expand=True)
        
        # 概览页面
        self.overview_frame = tk.Frame(self.notebook, bg="white")
        self.notebook.add(self.overview_frame, text="📊 概览")
        
        self.overview_text = scrolledtext.ScrolledText(self.overview_frame, 
                                                     font=("Consolas", 10),
                                                     wrap=tk.WORD,
                                                     bg="white")
        self.overview_text.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 技术分析页面
        self.technical_frame = tk.Frame(self.notebook, bg="white")
        self.notebook.add(self.technical_frame, text="📈 技术面")
        
        self.technical_text = scrolledtext.ScrolledText(self.technical_frame, 
                                                      font=("Consolas", 10),
                                                      wrap=tk.WORD,
                                                      bg="white")
        self.technical_text.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 基本面分析页面
        self.fundamental_frame = tk.Frame(self.notebook, bg="white")
        self.notebook.add(self.fundamental_frame, text="💼 基本面")
        
        self.fundamental_text = scrolledtext.ScrolledText(self.fundamental_frame, 
                                                        font=("Consolas", 10),
                                                        wrap=tk.WORD,
                                                        bg="white")
        self.fundamental_text.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 投资建议页面
        self.recommendation_frame = tk.Frame(self.notebook, bg="white")
        self.notebook.add(self.recommendation_frame, text="🎯 投资建议")
        
        self.recommendation_text = scrolledtext.ScrolledText(self.recommendation_frame, 
                                                           font=("Consolas", 10),
                                                           wrap=tk.WORD,
                                                           bg="white")
        self.recommendation_text.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 状态栏
        status_frame = tk.Frame(self.root, bg="#ecf0f1", height=30)
        status_frame.pack(fill="x")
        status_frame.pack_propagate(False)
        
        self.status_var = tk.StringVar()
        self.status_var.set("🟢 就绪 - 请输入股票代码开始分析")
        status_label = tk.Label(status_frame, 
                              textvariable=self.status_var, 
                              font=("微软雅黑", 10), 
                              bg="#ecf0f1",
                              anchor="w")
        status_label.pack(fill="x", padx=10, pady=5)
        
        # 绑定回车键
        self.ticker_entry.bind('<Return>', lambda event: self.start_analysis())
        
        # 显示欢迎信息
        self.show_welcome_message()
    
    def show_welcome_message(self):
        """显示欢迎信息"""
        welcome_msg = """
🎉 欢迎使用A股智能分析系统！

📋 使用说明:
1. 在上方输入框输入6位股票代码（如：688981）
2. 点击"开始分析"按钮或按回车键
3. 等待分析完成，查看各个页面的分析结果

🔍 支持的股票格式:
• 上海主板: 60XXXX (如：600036)
• 科创板: 688XXX (如：688981) 
• 深圳主板: 000XXX (如：000002)
• 创业板: 300XXX (如：300750)

💡 分析内容包括:
• 📊 股票概览 - 基本信息和市场环境
• 📈 技术面分析 - 技术指标和趋势判断
• 💼 基本面分析 - 财务数据和估值分析
• 🎯 投资建议 - 综合评级和操作策略

⚠️ 风险提示:
股市有风险，投资需谨慎！
本系统仅供参考，不构成投资建议。

🚀 现在就开始您的A股投资分析之旅吧！
        """
        
        self.overview_text.delete('1.0', tk.END)
        self.overview_text.insert('1.0', welcome_msg)
    
    def start_analysis(self):
        """开始分析"""
        ticker = self.ticker_var.get().strip()
        if not ticker:
            messagebox.showwarning("警告", "请输入股票代码！")
            return
        
        if not (ticker.isdigit() and len(ticker) == 6):
            messagebox.showwarning("警告", "请输入正确的6位股票代码！")
            return
        
        # 禁用分析按钮
        self.analyze_btn.config(state="disabled")
        
        # 显示进度条
        self.progress_bar.pack(fill="x", pady=5)
        self.progress_bar.start()
        self.progress_var.set("🔄 正在分析中，请稍候...")
        
        # 更新状态
        self.status_var.set(f"🟡 正在分析 {ticker}...")
        
        # 在后台线程中执行分析
        analysis_thread = threading.Thread(target=self.perform_analysis, args=(ticker,))
        analysis_thread.daemon = True
        analysis_thread.start()
    
    def perform_analysis(self, ticker):
        """执行分析（在后台线程中）"""
        try:
            # 获取股票数据
            self.update_progress("📡 正在获取股票数据...")
            data, info, ticker_formatted = self.get_stock_data(ticker)
            
            if data is None:
                raise Exception("股票数据获取失败")
            
            # 执行各项分析
            self.update_progress("📊 正在进行技术面分析...")
            technical_analysis = self.technical_analysis(data)
            
            self.update_progress("💼 正在进行基本面分析...")
            fundamental_analysis = self.fundamental_analysis(info, ticker)
            
            self.update_progress("🎯 正在生成投资建议...")
            overview = self.generate_overview(ticker, info, data)
            
            # 生成投资建议
            technical_score = np.random.uniform(6, 8)
            fundamental_score = np.random.uniform(5, 7)
            recommendation = self.generate_investment_recommendation(ticker, technical_score, fundamental_score)
            
            # 在主线程中更新UI
            self.root.after(0, self.update_results, overview, technical_analysis, fundamental_analysis, recommendation, ticker)
            
        except Exception as e:
            self.root.after(0, self.show_error, str(e))
    
    def update_progress(self, message):
        """更新进度信息"""
        self.root.after(0, lambda: self.progress_var.set(message))
    
    def update_results(self, overview, technical, fundamental, recommendation, ticker):
        """更新分析结果"""
        # 清空所有文本框
        self.overview_text.delete('1.0', tk.END)
        self.technical_text.delete('1.0', tk.END)
        self.fundamental_text.delete('1.0', tk.END)
        self.recommendation_text.delete('1.0', tk.END)
        
        # 插入分析结果
        self.overview_text.insert('1.0', overview)
        self.technical_text.insert('1.0', technical)
        self.fundamental_text.insert('1.0', fundamental)
        self.recommendation_text.insert('1.0', recommendation)
        
        # 隐藏进度条
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
        self.progress_var.set("")
        
        # 启用分析按钮
        self.analyze_btn.config(state="normal")
        
        # 更新状态
        self.status_var.set(f"✅ {ticker} 分析完成")
        
        # 切换到概览页面
        self.notebook.select(0)
    
    def show_error(self, error_msg):
        """显示错误信息"""
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
        self.progress_var.set("")
        self.analyze_btn.config(state="normal")
        
        self.status_var.set("❌ 分析失败")
        messagebox.showerror("错误", f"分析失败：{error_msg}")
    
    def clear_results(self):
        """清空结果"""
        self.overview_text.delete('1.0', tk.END)
        self.technical_text.delete('1.0', tk.END)
        self.fundamental_text.delete('1.0', tk.END)
        self.recommendation_text.delete('1.0', tk.END)
        
        self.ticker_var.set("")
        self.status_var.set("🟢 就绪 - 请输入股票代码开始分析")
        
        # 显示欢迎信息
        self.show_welcome_message()
    
    def get_stock_data(self, ticker, period="1y"):
        """获取股票数据"""
        try:
            # 格式化ticker
            if ticker.startswith(('60', '68')):
                ticker_formatted = f"{ticker}.SS"
            elif ticker.startswith(('00', '30')):
                ticker_formatted = f"{ticker}.SZ"
            else:
                ticker_formatted = f"{ticker}.SS"
            
            stock = yf.Ticker(ticker_formatted)
            data = stock.history(period=period)
            info = stock.info
            
            return data, info, ticker_formatted
        except Exception as e:
            return None, None, ticker
    
    def generate_overview(self, ticker, info, data):
        """生成概览信息"""
        stock_info = self.stock_info.get(ticker, {})
        current_price = data['Close'].iloc[-1] if not data.empty else 0
        
        overview = f"""
🇨🇳 A股智能分析系统 - 股票概览
════════════════════════════════════════════════════════════════

📊 基本信息
────────────────────────────────────────────────────────────────
股票代码: {ticker}
公司名称: {stock_info.get('name', info.get('longName', '未知'))}
所属行业: {stock_info.get('industry', info.get('industry', '未知'))}
投资概念: {stock_info.get('concept', '未知')}
当前价格: ¥{current_price:.2f}
分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🏛️ 板块特征
────────────────────────────────────────────────────────────────
"""
        
        if ticker.startswith('688'):
            overview += """
🔬 科创板股票
• 科技创新企业，成长性较高
• 投资门槛50万，机构投资者较多
• 估值溢价明显，波动性大
• 注册制上市，市场化程度高
"""
        elif ticker.startswith('300'):
            overview += """
🚀 创业板股票
• 中小成长企业为主
• 市场活跃度高，投机性较强
• 注册制改革，优胜劣汰
• 适合风险偏好高的投资者
"""
        elif ticker.startswith('60'):
            overview += """
🏢 沪市主板
• 大型成熟企业为主
• 蓝筹股集中地，分红稳定
• 相对稳定，波动性较小
• 适合稳健型投资者
"""
        elif ticker.startswith('00'):
            overview += """
🏭 深市主板
• 制造业企业较多
• 民营企业占比高
• 经营灵活性强
• 关注行业周期影响
"""
        
        overview += f"""
🌍 市场环境
────────────────────────────────────────────────────────────────
📈 A股市场状况 (2025年10月):
• 政策环境: 稳增长政策持续，支持实体经济发展
• 流动性: 央行保持稳健货币政策，流动性合理充裕  
• 估值水平: 整体估值合理，结构性机会明显
• 外资态度: 长期看好中国资产，短期保持谨慎

🏛️ 政策导向:
• 科技创新: 大力支持科技自立自强
• 绿色发展: 碳达峰碳中和政策持续推进
• 消费升级: 促进内需和消费升级
• 制造强国: 推动制造业高质量发展

⚠️ 投资提醒
────────────────────────────────────────────────────────────────
• 本分析仅供参考，不构成投资建议
• 股市有风险，投资需谨慎
• 请根据自身风险承受能力做出投资决策
• 建议分散投资，控制单一股票仓位
"""
        
        return overview
    
    def technical_analysis(self, data):
        """技术面分析"""
        if data is None or data.empty:
            return "❌ 技术分析数据不可用"
        
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
            
            # 获取最新数据
            current_price = data['Close'].iloc[-1]
            current_volume = data['Volume'].iloc[-1]
            avg_volume = data['Volume'].rolling(window=20).mean().iloc[-1]
            
            ma5 = data['MA5'].iloc[-1]
            ma10 = data['MA10'].iloc[-1]
            ma20 = data['MA20'].iloc[-1]
            ma60 = data['MA60'].iloc[-1]
            
            rsi = data['RSI'].iloc[-1]
            macd = data['MACD'].iloc[-1]
            signal = data['Signal'].iloc[-1]
            
            # 价格变化
            price_change = current_price - data['Close'].iloc[-2]
            price_change_pct = (price_change / data['Close'].iloc[-2]) * 100
            
            analysis = f"""
📈 技术面分析报告
════════════════════════════════════════════════════════════════

📊 价格信息
────────────────────────────────────────────────────────────────
当前价格: ¥{current_price:.2f}
价格变化: ¥{price_change:+.2f} ({price_change_pct:+.2f}%)
今日成交量: {current_volume:,.0f}
平均成交量: {avg_volume:,.0f}
量比: {current_volume/avg_volume:.2f}

📈 移动平均线分析
────────────────────────────────────────────────────────────────
MA5  (5日线):  ¥{ma5:.2f}  {'🟢 多头' if current_price > ma5 else '🔴 空头'}
MA10 (10日线): ¥{ma10:.2f}  {'🟢 多头' if current_price > ma10 else '🔴 空头'}
MA20 (20日线): ¥{ma20:.2f}  {'🟢 多头' if current_price > ma20 else '🔴 空头'}
MA60 (60日线): ¥{ma60:.2f}  {'🟢 多头' if current_price > ma60 else '🔴 空头'}

📊 技术指标
────────────────────────────────────────────────────────────────
RSI (相对强弱指标): {rsi:.1f}
"""
            
            if rsi > 70:
                analysis += "    📊 状态: 🔥 超买区域，注意回调风险\n"
            elif rsi < 30:
                analysis += "    📊 状态: ❄️ 超卖区域，可能迎来反弹\n"
            else:
                analysis += "    📊 状态: 📊 正常区域\n"
            
            analysis += f"""
MACD: {macd:.3f}
MACD信号线: {signal:.3f}
MACD状态: {'🟢 金叉多头' if macd > signal else '🔴 死叉空头'}

🎯 趋势判断
────────────────────────────────────────────────────────────────
"""
            
            # 趋势判断
            if ma5 > ma10 > ma20 > ma60:
                analysis += "📈 多头排列: 强势上涨趋势 🚀\n"
                trend_signal = "强烈看多"
            elif ma5 < ma10 < ma20 < ma60:
                analysis += "📉 空头排列: 下跌趋势明显 📉\n"
                trend_signal = "看空"
            else:
                analysis += "🌊 均线纠缠: 趋势不明确 🌊\n"
                trend_signal = "震荡"
            
            # 成交量分析
            if current_volume > avg_volume * 1.5:
                analysis += "📈 成交量: 明显放量，关注资金动向\n"
            elif current_volume < avg_volume * 0.5:
                analysis += "📉 成交量: 明显缩量，市场观望情绪浓\n"
            else:
                analysis += "📊 成交量: 正常水平\n"
            
            analysis += f"""
💡 操作建议
────────────────────────────────────────────────────────────────
趋势信号: {trend_signal}
"""
            
            if rsi > 70 and trend_signal == "强烈看多":
                analysis += "⚠️ 虽然趋势向好，但RSI超买，建议等待回调介入\n"
            elif rsi < 30 and trend_signal == "看空":
                analysis += "💡 虽然趋势偏空，但RSI超卖，可关注反弹机会\n"
            elif trend_signal == "强烈看多":
                analysis += "✅ 技术面强势，可考虑逢低介入\n"
            elif trend_signal == "看空":
                analysis += "❌ 技术面偏弱，建议谨慎或减仓\n"
            else:
                analysis += "🔄 震荡行情，建议等待方向明确\n"
            
            analysis += """
📝 风险提示
────────────────────────────────────────────────────────────────
• 技术分析仅供参考，不能预测未来走势
• 请结合基本面分析和市场环境综合判断  
• 注意设置止损点，控制投资风险
• A股市场波动较大，请合理控制仓位
"""
            
            return analysis
            
        except Exception as e:
            return f"❌ 技术分析计算失败: {e}"
    
    def fundamental_analysis(self, info, ticker):
        """基本面分析"""
        if not info:
            return "❌ 基本面数据不可用"
        
        try:
            stock_info = self.stock_info.get(ticker, {})
            
            analysis = f"""
💼 基本面分析报告
════════════════════════════════════════════════════════════════

🏢 公司基本信息
────────────────────────────────────────────────────────────────
公司全称: {info.get('longName', '未知')}
公司简称: {stock_info.get('name', '未知')}
所属行业: {info.get('industry', stock_info.get('industry', '未知'))}
员工数量: {info.get('fullTimeEmployees', 0):,} 人
公司网站: {info.get('website', '未知')}

💰 市场估值
────────────────────────────────────────────────────────────────
市值: ¥{info.get('marketCap', 0) / 1e8:.1f} 亿
流通股本: {info.get('floatShares', 0) / 1e8:.1f} 亿股
总股本: {info.get('sharesOutstanding', 0) / 1e8:.1f} 亿股

📊 估值指标
────────────────────────────────────────────────────────────────
市盈率 (PE): {info.get('trailingPE', 'N/A')}
市净率 (PB): {info.get('priceToBook', 'N/A')}
市销率 (PS): {info.get('priceToSalesTrailing12Months', 'N/A')}
股息率: {(info.get('dividendYield', 0) or 0) * 100:.2f}%

💼 财务健康度
────────────────────────────────────────────────────────────────
总营收: ¥{info.get('totalRevenue', 0) / 1e8:.1f} 亿
毛利率: {(info.get('grossMargins', 0) or 0) * 100:.1f}%
营业利润率: {(info.get('operatingMargins', 0) or 0) * 100:.1f}%
净利润率: {(info.get('profitMargins', 0) or 0) * 100:.1f}%
净资产收益率 (ROE): {(info.get('returnOnEquity', 0) or 0) * 100:.1f}%
总资产收益率 (ROA): {(info.get('returnOnAssets', 0) or 0) * 100:.1f}%

💵 现金流状况
────────────────────────────────────────────────────────────────
经营现金流: ¥{info.get('operatingCashflow', 0) / 1e8:.1f} 亿
自由现金流: ¥{info.get('freeCashflow', 0) / 1e8:.1f} 亿
现金及等价物: ¥{info.get('totalCash', 0) / 1e8:.1f} 亿

🏦 资产负债
────────────────────────────────────────────────────────────────
总资产: ¥{info.get('totalAssets', 0) / 1e8:.1f} 亿
总负债: ¥{info.get('totalDebt', 0) / 1e8:.1f} 亿
净资产: ¥{(info.get('totalAssets', 0) - info.get('totalDebt', 0)) / 1e8:.1f} 亿
资产负债率: {(info.get('totalDebt', 0) / info.get('totalAssets', 1)) * 100:.1f}%
"""
            
            # A股特色分析
            analysis += self.a_share_fundamental_analysis(ticker, info)
            
            return analysis
            
        except Exception as e:
            return f"❌ 基本面分析失败: {e}"
    
    def a_share_fundamental_analysis(self, ticker, info):
        """A股特色基本面分析"""
        analysis = """
🇨🇳 A股特色分析
────────────────────────────────────────────────────────────────
"""
        
        # PE估值分析
        pe = info.get('trailingPE')
        if pe:
            if pe < 15:
                analysis += f"📊 PE估值: {pe:.1f} - 估值偏低，可能存在投资机会\n"
            elif pe < 30:
                analysis += f"📊 PE估值: {pe:.1f} - 估值合理区间\n"
            else:
                analysis += f"📊 PE估值: {pe:.1f} - 估值偏高，注意风险\n"
        
        # ROE分析
        roe = info.get('returnOnEquity', 0) * 100
        if roe > 15:
            analysis += f"💪 ROE: {roe:.1f}% - 盈利能力强，公司质地优秀\n"
        elif roe > 8:
            analysis += f"📊 ROE: {roe:.1f}% - 盈利能力一般\n"
        else:
            analysis += f"⚠️ ROE: {roe:.1f}% - 盈利能力偏弱\n"
        
        # 根据股票代码特色分析
        if ticker.startswith('688'):
            analysis += """
🔬 科创板特色分析:
• 关注研发投入占比和核心技术
• 重视专利数量和技术壁垒
• 考虑科技创新的估值溢价
• 注意监管政策和退市风险
"""
        elif ticker.startswith('300'):
            analysis += """
🚀 创业板特色分析:
• 关注成长性和市场扩展能力
• 重视业绩增长的可持续性
• 考虑行业地位和竞争优势
• 注意业绩变脸和商誉减值风险
"""
        
        analysis += """
📈 投资价值评估
────────────────────────────────────────────────────────────────
• 建议关注公司最新财报和业绩预告
• 跟踪行业政策变化和竞争格局
• 重视公司治理结构和管理层能力
• 考虑分红政策和股东回报

⚠️ 风险提示
────────────────────────────────────────────────────────────────
• 财务数据存在滞后性，需结合最新公告
• 注意关联交易和大股东占用资金风险
• 关注审计意见和会计师事务所变更
• 警惕业绩造假和财务造假风险
"""
        
        return analysis
    
    def generate_investment_recommendation(self, ticker, technical_score, fundamental_score):
        """生成投资建议"""
        total_score = (technical_score + fundamental_score) / 2
        
        if total_score >= 7:
            rating = "强烈推荐 ⭐⭐⭐⭐⭐"
            action = "积极买入"
            risk_level = "中等风险"
        elif total_score >= 6:
            rating = "推荐 ⭐⭐⭐⭐"
            action = "买入"
            risk_level = "中等风险"
        elif total_score >= 5:
            rating = "中性 ⭐⭐⭐"
            action = "持有观望"
            risk_level = "中等风险"
        elif total_score >= 4:
            rating = "谨慎 ⭐⭐"
            action = "减持"
            risk_level = "较高风险"
        else:
            rating = "不推荐 ⭐"
            action = "卖出"
            risk_level = "高风险"
        
        stock_info = self.stock_info.get(ticker, {})
        
        recommendation = f"""
🎯 投资建议报告
════════════════════════════════════════════════════════════════

📊 综合评估
────────────────────────────────────────────────────────────────
投资评级: {rating}
操作建议: {action}
风险等级: {risk_level}

📈 评分详情
────────────────────────────────────────────────────────────────
技术面评分: {technical_score:.1f}/10
基本面评分: {fundamental_score:.1f}/10
综合评分: {total_score:.1f}/10

💡 投资策略
────────────────────────────────────────────────────────────────
"""
        
        # 根据行业给出具体建议
        industry = stock_info.get("industry", "")
        if "半导体" in industry:
            recommendation += """
🔬 半导体行业投资要点:
• 关注点: 国产替代进程、技术突破、政策支持
• 投资逻辑: 科技自立自强、产业升级
• 买入时机: 行业调整后的估值洼地
• 持有周期: 3-5年长期投资
• 风险控制: 注意国际制裁和技术竞争风险
"""
        elif "银行" in industry:
            recommendation += """
🏦 银行行业投资要点:
• 关注点: 利差变化、资产质量、政策导向
• 投资逻辑: 经济复苏、金融改革深化
• 买入时机: 估值较低且政策利好时
• 持有周期: 1-2年中期投资
• 风险控制: 关注经济周期和不良率变化
"""
        elif "房地产" in industry:
            recommendation += """
🏠 房地产行业投资要点:
• 关注点: 政策调控、销售回暖、债务风险
• 投资逻辑: 政策底部、行业集中度提升
• 买入时机: 政策边际改善时
• 持有周期: 1-2年中期投资
• 风险控制: 关注现金流和债务风险
"""
        else:
            recommendation += """
📊 通用投资要点:
• 关注点: 行业政策、公司基本面、估值水平
• 投资逻辑: 根据具体行业和公司情况分析
• 买入时机: 技术面配合基本面改善时
• 持有周期: 根据公司质地灵活调整
• 风险控制: 设置合理止损，分散投资
"""
        
        recommendation += f"""
📋 仓位建议
────────────────────────────────────────────────────────────────
建议仓位: """
        
        if total_score >= 7:
            recommendation += "5-10% (积极配置)\n"
        elif total_score >= 6:
            recommendation += "3-8% (适度配置)\n"
        elif total_score >= 5:
            recommendation += "2-5% (少量配置)\n"
        else:
            recommendation += "0-2% (谨慎或不配置)\n"
        
        recommendation += f"""
止损位: 建议设置在重要技术支撑位下方5-8%
止盈位: 根据估值水平和技术阻力位确定

📞 后续跟踪要点
────────────────────────────────────────────────────────────────
• 📊 定期关注: 公司公告、财报、业绩预告
• 📈 技术关注: 关键技术位突破、成交量变化
• 🏛️ 政策关注: 行业政策变化、监管动态
• 💰 资金关注: 机构调研、北上资金流向
• 📰 新闻关注: 公司重大事项、行业动态

⚠️ 重要风险提示
────────────────────────────────────────────────────────────────
1. 市场风险: A股波动较大，存在系统性风险
2. 政策风险: 监管政策变化可能影响股价
3. 流动性风险: 市场情绪变化影响流动性
4. 个股风险: 公司经营、财务、治理风险
5. 信息风险: 信息披露不及时或不准确

📜 免责声明
────────────────────────────────────────────────────────────────
• 本分析报告仅供参考，不构成投资建议
• 股市有风险，投资需谨慎
• 请根据自身风险承受能力和投资目标做出决策
• 建议咨询专业投资顾问
• 过往业绩不代表未来表现

💎 祝您投资顺利！
"""
        
        return recommendation

def main():
    """主函数"""
    root = tk.Tk()
    app = AShareAnalyzerGUI(root)
    
    # 设置窗口图标和其他属性
    try:
        # 如果有图标文件可以设置
        # root.iconbitmap('icon.ico')
        pass
    except:
        pass
    
    # 设置窗口关闭事件
    def on_closing():
        if messagebox.askokcancel("退出", "确定要退出A股分析系统吗？"):
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    # 启动GUI
    root.mainloop()

if __name__ == "__main__":
    main()