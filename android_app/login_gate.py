"""Fail-closed Android pre-login screen gate.

Both the independent foreground service and Android Activity must validate the
same official catalog and SQLite-backed runtime before showing login widgets.
No manifest revision string or launcher receipt can satisfy this predicate.
"""


def verified_for_login(service, local, *, connected):
    if connected is not True or type(service) is not dict or type(local) is not dict:
        return False
    if (service.get('status') != 'ready' or service.get('ready') is not True
            or local.get('status') != 'ready' or local.get('ready') is not True):
        return False
    token = service.get('catalog_token')
    if (type(token) not in (tuple, list) or len(token) != 2
            or token[0] is not True or type(token[1]) is not str
            or len(token[1]) != 64
            or any(ch not in '0123456789abcdef' for ch in token[1])):
        return False
    return local.get('catalog_token') == token
