import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import chainlit as cl
import chromadb
import pypdf
from dotenv import load_dotenv
from fastapi import HTTPException
from fastapi.responses import FileResponse
from llama_index.core import Settings, StorageContext, VectorStoreIndex
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.anthropic import Anthropic
from llama_index.vector_stores.chroma import ChromaVectorStore
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.server import app as fastapi_app

load_dotenv()

ROOT_DIR = Path(__file__).parent
STORAGE_DIR = ROOT_DIR / "storage"
DOCUMENTS_DIR = ROOT_DIR / "documents"
METADATA_FILE = ROOT_DIR / "documents_metadata.json"
DB_PATH = ROOT_DIR / "chat_history.db"
COLLECTION_NAME = "sifecat_manuals"
BOT_AUTHOR = "SIFECAT"

# ============================================================
# Serve documents/ via custom FastAPI route (symlinks blocked by /public)
# ============================================================

@fastapi_app.get("/documents/{category}/{filename}")
async def serve_document(category: str, filename: str):
    if "/" in category or "/" in filename or ".." in category or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid path")
    file_path = (DOCUMENTS_DIR / category / filename).resolve()
    docs_root = DOCUMENTS_DIR.resolve()
    if not str(file_path).startswith(str(docs_root)):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=filename,
    )


def _reorder_routes_for_documents():
    """Mou la ruta /documents davant del catch-all de Chainlit perquè es resolgui correctament."""
    doc_route = None
    catchall_idx = None
    for i, r in enumerate(fastapi_app.routes):
        p = getattr(r, "path", "")
        if p == "/documents/{category}/{filename}":
            doc_route = r
        if p == "/{full_path:path}" and catchall_idx is None:
            catchall_idx = i
    if doc_route is not None and catchall_idx is not None:
        fastapi_app.routes.remove(doc_route)
        fastapi_app.routes.insert(catchall_idx, doc_route)


_reorder_routes_for_documents()


CATEGORIES_ORDER = ["manuals", "normativa", "circulars", "instruccions", "faqs"]
CATEGORY_LABELS = {
    "manuals": "Manuals",
    "normativa": "Normativa FEDER",
    "circulars": "Circulars",
    "instruccions": "Instruccions",
    "faqs": "FAQs",
}
SCOPE_LABELS = {
    "europeu": "🇪🇺 Europeu",
    "estatal": "🇪🇸 Estatal",
    "autonòmic": "🏛 Autonòmic",
}

# ============================================================
# Auto-reindex on startup (idempotent, runs at module import)
# Important per a desplegaments cloud on storage/ no és persistent.
# ============================================================

def _auto_reindex_if_needed():
    import shutil as _shutil
    force = os.getenv("FORCE_REINDEX", "").strip().lower() in ("1", "true", "yes")
    has_storage = STORAGE_DIR.exists() and any(STORAGE_DIR.iterdir())
    if has_storage and not force:
        print(f"📦 storage/ existeix — saltant reindexat automàtic")
        return
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Falta OPENAI_API_KEY — no es pot reindexar", file=sys.stderr)
        return
    if not DOCUMENTS_DIR.exists() or not any(DOCUMENTS_DIR.rglob("*.pdf")):
        print(f"⚠️  No s'han trobat PDFs a {DOCUMENTS_DIR} — no es pot reindexar", file=sys.stderr)
        return
    if force and has_storage:
        print("🔁 FORCE_REINDEX=true — esborrant storage/ existent abans de reindexar…", flush=True)
        _shutil.rmtree(STORAGE_DIR, ignore_errors=True)
    print("🔄 Executant ingesta automàtica…", flush=True)
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT_DIR / "ingest.py"), "--force"],
            cwd=str(ROOT_DIR),
            timeout=900,
            check=False,
        )
        if result.returncode == 0:
            print("✅ Ingesta automàtica completada", flush=True)
        else:
            print(f"❌ Ingesta automàtica ha fallat (returncode={result.returncode})", file=sys.stderr)
    except Exception as e:
        print(f"❌ Error executant la ingesta automàtica: {e}", file=sys.stderr)


_auto_reindex_if_needed()


