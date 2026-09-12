"""
Step 2: Database Build.

Читает:
  - "SP 500 ESG Risk Ratings.csv"   (независимый рейтинг Sustainalytics, все 503 тикера)
  - "data/financials_demo22.csv"    (финансовые рычаги, демо-выборка 22 тикера, 2 на GICS-сектор)

Применяет "Прагматичный Штраф" (Pragmatic Penalty): если у компании нет ESG-данных,
ей присваивается 75-й перцентиль риска (т.е. хуже среднего) СРЕДИ КОМПАНИЙ ЕЁ ЖЕ СЕКТОРА
— отдельно для total score и для каждой из трёх risk-компонент (Environment/Governance/Social)
и для Controversy Score. Отсутствие прозрачности — это тоже риск, поэтому штраф, а не медиана.

Технический нюанс: SQLite не пишется напрямую в этой примонтированной (bridged) папке —
сборка идёт во временную локальную директорию, готовый .db-файл копируется в рабочую
папку одним atomic-write в конце.

Запуск: python3 pipeline/build_database.py
"""

import os
import sys
import shutil
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_models import Company, EsgRating, Financials, get_engine, get_session

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESG_CSV = os.path.join(ROOT, "SP 500 ESG Risk Ratings.csv")
FIN_CSV = os.path.join(ROOT, "data", "financials_demo22.csv")
FINAL_DB_PATH = os.path.join(ROOT, "sp500_sustainability.db")

BUILD_DIR = os.path.join(os.path.expanduser("~"), ".phsi_build")
BUILD_DB_PATH = os.path.join(BUILD_DIR, "sp500_sustainability.db")

# Колонки ESG-риска, к которым применяется прагматичный штраф по сектору
PENALTY_COLUMNS = [
    "Total ESG Risk score",
    "Environment Risk Score",
    "Governance Risk Score",
    "Social Risk Score",
    "Controversy Score",
]
PENALTY_PERCENTILE = 0.75


def load_esg(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df.rename(columns={
        "Full Time Employees": "Full_Time_Employees",
    })
    if df["Full_Time_Employees"].dtype == object:
        df["Full_Time_Employees"] = (
            df["Full_Time_Employees"].astype(str).str.replace(",", "", regex=False)
        )
        df["Full_Time_Employees"] = pd.to_numeric(df["Full_Time_Employees"], errors="coerce")

    # Data-quality gap в исходном CSV: у BF.B (Brown-Forman) полностью пустая строка
    # (Sector/Industry/все ESG-поля — NaN), вероятно скрейпер не справился с тикером,
    # содержащим точку. Sector нужен для sector-relative методологии, поэтому вручную
    # проставляем публично известную GICS-классификацию; ESG-поля остаются NaN и
    # получат обычный прагматичный штраф по сектору ниже.
    bf_mask = df["Symbol"] == "BF.B"
    if bf_mask.any() and df.loc[bf_mask, "Sector"].isna().all():
        df.loc[bf_mask, "Sector"] = "Consumer Defensive"
        df.loc[bf_mask, "Industry"] = "Beverages\u2014Wineries & Distilleries"

    return df


def apply_pragmatic_penalty(df: pd.DataFrame) -> pd.DataFrame:
    """Заполняет NaN в PENALTY_COLUMNS 75-м перцентилем той же GICS-Sector. Возвращает
    df с доп. колонками is_imputed (bool) и imputation_note."""
    df = df.copy()
    imputed_any = pd.Series(False, index=df.index)
    notes = pd.Series("", index=df.index)

    sector_p75 = df.groupby("Sector")[PENALTY_COLUMNS].quantile(PENALTY_PERCENTILE)

    for col in PENALTY_COLUMNS:
        was_null = df[col].isna()
        if not was_null.any():
            continue
        fill_values = df.loc[was_null, "Sector"].map(sector_p75[col])
        df.loc[was_null, col] = fill_values
        imputed_any |= was_null
        notes.loc[was_null] = notes.loc[was_null] + f"{col} imputed (sector p75); "

    df["is_imputed"] = imputed_any
    df["imputation_note"] = notes.replace("", None)
    return df


def load_financials(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def _none_if_nan(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return float(value) if isinstance(value, (int, float, np.floating, np.integer)) else value


def build():
    os.makedirs(BUILD_DIR, exist_ok=True)
    if os.path.exists(BUILD_DB_PATH):
        os.remove(BUILD_DB_PATH)  # чистая пересборка при каждом запуске — идемпотентно

    esg_raw = load_esg(ESG_CSV)
    esg = apply_pragmatic_penalty(esg_raw)
    fin = load_financials(FIN_CSV)

    engine = get_engine(BUILD_DB_PATH)
    session = get_session(engine)

    n_companies = n_esg = n_fin = 0

    for _, row in esg.iterrows():
        company = Company(
            symbol=row["Symbol"],
            name=row["Name"],
            sector=row["Sector"],
            industry=row["Industry"],
            full_time_employees=(
                int(row["Full_Time_Employees"]) if pd.notna(row["Full_Time_Employees"]) else None
            ),
        )
        session.merge(company)
        n_companies += 1

        rating = EsgRating(
            symbol=row["Symbol"],
            total_esg_risk_score=_none_if_nan(row["Total ESG Risk score"]),
            environment_risk_score=_none_if_nan(row["Environment Risk Score"]),
            governance_risk_score=_none_if_nan(row["Governance Risk Score"]),
            social_risk_score=_none_if_nan(row["Social Risk Score"]),
            controversy_level=row["Controversy Level"] if pd.notna(row["Controversy Level"]) else None,
            controversy_score=_none_if_nan(row["Controversy Score"]),
            esg_risk_percentile=row["ESG Risk Percentile"] if pd.notna(row["ESG Risk Percentile"]) else None,
            esg_risk_level=row["ESG Risk Level"] if pd.notna(row["ESG Risk Level"]) else None,
            is_imputed=bool(row["is_imputed"]),
            imputation_note=row["imputation_note"],
        )
        session.merge(rating)
        n_esg += 1

    for _, row in fin.iterrows():
        financials = Financials(
            symbol=row["Symbol"],
            revenue_musd=_none_if_nan(row["Revenue_musd"]),
            gross_profit_musd=_none_if_nan(row.get("Gross_Profit_musd")),
            net_income_musd=_none_if_nan(row["Net_Income_musd"]),
            market_cap_musd=_none_if_nan(row["Market_Cap_musd"]),
            fcf_musd=_none_if_nan(row.get("FCF_musd")),
            capex_musd=_none_if_nan(row.get("Capex_musd")),
            fiscal_year_note=row.get("Fiscal_Year_Note"),
            source_note=row.get("Source_Note"),
            is_demo_subset=True,
        )
        session.merge(financials)
        n_fin += 1

    session.commit()
    session.close()
    engine.dispose()

    shutil.copy2(BUILD_DB_PATH, FINAL_DB_PATH)

    n_imputed = int(esg["is_imputed"].sum())
    print(f"companies: {n_companies} | esg ratings: {n_esg} (imputed: {n_imputed}) | financials: {n_fin}")
    print(f"db written to: {FINAL_DB_PATH}")


if __name__ == "__main__":
    build()
