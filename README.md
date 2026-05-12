<div align="center">

# 🟥 SIFECAT Assistant

**Assistent conversacional intern per a la gestió dels fons FEDER 2021-2027**
*Generalitat de Catalunya*

Un chatbot RAG en català que respon dubtes sobre l'aplicació SIFECAT
basant-se exclusivament en els manuals oficials.

![Python](https://img.shields.io/badge/python-3.12-blue?style=flat-square)
![Chainlit](https://img.shields.io/badge/UI-Chainlit-ff4f4f?style=flat-square)
![Claude](https://img.shields.io/badge/LLM-Claude_Sonnet_4.6-d97757?style=flat-square)
![LlamaIndex](https://img.shields.io/badge/RAG-LlamaIndex-9333ea?style=flat-square)
![License](https://img.shields.io/badge/license-Internal-lightgrey?style=flat-square)

</div>

---

## ✨ Què fa

SIFECAT Assistant és un xat estil ChatGPT entrenat amb els **7 manuals oficials de SIFECAT** (BECU, gestió de contractes, factures IRPF, presentació, validació, signatura i justificació d'operacions).

- 💬 Respon **sempre en català**
- 📚 Es basa **exclusivament en els manuals oficials** — no inventa res
- 🚫 Diu *"Aquesta informació no es troba als manuals consultats"* quan no té base documental
- 🔐 Accés amb usuari i contrasenya — cada usuari té el seu propi historial
- 🗂️ Historial de converses persistent estil ChatGPT
- 👍/👎 Feedback per a millorar les respostes
- ⚡ Streaming token a token, com Claude o ChatGPT

---

## 🏗️ Arquitectura

```
                                                              ┌────────────────────┐
                                                              │   📄 manuals/*.pdf │
                                                              │   (7 manuals)      │
                                                              └─────────┬──────────┘
                                                                        │ ingest.py
                                                                        ▼
┌──────────────┐        ┌──────────────┐        ┌─────────────────────────────────┐
│  👤 Usuari   │ ─────► │ 🌐 Chainlit  │ ─────► │  🧠 LlamaIndex Query Engine     │
│ (navegador)  │ ◄───── │  (login +    │ ◄───── │   ↓ top-5 chunks per similitud  │
└──────────────┘        │   xat + UI)  │        │  ┌───────────────────────────┐  │
                        └──────┬───────┘        │  │ 💾 ChromaDB (./storage/)  │  │
                               │                │  │  embeddings text-3-small  │  │
                               │                │  └───────────────────────────┘  │
                               │                │   ↓ context + pregunta          │
                               │                │  ┌───────────────────────────┐  │
                               │                │  │ 🤖 Claude Sonnet 4.6      │  │
                               │                │  │   (Anthropic API)         │  │
                               │                │  └───────────────────────────┘  │
                               │                └─────────────────────────────────┘
                               │
                               ▼
                        ┌──────────────┐
                        │ 🗃️ SQLite     │  → usuaris, threads, missatges, feedback
                        │ chat_history │
                        └──────────────┘
```

---

## 🚀 Inici ràpid

### Requisits

- **macOS** o Linux
- **Python 3.12+** (`brew install python@3.12` si no el tens)
- Una **API key d'Anthropic** ([console.anthropic.com](https://console.anthropic.com))
- Una **API key d'OpenAI** ([platform.openai.com](https://platform.openai.com))

### 1. Clonar i instal·lar

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt   # o usa la llista de paquets de l'apartat següent
```

### 2. Configurar credencials

Edita el fitxer `.env` amb les teves claus:

```bash
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-proj-...
CHAT_PASSWORD=la_teva_contrasenya_compartida
CHAINLIT_AUTH_SECRET=un_secret_llarg_i_aleatori_per_signar_JWTs
```

> 💡 Genera un secret segur amb: `python -c "import secrets; print(secrets.token_urlsafe(64))"`

### 3. Posar els manuals

Copia els PDFs a la carpeta `manuals/`:

```
manuals/
├── Manual_BECU_21-27_revM.pdf
├── Manual_Gestió_contractes_transaccions.pdf
├── Manual_acceptacio_signatura_operacio_vGM.pdf
├── Manual_factures_IRPF_SIFECAT_RevM.pdf
├── Manual_justificacio_despesa_indicadors_revM.pdf
├── Manual_presentacio_operacions_vGM.pdf
└── Manual_validacio_operacions_vGM.pdf
```

### 4. Indexar els manuals i inicialitzar la BD

```bash
python ingest.py        # crea ./storage/ amb els embeddings (~10 segons)
python init_db.py       # crea l'esquema SQLite per a l'historial
```

> Si vols reindexar després d'actualitzar els manuals: `python ingest.py --force`

### 5. Arrencar l'assistent

```bash
chainlit run app.py -h
```

Obre [http://localhost:8000](http://localhost:8000) → login amb qualsevol nom d'usuari i la contrasenya que has definit a `.env`.

---

## 🌍 Exposar-ho públicament (per a companys remots)

Llança un túnel ràpid de Cloudflare (URL temporal, regenerada en cada arrencada):

```bash
brew install cloudflared
cloudflared tunnel --url http://localhost:8000
```

Et donarà una URL tipus `https://nom-aleatori.trycloudflare.com` que pots compartir.

> ⚠️ Per a una URL **estable** i un domini propi, mira l'apartat *Roadmap*.

---

## 📂 Estructura del projecte

```
RAG_S/
├── app.py                  # App Chainlit: auth, data layer, RAG query engine
├── ingest.py               # Llegeix PDFs → chunks → embeddings → ChromaDB
├── init_db.py              # Crea l'esquema SQLite per a l'historial de xats
├── manuals/                # PDFs originals (7 manuals oficials SIFECAT)
├── storage/                # ChromaDB persistent (embeddings)  [gitignored]
├── chat_history.db         # SQLite amb usuaris, threads, feedback [gitignored]
├── public/                 # Assets estàtics
│   ├── custom.css          # Estil personalitzat (Inter font, color marca, etc.)
│   ├── favicon.png
│   ├── logo_light.png
│   ├── logo_dark.png
│   └── avatars/
│       └── SIFECAT.png     # Avatar del bot
├── .chainlit/
│   └── config.toml         # Configuració de Chainlit (tema, sidebar, CoT…)
├── chainlit.md             # Pantalla "Readme" interna de Chainlit
├── .env                    # Secrets (API keys, password, JWT secret) [gitignored]
└── .gitignore
```

---

## 🔧 Configuració avançada

### Variables d'entorn (`.env`)

| Variable | Descripció | Obligatori |
|---|---|---|
| `ANTHROPIC_API_KEY` | Clau API per Claude Sonnet 4.6 | ✅ |
| `OPENAI_API_KEY` | Clau API per embeddings (`text-embedding-3-small`) | ✅ |
| `CHAT_PASSWORD` | Contrasenya compartida per accedir a l'app | ✅ |
| `CHAINLIT_AUTH_SECRET` | Secret per signar JWTs de sessió | ✅ |

### Personalització

- **Color de marca**: edita `--sifecat-red` a `public/custom.css`
- **Starters (preguntes suggerides)**: edita `@cl.set_starters` a `app.py`
- **System prompt**: edita la constant `SYSTEM_PROMPT` a `app.py`
- **Top-K retrieval**: canvia `similarity_top_k=5` a `app.py`
- **Chunk size**: edita `chunk_size=800, chunk_overlap=100` a `ingest.py`
- **Tema (clar/fosc)**: `default_theme` a `.chainlit/config.toml`

---

## 🧠 Com funciona el RAG

1. **Ingesta** (`ingest.py`)
   - Llegeix els PDFs amb `SimpleDirectoryReader`
   - Trosseja en chunks de 800 tokens (overlap 100) amb `SentenceSplitter`
   - Genera embeddings amb OpenAI `text-embedding-3-small`
   - Persisteix els vectors a ChromaDB local (`./storage/`)

2. **Consulta** (`app.py`)
   - L'usuari escriu una pregunta
   - El query engine recupera els **5 chunks més semblants** semànticament
   - Es construeix un prompt amb aquests chunks + la pregunta + el system prompt
   - Claude Sonnet 4.6 genera la resposta en català, basada només en el context

3. **Persistència**
   - Cada conversa es guarda a SQLite (taules `users`, `threads`, `steps`, `feedbacks`)
   - El sidebar mostra l'historial de l'usuari autenticat

---

## 🔐 Seguretat — notes honestes

| Aspecte | Estat |
|---|---|
| Login amb contrasenya | ✅ Compartida entre tots els usuaris |
| Historial separat per usuari | ✅ Cada `identifier` té els seus threads |
| Xifratge en repòs | ❌ SQLite en pla; xifra el disc si cal |
| Xifratge en trànsit | ✅ HTTPS via Cloudflare Tunnel |
| Auditoria | ⚠️ Bàsica (a SQLite); no exporta a SIEM |
| Rotació de contrasenyes | ❌ Manual (canviar `.env` i reiniciar) |
| OAuth corporatiu | ❌ Pendent (Google/Microsoft Generalitat) |

> Per a un desplegament en producció real cal: contrasenyes per usuari (no compartida), OAuth, logs centralitzats i revisió legal de l'ús de Claude/OpenAI per a dades internes.

---

## 🛠️ Comandes útils

```bash
# Reindexar els manuals (després d'actualitzar PDFs)
python ingest.py --force

# Veure les converses de la BD
sqlite3 chat_history.db "SELECT u.identifier, t.name, datetime(t.createdAt) FROM threads t JOIN users u ON u.id = t.userId ORDER BY t.createdAt DESC;"

# Resetejar tot l'historial
rm chat_history.db && python init_db.py

# Arrencar sense obrir el navegador (headless)
chainlit run app.py -h

# Arrencar amb watch mode (recàrrega en canvis a app.py)
chainlit run app.py -w
```

---

## 🗺️ Roadmap

- [ ] **OAuth corporatiu** (Google Workspace de la Generalitat)
- [ ] **Domini estable** (`sifecat.gencat.cat` o similar via Cloudflare Tunnel amb DNS propi)
- [ ] **Citacions de fonts** clickables (mostrar el PDF i la pàgina exactes al lateral)
- [ ] **Upload de PDFs ad-hoc** (l'usuari pot afegir el seu propi document a la consulta)
- [ ] **Analytics**: dashboard amb preguntes més freqüents i feedback agregat
- [ ] **Hybrid search** (BM25 + semàntic) per a queries amb noms propis i sigles
- [ ] **Reranking** dels chunks recuperats amb Cohere o Voyage AI
- [ ] **Evaluació automàtica** (golden set de preguntes amb resposta esperada)
- [ ] **Suport multi-idioma** (castellà a banda del català)
- [ ] **Caché de respostes** per a preguntes freqüents (estalvi API)

---

## 📦 Stack tècnic

| Capa | Tecnologia | Versió |
|---|---|---|
| Llenguatge | Python | 3.12 |
| UI / xat | Chainlit | 2.11.1 |
| RAG framework | LlamaIndex | 0.14.21 |
| LLM | Claude Sonnet 4.6 (Anthropic) | `claude-sonnet-4-5-20250929` |
| Embeddings | OpenAI `text-embedding-3-small` | — |
| Vector store | ChromaDB | 1.5.9 |
| Persistència xats | SQLite (via SQLAlchemy + aiosqlite) | — |
| Túnel públic | Cloudflare Quick Tunnels | — |

---

## 🤝 Crèdits

Construït amb [LlamaIndex](https://www.llamaindex.ai), [Chainlit](https://chainlit.io), [Anthropic Claude](https://anthropic.com) i [OpenAI](https://openai.com).
Logo i identitat inspirats en la imatge corporativa de la **Generalitat de Catalunya**.

---

<div align="center">

*Fet amb ❤️ a Catalunya*

</div>