SYSTEM_PROMPT = (
    "Ets SIFERAG, l'assistent expert en la gestió dels fons FEDER 2021-2027 "
    "de la Generalitat de Catalunya.\n\n"
    "BASE DE CONEIXEMENT:\n"
    "Disposes de dos cossos documentals indexats:\n"
    "  • MANUALS OPERATIUS SIFECAT — procediments del dia a dia dins l'aplicació "
    "(presentació, validació, signatura, justificació de despesa, factures amb IRPF, "
    "gestió de contractes, BECU, indicadors).\n"
    "  • NORMATIVA FEDER — marc jurídic que regula els fons:\n"
    "      · Europea: Reglament UE 2021/1060 (Disposicions Comunes - CPR) i "
    "Reglament UE 2021/1058 (FEDER).\n"
    "      · Estatal: Llei 38/2003 General de Subvencions.\n"
    "      · Autonòmica: Decret Legislatiu 3/2002 (Finances Públiques de Catalunya).\n\n"
    "COM PRIORITZAR LES FONTS:\n"
    "1. Per a procediments operatius, fluxos dins l'aplicació, pantalles, estats i "
    "passos del dia a dia → prioritza els MANUALS SIFECAT.\n"
    "2. Per a fonament legal, requisits jurídics, definicions normatives, "
    "interpretació i conflictes entre fonts → prioritza la NORMATIVA "
    "(europea > estatal > autonòmica quan hi hagi jerarquia aplicable).\n"
    "3. Quan una pregunta tingui dimensió operativa i legal alhora, combina les "
    "dues fonts: explica el procediment del manual i fonamenta'l amb la normativa.\n\n"
    "REGLES:\n"
    "1. Respon SEMPRE en català, encara que la font original sigui en castellà.\n"
    "2. Basa't EXCLUSIVAMENT en el context recuperat (manuals i normativa) i, si "
    "s'aporta, el document que l'usuari hagi adjuntat.\n"
    "3. Si la resposta no es troba al context, digues exactament: "
    "\"Aquesta informació no es troba als manuals ni a la normativa consultats.\"\n"
    "4. CITA SEMPRE el tipus de document i la referència exacta: per a normativa, "
    "indica article/apartat (p. ex. \"art. 63 del Reglament UE 2021/1060\" o "
    "\"art. 17 de la Llei 38/2003\"); per a manuals, indica el manual i la secció "
    "(p. ex. \"Manual de Presentació d'operacions, secció Validació prèvia\").\n"
    "5. Sigues clar, natural i directe. Fes servir llistes o passos numerats "
    "només quan aporti claredat."
)


# ============================================================
# Data layer + Auth
# ============================================================

@cl.data_layer
def get_data_layer():
    return SQLAlchemyDataLayer(conninfo=f"sqlite+aiosqlite:///{DB_PATH}")


def _is_admin(username: str) -> bool:
    admins = [u.strip().lower() for u in os.getenv("ADMIN_USERS", "").split(",") if u.strip()]
    return username.strip().lower() in admins


@cl.password_auth_callback
def auth_callback(username: str, password: str) -> Optional[cl.User]:
    expected = os.getenv("CHAT_PASSWORD", "")
    if not expected:
        return None
    if password == expected and username.strip():
        uname = username.strip().lower()
        role = "admin" if _is_admin(uname) else "user"
        return cl.User(
            identifier=uname,
            metadata={"display_name": username.strip(), "role": role},
        )
    return None


@cl.on_shared_thread_view
async def on_shared_thread_view(thread):
    return


# ============================================================
# Starters
# ============================================================

@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="Presentar una operació nova",
            message="Quins passos he de seguir per presentar una operació nova a SIFECAT?",
        ),
        cl.Starter(
            label="Justificar una despesa",
            message="Com he de justificar una despesa amb indicadors associats?",
        ),
        cl.Starter(
            label="Validar una operació",
            message="Qui pot validar una operació i quins estats pot tenir durant el procés?",
        ),
        cl.Starter(
            label="Signar una operació",
            message="Com s'accepta i es signa una operació? Qui ha de signar-la?",
        ),
    ]


# ============================================================
# LLM + Chat engine bootstrap
# ============================================================

