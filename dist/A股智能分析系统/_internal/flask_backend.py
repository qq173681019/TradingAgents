"""
A股交易系统 - Flask Web后端
将a_share_gui_compatible.py的所有分析功能暴露为REST API
"""

import json
import os
import sys
import threading
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List

from flask import Flask, jsonify, request
from flask_cors import CORS

# 导入原有的GUI应用（不显示GUI，仅使用分析逻辑）
sys.path.insert(0, os.path.dirname(__file__))

app = Flask(__name__)
CORS(app)  # 启用跨域请求

# 全局状态
analysis_status = {
    'current_batch': None,
    'progress': 0,
    'total': 0,
    'status': 'idle'
}

def get_gui_instance():
    """获取或创建GUI实例（仅用于分析逻辑，不显示UI）"""
    try:
        import tkinter as tk

        from a_share_gui_compatible import AShareAnalyzerGUI

        # 创建隐藏的Tk根窗口
        root = tk.Tk()
        root.withdraw()  # 隐藏窗口
        
        # 创建GUI实例（仅用于访问分析方法）
        gui = AShareAnalyzerGUI(root)
        return gui
    except Exception as e:
        print(f"❌ 无法创建GUI实例: {e}")
        return None


class AnalysisService:
    """分析服务类 - 提供所有分析功能"""
    
    def __init__(self):
        self.gui = get_gui_instance()
        if not self.gui:
            print("⚠️  警告: GUI实例创建失败，部分功能可能不可用")
    
    def analyze_single_stock(self, ticker: str) -> Dict[str, Any]:
        """
        分析单只股票
        返回完整的分析结果
        """
        if not self.gui:
            return {'error': 'GUI实例不可用'}
        
        try:
            print(f"\n{'='*80}")
            print(f"[API] 开始分析股票: {ticker}")
            print(f"{'='*80}\n")
            
            # 调用原有的perform_detailed_analysis方法（不显示UI）
            # 首先获取基本信息
            stock_info = self.gui.stock_info.get(ticker, {
                "name": f"股票{ticker}",
                "industry": "未知",
                "concept": "A股"
            })
            
            # 获取技术数据
            tech_data = self.gui._try_get_real_technical_data(ticker)
            if not tech_data:
                return {
                    'error': f'无法获取{ticker}的技术数据',
                    'code': ticker
                }
            
            # 获取基本面数据
            fund_data = self.gui._try_get_real_fundamental_data(ticker)
            if not fund_data:
                fund_data = {
                    'pe_ratio': 15.0,
                    'pb_ratio': 2.0,
                    'roe': 10.0,
                    'revenue_growth': 5.0,
                    'profit_growth': 5.0
                }
            
            # 计算分数
            tech_score = self.gui.calculate_technical_score(ticker, tech_data)
            fund_score = self.gui.calculate_fundamental_score(ticker, fund_data)
            comprehensive_score = self.gui.calculate_comprehensive_score(ticker, tech_score, fund_score)
            
            # 获取技术分析
            tech_analysis = self.gui.technical_analysis(ticker, tech_data)
            
            # 获取基本面分析
            fund_analysis = self.gui.fundamental_analysis(ticker, fund_data)
            
            # 获取投资建议（支持LLM）
            llm_model = self.gui.llm_var.get() if hasattr(self.gui, 'llm_var') else 'none'
            if llm_model != 'none':
                advice = self.gui.generate_investment_advice(ticker, comprehensive_score, tech_score, fund_score, llm_model)
            else:
                advice = self.gui.generate_investment_advice(ticker, comprehensive_score, tech_score, fund_score)
            
            # 获取筹码分析（如果可用）
            chip_analysis = None
            try:
                chip_analysis = self.gui._generate_chip_analysis_report(ticker)
            except:
                pass
            
            return {
                'success': True,
                'code': ticker,
                'name': stock_info.get('name', '未知'),
                'industry': stock_info.get('industry', '未知'),
                'data': {
                    'stock_info': stock_info,
                    'price': tech_data.get('current_price', 0),
                    'scores': {
                        'technical': tech_score,
                        'fundamental': fund_score,
                        'comprehensive': comprehensive_score
                    },
                    'tech_data': tech_data,
                    'fund_data': fund_data,
                    'tech_analysis': tech_analysis,
                    'fund_analysis': fund_analysis,
                    'advice': advice,
                    'chip_analysis': chip_analysis,
                    'timestamp': datetime.now().isoformat()
                }
            }
        
        except Exception as e:
            print(f"❌ 分析失败: {e}")
            traceback.print_exc()
            return {
                'error': str(e),
                'code': ticker
            }
    
    def batch_score_stocks(self, stock_codes: List[str], use_llm: bool = False) -> Dict[str, Any]:
        """
        批量评分股票
        """
        if not self.gui:
            return {'error': 'GUI实例不可用', 'results': {}}
        
        try:
            print(f"\n{'='*80}")
            print(f"[API] 开始批量评分: {len(stock_codes)} 只股票")
            print(f"{'='*80}\n")
            
            results = {}
            
            for idx, ticker in enumerate(stock_codes, 1):
                # 更新进度
                analysis_status['current_batch'] = idx
                analysis_status['total'] = len(stock_codes)
                analysis_status['progress'] = int((idx / len(stock_codes)) * 100)
                
                print(f"\r[进度] {idx}/{len(stock_codes)} ({analysis_status['progress']}%) - 分析 {ticker}", end='', flush=True)
                
                try:
                    # 快速评分（不调用LLM）
                    tech_data = self.gui._try_get_real_technical_data(ticker)
                    fund_data = self.gui._try_get_real_fundamental_data(ticker)
                    
                    if tech_data and fund_data:
                        tech_score = self.gui.calculate_technical_score(ticker, tech_data)
                        fund_score = self.gui.calculate_fundamental_score(ticker, fund_data)
                        comp_score = self.gui.calculate_comprehensive_score(ticker, tech_score, fund_score)
                        
                        results[ticker] = {
                            'technical_score': tech_score,
                            'fundamental_score': fund_score,
                            'comprehensive_score': comp_score,
                            'price': tech_data.get('current_price', 0)
                        }
                except Exception as e:
                    print(f"\n⚠️  {ticker} 评分失败: {e}")
                    continue
            
            print("\n")
            
            # 排序结果（按综合评分降序）
            sorted_results = sorted(
                results.items(),
                key=lambda x: x[1].get('comprehensive_score', 0),
                reverse=True
            )
            
            return {
                'success': True,
                'total': len(stock_codes),
                'scored': len(results),
                'results': dict(sorted_results),
                'timestamp': datetime.now().isoformat()
            }
        
        except Exception as e:
            print(f"❌ 批量评分失败: {e}")
            traceback.print_exc()
            return {
                'error': str(e),
                'results': {}
            }
    
    def get_recommendations(self, min_score: float = 6.0, stock_type: str = 'all') -> Dict[str, Any]:
        """
        获取投资推荐
        """
        if not self.gui:
            return {'error': 'GUI实例不可用', 'recommendations': []}
        
        try:
            print(f"\n{'='*80}")
            print(f"[API] 生成投资推荐 (最低评分: {min_score}, 类型: {stock_type})")
            print(f"{'='*80}\n")
            
            # 调用原有的generate_stock_recommendations_by_type
            recommendations = self.gui.generate_stock_recommendations_by_type(stock_type)
            
            return {
                'success': True,
                'min_score': min_score,
                'stock_type': stock_type,
                'recommendations': recommendations,
                'timestamp': datetime.now().isoformat()
            }
        
        except Exception as e:
            print(f"❌ 推荐生成失败: {e}")
            traceback.print_exc()
            return {
                'error': str(e),
                'recommendations': []
            }


