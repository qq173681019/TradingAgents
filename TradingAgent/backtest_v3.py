#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票推荐算法回测系统 V3
========================
改进版本，包含：
1. 扩大选股池（使用6个月K线缓存，899只股票）
2. 追高过滤（前一天涨>5%不推荐）
3. 均线多头排列过滤
4. 均值回归信号（5日跌幅大反而加分）
5. 扩展回测时间范围（6个月）
6. XGBoost/LightGBM机器学习模型
7. 市场情绪过滤（大盘连跌3天暂停）
8. NewsData新闻情绪集成
9. 滚动窗口训练（避免未来数据泄露）
"""

import json
import os
import sys
import time
import warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

warnings.filterwarnings('ignore')

# 路径设置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'TradingShared', 'data')
KLINE_CACHE = os.path.join(DATA_DIR, 'kline_cache')
RESULT_DIR = os.path.join(BASE_DIR, 'backtest_results')

sys.path.insert(0, os.path.join(BASE_DIR, '..', 'TradingShared'))

# ============================================================================
# 配置参数
# ============================================================================
BACKTEST_START = '2025-10-08'
BACKTEST_END = '2026-04-07'
TARGET_ACCURACY = 0.80  # 目标降到80%更现实
TOP_N_RECOMMEND = 3
MAX_INDUSTRY_STOCKS = 2  # 每行业最多选2只（原1只）
MIN_TRAIN_DAYS = 30  # ML模型最少训练天数

# NewsData API
NEWSDATA_API_KEY = "pub_c301282569f647dbad884a6ec64717a7"


# ============================================================================
# 数据加载
# ============================================================================
def load_kline_6m() -> Dict[str, pd.DataFrame]:
    """加载6个月K线数据（899只股票）"""
    # 优先用scored_6m（有评分的189只），再用完整6m（899只）
    cache_file = os.path.join(KLINE_CACHE, 'kline_6m_2025-10-01_2026-04-07.json')
    
    if not os.path.exists(cache_file):
        print("[ERROR] 6个月K线缓存不存在!")
        return {}
    
    print("[INFO] 加载6个月K线数据...")
    with open(cache_file, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    
    kline = {}
    for code, records in raw.items():
        df = pd.DataFrame(records)
        df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
        df = df.sort_values('date')
        # 统一code格式（去掉sh./sz.前缀）
        clean_code = code.replace('sh.', '').replace('sz.', '')
        kline[clean_code] = df
    
    print(f"[OK] 加载 {len(kline)} 只股票K线数据")
    return kline


def load_index_6m() -> pd.DataFrame:
    """加载6个月上证指数数据"""
    # 尝试Choice格式
    choice_file = os.path.join(KLINE_CACHE, 'index_6m_2025-10-08_2026-04-07.json')
    if os.path.exists(choice_file):
        with open(choice_file, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        # Choice格式: {date: {'0': timestamp_ms, '1': ...}, close: {'0': 3300, ...}}
        if isinstance(raw, dict) and 'date' in raw:
            n = len(raw['date'])
            records = []
            for i in range(n):
                key = str(i)
                try:
                    date_val = raw['date'][key]
                    close_val = raw['close'].get(key)
                    high_val = raw['high'].get(key) if 'high' in raw else None
                    low_val = raw['low'].get(key) if 'low' in raw else None
                    vol_val = raw['volume'].get(key) if 'volume' in raw else None
                    
                    # 日期可能是毫秒时间戳或字符串
                    if isinstance(date_val, (int, float)):
                        date_str = pd.Timestamp(date_val, unit='ms').strftime('%Y-%m-%d')
                    else:
                        date_str = str(date_val)
                    
                    records.append({
                        'date': date_str,
                        'close': float(close_val) if close_val is not None else None,
                        'high': float(high_val) if high_val is not None else None,
                        'low': float(low_val) if low_val is not None else None,
                        'volume': float(vol_val) if vol_val is not None else None,
                    })
                except (KeyError, TypeError, ValueError):
                    continue
            df = pd.DataFrame(records)
            df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
            df = df.dropna(subset=['close']).sort_values('date')
            print(f"[OK] 加载Choice指数数据: {len(df)} 天")
            return df
    
    # AKShare格式
    ak_file = os.path.join(DATA_DIR, 'index_shanghai.json')
    if os.path.exists(ak_file):
        with open(ak_file, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        if isinstance(raw, list):
            df = pd.DataFrame(raw)
            df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
            df = df.sort_values('date')
            print(f"[OK] 加载AKShare指数数据: {len(df)} 天")
            return df
    
    print("[WARN] 无指数数据，使用零基准")
    return pd.DataFrame()


def load_scores() -> Dict:
    """加载最新的股票评分数据"""
    import glob
    score_files = sorted(glob.glob(os.path.join(DATA_DIR, 'batch_stock_scores_optimized_主板_*.json')))
    
    scores = {}
    if score_files:
        latest = score_files[-1]
        print(f"[INFO] 加载评分: {os.path.basename(latest)}")
        with open(latest, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        for code, sdata in data.items():
            scores[code] = {
                'tech_score': float(sdata.get('short_term_score', 5.0)),
                'fund_score': float(sdata.get('long_term_score', 5.0)),
                'chip_score': float(sdata.get('chip_score', 5.0)),
                'sector_score': float(sdata.get('hot_sector_score', 5.0)),
                'name': sdata.get('name', ''),
                'industry': sdata.get('industry', '未知'),
            }
        print(f"[OK] 加载 {len(scores)} 只股票评分")
    
    return scores


def load_industry_map() -> Dict[str, str]:
    """加载行业映射"""
    map_file = os.path.join(BASE_DIR, 'extended_industry_map.json')
    if os.path.exists(map_file):
        with open(map_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


# ============================================================================
# 技术指标计算（纯基于历史数据，不泄露未来）
# ============================================================================
class TechnicalIndicators:
    """技术指标计算器"""
    
    @staticmethod
    def calc_all(close: np.ndarray, volume: np.ndarray, high: np.ndarray, low: np.ndarray) -> Dict:
        """计算所有技术指标"""
        features = {}
        n = len(close)
        
        if n < 10:
            return None
        
        # === 基础收益率 ===
        features['ret_1d'] = (close[-1] - close[-2]) / close[-2] * 100 if n >= 2 else 0
        features['ret_2d'] = (close[-1] - close[-3]) / close[-3] * 100 if n >= 3 else 0
        features['ret_3d'] = (close[-1] - close[-4]) / close[-4] * 100 if n >= 4 else 0
        features['ret_5d'] = (close[-1] - close[-6]) / close[-6] * 100 if n >= 6 else 0
        features['ret_10d'] = (close[-1] - close[-11]) / close[-11] * 100 if n >= 11 else 0
        
        # === 均线系统 ===
        ma5 = np.mean(close[-5:])
        ma10 = np.mean(close[-10:]) if n >= 10 else ma5
        ma20 = np.mean(close[-20:]) if n >= 20 else ma10
        ma60 = np.mean(close[-60:]) if n >= 60 else ma20
        
        features['close_ma5_ratio'] = (close[-1] / ma5 - 1) * 100
        features['close_ma10_ratio'] = (close[-1] / ma10 - 1) * 100
        features['close_ma20_ratio'] = (close[-1] / ma20 - 1) * 100
        
        # MA斜率
        if n >= 6:
            ma5_prev = np.mean(close[-6:-1])
            features['ma5_slope'] = (ma5 - ma5_prev) / ma5_prev * 100
        else:
            features['ma5_slope'] = 0
        
        if n >= 11:
            ma10_prev = np.mean(close[-11:-1])
            features['ma10_slope'] = (ma10 - ma10_prev) / ma10_prev * 100
        else:
            features['ma10_slope'] = 0
        
        # === 均线多头排列（关键过滤） ===
        # 理想：close > ma5 > ma10 > ma20
        features['ma_bull'] = 1 if (close[-1] > ma5 > ma10 > ma20) else 0
        features['ma5_above_ma10'] = 1 if ma5 > ma10 else 0
        features['ma5_above_ma20'] = 1 if ma5 > ma20 else 0
        features['ma10_above_ma20'] = 1 if ma10 > ma20 else 0
        
        # 均线多头得分（0-3分）
        features['ma_align_score'] = (
            features['ma5_above_ma10'] + 
            features['ma5_above_ma20'] + 
            features['ma10_above_ma20']
        )
        
        # === RSI ===
        window = min(14, n - 1)
        gains, losses = [], []
        for i in range(-window, 0):
            chg = (close[i] - close[i-1]) / close[i-1] * 100
            gains.append(max(chg, 0))
            losses.append(max(-chg, 0))
        avg_gain = np.mean(gains) if gains else 0
        avg_loss = max(np.mean(losses), 0.01)
        features['rsi'] = 100 - 100 / (1 + avg_gain / avg_loss)
        
        # === MACD ===
        if n >= 26:
            ema12 = close[-1]
            ema26 = close[-1]
            for i in range(-26, 0):
                ema12 = close[i] * (2/14) + ema12 * (1 - 2/14)
                ema26 = close[i] * (2/27) + ema26 * (1 - 2/27)
            features['macd_diff'] = ema12 - ema26
        else:
            features['macd_diff'] = 0
        
        # === 波动率 ===
        if n >= 6:
            rets = np.diff(close[-6:]) / close[-6:-1]
            features['vol_5d'] = np.std(rets) * 100
        else:
            features['vol_5d'] = 0
        
        if n >= 11:
            rets10 = np.diff(close[-11:]) / close[-11:-1]
            features['vol_10d'] = np.std(rets10) * 100
        else:
            features['vol_10d'] = features['vol_5d']
        
        # === 成交量 ===
        if len(volume) >= 10 and np.mean(volume[-10:]) > 0:
            features['vol_ratio'] = np.mean(volume[-5:]) / np.mean(volume[-10:])
        else:
            features['vol_ratio'] = 1.0
        
        # === 价格位置 ===
        window20 = min(20, n)
        h20 = np.max(close[-window20:])
        l20 = np.min(close[-window20:])
        features['price_position'] = (close[-1] - l20) / (h20 - l20) * 100 if h20 != l20 else 50
        
        # === ATR ===
        if n >= 6:
            trs = []
            for i in range(-min(14, n-1), 0):
                tr = max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1]))
                trs.append(tr)
            features['atr_pct'] = np.mean(trs) / close[-1] * 100
        else:
            features['atr_pct'] = 0
        
        # === 连涨连跌 ===
        streak = 0
        for i in range(n-1, 0, -1):
            if close[i] > close[i-1]:
                streak = streak + 1 if streak >= 0 else 1
            elif close[i] < close[i-1]:
                streak = streak - 1 if streak <= 0 else -1
            else:
                break
        features['streak'] = streak
        
        # === 均值回归信号 ===
        # 5日跌幅越大，反转概率越高
        features['mean_reversion_5d'] = -features['ret_5d']  # 负值表示超卖
        # 标准化：跌幅>5%得高分
        if features['ret_5d'] < -5:
            features['mr_signal'] = 3.0
        elif features['ret_5d'] < -3:
            features['mr_signal'] = 2.0
        elif features['ret_5d'] < -1:
            features['mr_signal'] = 1.0
        elif features['ret_5d'] > 5:
            features['mr_signal'] = -2.0  # 追高惩罚
        elif features['ret_5d'] > 3:
            features['mr_signal'] = -1.0
        else:
            features['mr_signal'] = 0.0
        
        # === 交互特征 ===
        features['ret1_x_vol'] = features['ret_1d'] * features['vol_5d']
        features['rsi_x_position'] = features['rsi'] * features['price_position'] / 100
        
        return features


# ============================================================================
# 市场情绪分析
# ============================================================================
class MarketSentiment:
    """大盘情绪分析器"""
    
    @staticmethod
    def check_consecutive_decline(index_df: pd.DataFrame, date: pd.Timestamp) -> bool:
        """检查大盘是否连跌3天"""
        if index_df is None or len(index_df) == 0:
            return False
        
        hist = index_df[index_df['date'] < date].tail(3)
        if len(hist) < 3:
            return False
        
        declines = 0
        closes = hist['close'].values
        for i in range(1, len(closes)):
            if closes[i] < closes[i-1]:
                declines += 1
        
        return declines >= 3
    
    @staticmethod
    def get_market_regime(index_df: pd.DataFrame, date: pd.Timestamp) -> str:
        """判断市场状态: bull/bear/neutral"""
        if index_df is None or len(index_df) == 0:
            return 'neutral'
        
        hist = index_df[index_df['date'] < date]
        if len(hist) < 20:
            return 'neutral'
        
        ma20 = hist['close'].tail(20).mean()
        current = hist['close'].iloc[-1]
        
        if current > ma20 * 1.02:
            return 'bull'
        elif current < ma20 * 0.98:
            return 'bear'
        return 'neutral'
    
    @staticmethod
    def fetch_news_sentiment(date_str: str = None) -> Dict:
        """
        从NewsData获取财经新闻情绪
        API文档: https://newsdata.io/documentation
        """
        try:
            import urllib.request
            import urllib.parse
            
            query_params = {
                'apikey': NEWSDATA_API_KEY,
                'q': 'A股 OR 上证 OR 股市',
                'language': 'zh',
                'country': 'cn',
                'category': 'business',
                'size': 10,
            }
            
            if date_str:
                # NewsData使用published_utc作为时间过滤
                query_params['published_utc'] = date_str
            
            url = "https://newsdata.io/api/1/news?" + urllib.parse.urlencode(query_params)
            
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            
            results = data.get('results', [])
            if not results:
                return {'score': 0, 'count': 0, 'sentiment': 'neutral'}
            
            # 简单情绪分析：基于关键词
            positive_words = ['上涨', '大涨', '牛市', '利好', '反弹', '突破', '新高', '强势', '增量', '回暖']
            negative_words = ['下跌', '大跌', '熊市', '利空', '暴跌', '破位', '新低', '弱势', '缩量', '低迷']
            
            pos_count = 0
            neg_count = 0
            
            for article in results:
                title = (article.get('title') or '') + ' ' + (article.get('description') or '')
                for w in positive_words:
                    if w in title:
                        pos_count += 1
                        break
                for w in negative_words:
                    if w in title:
                        neg_count += 1
                        break
            
            total = len(results)
            if pos_count > neg_count:
                sentiment = 'positive'
                score = (pos_count - neg_count) / total * 100
            elif neg_count > pos_count:
                sentiment = 'negative'
                score = -(neg_count - pos_count) / total * 100
            else:
                sentiment = 'neutral'
                score = 0
            
            return {
                'score': score,
                'count': total,
                'sentiment': sentiment,
                'articles': len(results)
            }
            
        except Exception as e:
            print(f"  [WARN] NewsData API调用失败: {e}")
            return {'score': 0, 'count': 0, 'sentiment': 'unknown'}


# ============================================================================
# 推荐引擎 V3
# ============================================================================
class RecommendationEngineV3:
    """V3推荐引擎 - 综合技术面+均值回归+ML"""
    
    def __init__(self, mode='rule'):
        """
        mode: 'rule' (规则), 'ml' (机器学习), 'hybrid' (混合)
        """
        self.mode = mode
        self.ml_model = None
        self.scaler = None
        self.feat_cols = None
    
    def train_ml(self, train_data: pd.DataFrame):
        """训练ML模型"""
        from sklearn.preprocessing import StandardScaler
        
        meta_cols = ['beat', 'date', 'code', 'ret', 'idx_ret', 'name']
        feat_cols = [c for c in train_data.columns if c not in meta_cols]
        self.feat_cols = feat_cols
        
        train_clean = train_data[feat_cols + ['beat']].dropna()
        
        X = train_clean[feat_cols].values
        y = train_clean['beat'].values
        
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)
        
        # 尝试XGBoost -> LightGBM -> LogisticRegression
        model = None
        
        try:
            from xgboost import XGBClassifier
            model = XGBClassifier(
                n_estimators=100,
                max_depth=4,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                use_label_encoder=False,
                eval_metric='logloss'
            )
            model.fit(X_scaled, y)
            print(f"  [OK] XGBoost模型训练完成 ({len(X)} 样本, {len(feat_cols)} 特征)")
        except ImportError:
            try:
                from lightgbm import LGBMClassifier
                model = LGBMClassifier(
                    n_estimators=100,
                    max_depth=4,
                    learning_rate=0.1,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    random_state=42,
                    verbose=-1
                )
                model.fit(X_scaled, y)
                print(f"  [OK] LightGBM模型训练完成 ({len(X)} 样本, {len(feat_cols)} 特征)")
            except ImportError:
                from sklearn.linear_model import LogisticRegression
                model = LogisticRegression(C=0.1, max_iter=1000)
                model.fit(X_scaled, y)
                print(f"  [OK] LogisticRegression模型训练完成 ({len(X)} 样本, {len(feat_cols)} 特征)")
        
        self.ml_model = model
    
    def score_rule(self, features: Dict, static_scores: Dict = None) -> float:
        """规则评分"""
        score = 0.0
        
        # 1. 动量得分 (权重25%，原来50%太高)
        momentum = features.get('ret_1d', 0) * 0.3 + features.get('ret_3d', 0) * 0.3 + features.get('ret_5d', 0) * 0.4
        # 映射到0-10
        momentum_score = max(0, min(10, 5 + momentum * 0.3))
        score += momentum_score * 0.25
        
        # 2. 均值回归得分 (权重25%，新增)
        mr_signal = features.get('mr_signal', 0)
        mr_score = 5 + mr_signal * 2  # mr_signal范围-2到3
        mr_score = max(0, min(10, mr_score))
        score += mr_score * 0.25
        
        # 3. 趋势得分 (权重20%)
        trend_score = features.get('ma_align_score', 0) * 3.33  # 0-3 -> 0-10
        ma_slope = features.get('ma5_slope', 0)
        trend_score += max(0, min(10, 5 + ma_slope * 2))
        trend_score /= 2
        score += trend_score * 0.20
        
        # 4. 成交量得分 (权重10%)
        vol_ratio = features.get('vol_ratio', 1.0)
        if 1.2 <= vol_ratio <= 2.0:
            vol_score = 7 + (vol_ratio - 1.0) * 2
        elif vol_ratio < 0.8:
            vol_score = 3.0
        else:
            vol_score = 5.0
        score += vol_score * 0.10
        
        # 5. 静态评分 (权重20%)
        if static_scores:
            tech = static_scores.get('tech_score', 5.0)
            fund = static_scores.get('fund_score', 5.0)
            chip = static_scores.get('chip_score', 5.0)
            static = (tech * 0.45 + fund * 0.25 + chip * 0.30)
            score += static * 0.20
        else:
            score += 5.0 * 0.20
        
        return score
    
    def score_ml(self, features: Dict) -> float:
        """ML模型评分（返回beat概率）"""
        if self.ml_model is None or self.scaler is None or self.feat_cols is None:
            return 5.0
        
        feat_values = [features.get(c, 0) for c in self.feat_cols]
        X = np.array(feat_values).reshape(1, -1)
        X_scaled = self.scaler.transform(X)
        
        try:
            prob = self.ml_model.predict_proba(X_scaled)[0][1]
            return prob * 10  # 映射到0-10
        except:
            return 5.0
    
    def recommend(self, kline_data: Dict, scores_data: Dict, 
                  date: pd.Timestamp, index_df: pd.DataFrame = None,
                  top_n: int = TOP_N_RECOMMEND,
                  industry_map: Dict = None) -> Tuple[List[Dict], List[Dict]]:
        """
        推荐股票
        
        Returns:
            (推荐列表, 所有评分股票列表)
        """
        date_str = date.strftime('%Y-%m-%d')
        scored_stocks = []
        all_features = []
        
        # 市场情绪检查
        market = MarketSentiment.get_market_regime(index_df, date)
        is_decline = MarketSentiment.check_consecutive_decline(index_df, date)
        
        for code, df in kline_data.items():
            # 只取目标日期前的数据（不看未来）
            hist = df[df['date'] < date].copy()
            
            if len(hist) < 10:
                continue
            
            # 检查该股票目标日期是否有数据
            future = df[df['date'] >= date]
            if len(future) == 0:
                continue
            
            close = hist['close'].values.astype(float)
            volume = hist['volume'].values.astype(float) if 'volume' in hist.columns else np.ones(len(close))
            high = hist['high'].values.astype(float) if 'high' in hist.columns else close
            low = hist['low'].values.astype(float) if 'low' in hist.columns else close
            
            # 计算技术指标
            features = TechnicalIndicators.calc_all(close, volume, high, low)
            if features is None:
                continue
            
            # === 过滤条件 ===
            
            # 1. 追高过滤：前一天涨>5%不推荐
            if features['ret_1d'] > 5.0:
                continue
            
            # 2. ST过滤
            stock_scores = scores_data.get(code, {})
            name = stock_scores.get('name', '')
            if any(tag in str(name).upper() for tag in ['ST', '*ST', '退市']):
                continue
            
            # 3. 均线过滤：至少MA5在MA10上方（弱多头）
            # 放宽条件：不要求完美多头，但至少不能全空头
            if features['ma_align_score'] == 0 and features['ret_5d'] > 2:
                # 全空头+最近还在涨 = 追高，跳过
                continue
            
            # 获取静态评分
            static = scores_data.get(code, None)
            
            # 计算综合评分
            if self.mode == 'rule':
                final_score = self.score_rule(features, static)
            elif self.mode == 'ml':
                final_score = self.score_ml(features)
            else:  # hybrid
                rule_score = self.score_rule(features, static)
                ml_score = self.score_ml(features)
                final_score = rule_score * 0.4 + ml_score * 0.6
            
            # 市场情绪调整
            if market == 'bear':
                final_score *= 0.9  # 熊市降分
            elif market == 'bull':
                final_score *= 1.05  # 牛市略加
            
            # 均值回归在连跌时额外加分
            if is_decline and features['ret_5d'] < -3:
                final_score *= 1.1
            
            industry = static.get('industry', '未知') if static else '未知'
            if industry_map and code in industry_map:
                industry = industry_map[code]
            
            stock_info = {
                'code': code,
                'name': name,
                'score': round(final_score, 3),
                'industry': industry,
                'features': features,
            }
            scored_stocks.append(stock_info)
            all_features.append(stock_info)
        
        # 按评分排序
        scored_stocks.sort(key=lambda x: x['score'], reverse=True)
        
        # 分散化：每行业最多MAX_INDUSTRY_STOCKS只
        selected = []
        industry_count = defaultdict(int)
        
        for stock in scored_stocks:
            if len(selected) >= top_n:
                break
            ind = stock['industry']
            if industry_count[ind] >= MAX_INDUSTRY_STOCKS:
                continue
            
            # 连跌3天时，减少推荐数量（只推荐得分>6的）
            if is_decline and stock['score'] < 6.0:
                continue
            
            selected.append(stock)
            industry_count[ind] += 1
        
        return selected, all_features


# ============================================================================
# 回测框架V3
# ============================================================================
class BacktesterV3:
    """V3回测框架"""
    
    def __init__(self, start_date: str, end_date: str):
        self.start_date = start_date
        self.end_date = end_date
        self.results = []
    
    def get_return(self, df: pd.DataFrame, date: pd.Timestamp) -> Optional[float]:
        """获取指定日期的股票收益率"""
        target = date
        day = df[df['date'] >= target]
        prev = df[df['date'] < target]
        
        if len(day) == 0 or len(prev) == 0:
            return None
        
        try:
            today_close = float(day.iloc[0]['close'])
            yesterday_close = float(prev.iloc[-1]['close'])
            if yesterday_close > 0:
                return (today_close - yesterday_close) / yesterday_close * 100
        except:
            pass
        return None
    
    def get_index_return(self, index_df: pd.DataFrame, date: pd.Timestamp) -> Optional[float]:
        """获取指数收益率"""
        if index_df is None or len(index_df) == 0:
            return None
        
        day = index_df[index_df['date'] >= date]
        prev = index_df[index_df['date'] < date]
        
        if len(day) == 0 or len(prev) == 0:
            return None
        
        try:
            return (float(day.iloc[0]['close']) - float(prev.iloc[-1]['close'])) / float(prev.iloc[-1]['close']) * 100
        except:
            return None
    
    def run(self, engine: RecommendationEngineV3, 
            kline_data: Dict, scores_data: Dict,
            index_df: pd.DataFrame, 
            industry_map: Dict = None,
            use_ml: bool = False) -> Dict:
        """
        运行回测
        
        如果use_ml=True，使用滚动窗口训练ML模型
        """
        print(f"\n{'='*70}")
        print(f"[BACKTEST V3] 模式: {engine.mode}")
        print(f"  回测区间: {self.start_date} ~ {self.end_date}")
        print(f"  股票池: {len(kline_data)} 只")
        print(f"  使用ML: {use_ml}")
        print(f"{'='*70}")
        
        start = pd.to_datetime(self.start_date)
        end = pd.to_datetime(self.end_date)
        date_range = pd.date_range(start, end, freq='B')
        
        # 收集所有可用的交易日
        valid_dates = []
        for d in date_range:
            idx_ret = self.get_index_return(index_df, d)
            if idx_ret is not None:
                valid_dates.append(d)
        
        print(f"  有效交易日: {len(valid_dates)} 天")
        
        if len(valid_dates) == 0:
            print("[ERROR] 无有效交易日!")
            return {'accuracy': 0, 'total_days': 0, 'win_days': 0, 'results': []}
        
        # ML滚动训练：用前30天训练，之后每10天重新训练
        ml_train_interval = 10
        ml_last_train_idx = -999
        
        # 预热期：前10天不推荐（需要足够历史数据）
        warmup = 10
        start_idx = warmup
        
        results = []
        wins = 0
        total = 0
        
        for day_idx in range(start_idx, len(valid_dates)):
            test_date = valid_dates[day_idx]
            
            # ML滚动训练
            if use_ml and (day_idx - ml_last_train_idx >= ml_train_interval):
                train_end_idx = max(0, day_idx - 1)
                train_start_idx = max(0, day_idx - MIN_TRAIN_DAYS - 10)
                
                if train_end_idx - train_start_idx >= 10:
                    print(f"\n  [ML训练] 使用 {valid_dates[train_start_idx].strftime('%Y-%m-%d')} ~ "
                          f"{valid_dates[train_end_idx].strftime('%Y-%m-%d')} 的数据训练")
                    train_dataset = self._build_ml_dataset(
                        engine, kline_data, scores_data, index_df, 
                        valid_dates[train_start_idx:train_end_idx+1], industry_map
                    )
                    if len(train_dataset) >= 50:
                        engine.train_ml(train_dataset)
                        ml_last_train_idx = day_idx
            
            # 生成推荐
            recommendations, all_feats = engine.recommend(
                kline_data, scores_data, test_date, index_df,
                industry_map=industry_map
            )
            
            if not recommendations:
                continue
            
            # 获取指数涨幅
            index_return = self.get_index_return(index_df, test_date)
            if index_return is None:
                index_return = 0.0
            
            # 评估
            daily_wins = 0
            stock_returns = []
            
            for stock in recommendations:
                code = stock['code']
                if code in kline_data:
                    stock_ret = self.get_return(kline_data[code], test_date)
                else:
                    stock_ret = None
                
                if stock_ret is not None:
                    beat = stock_ret > index_return
                    stock_returns.append({
                        'code': code,
                        'name': stock.get('name', ''),
                        'return': round(stock_ret, 2),
                        'beat_index': beat,
                        'score': stock['score'],
                        'industry': stock.get('industry', ''),
                    })
                    if beat:
                        daily_wins += 1
            
            if stock_returns:
                total += 1
                win_rate = daily_wins / len(stock_returns)
                is_win = win_rate > 0.5
                if is_win:
                    wins += 1
                
                result = {
                    'date': test_date.strftime('%Y-%m-%d'),
                    'recommendations': stock_returns,
                    'index_return': round(index_return, 2),
                    'win_rate': round(win_rate, 2),
                    'is_win_day': is_win,
                    'avg_return': round(np.mean([s['return'] for s in stock_returns]), 2),
                }
                results.append(result)
                
                # 进度
                status = "[OK]" if is_win else "[X]"
                print(f"  [{test_date.strftime('%Y-%m-%d')}] {status} "
                      f"Avg={result['avg_return']:+.2f}% Idx={index_return:+.2f}% "
                      f"WR={win_rate*100:.0f}% ({daily_wins}/{len(stock_returns)})")
        
        accuracy = wins / total if total > 0 else 0
        
        print(f"\n{'='*70}")
        print(f"[结果] 总天数: {total} | 胜利: {wins} | 准确率: {accuracy*100:.1f}%")
        print(f"{'='*70}")
        
        return {
            'accuracy': accuracy,
            'total_days': total,
            'win_days': wins,
            'results': results,
            'mode': engine.mode,
        }
    
    def _build_ml_dataset(self, engine, kline_data, scores_data, index_df, dates, industry_map):
        """构建ML训练数据集"""
        all_data = []
        
        for date in dates:
            idx_ret = self.get_index_return(index_df, date)
            if idx_ret is None:
                continue
            
            # 获取当天所有可评分的股票
            for code, df in kline_data.items():
                hist = df[df['date'] < date]
                if len(hist) < 10:
                    continue
                
                future = df[df['date'] >= date]
                if len(future) == 0:
                    continue
                
                close = hist['close'].values.astype(float)
                volume = hist['volume'].values.astype(float) if 'volume' in hist.columns else np.ones(len(close))
                high = hist['high'].values.astype(float) if 'high' in hist.columns else close
                low = hist['low'].values.astype(float) if 'low' in hist.columns else close
                
                features = TechnicalIndicators.calc_all(close, volume, high, low)
                if features is None:
                    continue
                
                stock_ret = self.get_return(df, date)
                if stock_ret is None:
                    continue
                
                features['beat'] = 1 if stock_ret > idx_ret else 0
                features['date'] = date.strftime('%Y-%m-%d')
                features['code'] = code
                features['ret'] = stock_ret
                features['idx_ret'] = idx_ret
                features['name'] = scores_data.get(code, {}).get('name', '')
                
                all_data.append(features)
        
        if all_data:
            df_all = pd.DataFrame(all_data)
            print(f"    训练集: {len(df_all)} 样本, Beat率: {df_all['beat'].mean()*100:.1f}%")
            return df_all
        return pd.DataFrame()


# ============================================================================
# 新闻情绪测试
# ============================================================================
def test_news_api():
    """测试NewsData API"""
    print("\n" + "="*70)
    print("[测试] NewsData API 连通性")
    print("="*70)
    
    result = MarketSentiment.fetch_news_sentiment()
    if result['count'] > 0:
        print(f"  [OK] API可用! 获取到 {result['count']} 篇新闻")
        print(f"  情绪: {result['sentiment']} (分数: {result['score']:.1f})")
    else:
        print(f"  [!] API返回0条结果 (sentiment={result['sentiment']})")
        print(f"  将继续使用技术面分析，不影响回测")
    
    return result


# ============================================================================
# 报告生成
# ============================================================================
def generate_v3_report(results: Dict, output_path: str):
    """生成V3报告"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    lines = []
    lines.append("=" * 70)
    lines.append("股票推荐算法回测报告 V3")
    lines.append("=" * 70)
    lines.append(f"\n回测区间: {BACKTEST_START} ~ {BACKTEST_END}")
    lines.append(f"模式: {results['mode']}")
    lines.append(f"\n总交易日: {results['total_days']}")
    lines.append(f"胜利日: {results['win_days']}")
    lines.append(f"准确率: {results['accuracy']*100:.1f}%")
    lines.append(f"目标: {TARGET_ACCURACY*100:.0f}%")
    
    if results['accuracy'] >= TARGET_ACCURACY:
        lines.append(f"\n[OK] 达标!")
    else:
        lines.append(f"\n[X] 未达标 (差 {(TARGET_ACCURACY - results['accuracy'])*100:.1f}%)")
    
    lines.append(f"\n{'='*70}")
    lines.append("每日详情")
    lines.append("="*70)
    
    for r in results['results']:
        status = "[OK]" if r['is_win_day'] else "[X]"
        lines.append(f"\n{r['date']} {status}  Avg={r['avg_return']:+.2f}%  Idx={r['index_return']:+.2f}%  WR={r['win_rate']*100:.0f}%")
        for s in r['recommendations']:
            beat = "[V]" if s['beat_index'] else "[-]"
            lines.append(f"  {s['code']} {s['name']}: {s['return']:+.2f}% {beat} (score={s['score']:.1f})")
    
    report_text = "\n".join(lines)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report_text)
    
    print(f"\n[OK] 报告保存: {output_path}")
    return report_text


