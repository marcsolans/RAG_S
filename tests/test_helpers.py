"""Tests unitaris dels helpers purs de SIFERAG.

No requereixen claus d'API ni índex: importar `app`/`ingest` és segur perquè
l'auto-reindex surt aviat si no hi ha storage/ ni OPENAI_API_KEY.
"""
import os

import app
import ingest


# ----------------------------- ingest.file_metadata -----------------------------

def test_file_metadata_extracts_category_and_relpath():
    md = ingest.file_metadata("/srv/app/documents/normativa/Reglament.pdf")
    assert md["category"] == "normativa"
    assert md["file_name"] == "Reglament.pdf"
    assert md["rel_path"] == "normativa/Reglament.pdf"


def test_file_metadata_uncategorized_when_no_documents_dir():
    md = ingest.file_metadata("/tmp/loose/file.pdf")
    assert md["category"] == "uncategorized"


# ----------------------------- ingest._existing_filenames -----------------------

class _FakeCollection:
    def __init__(self, metadatas):
        self._metadatas = metadatas

    def get(self, include=None):
        return {"metadatas": self._metadatas}


def test_existing_filenames_dedupes_and_ignores_empty():
    col = _FakeCollection([{"file_name": "a.pdf"}, {"file_name": "b.pdf"}, {}, None, {"file_name": "a.pdf"}])
    assert ingest._existing_filenames(col) == {"a.pdf", "b.pdf"}


def test_existing_filenames_handles_get_failure():
    class Boom:
        def get(self, include=None):
            raise RuntimeError("no collection")
    assert ingest._existing_filenames(Boom()) == set()


# ----------------------------- ingest._clear_dir_contents ------------------------

def test_clear_dir_contents_empties_without_removing_dir(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("y")
    ingest._clear_dir_contents(tmp_path)
    assert tmp_path.exists()
    assert list(tmp_path.iterdir()) == []


# ----------------------------- app._load_users ----------------------------------

def test_load_users_parses_valid_json(monkeypatch):
    monkeypatch.setenv("USERS", '{"Marc": "secret", "Anna": "clau"}')
    users = app._load_users()
    assert users == {"marc": "secret", "anna": "clau"}


def test_load_users_empty_when_unset(monkeypatch):
    monkeypatch.delenv("USERS", raising=False)
    assert app._load_users() == {}


def test_load_users_empty_on_bad_json(monkeypatch):
    monkeypatch.setenv("USERS", "{not valid json")
    assert app._load_users() == {}


# ----------------------------- app._is_admin ------------------------------------

def test_is_admin_matches_case_insensitive(monkeypatch):
    monkeypatch.setenv("ADMIN_USERS", "Marc, admin")
    assert app._is_admin("MARC") is True
    assert app._is_admin("admin") is True
    assert app._is_admin("anna") is False


# ----------------------------- app._format_sources ------------------------------

class _FakeNode:
    def __init__(self, metadata):
        self.metadata = metadata


class _FakeSourceNode:
    def __init__(self, metadata):
        self.node = _FakeNode(metadata)


def test_format_sources_empty_returns_empty():
    assert app._format_sources(None) == ""
    assert app._format_sources([]) == ""


def test_format_sources_builds_html_card_with_page():
    nodes = [_FakeSourceNode({"file_name": "x.pdf", "category": "manuals", "page_label": "12"})]
    html_out = app._format_sources(nodes)
    assert "siferag-sources" in html_out
    assert "/documents/manuals/x.pdf" in html_out
    assert "pàg. 12" in html_out


def test_format_sources_dedupes_same_file_and_page():
    md = {"file_name": "x.pdf", "category": "manuals", "page_label": "3"}
    nodes = [_FakeSourceNode(dict(md)), _FakeSourceNode(dict(md))]
    html_out = app._format_sources(nodes)
    assert html_out.count('class="siferag-source"') == 1


def test_format_sources_caps_at_six():
    nodes = [
        _FakeSourceNode({"file_name": f"f{i}.pdf", "category": "manuals", "page_label": str(i)})
        for i in range(10)
    ]
    html_out = app._format_sources(nodes)
    assert html_out.count('class="siferag-source"') == 6


def test_format_sources_skips_nodes_without_filename():
    nodes = [_FakeSourceNode({"category": "manuals"})]
    assert app._format_sources(nodes) == ""
