import argparse
import gc
import os
import shutil
import sys
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from llama_index.core import (
    Settings,
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore

ROOT_DIR = Path(__file__).parent
DOCUMENTS_DIR = ROOT_DIR / "documents"
STORAGE_DIR = ROOT_DIR / "storage"
COLLECTION_NAME = "sifecat_manuals"

# Chunks més grans → menys nodes en memòria i menys overhead de Chroma.
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 100
# Lots petits per mantenir el pic de RAM baix (Render Free té 512 MB).
EMBED_BATCH_SIZE = 32


def file_metadata(file_path: str) -> dict:
    """Extreu categoria (nom de la subcarpeta directa dins documents/) i fitxer."""
    p = Path(file_path).resolve()
    parts = p.parts
    category = "uncategorized"
    try:
        docs_idx = parts.index("documents")
        if docs_idx + 1 < len(parts):
            category = parts[docs_idx + 1]
    except ValueError:
        pass
    return {
        "file_name": p.name,
        "category": category,
        "rel_path": f"{category}/{p.name}",
    }


# Claus de metadata que són soroll per a la cerca semàntica (noms de fitxer,
# rutes, número de pàgina): les excloem del text que s'incrusta i del que rep
# l'LLM, però es conserven a la metadata del node per poder citar la font.
_NOISY_METADATA_KEYS = ["file_name", "rel_path", "page_label"]


def _clear_dir_contents(d: Path) -> None:
    """Buida el contingut d'un directori sense eliminar-lo. Imprescindible quan
    storage/ és un punt de muntatge (disc persistent de Render): un rmtree del
    propi directori fallaria amb 'device busy'."""
    for child in d.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink()
            except Exception:
                pass


def _existing_filenames(collection) -> set[str]:
    """Noms de fitxer ja indexats (llegits de la metadata de Chroma)."""
    try:
        got = collection.get(include=["metadatas"])
    except Exception:
        return set()
    names = set()
    for md in got.get("metadatas") or []:
        if md and md.get("file_name"):
            names.add(md["file_name"])
    return names


def _load_pdf_documents(input_files=None):
    """Carrega PDFs (tots o una llista concreta) i neteja la metadata sorollosa."""
    kwargs = dict(required_exts=[".pdf"], recursive=True, file_metadata=file_metadata)
    if input_files:
        reader = SimpleDirectoryReader(input_files=[str(f) for f in input_files], file_metadata=file_metadata)
    else:
        reader = SimpleDirectoryReader(input_dir=str(DOCUMENTS_DIR), **kwargs)
    documents = reader.load_data()
    for d in documents:
        d.excluded_embed_metadata_keys = list(_NOISY_METADATA_KEYS)
        d.excluded_llm_metadata_keys = list(_NOISY_METADATA_KEYS)
    return documents


def _index_documents(documents, chroma_collection) -> int:
    """Trosseja, incrusta i insereix per lots. Retorna nombre de chunks."""
    Settings.embed_model = OpenAIEmbedding(
        model="text-embedding-3-small",
        embed_batch_size=EMBED_BATCH_SIZE,
        max_retries=5,
        timeout=60.0,
    )
    Settings.node_parser = SentenceSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    print(f"✂️  Trocejant en chunks de {CHUNK_SIZE} tokens (overlap {CHUNK_OVERLAP})...")
    nodes = Settings.node_parser.get_nodes_from_documents(documents, show_progress=True)
    n_nodes = len(nodes)
    print(f"   → {n_nodes} chunks generats")

    documents.clear()
    gc.collect()

    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store, storage_context=storage_context
    )

    print(f"🔢 Generant embeddings per lots de {EMBED_BATCH_SIZE}...")
    inserted = 0
    for i in range(0, n_nodes, EMBED_BATCH_SIZE):
        batch = nodes[i : i + EMBED_BATCH_SIZE]
        index.insert_nodes(batch)
        inserted += len(batch)
        for j in range(i, i + len(batch)):
            nodes[j] = None
        gc.collect()
        print(f"   ⤳ {inserted}/{n_nodes} chunks indexats", flush=True)
    return inserted


def main():
    parser = argparse.ArgumentParser(description="Ingesta de documents a ChromaDB")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reindexa del tot encara que storage/ ja existeixi",
    )
    parser.add_argument(
        "--only-new",
        action="store_true",
        help="Indexa només els PDFs que encara no són a la col·lecció (incremental)",
    )
    args = parser.parse_args()

    load_dotenv()

    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY no està definida a .env", file=sys.stderr)
        sys.exit(1)

    if not DOCUMENTS_DIR.exists():
        print(f"ERROR: No existeix la carpeta {DOCUMENTS_DIR}", file=sys.stderr)
        sys.exit(1)

    pdf_files = list(DOCUMENTS_DIR.rglob("*.pdf"))
    if not pdf_files:
        print(f"ERROR: No s'han trobat PDFs dins de {DOCUMENTS_DIR}", file=sys.stderr)
        sys.exit(1)

    # Reindexat complet: esborrem l'índex (excepte en mode incremental).
    if STORAGE_DIR.exists() and not args.only_new:
        if not args.force:
            print(
                f"⚠️  La carpeta {STORAGE_DIR} ja existeix. "
                "Fes servir --force (complet) o --only-new (incremental)."
            )
            sys.exit(0)
        print(f"🗑️  Esborrant índex existent a {STORAGE_DIR}...")
        _clear_dir_contents(STORAGE_DIR)

    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    chroma_client = chromadb.PersistentClient(path=str(STORAGE_DIR))
    chroma_collection = chroma_client.get_or_create_collection(COLLECTION_NAME)

    # Mode incremental: filtrem els fitxers que ja estan indexats.
    if args.only_new:
        already = _existing_filenames(chroma_collection)
        pending = [f for f in pdf_files if f.name not in already]
        if not pending:
            print("✅ Cap fitxer nou per indexar. Tot està al dia.")
            return
        print(f"➕ {len(pending)} fitxers nous per indexar (de {len(pdf_files)} totals).")
        pdf_files = pending

    print(f"📚 Llegint {len(pdf_files)} PDFs...")
    by_cat: dict[str, int] = {}
    for f in pdf_files:
        rel = f.relative_to(DOCUMENTS_DIR)
        cat = rel.parts[0] if len(rel.parts) > 1 else "uncategorized"
        by_cat[cat] = by_cat.get(cat, 0) + 1
    for cat, n in sorted(by_cat.items()):
        print(f"   ├─ {cat}: {n} fitxers")

    documents = _load_pdf_documents(input_files=pdf_files if args.only_new else None)
    print(f"   → {len(documents)} pàgines/documents carregats")

    inserted = _index_documents(documents, chroma_collection)
    print(f"✅ Ingesta completada. {inserted} chunks indexats a {STORAGE_DIR}")


if __name__ == "__main__":
    main()
