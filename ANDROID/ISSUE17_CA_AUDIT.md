# Issue #17｜Android ARM64 APK 公開 CA 憑證安全稽核

## 證據與根因

- 失敗的 GitHub Actions Run：`39342830646` 與 `39355865501`。
- 兩次皆已完成 ARM64 編譯、固定簽章、原生核心與啟動圖檢查，
  但 `tools/android_hardening.py report` 於巢狀 TAR 檔名稽核拋出
  `ValueError: Potential credential file in nested archive`。
- Run `39355865501` 原始記錄確實顯示 python-for-android 安裝
  `certifi-2026.10.18`，並把 `certifi/cacert.pem` 放進 Python bundle
  的 `site-packages`；這是公開 HTTPS CA 信任根清單，並非私鑰。
- 因先前稽核刻意不輸出受阻擋的檔名，這是根據建置記錄確認的
  **高可信誤判候選**，待新版 APK 完整稽核成功後才能確認已排除
  所有同類建置阻礙。

## 精準修正

- 僅對 `certifi/cacert.pem` 或 `site-packages/certifi/cacert.pem`
  這兩個確切巢狀 TAR 路徑放寬「單憑 .pem 副檔名即拒絕」的規則。
- 內容仍強制讀取並檢查：最多 512 KiB、至少一個可成功解析的
  X.509 `BEGIN CERTIFICATE` 區塊，其餘內容只可包含空白及
  certifi 標頭註解；其他 PEM 區塊與敏感金鑰標記皆拒絕。
- 原本 `.key/.jks/.p8/.p12/.keystore` 等副檔名、帳密檔名、
  其他 `.pem`、巢狀 ZIP/TAR 的路徑穿越、符號連結、重複項目、
  深度和掃描上限照舊執行。
- 稽核的兩層檔名檢查與內容檢查保持一致；拒絕時不記錄原始
  憑證內容或可疑檔名。
- 新增正例與反例回歸測試；測試自行產生臨時自簽憑證，只使用
  **公開憑證**，不把測試私鑰寫入檔案或放進 APK。

## 驗收門檻

1. PR 僅執行 Android fast CI（無 APK），測試全部通過再合併 `main`。
2. Android ARM64 固定簽章 APK 須從新的 `main` 手動建置，不能用
   PR 的 CI 結果充當已通過完整 APK 安全稽核。
3. 最終必須實際成功產出 `PROTECTION_INFO.txt`、原生核心稽核、
   `SHA256SUMS.txt`、簽章報告、Phase09 release evidence，以及 APK Artifact。
4. 真機安裝、背景服務／連線驗收仍須另外完成。

安全檢查不能因單一例外被整體停用；若真實 APK 仍報錯，維持
fail closed 並重新分析原因。
