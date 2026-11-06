# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alfonso Rodríguez
"""PisoGen ARQ in IngeTrazo: a side panel (Ventana ▸ Paneles, or
Extensions ▸ PisoGen ARQ ▸ Panel) and the same commands in the Extensions
menu and the viewport's right-click menu.

Select a face and press «Crear en la cara seleccionada»: the floor is laid
on the face as one container group of component pieces (one undo step).
Select a floor and «Editar seleccionado» loads it into the panel;
«Reconstruir» lays it again with the new parameters where it stands.
"""
import copy
import logging
import re

from . import build, fields

log = logging.getLogger('ingetrazo.plugins.pisogen_arq')
TITLE = 'PisoGen ARQ'
LIBRARY_PREFIX = 'Biblioteca · '
PANEL_NAME = 'panel'
CONFIRM_PIECES = 20000

# Core messages in Spanish (panel.js coreMessages).
CORE_MESSAGES = [
    (r'^Clipping work limit exceeded|^Perimeter work limit exceeded',
     'El cálculo supera el límite de trabajo: divide la cara base o usa piezas más grandes.'),
    (r'^Joint eliminates', 'La junta elimina una pieza: reduce la junta o aumenta las medidas.'),
    (r'^Clipping boundary must be convex|^Invalid domain triangulation|^Domain cell',
     'La cara base no se pudo interpretar; simplifica su contorno.'),
    (r'^Overlapping piece fragments|^Touching perimeter branches|^Open piece perimeter|^Degenerate perimeter|'
     r'^Empty perimeter|^Invalid perimeter cycle',
     'Una pieza recortada tiene un contorno que no admite bisel; prueba sin bisel o mueve la cara base.'),
    (r'^Unsupported pattern', 'Patrón no disponible en esta versión.'),
    (r'^Piece limit exceeded|^Candidate limit exceeded',
     'El piso supera el límite de piezas de esta composición; divide la cara base o usa piezas más grandes.'),
    (r'^Invalid |^Degenerate polygon', 'Medidas o configuración inválidas para este patrón.'),
]


def explain(text):
    text = str(text)
    for pattern, spanish in CORE_MESSAGES:
        if re.search(pattern, text):
            return spanish
    return text


def validate(settings):
    try:
        fields.check(settings)
    except ValueError as error:
        raise build.FloorError(str(error)) from None


# ---------------------------------------------------------------------------
# IngeTrazo's material library: listed in the dialog, added to the document
# only when a floor uses it.
# ---------------------------------------------------------------------------

