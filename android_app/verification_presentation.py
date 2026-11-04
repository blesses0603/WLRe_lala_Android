"""Data-only Android pre-login display state, without Kivy or network calls.

The reference artwork depicts all checks green, but that is only a mockup.
This model never grants login, never infers completion from version numbers,
and never exposes raw remote error payloads in the UI.
"""
import re

STEPS = (
    ("official", "官方版本", "核對應用程式版本與官方資源"),
    ("data", "DataPackage", "資料包版本與來源一致性"),
    ("main", "MainPackage", "主資源包版本與來源一致性"),
    ("manifest", "Manifest", "雙 Manifest 檔案完整性"),
    ("bundle", "Bundle", "必要官方 Bundle 完整性"),
    ("runtime", "Runtime", "動態 Runtime 與身分核對"),
    ("sqlite", "SQLite", "本機資料庫結構與內容"),
)

# Internal error categories, never an untrusted server-provided stage name.
_FAILURE_STAGE = {
    "manifest_download_failed": "manifest",
    "manifest_parser_missing": "manifest",
    "manifest_parse_failed": "manifest",
    "manifest_validation_failed": "manifest",
    "manifest_identity_mismatch": "manifest",
    "manifest_asset_missing": "manifest",
    "bundle_download_failed": "bundle",
    "bundle_integrity_failed": "bundle",
    "bundle_plan_failed": "bundle",
    "required_bundle_missing": "bundle",
    "required_bundle_invalid": "bundle",
    "runtime_parse_failed": "runtime",
    "runtime_data_invalid": "runtime",
    "runtime_identity_mismatch": "runtime",
    "runtime_catalog_unavailable": "runtime",
    "runtime_check_failed": "runtime",
    "runtime_check_superseded": "runtime",
}
_VERSION = re.compile(r"[0-9]{1,6}\Z")
_CHECKED_UTC = re.compile(
    r"20[0-9]{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\+00:00|Z)?\Z"
)


def package_versions(service):
    """Return only checked, numeric identifiers explicitly sent by our worker."""
    if type(service) is not dict:
        return {}
    values = service.get("verified_versions")
    if type(values) is not dict:
        return {}
    result = {}
    for name in ("DataPackage", "MainPackage"):
        value = values.get(name)
        if type(value) is str and _VERSION.fullmatch(value):
            result[name] = value
    return result


def view_state(service, local, *, connected=False, login_ready=False):
    """Seven stable statuses: pending / checking / passed / blocked.

    A network-side `ready` receipt proves the worker's remote check.
    Runtime and SQLite still wait for Activity-side validation and matching
    catalog tokens, which only the existing login gate may confirm.
    """
    service = service if type(service) is dict else {}
    local = local if type(local) is dict else {}
    connected = connected is True
    approved = connected and login_ready is True
    network_ready = connected and service.get("status") == "ready" and service.get("ready") is True
    versions = package_versions(service)
    states = {key: "pending" for key, _, _ in STEPS}

    if approved:
        states = {key: "passed" for key in states}
    elif connected:
        if network_ready:
            for key in ("official", "data", "main", "manifest", "bundle"):
                states[key] = "passed"
            if local.get("status") == "checking":
                states["runtime"] = "checking"
            elif local.get("status") in ("blocked", "error"):
                states["runtime"] = "blocked"
        else:
            if len(versions) == 2:
                for key in ("official", "data", "main"):
                    states[key] = "passed"
            if service.get("status") == "checking":
                key = "manifest" if len(versions) == 2 else "official"
                states[key] = "checking"
            elif service.get("status") in ("blocked", "error"):
                stage = _FAILURE_STAGE.get(service.get("failure_code"))
                if stage is not None:
                    states[stage] = "blocked"

    if approved:
        headline = "所有項目驗證通過"
        headline_kind = "passed"
    elif not connected:
        headline = "等待背景服務連線"
        headline_kind = "pending"
    elif local.get("status") in ("blocked", "error") or service.get("status") in ("blocked", "error"):
        headline = "官方資源或手機端驗證未通過"
        headline_kind = "blocked"
    elif service.get("status") == "checking" or local.get("status") == "checking":
        headline = "正在檢查官方資源"
        headline_kind = "checking"
    else:
        headline = "等待完整驗證"
        headline_kind = "pending"

    checked_at = service.get("checked_at_utc")
    if type(checked_at) is not str or not _CHECKED_UTC.fullmatch(checked_at):
        checked_at = None
    return {
        "steps": states,
        "versions": versions,
        "headline": headline,
        "kind": headline_kind,
        "approved": approved,
        "checked_at_utc": checked_at,
    }
