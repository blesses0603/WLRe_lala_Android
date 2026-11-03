"""Remote official game resource compatibility gate; bundled baseline.

Do not read the local Unity installation, LaLa binary or disk ManifestFiles.
"""
from wlre.services.official_version import (
    BASELINE, RESOURCE_MAP_URL, check_official_game_resources, check_official_versions,
)
from wlre.services.resource_compatibility import baseline_label


def compare_database_identity(remote, identity):
    """Compare current official identifiers with the active stored catalog.

    A match identifies versions; actual source bytes are checked separately.
    """
    if type(remote) is not dict or type(identity) is not dict:
        return 'unverified'
    packages = remote.get('packages')
    entries = identity.get('packages')
    if type(packages) is not dict or type(entries) is not list or len(entries) != 2:
        return 'unverified'
    if any(type(row) is not dict for row in entries):
        return 'unverified'
    expected = {row.get('name'): row.get('full_version') for row in entries}
    if set(expected) != {'DataPackage', 'MainPackage'} or any(type(v) is not str for v in expected.values()):
        return 'unverified'
    observed = {name: packages.get(name, {}).get('remote') if type(packages.get(name)) is dict else None
                for name in expected}
    if (any(type(v) is not str for v in observed.values()) or
            type(remote.get('resource_path')) is not str or
            type(remote.get('official_exe_version')) is not str):
        return 'unverified'
    if (identity.get('data_ver') != remote['resource_path'] or
            identity.get('exe_version') != remote['official_exe_version'] or
            observed != expected):
        return 'different'
    return 'same'


def configured_sources(environ=None):
    """The public verified root; per-package paths are resolved dynamically."""
    return {"ResourcePath_PC.dat": RESOURCE_MAP_URL}



def classify_runtime_failure(error):
    """Public, bounded diagnostic labels; never return exception payloads.

    File paths, URLs, package bytes, account fields and arbitrary exception
    messages must not cross the Android UI/service IPC boundary.
    """
    kind = type(error).__name__
    message = str(error)
    from wlre.services.world.bundle_runtime_1275 import _REQUIRED_TABLES
    tables = frozenset(_REQUIRED_TABLES)
    for prefix, code in (
        ("仍缺少官方 Bundle：", "required_bundle_missing"),
        ("Bundle 來源校驗失敗：", "required_bundle_invalid"),
        ("官方 Bundle 的資料格式無法建立完整 1275 Runtime：", "runtime_parse_failed"),
    ):
        if kind == "BundleRuntimeUnavailable" and message.startswith(prefix):
            table = message[len(prefix):]
            return {"code": code, "table": table if table in tables else None}
    if kind == "BundleRuntimeUnavailable":
        if message == "官方動態 Manifest 身分不一致":
            return {"code": "manifest_identity_mismatch", "table": None}
        return {"code": "runtime_data_invalid", "table": None}
    if kind == "IncrementalSyncError":
        if message == "Planned downloads exceed the explicit byte/file quota":
            return {"code": "download_limit", "table": None}
        if message.startswith("Required resources missing from current Manifest:"):
            return {"code": "manifest_asset_missing", "table": None}
    if kind == "DynamicRuntimeUnavailable":
        if message in (
            "Official versions changed before Bundle sync",
            "Official versions changed during runtime load",
            "Official manifests changed during runtime load",
        ):
            return {"code": "official_version_changed", "table": None}
        if message == "Runtime does not match pre-login official identity":
            return {"code": "runtime_identity_mismatch", "table": None}
    if kind == "ValueError" and message == "Runtime identity mismatch":
        return {"code": "runtime_identity_mismatch", "table": None}
    return {"code": "runtime_check_failed", "table": None}


