from ihear.summarizer import Summarizer


def test_summariser_returns_top_sentences_in_order():
    text = (
        "The first sentence introduces the topic. "
        "The second sentence contains important information about the subject. "
        "Another sentence adds more context to the discussion. "
        "Finally, this closing sentence wraps things up neatly."
    )
    summary = Summarizer(max_sentences=2).summarise(text)
    assert "important information" in summary
    assert summary.count(".") == 2
