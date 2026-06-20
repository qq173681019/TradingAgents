#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创业板赛道龙头筛选器 V2
=========================
多数据源 + 硬知识库 + AKShare补充
"""

import json, os, sys, time, io
import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict

# Fix Windows encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

OUTPUT_DIR = r'D:\GitHub\TradingAgents\TradingAgent\chinext_screen'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================
# 硬知识库 — 创业板赛道龙头（基于公开信息整理）
# ============================================================
HARDCODED_POOL = {
    "AI-PCB": [
        ("300476.SZ", "胜宏科技", "HDl/多层板,英伟达供应链,AI算力PCB龙头"),
        ("300408.SZ", "三环集团", "陶瓷元器件+MLCC+PCB上游"),
        ("300765.SZ", "安靠智能", "高端PCB,HDI"),
        ("300847.SZ", "中天精工", "精密PCB,5G通信板"),
        ("300942.SZ", "堪通科技", "PCB制造"),
        ("301088.SZ", "景旺电子", "PCB行业龙头之一"),
        ("301046.SZ", "金禄电子", "汽车PCB"),
        ("300476.SZ", "胜宏科技", "已存在"),
    ],
    "AI-CCL": [
        ("300831.SZ", "派特尔", "覆铜板相关材料"),
        ("300853.SZ", "申昊科技", "电子材料"),
        ("301029.SZ", "裕太微", "覆铜板相关"),
    ],
    "电子特气": [
        # 创业板较少,主要在科创
        ("300699.SZ", "光威复材", "碳纤维+特种材料"),
        ("300398.SZ", "飞凯材料", "电子化学品+特气"),
        ("300699.SZ", "沃特股份", "特种工程塑料"),
    ],
    "电子布": [
        ("300600.SZ", "国轩高科", "锂电池(非电子布,排除)"),
        ("300056.SZ", "三维化学", "化工材料"),
    ],
    "钨产业链": [
        # 创业板无纯正钨股,主要在主板
        ("300117.SZ", "嘉寓股份", "建材类(非钨)"),
    ],
    "AI铜箔": [
        ("301511.SZ", "德福科技", "高端铜箔,AI算力供应链"),
        ("301217.SZ", "铜冠铜箔", "PCB铜箔+锂电铜箔,HVLP"),
    ],
    "半导体芯片": [
        ("300661.SZ", "圣邦股份", "模拟芯片龙头,电源管理"),
        ("300223.SZ", "北京君正", "存储+处理芯片"),
        ("300613.SZ", "富瀚微", "安防芯片"),
        ("300782.SZ", "卓胜微", "射频芯片龙头"),
        ("300768.SZ", "迪普科技", "网络芯片"),
        ("300053.SZ", "欧比特", "宇航级芯片+卫星"),
        ("300101.SZ", "振芯科技", "北斗芯片"),
        ("300706.SZ", "阿石创", "靶材,PVD镀膜材料"),
        ("300666.SZ", "江丰电子", "高纯溅射靶材,半导体材料"),
        ("300942.SZ", "坤能科技", "功率器件"),
        ("300373.SZ", "扬杰科技", "功率半导体,IGBT"),
        ("300671.SZ", "富满微", "电源管理芯片"),
        ("300628.SZ", "亿联网络", "通信设备(非芯片)"),
        ("300257.SZ", "开山股份", "压缩机(非芯片)"),
    ],
    "存储芯片": [
        ("300661.SZ", "圣邦股份", "存储相关模拟芯片"),
        ("300223.SZ", "北京君正", "DRAM+SRAM,车规存储"),
        ("300768.SZ", "迪普科技", "非存储"),
        ("301308.SZ", "华大九天", "EDA(非存储)"),
        ("300046.SZ", "台基股份", "功率器件(非存储)"),
    ],
    "AI算力": [
        ("300476.SZ", "胜宏科技", "AI服务器PCB"),
        ("300687.SZ", "赛意信息", "工业互联网+算力"),
        ("300602.SZ", "飞荣达", "散热方案,算力配套"),
        ("300842.SZ", "帝科股份", "导电银浆(非算力)"),
        ("300502.SZ", "新易盛", "光模块(算力配套)"),
        ("300308.SZ", "中际旭创", "光模块(算力配套)"),
    ],
    "光模块/CPO": [
        ("300308.SZ", "中际旭创", "全球光模块龙头,800G/1.6T,CPO布局"),
        ("300502.SZ", "新易盛", "光模块二线龙头,800G量产"),
        ("300323.SZ", "华灿光电", "LED+光电器件"),
        ("300620.SZ", "光库科技", "光隔离器/环形器,铌酸锂调制器"),
        ("300620.SZ", "光库科技", "CPO核心器件"),
        ("300564.SZ", "筑博设计", "建筑设计(非光模块)"),
        ("300738.SZ", "奥飞数据", "数据中心(IDC),光模块客户"),
        ("300803.SZ", "指南针", "金融软件(非光模块)"),
        ("300999.SZ", "金龙鱼", "消费品(排除)"),
        ("300059.SZ", "东方财富", "金融(排除)"),
    ],
    "液冷": [
        ("300602.SZ", "飞荣达", "导热界面材料+液冷板"),
        ("300830.SZ", "金现代", "电力IT(非液冷)"),
        ("300682.SZ", "新联电子", "温控设备"),
        ("300012.SZ", "华测检测", "检测服务(非液冷)"),
        ("300999.SZ", "居然之家", "零售(排除)"),
        # 补充
        ("300738.SZ", "奥飞数据", "IDC液冷"),
        ("300663.SZ", "科大国创", "储能液冷"),
    ],
    "HBM产业链": [
        # HBM主要在科创/主板,但封装/材料有创业板
        ("300666.SZ", "江丰电子", "靶材,HBM封装材料"),
        ("300706.SZ", "阿石创", "靶材,先进封装"),
        ("300661.SZ", "圣邦股份", "电源管理IC(HBM配套)"),
        ("300373.SZ", "扬杰科技", "功率半导体(非HBM)"),
    ],
    "消费电子": [
        ("300433.SZ", "蓝思科技", "玻璃盖板龙头,苹果链"),
        ("300115.SZ", "长盈精密", "精密结构件,苹果链"),
        ("300296.SZ", "利亚德", "小间距LED,显示"),
        ("300706.SZ", "阿石创", "消费电子镀膜"),
        ("300979.SZ", "华利集团", "鞋类制造(排除)"),
        ("300896.SZ", "爱美客", "医美(排除)"),
    ],
    "新能源电池": [
        ("300750.SZ", "宁德时代", "全球动力电池龙头"),
        ("300014.SZ", "亿纬锂能", "锂原电池+动力电池"),
        ("300207.SZ", "欣旺达", "消费电池+动力电池"),
        ("300438.SZ", "鹏辉能源", "储能电池"),
        ("300068.SZ", "南都电源", "铅酸+锂电+储能"),
        ("300825.SZ", "阿尔特", "新能源车设计(非电池)"),
        ("300750.SZ", "宁德时代", "已存在"),
    ],
    "机器人": [
        ("300024.SZ", "机器人", "工业机器人龙头,新松"),
        ("300756.SZ", "金马游乐", "游乐设备(非机器人)"),
        ("300024.SZ", "机器人", "已存在"),
        ("300699.SZ", "光威复材", "碳纤维(非机器人)"),
        ("300896.SZ", "爱美客", "医美(排除)"),
        # 真正机器人相关
        ("300457.SZ", "赢合科技", "锂电设备+机器人"),
        ("300606.SZ", "金太阳", "精密研磨(机器人配套)"),
    ],
    "华为产业链": [
        ("300476.SZ", "胜宏科技", "华为PCB供应商"),
        ("300661.SZ", "圣邦股份", "华为芯片供应链"),
        ("300223.SZ", "北京君正", "华为存储芯片"),
        ("300024.SZ", "机器人", "华为机器人合作"),
        ("300682.SZ", "新联电子", "华为电力合作"),
    ],
    "电力": [
        ("300443.SZ", "金智科技", "电力信息化"),
        ("300341.SZ", "麦克奥迪", "电气元器件"),
        ("300692.SZ", "中环股份", "光伏(非电力设备)"),
        ("300842.SZ", "帝科股份", "导电银浆(光伏配套)"),
        ("300322.SZ", "硕贝德", "天线+汽车电子"),
    ],
    "商业航天": [
        ("300034.SZ", "钢研高纳", "高温合金,航天材料"),
        ("300053.SZ", "欧比特", "宇航芯片+卫星星座"),
        ("300101.SZ", "振芯科技", "北斗+卫星导航"),
        ("300455.SZ", "康拓红外", "航天红外检测"),
        ("300699.SZ", "光威复材", "碳纤维,航天材料"),
        ("300527.SZ", "中船应急", "军工+应急装备"),
    ],
    "电子树脂": [
        ("300398.SZ", "飞凯材料", "电子化学品+树脂材料"),
        ("300699.SZ", "沃特股份", "特种工程塑料+树脂"),
    ],
    "MLCC": [
        ("300408.SZ", "三环集团", "MLCC龙头,陶瓷元器件"),
        # 创业板MLCC标的较少
    ],
}

# V29已有创业板池
EXISTING_CHINEXT = {
    "300476.SZ": "胜宏科技",
    "300408.SZ": "三环集团",
    "300661.SZ": "圣邦股份",
    "300308.SZ": "中际旭创",
    "300502.SZ": "新易盛",
    "300750.SZ": "宁德时代",
    "300024.SZ": "机器人",
    "300034.SZ": "钢研高纳",
}

def try_akshare_supplement():
    """尝试用AKShare补充数据"""
    results = {}
    try:
        import akshare as ak
        
        # 尝试获取概念板块
        print("[AKShare] 尝试获取概念板块...")
        for attempt in range(3):
            try:
                concept_list = ak.stock_board_concept_name_em()
                print(f"  概念板块: {len(concept_list)}个")
                
                # 找赛道相关的概念
                track_keywords = {
                    'CPO': ['CPO', '共封装', '硅光'],
                    '液冷': ['液冷', '数据中心冷却'],
                    'HBM': ['HBM', '高带宽'],
                    '光模块': ['光模块', '光通信'],
                    '半导体': ['半导体', '芯片', '集成电路'],
                    'PCB': ['PCB', '印制电路'],
                    '机器人': ['机器人'],
                    '新能源': ['锂电池', '固态电池'],
                    '航天': ['航天', '卫星', '北斗'],
                    '电力': ['电力', '电网'],
                    'MLCC': ['MLCC', '电容'],
                    '钨': ['钨'],
                    '存储': ['存储'],
                }
                
                for track, kws in track_keywords.items():
                    for _, row in concept_list.iterrows():
                        cname = str(row.get('板块名称', ''))
                        for kw in kws:
                            if kw in cname:
                                try:
                                    members = ak.stock_board_concept_cons_em(symbol=cname)
                                    chinext_members = members[
                                        members['代码'].astype(str).str.startswith(('300', '301'))
                                    ]
                                    for _, m in chinext_members.iterrows():
                                        code = f"{m['代码']}.SZ"
                                        name = m.get('名称', '')
                                        if code not in results:
                                            results[code] = {'name': name, 'concepts': []}
                                        results[code]['concepts'].append(f"{track}:{cname}")
                                    time.sleep(0.5)
                                except Exception:
                                    pass
                                break
                    break  # 成功获取概念列表就跳出重试
                break
            except Exception as e:
                print(f"  尝试{attempt+1}失败: {e}")
                time.sleep(2)
        
        print(f"  AKShare补充: {len(results)}只创业板")
    except ImportError:
        print("[AKShare] 未安装")
    except Exception as e:
        print(f"[AKShare] 错误: {e}")
    
    return results

def build_report():
    """构建最终报告"""
    print("="*60)
    print("创业板赛道龙头筛选报告")
    print("="*60)
    
    # 尝试AKShare
    ak_data = try_akshare_supplement()
    
    # 合并硬知识库 + AKShare
    final = defaultdict(list)
    seen_codes = set()
    
    for track, stocks in HARDCODED_POOL.items():
        for code, name, note in stocks:
            if code in EXISTING_CHINEXT:
                is_v29 = True
            else:
                is_v29 = False
            
            # 排除明显不属于该赛道的
            if '排除' in note or '非' in note:
                continue
            
            if code not in seen_codes:
                seen_codes.add(code)
            
            # 合并AKShare概念
            ak_concepts = ak_data.get(code, {}).get('concepts', [])
            
            final[track].append({
                'code': code,
                'name': name,
                'note': note,
                'is_v29': is_v29,
                'ak_concepts': ak_concepts[:3],
            })
    
    # 添加AKShare独有的
    for code, info in ak_data.items():
        if code.startswith(('300', '301')):
            for concept_str in info.get('concepts', []):
                track = concept_str.split(':')[0]
                if track not in final:
                    final[track] = []
                # 检查是否已存在
                exists = any(s['code'] == code for s in final[track])
                if not exists:
                    final[track].append({
                        'code': code,
                        'name': info['name'],
                        'note': f"AKShare概念: {concept_str}",
                        'is_v29': code in EXISTING_CHINEXT,
                        'ak_concepts': [],
                    })
    
    # 输出
    output = {}
    for track in sorted(final.keys()):
        stocks = final[track]
        # 去重
        seen = set()
        unique = []
        for s in stocks:
            if s['code'] not in seen:
                seen.add(s['code'])
                unique.append(s)
        
        new_stocks = [s for s in unique if not s['is_v29']]
        old_stocks = [s for s in unique if s['is_v29']]
        
        output[track] = {
            'total': len(unique),
            'new': len(new_stocks),
            'v29_existing': len(old_stocks),
            'stocks': unique,
        }
        
        print(f"\n[{track}] {len(unique)}只 (V29已有{len(old_stocks)}, 新{len(new_stocks)})")
        for s in old_stocks:
            print(f"  [V29] {s['code']} {s['name']} - {s['note']}")
        for s in new_stocks[:10]:
            print(f"  [NEW] {s['code']} {s['name']} - {s['note']}")
    
    # 保存
    out_file = os.path.join(OUTPUT_DIR, f'chinext_screen_{datetime.now().strftime("%Y%m%d")}.json')
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n保存: {out_file}")
    
    # 统计
    total_new = sum(d['new'] for d in output.values())
    total_old = sum(d['v29_existing'] for d in output.values())
    print(f"\n总计: {len(output)}个赛道, V29已有{total_old}只, 新发现{total_new}只")
    
    return output

if __name__ == '__main__':
    build_report()
