"""Prüfungen des Punktcode-Prüfers – reines Python, ohne QGIS (dadurch auch ohne QGIS testbar).

Eingabe: Liste von Punkten als dict mit den Schlüsseln
  fid, pkt (Punktnummer), code, linie (Liniennummer, optional), x, y, h (Höhe, optional)
Ergebnis: Liste von Fehlern (fehlertyp, fid, pkt, code, beschreibung)
"""
import csv
import math
from collections import defaultdict

UNKNOWN = "Unbekannter Code"
DUPLICATE = "Doppelte Punktnummer"
SINGLE = "Linie mit nur einem Punkt"
HEIGHT = "Höhenausreißer"

# Beschreibungstexte Deutsch / Englisch; Sprache mit set_language("de"/"en") wählen
MESSAGES = {
    "de": {
        "unknown": "Code '{c}' ist nicht in der Codeliste",
        "duplicate": "{n}× vorhanden, Abstand {d:.0f} mm",
        "single": "{c} Linie {l}: nur ein Punkt, Endpunkt fehlt",
        "height": "Höhe weicht um {d:+.2f} m von den Nachbarpunkten (Code {c}) ab",
    },
    "en": {
        "unknown": "Code '{c}' is not in the code list",
        "duplicate": "{n}× present, distance {d:.0f} mm",
        "single": "{c} line {l}: only one point, end point missing",
        "height": "Height differs by {d:+.2f} m from neighbouring points (code {c})",
    },
}
_lang = "de"


def set_language(lang):
    global _lang
    _lang = "de" if str(lang).lower().startswith("de") else "en"


def _msg(key, **kw):
    return MESSAGES[_lang][key].format(**kw)


def read_code_list(path):
    """Codeliste als CSV lesen (Trennzeichen ; oder ,). Spalten: Code;Bedeutung;Typ.
    Typ = Linie, Symbol oder Punkt. Gibt {code: (bedeutung, typ)} zurück."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        sample = f.read(2048)
        f.seek(0)
        delim = ";" if sample.count(";") >= sample.count(",") else ","
        rows = list(csv.reader(f, delimiter=delim))
    codes = {}
    for r in rows:
        if not r or not r[0].strip() or r[0].strip().lower() == "code":
            continue
        name = r[1].strip() if len(r) > 1 else ""
        typ = r[2].strip() if len(r) > 2 else "Punkt"
        codes[r[0].strip()] = (name, typ)
    return codes


def parse_code_text(text):
    """Codes aus einem Textfeld: 'BO:Linie, GEB:Linie, LM, SD' -> {code: ('', typ)}."""
    codes = {}
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        code, _, typ = part.partition(":")
        codes[code.strip()] = ("", typ.strip() or "Punkt")
    return codes


def is_line(typ):
    return str(typ).strip().lower() in ("linie", "line", "l")


def check_unknown(points, codes):
    return [(UNKNOWN, p["fid"], p["pkt"], p["code"],
             _msg("unknown", c=p["code"]))
            for p in points if str(p["code"]).strip() not in codes]


def check_duplicates(points):
    groups = defaultdict(list)
    for p in points:
        groups[str(p["pkt"])].append(p)
    errors = []
    for pkt, ps in groups.items():
        if len(ps) < 2:
            continue
        d = max(math.hypot(a["x"] - b["x"], a["y"] - b["y"]) for a in ps for b in ps)
        for p in ps[1:]:
            errors.append((DUPLICATE, p["fid"], pkt, p["code"],
                           _msg("duplicate", n=len(ps), d=d * 1000)))
    return errors


def check_single_lines(points, codes):
    groups = defaultdict(list)
    for p in points:
        code = str(p["code"]).strip()
        if code in codes and is_line(codes[code][1]):
            groups[(code, str(p.get("linie") or ""))].append(p)
    return [(SINGLE, ps[0]["fid"], ps[0]["pkt"], code,
             _msg("single", c=code, l=line or "–"))
            for (code, line), ps in groups.items() if len(ps) == 1]


def check_heights(points, tolerance, k=4):
    """Höhe eines Punktes mit dem Median der k nächsten Punkte mit gleichem Code vergleichen.
    Gleicher Code, damit z. B. Gebäudeecken nicht mit Straßenpunkten verglichen werden."""
    by_code = defaultdict(list)
    for p in points:
        if p.get("h") is not None:
            by_code[str(p["code"]).strip()].append(p)
    errors = []
    for code, pts in by_code.items():
        if len(pts) <= 2:
            continue
        kk = min(k, len(pts) - 1)
        for p in pts:
            near = sorted((q for q in pts if q is not p),
                          key=lambda q: (q["x"] - p["x"]) ** 2 + (q["y"] - p["y"]) ** 2)[:kk]
            hs = sorted(q["h"] for q in near)
            med = (hs[len(hs) // 2] + hs[(len(hs) - 1) // 2]) / 2
            diff = p["h"] - med
            if abs(diff) > tolerance:
                errors.append((HEIGHT, p["fid"], p["pkt"], p["code"],
                               _msg("height", d=diff, c=code)))
    return errors


def build_lines(points, codes):
    """Linienpunkte nach Code und Liniennummer verbinden (Reihenfolge = Punktnummer).
    Gibt Liste (code, linie, [(x, y), ...]) zurück."""
    groups = defaultdict(list)
    for p in points:
        code = str(p["code"]).strip()
        if code in codes and is_line(codes[code][1]):
            groups[(code, str(p.get("linie") or ""))].append(p)

    def key(p):
        s = str(p["pkt"])
        return (0, float(s)) if s.replace(".", "", 1).isdigit() else (1, s)
    return [(code, line, [(p["x"], p["y"]) for p in sorted(ps, key=key)])
            for (code, line), ps in groups.items() if len(ps) >= 2]
