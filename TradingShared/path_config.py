"""
TradingShared 路径配置
用于统一管理共享资源的路径
"""
import os
import sys

# 获取TradingShared的绝对路径
SHARED_ROOT = os.path.dirname(os.path.abspath(__file__))

# API文件夹路径
API_DIR = os.path.join(SHARED_ROOT, 'api')

# 数据文件夹路径
DATA_DIR = os.path.join(SHARED_ROOT, 'data')

# 将路径添加到系统路径
if SHARED_ROOT not in sys.path:
    sys.path.insert(0, SHARED_ROOT)

if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)

# 数据文件路径
STOCK_ANALYSIS_CACHE = os.path.join(DATA_DIR, 'stock_analysis_cache.json')
STOCK_INFO_FALLBACK = os.path.join(DATA_DIR, 'stock_info_fallback.json')
COMPREHENSIVE_STOCK_DATA = os.path.join(DATA_DIR, 'comprehensive_stock_data.json')
CHOICE_ACTIVATION_CONFIG = os.path.join(DATA_DIR, 'choice_activation_config.json')
CHOICE_DEVICE_INFO = os.path.join(DATA_DIR, 'choice_device_info.json')
KLINE_UPDATE_STATUS = os.path.join(DATA_DIR, 'kline_update_status.json')

def get_batch_scores_file(market='主板', timestamp=None):
    """获取批量评分文件路径"""
    if timestamp:
        filename = f'batch_stock_scores_optimized_{market}_{timestamp}.json'
    else:
        filename = f'batch_stock_scores_optimized_{market}_latest.json'
    return os.path.join(DATA_DIR, filename)

def setup_paths():
    """设置Python导入路径"""
    if SHARED_ROOT not in sys.path:
        sys.path.insert(0, SHARED_ROOT)
    if API_DIR not in sys.path:
        sys.path.insert(0, API_DIR)
    
    print(f"[PATH] TradingShared根目录: {SHARED_ROOT}")
    print(f"[PATH] API目录: {API_DIR}")
    print(f"[PATH] 数据目录: {DATA_DIR}")

if __name__ == "__main__":
    setup_paths()
    print("\n可用的API模块:")
    for file in os.listdir(API_DIR):
        if file.endswith('.py') and not file.startswith('__'):
            print(f"  - {file}")
    
    print("\n可用的数据文件:")
    for file in os.listdir(DATA_DIR):
        if file.endswith('.json'):
            print(f"  - {file}")
