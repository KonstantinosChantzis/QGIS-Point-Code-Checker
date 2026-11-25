"""Einfache Übersetzung (Deutsch / Englisch). Texte im Code sind deutsch;
ist QGIS nicht auf Deutsch eingestellt, wird EN verwendet."""

from qgis.core import QgsSettings

EN = {
    "Punktcode-Prüfer – Prüfung von Vermessungspunkten":
        "Punktcode-Prüfer – check of survey points",
    "Punktlayer:": "Point layer:",
    "Feld Punktnummer:": "Field point number:",
    "Feld Code:": "Field code:",
    "Feld Liniennummer (optional):": "Field line number (optional):",
    "Feld Höhe (optional):": "Field height (optional):",
    "Codeliste (CSV: Code;Bedeutung;Typ):":
        "Code list (CSV: code;meaning;type):",
    "… oder Codes als Text (z. B. BO:Linie, GEB:Linie, LM, SD):":
        "… or codes as text (e.g. BO:Linie, GEB:Linie, LM, SD):",
    "Durchsuchen…": "Browse…",
    "Unbekannte Codes": "Unknown codes",
    "Doppelte Punktnummern": "Duplicate point numbers",
    "Linien mit nur einem Punkt": "Lines with only one point",
    "Höhenausreißer": "Height outliers",
    "Toleranz Höhe:": "Height tolerance:",
    "Linienlayer aus den Codes erzeugen": "Create line layer from the codes",
    "Prüfung starten": "Start check",
    "Fehlerliste exportieren…": "Export error list…",
    "Schließen": "Close",
    "Fehlertyp": "Error type",
    "Punktnummer": "Point number",
    "Code": "Code",
    "Beschreibung": "Description",
    "Doppelklick auf eine Zeile zoomt zum Punkt.":
        "Double-click a row to zoom to the point.",
    "Bitte zuerst einen Punktlayer auswählen.":
        "Please select a point layer first.",
    "Bitte die Felder für Punktnummer und Code auswählen.":
        "Please select the fields for point number and code.",
    "Bitte eine Codeliste angeben (CSV-Datei oder Text).":
        "Please provide a code list (CSV file or text).",
    "Codeliste konnte nicht gelesen werden: {msg}":
        "Code list could not be read: {msg}",
    "{n} Fehler in {total} Punkten – {parts}":
        "{n} errors in {total} points – {parts}",
    "Keine Fehler gefunden ({total} Punkte geprüft).":
        "No errors found ({total} points checked).",
    " · {l} Linien erzeugt": " · {l} lines created",
    "Punktcode-Fehler – {name}": "Point code errors – {name}",
    "Linien aus Codes – {name}": "Lines from codes – {name}",
    "Keine Fehler zum Exportieren.": "No errors to export.",
    "Fehlerliste exportieren": "Export error list",
    "{n} Fehler exportiert: {path}": "{n} errors exported: {path}",
    "Export fehlgeschlagen: {msg}": "Export failed: {msg}",
    "Codeliste öffnen": "Open code list",
    "Unbekannter Code": "Unknown code",
    "Doppelte Punktnummer": "Duplicate point number",
    "Linie mit nur einem Punkt": "Line with only one point",
}


def is_german():
    loc = QgsSettings().value("locale/userLocale", "") or ""
    if not loc:
        from qgis.PyQt.QtCore import QLocale

        loc = QLocale.system().name()
    return str(loc).lower().startswith("de")


def tr(text, **kwargs):
    if not is_german():
        text = EN.get(text, text)
    return text.format(**kwargs) if kwargs else text
