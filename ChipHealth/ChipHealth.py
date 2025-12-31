@staticmethod
    def run_strategy(daily_data, mode="TREND"):
        # 1. 数据清洗与排序 (保持不变)
        clean_data = []
        for d in daily_data:
            dt = ChipAlgorithmV4.parse_date(d.get('date'))
            if dt and d.get('volume') and d.get('close'):
                d['_dt'] = dt
                clean_data.append(d)
        clean_data.sort(key=lambda x: x['_dt'])
        
        if len(clean_data) < 30: return None
        
        # 2. 计算核心指标 (保持不变)
        current_price = clean_data[-1]['close']
        sim_data = clean_data[-120:]
        buckets = ChipAlgorithmV4.calc_iterative_chip_distribution(sim_data, decay_factor=0.05)
        win_pct, scr, bias = ChipAlgorithmV4.analyze_chips(buckets, current_price)
        
        # 3. 评分逻辑 (升级版)
        result = {'win': round(win_pct, 1), 'scr': round(scr, 1), 'bias': round(bias, 1), 'score': 0, 'reason': ""}
        
        if mode == "TREND":
            # === [模式A：趋势跟随 V5.0] ===
            # 基础分：获利盘比例 (0-100)
            score = win_pct
            reasons = []

            # 修正1：乖离率风控 (重罚)
            if bias > 25:
                score *= 0.6  # 严重过热，打6折
                reasons.append("风险:严重超买")
            elif bias > 15:
                score *= 0.85 # 轻度过热
                reasons.append("警告:乖离偏大")
            
            # 修正2：SCR 奖励 (如果筹码没散，那是极品)
            if scr < 12 and win_pct > 90:
                score += 5     # 额外加分，突破100
                score = min(score, 100) # 封顶
                reasons.append("极品:锁仓拉升")
            elif scr > 40:
                # SCR太高说明筹码极度松动，即使获利盘高也不稳
                score *= 0.9
                reasons.append("提示:筹码松动")

            if not reasons:
                if win_pct > 95: reasons.append("主升浪:极强")
                elif win_pct > 80: reasons.append("趋势:强势")
                elif win_pct < 50: reasons.append("趋势:套牢")
            
            result['score'] = round(score, 1)
            result['reason'] = " | ".join(reasons)

        else:
            # === [模式B：低位潜伏 V5.0] (保持原样或微调) ===
            s = 0; reasons = []
            
            # 集中度 (核心)
            if scr < 10: s += 4; reasons.append("极度密集")
            elif scr < 15: s += 3.5; reasons.append("高度密集")
            elif scr < 20: s += 2
            else: reasons.append("筹码发散")
            
            # 获利盘 (要在启动初期)
            if 0 < win_pct < 20: s += 3; reasons.append("底部吸筹")
            elif 20 <= win_pct < 60: s += 2; reasons.append("蓄势待发") # 放宽一点范围
            elif win_pct > 85: reasons.append("高位风险") # 扣分
            
            # 乖离率 (要在成本附近)
            if abs(bias) <= 8: s += 3; reasons.append("紧贴成本")
            elif abs(bias) <= 15: s += 1.5
            
            result['score'] = s
            result['reason'] = " | ".join(reasons)
            
        return result