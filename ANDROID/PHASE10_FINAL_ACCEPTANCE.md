# Android 第 10 項｜正式 ARM64 APK 與實體手機終驗

基準：第 09 項已合併的 main commit af355ccd5e00744d1ea142f98a8f0fa7e1c4e3fa。版本仍為 v0.0.8；未新增 Release Tag，也未更換固定簽章或 Android Keystore。

## 真正的發行驗收流程

**已實作並可透過 PR 快速測試完成的部分**

1. tools/android_phase10_acceptance.py 提供雙層離線驗證：
   - 從正式 GitHub Actions 下載 ZIP Artifact，解壓至新資料夾後，以 verify-artifact 檢查唯一 APK、原生八核心、安全簽署者、SHA256SUMS、Phase09 發布證據 JSON、七份安全報告及其 SHA256 和來源 Commit。
   - 必須有 Android SDK apksigner 才能從實際 APK 取得簽署憑證；如果缺少、憑證不符或證據遭修改，直接失敗。檢查正式 APK 時應傳入正確 main Commit，不能用較舊的實驗 APK 代替。
   - device-preflight 僅用 ADB 讀取 SDK、ABI、是否為模擬器；**不安裝、不卸載、不清資料、不讀帳密、不上傳 logcat**，結果不含手機序號。
2. GitHub 快速測試涵蓋 APK/報告/雜湊篡改、簽章不符、舊 Commit、來源分支、錯誤 API、模擬器、32-bit 裝置及危險 ADB serial 等失敗情境。
3. 原正式 APK Build Action android-apk.yml 維持**只有 main 手動執行或符合規範的 vX.Y.Z Tag 才啟動**，不會因一般 PR/merge 而自動跑 2 小時 ARM64 建置。

**需要真實執行後才能標記成功的部分**

- [ ] 在 GitHub [Android ARM64 native phone APK (pinned signing)](https://github.com/blesses0603/WLRe_lala_Android/actions/workflows/android-apk.yml) 選 main，按 Run workflow。等這次完整 Run 的 Success/Artifact 實際出現，下載 WLRe_LaLa-Android-v0.0.8-debug ZIP。
- [ ] 核對 Artifact 來源 Commit 是此次 main 且 Phase04-09 七份報告、RELEASE_EVIDENCE.json 與 REPORT_SHA256SUMS.txt 均齊全；實際 signed APK 通過 apksigner。不得用舊 Run #39239015254 作為完整八核心新版證據。
- [ ] 請先確認手機目前 App 的簽署憑證與新版是否一致。**不同簽章的 APK 無法直接覆蓋；絕不可自動解除安裝以強行繼續。**先整理重要資料及原帳密後再決定下一步。
- [ ] 以 Android 12+ arm64-v8a 實體手機完成新版 APK 安裝／覆蓋，正常打開 App 並驗證 Activity Java/Kivy、前景 Service、Android Keystore 及新 runtime pin（A07）未阻擋正確簽章。
- [ ] 使用測試帳號驗證保存密文、重啟選取、刪除一筆、其他帳號不受影響、密文遭竄改時安全失敗，且不向 logcat 或 GitHub Artifact 保存密碼。
- [ ] 兩組帳號 A/B 分別登入、選角色、切換卡片／停止其中一組，確認另一組保持在線；需使用**使用者控制的測試帳號**，不在公共報告附帶密碼、帳號名稱或封包內容。
- [ ] 背景 Home、通知返回、螢幕鎖定 15／30／60 分鐘各做一次，記錄前景服務是否仍活著與實際遊戲連線（不是只看 PID）。
- [ ] Wi-Fi 與行動網路切換、省電模式、單帳號斷線／恢復、遠征 ACK／自動戰鬥操作在手機上實際驗證。
- [ ] 如安排重簽破壞性測試，只能在**備用裝置／測試帳號**進行；確認簽署者不符被 A07 拒絕。不得冒險破壞主要安裝的私有帳密。
- [ ] 填寫最終驗收結果及裝置版本／結果摘要。**未收到真機回報，不可把第 10 項標成完整驗收成功，也不能以 CI 主機模擬替代。**

## 離線 Android SDK 驗證（有 Windows、macOS 或 Linux + adb/apksigner 才適用）

在 Artifact ZIP **解壓後的資料夾**：

    python tools/android_phase10_acceptance.py verify-artifact PATH_TO_EXTRACTED_ARTIFACT --expected-commit MAIN_COMMIT_SHA

工具要求 apksigner 可透過 PATH 取得；若 Android SDK 安裝在其他目錄，可加 --apksigner ABSOLUTE_PATH。

手機已用 USB 啟用 ADB、已授權且使用者自願時，可選擇只讀預檢：

    adb devices -l
    python tools/android_phase10_acceptance.py device-preflight --serial DEVICE_SERIAL

手機預檢**不會**安裝 APK、不會測試登入、不會造成資料遺失。若使用者只有手機，直接手動驗收打包結果與 UI／帳號功能，不必使用 ADB。

## 最終交付狀態格式

| 驗收層 | 合格證據 | 初始狀態 |
| --- | --- | --- |
| 原始碼/CI | main 快速測試 Success | 等 PR 合併後 Run |
| 真正 ARM64 APK | 最新 main 的 Android APK Run Success | 未執行 |
| 七份安全報告＋簽章＋Release Evidence | 同一 Run Artifact 與離線校驗 | 未執行 |
| Android 12+ ARM64 真機 | 人工或 ADB 只讀檢查加上實際操作紀錄 | 未執行 |
| 更新/簽章相容 | 使用者實機覆蓋安裝或驗證無法覆蓋的原因 | 未執行 |
| 第 10 項終驗 | 前述全部驗證且能安全使用 | 未完成 |

整份文件不應紀錄帳號、密碼、原始 logcat 或手機唯一識別碼。這是正式 Debug 測試 APK 的驗收，不是 Play 商店正式 Release 發行，也不是無法逆向的安全保證。
