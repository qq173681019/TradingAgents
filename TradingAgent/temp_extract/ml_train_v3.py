#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ML Model Training V3 - Regime-Specialist Models
=================================================
V2 results: bull=88% PASS, bear=55% FAIL, overall=60.5%
Problem: single model can't handle bear market well.

V3 strategy:
  1. Train separate models for different market regimes
  2. Bear model: weighted to favor low-beta, defensive, positive rel_strength
  3. Use regime-appropriate model during backtest
  
Also try: Focus training on the problem area (bear market data)
"""

import os, sys, time, gc, json, warnings
import numpy as np
from datetime import datetime

warnings.filterwarnings('ignore')

BASE_DIR = r'D:\GitHub\TradingAgents\TradingAgent'
DATA_DIR = r'D:\GitHub\TradingAgents\TradingShared\data'
RESULT_DIR = os.path.join(BASE_DIR, 'backtest_results')
DATASET_FILE = os.path.join(DATA_DIR, 'ml_train_dataset.npz')

N_FEATURES = 50


def print_mem(label=""):
    try:
        import psutil
        mb = psutil.Process().memory_info().rss / 1024 / 1024
        if label:
            print(f"  [MEM] {label}: {mb:.0f}MB")
    except ImportError:
        pass


def load_data():
    """Load dataset with regime labels"""
    print(f"\n  Loading dataset...")
    data = np.load(DATASET_FILE, allow_pickle=True)
    feature_names = list(data['feature_names'])

    result = {}
    for key in ['X_train', 'y_train', 'y_train_cont', 'X_val', 'y_val', 'y_val_cont',
                'X_test', 'y_test', 'y_test_cont']:
        result[key] = data[key].astype(np.float32)
    result['feature_names'] = feature_names

    # Extract regime info from features (indices 39=bull, 40=bear, 41=range)
    # Feature 39=regime_bull, 40=regime_bear, 41=regime_range
    # Risk level = feature 38
    for split in ['train', 'val', 'test']:
        X = result[f'X_{split}']
        result[f'{split}_bull'] = X[:, 39] > 0.5  # regime_bull
        result[f'{split}_bear'] = X[:, 40] > 0.5  # regime_bear
        result[f'{split}_range'] = X[:, 41] > 0.5  # regime_range
        result[f'{split}_risk'] = X[:, 38]  # risk_level
        # Also extract: beta (27), is_defensive (48), is_high_beta (49)
        result[f'{split}_beta'] = X[:, 27]
        result[f'{split}_defensive'] = X[:, 48]
        result[f'{split}_high_beta'] = X[:, 49]
        result[f'{split}_vol5'] = X[:, 14]  # vol5
        result[f'{split}_rsi'] = X[:, 12]  # rsi

    del data
    gc.collect()

    print(f"    Train: {result['X_train'].shape}")
    print(f"      Bull: {result['train_bull'].sum()}, Bear: {result['train_bear'].sum()}, Range: {result['train_range'].sum()}")
    print(f"    Val: {result['X_val'].shape}")
    print(f"      Bull: {result['val_bull'].sum()}, Bear: {result['val_bear'].sum()}, Range: {result['val_range'].sum()}")
    print(f"    Test: {result['X_test'].shape}")

    return result


def train_bear_specialist(data):
    """Train a model specialized for bear market conditions.
    Key: heavily weight samples where defensive stocks beat the index."""
    try:
        import lightgbm as lgb
    except ImportError:
        return None

    print(f"\n{'='*60}")
    print("Bear Market Specialist Model")
    print(f"{'='*60}")

    X_tr = data['X_train']
    y_tr = data['y_train']
    y_tr_cont = data['y_train_cont']

    # Strategy: Weight bear-like samples heavily
    # "Bear-like" = high risk_level, high beta stocks tend to lose
    risk = data['train_risk']
    beta = data['train_beta']
    is_def = data['train_defensive']
    is_hb = data['train_high_beta']

    # Create bear-aware weights:
    # In high-risk contexts, defensive + low-beta winners get big weight
    weights = np.ones(len(X_tr), dtype=np.float32)

    # High risk samples: weight up
    high_risk = risk >= 4
    weights[high_risk] *= 3.0

    # In high risk: defensive winners are golden
    def_winners = high_risk & (is_def > 0.5) & (y_tr > 0.5)
    weights[def_winners] *= 5.0

    # In high risk: high-beta losers are also informative
    hb_losers = high_risk & (is_hb > 0.5) & (y_tr < 0.5)
    weights[hb_losers] *= 3.0

    # Low-beta winners in any context
    low_beta_winners = (beta < 0.8) & (y_tr > 0.5)
    weights[low_beta_winners] *= 2.0

    # Also weight by |relative return|
    weights *= (np.abs(y_tr_cont) + 0.5)
    weights = weights / weights.mean()

    feat_names = data['feature_names'][:N_FEATURES]

    dtrain = lgb.Dataset(X_tr, label=y_tr, weight=weights,
                         feature_name=feat_names, free_raw_data=False)
    dval = lgb.Dataset(data['X_val'], label=data['y_val'],
                       feature_name=feat_names, free_raw_data=False)

    params = {
        'objective': 'binary', 'metric': 'auc',
        'num_leaves': 31, 'learning_rate': 0.01, 'max_depth': 5,
        'min_child_samples': 100, 'feature_fraction': 0.7,
        'bagging_fraction': 0.8, 'bagging_freq': 5,
        'reg_alpha': 1.0, 'reg_lambda': 1.0,
        'verbosity': -1, 'n_jobs': -1, 'seed': 42,
    }

    eval_result = {}
    model = lgb.train(
        params, dtrain, num_boost_round=300,
        valid_sets=[dval], valid_names=['val'],
        callbacks=[
            lgb.log_evaluation(period=0),
            lgb.record_evaluation(eval_result),
        ],
    )

    val_auc = eval_result['val']['auc'][-1]

    # Evaluate specifically on bear samples in test
    bear_mask = data['test_bear']
    if bear_mask.sum() > 100:
        y_pred_bear = model.predict(data['X_test'][bear_mask])
        bear_auc = 0.0
        yt = data['y_test'][bear_mask]
        yp = y_pred_bear
        # Quick AUC
        desc = np.argsort(yp)[::-1]
        yt_s = yt[desc]
        di = np.where(np.diff(yp[desc]))[0]
        ti = np.append(di, len(yt) - 1)
        tps = np.cumsum(yt_s)[ti]
        fps = ti + 1 - tps
        tps = np.concatenate(([0], tps))
        fps = np.concatenate(([0], fps))
        fpr = fps / max(fps[-1], 1)
        tpr = tps / max(tps[-1], 1)
        bear_auc = float(np.sum((tpr[:-1] + tpr[1:]) / 2 * np.diff(fpr)))
        print(f"  Bear test AUC: {bear_auc:.4f} ({bear_mask.sum()} samples)")

    y_pred_all = model.predict(data['X_test'])
    # Overall AUC
    desc = np.argsort(y_pred_all)[::-1]
    yt_s = data['y_test'][desc]
    di = np.where(np.diff(y_pred_all[desc]))[0]
    ti = np.append(di, len(data['y_test']) - 1)
    tps = np.cumsum(yt_s)[ti]
    fps = ti + 1 - tps
    tps = np.concatenate(([0], tps))
    fps = np.concatenate(([0], fps))
    fpr = fps / max(fps[-1], 1)
    tpr = tps / max(tps[-1], 1)
    all_auc = float(np.sum((tpr[:-1] + tpr[1:]) / 2 * np.diff(fpr)))

    print(f"  Val AUC: {val_auc:.4f}")
    print(f"  Overall test AUC: {all_auc:.4f}")

    # Feature importance
    importance = model.feature_importance(importance_type='gain')
    feat_imp = sorted(zip(feat_names, importance), key=lambda x: x[1], reverse=True)
    print(f"\n  Feature Importance TOP 20:")
    for fname, imp in feat_imp[:20]:
        print(f"    {fname:30s} {imp:.1f}")

    # Save
    bear_model_path = os.path.join(DATA_DIR, 'ml_model_bear.txt')
    model.save_model(bear_model_path)
    print(f"  Bear model saved: {bear_model_path}")

    return {
        'model': model,
        'val_auc': val_auc,
        'bear_test_auc': bear_auc if bear_mask.sum() > 100 else 0,
        'feature_importance': feat_imp,
    }


def train_defense_model(data):
    """Train model that focuses on predicting which stocks will LOSE LESS
    in bad conditions. Essentially: predict y_continuous, but weight
    towards not losing money."""
    try:
        import lightgbm as lgb
    except ImportError:
        return None

    print(f"\n{'='*60}")
    print("Defense Model (regression with defensive bias)")
    print(f"{'='*60}")

    X_tr = data['X_train']
    y_tr_cont = data['y_train_cont']

    # Weight: emphasize samples in bad conditions
    risk = data['train_risk']
    weights = np.ones(len(X_tr), dtype=np.float32)
    weights[risk >= 4] *= 3.0
    weights[risk >= 5] *= 2.0
    weights *= (np.abs(y_tr_cont) + 0.5)
    weights = weights / weights.mean()

    feat_names = data['feature_names'][:N_FEATURES]
    dtrain = lgb.Dataset(X_tr, label=y_tr_cont, weight=weights,
                         feature_name=feat_names, free_raw_data=False)
    dval = lgb.Dataset(data['X_val'], label=data['y_val_cont'],
                       feature_name=feat_names, free_raw_data=False)

    params = {
        'objective': 'regression', 'metric': 'mae',
        'num_leaves': 31, 'learning_rate': 0.01, 'max_depth': 5,
        'min_child_samples': 100, 'feature_fraction': 0.7,
        'bagging_fraction': 0.8, 'bagging_freq': 5,
        'reg_alpha': 1.0, 'reg_lambda': 1.0,
        'verbosity': -1, 'n_jobs': -1, 'seed': 42,
    }

    eval_result = {}
    model = lgb.train(
        params, dtrain, num_boost_round=300,
        valid_sets=[dval], valid_names=['val'],
        callbacks=[
            lgb.log_evaluation(period=0),
            lgb.record_evaluation(eval_result),
        ],
    )

    # Test
    y_pred = model.predict(data['X_test'])
    y_te = data['y_test']
    # AUC using regression as ranker
    desc = np.argsort(y_pred)[::-1]
    yt_s = y_te[desc]
    di = np.where(np.diff(y_pred[desc]))[0]
    ti = np.append(di, len(y_te) - 1)
    tps = np.cumsum(yt_s)[ti]
    fps = ti + 1 - tps
    tps = np.concatenate(([0], tps))
    fps = np.concatenate(([0], fps))
    fpr = fps / max(fps[-1], 1)
    tpr = tps / max(tps[-1], 1)
    test_auc = float(np.sum((tpr[:-1] + tpr[1:]) / 2 * np.diff(fpr)))

    # Bear-specific
    bear_mask = data['test_bear']
    if bear_mask.sum() > 100:
        y_pred_bear = model.predict(data['X_test'][bear_mask])
        yt_bear = y_te[bear_mask]
        desc = np.argsort(y_pred_bear)[::-1]
        yt_s = yt_bear[desc]
        di = np.where(np.diff(y_pred_bear[desc]))[0]
        ti = np.append(di, len(yt_bear) - 1)
        tps = np.cumsum(yt_s)[ti]
        fps = ti + 1 - tps
        tps = np.concatenate(([0], tps))
        fps = np.concatenate(([0], fps))
        fpr = fps / max(fps[-1], 1)
        tpr = tps / max(tps[-1], 1)
        bear_auc = float(np.sum((tpr[:-1] + tpr[1:]) / 2 * np.diff(fpr)))
        print(f"  Bear test AUC: {bear_auc:.4f}")

    corr = np.corrcoef(y_pred, data['y_test_cont'])[0, 1]
    print(f"  Test AUC (as ranker): {test_auc:.4f}")
    print(f"  Correlation: {corr:.4f}")

    importance = model.feature_importance(importance_type='gain')
    feat_imp = sorted(zip(feat_names, importance), key=lambda x: x[1], reverse=True)
    print(f"\n  Feature Importance TOP 20:")
    for fname, imp in feat_imp[:20]:
        print(f"    {fname:30s} {imp:.1f}")

    def_model_path = os.path.join(DATA_DIR, 'ml_model_defense.txt')
    model.save_model(def_model_path)
    print(f"  Defense model saved: {def_model_path}")

    return {
        'model': model,
        'test_auc': test_auc,
        'feature_importance': feat_imp,
    }


def main():
    t0 = time.time()

    print("=" * 60)
    print("ML Model Training V3 - Regime Specialists")
    print("=" * 60)
    print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    data = load_data()

    # 1. Bear specialist
    bear_result = train_bear_specialist(data)

    # 2. Defense regression
    def_result = train_defense_model(data)

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"V3 Training Complete ({elapsed:.0f}s)")
    print(f"{'='*60}")
    print(f"  General model: {os.path.join(DATA_DIR, 'ml_model_best.txt')}")
    print(f"  Bear model: {os.path.join(DATA_DIR, 'ml_model_bear.txt')}")
    print(f"  Defense model: {os.path.join(DATA_DIR, 'ml_model_defense.txt')}")
    print(f"\n  Run ml_backtest.py to evaluate regime-switching strategy")


if __name__ == '__main__':
    main()
