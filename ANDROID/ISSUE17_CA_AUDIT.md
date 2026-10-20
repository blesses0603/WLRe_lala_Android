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

## 2026-10-20｜Run #39402846197 仍使用未合併的 main

- [Run #39402846197](https://github.com/blesses0603/WLRe_lala_Android/actions/runs/39402846197) 再次在 `android_archive_audit.py:_safe` 發生相同 `Potential credential file in nested archive`，其餘原生編譯、固定簽章、Phase04/05 與 presplash 皆通過；SHA256、Phase09 與 Artifact 因前置稽核失敗未完成。
- 原因：Run 執行時 [PR #20](https://github.com/blesses0603/WLRe_lala_Android/pull/20) **仍未合併 main**，原安全稽核程式無法套用 PR 裡的 p4a 公開 CA 精確路徑修正。不能由這個 Run 判斷 PR #20 的修正有效或無效。
- 為降低後續完整 ARM64 建置的除錯成本，PR #20 追加匿名化拒絕診斷，只顯示 `rule=reserved-name`、`rule=restricted-extension` 或 `rule=ca-bundle-location` 與路徑階層數。不輸出原始檔名、原始路徑、檔案內容或金鑰。
- 新增匿名化安全回歸測試，確保真正的敏感路徑仍被封鎖且不會洩漏檔名。
- **必要驗收順序**：PR 快速 CI Success → 授權合併 `main` → 由 `main` 手動執行新 Run（不要重跑舊 Run）→ 確認 Phase04–09、SHA256 與 Artifact → 再進行 Phase10 實機驗收。

## 2026-10-20｜Run #39407353092：Phase06 大型巢狀封存修正

- [Run #39407353092](https://github.com/blesses0603/WLRe_lala_Android/actions/runs/39407353092) 確認基於已合併 PR #20 的 main（`8813ef3b`），原 `Potential credential file` 未再出現，CA 憑證驗證繼續執行。新錯誤為 `_payload` 的 `Nested archive exceeds Phase06 safety limits`。
- 舊實作對 ZIP／TAR 採最多 24 MiB 完整讀入記憶體，超限即拒絕；但 APK 的合法圖片／地圖資源也可能封裝為較大 ZIP。目前失敗日誌未指出具體超限檔案與大小，無法宣稱已排除所有後續障礙。
- 新修正對不超過 24 MiB 的巢狀封存沿用記憶體路徑；較大的 ZIP／TAR 使用 `SpooledTemporaryFile`，透過分塊拷貝至自動清除的暫存檔，再由現有 ZIP／TAR 稽核器逐項檢查。並未直接略過 ZIP、檔名、金鑰標頭或文字檢查。
- 硬限制：單一封存最大 **256 MiB**、同一 APK 磁碟暫存總量 **384 MiB**、原遞迴深度 **4**、原檔案數 **20,000**、小型文字總掃描量 **64 MiB** 與其餘安全規則均保留。超限仍會 Fail Closed；錯誤僅輸出類別、封存類型與深度／容量級距，不洩漏原始檔名、路徑或內容。
- 補充大型 ZIP／TAR 成功掃描、巢狀敏感檔與私鑰內容阻擋、總暫存額度、深度與容量限制回歸測試。
- 確認 PR 快速 CI 後，須先合併主分支，再 **開新的** ARM64 手動建置驗證正式 APK；未通過 Phase04–09、SHA256 與 Artifact 上傳之前，不關閉 Issue #17。真機驗收另於 Phase10 完成。
