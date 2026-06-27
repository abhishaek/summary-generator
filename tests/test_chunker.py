from summary_generator.services.chunker import _is_toc_noise, chunk_for_embedding


# --- Unit: TOC-noise detection ----------------------------------------------

def test_toc_dot_leader_line_is_noise():
    # Taken verbatim from a real PDF table of contents.
    line = "AWS CloudFormation ........................................................................................................................... 92\nAWS CloudTrail"
    assert _is_toc_noise(line) is True


def test_real_prose_is_not_noise():
    prose = (
        "Cloud computing provides a simple way to access servers, storage, databases "
        "and a broad set of application services over the internet. You pay only for "
        "what you use."
    )
    assert _is_toc_noise(prose) is False


def test_prose_with_ellipsis_is_not_noise():
    # A genuine ellipsis (3 dots) must not trip the filter.
    assert _is_toc_noise("Well... it depends on the workload and the budget.") is False


# --- Integration: the filter runs inside chunk_for_embedding ----------------

def test_chunk_for_embedding_drops_toc_keeps_prose():
    text = (
        "Introduction ........................................................... 1\n"
        "What is cloud computing? ............................................... 2\n"
        "Cloud computing provides a simple way to access servers, storage, and "
        "databases over the internet, and you pay only for what you use."
    )
    chunks = chunk_for_embedding(text)
    bodies = [c for c, _ in chunks]

    # The dotted TOC rows are gone; the explanatory sentence survives.
    assert any("pay only for what you use" in b for b in bodies)
    assert not any("..............." in b for b in bodies)
