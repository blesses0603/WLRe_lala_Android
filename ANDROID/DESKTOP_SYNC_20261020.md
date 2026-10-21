# Android / Desktop parity checkpoint (2026-10-20)

## Baselines and truthfulness

Desktop: `blesses0603/WLRe_lala/main` at `403679657d15b2ff79f8df44f8c510805e367bd8`.
Android: `blesses0603/WLRe_lala_Android/main` at `533fe07a6d22f69f664d8a2ceca4d15232e87bb3` (Android v0.0.8).

**This UI PR is not a full desktop feature port.** Avoid asserting a feature exists just
because a similarly named menu or bundled desktop file exists. Android remains an
independent, ARM64-only platform with protected native P0/P1 cores and limited IPC.

## Implemented in this PR

- Native bootstrap splash: generate 512px dark canvas and a centered 196px logo,
  without enlarging the actual launcher icon or changing signatures.
- Crafting catalog: stable 88dp cards, six recipes per page, separate name, state,
  icon, and details action; group production queue below the catalog.
- Dashboard: compact selector, preserve existing 13 working feature pages.
- Overlay: online game character becomes the heading; no masked or raw login account,
  and no duplicate name block. Event status is followed by divider and actual EXP/h
  total, last-10 and last-30 summaries, with honest empty-sample placeholders.

## Desktop differences requiring separate, gated engineering

| Desktop main module / capability | Android current status | Safe next step |
| --- | --- | --- |
| `network/instances.py`, `instance_actions.py` and `services/instance_*.py` | **Not ported** | Port read-only snapshot parsing first; validate confirmed server responses and IDs |
| 副本／協力建立房間、加入、準備、開始、獎勵 | **Not available on Android** | Explicit IPC allowlist, confirmations, no blind retry; mobile room window and 720p regression |
| `services/battle/attribute_points.py` | **Not ported** | Examine attribute state schema, add read-only mobile display, then guarded allocations |
| `network/commands.py`, `command_envelope.py`, `service_scheduler.py` | Android service architecture differs | Compare semantics; port only verified changes with native-core tests |
| `core/state_*_events.py`, `services/coordination.py` | Android uses earlier monolithic state/network path | Port incrementally with state/event regression and protocol fixtures |
| Desktop refactored expedition manager and crafting reservations | Android has earlier functional logic | Behavioral diff and regression tests before any protected-core replacement |

Current Android features documented in `ANDROID/FEATURE_PARITY.md` still exist:
battle, roaming, bag, room storage (read-only), map, party, companions, expeditions,
alchemy, crafting, chat, EXP and event history. These are not all at identical
desktop revisions. Cross-platform Python modules with the same path but different
Git SHA do not by themselves prove functional incompatibility.

## Release and safety gates

- PR checks: `android-smoke.yml` only (unit/UI tests, Python syntax, hardening).
- New signed ARM64 APK is **not** produced by an ordinary PR; native build remains
  manual on `main` or a validated release tag.
- Do not merge desktop native Python code into Android P0/P1 shim files; follow
  Phase05 stage + audit + signing verification for future core ports.
- Real phone acceptance still needed: normal cold start, 1-hand portrait layout,
  scroll/pagination in crafting, multi-account overlay, EXP sample progression,
  rotation/IME, app pause/resume and lock-screen service continuity.

## 2026-10-20｜桌面 v0.5.6 增量同步（分階段 PR）

- 本批次電腦版來源：`11962634c48a04e82eb060226736c4ad3fe8b610`（v0.5.6）；Android 基底：`7b5dee8aab13a65cb22e1f66a2d73d56fb62ca73`（v0.0.8）。
- 同步 `wlre/services/instance_browser.py` 及官方核對的 `instance_catalog_1262.json`，新增手機「副本資料」唯讀搜尋與明細；完全不發 S85／S186 指令。
- 新增「角色能力」唯讀頁面，僅展示已由 S5 等資料同步的五項能力與剩餘點數；缺欄位顯示「待同步」，不發配點封包。
- Android 的 `GAME_COMMANDS` 仍不允許副本建立、加入、領獎或配點，必須完成協定核對、IPC 權限及回覆確認測試後才可開放。
- 未變更 `android_app/version.py`、`buildozer.spec`、原生 P0/P1 核心及簽章／Keystore／APK Actions。
- **尚未同步** 電腦版 v0.5.6 戰後維護／AI/S51-1 診斷修補、最新狀態拆分及副本即時互動。這些涉及 Android core 及 service 的介接，須以獨立 PR 逐項完成。
- 此 PR 只能代表唯讀功能移植；CI 執行結果以 GitHub Actions 為準，APK 與真機仍須另外驗收。


