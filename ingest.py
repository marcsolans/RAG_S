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


def main():
    parser = argparse.ArgumentParser(description="Ingesta de documents a ChromaDB")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reindexa aunque storage/ ya exista",
    )
    args = parser.parse_args()

    load_dotenv()

    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY no està definida a .env", file=sys.stderr)
        sys.exit(1)

    if STORAGE_DIR.exists():
        if not args.force:
            print(
                f"⚠️  La carpeta {STORAGE_DIR} ja existeix. "
                "Fes servir --force per reindexar."
            )
            sys.exit(0)
        print(f"🗑️  Esborrant índex existent a {STORAGE_DIR}...")
        shutil.rmtree(STORAGE_DIR)

    if not DOCUMENTS_DIR.exists():
        print(f"ERROR: No existeix la carpeta {DOCUMENTS_DIR}", file=sys.stderr)
        sys.exit(1)

    # Comptem PDFs per validar
    pdf_files = list(DOCUMENTS_DIR.rglob("*.pdf"))
    if not pdf_files:
        print(f"ERROR: No s'han trobat PDFs dins de {DOCUMENTS_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"📚 Llegint {len(pdf_files)} PDFs de {DOCUMENTS_DIR} (recursiu)...")
    # Mostra per categoria
    by_cat: dict[str, int] = {}
    for f in pdf_files:
        rel = f.relative_to(DOCUMENTS_DIR)
        cat = rel.parts[0] if len(rel.parts) > 1 else "uncategorized"
        by_cat[cat] = by_cat.get(cat, 0) + 1
    for cat, n in sorted(by_cat.items()):
        print(f"   ├─ {cat}: {n} fitxers")

    documents = SimpleDirectoryReader(
        input_dir=str(DOCUMENTS_DIR),
        required_exts=[".pdf"],
        recursive=True,
        file_metadata=file_metadata,
    ).load_data()
    print(f"   → {len(documents)} pàgines/documents carregats")

    Settings.embed_model = OpenAIEmbedding(
        model="text-embedding-3-small",
        embed_batch_size=EMBED_BATCH_SIZE,
    )
    Settings.node_parser = SentenceSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )

    print(f"✂️  Trocejant en chunks de {CHUNK_SIZE} tokens (overlap {CHUNK_OVERLAP})...")
    nodes = Settings.node_parser.get_nodes_from_documents(
        documents, show_progress=True
    )
    n_nodes = len(nodes)
    print(f"   → {n_nodes} chunks generats")

    # Alliberem les pàgines originals: no les necessitem un cop tenim els chunks.
    documents.clear()
    del documents
    gc.collect()

    print(f"💾 Creant ChromaDB persistent a {STORAGE_DIR}...")
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    chroma_client = chromadb.PersistentClient(path=str(STORAGE_DIR))
    chroma_collection = chroma_client.get_or_create_collection(COLLECTION_NAME)
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # Construïm l'índex buit i inserim els nodes per lots: així mai mantenim
    # tots els embeddings + nodes a RAM alhora (clau per a Render Free 512 MB).
    print(
        f"🔢 Generant embeddings (text-embedding-3-small) per lots de {EMBED_BATCH_SIZE}..."
    )
    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store, storage_context=storage_context
    )

    inserted = 0
    for i in range(0, n_nodes, EMBED_BATCH_SIZE):
        batch = nodes[i : i + EMBED_BATCH_SIZE]
        index.insert_nodes(batch)
        inserted += len(batch)
        # Allibera referències del lot abans del següent.
        for j in range(i, i + len(batch)):
            nodes[j] = None
        gc.collect()
        print(f"   ⤳ {inserted}/{n_nodes} chunks indexats", flush=True)

    print(f"✅ Ingesta completada. {inserted} chunks indexats a {STORAGE_DIR}")


if __name__ == "__main__":
    main()
