"""
SQLAlchemy ORM-схема для sp500_sustainability.db

Схема "звезда" вокруг Symbol:
  companies      — статичный справочник (тикер, сектор, индустрия)
  esg_ratings    — независимый рейтинг (Sustainalytics, via Kaggle CSV), покрытие: все 503
  financials     — финансовые рычаги (Yahoo Finance / stockanalysis.com), покрытие: демо-выборка 22 тикера
  phsi_scores    — результат Analytics Engine: z-score'ы, PHSI, разные варианты весов (sensitivity sweep)

Почему raw-значения хранятся отдельно от производных метрик:
производные (profit margin, cost-to-revenue, z-score, PHSI) — это результат методологии,
которая может поменяться (веса, окно винзоризации). Raw-данные — источник правды, их
не трогаем; phsi_scores можно пересчитать и перезаписать сколько угодно раз.
"""

from sqlalchemy import (
    create_engine, Column, String, Float, Integer, Boolean, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


class Company(Base):
    __tablename__ = "companies"

    symbol = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    sector = Column(String, nullable=False, index=True)      # GICS Sector — ключ для sector-relative нормализации
    industry = Column(String)
    full_time_employees = Column(Integer)

    esg = relationship("EsgRating", back_populates="company", uselist=False)
    financials = relationship("Financials", back_populates="company", uselist=False)
    scores = relationship("PhsiScore", back_populates="company")


class EsgRating(Base):
    __tablename__ = "esg_ratings"

    symbol = Column(String, ForeignKey("companies.symbol"), primary_key=True)

    total_esg_risk_score = Column(Float)
    environment_risk_score = Column(Float)
    governance_risk_score = Column(Float)
    social_risk_score = Column(Float)
    controversy_level = Column(String)
    controversy_score = Column(Float)
    esg_risk_percentile = Column(String)
    esg_risk_level = Column(String)

    # "Прагматичный штраф": True, если хотя бы total_esg_risk_score был NaN в исходном CSV
    # и заполнен 75-м перцентилем риска по сектору компании.
    is_imputed = Column(Boolean, default=False, nullable=False)
    imputation_note = Column(String)

    company = relationship("Company", back_populates="esg")


class Financials(Base):
    __tablename__ = "financials"

    symbol = Column(String, ForeignKey("companies.symbol"), primary_key=True)

    revenue_musd = Column(Float)
    gross_profit_musd = Column(Float)          # NULL для банков/REIT/utilities — см. source_note
    net_income_musd = Column(Float)
    market_cap_musd = Column(Float)
    fcf_musd = Column(Float)
    capex_musd = Column(Float)

    fiscal_year_note = Column(String)
    source_note = Column(String)
    is_demo_subset = Column(Boolean, default=True, nullable=False)  # пока True для всех — полное покрытие ждёт платного фида

    company = relationship("Company", back_populates="financials")


class PhsiScore(Base):
    """
    Результат Analytics Engine. weight_variant различает основной расчёт (60/40) и
    точки sensitivity sweep (50/50, 70/30, ...) — все хранятся одновременно, чтобы
    можно было построить график устойчивости ранжирования к весам без пересчёта.
    """
    __tablename__ = "phsi_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, ForeignKey("companies.symbol"), nullable=False, index=True)
    sector = Column(String, nullable=False)
    weight_variant = Column(String, nullable=False)   # напр. "60_40", "50_50", "70_30"

    fin_weight = Column(Float, nullable=False)
    esg_weight = Column(Float, nullable=False)

    financial_subscore = Column(Float)   # 0-100, после сектор-z-score + min-max
    esg_subscore = Column(Float)         # 0-100, после сектор-z-score + min-max
    phsi_score = Column(Float)           # 0-100, блендинг

    rank_overall = Column(Integer)       # ранг по всей демо-выборке (не по всем 503 — покрытие финансов ограничено)
    rank_in_sector = Column(Integer)

    __table_args__ = (
        UniqueConstraint("symbol", "weight_variant", name="uq_symbol_weight_variant"),
    )

    company = relationship("Company", back_populates="scores")


def get_engine(db_path: str = None):
    import os
    if db_path is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sp500_sustainability.db")
    return create_engine(f"sqlite:///{db_path}")


def get_session(engine=None):
    if engine is None:
        engine = get_engine()
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()