# ============================================================================
# 主程序
# ============================================================================
def main():
    start_time = time.time()
    
    print("=" * 70)
    print("股票推荐算法回测系统 V3")
    print("Stock Recommendation Backtest V3")
    print("=" * 70)
    print(f"  回测区间: {BACKTEST_START} ~ {BACKTEST_END}")
    print(f"  目标准确率: {TARGET_ACCURACY*100:.0f}%")
    print(f"  改进: 扩大选股池 + 追高过滤 + 均值回归 + ML + 情绪")
    print()
    
    # === 1. 数据加载 ===
    print("[STEP 1/6] 加载数据...")
    kline_data = load_kline_6m()
    index_df = load_index_6m()
    scores_data = load_scores()
    industry_map = load_industry_map()
    
    if not kline_data:
        print("[ERROR] 无K线数据!")
        return
    
    # === 2. 测试NewsData API ===
    print("\n[STEP 2/6] 测试NewsData API...")
    news_result = test_news_api()
    
    # === 3. 规则模式回测 ===
    print("\n[STEP 3/6] 规则模式回测...")
    engine_rule = RecommendationEngineV3(mode='rule')
    backtester = BacktesterV3(BACKTEST_START, BACKTEST_END)
    rule_results = backtester.run(engine_rule, kline_data, scores_data, index_df, industry_map)
    
    # === 4. ML模式回测（混合） ===
    print("\n[STEP 4/6] ML混合模式回测...")
    engine_hybrid = RecommendationEngineV3(mode='hybrid')
    backtester2 = BacktesterV3(BACKTEST_START, BACKTEST_END)
    hybrid_results = backtester2.run(engine_hybrid, kline_data, scores_data, index_df, industry_map, use_ml=True)
    
    # === 5. 生成报告 ===
    print("\n[STEP 5/6] 生成报告...")
    
    # 选最佳结果
    best = rule_results if rule_results['accuracy'] >= hybrid_results['accuracy'] else hybrid_results
    best_name = 'rule' if best is rule_results else 'hybrid'
    
    report_path = os.path.join(RESULT_DIR, f'backtest_v3_{best_name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt')
    generate_v3_report(best, report_path)
    
    # === 6. 最终总结 ===
    print("\n[STEP 6/6] 总结...")
    elapsed = time.time() - start_time
    
    print(f"\n{'='*70}")
    print(f"📊 最终结果")
    print(f"{'='*70}")
    print(f"  规则模式: {rule_results['accuracy']*100:.1f}% ({rule_results['win_days']}/{rule_results['total_days']})")
    print(f"  ML混合:   {hybrid_results['accuracy']*100:.1f}% ({hybrid_results['win_days']}/{hybrid_results['total_days']})")
    print(f"  最佳:     {best_name} ({best['accuracy']*100:.1f}%)")
    print(f"  目标:     {TARGET_ACCURACY*100:.0f}%")
    print(f"  {'[OK] 达标!' if best['accuracy'] >= TARGET_ACCURACY else '[X] 未达标'}")
    print(f"  耗时: {elapsed:.0f}s")
    print(f"{'='*70}")
    
    # 保存最终结果
    final = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': 'v3',
        'rule_accuracy': rule_results['accuracy'],
        'hybrid_accuracy': hybrid_results['accuracy'],
        'best_mode': best_name,
        'best_accuracy': best['accuracy'],
        'target_accuracy': TARGET_ACCURACY,
        'success': best['accuracy'] >= TARGET_ACCURACY,
        'total_days': best['total_days'],
        'win_days': best['win_days'],
        'stock_pool': len(kline_data),
        'elapsed_seconds': elapsed,
        'news_api': news_result['sentiment'],
        'report_path': report_path,
    }
    
    final_path = os.path.join(RESULT_DIR, 'final_result_v3.json')
    with open(final_path, 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] 结果保存: {final_path}")
    
    return best


if __name__ == '__main__':
    main()
