# Android 專案遷移 — 2026-10-18

來源：blesses0603/WLRe_lala 的 android-development，提交 f38bd2a12164aced0df31c507e79f86f4a8a7741。原始歷史仍保留於來源專案 Git 歷史。

本專案 main 專責 Android；APK 與 Android 12–16 模擬器流程均改以 main 觸發。套件 ID、Keystore 行為及手機圖示不變。沒有搬入帳密、執行期資料、桌面 Tk 介面、BAT 或 Nuitka 發布流程。

wlre/core、network、services、storage 與 resources 是手機必需的核心及資料，採用本地副本，建置不依賴另一專案。共用核心修正不會自動跨專案同步；修改後需明確移植並在兩邊驗證。來源 wlre/ui/minimap.py 的無介面圖片／投影工具移到 wlre/services/world/minimap.py，Android 呼叫一併調整。

移入目前核心的歷史座標上限及每兩小時清理，保留自己的位置。桌面顯示佇列屬於桌面介面，沒有移入。

歷史驗證文件記錄的是遷移前的建置；新專案 Actions 成功前，不代表已有新的 APK 或已完成新的 Android 實機驗收。Debug 簽章由 CI 產生，可能與舊 APK 不同；若安裝時簽章不符，請先保留設定並確認移除舊 App 的資料損失再處理。

本地測試：安裝 requirements-dev.txt，設定 JDK 17，使用 xvfb-run -a python -m unittest discover -s tests -q。手機 APK 使用 android-apk.yml；android-smoke.yml 產出 x86_64 模擬器包，不可當手機包。

## 遷移後本地驗證

Android 獨立專案：94 項測試全部通過，包含實際 Java／PyJNIUS 加密橋接、手機介面、帳號隔離、自動戰鬥／煉金核心、快照節流及座標快取。Python 語法與 Actions 靜態檢查通過。測試在 Linux／Python 3.11／JDK 17／虛擬顯示器執行，不代表新專案 APK 已成功打包或通過真機測試。
