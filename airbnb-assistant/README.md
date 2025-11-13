# Asistente para Anfitriones – RAG + LLM (Ollama)

Chatbot en **Streamlit** que responde correos de huéspedes para propiedades en Airbnb.
Combina **RAG** (búsqueda en tu propia KB), **NLP** (intención/fechas, multi-idioma básico) y verificación de **disponibilidad por iCal**. Redacta respuestas cordiales en español usando un **LLM local** vía **Ollama**.

---

## 📦 ¿Qué hace?

1. Le pegás el texto del huésped (ej.: *“¿Está disponible a partir del 2 de diciembre? ¿A qué hora es el check-in?”*).
2. Recupera fragmentos relevantes de la **KB** de la propiedad (check-in/out, amenities, reglas, etc.).
3. Detecta **intención** (availability, check-in, amenities, etc.) y **fechas** (con pre-parser: “a partir de…”).
4. Valida disponibilidad consultando el **iCal (.ics)** de la propiedad.
5. Genera un **borrador de respuesta** en español, amable y **apoyado en hechos** (RAG + iCal).

---

## 🗂 Estructura del repo (la que compartís)

```
AIRBNB-ASSISTANT/
├─ .venv/                    # (entorno virtual – no se sube a git)
├─ data/
│  ├─ faiss.index           # índice FAISS (generado)
│  ├─ kb.jsonl              # base de conocimiento (fuente)
│  └─ kb.sqlite             # KB en SQLite (generado)
├─ .env                      # variables (OLLAMA_HOST/MODEL, ICAL_*)
├─ app.py                    # UI + orquestación
├─ check_ical_demo.py        # script para probar iCal por consola
├─ generator.py              # cliente Ollama (prompts + JSON-out)
├─ ical_utils.py             # lectura .ics y verificación de disponibilidad
├─ kb_build.py               # construye kb.sqlite + faiss.index desde kb.jsonl
├─ requirements.txt          # dependencias (pinneadas)
└─ retriever.py              # motor de recuperación (FAISS + SQLite)
```

> **Importante:** `.env` lo tendrán tus compañeras (no se sube a GitHub).
> En GitHub podés incluir un `/.env.example` como plantilla con valores “dummy”.

---

## ✅ Requisitos

