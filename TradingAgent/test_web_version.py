"""
A股智能分析系统 - Web版测试脚本
测试所有API端点和功能
"""

import json
import time
from datetime import datetime

import requests

BASE_URL = "http://localhost:5000/api"

def print_section(title):
    """打印标题"""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")

def print_success(msg):
    """打印成功信息"""
    print(f"✅ {msg}")

def print_error(msg):
    """打印错误信息"""
    print(f"❌ {msg}")

def print_info(msg):
    """打印信息"""
    print(f"ℹ️  {msg}")

def test_health():
    """测试健康检查"""
    print_section("测试1: 健康检查 (GET /api/health)")
    
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        data = response.json()
        
        print_success(f"后端服务状态: {data['status']}")
        print_info(f"GUI就绪: {data['gui_ready']}")
        print_info(f"时间戳: {data['timestamp']}")
        
        return data['gui_ready']
    except Exception as e:
        print_error(f"连接失败: {e}")
        print_info("确保Flask后端运行: python flask_backend.py")
        return False

def test_single_stock_analysis():
    """测试单只股票分析"""
    print_section("测试2: 单只股票分析 (GET /api/analyze/<ticker>)")
    
    test_stocks = ["600519", "600036", "000002"]
    
    for ticker in test_stocks:
        try:
            print_info(f"正在分析: {ticker}")
            response = requests.get(f"{BASE_URL}/analyze/{ticker}", timeout=30)
            data = response.json()
            
            if 'error' in data:
                print_error(f"{ticker}: {data['error']}")
            else:
                scores = data['data']['scores']
                print_success(f"{ticker} ({data['name']})")
                print(f"  技术评分: {scores['technical']:.1f}")
                print(f"  基本面评分: {scores['fundamental']:.1f}")
                print(f"  综合评分: {scores['comprehensive']:.1f}")
                print(f"  价格: ¥{data['data']['price']:.2f}")
        except Exception as e:
            print_error(f"{ticker} 分析失败: {e}")
        
        time.sleep(1)  # 避免请求过快

def test_batch_score():
    """测试批量评分"""
    print_section("测试3: 批量股票评分 (POST /api/batch-score)")
    
    stocks = ["600519", "600036", "000002", "300750", "600887"]
    
    try:
        print_info(f"正在评分 {len(stocks)} 只股票...")
        response = requests.post(
            f"{BASE_URL}/batch-score",
            json={"stocks": stocks, "use_llm": False},
            timeout=60
        )
        data = response.json()
        
        if 'error' in data:
            print_error(f"批量评分失败: {data['error']}")
        else:
            print_success(f"已评分 {data['scored']}/{data['total']} 只股票")
            
            # 显示排名前3
            results = [(k, v) for k, v in data['results'].items()]
            results.sort(key=lambda x: x[1].get('comprehensive_score', 0), reverse=True)
            
            print("\n📊 评分排名 (前3):")
            for i, (code, info) in enumerate(results[:3], 1):
                print(f"  {i}. {code}: {info['comprehensive_score']:.1f} ⭐")
    
    except Exception as e:
        print_error(f"批量评分失败: {e}")

def test_recommendations():
    """测试推荐系统"""
    print_section("测试4: 投资推荐 (GET /api/recommendations)")
    
    try:
        print_info("正在生成投资推荐...")
        response = requests.get(
            f"{BASE_URL}/recommendations?min_score=6.0&type=all",
            timeout=30
        )
        data = response.json()
        
        if 'error' in data:
            print_error(f"推荐生成失败: {data['error']}")
        else:
            print_success(f"已生成推荐")
            print_info(f"最低评分: {data['min_score']}")
            print_info(f"股票类型: {data['stock_type']}")
    
    except Exception as e:
        print_error(f"推荐系统测试失败: {e}")

def test_status():
    """测试系统状态"""
    print_section("测试5: 系统状态 (GET /api/status)")
    
    try:
        response = requests.get(f"{BASE_URL}/status", timeout=5)
        data = response.json()
        
        print_success(f"系统状态: {data['status']}")
        print_info(f"GUI就绪: {data['gui_ready']}")
        print_info(f"时间戳: {data['timestamp']}")
    
    except Exception as e:
        print_error(f"状态查询失败: {e}")

def main():
    """主测试函数"""
    print("""
    ╔══════════════════════════════════════════════════════════════════════════════╗
    ║                  A股智能分析系统 - Web版测试脚本                            ║
    ║                                                                              ║
    ║  这个脚本将测试所有API端点的功能                                             ║
    ║  确保Flask后端正在运行: python flask_backend.py                             ║
    ║                                                                              ║
    ╚══════════════════════════════════════════════════════════════════════════════╝
    """)
    
    time.sleep(1)
    
    # 测试健康检查
    if not test_health():
        print("\n⚠️  后端服务未就绪，请先启动Flask后端")
        print("   python flask_backend.py")
        return
    
    # 运行所有测试
    try:
        test_single_stock_analysis()
        test_batch_score()
        test_recommendations()
        test_status()
        
        print_section("✅ 所有测试完成")
        print("✨ Web版本已准备好！")
        print("\n📱 在浏览器中打开: web_interface.html")
        print("🌐 或访问: http://localhost:5000 (如果配置了静态文件服务)")
        
    except Exception as e:
        print_error(f"测试过程中出错: {e}")

if __name__ == "__main__":
    main()
