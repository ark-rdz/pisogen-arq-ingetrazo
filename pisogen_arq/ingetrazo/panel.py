# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alfonso Rodríguez
"""The PisoGen ARQ side panel: the SketchUp panel's sections rebuilt in Qt
widgets (IngeTrazo ships without a web engine).

Header with logo, version and model units; Destino del trabajo; Presets;
Material Center; Composición (twenty previews drawn by the core);
Medidas; Colocación; Bisel superior; Materiales y UV; Relleno de juntas;
Cuantificación; and the footer with Actualizar en vivo, Crear and
Reconstruir. Sections fold like the HTML panel's.
"""
import webbrowser

from PySide6.QtCore import QByteArray, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QPolygonF
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QScrollArea,
                               QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from ..core import paving
from . import build, fields, store

LOGO_SVG = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#183236"/>'
            b'<g fill="#6fd0bd"><path d="M10 22 24 14 32 19 18 27Z"/><path d="M32 19 46 11 54 16 40 24Z"/>'
            b'<path d="M10 34 24 26 32 31 18 39Z"/><path d="M32 31 46 23 54 28 40 36Z"/>'
            b'<path d="M10 46 24 38 32 43 18 51Z"/><path d="M32 43 46 35 54 40 40 48Z"/></g></svg>')
TEAL = '#6fd0bd'
STYLE = f"""
QWidget#pisogen {{ font-size: 12px; }}
QToolButton[section="true"] {{ font-weight: bold; text-align: left; border: none; padding: 6px 2px; }}
QLabel[hint="true"] {{ color: #9aa5a8; font-size: 11px; }}
QLabel#badge {{ background: #1f4a45; color: {TEAL}; border-radius: 8px; padding: 1px 8px; font-weight: bold; }}
QLabel#banner {{ background: #1c2c2e; border: 1px solid #2c4a48; border-radius: 6px; padding: 6px; }}
QPushButton[primary="true"] {{ background: #2a8f7d; color: white; font-weight: bold; padding: 6px; border-radius: 4px; }}
QPushButton[primary="true"]:disabled {{ background: #3a4546; color: #8a9799; }}
QToolButton[pattern="true"] {{ border: 1px solid #3a4546; border-radius: 6px; padding: 3px; }}
QToolButton[pattern="true"]:checked {{ border: 2px solid {TEAL}; }}
"""
LIVE_LIMIT = 3000


def _hint(text):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setProperty('hint', True)
    return label


class Section(QWidget):
    """A foldable section: a header button over a form."""

    def __init__(self, title, collapsed=False):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.header = QToolButton()
        self.header.setProperty('section', True)
        self.header.setText(title)
        self.header.setCheckable(True)
        self.header.setChecked(not collapsed)
        self.header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.body = QWidget()
        self.form = QFormLayout(self.body)
        self.form.setContentsMargins(6, 0, 4, 8)
        self.form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        lay.addWidget(self.header)
        lay.addWidget(self.body)
        self.header.toggled.connect(self._fold)
        self._fold(self.header.isChecked())

    def _fold(self, open_):
        self.header.setArrowType(Qt.DownArrow if open_ else Qt.RightArrow)
        self.body.setVisible(open_)