def _build_llm() -> Anthropic:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY no està definida a .env", file=sys.stderr)
        sys.exit(1)

    for model_name in ["claude-sonnet-4-5-20250929", "claude-sonnet-4-20250514"]:
        try:
            llm = Anthropic(model=model_name, system_prompt=SYSTEM_PROMPT, max_tokens=2048)
            _ = llm.metadata
            print(f"✅ Model LLM carregat: {model_name}")
            return llm
        except Exception as e:
            print(f"⚠️  No s'ha pogut carregar {model_name}: {e}")
    raise RuntimeError("No s'ha pogut carregar cap model de Claude.")


def _build_index() -> VectorStoreIndex:
    Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")
    Settings.llm = _build_llm()
    chroma_client = chromadb.PersistentClient(path=str(STORAGE_DIR))
    chroma_collection = chroma_client.get_or_create_collection(COLLECTION_NAME)
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    return VectorStoreIndex.from_vector_store(
        vector_store=vector_store, storage_context=storage_context
    )


def _build_chat_engine(index: VectorStoreIndex, chat_history: Optional[list[ChatMessage]] = None):
    memory = ChatMemoryBuffer.from_defaults(chat_history=chat_history or [], token_limit=4000)
    return index.as_chat_engine(
        chat_mode="condense_plus_context",
        memory=memory,
        similarity_top_k=5,
        system_prompt=SYSTEM_PROMPT,
        streaming=True,
    )


def _ensure_engine():
    engine = cl.user_session.get("chat_engine")
    if engine is not None:
        return engine
    if not STORAGE_DIR.exists():
        return None
    try:
        index = cl.user_session.get("index") or _build_index()
        cl.user_session.set("index", index)
        engine = _build_chat_engine(index)
        cl.user_session.set("chat_engine", engine)
        return engine
    except Exception as e:
        print(f"❌ Error creant chat engine: {e}", file=sys.stderr)
        return None


# ============================================================
# AI Brain helpers
# ============================================================

def _load_documents_metadata() -> list[dict]:
    if not METADATA_FILE.exists():
        return []
    try:
        return json.loads(METADATA_FILE.read_text(encoding="utf-8")).get("documents", [])
    except Exception as e:
        print(f"⚠️  Error llegint {METADATA_FILE}: {e}", file=sys.stderr)
        return []


_PAGE_CACHE: dict[str, int] = {}


def _count_pages(pdf_path: Path) -> int:
    key = str(pdf_path)
    if key in _PAGE_CACHE:
        return _PAGE_CACHE[key]
    try:
        n = len(pypdf.PdfReader(str(pdf_path)).pages)
    except Exception:
        n = 0
    _PAGE_CACHE[key] = n
    return n


def _count_chunks() -> int:
    try:
        client = chromadb.PersistentClient(path=str(STORAGE_DIR))
        col = client.get_or_create_collection(COLLECTION_NAME)
        return col.count()
    except Exception:
        return 0


def _scan_filesystem_docs() -> list[dict]:
    """Detecta docs al filesystem (per a categories sense entrada al JSON)."""
    found = []
    if not DOCUMENTS_DIR.exists():
        return found
    for pdf in DOCUMENTS_DIR.rglob("*.pdf"):
        rel = pdf.relative_to(DOCUMENTS_DIR)
        category = rel.parts[0] if len(rel.parts) > 1 else "uncategorized"
        found.append({"filename": pdf.name, "category": category, "path": pdf})
    return found


def _enriched_documents() -> list[dict]:
    """Combina JSON metadata + filesystem scan. Calcula pàgines en temps real."""
    meta = _load_documents_metadata()
    by_filename = {d["filename"]: d for d in meta}
    fs_docs = _scan_filesystem_docs()
    fs_by_filename = {d["filename"]: d for d in fs_docs}

    all_filenames = set(by_filename) | set(fs_by_filename)
    enriched = []
    for fname in sorted(all_filenames):
        m = by_filename.get(fname, {})
        f = fs_by_filename.get(fname, {})
        category = m.get("category") or f.get("category", "uncategorized")
        path = f.get("path") or (DOCUMENTS_DIR / category / fname)
        pages = _count_pages(path) if path.exists() else 0
        enriched.append({
            "id": m.get("id") or fname.replace(".pdf", "").lower().replace(" ", "_"),
            "filename": fname,
            "category": category,
            "title": m.get("title") or fname.replace("_", " ").replace(".pdf", ""),
            "description": m.get("description") or "",
            "version": m.get("version"),
            "last_updated": m.get("last_updated"),
            "source": m.get("source"),
            "scope": m.get("scope"),
            "language": m.get("language"),
            "pages": pages,
            "url": f"/documents/{category}/{fname}",
            "exists": path.exists(),
        })
    return enriched


