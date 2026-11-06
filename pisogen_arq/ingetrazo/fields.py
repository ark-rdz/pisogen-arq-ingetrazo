# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alfonso Rodríguez
"""The PisoGen ARQ parameters, as the SketchUp panel offers them.

Each field: (key, label, kind, default, section, visible(values)). Keys and
defaults are main.rb's DEFAULTS, so presets and catalog products move
between both programs. Kinds: 'len' (metres, shown in the model's units),
'len?' (empty allowed), 'num', 'int', 'pct' (0–1 stored, % shown), 'bool',
or a tuple of choices.
"""
BOARDS = ('wood', 'brick', 'tile', 'strip', 'herringbone', 'chevron')
ROWS = ('wood', 'brick', 'tile', 'strip')
STAGGERED = ('wood', 'brick', 'strip')
SIDES = ('pinwheel', 'hopscotch_1', 'hopscotch_2', 'hopscotch_3', 'hopscotch_4', 'basketweave', 'hexagon', 'octagon',
         'adopasto', 'adopasto_reja', 'irregular', 'diamonds')
WITH_INSERTS = ('pinwheel', 'hopscotch_1', 'hopscotch_2', 'hopscotch_3', 'hopscotch_4', 'octagon', 'wedge', 'diamonds',
                'adopasto', 'adopasto_reja')
GRASS = ('adopasto', 'adopasto_reja')
# Bevels on these patterns belong in the render material (main.rb NO_BEVEL_PATTERNS).
NO_BEVEL = ('hexagon', 'octagon', 'adopasto', 'adopasto_reja', 'irregular', 'wedge', 'i_block', 'diamonds')

SECTIONS = ('Medidas', 'Colocación', 'Bisel superior', 'Materiales y UV', 'Relleno de juntas', 'Cuantificación')


def _in(*patterns):
    return lambda v: v.get('pattern') in patterns


def _always(_v):
    return True


