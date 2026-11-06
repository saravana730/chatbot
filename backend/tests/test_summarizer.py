from app.ingestion.summarizer import _fallback_faqs, _parse_faqs, _split_to_budget


def test_split_to_budget_creates_multiple_sections():
    text = "\n\n".join([f"Paragraph {i} " + ("word " * 40) for i in range(20)])
    sections = _split_to_budget(text, max_tokens=80)
    assert len(sections) > 1
    assert all(s.strip() for s in sections)


def test_parse_faqs_json():
    raw = '{"faqs":[{"question":"Q1?","answer":"A1"},{"question":"Q2?","answer":"A2"}]}'
    faqs = _parse_faqs(raw, 2)
    assert len(faqs) == 2
    assert faqs[0]["question"] == "Q1?"


def test_fallback_faqs_count():
    faqs = _fallback_faqs("This is a short summary about a policy.", 2)
    assert len(faqs) == 2
    assert all(f["question"] and f["answer"] for f in faqs)
