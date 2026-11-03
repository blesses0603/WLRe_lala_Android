# 飄流 RE:LaLa｜Android

目前程式：**v7.1.8 開發修補候選（未正式發布）**。Android Major.Minor 與桌面版最新 main v7.1.1 同為 7.1，Patch 獨立維護。本版針對 Android v7.1.7 真機顯示 `DataPackage.hash；TLS 憑證驗證失敗`，修正原 Manifest／Bundle 使用 urllib 預設 SSL 憑證查找路徑、與官方版本查詢不同的問題：改為由 Android 的驗證 HTTPS 處理器明確載入 `SSL_CERT_FILE` 指定的 certifi／Android 系統 CA；仍要求 TLS 憑證鏈及主機名稱驗證，並保留拒絕轉址、Manifest CRC32 與 Bundle MD5／CRC。v7.1.7 已增加 Manifest 下載階段固定診斷與同源受限重試。本次是否真正修復實機憑證連線，仍須完成 v7.1.8 ARM64 APK 及真機實測。

Android 12 以上、ARM64。保留 Kivy 直式觸控介面、前景連線服務、懸浮球、Android Keystore、固定簽章與八核心原生封裝。Android 與桌面版各自維護版本號。

**Android 啟動流程：**先顯示獨立「官方資料與資料庫檢查」畫面，背景服務完成官方版本、雙 Manifest、必要 Bundle、Runtime 與 SQLite 驗證後，手機介面端再獨立核對同一份 Catalog 身分；**兩端都確認 ready 且 SHA-256 來源識別一致，才顯示帳號／密碼輸入畫面**。未通過時保留原因、重新檢查及啟動服務入口，不提供跳過驗證。


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

既有 P1／P2 保存 **ccache 編譯物件**與明確白名單的第三方 p4a Recipe 目錄。**P3 新增八個 LaLa 原生核心個別的 SHA-256 命中快取**，僅保存受信任 main／版本 Tag 已通過完整固定簽章與 APK 安全稽核的 ARM64 `.so`，不保存 APK、中繼 Distribution、完整 `python-installs`、Android Keystore、Secret、原始遊戲資料或帳密。每次仍從隔離 staging 重新封裝 APK、固定簽章並完成所有原生／資源／版本安全檢查。

**P1：** `ccache` 按編譯器內容與旗標重用 C／C++ 物件。**P2：** 只快取十個第三方 Recipe 及來源，綁定 Runner 映像／p4a／NDK／相依需求。**P3：** 依八核心各自的 staged `.pyx`、Recipe、共用快取規則、p4a 與工具鏈算出獨立 SHA-256；命中時重新檢查收據、檔案 SHA-256、大小及 ARM64 ELF，直接還原對應 native extension，缺漏、篡改、版本不同或未知 Runner 則執行原本 `CythonRecipe` 編譯。快取是最佳化，不是信任憑證。

本次僅調整 CI／測試／文件，Android 版本保持 v7.1.5；是否真正命中、節省多少編譯時間及 ARM64 APK／真機驗收，以後續受信任 main 手動建置的實際紀錄為準。詳細限制與驗收見 [Android 建置說明](ANDROID/README.md)。

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
