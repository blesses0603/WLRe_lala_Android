# Android ARM64 固定簽章與指紋鎖定（第 02 項）

> 本機／GitHub 的測試簽章是 Android APK 安裝與升級身份，與帳號的 Android Keystore、APK SHA256SUMS、Python Cython 防逆向是不同機制。

## 實際狀態與發布政策

- **正式提供給手機更新的 main ARM64 APK、Tag／手動版本 APK**：必須提供私有簽章金鑰 **以及**獨立的公開憑證 SHA-256 指紋鎖定；兩者任何一項不存在、無效或不一致就停止建置／上傳，不能退回隨機 Debug 簽章。
- **未合併 PR 的 ARM64 驗證 APK**：使用臨時 Debug 憑證，不取用 Secrets。Artifact 名稱為 `Android-arm64-pr-ephemeral-apk`，**不可當作可持續更新的手機發行版**。
- 採用原本的 `debug.keystore` 格式、`androiddebugkey` 別名與公認 Debug 密碼只適用於測試包及自行分發。真正公開發行請改用獨立強密碼的 Release 金鑰。
- 當前未能從 GitHub 讀到 Actions Secrets／Variables 的值；本次修改無法代替使用者設定。**未完成兩項設定前 main 及 Tag 建置會明確失敗**，這是為了避免無意間更換簽章。

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

1. 在 `main` 執行一次 [ARM64 Actions](https://github.com/blesses0603/WLRe_lala_Android/actions/workflows/android-smoke.yml)。
2. 確認 `Android-arm64-apk` Artifact 包含 `SIGNING_INFO.txt`；內容必須有 `Mode: persistent`、`Pinned public signer SHA256: VERIFIED` 與完整 `Certificate SHA256`。
3. 再觸發第二次 main 建置，比對這兩份 `SIGNING_INFO.txt` 的 SHA256 指紋是否完全相同。
4. Android 手機實際更新前，確認 App package name／version code／最低 API／簽章都相容；有固定簽章不等於所有舊 APK 都可直接升級。

錯誤 Secret、指紋不一致、缺少 pin、多簽署者、截斷的 SHA256，都會拒絕發布；測試請執行 `python -m unittest tests.test_android_signing -v`。

## 重要限制

- 已安裝在手機上、由舊的臨時簽章簽署的 APK **不能被不同簽章的新版 APK 直接覆蓋**。若沒有舊簽章私鑰，通常只能卸載後安裝；卸載會刪除 App 私有資料及 Android Keystore，請先整理能安全匯出的設定。
- GitHub PR 不提供私人 Secret，所以 PR Artifact 是臨時簽章；其 CI 成功只能證明簽署程式測試、ARM64 打包可用，**無法證明固定簽章在主分支已生效**。
- `SIGNING_INFO.txt` 記錄 APK 簽署憑證的公開指紋；`SHA256SUMS.txt` 是 APK 位元檔案校驗，不可互相取代。
- R8／ProGuard 不保護 Python `.pyc`，固定簽章亦不會阻止逆向或重新打包。
