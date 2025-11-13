# app.py
import re
import sqlite3
import unicodedata

import streamlit as st
from langdetect import detect
import dateparser
from jinja2 import Template

from retriever import Retriever
from generator import generate_with_llm  # Ollama JSON-out

import os
from datetime import date
from typing import List, Tuple
import re
from datetime import timedelta

from dotenv import load_dotenv
load_dotenv()

st.set_page_config(page_title="Asistente Airbnb – RAG + LLM (Ollama)", layout="wide")

# =========================
# Utilidades de texto/NLP
# =========================
def normalize(text: str) -> str:
    t = text.lower()
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    t = t.replace("-", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t

def extract_dates(text: str):
    try:
        matches = dateparser.search.search_dates(
            text, languages=["es", "en"], settings={"PREFER_DATES_FROM": "future"}
        )
        if not matches:
            return []
        out = []
        for m in matches:
            out.append((m[0], m[1].date().isoformat()))
        # únicos
        seen = set()
        unique = []
        for lit, d in out:
            if (lit, d) not in seen:
                seen.add((lit, d))
                unique.append((lit, d))
        return unique
    except Exception:
        return []

def detect_lang(text: str):
    try:
        return detect(text)
    except Exception:
        return "es"

# === Patrones (ampliados) ===
PATTERNS = {
    "checkin": [
        r"\bcheck ?in\b", r"\bingreso\b", r"\bllegada\b",
        r"\bhora de llegada\b", r"\bhorario de ingreso\b", r"\bentrada\b"
    ],
    "checkout": [
        r"\bcheck ?out\b", r"\bsalida\b", r"\bhora de salida\b",
        r"\bhorario de egreso\b", r"\begreso\b"
    ],
    "availability": [
        r"\bdisponibl(e|idad)\b", r"\breserv(ar|a|as)?\b", r"\bbooking\b",
        r"\bfecha(s)?\b", r"\bhay lugar\b", r"\bavailable\b", r"\bavailability\b",
        r"\ba\s*partir\s*de\b", r"\bdesde\s*el\b", r"\bdel\s+\d{1,2}\s+al\s+\d{1,2}\b",
        r"\bentre\s+\d{1,2}\s+y\s+\d{1,2}\b", r"\bpara\s+el\s+\d{1,2}\b"
    ],
    "amenities": [
        r"\bamenities?\b", r"\btoalla(s)?\b", r"\bsabana(s)?\b", r"\bwifi\b", r"\bwi fi\b",
        r"\bcocina\b", r"\bestacionamiento\b", r"\bcochera\b", r"\bpileta\b", r"\bpiscina\b",
        r"\bsecador de pelo\b", r"\bplancha\b", r"\bropa blanca\b", r"\bair(e)? acondicionado\b"
    ],
    "recommendations": [
        r"\brecomendacion(es)?\b", r"\bdonde comer\b", r"\brestaurante(s)?\b",
        r"\bbar(es)?\b", r"\bmuseo(s)?\b", r"\bque hacer\b", r"\bcafe(s)?\b", r"\bactividades\b"
    ],
    "pricing": [
        r"\bprecio(s)?\b", r"\btarifa(s)?\b", r"\bcosto(s)?\b",
        r"\bcuanto sale\b", r"\bhow much\b", r"\bprice\b"
    ],
    "policy": [
        r"\bcancelaci(ón|on)\b", r"\bcancelar\b", r"\bnorma(s)?\b",
        r"\bpolitica(s)?\b", r"\bregla(s)?\b"
    ],
}

# Meses en español (para detectar cues de fecha en texto aunque el parser falle)
MONTHS_ES = r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)"

DATE_CUES = [
    rf"\b\d{{1,2}}/{1,2}\d{{1,2}}/\d{{2,4}}\b",              # 01/12/2025
    rf"\b\d{{1,2}}/\d{{1,2}}\b",                             # 01/12
    rf"\b\d{{1,2}}\s+de\s+{MONTHS_ES}\b",                    # 1 de diciembre
    rf"\b{MONTHS_ES}\s+\d{{1,2}}\b",                         # diciembre 1
    r"\ba\s*partir\s*de\b", r"\bdesde\s*el\b", r"\bdel\b.*\bal\b",
]

