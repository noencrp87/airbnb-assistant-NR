🏡 Airbnb Assistant – RAG + LLM + Ollama

Asistente inteligente para anfitriones de Airbnb

Chatbot local que responde mensajes de huéspedes utilizando:

RAG (búsqueda en base de conocimiento propia)

Ollama como motor LLM local

Reconocimiento de intención & fechas

Lectura de disponibilidad vía iCal

Redacción automática de respuestas cordiales

Streamlit como interfaz web

Ideal para automatizar respuestas, acelerar consultas y centralizar información de los anuncios.

📦 Funcionalidades principales
✅ 1. Pegá el texto del huésped

Ejemplo:
“¿Está disponible del 2 al 5 de diciembre? ¿A qué hora es el check-in?”

✅ 2. El sistema realiza:

Recuperación de información exacta (check-in, amenities, reglas, etc.)

Detección de intención: disponibilidad, check-in/out, amenities, consultas generales

Extracción y normalización de fechas (incluye “a partir de…”, expresiones ambiguas, etc.)

Validación de disponibilidad leyendo el iCal real de cada propiedad

Generación de borrador de respuesta en español, amable y coherente

✅ 3. Resultado final

Un mensaje completo, revisable, que podés copiar y pegar en Airbnb, WhatsApp o mail.

🧱 Estructura del proyecto
AIRBNB-ASSISTANT/
│
├── app.py                # UI + orquestación general
├── generator.py          # prompts + llamada al LLM (Ollama)
├── retriever.py          # FAISS + SQLite (modelo RAG)
├── kb_build.py           # construye la KB (faiss.index + kb.sqlite)
├── ical_utils.py         # utilidades iCal (lectura y disponibilidad)
├── check_ical_demo.py    # script opcional para probar .ics
│
├── data/
│   ├── kb.jsonl          # base de conocimiento editable ✔
│   ├── faiss.index       # índice FAISS (se genera) ❌ no subir
│   ├── kb.sqlite         # base SQLite generada ❌ no subir
│
├── .env                  # credenciales locales ❌ no subir
├── .env.example          # plantilla ✔
├── requirements.txt      # dependencias
├── .gitignore            # exclusiones para GitHub
└── README.md             # este documento

🔧 Requisitos
✔ Python 3.11

Puedes verificar tu versión con:

python --version

✔ Instalar Ollama

https://ollama.com/download

✔ Modelo recomendado

Se usa:

qwen2.5:3b-instruct


Para descargarlo:

ollama pull qwen2.5:3b-instruct


Luego ejecutar Ollama:

ollama serve

🚀 Instalación y ejecución
1. Clonar el repositorio
git clone https://github.com/noencrp87/airbnb-assistant.git
cd airbnb-assistant

2. Crear entorno virtual
Windows (PowerShell)
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1

3. Instalar dependencias
pip install --upgrade pip
pip install -r requirements.txt

4. Crear archivo .env

Duplicar la plantilla:

cp .env.example .env


Completar dentro del archivo .env:

# Ollama
OLLAMA_HOST="http://localhost:11434"
OLLAMA_MODEL="qwen2.5:3b-instruct"

# iCal URLs (exportadas desde Airbnb)
ICAL_RECOLETA="https://URL_ICS_RECOLETA"
ICAL_PARAGUAY="https://URL_ICS_PARAGUAY"

5. Construir la base de conocimiento (KB)

Cada vez que edites data/kb.jsonl, corré:

python kb_build.py


Esto genera:

data/faiss.index

data/kb.sqlite

6. Ejecutar la aplicación
python -m streamlit run app.py


Abrirá la app en:
👉 http://localhost:8501

📚 Cómo editar la Base de Conocimiento (KB)

El archivo que sí se edita es:

data/kb.jsonl


Formato: una línea JSON válida por fragmento.

Ejemplo:

{"property_id": "MICRO-PARAGUAY-870", "section": "checkin", "lang": "es", "text": "Check-in a partir de las 15:00. Instrucciones 24 h antes."}


Después de cada cambio:

python kb_build.py

🧪 Probar iCal directamente

Opcional, útil para verificar links ICS:

python check_ical_demo.py

🔒 Seguridad y buenas prácticas

El repositorio no debe contener:

.env

data/faiss.index

data/kb.sqlite

.venv/

__pycache__/

Todo esto está protegido por .gitignore.

❗️ Errores comunes y soluciones
❌ “model not found”

No descargaste el modelo:

ollama pull qwen2.5:3b-instruct

❌ “Could not open data/faiss.index”

No corriste:

python kb_build.py

❌ “ModuleNotFoundError” (faiss, sentence-transformers, dateparser, etc.)

Ejecutar:

pip install -r requirements.txt

❌ No funciona Streamlit o no abre localhost

Cerrá la consola, reactivá venv y probá:

python -m streamlit run app.py

✨ Créditos

Proyecto creado por Sabrina Jablonski - Noelia Ramírez - Victor Ruiz
Maestría en Ciencia de Datos – Universidad Austral
