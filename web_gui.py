#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股智能分析系统 - Web GUI版本
基于Flask的网页界面，避免tkinter依赖问题
"""

try:
    from flask import Flask, render_template_string, request, jsonify
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

import sys
import os
import json
import threading
import webbrowser
from datetime import datetime
import subprocess

# 导入分析逻辑
from cli_launcher import AShareAnalyzerCLI

app = Flask(__name__)

# HTML模板
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>A股智能分析系统</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(45deg, #FF6B6B, #4ECDC4);
            color: white;
            padding: 30px;
            text-align: center;
        }
        
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        
        .header p {
            font-size: 1.2em;
            opacity: 0.9;
        }
        
        .nav-tabs {
            display: flex;
            background: #f8f9fa;
            border-bottom: 1px solid #dee2e6;
        }
        
        .tab-button {
            flex: 1;
            padding: 15px 20px;
            background: none;
            border: none;
            cursor: pointer;
            font-size: 16px;
            color: #666;
            transition: all 0.3s;
        }
        
        .tab-button.active {
            background: white;
            color: #FF6B6B;
            border-bottom: 3px solid #FF6B6B;
        }
        
        .tab-button:hover {
            background: #e9ecef;
        }
        
        .tab-content {
            padding: 30px;
        }
        
        .tab-pane {
            display: none;
        }
        
        .tab-pane.active {
            display: block;
        }
        
        .action-buttons {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .btn {
            padding: 15px 25px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
            font-weight: bold;
            transition: all 0.3s;
            text-decoration: none;
            display: inline-block;
            text-align: center;
        }
        
        .btn-primary {
            background: linear-gradient(45deg, #FF6B6B, #FF8E53);
            color: white;
        }
        
        .btn-secondary {
            background: linear-gradient(45deg, #4ECDC4, #44A08D);
            color: white;
        }
        
        .btn-success {
            background: linear-gradient(45deg, #56C596, #4CAF50);
            color: white;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.1);
        }
        
        .results-area {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            margin-top: 20px;
            min-height: 300px;
            font-family: monospace;
            white-space: pre-wrap;
            overflow-y: auto;
            max-height: 500px;
        }
        
        .loading {
            display: none;
            text-align: center;
            padding: 20px;
        }
        
        .spinner {
            width: 40px;
            height: 40px;
            border: 4px solid #f3f3f3;
            border-top: 4px solid #FF6B6B;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .stock-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        
        .stock-card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            border-left: 5px solid #FF6B6B;
        }
        
        .stock-name {
            font-size: 1.2em;
            font-weight: bold;
            color: #333;
            margin-bottom: 10px;
        }
        
        .stock-info {
            color: #666;
            margin-bottom: 5px;
        }
        
        .stock-score {
            background: linear-gradient(45deg, #FF6B6B, #FF8E53);
            color: white;
            padding: 5px 10px;
            border-radius: 20px;
            display: inline-block;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 A股智能分析系统</h1>
            <p>Web图形界面版本 - 专业的股票分析与推荐</p>
        </div>
        
        <div class="nav-tabs">
            <button class="tab-button active" onclick="showTab('analysis')">📊 股票分析</button>
            <button class="tab-button" onclick="showTab('recommendations')">📈 推荐股票</button>
            <button class="tab-button" onclick="showTab('single')">🔍 单股分析</button>
            <button class="tab-button" onclick="showTab('status')">⚙️ 系统状态</button>
        </div>
        
        <div class="tab-content">
            <!-- 股票分析标签页 -->
            <div id="analysis" class="tab-pane active">
                <h2>📊 批量股票分析</h2>
                <p>对所有股票进行技术面和基本面综合分析，生成三时期评分数据</p>
                
                <div class="action-buttons">
                    <button class="btn btn-primary" onclick="startBatchAnalysis()">
                        🔄 开始批量分析
                    </button>
                    <button class="btn btn-secondary" onclick="loadExistingData()">
                        📂 加载现有数据
                    </button>
                </div>
                
                <div id="analysis-loading" class="loading">
                    <div class="spinner"></div>
                    <p>正在分析股票数据，请稍候...</p>
                </div>
                
                <div id="analysis-results" class="results-area"></div>
            </div>
            
            <!-- 推荐股票标签页 -->
            <div id="recommendations" class="tab-pane">
                <h2>📈 智能股票推荐</h2>
                <p>基于多维度分析，为不同投资期限提供个性化推荐</p>
                
                <div class="action-buttons">
                    <button class="btn btn-primary" onclick="showRecommendations('short')">
                        ⚡ 短期推荐 (1-7天)
                    </button>
                    <button class="btn btn-secondary" onclick="showRecommendations('medium')">
                        📊 中期推荐 (7-30天)
                    </button>
                    <button class="btn btn-success" onclick="showRecommendations('long')">
                        🎯 长期推荐 (30-90天)
                    </button>
                    <button class="btn btn-primary" onclick="showAllRecommendations()">
                        📋 查看所有推荐
                    </button>
                </div>
                
                <div id="recommendations-loading" class="loading">
                    <div class="spinner"></div>
                    <p>正在生成推荐...</p>
                </div>
                
                <div id="recommendations-results" class="stock-grid"></div>
            </div>
            
            <!-- 单股分析标签页 -->
            <div id="single" class="tab-pane">
                <h2>🔍 单只股票分析</h2>
                <p>深度分析单只股票的各项指标和投资建议</p>
                
                <div style="margin-bottom: 20px;">
                    <label for="stock-code">股票代码：</label>
                    <input type="text" id="stock-code" placeholder="输入6位股票代码，如：000001" 
                           style="padding: 10px; border: 1px solid #ddd; border-radius: 5px; width: 200px;">
                    <button class="btn btn-primary" onclick="analyzeSingleStock()" style="margin-left: 10px;">
                        📊 开始分析
                    </button>
                </div>
                
                <div id="single-loading" class="loading">
                    <div class="spinner"></div>
                    <p>正在分析股票...</p>
                </div>
                
                <div id="single-results" class="results-area"></div>
            </div>
            
            <!-- 系统状态标签页 -->
            <div id="status" class="tab-pane">
                <h2>⚙️ 系统状态</h2>
                <p>查看系统运行状态和数据统计</p>
                
                <div class="action-buttons">
                    <button class="btn btn-secondary" onclick="checkSystemStatus()">
                        🔍 检查系统状态
                    </button>
                    <button class="btn btn-primary" onclick="clearCache()">
                        🗑️ 清理缓存
                    </button>
                </div>
                
                <div id="status-results" class="results-area"></div>
            </div>
        </div>
    </div>
    
    <script>
        // 标签页切换
        function showTab(tabName) {
            // 隐藏所有标签页
            document.querySelectorAll('.tab-pane').forEach(pane => {
                pane.classList.remove('active');
            });
            
            // 移除所有按钮的active类
            document.querySelectorAll('.tab-button').forEach(btn => {
                btn.classList.remove('active');
            });
            
            // 显示目标标签页
            document.getElementById(tabName).classList.add('active');
            
            // 激活对应按钮
            event.target.classList.add('active');
        }
        
        // API调用函数
        async function apiCall(endpoint, data = {}) {
            try {
                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(data)
                });
                return await response.json();
            } catch (error) {
                console.error('API调用失败:', error);
                return { error: '网络请求失败' };
            }
        }
        
        // 显示加载状态
        function showLoading(loadingId) {
            document.getElementById(loadingId).style.display = 'block';
        }
        
        // 隐藏加载状态
        function hideLoading(loadingId) {
            document.getElementById(loadingId).style.display = 'none';
        }
        
        // 开始批量分析
        async function startBatchAnalysis() {
            showLoading('analysis-loading');
            const results = await apiCall('/api/batch_analysis');
            hideLoading('analysis-loading');
            
            if (results.error) {
                document.getElementById('analysis-results').textContent = '错误: ' + results.error;
            } else {
                document.getElementById('analysis-results').textContent = results.message;
            }
        }
        
        // 加载现有数据
        async function loadExistingData() {
            const results = await apiCall('/api/load_data');
            document.getElementById('analysis-results').textContent = results.message;
        }
        
        // 显示推荐
        async function showRecommendations(period) {
            showLoading('recommendations-loading');
            const results = await apiCall('/api/recommendations', { period: period });
            hideLoading('recommendations-loading');
            
            const container = document.getElementById('recommendations-results');
            if (results.error) {
                container.innerHTML = '<p style="color: red;">错误: ' + results.error + '</p>';
                return;
            }
            
            container.innerHTML = '';
            results.stocks.forEach(stock => {
                const card = document.createElement('div');
                card.className = 'stock-card';
                card.innerHTML = `
                    <div class="stock-name">${stock.name} (${stock.code})</div>
                    <div class="stock-info">价格: ¥${stock.price} | 行业: ${stock.industry}</div>
                    <div class="stock-info">推荐: ${stock.recommendation}</div>
                    <div class="stock-info">理由: ${stock.factors.join(', ')}</div>
                    <div class="stock-score">评分: ${stock.score}</div>
                `;
                container.appendChild(card);
            });
        }
        
        // 显示所有推荐
        async function showAllRecommendations() {
            showLoading('recommendations-loading');
            
            const periods = ['short', 'medium', 'long'];
            const periodNames = ['短期', '中期', '长期'];
            const container = document.getElementById('recommendations-results');
            container.innerHTML = '';
            
            for (let i = 0; i < periods.length; i++) {
                const results = await apiCall('/api/recommendations', { period: periods[i] });
                
                if (!results.error && results.stocks.length > 0) {
                    const section = document.createElement('div');
                    section.innerHTML = `<h3>${periodNames[i]}推荐</h3>`;
                    container.appendChild(section);
                    
                    results.stocks.slice(0, 5).forEach(stock => {
                        const card = document.createElement('div');
                        card.className = 'stock-card';
                        card.innerHTML = `
                            <div class="stock-name">${stock.name} (${stock.code})</div>
                            <div class="stock-info">价格: ¥${stock.price} | 行业: ${stock.industry}</div>
                            <div class="stock-info">推荐: ${stock.recommendation}</div>
                            <div class="stock-score">评分: ${stock.score}</div>
                        `;
                        container.appendChild(card);
                    });
                }
            }
            
            hideLoading('recommendations-loading');
        }
        
        // 分析单只股票
        async function analyzeSingleStock() {
            const code = document.getElementById('stock-code').value.trim();
            if (!code) {
                alert('请输入股票代码');
                return;
            }
            
            showLoading('single-loading');
            const results = await apiCall('/api/single_analysis', { code: code });
            hideLoading('single-loading');
            
            document.getElementById('single-results').textContent = results.message || results.error;
        }
        
        // 检查系统状态
        async function checkSystemStatus() {
            const results = await apiCall('/api/status');
            document.getElementById('status-results').textContent = results.message;
        }
        
        // 清理缓存
        async function clearCache() {
            const results = await apiCall('/api/clear_cache');
            document.getElementById('status-results').textContent = results.message;
        }
        
        // 页面加载时自动加载数据
        window.onload = function() {
            loadExistingData();
        };
    </script>
</body>
</html>
"""

