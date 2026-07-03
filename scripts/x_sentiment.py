#!/usr/bin/env python3
"""x_sentiment.py — captura sentimiento de x.com via search/recent (cuenta de Yunior, OAuth1).

Uso: ./venv/bin/python scripts/x_sentiment.py --preset skhynix|samsung|kospi|<SYM-flota>
     [--query "..."] [--max 100]
Una llamada = una lectura pagada. Guarda crudo en data/x_sentiment/<preset>_<ts>.json
(atomico) y imprime tally pos/neg/neutro + top tuits. Fail-loud: sin credenciales o
HTTP != 200 levanta, jamas devuelve un numero plausible."""
import argparse, json, os, re, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import x_post_common as xc

PRESETS = {
    "skhynix": "(SK하이닉스 OR 하이닉스) lang:ko -is:retweet",
    "samsung": "(삼성전자 OR 005930) lang:ko -is:retweet",
    "kospi":   "(코스피 OR KOSPI) lang:ko -is:retweet",
}
POS_KO = ["양전", "추매", "매수", "반등", "숏커버", "숏스퀴즈", "과도", "저가", "바닥",
          "주주환원", "역대 최대", "역대급", "사상 최대", "상승", "호재"]
NEG_KO = ["미스", "하회", "하향", "급락", "숏뷰", "걱정", "어닝쇼크", "투매", "폭락",
          "쇼크", "실망", "미달", "악재", "하락"]
POS_EN = ["bull", "buy", "long", "beat", "squeeze", "oversold", "bottom", "bounce", "upgrade"]
NEG_EN = ["bear", "sell", "short", "miss", "downgrade", "dump", "crash", "top", "overbought"]


def classify(texts, pos, neg):
    p = n = m = 0
    for tx in texts:
        low = tx.lower()
        sp = sum(k in tx or k in low for k in pos)
        sn = sum(k in tx or k in low for k in neg)
        if sp > sn: p += 1
        elif sn > sp: n += 1
        else: m += 1
    return p, n, m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", default=None)
    ap.add_argument("--query", default=None)
    ap.add_argument("--max", type=int, default=100)
    a = ap.parse_args()
    if a.preset and a.preset in PRESETS:
        q, tag, ko = PRESETS[a.preset], a.preset, True
    elif a.preset:
        sym = a.preset.upper()
        q, tag, ko = f"(${sym} OR {sym}) lang:en -is:retweet", sym.lower(), False
    elif a.query:
        q, tag, ko = a.query, "custom", False
    else:
        ap.error("--preset o --query obligatorio")

    env = xc.load_env()
    auth = xc.make_auth(env)
    import requests
    r = requests.get("https://api.twitter.com/2/tweets/search/recent",
                     params={"query": q, "max_results": max(10, min(100, a.max)),
                             "tweet.fields": "created_at,public_metrics"},
                     auth=auth, timeout=20)
    if r.status_code != 200:
        raise SystemExit(f"X API {r.status_code}: {r.text[:200]}")
    j = r.json()
    d = j.get("data") or []
    outdir = os.path.join(ROOT, "data", "x_sentiment")
    os.makedirs(outdir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(outdir, f"{tag}_{ts}.json")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"ts": ts, "query": q, "n": len(d), "data": d}, f, ensure_ascii=False)
    os.replace(tmp, path)

    pos, neg = (POS_KO, NEG_KO) if ko else (POS_EN, NEG_EN)
    p, n, m = classify([t["text"] for t in d], pos, neg)
    d.sort(key=lambda t: -(t["public_metrics"]["like_count"] + 2 * t["public_metrics"]["retweet_count"]))
    print(f"{tag}: {len(d)} tuits | pos {p} / neg {n} / neutro {m} | {path}")
    for t in d[:8]:
        pm = t["public_metrics"]
        print(f"  [{t['created_at'][5:16]}] L{pm['like_count']} R{pm['retweet_count']} | "
              + re.sub(r"\s+", " ", t["text"])[:140])


if __name__ == "__main__":
    main()
