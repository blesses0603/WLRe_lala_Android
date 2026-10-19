# Android 第 09 項｜正式 APK 發布證據與版本完整性門檻

基準：main 3fe7c20ff5df64b52e14b4710d9db0fa4c0ae7d3（第 08 項已合併）；Android v0.0.8。**不重新產生任何簽章、金鑰、版本或 Release Tag，不在一般 PR 打包 APK。**

## 本次實作

1. **移除 CI 寫死的 v0.0.8**：原先正式 Buildozer stage 固定檢查等於 v0.0.8，會在未來改版時誤擋正確版本。現在改用 android_release_version.py 確認過的動態 RELEASE_VERSION 比對原始及暫存專案版本。
2. **正式上傳前驗證實際 APK metadata**：tools/android_release_gate.py 使用 Android SDK aapt dump badging 檢查 package=org.lala.client.wlrelala、實際 versionName 與兩處原始碼版本一致、versionCode 為正整數、minSdk=31、targetSdk=35。版本 Tag 必須吻合 vX.Y.Z；手動建置僅限 main；source SHA 必須是完整 40 位 Git Commit。
3. **驗收檔缺失一律阻擋**：最終發布目錄必須只有一個確定命名、可開啟的 APK、SHA256SUMS.txt 及七份來自前期檢查的報告：
   - NATIVE_WIRE_INFO.txt
   - NATIVE_VAULT_INFO.txt
   - PHASE05_ALL_CORES_INFO.txt
   - PRESPLASH_INFO.txt
   - SIGNING_INFO.txt
   - RUNTIME_INTEGRITY_INFO.txt
   - PROTECTION_INFO.txt
4. **拒絕舊式、失敗或混淆簽章證據**：簽章報告必須顯示 persistent 固定測試簽章與公開 SHA-256 憑證 pin 已驗證；公開憑證身分須與 CI 預期相符。八核心安全檢查、Phase06 ZIP/TAR 防護、Phase07 編譯 DEX 完整性等必須各自留下 PASS/VERIFIED 證據。APK SHA256SUMS 必須與實際檔案完全一致。
5. **發布清單與報告校驗**：全部驗證通過才產出 RELEASE_EVIDENCE.json，記錄 GitHub Commit/Ref/Event、APK SHA256/版本/API/檔案大小、驗收報告名稱與各檔 SHA256；另產出 REPORT_SHA256SUMS.txt 對證據與報告作核對。任何缺失、安全稽核失敗、未預期多出的檔案/keystore、版本不符、錯簽章都不上傳 Artifact。

## 安全邊界

- 本階段產出可核對、非秘密資訊清單，**不是** Sigstore、SLSA 高等級來源證明、不可篡改簽署憑證、APK reproducible build 或 Play Integrity 遠端 attestation。
- 私鑰仍只在固定簽章工作步驟使用。公開 SHA256 可以列入報告，CI 還需要 GitHub 分支保護與權限最小化。
- aapt 確認 APK metadata 是必要但不充分，實際 ARM64 八核心、runtime signer/DEX、深層敏感資料稽核仍由專用 APK 工具執行。
- 正式 v0.0.8 目前仍是 Debug 測試簽章，不是 Play 商店的正式 Release 金鑰。不同舊簽署者或 versionCode 不相容的手機不保證可直接升級。
- 第 09 項完成程式與 PR 回歸後合併 main。實際新版 APK 建置與 Android 12+ ARM64 真機覆蓋更新/背景服務/Keystore 驗收留給第 10 項，不能把單元測試假造的 aapt 輸出當實際 APK 測試。

## 執行與驗收

正常 PR：python -m unittest discover -s tests -q，不使用私鑰、不編譯 APK。

Release 於 main 手動或版本 Tag 觸發 android-apk.yml，android_release_gate.py 在 APK 固定重簽、native/presplash/signing/runtime/hardening/sha256 全部通過後、上傳前執行。版本/commit/ref/event/公開憑證 pin 均從當次 GitHub Actions 上下文帶入。

第 09 項程式通過 GitHub Actions PR/merge 快速測試後合併 main，原有 Phase04-08 核心保留。
