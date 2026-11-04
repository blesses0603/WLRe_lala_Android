## 同步 2026-10-18 桌面 main 新功能

基準：`blesses0603/WLRe_lala` 的提交 `c6bee236f0074f1981f29e957785beffe21f0ed8`，只移植跨平台核心與 Android 專用觸控頁面。

- 「夥伴出戰」：檢視出戰條件、手動出戰／休息，收到 S19 伺服器回覆後才更新。
- 「遠征」：內建 1262 官方 260 任務與 10 級、駐紮所和任務資料、好友度補充、出發及結算；設定依帳號／伺服器保存，但不自動開始。正式服派遣與領獎尚待驗證。
- 「包包與特技」：手機 4×6 每頁 24 格、64dp 物品原圖、資訊卡；超空間袋只能讀取 S62 已同步的遠端儲藏資料，沒有經驗證的寄取操作一律不提供。
- 「AI與補給設定」：新增修理／整理頁，包含 2 種修理道具、15 種整理物品及耐久門檻。真正自動修理、賣出或丟棄仍由共用核心檢查伺服器確認，不會僅因 UI 切換就執行。
- 原版遊戲圖示：帳號角色功能頁提供可左右滑動的操作捷徑。
- 真機測試：請特別檢查新增的多帳號遠征隔離、文字輸入、鎖屏後自動化存續，及遠端儲藏資料是否已同步。模擬器不會登入真實遊戲帳號。

# 飄流 RE:LaLa｜Android 使用與技術指南

本文件集中說明 Android 客戶端的**操作流程、權限、背景機制、APK 建置及驗收限制**。首次安裝與下載入口請先閱讀 [專案首頁 README](../README.md)；功能逐項對照請參考 [FEATURE_PARITY.md](FEATURE_PARITY.md)。

**目前開發候選版本：v7.1.14（尚未正式發布）** ｜ **最低 Android 12（API 31）** ｜ **只建置 ARM64 手機 APK** ｜ **Debug 測試用途**

**v7.1.13 觸控頁對照修補：**夥伴出戰卡顯示由當前同步資料驅動的 HP／SP 條及出戰狀態；角色能力頁把官方五項目前值、增量與觸控加減鍵放在各自同一卡片。未取得資料不畫假進度、不假設忠誠度上限；不增加未確認的遊戲指令。此次屬局部功能佈局修補，非宣稱已完成十張概念圖，Android 真機排版與正式服操作仍待驗證。\n\nAndroid Major.Minor 跟隨已核對的桌面 main（此輪桌面 v7.1.1，Android v7.1.5），Android Patch 獨立維護。桌面 Major.Minor 再變動時應先核對最新桌面 main，更新 Android 前兩段並單獨評估 Patch；版本號相近不代表功能已驗收。v7.1.5 針對新版官方 Manifest、Bundle、YooAsset 及 Runtime 失敗加入固定安全分類，仍須驗證實際原因；v7.1.4 強化背景服務 IPC 容錯：單筆角色詳細資料讀取異常不影響全域在線判定、重複資源檢查請求會被抑制、無法序列化的 IPC 回覆改為安全錯誤；v7.1.3 新增必要 Bundle 缺失／校驗／解析等安全診斷，並辨識資源準備超過 32 MiB／24 檔單次額度；v7.1.2 修補官方 TLS 診斷、PEM／DER CA 載入與明確 HTTPS 信任來源；下方 v0.0.8 小節屬於歷史建置紀錄。

**v7.1.13 包包／特技效能修補：**載入頁面時每批最多 6 筆繪製、共用 ZIP 讀取、100 個上限的 Kivy 原圖快取。刷新僅比對目前資料來源所需欄位，並取消過期分批回呼；技能仍監聽戰鬥與角色資料以防狀態變更後失效。UI 線程仍會解碼當批圖片，是否達到流暢觸控須在手機上驗證。

**v7.1.14 小地圖與物品操作還原：**小地圖的放大／縮小、定位與重設只調整本地紋理 UV，保留原始出口、安全路徑及步行指令；縮放後觸碰座標仍依已驗證的投影換算。包包格位先顯示頁內真實道具詳情，再透過明確按鈕開啟使用／檢視對話框；操作前檢查最新物品 ID、數量、保留與是否可使用；遠端超空間袋仍唯讀。新增 Kivy 幾何反向換算與物品狀態變更回歸。實機截圖/FPS 仍待驗收。

