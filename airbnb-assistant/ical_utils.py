# ical_utils.py
import io
import os
import requests
from datetime import datetime, timedelta, timezone, date
from typing import List, Tuple, Dict

import pytz
from icalendar import Calendar
#import recurring_ical_events

# Zona horaria de trabajo (ajusta si corresponde)
TZ = pytz.timezone("America/Argentina/Buenos_Aires")

def _to_aware(dt) -> datetime:
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return TZ.localize(datetime(dt.year, dt.month, dt.day, 0, 0))
    if isinstance(dt, datetime):
        # normalizamos todo a TZ local
        if dt.tzinfo is None:
            return TZ.localize(dt)
        return dt.astimezone(TZ)
    raise ValueError("Tipo de fecha no soportado")

def fetch_calendar(ics_url: str) -> Calendar:
    """
    Descarga el .ics y devuelve un objeto Calendar.
    """
    resp = requests.get(ics_url, timeout=30)
    resp.raise_for_status()
    return Calendar.from_ical(resp.content)

def expand_busy_intervals(cal: Calendar, start: datetime, end: datetime) -> List[Tuple[datetime, datetime, str]]:
    """
    Expande eventos (incluyendo recurrencias) entre [start, end),
    devolviendo una lista de intervalos ocupados con (inicio, fin, resumen).
    """
    # recurring_ical_events requiere objetos aware en UTC o TZ consistente
    # Usamos TZ y luego normalizamos cada evento.
    events = recurring_ical_events.of(cal).between(
        start.astimezone(pytz.utc),
        end.astimezone(pytz.utc)
    )
    busy = []
    for ev in events:
        summary = str(ev.get("summary", "Evento")).strip()
        dtstart = ev.get("dtstart")
        dtend = ev.get("dtend")

        if not dtstart:
            continue
        start_dt = _to_aware(dtstart.dt)

        # Fin exclusivo: si falta dtend, asumimos duración 1 día
        if dtend:
            end_dt = _to_aware(dtend.dt)
        else:
            # Por seguridad, 1 día
            end_dt = start_dt + timedelta(days=1)

        # Guardamos intervalo
        busy.append((start_dt, end_dt, summary))

    # Unificar solapados
    busy.sort(key=lambda x: x[0])
    merged = []
    for s, e, name in busy:
        if not merged:
            merged.append([s, e, [name]])
        else:
            last_s, last_e, names = merged[-1]
            if s <= last_e:  # solapa
                merged[-1][1] = max(last_e, e)
                names.append(name)
            else:
                merged.append([s, e, [name]])
    # Volver a tupla e incluir nombres unidos
    return [(s, e, ", ".join(names)) for s, e, names in merged]

def is_available(ics_url: str, start_date: date, end_date: date) -> Dict:
    """
    Chequea disponibilidad para el rango [start_date, end_date) en TZ.
    Devuelve dict con disponible (bool), conflictos (lista) y detalle.
    """
    # Normalizamos a rangos aware en 00:00
    start_dt = TZ.localize(datetime(start_date.year, start_date.month, start_date.day, 0, 0))
    end_dt   = TZ.localize(datetime(end_date.year, end_date.month, end_date.day, 0, 0))

    cal = fetch_calendar(ics_url)
    busy = expand_busy_intervals(cal, start_dt - timedelta(days=1), end_dt + timedelta(days=1))

    conflicts = []
    for b_start, b_end, title in busy:
        # Solapado si: start < b_end y b_start < end  (intervalos semiabiertos)
        if start_dt < b_end and b_start < end_dt:
            conflicts.append({"start": b_start.isoformat(), "end": b_end.isoformat(), "title": title})

    return {
        "available": len(conflicts) == 0,
        "conflicts": conflicts,
        "query": {"start": start_dt.isoformat(), "end": end_dt.isoformat()}
    }


def debug_list_intervals(ics_url: str, start_date: date, end_date: date) -> list[dict]:
    """
    Devuelve los intervalos ocupados (ya unificados) entre start-end para inspección en UI.
    """
    start_dt = TZ.localize(datetime(start_date.year, start_date.month, start_date.day, 0, 0))
    end_dt   = TZ.localize(datetime(end_date.year, end_date.month, end_date.day, 0, 0))
    cal = fetch_calendar(ics_url)
    busy = expand_busy_intervals(cal, start_dt - timedelta(days=1), end_dt + timedelta(days=1))
    out = []
    for s, e, title in busy:
        out.append({
            "start": s.isoformat(),
            "end": e.isoformat(),
            "title": title
        })
    return out
