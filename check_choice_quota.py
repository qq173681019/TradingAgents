"""检查Choice API配额和权限状态"""
import os
import sys
from datetime import datetime

# 设置DLL路径
dll_dir = os.path.join(os.path.dirname(__file__), "libs", "windows")
if dll_dir not in os.environ.get('PATH', ''):
    os.environ['PATH'] = dll_dir + os.pathsep + os.environ.get('PATH', '')
if sys.version_info >= (3, 8):
    os.add_dll_directory(dll_dir)

from config import CHOICE_PASSWORD, CHOICE_USERNAME
from EmQuantAPI import c

print("=" * 60)
print("Choice API 配额和权限诊断")
print("=" * 60)

# 登录
login_options = f"username={CHOICE_USERNAME},password={CHOICE_PASSWORD}"
result = c.start(login_options)
if result.ErrorCode != 0:
    print(f"❌ 登录失败")
    sys.exit(1)
print(f"✅ 登录成功: {CHOICE_USERNAME}\n")

# 权限信息
print("权限信息（来自网页）：")
print("-" * 60)
print("  EM_CSD 序列函数")
print("    - 流量计费周期: W (周)")
print("    - 流量配额: 4000000 次/周")
print("    - 权限起始: 2025-12-02 (本周一)")
print("    - 权限截止: 2025-12-31")
print(f"    - 当前日期: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"    - 本周已过: {datetime.now().strftime('%A')} (周{datetime.now().isoweekday()})")

# 数据采集历史
print("\n最近数据采集记录：")
print("-" * 60)
print("  2025-12-06 21:00-23:00: 大量数据采集")
print("  - choice_mainboard_all.json: 28.41 MB")
print("  - comprehensive_stock_data: 24个分片文件")
print("  - 估计API调用: 数万至数十万次")

# 测试当前状态
print("\n当前API测试：")
print("-" * 60)

# 测试1: CSS接口（应该正常）
print("\n[测试1] CSS接口 - 截面数据")
data = c.css("000001.SZ", "CLOSE", "")
print(f"  ErrorCode: {data.ErrorCode} - {data.ErrorMsg}")
if data.ErrorCode == 0:
    print(f"  ✅ CSS接口正常: CLOSE={data.Data.get('000001.SZ', [None])[0]}")
else:
    print(f"  ❌ CSS接口失败")

# 测试2: CSD接口（可能配额不足）
print("\n[测试2] CSD接口 - 序列数据")
data = c.csd("000001.SZ", "CLOSE", "2025-12-05", "2025-12-05", "")
print(f"  ErrorCode: {data.ErrorCode} - {data.ErrorMsg}")
if data.ErrorCode == 0:
    print(f"  ✅ CSD接口正常")
elif data.ErrorCode == 10001012:
    print(f"  ❌ CSD接口权限不足")
    print(f"  【原因分析】")
    print(f"    可能1: 周配额已用完（本周一12/2开始，已经过5天）")
    print(f"    可能2: 试用版CSD功能受限")
    print(f"    可能3: 需要联系客服激活完整权限")

# 建议
print("\n" + "=" * 60)
print("【建议方案】")
print("=" * 60)
print("1. 等待配额重置：")
print("   - 下周一 (2025-12-09) 配额应该会重置")
print("   - 届时重新测试CSD接口")
print()
print("2. 优化API调用：")
print("   - 减少单次数据采集的股票数量")
print("   - 增加数据缓存，避免重复请求")
print("   - 使用CSS接口替代部分CSD调用")
print()
print("3. 使用CSS接口方案：")
print("   - CSS可以指定日期: tradeDate=2025-12-05")
print("   - 可获取字段: CLOSE, PRECLOSE, PE, PB等")
print("   - 通过循环日期来构建历史数据")
print()
print("4. 备用数据源：")
print("   - akshare: 完全免费，无配额限制")
print("   - tushare: 免费版有限制，付费版充足")

print("\n" + "=" * 60)
c.stop()
