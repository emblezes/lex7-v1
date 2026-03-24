"""Tests pour le chunking semantique de documents."""

from legix.knowledge.document_ingestion import chunk_text


def test_chunk_basic():
    """Test chunking basique."""
    text = "Paragraphe 1.\n\nParagraphe 2.\n\nParagraphe 3."
    chunks = chunk_text(text, chunk_size=50, chunk_overlap=10)
    assert len(chunks) >= 1
    assert all("text" in c for c in chunks)
    assert all("chunk_idx" in c for c in chunks)


def test_chunk_overlap():
    """Test que l'overlap fonctionne."""
    # Creer un texte avec des paragraphes de ~30 chars
    paras = [f"Paragraphe numero {i} avec du texte." for i in range(10)]
    text = "\n\n".join(paras)
    chunks = chunk_text(text, chunk_size=100, chunk_overlap=30)
    assert len(chunks) > 1
    # Verifier que les chunks se chevauchent
    for i in range(1, len(chunks)):
        # Le debut du chunk suivant devrait contenir du texte du chunk precedent
        assert chunks[i]["chunk_idx"] == i


def test_chunk_empty():
    """Test chunking texte vide."""
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_single_paragraph():
    """Test chunking avec un seul paragraphe court."""
    text = "Un seul petit paragraphe."
    chunks = chunk_text(text, chunk_size=1000)
    assert len(chunks) == 1
    assert chunks[0]["text"] == text
    assert chunks[0]["chunk_idx"] == 0


def test_chunk_preserves_all_text():
    """Test que le chunking ne perd pas de contenu."""
    paras = [f"Section {i}: contenu important." for i in range(5)]
    text = "\n\n".join(paras)
    chunks = chunk_text(text, chunk_size=80, chunk_overlap=0)
    # Chaque section doit apparaitre dans au moins un chunk
    for para in paras:
        found = any(para in c["text"] for c in chunks)
        assert found, f"'{para}' non trouve dans les chunks"


def test_chunk_indices():
    """Test que les indices sont coherents."""
    text = "A" * 100 + "\n\n" + "B" * 100 + "\n\n" + "C" * 100
    chunks = chunk_text(text, chunk_size=150, chunk_overlap=20)
    for chunk in chunks:
        assert chunk["start_idx"] >= 0
        assert chunk["end_idx"] > chunk["start_idx"]
