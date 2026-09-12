"""
Step 3: Math & Normalization (Analytics Engine).

Считает PHSI Score для компаний, у которых есть и ESG-рейтинг (все 503), и финансовые
рычаги (демо-подвыборка, пока 22 тикера — см. data/financials_demo22.csv и заметку в
README про блокировку bulk-доступа к Yahoo Finance/SEC в этой сети).

Пайплайн для каждого блока метрик:
  1. Winsorize по всей выборке (5-й / 95-й перцентиль) — режем выбросы вроде WDC
     с 71.88% net margin (разовая история, не операционная норма).
  2. Пропуски: тот же принцип "прагматичного штрафа", что и для ESG — если у компании
     нет метрики (банки/REIT/utilities часто не публикуют Gross Profit или классический
     Capex), ей присваивается 75-й перцентиль ХУДШЕГО направления по сектору.
  3. Z-score ВНУТРИ GICS-сектора (не по всей выборке!) — сравниваем PPG с SHW, а не с Visa.
  4. Направление рисков разворачивается (invert), чтобы "выше z-score = лучше" было
     верно для обоих блоков.
  5. Min-Max в 0-100 и блендинг с весами (60/40 по умолчанию + sensitivity sweep).

  Оговорка: при n=2 на сектор (демо-выборка) percentile/z-score статистически шатки —
  это ожидаемо для PoC и снимается при полном покрытии (503 компании на сектор — десятки).

Запуск: python3 pipeline/scoring.py
"""

import os
import sys
import sqlite3
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FINAL_DB_PATH = os.path.join(ROOT, "sp500_sustainability.db")

# SQLite не читается/не пишется напрямую в этой примонтированной (bridged) папке —
# работаем с локальной копией на диске, в конце синхронизируем обратно (см. build_database.py).
BUILD_DIR = os.path.join(os.path.expanduser("~"), ".phsi_build")
DB_PATH = os.path.join(BUILD_DIR, "sp500_sustainability.db")

WINSOR_LOW, WINSOR_HIGH = 0.05, 0.95
PENALTY_PERCENTILE = 0.75  # тот же "прагматичный штраф", что для ESG

# metric -> (+1 если "больше = лучше", -1 если "больше = хуже/рискованнее")
FINANCIAL_DIRECTION = {
    "profit_margin": +1,
    "fcf_yield": +1,
    "capex_to_revenue": +1,
    "cost_to_revenue": -1,
}
ESG_DIRECTION = {
    "environment_risk_score": -1,
    "governance_risk_score": -1,
    "social_risk_score": -1,
    "controversy_score": -1,
}

WEIGHT_VARIANTS = {
    "60_40": (0.60, 0.40),  # основной вариант
    "50_50": (0.50, 0.50),  # sensitivity sweep
    "70_30": (0.70, 0.30),  # sensitivity sweep
}