def pattern_icon(pattern, size=QSize(150, 75)):
    """Preview drawn from the core, as the SketchUp panel draws its buttons."""
    s = {'length_m': .45 if pattern == 'wood' else .3, 'width_m': .05 if pattern == 'strip' else .12, 'joint_m': .006,
         'side_m': .24 if pattern == 'adopasto_reja' else .15 if pattern == 'adopasto' else
         .075 if pattern in ('hexagon', 'octagon', 'diamonds') else .30,
         'wedge_long_m': .12, 'wedge_short_m': .06, 'wedge_height_m': .09, 'wedge_inverse_m': 0,
         'iblock_length_m': .13, 'iblock_width_m': .11, 'iblock_web_m': .06}
    if pattern == 'irregular':
        s.update(irregular_style='stone', irregularity_pct=100, side_m=.14)
    if pattern == 'adopasto_reja':
        s.update(reja_opening_m=.04, reja_chamfer_m=.006)
    pixmap = QPixmap(size)
    pixmap.fill(QColor('#20292b'))
    try:
        demo = paving.generate({'schema': paving.SCHEMA, 'unit': 'm', 'pattern': pattern,
                                'boundary': [[0, 0], [.6, 0], [.6, .3], [0, .3]], 'settings': s})
    except Exception:  # noqa: BLE001 - a preview never blocks the panel
        return QIcon(pixmap)
    scale = size.width() / .6
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    for piece in demo['pieces']:
        grass = pattern in fields.GRASS
        painter.setBrush(QColor(('#73a752' if grass else '#d9b176') if piece['role'] == 'insert' else '#70aa9e'))
        for poly in piece['polygons_m']:
            painter.drawPolygon(QPolygonF([QPointF(x * scale, size.height() - y * scale) for x, y in poly]))
    painter.end()
    return QIcon(pixmap)


