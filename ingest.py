import argparse
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

MANUALS_DIR = Path(__file__).parent / "manuals"
STORAGE_DIR = Path(__file__).parent / "storage"
COLLECTION_NAME = "sifecat_manuals"


def main():
    parser = argparse.ArgumentParser(description="Ingesta de PDFs a ChromaDB")
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

    if not MANUALS_DIR.exists() or not any(MANUALS_DIR.iterdir()):
        print(f"ERROR: No hi ha PDFs a {MANUALS_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"📚 Llegint documents de {MANUALS_DIR}...")
    documents = SimpleDirectoryReader(
        input_dir=str(MANUALS_DIR),
        required_exts=[".pdf"],
        recursive=True,
    ).load_data()
    print(f"   → {len(documents)} pàgines/documents carregats")

    Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")
    Settings.node_parser = SentenceSplitter(chunk_size=800, chunk_overlap=100)

    print("✂️  Trocejant en chunks de 800 tokens (overlap 100)...")
    nodes = Settings.node_parser.get_nodes_from_documents(
        documents, show_progress=True
    )
    print(f"   → {len(nodes)} chunks generats")

    print(f"💾 Creant ChromaDB persistent a {STORAGE_DIR}...")
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    chroma_client = chromadb.PersistentClient(path=str(STORAGE_DIR))
    chroma_collection = chroma_client.get_or_create_collection(COLLECTION_NAME)
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    print("🔢 Generant embeddings amb OpenAI text-embedding-3-small...")
    VectorStoreIndex(
        nodes=nodes,
        storage_context=storage_context,
        show_progress=True,
    )

    print(f"✅ Ingesta completada. {len(nodes)} chunks indexats a {STORAGE_DIR}")


if __name__ == "__main__":
    main()
