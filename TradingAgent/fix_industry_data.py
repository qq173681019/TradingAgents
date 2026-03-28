#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复行业信息 - 使用 akshare 实时获取
"""
import json
import os
import time
import akshare as ak
from datetime import datetime, timedelta

# 禁用代理
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''

def get_industry_from_akshare(stock_code):
    """
    使用 akshare 获取股票的真实行业信息
    """
    try:
        # 获取个股信息
        df = ak.stock_individual_info_em(symbol=stock_code)
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                item = str(row.get('item', ''))
                if '行业' in item or '所属行业' in item or '申万行业' in item:
                    value = row.get('value', '')
                    if value and value not in ['未知', '', 'None']:
                        return value
        time.sleep(0.1)  # 避免请求过快
    except Exception as e:
        print(f'[WARN] {stock_code} akshare查询失败: {e}')
        return None

def get_sector_ranking():
    """
    获取板块涨幅排名（使用akshare）
    """
    try:
        print('[INFO] 正在获取板块近3日涨幅数据...')
        
        # 获取行业板块行情数据
        df_sector = ak.stock_board_industry_name_em()
        if df_sector is None or df_sector.empty:
            print('[WARN] 未获取到板块数据')
            return None
        
        print(f'[OK] 获取到 {len(df_sector)} 个行业板块')
        
        # 获取每个板块的近3日涨幅
        sector_changes = {}
        
        # 只处理前50个热门板块（避免请求过多）
        for idx, row in df_sector.head(50).iterrows():
            try:
                sector_name = str(row.get('板块名称', '')).strip()
                if not sector_name:
                    continue
                
                # 获取板块K线数据
                df_kline = ak.stock_board_industry_hist_em(
                    symbol=sector_name,
                    period="日k",
                    start_date=(datetime.now() - timedelta(days=10)).strftime("%Y%m%d"),
                    end_date=datetime.now().strftime("%Y%m%d")
                )
                if df_kline is not None and len(df_kline) >= 4:
                    # 计算近3日涨幅
                    latest_close = float(df_kline.iloc[-1]['收盘'])
                    close_3d_ago = float(df_kline.iloc[-4]['收盘'])
                    change_3d = (latest_close - close_3d_ago) / close_3d_ago * 100
                    sector_changes[sector_name] = round(change_3d, 2)
                else:
                    # 至少有2天数据，用当前涨幅
                    if len(df_kline) >= 2:
                        latest_close = float(df_kline.iloc[-1]['收盘'])
                        prev_close = float(df_kline.iloc[-2]['收盘'])
                        change = (latest_close - prev_close) / prev_close * 100
                        sector_changes[sector_name] = round(change, 2)
                
                time.sleep(0.05)  # 避免请求过快
                
            except Exception as e:
                continue
        
        # 按涨幅排序
        sorted_sectors = sorted(sector_changes.items(), key=lambda x: x[1], reverse=True)
        
        print(f'\n[OK] 成功计算 {len(sorted_sectors)} 个板块的涨幅')
        print('[INFO] 热门板块涨幅Top 10:')
        for i, (name, change) in enumerate(sorted_sectors[:10]):
            print(f'  {i+1}. {name}: {change:+.2f}%')
        
        return sector_changes
        
    except Exception as e:
        print(f'[ERROR] 获取板块数据失败: {e}')
        return None

def update_industry_data():
    """
    更新 comprehensive_stock_data.json 中的行业信息
    """
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'TradingShared', 'data')
    comp_file = os.path.join(data_dir, 'comprehensive_stock_data.json')
    
    print('='*70)
    print('开始修复行业信息...')
    print('='*70)
    
    # 读取现有数据
    with open(comp_file, 'r', encoding='utf-8') as f:
        comp_data = json.load(f)
    
    if 'stocks' not in comp_data:
        print('[ERROR] 数据结构错误')
        return
    
    stocks = comp_data['stocks']
    total = len(stocks)
    
    print(f'\n总股票数: {total}')
    
    # 获取板块涨幅数据
    print('\n正在获取板块涨幅数据...')
    sector_changes = get_sector_ranking()
    
    if not sector_changes:
        print('[WARN] 使用默认板块数据')
        sector_changes = {
            '半导体': 8.0, '人工智能': 8.5, '机器人': 8.0,
            '新能源汽车': 7.5, '光伏': 6.5, '医药': 6.0
        }
    
    # 更新每只股票的行业信息
    updated = 0
    failed = 0
    
    for i, (code, stock) in enumerate(stocks.items(), 1):
        if i % 10 == 0 or i == 1:
            print(f'\n进度: {i}/{total} ({i/total*100:.1f}%)')
        
        # 获取真实行业
        real_industry = get_industry_from_akshare(code)
        
        if real_industry:
            # 更新 basic_info.industry
            if 'basic_info' not in stock:
                stock['basic_info'] = {}
            stock['basic_info']['industry'] = real_industry
            
            # 更新 industry_concept
            if 'industry_concept' not in stock:
                stock['industry_concept'] = {}
            stock['industry_concept']['industry'] = real_industry
            
            updated += 1
            if i <= 10:
                print(f'  {code} -> {real_industry}')
        else:
            failed += 1
    
    print(f'\n\n更新完成！')
    print(f'  成功: {updated} 只')
    print(f'  失败: {failed} 只')
    
    # 保存更新后的数据
    backup_file = comp_file + '.backup'
    os.rename(comp_file, backup_file)
    print(f'\n已备份原文件到: {os.path.basename(backup_file)}')
    
    with open(comp_file, 'w', encoding='utf-8') as f:
        json.dump(comp_data, f, ensure_ascii=False, indent=2)
    
    print(f'\n✅ 已保存更新后的数据到: {os.path.basename(comp_file)}')
    
    # 保存板块涨幅数据
    sector_file = os.path.join(data_dir, 'sector_changes_3d.json')
    with open(sector_file, 'w', encoding='utf-8') as f:
        json.dump(sector_changes, f, ensure_ascii=False, indent=2)
    
    print(f'✅ 已保存板块涨幅数据到: {os.path.basename(sector_file)}')

if __name__ == '__main__':
    update_industry_data()