class Panel(QScrollArea):
    def __init__(self, app, actions):
        """``actions``: create(values), rebuild(floor, values), selected_floor(),
        unit_name(), fmt(metres), parse_length(text, optional), library()."""
        super().__init__()
        self.app = app
        self.actions = actions
        self.target = None
        self.values = fields.defaults()
        self.loading = False
        self.live_timer = QTimer(self)
        self.live_timer.setSingleShot(True)
        self.live_timer.setInterval(700)
        self.live_timer.timeout.connect(self._live_rebuild)
        # The active floor can leave the scene without the panel knowing (undo,
        # new or opened document).
        self.target_timer = QTimer(self)
        self.target_timer.setInterval(1000)
        self.target_timer.timeout.connect(self._check_target)
        self.target_timer.start()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root = QWidget()
        root.setObjectName('pisogen')
        root.setStyleSheet(STYLE)
        self.setWidget(root)
        self.lay = QVBoxLayout(root)
        self.lay.setContentsMargins(8, 8, 8, 8)
        self._header()
        self._target_section()
        self._presets_section()
        self._catalog_section()
        self._patterns_section()
        self.widgets, self.sections = {}, {}
        for name in fields.SECTIONS:
            section = Section(name, collapsed=name in ('Colocación', 'Cuantificación'))
            self.sections[name] = section
            self.lay.addWidget(section)
        self._fields()
        self._materials()
        self._footer()
        self.lay.addStretch(1)
        self.refresh_materials()
        self.apply(self.values)
        self.refresh_presets()
        self.refresh_catalog()
        self._fit_width(root)

    # ---- construction -----------------------------------------------------

    @staticmethod
    def _fit_width(root):
        """Long material names must not widen the panel past the dock: the
        scroll area has no horizontal bar and would clip the right."""
        for combo in root.findChildren(QComboBox):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(12)

    def _header(self):
        from PySide6.QtSvg import QSvgRenderer
        row = QHBoxLayout()
        pixmap = QPixmap(104, 104)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        QSvgRenderer(QByteArray(LOGO_SVG)).render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(2)
        logo = QLabel()
        logo.setPixmap(pixmap)
        logo.setFixedSize(52, 52)
        row.addWidget(logo)
        text = QVBoxLayout()
        title = QLabel('<span style="font-size:18px;font-weight:bold">PisoGen ARQ</span>')
        self.subtitle = QLabel()
        badge = QLabel('v' + build.VERSION)
        badge.setObjectName('badge')
        badge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        for w in (title, self.subtitle, badge):
            text.addWidget(w)
        row.addLayout(text, 1)
        self.lay.addLayout(row)
        self.banner = QLabel()
        self.banner.setObjectName('banner')
        self.banner.setWordWrap(True)
        self.lay.addWidget(self.banner)

    def _target_section(self):
        section = Section('Destino del trabajo')
        self.target_label = QLabel('Preparando piso nuevo')
        self.target_label.setWordWrap(True)
        self.target_label.setStyleSheet(f'color: {TEAL}')
        section.form.addRow(self.target_label)
        row = QHBoxLayout()
        new, edit = QPushButton('Nuevo piso'), QPushButton('Editar seleccionado')
        new.clicked.connect(self.new_floor)
        edit.clicked.connect(self.edit_selected)
        row.addWidget(new)
        row.addWidget(edit)
        section.form.addRow(row)
        section.form.addRow(_hint('Para recuperar un piso guardado, selecciona su grupo y pulsa Editar seleccionado.'))
        self.lay.addWidget(section)

    def _presets_section(self):
        section = Section('Presets', collapsed=True)
        self.preset_list = QComboBox()
        section.form.addRow('Preset', self.preset_list)
        row = QHBoxLayout()
        apply_, delete = QPushButton('Aplicar'), QPushButton('Eliminar')
        apply_.clicked.connect(self.apply_preset)
        delete.clicked.connect(self.delete_preset)
        row.addWidget(apply_)
        row.addWidget(delete)
        section.form.addRow(row)
        self.preset_name = QLineEdit()
        self.preset_name.setMaxLength(60)
        section.form.addRow('Nombre para guardar', self.preset_name)
        save = QPushButton('Guardar ajustes actuales')
        save.clicked.connect(self.save_preset)
        section.form.addRow(save)
        section.form.addRow(_hint('Un preset guarda composición, medidas, juntas, bisel, textura y cantidades; no guarda '
                                  'materiales, que dependen de cada modelo. Aplicar no reconstruye: pulsa Reconstruir o '
                                  'Crear. Los presets propios se guardan en este equipo.'))
        self.lay.addWidget(section)

    def _catalog_section(self):
        section = Section('Material Center', collapsed=True)
        self.catalog_list = QComboBox()
        section.form.addRow('Producto', self.catalog_list)
        row = QHBoxLayout()
        apply_, delete = QPushButton('Aplicar'), QPushButton('Eliminar')
        apply_.clicked.connect(self.apply_product)
        delete.clicked.connect(self.delete_product)
        row.addWidget(apply_)
        row.addWidget(delete)
        section.form.addRow(row)
        self.catalog_fields = {}
        for key, label, top in (('marca', 'Marca', 60), ('coleccion', 'Colección', 60), ('nombre', 'Producto', 60),
                                ('codigo', 'Código', 60), ('acabado', 'Acabado', 60), ('notas', 'Notas', 300)):
            edit = QLineEdit()
            edit.setMaxLength(top)
            self.catalog_fields[key] = edit
            section.form.addRow(label, edit)
        save = QPushButton('Guardar ajustes actuales como producto')
        save.clicked.connect(self.save_product)
        section.form.addRow(save)
        grid = QGridLayout()
        for i, (text, slot) in enumerate((('Buscar producto en web', self.search_product), ('Abrir archivo', self.open_catalog),
                                          ('Recargar', self.reload_catalog), ('Usar otro archivo…', self.choose_catalog),
                                          ('Volver al de este equipo', self.default_catalog))):
            button = QPushButton(text)
            button.clicked.connect(slot)
            grid.addWidget(button, i // 2, i % 2)
        section.form.addRow(grid)
        self.catalog_error = _hint('')
        self.catalog_file = _hint('')
        section.form.addRow(self.catalog_error)
        section.form.addRow(self.catalog_file)
        section.form.addRow(_hint('Es el mismo catálogo que usa PisoGen ARQ en SketchUp. Un producto guarda patrón, medidas '
                                  'de la pieza, espesor, junta y datos de caja; no guarda materiales ni colocación. Aplicar '
                                  'no reconstruye. Al guardar, un producto con la misma marca, colección y nombre se reemplaza; '
                                  'si el archivo tiene un error, no se sobrescribe.'))
        self.lay.addWidget(section)

    def _patterns_section(self):
        section = Section('Composición')
        grid = QGridLayout()
        grid.setSpacing(4)
        self.pattern_buttons = {}
        for i, (code, name) in enumerate(build.NAMES.items()):
            button = QToolButton()
            button.setProperty('pattern', True)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setIcon(pattern_icon(code))
            button.setIconSize(QSize(100, 50))
            button.setText(name)
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.clicked.connect(lambda _c=False, code=code: self.choose_pattern(code))
            self.pattern_buttons[code] = button
            grid.addWidget(button, i // 2, i % 2)
        holder = QWidget()
        holder.setLayout(grid)
        section.form.addRow(holder)
        self.lay.addWidget(section)

    def _fields(self):
        for key, label, kind, _default, section_name, _show in fields.FIELDS:
            if kind == 'bool':
                w = QCheckBox()
                w.toggled.connect(self.changed)
            elif isinstance(kind, tuple):
                w = QComboBox()
                for code in kind:
                    w.addItem(fields.CHOICE_LABELS.get(code, str(code)), code)
                w.currentIndexChanged.connect(self.changed)
            else:
                w = QLineEdit()
                w.editingFinished.connect(self.changed)
            self.widgets[key] = w
            self.sections[section_name].form.addRow(label, w)
        hints = {
            'Medidas': 'Los valores admiten unidades (60cm, 600mm, 0.6m). Desnivel: cada pieza sube al azar entre 0 y '
                       'este valor (máximo 10 mm). Recorte mínimo: 0 = sin control; máximo, la mitad de la tabla más corta.',
            'Colocación': 'El ángulo se suma al borde elegido. Las esquinas son las del rectángulo que envuelve la cara, '
                          'medido en la dirección del patrón. El desplazamiento se mide a lo largo de los ejes del patrón ya girado.',
            'Bisel superior': 'La altura total de la pieza se conserva. En recortes estrechos el bisel se reduce; los '
                              'recortes demasiado pequeños se conservan sin bisel.',
            'Relleno de juntas': 'El ancho se controla con Junta, en Medidas. El relleno queda bajo las piezas y respeta '
                                 'los huecos de la cara base, separado 0.2 mm. En Adopasto, su hundimiento debe ser al '
                                 'menos el del pasto.',
            'Cuantificación': 'Se calculan al construir el piso y se guardan con él. Un valor 0 omite ese dato. Las cajas '
                              'usan m² por caja; si es 0, piezas por caja. Los cálculos son preliminares: verifícalos '
                              'contra la ficha técnica y las condiciones reales de obra.',
        }
        for name, text in hints.items():
            self.sections[name].form.addRow(_hint(text))
        self.quantities_label = _hint('Construye o selecciona un piso para ver sus cantidades.')
        self.quantities_label.setStyleSheet(f'color: {TEAL}')
        self.sections['Cuantificación'].form.insertRow(0, self.quantities_label)
        self.no_bevel_hint = _hint('Este patrón no lleva bisel geométrico: en Hexágono, Octágono, Adopasto, Irregular, '
                                   'Cuña, Bloque I y Diamantes el bisel va en el material del render.')
        self.sections['Bisel superior'].form.insertRow(0, self.no_bevel_hint)

    def _materials(self):
        form = self.sections['Materiales y UV'].form
        self.main_list = QListWidget()
        self.main_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.main_list.setMinimumHeight(150)
        self.main_list.itemSelectionChanged.connect(self._materials_changed)
        form.insertRow(1, 'Materiales principales', self.main_list)
        row = QHBoxLayout()
        clear, refresh = QPushButton('Limpiar'), QPushButton('Actualizar lista')
        clear.clicked.connect(self.main_list.clearSelection)
        refresh.clicked.connect(self.refresh_materials)
        self.material_count = _hint('0 material(es)')
        row.addWidget(clear)
        row.addWidget(refresh)
        row.addWidget(self.material_count, 1)
        form.insertRow(2, row)
        form.insertRow(3, _hint('Clic para elegir o quitar; puedes elegir varios. Sin selección se usa «PisoGen ARQ piezas». '
                                'Los de «Biblioteca» son de INGETRAZO y se agregan al documento al construir. Muchas maderas '
                                'de la biblioteca traen la veta vertical: elige «Vertical → largo de la pieza».'))
        self.insert_combo = QComboBox()
        self.insert_combo.currentIndexChanged.connect(self.changed)
        form.addRow('Material de insertos', self.insert_combo)
        self.grout_combo = QComboBox()
        self.grout_combo.currentIndexChanged.connect(self.changed)
        self.sections['Relleno de juntas'].form.insertRow(1, 'Material de relleno', self.grout_combo)

    def _footer(self):
        self.live = QCheckBox('Actualizar en vivo')
        self.live.toggled.connect(self.changed)
        self.lay.addWidget(self.live)
        self.lay.addWidget(_hint(f'Solo en un piso existente: al cambiar un ajuste se reconstruye solo. Por encima de '
                                 f'{LIVE_LIMIT:,} piezas queda en pausa; usa Reconstruir.'.replace(',', ' ')))
        row = QHBoxLayout()
        self.create_button = QPushButton('Crear en la cara seleccionada')
        self.rebuild_button = QPushButton('Reconstruir este piso')
        for button in (self.create_button, self.rebuild_button):
            button.setProperty('primary', True)
            row.addWidget(button)
        self.create_button.clicked.connect(self.create)
        self.rebuild_button.clicked.connect(self.rebuild)
        self.lay.addLayout(row)
        self.status = _hint('Panel listo.')
        self.status.setStyleSheet(f'color: {TEAL}')
        self.lay.addWidget(self.status)

    # ---- values -----------------------------------------------------------

    def _text(self, key, kind, value):
        if kind in ('len', 'len?'):
            return self.actions['fmt'](value) if value is not None else ''
        if kind == 'pct':
            return f'{round(value * 100, 6):g}'
        return '' if value is None else f'{value:g}'

    def apply(self, values):
        """Shows ``values`` in the widgets (no rebuild)."""
        self.loading = True
        try:
            self.values = dict(fields.defaults(), **values)
            for key, _label, kind, _default, _section, _show in fields.FIELDS:
                w, value = self.widgets[key], self.values.get(key)
                if kind == 'bool':
                    w.setChecked(bool(value))
                elif isinstance(kind, tuple):
                    w.setCurrentIndex(list(kind).index(value) if value in kind else 0)
                else:
                    w.setText(self._text(key, kind, value))
            chosen = set(self.values.get('main_materials') or [])
            for i in range(self.main_list.count()):
                item = self.main_list.item(i)
                item.setSelected(item.text() in chosen)
            self.insert_combo.setCurrentText(self.values.get('insert_material') or build.INSERT_MAT)
            self.grout_combo.setCurrentText(self.values.get('grout_material') or build.GROUT_MAT)
            button = self.pattern_buttons.get(self.values.get('pattern'))
            if button:
                button.setChecked(True)
            self.live.setChecked(bool(self.values.get('live_update')))
        finally:
            self.loading = False
        self.visibility()

    def collect(self):
        """Widgets → values. Raises build.FloorError on a bad entry."""
        out = dict(self.values)
        for key, label, kind, _default, _section, show in fields.FIELDS:
            w = self.widgets[key]
            if kind == 'bool':
                out[key] = w.isChecked()
            elif isinstance(kind, tuple):
                out[key] = w.currentData()
            elif not show(out):
                continue    # hidden measures keep their last valid value
            elif kind in ('len', 'len?'):
                out[key] = self.actions['parse_length'](w.text(), optional=kind == 'len?')
            else:
                text = w.text().strip().replace(',', '.')
                try:
                    number = float(text)
                except ValueError:
                    raise build.FloorError(f'«{label}»: número no válido ({w.text()!r}).') from None
                if kind == 'int':
                    if not number.is_integer():
                        raise build.FloorError(f'«{label}»: se espera un número entero.')
                    number = int(number)
                out[key] = number / 100 if kind == 'pct' else number
        out['main_materials'] = [i.text() for i in self.main_list.selectedItems()]
        out['insert_material'] = self.insert_combo.currentText()
        out['grout_material'] = self.grout_combo.currentText()
        out['live_update'] = self.live.isChecked()
        return out

    def visibility(self):
        values = dict(self.values)
        for key, _label, kind, _default, _section, _show in fields.FIELDS:
            w = self.widgets[key]
            if kind == 'bool':
                values[key] = w.isChecked()
            elif isinstance(kind, tuple):
                values[key] = w.currentData()
        pattern = values.get('pattern')
        for key, _label, _kind, _default, section, show in fields.FIELDS:
            visible = bool(show(values))
            if section == 'Bisel superior':
                visible = visible and pattern not in fields.NO_BEVEL
            self.sections[section].form.setRowVisible(self.widgets[key], visible)
        self.sections['Bisel superior'].form.setRowVisible(self.no_bevel_hint, pattern in fields.NO_BEVEL)
        grass = pattern in fields.GRASS
        self.sections['Materiales y UV'].form.setRowVisible(
            self.insert_combo, pattern in fields.WITH_INSERTS and (values.get('insert_enabled') or grass))
        form = self.sections['Materiales y UV'].form
        label = form.labelForField(self.insert_combo)
        if label:
            label.setText('Material de pasto' if grass else 'Material de insertos')
        self.sections['Relleno de juntas'].form.setRowVisible(self.grout_combo, bool(values.get('grout_enabled')))
        self.rebuild_button.setEnabled(self._target_alive())

    def changed(self, *_args):
        if self.loading:
            return
        self.visibility()
        try:
            self.values = self.collect()
        except build.FloorError:
            return
        if self.live.isChecked() and self._target_alive():
            self.live_timer.start()

    def _materials_changed(self):
        self.material_count.setText(f'{len(self.main_list.selectedItems())} material(es)')
        self.changed()

    def refresh_materials(self):
        names = self.actions['material_names']()
        chosen = set(self.values.get('main_materials') or [])
        self.loading = True
        try:
            self.main_list.clear()
            self.main_list.addItems(names)
            for i in range(self.main_list.count()):
                self.main_list.item(i).setSelected(self.main_list.item(i).text() in chosen)
            for combo, current, fallback in ((self.insert_combo, self.values.get('insert_material'), build.INSERT_MAT),
                                             (self.grout_combo, self.values.get('grout_material'), build.GROUT_MAT)):
                combo.clear()
                combo.addItems(names)
                combo.setCurrentText(current if current in names else fallback)
        finally:
            self.loading = False
        self.material_count.setText(f'{len(self.main_list.selectedItems())} material(es)')

    def refresh_units(self):
        unit = self.actions['unit_name']()
        names = {'m': 'metros (m)', 'cm': 'centímetros (cm)', 'mm': 'milímetros (mm)'}
        self.subtitle.setText(f'Parámetros profesionales · medidas en {unit}')
        self.banner.setText(f'<b>Unidades del modelo: {names.get(unit, unit)}</b><br>'
                            'Las medidas se muestran en m y mm; puedes escribir cualquier unidad.')

    def message(self, text):
        self.status.setText(text)

    # ---- composition ------------------------------------------------------

    def choose_pattern(self, code):
        try:
            values = self.collect()
        except build.FloorError as error:
            self.message(str(error))
            values = dict(self.values)
        values['pattern'] = code
        values.update(fields.PATTERN_STARTS.get(code, {}))
        if code in fields.NO_BEVEL:
            values['bevel_enabled'] = False
        self.apply(values)
        self.changed()
        self.message(f'Composición: {build.NAMES[code]}.')

    # ---- target -----------------------------------------------------------

    def _target_alive(self):
        return self.target is not None and self.target in self.app.viewport.scene.groups

    def _check_target(self):
        if self.target is not None and not self._target_alive():
            self.set_target(None)

    def set_target(self, floor):
        self.target = floor
        if floor is None:
            self.target_label.setText('Preparando piso nuevo')
        else:
            data = build.floor_data(floor) or {}
            stats = data.get('stats') or {}
            self.target_label.setText(f'Editando: {floor.name} · {stats.get("pieces", 0)} piezas')
            totals = stats.get('quantities')
            self.quantities_label.setText('Cantidades: ' + store.quantities_text(totals) if totals else
                                          'Este piso no tiene cantidades guardadas.')
        self.visibility()

    def new_floor(self):
        self.set_target(None)
        self.message('Piso nuevo: selecciona una cara (si está en un grupo, entra con doble clic) y pulsa Crear en la cara seleccionada.')

    def edit_selected(self):
        floor = self.actions['selected_floor']()
        if floor is None:
            self.message('Selecciona un piso hecho con PisoGen ARQ y vuelve a pulsar Editar seleccionado.')
            return
        data = build.floor_data(floor)
        values = dict(fields.defaults(), **data['settings'])
        values['pattern'] = data['pattern']
        self.apply(values)
        self.set_target(floor)
        self.message(f'Ajustes de «{floor.name}» cargados. Cambia lo que quieras y pulsa Reconstruir.')

    def create(self):
        try:
            values = self.collect()
            self.actions['validate'](values)
        except build.FloorError as error:
            # Also in the status bar: from a menu the panel's foot may be out of view.
            self.actions['refused'](str(error))
            return
        self.values = values
        made = self.actions['create'](values)
        if made:
            self.set_target(made[-1])

    def rebuild(self):
        if not self._target_alive():
            self.message('No hay piso activo: usa Editar seleccionado o Crear.')
            return
        try:
            values = self.collect()
            self.actions['validate'](values)
        except build.FloorError as error:
            self.actions['refused'](str(error))
            return
        self.values = values
        if self.actions['rebuild'](self.target, values):
            self.set_target(self.target)

    def _live_rebuild(self):
        if not (self.live.isChecked() and self._target_alive()):
            return
        pieces = ((build.floor_data(self.target) or {}).get('stats') or {}).get('pieces', 0)
        if pieces > LIVE_LIMIT:
            self.message(f'Actualizar en vivo en pausa: el piso tiene {pieces} piezas. Pulsa Reconstruir.')
            return
        self.rebuild()

    # ---- presets ----------------------------------------------------------

    def refresh_presets(self):
        current = self.preset_list.currentText()
        self.preset_list.clear()
        self.preset_list.addItem('Seleccionar…', None)
        for name in store.BUILTIN_PRESETS:
            self.preset_list.addItem(name, ('b', name))
        for name in sorted(store.user_presets()):
            self.preset_list.addItem(name, ('u', name))
        self.preset_list.setCurrentIndex(max(0, self.preset_list.findText(current)))

    def apply_preset(self):
        choice = self.preset_list.currentData()
        if not choice:
            self.message('Elige un preset.')
            return
        kind, name = choice
        preset = store.BUILTIN_PRESETS.get(name) if kind == 'b' else store.user_presets().get(name)
        if not preset:
            self.message('Ese preset ya no existe.')
            return
        values = dict(self.values)
        values.update({k: v for k, v in preset.items() if k not in fields.MATERIAL_KEYS})
        self.apply(values)
        self.changed()
        self.message(f'Preset «{name}» aplicado. Pulsa Reconstruir o Crear.')

    def save_preset(self):
        try:
            store.save_preset(self.preset_name.text(), self.collect())
        except (build.FloorError, store.StoreError, OSError) as error:
            self.message(str(error))
            return
        self.refresh_presets()
        self.message(f'Preset «{self.preset_name.text().strip()}» guardado en este equipo.')

    def delete_preset(self):
        choice = self.preset_list.currentData()
        if not choice or choice[0] != 'u':
            self.message('Elige un preset propio (los ejemplos no se eliminan).')
            return
        try:
            store.delete_preset(choice[1])
        except (store.StoreError, OSError) as error:
            self.message(str(error))
            return
        self.refresh_presets()
        self.message(f'Preset «{choice[1]}» eliminado.')

    # ---- Material Center --------------------------------------------------

    def refresh_catalog(self):
        info = store.catalog()
        self.catalog_info = info
        self.catalog_list.clear()
        self.catalog_list.addItem('Seleccionar…', None)
        for product in info['products']:
            self.catalog_list.addItem(store.product_label(product), product)
        error = info['error'] or (f"{info['skipped']} producto(s) del archivo con datos inválidos no se muestran."
                                  if info['skipped'] else '')
        self.catalog_error.setText(error)
        self.catalog_file.setText(('Archivo elegido: ' if info['custom'] else 'Archivo de este equipo: ') + info['path'])
        return info

    def _product(self):
        product = self.catalog_list.currentData()
        if not product:
            raise store.StoreError('Elige un producto.')
        return product

    def apply_product(self):
        try:
            product = self._product()
        except store.StoreError as error:
            self.message(str(error))
            return
        values = dict(self.values)
        values['pattern'] = product['patron']
        values.update(product['medidas'])
        values.update(product['cantidades'])
        self.apply(values)
        for key, edit in self.catalog_fields.items():
            edit.setText(product.get(key, ''))
        self.changed()
        self.message(f"Producto «{product['nombre']}» aplicado: patrón, medidas y datos de caja. Pulsa Reconstruir o Crear.")

    def save_product(self):
        try:
            values = self.collect()
            measures = {k: values.get(k) for k in fields.product_keys(values['pattern']) if k in values}
            if not values.get('length_variable'):
                for k in ('length_variable', 'length_min_m', 'length_max_m', 'length_steps'):
                    measures.pop(k, None)
            product = {k: e.text().strip() for k, e in self.catalog_fields.items()}
            product.update(patron=values['pattern'], medidas=measures,
                           cantidades={k: values.get(k) or 0 for k in fields.QUANTITY_KEYS})
            replaced = store.save_product(product)
        except (build.FloorError, store.StoreError, OSError) as error:
            self.message(str(error))
            return
        self.refresh_catalog()
        self.message(f"Producto «{product['nombre']}» {'actualizado en' if replaced else 'agregado al'} catálogo.")

    def delete_product(self):
        try:
            product = self._product()
            if QMessageBox.question(self, 'PisoGen ARQ', f"¿Eliminar «{product['nombre']}» del catálogo?") != QMessageBox.Yes:
                return
            store.delete_product(product)
        except (store.StoreError, OSError) as error:
            self.message(str(error))
            return
        self.refresh_catalog()
        self.message(f"Producto «{product['nombre']}» eliminado del catálogo.")

    def search_product(self):
        product = {k: e.text() for k, e in self.catalog_fields.items()}
        if not any(product.get(k, '').strip() for k in ('marca', 'coleccion', 'nombre', 'codigo')):
            product = self.catalog_list.currentData() or {}
        try:
            text, url = store.search_url(product)
        except store.StoreError as error:
            self.message(str(error))
            return
        webbrowser.open(url)
        self.message(f'Buscando «{text}» en el navegador.')

    def open_catalog(self):
        import os
        info = self.refresh_catalog()
        if not os.path.exists(info['path']):
            self.message('No hay archivo de catálogo que abrir.')
            return
        import subprocess
        # Notepad, as the SketchUp version opens it; nothing of IngeTrazo's open files is inherited.
        subprocess.Popen(['notepad.exe', info['path']], close_fds=True)  # noqa: S603,S607
        self.message('Catálogo abierto. Al terminar de editarlo, guárdalo y pulsa Recargar.')

    def reload_catalog(self):
        info = self.refresh_catalog()
        self.message('El catálogo tiene un error; revisa el aviso.' if info['error'] else
                     f"Catálogo recargado: {len(info['products'])} productos.")

    def choose_catalog(self):
        import os
        path, _ = QFileDialog.getOpenFileName(self, 'Catálogo de productos (JSON)', os.path.dirname(store.catalog_path()),
                                              'Catálogo JSON (*.json)')
        if path:
            store.use_catalog(path)
            self.reload_catalog()

    def default_catalog(self):
        store.use_catalog(None)
        self.reload_catalog()