FIELDS = [
    # Medidas
    ('length_m', 'Largo', 'len', 1.2, 'Medidas', _in(*BOARDS)),
    ('width_m', 'Ancho', 'len', 0.18, 'Medidas', _in(*BOARDS)),
    ('side_m', 'Lado del módulo / polígono', 'len', 0.3, 'Medidas', _in(*SIDES)),
    ('joint_m', 'Junta', 'len', 0.003, 'Medidas', _always),
    ('joint_end_m', 'Junta de testa (vacía = igual a Junta)', 'len?', None, 'Medidas', _in(*ROWS)),
    ('depth_m', 'Espesor', 'len', 0.02, 'Medidas', _always),
    ('lift_max_m', 'Desnivel máximo entre piezas', 'len', 0.0, 'Medidas', _always),
    ('offset', 'Desfase (%)', 'pct', 0.5, 'Medidas', _in(*STAGGERED)),
    ('length_variable', 'Largos variables', 'bool', False, 'Medidas', _in(*STAGGERED)),
    ('length_min_m', 'Largo mínimo', 'len', 0.6, 'Medidas', lambda v: v.get('pattern') in STAGGERED and v.get('length_variable')),
    ('length_max_m', 'Largo máximo', 'len', 1.8, 'Medidas', lambda v: v.get('pattern') in STAGGERED and v.get('length_variable')),
    ('length_steps', 'Número de largos', 'int', 5, 'Medidas', lambda v: v.get('pattern') in STAGGERED and v.get('length_variable')),
    ('min_cut_m', 'Recorte mínimo junto a bordes y huecos', 'len', 0.0, 'Medidas', _in(*STAGGERED)),
    ('chevron_angle_deg', 'Ángulo de Chevron (15–75°)', 'num', 45, 'Medidas', _in('chevron')),
    ('diamond_angle_deg', 'Ángulo del rombo (30–90°)', 'num', 90, 'Medidas', _in('diamonds')),
    ('wedge_long_m', 'Base mayor', 'len', 0.2, 'Medidas', _in('wedge')),
    ('wedge_short_m', 'Base menor', 'len', 0.1, 'Medidas', _in('wedge')),
    ('wedge_height_m', 'Alto de la fila', 'len', 0.15, 'Medidas', _in('wedge')),
    ('wedge_inverse_m', 'Base menor de la pieza invertida (0 = triángulo)', 'len', 0.0, 'Medidas', _in('wedge')),
    ('iblock_length_m', 'Largo total', 'len', 0.2, 'Medidas', _in('i_block')),
    ('iblock_width_m', 'Ancho de las alas', 'len', 0.165, 'Medidas', _in('i_block')),
    ('iblock_web_m', 'Ancho del alma', 'len', 0.11, 'Medidas', _in('i_block')),
    ('grass_frame_m', 'Ancho del marco de concreto (por lado)', 'len', 0.03, 'Medidas', _in('adopasto')),
    ('reja_opening_m', 'Lado de cada celda de pasto', 'len', 0.085, 'Medidas', _in('adopasto_reja')),
    ('reja_chamfer_m', 'Recorte de esquinas del contorno', 'len', 0.015, 'Medidas', _in('adopasto_reja')),
    ('grass_recess_m', 'Hundimiento del pasto', 'len', 0.01, 'Medidas', _in(*GRASS)),
    ('irregular_style', 'Tipo de composición', ('stone', 'grid'), 'grid', 'Medidas', _in('irregular')),
    ('irregularity_pct', 'Irregularidad (%)', 'num', 70, 'Medidas', _in('irregular')),
    ('layout_seed', 'Semilla de composición', 'int', 1, 'Medidas',
     lambda v: v.get('pattern') == 'irregular' or (v.get('pattern') in STAGGERED and v.get('length_variable'))),
    # Colocación
    ('pattern_angle_deg', 'Ángulo del patrón (°)', 'num', 0, 'Colocación', _always),
    ('align_mode', 'Alinear con', ('first_edge', 'longest_edge'), 'first_edge', 'Colocación', _always),
    ('origin_mode', 'Origen', ('first_vertex', 'centroid', 'corner_bl', 'corner_br', 'corner_tl', 'corner_tr'),
     'first_vertex', 'Colocación', _always),
    ('origin_anchor', 'En el origen cae', ('corner', 'center'), 'corner', 'Colocación', _always),
    ('offset_x_m', 'Desplazamiento X', 'len', 0.0, 'Colocación', _always),
    ('offset_y_m', 'Desplazamiento Y', 'len', 0.0, 'Colocación', _always),
    ('base_level', 'Nivel del piso', ('flush', 'on_face'), 'flush', 'Colocación', _always),
    # Bisel superior
    ('bevel_enabled', 'Activar bisel superior', 'bool', False, 'Bisel superior', _always),
    ('bevel_height_m', 'Altura', 'len', 0.002, 'Bisel superior', lambda v: v.get('bevel_enabled')),
    ('bevel_lock', 'Igualar ancho y altura (recto a 45°)', 'bool', True, 'Bisel superior', lambda v: v.get('bevel_enabled')),
    ('bevel_width_m', 'Ancho del bisel', 'len', 0.002, 'Bisel superior',
     lambda v: v.get('bevel_enabled') and not v.get('bevel_lock')),
    ('bevel_profile', 'Perfil', ('straight', 'curved'), 'straight', 'Bisel superior', lambda v: v.get('bevel_enabled')),
    ('bevel_segments', 'Segmentos de curva (2–6)', 'int', 3, 'Bisel superior',
     lambda v: v.get('bevel_enabled') and v.get('bevel_profile') == 'curved'),
    # Materiales y UV (the material lists are widgets of their own)
    ('material_assignment', 'Asignación', ('random', 'sequence'), 'random', 'Materiales y UV', _always),
    ('texture_mode', 'Modo de textura', ('piece', 'continuous'), 'piece', 'Materiales y UV', _always),
    ('texture_fit', 'Escala de textura', ('length', 'width', 'manual'), 'length', 'Materiales y UV',
     lambda v: v.get('texture_mode') != 'continuous'),
    ('texture_width_m', 'Ancho real de la imagen', 'len', 0.5, 'Materiales y UV',
     lambda v: v.get('texture_fit') == 'manual' or v.get('texture_mode') == 'continuous'),
    ('texture_rotation_deg', 'Dirección de la veta en la imagen', (0, 90, 180, 270), 0, 'Materiales y UV', _always),
    ('texture_flip_u', 'Espejo aleatorio a lo largo (U)', 'bool', False, 'Materiales y UV', lambda v: v.get('texture_mode') != 'continuous'),
    ('texture_flip_v', 'Espejo aleatorio a lo ancho (V)', 'bool', False, 'Materiales y UV', lambda v: v.get('texture_mode') != 'continuous'),
    ('texture_random', 'Desplazamiento aleatorio a lo largo (U) e inversión', 'bool', False, 'Materiales y UV',
     lambda v: v.get('texture_mode') != 'continuous'),
    ('texture_random_v', 'Desplazamiento aleatorio a lo ancho (V)', 'bool', False, 'Materiales y UV',
     lambda v: v.get('texture_mode') != 'continuous'),
    ('texture_random_rotation', 'Rotación UV aleatoria', ('none', 'half', 'quarter'), 'none', 'Materiales y UV',
     lambda v: v.get('texture_mode') != 'continuous'),
    ('texture_offset_u_m', 'Desplazamiento UV a lo largo', 'len', 0.0, 'Materiales y UV', _always),
    ('texture_offset_v_m', 'Desplazamiento UV a lo ancho', 'len', 0.0, 'Materiales y UV', _always),
    ('material_seed', 'Semilla de mezcla', 'int', 1, 'Materiales y UV', _always),
    ('material_randomness_pct', 'Random de materiales (%)', 'num', 100, 'Materiales y UV',
     lambda v: v.get('material_assignment') == 'random'),
    ('material_avoid_repeat', 'No repetir material en piezas vecinas', 'bool', False, 'Materiales y UV',
     lambda v: v.get('material_assignment') == 'random'),
    ('insert_enabled', 'Material diferente para insertos', 'bool', False, 'Materiales y UV', _in(*WITH_INSERTS)),
    # Relleno de juntas
    ('grout_enabled', 'Rellenar juntas con material independiente', 'bool', False, 'Relleno de juntas', _always),
    ('grout_recess_m', 'Hundimiento respecto de la superficie (mín. 0.5 mm)', 'len', 0.002, 'Relleno de juntas',
     lambda v: v.get('grout_enabled')),
    # Cuantificación
    ('waste_enabled', 'Incluir desperdicio', 'bool', True, 'Cuantificación', _always),
    ('waste_pct', 'Desperdicio (%)', 'num', 10, 'Cuantificación', lambda v: v.get('waste_enabled')),
    ('box_m2', 'm² por caja', 'num', 0, 'Cuantificación', _always),
    ('box_pieces', 'Piezas por caja', 'int', 0, 'Cuantificación', _always),
    ('box_price', 'Precio por caja', 'num', 0, 'Cuantificación', _always),
    ('adhesive_m2', 'Adhesivo: m² por saco', 'num', 0, 'Cuantificación', _always),
    ('grout_unit_m2', 'Boquilla: m² por bolsa', 'num', 0, 'Cuantificación', _always),
]

