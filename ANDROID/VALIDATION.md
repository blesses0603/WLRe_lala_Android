## v0.0.7 桌面 main → Android 增量移植

- 來源固定為桌面 `WLRe_lala/main` 的 `c6bee236f0074f1981f29e957785beffe21f0ed8`；包含核心遠征、夥伴出戰、戰後修理／整理、遠端儲藏 S62 唯讀解碼及正式名稱資料。
- Android 保留獨立 `main.py`、Kivy 頁面、前景服務和私有 IPC；不匯入桌面 Tkinter GUI。
- 已新增桌面核心可在無桌面環境執行的測試、Android 功能橋接與編排測試、原始物品圖示及原版功能 ICON。
- 驗證尚以新 GitHub Actions 的實際結果為準。傳統 Smoke 只測無登入的 Activity／Keystore／服務啟動，**不代表已對正式服執行遠征派遣、道具消耗、儲藏室或出戰操作**。

## v0.0.7：原生啟動畫面提交後 API 35／36 Smoke 回歸

- [Actions 39109093293](https://github.com/blesses0603/WLRe_lala_Android/actions/runs/39109093293) 編譯並驗證 ARM64 與 x86_64 APK 內含自訂 `presplash.jpg`，但工作流程總結為 **failure**；API 31～34 通過，API 35／36 失敗。
- 兩個失敗日誌皆在 `tools/android_smoke.py` 啟動就緒等待迴圈、原本第 85 行的 `adb logcat -d -v threadtime` 遇到返回碼 **255**，未進入既有的測試結束診斷容錯。API 36 日誌已出現 UI 及 Keystore 就緒標記，但仍不能因此宣稱服務與全部 Smoke 測項已成功。
- 修正：啟動期間的 `adb logcat` 暫時中斷先記錄並重試，累積已觀察到的正向就緒標記，等待時間為 150 秒；**未看到全部標記仍會在期限到時失敗**。新增對 255、執行逾時、分段標記及真正就緒逾時的回歸測試。
- 本次只調整 CI 測試程式及文件，保留 `v0.0.7`、原生啟動畫面設定、IPC 與遊戲邏輯。驗證結果以修正後新 Actions Run 為準。

## v0.0.7：原生啟動畫面客製化

- 使用者手機截圖仍顯示 Kivy 預設黑色 `Loading...`。查明 `buildozer.spec` 原本只有 `icon.filename`，沒有 `presplash.filename`；Kivy 內部 UI 圓角與主題不會影響 SDL2 原生載入畫面。
- 設定 `presplash.filename = android_app/assets/app.png` 與 `android.presplash_color = #081626`，重用既有 LaLa App ICON。
- 兩套 Actions 新增原生啟動畫面設定與 APK 資源檢查，驗證圖像像素與來源 ICON 相符，並在 Artifact 內提供 `PRESPLASH_INFO.txt`。
- 修改前的 [Actions 39107618405](https://github.com/blesses0603/WLRe_lala_Android/actions/runs/39107618405) 雖然 API 31～36 啟動測試全部成功，但**沒有測試自訂 presplash 圖像**。須以本次變更後的 Actions 為準，仍需真機確認是否顯示新圖案。

## v0.0.7：Android 15（API 35）Smoke 診斷補丁

- [Actions 39106328993](https://github.com/blesses0603/WLRe_lala_Android/actions/runs/39106328993) 的 API 35 工作：UI、前景服務、Home、鎖屏 30 秒、恢復畫面皆已通過，日誌明確出現 `smoke passed`；但 `tools/android_smoke.py` 最後在 `finally` 讀取 `adb logcat -d -v threadtime` 時發生退出碼 **255**，觸發 `CalledProcessError`，因此工作結果為失敗。其餘 API 31、32、33、34、36 均成功。
- 修正重點：將測試完成後的 logcat 與 services dump 定位為**非必要診斷**，採兩次擷取並支援少量日誌備援，失敗時寫入原因與保留其他診斷，不覆蓋主測試的成功或失敗結果。
- 增補自動回歸案例：模擬 logcat 255、診斷完全失效、正常啟動成功與真正的 Activity 退出失敗，確保不把真正崩潰當作通過。
- 此項屬於 CI 測試腳本修復，**未修改遊戲功能、Android APK 版號或編譯設定**。此處僅記錄 39106328993 的失敗及補丁目的；後續流程結果需以新 Actions 執行紀錄為準。

# Android v0.0.1 開發驗證 — 2026-10-18

檢查基準：`c6ec340` 的 Kivy／Buildozer 實作。

- 使用假的網路 runner 重現鎖定角色欄位遺失、同角色重複入列，以及例外狀態被 finished 訊息覆蓋；修正後 9 項 session 測試通過。
- 在 Kivy 2.3.1 與虛擬桌面執行 5 項 UI 測試，驗證中文字形、鎖定／待選角色、錯誤保留／結束卡片移除、HP／SP 零值與未知位置、背景清空密碼及停線。
- 相同環境完整執行 191 項測試：189 通過、2 項略過（Windows DPAPI、macOS ditto）。
- Actions 工作流程通過 actionlint 1.7.12；語法與 diff 檢查通過。
- 沒有使用正式帳號、沒有連線遊戲伺服器。Android APK 的 Buildozer 編譯、手機安裝及真實登入結果，仍以 Actions 產物與手機實測為準。

本次保留既有 Kivy 多連線設計，未混入另一套 Android 原生／Chaquopy 入口。

## v0.0.2 — 2026-10-18

- 完整 198 項測試：196 通過、2 項平台限定略過。Android 專用 22 項測試涵蓋獨立連線、私有 socket、畫面重新附接、背景生命週期、無畫面事件清理、保存帳號切換及刪除。
- 密文儲存測試使用桌面 AESGCM 驗證非明文、載入、刪除、竄改失敗與原檔保留；**不等同於 Android Keystore 真機測試**。
- 自訂 Java 前景通知／Android 15 超時服務，使用 Android 35 SDK 與 JDK 17 編譯檢查通過；測試時 PythonService／PythonActivity 使用最小介面 stub，完整整合仍須 APK 建置驗證。
- actionlint、Python compileall、diff whitespace 檢查通過。
- 上一輪 Actions 39050117226 失敗於 charset_normalizer 3.5.2 Android wheel 被 Linux 主機 pip 拒收；本版固定 charset-normalizer 3.4.2 及 python-for-android revision，重跑完整建置。
- 尚無正式帳號連線、手機 Keystore、背景或鎖屏時長的實測結果；15／30／60 分鐘測試仍需手機驗收。

- 後續追加暫停畫面的事件合併測試：10,000 次更新僅保留各帳號最新狀態；Android 專用 22 項全部通過。完整測試前次 198 項通過（含 2 略過），新增此項後未重跑完整套件。

## APK 建置結果 — v0.0.2

- GitHub Actions [39051241946](https://github.com/blesses0603/WLRe_lala_Android/actions/runs/39051241946) 全部成功，原始碼 commit `405b1d5`，工作耗時 13 分 44 秒。
- CI 的 22 項 Android 專用測試、compileall、Buildozer／Gradle APK 編譯及上傳全部成功。
- 產物：[WLRe_LaLa-Android-v0.0.2-debug](https://github.com/blesses0603/WLRe_lala_Android/actions/runs/39051241946/artifacts/12108650193)，包含 APK 與 SHA256SUMS；GitHub 回報壓縮產物大小 111,303,027 bytes。
- 此執行環境取回 GitHub Azure Blob 產物時收到 Forbidden，因此未在本地解開 APK 檢查 manifest／校驗碼，不能宣稱已做本地產物驗證。
- Android Keystore 實際加解密、手機安裝、正式服雙帳號、切 App、鎖屏與耗電仍待手機實測。

## v0.0.3 啟動閃退調查

使用者回報 v0.0.2 點開後、尚未看到登入畫面即閃退；尚未取得手機型號、Android 版本或 logcat，根因未確定。

- 將 Android 服務／Keystore 初始化移出 App 建構子，等 Kivy 畫面建立後才執行；服務初始化失敗顯示 A01／A02，Keystore 失敗顯示 A03，避免未處理例外直接結束畫面。
- 服務尚未就緒時禁止退回 Activity 內建立遊戲連線；資源監控例外顯示 A06，保留介面與服務連線。
- 增加無正式帳號的 Android 12／12L／13／14／15／16（API 31–36）x86_64 模擬器測試：確認 UI 與服務 readiness、切 Home、短暫關屏及返回，並上傳 logcat。此測試不能代替手機 ABI、正式連線或長時間鎖屏驗收。
- 本地 Android 專用 24 項測試通過，包括初始化失敗不退出、不顯示例外中的敏感字串，以及監控例外保留畫面。

- 依使用者指定，以 Android 12+ 為支援目標，最低 API 調整為 31；不預先宣稱尚未測試的 Android 版本或所有廠牌均已相容。

## v0.0.4：模擬器重現的 JNI 原生中止

- v0.0.3 Android API 31／32／33 啟動測試失敗；API 31 的 logcat 明確顯示 `ArrayStoreException: java.lang.String[] cannot be stored in an array of type java.lang.String[]`，隨後 `JNI DETECTED ERROR IN APPLICATION`／SIGABRT。
- Keystore Builder 的 Java varargs 誤傳 Python list，PyJNIUS 將其再次包成陣列；修正為逐個字串參數。這種 JVM 原生中止不能由 Python try/except 攔截，因此 v0.0.3 的啟動防護不足以修好此問題，請勿視為修復完成。
- 使用真實 PyJNIUS 1.7.0／JDK 17 發現並修正 Cipher.init／KeyGenerator.init 的多載型別選擇，明確 cast 為 Key／AlgorithmParameterSpec。
- 新增真實 Java varargs 與 AES-GCM 全位元組回歸測試（Android KeyStore provider 以測試 stub 代替，JCE 加解密為真實 Java 呼叫）；本地 25 項 Android 測試通過。
- 模擬器新增實際 Android Keystore 隨機資料加密／解密成功標記，必須同時通過 UI、服務與 Keystore 才算啟動測試成功。v0.0.4 需重新跑 API 31–36，結果另行記錄。


## v0.0.5：帳號獨立自動操作

- 每個帳號提供啟動／停止自動戰鬥、自動徘徊及 AI 設定，透過背景服務傳送到既有遊戲核心；UI 以核心回報更新，不將送出命令視為成功。
- 登入完成後才能啟動；處理中避免重複點擊。斷線或服務失聯時停用控制，失聯顯示狀態未知。
- 徘徊使用伺服器確認位置的四點循環，沿用遇戰、事件、補給與隊長限制。
- AI 設定依帳號＋伺服器保存於 App 私有、不備份目錄，官方同伺服器各分流共用；不含帳密。提供角色／夥伴普通攻擊、自動選擇已知技能、防禦，以及陣亡停機選項；其他既有規則保留。保存後下次啟動套用，不自動啟動戰鬥或徘徊。
- 使用者提供 v0.0.4 實機畫面：已登入，角色 HP/SP、地圖及位置同步。這不代表自動操作或長時間鎖屏連線已驗收；新操作仍需正式帳號實機確認。

### v0.0.4 相容性實測結果

[Actions 39054756636](https://github.com/blesses0603/WLRe_lala_Android/actions/runs/39054756636) 全部成功：API 31、32、33、34、35、36。測項為 UI／Keystore／服務就緒、切至主畫面 15 秒、鎖屏 30 秒、恢復畫面後程序存活；未使用正式遊戲帳號，不能據此宣稱長時間網路穩定。

## v0.0.6：桌面遊戲功能的手機操作介面

功能範圍、平台替代入口與已知限制見 [功能對照](FEATURE_PARITY.md)。新增各帳號詳細狀態、受限命令橋接、聊天／事件有界紀錄、帳號伺服器偏好保存與完整 Kivy 功能頁；不載入桌面 Tkinter 視窗。剪貼簿匯入／匯出與桌面 JSON／方案格式相同。

本機已檢查 392×844 直式視窗、頁面建構／空資料／角色資料更新、草稿取消與保存、命令隔離及資料有界。最初完整測試因雲端 Xorg 重啟而出現顯示服務錯誤，恢復顯示服務後重新執行；並非把該次失敗當成功。

- 本機完整回歸：共214項，212項通過、2項略過；另外新增的消耗預覽／真實核心回合核對加入後，Android 專項共 39 項通過。Workflow YAML 語法與 Python 編譯檢查通過。

### v0.0.6 最終本機檢查（程式 c9aa986）

- 完整回歸共218項，216項通過、2項略過；Android 專項 41 項通過。
- 新增確認：分頁切換保留材料與聊天草稿、聊天 ACK 依請求識別碼核對、遭拒保留文字、密語保留正確 target_id、完整設定入口先附接該帳號詳細資料。
- 正式伺服器的材料／補品消耗與多帳號長時間背景操作未自動執行，仍待手機驗收。


### v0.0.6 Actions 結果（程式 c9aa986）

- [手機 APK 流程 39082627294](https://github.com/blesses0603/WLRe_lala_Android/actions/runs/39082627294)：成功。產物 [WLRe_LaLa-Android-v0.0.6-debug](https://github.com/blesses0603/WLRe_lala_Android/actions/runs/39082627294/artifacts/12120095506)，內含 ARM64 手機 APK 與 SHA256SUMS。
- [相容性流程 39082627295](https://github.com/blesses0603/WLRe_lala_Android/actions/runs/39082627295)：建置與 API 31／32／33／34／35／36 七個工作全部成功。涵蓋 Android 12／12L／13／14／15／16 的啟動、UI／服務／Keystore 就緒、Home 15 秒、鎖屏 30 秒與回到畫面後程序存活。
- 上述模擬器流程未登入正式遊戲帳號，不能替代實機功能操作、材料消耗確認或 15／30／60 分鐘背景網路驗收。