## 2026-10-20 第二批：S85／S186 唯讀協定與診斷

- 桌面基準 `11962634c48a04e82eb060226736c4ad3fe8b610`。移植 `wlre/network/instances.py` 與 1262 的 S85／S186 安全解析器，並引入相關副本狀態與操作確認模組，分別保存 main／coop 的伺服器資料。
- Android 僅將 `instance_refresh`、`instance_members` 納入 IPC 允許清單，並在遊戲核心驗證模式、參數、戰鬥／事件狀態、已確認房間 ID。沒有開放建立／加入／待命／開始／領獎，也沒有自動重送。
- 手機副本頁提供使用者觸發的房間清單查詢與已同步房間唯讀瀏覽。未回覆、失聯、未登入均顯示未知，靜態副本目錄不冒充即時狀態。
- 引入屬性點數驗證／確認模型與 S8-4 回覆辨識。**配點指令仍未開放**。
- S51-1 不完整 7 位元組資料形態會丟棄整筆、保留連線；記錄數字長度與截斷長度，不記錄原始封包。
- 連線例外安全診斷只保留例外類型與原始碼位置；AI 合作戰鬥 war_style=16 不再單純因戰鬥種類暫停。
- 不修改 Android Keystore、前景服務生命週期、原生封裝建置工作流程或版本號。簽章 APK、正式連線與真機仍待驗收。


## 2026-10-20 第三批：戰後維護、背包預留與核心事件分派

**已整合，尚非桌面核心 100% 同步：**

- 引入桌面 v0.5.6 的 `state_events.py`、`state_world_events.py`、`state_battle_events.py`、`state_session_events.py`。Android 的 `State.apply` 保留先執行各服務觀察器、再分派登入／場景／戰鬥事件、最後更新效率統計；不替換 Android Kivy／前景服務。
- 加入 `coordination.py`，集中手動指令與各服務的等待原因。煉金、製作、遠征、徘徊在維護／事件／共用資源忙碌時暫停**新增請求**，但仍處理原本 pending 的伺服器回覆與逾時。補給標記 uncertain 時煉金必須 **fail-stop**，不可將未知結果當一般可恢復暫停。
- 加入 `items/reservations.py` 的格位、道具 ID、序號、數量預留機制；將戰後維護和非戰鬥背包補給接到共用保留登記。背包 snapshot 保留未確認的 holds，格位替換／序號異常使資料不可靠；逾時僅標記 uncertain、不得重送或自動解鎖。
- Android 仍有舊式 `inventory.reserved` 介面。手動戰鬥耗材、煉金和遠征的全部預留流程**尚未改寫為完整桌面 registry**；這一批透過相容檢查讓新舊預留互斥，避免大幅度替換引入回歸。
- 加入 `network/command_envelope.py`；網路佇列先驗證 command type。錯誤回報只允許安全有界的指令名稱，不回顯任意物件／帳密。
- 增加 `tests/test_android_coordination.py` 驗證跨服務拒絕／暫停、原子保留、背包快照、序號變更、補給確認與逾時、無效命令及事件分派。
- 不增加新的副本建立／配點／領獎命令；不修改 Android 版本號、JNI／Cython、Keystore／固定簽章或 APK 工作流程。

**待實機驗收：** 遠征領獎後續連線、多人協力戰鬥、戰後自動補給／修理、手機鎖屏後續執行與安裝更新。GitHub 快速 CI 僅能驗證測試與靜態安全條件，不能等同真實 APK 與遊戲伺服器驗收。


## 第四批：共用物品預留全面串接與遠征斷線防護（2026-10-20）

**來源與架構**：繼續對照桌面 v0.5.6 `main` (`11962634c48a04e82eb060226736c4ad3fe8b610`)，只修改 Android Python 核心／測試。不更換 Android Kivy／前景服務、Cython／JNI、版本號、簽章或 APK 建置程序。

