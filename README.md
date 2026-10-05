# 🏦 My RSI Strategy 訊號監控 — 加密貨幣合約波段訊號監控系統

透過 **CoinGecko 市值** 篩選前 20 的加密貨幣（排除穩定幣與包裝代幣），並透過 **CCXT (Bitget)** 取得 USDT-M 永續合約完整多級別 K 線歷史資料（日K、1H、6H、4H），依照 **My RSI Strategy（5步時序驗證）** 判斷精準進出場訊號，每小時自動掃描並在出現新訊號時透過 Telegram Bot 即時推送圖文卡片與操作指引。

---

## 📋 策略邏輯（My RSI Strategy 5 步時序）

My RSI Strategy 結合趨勢確認、動量反轉、濾網與成交量確認，由以下 **5 大條件** 嚴格時序驗證：

| 步驟 / 條件 | 週期 | 多方條件 (🟢 做多) | 空方條件 (🔴 做空) | 說明 / 指標來源 |
|------------|------|-------------------|-------------------|---------------|
| **1. RD 趨勢** | 日K | Low > EMA10 且 > EMA20 | High < EMA10 且 < EMA20 | 日線大級別多空定調（無中性持態機制） |
| **2. RSI 超賣/超買反轉** | 1小時K | RSI 跌破 30 後向上突破 30 | RSI 突破 70 後向下跌破 70 | 捕捉次級折返後的動能回升 |
| **3. Heikin-Ashi 趨勢** | 6小時K | 連續綠 K（非 NTZ 盤整） | 連續紅 K（非 NTZ 盤整） | 中級別濾網，避開上下影線糾結盤整 |
| **4. RSI 突破 50 中軸** | 1小時K | RSI 向上突破 50 | RSI 向下跌破 50 | 觸發進場主訊號（多空分水嶺確認） |
| **5. OBV Oscillator 能量** | 日K | OBV Osc > 0 或 量縮 | OBV Osc < 0 或 量縮 | 資金能量確認（OBV Oscillator = OBV - EMA21，接續步驟4當下） |

---

### 🌊 條件 1：日線 RD 趨勢持態與河中次數分析

- **持態機制**：
  - 一旦確立為 🟢 RD（多頭），持續維持多頭，直到日線明確收成 🔴 RD（空頭）。
  - 盤整或 K 棒觸碰 EMA 時，維持原趨勢方向。
- **已掉入河中次數（回測警示）**：
  - 當日 K 實體或影線回測/跌破 EMA10、EMA20 河道時，計入「掉入河中次數」。
  - ⚠️ 若回測已達 **2 次以上**，系統自動標註提醒，注意動能衰竭與反轉風險。

---

### 🚦 進出場訊號定義

- 🚀 **合約做多進場**: 條件 1~5 全數達成（日線多 + 1H RSI回升 + 6H HA順向 + 1H RSI破50 + 天圖 OBV Osc 配合）。
- 🛑 **多單平倉出場**: 日線 RD 轉為空頭第一天，或 1H RSI 明確跌破 50。
- 📉 **合約做空進場**: 條件 1~5 全數達成（日線空 + 1H RSI回落 + 6H HA順向 + 1H RSI破50 + 天圖 OBV Osc 配合）。
- 🔄 **空單平倉出場**: 日線 RD 轉為多頭第一天，或 1H RSI 明確突破 50。

---

### 📱 Telegram 推播模組（精美圖文卡片與防重複機制）

#### 1. 防重複推播機制
系統內建狀態持久化追蹤器（`state/notified_signals.json`），結合 GitHub Actions Cache 與 Git 自動存檔：
- 每小時排程掃描時，**只推播當次新發生的進出場訊號**。
- 24 小時內若同一波訊號已推播過，系統靜默略過，不重複轟炸通知。

#### 2. 個幣多週期指標圖表
由 Matplotlib 繪製暗黑專業質感四子圖：
- **子圖 1（日K）**：日 K 棒 + EMA10 (藍) + EMA20 (紅) + RD趨勢標註
- **子圖 2（1H RSI）**：14 週期 RSI 折線 + 70/30 超買超賣區域 + 50 中軸
- **子圖 3（6H Heikin-Ashi）**：平均足 K 線，清楚呈現趨勢波段與盤整濾網
- **子圖 4（4H OBV Oscillator）**：能量震盪指標 + EMA21 均線

---

## 🚀 部署與設定指南

### 🔑 必要環境變數 (GitHub Secrets)

在 GitHub 倉庫的 `Settings` → `Secrets and variables` → `Actions` 中設定：

| Secret 名稱 | 說明 | 範例 |
|------------|------|------|
| `TELEGRAM_BOT_TOKEN` | 來自 @BotFather 的機器人 Token | `123456789:ABCdef...` |
| `TELEGRAM_CHAT_ID` | 接收通知的個人或群組 Chat ID | `987654321` |

---

### ⏰ 排程觸發方式

本專案支援由外部排程服務（例如 [Cron-job.org](https://cron-job.org)）定期觸發，維持即時且精準的監控：

- **請求方式**: `POST`
- **URL**: `https://api.github.com/repos/minicheng/CryptoRsiNotifier_Bot/dispatches`
- **Headers**:
  ```http
  Accept: application/vnd.github.v3+json
  Authorization: Bearer <你的_GITHUB_PERSONAL_ACCESS_TOKEN>
  Content-Type: application/json
  ```
- **Body**:
  ```json
  {"event_type": "signal-scan"}
  ```

---

## 📁 專案結構

```
CryptoRsiNotifier_Bot/
├── .github/
│   └── workflows/
│       └── daily_notify.yml    # My RSI Strategy 訊號監控 GitHub Actions 排程
├── src/
│   ├── config.py               # 策略參數與設定
│   ├── scanner.py              # CoinGecko 市值篩選 + CCXT (Bitget) 多週期K線抓取
│   ├── strategy.py             # My RSI Strategy 邏輯（5步時序驗證、進出場判斷）
│   ├── state_manager.py        # 訊號狀態管理器（防止重複推播）
│   ├── chart_generator.py      # Matplotlib 四子圖指標圖表繪製模組
│   ├── notifier.py             # Telegram 圖文卡片與訊號格式化
│   └── main.py                 # 主程式入口
├── state/
│   └── notified_signals.json   # 已推播歷史訊號狀態紀錄檔
├── script/
│   └── FT_pineScript_V1.rtf    # 原始 Pine Script 參考存檔
├── requirements.txt            # Python 依賴套件
└── README.md                   # 專案說明文件
```

---

## ⚙️ 技術架構

- **數據來源**: CoinGecko API (Top 20 市值) + CCXT Bitget (USDT-M 永續合約)
- **週期分析**: 天圖日K (Trend) + 1H (RSI) + 6H (Heikin-Ashi) + 4H (OBV Oscillator)
- **通知渠道**: Telegram Bot API (`sendPhoto` + `sendMessage`)
- **排程調度**: GitHub Actions `repository_dispatch` + Cron-job.org
- **語言版本**: Python 3.11+
