# Dealer-neutral / MM top-profit daily + weekly chronological audit

Generated: 2026-08-12T14:13:59.564198+00:00

These are London volume-only proxies, not Net Dealer, PML, OI max pain, or a market-maker book.

## Coverage

- QQQ: {'state': 'OK', 'dates': 91, 'iv_rows': 43890, 'iv_solved': 36707, 'iv_solve_pct': 83.63}
- NVDA: {'state': 'OK', 'dates': 91, 'iv_rows': 12548, 'iv_solved': 10364, 'iv_solve_pct': 82.59}
- SMH: {'state': 'OK', 'dates': 91, 'iv_rows': 25467, 'iv_solved': 22702, 'iv_solve_pct': 89.14}
- MU: {'state': 'OK', 'dates': 91, 'iv_rows': 37414, 'iv_solved': 31906, 'iv_solve_pct': 85.28}
- AAPL: {'state': 'OK', 'dates': 91, 'iv_rows': 12636, 'iv_solved': 10304, 'iv_solve_pct': 81.54}
- MSFT: {'state': 'MISSING', 'why': 'options parquet or underlying daily bars absent'}

## DN_DAY_VOL

- Verdict: **DATA_INSUFFICIENT**
- Preliminary: **NO_POSITIVE_TRAIN_EDGE**
- Train/OOS dates: 54 / 36
- Frozen train cell: `{'threshold_pct': 0.25, 'n': 43, 'date_clusters': 33, 'effective_n': 34.98, 'intra_date_rho': 0.7568, 'touch_rate': 0.6047, 'matched_null_rate': 0.6279, 'touch_edge': -0.0233, 'cluster_sign_p': 1.0, 'positive_dates': 3, 'negative_dates': 4, 'barrier_resolved': 38, 'barrier_win_rate': 0.1316, 'barrier_wilson_lb': 0.0575, 'barrier_expectancy_lb_r': -0.8849, 'bh_fdr_05': False}`
- Frozen OOS: `{'threshold_pct': 0.25, 'n': 28, 'date_clusters': 20, 'effective_n': 20.48, 'intra_date_rho': 0.9181, 'touch_rate': 0.6786, 'matched_null_rate': 0.6429, 'touch_edge': 0.0357, 'cluster_sign_p': 1.0, 'positive_dates': 2, 'negative_dates': 1, 'barrier_resolved': 25, 'barrier_win_rate': 0.2, 'barrier_wilson_lb': 0.0886, 'barrier_expectancy_lb_r': -0.8228}`

## DN_WEEK_VOL

- Verdict: **DATA_INSUFFICIENT**
- Preliminary: **NO_POSITIVE_TRAIN_EDGE**
- Train/OOS dates: 46 / 32
- Frozen train cell: `{'threshold_pct': 0.25, 'n': 28, 'date_clusters': 21, 'effective_n': 21.79, 'intra_date_rho': 0.8542, 'touch_rate': 0.5714, 'matched_null_rate': 0.6429, 'touch_edge': -0.0714, 'cluster_sign_p': 0.625, 'positive_dates': 1, 'negative_dates': 3, 'barrier_resolved': 26, 'barrier_win_rate': 0.0385, 'barrier_wilson_lb': 0.0068, 'barrier_expectancy_lb_r': -0.9864, 'bh_fdr_05': False}`
- Frozen OOS: `{'threshold_pct': 0.25, 'n': 25, 'date_clusters': 17, 'effective_n': 18.79, 'intra_date_rho': 0.7024, 'touch_rate': 0.72, 'matched_null_rate': 0.68, 'touch_edge': 0.04, 'cluster_sign_p': 1.0, 'positive_dates': 2, 'negative_dates': 1, 'barrier_resolved': 21, 'barrier_win_rate': 0.2381, 'barrier_wilson_lb': 0.1063, 'barrier_expectancy_lb_r': -0.7874}`

## MM_TOP_DAY_VOL

- Verdict: **DATA_INSUFFICIENT**
- Preliminary: **TRAIN_EDGE_NOT_SIGNIFICANT**
- Train/OOS dates: 54 / 36
- Frozen train cell: `{'threshold_pct': 0.25, 'n': 52, 'date_clusters': 38, 'effective_n': 39.6, 'intra_date_rho': 0.8495, 'touch_rate': 0.6923, 'matched_null_rate': 0.6731, 'touch_edge': 0.0192, 'cluster_sign_p': 1.0, 'positive_dates': 3, 'negative_dates': 2, 'barrier_resolved': 39, 'barrier_win_rate': 0.2308, 'barrier_wilson_lb': 0.1265, 'barrier_expectancy_lb_r': -0.7471, 'bh_fdr_05': False}`
- Frozen OOS: `{'threshold_pct': 0.25, 'n': 23, 'date_clusters': 16, 'effective_n': 16.48, 'intra_date_rho': 0.9042, 'touch_rate': 0.6522, 'matched_null_rate': 0.6087, 'touch_edge': 0.0435, 'cluster_sign_p': 1.0, 'positive_dates': 1, 'negative_dates': 0, 'barrier_resolved': 14, 'barrier_win_rate': 0.2143, 'barrier_wilson_lb': 0.0757, 'barrier_expectancy_lb_r': -0.8486}`

## MM_TOP_WEEK_VOL

- Verdict: **DATA_INSUFFICIENT**
- Preliminary: **NO_POSITIVE_TRAIN_EDGE**
- Train/OOS dates: 46 / 32
- Frozen train cell: `{'threshold_pct': 0.5, 'n': 75, 'date_clusters': 38, 'effective_n': 46.91, 'intra_date_rho': 0.615, 'touch_rate': 0.6667, 'matched_null_rate': 0.68, 'touch_edge': -0.0133, 'cluster_sign_p': 1.0, 'positive_dates': 7, 'negative_dates': 8, 'barrier_resolved': 60, 'barrier_win_rate': 0.15, 'barrier_wilson_lb': 0.081, 'barrier_expectancy_lb_r': -0.8381, 'bh_fdr_05': False}`
- Frozen OOS: `{'threshold_pct': 0.5, 'n': 47, 'date_clusters': 24, 'effective_n': 30.93, 'intra_date_rho': 0.542, 'touch_rate': 0.6596, 'matched_null_rate': 0.7021, 'touch_edge': -0.0426, 'cluster_sign_p': 1.0, 'positive_dates': 3, 'negative_dates': 3, 'barrier_resolved': 38, 'barrier_win_rate': 0.1053, 'barrier_wilson_lb': 0.0417, 'barrier_expectancy_lb_r': -0.9166}`

## Guard

60 train dates + 40 untouched OOS dates + BH-FDR train + positive OOS matched-null edge + positive OOS Wilson-LB expectancy
