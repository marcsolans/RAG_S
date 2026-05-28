"""Eval de recuperació (retrieval) per a SIFERAG.

Per cada pregunta del golden set, comprova si el document esperat apareix
entre els top-K fragments recuperats de ChromaDB. Mètrica: recall@K a nivell
de document — el senyal més important d'un RAG (si no recuperes la font,
no pots citar-la ni respondre-hi bé).

Requereix OPENAI_API_KEY i un índex ja construït a storage/.
Ús:  python eval/run_eval.py      (EVAL_TOP_K=8 per defecte)
No depèn d'Anthropic: només avalua la recuperació, no la generació.
"""
import json
import os
import sys
import unicodedata
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from llama_index.core import Settings, StorageContext, VectorStoreIndex
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
STORAGE_DIR = ROOT / "storage"
COLLECTION_NAME = "sifecat_manuals"
GOLDEN = Path(__file__).resolve().parent / "golden_set.json"
TOP_K = int(os.getenv("EVAL_TOP_K", "8"))


def main() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY requerida per generar embeddings.", file=sys.stderr)
        sys.exit(1)
    if not STORAGE_DIR.exists():
        print(f"ERROR: no existeix l'índex a {STORAGE_DIR}. Executa ingest.py primer.", file=sys.stderr)
        sys.exit(1)

    Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")
    client = chromadb.PersistentClient(path=str(STORAGE_DIR))
    col = client.get_or_create_collection(COLLECTION_NAME)
    vs = ChromaVectorStore(chroma_collection=col)
    index = VectorStoreIndex.from_vector_store(
        vector_store=vs, storage_context=StorageContext.from_defaults(vector_store=vs)
    )
    retriever = index.as_retriever(similarity_top_k=TOP_K)

    def norm(s: str) -> str:
        # macOS desa els noms de fitxer en NFD; el JSON pot ser NFC. Normalitzem.
        return unicodedata.normalize("NFC", s or "")

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    passed = 0
    print(f"Eval de recuperació · top_k={TOP_K} · {len(golden)} preguntes\n")
    for item in golden:
        q, expected = item["question"], norm(item["expected_source"])
        nodes = retriever.retrieve(q)
        files = {norm(n.node.metadata.get("file_name")) for n in nodes}
        ok = expected in files
        passed += int(ok)
        print(f"[{'OK ' if ok else 'FAIL'}] {q[:58]:58s} → {expected}")
        if not ok:
            print(f"         recuperat: {sorted(f for f in files if f)}")

    n = len(golden)
    print(f"\nRecall@{TOP_K}: {passed}/{n} = {passed / n:.0%}")
    sys.exit(0 if passed == n else 1)


if __name__ == "__main__":
    main()
