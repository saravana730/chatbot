from app.rag.retriever import extract_at_references, strip_at_mentions


def test_extract_multiple_refs():
    text = "Compare @Policy.pdf with @Guidelines.pdf please"
    assert extract_at_references(text) == ["Policy.pdf", "Guidelines.pdf"]


def test_extract_none():
    assert extract_at_references("What is the coverage?") == []


def test_extract_filename_with_spaces():
    text = "@Arabic Health Insurance Policy Document.png explain"
    assert extract_at_references(text) == [
        "Arabic Health Insurance Policy Document.png"
    ]


def test_strip_spaced_mention_leaves_question():
    text = "@Arabic Health Insurance Policy Document.png explain the coverage"
    cleaned = strip_at_mentions(
        text, ["Arabic Health Insurance Policy Document.png"]
    )
    assert cleaned == "explain the coverage"
