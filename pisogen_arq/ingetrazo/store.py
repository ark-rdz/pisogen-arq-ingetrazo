# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alfonso Rodríguez
"""Presets, the Material Center catalog and quantities (ports of main.rb).

The catalog is the SAME file the SketchUp version uses — Documents\\ARCHVIZ
Pisos Propio\\catalogo.json, or the one the user picked — read and written with
its rules, so a product saved in one program appears in the other. The
user's presets live in this computer's IngeTrazo data folder.
"""
import json
import math
import os
import shutil

from ..core.paving import PATTERNS
from . import fields

CATALOG_SCHEMA = 'archviz.catalogo/1'
CATALOG_LIMIT = 500
CATALOG_MEASURES = ('length_m', 'width_m', 'side_m', 'depth_m', 'joint_m', 'joint_end_m', 'chevron_angle_deg',
                    'length_variable', 'length_min_m', 'length_max_m', 'length_steps',
                    'wedge_long_m', 'wedge_short_m', 'wedge_height_m', 'wedge_inverse_m',
                    'iblock_length_m', 'iblock_width_m', 'iblock_web_m', 'diamond_angle_deg',
                    'grass_frame_m', 'grass_recess_m', 'reja_opening_m', 'reja_chamfer_m')
PRESET_LIMIT = 100
BUILTIN_PRESETS = {
    'Ejemplo · Duela 120×18': {'pattern': 'wood', 'length_m': 1.2, 'width_m': 0.18, 'joint_m': 0.003, 'joint_end_m': None, 'offset': 0.5},
    'Ejemplo · Porcelanato 60×60': {'pattern': 'tile', 'length_m': 0.6, 'width_m': 0.6, 'joint_m': 0.002, 'joint_end_m': None, 'offset': 0},
    'Ejemplo · Ladrillo 30×15': {'pattern': 'brick', 'length_m': 0.3, 'width_m': 0.15, 'joint_m': 0.01, 'joint_end_m': None, 'offset': 0.5},
}


class StoreError(ValueError):
    pass


def data_dir():
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    return os.path.join(base, 'ingetrazo', 'pisogen_arq')


def _read_json(path, default):
    try:
        with open(path, encoding='utf-8-sig') as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


def _write_json(path, data):
    """Keeps the previous file as .bak and replaces it only once the new one is fully written."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        shutil.copyfile(path, path + '.bak')
    temp = path + '.tmp'
    with open(temp, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(temp, path)


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

def _settings_path():
    return os.path.join(data_dir(), 'ajustes.json')


def _settings():
    data = _read_json(_settings_path(), {})
    return data if isinstance(data, dict) else {}


def _save_setting(key, value):
    data = _settings()
    if value is None:
        data.pop(key, None)
    else:
        data[key] = value
    _write_json(_settings_path(), data)


def user_presets():
    data = _read_json(os.path.join(data_dir(), 'presets.json'), {})
    return data if isinstance(data, dict) else {}


def save_preset(name, values):
    name = str(name).strip()
    if not 1 <= len(name) <= 60:
        raise StoreError('El nombre del preset debe tener entre 1 y 60 caracteres.')
    if name in BUILTIN_PRESETS:
        raise StoreError('Ese nombre es de un ejemplo; elige otro.')
    presets = user_presets()
    if len(presets) >= PRESET_LIMIT and name not in presets:
        raise StoreError(f'Se admiten hasta {PRESET_LIMIT} presets propios.')
    presets[name] = {k: v for k, v in values.items() if k not in fields.MATERIAL_KEYS and k != 'live_update'}
    _write_json(os.path.join(data_dir(), 'presets.json'), presets)


def delete_preset(name):
    presets = user_presets()
    if presets.pop(name, None) is None:
        raise StoreError('Ese preset no existe (los ejemplos no se eliminan).')
    _write_json(os.path.join(data_dir(), 'presets.json'), presets)


# ---------------------------------------------------------------------------
# Catalog (Material Center)
# ---------------------------------------------------------------------------

def documents_dir():
    """The user's real Documents folder (it may live in OneDrive)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders') as key:
            folder = winreg.QueryValueEx(key, 'Personal')[0]
            if folder and os.path.isdir(folder):
                return folder
    except (ImportError, OSError):   # no winreg outside Windows
        pass
    return os.path.join(os.path.expanduser('~'), 'Documents')