- 戰鬥耗材：`combat_resources.reserve` 改用 `reservations.acquire(..., 'battle')`；保留道具 ID、格位、序號與數量。背包確認扣料才減記。AI 回合與手動 `battle_submit` 出錯時透過 checkpoint／restore 同時回滾 `holds`、`reserved` 與格位鎖定。
- 連續煉金：以 `alchemy` owner 統一預留；只有「煉金結果、產物入包、所有材料扣除、背包可靠」全部確認後才釋放。失敗、材料不明或逾時一律保留 `uncertain`，不重送或樂觀回復。
- 遠征好友度：恢復物品改以 `expedition` owner 綁定格位、物品身分與數量，先預留後發出 S31-27；需要好友度變更與材料扣除雙確認。逾時即 `uncertain` 且停止派遣，禁止重送。
- 遠征領獎：維持 S31-16 獎勵回覆與背包入包雙重確認。新增「領獎結果先到、S31-19 任務刷新接著到、背包最後到」以及模擬 socket 連續事件測試。
- 1262 封包相容性：S31-15 允許官方 Lua 不解析的擴充尾端（只記長度、不保留內容）；S31-19 正式讀取 50 組資料後的必要 show/refresh 旗標。保留未知封包及 S31-16 的長度檢查，不猜測內容。
- 網路結束：引入 Android 專用 `SessionLogic.disconnect`，凍結所有未確認 `holds`，標記原狀態不可靠；若領獎／遠征／補給／維修尚未確認，標記 uncertain，保留等待狀態供診斷。重新連線仍新建 `State`。
- 已新增 `tests/test_android_shared_reservations.py`，涵蓋真實可堆疊官方材料、AI／手動保留、煉金未知結果、遠征領獎兩階段確認、伺服器事件順序及斷線安全。
- **驗收界線：** Python CI 與模擬封包不等同 Android APK 安裝、正式伺服器封包實測；需以實際斷線 Log／正式服務器回覆驗證是否仍有其他斷線原因。沒有自動領獎重試。


## 第五批：製作材料共用預留與跨服務一致性修正（2026-10-21）

本批修正第四批稽核發現的 `crafting` 漏接共用預留問題。對照桌面 v0.5.6 的 `wlre/services/items/crafting.py` 與 `crafting_plan.py`，保留 Android 原有 Kivy／網路架構，不導入桌面專用的 `state_ownership` 寫入裝飾器。

- 手動或自訂製作排程在 S64-1 送出前，使用 `reservations.acquire(inv,'crafting',allocations,exclusive=True)` 原子預留所需格位。道具序號、材料數量及共用 `holds` 與 `reserved` 均保留，不能在伺服器回覆前被戰鬥、煉金、遠征搶用。
- 只有伺服器已確認 `craft_added`／有效快速製作回覆，且背包可靠、材料扣量符合、格位道具與序號不矛盾時，才釋放預留。只收到 ACK、扣料不足、序號變更、材料尚有剩餘卻整格消失，均不得宣稱已確認。
- 製作回覆逾時、材料狀態不明或連線中斷時，保留 `crafting` 的 `uncertain` 鎖定，停用自動接續，不重送消耗性封包。明確伺服器拒絕則依已確認失敗流程處理。
- `PlanMixin.plan_start`、自訂清單續送及手動 `_server_command` 一律檢查共同 `coordination_reason(state,'crafting')`；既有待確認回覆／逾時仍先處理，暫停時同步更新手機 UI 的繁體中文等待原因。
- 新增 `tests/test_android_crafting_reservations.py` 的 **10 項**案例：原子預留、重複格位衝突、ACK 與真實扣料順序、錯誤道具序號／格位消失、背包快照、逾時不解鎖、自訂清單閘門、連線結束等。
- 完整診斷回歸：**398 項測試通過**（詳細測試工作流程；標準快速工作流程另行驗證）。不修改原生程式碼、Keystore、ARM64 建置配置、簽章或 Android 版本 `0.0.8`。

**仍未實機驗收：** 正式伺服器的製作材料扣除、長時間自動接續、Android 鎖屏背景連線及固定簽章 APK 安裝。歷史第三／第四批的限制陳述屬當時進度，以本第五批覆核結果為準。


## 2026-10-21：第六批，桌面 v0.5.12 非 NPC 同步

- 桌面基準 ad1eba0af4dc41232baa1cece72680f6f40ee3b3；Android 基準 ab6bc331de5faa7d8bc096fb4b19fc5521f153d3。工作於獨立 PR #24。
- 完成可由手機明確確認操作的一般副本及協力房間服務和頁面、免費獎勵、角色配點、S85／S186 成員刷新與協力戰後一次事件接續。
- 採用 0.5.7 獎勵 S186-11／S186-3 非同步抵達修補，離房要求不可假設已經領獎成功。
- 同步部分跨服務／事件安全：對外指令格式先驗證、操作逾時各自處理、斷線防重送、匿名協力與維護診斷。
- 不加入 NPC 對話、選項、購物、NPC 資料資產或相關網路指令；電腦版原生視窗與桌面發布工具不適用於手機。
- 尚未執行正式伺服器的消耗性操作、ARM64 固定簽章 APK 編譯及實機驗收。Android 版本 0.0.8、簽章、原生防護維持不變。
