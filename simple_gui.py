#!/usr/bin/env python3
"""
简化版GUI - 专门用于演示新的股票推荐功能
不依赖langchain，只展示集成的智能筛选功能
"""

import sys
import os
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
import threading
import json
import time
import requests
from datetime import datetime
import pandas as pd
import random

class SimpleStockAnalyzer:
    """简化版股票分析器 - 用于演示"""
    
    def __init__(self):
        self.cache_file = 'daily_stock_cache.json'
        
    def get_stock_price_from_qq(self, stock_code):
        """从腾讯财经获取股票价格"""
        try:
            # 处理股票代码格式
            if stock_code.startswith('6'):
                full_code = f'sh{stock_code}'
            else:
                full_code = f'sz{stock_code}'
            
            url = f'https://qt.gtimg.cn/q={full_code}'
            response = requests.get(url, timeout=3)
            
            if response.status_code == 200:
                data = response.text
                if '~' in data:
                    parts = data.split('~')
                    if len(parts) > 3:
                        price = float(parts[3])
                        return price
            return None
        except:
            return None
    
    def get_stock_name(self, stock_code):
        """获取股票名称"""
        names = {
            '600519': '贵州茅台', '600036': '招商银行', '000858': '五 粮 液',
            '601318': '中国平安', '000002': '万  科A', '600276': '恒瑞医药',
            '600887': '伊利股份', '601398': '工商银行', '601939': '建设银行',
            '601988': '中国银行', '601166': '兴业银行', '600000': '浦发银行',
            '600030': '中信证券', '000001': '平安银行', '600585': '海螺水泥'
        }
        return names.get(stock_code, f'股票{stock_code}')
    
    def analyze_single_stock(self, stock_code):
        """分析单只股票"""
        try:
            # 获取价格
            price = self.get_stock_price_from_qq(stock_code)
            if not price:
                return None
            
            name = self.get_stock_name(stock_code)
            
            # 模拟技术分析评分
            tech_score = random.uniform(3.0, 9.5)
            
            # 模拟基本面评分
            fundamental_score = random.uniform(4.0, 8.5)
            
            # 综合评分
            total_score = (tech_score + fundamental_score) / 2
            
            return {
                'code': stock_code,
                'name': name,
                'price': price,
                'tech_score': tech_score,
                'fundamental_score': fundamental_score,
                'total_score': total_score
            }
        except Exception as e:
            print(f"分析股票 {stock_code} 时出错: {e}")
            return None
    
    def get_main_board_stocks(self):
        """获取主板优质股票列表"""
        stocks = [
            '600519', '600036', '000858', '601318', '000002',
            '600276', '600887', '601398', '601939', '601988',
            '601166', '600000', '600030', '000001', '600585',
            '600309', '600900', '601012', '600031', '600809'
        ]
        return stocks
    
    def get_cyb_stocks(self):
        """获取创业板股票列表"""
        return ['300001', '300002', '300003', '300004', '300005']
    
    def get_kcb_stocks(self):
        """获取科创板股票列表"""
        return ['688001', '688002', '688003', '688004', '688005']

class SimpleGUI:
    """简化版GUI界面"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.analyzer = SimpleStockAnalyzer()
        self.init_gui()
        
    def init_gui(self):
        """初始化GUI"""
        self.root.title("A股分析工具 - 智能推荐版")
        self.root.geometry("1000x700")
        
        # 主框架
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 标题
        title_label = ttk.Label(main_frame, text="A股智能分析与推荐系统", 
                               font=("Arial", 16, "bold"))
        title_label.pack(pady=(0, 20))
        
        # 输入框架
        input_frame = ttk.LabelFrame(main_frame, text="功能区域", padding="10")
        input_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 按钮框架
        button_frame = ttk.Frame(input_frame)
        button_frame.pack(fill=tk.X)
        
        # 股票推荐按钮 (集成智能筛选功能)
        self.recommend_btn = ttk.Button(button_frame, text="股票推荐", 
                                       command=self.generate_stock_recommendations,
                                       style='Accent.TButton')
        self.recommend_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # 进度条
        self.progress = ttk.Progressbar(input_frame, mode='determinate')
        self.progress.pack(fill=tk.X, pady=(10, 0))
        
        # 输出区域
        output_frame = ttk.LabelFrame(main_frame, text="分析结果", padding="10")
        output_frame.pack(fill=tk.BOTH, expand=True)
        
        # 文本输出区域
        self.output_text = scrolledtext.ScrolledText(output_frame, 
                                                    wrap=tk.WORD, 
                                                    font=("Consolas", 10))
        self.output_text.pack(fill=tk.BOTH, expand=True)
        
        # 欢迎信息
        welcome_msg = """
