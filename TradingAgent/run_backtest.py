#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测系统主执行器
自动运行回测、优化算法、生成报告
"""

import os
import sys
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from backtest_data_prep import prepare_backtest_data
from backtest_system import (
    AlgorithmOptimizer,
    Backtester,
    generate_report,
    send_notification,
    BACKTEST_START,
    BACKTEST_END,
    TARGET_ACCURACY
)

RESULT_DIR = os.path.join(os.path.dirname(__file__), 'backtest_results')


def run_complete_backtest():
    """
    运行完整的回测流程
    """
    print("\n" + "=" * 70)
    print("股票推荐算法回测验证系统")
    print("Stock Recommendation Algorithm Backtest System")
    print("=" * 70)
    print(f"\n回测时间段: {BACKTEST_START} 至 {BACKTEST_END}")
    print(f"目标准确率: {TARGET_ACCURACY*100:.0f}%")
    print()
    
    # 记录开始时间
    start_time = time.time()
    
    # 1. 准备数据
    print("\n[PHASE 1/4] Preparing data...")
    stocks_data, kline_data, index_data = prepare_backtest_data()
    
    if not stocks_data:
        print("[ERROR] No data available, exiting...")
        return
    
    # 2. 运行优化
    print("\n[PHASE 2/4] Running algorithm optimization...")
    optimizer = AlgorithmOptimizer()
    best_version, best_accuracy, best_result = optimizer.optimize(
        stocks_data, kline_data, index_data, TARGET_ACCURACY
    )
    
    # 3. 生成报告
    print("\n[PHASE 3/4] Generating report...")
    if best_result is None:
        print("[ERROR] No valid backtest result generated. Check data availability.")
        return None, 0.0, None
    os.makedirs(RESULT_DIR, exist_ok=True)
    report_path = os.path.join(RESULT_DIR, f'backtest_report_{best_version}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt')
    generate_report(best_result, report_path)
    
    # 4. 发送通知
    print("\n[PHASE 4/4] Sending notification...")
    success = best_accuracy >= TARGET_ACCURACY
    send_notification(success, best_accuracy, best_version)
    
    # 计算耗时
    elapsed_time = time.time() - start_time
    minutes, seconds = divmod(int(elapsed_time), 60)
    
    # 最终总结
    print("\n" + "=" * 70)
    print("[COMPLETE] Backtest finished!")
    print("=" * 70)
    print(f"\n耗时: {minutes}分{seconds}秒")
    print(f"最佳版本: {best_version}")
    print(f"准确率: {best_accuracy*100:.2f}%")
    print(f"结果: {'通过 OK' if success else '未达标 FAIL'}")
    print(f"\n报告位置: {report_path}")
    print("=" * 70)
    
    # 保存最终结果
    final_result = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'success': success,
        'best_version': best_version,
        'accuracy': best_accuracy,
        'target_accuracy': TARGET_ACCURACY,
        'elapsed_seconds': elapsed_time,
        'report_path': report_path
    }
    
    result_file = os.path.join(RESULT_DIR, 'final_result.json')
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(final_result, f, ensure_ascii=False, indent=2)
    
    print(f"\n[OK] Final result saved to: {result_file}")
    
    return success, best_accuracy, best_version


if __name__ == '__main__':
    try:
        result = run_complete_backtest()
        if result is None or result[0] is None:
            print("\n[ERROR] Backtest produced no results.")
            sys.exit(1)
        success, accuracy, version = result
        
        # 返回退出码
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n[INTERRUPT] Backtest interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n[ERROR] Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