def _run_dynamic_check(remote):
    """Permit login when current official runtime and database content agree."""
    from wlre.services.world.catalog_runtime import official_package_versions
    from wlre.services.world.dynamic_bundle_runtime import activate_for_official, invalidate_runtime
    result={"status":"unverified","blocked":True,"remote":remote,
            "source":"official_remote_only","dynamic_runtime":"unavailable",
            "baseline":{},"baseline_label":"官方動態 Runtime",
            "database_comparison":"unverified","data_compatibility":"unverified",
            "protocol_compatibility":"unverified","can_send_packets":False,
            "login_allowed":False,"database_verified":False,
            "block_reason":"official_identity_unverified",
            "message":"官方版本無法完整驗證；禁止登入，請重新查詢。"}
    if not isinstance(remote,dict):
        invalidate_runtime()
        return result
    try:
        versions=official_package_versions(remote)
        if (remote.get('status') not in ('same_resources','resources_changed') or
                any(remote['packages'][p].get('comparison') not in
                    ('same','newer','older','different') for p in versions)):
            raise ValueError('Incomplete official observation')
    except (ValueError,TypeError,KeyError):
        invalidate_runtime()
        return result
    support='／'.join(p+' '+versions[p].split('_',1)[0] for p in ('DataPackage','MainPackage'))
    result.update(baseline=versions,baseline_label=support,block_reason="runtime_unavailable",
                  status="runtime_unavailable",
                  message="官方版本已確認（"+support+"）；目前版本的完整 Runtime 未通過驗證，禁止登入。")
    try:
        runtime=activate_for_official(remote)
        identity=runtime.catalog_identity.as_dict()
        if compare_database_identity(remote,identity)!='same':
            raise ValueError('Runtime identity mismatch')
    except (OSError,ValueError,RuntimeError,TypeError,AttributeError) as exc:
        result["runtime_failure"] = classify_runtime_failure(exc)
        # Activation clears its own previous generation before loading.
        # A failed older worker must not invalidate a newer successful one.
        return result
    result.update(status="database_mismatch",dynamic_runtime="verified",
                  data_compatibility="compatible",runtime_identity=identity,
                  record_counts=dict(runtime.record_counts),
                  block_reason="database_mismatch",
                  message="官方 Runtime 已驗證，但 LaLa 資料庫尚未與官方資料一致；請先完成資料同步。")
    from wlre.storage.paths import data_root
    from wlre.services.world.resource_database import read_active_database_identity, database_matches_runtime
    database=data_root()/'official_sync'/'derived_catalogs'/'resource_inventory.sqlite3'
    try:
        stored=read_active_database_identity(database)
        result['database_comparison']=compare_database_identity(remote,stored)
        if database_matches_runtime(database,runtime):
            result.update(status="database_matches_official",blocked=False,
                          login_allowed=True,database_verified=True,can_send_packets=True,
                          database_comparison="same",block_reason=None,
                          message="LaLa 資料庫、官方最新資源與 Runtime 已核對一致（"+support+"），可進入登入。")
        elif result['database_comparison']=='same':
            result['database_comparison']='different'
    except (OSError,ValueError,RuntimeError):
        pass
    return result


def run_prelogin_check(sources=None, *, checker=None):
    """Use verified current manifests/runtime in production; fixtures are explicit."""
    if checker is None and sources is None:
        return _run_dynamic_check(check_official_game_resources())
    remote=checker(sources or {}) if checker is not None else check_official_versions(sources)
    packages=remote.get('packages',{})
    changed=(remote.get('status')=='resources_changed' or
             any(row.get('comparison') in ('newer','older','different') for row in packages.values()))
    client_changed=bool(remote.get('newer_official_client'))
    matched=(remote.get('status')=='same_resources' and
             all(packages.get(p,{}).get('comparison')=='same' for p in BASELINE))
    support=baseline_label(BASELINE)
    blocked=changed or client_changed or not matched
    if changed or client_changed:
        status='blocked'
        message=(f'官方遊戲客戶端版本已有變更，LaLa 支援資源基準為 {support}；禁止登入，請等待 LaLa 更新與相容性確認。'
                 if client_changed and not changed else
                 f'官方遊戲資源版本與 LaLa 支援基準 {support} 不同；禁止登入，請等待 LaLa 更新與相容性驗證。')
    elif matched:
        status='version_identifiers_match'
        message=f'官方 MainPackage／DataPackage 版本識別值均符合 LaLa 支援基準 {support}；遊戲協定相容性仍須另外驗證。'
    else:
        status='unverified'
        message=f'官方版本無法完整驗證（LaLa 支援基準 {support}）；禁止登入，請重新查詢官方版本。'
    return {'status':status,'blocked':blocked,'message':message,'remote':remote,
            'baseline':dict(BASELINE),'baseline_label':support,'database_comparison':'unverified',
            'source':'official_remote_only','dynamic_runtime':'unverified'}
