# Android 第 07 項｜執行時安裝簽章完整性與安全失敗處理

基準 main e404d70226d01feb660cf2985db65cd152975576。版本維持 v0.0.8、Android 12+、ARM64-only。既有 Phase04 wire、Phase05 八核心 Cython、Phase06 IPC/帳密加固與固定 debug 簽章原封保留。

## 技術設計

- **公開指紋非私鑰**：正式 Android APK 的 GitHub Actions 將原本固定憑證 SHA-256 Variable \`ANDROID_EXPECTED_SIGNER_SHA256\` 注入隔離 stage 的 \`RuntimeIntegrity.java\`，並在 APK 重簽及獨立 apksigner 憑證檢查後生成 \`RUNTIME_INTEGRITY_INFO.txt\`。真正私鑰維持只進入既有簽章步驟，不放到 Java、資源或暫存專案裡。
- **簽署者身分檢查**：Android Java \`PackageManager.GET_SIGNING_CERTIFICATES\` + \`SigningInfo.getApkContentsSigners()\`，確認 package \`org.lala.client.wlrelala\`、只有一位目前有效的簽署者，並在 Java 用 SHA-256 + 常數時間位元組比對已安裝 APK 的公開簽署憑證。驗證結果僅為固定狀態碼，不輸出憑證、簽署細節、密碼或堆疊。
- **多入口 fail-closed**：Python Activity \`initialize_android\` 在啟動前景服務、打開 Android Keystore、載入已存帳號之前驗證；Android \`ConnectionService.onStartCommand\` 在初始化 PythonService 之前驗證；獨立 \`android_app/service.py\` 再自行驗證，不信任 Activity 的驗證結果。任何 mismatch、設定缺失、JNI 例外或 API 不支援均拒絕啟動敏感工作。
- **錯誤行為**：UI 顯示簡短 A07 訊息，不透露私鑰或例外內容；service 不建立 SessionManager、不觸碰已有帳號資料，直接停掉；正常版本不影響 IP/IPC、密文資料格式、多帳號及遠征/戰鬥運作。
- **本機/debug 差異**：未透過正式固定簽章流程建立的 Android APK 因沒有 public signer pin，預設會阻擋帳號／服務啟動。桌面 Python 和 PR 快速測試可正常運作；若需要手機可用的 Android APK，請由可信任 main/tag 的固定簽章正式建置取得。
- **既有安全限制**：客戶端 Java 驗證可被具備逆向／修改能力的攻擊者 patch 掉，因此不宣稱阻擋 Hook、Root、Frida、Xposed 或假冒伺服器；不是 Play Integrity API，也沒有遠端強制執行的 attestation。此項只提高重新簽署／未經授權重包的成本與可見性。

## 驗收順序

1. Android Python 回歸、Java Android API 編譯形狀、pin-stage/symlink/placeholder/格式/簽署者錯誤與清潔錯誤訊息測試成功。
2. PR 合併後 \`main\` 快速回歸成功，不會自動消耗完整 APK 編譯額度。
3. **正式發行閘門**：main 手動或對應 Tag 才重新 ARM64 NDK 建置、固定重簽，必須在簽章前完成 Java public pin 注入，並以 \`apksigner\` 驗證公開 pin，生成三個資訊檔：\`SIGNING_INFO.txt\`、\`RUNTIME_INTEGRITY_INFO.txt\`、\`SHA256SUMS.txt\`。
4. **真機驗收未實際完成前不能聲稱成功**：Android 12+/ARM64 正版固定簽章 APK 啟動→UI/服務/Keystore/多帳號/遠征正常；用測試簽章重新簽署的改包 APK 必須拒絕進入帳號；升級/簽章相容性另驗。

報告欄位與 ZIP/ARM64 原生核心稽核仍沿用 Phase05/Phase06，嚴禁將 client-side guard 當成高保證反篡改。