def _render_brain_html(focus_id: Optional[str] = None, is_admin: bool = False) -> str:
    docs = _enriched_documents()
    docs = [d for d in docs if d["exists"]]
    n_docs = len(docs)
    n_pages = sum(d["pages"] for d in docs)
    n_chunks = _count_chunks()

    grouped: dict[str, list[dict]] = {}
    for d in docs:
        grouped.setdefault(d["category"], []).append(d)

    ordered_cats = [c for c in CATEGORIES_ORDER if c in grouped]
    extras = [c for c in grouped if c not in ordered_cats]
    ordered_cats.extend(sorted(extras))

    out = []
    out.append('<div class="brain-panel">')
    out.append('<div class="brain-header">')
    out.append('<h2 class="brain-title">🧠 AI Brain</h2>')
    out.append('<p class="brain-subtitle">Tot el que sap aquest assistent</p>')
    out.append('</div>')

    out.append('<div class="brain-stats">')
    out.append(f'<span><strong>{n_docs}</strong> documents</span>')
    out.append(f'<span><strong>{n_pages}</strong> pàgines</span>')
    out.append(f'<span><strong>{n_chunks}</strong> fragments indexats</span>')
    out.append('</div>')

    for cat in ordered_cats:
        cat_label = CATEGORY_LABELS.get(cat, cat.capitalize())
        items = grouped[cat]
        out.append(f'<section class="brain-section" data-category="{cat}">')
        out.append(f'<h3 class="brain-section-title">{cat_label} <span class="brain-section-count">{len(items)}</span></h3>')
        out.append('<div class="brain-doc-list">')
        for d in items:
            anchor = f' id="brain-doc-{d["id"]}"' if d["id"] else ''
            highlight = ' brain-doc-focus' if focus_id and d["id"] == focus_id else ''
            version_html = f'<span class="brain-doc-meta-item">{d["version"]}</span>' if d.get("version") else ''
            date_html = f'<span class="brain-doc-meta-item">{d["last_updated"]}</span>' if d.get("last_updated") else ''
            pages_html = f'<span class="brain-doc-meta-item">{d["pages"]} pàgines</span>' if d.get("pages") else ''
            scope_label = SCOPE_LABELS.get(d.get("scope") or "", "")
            scope_html = f'<span class="brain-doc-chip brain-doc-chip-scope">{scope_label}</span>' if scope_label else ''
            language_html = f'<span class="brain-doc-meta-item">{d["language"]}</span>' if d.get("language") else ''
            out.append(f'<article class="brain-doc{highlight}"{anchor}>')
            out.append('<div class="brain-doc-icon">📕</div>')
            out.append('<div class="brain-doc-body">')
            out.append(f'<h4 class="brain-doc-title">{d["title"]}</h4>')
            if d["description"]:
                out.append(f'<p class="brain-doc-desc">{d["description"]}</p>')
            out.append('<div class="brain-doc-meta">')
            out.append(f'<span class="brain-doc-chip">{cat_label}</span>')
            out.append(scope_html)
            out.append(version_html)
            out.append(language_html)
            out.append(date_html)
            out.append(pages_html)
            out.append('</div>')
            out.append('<div class="brain-doc-actions">')
            out.append(f'<a href="{d["url"]}" target="_blank" rel="noopener" class="brain-btn">👁 Previsualitzar</a>')
            out.append(f'<a href="{d["url"]}" download class="brain-btn">⬇ Descarregar</a>')
            out.append('</div>')
            out.append('</div>')
            out.append('</article>')
        out.append('</div>')
        out.append('</section>')

    # Empty categories shown as placeholders
    for cat in CATEGORIES_ORDER:
        if cat not in grouped:
            out.append(f'<section class="brain-section brain-section-empty">')
            out.append(f'<h3 class="brain-section-title">{CATEGORY_LABELS[cat]} <span class="brain-section-count">0</span></h3>')
            out.append(f'<p class="brain-empty-text">Encara no hi ha documents en aquesta categoria.</p>')
            out.append('</section>')

    if is_admin:
        last_modified = ""
        if STORAGE_DIR.exists():
            try:
                ts = max(p.stat().st_mtime for p in STORAGE_DIR.rglob("*") if p.is_file())
                last_modified = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
        out.append('<section class="brain-admin">')
        out.append('<h3 class="brain-section-title">🛠 Gestió (admin)</h3>')
        out.append('<div class="brain-admin-stats">')
        if last_modified:
            out.append(f'<p>Última reindexació: <strong>{last_modified}</strong></p>')
        out.append(f'<p>Fragments al ChromaDB: <strong>{n_chunks}</strong></p>')
        out.append('</div>')
        out.append('<p class="brain-admin-hint">Per reindexar, fes servir el botó "Reindexar documents" sota aquest panell.</p>')
        out.append('</section>')

    out.append('</div>')
    return "\n".join(out)


