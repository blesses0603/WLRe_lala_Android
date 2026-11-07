"""Account/server-scoped UI data, private storage; never credentials or auto-start."""
import json
from pathlib import Path
from wlre.storage.atomic import write_json, file_lock
from wlre.services.expedition import preferences as expedition_defaults, validate as validate_expedition


def defaults(): return {'favorites': [], 'plan': [], 'expedition': expedition_defaults()}


def validate(value):
    if not isinstance(value, dict) or set(value) - {'favorites', 'plan', 'expedition'}:
        raise ValueError('偏好格式錯誤')
    ids = value.get('favorites', [])
    if (not isinstance(ids, list) or len(ids) > 100 or
            any(type(sid) is not int or not 0 < sid <= 65535 for sid in ids)):
        raise ValueError('收藏配方無效，最多 100 項')
    # Preferences are user drafts, not permission to execute a recipe.
    # Keep unavailable IDs through cold starts and official catalog changes.
    rows=value.get('plan', [])
    if not isinstance(rows,list): raise ValueError('清單格式錯誤')
    plan=[]
    for row in rows:
        if (not isinstance(row,dict) or type(row.get('item_id')) is not int
                or not 0 < row['item_id'] <= 65535
                or type(row.get('count')) is not int or row['count'] < 1):
            raise ValueError('清單項目格式錯誤')
        plan.append({'item_id':row['item_id'],'count':row['count']})
    return {'favorites': list(dict.fromkeys(ids)), 'plan': plan,
            'expedition': validate_expedition(value.get('expedition', expedition_defaults()))}


def path(base, key): return Path(base) / 'mobile' / (key + '.json')


def load(base, key):
    file = path(base, key)
    with file_lock(file):
        if not file.exists(): return defaults()
        data = json.loads(file.read_text(encoding='utf8'))
        if data.get('version') != 1: raise ValueError('偏好版本不支援')
        return validate(data['preferences'])


def save(base, key, value):
    value = validate(value); file = path(base, key)
    with file_lock(file): write_json(file, {'version': 1, 'preferences': value})
    return value
