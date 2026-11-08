#!/usr/bin/env python3
"""Official NepTel v0.2 scorer.

Word error rate on normalized text. Both sides are normalized the same way: digits become spoken Nepali words,
English words in either script map to one Devanagari form (benchmark/latin_map.json), punctuation is removed.

    python eval/score_v02.py --hyp your_outputs.json
    python eval/score_v02.py --hyp a.json --compare b.json      # paired segment bootstrap, b minus a

Hypothesis file: a JSON list of {"seg": ..., "text": ...}.
"""
import argparse
import html
import json
import random
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import nepali_numbers  # noqa: E402

BENCH = HERE.parent / "benchmark"
MAP = json.loads((BENCH / "latin_map.json").read_text(encoding="utf-8"))
MAPPING, MAX_WORDS = MAP["mapping"], MAP["max_words"]
LATIN = re.compile(r"[A-Za-z]+(?:['-][A-Za-z]+)*(?:[ \t]+[A-Za-z]+(?:['-][A-Za-z]+)*)*")
AT = re.compile(r"\s*@\s*")
DOT = re.compile(r"(?<=[A-Za-zऀ-ॣ॰-ॿ])\.(?=[A-Za-zऀ-ॣ॰-ॿ])")
EVENT = re.compile(r"[\[(][^\])]*[\])]")
PUNCT = re.compile(r"[।॥,.?!:;\"“”‘’…–—_/\\|*~^`<>{}=+#%&@$]")
LAT_WORD = re.compile(r"^[A-Za-z][A-Za-z'\-]*$")


def replace_run(match):
    words, out, i = match.group().split(), [], 0
    while i < len(words):
        for length in range(min(MAX_WORDS, len(words) - i), 0, -1):
            key = " ".join(words[i:i + length]).lower()
            if key in MAPPING:
                out.append(MAPPING[key])
                i += length
                break
        else:
            out.append(words[i])
            i += 1
    return " ".join(out)


def clean(text):
    s = unicodedata.normalize("NFC", html.unescape(text)).replace("‌", "").replace("‍", "").replace(">>", " ")
    s = PUNCT.sub(" ", EVENT.sub(" ", s))
    out = []
    for tok in s.split():
        tok = tok.strip("-'")
        if not tok:
            continue
        if LAT_WORD.match(tok):
            letters = tok.replace("-", "").replace("'", "")
            tok = tok if (len(letters) >= 2 and letters.isupper()) else tok.lower()
        out.append(tok)
    return " ".join(out)


def normalize(text):
    text = DOT.sub(" dot ", AT.sub(" at the rate ", text))
    if re.search("[0-9०-९]", text):
        text = nepali_numbers.normalize(text, english=False)
    return clean(LATIN.sub(replace_run, text))


def edits(a, b):
    d = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        p, d[0] = d[0], i
        for j in range(1, len(b) + 1):
            c = min(d[j] + 1, d[j - 1] + 1, p + (a[i - 1] != b[j - 1]))
            p, d[j] = d[j], c
    return d[len(b)]


def load_refs(path):
    return {s["seg"]: normalize(s["reference_verbatim"]).split() for s in json.loads(Path(path).read_text(encoding="utf-8"))["segments"]}


def score(refs, path):
    hyps = {r["seg"]: r["text"] for r in json.loads(Path(path).read_text(encoding="utf-8"))}
    missing = [k for k in refs if k not in hyps]
    if missing:
        sys.exit(f"{path}: missing {len(missing)} segments, for example {missing[0]}")
    return {k: edits(r, normalize(hyps[k]).split()) for k, r in refs.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refs", default=str(BENCH / "references.json"))
    ap.add_argument("--hyp", required=True)
    ap.add_argument("--compare")
    a = ap.parse_args()
    refs = load_refs(a.refs)
    words = sum(map(len, refs.values()))
    e = score(refs, a.hyp)
    print(f"{len(refs)} segments, {words} words, WER {100 * sum(e.values()) / words:.2f}")
    if a.compare:
        f = score(refs, a.compare)
        keys, draws = sorted(refs), []
        random.seed(20261108)
        for _ in range(5000):
            s = [random.choice(keys) for _ in keys]
            draws.append(100 * (sum(f[k] for k in s) - sum(e[k] for k in s)) / sum(len(refs[k]) for k in s))
        draws.sort()
        print(f"second WER {100 * sum(f.values()) / words:.2f}; difference {sum(draws) / len(draws):+.2f} points, 95% CI [{draws[125]:+.2f}, {draws[4874]:+.2f}]")


if __name__ == "__main__":
    main()