CHOICE_LABELS = {
    'grid': 'Retícula deformada', 'stone': 'Piedra irregular',
    'first_edge': 'Primer borde de la cara', 'longest_edge': 'Borde más largo',
    'first_vertex': 'Primer vértice de la cara', 'centroid': 'Centro de masa de la cara',
    'corner_bl': 'Esquina inferior izquierda', 'corner_br': 'Esquina inferior derecha',
    'corner_tl': 'Esquina superior izquierda', 'corner_tr': 'Esquina superior derecha',
    'corner': 'Esquina de pieza', 'center': 'Centro de pieza',
    'on_face': 'Sobre la cara (sube el espesor)', 'flush': 'Al nivel de la cara (la losa baja el espesor)',
    'straight': 'Recto', 'curved': 'Curvo · redondeado',
    'random': 'Materiales aleatorios', 'sequence': 'En secuencia',
    'piece': 'Por pieza', 'continuous': 'Continua en todo el piso',
    'length': 'Ajustar al largo', 'width': 'Ajustar al ancho de la tabla', 'manual': 'Tamaño real de la imagen',
    0: 'Horizontal → largo de la pieza', 90: 'Vertical → largo de la pieza',
    180: 'Horizontal invertida (180°)', 270: 'Vertical invertida (270°)',
    'none': 'No', 'half': '0° / 180°', 'quarter': '0° / 90° / 180° / 270° (losetas)',
}

