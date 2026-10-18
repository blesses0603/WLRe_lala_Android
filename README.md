# 飄流 RE:LaLa Android

**Android 測試版本：v0.0.7** ｜ **專案：`WLRe_lala_Android` ｜ 分支：`main`**

本專案用於開發《飄流 RE:LaLa》的 **Android 直式手機客戶端**，與 Windows／macOS 桌面版分開管理版本與建置流程。桌面正式版本請參閱 [`main` 分支](https://github.com/blesses0603/WLRe_lala/tree/main)。

## 📱 Android v0.0.7

本版新增可拖曳的 Android 懸浮小球：使用者開啟特殊權限後，在其他 App 上方查看遮罩帳號連線／自動戰鬥狀態。小球由原前景服務管理，關閉小球不影響連線；更多限制與授權說明見 [Android README](ANDROID/README.md)。

沿用 v0.0.6 的前景服務與安全帳號管理，v0.0.7 新增懸浮小球，目前包含：

- 每帳號的角色概況、包包／特技、小地圖、戰場陣形與手動指令、聊天、組隊、煉金、製作、經驗效率、事件紀錄。
- 完整 AI 規則、HP／SP 戰後補給、必要成員、配方收藏及自訂製作清單；詳見 [功能對照](ANDROID/FEATURE_PARITY.md)。

- **直式操作介面**：手機登入表單與地球／水星分流選擇。
- **多帳號工作階段**：同一個 App 可以建立多個獨立連線，並逐一停止。
- **角色選擇與連線狀態**：沿用 Python 遊戲通訊核心，提供初步選角和狀態顯示。
- **測試 APK 建置**：使用 Buildozer。更新 `main` 時，`android-smoke.yml` 會自動執行單元測試、模擬器相容性測試，並產生可供 ARM64 手機安裝的 Debug 測試 APK；僅推送版本 Git Tag（如 `v0.0.7`）或手動執行 `android-apk.yml` 才建立帶版本名稱的手機發布測試包。
- **帳號隱私**：可選用 Keystore AES-GCM 加密保存、切換及刪除帳密；未勾選時不保存。
- **背景服務**：獨立程序管理連線，常駐通知可返回或停止；畫面重建可重新附接。
- **資源監控**：連線數、畫面／服務記憶體、裝置電量／溫度與取樣時間。

> **待實機驗收**：正式服登入、Keystore、切 App 與鎖屏仍須在手機驗證。Android 15 dataSync 背景服務有累計時限；不保證永久在線。自動戰鬥／徘徊及功能頁已整合，真機操作仍待驗收。

## 🧪 取得與測試 APK

1. 日常提交 `main` 的程式碼時，`android-smoke.yml` 自動進行單元測試、Python 語法檢查、Android 12～16 模擬器啟動測試，**並產生 ARM64 手機測試 APK**。在 [Smoke Actions](https://github.com/blesses0603/WLRe_lala_Android/actions/workflows/android-smoke.yml) 的執行頁下載 `Android-arm64-apk` Artifact，解壓後安裝 `WLRe_LaLa-Android-arm64-debug.apk`；`Android-emulator-apk` 僅供 x86_64 模擬器測試。
2. 發布新版本時，同步更新 `buildozer.spec` 的 `version` 與 `android_app/version.py` 的 `ANDROID_VERSION`（例如 `0.0.7`），將修改提交至 `main`，確認測試成功後建立並推送 `v0.0.7` Git Tag。
3. Git Tag 自動觸發 [手機 APK Actions](https://github.com/blesses0603/WLRe_lala_Android/actions/workflows/android-apk.yml)；也可以在 Actions 選 **Run workflow** 從 `main` 手動建置目前版號。
4. 手機 APK 成功後，在該次執行的 **Artifacts** 下載 `WLRe_LaLa-Android-v<版本號>-debug`，內含對應版本 APK 與 `SHA256SUMS.txt`。
5. 解壓 ZIP 並安裝到 Android 手機，先驗證 App 啟動、直式版面與分流選單，再以測試帳號驗證伺服器連線及選角。

**v0.0.2／v0.0.3 已知會在 Keystore 初始化時觸發 JNI 原生中止，請勿使用舊產物。v0.0.4／v0.0.5 已通過 Android 12–16 啟動流程；v0.0.6 增加完整手機功能頁；v0.0.7 新增懸浮小球，應下載新專案建置成功後的最新產物。**

📖 **[完整 Android 開發狀態、安全注意事項及測試步驟](ANDROID/README.md)**

## 📂 主要檔案

| 路徑 | 用途 |
| --- | --- |
| `ANDROID/README.md` | Android 專用詳細說明 |
| `android_app/` | Android 直式介面、多帳號工作階段 |
| `main.py` | Android 啟動入口 |
| `buildozer.spec` | Android APK 打包設定 |
| `.github/workflows/android-apk.yml` | GitHub Actions 安卓測試建置流程 |
| `wlre/` | 沿用中的遊戲通訊及服務核心 |
