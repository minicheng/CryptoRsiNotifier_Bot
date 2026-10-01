"""
訊號推播狀態管理模組
1. 記錄已成功推播至 Telegram 的訊號唯一 ID (signal_key) 與發送時間。
2. 避免每小時排程重複推播相同的舊訊號。
3. 自動清理超過指定天數（預設 14 天）的過期紀錄，保持狀態檔輕巧。
"""

import os
import json
import datetime
from config import NOTIFIED_SIGNALS_FILE, STATE_DIR


class SignalStateManager:
    def __init__(self, state_file=None):
        self.state_file = state_file or os.environ.get("NOTIFIED_SIGNALS_FILE", NOTIFIED_SIGNALS_FILE)
        self.state = {}
        self.load()

    def load(self):
        """從 JSON 檔案載入已推播紀錄"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
            except Exception as e:
                print(f"⚠️ 載入訊號狀態檔失敗 ({self.state_file}): {e}，將以空狀態初始化")
                self.state = {}
        else:
            self.state = {}

    def save(self):
        """將狀態儲存至 JSON 檔案"""
        try:
            folder = os.path.dirname(self.state_file)
            if folder and not os.path.exists(folder):
                os.makedirs(folder, exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"❌ 儲存訊號狀態檔失敗 ({self.state_file}): {e}")
            return False

    def is_notified(self, signal_key):
        """檢查該 signal_key 是否已推播過"""
        if not signal_key:
            return False
        return signal_key in self.state

    def record_notified(self, signal_key, symbol, sig_type, trigger_time=None, extra=None):
        """記錄訊號已推播"""
        if not signal_key:
            return
        now_str = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        self.state[signal_key] = {
            "symbol": symbol,
            "sig_type": sig_type,
            "trigger_time": trigger_time or "",
            "notified_at": now_str,
            "extra": extra or {},
        }

    def filter_new_signals(self, signals_dict):
        """
        過濾出尚未推播過的全新訊號。

        Args:
            signals_dict: {"long_entry": [...], "short_entry": [...], "long_exit": [...], "short_exit": [...]}

        Returns:
            dict: 僅包含未推播新訊號的 signals_dict
        """
        new_signals = {}
        for sig_type, items in signals_dict.items():
            unnotified = []
            for item in items:
                # 取得該訊號對應的 key
                if "entry" in sig_type:
                    s_key = item.get("entry_signal_key") or item.get("signal_key")
                else:
                    s_key = item.get("exit_signal_key") or item.get("signal_key")

                if s_key and not self.is_notified(s_key):
                    unnotified.append(item)
            new_signals[sig_type] = unnotified
        return new_signals

    def mark_all_as_notified(self, signals_dict):
        """將推播成功的訊號標記為已發送並存檔"""
        count = 0
        for sig_type, items in signals_dict.items():
            for item in items:
                symbol = item.get("symbol", "")
                if "entry" in sig_type:
                    s_key = item.get("entry_signal_key") or item.get("signal_key")
                    t_time = item.get("cond4_time", "")
                else:
                    s_key = item.get("exit_signal_key") or item.get("signal_key")
                    t_time = item.get("exit_time", "") or item.get("latest_bar_date", "")

                if s_key:
                    self.record_notified(s_key, symbol, sig_type, trigger_time=t_time)
                    count += 1
        if count > 0:
            self.save()
        return count

    def prune_old_records(self, max_days=14):
        """清理超過 max_days 天的舊紀錄"""
        cutoff = datetime.datetime.now() - datetime.timedelta(days=max_days)
        to_delete = []
        for key, info in self.state.items():
            notified_at_str = info.get("notified_at")
            if notified_at_str:
                try:
                    dt = datetime.datetime.strptime(notified_at_str, "%Y/%m/%d %H:%M:%S")
                    if dt < cutoff:
                        to_delete.append(key)
                except Exception:
                    pass
        for k in to_delete:
            del self.state[k]
        if to_delete:
            self.save()
