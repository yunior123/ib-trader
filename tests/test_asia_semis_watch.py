import importlib.util
import os


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    path = os.path.join(REPO, "scripts", "asia_semis_watch.py")
    spec = importlib.util.spec_from_file_location("asia_semis_watch_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_quotes_delayed_retiradas():
    assert _load().quotes_block() == {}


def test_news_relevance_rejects_google_false_positive():
    m = _load()
    terms = ("tokyo electron", "advantest", "nikkei semiconductor")
    assert not m.relevant_title(
        "Cast Steel Rail Anchor Bolts Market To Hit 155 Index by 2035", terms
    )
    assert m.relevant_title("Advantest raises forecast on AI chip demand", terms)


def test_each_query_has_specific_relevance_terms():
    m = _load()
    assert all(terms for _query, _flag, terms in m.NEWS_Q)
