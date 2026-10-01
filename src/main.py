"""
合約波段策略通知系統 — 主程式

流程：
  1. 使用 CoinGecko API 篩選市值前 20 幣種（排除穩定幣與包裝代幣）
  2. 使用 CCXT 從 Bitget 抓取多時間框架 K 線 (日/1h/6h/4h)
  3. 執行合約波段策略分析（RD趨勢、RSI、Heikin-Ashi NTZ、OBV Oscillator）
  4. 格式化訊號並透過 Telegram Bot 推送
"""

import os
import sys
from datetime import datetime, timezone, timedelta

# 確保能 import 同目錄下的模組
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 解決 Windows 控制台 cp950 編碼無法輸出 Emoji 問題
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import time
from scanner import fetch_top_coins
from strategy import analyze_all, get_signals
from notifier import (
    format_signals_message,
    format_coin_card_caption,
    send_telegram_message,
    send_telegram_photo,
    send_telegram_media_group,
)
from chart_generator import generate_coin_chart, generate_all_strategy_charts
from config import TOP_N_COINS, CARD_SEND_MODE, CARD_TOP_N, CARD_MAX_FEATURED, CHARTS_DIR


def select_card_targets(results, signals, mode=CARD_SEND_MODE, top_n=CARD_TOP_N, max_featured=CARD_MAX_FEATURED):
    """
    依據設定決定要產生並發送個幣圖文卡片的幣種清單。
    模式 A (featured): 今日新訊號幣種 + 市值前 top_n 大幣 (BTC, ETH, BNB) + 掉河≥2次警告幣。
    兼顧重點權重幣與重大異動幣，每日約發送 3~5 張重點圖文卡片，避免大量洗版。
    """
    if mode == "all":
        return results

    if mode == "signals_only":
        signal_symbols = set()
        for items in signals.values():
            for item in items:
                signal_symbols.add(item.get("symbol"))
        return [r for r in results if r.get("symbol") in signal_symbols]

    # 模式 A（推薦 featured）：
    signal_symbols = set()
    for items in signals.values():
        for item in items:
            signal_symbols.add(item.get("symbol"))

    selected = []
    seen = set()

    # 第一順位：今日有新進出場訊號者
    for r in results:
        sym = r.get("symbol")
        has_signal = sym in signal_symbols
        if has_signal and sym not in seen:
            selected.append(r)
            seen.add(sym)

    # 第二順位：市值前 top_n 大幣（權重核心：BTC, ETH, BNB）
    for r in results:
        sym = r.get("symbol")
        if r.get("rank", 999) <= top_n and sym not in seen:
            selected.append(r)
            seen.add(sym)

    # 第三順位：今日剛好跌入河中且累積次數≥2的重大異動警告幣（當天最新觸發警示）
    for r in results:
        sym = r.get("symbol")
        if sym not in seen and r.get("has_warning"):
            latest_bar = r.get("latest_bar_date", "")
            dip_dates = r.get("dip_dates", [])
            if latest_bar and dip_dates and latest_bar == dip_dates[-1]:
                selected.append(r)
                seen.add(sym)

    # 第四順位：若尚未達每日張數上限（預設 5 張），依序補充目前回測河中且警示次數最多的幣種
    if max_featured and len(selected) < max_featured:
        warning_pool = [
            r for r in results
            if r.get("symbol") not in seen and r.get("has_warning") and r.get("in_dip")
        ]
        # 優先依掉河次數多者、次依市值大小排序
        warning_pool.sort(key=lambda x: (-x.get("dips_completed", 0), x.get("rank", 999)))
        for r in warning_pool:
            if len(selected) >= max_featured:
                break
            selected.append(r)
            seen.add(r.get("symbol"))

    return selected