新 APK 安裝後按「重新檢查官方資源」，核對完整 Runtime 錯誤分類與 ResourcePath_PC.dat 階段錯誤種類；Chrome 能載入不代表 Python/OpenSSL 能完成驗證。請勿關閉憑證檢查。

> 請勿安裝早期 v0.0.2／v0.0.3 的舊 APK：歷史紀錄曾確認 Keystore／PyJNIUS JNI 初始化崩潰。v0.0.7 新增的懸浮小球與遊戲自動化操作仍需真機驗收；「Actions 成功」不等於正式遊戲連線驗收。


**v7.1.9 Android 分頁效能候選：**角色功能頁採按需載入、相同快照合併刷新，背景服務連線／遊戲事件照常處理；裝置記憶體監控每 2 秒讀取、帳號自動化卡片每秒更新，避免 Kivy 主執行緒因重複繪圖而卡頓。此為程式優化，實際 FPS／切頁延遲／耗電仍須手機實測。

## 官方資源驗證頁視覺修補（v7.1.12）

- **參考基準**：使用者提供的深藍星空霓虹概念圖，不再只有三個固定進度框；新增角色與天空城堡兩張輕量 JPEG 裝飾，實際畫面仍是可操作的 Kivy 控制項。
- **七項真實狀態**：官方版本、DataPackage、MainPackage、Manifest、Bundle、Runtime、SQLite 均獨立顯示未確認／檢查中／驗證成功／未通過；須通過背景服務與 Activity 的相同 SHA-256 Catalog 身分才可全部顯示成功。
- **版本與時間**：由背景服務回報已核對的官方資源版本、UTC 檢查時間及白名單錯誤類別；未知顯示尚未取得，不能把概念圖的 1286／1284、時間和綠色勾選當成真實結果。重試會清除舊的顯示收據。
- **視覺與效能**：靜態 Kivy 霓虹邊框與大尺寸觸控按鈕，不加入昂貴的逐幀模糊與 Glow 動畫；窄螢幕由 ScrollView 捲動。
- **待實測**：完整 ARM64 APK、320dp 真機版面、正確的 TLS／Manifest、觸控、FPS 及正式伺服器流程須各自驗收。

## 全 Android 18 個功能分頁的設計一致化（v7.1.12 同版本追加）

- 在官方驗證頁參考圖重製基礎上，延伸相同的**星空角色品牌標頭、青藍霓虹玻璃卡片、靜態頂部高光、操作按鈕、分類圖示和底部導覽**到登入、帳號管理、角色工作區及全部 18 個現有功能分頁。
- 已有 1262 原版功能圖示的頁面優先使用原圖；無原圖頁使用相同色系簡潔符號。所有圖示只作視覺提示，不替代真正的伺服器回覆和操作權限。
- 原本僅文字堆疊的「事件紀錄、經驗效率、戰場陣形」補上完整霓虹狀態卡及可操作面板。戰場目標選取使用按鈕實際樣式高亮，而不是修改透明背景色。
- 保留資料來源、資源驗證、安全登入、原有指令、分頁懶載入、快照刷新節流及中文 IME 對比，不增加每幀動畫與網路請求。僅在必要幾何變化時更新 Kivy Canvas。
- **驗收界線**：此處是程式碼的設計系統與跨頁整合，不代表與概念圖「像素級相同」。必須以正式 ARM64 APK 依序比對驗證、登入、18 頁、彈窗在 320dp 與一般手機的截圖、觸控、FPS 和背景連線，才能確認視覺及功能品質。

## Android 介面重新設計（第一階段：v7.1.10）

- 視覺基準：使用者確認的深藍科技風格；使用原本內建的 LaLa 角色圖示，不把產生式概念圖上的角色狀態、物品、伺服器或驗證結果直接寫入 App。
- 已套用：共用卡片、按鈕、暗色高對比中英文輸入框、品牌標頭、官方驗證頁、登入／帳號管理、角色功能的四區底部導覽、18 個頁面的標題與彈出視窗。
- 安全：只有背景服務及手機端官方資源驗證真正完成，登入標頭才顯示「官方資源已驗證」；失敗、等待或背景服務斷線不得顯示假的成功狀態。
- 效能：不使用逐幀模糊或大量發光動畫；使用輕量 Kivy Canvas 與原本的頁面懶載入、IPC 更新節流；優先驗收 320dp 窄螢幕的中文字顯示與觸控。
- 第一階段 PR #51 已合併 Android `main`；第二階段 PR #52 完成核心七類分頁，第三階段專注進階操作介面。實際畫面與概念設計圖是否一致仍須真機驗收。

