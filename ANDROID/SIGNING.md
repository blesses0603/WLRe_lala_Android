# Android ARM64 固定簽章與指紋鎖定（第 02 項）

> 本機／GitHub 的測試簽章是 Android APK 安裝與升級身份，與帳號的 Android Keystore、APK SHA256SUMS、Python Cython 防逆向是不同機制。

## 實際狀態與發布政策

- **正式提供給手機更新的手動 main／Tag 版本 APK**：必須提供私有簽章金鑰 **以及**獨立的公開憑證 SHA-256 指紋鎖定；兩者任何一項不存在、無效或不一致就停止建置／上傳，不能退回隨機 Debug 簽章。
- **Buildozer Debug 特例**：Gradle 有時使用自己的 Debug 簽章，而不是 CI 事先恢復至 `~/.android/debug.keystore` 的金鑰；因此正式可下載 APK 在編譯完成後，會先由 `apksigner sign` 用固定金鑰重新簽署、以公開指紋驗證通過，才產生 `SHA256SUMS.txt`、`SIGNING_INFO.txt` 和上傳。PR 不取得私鑰也不重新簽署。
- **未合併 PR 的快速驗證**：只執行 Python 回歸及安全預檢，**不編譯、不簽署、不上傳 APK，也不取用 Secrets**。舊紀錄中的 `Android-arm64-pr-ephemeral-apk` 是歷史測試產物，不可當作可持續更新的手機發行版。
- 採用原本的 `debug.keystore` 格式、`androiddebugkey` 別名與公認 Debug 密碼只適用於測試包及自行分發。真正公開發行請改用獨立強密碼的 Release 金鑰。
- 當前未能從 GitHub 讀到 Actions Secrets／Variables 的值；本次修改無法代替使用者設定。**未完成兩項設定前手動／Tag 完整 APK 建置會明確失敗**，這是為了避免無意間更換簽章。

## 你需要在自己的可信任電腦上設定兩個 GitHub 項目

### 1. 產生一次金鑰，永久保管原檔

若已有固定簽章原檔，優先沿用，**不要重新產生**：

```bash
keytool -genkeypair -v -keystore WLRe_LaLa.debug.keystore -alias androiddebugkey -keyalg RSA -keysize 3072 -validity 10000 -storepass android -keypass android -dname "CN=WLRe LaLa Debug,O=WLRe,C=TW"
```

不要把 keystore 原檔、完整 Base64 或私鑰貼在聊天、PR、Commit、Issue，也不要提交至任何 GitHub 分支。

### 2. 設置 GitHub Actions Secret（私有）

在 GitHub 儲存庫 **Settings → Secrets and variables → Actions → Secrets → New repository secret**：

- 名稱：`ANDROID_DEBUG_KEYSTORE_BASE64`
- 值：keystore 檔案的 Base64（不可有換行）

