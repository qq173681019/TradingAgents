"""
清理批量评分文件：
1) 备份并删除 data/batch_stock_scores_none.json（如果存在）
2) 遍历 data/ 下所有 batch_stock_scores_*.json 文件，删除 analysis_type == 'real_llm_analysis' 的条目
3) 为每个处理过的文件写入一个 .cleaned.json 备份，并更新原文件

用法：
    python tools/cleanup_batch_scores.py

脚本会打印处理摘要。
"""
import json
import os
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
NONE_FILE = os.path.join(DATA_DIR, 'batch_stock_scores_none.json')

def backup_and_remove_none_file():
    if not os.path.exists(NONE_FILE):
        print(f"未找到 {NONE_FILE}，跳过备份/删除步骤")
        return False
    try:
        bak = NONE_FILE + '.bak.' + datetime.now().strftime('%Y%m%d_%H%M%S')
        print(f"备份 {NONE_FILE} -> {bak}")
        with open(NONE_FILE, 'rb') as fr, open(bak, 'wb') as fw:
            fw.write(fr.read())
        print(f"删除原始文件 {NONE_FILE}")
        os.remove(NONE_FILE)
        return True
    except Exception as e:
        print(f"备份或删除 {NONE_FILE} 失败: {e}")
        return False


def clean_batch_files():
    pattern_prefix = 'batch_stock_scores'
    files = [f for f in os.listdir(DATA_DIR) if f.startswith(pattern_prefix) and f.endswith('.json')]
    if not files:
        print("data 目录中没有找到批量评分文件。")
        return

    total_files = 0
    total_removed_entries = 0
    for fname in files:
        total_files += 1
        path = os.path.join(DATA_DIR, fname)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"读取 {fname} 失败: {e}")
            continue

        scores = data.get('scores') or data.get('stocks') or {}
        if isinstance(scores, list):
            # 如果是数组格式，尝试转换成 dict 以便清理
            new_scores = []
            removed = 0
            for item in scores:
                if isinstance(item, dict):
                    analysis_type = item.get('analysis_type') or item.get('analysis', {}).get('analysis_type')
                    # 标记为 LLM 的项会被过滤
                    if analysis_type == 'real_llm_analysis' or any(k.startswith('llm') for k in item.keys()):
                        removed += 1
                        continue
                    new_scores.append(item)
            if removed > 0:
                data['stocks'] = new_scores
                total_removed_entries += removed
                cleaned_path = path + '.cleaned.json'
                with open(cleaned_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                # 覆盖原文件
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"清理 {fname}: 移除 {removed} 条 LLM 条目 -> 保存为 {cleaned_path}")
            else:
                print(f"{fname}: 未发现 LLM 条目，跳过")
        elif isinstance(scores, dict):
            removed_codes = []
            for code, entry in list(scores.items()):
                try:
                    analysis_type = None
                    if isinstance(entry, dict):
                        analysis_type = entry.get('analysis_type') or entry.get('analysis', {}).get('analysis_type')
                    if analysis_type == 'real_llm_analysis':
                        removed_codes.append(code)
                        del scores[code]
                    else:
                        # 防御性检查：如果条目里存在 llm_model 或 llm_* 字段，也当作 LLM 条目移除
                        if isinstance(entry, dict) and any(k.startswith('llm') for k in entry.keys()):
                            removed_codes.append(code)
                            del scores[code]
                except Exception:
                    continue

            if removed_codes:
                total_removed_entries += len(removed_codes)
                data['scores'] = scores
                cleaned_path = path + '.cleaned.json'
                with open(cleaned_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                # 覆盖原文件
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"清理 {fname}: 移除 {len(removed_codes)} 条 LLM 条目 (示例: {removed_codes[:5]}) -> 保存为 {cleaned_path}")
            else:
                print(f"{fname}: 未发现 LLM 条目，跳过")
        else:
            print(f"无法解析 {fname} 中的 scores/stocks 结构，跳过")

    print('\n处理完成。')
    print(f"总文件数: {total_files}, 总移除 LLM 条目: {total_removed_entries}")


if __name__ == '__main__':
    print("开始：备份并删除 none 文件（如果存在），然后清理批量评分文件中的 LLM 条目")
    os.makedirs(DATA_DIR, exist_ok=True)
    backup_and_remove_none_file()
    clean_batch_files()
    print("结束")