# ==================== API 端点 ====================

service = AnalysisService()


@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        'status': 'online',
        'timestamp': datetime.now().isoformat(),
        'gui_ready': service.gui is not None
    })


@app.route('/api/analyze/<ticker>', methods=['GET'])
def analyze_stock(ticker):
    """
    分析单只股票
    GET /api/analyze/600519
    """
    result = service.analyze_single_stock(ticker)
    return jsonify(result)


@app.route('/api/batch-score', methods=['POST'])
def batch_score():
    """
    批量评分
    POST /api/batch-score
    {
        "stocks": ["600519", "600036", ...],
        "use_llm": false
    }
    """
    data = request.json or {}
    stocks = data.get('stocks', [])
    use_llm = data.get('use_llm', False)
    
    if not stocks:
        return jsonify({'error': '未提供股票代码列表'}), 400
    
    result = service.batch_score_stocks(stocks, use_llm)
    return jsonify(result)


@app.route('/api/recommendations', methods=['GET'])
def get_recommendations():
    """
    获取投资推荐
    GET /api/recommendations?min_score=6.0&type=mainboard
    """
    min_score = float(request.args.get('min_score', 6.0))
    stock_type = request.args.get('type', 'all')
    
    result = service.get_recommendations(min_score, stock_type)
    return jsonify(result)


@app.route('/api/batch-status', methods=['GET'])
def get_batch_status():
    """获取批量分析进度"""
    return jsonify(analysis_status)


@app.route('/api/status', methods=['GET'])
def get_system_status():
    """获取系统状态"""
    return jsonify({
        'status': 'running',
        'gui_ready': service.gui is not None,
        'timestamp': datetime.now().isoformat()
    })


# ==================== 错误处理 ====================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': '端点不存在'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': '服务器内部错误'}), 500


# ==================== 启动脚本 ====================

if __name__ == '__main__':
    print("""
    ╔══════════════════════════════════════════════════════════════════════════════╗
    ║                     A股智能分析系统 - Flask Web后端                          ║
    ║                                                                              ║
    ║  核心功能:                                                                   ║
    ║  ✅ 单只股票深度分析 (GET /api/analyze/<ticker>)                            ║
    ║  ✅ 批量股票评分    (POST /api/batch-score)                                 ║
    ║  ✅ 投资推荐系统    (GET /api/recommendations)                              ║
    ║  ✅ 技术面分析      (集成到单只分析)                                          ║
    ║  ✅ 基本面分析      (集成到单只分析)                                          ║
    ║  ✅ LLM投资建议    (可选，见配置)                                           ║
    ║  ✅ 筹码分析        (可选，见配置)                                           ║
    ║                                                                              ║
    ║  启动地址: http://localhost:5000                                             ║
    ║                                                                              ║
    ╚══════════════════════════════════════════════════════════════════════════════╝
    """)
    
    app.run(
        host='127.0.0.1',
        port=5000,
        debug=True,
        use_reloader=False,
        threaded=True
    )