def has_date_cues(text: str) -> bool:
    t = normalize(text)
    for rx in DATE_CUES:
        if re.search(rx, t):
            return True
    return False


def classify_intent(text: str, dates_found: list) -> str:
    t = normalize(text)
    # Si hay fechas y señales de reserva → availability
    if dates_found:
        for rx in PATTERNS["availability"]:
            if re.search(rx, t):
                return "availability"
    # Prioridades específicas
    for label in ["checkin", "checkout", "amenities", "recommendations", "pricing", "policy", "availability"]:
        for rx in PATTERNS[label]:
            if re.search(rx, t):
                return label
    return "other"

def guess_guest_name(text: str):
    t = normalize(text)
    m = re.search(r"\bsoy ([a-zñ]+)\b", t)
    if m:
        return m.group(1).title()
    m = re.search(r"\bme llamo ([a-zñ]+)\b", t)
    if m:
        return m.group(1).title()
    return None

def pick_section_snippets(chunks, preferred_section: str, k=2):
    if not chunks:
        return []
    preferred = [c for c in chunks if c.get("section") == preferred_section] if preferred_section else []
    others = [c for c in chunks if not preferred_section or c.get("section") != preferred_section]
    out = []
    for c in preferred:
        if len(out) < k:
            out.append(c)
    for c in others:
        if len(out) < k:
            out.append(c)
    return out

# ---- Normalización de intención a "availability" ----
AVAIL_ALIASES = {
    # en inglés
    "availability", "availability_check", "booking", "confirm_reservation",
    # en español (varias variantes que suelen salir del LLM)
    "disponibilidad", "consulta_disponibilidad", "consulta disponibilidad",
    "confirmacion_reserva", "confirmación_reserva", "confirmacion de reserva",
    "consulta_reserva", "consulta de reserva", "reserva"
}

def normalize_intent(intent: str, text: str, dates_found: list[str]) -> str:
    t = normalize(text)
    i = (intent or "").strip().lower()

    # 1) Aliases
    if i in AVAIL_ALIASES:
        return "availability"

    # 2) Si hay señales fuertes de reserva + fechas detectadas
    if dates_found and re.search(r"\b(disponible|disponibilidad|reserv(ar|a)|booking|hay lugar)\b", t):
        return "availability"

    # 3) NUEVO: si hay "cues" de fecha (a partir de / desde / 1 de diciembre, etc.) + palabra de reserva
    if has_date_cues(text) and re.search(r"\b(disponible|disponibilidad|reserv(ar|a)|booking|hay lugar)\b", t):
        return "availability"

    return i or "other"



# =========================
# Plantilla (fallback sin LLM)
# =========================
BASE = """Hola {{guest_name or ''}}:
{% if intent=='availability' -%}
Gracias por tu consulta. Para verificar disponibilidad necesitamos las fechas exactas (check-in y check-out). {% if dates %}Recibimos: {{ dates | join(', ') }}.{% endif %} Apenas nos confirmes, lo cotejamos en el calendario y te avisamos.
{%- elif intent=='amenities' -%}
Te detallo lo más relevante del alojamiento:
{{ ctx_summary }}
Si necesitás algo específico, contanos y lo confirmamos.
{%- elif intent=='checkin' -%}
Sobre el check-in:
{{ ctx_summary }}
Si tu horario de llegada cambia, avisá así coordinamos.
{%- elif intent=='checkout' -%}
Sobre el check-out:
{{ ctx_summary }}
Podemos evaluar late check-out según disponibilidad.
{%- elif intent=='policy' -%}
Políticas y normas:
{{ ctx_summary }}
Si tenés una duda puntual, decinos y la aclaramos.
{%- elif intent=='pricing' -%}
Las tarifas varían según fechas y demanda. Si nos indicás período y cantidad de huéspedes, te pasamos el costo actualizado.
{%- elif intent=='recommendations' -%}
¡Genial! Podemos sugerirte lugares cerca del alojamiento (comida/café/actividades). Contanos preferencias y presupuesto.
{%- else -%}
¡Gracias por escribirnos! ¿Podrías ampliar un poco la consulta (fechas, cantidad de huéspedes, intereses)? Así te respondemos con precisión.
{%- endif %}

Quedo atento/a,
{{signature}}
"""