def library_materials():
    """{name: (image path, sw, sh)} from IngeTrazo's bundled texture library."""
    import json
    import os
    import core.materials
    root = os.path.join(os.path.dirname(os.path.dirname(core.materials.__file__)), 'resources', 'textures')
    try:
        with open(os.path.join(root, 'library.json'), encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    result = {}
    for category in data.get('categories', []):
        for item in category.get('items', []):
            path = os.path.join(root, 'library', *item['file'].split('/'))
            if os.path.exists(path):
                name = f"{LIBRARY_PREFIX}{category.get('id', '')} · {item.get('name', item['file'])}"
                result[name] = (path, float(item.get('sw') or 1.0), float(item.get('sh') or 1.0))
    return result


def ensure_library(scene, names):
    """Adds the library materials named in ``names`` to the document."""
    from core.materials import Material
    library = None
    for name in names:
        if name and name.startswith(LIBRARY_PREFIX) and name not in scene.materials:
            library = library if library is not None else library_materials()
            if name in library:
                path, sw, sh = library[name]
                scene.materials[name] = Material(name, color=(1, 1, 1), texture={'path': path, 'sw': sw, 'sh': sh})


def _material_names(settings):
    return list(settings.get('main_materials') or []) + [settings.get('insert_material'), settings.get('grout_material')]


# ---------------------------------------------------------------------------
# One undo step (the Windowizer pattern): loose mesh, groups, parts, data and
# the material registry are captured before and after, and so is the mesh of
# a group whose slab the floor lowers.
# ---------------------------------------------------------------------------

def _command_class():
    from core.history import Command

    class FloorCommand(Command):
        def __init__(self, mutate, meshes=()):
            self.mutate = mutate
            self.meshes = [m for m in meshes if m is not None]
            self.before = self.after = None

        def _capture(self, scene):
            return {
                'extra': [(m, m.capture_state()) for m in self.meshes if m is not scene.mesh],
                'mesh': scene.mesh.capture_state(),
                'groups': list(scene.groups),
                'state': [(g, list(g.children or ()), copy.deepcopy(getattr(g, 'ext', None)), g.xform, g.name)
                          for g in scene.groups],
                'mats': dict(scene.materials),
            }

        @staticmethod
        def _restore(scene, s):
            scene.mesh.restore_state(s['mesh'])
            for mesh, state in s['extra']:
                mesh.restore_state(state)
            scene.groups[:] = s['groups']
            for g, kids, ext, xform, name in s['state']:
                g.children, g.xform, g.name = list(kids), xform, name
                g.ext = copy.deepcopy(ext)
            scene.materials.clear()
            scene.materials.update(s['mats'])
            scene.selection.intersection_update(set(scene.mesh.faces) | set(scene.mesh.edges) | set(scene.groups))

        def do(self, scene):
            if self.after is None:
                self.before = self._capture(scene)
                try:
                    self.mutate(scene)
                except BaseException:
                    self._restore(scene, self.before)
                    raise
                self.after = self._capture(scene)
            else:
                self._restore(scene, self.after)
            scene.version += 1

        def undo(self, scene):
            self._restore(scene, self.before)
            scene.version += 1

    return FloorCommand


def _run(viewport, mutate, meshes=()):
    hist = viewport.history
    hist.execute(_command_class()(mutate, meshes))
    if hist.last_error:
        _warn(viewport, explain(hist.last_error.split(': ', 1)[-1]))
        return False
    notify = getattr(viewport, 'notify_scene_changed', None)
    if callable(notify):
        notify()
    viewport.update()
    return True


def _warn(viewport, text):
    from PySide6.QtWidgets import QMessageBox
    try:
        viewport.flash_status(TITLE + ': ' + text.splitlines()[0], 6000)
    except Exception:  # noqa: BLE001
        pass
    QMessageBox.warning(viewport.window(), TITLE, text)


def _status(viewport, text):
    try:
        viewport.flash_status(text, 6000)
    except Exception:  # noqa: BLE001
        log.info(text)


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def selected_faces(scene):
    from core.mesh import Face
    return [e for e in scene.selection if isinstance(e, Face) and e in scene.mesh.faces]


def selected_floors(scene):
    out = []
    for e in scene.selection:
        g = getattr(e, 'owner', None) or e
        if g in scene.groups and build.floor_data(g) is not None and g not in out:
            out.append(g)
    return out


def _inside_floor(scene):
    """Whether the open group is a PisoGen ARQ floor or one of its pieces."""
    group = getattr(scene, 'edit_group', None)
    while group is not None:
        if build.floor_data(group) is not None:
            return True
        group = getattr(group, 'owner', None)
    return False


def _at_top_level(viewport):
    if getattr(viewport.scene, 'edit_group', None) is not None:
        _warn(viewport, 'Cierra el grupo que estás editando y vuelve a ejecutar PisoGen ARQ.')
        return False
    return True


# ---------------------------------------------------------------------------
# The dialog
# ---------------------------------------------------------------------------

def _fmt(metres):
    """Metric documents: joints and bevels in mm, pieces in m (exact, no
    rounding to the document's display precision); others as the document."""
    if metres is None:
        return ''
    if _unit_name() in ('m', 'cm', 'mm'):
        if abs(metres) < 0.1:
            return f'{round(metres * 1000, 4):g} mm'
        return f'{round(metres, 6):g} m'
    try:
        from core.units import fmt_len
        return fmt_len(metres)
    except Exception:  # noqa: BLE001
        return f'{metres:g}'


def _parse_length(text, optional=False):
    text = str(text).strip()
    if optional and not text:
        return None
    # «0.3 2cm» must not read as 0.32 cm; «5' 3"» and «1 1/2"» are fine.
    if re.search(r'\d\s+\d', text) and not re.search(r"['\"/]", text):
        raise build.FloorError(f'Medida no válida: {text!r} (por ejemplo 60cm, 600mm, 0.6)')
    try:
        from views.viewport import _parse_length_field
        value = _parse_length_field(text.replace(' ', '').replace(',', '.'))
    except Exception:  # noqa: BLE001
        value = None
    if value is None:
        raise build.FloorError(f'Medida no válida: {text!r} (por ejemplo 60cm, 600mm, 0.6)')
    return value


def _parse_number(text, integer=False):
    try:
        value = float(str(text).strip().replace(',', '.'))
    except ValueError:
        raise build.FloorError(f'Número no válido: {text!r}') from None
    if integer:
        if not value.is_integer():
            raise build.FloorError(f'Se espera un número entero: {text!r}')
        return int(value)
    return value


def _unit_name():
    try:
        from core.units import model_unit
        return model_unit()
    except Exception:  # noqa: BLE001
        return 'm'


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Commands (the panel and the menus call these)
# ---------------------------------------------------------------------------

_state = {'panel': None, 'dock': None, 'app': None}


def _settings_of(values):
    settings = fields.core_settings(values)
    validate(settings)
    return settings


def _confirmed(viewport, pieces):
    """Large floors ask first, as main.rb does: the build blocks the program."""
    from PySide6.QtWidgets import QMessageBox
    if pieces <= CONFIRM_PIECES:
        return True
    # No by default: a stray Enter must not start a build that blocks the program.
    answer = QMessageBox.question(viewport.window(), TITLE, f'Se construirán {pieces} piezas. Puede tardar uno o más '
                                  'minutos y INGETRAZO no responderá mientras tanto.\n\n¿Continuar?',
                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    if answer == QMessageBox.Yes:
        return True
    _message('Construcción cancelada; el piso no cambió.')
    return False


def _face_pieces(face, pattern, settings):
    try:
        _matrix, boundary, triangles = build.face_domain(face)
    except build.FloorError:
        return 0
    return build.count_pieces(boundary, triangles, pattern, settings)


def create_floors(viewport, values):
    """Floors on the selected faces with the panel's values. Returns them. In
    an open group its faces are read in world coordinates and the group closes
    just before building: floors live at the top level of the document."""
    scene = viewport.scene
    if _inside_floor(scene):
        _warn(viewport, 'Esa cara es de un piso de PisoGen ARQ. Cierra el grupo y elige la superficie de abajo.')
        return []
    faces = selected_faces(scene)
    if not faces:
        _warn(viewport, 'Selecciona la cara del piso y vuelve a pulsar «Crear en la cara seleccionada». '
              'Si está dentro de un grupo, entra con doble clic y haz clic en la cara.')
        return []
    group = getattr(scene, 'edit_group', None)
    in_group = group is not None
    # The face's own mesh stays valid after the group closes. A group placed
    # by a matrix, or whose mesh other groups share, is never moved: its mesh
    # is not in world metres, or changing it would change the copies too.
    host_mesh = scene.mesh
    shared = in_group and (getattr(group, 'xform', None) is not None or build.mesh_shared(scene, host_mesh))
    hosts = [(face, None if shared else build.host_record(face)) for face in faces]
    # Floors read their face as it is now, before a slab under them goes down.
    faces = [build.FaceCopy(face) for face in faces]
    try:
        settings = _settings_of(values)
    except build.FloorError as error:
        _warn(viewport, str(error))
        return []
    pattern = settings['pattern']
    if not _confirmed(viewport, sum(_face_pieces(face, pattern, settings) for face in faces)):
        return []
    if in_group:
        viewport.end_group_edit()
    made = []

    def mutate(sc):
        build.ensure_materials(sc)
        ensure_library(sc, _material_names(settings))
        for face, (real, record) in zip(faces, hosts):
            record = build.place_host(host_mesh, real, record, settings)
            floor = build.make_floor(sc, face, pattern, settings, host=record)
            sc.groups.append(floor)
            made.append(floor)
        sc.selection.clear()
        sc.selection.update(made)

    if not _run(viewport, mutate, [host_mesh]):
        return []
    stats = [f.ext[build.KEY]['stats'] for f in made]
    text = f'{TITLE}: {len(made)} piso(s), {sum(s["pieces"] for s in stats)} piezas.'
    if len(made) == 1 and stats[0].get('quantities'):
        from . import store
        text += ' ' + store.quantities_text(stats[0]['quantities'])
    if settings.get('base_level') == 'flush':
        lowered = sum(1 for f in made if (f.ext[build.KEY].get('host') or {}).get('push'))
        if lowered:
            text += ' La losa bajó %.1f cm para dejar lugar al piso.' % (settings.get('depth_m', 0.02) * 100)
        if lowered < len(made):
            text += (' Una cara que no es la parte de arriba de una losa no se movió: las juntas y los huecos '
                     'solo se ven si bajas esa superficie.')
    _status(viewport, text)
    _message(text)
    return made


def rebuild_floor(viewport, floor, values):
    if not _at_top_level(viewport):
        return False
    try:
        settings = _settings_of(values)
    except build.FloorError as error:
        _warn(viewport, str(error))
        return False
    data = build.floor_data(floor)
    if not _confirmed(viewport, build.count_pieces(data['boundary'], data['triangles'], settings['pattern'], settings)):
        return False

    # Its host face, wherever it is now: the slab goes back up before the
    # new level applies.
    found = build.find_host(viewport.scene, data.get('host'))

    def mutate(sc):
        build.ensure_materials(sc)
        ensure_library(sc, _material_names(settings))
        build.rebuild_floor(sc, floor, settings['pattern'], settings, found)

    if not _run(viewport, mutate, [found[0]] if found else []):
        return False
    stats = build.floor_data(floor)['stats']
    text = f'{TITLE}: «{floor.name}» reconstruido, {stats["pieces"]} piezas.'
    _status(viewport, text)
    _message(text)
    return True


def _message(text):
    panel = _state['panel']
    if panel is not None:
        panel.message(text)


def material_names(scene):
    """Document materials first, then IngeTrazo's library (added on use)."""
    names = sorted(scene.materials)
    for name in (build.MAIN_MAT, build.INSERT_MAT, build.GROUT_MAT):
        if name not in names:
            names.insert(0, name)
    names += [n for n in sorted(library_materials()) if n not in scene.materials]
    return names


def show_panel(app):
    dock = _state['dock']
    if dock is not None:
        dock.show()
        dock.raise_()
    panel = _state['panel']
    if panel is not None:
        panel.refresh_units()
        panel.refresh_materials()
    return panel


def menu_create(app):
    panel = show_panel(app)
    if panel is not None:
        panel.create()


def menu_edit(app):
    panel = show_panel(app)
    if panel is not None:
        panel.edit_selected()


# ---------------------------------------------------------------------------
# Menus and setup
# ---------------------------------------------------------------------------

def _fill_menu(menu, app, faces=True, floors=True, later=False):
    from PySide6.QtCore import QTimer

    def run(fn):
        if not later:
            return lambda: fn(app)
        # From the right-click menu: after the popup has closed.
        return lambda: QTimer.singleShot(0, lambda: fn(app))

    menu.addAction('Panel PisoGen ARQ', run(show_panel))
    if faces:
        menu.addAction('Crear piso en la cara seleccionada', run(menu_create))
    if floors:
        menu.addAction('Editar piso en el panel', run(menu_edit))


def setup(app):
    from .panel import Panel
    _state['app'] = app
    actions = {
        'create': lambda values: create_floors(app.viewport, values),
        'rebuild': lambda floor, values: rebuild_floor(app.viewport, floor, values),
        'selected_floor': lambda: next(iter(selected_floors(app.viewport.scene)), None),
        'validate': _settings_of,
        'refused': lambda text: (_message(text), _status(app.viewport, f'{TITLE}: {text}')),
        'unit_name': _unit_name,
        'fmt': _fmt,
        'parse_length': _parse_length,
        'material_names': lambda: material_names(app.viewport.scene),
    }
    panel = Panel(app, actions)
    _state['panel'] = panel
    _state['dock'] = app.add_panel(TITLE, panel, PANEL_NAME, start_hidden=True)
    panel.refresh_units()
    sub = app.add_menu(TITLE)
    if sub is not None:
        _fill_menu(sub, app)

    def context(menu, selection):
        scene = app.viewport.scene
        faces, floors = selected_faces(scene), selected_floors(scene)
        if not faces and not floors:
            return
        menu.addSeparator()
        _fill_menu(menu.addMenu(TITLE), app, faces=bool(faces), floors=bool(floors), later=True)

    app.add_context_menu(context)
    add_kind = getattr(app, 'add_outliner_kind', None)
    if add_kind is not None:
        add_kind(outliner_kind)


def outliner_kind(group):
    """What a PisoGen ARQ floor is, for the Browser."""
    data = build.floor_data(group)
    if data is None:
        return None
    stats = data.get('stats') or {}
    s = data.get('settings') or {}
    props = [('Composición', build.NAMES.get(data['pattern'], data['pattern'])),
             ('Piezas', str(stats.get('pieces', ''))),
             ('Área de piezas', f'{stats.get("area_m2", 0):.2f} m²'),
             ('Junta', _fmt(s.get('joint_m'))), ('Espesor', _fmt(s.get('depth_m')))]
    totals = stats.get('quantities') or {}
    if totals.get('boxes'):
        props.append(('Cajas', str(totals['boxes'])))
    return {'type': 'Piso', 'props': props}
