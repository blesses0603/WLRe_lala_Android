# 版本紀錄

## 7.1.7 Android 官方 Manifest 網路診斷與同源重試（2026-11-04，修補候選）

- 依 Android v7.1.6 真機畫面確認：官方版本可取得 DataPackage 1286／MainPackage 1284，但完整 Runtime 被 `ManifestSyncError: Official Manifest download failed` 阻擋。無法從畫面判定 .hash／.bytes 及 HTTP／TLS／DNS／逾時根因；未取得真機原始連線 Log。
- 原本官方版本查詢有受限數字查詢與回退，Manifest 僅使用固定原始 URL。現在 Manifest 在 HTTP 400／403／404 時，最多增加**一次同主機、同路徑、HTTPS、數字查詢字尾**的重試；任何回應仍須通過原本的 .hash／.bytes CRC32、YooAsset 解析、版本身分與完整 Runtime／SQLite Gate。
- 將 Manifest 下載失敗辨識到 DataPackage／MainPackage 的 .hash／.bytes，以及固定的 HTTP 狀態碼、TLS 憑證／握手、DNS、逾時／拒絕連線類型。Android 畫面不輸出例外原文、伺服器回應內容、真實路徑、帳號或 Token。
- 增加模擬官方 CDN HTTP 404、TLS 拒絕、CRC32 與診斷隱私的離線回歸測試。實際官方 CDN 可用性、ARM64 APK 編譯、真機安裝與登入仍須單獨驗收，**不宣稱已修復真機下載根因**。
- Android 版本預計從 7.1.6 升到 7.1.7；桌面版本不變。不改遊戲封包、帳號與正式伺服器安全政策，不合併 main、Tag 或 Release。

## 7.1.6 APK 編譯啟動修補候選（2026-11-04，尚未正式發布）

- 根據主分支 APK CI #41683915841 的實際日誌，P3 的「Compute P3 SHA-256 keys」在 Step 17 出現 `ModuleNotFoundError: No module named 'tools'`，導致 Buildozer 原生編譯尚未執行就停止。
- 將 P3 計算快取鍵、恢復前校驗及安全門檻通過後保存的三個工作流程命令改用 `python -m tools.android_core_incremental`，修復專案根目錄套件解析；新增真實 subprocess CLI 和三入口政策測試。
- 保留八核心各自的 SHA-256 校驗、無效快取自動完整重編、固定簽章、所有 APK 原生／資源／安全 Gate。不變更遊戲指令或帳號、官方資料。Android 程式版本從 7.1.5 調整為 **7.1.6（預計版本）**，桌面版本不變。
- PR Python 回歸與實際 ARM64 APK 編譯、固定簽章、手機安裝和伺服器 E2E 必須各自驗收；未完成驗證前不合併 main 或建立 Release／Tag。

## 2026-11-03：P3 八個 LaLa 核心 SHA-256 增量編譯（CI-only）

- Android 八個原生 Cython Recipe 各自以來源 .pyx、Recipe 與 setup.py、共用快取程式、Runner ImageVersion、p4a／Cython／Buildozer／NDK／API／ABI 計算完整 SHA-256 指紋。
- 在隔離原生 staging 還原受信任 main／Tag 已完成安全稽核的 ARM64 擴充模組；逐個驗證鍵、收據、SHA-256、大小、ELF，只有可信命中可跳過該核心的 Cython 重建，失效一律正常重編。
- 每次仍重建與簽署完整 APK，逐項執行 Phase04／05 原生模組、Shim、資源、固定憑證、SHA256、Phase09 安全稽核；只有完整 Gate 通過後可逐核心保存快取。不中斷既有 P1／P2 快取。
- 新增精確單核失效、快取竄改防護、未知 Runner 與 GitHub Workflow 安全策略回歸測試。真正 ARM64 APK 的快取命中率、時間效益和真機驗收仍需受信任 main 手動編譯驗證。
- 不修改任何遊戲指令、帳號、官方資源判斷、Android 版本 7.1.5，不建立 Tag／Release，不合併 main。

## 7.1.5 開發修補版（尚未正式發布）

- 修正 APK 在官方版本查詢成功但完整 Runtime 失敗時，只顯示「Runtime 檢查發生未分類錯誤」的診斷缺口。
- 分別將官方 Manifest 下載／解析／完整性、Catalog Identity、Bundle 下載／驗證／依賴、UnityFS TextAsset、Runtime 快取或並行檢查等錯誤歸類為固定狀態碼；仍無法分類的未知錯誤保持泛用標示。
- Android UI 只顯示固定繁體中文原因，不回傳例外原文、官方封包、私人裝置路徑、帳號密碼或原始伺服器資料。
- **不變更官方資源 SHA-256 驗證、Runtime／SQLite 同版檢查、登入 fail-closed、任何遊戲指令與版本相容性判定**；新版 1286／1284 Runtime 是否可載入仍需真機重測。
- 新增對應的錯誤映射、隱私及禁止登入回歸測試，完整 APK 與手機正式服驗收仍需另外進行。

## 2026-11-03：P1／P2 Android 原生相依編譯快取（CI-only）

- P1：引入 ccache 850 MiB 並設定編譯器內容校驗，讓 NDK C／C++ 編譯輸出能依來源與編譯參數重用；每次建置顯示命中統計。
- P2：僅保存十個明確列出的第三方 p4a Recipe 的其他建置目錄及來源快取，使用含 Runner ImageVersion、p4a／NDK／API／ABI、Buildozer／Cython／requirements、本機 Recipe SHA-256 的版本化快取鍵。
- 所有 LaLa 原生核心、應用 Distribution、APK、私鑰、帳密仍不直接跨版重用；首次建置與快取失效走完整編譯，固定簽章及安全稽核不變。
- 新增 P1／P2 快取版本鍵、白名單、GitHub Workflow 安全邊界與 fail-open 快取服務回歸測試。
- 僅為 CI／文件變更，Android 版本保持 v7.1.4；真正的 p4a 快取命中、ARM64 APK 及編譯時間仍待手動 main 建置驗收。

