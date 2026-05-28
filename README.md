<div align="center">

# 🟥 SIFERAG

**Assistent conversacional intern per a la gestió dels fons FEDER 2021-2027**
*Generalitat de Catalunya · Departament d'Economia i Finances*

Un chatbot RAG en català que respon dubtes sobre **SIFECAT** (l'aplicació operativa)
i sobre la **normativa FEDER** aplicable, citant sempre la font exacta.

![Python](https://img.shields.io/badge/python-3.12-blue?style=flat-square)
![Chainlit](https://img.shields.io/badge/UI-Chainlit-ff4f4f?style=flat-square)
![Claude](https://img.shields.io/badge/LLM-Claude_Sonnet_4.5-d97757?style=flat-square)
![LlamaIndex](https://img.shields.io/badge/RAG-LlamaIndex-9333ea?style=flat-square)
![Render](https://img.shields.io/badge/deploy-Render-46e3b7?style=flat-square)
![License](https://img.shields.io/badge/license-Internal-lightgrey?style=flat-square)

</div>

---

## ✨ Què fa

SIFERAG és un xat estil ChatGPT que combina **dues fonts de coneixement**:

- **📘 Manuals operatius SIFECAT** (7 manuals): BECU 21-27, gestió de contractes i transaccions, factures amb IRPF, presentació, validació, acceptació/signatura i justificació d'operacions.
- **⚖️ Normativa FEDER** (4 normatives):
  - **Europea** — Reglament (UE) 2021/1060 (Disposicions Comunes, CPR) i Reglament (UE) 2021/1058 (FEDER).
  - **Estatal** — Llei 38/2003 General de Subvencions.
  - **Autonòmica** — Decret Legislatiu 3/2002 (Finances Públiques de Catalunya).

Característiques:

- 💬 Respon **sempre en català** (encara que la font sigui en castellà).
- 🎯 **Prioritza la font segons la pregunta**: manuals per a procediments operatius, normativa per a fonament jurídic.
- 📎 **Cita la font real** sota cada resposta (document + categoria + pàgina), enllaçant al PDF.
- 🚫 Diu *"Aquesta informació no es troba als manuals ni a la normativa consultats"* quan no té base documental — i ho registra per detectar llacunes.
- 🔐 Accés amb usuari i contrasenya (compartida o multiusuari) — cada usuari té el seu propi historial.
- 🗂️ Historial de converses persistent estil ChatGPT + feedback 👍/👎.
- ⚡ Streaming token a token.

---

## 🏗️ Arquitectura

```
                                                  ┌─────────────────────────────────────┐
                                                  │  📄 documents/                       │
                                                  │   ├── manuals/   (7 PDFs SIFECAT)    │
                                                  │   └── normativa/ (4 PDFs FEDER)      │
                                                  └──────────────────┬──────────────────┘
                                                                     │ ingest.py
                                                                     │ (chunks 1500, batch 32)
                                                                     ▼
┌──────────────┐        ┌──────────────┐        ┌─────────────────────────────────────┐
│  👤 Usuari   │ ─────► │ 🌐 Chainlit  │ ─────► │  🧠 LlamaIndex Chat Engine          │
│ (navegador)  │ ◄───── │  login + xat │ ◄───── │   ↓ recupera top-8 chunks           │
└──────────────┘        │  + /brain    │        │   ↓ reranker Cohere (opcional) → 5  │
                        └──────┬───────┘        │  ┌────────────────────────────────┐ │
                               │                │  │ 💾 ChromaDB (disc persistent)  │ │
                               │                │  │  embeddings text-3-small       │ │
                               │                │  └────────────────────────────────┘ │
                               │                │   ↓ context + pregunta + system     │
                               │                │  ┌────────────────────────────────┐ │
                               │                │  │ 🤖 Claude Sonnet 4.5 (Anthropic)│ │
                               │                │  └────────────────────────────────┘ │
                               │                └─────────────────────────────────────┘
                               ▼                          │ resposta + 📎 fonts citades
                        ┌──────────────┐
                        │ 🗃️ SQLite     │  → usuaris, threads, missatges, feedback
                        │ chat_history │
                        └──────────────┘
```

---

## 🚀 Inici ràpid (local)

### Requisits

- **macOS** o Linux, **Python 3.12+**
- Una **API key d'Anthropic** ([console.anthropic.com](https://console.anthropic.com))
- Una **API key d'OpenAI** ([platform.openai.com](https://platform.openai.com))

### 1. Instal·lar

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configurar credencials (`.env`)

```bash
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-proj-...
CHAT_PASSWORD=la_teva_contrasenya_compartida
CHAINLIT_AUTH_SECRET=un_secret_llarg_i_aleatori
ADMIN_USERS=marc,admin
# Opcionals:
# USERS={"marc":"clau1","anna":"clau2"}   # multiusuari (té prioritat sobre CHAT_PASSWORD)
# COHERE_API_KEY=...                       # activa el reranker
```

> 💡 Genera un secret amb: `python -c "import secrets; print(secrets.token_urlsafe(64))"`

### 3. Posar els documents

```
documents/
├── manuals/         # PDFs amb manuals oficials SIFECAT
├── normativa/       # Reglaments UE, lleis, decrets
├── circulars/       # Circulars internes
├── instruccions/    # Instruccions tècniques
└── faqs/            # Preguntes freqüents en PDF
```

La **categoria** s'extreu del nom de la subcarpeta i s'afegeix com a metadata a cada chunk.

### 4. Indexar i inicialitzar

```bash
python ingest.py            # indexa documents/ recursiu → ./storage/
python init_db.py           # crea l'esquema SQLite de l'historial
```

Reindexar després d'afegir documents:

```bash
python ingest.py --force      # reconstrueix tot l'índex
python ingest.py --only-new   # incremental: només els PDFs encara no indexats
```

### 5. Arrencar

```bash
chainlit run app.py -w
```

[http://localhost:8000](http://localhost:8000) → login amb un usuari i la contrasenya del `.env`.

---

## ☁️ Desplegament a Render

El projecte inclou `render.yaml` (Blueprint) per a desplegar a [Render](https://render.com):

- **Disc persistent** muntat a `storage/`: l'índex ChromaDB sobreviu entre deploys, així **no cal reindexar** (ni cremar quota d'OpenAI) a cada desplegament.
- **`FORCE_REINDEX=false`**: la ingesta automàtica només s'executa si `storage/` és buit (primer deploy). Posa-ho a `true` puntualment per reconstruir tot l'índex.
- Reindexat segur sobre el punt de muntatge (buida el contingut, no el directori).

### Variables d'entorn a Render

| Variable | Descripció | Obligatori |
|---|---|---|
| `ANTHROPIC_API_KEY` | Clau API per Claude | ✅ |
| `OPENAI_API_KEY` | Clau API per embeddings | ✅ |
| `CHAT_PASSWORD` | Contrasenya compartida (fallback si no hi ha `USERS`) | ✅ |
| `CHAINLIT_AUTH_SECRET` | Secret per signar JWTs (es genera automàticament) | ✅ |
| `ADMIN_USERS` | Usernames admin separats per comes | ❌ |
| `USERS` | JSON `{"usuari":"contrasenya"}` per a multiusuari real | ❌ |
| `COHERE_API_KEY` | Activa el reranker Cohere (sense ella, RAG funciona igual) | ❌ |
| `FORCE_REINDEX` | `true` per forçar reindexat complet al pròxim deploy | ❌ |

> El desplegament s'activa automàticament en fer `git push origin main`.

### URL temporal per a proves locals

```bash
brew install cloudflared
cloudflared tunnel --url http://localhost:8000
```

---

## 📂 Estructura del projecte

```
RAG_S/
├── app.py                      # App Chainlit: auth, RAG, /brain, cita de fonts, admin
├── ingest.py                   # documents/ → ChromaDB (chunks, batch, --only-new)
├── init_db.py                  # Esquema SQLite per a l'historial de xats
├── documents_metadata.json     # Metadata humà-llegible (títol, descripció, àmbit, idioma…)
├── documents/                  # PDFs que nodreixen el bot, per categoria
├── storage/                    # ChromaDB persistent + unanswered.log [gitignored / disc Render]
├── chat_history.db             # SQLite (usuaris, threads, feedback) [gitignored]
├── public/                     # custom.css, custom.js, logos, avatars
├── .chainlit/config.toml       # Configuració de Chainlit (allow_origins, features…)
├── chainlit.md                 # Pàgina de benvinguda de l'assistent
├── render.yaml                 # Blueprint de desplegament a Render
├── requirements.txt
└── .env                        # Secrets [gitignored]
```

---

## 🧠 Com funciona el RAG

1. **Ingesta** (`ingest.py`)
   - Llegeix els PDFs amb `SimpleDirectoryReader` (recursiu, categoria per subcarpeta).
   - Trosseja en chunks de **1500 tokens** (overlap 100) amb `SentenceSplitter`.
   - Conserva `page_label` per poder citar la pàgina; exclou metadata sorollosa dels embeddings.
   - Genera embeddings amb OpenAI `text-embedding-3-small` i els insereix **per lots de 32** (pic de RAM baix).
   - Persisteix a ChromaDB (`./storage/`).

2. **Consulta** (`app.py`)
   - Recupera els **8 chunks** més semblants.
   - Si hi ha `COHERE_API_KEY`, un **reranker** (rerank-v3.5) els reordena i es queda amb els 5 millors.
   - Claude Sonnet 4.5 respon en català, basant-se només en el context, i **cita la font** (document + pàgina).

3. **Persistència**
   - Cada conversa es desa a SQLite (`users`, `threads`, `steps`, `feedbacks`).
   - Les preguntes sense resposta es registren a `storage/unanswered.log`.

---

## 🧠 AI Brain (`/brain`) — Transparència total

Panell que mostra **tots els documents que nodreixen l'assistent**, per categoria, amb comptadors (documents · pàgines · fragments) i, per a la normativa, l'àmbit (🇪🇺/🇪🇸/🏛) i l'idioma. Cada document es pot **previsualitzar** i **descarregar**.

Obre'l amb el botó del lateral o escrivint `/brain`.

### Rol d'admin

Els usuaris a `ADMIN_USERS` veuen una secció extra **🛠 Gestió** amb:

- 📊 **Feedback agregat** (👍/👎) i les respostes pitjor valorades.
- ❓ **Preguntes sense resposta** recents (per detectar llacunes).
- ⬆ **Pujar document**: adjunta un PDF, tria categoria i s'indexa de forma **incremental** (`ingest.py --only-new`).
- 🔄 **Reindexar documents** (complet) des de la UI.

> ⚠️ Els PDFs pujats des de la UI s'indexen al disc persistent, però el fitxer a `documents/` és efímer en cloud: afegeix-lo també al repositori git per a permanència.

---

## 🔐 Seguretat — notes honestes

| Aspecte | Estat |
|---|---|
| Login amb contrasenya | ✅ Compartida (`CHAT_PASSWORD`) o multiusuari (`USERS`) |
| Historial separat per usuari | ✅ Cada `identifier` té els seus threads |
| `allow_origins` restringit | ✅ Limitat al domini de producció |
| HTML del `/brain` escapat | ✅ `html.escape` a tots els camps dinàmics |
| Xifratge en trànsit | ✅ HTTPS (Render / Cloudflare) |
| Contrasenyes xifrades | ❌ En clar a l'env (pendent: hash + OAuth corporatiu) |
| Auditoria centralitzada | ⚠️ Bàsica (SQLite); no exporta a SIEM |

---

## 📦 Stack tècnic

| Capa | Tecnologia | Versió |
|---|---|---|
| Llenguatge | Python | 3.12 |
| UI / xat | Chainlit | 2.11.1 |
| RAG framework | LlamaIndex | 0.14.21 |
| LLM | Claude Sonnet 4.5 (Anthropic) | `claude-sonnet-4-5-20250929` |
| Embeddings | OpenAI `text-embedding-3-small` | — |
| Reranker (opcional) | Cohere `rerank-v3.5` | — |
| Vector store | ChromaDB | 1.5.9 |
| Persistència xats | SQLite (SQLAlchemy + aiosqlite) | — |
| Desplegament | Render (web service + disc persistent) | — |

---

## 🗺️ Roadmap

- [ ] **Tests** (unit + integració) i **eval harness** (golden set amb resposta i font esperades).
- [ ] **CI/CD** amb gate (ruff + mypy + tests) abans del deploy.
- [ ] **Error tracking** (Sentry) i analytics d'ús.
- [ ] **Parsing estructurat** de la normativa (articles/seccions) per a citacions encara més precises.
- [ ] **Hybrid search** (BM25 + semàntic) per a sigles i referències exactes.
- [ ] **Persistència** de l'historial/feedback entre deploys (disc o Postgres gestionat).
- [ ] **Accessibilitat WCAG 2.1 AA** (requisit legal del sector públic) + avís RGPD.
- [ ] **OAuth corporatiu** i domini propi (`siferag.gencat.cat`).

---

## 🤝 Crèdits

Construït amb [LlamaIndex](https://www.llamaindex.ai), [Chainlit](https://chainlit.io), [Anthropic Claude](https://anthropic.com), [OpenAI](https://openai.com) i [Cohere](https://cohere.com).
Identitat visual inspirada en la imatge corporativa de la **Generalitat de Catalunya**.

---

<div align="center">

*Fet amb ❤️ a Catalunya*

</div>
