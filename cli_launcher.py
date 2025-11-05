#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股分析系统 - 增强命令行版本
解决GUI无法显示的问题，提供完整功能
"""

import os
import sys
import json
import random
from datetime import datetime

class AShareAnalyzerCLI:
    """A股分析系统增强命令行版本"""
    
    def __init__(self):
        self.clear_screen()
        self.print_banner()
        
        # 初始化数据
        self.stock_info = self._load_stock_database()
        self.comprehensive_data = {}
        self.comprehensive_data_file = "comprehensive_stock_data.json"
        
        # 尝试加载现有数据
        self.load_comprehensive_data()
        
    def clear_screen(self):
        """清屏"""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def print_banner(self):
        """打印标题横幅"""
        print("=" * 60)
        print("           A股智能分析系统 - 增强版")
        print("              解决GUI显示问题")
        print("=" * 60)
    
    def _load_stock_database(self):
        """加载股票数据库"""
        # 模拟股票数据库
        stock_db = {
            '000001': {'name': '平安银行', 'industry': '银行'},
            '000002': {'name': '万科A', 'industry': '房地产'},
            '000858': {'name': '五粮液', 'industry': '食品饮料'},
            '600036': {'name': '招商银行', 'industry': '银行'},
            '600519': {'name': '贵州茅台', 'industry': '食品饮料'},
            '000538': {'name': '云南白药', 'industry': '医药生物'},
            '600887': {'name': '伊利股份', 'industry': '食品饮料'},
            '002415': {'name': '海康威视', 'industry': '电子'},
            '300059': {'name': '东方财富', 'industry': '非银金融'},
            '600309': {'name': '万华化学', 'industry': '化工'},
            '002594': {'name': 'BYD', 'industry': '汽车'},
            '300750': {'name': '宁德时代', 'industry': '电池'},
            '600276': {'name': '恒瑞医药', 'industry': '医药'},
            '000069': {'name': '华侨城A', 'industry': '房地产'},
            '000725': {'name': '京东方A', 'industry': '电子'},
        }
        
        print(f"📊 股票数据库: {len(stock_db)}只股票")
        return stock_db
    
    def generate_mock_data(self, code):
        """生成模拟股票数据"""
        random.seed(hash(code) % 1000)
        
        return {
            'code': code,
            'name': self.stock_info.get(code, {}).get('name', f'股票{code}'),
            'current_price': round(random.uniform(8, 50), 2),
            'pe_ratio': round(random.uniform(5, 25), 1),
            'pb_ratio': round(random.uniform(0.5, 3.0), 2),
            'roe': round(random.uniform(5, 20), 1),
            'rsi': round(random.uniform(20, 80), 1),
            'volume_ratio': round(random.uniform(0.8, 2.5), 2),
            'price_change': round(random.uniform(-5, 8), 2),
            'industry': self.stock_info.get(code, {}).get('industry', '未知')
        }
    
    def calculate_period_score(self, data, period):
        """计算不同时期的评分"""
        score = 50  # 基础分
        factors = []
        
        if period == 'short':
            # 短期评分：技术指标为主
            if data['price_change'] > 5:
                score += 15
                factors.append("价格大幅上涨")
            elif data['price_change'] > 2:
                score += 10
                factors.append("价格稳步上涨")
            
            if 30 <= data['rsi'] <= 50:
                score += 12
                factors.append("RSI处于健康区间")
            elif data['rsi'] < 30:
                score += 8
                factors.append("RSI超卖，反弹机会")
            
            if data['volume_ratio'] > 1.5:
                score += 10
                factors.append("成交量放大")
                
        elif period == 'medium':
            # 中期评分：技术+基本面
            tech_score = min(30, score * 0.6)
            
            if data['roe'] > 15:
                score += 15
                factors.append("ROE优秀")
            elif data['roe'] > 10:
                score += 10
                factors.append("ROE良好")
            
            if data['pe_ratio'] < 15:
                score += 10
                factors.append("估值合理")
                
        else:  # long
            # 长期评分：基本面为主
            if data['roe'] > 20:
                score += 25
                factors.append("ROE卓越")
            elif data['roe'] > 15:
                score += 20
                factors.append("ROE优秀")
            
            if data['pe_ratio'] < 10 and data['pb_ratio'] < 1:
                score += 20
                factors.append("深度价值股")
            elif data['pe_ratio'] < 15:
                score += 10
                factors.append("估值偏低")
        
        # 行业加分
        if data['industry'] in ['医药生物', '食品饮料', '电子']:
            score += 5
            factors.append("优质行业")
        
        return min(100, max(0, score)), factors
    
    def batch_analysis(self):
        """批量分析所有股票"""
        print("\n🔄 开始批量分析股票...")
        
        total_stocks = len(self.stock_info)
        processed = 0
        
        for code in self.stock_info.keys():
            try:
                # 生成模拟数据
                data = self.generate_mock_data(code)
                
                # 计算三个时期评分
                short_score, short_factors = self.calculate_period_score(data, 'short')
                medium_score, medium_factors = self.calculate_period_score(data, 'medium')
                long_score, long_factors = self.calculate_period_score(data, 'long')
                
                # 保存完整数据
                self.comprehensive_data[code] = {
                    'code': code,
                    'name': data['name'],
                    'current_price': data['current_price'],
                    'industry': data['industry'],
                    'short_term': {
                        'score': short_score,
                        'factors': short_factors,
                        'recommendation': self._get_recommendation(short_score)
                    },
                    'medium_term': {
                        'score': medium_score,
                        'factors': medium_factors,
                        'recommendation': self._get_recommendation(medium_score)
                    },
                    'long_term': {
                        'score': long_score,
                        'factors': long_factors,
                        'recommendation': self._get_recommendation(long_score)
                    },
                    'timestamp': datetime.now().isoformat()
                }
                
                processed += 1
                if processed % 3 == 0:
                    print(f"   进度: {processed}/{total_stocks}")
                    
            except Exception as e:
                print(f"   ❌ 分析{code}失败: {e}")
        
        # 保存数据
        self.save_comprehensive_data()
        print(f"✅ 批量分析完成！共分析{processed}只股票")
    
    def _get_recommendation(self, score):
        """根据评分获取推荐"""
        if score >= 80:
            return "强烈推荐"
        elif score >= 70:
            return "推荐"
        elif score >= 60:
            return "谨慎推荐"
        elif score >= 50:
            return "观望"
        else:
            return "不推荐"
    
    def get_recommendations(self, period='short', top_n=10):
        """获取推荐股票"""
        if not self.comprehensive_data:
            print("❌ 没有分析数据，请先运行批量分析")
            return []
        
        period_key = f"{period}_term"
        recommendations = []
        
        for code, data in self.comprehensive_data.items():
            if period_key in data:
                recommendations.append({
                    'code': code,
                    'name': data['name'],
                    'score': data[period_key]['score'],
                    'recommendation': data[period_key]['recommendation'],
                    'factors': data[period_key]['factors'],
                    'price': data['current_price'],
                    'industry': data['industry']
                })
        
        # 按评分排序
        recommendations.sort(key=lambda x: x['score'], reverse=True)
        return recommendations[:top_n]
    
    def display_recommendations(self, period='short'):
        """显示推荐结果"""
        print(f"\n📊 {period.upper()}期推荐股票 (Top 10)")
        print("=" * 80)
        
        recommendations = self.get_recommendations(period, 10)
        
        if not recommendations:
            print("❌ 暂无推荐数据，请先运行'批量分析股票'")
            return
        
        for i, stock in enumerate(recommendations, 1):
            print(f"\n{i:2d}. {stock['name']} ({stock['code']})")
            print(f"    评分: {stock['score']:.1f} | 推荐: {stock['recommendation']}")
            print(f"    价格: ¥{stock['price']} | 行业: {stock['industry']}")
            print(f"    理由: {', '.join(stock['factors'][:3])}")
    
    def save_comprehensive_data(self):
        """保存数据"""
        try:
            data = {
                'timestamp': datetime.now().isoformat(),
                'count': len(self.comprehensive_data),
                'data': self.comprehensive_data
            }
            
            with open(self.comprehensive_data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            print(f"💾 数据已保存到 {self.comprehensive_data_file}")
            
        except Exception as e:
            print(f"❌ 保存数据失败: {e}")
    
    def load_comprehensive_data(self):
        """加载数据"""
        try:
            if os.path.exists(self.comprehensive_data_file):
                with open(self.comprehensive_data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if 'data' in data:
                    self.comprehensive_data = data['data']
                    print(f"✅ 加载现有数据: {len(self.comprehensive_data)}只股票")
                    return True
            
            print("📄 未找到现有数据文件")
            return False
            
        except Exception as e:
            print(f"❌ 加载数据失败: {e}")
            return False
    
    def run(self):
        """主运行函数"""
        while True:
            print("\n" + "=" * 50)
            print("📋 A股分析系统 - 增强命令行版本")
            print("=" * 50)
            print("1. 批量分析股票 (相当于'开始获取评分')")
            print("2. 短期推荐 (1-7天)")
            print("3. 中期推荐 (7-30天)")
            print("4. 长期推荐 (30-90天)")
            print("5. 查看所有时期推荐")
            print("6. 单股票分析")
            print("7. 系统状态")
            print("8. 退出")
            print("=" * 50)
            
            try:
                choice = input("请选择功能 (1-8): ").strip()
                
                if choice == '1':
                    self.batch_analysis()
                elif choice == '2':
                    self.display_recommendations('short')
                elif choice == '3':
                    self.display_recommendations('medium')
                elif choice == '4':
                    self.display_recommendations('long')
                elif choice == '5':
                    for period in ['short', 'medium', 'long']:
                        self.display_recommendations(period)
                elif choice == '6':
                    self.single_stock_analysis()
                elif choice == '7':
                    self.show_system_status()
                elif choice == '8':
                    print("👋 感谢使用A股分析系统！")
                    break
                else:
                    print("❌ 无效选择，请重新输入")
                    
            except KeyboardInterrupt:
                print("\n👋 用户退出程序")
                break
            except Exception as e:
                print(f"❌ 操作失败: {e}")
    
    def single_stock_analysis(self):
        """单股票分析"""
        print("\n📈 单股票分析")
        print("=" * 40)
        
        # 显示可用股票
        print("可用股票代码:")
        for i, (code, info) in enumerate(self.stock_info.items()):
            if i % 3 == 0:
                print()
            print(f"{code}({info['name']})".ljust(20), end="")
        print("\n")
        
        stock_code = input("请输入股票代码: ").strip()
        
        if stock_code not in self.stock_info:
            print("❌ 股票代码不存在")
            return
        
        # 生成分析数据
        data = self.generate_mock_data(stock_code)
        
        print(f"\n📊 {data['name']} ({data['code']}) 分析报告")
        print("=" * 50)
        print(f"当前价格: ¥{data['current_price']}")
        print(f"涨跌幅: {data['price_change']:+.2f}%")
        print(f"行业: {data['industry']}")
        print(f"PE比率: {data['pe_ratio']}")
        print(f"PB比率: {data['pb_ratio']}")
        print(f"ROE: {data['roe']}%")
        print(f"RSI: {data['rsi']}")
        print(f"成交量比: {data['volume_ratio']}")
        
        # 三时期评分
        periods = ['short', 'medium', 'long']
        period_names = ['短期(1-7天)', '中期(7-30天)', '长期(30-90天)']
        
        print("\n三时期评分:")
        for period, name in zip(periods, period_names):
            score, factors = self.calculate_period_score(data, period)
            recommendation = self._get_recommendation(score)
            print(f"\n{name}:")
            print(f"  评分: {score:.1f}")
            print(f"  推荐: {recommendation}")
            print(f"  理由: {', '.join(factors[:3])}")
    
    def show_system_status(self):
        """显示系统状态"""
        print("\n🔧 系统状态")
        print("=" * 40)
        print(f"股票数据库: {len(self.stock_info)}只股票")
        print(f"分析数据: {len(self.comprehensive_data)}只股票")
        
        if self.comprehensive_data:
            # 统计推荐分布
            periods = ['short_term', 'medium_term', 'long_term']
            for period in periods:
                scores = [data[period]['score'] for data in self.comprehensive_data.values() if period in data]
                if scores:
                    avg_score = sum(scores) / len(scores)
                    print(f"{period.replace('_', ' ').title()}: 平均评分 {avg_score:.1f}")
        
        print(f"数据文件: {self.comprehensive_data_file}")
        print(f"文件存在: {'是' if os.path.exists(self.comprehensive_data_file) else '否'}")

def main():
    """主函数"""
    try:
        print("🔍 检查GUI环境...")
        try:
            import tkinter
            print("✅ tkinter可用，但使用命令行版本避免显示问题")
        except ImportError:
            print("❌ tkinter不可用，使用命令行版本")
        
        print("\n🚀 启动命令行版本...")
        cli = AShareAnalyzerCLI()
        cli.run()
    except Exception as e:
        print(f"❌ 程序启动失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()