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

## 2026-10-20｜Run #39367836286 後續根因與修復分支

- [Run #39367836286](https://github.com/blesses0603/WLRe_lala_Android/actions/runs/39367836286) 已完成 APK 編譯、固定憑證重新簽章、Phase04/05 報告及 presplash 檢查；在 `android_hardening.py report` -> `android_archive_audit.py:_safe` 遇到 `Potential credential file in nested archive`，因此 SHA256、Phase09 與 Artifact 上傳未執行完成。
- 追查 python-for-android 的 `libpybundle.so` 打包方式：其 TAR 成員根目錄包含 `_python_bundle/site-packages/`，故 certifi 公開根憑證的實際 TAR 相對路徑為 `_python_bundle/site-packages/certifi/cacert.pem`。原稽核僅白名單 `certifi/cacert.pem` 與 `site-packages/certifi/cacert.pem`，會拒絕帶根目錄的合法路徑。此為可由 p4a 封裝結構與單元測試重現的路徑不一致；由於失敗的 CI 沒有保留 APK，仍須由下一次完整建置確認真實封存沒有其他受阻檔案。
- 本次僅增加 **完整字串完全相符** 的 `_python_bundle/site-packages/certifi/cacert.pem`，不放寬任意前綴或 `.pem`。原本的 **X.509 公開憑證解析、512 KiB 限制、私鑰標頭／未知區塊攔截、危險副檔名、路徑穿越、重複項與巢狀封存上限** 照舊。
- 回歸測試涵蓋 p4a 真實前綴、`./` 正規化、錯誤前綴／假冒路徑、私鑰標頭、混合敏感內容、畸形憑證及尺寸限制。
- 正式打包依原有流程 **僅允許 main 手動或合規版本 Tag**。修復分支 PR 不持有簽章 Secret，也不可用 PR 快速 CI 取代正式 ARM64 編譯及 APK 檢查。Issue #17 必須等正式 APK Artifact、稽核與 Phase09 成功再關閉。
