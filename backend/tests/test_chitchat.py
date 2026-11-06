from app.rag.chitchat import is_chitchat


def test_greetings_are_chitchat():
    assert is_chitchat("hi")
    assert is_chitchat("Hello!")
    assert is_chitchat("hey there")
    assert is_chitchat("thanks")
    assert is_chitchat("who are you")


def test_doc_questions_are_not_chitchat():
    assert not is_chitchat("What is the coverage period?")
    assert not is_chitchat("hi @Policy.pdf what is covered?")
    assert not is_chitchat("Summarize the exclusions")
