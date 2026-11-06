from app.rag.history import extractive_summary, split_sliding_window
from app.rag.retriever import maybe_rewrite_query


def test_split_keeps_last_10_turns():
    pairs = []
    for i in range(15):
        pairs.append(("user", f"q{i}"))
        pairs.append(("assistant", f"a{i}"))
    older, recent = split_sliding_window(pairs, max_turns=10)
    assert len(recent) == 20
    assert recent[0] == ("user", "q5")
    assert recent[-1] == ("assistant", "a14")
    assert len(older) == 10
    assert older[0] == ("user", "q0")


def test_extractive_summary_mentions_user_asks():
    older = [
        ("user", "@Motor1.pdf summarize"),
        ("assistant", "Policy number MTP…"),
        ("user", "what is the premium?"),
        ("assistant", "QAR 1000"),
    ]
    text = extractive_summary(older)
    assert "Motor1" in text or "summarize" in text
    assert "Earlier conversation" in text


def test_rewrite_skips_when_scoped():
    history = [("user", "@Motor1.pdf summarize"), ("assistant", "long motor answer")]
    out = maybe_rewrite_query(
        "summarize",
        history,
        scoped_filenames=["Arabic Health.png"],
    )
    assert out == "summarize"


def test_rewrite_skips_standalone_summarize():
    history = [("user", "tell me about motor"), ("assistant", "…")]
    out = maybe_rewrite_query("summarize this policy", history)
    assert out == "summarize this policy"


def test_rewrite_pronoun_followup():
    history = [("user", "coverage period for Scott"), ("assistant", "20 Sep 2026")]
    out = maybe_rewrite_query("what about that?", history)
    assert "prior context" in out.lower()
    assert "what about that?" in out