# A new composition starts from these measures (the SketchUp panel's choices).
PATTERN_STARTS = {
    'irregular': {'irregular_style': 'stone', 'side_m': 0.30, 'irregularity_pct': 100, 'layout_seed': 1, 'depth_m': 0.02},
    'basketweave': {'side_m': 0.30}, 'hexagon': {'side_m': 0.15}, 'octagon': {'side_m': 0.12}, 'diamonds': {'side_m': 0.20},
    'pinwheel': {'side_m': 0.30}, 'hopscotch_1': {'side_m': 0.30}, 'hopscotch_2': {'side_m': 0.30},
    'hopscotch_3': {'side_m': 0.30}, 'hopscotch_4': {'side_m': 0.30},
    'adopasto_reja': {'side_m': 0.465, 'reja_opening_m': 0.085, 'reja_chamfer_m': 0.015, 'grass_recess_m': 0.01,
                      'depth_m': 0.08, 'insert_enabled': True},
    'adopasto': {'side_m': 0.20, 'grass_frame_m': 0.03, 'grass_recess_m': 0.01, 'depth_m': 0.08, 'insert_enabled': True},
    'strip': {'length_m': 0.30, 'width_m': 0.05, 'offset': 0.5, 'length_min_m': 0.15, 'length_max_m': 0.45},
    'tile': {'length_m': 0.30, 'width_m': 0.30, 'offset': 0},
    'brick': {'length_m': 0.30, 'width_m': 0.15, 'offset': 0.5, 'length_min_m': 0.20, 'length_max_m': 0.30},
    'wood': {'length_m': 1.2, 'width_m': 0.18, 'offset': 0.5, 'length_min_m': 0.6, 'length_max_m': 1.8},
    'herringbone': {'length_m': 0.60, 'width_m': 0.10}, 'chevron': {'length_m': 0.60, 'width_m': 0.10},
}

# Presets and products never carry materials (they depend on each model).
MATERIAL_KEYS = ('main_materials', 'insert_material', 'grout_material')


def defaults():
    values = {key: default for key, _label, _kind, default, _section, _show in FIELDS}
    values.update(pattern='wood', main_materials=[], insert_material='', grout_material='', live_update=False)
    return values


def core_settings(values):
    """Panel values → the settings the core and the builder read."""
    settings = {k: v for k, v in values.items() if v is not None and k not in ('live_update',)}
    pattern = settings.get('pattern')
    if pattern in NO_BEVEL:
        settings['bevel_enabled'] = False
    if settings.get('bevel_lock'):
        settings['bevel_width_m'] = settings.get('bevel_height_m', 0.002)
    if pattern not in STAGGERED:
        settings.pop('min_cut_m', None)
        settings['length_variable'] = False
    if not settings.get('length_variable'):
        for key in ('length_min_m', 'length_max_m', 'length_steps'):
            settings.pop(key, None)
    if pattern in GRASS:
        settings['insert_enabled'] = True
    return settings


def product_keys(pattern):
    """Measures a catalog product keeps for its composition (panel.js productKeys)."""
    common = ['depth_m', 'joint_m']
    if pattern in ROWS:
        return ['length_m', 'width_m', 'joint_end_m', 'length_variable', 'length_min_m', 'length_max_m', 'length_steps'] + common
    if pattern == 'herringbone':
        return ['length_m', 'width_m'] + common
    if pattern == 'chevron':
        return ['length_m', 'width_m', 'chevron_angle_deg'] + common
    if pattern == 'wedge':
        return ['wedge_long_m', 'wedge_short_m', 'wedge_height_m', 'wedge_inverse_m'] + common
    if pattern == 'i_block':
        return ['iblock_length_m', 'iblock_width_m', 'iblock_web_m'] + common
    if pattern == 'diamonds':
        return ['side_m', 'diamond_angle_deg'] + common
    if pattern == 'adopasto':
        return ['side_m', 'grass_frame_m', 'grass_recess_m'] + common
    if pattern == 'adopasto_reja':
        return ['side_m', 'reja_opening_m', 'reja_chamfer_m', 'grass_recess_m'] + common
    return ['side_m'] + common


QUANTITY_KEYS = ('box_m2', 'box_pieces', 'box_price', 'adhesive_m2', 'grout_unit_m2')

GROUT_CLEARANCE_M = 0.0002
_LABELS = {key: label.split(' (')[0] for key, label, *_rest in FIELDS}

