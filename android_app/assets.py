"""Bounded Kivy textures from bundled PNG archives; no desktop Tk dependency."""
import io
import json
import zipfile
from collections import OrderedDict
from kivy.core.image import Image as CoreImage
from kivy.uix.image import Image
from kivy.metrics import dp
from wlre.paths import RESOURCE_ROOT

_CACHE = OrderedDict()


def _trim_texture_cache():
    """Keep game sprites bounded and preserve at most four map textures."""
    maps = [key for key in _CACHE if key[0] == 'smallmaps.zip']
    for old in maps[:-4]:
        _CACHE.pop(old, None)
    while len(_CACHE) > 100:
        _CACHE.popitem(last=False)


def _item_entry(sid):
    if not hasattr(item_image, 'mapping'):
        from wlre.storage.bundled_database import load_bundled_json
        item_image.mapping = load_bundled_json('item_icon_map.json')['items']
    return item_image.mapping.get(str(sid), {}).get('icon', 's1000') + '.png'


def prefetch_item_icons(item_ids):
    """Decode one bounded UI batch with a single archive read.

    Always called from Kivy's UI thread; textures must not be created in a
    worker thread. Only uncached icons are decoded. The caller limits a batch
    to the currently visible slice so no full-inventory warmup occurs.
    """
    pending = []
    seen = set()
    for sid in item_ids:
        entry = _item_entry(sid)
        key = ('item_icons.zip', entry)
        if key not in _CACHE and entry not in seen:
            pending.append(entry)
            seen.add(entry)
    if not pending:
        return 0
    from wlre.storage.bundled_database import load_bundled_bytes
    with zipfile.ZipFile(io.BytesIO(load_bundled_bytes(
            'item_icons.zip', root=RESOURCE_ROOT))) as source:
        for entry in pending:
            try:
                raw = source.read(entry)
            except KeyError:
                raw = source.read('s1000.png')
            _CACHE['item_icons.zip', entry] = CoreImage(io.BytesIO(raw), ext='png')
    _trim_texture_cache()
    return len(pending)


def texture(archive, entry):
    key = archive, entry
    if key not in _CACHE:
        from wlre.storage.bundled_database import load_bundled_bytes
        with zipfile.ZipFile(io.BytesIO(load_bundled_bytes(archive, root=RESOURCE_ROOT))) as source:
            _CACHE[key] = CoreImage(io.BytesIO(source.read(entry)), ext='png')
    _CACHE.move_to_end(key)
    _trim_texture_cache()
    return _CACHE[key].texture


def item_image(sid, size=40):
    entry = _item_entry(sid)
    try: value = texture('item_icons.zip', entry)
    except (KeyError, OSError, ValueError): value = texture('item_icons.zip', 's1000.png')
    return Image(texture=value, size_hint=(None, None), size=(dp(size), dp(size)))


def emoji_entries():
    if not hasattr(emoji_entries, 'catalog'):
        from wlre.storage.bundled_database import load_bundled_json
        emoji_entries.catalog = load_bundled_json('emoji_catalog.json')['entries']
    return emoji_entries.catalog


def emoji_texture(index):
    data = emoji_entries().get(str(index))
    if not data or not data.get('available', True): return None
    try: return texture('emoji_images.zip', data['sprite']+'.png')
    except (KeyError, OSError, ValueError): return None


# Original function pictograms are from the user-provided 1262 game atlas.
GAME_ICONS = {
    '角色概況': 'MainIcon_041',
    '包包與特技': 'MainIcon_001',
    '組隊': 'MainIcon_005',
    '夥伴出戰': 'MainIcon_010',
    '遠征': 'MainIcon_038',
    '煉金': 'MainIcon_007',
    '製作': 'MainIcon_011',
    '經驗效率': 'MainIcon_020',
    'AI與補給設定': 'Btn_AI',
}


def function_icon(name, size=34):
    icon = GAME_ICONS.get(name)
    if not icon:
        return None
    path = RESOURCE_ROOT / 'assets' / 'function-icons' / (icon + '.png')
    if not path.is_file():
        return None
    return Image(source=str(path), size_hint=(None, None),
                 size=(dp(size), dp(size)))

