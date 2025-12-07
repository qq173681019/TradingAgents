# Headless verification for ticker 600519
# Instantiates AShareAnalyzerGUI with no GUI and runs single-stock and batch score paths.
import json
import traceback

from a_share_gui_compatible import AShareAnalyzerGUI


def safe_get(d, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d:
            return d[k]
    return default


def run():
    ticker = '600519'
    print(f"Headless verification for {ticker}")

    try:
        analyzer = AShareAnalyzerGUI(None)
        analyzer.llm_model = 'none'

        print('\n-- Generating investment advice (predictions) --')
        try:
            short_pred, med_pred, long_pred = analyzer.generate_investment_advice(ticker)
        except Exception as e:
            print('generate_investment_advice failed:')
            traceback.print_exc()
            short_pred, med_pred, long_pred = ({}, {}, {})

        print('Short prediction:', short_pred)
        print('Medium prediction:', med_pred)
        print('Long prediction:', long_pred)

        # Extract raw numerical scores (these may be "raw" scale from heuristics or already normalized)
        short_tech = safe_get(short_pred, 'technical_score', 'technical_score') or 0
        short_score_norm = safe_get(short_pred, 'score', default=None)

        medium_total = safe_get(med_pred, 'total_score', 'total_score') or 0
        medium_score_norm = safe_get(med_pred, 'score', default=None)

        long_fund = safe_get(long_pred, 'fundamental_score', 'fundamental_score') or 0
        long_score_norm = safe_get(long_pred, 'score', default=None)

        print(f"\nExtracted values:\n short_tech={short_tech} (norm:{short_score_norm})\n medium_total={medium_total} (norm:{medium_score_norm})\n long_fund={long_fund} (norm:{long_score_norm})")

        # Compare calculate_comprehensive_score with both input types
        try:
            comp_from_raw = analyzer.calculate_comprehensive_score(short_tech, medium_total, long_fund, input_type='raw')
        except Exception:
            comp_from_raw = None
        try:
            # If norm fields exist, use them; otherwise try converting raw->1-10 by using input_type='raw'
            if short_score_norm is not None or medium_score_norm is not None or long_score_norm is not None:
                s = short_score_norm if short_score_norm is not None else (5.0 + short_tech * 0.5)
                m = medium_score_norm if medium_score_norm is not None else (5.0 + medium_total * 0.5)
                l = long_score_norm if long_score_norm is not None else (5.0 + long_fund * 0.5)
                comp_from_norm = analyzer.calculate_comprehensive_score(s, m, l, input_type='normalized')
            else:
                comp_from_norm = None
        except Exception:
            comp_from_norm = None

        print(f"\nCalculated comprehensive scores:\n - from_raw (raw->1-10 internally): {comp_from_raw}\n - from_norm (direct 1-10): {comp_from_norm}")

        # Run single-stock algorithmic path
        print('\n-- Running single-stock algorithmic calculation (_calculate_stock_score_algorithmic) --')
        try:
            calc_result = analyzer._calculate_stock_score_algorithmic(ticker)
            print('Algorithmic calc_result:', calc_result)
        except Exception:
            print('Algorithmic calc failed:')
            traceback.print_exc()
            calc_result = None

        # Run batch score path
        print('\n-- Running batch scoring path (get_stock_score_for_batch) --')
        try:
            batch_score = analyzer.get_stock_score_for_batch(ticker)
            print('Batch score (get_stock_score_for_batch) result:', batch_score)
        except Exception:
            print('get_stock_score_for_batch failed:')
            traceback.print_exc()
            batch_score = None

        # If calc_result present, print its overall_score
        if calc_result and isinstance(calc_result, dict):
            print('\nSingle-stock returned overall_score (calc_result["overall_score"]):', calc_result.get('overall_score'))

        # If analyzer has batch_scores entry for ticker, print it
        bs = analyzer.batch_scores.get(ticker)
        print('\nAnalyzer.batch_scores entry for ticker:', bs)

        # Summary comparison
        print('\n-- Summary --')
        print('comp_from_raw:', comp_from_raw)
        print('comp_from_norm:', comp_from_norm)
        print('single-stock overall_score (calc_result):', calc_result.get('overall_score') if isinstance(calc_result, dict) else None)
        print('batch_score (get_stock_score_for_batch):', batch_score)
        print('batch_scores[ticker]:', bs)

    except Exception:
        print('Headless verification failed:')
        traceback.print_exc()


if __name__ == '__main__':
    run()