async def _send_brain(focus_id: Optional[str] = None):
    user = cl.user_session.get("user")
    is_admin = bool(user and user.metadata.get("role") == "admin")
    html = _render_brain_html(focus_id=focus_id, is_admin=is_admin)
    actions = []
    if is_admin:
        actions.append(
            cl.Action(
                name="reindex_docs",
                payload={},
                label="🔄 Reindexar documents",
                icon="refresh-cw",
            )
        )
    await cl.Message(
        author=BOT_AUTHOR,
        content=html,
        actions=actions,
    ).send()


# ============================================================
# Helpers: PDF extraction + follow-ups
# ============================================================

def _extract_pdf_text(path: str, max_chars: int = 8000) -> str:
    reader = pypdf.PdfReader(path)
    text = ""
    for page in reader.pages:
        try:
            text += (page.extract_text() or "") + "\n\n"
        except Exception:
            continue
        if len(text) >= max_chars:
            break
    return text[:max_chars]


async def _generate_followups(question: str, answer: str) -> list[str]:
    if not answer or len(answer) < 40:
        return []
    prompt = (
        "A partir d'aquesta darrera pregunta i resposta sobre SIFECAT (FEDER 21-27), "
        "genera EXACTAMENT 3 preguntes curtes de seguiment en català que un usuari "
        "podria voler fer després. Una pregunta per línia, sense numeració ni guions, "
        "màxim 75 caràcters per pregunta, naturals i específiques.\n\n"
        f"PREGUNTA: {question}\n"
        f"RESPOSTA: {answer[:1200]}\n\n"
        "Les 3 preguntes:"
    )
    try:
        resp = await Settings.llm.acomplete(prompt)
        raw = str(resp).strip()
        lines = []
        for ln in raw.split("\n"):
            ln = ln.strip().lstrip("-•*0123456789. )")
            ln = ln.strip(' "\'')
            if 8 < len(ln) < 120 and "?" in ln:
                lines.append(ln)
        return lines[:3]
    except Exception as e:
        print(f"⚠️  Error generant follow-ups: {e}", file=sys.stderr)
        return []


# ============================================================
# Chainlit handlers
# ============================================================

@cl.on_chat_start
async def on_chat_start():
    if not STORAGE_DIR.exists():
        await cl.Message(
            author=BOT_AUTHOR,
            content="No s'ha trobat l'índex de manuals. Contacta amb l'administrador.",
        ).send()
        return
    _ensure_engine()


@cl.on_chat_resume
async def on_chat_resume(thread):
    if not STORAGE_DIR.exists():
        return
    try:
        history: list[ChatMessage] = []
        steps = thread.get("steps", []) if isinstance(thread, dict) else getattr(thread, "steps", [])
        for step in steps:
            stype = step.get("type") if isinstance(step, dict) else getattr(step, "type", None)
            output = step.get("output") if isinstance(step, dict) else getattr(step, "output", None)
            inp = step.get("input") if isinstance(step, dict) else getattr(step, "input", None)
            if stype == "user_message" and (output or inp):
                history.append(ChatMessage(role=MessageRole.USER, content=output or inp))
            elif stype == "assistant_message" and output:
                history.append(ChatMessage(role=MessageRole.ASSISTANT, content=output))
        index = _build_index()
        cl.user_session.set("index", index)
        cl.user_session.set("chat_engine", _build_chat_engine(index, chat_history=history))
    except Exception as e:
        print(f"❌ Error reprenent la conversa: {e}", file=sys.stderr)
        _ensure_engine()