# (keys, lowest, highest, range as the message says it): main.rb read_settings.
_RANGES = (
    (('length_m', 'width_m', 'side_m', 'depth_m', 'length_min_m', 'length_max_m', 'texture_width_m', 'wedge_long_m',
      'wedge_height_m', 'iblock_length_m', 'iblock_width_m', 'iblock_web_m'), 0.001, 100, 'entre 1 mm y 100 m'),
    (('wedge_short_m', 'wedge_inverse_m', 'grass_frame_m', 'grass_recess_m', 'reja_opening_m', 'reja_chamfer_m',
      'grout_recess_m'), 0, 100, 'entre 0 y 100 m'),
    (('offset_x_m', 'offset_y_m', 'texture_offset_u_m', 'texture_offset_v_m'), -100, 100, 'entre −100 y 100 m'),
    (('joint_m', 'min_cut_m'), 0, 1, 'entre 0 y 1 m'),
    (('offset',), 0, 1, 'entre 0 y 100 %'),
    (('lift_max_m',), 0, 0.01, 'entre 0 y 10 mm'),
    (('bevel_height_m', 'bevel_width_m'), 0.0001, 1, 'entre 0.1 mm y 1 m'),
    (QUANTITY_KEYS, 0, 1000000, 'entre 0 y 1 000 000'),
    (('waste_pct', 'irregularity_pct', 'material_randomness_pct'), 0, 100, 'entre 0 y 100'),
    (('pattern_angle_deg',), -360, 360, 'entre −360 y 360°'),
    (('chevron_angle_deg',), 15, 75, 'entre 15 y 75°'),
    (('diamond_angle_deg',), 30, 90, 'entre 30 y 90°'),
)
_INTEGERS = (('length_steps', 2, 10), ('bevel_segments', 2, 6),
             ('layout_seed', -2147483647, 2147483647), ('material_seed', -2147483647, 2147483647))


def _number(value):
    # A boolean is an int to Python; nan fails every comparison but not this one.
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and abs(value) != float('inf')


def check(settings):
    """The limits main.rb read_settings enforces. Raises ValueError with the
    message for the user; measures of other compositions are checked too,
    as there, since a preset or an edited floor can bring them."""
    values = dict(defaults(), **settings)
    for keys, low, high, text in _RANGES:
        for key in keys:
            if not _number(values[key]) or not low <= values[key] <= high:
                raise ValueError(f'«{_LABELS[key]}» debe estar {text}.')
    end_joint = values['joint_end_m']
    if end_joint is not None and (not _number(end_joint) or not 0 <= end_joint <= 1):
        raise ValueError(f'«{_LABELS["joint_end_m"]}» debe estar entre 0 y 1 m.')
    for key, low, high in _INTEGERS:
        if not isinstance(values[key], int) or isinstance(values[key], bool) or not low <= values[key] <= high:
            raise ValueError(f'«{_LABELS[key]}» debe ser un número entero entre {low} y {high}.')
    if values['base_level'] not in ('on_face', 'flush'):
        raise ValueError('Nivel del piso inválido.')
    pattern = values['pattern']
    depth, recess = values['depth_m'], values['grout_recess_m']
    if pattern == 'adopasto':
        opening = values['side_m'] - values['joint_m'] - 2 * values['grass_frame_m']
        if values['grass_frame_m'] < 0.001 or opening < 0.001 or depth - values['grass_recess_m'] < 0.001:
            raise ValueError('Adopasto requiere marco, celda y altura de pasto de al menos 1 mm.')
    if pattern == 'adopasto_reja':
        width = (values['side_m'] + values['joint_m']) / 3.0 - values['joint_m']
        opening = values['reja_opening_m']
        if (opening < 0.001 or width - opening < 0.002 or depth - values['grass_recess_m'] < 0.001
                or values['reja_chamfer_m'] > (width - opening) / 2.0 - 0.001):
            raise ValueError('Medidas incompatibles en Adopasto Reja: revisa celdas, nervios, recortes y hundimiento.')
    if values['grout_enabled']:
        if recess < 0.0005 - 1e-9 or depth - recess - GROUT_CLEARANCE_M < 0.001:
            raise ValueError('El hundimiento del relleno debe ser de al menos 0.5 mm y dejar 1 mm de relleno dentro del espesor.')
        if pattern in GRASS and recess < values['grass_recess_m'] - 1e-9:
            raise ValueError('En Adopasto el hundimiento del relleno debe ser al menos igual al hundimiento del pasto.')
    if values['length_variable'] and pattern in STAGGERED and values['length_max_m'] < values['length_min_m'] + 0.001:
        raise ValueError('El largo máximo debe superar al mínimo en al menos 1 mm.')
    if pattern in ('herringbone', 'chevron') and values['length_m'] <= values['width_m']:
        raise ValueError('El largo de la pieza debe ser mayor que el ancho.')
    if values['bevel_enabled'] and pattern not in NO_BEVEL and values['bevel_height_m'] >= depth:
        raise ValueError('La altura del bisel debe ser menor que el espesor de la pieza.')
