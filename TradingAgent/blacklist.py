#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推荐黑名单管理模块
跟踪历史推荐表现，将近期亏损股加入黑名单，避免重复推荐

黑名单规则：
- 推荐后次日跌幅 > 3%：加入黑名单 7 天
- 推荐后次日跌幅 > 5%：加入黑名单 14 天
- 连续2次推荐亏损：加入黑名单 21 天
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BLACKLIST_FILE = os.path.join(BASE_DIR, 'recommendation_blacklist.json')
HISTORY_DIR = os.path.join(BASE_DIR, 'recommendation_history')


def load_blacklist() -> Dict:
    """加载黑名单"""
    if os.path.exists(BLACKLIST_FILE):
        try:
            with open(BLACKLIST_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'entries': {}, 'stats': {'total_blocked': 0, 'total_expired': 0}}


def save_blacklist(blacklist: Dict):
    """保存黑名单"""
    with open(BLACKLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(blacklist, f, ensure_ascii=False, indent=2)


def is_blocked(stock_code: str) -> Optional[str]:
    """检查股票是否在黑名单中，返回原因或None"""
    blacklist = load_blacklist()
    entry = blacklist['entries'].get(stock_code)
    if not entry:
        return None
    
    # 检查是否过期
    expire_date = entry.get('expire_date', '')
    if expire_date and datetime.now().strftime('%Y-%m-%d') > expire_date:
        # 过期了，移除
        del blacklist['entries'][stock_code]
        blacklist['stats']['total_expired'] = blacklist['stats'].get('total_expired', 0) + 1
        save_blacklist(blacklist)
        return None
    
    return entry.get('reason', '历史推荐亏损')


def add_to_blacklist(stock_code: str, stock_name: str, reason: str, days: int = 7):
    """将股票加入黑名单"""
    blacklist = load_blacklist()
    expire = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
    
    blacklist['entries'][stock_code] = {
        'name': stock_name,
        'reason': reason,
        'added_date': datetime.now().strftime('%Y-%m-%d'),
        'expire_date': expire,
        'block_days': days,
    }
    blacklist['stats']['total_blocked'] = blacklist['stats'].get('total_blocked', 0) + 1
    save_blacklist(blacklist)


def filter_blacklist(candidates: List[Dict]) -> List[Dict]:
    """从候选股列表中过滤掉黑名单中的股票"""
    filtered = []
    for stock in candidates:
        code = stock.get('code', '')
        reason = is_blocked(code)
        if reason:
            print(f"[BLACKLIST] 跳过 {code} {stock.get('name', '')}: {reason}")
        else:
            filtered.append(stock)
    return filtered


def update_blacklist_from_history():
    """遍历历史推荐记录，根据次日表现更新黑名单
    
    由验证脚本（收盘后）调用，不是推荐时调用
    """
    if not os.path.exists(HISTORY_DIR):
        return
    
    blacklist = load_blacklist()
    updated = 0
    
    # 遍历所有历史推荐
    for filename in os.listdir(HISTORY_DIR):
        if not filename.startswith('recommendation_') or not filename.endswith('.json'):
            continue
        
        filepath = os.path.join(HISTORY_DIR, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                record = json.load(f)
        except Exception:
            continue
        
        rec_date = record.get('date', '')
        recommendations = record.get('recommended', [])
        if isinstance(recommendations, dict):
            recommendations = [recommendations]
        
        # 只处理2天前的记录（确保有次日数据）
        try:
            rec_dt = datetime.strptime(rec_date, '%Y-%m-%d')
            if rec_dt > datetime.now() - timedelta(days=1):
                continue
        except ValueError:
            continue
        
        for rec in recommendations:
            code = rec.get('stock_code', '')
            name = rec.get('stock_name', '')
            
            if not code:
                continue
            
            # 检查是否已在黑名单
            if code in blacklist['entries']:
                continue
            
            # 检查次日表现（如果有verify数据）
            verify = rec.get('verify', {})
            if verify:
                next_day_change = verify.get('next_day_change_pct', 0)
                if next_day_change < -5:
                    add_to_blacklist(code, name, f"推荐后次日大跌{next_day_change:.1f}%", 14)
                    updated += 1
                elif next_day_change < -3:
                    add_to_blacklist(code, name, f"推荐后次日跌{next_day_change:.1f}%", 7)
                    updated += 1
    
    if updated:
        print(f"[BLACKLIST] 更新了 {updated} 只股票的黑名单")


def get_blacklist_summary() -> str:
    """获取黑名单摘要"""
    blacklist = load_blacklist()
    entries = blacklist.get('entries', {})
    if not entries:
        return "黑名单为空"
    
    lines = [f"当前黑名单 ({len(entries)} 只):"]
    for code, entry in entries.items():
        lines.append(f"  {code} {entry.get('name', '')} - {entry.get('reason', '')} (到期: {entry.get('expire_date', '')})")
    return '\n'.join(lines)


if __name__ == '__main__':
    print(get_blacklist_summary())
