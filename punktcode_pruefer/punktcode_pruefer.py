"""Hauptklasse: Menüeintrag, Werkzeugleisten-Knopf, Ablauf der Prüfung, Fehler- und Linienlayer, Export."""
import os
from collections import Counter

from qgis.PyQt.QtGui import QIcon, QColor
from qgis.PyQt.QtWidgets import QAction, QFileDialog
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt import sip
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsField, QgsFields, QgsGeometry, QgsPointXY,
    QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsSymbol, QgsVectorFileWriter, QgsWkbTypes,
    QgsCoordinateTransform,
)

from . import checks
from .dialog import PunktcodeDialog
from .i18n import tr, is_german

try:
    WRITER_OK = QgsVectorFileWriter.WriterError.NoError
except AttributeError:
    WRITER_OK = QgsVectorFileWriter.NoError
try:
    from qgis.core import Qgis
    NO_GEOMETRY = Qgis.WkbType.NoGeometry
except AttributeError:
    NO_GEOMETRY = QgsWkbTypes.NoGeometry

EXPORT = {".gpkg": "GPKG", ".xlsx": "XLSX", ".csv": "CSV"}
COLORS = {checks.UNKNOWN: "#8e44ad", checks.DUPLICATE: "#e74c3c", checks.SINGLE: "#f39c12", checks.HEIGHT: "#2980b9"}


def _num(v):
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


class PunktcodePrueferPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dialog = None
        self.errors = []
        self.layers = []

    def initGui(self):
        icon = QIcon(os.path.join(os.path.dirname(__file__), "icon.png"))
        self.action = QAction(icon, "Punktcode-Prüfer", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToVectorMenu("&Punktcode-Prüfer", self.action)

    def unload(self):
        self.iface.removeToolBarIcon(self.action)
        self.iface.removePluginVectorMenu("&Punktcode-Prüfer", self.action)

    def run(self):
        if self.dialog is None:
            self.dialog = PunktcodeDialog(self.iface.mainWindow())
            self.dialog.run_button.clicked.connect(self.start_check)
            self.dialog.export_button.clicked.connect(self.export_errors)
            self.dialog.table.cellDoubleClicked.connect(self.zoom_to)
        # eigene Ergebnislayer nicht als Punktlayer anbieten
        own = [l for l in QgsProject.instance().mapLayers().values()
               if l.customProperty("punktcode_pruefer/output", False)
               or l.name().startswith(("Punktcode-Fehler –", "Point code errors –"))]
        self.dialog.layer_combo.setExceptedLayerList(own)
        self.dialog.show()
        self.dialog.raise_()

    # --- Prüfung ---
    def read_points(self, layer):
        d = self.dialog
        fp, fc, fl, fh = d.f_pkt.currentField(), d.f_code.currentField(), d.f_line.currentField(), d.f_h.currentField()
        pts = []
        for f in layer.getFeatures():
            g = f.geometry()
            if g is None or g.isEmpty():
                continue
            p = g.asPoint() if not g.isMultipart() else g.asMultiPoint()[0]
            h = _num(f[fh]) if fh else None
            if h is None and fh == "" and QgsWkbTypes.hasZ(g.wkbType()):
                h = g.constGet().z()
            pts.append({"fid": f.id(), "pkt": f[fp], "code": "" if f[fc] is None else str(f[fc]).strip(),
                        "linie": "" if not fl or f[fl] is None else str(f[fl]).strip(),
                        "x": p.x(), "y": p.y(), "h": h})
        return pts

    def start_check(self):
        d = self.dialog
        layer = d.layer_combo.currentLayer()
        if layer is None:
            d.summary.setText(tr("Bitte zuerst einen Punktlayer auswählen."))
            return
        if not d.f_pkt.currentField() or not d.f_code.currentField():
            d.summary.setText(tr("Bitte die Felder für Punktnummer und Code auswählen."))
            return
        try:
            if d.code_file.text().strip():
                codes = checks.read_code_list(d.code_file.text().strip())
            else:
                codes = checks.parse_code_text(d.code_text.text())
        except (OSError, UnicodeDecodeError) as exc:
            d.summary.setText(tr("Codeliste konnte nicht gelesen werden: {msg}", msg=str(exc)))
            return
        if not codes:
            d.summary.setText(tr("Bitte eine Codeliste angeben (CSV-Datei oder Text)."))
            return
        d.save_settings()

        pts = self.read_points(layer)
        errors = []
        checks.set_language("de" if is_german() else "en")
        if d.chk_unknown.isChecked():
            errors += checks.check_unknown(pts, codes)
        if d.chk_dupl.isChecked():
            errors += checks.check_duplicates(pts)
        if d.chk_single.isChecked():
            errors += checks.check_single_lines(pts, codes)
        if d.chk_height.isChecked():
            errors += checks.check_heights(pts, d.tol.value())
        errors = [(tr(e[0]),) + tuple(e[1:]) for e in errors]
        self.errors = errors
        d.show_errors(errors)

        self.remove_layers()
        if errors:
            parts = ", ".join(f"{k}: {v}" for k, v in Counter(e[0] for e in errors).items())
            text = tr("{n} Fehler in {total} Punkten – {parts}", n=len(errors), total=len(pts), parts=parts)
        else:
            text = tr("Keine Fehler gefunden ({total} Punkte geprüft).", total=len(pts))
        if d.chk_lines.isChecked():
            bad = {e[1] for e in errors}
            lines = checks.build_lines([p for p in pts if p["fid"] not in bad], codes)
            self.add_line_layer(layer, lines, codes)
            text += tr(" · {l} Linien erzeugt", l=len(lines))
        self.add_error_layer(layer, errors)
        d.summary.setText(text)

    # --- Layer ---
    def remove_layers(self):
        for vl in self.layers:
            if not sip.isdeleted(vl) and QgsProject.instance().mapLayer(vl.id()) is not None:
                QgsProject.instance().removeMapLayer(vl.id())
        self.layers = []

    def add_line_layer(self, layer, lines, codes):
        if not lines:
            return
        vl = QgsVectorLayer(f"LineString?crs={layer.crs().authid()}", tr("Linien aus Codes – {name}", name=layer.name()), "memory")
        flds = QgsFields()
        for n in ("code", "linie", "bedeutung"):
            flds.append(QgsField(n, QVariant.String))
        vl.dataProvider().addAttributes(flds)
        vl.updateFields()
        feats = []
        for code, line, xy in lines:
            f = QgsFeature(vl.fields())
            f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in xy]))
            f.setAttributes([code, line, codes.get(code, ("", ""))[0]])
            feats.append(f)
        vl.dataProvider().addFeatures(feats)
        vl.updateExtents()
        vl.setCustomProperty("punktcode_pruefer/output", True)
        QgsProject.instance().addMapLayer(vl)
        self.layers.append(vl)

    def _error_fields(self, xy=False):
        flds = QgsFields()
        flds.append(QgsField("fehler_typ", QVariant.String))
        flds.append(QgsField("objekt_id", QVariant.Int))
        flds.append(QgsField("punktnummer", QVariant.String))
        flds.append(QgsField("code", QVariant.String))
        flds.append(QgsField("beschreibung", QVariant.String))
        if xy:
            flds.append(QgsField("x", QVariant.Double))
            flds.append(QgsField("y", QVariant.Double))
        return flds

    def _error_features(self, layer, vl, xy=False):
        feats = []
        for typ, fid, pkt, code, text in self.errors:
            src = layer.getFeature(int(fid))
            f = QgsFeature(vl.fields())
            attrs = [typ, int(fid), str(pkt), str(code), text]
            g = src.geometry() if src.isValid() else None
            if g is not None and not g.isEmpty():
                f.setGeometry(QgsGeometry(g))
                if xy:
                    p = g.centroid().asPoint()
                    attrs += [round(p.x(), 3), round(p.y(), 3)]
            elif xy:
                attrs += [None, None]
            f.setAttributes(attrs)
            feats.append(f)
        return feats

    def add_error_layer(self, layer, errors):
        if not errors:
            return
        vl = QgsVectorLayer(f"Point?crs={layer.crs().authid()}", tr("Punktcode-Fehler – {name}", name=layer.name()), "memory")
        vl.dataProvider().addAttributes(self._error_fields())
        vl.updateFields()
        vl.dataProvider().addFeatures(self._error_features(layer, vl))
        vl.updateExtents()
        cats = []
        colors = {tr(k): v for k, v in COLORS.items()}
        for typ in sorted({e[0] for e in errors}):
            sym = QgsSymbol.defaultSymbol(vl.geometryType())
            sym.setColor(QColor(colors.get(typ, "#000000")))
            sym.setSize(4.0)
            cats.append(QgsRendererCategory(typ, sym, typ))
        vl.setRenderer(QgsCategorizedSymbolRenderer("fehler_typ", cats))
        vl.setCustomProperty("punktcode_pruefer/output", True)
        QgsProject.instance().addMapLayer(vl)
        self.layers.append(vl)

    # --- Export und Zoom ---
    def export_errors(self):
        d = self.dialog
        layer = d.layer_combo.currentLayer()
        if not self.errors or layer is None:
            d.summary.setText(tr("Keine Fehler zum Exportieren."))
            return
        path, filt = QFileDialog.getSaveFileName(d, tr("Fehlerliste exportieren"), "punktcode_fehler",
                                                 "GeoPackage (*.gpkg);;Excel (*.xlsx);;CSV (*.csv)")
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in EXPORT:
            ext = ".xlsx" if "xlsx" in filt else ".csv" if "csv" in filt else ".gpkg"
            path += ext
        vl = QgsVectorLayer(f"Point?crs={layer.crs().authid()}", "punktcode_fehler", "memory")
        vl.dataProvider().addAttributes(self._error_fields(xy=True))
        vl.updateFields()
        vl.dataProvider().addFeatures(self._error_features(layer, vl, xy=True))
        opts = QgsVectorFileWriter.SaveVectorOptions()
        opts.driverName = EXPORT[ext]
        opts.fileEncoding = "UTF-8"
        opts.layerName = "punktcode_fehler"
        if EXPORT[ext] != "GPKG":
            opts.overrideGeometryType = NO_GEOMETRY
        res = QgsVectorFileWriter.writeAsVectorFormatV3(vl, path, QgsProject.instance().transformContext(), opts)
        if res[0] == WRITER_OK:
            d.summary.setText(tr("{n} Fehler exportiert: {path}", n=len(self.errors), path=path))
        else:
            d.summary.setText(tr("Export fehlgeschlagen: {msg}", msg=res[1]))

    def zoom_to(self, row, _col):
        layer = self.dialog.layer_combo.currentLayer()
        if layer is None or row >= len(self.errors):
            return
        fid = int(self.errors[row][1])
        f = layer.getFeature(fid)
        if not f.isValid():
            return
        g = QgsGeometry(f.geometry())
        canvas = self.iface.mapCanvas()
        dest = canvas.mapSettings().destinationCrs()
        if layer.crs() != dest:
            g.transform(QgsCoordinateTransform(layer.crs(), dest, QgsProject.instance()))
        dist = 0.0001 if dest.isGeographic() else 10
        canvas.setExtent(g.buffer(dist, 4).boundingBox())
        canvas.refresh()
        layer.selectByIds([fid])
