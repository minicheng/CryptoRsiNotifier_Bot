"""
FT 波段策略 — 設定檔
對應 Pine Script 的 input 參數
"""

# === EMA 參數 (日K — 條件1 RD趨勢) ===
EMA_SMALL_LEN = 10   # EMA 快線長度 (Pine: SmallLen)
EMA_BIG_LEN = 20     # EMA 慢線長度 (Pine: BigLen)

# === RSI 參數 (1小時K — 條件2 & 4) ===
RSI_PERIOD = 14       # RSI 計算週期

# === OBV 參數 (天圖日K — 條件5) ===
OBV_EMA_PERIOD = 21   # OBV Oscillator 使用的 EMA 週期

# === Scanner 設定 ===
TOP_N_COINS = 20      # 掃描市值前 N 名（排除穩定幣後）
COINGECKO_API_URL = "https://api.coingecko.com/api/v3/coins/markets"
EXCHANGE_ID = "bitget"  # 使用 Bitget 作為 K 線資料來源
DEFAULT_MARKET_TYPE = "swap"  # 使用 Bitget USDT-M 永續合約 (Perpetual Futures)
LOOKBACK_BARS = 300     # 抓取日 K 棒數量（預設 300 根日 K）
LOOKBACK_BARS_1H = 200  # 抓取 1 小時 K 棒數量（RSI 計算用）
LOOKBACK_BARS_6H = 50   # 抓取 6 小時 K 棒數量（Heikin-Ashi NTZ 判斷用）
LOOKBACK_BARS_4H = 200  # 抓取 4 小時 K 棒數量（OBV 計算用）

# === 穩定幣與包裝代幣排除清單 (Symbol 小寫) ===
EXCLUDED_SYMBOLS = {
    # 穩定幣
    "usdt", "usdc", "dai", "busd", "tusd", "fdusd", "usdd", "usde", "pyusd",
    "eurc", "usds", "rlusd", "xaut", "paxg", "frax", "usdp", "cusd", "susde",
    "sdai", "crvusd", "usdee", "usad2", "usd1w", "usdt0", "usdgo", "usdgg",
    # Wrapped / Staked / Bridged
    "wbtc", "weth", "wsteth", "cbbtc", "cbeth", "steth", "weeth", "wbeth",
    "beth", "jitosol", "bsol", "msol", "stbtc", "btcb", "webtc", "lseth",
    "wegld", "cdceth",
}

# === Telegram 設定 ===
TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_PHOTO_URL = "https://api.telegram.org/bot{token}/sendPhoto"
TELEGRAM_MEDIA_GROUP_URL = "https://api.telegram.org/bot{token}/sendMediaGroup"

# === 個幣圖文卡片推播設定 ===
# "featured": 模式 A（推薦）今日新訊號幣種 + 市值前 3 大幣 (BTC, ETH, BNB) + 掉河≥2次警告幣（每日約 3~5 張重點卡片，避免洗版）
# "all": 前 20 檔全數發送個幣圖文卡片
# "signals_only": 僅發送今日有新訊號的幣種
CARD_SEND_MODE = "featured"
CARD_TOP_N = 3          # featured 模式下固定包含前 N 大幣（如 BTC, ETH, BNB）
CARD_MAX_FEATURED = 5   # featured 模式每日最大發送張數（預設 5 張，避免大量洗版；設為 0 則不限張數）
CHARTS_DIR = "charts"   # 圖表快取儲存目錄

# === TradingView 圖表連結前綴 ===
TV_CHART_URL = "https://tw.tradingview.com/chart/?symbol={symbol}"

# === 訊號狀態紀錄與推播去重設定 ===
STATE_DIR = "state"
NOTIFIED_SIGNALS_FILE = "state/notified_signals.json"
MAX_SIGNAL_AGE_HOURS = 24  # 訊號最長有效時效（超過 24 小時前的舊訊號不當作當前新訊號推播）

