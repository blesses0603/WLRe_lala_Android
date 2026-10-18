# Android APK 固定簽章設定

這裡的「簽章」是 Android 安裝／更新用的**簽名憑證與私鑰**，不是 APK 檔案的 SHA256SUMS.txt。

## 目前兩種建置模式

- **未設定 GitHub Secret**：Actions 使用臨時 Debug keystore。APK 可用來測試，但每次新 runner 的簽章可能不同，手機不一定能覆蓋舊版。
- **設定 GitHub Secret**：Smoke ARM64、Smoke x86_64 及 Git Tag／手動手機 APK **共用同一把私有 Debug keystore**，未更換 package ID 且版本允許升級時，能使用相同簽章更新。

每份 APK Artifact 都包含 SIGNING_INFO.txt，其 Certificate SHA256 是**公開憑證指紋**，方便確認簽名金鑰相同。SHA256SUMS.txt 是 APK 檔案完整性校驗，原始碼變更後數值通常不同，即使簽章保持一致。

## 第一次設定（僅需做一次）

請在**自己的電腦上**建立並保管金鑰。請勿把金鑰、Base64 內容或密碼貼到聊天、Commit 或 GitHub Issue。

有 JDK 的 Windows PowerShell 或 Linux／macOS 終端機都可以執行以下指令，金鑰有效期設定為約 27 年：

```bash
keytool -genkeypair -v -keystore WLRe_LaLa.debug.keystore -alias androiddebugkey -keyalg RSA -keysize 3072 -validity 10000 -storepass android -keypass android -dname "CN=WLRe LaLa Debug,O=WLRe,C=TW"
```

**Windows PowerShell**：複製 Base64 到剪貼簿（請避免保存到公開檔案）：

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes((Resolve-Path .\WLRe_LaLa.debug.keystore))) | Set-Clipboard
```

**Linux**：

```bash
base64 -w 0 WLRe_LaLa.debug.keystore
```

**macOS**：

```bash
base64 < WLRe_LaLa.debug.keystore | tr -d '\n'
```

到 GitHub 儲存庫 **Settings → Secrets and variables → Actions → New repository secret**，建立：

- 名稱：`ANDROID_DEBUG_KEYSTORE_BASE64`
- 值：上面產生的完整 Base64 文字（不要加引號或換行）。

然後重新執行 Android Smoke 或更新 `main`。在成功 Actions 執行頁下載 `Android-arm64-apk`，ZIP 中開啟 `SIGNING_INFO.txt`，確認 `Mode: persistent`，並比較不同版本的 `Certificate SHA256` 是否相同。

**這個 Secret 目前無法由連接的 GitHub 讀寫工具替你設定，需要你在 GitHub 網頁完成。**

## 重要限制

- 使用同一把 Debug 金鑰的是**測試 APK**，不是 Google Play 正式 Release 簽章。不應以公認 Debug 密碼的金鑰作為正式商店發佈簽章。
- 若手機既有 APK 是先前 CI 的**臨時簽章**，新設定的金鑰不能回頭變成舊簽章。除非持有當時那把私鑰，否則無法直接覆蓋；解除安裝會移除 App 私有帳號設定與 Keystore 資料，請先備份你能備份的設定。
- 即使簽名一致，若 Android package name 不同、版本降級、APK 架構不相容或 SDK 不支援，依然可能無法直接安裝。
- 請永久保留自己的 `WLRe_LaLa.debug.keystore` 原檔安全備份。更換或遺失私鑰，日後就無法維持這條升級簽名鏈。
- GitHub Actions 在沒有設定 Secret 時**會繼續建置**，但 SIGNING_INFO.txt 將顯示 `Mode: ephemeral`，不保證簽名一致。