## 7.1.4 開發修補版（尚未正式發布）

- 背景服務 IPC 若有單筆無法序列化／過大的回覆，改為回傳固定安全錯誤，不因單筆資料損壞而結束服務 socket。
- Android 畫面端的帳號詳細資料 RPC 改為可獨立失敗，仍可接收其他帳號的狀態、資源與服務存活資訊；舊的詳細資料快取會清除。
- 官方資源重新檢查改為單次排程，檢查中／佇列已有請求時不重複送出，並在畫面提示實際狀態；不自動重送登入或遊戲指令。
- 新增 IPC 異常回覆恢復、跨帳號隔離及資源檢查單次排程測試。
- Android 改為資源驗證優先的啟動流程：先顯示官方資源／SQLite 檢查頁，只有獨立服務與手機兩端 Runtime ready 且 Catalog Token 一致才顯示登入表單；保留失敗診斷、手動重試與 Activity 恢復驗證流程。
- 本次僅為原始碼與 CI 驗證範圍，尚未宣稱 ARM64 APK 或 Android 實機背景執行通過。


## 2026-11-03：APK 建置依賴快取（CI-only，不升級版本）

- 手動／Tag APK 工作流程增加 pip 套件快取及版本指紋控制的 SDK／NDK r28c、Gradle 依賴快取，以減少未變動的第三方工具鏈重複下載。
- 版本指紋由 Buildozer、Cython、p4a pinned commit、API／ABI 與 requirements 等輸入計算，App Patch 版號不會自行清除工具鏈快取。
- 快取僅保存非敏感依賴，完整 APK、Cython 編譯輸出、簽章私鑰、測試憑證、正式核心與帳密資料皆不快取；所有 ARM64 編譯／安全稽核仍保留。
- 新增離線測試檢查快取鍵正確性與流程安全邊界；實際快取命中率與加速效果需後續 main 手動建置驗證。
- 僅改 CI，不修改 Android 程式版本 v7.1.4；不建立 Tag／Release。

## 7.1.3 開發修補版（尚未正式發布）

- 新增完整 Runtime 失敗的固定、有限診斷分類：必要 Bundle 缺少／校驗失敗、Eve／資料結構解析、版本或 Manifest 身分不符及其他未分類失敗。
- 前景服務的資源準備若超過單次 32 MiB／24 檔額度，介面會明確顯示準備階段的原因，不再只顯示「完整 Runtime 未通過驗證」。
- 對可疑路徑、帳密及遠端例外資訊保持遮蔽；保留官方 TLS、Bundle 雜湊、SQLite 與登入 fail-closed 規則。
- CI 測試與手機 APK／正式服驗收須分開確認；本次不宣稱已取得手機端真正失敗原因或已完成登入。


## 7.1.2 開發修補版（尚未正式發布）

- Android Major.Minor 跟隨桌面版 main v7.1.1（7.1），Patch 獨立累進；此版為 Android TLS 修補，並不代表桌面功能全數完成實機驗收。
- 唯讀系統 CA 支援 PEM／DER X.509；載入前使用 OpenSSL 核對，不會降級為無憑證驗證。
- 官方 urllib HTTPS 明確使用經選定的 CA 建立 CERT_REQUIRED 和 hostname checking 的 SSLContext；CA 設定失敗時保持拒絕登入。
- 區分 TLS 憑證驗證、TLS 握手與 CA 載入失敗，補充 DER、TLS 分類、信任來源與 UI 診斷離線回歸測試。
- 本版未進行完整 APK 編譯、手機實機連線與正式服登入驗收。

## 0.1.1 開發修補版（歷史記錄）

- Android Activity 與服務啟動時明確載入並解析 certifi CA bundle，加入 Android 唯讀系統 CA，取代可能保留失效繼承路徑的 `setdefault`。
- urllib 與 Requests 使用同一份已解析的 CA 檔案；保留憑證、主機名稱與官方資源完整性驗證，不匯入使用者安裝的 CA，也不信任下載的伺服器憑證。
- 本次修補的 APK、裝置 TLS 連線及正式服登入仍待驗收。

## 0.1.0 開發整合版（尚未正式發布）

- 補上 `tpk_ar 0.2.4` 的固定來源與 SHA-256 本機 recipe，從原始碼安裝純 Python TPK 解析器及授權檔，排除 APK 建置 binary-only 安裝找不到 wheel 的問題；完整 APK 仍待 CI 驗證。

- 修復 LZ4 編譯時 `setuptools_scm` 找不到 `vcs_versioning`：透過 p4a 的 hostpython 建置相依安裝版本工具，避免只安裝到 Android 目標環境；完整 APK 編譯仍待 CI 驗證。

- 同步桌面 v7.0.1 與 PR #65 遊戲核心、動態官方資料及 SQLite。
- 新增 Android NPC、帳篷、儲藏存取、福利魔方及自動接續入口。
- 保留副本／協力手動開始、Android 背景服務、Keystore、固定簽章與八核心原生稽核。
- APK 安裝、ARM64 執行與正式服逐項驗收尚待完成。

## 0.0.8

本次修改前 Android main 的版本；既有發布與歷史驗收紀錄請參閱 ANDROID/ 下原始文件。
