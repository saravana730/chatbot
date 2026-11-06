from app.rag.intent import classify_intent
from app.services.chat_service import _default_question


def test_empty_with_chips_is_summarize():
    assert (
        classify_intent("", scoped_count=2, question_was_empty=True) == "summarize"
    )


def test_compare_keywords():
    assert classify_intent("compare these two policies") == "compare"
    assert classify_intent("Motor vs Medical coverage") == "compare"
    assert classify_intent("what is the difference between them?") == "compare"


def test_summarize_keywords():
    assert classify_intent("summarize SBI.pdf") == "summarize"
    assert classify_intent("give me an overview") == "summarize"
    assert classify_intent("key points please") == "summarize"


def test_default_is_qa():
    assert classify_intent("What is the premium amount?") == "qa"
    assert classify_intent("Who is the insured?") == "qa"


def test_default_question_multi_chip():
    q = _default_question(["A.pdf", "B.pdf"])
    assert "A.pdf" in q and "B.pdf" in q
    assert "each" in q.lower()


def test_default_question_single():
    assert "A.pdf" in _default_question(["A.pdf"])