def default_catalog_path():
    return os.path.join(documents_dir(), 'ARCHVIZ Pisos Propio', 'catalogo.json')


def catalog_path():
    return _settings().get('catalog_path') or default_catalog_path()


def use_catalog(path):
    _save_setting('catalog_path', os.path.abspath(path) if path else None)


def catalog_demo():
    note = 'Ejemplo propio con datos inventados: edítalo o elimínalo.'
    return {'esquema': CATALOG_SCHEMA,
            '_ayuda': 'Catálogo de ARCHVIZ Pisos Propio. Medidas en metros. patron: wood Madera, brick Ladrillo, tile Loseta, '
                      'strip Cintilla, pinwheel Tweed, hopscotch_1 a hopscotch_4, herringbone Espiga, chevron Chevron, '
                      'basketweave Cestería, hexagon Hexágono, octagon Octágono, adopasto, adopasto_reja, irregular, wedge Cuña, '
                      'i_block Bloque I, diamonds Diamantes. cantidades: box_m2 m² por caja, box_pieces piezas por caja, '
                      'box_price precio por caja, adhesive_m2 m² por saco de adhesivo, grout_unit_m2 m² por bote de boquilla; '
                      '0 omite el dato. Al guardar desde el panel, un producto con la misma marca, colección y nombre se reemplaza.',
            'productos': [
                {'marca': 'Demostración', 'coleccion': 'Duelas', 'nombre': 'Roble 120 × 18 cm', 'demostracion': True, 'patron': 'wood',
                 'medidas': {'length_m': 1.2, 'width_m': 0.18, 'depth_m': 0.015, 'joint_m': 0.002},
                 'cantidades': {'box_m2': 1.944, 'box_pieces': 9, 'box_price': 0, 'adhesive_m2': 0, 'grout_unit_m2': 0}, 'notas': note},
                {'marca': 'Demostración', 'coleccion': 'Porcelanatos', 'nombre': 'Gris 60 × 60 cm', 'demostracion': True, 'patron': 'tile',
                 'medidas': {'length_m': 0.6, 'width_m': 0.6, 'depth_m': 0.01, 'joint_m': 0.002},
                 'cantidades': {'box_m2': 1.44, 'box_pieces': 4, 'box_price': 0, 'adhesive_m2': 4, 'grout_unit_m2': 10}, 'notas': note},
                {'marca': 'Demostración', 'coleccion': 'Adoquines', 'nombre': 'Bloque I 20 × 16.5 cm', 'demostracion': True, 'patron': 'i_block',
                 'medidas': {'iblock_length_m': 0.2, 'iblock_width_m': 0.165, 'iblock_web_m': 0.11, 'depth_m': 0.08, 'joint_m': 0.003},
                 'cantidades': {'box_m2': 0, 'box_pieces': 0, 'box_price': 0, 'adhesive_m2': 0, 'grout_unit_m2': 0}, 'notas': note},
            ]}


def identity(entry):
    return tuple(str(entry.get(k) or '').strip().lower() for k in ('marca', 'coleccion', 'nombre'))


def _number(value, low, high):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and low <= value <= high


