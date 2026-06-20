#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查dryrun推荐名称"""
import json, glob, os

files = sorted(glob.glob(r'D:\GitHub\TradingAgents\TradingAgent\recommendation_history\v28_recommendation_*_dryrun.json'), reverse=True)
for f in files[:5]:
    with open(f, 'r', encoding='utf-8') as fh:
        d = json.load(fh)
    date = d.get('date', '?')
    recs = d.get('recommendations', [])
    names_empty = sum(1 for r in recs if not r.get('name'))
    print(f"\n{date}: {len(recs)}只, 空名={names_empty}")
    for r in recs:
        print(f"  {r.get('code','')} \"{r.get('name','')}\" ind={r.get('industry','')} score={r.get('final_score',0)}")
    
    # 看top10 debug
    debug = d.get('top_10_debug', [])
    if debug:
        empty_in_debug = sum(1 for s in debug if not s.get('name'))
        print(f"  Top10 debug空名: {empty_in_debug}/10")