def compose_reply(context):
    tpl = Template(BASE)
    return tpl.render(**context)

# =========================
# Datos / RAG
# =========================
@st.cache_data
def load_property_ids(db_path="data/kb.sqlite"):
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT property_id FROM kb ORDER BY property_id;")
        props = [r[0] for r in cur.fetchall()]
        conn.close()
        return props
    except Exception:
        return []

@st.cache_resource
def get_retriever():
    return Retriever()

# =========================
# UI
# =========================
st.title("Asistente para anfitriones – RAG + LLM local (Ollama)")
st.caption("MVP de Text Mining/NLP: IR (FAISS), clasificación de intención, generación con grounding.")

col1, col2 = st.columns([2, 1], gap="large")
with col1:
    email_text = st.text_area(
        "Correo del huésped (texto plano):",
        height=260,
        placeholder="Ej: Hola! ¿A qué hora es el check-in? Llego el 15 y me voy el 18. ¿Tienen toallas y buen WiFi?"
    )
    run = st.button("Procesar", use_container_width=True)

with col2:
    st.subheader("Parámetros del host")
    signature = st.text_input("Firma", value="Equipo de Atención")
    # Cargar propiedades desde KB
    props = load_property_ids()
    options = ["(sin filtro)"] + props if props else ["(sin filtro)"]
    property_id_choice = st.selectbox("Propiedad", options=options, index=1 if len(options) > 1 else 0)
    property_id = None if property_id_choice == "(sin filtro)" else property_id_choice
    use_llm = st.checkbox("Usar LLM (Ollama) para redactar y clasificar", value=True,
                          help="Requiere tener Ollama corriendo con un modelo como qwen2.5:3b-instruct.")

# ===== Helpers de fechas =====
from datetime import date
from typing import List, Tuple

def to_date(iso: str) -> date:
    y, m, d = map(int, iso.split("-"))
    return date(y, m, d)

def infer_ranges(dates_iso: List[str]) -> List[Tuple[date, date]]:
    ds = sorted({d for d in dates_iso})
    if len(ds) < 2:
        return []
    return [(to_date(ds[0]), to_date(ds[-1]))]


def normalize_future_dates(email_text: str, dates_iso: list[str], today: date | None = None) -> tuple[list[str], bool]:
    """
    - Si el usuario NO menciona año explícito en el texto, reasignamos todas las fechas al año vigente.
    - Luego, garantizamos que TODAS queden en el futuro (si no, vamos sumando años).
    - Devuelve: (fechas_normalizadas, hubo_cambios)
    """
    if today is None:
        today = date.today()

    # ¿El usuario mencionó explícitamente un año?
    years_in_text = set(re.findall(r'\b(20\d{2})\b', email_text))
    has_explicit_year = bool(years_in_text)

    fixed, changed = [], False
    for iso in (dates_iso or []):
        try:
            y, m, d = map(int, iso.split("-"))
            # Si NO hay año explícito en el texto, imponemos el año vigente
            if not has_explicit_year:
                y = today.year
                changed = True  # porque pisamos el año que venía del parser/LLM

            dt = date(y, m, d)

            # Forzar futuro: si quedó en el pasado, saltamos años hasta que sea futuro
            while dt < today:
                y += 1
                dt = date(y, m, d)
                changed = True

            fixed.append(dt.isoformat())
        except Exception:
            # Si vino una fecha inválida la ignoramos
            continue

    return fixed, changed

# ===== PRE-PARSER: “a partir de / desde el …” =====


APARTIR_PAT = re.compile(
    r'\b(?:a\s*partir\s*de|desde)\s*el?\s*('
    r'\d{1,2}\s*de\s*[a-záéíóú]+'             # 1 de diciembre
    r'|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?'     # 1/12 o 1/12/2025 o 1-12
    r'|\d{1,2}'                                # 1 (sin mes, el parser usa contexto)
    r')',
    flags=re.IGNORECASE
)

