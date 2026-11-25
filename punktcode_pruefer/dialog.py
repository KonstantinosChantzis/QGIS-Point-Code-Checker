"""Dialogfenster des Punktcode-Prüfers (ohne .ui-Datei)."""
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QCheckBox, QPushButton, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QHBoxLayout, QAbstractItemView, QFileDialog,
)
from qgis.gui import QgsMapLayerComboBox, QgsFieldComboBox, QgsDoubleSpinBox
from qgis.core import QgsMapLayerProxyModel, QgsSettings

from .i18n import tr

try:  # QGIS >= 3.34
    from qgis.core import Qgis
    POINT_FILTER = Qgis.LayerFilter.PointLayer
except AttributeError:
    POINT_FILTER = QgsMapLayerProxyModel.PointLayer


class PunktcodeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Punktcode-Prüfer – Prüfung von Vermessungspunkten"))
        self.resize(760, 640)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.layer_combo = QgsMapLayerComboBox()
        self.layer_combo.setFilters(POINT_FILTER)
        form.addRow(tr("Punktlayer:"), self.layer_combo)

        self.f_pkt = QgsFieldComboBox()
        self.f_code = QgsFieldComboBox()
        self.f_line = QgsFieldComboBox()
        self.f_line.setAllowEmptyFieldName(True)
        self.f_h = QgsFieldComboBox()
        self.f_h.setAllowEmptyFieldName(True)
        form.addRow(tr("Feld Punktnummer:"), self.f_pkt)
        form.addRow(tr("Feld Code:"), self.f_code)
        form.addRow(tr("Feld Liniennummer (optional):"), self.f_line)
        form.addRow(tr("Feld Höhe (optional):"), self.f_h)

        row = QHBoxLayout()
        self.code_file = QLineEdit()
        browse = QPushButton(tr("Durchsuchen…"))
        browse.clicked.connect(self.choose_file)
        row.addWidget(self.code_file)
        row.addWidget(browse)
        form.addRow(tr("Codeliste (CSV: Code;Bedeutung;Typ):"), row)
        self.code_text = QLineEdit()
        form.addRow(tr("… oder Codes als Text (z. B. BO:Linie, GEB:Linie, LM, SD):"), self.code_text)

        self.chk_unknown = QCheckBox(tr("Unbekannte Codes"))
        self.chk_dupl = QCheckBox(tr("Doppelte Punktnummern"))
        self.chk_single = QCheckBox(tr("Linien mit nur einem Punkt"))
        self.chk_height = QCheckBox(tr("Höhenausreißer"))
        for c in (self.chk_unknown, self.chk_dupl, self.chk_single, self.chk_height):
            c.setChecked(True)
            form.addRow(c)
        self.tol = QgsDoubleSpinBox()
        self.tol.setDecimals(2)
        self.tol.setRange(0.01, 100.0)
        self.tol.setValue(0.50)
        self.tol.setSuffix(" m")
        form.addRow(tr("Toleranz Höhe:"), self.tol)
        self.chk_lines = QCheckBox(tr("Linienlayer aus den Codes erzeugen"))
        self.chk_lines.setChecked(True)
        form.addRow(self.chk_lines)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.run_button = QPushButton(tr("Prüfung starten"))
        self.export_button = QPushButton(tr("Fehlerliste exportieren…"))
        self.export_button.setEnabled(False)
        close_button = QPushButton(tr("Schließen"))
        close_button.clicked.connect(self.close)
        buttons.addStretch()
        for b in (self.run_button, self.export_button, close_button):
            buttons.addWidget(b)
        layout.addLayout(buttons)

        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([tr("Fehlertyp"), tr("Punktnummer"), tr("Code"), tr("Beschreibung")])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table)
        layout.addWidget(QLabel(tr("Doppelklick auf eine Zeile zoomt zum Punkt.")))

        self.layer_combo.layerChanged.connect(self.update_fields)
        self.update_fields(self.layer_combo.currentLayer())
        self.load_settings()

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Codeliste öffnen"), "", "CSV (*.csv *.txt)")
        if path:
            self.code_file.setText(path)

    def update_fields(self, layer):
        for combo in (self.f_pkt, self.f_code, self.f_line, self.f_h):
            combo.setLayer(layer)
        if layer is None:
            return
        names = [f.name() for f in layer.fields()]
        guess = {self.f_pkt: ("pkt", "punkt", "pnr", "id", "name", "number"),
                 self.f_code: ("code", "cod"), self.f_line: ("linie", "line", "lnr"),
                 self.f_h: ("h", "hoehe", "höhe", "z", "height", "elev")}
        for combo, keys in guess.items():
            for n in names:
                if n.lower() in keys or any(n.lower().startswith(k) for k in keys if len(k) > 2):
                    combo.setField(n)
                    break

    def _boxes(self):
        return {"unknown": self.chk_unknown, "dupl": self.chk_dupl, "single": self.chk_single,
                "height": self.chk_height, "lines": self.chk_lines}

    def load_settings(self):
        s = QgsSettings()
        for k, b in self._boxes().items():
            b.setChecked(s.value(f"punktcode_pruefer/{k}", b.isChecked(), type=bool))
        self.tol.setValue(s.value("punktcode_pruefer/tol", self.tol.value(), type=float))
        self.code_file.setText(s.value("punktcode_pruefer/code_file", "", type=str))
        self.code_text.setText(s.value("punktcode_pruefer/code_text", "", type=str))

    def save_settings(self):
        s = QgsSettings()
        for k, b in self._boxes().items():
            s.setValue(f"punktcode_pruefer/{k}", b.isChecked())
        s.setValue("punktcode_pruefer/tol", self.tol.value())
        s.setValue("punktcode_pruefer/code_file", self.code_file.text())
        s.setValue("punktcode_pruefer/code_text", self.code_text.text())

    def show_errors(self, errors):
        self.table.setRowCount(len(errors))
        for row, (typ, _fid, pkt, code, text) in enumerate(errors):
            for col, val in enumerate((typ, str(pkt), str(code), text)):
                self.table.setItem(row, col, QTableWidgetItem(val))
        self.table.resizeColumnsToContents()
        self.export_button.setEnabled(len(errors) > 0)
