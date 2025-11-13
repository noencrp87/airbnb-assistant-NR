# generator.py
from __future__ import annotations

import json
import requests
from typing import List, Dict, Any, Optional

# ---------------------------------------------------------------------
# Configuración básica del modelo local (Ollama)
# Cambia el nombre del modelo si usas otro (ej: "llama3.1:8b-instruct")
# ---------------------------------------------------------------------
OLLAMA_API = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "qwen2.5:3b-instruct"
DEFAULT_TEMPERATURE = 0.2


# ---------------------------------------------------------------------
# Utilidad para renderizar los fragmentos del RAG de forma legible
# ---------------------------------------------------------------------
def render_ctx_snippets(snippets: List[Dict[str, Any]]) -> str:
    if not snippets:
        return "(sin fragmentos)"
    lines = []
    for i, s in enumerate(snippets, start=1):
        pid = s.get("property_id", "N/A")
        sec = s.get("section", "N/A")
        txt = s.get("text", "").strip().replace("\n", " ")
        lines.append(f"[{i}] ({pid} | {sec}) {txt}")
    return "\n".join(lines[:12])  # límite razonable


# ---------------------------------------------------------------------
# Prompt base: instrucciones fuertes para RESPETAR FACTS (iCal)
# y devolver SIEMPRE el JSON con campos esperados
# ---------------------------------------------------------------------
SYSTEM_PROMPT = """Eres un asistente para anfitriones de Airbnb. Respondes en español, con tono cálido, profesional y conciso.
REGLAS:
1) Debes usar el contexto (RAG) solo como referencia; si hay discrepancias con HECHOS verificados, GANAN los HECHOS.
2) HECHOS VERIFICADOS (FACTS) tienen prioridad absoluta (ej: disponibilidad iCal).
3) Si los FACTS dicen "NO disponible", debes comunicarlo con cortesía y proponer alternativas (fechas cercanas, lista de espera, etc.).
4) Si faltan datos críticos (fechas, número de huéspedes), pide aclaración puntual.
5) No inventes políticas ni datos sensibles que no estén en el contexto o en FACTS.
6) La salida debe ser SOLO un JSON con el esquema indicado, sin texto adicional.

OBJETIVO:
- Clasificar intención del huésped (en minúsculas y sin tildes si es posible).
- Extraer fechas en lista ISO (YYYY-MM-DD), cuando existan.
- Redactar "draft" (respuesta lista para enviar).
- Incluir "citations" mínimas (2-4 frases del contexto o hechos breves usados).
- language: "es" o "en" (detectar).

"""

# Nota: En Ollama, "format":"json" fuerza que el modelo devuelva JSON puro.
# Definimos el "user prompt" como bloques bien marcados.
USER_TEMPLATE = """[EMAIL_HUESPED]
{email_text}

[PROPERTY_ID]
{property_id}

[CONTEXT_SNIPPETS]
{ctx_text}

[FACTS]
{facts_text}

[ESTILO]
Tono: {style}. Firma sugerida: {signature}

[INSTRUCCIONES DE SALIDA]
Devuelve SOLO este JSON:
{{
  "intent": "<una_palabra_o_snake_case>",
  "dates": ["YYYY-MM-DD", ...],
  "draft": "<respuesta lista para enviar, amable y profesional en español>",
  "citations": ["<cita1>", "<cita2>"],
  "language": "es"
}}
"""


def _facts_to_text(extra_facts: Optional[List[str]]) -> str:
    if not extra_facts:
        return "(sin hechos adicionales)"
    # Prepara lista corta y clara
    return "\n".join(f"- {f}" for f in extra_facts[:6])


def _call_ollama(
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = DEFAULT_TEMPERATURE,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Llama a Ollama /api/chat y devuelve el dict del JSON generado por el modelo.
    Asume que "format":"json" para respuesta JSON pura.
    """
    body = {
        "model": model,
        "format": "json",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "options": {
            "temperature": temperature,
            # Nota: algunos builds de Ollama usan "seed"; si no, lo ignora.
            **({"seed": seed} if seed is not None else {}),
        },
        "stream": False,
    }
    r = requests.post(OLLAMA_API, json=body, timeout=120)
    r.raise_for_status()
    data = r.json()

    # Estructura típica: {"message":{"role":"assistant","content":"{...json...}"}}
    content = data.get("message", {}).get("content", "").strip()
    if not content:
        raise RuntimeError("Ollama no devolvió contenido")

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        # Si falla el JSON, devolvemos forma mínima para que la app no se caiga
        return {
            "intent": "other",
            "dates": [],
            "draft": "Perdón, hubo un inconveniente técnico generando la respuesta.",
            "citations": [],
            "language": "es",
            "_raw": content,
            "_error": f"JSONDecodeError: {e}",
        }


def generate_with_llm(
    *,
    email_text: str,
    property_id: Optional[str],
    ctx_snippets: List[Dict[str, Any]],
    style: str = "calido",
    signature: str = "Equipo de Atención",
    seed: Optional[int] = 7,
    extra_facts: Optional[List[str]] = None,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
) -> Dict[str, Any]:
    """
    Genera respuesta usando LLM local (Ollama).
    - Integra RAG (ctx_snippets) y FACTS (hechos verificados: iCal).
    - Fuerza salida JSON con campos: intent, dates, draft, citations, language.
    """
    ctx_text = render_ctx_snippets(ctx_snippets)
    facts_text = _facts_to_text(extra_facts)

    user_prompt = USER_TEMPLATE.format(
        email_text=email_text.strip(),
        property_id=property_id or "(sin filtro)",
        ctx_text=ctx_text,
        facts_text=facts_text,
        style=style,
        signature=signature,
    )

    out = _call_ollama(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=temperature,
        seed=seed,
    )

    # Normalización defensiva de campos por si el modelo omite alguno
    intent = (out.get("intent") or "other").strip().lower()
    dates = out.get("dates") or []
    draft = out.get("draft") or ""
    citations = out.get("citations") or []
    language = (out.get("language") or "es").strip().lower()

    # Recortes de seguridad
    if not isinstance(dates, list):
        dates = []
    if not isinstance(citations, list):
        citations = []

    return {
        "intent": intent,
        "dates": dates,
        "draft": draft,
        "citations": citations[:6],
        "language": language,
        "_debug": out,   # útil para inspeccionar la salida cruda del modelo
    }
