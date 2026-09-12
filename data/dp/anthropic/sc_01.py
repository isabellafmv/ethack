import pandas as pd
import requests
import yfinance as yf
import numpy as np
import time
from tqdm import tqdm
import random


# Пул популярных User-Agents для маскировки
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15"
]

def get_sp500_universe():
    """Скачивает актуальный список S&P 500 из Wikipedia с обходом защиты (403 Forbidden)."""
    print("Fetching S&P 500 universe...")
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    
    # Добавляем User-Agent, чтобы притвориться обычным браузером
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # Делаем запрос через requests
    response = requests.get(url, headers=headers)
    response.raise_for_status() # Проверяем, что запрос успешен (не 404, не 403)
    
    # Передаем сырой HTML-текст в Pandas
    from io import StringIO
    tables = pd.read_html(StringIO(response.text))
    df = tables[0]
    
    # Оставляем только нужные колонки
    universe = df[['Symbol', 'Security', 'GICS Sector', 'GICS Sub-Industry']].copy()
    
    # Очистка тикеров (в yfinance вместо точек используются дефисы, например BRK.B -> BRK-B)
    universe['Symbol'] = universe['Symbol'].str.replace('.', '-', regex=False)
    
    print(f"Successfully fetched {len(universe)} tickers.")
    return universe

def fetch_financial_levers_robust(tickers):
    """
    Production-ready сборщик с ротацией User-Agent и защитой от Rate Limit (HTTP 429).
    """
    results = []
    print(f"Fetching financial data for {len(tickers)} companies...")
    
    for ticker in tqdm(tickers):
        max_retries = 3
        success = False
        
        for attempt in range(max_retries):
            try:
                # 1. Новая сессия и случайный браузер для каждой попытки
                session = requests.Session()
                session.headers.update({"User-Agent": random.choice(USER_AGENTS)})
                
                stock = yf.Ticker(ticker, session=session)
                info = stock.info
                
                if not info or len(info) <= 1:
                    raise ValueError("Empty info returned")
                    
                # 2. Извлекаем наши рычаги
                revenue = info.get('totalRevenue', np.nan)
                gross_profit = info.get('grossProfits', np.nan)
                fcf = info.get('freeCashflow', np.nan)
                market_cap = info.get('marketCap', np.nan)
                profit_margin = info.get('profitMargins', np.nan)
                
                cost_to_revenue = np.nan
                if pd.notna(revenue) and pd.notna(gross_profit) and revenue > 0:
                    cost_to_revenue = (revenue - gross_profit) / revenue
                    
                capex_to_revenue = np.nan
                try:
                    cf = stock.cashflow
                    if not cf.empty and 'Capital Expenditure' in cf.index:
                        capex = abs(cf.loc['Capital Expenditure'].iloc[0])
                        if pd.notna(revenue) and revenue > 0:
                            capex_to_revenue = capex / revenue
                except Exception:
                    pass # Тихий пропуск ошибки cashflow

                # 3. Сохраняем результат
                results.append({
                    'Symbol': ticker,
                    'Profit_Margin': profit_margin,
                    'FCF_Yield': fcf / market_cap if pd.notna(fcf) and pd.notna(market_cap) and market_cap > 0 else np.nan,
                    'Cost_to_Revenue': cost_to_revenue,
                    'Capex_to_Revenue': capex_to_revenue
                })
                
                success = True
                break # Выходим из цикла retries при успехе
                
            except Exception as e:
                error_msg = str(e)
                # Если поймали 429 Rate Limit
                if "429" in error_msg or "Too Many Requests" in error_msg:
                    wait_time = (attempt + 1) * 5 # Ждем 5с, 10с, 15с
                    print(f"\n[WARNING] Rate Limit для {ticker}. Ожидание {wait_time} сек (Попытка {attempt+1}/{max_retries})...")
                    time.sleep(wait_time)
                else:
                    # Другая ошибка (например, делистинг тикера)
                    print(f"\n[ERROR] {ticker}: {error_msg}")
                    break
        
        # Если все попытки провалились, пишем NaN
        if not success:
            results.append({
                'Symbol': ticker, 'Profit_Margin': np.nan, 
                'FCF_Yield': np.nan, 'Cost_to_Revenue': np.nan, 
                'Capex_to_Revenue': np.nan
            })

        # 4. Рандомная пауза перед следующим тикером (от 1.5 до 3 секунд)
        time.sleep(random.uniform(1.5, 3.0))
        
    return pd.DataFrame(results)

# --- ЗАПУСК ---
if __name__ == "__main__":
    # 1. Получаем список
    sp500_df = get_sp500_universe()
    
    # ДЛЯ ТЕСТА: возьмем первые 10 компаний (чтобы не ждать долго). 
    # На хакатоне уберешь .head(10)
    test_tickers = sp500_df['Symbol'].head(10).tolist()
    
    # 2. Собираем финансы
    financials_df = fetch_financial_levers_robust(test_tickers)
    
    # 3. Мержим данные
    final_df = pd.merge(sp500_df, financials_df, on='Symbol', how='inner')
    
    print("\nSample Data:")
    print(final_df.head())