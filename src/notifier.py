"""
Telegram Bot 通知模組
1. 產生每日加密貨幣趨勢總覽報表（分開 🟢 RD向上 與 🔴 RD向下，置頂今日新訊號）
2. 產生個幣圖文卡片文案（包含 K 線指標圖、操作建議、掉河次數、注意事項、5大條件與 TradingView 連結）
3. 提供 Telegram 文字訊息 (sendMessage) 與圖片推播 (sendPhoto) API
"""

import os
import requests
import datetime
import urllib.parse
import json
import html
from config import TELEGRAM_API_URL, TELEGRAM_PHOTO_URL, TELEGRAM_MEDIA_GROUP_URL, TV_CHART_URL


def _clean_credentials(bot_token=None, chat_id=None):
    """清理 Token 與 Chat ID 的多餘引號與空白"""
    token = (bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip().strip("'\"")
    cid = str(chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")).strip().strip("'\"")
    return token, cid


def send_telegram_message(text, bot_token=None, chat_id=None, parse_mode="HTML"):
    """
    透過 Telegram Bot API 發送文字訊息。

    Args:
        text (str): 訊息內容（支援 HTML 格式）
        bot_token (str): Bot Token（預設從環境變數讀取）
        chat_id (str): Chat ID（預設從環境變數讀取）
        parse_mode (str): 解析模式，預設 HTML；若為 None 則為純文字

    Returns:
        bool: 發送成功與否
    """
    token, cid = _clean_credentials(bot_token, chat_id)

    if not token or not cid:
        print("❌ 缺少 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID")
        return False

    url = TELEGRAM_API_URL.format(token=token)
    payload = {
        "chat_id": cid,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    try:
        resp = requests.post(url, json=payload, timeout=30)
        try:
            result = resp.json()
        except Exception:
            result = {}

        if resp.status_code == 200 and result.get("ok"):
            print("✅ Telegram 總覽訊息發送成功")
            return True
        else:
            desc = result.get("description", resp.text)
            print(f"❌ Telegram 發送失敗: HTTP {resp.status_code} - {desc}")
            # 若為 HTML 格式解析錯誤，自動降級以純文字重試
            if parse_mode and ("can't parse entities" in desc.lower() or "entity" in desc.lower()):
                print("🔄 偵測到 HTML 解析異常，嘗試以純文字模式重發...")
                return send_telegram_message(text, bot_token=token, chat_id=cid, parse_mode=None)
            return False
    except requests.RequestException as e:
        print(f"❌ Telegram 連線失敗: {e}")
        return False


def send_telegram_photo(photo_path, caption="", bot_token=None, chat_id=None, parse_mode="HTML"):
    """
    透過 Telegram Bot API 發送照片與圖文卡片說明。

    Args:
        photo_path (str): 圖片檔案本機路徑
        caption (str): 圖片附帶說明文案（最高 1024 字元）
        bot_token (str): Bot Token
        chat_id (str): Chat ID
        parse_mode (str): 解析模式，預設 HTML；若為 None 則為純文字

    Returns:
        bool: 發送成功與否
    """
    token, cid = _clean_credentials(bot_token, chat_id)

    if not token or not cid:
        print("❌ 缺少 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID")
        return False

    if not photo_path or not os.path.exists(photo_path):
        print(f"❌ 圖片檔案不存在: {photo_path}")
        return False

    url = TELEGRAM_PHOTO_URL.format(token=token)
    try:
        with open(photo_path, "rb") as f:
            files = {"photo": f}
            data = {
                "chat_id": cid,
                "caption": caption[:1024],
            }
            if parse_mode:
                data["parse_mode"] = parse_mode

            resp = requests.post(url, data=data, files=files, timeout=35)
            try:
                result = resp.json()
            except Exception:
                result = {}

            if resp.status_code == 200 and result.get("ok"):
                print(f"✅ Telegram 圖文卡片發送成功 ({os.path.basename(photo_path)})")
                return True
            else:
                desc = result.get("description", resp.text)
                print(f"❌ 發送 Telegram 圖片失敗: HTTP {resp.status_code} - {desc}")
                if parse_mode and ("can't parse entities" in desc.lower() or "entity" in desc.lower()):
                    print("🔄 嘗試以純文字模式重發圖片...")
                    return send_telegram_photo(photo_path, caption=caption, bot_token=token, chat_id=cid, parse_mode=None)
                return False
    except Exception as e:
        print(f"❌ 發送 Telegram 圖片例外異常: {e}")
        return False


def send_telegram_media_group(photo_paths, caption="", bot_token=None, chat_id=None, parse_mode="HTML"):
    """
    透過 Telegram Bot API (sendMediaGroup) 將多張圖片組合成單一相簿發送。
    最多支援 10 張圖片，第一張附帶說明卡片文案。

    Args:
        photo_paths (list[str]): 圖片路徑列表
        caption (str): 附帶說明文案（最高 1024 字元）
        bot_token (str): Bot Token
        chat_id (str): Chat ID
        parse_mode (str): 解析模式

    Returns:
        bool: 發送成功與否
    """
    token, cid = _clean_credentials(bot_token, chat_id)

    if not token or not cid:
        print("❌ 缺少 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID")
        return False

    valid_paths = [p for p in photo_paths if p and os.path.exists(p)]
    if not valid_paths:
        print("❌ 無有效的圖片路徑可供發送相簿")
        return False

    if len(valid_paths) == 1:
        return send_telegram_photo(valid_paths[0], caption, bot_token=token, chat_id=cid, parse_mode=parse_mode)

    url = TELEGRAM_MEDIA_GROUP_URL.format(token=token)
    media = []
    files = {}
    file_handles = []

    try:
        for i, path in enumerate(valid_paths[:10]):
            attach_key = f"photo_{i}"
            item = {
                "type": "photo",
                "media": f"attach://{attach_key}",
            }
            if i == 0 and caption:
                item["caption"] = caption[:1024]
                if parse_mode:
                    item["parse_mode"] = parse_mode
            media.append(item)
            fh = open(path, "rb")
            file_handles.append(fh)
            files[attach_key] = (os.path.basename(path), fh, "image/png")

        data = {
            "chat_id": cid,
            "media": json.dumps(media),
        }
        resp = requests.post(url, data=data, files=files, timeout=60)
        try:
            result = resp.json()
        except Exception:
            result = {}

        if resp.status_code == 200 and result.get("ok"):
            print(f"✅ Telegram 多圖相簿發送成功 (共 {len(media)} 張圖表)")
            return True
        else:
            desc = result.get("description", resp.text)
            print(f"❌ 發送 Telegram MediaGroup 失敗: HTTP {resp.status_code} - {desc}，嘗試退回單張發送")
            return send_telegram_photo(valid_paths[0], caption, bot_token=token, chat_id=cid, parse_mode=parse_mode)
    except Exception as e:
        print(f"❌ 發送 Telegram MediaGroup 例外異常: {e}，嘗試退回單張發送")
        return send_telegram_photo(valid_paths[0], caption, bot_token=token, chat_id=cid, parse_mode=parse_mode)
    finally:
        for fh in file_handles:
            try:
                fh.close()
            except Exception:
                pass


def _format_price(price):
    """格式化價格顯示"""
    if price is None:
        return "N/A"
    if price >= 1000:
        return f"${price:,.2f}"
    elif price >= 1:
        return f"${price:.4f}"
    else:
        return f"${price:.6f}"


def _format_market_cap(cap):
    """格式化市值顯示"""
    if cap is None:
        return "N/A"
    if cap >= 1e12:
        return f"${cap/1e12:.2f}T"
    elif cap >= 1e9:
        return f"${cap/1e9:.2f}B"
    elif cap >= 1e6:
        return f"${cap/1e6:.2f}M"
    else:
        return f"${cap:,.0f}"


def _format_change(change):
    """格式化漲跌幅"""
    if change is None:
        return "N/A"
    pct = change * 100
    emoji = "📈" if pct > 0 else ("📉" if pct < 0 else "➖")
    return f"{emoji} {pct:+.2f}%"


def _format_vol(vol):
    """格式化成交量顯示 (K / M / B)"""
    if vol is None:
        return "N/A"
    if vol >= 1e9:
        return f"{vol/1e9:.2f}B"
    elif vol >= 1e6:
        return f"{vol/1e6:.2f}M"
    elif vol >= 1e3:
        return f"{vol/1e3:.1f}K"
    else:
        return f"{vol:,.1f}"


def _get_tv_link(coin):
    """產生 TradingView 永續合約圖表連結"""
    sym = coin.get("symbol", "") if isinstance(coin, dict) else str(coin)
    trade_symbol = coin.get("trade_symbol", "") if isinstance(coin, dict) else ""
    raw_sym = trade_symbol if trade_symbol else f"BITGET:{sym}USDT.P"
    encoded_sym = urllib.parse.quote(raw_sym, safe="")
    return TV_CHART_URL.format(symbol=encoded_sym)


def _format_overview_coin_line(i, r):
    """格式化總覽列表中的單一幣種資訊列"""
    rd_emoji = "🟢" if r["status_rd"] == 3 else "🔴"
    change_str = _format_change(r.get("change"))
    rsi_val = r.get("rsi", 50.0)
    conds_cnt = r.get("conditions_met_count", 0)

    # 狀態標記（出場優先於進場與持倉）
    if r.get("long_exit"):
        status_tag = "🛑多單出場"
    elif r.get("short_exit"):
        status_tag = "🔄空單出場"
    elif r.get("long_entry"):
        status_tag = "🚀新做多進場"
    elif r.get("short_entry"):
        status_tag = "📉新做空進場"
    elif r.get("in_position"):
        status_tag = "持倉中(5/5已進場)"
    elif r.get("has_already_exited"):
        status_tag = "已出場(觀望中)"
    else:
        status_tag = f"進度:{conds_cnt}/5"

    rd_trend_str = f"RD{rd_emoji} {r.get('trend_days', 0)}天"
    sym_display = f"{r['symbol'][:5]:<5s}"
    price_display = f"{_format_price(r['close']):>9s}"

    return (
        f"{i:2d}. {sym_display} | {price_display} | {change_str} | "
        f"{rd_trend_str} | RSI:{rsi_val:4.1f} | {status_tag}"
    )


def format_signals_message(signals, results, scan_time=""):
    """
    將 5 步時序波段策略掃描總覽格式化為 Telegram 訊息。
    包含：標題時間、⚡️今日觸發進出場訊號、🟢 RD多頭向上分組、🔴 RD空頭向下分組。

    Args:
        signals (dict): get_signals() 或 filter_new_signals() 的回傳值
        results (list[dict]): 所有幣種的分析結果
        scan_time (str): 掃描時間

    Returns:
        str: 總覽文字訊息
    """
    sep = "———————————————————————————————————"
    lines = []

    lines.append("📊 加密貨幣合約波段策略日報（5步時序掃描）")
    if scan_time:
        time_clean = scan_time.replace("-", "/").replace(" (台北時間)", " (台北時區）")
        if "(台北" not in time_clean:
            time_clean += " (台北時區）"
        lines.append(time_clean)
    else:
        now_str = datetime.datetime.now().strftime("%Y/%m/%d %H:%M (台北時區）")
        lines.append(now_str)

    lines.append(sep)

    # ⚡️今日訊號（出場優先於進場列出）
    new_signals_list = []
    if isinstance(signals, dict) and any(signals.values()):
        for r in signals.get("long_exit", []):
            new_signals_list.append(f"🛑 {r.get('symbol')} (合約做多出場 - 1h RSI>70 超買獲利了結)")
        for r in signals.get("short_exit", []):
            new_signals_list.append(f"🔄 {r.get('symbol')} (合約做空出場 - 1h RSI<30 超賣獲利了結)")
        for r in signals.get("long_entry", []):
            new_signals_list.append(f"🚀 {r.get('symbol')} (合約做多進場 - 5/5條件達成)")
        for r in signals.get("short_entry", []):
            new_signals_list.append(f"📉 {r.get('symbol')} (合約做空進場 - 5/5條件達成)")
    else:
        for r in results:
            sym = r.get("symbol", "")
            if r.get("long_exit"):
                new_signals_list.append(f"🛑 {sym} (合約做多出場 - 1h RSI>70 超買獲利了結)")
            elif r.get("short_exit"):
                new_signals_list.append(f"🔄 {sym} (合約做空出場 - 1h RSI<30 超賣獲利了結)")
            elif r.get("long_entry"):
                new_signals_list.append(f"🚀 {sym} (合約做多進場 - 5/5條件達成)")
            elif r.get("short_entry"):
                new_signals_list.append(f"📉 {sym} (合約做空進場 - 5/5條件達成)")

    lines.append("⚡️ 今日觸發進出場訊號:")
    if new_signals_list:
        for s in new_signals_list:
            lines.append(f" • {s}")
    else:
        lines.append(" • 今日無新進出場訊號")

    lines.append(sep)

    # 分開 RD 向上 與 RD 向下
    up_coins = [r for r in results if r.get("status_rd") == 3]
    down_coins = [r for r in results if r.get("status_rd") == -3]

    # 🟢 RD多頭向上
    lines.append(f"🟢 RD多頭向上：共 {len(up_coins)} 個幣種")
    for i, r in enumerate(up_coins, 1):
        lines.append(_format_overview_coin_line(i, r))

    lines.append(sep)

    # 🔴 RD空頭向下
    lines.append(f"🔴 RD空頭向下：共 {len(down_coins)} 個幣種")
    for i, r in enumerate(down_coins, 1):
        lines.append(_format_overview_coin_line(i, r))

    lines.append(sep)
    lines.append("💡 策略核心時序：天圖RD ➜ 1h RSI極值 ➜ 6h NTZ轉折 ➜ 1h RSI中軸 ➜ 天圖OBV")

    return "\n".join(lines)


def format_coin_card_caption(r):
    """
    產生個幣圖文卡片說明文案（專為 5 步時序波段策略設計）。
    包含：訊號狀態標題、收盤價、天圖趨勢、1h RSI、5大時序檢核步驟、操作建議、風控提醒、TradingView 連結。

    Args:
        r (dict): analyze_coin 回傳的幣種分析結果

    Returns:
        str: 卡片文字內容
    """
    lines = []

    symbol = r.get("symbol", "")
    name = r.get("name", symbol)
    rank = r.get("rank", 1)
    close = r.get("close", 0.0)
    change_str = _format_change(r.get("change"))

    # 最新完成日 K 日期
    bar_date = r.get("latest_bar_date", "")
    if bar_date.startswith("0"):
        bar_date_display = bar_date[1:]
    else:
        bar_date_display = bar_date if bar_date else "今日"

    # 訊號狀態頂部 Header（出場訊號優先於進場與持倉）
    if r.get("long_exit"):
        header = f"🛑【合約做多出場訊號】#{rank} {symbol} ({name})"
    elif r.get("short_exit"):
        header = f"🔄【合約做空出場訊號】#{rank} {symbol} ({name})"
    elif r.get("long_entry"):
        header = f"🚀【合約做多進場訊號】#{rank} {symbol} ({name})"
    elif r.get("short_entry"):
        header = f"📉【合約做空進場訊號】#{rank} {symbol} ({name})"
    elif r.get("in_position"):
        header = f"💼【波段持倉中】#{rank} {symbol} ({name})"
    else:
        header = f"🔍【策略監控中】#{rank} {symbol} ({name})"

    lines.append(header)
    lines.append(f"💰 {bar_date_display} 收盤價：{_format_price(close)} ({change_str})")
    lines.append("")

    status_rd = r.get("status_rd", 3)
    rd_txt = "🟢 RD多頭向上" if status_rd == 3 else "🔴 RD空頭向下"
    trend_days = r.get("trend_days", 0)
    rsi_val = r.get("rsi", 50.0)
    conditions_met_count = r.get("conditions_met_count", 0)

    lines.append("📊 策略指標狀態：")
    lines.append(f" • 天圖主趨勢：{rd_txt} (已維持 {trend_days} 天)")
    lines.append(f" • 即時 1h RSI：{rsi_val:.1f}")
    if r.get("long_exit"):
        lines.append(f" • 訊號狀態：🛑 合約做多出場觸發 (1h RSI={rsi_val:.1f} > 70 超買獲利出場)")
    elif r.get("short_exit"):
        lines.append(f" • 訊號狀態：🔄 合約做空出場觸發 (1h RSI={rsi_val:.1f} < 30 超賣獲利出場)")
    elif r.get("has_already_exited"):
        lines.append(" • 訊號狀態：波段已獲利出場結案 (觀望新時序中)")
    else:
        lines.append(f" • 5 步時序進度：{conditions_met_count} / 5 條件滿足")
    lines.append("")

    checklist = r.get("checklist", [])
    if checklist:
        lines.append("📋 策略 5 步時序檢核：")
        for item in checklist:
            lines.append(f" • {item}")
        lines.append("")

    action_advice = r.get("action_advice", "")
    if action_advice:
        lines.append(f"💡 操作建議：")
        lines.append(action_advice)
        lines.append("")

    caution_note = r.get("caution_note", "")
    if caution_note:
        lines.append(f"⚠️ 注意事項：")
        lines.append(caution_note)

    # 對所有文字行進行 HTML 轉義，避免 <30, <50, >0 等字元導致 Telegram HTML 解析失敗
    escaped_lines = [html.escape(line) for line in lines]
    escaped_lines.append("")
    escaped_lines.append(f'<a href="{_get_tv_link(r)}">🔗TradingView 合約圖表</a>')

    return "\n".join(escaped_lines)
