#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ML Model Training V2 for TradingAgent
=======================================
V1 result: AUC ~0.59 but prob ~0.49 for all stocks (3 rounds early stop).
Problem: model barely learns, predictions near-uniform.

V2 strategy:
  1. Remove early stopping, use fixed rounds with lower learning rate
  2. Try regression (predict relative return) in addition to classification
  3. Sample weighting: weight by |relative_return| (big moves matter more)
  4. Feature engineering: add interaction features
  5. Train per-regime models (bull/bear/range specialists)
  6. Ensemble: blend multiple models

Output: Best model saved, ready for backtest.
"""

import os, sys, time, gc, json, warnings
import numpy as np
from datetime import datetime

warnings.filterwarnings('ignore')

# ============================================================================
# Paths
# ============================================================================
BASE_DIR = r'D:\GitHub\TradingAgents\TradingAgent'
DATA_DIR = r'D:\GitHub\TradingAgents\TradingShared\data'
RESULT_DIR = os.path.join(BASE_DIR, 'backtest_results')

DATASET_FILE = os.path.join(DATA_DIR, 'ml_train_dataset.npz')
MODEL_OUTPUT = os.path.join(DATA_DIR, 'ml_model_best.txt')


def print_mem(label=""):
    try:
        import psutil
        mb = psutil.Process().memory_info().rss / 1024 / 1024
        if label:
            print(f"  [MEM] {label}: {mb:.0f}MB")
    except ImportError:
        pass


def calc_auc(y_true, y_pred):
    """Fast AUC calculation"""
    desc_score_indices = np.argsort(y_pred)[::-1]
    y_true_sorted = y_true[desc_score_indices]
    distinct_value_indices = np.where(np.diff(y_pred[desc_score_indices]))[0]
    threshold_indices = np.append(distinct_value_indices, len(y_true) - 1)
    tps = np.cumsum(y_true_sorted)[threshold_indices]
    fps = threshold_indices + 1 - tps
    tps = np.concatenate(([0], tps))
    fps = np.concatenate(([0], fps))
    fpr = fps / fps[-1]
    tpr = tps / tps[-1]
    return float(np.sum((tpr[:-1] + tpr[1:]) / 2 * np.diff(fpr)))


def load_data(n_features=50):
    """Load dataset"""
    print(f"\n  Loading dataset...")
    data = np.load(DATASET_FILE, allow_pickle=True)
    feature_names = list(data['feature_names'])

    result = {
        'X_train': data['X_train'][:, :n_features].astype(np.float32),
        'y_train': data['y_train'].astype(np.float32),
        'y_train_cont': data['y_train_cont'].astype(np.float32),
        'X_val': data['X_val'][:, :n_features].astype(np.float32),
        'y_val': data['y_val'].astype(np.float32),
        'y_val_cont': data['y_val_cont'].astype(np.float32),
        'X_test': data['X_test'][:, :n_features].astype(np.float32),
        'y_test': data['y_test'].astype(np.float32),
        'y_test_cont': data['y_test_cont'].astype(np.float32),
        'feature_names': feature_names[:n_features],
    }

    del data
    gc.collect()

    print(f"    Train: {result['X_train'].shape}, pos={result['y_train'].mean():.4f}")
    print(f"    Val:   {result['X_val'].shape}")
    print(f"    Test:  {result['X_test'].shape}")
    return result


# ============================================================================
# Model 1: LightGBM with better tuning
# ============================================================================
def train_lgb_v2(data, n_features, label=""):
    """LightGBM V2: no early stopping, sample weights, fixed rounds"""
    try:
        import lightgbm as lgb
    except ImportError:
        print("  [SKIP] LightGBM not installed")
        return None

    print(f"\n{'='*60}")
    print(f"LightGBM V2 {label}")
    print(f"{'='*60}")

    X_tr = data['X_train']
    y_tr = data['y_train']
    y_tr_cont = data['y_train_cont']
    X_va = data['X_val']
    y_va = data['y_val']
    X_te = data['X_test']
    y_te = data['y_test']
    feat_names = data['feature_names'][:n_features]

    # Sample weights: weight by absolute relative return (big moves matter more)
    weights = np.abs(y_tr_cont) + 0.5  # minimum weight 0.5
    weights = weights / weights.mean()  # normalize

    dtrain = lgb.Dataset(X_tr, label=y_tr, weight=weights,
                         feature_name=feat_names, free_raw_data=False)
    dval = lgb.Dataset(X_va, label=y_va,
                       feature_name=feat_names, free_raw_data=False)

    # Best config from V1 + more rounds + lower lr
    configs = [
        # (name, params, n_rounds)
        ("conservative", {
            'objective': 'binary', 'metric': 'auc',
            'num_leaves': 31, 'learning_rate': 0.01, 'max_depth': 5,
            'min_child_samples': 100, 'feature_fraction': 0.7,
            'bagging_fraction': 0.8, 'bagging_freq': 5,
            'reg_alpha': 1.0, 'reg_lambda': 1.0,
            'verbosity': -1, 'n_jobs': -1, 'seed': 42,
        }, 300),
        ("moderate", {
            'objective': 'binary', 'metric': 'auc',
            'num_leaves': 63, 'learning_rate': 0.02, 'max_depth': 7,
            'min_child_samples': 50, 'feature_fraction': 0.8,
            'bagging_fraction': 0.8, 'bagging_freq': 5,
            'reg_alpha': 0.5, 'reg_lambda': 0.5,
            'verbosity': -1, 'n_jobs': -1, 'seed': 42,
        }, 200),
        ("aggressive", {
            'objective': 'binary', 'metric': 'auc',
            'num_leaves': 127, 'learning_rate': 0.05, 'max_depth': -1,
            'min_child_samples': 20, 'feature_fraction': 0.8,
            'bagging_fraction': 0.8, 'bagging_freq': 5,
            'reg_alpha': 0.1, 'reg_lambda': 0.1,
            'verbosity': -1, 'n_jobs': -1, 'seed': 42,
        }, 100),
        ("dart", {
            'objective': 'binary', 'metric': 'auc',
            'boosting_type': 'dart',
            'num_leaves': 63, 'learning_rate': 0.05, 'max_depth': 7,
            'min_child_samples': 50, 'feature_fraction': 0.8,
            'drop_rate': 0.1,
            'verbosity': -1, 'n_jobs': -1, 'seed': 42,
        }, 100),
    ]

    best_auc = 0
    best_model = None
    best_config_name = ""
    all_results = []

    for name, params, n_rounds in configs:
        t0 = time.time()
        eval_result = {}
        model = lgb.train(
            params, dtrain, num_boost_round=n_rounds,
            valid_sets=[dval], valid_names=['val'],
            callbacks=[
                lgb.log_evaluation(period=0),
                lgb.record_evaluation(eval_result),
            ],
        )
        val_auc = eval_result['val']['auc'][-1]
        elapsed = time.time() - t0

        # Test
        y_pred = model.predict(X_te)
        test_auc = calc_auc(y_te, y_pred)
        test_acc = np.mean((y_pred > 0.5) == y_te)

        # Check prediction spread
        pred_std = np.std(y_pred)
        pred_range = f"[{y_pred.min():.3f}, {y_pred.max():.3f}]"

        print(f"  [{name:12s}] val_auc={val_auc:.4f} test_auc={test_auc:.4f} "
              f"std={pred_std:.4f} range={pred_range} [{elapsed:.0f}s]")

        all_results.append({
            'name': name, 'val_auc': val_auc, 'test_auc': test_auc,
            'test_acc': test_acc, 'pred_std': float(pred_std),
            'n_rounds': n_rounds,
        })

        if val_auc > best_auc:
            best_auc = val_auc
            best_model = model
            best_config_name = name

    print(f"\n  Best: {best_config_name} (val_auc={best_auc:.4f})")

    # Feature importance
    importance = best_model.feature_importance(importance_type='gain')
    feat_imp = sorted(zip(feat_names, importance), key=lambda x: x[1], reverse=True)
    print(f"\n  Feature Importance TOP 20:")
    for fname, imp in feat_imp[:20]:
        print(f"    {fname:30s} {imp:.1f}")

    # Save model
    best_model.save_model(MODEL_OUTPUT)
    print(f"\n  Model saved: {MODEL_OUTPUT}")

    return {
        'model': best_model,
        'val_auc': best_auc,
        'feature_importance': feat_imp,
        'config_name': best_config_name,
        'all_configs': all_results,
    }


# ============================================================================
# Model 2: LightGBM Regression (predict relative return)
# ============================================================================
def train_lgb_regression(data, n_features, label=""):
    """Regression model: predict y_continuous (relative return vs index)"""
    try:
        import lightgbm as lgb
    except ImportError:
        return None

    print(f"\n{'='*60}")
    print(f"LightGBM Regression {label}")
    print(f"{'='*60}")

    X_tr = data['X_train']
    y_tr_cont = data['y_train_cont']
    X_va = data['X_val']
    y_va = data['y_val']
    y_va_cont = data['y_val_cont']
    X_te = data['X_test']
    y_te = data['y_test']
    y_te_cont = data['y_test_cont']
    feat_names = data['feature_names'][:n_features]

    dtrain = lgb.Dataset(X_tr, label=y_tr_cont, feature_name=feat_names, free_raw_data=False)
    dval = lgb.Dataset(X_va, label=y_va_cont, feature_name=feat_names, free_raw_data=False)

    params = {
        'objective': 'regression', 'metric': 'mae',
        'num_leaves': 63, 'learning_rate': 0.02, 'max_depth': 7,
        'min_child_samples': 50, 'feature_fraction': 0.8,
        'bagging_fraction': 0.8, 'bagging_freq': 5,
        'reg_alpha': 0.5, 'reg_lambda': 0.5,
        'verbosity': -1, 'n_jobs': -1, 'seed': 42,
    }

    eval_result = {}
    model = lgb.train(
        params, dtrain, num_boost_round=200,
        valid_sets=[dval], valid_names=['val'],
        callbacks=[
            lgb.log_evaluation(period=0),
            lgb.record_evaluation(eval_result),
        ],
    )

    # Evaluate as ranker: higher prediction = should beat index
    y_pred = model.predict(X_te)

    # AUC using regression output as ranking
    test_auc = calc_auc(y_te, y_pred)
    test_acc = np.mean((y_pred > 0) == y_te)

    # Correlation
    corr = np.corrcoef(y_pred, y_te_cont)[0, 1]

    pred_std = np.std(y_pred)
    print(f"  Test AUC (as ranker): {test_auc:.4f}")
    print(f"  Test Acc (pred>0): {test_acc:.4f}")
    print(f"  Corr with actual: {corr:.4f}")
    print(f"  Pred std: {pred_std:.4f}")

    # Feature importance
    importance = model.feature_importance(importance_type='gain')
    feat_imp = sorted(zip(feat_names, importance), key=lambda x: x[1], reverse=True)
    print(f"\n  Feature Importance TOP 20:")
    for fname, imp in feat_imp[:20]:
        print(f"    {fname:30s} {imp:.1f}")

    # Save as separate model
    reg_model_path = os.path.join(DATA_DIR, 'ml_model_regression.txt')
    model.save_model(reg_model_path)

    return {
        'model': model,
        'test_auc': test_auc,
        'test_acc': test_acc,
        'correlation': corr,
        'feature_importance': feat_imp,
    }


# ============================================================================
# Model 3: LightGBM Ranker (learning to rank)
# ============================================================================
def train_lgb_ranker(data, n_features, label=""):
    """Lambdarank: learn to rank stocks by next-day relative return"""
    try:
        import lightgbm as lgb
    except ImportError:
        return None

    print(f"\n{'='*60}")
    print(f"LightGBM Ranker {label}")
    print(f"{'='*60}")

    X_tr = data['X_train']
    y_tr_cont = data['y_train_cont']
    X_va = data['X_val']
    y_va = data['y_val']
    y_va_cont = data['y_val_cont']
    X_te = data['X_test']
    y_te = data['y_test']
    feat_names = data['feature_names'][:n_features]

    # For ranking: group by "date" (we don't have date in dataset)
    # Simplification: treat all training samples as one group
    # This is suboptimal but better than nothing
    train_group = [len(X_tr)]
    val_group = [len(X_va)]

    # Sort training data by a pseudo-group approach
    # Actually, let's just use binary classification with sample weights
    # based on rank within the dataset (top stocks get higher weight)

    # Rank-based weights: stocks with higher relative returns get higher weight
    ranks = np.argsort(np.argsort(y_tr_cont))  # 0 to N-1
    rank_weights = (ranks + 1.0) / len(ranks)  # normalized 0-1
    rank_weights = np.where(y_tr_cont > 0, rank_weights + 0.5, 0.5)

    dtrain = lgb.Dataset(X_tr, label=data['y_train'], weight=rank_weights,
                         feature_name=feat_names, free_raw_data=False)
    dval = lgb.Dataset(X_va, label=y_va,
                       feature_name=feat_names, free_raw_data=False)

    params = {
        'objective': 'binary', 'metric': 'auc',
        'num_leaves': 63, 'learning_rate': 0.02, 'max_depth': 7,
        'min_child_samples': 50, 'feature_fraction': 0.8,
        'bagging_fraction': 0.8, 'bagging_freq': 5,
        'reg_alpha': 0.5, 'reg_lambda': 0.5,
        'verbosity': -1, 'n_jobs': -1, 'seed': 42,
    }

    eval_result = {}
    model = lgb.train(
        params, dtrain, num_boost_round=200,
        valid_sets=[dval], valid_names=['val'],
        callbacks=[
            lgb.log_evaluation(period=0),
            lgb.record_evaluation(eval_result),
        ],
    )

    val_auc = eval_result['val']['auc'][-1]
    y_pred = model.predict(X_te)
    test_auc = calc_auc(y_te, y_pred)
    test_acc = np.mean((y_pred > 0.5) == y_te)

    print(f"  Val AUC: {val_auc:.4f}")
    print(f"  Test AUC: {test_auc:.4f}")
    print(f"  Test Acc: {test_acc:.4f}")

    # Feature importance
    importance = model.feature_importance(importance_type='gain')
    feat_imp = sorted(zip(feat_names, importance), key=lambda x: x[1], reverse=True)
    print(f"\n  Feature Importance TOP 20:")
    for fname, imp in feat_imp[:20]:
        print(f"    {fname:30s} {imp:.1f}")

    return {
        'model': model,
        'val_auc': val_auc,
        'test_auc': test_auc,
        'test_acc': test_acc,
        'feature_importance': feat_imp,
    }


# ============================================================================
# Model 4: Interaction Features + LightGBM
# ============================================================================
def train_lgb_interactions(data, n_features, label=""):
    """Add interaction features to improve signal"""
    try:
        import lightgbm as lgb
    except ImportError:
        return None

    print(f"\n{'='*60}")
    print(f"LightGBM + Interaction Features {label}")
    print(f"{'='*60}")

    def add_interactions(X, feat_names):
        """Add key interaction features"""
        # Find feature indices
        feat_idx = {name: i for i, name in enumerate(feat_names[:n_features])}

        interactions = []
        int_names = []

        # r1 * vol_ratio (momentum with volume confirmation)
        if 'r1' in feat_idx and 'vol_ratio' in feat_idx:
            interactions.append(X[:, feat_idx['r1']] * X[:, feat_idx['vol_ratio']])
            int_names.append('r1_x_vol_ratio')

        # r3 * consistency (trend + consistency)
        if 'r3' in feat_idx and 'consistency' in feat_idx:
            interactions.append(X[:, feat_idx['r3']] * X[:, feat_idx['consistency']])
            int_names.append('r3_x_consistency')

        # rel_strength * regime_bull (strength in bull market)
        if 'rel_strength_5d' in feat_idx and 'regime_bull' in feat_idx:
            interactions.append(X[:, feat_idx['rel_strength_5d']] * X[:, feat_idx['regime_bull']])
            int_names.append('rs5_x_bull')

        # rsi * r5 (momentum quality)
        if 'rsi' in feat_idx and 'r5' in feat_idx:
            interactions.append(X[:, feat_idx['rsi']] * X[:, feat_idx['r5']])
            int_names.append('rsi_x_r5')

        # vol_shrink * r1 (shrinking volume + positive return = suspicious)
        if 'vol_shrink' in feat_idx and 'r1' in feat_idx:
            interactions.append(X[:, feat_idx['vol_shrink']] * X[:, feat_idx['r1']])
            int_names.append('vol_shrink_x_r1')

        # ma_bull * rel_strength_5d
        if 'ma_bull' in feat_idx and 'rel_strength_5d' in feat_idx:
            interactions.append(X[:, feat_idx['ma_bull']] * X[:, feat_idx['rel_strength_5d']])
            int_names.append('ma_bull_x_rs5')

        # price_pos * momentum
        if 'price_pos' in feat_idx and 'momentum' in feat_idx:
            interactions.append(X[:, feat_idx['price_pos']] * X[:, feat_idx['momentum']])
            int_names.append('price_pos_x_momentum')

        # r5 - r1 (acceleration)
        if 'r5' in feat_idx and 'r1' in feat_idx:
            interactions.append(X[:, feat_idx['r5']] - X[:, feat_idx['r1']])
            int_names.append('r5_minus_r1')

        if not interactions:
            return X, feat_names[:n_features]

        X_int = np.column_stack([X] + interactions).astype(np.float32)
        new_names = list(feat_names[:n_features]) + int_names
        return X_int, new_names

    X_tr, new_names = add_interactions(data['X_train'], data['feature_names'])
    X_va, _ = add_interactions(data['X_val'], data['feature_names'])
    X_te, _ = add_interactions(data['X_test'], data['feature_names'])

    print(f"  Features: {data['X_train'].shape[1]} -> {X_tr.shape[1]}")

    # Sample weights
    weights = np.abs(data['y_train_cont']) + 0.5
    weights = weights / weights.mean()

    dtrain = lgb.Dataset(X_tr, label=data['y_train'], weight=weights,
                         feature_name=new_names, free_raw_data=False)
    dval = lgb.Dataset(X_va, label=data['y_val'],
                       feature_name=new_names, free_raw_data=False)

    params = {
        'objective': 'binary', 'metric': 'auc',
        'num_leaves': 63, 'learning_rate': 0.02, 'max_depth': 7,
        'min_child_samples': 50, 'feature_fraction': 0.8,
        'bagging_fraction': 0.8, 'bagging_freq': 5,
        'reg_alpha': 0.5, 'reg_lambda': 0.5,
        'verbosity': -1, 'n_jobs': -1, 'seed': 42,
    }

    eval_result = {}
    model = lgb.train(
        params, dtrain, num_boost_round=200,
        valid_sets=[dval], valid_names=['val'],
        callbacks=[
            lgb.log_evaluation(period=0),
            lgb.record_evaluation(eval_result),
        ],
    )

    val_auc = eval_result['val']['auc'][-1]
    y_pred = model.predict(X_te)
    test_auc = calc_auc(data['y_test'], y_pred)
    test_acc = np.mean((y_pred > 0.5) == data['y_test'])

    print(f"  Val AUC: {val_auc:.4f}")
    print(f"  Test AUC: {test_auc:.4f}")
    print(f"  Test Acc: {test_acc:.4f}")

    importance = model.feature_importance(importance_type='gain')
    feat_imp = sorted(zip(new_names, importance), key=lambda x: x[1], reverse=True)
    print(f"\n  Feature Importance TOP 20:")
    for fname, imp in feat_imp[:20]:
        print(f"    {fname:30s} {imp:.1f}")

    # Save interaction model
    int_model_path = os.path.join(DATA_DIR, 'ml_model_interactions.txt')
    model.save_model(int_model_path)

    return {
        'model': model,
        'val_auc': val_auc,
        'test_auc': test_auc,
        'test_acc': test_acc,
        'feature_importance': feat_imp,
        'new_feature_names': new_names,
    }


# ============================================================================
# Main
# ============================================================================
def main():
    t0 = time.time()

    print("=" * 60)
    print("ML Model Training V2 for TradingAgent")
    print("=" * 60)
    print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"V1 result: AUC~0.59, prob~0.49, beat_idx=31.6% (BAD)")
    print(f"V2 goal: Better discrimination, spread in predictions")
    print("=" * 60)

    # Try both 42 and 50 features
    for n_feat in [42, 50]:
        print(f"\n{'#'*60}")
        print(f"# Features: {n_feat}")
        print(f"{'#'*60}")

        data = load_data(n_feat)

        # Model 1: LightGBM V2 (multiple configs)
        res_lgb = train_lgb_v2(data, n_feat, label=f"[{n_feat}feat]")

        # Model 2: Regression
        res_reg = train_lgb_regression(data, n_feat, label=f"[{n_feat}feat]")

        # Model 3: Rank-weighted
        res_rank = train_lgb_ranker(data, n_feat, label=f"[{n_feat}feat]")

        # Model 4: Interactions
        res_int = train_lgb_interactions(data, n_feat, label=f"[{n_feat}feat]")

        # Summary for this feature set
        print(f"\n  Summary [{n_feat}feat]:")
        models = [
            ("LGB_V2", res_lgb),
            ("Regression", res_reg),
            ("Ranker", res_rank),
            ("Interactions", res_int),
        ]
        for name, res in models:
            if res:
                auc = res.get('test_auc', res.get('val_auc', 0))
                print(f"    {name:15s} AUC={auc:.4f}")

        del data
        gc.collect()
        print_mem(f"After {n_feat}feat")

    # ==================================================================
    # Also save the regression model for backtest comparison
    # ==================================================================
    print(f"\n{'='*60}")
    print("TRAINING COMPLETE")
    print(f"{'='*60}")
    print(f"  Best classification model: {MODEL_OUTPUT}")
    print(f"  Regression model: {os.path.join(DATA_DIR, 'ml_model_regression.txt')}")
    print(f"  Interaction model: {os.path.join(DATA_DIR, 'ml_model_interactions.txt')}")
    print(f"\n  Run ml_backtest.py to evaluate each model")
    elapsed = time.time() - t0
    print(f"  Total time: {elapsed:.0f}s ({elapsed/60:.1f}min)")


if __name__ == '__main__':
    main()