def load_joined() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT c.symbol, c.name, c.sector,
               e.environment_risk_score, e.governance_risk_score,
               e.social_risk_score, e.controversy_score, e.is_imputed AS esg_is_imputed,
               f.revenue_musd, f.gross_profit_musd, f.net_income_musd,
               f.market_cap_musd, f.fcf_musd, f.capex_musd
        FROM companies c
        JOIN esg_ratings e ON e.symbol = c.symbol
        JOIN financials f ON f.symbol = c.symbol
        """,
        conn,
    )
    conn.close()
    return df


def compute_financial_ratios(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["profit_margin"] = df["net_income_musd"] / df["revenue_musd"]
    df["cost_to_revenue"] = np.where(
        df["gross_profit_musd"].notna(),
        (df["revenue_musd"] - df["gross_profit_musd"]) / df["revenue_musd"],
        np.nan,
    )
    df["fcf_yield"] = df["fcf_musd"] / df["market_cap_musd"]
    df["capex_to_revenue"] = df["capex_musd"].abs() / df["revenue_musd"]
    return df


def winsorize(df: pd.DataFrame, columns: list) -> pd.DataFrame:
    df = df.copy()
    for col in columns:
        lo, hi = df[col].quantile(WINSOR_LOW), df[col].quantile(WINSOR_HIGH)
        df[col] = df[col].clip(lower=lo, upper=hi)
    return df


def pragmatic_fill(df: pd.DataFrame, columns: list, direction: dict) -> pd.DataFrame:
    """Пропуски -> 75-й перцентиль ХУДШЕГО направления той же сектор-группы."""
    df = df.copy()
    for col in columns:
        was_null = df[col].isna()
        if not was_null.any():
            continue
        # "худшее" направление: если больше=лучше (+1), худший перцентиль — низкий (p25);
        # если больше=хуже (-1), худший перцентиль — высокий (p75).
        q = PENALTY_PERCENTILE if direction[col] == -1 else (1 - PENALTY_PERCENTILE)
        sector_q = df.groupby("sector")[col].transform(lambda s: s.quantile(q))
        df.loc[was_null, col] = sector_q[was_null]
    return df


def sector_zscore(df: pd.DataFrame, columns: list, direction: dict, prefix: str) -> pd.DataFrame:
    df = df.copy()
    for col in columns:
        grp = df.groupby("sector")[col]
        mean, std = grp.transform("mean"), grp.transform("std").replace(0, np.nan)
        z = (df[col] - mean) / std
        z = z.fillna(0.0)  # sector std=0 (n=1 после фильтров) -> нейтральный z
        df[f"{prefix}_{col}_z"] = z * direction[col]
    return df


def blend_subscore(df: pd.DataFrame, z_columns: list, out_col: str) -> pd.DataFrame:
    df = df.copy()
    avg_z = df[z_columns].mean(axis=1)
    # Min-Max по всей демо-выборке в 0-100 (для полной базы — тот же принцип на 503)
    lo, hi = avg_z.min(), avg_z.max()
    df[out_col] = 100 * (avg_z - lo) / (hi - lo) if hi > lo else 50.0
    return df


def compute_phsi(df: pd.DataFrame) -> pd.DataFrame:
    fin_cols = list(FINANCIAL_DIRECTION.keys())
    esg_cols = list(ESG_DIRECTION.keys())

    df = compute_financial_ratios(df)
    df = winsorize(df, fin_cols)
    df = pragmatic_fill(df, fin_cols, FINANCIAL_DIRECTION)   # esg уже пропатчен в build_database.py
    df = sector_zscore(df, fin_cols, FINANCIAL_DIRECTION, prefix="fin")
    df = sector_zscore(df, esg_cols, ESG_DIRECTION, prefix="esg")

    df = blend_subscore(df, [f"fin_{c}_z" for c in fin_cols], "financial_subscore")
    df = blend_subscore(df, [f"esg_{c}_z" for c in esg_cols], "esg_subscore")

    results = []
    for variant, (fw, ew) in WEIGHT_VARIANTS.items():
        v = df.copy()
        v["weight_variant"] = variant
        v["fin_weight"], v["esg_weight"] = fw, ew
        v["phsi_score"] = fw * v["financial_subscore"] + ew * v["esg_subscore"]
        v["rank_overall"] = v["phsi_score"].rank(ascending=False, method="min").astype(int)
        v["rank_in_sector"] = v.groupby("sector")["phsi_score"].rank(ascending=False, method="min").astype(int)
        results.append(v)

    return pd.concat(results, ignore_index=True)


def write_scores(df: pd.DataFrame):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM phsi_scores")  # идемпотентный пересчёт
    out = df[[
        "symbol", "sector", "weight_variant", "fin_weight", "esg_weight",
        "financial_subscore", "esg_subscore", "phsi_score", "rank_overall", "rank_in_sector",
    ]].copy()
    out.to_sql("phsi_scores", conn, if_exists="append", index=False)
    conn.commit()
    conn.close()


def print_summary(df: pd.DataFrame):
    main = df[df["weight_variant"] == "60_40"].sort_values("phsi_score", ascending=False)
    print("\n=== PHSI Score (60/40, demo — 22 tickers) ===")
    print(
        main[["symbol", "sector", "financial_subscore", "esg_subscore", "phsi_score", "rank_overall"]]
        .round(1)
        .to_string(index=False)
    )

    print("\n=== Sensitivity sweep: top/bottom-5 stability across weight variants ===")
    pivot = df.pivot_table(index="symbol", columns="weight_variant", values="rank_overall")
    pivot = pivot[["50_50", "60_40", "70_30"]]
    top5 = pivot.sort_values("60_40").head(5)
    bottom5 = pivot.sort_values("60_40").tail(5)
    print("Top-5 @ 60/40:\n", top5.to_string())
    print("\nBottom-5 @ 60/40:\n", bottom5.to_string())


if __name__ == "__main__":
    import shutil
    if not os.path.exists(DB_PATH):
        shutil.copy2(FINAL_DB_PATH, DB_PATH)  # на случай запуска scoring.py без пересборки

    raw = load_joined()
    scored = compute_phsi(raw)
    write_scores(scored)
    print_summary(scored)

    shutil.copy2(DB_PATH, FINAL_DB_PATH)
    print(f"\nscores synced back to: {FINAL_DB_PATH}")