async def _answer(question: str, attached_pdf_text: str = "") -> str:
    engine = _ensure_engine()
    if engine is None:
        await cl.Message(
            author=BOT_AUTHOR,
            content="L'assistent no està disponible. Recarrega la pàgina.",
        ).send()
        return ""

    full_question = question
    if attached_pdf_text:
        full_question = (
            "L'usuari ha adjuntat un document. Contingut extret:\n"
            "<<<\n" + attached_pdf_text + "\n>>>\n\n"
            f"Pregunta de l'usuari: {question}"
        )

    msg = cl.Message(content="", author=BOT_AUTHOR)
    await msg.send()

    full_text = ""
    try:
        response = await cl.make_async(engine.stream_chat)(full_question)
        for token in response.response_gen:
            full_text += token
            await msg.stream_token(token)
    except Exception as e:
        print(f"❌ Error en stream_chat: {e}", file=sys.stderr)
        msg.content = "Hi ha hagut un problema processant la teva pregunta. Torna-ho a intentar."
        await msg.update()
        return ""

    await msg.update()
    return full_text


@cl.on_message
async def on_message(message: cl.Message):
    text = (message.content or "").strip()

    # /brain command — opens the AI Brain panel
    if text.lower().startswith("/brain"):
        # Optional focus: /brain manual_becu
        parts = text.split(None, 1)
        focus_id = parts[1].strip() if len(parts) > 1 else None
        await _send_brain(focus_id=focus_id)
        return

    # PDF attachments
    attached_text = ""
    if message.elements:
        for el in message.elements:
            path = getattr(el, "path", None)
            if path and str(path).lower().endswith(".pdf") and os.path.exists(path):
                try:
                    attached_text += f"\n\n[{el.name}]\n" + _extract_pdf_text(path)
                except Exception as e:
                    print(f"⚠️  Error llegint PDF adjunt: {e}", file=sys.stderr)

    answer_text = await _answer(text, attached_pdf_text=attached_text)

    if answer_text:
        followups = await _generate_followups(text, answer_text)
        if followups:
            actions = [
                cl.Action(name="followup", payload={"question": q}, label=q, icon="message-circle")
                for q in followups
            ]
            await cl.Message(
                author=BOT_AUTHOR,
                content="**Vols seguir explorant?**",
                actions=actions,
            ).send()


@cl.action_callback("followup")
async def on_followup(action: cl.Action):
    question = action.payload.get("question", "")
    if not question:
        return
    await cl.Message(content=question, author="user", type="user_message").send()
    answer_text = await _answer(question)
    if answer_text:
        followups = await _generate_followups(question, answer_text)
        if followups:
            actions = [
                cl.Action(name="followup", payload={"question": q}, label=q, icon="message-circle")
                for q in followups
            ]
            await cl.Message(
                author=BOT_AUTHOR,
                content="**Vols seguir explorant?**",
                actions=actions,
            ).send()
    await action.remove()


@cl.action_callback("reindex_docs")
async def on_reindex(action: cl.Action):
    user = cl.user_session.get("user")
    if not user or user.metadata.get("role") != "admin":
        await cl.Message(
            author=BOT_AUTHOR,
            content="No tens permís per executar aquesta acció.",
        ).send()
        return

    msg = cl.Message(author=BOT_AUTHOR, content="🔄 Reindexant documents…")
    await msg.send()
    try:
        result = await cl.make_async(subprocess.run)(
            [sys.executable, "ingest.py", "--force"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=600,
        )
        log_tail = (result.stdout or "")[-1500:]
        if result.returncode == 0:
            n_chunks = _count_chunks()
            msg.content = (
                f"✅ Reindexació completada. **{n_chunks}** fragments al ChromaDB.\n\n"
                f"```\n{log_tail}\n```\n\n"
                "ℹ️  Recarrega la pàgina o inicia una nova conversa per fer servir l'índex actualitzat."
            )
        else:
            err = (result.stderr or "")[-1500:]
            msg.content = f"❌ La reindexació ha fallat:\n```\n{err}\n```"
    except Exception as e:
        msg.content = f"❌ Error executant la reindexació: {e}"
    await msg.update()
    await action.remove()
