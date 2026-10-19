# Android 第 06 項｜巢狀封裝、帳密檔案與 IPC 安全強化

基準：main 694c324fa28c7754b88ad2c41b755f78fb14341b，Android v0.0.8；前項 Phase05 八個 P0/P1 Cython 核心已合併。

## 目標及實作

1. **APK 深層稽核（tools/android_archive_audit.py）**：保留 Phase03 既有的 APK 外層及 private.tar 檔名／ABI 檢查，再增加 APK、p4a 的 private.tar、libpybundle.so TAR 及內嵌 ZIP/TAR 等逐層驗證。檔案名稱、硬連結／軟連結／危險路徑、大小與深度限制、重複檔名、常見私鑰與憑證特徵會 fail closed。使用 streaming 讀取 TAR、限制 ZIP/TAR 巢狀記憶體負擔，不解壓到磁碟，錯誤資訊不印出秘密。
2. **IPC（android_app/runtime.py）**：前景服務的私有 Unix socket 在接受 client 後，用 Linux SO_PEERCRED 確認來源 UID 與 Android App 同 UID（必須支援 SO_PEERCRED，否則拒絕）。對 UI→service 和回覆的 JSON frame 限制最大長度，要求完整換行與物件格式，拒絕重複 JSON keys、NaN、不合法 UTF-8 或截斷封包；不把敏感 payload 寫入例外訊息。
3. **AccountVault（android_app/vault.py）**：保持 Android Keystore AES-256-GCM 密鑰與 alias 不變。密文檔案改用 O_NOFOLLOW 讀取並確認普通檔案；保護 parent 為 0700、暫存檔 O_EXCL|O_NOFOLLOW 0600，防止 symlink 重導或 pre-planted 暫存檔覆寫外部資料。資料仍以原 JSON 加密格式保存。
4. **CI**：一般 PR 仍只做 Python/Security 測試，正式固定簽章 APK 工作流依原設計在報告前執行 python tools/android_hardening.py report，因此將自動啟用深層稽核，不增加日常打包次數。不更換簽章、不改變 Android 12+、ARM64-only、Phase05 原生建置配線。

## 測試與驗收

- 腳本／資料：tests/test_android_phase06_security.py，包含惡意巢狀 ZIP→TAR、libpybundle 隱藏憑證、重複檔名、目錄跳脫、symlink、PEM 片段、正常封包與封裝相容性。
- Android IPC：正常 request/reply、異常 JSON、重複鍵、NaN、UTF-8、上限、SO_PEERCRED 相同/不同 UID。
- 加密儲存：正常存取及二次儲存、0700/0600 權限、symlink 與預置暫存檔保護。
- PR 快速 CI 全綠即可合併 code；新 APK 的最終 Android 12+ ARM64 真機帳號讀寫、跨程序連線仍需下一次正式固定簽章建置與真機驗收，不把 Python 模擬當成實機證據。

## 已知邊界

這是**靜態 APK 已知秘密樣式**防洩漏閘門，不可檢出所有硬編碼秘密；加密、混淆及大型二進位內容無法全面自動判斷。允許的掃描文字檔大小、巢狀 ZIP/TAR 深度與解壓資料量均有界，超出適用條件的巢狀封裝拒絕發布。此項不是反 Hook、執行時防篡改（第 07 項），也不宣稱 Cython 無法還原。