def preparse_from_date(text: str) -> list[str] | None:
    """
    Detecta expresiones tipo “a partir del 3 de febrero / desde el 3 de febrero”.
    Devuelve 2 fechas ISO [start, end] asumiendo 1 noche si no hay checkout explícito.
    Si no encuentra nada, devuelve None.
    """
    m = APARTIR_PAT.search(text or "")
    if not m:
        return None

    literal = m.group(0)
    dt = dateparser.parse(
        literal,
        languages=["es"],
        settings={"PREFER_DATES_FROM": "future"}
    )
    if not dt:
        return None

    start = dt.date()
    end = start + timedelta(days=1)  # por defecto 1 noche
    return [start.isoformat(), end.isoformat()]


# ===== iCal: cargar variables de entorno (.env) y helper =====
from dotenv import load_dotenv
load_dotenv()  # carga .env -> os.environ

import os

def get_ical_url(property_id: str) -> str:
    """
    Lee SOLO desde .env / os.environ (no usa st.secrets).
    """
    if not property_id:
        return ""
    mapping = {
        "RECOLETA-PATIO": os.environ.get("ICAL_RECOLETA", ""),
        "MICRO-PARAGUAY-870": os.environ.get("ICAL_PARAGUAY", ""),
    }
    return mapping.get(property_id, "")

# ===== Controles de fechas en UI (para pruebas, y para Debug iCal) =====
with col2:
    st.subheader("Fechas de prueba (UI)")
    ui_start_date = st.date_input("Check-in (fecha)", value=date.today())
    ui_end_date   = st.date_input("Check-out (fecha)", value=date.today())

# URL iCal para la propiedad elegida (se calcula una sola vez)
ical_url = get_ical_url(property_id)

