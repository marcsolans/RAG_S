import os
import sys
from pathlib import Path
from typing import Optional

import chainlit as cl
import chromadb
import pypdf
from dotenv import load_dotenv
from llama_index.core import Settings, StorageContext, VectorStoreIndex
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.anthropic import Anthropic
from llama_index.vector_stores.chroma import ChromaVectorStore
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer

load_dotenv()

ROOT_DIR = Path(__file__).parent
STORAGE_DIR = ROOT_DIR / "storage"
MANUALS_DIR = ROOT_DIR / "manuals"
DB_PATH = ROOT_DIR / "chat_history.db"
COLLECTION_NAME = "sifecat_manuals"
BOT_AUTHOR = "SIFECAT"

SYSTEM_PROMPT = (
    "Ets un assistent expert en SIFECAT, l'aplicació interna de la Generalitat "
    "de Catalunya per a la gestió dels fons FEDER 2021-2027.\n\n"
    "REGLES:\n"
    "1. Respon SEMPRE en català.\n"
    "2. Basa't EXCLUSIVAMENT en el context recuperat dels manuals i, si s'aporta, "
    "el document que l'usuari hagi adjuntat.\n"
    "3. Si la resposta no es troba al context, digues exactament: "
    "\"Aquesta informació no es troba als manuals consultats.\"\n"
    "4. Sigues clar, natural i directe. Fes servir llistes o passos numerats "
    "només quan aporti claredat. No citis fonts ni números de pàgina dins del text "
    "(es mostren a part)."
)


# ----------------------------- Data layer + Auth -----------------------------

@cl.data_layer
def get_data_layer():
    return SQLAlchemyDataLayer(conninfo=f"sqlite+aiosqlite:///{DB_PATH}")


@cl.password_auth_callback
def auth_callback(username: str, password: str) -> Optional[cl.User]:
    expected = os.getenv("CHAT_PASSWORD", "")
    if not expected:
        return None
    if password == expected and username.strip():
        return cl.User(
            identifier=username.strip().lower(),
            metadata={"display_name": username.strip(), "role": "user"},
        )
    return None


@cl.on_shared_thread_view
async def on_shared_thread_view(thread):
    """Permet que altres usuaris vegin una conversa compartida (lectura)."""
    return


# ----------------------------- Starters -----------------------------

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


# ----------------------------- LLM + Engine bootstrap -----------------------------

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
    memory = ChatMemoryBuffer.from_defaults(
        chat_history=chat_history or [],
        token_limit=4000,
    )
    return index.as_chat_engine(
        chat_mode="condense_plus_context",
        memory=memory,
        similarity_top_k=5,
        system_prompt=SYSTEM_PROMPT,
        streaming=True,
    )


def _ensure_engine() -> Optional[object]:
    """Recupera o crea el chat engine per a la sessió actual."""
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


# ----------------------------- Helpers: PDFs, citacions, follow-ups -----------------------------

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
    """Genera 3 preguntes de seguiment basades en l'última Q&A."""
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


# ----------------------------- Chainlit handlers -----------------------------

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
    """Reconstrueix el chat engine amb l'historial complet del thread."""
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


async def _answer(question: str, attached_pdf_text: str = "") -> tuple[str, list]:
    """Genera la resposta en streaming. Retorna (text_final, source_elements)."""
    engine = _ensure_engine()
    if engine is None:
        msg = cl.Message(
            author=BOT_AUTHOR,
            content="L'assistent no està disponible. Recarrega la pàgina.",
        )
        await msg.send()
        return ("", [])

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
        return ("", [])

    await msg.update()
    return (full_text, [])


@cl.on_message
async def on_message(message: cl.Message):
    # Process attached PDFs (if any)
    attached_text = ""
    if message.elements:
        for el in message.elements:
            path = getattr(el, "path", None)
            if path and str(path).lower().endswith(".pdf") and os.path.exists(path):
                try:
                    attached_text += f"\n\n[{el.name}]\n" + _extract_pdf_text(path)
                except Exception as e:
                    print(f"⚠️  Error llegint PDF adjunt: {e}", file=sys.stderr)

    answer_text, _ = await _answer(message.content, attached_pdf_text=attached_text)

    if answer_text:
        followups = await _generate_followups(message.content, answer_text)
        if followups:
            actions = [
                cl.Action(
                    name="followup",
                    payload={"question": q},
                    label=q,
                    icon="message-circle",
                )
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
    answer_text, _ = await _answer(question)
    if answer_text:
        followups = await _generate_followups(question, answer_text)
        if followups:
            actions = [
                cl.Action(
                    name="followup",
                    payload={"question": q},
                    label=q,
                    icon="message-circle",
                )
                for q in followups
            ]
            await cl.Message(
                author=BOT_AUTHOR,
                content="**Vols seguir explorant?**",
                actions=actions,
            ).send()
    await action.remove()
