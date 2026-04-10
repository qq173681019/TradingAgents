#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务执行器和通知器
执行回测并通过OpenClaw发送通知
"""

import os
import sys
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

# 导入简化版回测系统
from backtest_simple import optimize_and_test

RESULT_DIR = os.path.join(os.path.dirname(__file__), 'backtest_results')
NOTIFICATION_FILE = os.path.join(RESULT_DIR, 'notification.json')


def main():
    """
    主执行函数
    """
    print("=" * 70)
    print("股票推荐算法回测验证系统")
    print("执行时间:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 70)
    print()
    
    # 运行回测
    start_time = time.time()
    
    try:
        success, accuracy, version = optimize_and_test()
        
        elapsed = time.time() - start_time
        minutes, seconds = divmod(int(elapsed), 60)
        
        # 生成最终通知
        if success:
            title = "[PASS] 股票推荐算法验证通过！"
            message = f"""
🎉 算法验证成功！

算法版本: {version}
准确率: {accuracy*100:.2f}% (目标: 85%)
回测时间: 2026-02-20 至 2026-04-07
耗时: {minutes}分{seconds}秒

状态: 算法验证成功！可以投入生产使用。
"""
        else:
            title = "[FAIL] 股票推荐算法未达标"
            message = f"""
⚠️ 算法需要优化

算法版本: {version}
准确率: {accuracy*100:.2f}% (目标: 85%)
差距: {(0.85 - accuracy)*100:.2f}%
回测时间: 2026-02-20 至 2026-04-07
耗时: {minutes}分{seconds}秒

建议: 调整权重配置或增加更多数据源
"""
        
        # 保存通知
        os.makedirs(RESULT_DIR, exist_ok=True)
        
        notification = {
            'title': title,
            'message': message,
            'success': success,
            'accuracy': accuracy,
            'version': version,
            'elapsed_seconds': elapsed,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        with open(NOTIFICATION_FILE, 'w', encoding='utf-8') as f:
            json.dump(notification, f, ensure_ascii=False, indent=2)
        
        print("\n" + "=" * 70)
        print(title)
        print("=" * 70)
        print(message)
        print()
        print(f"通知已保存: {NOTIFICATION_FILE}")
        print("=" * 70)
        
        return success
        
    except Exception as e:
        print(f"\n[ERROR] Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        
        # 保存错误通知
        error_notification = {
            'title': '[ERROR] 回测执行失败',
            'message': f'错误信息: {str(e)}',
            'success': False,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        with open(NOTIFICATION_FILE, 'w', encoding='utf-8') as f:
            json.dump(error_notification, f, ensure_ascii=False, indent=2)
        
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
