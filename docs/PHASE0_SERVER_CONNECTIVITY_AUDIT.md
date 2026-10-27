# Phase 0：官方伺服器連線實作盤點（Android 版）

> 狀態：靜態程式碼檢查。沒有在本次盤點中連線官方正式伺服器、登入帳號、送出遊戲操作、建置 APK 或執行測試。
> 基準：main commit `e1767b33ac4e83dc60bd34539c3d2889380b861d`（Android 發行版本 v0.0.8）。

## 1. 已確認的程式位置與責任

| 路徑 | 已確認責任 | 尚不能據此宣稱 |
|---|---|---|
| `wlre/network/client.py` | `run_client(host, port, profile, ...)` 執行 TCP 連線、登入／封包收發與事件處理；有 `verify_account()` 驗證流程。 | 官方正式服登入成功或所有遊戲操作相容。 |
| `wlre/network/protocol.py` | 建立登入、選角、移動與戰鬥封包並解析伺服器回覆；帳密目前只接受 ASCII，非 ASCII 編碼明確標記為未驗證。 | 所有封包已經正式服 E2E 驗收。 |
| `wlre/network/wire.py` | 封包框架、Reader／Writer 與 XOR codec；註記 outbound codec 仍需真實客戶端擷取驗證。 | 本機 codec 測試足以證明官方協定相容。 |
| `wlre/resources/default_profile.json` | 有端點、XOR、platform/language 設定及 PCAP 證據摘要。 | 端點目前有效、屬於官方正式服或可直接登入。該檔明確寫著「observed PCAP; official live client not tested」。 |
| `android_app/sessions.py` | `SessionManager.start()` 驗證必要帳密與 host／port，建立記憶體 session 及 worker；以事件回報連線、驗證與登入狀態。 | UI 顯示「伺服器已連接」就代表登入成功；本機 session 建立不等於伺服器接受登入。 |
| `android_app/runtime.py` | Android Activity 與背景服務之間使用受限的本機 Unix socket IPC；不是遊戲伺服器連線。 | 此 IPC 測試能取代遊戲 TCP 連線或正式服測試。 |
| `tests/test_android_sessions.py` 及網路測試 | 可使用 fixture／mock host 與 socket 測試 session 生命週期及網路邏輯。 | mock 測試不是官方伺服器 E2E。 |

## 2. 連線流程（由程式碼確認）

1. Android UI 將帳號、密碼與 host／port 傳給 SessionManager；session worker 再執行網路 client。
2. 若啟用 `verify_first`，會先執行 login kind 0 的帳號驗證；該結果不等於正式遊戲登入成功。
3. 正式登入使用 login kind 2，之後解析登入結果、角色列表與遊戲狀態。
4. Android Runtime 的本機 IPC 只負責 UI 與服務程序溝通；遊戲網路連線由 `wlre/network/client.py` 負責。
5. 「已連接」「登入成功」「收到角色列表」「權威遊戲狀態更新」是不同階段，驗收必須分開判定。

## 3. 現有證據等級

- **已確認：** Android 版有 TCP client、登入／驗證流程、封包解析、session 管理及本機 IPC。
- **已確認：** 預設 profile 的證據描述是 PCAP 觀察，且明確標示官方 live client 尚未測試。
- **未確認：** 預設端點目前是否為官方正式服有效端點，以及伺服器是否接受目前程式登入。
- **未確認：** Android 實機上的正式服登入、背景服務生命週期及 Battle／Map 端到端結果。
- **未執行：** 本次沒有執行 pytest、socket 連線、正式登入、APK 建置或實機測試。

## 4. 下一步驗收順序（直接正式服測試策略）

### Gate A — 本機安全與協定測試
- 執行既有網路、協定、session 與 Runtime 測試，保留實際測試輸出。
- 測試登入狀態分層、TCP 分段／合併封包、逾時、EOF、錯誤回覆及敏感資料不落 Log。
- 確認帳密只在必要生命週期存在，不寫入 Log／PR／Issue，不透過 Android IPC 錯誤訊息洩漏。

### Gate B — 低風險連線確認
- 先核對端點可信來源與目前有效性，再只確認 TCP 可達性；不送帳密、不送遊戲指令。
- 若端點來源或有效性不明，停止，不將網路不可達直接解讀為協定錯誤。

### Gate C — 帳號驗證與正式登入
- 由帳號持有人在 Android 本機安全輸入測試帳號；不得將密碼寫入文件、Log 或對話。
- 先單獨驗證帳號驗證結果，再由使用者明確啟動正式登入；保存去識別化的階段、結果代碼與時間。
- 不自動重試不明登入結果；防止重複 session 或重複送出有副作用的操作。

### Gate D — Android 實機 Battle／Map 驗收
- 先觀察登入、角色列表與權威狀態，再由使用者逐項觸發可逆、低風險的手動操作。
- Battle 先驗證單次手動操作及伺服器回覆，再測試回合去重與自動戰鬥。
- Map 先驗證座標／場景權威更新，再測試短距離移動；傳送及消耗資源操作需獨立驗收。
- 額外驗證鎖屏、切換前後景、網路切換、服務停止／恢復及程序重建；不可把模擬生命週期測試當成真機結果。
- 每項案例分開記錄「本機送出」「收到伺服器回覆」「權威狀態改變」三種證據。

## 5. 安全與驗收停止條件

- 不記錄帳密、原始登入 payload、session token、聊天內容或含個資的 PCAP。
- 不自動重複登入、重複戰鬥指令、購買／交易、領獎或消耗物品。
- 若登入結果不明、背景服務與網路狀態不一致、收到未知封包或權威狀態不同步，停止該案例並保留最小必要診斷。
- 正式服 E2E 需實機測試證據；CI／mock 通過不能取代正式服驗收。

## 6. 結論

目前可以確認「Android 版具備 TCP client 與遊戲協定處理」，但**不能宣稱目前程式已成功登入官方正式伺服器**。應先執行本機測試並核對端點證據，再進行不送帳密的 TCP 可達性確認；登入與 Battle／Map 測試需由帳號持有人在安全條件下逐階段驗收。
