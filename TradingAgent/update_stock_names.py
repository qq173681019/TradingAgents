"""
通过东方财富 datacenter API 更新评分文件的股票名称和行业
使用多线程 + web 请求，不依赖 Choice/AKShare
"""
import json
import os
import sys
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
import urllib.parse
import ssl

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

DATA_DIR = r"D:\GitHub\TradingAgents\TradingShared\data"
SCORE_FILE = os.path.join(DATA_DIR, "batch_stock_scores_optimized_主板_20260601_204416.json")

# 忽略 SSL 验证
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def fetch_stock_info(code: str) -> dict:
    """通过东方财富 datacenter API 获取单只股票的最新名称和行业"""
    # 判断市场后缀
    if code.startswith("6"):
        secucode = f"{code}.SH"
    elif code.startswith(("0", "3")):
        secucode = f"{code}.SZ"
    elif code.startswith(("8", "4")):
        secucode = f"{code}.BJ"
    else:
        secucode = f"{code}.SZ"

    url = (
        "https://datacenter.eastmoney.com/securities/api/data/v1/get?"
        f"reportName=RPT_F10_BASIC_ORGINFO"
        f"&columns=SECUCODE,SECURITY_NAME_ABBR,EM2016"
        f"&filter=(SECUCODE=%22{secucode}%22)"
    )

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if data.get("success") and data.get("result", {}).get("data"):
            row = data["result"]["data"][0]
            return {
                "code": code,
                "name": row.get("SECURITY_NAME_ABBR", ""),
                "industry": row.get("EM2016", ""),
            }
    except Exception as e:
        logger.debug(f"{code}: {e}")

    return {"code": code, "name": None, "industry": None}


def update_scores_file():
    """批量更新评分文件中的名称和行业"""
    with open(SCORE_FILE, "r", encoding="utf-8") as f:
        scores = json.load(f)

    total = len(scores)
    print(f"加载评分文件: {total} 只股票")
    print(f"文件: {os.path.basename(SCORE_FILE)}")

    # 备份
    backup = SCORE_FILE + ".bak"
    if not os.path.exists(backup):
        import shutil
        shutil.copy2(SCORE_FILE, backup)
        print(f"已备份到: {backup}")

    # 多线程查询
    updated_name = 0
    updated_industry = 0
    name_changes = []
    failed = []
    processed = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {
            pool.submit(fetch_stock_info, code): code
            for code in scores.keys()
        }

        for future in as_completed(futures):
            processed += 1
            code = futures[future]
            try:
                info = future.result()
                if info["name"]:
                    old_name = scores[code].get("name", "")
                    if old_name != info["name"]:
                        scores[code]["name"] = info["name"]
                        updated_name += 1
                        if old_name:
                            name_changes.append((code, old_name, info["name"]))
                else:
                    failed.append(code)

                if info["industry"]:
                    old_ind = scores[code].get("industry", "")
                    if old_ind != info["industry"] and info["industry"] not in ("未知", "null", ""):
                        scores[code]["industry"] = info["industry"]
                        updated_industry += 1
            except Exception as e:
                failed.append(code)

            if processed % 500 == 0 or processed == total:
                elapsed = time.time() - t0
                rate = processed / elapsed if elapsed > 0 else 0
                eta = (total - processed) / rate if rate > 0 else 0
                print(f"  进度: {processed}/{total} ({processed*100//total}%) | "
                      f"名称更新: {updated_name} | 行业更新: {updated_industry} | "
                      f"失败: {len(failed)} | ETA: {eta:.0f}s")

    # 保存
    with open(SCORE_FILE, "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False)

    elapsed = time.time() - t0
    print(f"\n{'=' * 60}")
    print(f"更新完成! 耗时: {elapsed:.0f}s")
    print(f"  名称更新: {updated_name} 只")
    print(f"  行业更新: {updated_industry} 只")
    print(f"  失败: {len(failed)} 只")

    if name_changes:
        print(f"\n=== 名称变更 ({len(name_changes)} 只) ===")
        for code, old, new in name_changes[:30]:
            print(f"  {code}: {old} → {new}")
        if len(name_changes) > 30:
            print(f"  ... 还有 {len(name_changes) - 30} 只")

    if failed[:10]:
        print(f"  失败示例: {failed[:10]}")


if __name__ == "__main__":
    update_scores_file()
