"""诊断Choice API错误10000013的原因"""
import os
import sys
import time
from datetime import datetime

# 设置DLL路径
script_dir = os.path.dirname(os.path.abspath(__file__))
dll_dir = os.path.join(script_dir, "libs", "windows")
if dll_dir not in os.environ.get('PATH', ''):
    os.environ['PATH'] = dll_dir + os.pathsep + os.environ.get('PATH', '')

if sys.version_info >= (3, 8):
    os.add_dll_directory(dll_dir)

from EmQuantAPI import c

print("="*60)
print("Choice API 错误诊断工具")
print("="*60)

# 1. 初始化连接
print("\n[1] 初始化Choice SDK...")
result = c.start("")
if result.ErrorCode != 0:
    print(f"❌ 连接失败: {result.ErrorMsg}")
    sys.exit(1)
print("✅ 连接成功")

# 2. 测试单个股票的css查询
print("\n[2] 测试单个股票css查询...")
test_codes = ["000001.SZ", "600000.SH", "000002.SZ"]

for code in test_codes:
    print(f"\n  测试 {code}...")
    result = c.css(code, "SECNAME,LISTDATE,DELISTDATE", "")
    print(f"    ErrorCode: {result.ErrorCode}")
    if result.ErrorCode == 0:
        print(f"    ✅ 查询成功")
        if hasattr(result, 'Data') and code in result.Data:
            print(f"    数据: {result.Data[code]}")
    else:
        print(f"    ❌ 查询失败")
        if hasattr(result, 'ErrorMsg'):
            print(f"    错误信息: {result.ErrorMsg}")
    
    # 短暂延迟
    time.sleep(0.5)

# 3. 测试批量查询（不同数量）
print("\n[3] 测试批量css查询...")
batch_sizes = [2, 5, 10, 20, 50]

for size in batch_sizes:
    # 生成测试代码
    codes = []
    for i in range(size):
        codes.append(f"00000{i % 10}.SZ" if i % 2 == 0 else f"60000{i % 10}.SH")
    
    codes_str = ",".join(codes)
    print(f"\n  批量大小: {size} 只股票")
    print(f"  代码示例: {codes[:3]}")
    
    start_time = time.time()
    result = c.css(codes_str, "SECNAME", "")
    elapsed = time.time() - start_time
    
    print(f"    ErrorCode: {result.ErrorCode}")
    print(f"    耗时: {elapsed:.2f}秒")
    
    if result.ErrorCode == 0:
        print(f"    ✅ 查询成功")
        if hasattr(result, 'Data'):
            print(f"    返回数据数量: {len(result.Data)}")
    else:
        print(f"    ❌ 查询失败 (ErrorCode: {result.ErrorCode})")
        if hasattr(result, 'ErrorMsg'):
            print(f"    错误信息: {result.ErrorMsg}")
    
    # 延迟避免频率限制
    time.sleep(1)

# 4. 测试连续查询（频率测试）
print("\n[4] 测试连续查询（检测频率限制）...")
success_count = 0
fail_count = 0
test_count = 10

print(f"  将连续查询 {test_count} 次...")

for i in range(test_count):
    result = c.css("000001.SZ", "SECNAME", "")
    if result.ErrorCode == 0:
        success_count += 1
        print(f"  [{i+1}] ✅", end="", flush=True)
    else:
        fail_count += 1
        print(f"  [{i+1}] ❌ (ErrorCode: {result.ErrorCode})", end="", flush=True)
    
    # 不加延迟，测试频率限制
    # time.sleep(0.1)

print(f"\n  结果: 成功 {success_count}/{test_count}, 失败 {fail_count}/{test_count}")

# 5. 测试带延迟的连续查询
print("\n[5] 测试带延迟的连续查询（每次延迟0.2秒）...")
success_count = 0
fail_count = 0

for i in range(test_count):
    result = c.css("000002.SZ", "SECNAME", "")
    if result.ErrorCode == 0:
        success_count += 1
        print(f"  [{i+1}] ✅", end="", flush=True)
    else:
        fail_count += 1
        print(f"  [{i+1}] ❌ (ErrorCode: {result.ErrorCode})", end="", flush=True)
    
    time.sleep(0.2)  # 200ms延迟

print(f"\n  结果: 成功 {success_count}/{test_count}, 失败 {fail_count}/{test_count}")

# 6. 测试LISTDATE字段是否需要权限
print("\n[6] 测试不同字段的权限...")
fields_to_test = [
    ("SECNAME", "股票名称"),
    ("LISTDATE", "上市日期"),
    ("DELISTDATE", "退市日期"),
    ("SECNAME,LISTDATE", "名称+上市日期"),
    ("SECNAME,LISTDATE,DELISTDATE", "名称+上市日期+退市日期"),
]

for field, desc in fields_to_test:
    print(f"\n  测试字段: {desc} ({field})")
    result = c.css("000001.SZ", field, "")
    print(f"    ErrorCode: {result.ErrorCode}")
    
    if result.ErrorCode == 0:
        print(f"    ✅ 查询成功")
        if hasattr(result, 'Data') and "000001.SZ" in result.Data:
            print(f"    数据: {result.Data['000001.SZ']}")
    else:
        print(f"    ❌ 查询失败")
        if hasattr(result, 'ErrorMsg'):
            print(f"    错误信息: {result.ErrorMsg}")
    
    time.sleep(0.5)

# 7. 总结
print("\n" + "="*60)
print("诊断总结:")
print("="*60)
print("\n错误代码 10000013 通常表示:")
print("  1. 服务端错误 (service error)")
print("  2. 可能原因:")
print("     - API权限不足（某些字段需要更高权限）")
print("     - 访问频率过高（触发限流）")
print("     - 批量查询数量过大")
print("     - 某些字段在特定账户下不可用")
print("\n建议:")
print("  1. 检查您的Choice账户权限级别")
print("  2. 在批量查询时添加延迟（建议0.2-0.5秒/次）")
print("  3. 减少批量查询的数量（建议每批≤20只股票）")
print("  4. 避免使用需要高级权限的字段")

# 断开连接
c.stop()
print("\n✅ 诊断完成")
