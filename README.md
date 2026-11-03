# 飄流 RE:LaLa｜Android

目前程式：**v7.1.3 開發修補版**。Android Major.Minor 與桌面版最新 main v7.1.1 同為 7.1，Patch 由 Android 獨立維護。本版新增完整 Runtime 失敗階段與下載額度的安全診斷，保留 TLS、Manifest、Bundle 完整性及登入阻擋規則；APK 建置與手機登入仍待驗收。v7.1.2 為 TLS 修補版。v0.1.0 已有成功 APK 建置及手機啟動畫面，尚未通過官方資源與登入驗收。

Android 12 以上、ARM64。保留 Kivy 直式觸控介面、前景連線服務、懸浮球、Android Keystore、固定簽章與八核心原生封裝。Android 與桌面版各自維護版本號。

## 本次桌面功能同步

以桌面 main v7.0.1 及 PR #65 的遊戲核心為來源，精確提交與逐檔雜湊記於 [來源鎖定](ANDROID/DESKTOP_SOURCE_LOCK.json)。桌面 Tkinter／Nuitka 與桌面發佈流程不搬進 Android。

| 範圍 | Android 本次整合 |
| --- | --- |
| 官方資源與 SQLite | 共用動態 Runtime、雙 Manifest 驗證、資料庫與官方資料一致性檢查；驗證完成前不登入，不退回舊資料冒充新版 |
| 帳號、角色、戰鬥、AI、補給、隊伍、聊天 | 同步共用核心，保留多帳號隔離與手機操作入口 |
| 遠征、煉金、製作、材料共用預留 | 同步最新服務與回覆確認，製作包含雜物櫃材料與排程整合 |
| 地圖與傳送 | 同步實體門配對、StageMap-only 入口與目的地無圖片時的已核對出口操作 |
| NPC | 新增官方清單、前往、互動、對話、明確選項與唯讀商店預覽；未知選項不代選，實際商店買賣維持桌面版相同限制 |
| 帳篷與儲藏 | 新增展開、收起、進入、離開及儲藏室／雜物櫃存取；等待伺服器與庫存確認 |
| 福利 → 魔方 | 新增已分析魔方自動開啟、倒數與狀態；關閉頁面仍由服務排程，逾時不重送 |
| 自動接續 | 新增全域暫停、NPC／製作接續與免費協力領獎；**副本與協力開始維持手動** |
| 操作確認 | 移除重複是／否確認，保留必要的數量、密碼、答案與目標輸入，以及後端驗證 |

上表代表原始碼整合範圍，不代表 APK、手機背景執行或正式伺服器已驗收。完整範圍及限制見 [本次同步紀錄](ANDROID/DESKTOP_SYNC_20261103.md)。

## Android APK 建置快取（不更動版本）
  
手動／版本 Tag 完整 APK 工作流程在受信任 main 執行時，會使用對應的 Python pip 套件快取及 Android SDK／NDK r28c、Gradle 下載快取。平台快取會依 p4a commit、API／ABI、相依需求以及實際 Buildozer／Cython 版本產生指紋，**純 App Patch 版號改變不會造成工具鏈快取失效**。

只快取第三方建置依賴，**不快取 Cython 原生編譯輸出、APK、中繼封裝、Android Keystore 或 GitHub Secret**。每次仍從隔離 staging 重新打包 ARM64 APK、使用既有固定簽章並執行完整檢查。快取失效時仍走原本下載／建置流程；首輪需成功產生快取，後續命中率與時間節省需要以 Actions log 實測。

此修改為 CI／文件／測試調整，Android 版本維持 v7.1.3。詳細限制與驗收見 [Android 建置說明](ANDROID/README.md)。

## 開發與驗證

```bash
python -m pip install -r requirements-dev.txt
python tools/android_resource_seed.py
python tools/android_parity_audit.py
python -m unittest discover -s tests -q
```

圖形測試需要可用的顯示環境。Linux CI 使用 Xvfb。初始 SQLite 從鎖定的桌面提交取得，驗證固定大小、SHA-256 與資料庫內容後，才供本機測試及 APK staging 使用；不把 27 份歷史 JSON／ZIP 再複製一份隨 APK 打包。

手機端使用私人資料目錄，官方資源準備由服務執行；Activity 從同一私人快取獨立驗證並啟用 Runtime，不由 IPC 傳遞整套靜態目錄或帳密。

一般 PR 執行快速回歸，**不產生 APK**。完整固定簽章 APK 維持 main 手動或合法版本 Tag 的既有流程，不自動合併、不建立正式 Release。詳見 [建置說明](ANDROID/README.md)、[簽章](ANDROID/SIGNING.md)、[安全](ANDROID/SECURITY.md)。
