#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试股票类型过滤功能 - 模拟GUI环境
"""

import json
from datetime import datetime

# 模拟AShareAnalyzerGUI类的核心过滤功能
class MockStockAnalyzer:
    def __init__(self):
        # 模拟股票信息
        self.stock_info = {
            # 60/00开头的股票
            "600519": {"name": "贵州茅台", "industry": "食品饮料"},
            "000858": {"name": "五粮液", "industry": "食品饮料"},
            "002415": {"name": "海康威视", "industry": "电子"},
            
            # 创业板股票
            "300750": {"name": "宁德时代", "industry": "电池"},
            "300059": {"name": "东方财富", "industry": "互联网金融"},
            
            # 科创板股票
            "688981": {"name": "中芯国际", "industry": "半导体制造"},
            "688036": {"name": "传音控股", "industry": "消费电子"},
            
            # ETF基金
            "510300": {"name": "沪深300ETF", "industry": "基金"},
            "159915": {"name": "创业板ETF", "industry": "基金"},
            "512100": {"name": "中证1000ETF", "industry": "基金"},
        }
        
        # 模拟批量评分数据
        self.batch_scores = {}
        for code, info in self.stock_info.items():
            self.batch_scores[code] = {
                'name': info['name'],
                'score': 7.5 + (hash(code) % 20) / 10,  # 随机评分 7.5-9.5
                'industry': info['industry'],
                'timestamp': datetime.now().strftime('%H:%M:%S')
            }
    
    def is_stock_type_match(self, code, stock_type):
        """判断股票代码是否符合指定类型"""
        if stock_type == "全部":
            return code.startswith(('600', '000', '002', '300', '688', '51', '15'))
        elif stock_type == "60/00":
            return code.startswith(('600', '000', '002'))
        elif stock_type == "68科创板":
            return code.startswith('688')
        elif stock_type == "30创业板":
            return code.startswith('300')
        elif stock_type == "ETF":
            return code.startswith(('510', '511', '512', '513', '515', '516', '518', '159', '560', '561', '562', '563'))
        return False
    
    def get_all_stock_codes(self, stock_type="全部"):
        """获取A股股票代码，根据股票类型过滤"""
        all_stocks = []
        
        # 从已知股票信息中获取
        for code in self.stock_info.keys():
            if self.is_stock_type_match(code, stock_type):
                all_stocks.append(code)
        
        return sorted(all_stocks)
    
    def simulate_batch_scoring(self, stock_type="全部"):
        """模拟批量获取评分功能"""
        print(f"🚀 开始获取{stock_type}股票评分...")
        
        # 获取符合类型要求的股票代码
        all_codes = self.get_all_stock_codes(stock_type)
        total_stocks = len(all_codes)
        
        if total_stocks == 0:
            print(f"❌ 未找到{stock_type}类型的股票代码")
            return
        
        print(f"📊 准备分析 {total_stocks} 只{stock_type}股票...")
        
        # 显示将要分析的股票
        print(f"📝 股票列表: {', '.join(all_codes)}")
        
        # 模拟评分过程
        success_count = 0
        for i, code in enumerate(all_codes):
            name = self.stock_info[code]['name']
            score = self.batch_scores[code]['score']
            print(f"  {i+1:2d}. {code} - {name:<10} 评分: {score:.1f}")
            success_count += 1
        
        print(f"✅ 批量评分完成！成功: {success_count}, 失败: 0")
    
    def generate_ranking_report(self, stock_type, count=10):
        """生成评分排行报告"""
        # 过滤符合类型要求的股票
        filtered_stocks = []
        
        for code, data in self.batch_scores.items():
            if not self.is_stock_type_match(code, stock_type):
                continue
            
            filtered_stocks.append({
                'code': code,
                'name': data.get('name', f'股票{code}'),
                'score': data.get('score', 0),
                'industry': data.get('industry', '未知'),
            })
        
        # 按评分排序
        filtered_stocks.sort(key=lambda x: x['score'], reverse=True)
        
        # 取前N个
        top_stocks = filtered_stocks[:count]
        
        print(f"\n📊 {stock_type} 评分排行榜 Top {count}")
        print("=" * 50)
        
        if not top_stocks:
            print(f"❌ 暂无符合条件的{stock_type}股票数据")
        else:
            for i, stock in enumerate(top_stocks, 1):
                score_color = "🟢" if stock['score'] >= 8 else "🟡" if stock['score'] >= 7 else "🔴"
                print(f"【{i:02d}】{stock['code']} - {stock['name']:<12} {score_color} {stock['score']:.1f}分 | {stock['industry']}")

def test_stock_type_filtering():
    """测试股票类型过滤功能"""
    print("🧪 测试股票类型过滤功能")
    print("=" * 60)
    
    analyzer = MockStockAnalyzer()
    
    # 测试各种股票类型
    stock_types = ["全部", "60/00", "68科创板", "30创业板", "ETF"]
    
    for stock_type in stock_types:
        print(f"\n🔍 测试类型: {stock_type}")
        print("-" * 40)
        
        # 测试获取股票代码
        codes = analyzer.get_all_stock_codes(stock_type)
        print(f"📈 找到 {len(codes)} 只{stock_type}股票: {codes}")
        
        # 模拟批量评分
        analyzer.simulate_batch_scoring(stock_type)
        
        # 生成排行榜
        analyzer.generate_ranking_report(stock_type, 5)
        
        print()

if __name__ == "__main__":
    test_stock_type_filtering()