* **Python 3.11** (recomendado).
* **Ollama** instalado y corriendo: [https://ollama.com/](https://ollama.com/)
* Modelo por defecto en Ollama: **`qwen2.5:3b-instruct`**.

Preparar el modelo (una vez):

```bash
ollama serve &
ollama pull qwen2.5:3b-instruct
ollama list
```

> Si usás otro host/puerto: `export OLLAMA_HOST="http://localhost:11434"`

---

## ⚙️ Instalación local (paso a paso)

> Supongo que ya clonaron o descargaron la carpeta **AIRBNB-ASSISTANT**.

1. **Activar el entorno** (si ya viene listo, solo activarlo):

```bash
cd AIRBNB-ASSISTANT
# macOS / Linux
python3.11 -m venv .venv
source .venv/bin/activate
# (Windows PowerShell)
# py -3.11 -m venv .venv
# .venv\Scripts\Activate.ps1
```

2. **Instalar dependencias**:

```bash
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

3. **Configurar variables** en `.env` (cada una pone su archivo `.env`):

```env
# Ollama
OLLAMA_HOST="http://localhost:11434"
OLLAMA_MODEL="qwen2.5:3b-instruct"

# iCal: URL públicas del .ics (una por propiedad)
ICAL_RECOLETA="https://example.com/recoleta.ics"
ICAL_PARAGUAY="https://example.com/paraguay.ics"
```

4. **Revisar/editar la KB** en `data/kb.jsonl`.
   Formato **JSONL**: **una línea por fragmento**. Ejemplo:

```jsonl
{"property_id":"MICRO-PARAGUAY-870","section":"checkin","lang":"es","text":"Check-in a partir de las 15:00. Instrucciones 24 h antes."}
{"property_id":"RECOLETA-PATIO","section":"checkout","lang":"es","text":"Check-out hasta las 11:00. Late check-out sujeto a disponibilidad."}
```

> Secciones sugeridas: `nombre`, `ubicacion`, `descripcion`, `checkin`, `checkout`, `amenities`, `reglas`, `politica`, `trabajo_remoto`, `recomendaciones_base`, etc.

5. **Construir índice** (FAISS + SQLite) desde la KB:

```bash
python kb_build.py
```

Genera/actualiza `data/kb.sqlite` y `data/faiss.index`.

---

## ▶️ Ejecutar la app

Con **Ollama** corriendo en otra ventana:

```bash
streamlit run app.py
```

Abrí `http://localhost:8501`.

**Cómo usarla:**

* Elegí la **propiedad** (ej.: `RECOLETA-PATIO` o `MICRO-PARAGUAY-870`).
* Pegá el **mensaje del huésped**.
* Dejá tildado “Usar LLM (Ollama)…” para redacción más natural.
* Presioná **Procesar**.
* Revisá el **panel de Análisis** (intención, fechas detectadas, hecho iCal) y el **Borrador de respuesta**.

> La app incluye un **pre-parser de fechas**: entiende “a partir del …”, normaliza al **futuro** y al **año vigente** si el usuario no menciona año.

---

## 🗓 Probar iCal desde consola (opcional)

```bash
python check_ical_demo.py
```

* Muestra eventos leídos del `.ics` y resultados de `is_available()` para un rango.
* Sirve para confirmar que tu URL de iCal es correcta.

---

## 🧩 ¿Cómo agrego/actualizo contenido de la KB?

1. Editá `data/kb.jsonl` agregando nuevas líneas (fragmentos).
2. Corré **`python kb_build.py`** para reconstruir el índice.
3. Volvé a la app y probá.

> Tip: mantené **textos cortos** y **específicos** por sección; mejora el RAG.

---

## 🧪 Ejemplos de consulta

* “¿Está **disponible a partir del 2 de diciembre**? Somos 2 personas.”
* “Llego el **01/12** y me voy el **03/12**. ¿A qué hora es el **check-in**?”
* “¿Tienen **WiFi** y **cocina** completa?”

---

## 🛠 Problemas comunes

* **No detecta Jinja2 / typing_extensions** → `pip install -r requirements.txt` (incluye todo).
* **Ollama “model not found”** → `ollama pull qwen2.5:3b-instruct` y `ollama list`.
* **No toma el iCal** → verificá que la **URL .ics** en `.env` sea pública y pertenezca a la propiedad seleccionada.
* **`JSONDecodeError` al construir KB** → asegurate que `kb.jsonl` no tenga **líneas vacías** ni comas sobrantes; cada línea debe ser **JSON válido**.
* **Fechas raras** → el pre-parser fuerza **futuro** y asume el **año actual** si no se especifica.

---

## 🔒 Buenas prácticas al compartir

* **No suban** `.env`, `.venv/`, ni `data/*.index`/`*.sqlite` a GitHub público.
* Incluyan un **`.env.example`** con placeholders para que cada una lo copie a `.env`.

---

## 🗺 Roadmap (si quieren seguir)

* Embeddings semánticos con **sentence-transformers** + re-ranking.
* Integración **Gmail API** para crear borradores/responder.
* Panel para editar KB desde la UI y registrar feedback.
* Backend **FastAPI** + despliegue en HF Spaces/Render/Heroku.

---

## ✅ Checklist rápido

1. `ollama serve &` + `ollama pull qwen2.5:3b-instruct`
2. Activar `.venv` (Python 3.11)
3. `pip install -r requirements.txt`
4. Completar `.env` con `OLLAMA_*` e `ICAL_*`
5. Revisar/editar `data/kb.jsonl`
6. `python kb_build.py`
7. `streamlit run app.py` → **Listo** 💫

