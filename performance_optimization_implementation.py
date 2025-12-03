# ==================== 性能优化实现模块 ====================
"""
性能优化实现模块 - 提供缓存、异步处理和优化分析功能
为A股智能分析系统提供性能增强
"""

import asyncio
import hashlib
import json
import threading
import time
from collections import OrderedDict, defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


class HighPerformanceCache:
    """高性能缓存系统"""
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache = OrderedDict()
        self.timestamps = {}
        self.hit_count = 0
        self.miss_count = 0
        self._lock = threading.RLock()
        
    def _is_expired(self, key: str) -> bool:
        """检查缓存项是否过期"""
        if key not in self.timestamps:
            return True
        return (datetime.now() - self.timestamps[key]).seconds > self.ttl_seconds
        
    def _cleanup_expired(self):
        """清理过期缓存项"""
        current_time = datetime.now()
        expired_keys = [
            key for key, timestamp in self.timestamps.items()
            if (current_time - timestamp).seconds > self.ttl_seconds
        ]
        for key in expired_keys:
            self.cache.pop(key, None)
            self.timestamps.pop(key, None)
            
    def _make_key(self, *args, **kwargs) -> str:
        """生成缓存键"""
        key_data = str(args) + str(sorted(kwargs.items()))
        return hashlib.md5(key_data.encode()).hexdigest()
        
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self._lock:
            if key in self.cache and not self._is_expired(key):
                # 移动到末尾（LRU）
                value = self.cache.pop(key)
                self.cache[key] = value
                self.hit_count += 1
                return value
            else:
                self.miss_count += 1
                return None
                
    def put(self, key: str, value: Any):
        """存储缓存值"""
        with self._lock:
            # 清理过期项
            self._cleanup_expired()
            
            # 如果缓存满了，删除最老的项
            if len(self.cache) >= self.max_size:
                oldest_key = next(iter(self.cache))
                self.cache.pop(oldest_key)
                self.timestamps.pop(oldest_key, None)
                
            self.cache[key] = value
            self.timestamps[key] = datetime.now()
            
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total_requests = self.hit_count + self.miss_count
        hit_rate = (self.hit_count / total_requests) if total_requests > 0 else 0
        
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hit_count': self.hit_count,
            'miss_count': self.miss_count,
            'hit_rate': round(hit_rate, 3),
            'ttl_seconds': self.ttl_seconds
        }
        
    def clear(self):
        """清空缓存"""
        with self._lock:
            self.cache.clear()
            self.timestamps.clear()
            self.hit_count = 0
            self.miss_count = 0


class AsyncDataProcessor:
    """异步数据处理器"""
    
    def __init__(self, cache: HighPerformanceCache = None):
        self.cache = cache or HighPerformanceCache()
        self.executor = None
        self.max_workers = 5
        
    def start_executor(self):
        """启动线程池执行器"""
        if self.executor is None:
            from concurrent.futures import ThreadPoolExecutor
            self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
            
    def stop_executor(self):
        """停止线程池执行器"""
        if self.executor:
            self.executor.shutdown(wait=True)
            self.executor = None
            
    def submit_task(self, func, *args, **kwargs):
        """提交异步任务"""
        self.start_executor()
        return self.executor.submit(func, *args, **kwargs)
        
    def batch_process(self, func, items: List[Any], batch_size: int = 10) -> List[Any]:
        """批量处理数据"""
        results = []
        
        # 检查缓存
        for item in items:
            cache_key = self.cache._make_key(func.__name__, item)
            cached_result = self.cache.get(cache_key)
            if cached_result is not None:
                results.append(cached_result)
            else:
                # 需要处理的项
                try:
                    result = func(item)
                    self.cache.put(cache_key, result)
                    results.append(result)
                except Exception as e:
                    print(f"处理项目 {item} 时出错: {e}")
                    results.append(None)
                    
        return results
        
    def parallel_process(self, func, items: List[Any], max_workers: int = None) -> List[Any]:
        """并行处理数据"""
        if max_workers:
            self.max_workers = max_workers
            
        self.start_executor()
        futures = []
        
        for item in items:
            # 检查缓存
            cache_key = self.cache._make_key(func.__name__, item)
            cached_result = self.cache.get(cache_key)
            if cached_result is not None:
                futures.append(None)  # 占位符
            else:
                future = self.executor.submit(func, item)
                futures.append(future)
                
        # 收集结果
        results = []
        for i, future in enumerate(futures):
            if future is None:
                # 使用缓存结果
                cache_key = self.cache._make_key(func.__name__, items[i])
                results.append(self.cache.get(cache_key))
            else:
                try:
                    result = future.result(timeout=30)
                    cache_key = self.cache._make_key(func.__name__, items[i])
                    self.cache.put(cache_key, result)
                    results.append(result)
                except Exception as e:
                    print(f"并行处理项目 {items[i]} 时出错: {e}")
                    results.append(None)
                    
        return results