### 第二階段：七類角色核心操作頁（以第一階段 PR 為基礎）

- **角色概況**：真實 HP／SP 數值與低負載進度條、戰鬥／徘徊／遠征切換、帳篷進出及最近三筆已同步事件。
- **包包與特技**：包包／超空間袋／特技快速選取、查詢、24 格原生圖示、選取道具資訊與受庫存、可靠數量及戰鬥規則限制的原本使用入口。
- **小地圖**：當前場景與座標、互動地圖、座標移動、NPC／出口／怪物選單及逐圖核對；內容與畫面位置不變時不重建 Canvas。
- **聊天及組隊**：不同發話角色的訊息泡泡、真實伺服器確認／未知狀態、引用／密語、同場景玩家、隊伍、申請與邀請。
- **夥伴及角色能力**：每隻已同步夥伴的 HP／SP、忠誠／好友度、出戰／休息限制；五項能力已確認數值、觸控加減及現有配點二次驗證。
- 第二階段 PR #52 已合併 Android `main`（v7.1.10）。完成程式測試不等於已完成 ARM64 APK、真機效能及正式服功能驗收。
- 示意圖上的角色名稱、等級、HP、裝備、房間、驗證通過狀態不會寫入 App；未知資料必須顯示未同步。

### 第三階段：Android 進階操作介面（v7.1.11 候選）

- **遠征**：遠征狀態、派遣條件、可用任務與駐紮所夥伴分成四張操作卡；選取任務的時間／好友度／獎勵資訊不再被下一次狀態更新蓋掉。派遣前仍執行原設定驗證、使用者確認及好友度補給檢查。
- **副本／協力**：官方 1262 靜態副本查閱與即時房間分離；建房、入房、準備／取消、開始／進場及免費協力獎勵各自分區。保留密碼遮罩、手動確認成本、禁止自動購買付費寶箱與未知回覆禁止重送。
- **煉金／製作**：煉金模式、五材料格位與執行佇列卡片化；製作的官方配方、設備／收藏篩選、排程、配方詳情及「自訂製作清單」彈出視窗統一霓虹版型。原先材料預覽、批數驗證、製作佇列版次及明確消耗確認全部保留。
- **NPC 與儲藏**：NPC 場景／選擇、已驗證對話與商店唯讀資訊分區；儲藏室／雜物櫃選區、來源道具、數量及存取結果分區。仍須核對官方資料版本、角色場景、兩端物品身分與庫存版次。
- **福利／魔方**：可開啟次數、分析倒數與背景自動開啟按鈕分區；倒數每秒更新且不增加 IPC 輪詢頻率，設定同步期間不發送錯誤自動開啟指令；禁止未確認或逾時結果自動重送。
- **AI／補給設定**：原七類設定分為基本戰鬥、補給／必要成員、維護／JSON 資料交換三組；彈出編輯器的分類、草稿、保存與取消均使用共用 Kivy 卡片。保留角色與夥伴技能規則、補給數值、整理規則及明確保存後才套用。
- 全數為 **Android 倉庫 UI 修改**，不改動電腦版 Repository、遊戲封包核心或原本的安全限制。尚未進行的 ARM64 APK、320dp 小螢幕、實際 FPS、正式服登入及操作需獨立驗收，不得宣稱已測試。

## 操作流程

### Android 原生啟動畫面

手機開啟 APK 時，Kivy 主畫面還沒建立，會先顯示 python-for-android SDL2 的原生 `presplash`。原本 `buildozer.spec` 只有設定 App ICON，沒有設定 `presplash.filename`，因此手機仍顯示 Kivy 預設黑底 `Loading...`。目前啟動圖改由 `tools/android_presplash.py check-spec` 使用原始 App 圖示即時產生獨立 `android_app/assets/presplash.png`（512×512 深藍畫布，原圖置中縮至 196px），避免啟動畫面整張人物圖佔滿手機寬度。App 圖示本身不變，背景仍為 `#081626`。

完整 APK 建置流程會在編譯後檢查 APK 內的 `res/drawable*/presplash` 圖片是否與產生的 LaLa 精簡啟動圖相符，通過後才上傳；Artifact 中另附 `PRESPLASH_INFO.txt`。**此修改只改啟動圖案，並不能修復真正卡在 Loading 的崩潰或初始化失敗**。若新版本停留在啟動畫面超過一分鐘，請提供手機 Logcat 供進一步定位。

### 1. 安裝及開始登入