def clean_product(item):
    """A product with an unknown key or an out-of-range value is skipped as a
    whole, so a typo in the file is reported instead of silently ignored."""
    if not isinstance(item, dict):
        return None
    texts = {}
    for key, top in (('marca', 60), ('coleccion', 60), ('nombre', 60), ('codigo', 60), ('acabado', 60), ('notas', 300)):
        value = '' if item.get(key) is None else item.get(key)
        if not isinstance(value, str) or len(value.strip()) > top:
            return None
        texts[key] = value.strip()
    if not texts['nombre'] or item.get('patron') not in PATTERNS:
        return None
    measures, quantities = item.get('medidas', {}), item.get('cantidades', {})
    if not isinstance(measures, dict) or not isinstance(quantities, dict):
        return None
    for key, value in measures.items():
        if key == 'length_variable':
            valid = value in (True, False)
        elif key == 'length_steps':
            valid = isinstance(value, int) and not isinstance(value, bool) and 2 <= value <= 10
        elif key == 'joint_end_m':
            valid = value is None or _number(value, 0, 1)
        elif key == 'chevron_angle_deg':
            valid = _number(value, 15, 75)
        elif key == 'diamond_angle_deg':
            valid = _number(value, 30, 90)
        else:
            valid = key in CATALOG_MEASURES and _number(value, 0, 100)
        if not valid:
            return None
    for key, value in quantities.items():
        if key not in fields.QUANTITY_KEYS or not _number(value, 0, 1000000):
            return None
    product = dict(texts, patron=item['patron'], medidas=measures, cantidades=quantities)
    if item.get('demostracion') is True:
        product['demostracion'] = True
    return product


def _read_catalog(path):
    try:
        with open(path, encoding='utf-8-sig') as handle:
            data = json.load(handle)
    except ValueError as error:
        raise StoreError(f'El archivo no es JSON válido ({str(error)[:80]}).') from None
    if not isinstance(data, dict) or not isinstance(data.get('productos'), list):
        raise StoreError('El catálogo debe tener la lista «productos».')
    return data


def catalog():
    """Reads the catalog (creating this computer's file with examples the
    first time). Never raises: an unreadable file is reported in 'error'."""
    path = catalog_path()
    custom = path != default_catalog_path()
    try:
        if not os.path.exists(path):
            if custom:
                raise StoreError('No se encontró el archivo elegido. Elige otro o vuelve al de este equipo.')
            _write_json(path, catalog_demo())
        data = _read_catalog(path)
        products, skipped = [], 0
        for item in data['productos']:
            product = clean_product(item) if len(products) < CATALOG_LIMIT else None
            if product:
                products.append(product)
            else:
                skipped += 1
        return {'path': path, 'custom': custom, 'products': products, 'skipped': skipped, 'error': None}
    except (OSError, StoreError) as error:
        return {'path': path, 'custom': custom, 'products': [], 'skipped': 0, 'error': str(error)}


def save_product(product):
    """Adds the product, or replaces the one with the same brand, collection
    and name; entries written by hand and their order survive."""
    info = catalog()
    if info['error']:
        raise StoreError('Corrige el archivo del catálogo antes de guardar: ' + info['error'])
    clean = clean_product(product)
    if not clean:
        raise StoreError('Producto inválido: revisa el nombre (hasta 60 caracteres) y las medidas.')
    data = _read_catalog(info['path'])
    entries = data['productos']
    index = next((i for i, e in enumerate(entries) if isinstance(e, dict) and identity(e) == identity(clean)), None)
    if index is None and len(entries) >= CATALOG_LIMIT:
        raise StoreError(f'Se admiten hasta {CATALOG_LIMIT} productos.')
    clean.pop('demostracion', None)
    if index is None:
        entries.append(clean)
    else:
        entries[index] = clean
    _write_json(info['path'], data)
    return index is not None


def delete_product(product):
    info = catalog()
    if info['error']:
        raise StoreError('Corrige el archivo del catálogo antes de eliminar: ' + info['error'])
    data = _read_catalog(info['path'])
    before = len(data['productos'])
    data['productos'] = [e for e in data['productos'] if not (isinstance(e, dict) and identity(e) == identity(product))]
    if len(data['productos']) == before:
        raise StoreError('Ese producto ya no está en el catálogo.')
    _write_json(info['path'], data)