def main():
    """主流程"""
    # 台北時間
    tw_tz = timezone(timedelta(hours=8))
    now = datetime.now(tw_tz)
    scan_time = now.strftime("%Y/%m/%d %H:%M (台北時區）")

    print(f"🔍 合約波段策略掃描開始 — {scan_time}")
    print(f"📊 篩選目標：CoinGecko 市值前 {TOP_N_COINS} 名非穩定幣（Bitget 多時間框架）")
    print(f"🖼️ 個幣卡片模式：{CARD_SEND_MODE}")
    print()

    # === Step 1: 抓取數據 ===
    print("Step 1: 從 CoinGecko 取得市值排名並從 Bitget 抓取多時間框架 K 線...")
    try:
        coins = fetch_top_coins(TOP_N_COINS)
        print(f"  ✅ 成功取得 {len(coins)} 個幣種完整數據")
    except Exception as e:
        print(f"  ❌ 取得數據失敗: {e}")
        sys.exit(1)

    if not coins:
        print("  ❌ 沒有取得任何幣種數據")
        sys.exit(1)

    # === Step 2: 策略分析 ===
    print("\nStep 2: 執行合約波段策略分析（RD趨勢、RSI、NTZ、OBV）...")
    results = analyze_all(coins)
    signals = get_signals(results)

    # 印出摘要
    for sig_type, items in signals.items():
        if items:
            names = ", ".join(i["symbol"] for i in items)
            print(f"  📌 {sig_type}: {names}")

    total_signals = sum(len(v) for v in signals.values())
    if total_signals == 0:
        print("  💤 今日無進出場訊號")

    # === Step 3: 判斷是否有進出場訊號 ===
    # 統計所有進出場訊號（做多進場、做空進場、做多出場、做空出場）
    active_signals = [
        item for key in ("long_entry", "short_entry", "long_exit", "short_exit")
        for item in signals.get(key, [])
    ]
    has_signal = len(active_signals) > 0

    if not has_signal:
        print("\n💤 本次掃描無進出場訊號 — 靜默結束，不推播 Telegram。")
        print(f"\n✅ 合約波段策略掃描完成 — {scan_time}")
        return  # 無訊號直接結束，不做任何推播

    print(f"\n🚨 偵測到 {len(active_signals)} 個進出場訊號！準備推播 Telegram...")

    # === Step 4: 發送通知 ===
    print("\nStep 4: 格式化並發送 Telegram 總覽訊息與個幣圖文卡片...")
    overview_message = format_signals_message(signals, results, scan_time)
    # 只推播有進出場訊號的幣種
    signal_symbols = {item["symbol"] for item in active_signals}
    card_targets = [r for r in results if r.get("symbol") in signal_symbols]

    # 檢查是否為 dry-run 模式（環境變數或 CLI 參數）
    dry_run = (
        os.environ.get("DRY_RUN", "false").lower() == "true"
        or "--dry-run" in sys.argv
    )

    if dry_run:
        print("\n📝 [DRY-RUN 模式] ===== 總覽日報 =====")
        print("=" * 55)
        print(overview_message)
        print("=" * 55)

        print(f"\n🖼️ [DRY-RUN 模式] 預計為 {len(card_targets)} 檔個幣各產生 5 張策略時序檢核圖表：")
        for r in card_targets:
            chart_paths = generate_all_strategy_charts(r, output_dir=CHARTS_DIR)
            caption = format_coin_card_caption(r)
            print(f"\n" + "-" * 40)
            print(f"📌 卡片幣種: {r['symbol']} ({r['name']}) | 排名: #{r['rank']}")
            print(f"🖼️ 5 張策略檢核圖表 (共 {len(chart_paths)} 張):")
            labels = [
                "1. 步驟1 RD天圖趨勢",
                "2. 步驟2 1h RSI超賣/超買",
                "3. 步驟3 6h 平均K線NTZ轉折",
                "4. 步驟4 1h RSI方向確認",
                "5. 步驟5 天圖OBV動能確認",
            ]
            for idx, cp in enumerate(chart_paths):
                lbl = labels[idx] if idx < len(labels) else f"圖表 {idx+1}"
                print(f"   • {lbl}: {os.path.basename(cp)} (存在: {os.path.exists(cp)})")
            print("📝 卡片文案:")
            print(caption)
            print("-" * 40)
    else:
        # 1. 先發送總覽訊息
        print("📡 發送總覽文字日報...")
        send_telegram_message(overview_message)
        time.sleep(1.0)

        # 2. 逐一產生並發送個幣圖文相簿 (5 張檢核圖)
        print(f"📡 開始產生並發送 {len(card_targets)} 檔個幣 5 圖時序檢核相簿...")
        success_cards = 0
        for r in card_targets:
            sym = r.get("symbol", "")
            try:
                chart_paths = generate_all_strategy_charts(r, output_dir=CHARTS_DIR)
                caption = format_coin_card_caption(r)
                if chart_paths:
                    ok = send_telegram_media_group(chart_paths, caption)
                    if ok:
                        success_cards += 1
                else:
                    # fallback: 僅發送文字
                    send_telegram_message(caption)
            except Exception as e:
                print(f"⚠️ 發送 {sym} 5圖卡片失敗: {e}")

            time.sleep(1.0)  # 避免 Telegram rate limit

        print(f"\n🎉 推播完成！成功發送總覽及 {success_cards}/{len(card_targets)} 組個幣 5 圖時序檢核卡片。")

    print(f"\n✅ 合約波段策略掃描完成 — {scan_time}")


if __name__ == "__main__":
    main()