1. 從 [手動／Tag APK 建置流程](https://github.com/blesses0603/WLRe_lala_Android/actions/workflows/android-apk.yml) 的成功執行紀錄下載帶版本號的 ARM64 APK；舊版的 [ARM64 Artifact](https://github.com/blesses0603/WLRe_lala_Android/actions/runs/39141939393) 可在尚未過期時使用。日常 [快速測試流程](https://github.com/blesses0603/WLRe_lala_Android/actions/workflows/android-smoke.yml) **不再上傳 APK**。
2. 解壓後確認 APK 與 `SHA256SUMS.txt`，在 ARM64 Android 12 以上手機安裝測試包。
3. 啟動程式後先進入「官方資料與資料庫檢查」頁；前景服務核對官方版本、Manifest、Bundle、Runtime 與 SQLite，Activity 另行確認相同 Catalog 識別。**兩端驗證均通過才顯示帳號登入頁**；失敗可在檢查頁查看原因、重新檢查或重新啟動背景服務，不能跳過驗證。
4. 進入帳號登入頁後選擇地球／水星及分流，輸入帳號與密碼。帳號驗證、角色清單與角色入場須等待伺服器實際回覆。
5. 可新增多個獨立連線；各帳號各自擁有停止旗標、指令佇列與狀態，不將一個帳號的操作轉送給另一個帳號。
6. 入場後在帳號卡片啟動／停止自動戰鬥或徘徊，也可開啟角色功能，操作戰場、地圖、補給、社交與製作等頁面。

停止某個帳號不等於停止其他帳號；「停止全部連線與服務」會關閉整個連線服務。若服務尚未就緒或已失去回應，UI 應顯示未知或失聯，不以先前快照冒充目前在線。

### 2. 前景通知及背景連線

App 回到前景時會重新建立 Kivy 畫面，恢復帳號／伺服器欄位與原角色功能頁，再從仍在執行的連線服務讀取帳號快照。此動作不重新登入、不重啟遊戲服務，亦不保存背景期間輸入的明文密碼。若手機仍出現全空白主畫面，請提供當次 Logcat 的 `WLRE_ANDROID_UI_RESTORE_` 診斷標記。

本專案不是單靠 Kivy 畫面維持連線。`android_app/service.py` 啟動獨立的 Python 前景服務程序，在服務端管理多帳號連線；`android_app/runtime.py` 使用 App 私有 Unix socket 將畫面操作交給服務處理。

- 畫面暫停、切換到其他 App 或 Activity 重建時，前景服務可繼續管理連線；使用者重新開啟畫面後可取回狀態。
- 系統前景通知提供返回 App 與停止全部連線的入口。通知的常駐標記不能保證 Android 不允許使用者移除。
- 活動連線時使用**有期限的 partial wake lock**，並透過 TCP keepalive 協助偵測網路中斷；兩者都不是永久在線的保證。
- Android 15 的 `dataSync` 類型前景服務在適用條件下有每 24 小時累計約 **6 小時** 的背景執行時限；系統停止服務後不會擅自用儲存帳密重新登入。
- 網路切換、省電模式、Doze、廠商背景限制及使用者在系統設定強制停止 App，都可能中斷服務。長時間行為須逐台手機驗證。
- 裝置電池、記憶體、喚醒鎖等監控讀取如果失敗，只會回報監控異常，不會因為監控本身的例外直接關閉 IPC 服務或所有角色連線。

### 3. 懸浮小球（v0.0.7）

**懸浮球是選用的狀態介面，不是另一條遊戲連線，也不能替代前景服務通知。**

1. 開啟 App → **服務與資源** → **開啟懸浮小球（需額外授權）**。
2. 系統開啟「顯示在其他應用程式上層」設定時，允許本 App 使用；返回程式，等待背景服務同步設定。
3. 小球可以拖曳至螢幕其他位置，點擊小球展開狀態面板。
4. 小球沿用 App 原本的 ICON 並顯示在線數徽記。展開的科技風格「角色概況」卡片顯示在線／活動／總帳號數，以及各帳號實際同步的角色、夥伴、Lv.、HP／SP 數值與進度條、自動戰鬥、自動徘徊與事件狀態；卡片可捲動，亦可返回 App 或收合面板。
5. 點「隱藏懸浮小球（不斷線）」或回到「服務與資源」關閉小球；**不會因單純關閉小球而停止遊戲連線**。

顯示在其他 App 上層時，帳號名稱會遮罩，不顯示密碼、聊天內文或憑證；狀態面板最多列出六筆帳號；每個帳號只顯示角色本人，以及經 S19 伺服器回覆確認正在出戰的唯一夥伴。沒有出戰夥伴時不顯示夥伴列，也不列出待命夥伴或「還有幾位夥伴」提示；斷線後不顯示舊角色詳細資料。當權限被撤銷或前景服務結束，小球可能消失；普通 Android App 無法禁止使用者或系統關閉它。

主 App 介面統一採用深藍圓角科技主題：帳號卡片、操作按鈕、角色功能頁、文字輸入框、下拉選單及選項、核取圓鈕和設定視窗皆使用共用圓角樣式，且有按下與停用狀態。懸浮球只保留戰鬥、徘徊及事件；**煉金、製作、補給仍顯示在主 App 的角色概況**，但不傳入懸浮面板。

懸浮權限與 Android 13 以上的**通知權限**是不同設定。通知權限在系統要求時處理，懸浮權限只在使用者主動開啟小球時要求。**安裝 APK 並不會自動取得懸浮權限**。

### 4. 帳號與設定資料

- **帳號保存是自願選項**：勾選「加密保存帳密」時，使用 Android Keystore 的 AES-256-GCM 加密後，儲存在 App 私有、不備份的檔案位置；未勾選則不保存密碼。
- Keystore 金鑰不可匯出。解除安裝、清除 App 資料、換機或系統金鑰失效，都可能導致舊密文無法恢復。不要把此機制當作跨裝置備份。
- 自動戰鬥 AI 與偏好依帳號及伺服器保存，重新登入可載入，但**不會自動啟動戰鬥或徘徊**。
- 畫面與服務之間使用私有 Unix socket；沒有開放外部 TCP 控制埠。帳密不得寫入日誌、聊天事件或公開通知。
- 事件歷史與聊天紀錄在服務內做有限長度保存；若服務終止，不應假設未另存的記錄可永久保留。
- 聊天僅在收到伺服器發話結果為成功時才清除相同草稿；發話被拒絕、IPC 結果不明或伺服器長時間沒有回覆時，保留原文字並解除送出按鈕。因協定不支援端到端已讀確認，仍不保證對方已收到。
- IPC 失聯不會自動重送道具使用、煉金、製作或聊天等可能重複執行的操作；畫面將提示使用者先確認伺服器狀態。

## 功能分類

完整細項、條件及桌面版差異請閱讀 [電腦／手機功能對照](FEATURE_PARITY.md)。手機端的功能分區如下：

| 分區 | 範圍 |
| --- | --- |
| 帳號／角色 | 伺服器分流、登入選角、獨立連線、狀態與資源監控 |
| 戰鬥／隊伍 | AI 條件、補給、戰場陣形、手動戰鬥、組隊管理 |
| 移動／地圖／傳送 | 小地圖、位置、路線、傳送與場景資料 |
| 物品／製作／補給 | 背包、技能、煉金、材料、配方、收藏與排程 |
| 社交／紀錄／其他 | 聊天、組織、事件紀錄、經驗效率及偏好 |

資料尚未由遊戲伺服器確認時，核心應拒絕或暫停相關操作，例如未知位置、未學會的技能、未確認配方、未收到材料消耗結果等。不能用 UI 上存在某個按鈕，推論遊戲伺服器已接受該功能。

## v0.0.8｜正式 ARM64 原生核心打包

自 v0.0.8 起，手動／版本 Tag 完整 APK 工作流程改為 **先在隔離資料夾中把 `wlre/network/wire.py` 編譯成 `_wlre_wire_native.so`，再以既有固定 Debug 金鑰重新簽章**。正式儲存庫中的 Python 原始檔仍可用於回歸測試；原生替換只在 Android 打包暫存環境進行，桌面版不受影響。

正式 APK 上傳前必須同時通過 `NATIVE_WIRE_INFO.txt`（ARM64 ELF、Cython 模組位置、只有 shim bytecode）、`SIGNING_INFO.txt`（`Mode: persistent`、公開簽署者指紋 VERIFIED）、`PROTECTION_INFO.txt` 及 SHA256SUMS。任一項不通過就不提供新的 APK Artifact。其他 Python 位元碼仍可能被分析，並非全部原生化。

**更新注意**：如果手機目前安裝的是固定 Debug 簽章的舊版，同時 App package name 不變且系統判定 versionCode 可升級，v0.0.8 應能直接覆蓋更新；若安裝的是先前 Phase04 **臨時簽章的實驗 APK**，無法用固定簽章正式版直接覆蓋，且卸載可能刪除加密帳密／私有設定。請先確認簽署者，不要貿然卸載。

這次 CI 正式編譯、固定簽章與舊版原地升級仍須以 **v0.0.8 main 工作流程實際成功執行及手機更新結果**驗證，不能用先前實驗 APK 的成功紀錄代替。

## GitHub Actions｜P3 八核心 SHA-256 增量編譯（2026-11-03）

在 P1 ccache、P2 第三方 Recipe 快取之外，P3 針對八個 LaLa 原生 Cython Recipe 各自計算 SHA-256：lalawire、lalavault、lalaruntime、lalasessions、lalaclient、lalaprotocol、lalaautobattle、lalaexpedition。

每個指紋包含隔離 staging 的原始 .pyx、Recipe 定義與 setup.py、共用快取程式、收據產生工具、p4a 與工具鏈設定、Android API/ABI、NDK、Python target 及 Runner ImageVersion。個別核心修改只讓該核心失效；平台或共用實作變動使相關快取全部失效。以個別完整 SHA-256 精確命名 actions/cache key，不使用模糊的 restore-keys 前綴；Android Patch 版本編號不會自行讓原生快取失效。

只有受信任 main 手動／Tag 工作流的完整固定簽章 APK 已通過八核心 ELF、Shim、資源、正式憑證、SHA256SUMS 與 Phase09 發行 Gate，才將每個核心唯一的已核驗 ARM64 .so 加上大小／SHA-256 收據保存至隔離 cache。不可保存完整 python-installs、Distribution、APK、Keystore、帳密、Secret、原始敏感 Python 實作；仍重新進行 APK staging／組裝與完整安全稽核。

恢復前再次核對 per-core key、檔名、大小、SHA-256 與 ARM64 ELF；損壞、來源不符、快取服務失效、Runner 身分不明時，直接走原 p4a CythonRecipe 完整編譯，不能把快取命中視為原生功能驗收。PR 快測不取得簽章 Secret，也不執行 Buildozer。

驗收方式：PR 先做各核心來源隔離失效、快取遭竄改、標準編譯降級和 Workflow 安全政策回歸；授權合併 main 後在相同 Runner／工具鏈執行兩次完整 ARM64 APK 手動建置，比較八核心命中數、實際編譯時間和完整 Phase09 結果。兩輪 APK 通過仍需 Android 真機 native import、背景服務與正式伺服器驗收。P3 僅修改 CI／測試／文件，Android 版本維持 v7.1.5。

## GitHub Actions｜P1／P2 原生編譯快取（2026-11-03）

在既有 SDK／NDK／Gradle 下載快取上新增兩層 **受信任 main 手動／Tag APK 建置專用**優化。此項不更改遊戲程式版本 v7.1.4，也不提前發布或減少既有稽核。

- **P1：ccache**：CI 安裝 ccache，透過 p4a 自動偵測及 NDK Clang 編譯器內容校驗，重用相同 C／C++ 輸入的編譯物件。設定 850 MiB 容量上限；快取鍵包含 Buildozer、p4a、Cython、Android API／ABI 和 requirements，逐次成功建置再以 run ID 保存新物件。執行 `ccache --show-stats` 檢視命中情況。
- **P2：第三方 p4a Recipe 快取**：只保存指定的 `other_builds` 編譯目錄及 `packages` 來源快取：`freetype`、`hostpython3`、`jpeg`、`libffi`、`liblzma`、`libwebp`、`openssl`、`png`、`sqlite3`、`python3-liblzma`（package 目錄使用 `python3`）。以 Runner `ImageVersion`、p4a pinned commit、NDK r28c、API 31、arm64-v8a、Buildozer／Cython、requirements 及全部本機 Recipe 文字來源內容計算 SHA-256 指紋；Runner 映像版本未知時不恢復已編譯原生快取。
- **明確不保存**：任何 `lala*` 原生 Recipe 建置結果、`dists`、`python-installs`、`bootstrap_builds`、簽章私鑰、APK、應用程式來源、帳密或遊戲資料庫。八個 LaLa 原生核心依既有流程 Stage／Buildozer 編譯及 APK 稽核，不以快取取代原始碼一致性檢查。
- **失敗恢復與保護**：快取讀取／寫入異常不阻止原本完整編譯；只有完整 APK 已通過版本／固定簽章／八核心 ELF／SHA-256／安全檢查後才保存。PR 快速 CI 只做離線單元測試，不讀取簽章 Secret、不直接產生 APK。

**驗收**：在 PR 快速 CI 驗證政策／指紋測試；合併 main 後手動建置兩次，首次保存、第二次確認 `Restore pinned third-party p4a recipe builds` 是否 cache-hit、`Display compiler cache statistics` 的 ccache 命中率，檢查 APK 正式簽章與原生稽核全數通過。若 p4a 重建過多、快取過大或儲存／還原耗時，應依 Actions 記錄調整白名單。**目前仍需實際 ARM64 CI 驗證快取可否加快、能否重用選定 Recipe。**

## GitHub Actions｜安全增量下載快取（2026-11-03）

完整 ARM64 APK 建置新增 Python pip 套件快取，並以 `tools/android_build_cache.py` 的指紋控制下列下載目錄：`~/.buildozer/android/platform/android-sdk`、`~/.buildozer/android/platform/android-ndk-r28c`、`~/.gradle/caches/modules-2`、`~/.gradle/wrapper/dists`。這些全域工具鏈位置已由 v7.1.2 成功的 Buildozer 日誌核對。只有成功通過既有 APK 原生、簽章與完整性檢查，才會保存版本化快取。版本變更但相依不變時可重用工具鏈；p4a commit／編譯器或 Buildozer 版本／API／ABI 或 requirements 異動將使快取鍵變更。

**安全邊界**：不快取隔離 staging、p4a 編譯輸出、`android-output`、APK、中繼封裝、私鑰、簽章或帳密。每次仍完整重建八個 ARM64 原生核心、產出 APK 並執行安全稽核及固定簽章。這是「增量依賴下載」，不是已實現「只編譯變動的 Cython 模組」；後者需驗證 p4a 依賴圖及原生產物清潔性後才能逐步導入。

**驗收方式**：先由 PR 快速 CI 確認 Python 與快取政策測試；合併 main 後由使用者手動執行 APK workflow，首次正常保存快取，後續相同相依環境的建置觀察 `Restore Android SDK, NDK and Gradle dependency cache` 是否顯示 cache-hit，並比對 Buildozer 執行時間。快取上限與清除由 GitHub 管理；下載及壓縮耗時不保證每次都更快。僅調整 CI，不變更 Android v7.1.4 版號。

## GitHub Actions｜節省額度的兩階段模式（2026-10-19）

因 GitHub-hosted Runner 免費分鐘數有限，已將日常 Python 測試與完整 Android 原生編譯分開。**一般 PR／main push 不再自動執行 Buildozer，也不會產生 APK。** 此模式不更改 Android 12（API 31）、ARM64-only、APK 版號、功能或既有固定簽章。

| 工作流程 | 觸發方式 | 執行項目 | APK 產物 |
| --- | --- | --- | --- |
| [Android fast checks (no APK)](../.github/workflows/android-smoke.yml) | 指定路徑的 PR、main push，或手動 | Python 3.11 回歸、語法、版本一致性、安全預檢、ARM64 配置檢查 | **無** |
| [Android ARM64 native phone APK (pinned signing)](../.github/workflows/android-apk.yml) | 在 **main 手動** Run workflow；或推送符合目前版本的 `vX.Y.Z` Tag | 相同測試 + 隔離 staging 內 Cython 3.0.12／NDK ARM64 原生 wire + pinned persistent 簽章 + SHA256 + 原生 ELF／shim／啟動畫面檢查 | `WLRe_LaLa-Android-vX.Y.Z-debug` |

### 需要新 APK 時：手動建置

1. 先確認 [快速測試 Actions](https://github.com/blesses0603/WLRe_lala_Android/actions/workflows/android-smoke.yml) 的最新 main 測試通過。
2. 打開 [Android phone APK (version tag)](https://github.com/blesses0603/WLRe_lala_Android/actions/workflows/android-apk.yml)，按 **Run workflow**。
3. Branch 選擇 **main**，再按 **Run workflow**。其他分支會被版號檢查拒絕。
4. 等待成功後下載 `WLRe_LaLa-Android-v0.0.8-debug`（版本升級後名稱會隨版本變更）。ZIP 包含 APK、`SHA256SUMS.txt`、`SIGNING_INFO.txt`、`NATIVE_WIRE_INFO.txt`、`PRESPLASH_INFO.txt` 及 `PROTECTION_INFO.txt`。
5. 對照 `SIGNING_INFO.txt` 的 `Mode: persistent` 與 `Pinned public signer SHA256: VERIFIED`。不要把 PR 用的臨時簽章 APK 當作手機長期更新包。

需要發佈下一個新版本時，須先同步更新 `buildozer.spec` 與 `android_app/version.py`，然後才建立相符的 `vX.Y.Z` Tag；Tag 必須指向 main 歷史中的 Commit。**既有 GitHub Secret `ANDROID_DEBUG_KEYSTORE_BASE64` 和 Variable `ANDROID_EXPECTED_SIGNER_SHA256` 保持原樣，不重新產生或輸出私鑰。**沒有它們，完整建置會拒絕發佈，不會悄悄改用臨時簽章。

### 已有的最後一份自動 ARM64 主分支產物

- 歷史成功 Run：[39141939393](https://github.com/blesses0603/WLRe_lala_Android/actions/runs/39141939393)，Commit `dda1719`，Artifact 為 `Android-arm64-apk`，保存至 2026-10-26（台灣時間）。
- 此舊 Artifact 只在 GitHub 保存期限內可下載；**改成快速測試後，新 main/PR 的每次提交都不會再有 APK**。
- 當前不會自動進行 API 31～36 模擬器測試；ARM64 打包成功也不能代替真機遊戲登入與長時間背景驗收。

## 開發與測試

**主要程式**：`main.py`（Kivy 直式入口）；`android_app/`（UI、連線與服務）；`wlre/`（共用遊戲核心與資料）；`buildozer.spec`（Android 套件設定）。Android 使用本地 `wlre/` 副本，桌面專案的更改不會自動同步至手機。

日常快速 CI 使用 **Ubuntu 22.04、Python 3.11、Java 17**；只有手動／Tag APK 工作流程額外安裝 Buildozer 與 Android 工具鏈。本地 Linux 測試須具備系統相依套件及可用顯示器（或 Xvfb）：

```bash
python -m pip install -r requirements-dev.txt
xvfb-run -a python -m unittest discover -s tests -q
python -m compileall -q main.py android_app wlre tools
```

本地 ARM64 編譯（還需要 Android SDK／NDK 與 Buildozer 原生建置相依）：

```bash
python tools/android_native_wire.py stage --source . --output /tmp/wlre-android-native-release
(cd /tmp/wlre-android-native-release && buildozer -v android debug)
```

**修改 Android 版本**時，需同步調整 `buildozer.spec` 的 `version` 與 `android_app/version.py` 的 `ANDROID_VERSION`；一般 `main` 更新**只執行快速測試，不再編譯 ARM64 APK**。要測試安裝包時從 main 手動執行 `android-apk.yml`；準備發布新版本時才建立相符的 Git Tag。不要把桌面版的 Nuitka、BAT、Tkinter 建置步驟混入 Android 專案。

## 驗收項目及限制

請區分快速測試與完整 APK 產物的 GitHub Actions 結果；只有手動／Tag 完整工作流程才能確認 ARM64 打包與固定簽章；歷史測試細節收錄於 [VALIDATION.md](VALIDATION.md)。目前**仍須 Android 真機確認**的項目包括：

- ARM64 手機的安裝、啟動、登入、選角，以及不同伺服器／分流下的狀態同步。
- 同時多帳號登入；中斷 A 帳號時不影響 B 帳號，網路切換與重新連線狀態是否正確。
- 懸浮小球授權、拖曳、展開、關閉、跨 App 顯示及權限撤銷後的回復。
- 自動戰鬥、徘徊、補給、煉金、製作與社交操作的實際伺服器回覆。
- 15／30／60 分鐘鎖屏與省電模式測試，包含斷線、重連、記憶體及裝置耗電觀察。

**請以實際封包或伺服器回應辨識成功，不以畫面顯示或背景服務程序存活代表所有功能正常。**

相關文件：[驗收規格](ACCEPTANCE.md) · [桌面／手機功能對照](FEATURE_PARITY.md) · [歷史驗證紀錄](VALIDATION.md) · [遷移說明](../MIGRATION.md)。


### v0.5.12 非 NPC 功能同步（開發 PR #24）

手機副本頁新增經使用者明確確認的建立、加入、離開、協力準備、一般副本開始與入場、免費協力獎勵手動／可選自動領取及取消；手機配點頁可依完整伺服器同步的基準手動分配五項能力點。協力獎勵非同步修補、事件接續與匿名診斷亦同步。只有完成正式伺服器回覆才算成功，未確認／斷線後不重送。

依使用者要求，本次完整排除新的 NPC 互動、對話、選項、商店及相關資料索引。桌面專用 Tkinter／Nuitka 不移植到 Android。這些功能需要新 APK 才能實機使用，目前仍未完成遊戲伺服器與正式固定簽章 APK 驗收，Android 版本維持 v0.0.8。