def search_url(product):
    from urllib.parse import quote_plus
    query = ' '.join(str(product.get(k) or '').strip() for k in ('marca', 'coleccion', 'nombre', 'codigo')).split()
    if not query:
        raise StoreError('Escribe o elige un producto para buscarlo.')
    text = ' '.join(query)
    return text, 'https://www.google.com/search?q=' + quote_plus(text)


def product_label(product):
    label = ' · '.join(p for p in (product.get('marca'), product.get('coleccion'), product.get('nombre')) if p)
    if product.get('codigo'):
        label += f" ({product['codigo']})"
    if product.get('demostracion'):
        label += ' (demostración)'
    return label


# ---------------------------------------------------------------------------
# Quantities (main.rb quantities / quantities_text)
# ---------------------------------------------------------------------------

def _area(polygon):
    return sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(polygon, polygon[1:] + polygon[:1])) / 2


def quantities(pieces, settings, net_area):
    """Whole pieces keep their nominal area; anything smaller was cut by the
    face outline or a hole. Boxes cover the face minus insert pieces."""
    roles = {}
    for piece in pieces:
        area = sum(abs(_area(poly)) for poly in piece['polygons_m'])
        nominal = piece.get('nominal_area_m2')
        whole = isinstance(nominal, (int, float)) and area >= nominal * (1 - 1e-6)
        entry = roles.setdefault(piece['role'], {'whole': 0, 'cut': 0, 'area_m2': 0.0})
        entry['whole' if whole else 'cut'] += 1
        entry['area_m2'] += area
    waste = 0.0 if settings.get('waste_enabled') is False else (settings.get('waste_pct') or 0) / 100.0
    main = roles.get('main', {'whole': 0, 'cut': 0, 'area_m2': 0.0})
    main_face = net_area - (roles['insert']['area_m2'] if 'insert' in roles else 0)
    with_waste = main_face * (1 + waste)

    def units(amount, per):
        return math.ceil(amount / per - 1e-9) if per and per > 0 else None

    box_m2, box_pieces = settings.get('box_m2') or 0, settings.get('box_pieces') or 0
    boxes = units(with_waste, box_m2) if box_m2 > 0 else units((main['whole'] + main['cut']) * (1 + waste), box_pieces)
    price = settings.get('box_price') or 0
    return {'roles': roles, 'net_area_m2': net_area, 'main_face_m2': main_face, 'waste_pct': settings.get('waste_pct') or 0,
            'waste_enabled': settings.get('waste_enabled') is not False, 'with_waste_m2': with_waste, 'boxes': boxes,
            'adhesive_units': units(net_area, settings.get('adhesive_m2') or 0),
            'grout_units': units(net_area, settings.get('grout_unit_m2') or 0),
            'cost': boxes * price if boxes and price > 0 else None}


def quantities_text(totals):
    main = totals['roles'].get('main', {'whole': 0, 'cut': 0})
    parts = [f"{main['whole'] + main['cut']} piezas ({main['whole']} enteras, {main['cut']} recortadas)"]
    insert = totals['roles'].get('insert')
    if insert:
        parts.append(f"{insert['whole'] + insert['cut']} insertos ({insert['whole']} enteros, {insert['cut']} recortados)")
    parts.append(f"área neta {totals['net_area_m2']:.3f} m²")
    if totals.get('waste_enabled', True):
        parts.append(f"con {totals['waste_pct']:g} % de desperdicio {totals['with_waste_m2']:.3f} m²")
    if totals['boxes']:
        parts.append(f"{totals['boxes']} cajas")
    if totals['adhesive_units']:
        parts.append(f"{totals['adhesive_units']} de adhesivo")
    if totals['grout_units']:
        parts.append(f"{totals['grout_units']} de boquilla")
    if totals['cost']:
        parts.append(f"costo {totals['cost']:.2f}")
    return ' · '.join(parts)