# ===== BLOQUE PRINCIPAL =====
if run and email_text.strip():
    retr = get_retriever()
    ctx_chunks = retr.retrieve(email_text, k=8, property_id=property_id)
    pre_dates = preparse_from_date(email_text) or []

    # ---------- 1) PRIMERA PASADA ----------
    llm_ok = False
    intent = "other"
    lang = "es"
    dates_norm = []
    cites = []
    draft = ""

    if use_llm:
        try:
            r1 = generate_with_llm(
                email_text=email_text,
                property_id=property_id,
                ctx_snippets=ctx_chunks,
                style="calido",
                signature=signature,
                seed=7,
                extra_facts=None
            )
            intent = r1.get("intent", "other")
            lang = r1.get("language", "es")
            dates_norm = r1.get("dates", []) or pre_dates
            dates_norm, _fixed1 = normalize_future_dates(email_text, dates_norm)    
            draft = r1.get("draft", "")
            cites = r1.get("citations", [])
            intent = normalize_intent(intent, email_text, dates_norm)
            llm_ok = True
            if not dates_norm:
                dp = extract_dates(email_text)  # tu helper devuelve [(literal, ISO)]
                dates_norm = [d for (_, d) in dp]
        except Exception as e:
            st.warning(f"Ollama no respondió: {e}. Usando modo fallback…")
            llm_ok = False

    if not llm_ok:
        # ---- Fallback clásico (sin LLM) ----
        lang = detect_lang(email_text)
        dates = extract_dates(email_text)
        intent = classify_intent(email_text, dates_found=dates)
        intent = normalize_intent(intent, email_text, [d for (_, d) in dates])
        section_map = {"checkin":"checkin", "checkout":"checkout", "amenities":"amenities", "policy":"politica"}
        preferred_section = section_map.get(intent)
        focused = pick_section_snippets(ctx_chunks, preferred_section, k=2)
        ctx_summary = " ".join([f"[{c['section']}] {c['text']}" for c in focused]) if focused else ""
        dates_norm = [d for (_, d) in dates] if dates else []
        if not dates_norm and pre_dates:
            dates_norm = pre_dates
        dates_norm, _fixed2 = normalize_future_dates(email_text, dates_norm)
        guest_name = guess_guest_name(email_text)
        ctx = {
            "guest_name": guest_name,
            "intent": intent,
            "signature": signature,
            "ctx_summary": ctx_summary,
            "dates": dates_norm if dates_norm else None
        }
        draft = compose_reply(ctx)
        cites = [f"[{c['section']}] {c['text']}" for c in focused[:2]]

    # ---------- 2) iCal si la intención es availability ----------
    availability_fact = None
    if intent == "availability":
        from ical_utils import is_available

        ranges = infer_ranges(dates_norm)

        if not property_id:
            availability_fact = "Para verificar disponibilidad necesito saber a cuál propiedad corresponde la consulta."
        elif not ical_url:
            availability_fact = "No puedo verificar disponibilidad automáticamente porque la propiedad no tiene URL iCal configurada."
        elif not ranges:
            availability_fact = "Para verificar disponibilidad, necesito dos fechas (check-in y check-out)."
        else:
            start_d, end_d = ranges[0]
            if end_d <= start_d:
                availability_fact = "El check-out debe ser posterior al check-in. ¿Podrías confirmar las fechas?"
            else:
                res = is_available(ical_url, start_d, end_d)
                if res["available"]:
                    availability_fact = f"Disponible del {start_d.strftime('%d/%m/%Y')} al {end_d.strftime('%d/%m/%Y')}."
                else:
                    if res["conflicts"]:
                        c0 = res["conflicts"][0]
                        availability_fact = (
                            f"No disponible entre el {start_d.strftime('%d/%m/%Y')} y el {end_d.strftime('%d/%m/%Y')}. "
                            f"Conflicto: {c0['start'][:10].replace('-', '/')} → {c0['end'][:10].replace('-', '/')}."
                        )
                    else:
                        availability_fact = "No disponible en esas fechas."

    # ---------- 3) SEGUNDA PASADA / INTEGRACIÓN DEL HECHO ----------
    if availability_fact:
        facts = [f"[HECHO_VERIFICADO] {availability_fact}"]
        if llm_ok:
            r2 = generate_with_llm(
                email_text=email_text,
                property_id=property_id,
                ctx_snippets=ctx_chunks,
                style="calido",
                signature=signature,
                seed=7,
                extra_facts=facts
            )
            draft = r2.get("draft", draft)
            cites = r2.get("citations", cites)
        else:
            draft = draft.rstrip() + f"\n\nActualización de disponibilidad: {availability_fact}"


    # ---------- Panel de análisis ----------
    st.markdown("### Análisis")
    st.write(f"- **Intención:** `{intent}`")
    st.write(f"- **Idioma detectado:** {lang}")
    if dates_norm:
        st.write("- **Fechas detectadas:**")
        for d in dates_norm:
            st.write(f"  • {d}")
    else:
        st.write("- **Fechas detectadas:** ninguna")
    st.write(f"- **Propiedad filtro:** `{property_id or 'ninguno'}`")
    if availability_fact:
        st.info(f"**Hecho iCal**: {availability_fact}")

    # Fragmentos recuperados
    if ctx_chunks:
        with st.expander("🔎 Fragmentos recuperados de la KB (top-k)"):
            for i, ch in enumerate(ctx_chunks, start=1):
                st.markdown(f"**[{i}]** `{ch['property_id']}` · *{ch['section']}* · score: {ch['score']:.3f}")
                st.write(ch["text"])

    # Borrador final
    st.markdown("### Borrador de respuesta")
    st.text_area("Respuesta sugerida", draft, height=280)

    # Citaciones usadas por el LLM o por el fallback
    if cites:
        with st.expander("📎 Citas / fundamento"):
            for c in cites[:4]:
                st.write("- " + c)

# ===== Debug iCal (usa la misma ical_url ya calculada y las fechas del panel de la derecha) =====
from ical_utils import debug_list_intervals
with st.expander("🔧 Debug iCal (eventos leídos del .ics)"):
    if property_id and ical_url:
        try:
            dbg = debug_list_intervals(ical_url, ui_start_date, ui_end_date)
            if not dbg:
                st.write("No se leyeron eventos en este rango.")
            for ev in dbg:
                st.write(f"- {ev['title']} :: {ev['start']} → {ev['end']}")
        except Exception as e:
            st.error(f"Error leyendo iCal: {e}")
    else:
        st.caption("Seleccioná una propiedad y asegurate de tener configurada la URL iCal.")





