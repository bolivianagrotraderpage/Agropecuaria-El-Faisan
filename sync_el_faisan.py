"""
Fetches published Google Sheet CSVs (from the "El Faisán — Registro de
Lotes" workbook) and writes processed/history.json for the dashboard.

Four sheets are read, each published separately (File > Share > Publish
to web > (sheet) > Comma-separated values (.csv)):

1. NUEVO_LOTE_CSV_URL      - "Nuevo Lote" tab. One row per lote: which
                              núcleo/galpón it's in, when it started, how
                              many pollitos went in. Used to know which
                              lotes exist and as the base for "activos".

2. CONTROL_SEMANAL_CSV_URL - "Control Semanal" tab. One row per weekly
                              check-in per lote (peso, cantidad viva).
                              Used to build the week-by-week growth /
                              mortality curves for lotes still active.

3. RESUMEN_LOTE_CSV_URL    - "Resumen por Lote" tab. Already computed by
                              the spreadsheet's own SUMIFS formulas - a
                              lote shows up here with a "Fecha venta"
                              once its final control is marked. Nothing
                              is recomputed in Python; these numbers are
                              read as-is, same philosophy as the
                              Agrotrader sync script.

4. RANGOS_ESPERADOS_CSV_URL - "Rangos esperados" tab. Editable weekly
                              peso/mortalidad bands, used to shade the
                              "expected range" behind each lote's curve
                              on the dashboard.

Leave any URL as the placeholder to skip that source without breaking
the sync (the dashboard just shows its empty state for that part).
"""

import csv
import json
import sys
import urllib.request
from collections import defaultdict
from datetime import date, datetime
from io import StringIO
from pathlib import Path

NUEVO_LOTE_CSV_URL = "PASTE_NUEVO_LOTE_PUBLISHED_CSV_LINK_HERE"
CONTROL_SEMANAL_CSV_URL = "PASTE_CONTROL_SEMANAL_PUBLISHED_CSV_LINK_HERE"
RESUMEN_LOTE_CSV_URL = "PASTE_RESUMEN_POR_LOTE_PUBLISHED_CSV_LINK_HERE"
RANGOS_ESPERADOS_CSV_URL = "PASTE_RANGOS_ESPERADOS_PUBLISHED_CSV_LINK_HERE"

# Physical layout of the farm - not data from a sheet, since it doesn't
# change day to day. Update here if a núcleo or galpón is added/removed.
NUCLEOS = [
    {"key": "n1", "label": "Núcleo 1", "sheet_name": "Núcleo 1", "galpones": 4},
    {"key": "n2", "label": "Núcleo 2", "sheet_name": "Núcleo 2", "galpones": 4},
    {"key": "n3", "label": "Núcleo 3", "sheet_name": "Núcleo 3", "galpones": 4},
    {"key": "n4", "label": "Núcleo 4", "sheet_name": "Núcleo 4", "galpones": 4},
    {"key": "n5", "label": "Núcleo 5", "sheet_name": "Núcleo 5", "galpones": 4},
]
NUCLEO_KEY_BY_LABEL = {n["sheet_name"]: n["key"] for n in NUCLEOS}


