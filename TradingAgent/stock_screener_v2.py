#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票筛选器 V2 — 参照 Anthropic Financial Services 思路重构
三层过滤 + 投资论点评估

核心理念（来自 thesis-tracker 思路）：
- 每只股票不是一个分数，而是一个"投资论点"
- 论点 = 核心驱动 + 催化剂 + 风险点
- 选股 = 验证论点是否成立，而非堆砌技术指标

三层过滤架构：
第一层 [硬过滤] - 市场状态 → 板块轮动
  → 只有热点板块内的股票才进入候选池
  
第二层 [硬过滤] - 资金流向
  → 没有主力资金净流入的股票直接淘汰
  
第三层 [评分] - 投资论点评估
  → 趋势确认 + 量价配合 + 催化剂事件 + 风险点检查

作者: TradingAgent 重构版
日期: 2026-05-17
"""

import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# 禁用代理
for _k in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'NO_PROXY']:
    os.environ.pop(_k, None)
os.environ['NO_PROXY'] = '*'

# 添加路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'TradingShared'))
try:
    from config import MAX_MARKET_CAP
except ImportError:
    MAX_MARKET_CAP = 100e8


# ═══════════════════════════════════════════════════════════
# 第一层：市场状态判断
# ═══════════════════════════════════════════════════════════

def detect_market_regime() -> Tuple[str, float, int]:
    """
    判断市场状态
    
    Returns:
        (regime, confidence, risk_level)
        regime: 'strong_bull' | 'bull' | 'range' | 'bear' | 'crisis'
        confidence: 0.0 ~ 1.0
        risk_level: 1 ~ 5
    """
    try:
        from market_state import detect_market_state
        state = detect_market_state()
        regime = state.get('regime', 'range')
        confidence = state.get('confidence', 0.5)
        risk = state.get('risk_level', 3)
        logger.info(f"市场状态: {regime}, 置信度: {confidence:.1%}, 风险等级: {risk}")
        return regime, confidence, risk
    except Exception as e:
        logger.warning(f"市场状态检测失败: {e}, 默认震荡市")
        return 'range', 0.5, 3


# ═══════════════════════════════════════════════════════════
# 第二层：板块轮动识别（核心新增）
# ═══════════════════════════════════════════════════════════

class SectorRotator:
    """
    板块轮动识别器
    
    核心逻辑：
    - 计算每个板块的"综合热度分"
    - 找出当前热点板块 + 新兴热点 + 冷却板块
    - 只有热点/新兴板块的股票才进入候选池
    """
    
    def __init__(self):
        self.sector_cache_dir = os.path.join(
            os.path.dirname(__file__), 'sector_cache'
        )
        self._cache = {}
        
    def get_hot_sectors(self, top_n: int = 10) -> List[Tuple[str, float]]:
        """
        获取当前最热的N个板块
        
        Returns:
            [(板块名, 热度分), ...]
        """
        try:
            from hot_sector_tracker import HotSectorTracker
            tracker = HotSectorTracker(cache_ttl=1800)
            # 调用实际存在的方法 get_hot_sectors
            sectors = tracker.get_hot_sectors(top_n=top_n)
            
            if not sectors:
                logger.warning("板块数据为空，使用默认板块")
                return self._get_default_hot_sectors()
            
            # 转换为 (name, score) 格式
            result = []
            for s in sectors:
                name = s.get('name', s.get('sector', '未知'))
                score = s.get('heat_score', s.get('total_score', 5.0))
                result.append((name, score))
            
            logger.info(f"热点板块: {[n for n,s in result[:5]]}")
            return result
            
        except Exception as e:
            logger.warning(f"板块追踪失败: {e}, 使用默认热点")
            return self._get_default_hot_sectors()
    
    def _get_default_hot_sectors(self) -> List[Tuple[str, float]]:
        """默认热点板块（当无法获取真实数据时）"""
        defaults = [
            ('人工智能', 7.5), ('半导体', 7.5), ('芯片', 7.0),
            ('新能源', 6.5), ('光伏', 6.0), ('军工', 6.0),
            ('医疗器械', 5.5), ('新能源汽车', 5.5),
        ]
        logger.info(f"使用默认热点板块: {[n for n,s in defaults]}")
        return defaults
    
    def is_in_hot_sector(self, stock: Dict, hot_sectors: List[Tuple[str, float]]) -> bool:
        """判断股票是否属于热点板块（放宽匹配）"""
        # 优先用 matched_sector
        matched = stock.get('matched_sector', '')
        industry = stock.get('industry', '')
        name = stock.get('name', '')
        
        # 收集所有可用的板块/行业标识
        tags = set()
        if matched and matched not in [None, 'None', '']:
            tags.add(matched)
        if industry and industry not in ['未知', '', '未分类', None]:
            tags.add(industry)
        
        # 从名称中提取行业关键词
        for kw in ['银行', '证券', '保险', '医药', '白酒', '新能源', '光伏', '芯片', 
                   '半导体', '人工智能', '军工', '钢铁', '煤炭', '化工', '地产', '汽车',
                   '软件', '通信', '电子', '环保', '传媒', '旅游', '食品', '家电']:
            if kw in name:
                tags.add(kw)
        
        # 与热点板块匹配
        for tag in tags:
            if not tag:
                continue
            for sector_name, _ in hot_sectors:
                # 完全包含
                if sector_name in tag or tag in sector_name:
                    return True
                # 去掉"板块"后缀的模糊匹配
                clean_sector = sector_name.replace('板块', '').replace('行业', '')
                if clean_sector in tag or tag in clean_sector:
                    return True
                # 关键词匹配（半导体/芯片互通、AI/人工智能互通）
                synonyms = {
                    'AI': ['人工智能'], '人工智能': ['AI'],
                    '芯片': ['半导体', '集成电路'], '半导体': ['芯片', '集成电路'],
                    '新能源': ['锂电池', '储能'], '新能源汽车': ['新能源', '锂电池'],
                }
                for kw, syns in synonyms.items():
                    if kw in sector_name and any(s in tag for s in syns):
                        return True
        
        return False


# ═══════════════════════════════════════════════════════════
# 第三层：资金流向过滤（硬过滤，不是加分项）
# ═══════════════════════════════════════════════════════════

class MoneyFlowFilter:
    """
    资金流向过滤器
    
    关键原则：
    - 资金流向是硬过滤条件，不是加分项
    - 没有主力资金净流入的股票直接淘汰
    - 配合放量上涨形态才有效
    """
    
    def __init__(self):
        self._flow_cache = {}
        
    def check_money_flow(self, stock_code: str, kline_data: List[Dict], 
                     in_hot_sector: bool = True) -> Tuple[bool, float]:
        """
        检查资金流向是否合格
        
        Args:
            stock_code: 股票代码
            kline_data: K线数据列表
            in_hot_sector: 是否在热点板块（在热点板块则放宽过滤）
            
        Returns:
            (passed, score)
            passed: 是否通过资金流向过滤
            score: 资金流向评分 0-10
            
        核心逻辑：
        - 热点板块股票：只要不是明显出货形态，都可以通过
        - 非热点板块：必须有明确资金流入信号
        """
        if not kline_data or len(kline_data) < 10:
            return in_hot_sector, 0.0
        
        try:
            # 计算近5日资金流向
            recent = kline_data[-5:]
            prev = kline_data[-10:-5] if len(kline_data) >= 10 else kline_data[-5:]
            
            # 1. 计算量价关系
            closes = [float(d.get('close', 0)) for d in recent]
            opens = [float(d.get('open', 0)) for d in recent]
            volumes = [float(d.get('volume', 0)) for d in recent]
            
            up_days = sum(1 for i in range(5) if closes[i] > opens[i])
            up_ratio = up_days / len(recent)  # 上涨日占比
            price_change = (closes[-1] - closes[0]) / max(closes[0], 1) * 100
            
            # 2. 计算成交量变化
            vol_now = sum(volumes)
            vol_prev = sum(float(d.get('volume', 0)) for d in prev) if prev else vol_now
            vol_ratio = vol_now / max(vol_prev, 1)
            
            # 3. 评分（0-10）
            score = 5.0
            
            # 放量上涨 = 好（最高加分）
            if vol_ratio > 1.5 and price_change > 0:
                score += 2.0
            if vol_ratio > 2.0 and price_change > 2:
                score += 1.5
            if vol_ratio > 2.5 and price_change > 3:
                score += 1.0
            
            # 缩量下跌 = 好（可能是主力吸筹）
            if vol_ratio < 0.8 and price_change < -2:
                score += 1.5
            if vol_ratio < 0.6 and price_change < -3:
                score += 1.0
            
            # 温和放量 + 小幅下跌（正常回调，可以接受）
            if 0.7 < vol_ratio < 1.3 and -3 < price_change < 0:
                score += 0.5
            
            # 放量下跌 = 坏（主力出货）
            if vol_ratio > 1.5 and price_change < -3:
                score -= 3.0
            elif vol_ratio > 1.3 and price_change < -5:
                score -= 2.0
            
            # 缩量上涨 = 中性（可能是小庄控盘）
            if vol_ratio < 0.8 and price_change > 2:
                score += 0.0  # 不加分不扣分
            
            score = max(0.0, min(10.0, score))
            
            # 4. 硬过滤条件（更宽松）
            if in_hot_sector:
                # 热点板块：只有放量出货是硬排除
                passed = not (vol_ratio > 1.5 and price_change < -3)
            else:
                # 非热点板块：需要有明确资金流入
                passed = (up_ratio >= 0.6 or price_change > 0) and not (vol_ratio > 1.3 and price_change < -3)
            
            return passed, score
            
        except Exception as e:
            logger.debug(f"资金流向分析失败 {stock_code}: {e}")
            return in_hot_sector, 5.0
    
    def get_sector_fund_flow(self, sector_name: str) -> Tuple[bool, float]:
        """
        获取板块资金流向（简化版）
        """
        try:
            from hot_sector_tracker import HotSectorTracker
            tracker = HotSectorTracker()
            sector_data = tracker.get_sector_detail(sector_name)
            
            if sector_data:
                fund_flow = sector_data.get('fund_flow', 0)
                # 资金净流入 = True
                passed = fund_flow > 0
                score = min(10.0, max(0.0, 5.0 + fund_flow / 1e8))
                return passed, score
        except Exception:
            pass
        
        # Fallback: 默认有资金
        return True, 5.0


# ═══════════════════════════════════════════════════════════
# 第四层：投资论点评估
# ═══════════════════════════════════════════════════════════

class ThesisEvaluator:
    """
    投资论点评估器（核心创新）
    
    参照 Anthropic thesis-tracker 的思路：
    - 每只股票 = 一个投资论点
    - 论点 = 核心驱动 + 催化剂 + 风险点 + 验证结果
    
    评估维度（只有5个核心指标，拒绝堆砌）：
    1. 趋势确认（周线/日线多周期）
    2. 量价配合（放量上涨形态）
    3. 板块协同（与热点板块共振）
    4. 催化剂存在（业绩/政策/事件）
    5. 风险可控（无明显利空）
    """
    
    def evaluate(self, stock: Dict, kline_data: List[Dict], 
                 hot_sectors: List[Tuple[str, float]]) -> Dict:
        """
        评估股票的投资论点质量
        
        Args:
            stock: 股票基本信息
            kline_data: K线数据
            hot_sectors: 热点板块列表
            
        Returns:
            {
                'passed': bool,           # 论点是否成立
                'total_score': float,     # 总分 0-10
                'trend_score': float,     # 趋势分
                'momentum_score': float,  # 动量分
                'sector_score': float,    # 板块分
                'catalyst_score': float,  # 催化剂分
                'risk_score': float,      # 风险分
                'thesis': str,            # 论点描述
                'risks': List[str],       # 风险点
            }
        """
        result = {
            'passed': False,
            'total_score': 0.0,
            'trend_score': 0.0,
            'momentum_score': 0.0,
            'sector_score': 0.0,
            'catalyst_score': 0.0,
            'risk_score': 0.0,
            'thesis': '',
            'risks': [],
        }
        
        if not kline_data or len(kline_data) < 20:
            return result
        
        try:
            closes = [float(d.get('close', 0)) for d in kline_data]
            volumes = [float(d.get('volume', 0)) for d in kline_data]
            highs = [float(d.get('high', 0)) for d in kline_data]
            lows = [float(d.get('low', 0)) for d in kline_data]
            opens = [float(d.get('open', 0)) for d in kline_data]
            
            n = len(closes)
            
            # ─────────────────────────────────────────
            # 1. 趋势确认（权重40%）
            # ─────────────────────────────────────────
            trend_score = self._calc_trend_score(closes, n)
            result['trend_score'] = trend_score
            
            # ─────────────────────────────────────────
            # 2. 量价配合（权重30%）
            # ─────────────────────────────────────────
            momentum_score = self._calc_momentum_score(closes, volumes, opens, n)
            result['momentum_score'] = momentum_score
            
            # ─────────────────────────────────────────
            # 3. 板块协同（权重15%）
            # ─────────────────────────────────────────
            sector_score = self._calc_sector_score(stock, hot_sectors, kline_data)
            result['sector_score'] = sector_score
            
            # ─────────────────────────────────────────
            # 4. 催化剂（权重10%）
            # ─────────────────────────────────────────
            catalyst_score = self._calc_catalyst_score(stock, kline_data)
            result['catalyst_score'] = catalyst_score
            
            # ─────────────────────────────────────────
            # 5. 风险评估（权重5%）
            # ─────────────────────────────────────────
            risk_score, risks = self._calc_risk_score(stock, closes, volumes, n)
            result['risk_score'] = risk_score
            result['risks'] = risks
            
            # ─────────────────────────────────────────
            # 综合评分（含已有评分数据加成）
            # ─────────────────────────────────────────
            total = (
                trend_score * 0.40 +
                momentum_score * 0.30 +
                sector_score * 0.15 +
                catalyst_score * 0.10 +
                risk_score * 0.05
            )
            
            # 叠加已有评分数据（使用原始数据增强）
            short_score = stock.get('short_term_score', 5.0)
            chip_score = stock.get('chip_score', 5.0)
            long_score = stock.get('long_term_score', 5.0)
            
            if short_score > 5.0:
                total += (short_score - 5.0) * 0.05  # 技术面好加分
            if chip_score > 5.0:
                total += (chip_score - 5.0) * 0.03  # 筹码好加分
            if long_score > 5.0:
                total += (long_score - 5.0) * 0.02  # 基本面好加分
            if 'hot_sector_score' in stock and stock['hot_sector_score'] > 5.0:
                total += (stock['hot_sector_score'] - 5.0) * 0.05  # 板块热度加分
            
            result['total_score'] = round(total, 2)
            
# 论点是否成立：总分>=5.0 且趋势分>=4.0
            # 热点板块股票：放宽要求，因为有板块共振保护
            result['passed'] = total >= 5.0 and trend_score >= 4.0
            
            # 如果原有评分数据好，额外放宽
            short_score = stock.get('short_term_score', 5.0)
            if short_score >= 7.0:
                result['passed'] = result['passed'] or (total >= 4.5 and trend_score >= 3.5)
            
            # 生成论点描述
            result['thesis'] = self._generate_thesis(stock, result)
            
        except Exception as e:
            logger.debug(f"论点评估失败 {stock.get('code')}: {e}")
            
        return result
    
    def _calc_trend_score(self, closes: List[float], n: int) -> float:
        """计算趋势评分（多周期确认）"""
        score = 5.0  # 基准
        
        if n < 20:
            return score
        
        # 日线MA
        ma5 = sum(closes[-5:]) / 5
        ma10 = sum(closes[-10:]) / 10
        ma20 = sum(closes[-20:]) / 20
        
        # 多头排列加分
        if closes[-1] > ma5 > ma10 > ma20:
            score += 2.0
        elif closes[-1] > ma5 > ma10:
            score += 1.0
        elif closes[-1] < ma5 < ma10 < ma20:
            score -= 2.0
            
        # 均线向上发散
        if ma5 > closes[-6] if n >= 6 else False:
            score += 0.5
        if ma10 > sum(closes[-11:-1]) / 10 if n >= 11 else False:
            score += 0.5
            
        # 周线趋势（简化：用日线数据估算）
        if n >= 60:
            weekly_closes = closes[::5][:12]  # 约12周
            if len(weekly_closes) >= 4:
                wma4 = sum(weekly_closes[-4:]) / 4
                if weekly_closes[-1] > wma4:
                    score += 1.0
                elif weekly_closes[-1] < wma4:
                    score -= 1.0
        
        return max(0.0, min(10.0, score))
    
    def _calc_momentum_score(self, closes: List[float], volumes: List[float],
                             opens: List[float], n: int) -> float:
        """计算量价配合评分"""
        score = 5.0
        
        if n < 10:
            return score
        
        # 近5日分析
        recent_closes = closes[-5:]
        recent_volumes = volumes[-5:]
        recent_opens = opens[-5:]
        
        # 1. 放量上涨天数
        up_days = sum(1 for i in range(5) 
                     if recent_closes[i] > recent_opens[i])
        up_ratio = up_days / 5
        
        if up_ratio >= 0.8:
            score += 2.0
        elif up_ratio >= 0.6:
            score += 1.0
        elif up_ratio <= 0.2:
            score -= 1.5
        
        # 2. 量价配合：涨时放量，跌时缩量
        vol_ratio = sum(recent_volumes) / max(sum(volumes[-10:-5]), 1)
        
        # 统计上涨日和下跌日的平均成交量
        up_vols = [recent_volumes[i] for i in range(5) 
                   if recent_closes[i] > recent_opens[i]]
        dn_vols = [recent_volumes[i] for i in range(5) 
                   if recent_closes[i] <= recent_opens[i]]
        
        if up_vols and dn_vols:
            vol_up_ratio = sum(up_vols) / max(sum(dn_vols), 1)
            if vol_up_ratio > 1.5:
                score += 1.5
            elif vol_up_ratio < 0.7:
                score -= 1.0
        
        # 3. 近5日涨幅
        gain_5d = (closes[-1] - closes[-6]) / max(closes[-6], 1) * 100 if n >= 6 else 0
        if 2 < gain_5d < 15:
            score += 1.0
        elif gain_5d >= 15:
            score -= 0.5  # 涨幅过大，追高风险
        elif gain_5d < -5:
            score -= 1.0
        
        return max(0.0, min(10.0, score))
    
    def _calc_sector_score(self, stock: Dict, hot_sectors: List[Tuple[str, float]],
                          kline_data: List[Dict]) -> float:
        """计算板块协同评分"""
        score = 5.0
        
        industry = stock.get('industry', '')
        matched = stock.get('matched_sector', '')
        name = stock.get('name', '')
        
        # 检查是否在热点板块
        in_hot = False
        best_heat = 0.0
        for sector_name, heat in hot_sectors:
            # 完全匹配
            if sector_name == industry or sector_name == matched:
                in_hot = True
                best_heat = max(best_heat, heat)
            # 模糊匹配
            elif sector_name in industry or industry in sector_name:
                in_hot = True
                best_heat = max(best_heat, heat)
            elif sector_name in name or name in sector_name:
                in_hot = True
                best_heat = max(best_heat, heat)
            # 同义词匹配
            synonyms = {
                'AI': ['人工智能'], '人工智能': ['AI'],
                '芯片': ['半导体'], '半导体': ['芯片'],
                '新能源': ['锂电池'], '新能源汽车': ['新能源'],
            }
            for kw, syns in synonyms.items():
                if kw in sector_name:
                    if any(s in industry or s in name for s in syns):
                        in_hot = True
                        best_heat = max(best_heat, heat)
        
        if in_hot:
            # 热点板块加分：热度越高，加分越多
            if best_heat > 7.0:
                score = 8.0  # 强烈热点
            elif best_heat > 6.5:
                score = 7.0  # 中等热点
            elif best_heat > 6.0:
                score = 6.5  # 一般热点
            else:
                score = 6.0  # 边缘热点
        else:
            score = 3.0  # 不在热点
        
        # 叠加已有的板块评分数据（如果存在）
        if 'hot_sector_score' in stock:
            existing = stock['hot_sector_score']
            if existing > 5.0:
                score = (score * 0.7 + existing)  # 混合
            elif existing < 5.0:
                score = score * 0.8 + existing * 0.2
        
        return max(0.0, min(10.0, score))
    
    def _calc_catalyst_score(self, stock: Dict, kline_data: List[Dict]) -> float:
        """计算催化剂评分"""
        score = 5.0
        
        # 简化版：检测是否有明显催化剂信号
        if len(kline_data) < 20:
            return score
        
        closes = [float(d.get('close', 0)) for d in kline_data]
        
        # 1. 突破前期高点
        recent_high = max(closes[-20:-1])
        if closes[-1] > recent_high * 0.98:
            score += 1.5  # 接近/突破前期高点
            
        # 2. 近1月有涨停（强烈催化剂）
        for d in kline_data[-20:]:
            change = float(d.get('change_pct', 0))
            if change >= 9.5:  # 接近涨停
                score += 1.0
                break
        
        # 3. 量能异动（可能有利好）
        if len(kline_data) >= 10:
            vol_recent = sum(float(d.get('volume', 0)) for d in kline_data[-5:])
            vol_prev = sum(float(d.get('volume', 0)) for d in kline_data[-10:-5])
            if vol_recent > vol_prev * 2:
                score += 0.5
        
        return max(0.0, min(10.0, score))
    
    def _calc_risk_score(self, stock: Dict, closes: List[float],
                        volumes: List[float], n: int) -> Tuple[float, List[str]]:
        """计算风险评分，返回(分数, 风险点列表)"""
        score = 10.0  # 风险分越高越好
        risks = []
        
        if n < 20:
            return score, risks
        
        # 1. 涨幅过大风险
        gain_20d = (closes[-1] - closes[-21]) / max(closes[-21], 1) * 100 if n >= 21 else 0
        if gain_20d > 40:
            score -= 2.0
            risks.append(f"近20日涨幅过大({gain_20d:.1f}%)")
        elif gain_20d > 30:
            score -= 1.0
            risks.append(f"近20日涨幅偏高({gain_20d:.1f}%)")
        
        # 2. 高位放量滞涨风险
        if n >= 10:
            recent_vol = sum(volumes[-5:]) / 5
            prev_vol = sum(volumes[-10:-5]) / 5
            gain_recent = (closes[-1] - closes[-6]) / max(closes[-6], 1) * 100 if n >= 6 else 0
            
            if recent_vol > prev_vol * 1.5 and abs(gain_recent) < 2:
                score -= 1.5
                risks.append("高位放量滞涨")
        
        # 3. ST风险
        if 'ST' in stock.get('name', '').upper():
            score -= 3.0
            risks.append("ST股票")
        
        # 4. 市值风险
        mcap = stock.get('market_cap_raw', 0)
        if mcap > 200e8:  # >200亿
            score -= 1.0
            risks.append("市值偏大")
        elif mcap > 500e8:
            score -= 2.0
            risks.append("市值过大")
        
        return max(0.0, min(10.0, score)), risks
    
    def _generate_thesis(self, stock: Dict, result: Dict) -> str:
        """生成投资论点描述"""
        code = stock.get('code', '')
        name = stock.get('name', code)
        
        parts = []
        
        # 趋势论点
        trend = result['trend_score']
        if trend >= 7:
            parts.append("周线、日线多头排列，趋势向好")
        elif trend >= 5:
            parts.append("短期趋势向上")
        
        # 量价论点
        momentum = result['momentum_score']
        if momentum >= 7:
            parts.append("量价配合健康，主力资金积极介入")
        elif momentum >= 5:
            parts.append("量价配合尚可")
        
        # 板块论点
        sector = result['sector_score']
        industry = stock.get('industry', '')
        if sector >= 7:
            parts.append(f"属于热点板块{industry}，有板块共振")
        elif sector >= 5:
            parts.append(f"所在{industry}板块有机会")
        
        # 风险
        risks = result['risks']
        if risks:
            parts.append(f"注意：{'/'.join(risks)}")
        
        return f"{name}({code}): " + "；".join(parts) if parts else f"{name}({code}): 综合评分{result['total_score']:.1f}"


# ═══════════════════════════════════════════════════════════
# 主筛选器类
# ═══════════════════════════════════════════════════════════

class StockScreenerV2:
    """
    股票筛选器 V2
    
    三层过滤流程：
    1. 市场状态 → 决定是否交易、交易多少
    2. 板块轮动 → 只有热点板块的股票进入候选
    3. 资金流向 → 硬过滤，无资金流入的股票淘汰
    4. 论点评估 → 最终评分和筛选
    
    特点：
    - 硬过滤 + 软评分，不是所有指标都平等
    - 拒绝40+参数的Optuna优化
    - 每只股评估为一个"投资论点"
    """
    
    def __init__(self, risk_level: int = None):
        self.data_dir = os.path.join(
            os.path.dirname(__file__), '..', 'TradingShared', 'data'
        )
        
        # 子组件
        self.sector_rotator = SectorRotator()
        self.money_flow = MoneyFlowFilter()
        self.thesis_evaluator = ThesisEvaluator()
        
        # 市场状态
        self.regime = 'range'
        self.confidence = 0.5
        self.risk_level = risk_level or 3
        
        # 热点板块
        self.hot_sectors = []
        
        # K线数据
        self._kline_cache = {}
        self._stock_scores = {}
        
    def screen(self, top_n: int = 50) -> List[Dict]:
        """
        主筛选方法
        
        Args:
            top_n: 最多返回N只股票
            
        Returns:
            筛选通过的股票列表，按综合评分排序
        """
        logger.info("=" * 60)
        logger.info("开始 V2 筛选流程")
        logger.info("=" * 60)
        
        # ─────────────────────────────────────────
        # 第一步：判断市场状态
        # ─────────────────────────────────────────
        self.regime, self.confidence, self.risk_level = detect_market_regime()
        
        # 熊市/危机：减少推荐或停止
        if self.risk_level >= 5:
            logger.warning("危机模式，停止推荐")
            return []
        if self.risk_level == 4 and self.confidence > 0.6:
            max_stocks = 1  # 熊市最多1只
        elif self.risk_level <= 2:
            max_stocks = min(3, top_n)  # 牛市可多推
        else:
            max_stocks = min(2, top_n)  # 震荡市2只
        top_n = min(top_n, max_stocks)
        
        # ─────────────────────────────────────────
        # 第二步：获取热点板块
        # ─────────────────────────────────────────
        logger.info("获取热点板块...")
        self.hot_sectors = self.sector_rotator.get_hot_sectors(top_n=10)
        
        if not self.hot_sectors:
            logger.warning("未获取到热点板块，使用默认")
            self.hot_sectors = self.sector_rotator._get_default_hot_sectors()
        
        # ─────────────────────────────────────────
        # 第三步：加载候选股票
        # ─────────────────────────────────────────
        self._load_stock_data()
        candidates = list(self._stock_scores.keys())
        logger.info(f"候选股票: {len(candidates)} 只")
        
        # ─────────────────────────────────────────
        # 第四步：三层过滤
        # ─────────────────────────────────────────
        results = []
        stats = {
            'total': len(candidates),
            'sector_fail': 0,
            'fund_flow_fail': 0,
            'thesis_fail': 0,
            'passed': 0,
        }
        
        for code in candidates:
            stock = self._stock_scores[code]
            stock['code'] = code
            
            # 跳过ST
            if 'ST' in stock.get('name', '').upper():
                continue
            
            # ── Layer 1: 板块过滤 ──
            if not self.sector_rotator.is_in_hot_sector(stock, self.hot_sectors):
                stats['sector_fail'] += 1
                continue
            
            # ── Layer 2: 资金流向过滤 ──
            in_hot = True  # 已经通过Layer1，说明在热点板块
            kline_data = self._load_kline(code)
            fund_passed, fund_score = self.money_flow.check_money_flow(code, kline_data, in_hot)
            stock['fund_score'] = fund_score
            
            if not fund_passed:
                stats['fund_flow_fail'] += 1
                continue
            
            # ── Layer 3: 论点评估 ──
            thesis_result = self.thesis_evaluator.evaluate(stock, kline_data, self.hot_sectors)
            stock.update(thesis_result)
            
            if not thesis_result['passed']:
                stats['thesis_fail'] += 1
                continue
            
            stats['passed'] += 1
            results.append(stock)
        
        # ─────────────────────────────────────────
        # 第五步：排序输出
        # ─────────────────────────────────────────
        results.sort(key=lambda x: x['total_score'], reverse=True)
        
        # 打印统计
        logger.info("=" * 60)
        logger.info("V2 筛选完成")
        logger.info(f"原始候选: {stats['total']}")
        logger.info(f"板块过滤失败: {stats['sector_fail']}")
        logger.info(f"资金过滤失败: {stats['fund_flow_fail']}")
        logger.info(f"论点评估失败: {stats['thesis_fail']}")
        logger.info(f"最终通过: {stats['passed']}")
        logger.info(f"市场状态: {self.regime}, 推荐数量: {len(results[:top_n])}")
        logger.info("=" * 60)
        
        return results[:top_n]
    
    def _load_stock_data(self) -> Dict:
        """加载评分数据"""
        score_files = [
            f for f in os.listdir(self.data_dir)
            if f.startswith('batch_stock_scores_optimized_主板_') and f.endswith('.json')
        ]
        
        if score_files:
            latest_file = max(score_files)
            file_path = os.path.join(self.data_dir, latest_file)
        else:
            file_path = os.path.join(self.data_dir, 'batch_stock_scores_none.json')
            if not os.path.exists(file_path):
                file_path = os.path.join(self.data_dir, 'batch_stock_scores.json')
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            
            self._stock_scores = {
                k: v for k, v in raw_data.items()
                if isinstance(v, dict) and ('short_term_score' in v or 'name' in v)
            }
            logger.info(f"加载 {len(self._stock_scores)} 只股票评分")
        except Exception as e:
            logger.error(f"加载评分失败: {e}")
            self._stock_scores = {}
    
    def _load_kline(self, code: str) -> List[Dict]:
        """加载K线数据"""
        if code in self._kline_cache:
            return self._kline_cache[code]
        
        try:
            # 尝试从合并文件加载
            kline_dir = os.path.join(
                os.path.dirname(__file__), '..', 'TradingShared', 'data', 'kline_cache'
            )
            kline_file = os.path.join(kline_dir, 'kline_full_latest.json')
            
            if os.path.exists(kline_file):
                with open(kline_file, 'r', encoding='utf-8') as f:
                    kline_full = json.load(f)
                
                actual_key = code
                if code not in kline_full:
                    if code.startswith(('6', '9')):
                        actual_key = f'sh{code}'
                    else:
                        actual_key = f'sz{code}'
                
                if actual_key in kline_full:
                    data = kline_full[actual_key]
                    if isinstance(data, list):
                        self._kline_cache[code] = data
                        return data
        except Exception as e:
            logger.debug(f"加载K线失败 {code}: {e}")
        
        return []


# ═══════════════════════════════════════════════════════════
# 兼容旧接口
# ═══════════════════════════════════════════════════════════

def screen_v2(n: int = 10) -> List[Dict]:
    """快速筛选接口"""
    screener = StockScreenerV2()
    return screener.screen(top_n=n)


if __name__ == '__main__':
    print("运行 V2 筛选器测试...")
    screener = StockScreenerV2()
    results = screener.screen(top_n=10)
    
    print(f"\n推荐 {len(results)} 只股票:")
    print("-" * 100)
    for i, stock in enumerate(results, 1):
        print(f"{i:2}. {stock.get('code')} {stock.get('name', '未知'):8}")
        print(f"    评分: {stock.get('total_score', 0):.2f} | " + 
              f"趋势:{stock.get('trend_score', 0):.1f} " +
              f"动量:{stock.get('momentum_score', 0):.1f} " +
              f"板块:{stock.get('sector_score', 0):.1f} " +
              f"催化:{stock.get('catalyst_score', 0):.1f}")
        print(f"    论点: {stock.get('thesis', '')}")
        if stock.get('risks'):
            print(f"    风险: {'/'.join(stock['risks'])}")
        print()