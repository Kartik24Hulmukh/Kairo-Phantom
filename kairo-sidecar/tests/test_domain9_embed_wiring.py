import importlib.util


def test_embed_anything_installed():
    assert (
        importlib.util.find_spec("embed_anything") is not None
    ), "embed-anything must be installed (hard dep)"


def test_flag_true():
    from sidecar.parsers import media_embeddings as me

    assert me.HAS_EMBED_ANYTHING is True, "dep present but guard False = stale API regression"


def test_ctor_does_not_report_missing():
    from sidecar.parsers.media_embeddings import MediaEmbeddings

    try:
        MediaEmbeddings()
    except RuntimeError as exc:
        assert "not installed" not in str(exc), "wrongly reported missing dep"
