"""验证颜色警告功能实现"""
import re


def _get_status_color(status_text):
    """根据状态文本返回颜色"""
    # 检查是否有错误状态
    if "无" in status_text or "失败" in status_text:
        return "#e74c3c"  # 红色
    
    # 提取天数差异信息 [AGE:X]
    age_match = re.search(r'\[AGE:(\d+)\]', status_text)
    if age_match:
        days_old = int(age_match.group(1))
        
        if days_old == 0:
            return "#27ae60"  # 绿色 - 当天数据
        elif days_old <= 5:
            return "#f39c12"  # 黄色 - 1-5天旧数据
        else:
            return "#e74c3c"  # 红色 - 超过5天
    
    # 没有年龄信息时默认绿色
    return "#27ae60"

print("=" * 70)
print("颜色警告功能验证")
print("=" * 70)

test_cases = [
    ("本地数据: 2024-12-15 (16个文件) [AGE:0]", "#27ae60", "当天数据 → 绿色"),
    ("本地数据: 2024-12-12 (16个文件) [AGE:3]", "#f39c12", "3天前数据 → 黄色"),
    ("本地数据: 2024-12-08 (16个文件) [AGE:7]", "#e74c3c", "7天前数据 → 红色"),
    ("K线数据: 2024-12-15 [AGE:0]", "#27ae60", "当天K线 → 绿色"),
    ("K线数据: 2024-12-10 [AGE:5]", "#f39c12", "5天前K线 → 黄色"),
    ("K线数据: 2024-12-01 [AGE:14]", "#e74c3c", "14天前K线 → 红色"),
    ("2024-12-15 14:30 | DeepSeek AI [AGE:0]", "#27ae60", "当天评分 → 绿色"),
    ("2024-12-13 14:30 | DeepSeek AI [AGE:2]", "#f39c12", "2天前评分 → 黄色"),
    ("2024-12-05 14:30 | DeepSeek AI [AGE:10]", "#e74c3c", "10天前评分 → 红色"),
    ("无本地数据", "#e74c3c", "无数据 → 红色"),
    ("数据检查失败", "#e74c3c", "失败 → 红色"),
]

passed = 0
failed = 0

for status_text, expected_color, description in test_cases:
    actual_color = _get_status_color(status_text)
    result = "✅" if actual_color == expected_color else "❌"
    
    if actual_color == expected_color:
        passed += 1
    else:
        failed += 1
    
    # 移除AGE标记用于显示
    display_text = re.sub(r'\s*\[AGE:\d+\]', '', status_text)
    
    print(f"{result} {description}")
    print(f"   文本: {display_text}")
    print(f"   期望颜色: {expected_color}, 实际颜色: {actual_color}")
    print()

print("=" * 70)
print(f"测试结果: {passed} 通过 / {failed} 失败")
print("=" * 70)

if failed == 0:
    print("\n✅ 所有测试通过！颜色警告功能正常工作")
    print("\n颜色说明:")
    print("  🟢 #27ae60 (绿色) - 当天的数据（最新）")
    print("  🟡 #f39c12 (黄色) - 1-5天前的数据（需要注意）")
    print("  🔴 #e74c3c (红色) - 超过5天的数据或错误状态（需要更新）")
else:
    print(f"\n❌ 有 {failed} 个测试失败，请检查实现")