class OptimizedStockAnalyzer:
    """优化的股票分析器"""
    
    def __init__(self, cache: HighPerformanceCache = None):
        self.cache = cache or HighPerformanceCache()
        self.processor = AsyncDataProcessor(self.cache)
        
    def analyze_stock_batch(self, stock_codes: List[str], analysis_func) -> Dict[str, Any]:
        """批量分析股票"""
        start_time = time.time()
        
        # 并行处理股票分析
        results = self.processor.parallel_process(analysis_func, stock_codes)
        
        # 组织结果
        analysis_results = {}
        for code, result in zip(stock_codes, results):
            if result is not None:
                analysis_results[code] = result
                
        end_time = time.time()
        processing_time = round(end_time - start_time, 2)
        
        return {
            'results': analysis_results,
            'stats': {
                'total_stocks': len(stock_codes),
                'successful_analyses': len(analysis_results),
                'processing_time_seconds': processing_time,
                'cache_stats': self.cache.get_stats()
            }
        }
        
    def get_cached_analysis(self, stock_code: str, analysis_type: str = "default") -> Optional[Any]:
        """获取缓存的分析结果"""
        cache_key = self.cache._make_key(stock_code, analysis_type)
        return self.cache.get(cache_key)
        
    def cache_analysis_result(self, stock_code: str, result: Any, analysis_type: str = "default"):
        """缓存分析结果"""
        cache_key = self.cache._make_key(stock_code, analysis_type)
        self.cache.put(cache_key, result)
        
    def optimize_data_loading(self, data_loader_func, data_keys: List[str]) -> Dict[str, Any]:
        """优化数据加载"""
        # 检查哪些数据已经缓存
        cached_data = {}
        missing_keys = []
        
        for key in data_keys:
            cache_key = self.cache._make_key("data_load", key)
            cached_result = self.cache.get(cache_key)
            if cached_result is not None:
                cached_data[key] = cached_result
            else:
                missing_keys.append(key)
                
        # 只加载缺失的数据
        if missing_keys:
            new_data = self.processor.parallel_process(data_loader_func, missing_keys)
            
            # 缓存新数据
            for key, data in zip(missing_keys, new_data):
                if data is not None:
                    cache_key = self.cache._make_key("data_load", key)
                    self.cache.put(cache_key, data)
                    cached_data[key] = data
                    
        return cached_data
        
    def cleanup(self):
        """清理资源"""
        self.processor.stop_executor()
        self.cache.clear()


# 便捷函数
def create_optimized_system() -> Tuple[HighPerformanceCache, AsyncDataProcessor, OptimizedStockAnalyzer]:
    """创建优化系统的便捷函数"""
    cache = HighPerformanceCache(max_size=2000, ttl_seconds=7200)  # 2小时TTL
    processor = AsyncDataProcessor(cache)
    analyzer = OptimizedStockAnalyzer(cache)
    
    return cache, processor, analyzer


def benchmark_performance(func, *args, **kwargs) -> Dict[str, Any]:
    """性能基准测试"""
    start_time = time.time()
    start_memory = 0  # 简化版本，不实际测量内存
    
    try:
        result = func(*args, **kwargs)
        success = True
        error = None
    except Exception as e:
        result = None
        success = False
        error = str(e)
        
    end_time = time.time()
    execution_time = round(end_time - start_time, 3)
    
    return {
        'success': success,
        'execution_time_seconds': execution_time,
        'result': result,
        'error': error,
        'function_name': func.__name__
    }


# 模块版本信息
__version__ = "1.0.0"
__author__ = "A股智能分析系统"
__description__ = "性能优化实现模块"

# 导出的主要类和函数
__all__ = [
    'HighPerformanceCache',
    'AsyncDataProcessor', 
    'OptimizedStockAnalyzer',
    'create_optimized_system',
    'benchmark_performance'
]


if __name__ == "__main__":
    # 测试模块功能
    print("🚀 性能优化模块测试")
    
    # 测试缓存
    cache = HighPerformanceCache(max_size=5)
    cache.put("test1", {"data": "value1"})
    cache.put("test2", {"data": "value2"})
    
    print("缓存测试:")
    print(f"获取test1: {cache.get('test1')}")
    print(f"缓存统计: {cache.get_stats()}")
    
    # 测试异步处理器
    processor = AsyncDataProcessor(cache)
    
    def test_func(x):
        time.sleep(0.1)  # 模拟处理时间
        return x * 2
        
    print("\n并行处理测试:")
    start_time = time.time()
    results = processor.parallel_process(test_func, [1, 2, 3, 4, 5])
    end_time = time.time()
    print(f"结果: {results}")
    print(f"处理时间: {round(end_time - start_time, 2)} 秒")
    
    # 测试优化分析器
    analyzer = OptimizedStockAnalyzer(cache)
    
    def mock_stock_analysis(stock_code):
        time.sleep(0.05)  # 模拟分析时间
        return {
            'code': stock_code,
            'score': 8.5,
            'recommendation': 'buy'
        }
    
    print("\n股票批量分析测试:")
    stocks = ['000001', '000002', '600000']
    batch_results = analyzer.analyze_stock_batch(stocks, mock_stock_analysis)
    print(f"分析结果: {batch_results['stats']}")
    
    # 清理
    processor.stop_executor()
    
    print("\n✅ 性能优化模块测试完成")