Windows PowerShell：

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes((Resolve-Path .\WLRe_LaLa.debug.keystore))) | Set-Clipboard
```

Linux：

```bash
base64 -w 0 WLRe_LaLa.debug.keystore
```

macOS：

```bash
base64 < WLRe_LaLa.debug.keystore | tr -d '\n'
```

### 3. 設置 GitHub Actions Variable（公開憑證指紋，**不是金鑰**）

請在原始 keystore 的檔案路徑執行：

```bash
keytool -list -v -keystore WLRe_LaLa.debug.keystore -storepass android -alias androiddebugkey
```

尋找輸出中 **SHA256** 的 32 位元組憑證指紋（64 個十六進位字元，允許用冒號隔開）。

在 GitHub **Settings → Secrets and variables → Actions → Variables → New repository variable**：

- 名稱：`ANDROID_EXPECTED_SIGNER_SHA256`
- 值：剛取得的 **SHA256 憑證指紋**，例如 `AA:BB:...`（請填入實際完整 32 位元組，而非範例）。

這個值是公開身份資訊，可以顯示在報告，不是簽章私鑰。

## 驗收方式

1. 在 `main` 手動執行 [Android phone APK (version tag)](https://github.com/blesses0603/WLRe_lala_Android/actions/workflows/android-apk.yml)。日常快速測試不再打包。
2. 確認 `WLRe_LaLa-Android-vX.Y.Z-debug` Artifact 包含 `SIGNING_INFO.txt`；內容必須有 `Mode: persistent`、`Pinned public signer SHA256: VERIFIED` 與完整 `Certificate SHA256`。
3. 如需比對跨版一致性，使用先前已驗收的 main Run 產物或在確有需要時再手動建置；不可為了反覆檢查而耗盡 Actions 額度。
4. Android 手機實際更新前，確認 App package name／version code／最低 API／簽章都相容；有固定簽章不等於所有舊 APK 都可直接升級。

錯誤 Secret、指紋不一致、缺少 pin、多簽署者、截斷的 SHA256，都會拒絕發布；測試請執行 `python -m unittest tests.test_android_signing -v`。

## 重要限制

- 已安裝在手機上、由舊的臨時簽章簽署的 APK **不能被不同簽章的新版 APK 直接覆蓋**。若沒有舊簽章私鑰，通常只能卸載後安裝；卸載會刪除 App 私有資料及 Android Keystore，請先整理能安全匯出的設定。
- GitHub PR 不提供私人 Secret，現在也不再自動打包 APK；快速 CI 成功**不能證明 ARM64 APK 編譯或固定簽章已通過**。完整簽章證據只取自手動／Tag APK 產物。
- `SIGNING_INFO.txt` 記錄 APK 簽署憑證的公開指紋；`SHA256SUMS.txt` 是 APK 位元檔案校驗，不可互相取代。
- R8／ProGuard 不保護 Python `.pyc`，固定簽章亦不會阻止逆向或重新打包。

### 2026-10-18：PR 臨時簽章比對修復

PR 使用臨時簽章，不應該用正式版的公開憑證指紋檢查 PR APK；在 `Mode: ephemeral` 時，`SIGNING_INFO.txt` 只報告 APK 真實簽章及 `Pinned public signer SHA256: NOT CONFIGURED`。只有 `Mode: persistent` 才必須比對固定 pin。不影響 main/Tag 的嚴格簽章阻擋。

### 2026-10-19：節省 Actions 額度的流程調整

日常 PR／main 改成快速 Python 驗證，不向工作提供 APK 私鑰，也不產出 APK；版本 Tag 或在 main 手動執行 `android-apk.yml` 時，才使用原有 `ANDROID_DEBUG_KEYSTORE_BASE64` 與 `ANDROID_EXPECTED_SIGNER_SHA256` 完成重簽與驗證。金鑰、pin、別名、密碼和 APK 安全報告程式均未更動。歷史 Run 39141939393 已經通過 main 的固定簽章工作流程，不需僅為這次 CI 設定變更重新打包。

### 2026-10-19｜v0.0.8 ARM64 Cython 正式打包

正式 `android-apk.yml` 將先使用 `tools/android_native_wire.py stage` 在獨立路徑編譯 `_wlre_wire_native.so`，**不將私鑰放入 staging 專案**。建置後繼續使用同一組 `ANDROID_DEBUG_KEYSTORE_BASE64` 與 `ANDROID_EXPECTED_SIGNER_SHA256`，依次重新簽章、驗證 APK 中 ARM64 原生模組與 shim、檢查簽署者、生成 SHA256，全部通過才上傳可下載 Artifact。

- 只有在 main 手動觸發或 main 版本 Tag 才執行完整 APK。PR 的快速驗證不會提供私鑰、不會上傳假正式 APK。
- `NATIVE_WIRE_INFO.txt` 是原生封裝證據，`SIGNING_INFO.txt` 是固定簽章憑證證據，`SHA256SUMS.txt` 用於位元檔案完整性，三者不可混淆。
- **先前 Phase04 試驗 APK 使用臨時 Debug 簽章**，如手機是安裝該試驗 APK，無法保證可直接覆蓋成固定簽章版本。不要在沒有備份方案前解除安裝，因為帳密和 Keystore 資料可能丟失。
- 正式 v0.0.8 的固定簽章與原地更新狀態需要從該版本實際 GitHub Actions Run 的 Artifact 與手機覆蓋安裝來確認。此文件的「接線」本身不冒充已驗收簽署成品。