def fetch_csv(url: str, required_marker: str | None = None) -> str | None:
    """Fetches a published-CSV URL. Returns None (without raising) if the
    URL is still the placeholder, so optional sources can be skipped."""
    if not url or url.startswith("PASTE_"):
        return None

    req = urllib.request.Request(url, headers={"User-Agent": "sync-el-faisan"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status != 200:
                sys.exit(f"ERROR: Sheet fetch returned HTTP {resp.status} for {url}")
            text = resp.read().decode("utf-8")
    except Exception as e:
        sys.exit(f"ERROR: Could not fetch published sheet CSV ({url}): {e}")

    if required_marker and required_marker not in text:
        sys.exit(
            "ERROR: Fetched content doesn't look like the expected CSV "
            f"(missing '{required_marker}' header) for {url}. Aborting without writing."
        )
    return text


def to_float(v):
    v = (v or "").strip().replace(",", "")
    if v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def to_fraction(v):
    """Percent cells may publish as '4.00%' or as a plain decimal like
    '0.04' depending on how Sheets exports them - handle both."""
    v = (v or "").strip()
    if v == "":
        return None
    if v.endswith("%"):
        num = to_float(v[:-1])
        return None if num is None else num / 100.0
    return to_float(v)


def to_date(v):
    v = (v or "").strip()
    if v == "":
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def nucleo_key(raw_label: str) -> str:
    raw_label = (raw_label or "").strip()
    return NUCLEO_KEY_BY_LABEL.get(raw_label, raw_label.lower().replace(" ", "_"))


def lote_key(nucleo, galpon, lote):
    return f"{(nucleo or '').strip()}|{(galpon or '').strip()}|{(lote or '').strip()}"


# --- 1. Nuevo Lote: which lotes exist, and their start info -------------
def parse_nuevo_lote(csv_text: str) -> dict:
    lotes = {}
    for row in csv.DictReader(StringIO(csv_text)):
        nucleo, galpon, lote = row.get("Núcleo"), row.get("Galpón"), row.get("Lote")
        if not (nucleo and galpon and lote):
            continue
        lotes[lote_key(nucleo, galpon, lote)] = {
            "nucleo": nucleo.strip(),
            "galpon": galpon.strip(),
            "lote": lote.strip(),
            "fecha_ingreso": to_date(row.get("Fecha de ingreso")),
            "cantidad_inicial": to_float(row.get("Cantidad de pollitos ingresados")),
        }
    return lotes


# --- 2. Control Semanal: weekly peso/mortalidad curve per lote ----------
def parse_control_semanal(csv_text: str, nuevo_lote: dict) -> dict:
    """Returns {lote_key: {"semanas": [...], "peso": [...], "mortalidad": [...],
    "es_final": bool}} built from every weekly row for that lote, ordered
    by control date. 'semana' is weeks elapsed since Fecha de ingreso."""
    rows_by_lote = defaultdict(list)
    for row in csv.DictReader(StringIO(csv_text)):
        nucleo, galpon, lote = row.get("Núcleo"), row.get("Galpón"), row.get("Lote")
        if not (nucleo and galpon and lote):
            continue
        fecha = to_date(row.get("Fecha del control"))
        if fecha is None:
            continue
        rows_by_lote[lote_key(nucleo, galpon, lote)].append({
            "fecha": fecha,
            "peso": to_float(row.get("Peso promedio (kg)")),
            "mortalidad": to_fraction(row.get("% Mortalidad acumulada")),
            "es_final": (row.get("Es control final") or "").strip().lower() == "sí",
        })

    curves = {}
    for key, rows in rows_by_lote.items():
        rows.sort(key=lambda r: r["fecha"])
        ingreso = nuevo_lote.get(key, {}).get("fecha_ingreso")
        semanas, pesos, morts = [], [], []
        for r in rows:
            if ingreso:
                semana = round((r["fecha"] - ingreso).days / 7)
            else:
                semana = len(semanas)
            semanas.append(semana)
            pesos.append(r["peso"])
            morts.append(None if r["mortalidad"] is None else round(r["mortalidad"] * 100, 2))
        curves[key] = {
            "semanas": semanas,
            "peso": pesos,
            "mortalidad": morts,
            "es_final": rows[-1]["es_final"] if rows else False,
        }
    return curves


# --- 3. Resumen por Lote: already-computed totals for closed lotes ------
def parse_resumen_por_lote(csv_text: str) -> list:
    """Nothing is computed here - the spreadsheet's own SUMIFS formulas
    already did the math. A row counts as a closed lote once it has a
    'Fecha venta'."""
    cerrados = []
    for row in csv.DictReader(StringIO(csv_text)):
        fecha_venta = to_date(row.get("Fecha venta"))
        if fecha_venta is None:
            continue
        cerrados.append({
            "nucleo": (row.get("Núcleo") or "").strip(),
            "galpon": (row.get("Galpón") or "").strip(),
            "lote": (row.get("Lote") or "").strip(),
            "fecha_venta": fecha_venta.isoformat(),
            "mortalidad": to_fraction(row.get("% Mortalidad final")),
            "costo_pollo": to_float(row.get("Costo por pollo")),
            "precio_venta": to_float(row.get("Precio venta/kg")),
            "ganancia": to_float(row.get("Ganancia")),
        })
    cerrados.sort(key=lambda l: l["fecha_venta"])
    return cerrados


# --- 4. Rangos esperados: editable weekly peso/mortalidad bands ---------
def parse_rangos_esperados(csv_text: str) -> list:
    rangos = []
    for row in csv.DictReader(StringIO(csv_text)):
        semana = to_float(row.get("Semana"))
        if semana is None:
            continue
        rangos.append({
            "semana": int(semana),
            "peso_min": to_float(row.get("Peso mínimo esperado (kg)")),
            "peso_max": to_float(row.get("Peso máximo esperado (kg)")),
            "mort_min": to_fraction(row.get("Mortalidad mínima acumulada esperada")),
            "mort_max": to_fraction(row.get("Mortalidad máxima acumulada esperada")),
        })
    rangos.sort(key=lambda r: r["semana"])
    return rangos


def build_nucleo_summary(nuevo_lote: dict, curves: dict, cerrados: list) -> list:
    cerrados_keys = {lote_key(l["nucleo"], l["galpon"], l["lote"]) for l in cerrados}
    activos = {k: v for k, v in nuevo_lote.items() if k not in cerrados_keys}

    galpones_activos_por_nucleo = defaultdict(set)
    lotes_activos_por_nucleo = defaultdict(int)
    pollos_vivos_por_nucleo = defaultdict(float)

    for key, info in activos.items():
        nk = nucleo_key(info["nucleo"])
        galpones_activos_por_nucleo[nk].add(info["galpon"])
        lotes_activos_por_nucleo[nk] += 1
        curve = curves.get(key)
        if curve and curve["mortalidad"]:
            # pollos vivos ~= cantidad inicial * (1 - mortalidad acumulada actual)
            ultima_mort = next((m for m in reversed(curve["mortalidad"]) if m is not None), None)
            cantidad_inicial = info.get("cantidad_inicial")
            if ultima_mort is not None and cantidad_inicial is not None:
                pollos_vivos_por_nucleo[nk] += cantidad_inicial * (1 - ultima_mort / 100)
            elif cantidad_inicial is not None:
                pollos_vivos_por_nucleo[nk] += cantidad_inicial
        elif info.get("cantidad_inicial") is not None:
            pollos_vivos_por_nucleo[nk] += info["cantidad_inicial"]

    summary = []
    for n in NUCLEOS:
        summary.append({
            "key": n["key"],
            "label": n["label"],
            "galpones": n["galpones"],
            "galpones_activos": len(galpones_activos_por_nucleo.get(n["key"], set())),
            "lotes_activos": lotes_activos_por_nucleo.get(n["key"], 0),
            "pollos_vivos": round(pollos_vivos_por_nucleo.get(n["key"], 0)),
        })
    return summary


def build_lotes_activos(nuevo_lote: dict, curves: dict, cerrados: list) -> list:
    cerrados_keys = {lote_key(l["nucleo"], l["galpon"], l["lote"]) for l in cerrados}
    lotes = []
    for key, info in nuevo_lote.items():
        if key in cerrados_keys:
            continue
        curve = curves.get(key, {"semanas": [], "peso": [], "mortalidad": []})
        lotes.append({
            "lote": info["lote"],
            "galpon": info["galpon"],
            "nucleo": info["nucleo"],
            "semanas": curve["semanas"],
            "peso": curve["peso"],
            "mortalidad": curve["mortalidad"],
        })
    lotes.sort(key=lambda l: l["lote"])
    return lotes


def main():
    nuevo_lote_csv = fetch_csv(NUEVO_LOTE_CSV_URL, required_marker="Lote")
    control_csv = fetch_csv(CONTROL_SEMANAL_CSV_URL, required_marker="Lote")
    resumen_csv = fetch_csv(RESUMEN_LOTE_CSV_URL, required_marker="Lote")
    rangos_csv = fetch_csv(RANGOS_ESPERADOS_CSV_URL, required_marker="Semana")

    nuevo_lote = parse_nuevo_lote(nuevo_lote_csv) if nuevo_lote_csv else {}
    curves = parse_control_semanal(control_csv, nuevo_lote) if control_csv else {}
    cerrados = parse_resumen_por_lote(resumen_csv) if resumen_csv else []
    rangos = parse_rangos_esperados(rangos_csv) if rangos_csv else []

    if not nuevo_lote:
        print("[sync] 'Nuevo Lote' not fetched or empty - nucleos/lotes activos will be empty.")
    if not control_csv:
        print("[sync] 'Control Semanal' not fetched or empty - growth curves will be empty.")
    if not resumen_csv:
        print("[sync] 'Resumen por Lote' not fetched or empty - lotes cerrados will be empty.")
    if not rangos_csv:
        print("[sync] 'Rangos esperados' not fetched or empty - chart bands will be empty.")

    output = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "nucleos": build_nucleo_summary(nuevo_lote, curves, cerrados),
        "lotes_activos": build_lotes_activos(nuevo_lote, curves, cerrados),
        "lotes_cerrados": cerrados,
        "rangos_esperados": rangos,
    }

    out_path = Path("processed/history.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(
        f"Wrote processed/history.json - "
        f"{len(output['lotes_activos'])} lote(s) activos, "
        f"{len(output['lotes_cerrados'])} lote(s) cerrados, "
        f"{len(output['rangos_esperados'])} fila(s) de rangos."
    )


if __name__ == "__main__":
    main()
