# Android 第 08 項｜帳密生命週期與診斷資料最小化

基準：Android v0.0.8、main commit 6e6aa268d2af38fcc7ef5f4eca9a2ab5d6922097（Phase07 已合併）。保留 Phase05 ARM64 八個原生核心、Phase06 IPC 同 UID 驗證、Phase07 runtime signer pin、固定簽章與現有 Android Keystore alias/密文資料格式。

## 本階段落地變更

1. **Activity 帳號清單不快取明文密碼**。新增 \`android_app/credentials.py\` 的 metadata-only \`public_accounts\`；初始化時仍用原 Keystore 密文解出紀錄，但介面長期只留 \`server/account\`。選取已保存帳號才 \`vault.load()\` 並將所選密碼放入密碼輸入框；送出登入、暫停、停止、介面重建時沿用原本清除輸入框的動作。保存/刪除時重新從密文保管庫讀取完整紀錄，以原密文格式回存，保留其他帳號並避免明文長期存在 \`self.saved_accounts\`。
2. **背景 IPC 命令不持續保有帳密參照**。\`ServiceManager.call\` 在成功或失敗後立即移除已取出的 \`request['args']['password']\`，服務端 \`Runtime.dispatch\` 在交給 \`SessionManager.start\` 後（包括例外）也會移除該參照。這降低被佇列、診斷工具誤取到的風險，但 **Python 字串和仍在連線中的登入流程不能保證從記憶體中立即擦除**。
3. **診斷產物不再保存原始 \`logcat\` 與 \`dumpsys\`**。\`tools/android_diagnostic_redaction.py\` 只保留固定 WLRE 就緒事件、允許清單內的錯誤種類與診斷計數，不複製例外原文、Android Intent extras、裝置路徑或任意後綴文字。測試失敗時 console 也只輸出這份摘要，不印出原始診斷，避免 CI Artifacts/Actions Log 帶出帳密。

## 回歸驗收

- 驗證保存兩個帳號、更新其中一個、只刪除目標帳號、重新選擇時才解密，並保留既有完整密文格式。
- 驗證 Keystore 解密錯誤時 UI 清空舊密碼，錯誤訊息不帶解密例外內容。
- 驗證 IPC 登入命令在成功及失敗時都移除佇列中密碼參照。
- 驗證包含 \`password=\`、\`Bearer\`、帳號字串、Android 原始錯誤與檔案路徑的診斷素材，輸出不帶入任一私密內容。
- PR 只跑快速回歸，不啟動完整 Nuitka／Android Buildozer APK；正式 main/tag 的原有固定簽章安全門檻保持不變。

## 必須誠實保留的限制

- \`saved_password()\` 會短暫產生 Python \`str\`，Kivy 密碼輸入框也會短暫持有明文。標準 CPython、Cython/JNI 的不可變字串無法保證零化，因此此項是**縮短參照生命週期**，不是零敏感資料記憶體。
- 畫面或系統已被 Root/Hook 的惡意元件監視時，本地資料仍可能遭存取。第 07 項的本地 pin 不取代 server-backed attestation。
- 診斷產物變成保守摘要，會犧牲逐行堆疊資訊；必要時應讓使用者在可信裝置上明確同意本機收集詳細日誌並安全移交，不能把未遮罩原始內容上傳公開 Actions。
- 本階段 CI 與單元測試成功不等於實際 Android 12+ ARM64 的密文升級、背景服務／長時間多帳號已完成真機驗收。版本仍是 v0.0.8。

## 發布與合併

PR 通過全部 Python 及 CI 安全測試後合併 main；只在後續正式固定簽章 APK 發行時重新打包，維持一般開發不觸發完整 Android APK Build。
