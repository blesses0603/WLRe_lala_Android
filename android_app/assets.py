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


_ITEM_SOURCE = None
_ITEM_WIDGETS = None
_ITEM_TIMER = None
_ITEM_WIDGET_SOURCE = None


def _item_entry(sid):
    from wlre.services.world.item_image_database import current_catalog
    catalog=current_catalog()
    return 's%04d.png'%(catalog.icon(sid) if catalog else 1000)


def item_texture(sid):
    global _ITEM_SOURCE
    from wlre.services.world.item_image_database import current_catalog, source_token
    token=source_token()
    if token!=_ITEM_SOURCE:
        for key in list(_CACHE):
            if key[0]=='official_items':_CACHE.pop(key,None)
        _ITEM_SOURCE=token
    catalog=current_catalog()
    if catalog is None:return None
    key=('official_items',catalog.icon(sid))
    try:
        if key not in _CACHE:
            raw=catalog.png(sid)
            if raw is None:return None
            _CACHE[key]=CoreImage(io.BytesIO(raw),ext='png',nocache=True)
        _CACHE.move_to_end(key);_trim_texture_cache()
        return _CACHE[key].texture
    except (KeyError,OSError,ValueError,TypeError):return None


def prefetch_item_icons(item_ids):
    before=set(_CACHE)
    for sid in dict.fromkeys(item_ids):item_texture(sid)
    return len(set(_CACHE)-before)


def _refresh_item_widgets(_dt):
    from wlre.services.world.item_image_database import source_token
    global _ITEM_WIDGET_SOURCE
    token=source_token()
    if token!=_ITEM_WIDGET_SOURCE and _ITEM_WIDGETS:
        for widget in tuple(_ITEM_WIDGETS):widget.texture=item_texture(widget.official_item_id)
        _ITEM_WIDGET_SOURCE=token


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
    global _ITEM_WIDGETS,_ITEM_TIMER
    from weakref import WeakSet
    from kivy.clock import Clock
    if _ITEM_WIDGETS is None:_ITEM_WIDGETS=WeakSet()
    widget=Image(texture=item_texture(sid),size_hint=(None,None),size=(dp(size),dp(size)))
    widget.official_item_id=sid;_ITEM_WIDGETS.add(widget)
    if _ITEM_TIMER is None:_ITEM_TIMER=Clock.schedule_interval(_refresh_item_widgets,1)
    return widget


def emoji_entries():
    from wlre.services.world.emoji_database import current_entries
    return current_entries()


_EMOJI_SOURCE = None


def emoji_texture(index):
    global _EMOJI_SOURCE
    from wlre.services.world.emoji_database import source_token, current_png
    token=source_token()
    if token!=_EMOJI_SOURCE:
        for key in list(_CACHE):
            if key[0]=='official_emoji':_CACHE.pop(key,None)
        _EMOJI_SOURCE=token
    key=('official_emoji',str(index))
    try:
        raw=current_png(str(index))
        if raw is None:return None
        if key not in _CACHE:_CACHE[key]=CoreImage(io.BytesIO(raw),ext='png',nocache=True)
        _CACHE.move_to_end(key);_trim_texture_cache()
        return _CACHE[key].texture
    except (KeyError,OSError,ValueError,TypeError):return None


def prefetch_emoji_textures(indices):
    results={}
    for index in dict.fromkeys(indices):
        value=emoji_texture(index)
        if value is not None:results[index]=value
    return results


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