class WebGUI:
    def __init__(self):
        self.analyzer = AShareAnalyzerCLI()
        
    def start_server(self):
        """启动Web服务器"""
        @app.route('/')
        def index():
            return render_template_string(HTML_TEMPLATE)
        
        @app.route('/api/batch_analysis', methods=['POST'])
        def batch_analysis():
            try:
                self.analyzer.batch_analysis()
                return jsonify({'message': '批量分析完成！数据已保存。'})
            except Exception as e:
                return jsonify({'error': str(e)})
        
        @app.route('/api/load_data', methods=['POST'])
        def load_data():
            try:
                success = self.analyzer.load_comprehensive_data()
                if success:
                    return jsonify({'message': f'成功加载 {len(self.analyzer.comprehensive_data)} 只股票数据'})
                else:
                    return jsonify({'message': '未找到现有数据，请先进行批量分析'})
            except Exception as e:
                return jsonify({'error': str(e)})
        
        @app.route('/api/recommendations', methods=['POST'])
        def recommendations():
            try:
                data = request.get_json()
                period = data.get('period', 'short')
                stocks = self.analyzer.get_recommendations(period, 10)
                return jsonify({'stocks': stocks})
            except Exception as e:
                return jsonify({'error': str(e)})
        
        @app.route('/api/single_analysis', methods=['POST'])
        def single_analysis():
            try:
                data = request.get_json()
                code = data.get('code', '')
                
                if code not in self.analyzer.stock_info:
                    return jsonify({'error': '股票代码不存在'})
                
                # 生成分析报告
                stock_data = self.analyzer.generate_mock_data(code)
                
                report = f"""
股票分析报告 - {stock_data['name']} ({code})
========================================
当前价格: ¥{stock_data['current_price']}
涨跌幅: {stock_data['price_change']:+.2f}%
行业: {stock_data['industry']}
PE比率: {stock_data['pe_ratio']}
PB比率: {stock_data['pb_ratio']}
ROE: {stock_data['roe']}%
RSI: {stock_data['rsi']}
成交量比: {stock_data['volume_ratio']}

三时期评分:
"""
                periods = ['short', 'medium', 'long']
                period_names = ['短期(1-7天)', '中期(7-30天)', '长期(30-90天)']
                
                for period, name in zip(periods, period_names):
                    score, factors = self.analyzer.calculate_period_score(stock_data, period)
                    recommendation = self.analyzer._get_recommendation(score)
                    report += f"""
{name}:
  评分: {score:.1f}
  推荐: {recommendation}
  理由: {', '.join(factors[:3])}
"""
                
                return jsonify({'message': report})
            except Exception as e:
                return jsonify({'error': str(e)})
        
        @app.route('/api/status', methods=['POST'])
        def status():
            try:
                message = f"""
系统状态报告
====================
股票数据库: {len(self.analyzer.stock_info)} 只股票
分析数据: {len(self.analyzer.comprehensive_data)} 只股票
数据文件: {self.analyzer.comprehensive_data_file}
文件存在: {'是' if os.path.exists(self.analyzer.comprehensive_data_file) else '否'}
当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
                return jsonify({'message': message})
            except Exception as e:
                return jsonify({'error': str(e)})
        
        @app.route('/api/clear_cache', methods=['POST'])
        def clear_cache():
            try:
                # 清理缓存文件
                cache_files = ['stock_analysis_cache.json']
                cleared = 0
                for file in cache_files:
                    if os.path.exists(file):
                        os.remove(file)
                        cleared += 1
                
                return jsonify({'message': f'已清理 {cleared} 个缓存文件'})
            except Exception as e:
                return jsonify({'error': str(e)})
        
        # 启动服务器
        print("🚀 启动A股分析系统Web界面...")
        print("📱 正在打开浏览器...")
        
        # 在新线程中启动浏览器
        def open_browser():
            import time
            time.sleep(1.5)  # 等待服务器启动
            webbrowser.open('http://localhost:5000')
        
        threading.Thread(target=open_browser).start()
        
        try:
            app.run(host='localhost', port=5000, debug=False)
        except Exception as e:
            print(f"❌ Web服务器启动失败: {e}")

def main():
    """主函数"""
    if not FLASK_AVAILABLE:
        print("❌ Flask未安装，正在尝试安装...")
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'install', 'flask'], check=True)
            print("✅ Flask安装成功，请重新运行程序")
        except Exception as e:
            print(f"❌ Flask安装失败: {e}")
            print("💡 请手动运行: pip install flask")
        return
    
    try:
        web_gui = WebGUI()
        web_gui.start_server()
    except KeyboardInterrupt:
        print("\n👋 用户退出程序")
    except Exception as e:
        print(f"❌ 程序异常: {e}")

if __name__ == "__main__":
    main()