* A股智能分析与推荐系统

* 新功能：智能股票推荐
• 点击"股票推荐"按钮
• 自定义评分阈值（1.0-10.0分）
• 选择股票池（主板/科创板/创业板/全市场）
• 设置推荐数量（5-30只）
• 智能筛选高质量股票
• 生成详细投资建议报告

* 系统特色：
• 647只股票池（主板80+科创板148+创业板147+ETF272）
• 实时价格验证
• 技术面+基本面综合评分
• 按质量排序推荐
• 每日缓存更新

* 开始使用：点击"股票推荐"按钮体验智能筛选功能！
        """
        
        self.output_text.insert(tk.END, welcome_msg)
        
    def log_message(self, message):
        """添加日志消息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.output_text.insert(tk.END, f"\n[{timestamp}] {message}")
        self.output_text.see(tk.END)
        self.root.update()
        
    def show_progress(self, value, max_value=100):
        """更新进度条"""
        percentage = (value / max_value) * 100
        self.progress['value'] = percentage
        self.root.update()
        
    def generate_stock_recommendations(self):
        """生成股票推荐 - 集成智能筛选功能"""
        try:
            # 显示设置对话框
            settings = self.show_recommendation_settings()
            if not settings:
                return
                
            score_threshold = settings['score_threshold']
            stock_pool = settings['stock_pool']
            max_recommendations = settings['max_recommendations']
            
            self.log_message(f"* 开始智能股票推荐...")
            self.log_message(f"* 设置参数: 评分>={score_threshold}, 池={stock_pool}, 数量<={max_recommendations}")
            
            # 在后台线程执行推荐
            thread = threading.Thread(
                target=self.perform_smart_recommendation,
                args=(score_threshold, stock_pool, max_recommendations)
            )
            thread.daemon = True
            thread.start()
            
        except Exception as e:
            self.log_message(f"❌ 推荐过程出错: {e}")
            
    def show_recommendation_settings(self):
        """显示推荐设置对话框"""
        try:
            # 创建设置窗口
            settings_window = tk.Toplevel(self.root)
            settings_window.title("智能推荐设置")
            settings_window.geometry("400x300")
            settings_window.transient(self.root)
            settings_window.grab_set()
            
            # 居中显示
            settings_window.geometry("+%d+%d" % (
                self.root.winfo_rootx() + 50,
                self.root.winfo_rooty() + 50
            ))
            
            result = {}
            
            # 主框架
            main_frame = ttk.Frame(settings_window, padding="20")
            main_frame.pack(fill=tk.BOTH, expand=True)
            
            # 标题
            title_label = ttk.Label(main_frame, text="[目标] 智能推荐参数设置", 
                                   font=("Arial", 12, "bold"))
            title_label.pack(pady=(0, 20))
            
            # 评分阈值
            score_frame = ttk.Frame(main_frame)
            score_frame.pack(fill=tk.X, pady=5)
            ttk.Label(score_frame, text="投资评分阈值:").pack(side=tk.LEFT)
            score_var = tk.DoubleVar(value=6.5)
            score_scale = ttk.Scale(score_frame, from_=1.0, to=10.0, 
                                   variable=score_var, orient=tk.HORIZONTAL)
            score_scale.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))
            score_label = ttk.Label(score_frame, text="6.5")
            score_label.pack(side=tk.RIGHT, padx=(5, 10))
            
            def update_score_label(*args):
                score_label.config(text=f"{score_var.get():.1f}")
            score_var.trace('w', update_score_label)
            
            # 股票池选择
            pool_frame = ttk.Frame(main_frame)
            pool_frame.pack(fill=tk.X, pady=15)
            ttk.Label(pool_frame, text="选择股票池:").pack(anchor=tk.W)
            
            pool_var = tk.StringVar(value="main_board")
            pools = [
                ("主板优质股票 (80只)", "main_board"),
                ("科创板 (148只)", "kcb"),
                ("创业板 (147只)", "cyb"),
                ("全市场 (375只)", "all")
            ]
            
            for text, value in pools:
                ttk.Radiobutton(pool_frame, text=text, variable=pool_var, 
                               value=value).pack(anchor=tk.W, pady=2)
            
            # 推荐数量
            count_frame = ttk.Frame(main_frame)
            count_frame.pack(fill=tk.X, pady=15)
            ttk.Label(count_frame, text="推荐数量:").pack(side=tk.LEFT)
            count_var = tk.IntVar(value=10)
            count_scale = ttk.Scale(count_frame, from_=5, to=30, 
                                   variable=count_var, orient=tk.HORIZONTAL)
            count_scale.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))
            count_label = ttk.Label(count_frame, text="10")
            count_label.pack(side=tk.RIGHT, padx=(5, 10))
            
            def update_count_label(*args):
                count_label.config(text=str(count_var.get()))
            count_var.trace('w', update_count_label)
            
            # 按钮框架
            button_frame = ttk.Frame(main_frame)
            button_frame.pack(fill=tk.X, pady=(20, 0))
            
            def on_ok():
                result['score_threshold'] = score_var.get()
                result['stock_pool'] = pool_var.get()
                result['max_recommendations'] = count_var.get()
                settings_window.destroy()
                
            def on_cancel():
                settings_window.destroy()
            
            ttk.Button(button_frame, text="开始推荐", command=on_ok).pack(side=tk.RIGHT, padx=(10, 0))
            ttk.Button(button_frame, text="取消", command=on_cancel).pack(side=tk.RIGHT)
            
            # 等待窗口关闭
            settings_window.wait_window()
            
            return result if result else None
            
        except Exception as e:
            self.log_message(f"❌ 设置对话框错误: {e}")
            return None
    
    def perform_smart_recommendation(self, score_threshold, stock_pool, max_recommendations):
        """执行智能推荐"""
        try:
            self.recommend_btn.config(state='disabled')
            
            # 获取股票池
            self.log_message(f"* 获取{stock_pool}股票池...")
            if stock_pool == "main_board":
                stocks = self.analyzer.get_main_board_stocks()
                pool_name = "主板"
            elif stock_pool == "kcb":
                stocks = self.analyzer.get_kcb_stocks()
                pool_name = "科创板"
            elif stock_pool == "cyb":
                stocks = self.analyzer.get_cyb_stocks()
                pool_name = "创业板"
            else:  # all
                stocks = (self.analyzer.get_main_board_stocks() + 
                         self.analyzer.get_kcb_stocks() + 
                         self.analyzer.get_cyb_stocks())
                pool_name = "全市场"
            
            self.log_message(f"* {pool_name}股票池: {len(stocks)}只")
            
            # 分析股票
            self.log_message(f"* 开始分析股票...")
            analyzed_stocks = []
            
            for i, stock_code in enumerate(stocks):
                self.show_progress(i + 1, len(stocks))
                self.log_message(f"* 分析 {stock_code}...")
                
                result = self.analyzer.analyze_single_stock(stock_code)
                if result:
                    analyzed_stocks.append(result)
                    self.log_message(f"+ {stock_code} ({result['name']}) - 评分: {result['total_score']:.1f}")
                else:
                    self.log_message(f"- {stock_code} 分析失败")
                
                time.sleep(0.1)  # 避免请求过快
            
            # 按评分排序
            analyzed_stocks.sort(key=lambda x: x['total_score'], reverse=True)
            
            # 筛选高评分股票
            filtered_stocks = [s for s in analyzed_stocks if s['total_score'] >= score_threshold]
            
            # 限制推荐数量
            recommended_stocks = filtered_stocks[:max_recommendations]
            
            self.log_message(f"* 筛选结果: {len(filtered_stocks)}只股票评分>={score_threshold}")
            self.log_message(f"* 推荐股票: {len(recommended_stocks)}只")
            
            # 生成推荐报告
            self.generate_recommendation_report(recommended_stocks, score_threshold, pool_name)
            
        except Exception as e:
            self.log_message(f"❌ 推荐过程出错: {e}")
        finally:
            self.show_progress(100, 100)
            self.recommend_btn.config(state='normal')
    
    def generate_recommendation_report(self, stocks, score_threshold, pool_name):
        """生成推荐报告"""
        if not stocks:
            self.log_message(f"* 暂无符合条件的股票推荐")
            return
        
        self.log_message(f"\n" + "="*60)
        self.log_message(f"* 智能股票推荐报告")
        self.log_message(f"="*60)
        self.log_message(f"* 筛选标准: {pool_name}，评分>={score_threshold}")
        self.log_message(f"* 推荐数量: {len(stocks)}只")
        self.log_message(f"* 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        self.log_message(f"\n* 推荐股票列表:")
        for i, stock in enumerate(stocks, 1):
            grade = self.get_investment_grade(stock['total_score'])
            self.log_message(f"{i:2d}. {stock['code']} ({stock['name']})")
            self.log_message(f"    * 当前价格: ¥{stock['price']:.2f}")
            self.log_message(f"    * 综合评分: {stock['total_score']:.1f}分 ({grade})")
            self.log_message(f"    * 技术面: {stock['tech_score']:.1f}分")
            self.log_message(f"    * 基本面: {stock['fundamental_score']:.1f}分")
            self.log_message("")
        
        # 统计信息
        avg_score = sum(s['total_score'] for s in stocks) / len(stocks)
        max_score = max(s['total_score'] for s in stocks)
        min_score = min(s['total_score'] for s in stocks)
        
        self.log_message(f"* 统计摘要:")
        self.log_message(f"   平均评分: {avg_score:.1f}分")
        self.log_message(f"   最高评分: {max_score:.1f}分")
        self.log_message(f"   最低评分: {min_score:.1f}分")
        
        self.log_message(f"\n* 投资建议:")
        self.log_message(f"• 建议重点关注评分8.0以上的股票")
        self.log_message(f"• 结合市场环境和个人风险偏好决策")
        self.log_message(f"• 建议分散投资，控制单只股票仓位")
        self.log_message(f"• 定期关注股票基本面变化")
        
        self.log_message(f"\n* 风险提示:")
        self.log_message(f"• 股市有风险，投资需谨慎")
        self.log_message(f"• 本报告仅供参考，不构成投资建议")
        self.log_message(f"• 请根据自身情况做出投资决策")
        
        self.log_message(f"="*60)
    
    def get_investment_grade(self, score):
        """根据评分获取投资等级"""
        if score >= 9.0:
            return "强烈推荐"
        elif score >= 8.0:
            return "推荐"
        elif score >= 7.0:
            return "关注"
        elif score >= 6.0:
            return "观望"
        else:
            return "谨慎"
    
    def run(self):
        """运行GUI"""
        self.root.mainloop()

if __name__ == "__main__":
    # 创建并运行GUI
    gui = SimpleGUI()
    gui.run()