#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Real Feature Calculator — 方案A核心模块

用真实K线数据计算特征，替代 stock_screener 0-10分映射。

问题：推荐器用 stock_screener 的 0-10 评分估算回测特征（map_stock_to_subscores），
导致评分偏差巨大（回测86.2% vs 实盘25%）。

方案：直接调用 calc_features() + compute_stock_subscores() 逻辑，
用真实K线数据计算 RSI、MA偏离度、连涨天数、波动率等特征，
与回测保持100%一致。

使用方法：
    from real_feature_calculator import RealFeatureCalculator
    calc = RealFeatureCalculator()
    subscores = calc.compute_real_subscores('000001')
"""

import json
import os
import sys
import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 路径配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'TradingShared', 'data')
KLINE_CACHE = os.path.join(DATA_DIR, 'kline_cache')

# 防御型/高Beta行业关键词（与回测一致）
DEFENSIVE_KEYWORDS = [
    '电力', '水务', '燃气', '公用', '银行', '医药', '食品', '饮料',
    '高速公路', '港口', '机场', '交通', '通信', '电信',
]
HIGH_BETA_KEYWORDS = [
    '半导体', '芯片', '新能源', '光伏', '锂电', '军工', '证券',
    '保险', '房地产', '钢铁', '煤炭', '有色',
]


def is_defensive_industry(industry: str) -> bool:
    return any(kw in industry for kw in DEFENSIVE_KEYWORDS)


def is_high_beta_industry(industry: str) -> bool:
    return any(kw in industry for kw in HIGH_BETA_KEYWORDS)


def normalize_code(code: str) -> str:
    """统一股票代码格式"""
    code = str(code).strip()
    if code.startswith('sh.') or code.startswith('sz.'):
        return code[3:]
    code = code.replace('.SZ', '').replace('.SH', '')
    if code.startswith('sh') or code.startswith('sz'):
        return code[2:]
    return code


# ============================================================================
# 特征计算（直接从 backtest_v19_sector.py 移植，保持100%一致）
# ============================================================================
def calc_features(df, target_date):
    """计算K线特征 — 与回测完全一致"""
    hist = df[df['date'] < target_date].copy()
    if len(hist) < 20:
        return None

    c = hist['close'].values
    v = hist['volume'].values
    h = hist['high'].values if 'high' in hist.columns else c
    lo = hist['low'].values if 'low' in hist.columns else c
    turn = hist['turn'].values if 'turn' in hist.columns else np.ones(len(c))
    pct = hist['pctChg'].values if 'pctChg' in hist.columns else np.zeros(len(c))

    n = len(c)
    f = {}

    f['r1'] = (c[-1] - c[-2]) / c[-2] * 100 if n >= 2 else 0
    f['r3'] = (c[-1] - c[-4]) / c[-4] * 100 if n >= 4 else 0
    f['r5'] = (c[-1] - c[-6]) / c[-6] * 100 if n >= 6 else 0
    f['r10'] = (c[-1] - c[-11]) / c[-11] * 100 if n >= 11 else 0
    f['r20'] = (c[-1] - c[-21]) / c[-21] * 100 if n >= 21 else 0

    ma5 = np.mean(c[-5:])
    ma10 = np.mean(c[-10:]) if n >= 10 else ma5
    ma20 = np.mean(c[-20:]) if n >= 20 else ma10

    f['close_ma5'] = c[-1] / ma5 - 1
    f['close_ma10'] = c[-1] / ma10 - 1
    f['close_ma20'] = c[-1] / ma20 - 1
    f['ma5_slope'] = (ma5 - np.mean(c[-6:-1])) / np.mean(c[-6:-1]) if n >= 6 else 0
    f['ma10_slope'] = (ma10 - np.mean(c[-11:-1])) / np.mean(c[-11:-1]) if n >= 11 else 0
    f['ma_bull'] = int(c[-1] > ma5 > ma10 > ma20)
    f['ma_align'] = int(ma5 > ma10) + int(ma5 > ma20) + int(ma10 > ma20)

    # RSI(14)
    w = min(14, n - 1)
    gains, losses = [], []
    for i in range(-w, 0):
        chg = (c[i] - c[i-1]) / c[i-1] * 100
        gains.append(max(chg, 0))
        losses.append(max(-chg, 0))
    ag = np.mean(gains)
    al = max(np.mean(losses), 0.01)
    f['rsi'] = 100 - 100 / (1 + ag / al)

    # MACD
    if n >= 26:
        ema12 = ema26 = c[-1]
        for i in range(-26, 0):
            ema12 = c[i] * (2/14) + ema12 * (1 - 2/14)
            ema26 = c[i] * (2/27) + ema26 * (1 - 2/27)
        f['macd'] = ema12 - ema26
    else:
        f['macd'] = 0

    # 波动率
    if n >= 6:
        rets = np.diff(c[-6:]) / c[-6:-1]
        f['vol5'] = np.std(rets) * 100
    else:
        f['vol5'] = 0
    if n >= 11:
        rets10 = np.diff(c[-11:]) / c[-11:-1]
        f['vol10'] = np.std(rets10) * 100
    else:
        f['vol10'] = f.get('vol5', 0)

    # 成交量比率
    if n >= 10 and np.mean(v[-10:]) > 0:
        f['vol_ratio'] = np.mean(v[-5:]) / np.mean(v[-10:])
    else:
        f['vol_ratio'] = 1.0

    # 成交量缩放
    if n >= 6:
        v5 = np.mean(v[-5:])
        v5_prev = np.mean(v[-10:-5]) if n >= 10 else v5
        f['vol_shrink'] = v5 / max(v5_prev, 1)
    else:
        f['vol_shrink'] = 1.0

    # 换手率异常
    if n >= 10 and not np.all(turn == 1):
        turn5 = np.nanmean(turn[-5:])
        turn10 = np.nanmean(turn[-10:])
        f['turn_spike'] = turn[-1] / max(turn5, 0.01)
    else:
        f['turn_spike'] = 1.0

    # 价格位置
    w20 = min(20, n)
    f['price_pos'] = (c[-1] - np.min(c[-w20:])) / max(np.max(c[-w20:]) - np.min(c[-w20:]), 0.01) * 100

    # 连涨/连跌天数
    streak = 0
    for i in range(n-1, 0, -1):
        if c[i] > c[i-1]:
            streak = streak + 1 if streak >= 0 else 1
        elif c[i] < c[i-1]:
            streak = streak - 1 if streak <= 0 else -1
        else:
            break
    f['streak'] = streak

    # 均值回归
    f['mr_5d'] = -f['r5']
    f['mr_3d'] = -f['r3']
    f['oversold'] = 1 if (f['rsi'] < 35 and f['r5'] < -3) else 0
    f['overbought'] = 1 if (f['rsi'] > 70 and f['r5'] > 5) else 0

    f['pct_1d'] = f['r1']

    # 最大回撤(10日)
    if n >= 10:
        peak = c[-10]
        max_dd = 0
        for i in range(-9, 1):
            if c[i] > peak:
                peak = c[i]
            dd = (c[i] - peak) / peak * 100
            if dd < max_dd:
                max_dd = dd
        f['max_dd_10d'] = max_dd
    else:
        f['max_dd_10d'] = 0

    f['beta_20d'] = 1.0
    f['rel_strength_5d'] = 0.0
    f['rel_strength_3d'] = 0.0

    # 连涨一致性
    f['consistency'] = 0
    if n >= 5:
        for i in range(-4, 0):
            if c[i+1] > c[i]:
                f['consistency'] += 1

    # === V22 新增特征（与 backtest_v22_honest.py 完全一致） ===

    # 1. Bollinger Band %B (布林带位置，0~1)
    if n >= 20:
        bb_mid = ma20
        bb_std = np.std(c[-20:])
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        bb_range = bb_upper - bb_lower
        f['bb_pctb'] = (c[-1] - bb_lower) / max(bb_range, 0.01)  # 0~1
        f['bb_upper_dist'] = (bb_upper - c[-1]) / c[-1] * 100
    else:
        f['bb_pctb'] = 0.5
        f['bb_upper_dist'] = 5.0

    # 2. ATR ratio (ATR14 / ATR28，与backtest一致)
    if n >= 28 and 'high' in df.columns:
        trs14 = []
        for i in range(-14, 0):
            tr = max(h[i] - lo[i], abs(h[i] - c[i-1]), abs(lo[i] - c[i-1]))
            trs14.append(tr)
        atr14 = np.mean(trs14)
        trs28 = []
        for i in range(-28, -14):
            tr = max(h[i] - lo[i], abs(h[i] - c[i-1]), abs(lo[i] - c[i-1]))
            trs28.append(tr)
        atr28 = np.mean(trs28)
        f['atr_ratio'] = atr14 / max(atr28, 0.01)
    else:
        f['atr_ratio'] = 1.0
    f['atr_14'] = atr14 / c[-1] * 100 if n >= 14 else 2.0

    # 3. 下跌日量比 (distribution indicator)
    if n >= 10:
        up_vols = [v[i] for i in range(-10, 0) if c[i] > c[i-1]]
        dn_vols = [v[i] for i in range(-10, 0) if c[i] <= c[i-1]]
        avg_up = np.mean(up_vols) if up_vols else 1
        avg_dn = np.mean(dn_vols) if dn_vols else 1
        f['down_vol_ratio'] = avg_dn / max(avg_up, 1)
    else:
        f['down_vol_ratio'] = 1.0

    # 4. 支撑位距离 (与backtest一致: 相对20日高低范围的位置)
    if n >= 20:
        low_20d = np.min(lo[-20:]) if 'low' in df.columns else np.min(c[-20:])
        high_20d = np.max(h[-20:]) if 'high' in df.columns else np.max(c[-20:])
        range_20d = high_20d - low_20d
        if range_20d > 0.01:
            f['support_dist'] = (c[-1] - low_20d) / range_20d
        else:
            f['support_dist'] = 0.5
    else:
        f['support_dist'] = 0.5
    f['support_touches'] = 0

    # 5. OBV acceleration (与backtest一致)
    if n >= 11:
        obv_first_half = 0
        obv_second_half = 0
        for i in range(-10, -5):
            if c[i] > c[i-1]: obv_first_half += v[i]
            elif c[i] < c[i-1]: obv_first_half -= v[i]
        for i in range(-5, 0):
            if c[i] > c[i-1]: obv_second_half += v[i]
            elif c[i] < c[i-1]: obv_second_half -= v[i]
        f['obv_accel'] = obv_second_half - obv_first_half
    else:
        f['obv_accel'] = 0
    f['obv_trend'] = 0.0  # legacy compat

    # 6. Volume-Price Confirmation (与backtest一致)
    if n >= 6:
        price_up = c[-1] > c[-2]
        vol_up = v[-1] > np.mean(v[-6:-1])
        f['vol_price_confirm'] = 1 if (price_up and vol_up) else 0
        f['vol_price_diverge'] = 1 if (price_up and not vol_up) else 0
    else:
        f['vol_price_confirm'] = 0
        f['vol_price_diverge'] = 0

    # 7. Momentum exhaustion (与backtest一致)
    if n >= 5:
        consec_up = 0
        vol_declining = True
        for i in range(-1, max(-6, -n), -1):
            if c[i] > c[i-1]:
                consec_up += 1
                if i > -n+1 and v[i] > v[i-1]:
                    vol_declining = False
            else:
                break
        f['exhaustion'] = 1 if (consec_up >= 3 and vol_declining) else 0
    else:
        f['exhaustion'] = 0

    return f


class RealFeatureCalculator:
    """真实特征计算器 — 用K线数据替代估算映射"""

    def __init__(self):
        self.kline = None      # {code: DataFrame}
        self.index_df = None   # 指数DataFrame
        self.scores = None     # 静态评分 {code: {tech, fund, chip, sector, name, industry}}
        self._loaded = False

    def load_data(self, codes=None):
        """加载K线、指数、静态评分数据
        
        Args:
            codes: 可选，只加载这些股票代码的K线（节省内存和时间）
        """
        if self._loaded:
            return True

        try:
            # 1. 加载K线
            self.kline = self._load_kline(codes=codes)
            if not self.kline:
                logger.error("K线数据加载失败")
                return False
            logger.info(f"K线数据加载成功: {len(self.kline)} 只股票")

            # 2. 加载指数
            self.index_df = self._load_index()
            if self.index_df is None:
                logger.warning("指数数据加载失败，Beta和相对强度将使用默认值")
            else:
                logger.info(f"指数数据加载成功: {len(self.index_df)} 天")

            # 3. 加载静态评分
            self.scores = self._load_scores()
            logger.info(f"静态评分加载成功: {len(self.scores)} 只股票")

            self._loaded = True
            return True

        except Exception as e:
            logger.error(f"数据加载失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _load_kline(self, codes=None):
        """加载K线数据
        
        Args:
            codes: 可选set/list，只加载这些股票代码
        """
        import glob

        # 尝试多个路径
        patterns = [
            os.path.join(KLINE_CACHE, 'kline_full_latest.json'),
            os.path.join(KLINE_CACHE, 'kline_latest.json'),
            os.path.join(KLINE_CACHE, 'kline_full_*.json'),
            os.path.join(KLINE_CACHE, 'kline_6m_*.json'),
        ]

        kline_file = None
        for pattern in patterns:
            files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
            if files:
                kline_file = files[0]
                break

        if kline_file is None:
            logger.error(f"未找到K线数据文件: {KLINE_CACHE}")
            return {}

        fsize = os.path.getsize(kline_file) / 1024 / 1024
        logger.info(f"加载K线: {os.path.basename(kline_file)} ({fsize:.1f}MB)")

        # 预处理codes集合
        code_set = None
        if codes:
            code_set = {normalize_code(c) for c in codes}

        # 如果指定了少量codes且文件大，尝试用ijson流式解析
        use_ijson = code_set and len(code_set) <= 100 and fsize > 10
        
        if use_ijson:
            try:
                import ijson
                logger.info(f"  使用ijson流式解析，目标{len(code_set)}只...")
                kline = {}
                found = 0
                with open(kline_file, 'rb') as f:
                    parser = ijson.kvitems(f, '')
                    for code, records in parser:
                        clean = normalize_code(code)
                        if clean not in code_set:
                            continue
                        if not records:
                            continue
                        df = pd.DataFrame(records)
                        df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
                        df = df.sort_values('date')
                        for col in ['open', 'high', 'low', 'close', 'volume', 'amount', 'turn', 'pctChg']:
                            if col in df.columns:
                                df[col] = pd.to_numeric(df[col], errors='coerce')
                        kline[clean] = df
                        found += 1
                        if found >= len(code_set):
                            break
                logger.info(f"  ijson加载: {found}/{len(code_set)} 只")
                return kline
            except ImportError:
                logger.info("  ijson不可用，使用标准加载")
            except Exception as e:
                logger.warning(f"  ijson加载失败({e})，使用标准加载")

        # 标准加载（全量读取后过滤）
        with open(kline_file, 'r', encoding='utf-8') as f:
            raw = json.load(f)

        kline = {}
        loaded = 0
        total = len(raw)
        for code, records in raw.items():
            clean = normalize_code(code)
            
            if code_set and clean not in code_set:
                continue
            
            if not records:
                continue
            
            # 只保留最近40条记录（够用且省内存）
            recent = records[-40:] if len(records) > 40 else records
            
            df = pd.DataFrame(recent)
            df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
            df = df.sort_values('date')
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount', 'turn', 'pctChg']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            kline[clean] = df
            loaded += 1

        if code_set:
            logger.info(f"选择性加载: {loaded}/{len(code_set)} 只目标股票")
        else:
            logger.info(f"全量加载: {loaded}/{total} 只股票")

        return kline

    def _load_index(self):
        """加载指数数据"""
        import glob

        patterns = [
            os.path.join(KLINE_CACHE, 'index_latest.json'),
            os.path.join(KLINE_CACHE, 'index_full_*.json'),
            os.path.join(KLINE_CACHE, 'index_6m_*.json'),
        ]

        index_file = None
        for pattern in patterns:
            files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
            if files:
                index_file = files[0]
                break

        if index_file is None:
            return None

        logger.info(f"加载指数: {os.path.basename(index_file)}")

        with open(index_file, 'r', encoding='utf-8') as f:
            raw_idx = json.load(f)

        n = len(raw_idx['date'])
        idx_records = []
        for i in range(n):
            key = str(i)
            try:
                ts = raw_idx['date'][key]
                ds = pd.Timestamp(ts, unit='ms').strftime('%Y-%m-%d') if isinstance(ts, (int, float)) else str(ts)
                idx_records.append({'date': ds, 'close': float(raw_idx['close'][key])})
            except:
                continue

        index_df = pd.DataFrame(idx_records)
        index_df['date'] = pd.to_datetime(index_df['date']).dt.tz_localize(None)
        index_df = index_df.dropna(subset=['close']).sort_values('date')

        return index_df

    def _load_scores(self):
        """加载静态评分（行业、名称等）"""
        import glob

        score_file = os.path.join(DATA_DIR, 'batch_stock_scores_2805.json')
        if not os.path.exists(score_file):
            all_sf = glob.glob(os.path.join(DATA_DIR, 'batch_stock_scores_*.json'))
            if all_sf:
                score_file = max(all_sf, key=lambda x: os.path.getsize(x))

        scores = {}
        if os.path.exists(score_file):
            with open(score_file, 'r', encoding='utf-8') as f:
                sd = json.load(f)
            for code, s in sd.items():
                if not isinstance(s, dict):
                    continue
                clean = normalize_code(code)
                scores[clean] = {
                    'tech': 5.0, 'fund': 5.0, 'chip': 5.0, 'sector': 5.0,
                    'name': s.get('name', ''),
                    'industry': s.get('industry', 'unknown'),
                    'sector_change': 0.0,
                }

        return scores

    def _get_index_info(self, target_date):
        """计算指数的20日收益率和5日/3日涨幅"""
        if self.index_df is None:
            return None, 0.0, 0.0

        idx_hist = self.index_df[self.index_df['date'] < target_date]
        closes = idx_hist['close'].values
        n = len(closes)

        if n < 22:
            return None, 0.0, 0.0

        # 20日收益率序列（用于计算Beta）
        idx_diff = np.diff(closes[-21:])
        idx_base = closes[-21:-1]
        idx_rets_20 = idx_diff[:len(idx_base)] / idx_base[:len(idx_diff)] * 100

        # 5日和3日涨幅
        idx_ret_5d = (closes[-1] - closes[-6]) / closes[-6] * 100 if n >= 6 else 0.0
        idx_ret_3d = (closes[-1] - closes[-4]) / closes[-4] * 100 if n >= 4 else 0.0

        return idx_rets_20, idx_ret_5d, idx_ret_3d

    def compute_real_subscores(self, code: str, target_date=None, 
                                stock_data: Dict = None) -> Optional[Dict]:
        """计算单只股票的真实子分数

        与回测的 compute_stock_subscores() 保持100%一致。

        Args:
            code: 股票代码（6位纯数字）
            target_date: 目标日期（默认今天）
            stock_data: 推荐器的stock dict（用于获取行业信息fallback）

        Returns:
            子分数dict，与 map_stock_to_subscores() 返回格式兼容
        """
        if not self._loaded:
            if not self.load_data():
                return None

        code = normalize_code(code)

        if target_date is None:
            target_date = pd.Timestamp.now().normalize()
        else:
            target_date = pd.Timestamp(target_date)

        # 获取K线数据
        df = self.kline.get(code)
        if df is None or len(df) < 20:
            logger.debug(f"  {code}: K线数据不足({len(df) if df is not None else 0}天)")
            return None

        # 计算特征
        feats = calc_features(df, target_date)
        if feats is None:
            return None

        # 涨停/跌停过滤
        if feats.get('pct_1d', 0) > 9.5 or feats.get('pct_1d', 0) < -9.5:
            logger.debug(f"  {code}: 涨停/跌停，跳过")
            return None

        # 计算Beta
        idx_rets_20, idx_ret_5d, idx_ret_3d = self._get_index_info(target_date)

        stock_hist = df[df['date'] < target_date]
        s_closes = stock_hist['close'].values
        s_n = len(s_closes)

        beta = 1.0
        if idx_rets_20 is not None and s_n >= 23:
            s_rets_20 = np.diff(s_closes[-21:]) / s_closes[-21:-1] * 100
            sr_len = min(len(s_rets_20), len(idx_rets_20))
            if sr_len >= 10:
                s_r = s_rets_20[-sr_len:]
                i_r = idx_rets_20[-sr_len:]
                idx_var = np.var(i_r)
                if idx_var > 0.001:
                    beta = np.cov(s_r, i_r)[0, 1] / idx_var

        # 相对强度
        rel_str = 0.0
        rel_str_3d = 0.0
        if s_n >= 6:
            rel_str = (s_closes[-1] - s_closes[-6]) / s_closes[-6] * 100 - idx_ret_5d
        if s_n >= 4:
            rel_str_3d = (s_closes[-1] - s_closes[-4]) / s_closes[-4] * 100 - idx_ret_3d

        feats['beta_20d'] = beta
        feats['rel_strength_5d'] = rel_str
        feats['rel_strength_3d'] = rel_str_3d

        # ---- 子分数计算（与回测完全一致） ----
        f = feats

        momentum_s = f['r1'] * 0.3 + f['r3'] * 0.3 + f['r5'] * 0.4
        trend_s = f['ma_align'] * 2.5 + f.get('ma5_slope', 0) * 50 + f.get('ma10_slope', 0) * 30
        mr_s = f['mr_5d'] * 0.5 + f['mr_3d'] * 0.3 + f.get('oversold', 0) * 5 - f.get('overbought', 0) * 5

        vr = f.get('vol_ratio', 1)
        if 1.1 <= vr <= 2.0:
            vol_s = 3.0
        elif vr > 2.0:
            vol_s = 1.0
        else:
            vol_s = 2.0

        rsi = f.get('rsi', 50)
        if 40 <= rsi <= 60:
            rsi_s = 3.0
        elif 30 <= rsi < 40:
            rsi_s = 4.0
        elif 60 < rsi <= 70:
            rsi_s = 2.0
        else:
            rsi_s = 1.0

        vol5 = f.get('vol5', 2)
        if vol5 < 1.5:
            low_vol_s = 4.0
        elif vol5 < 2.5:
            low_vol_s = 3.0
        elif vol5 < 3.5:
            low_vol_s = 2.0
        else:
            low_vol_s = 1.0

        # 获取行业信息
        static = self.scores.get(code, {})
        industry = static.get('industry', 'unknown') if static else 'unknown'
        # 推荐器stock_data中的行业可能更准确
        if stock_data and stock_data.get('industry', '未知') not in ('未知', 'unknown', ''):
            industry = stock_data.get('industry', industry)

        defense_base = 0.0
        is_def = is_defensive_industry(industry)
        is_hb = is_high_beta_industry(industry)
        if is_def:
            defense_base += 3.0
        if is_hb:
            defense_base -= 2.0

        max_dd = f.get('max_dd_10d', 0)
        dd_pen = -3.0 if max_dd < -15 else (-1.0 if max_dd < -10 else 0.0)
        defense_s = defense_base + low_vol_s + dd_pen

        # 板块热度（简化：推荐器环境没有daily_sector_avg）
        sector_heat = 0.0
        ind_heat = 0.0
        if stock_data:
            sector_change = stock_data.get('sector_change', 0.0)
            hot_sector = stock_data.get('hot_sector_score', 5.0)
            sector_heat = sector_change * 0.1
            if abs(sector_heat) < 0.01:
                sector_heat = (hot_sector - 5.0) * 0.3
            ind_heat = sector_change

        consistency = f.get('consistency', 0)
        consistency_s = consistency * 1.5

        # 静态评分
        static_score = 0.0
        if static:
            tech = max(static.get('tech', 5), 0)
            fund = max(static.get('fund', 5), 0)
            chip = max(static.get('chip', 5), 0)
            sec = max(static.get('sector', 5), 0)
            static_score = (tech * 0.30 + fund * 0.30 + chip * 0.25 + sec * 0.15) / 10 * 5
        elif stock_data:
            # 从推荐器数据估算
            tech = stock_data.get('short_term_score', 5.0)
            fund = stock_data.get('long_term_score', 5.0)
            chip = stock_data.get('chip_score', 5.0)
            sec = stock_data.get('hot_sector_score', 5.0)
            static_score = (tech * 0.30 + fund * 0.30 + chip * 0.25 + sec * 0.15) / 10 * 5

        beta_bonus = 2.0 - min(beta, 2.0)

        # === V22 NEW sub-scores（与backtest_v22_honest完全一致） ===

        # BB position score
        bb = f.get('bb_pctb', 0.5)
        if bb < 0.2: bb_s = 4.0
        elif bb < 0.4: bb_s = 3.0
        elif bb < 0.6: bb_s = 2.5
        elif bb < 0.8: bb_s = 2.0
        else: bb_s = 1.0

        # ATR ratio score
        atr_r = f.get('atr_ratio', 1.0)
        if atr_r < 0.8: atr_s = 4.0
        elif atr_r < 1.2: atr_s = 3.0
        elif atr_r < 1.5: atr_s = 2.0
        else: atr_s = 1.0

        # Volume health score
        dvr = f.get('down_vol_ratio', 1.0)
        if dvr < 0.7: vol_health_s = 4.0
        elif dvr < 1.0: vol_health_s = 3.0
        elif dvr < 1.3: vol_health_s = 2.0
        else: vol_health_s = 1.0

        # Support proximity score
        sp = f.get('support_dist', 0.5)
        if sp < 0.2: support_s = 3.5
        elif sp < 0.4: support_s = 3.0
        elif sp < 0.6: support_s = 2.5
        else: support_s = 1.5

        # OBV trend score (与backtest完全一致)
        obv_acc = f.get('obv_accel', 0)
        avg_v = np.mean(stock_hist['volume'].values[-10:]) if s_n >= 10 else 1
        obv_norm = obv_acc / max(avg_v, 1) * 100
        if obv_norm > 10: obv_s = 3.5
        elif obv_norm > 0: obv_s = 2.5
        elif obv_norm > -10: obv_s = 2.0
        else: obv_s = 1.0

        return {
            'momentum_s': momentum_s,
            'trend_s': trend_s,
            'consistency_s': consistency_s,
            'mr_s': mr_s,
            'vol_s': vol_s,
            'rsi_s': rsi_s,
            'static_score': static_score,
            'defense_s': defense_s,
            'sector_heat': sector_heat,
            'low_vol_s': low_vol_s,
            'rel_str': rel_str,
            'rel_str_3d': rel_str_3d,
            'beta_bonus': beta_bonus,
            'beta': beta,
            # 条件判断用（boost/penalty乘数）
            'consistency': consistency,
            'r1': f.get('r1', 0),
            'r3': f.get('r3', 0),
            'r5': f.get('r5', 0),
            'close_ma5': f.get('close_ma5', 0),
            'close_ma20': f.get('close_ma20', 0),
            'vol5': vol5,
            'vol_shrink': f.get('vol_shrink', 1),
            'turn_spike': f.get('turn_spike', 1),
            'rsi': rsi,
            'streak': f.get('streak', 0),
            'oversold': f.get('oversold', 0),
            'overbought': f.get('overbought', 0),
            'ind_heat': ind_heat,
            'is_defensive': is_def,
            'is_high_beta': is_hb,
            # V22 new sub-scores
            'bb_pctb': bb,
            'bb_s': bb_s,
            'atr_ratio': atr_r,
            'atr_s': atr_s,
            'down_vol_ratio': dvr,
            'vol_health_s': vol_health_s,
            'support_dist': sp,
            'support_s': support_s,
            'obv_s': obv_s,
            'vol_price_confirm': f.get('vol_price_confirm', 0),
            'vol_price_diverge': f.get('vol_price_diverge', 0),
            'exhaustion': f.get('exhaustion', 0),
        }

    def batch_compute_subscores(self, stock_list, target_date=None):
        """批量计算子分数

        Args:
            stock_list: 推荐器候选股列表 [{code, name, ...}, ...]
            target_date: 目标日期

        Returns:
            {code: subscores_dict} 成功的股票映射
        """
        if not self._loaded:
            if not self.load_data():
                return {}

        results = {}
        success = 0
        fallback = 0

        for stock in stock_list:
            code = normalize_code(stock.get('code', ''))
            if not code:
                continue

            subscores = self.compute_real_subscores(code, target_date, stock)
            if subscores is not None:
                results[code] = subscores
                success += 1
            else:
                fallback += 1

        logger.info(f"真实特征计算: {success} 成功, {fallback} 回退到映射")
        return results


# ============================================================================
# 单元测试
# ============================================================================
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    calc = RealFeatureCalculator()
    calc.load_data()

    # 测试几只股票
    test_codes = ['000001', '600519', '002818', '000002', '601398']

    for code in test_codes:
        result = calc.compute_real_subscores(code)
        if result:
            print(f"\n{'='*60}")
            print(f"  {code}:")
            for k, v in sorted(result.items()):
                print(f"    {k:20s}: {v:.4f}" if isinstance(v, float) else f"    {k:20s}: {v}")
        else:
            print(f"\n  {code}: 数据不足或无K线")
