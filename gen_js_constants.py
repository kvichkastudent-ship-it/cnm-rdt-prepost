#!/usr/bin/env python3
"""
gen_js_constants.py
===================
Generates lib/constants.mjs from fetch_rdt_results.py.

WHY THIS EXISTS
---------------
The Netlify function has to score submissions exactly the way the Python script
does, or the live dashboard and the generated one would disagree. That means the
answer key, the 15 question labels, the 60 option texts, the province and
position labels and the pass mark all have to exist in JavaScript too.

Transcribing 75 Khmer strings by hand is how spelling drift gets introduced, so
nothing is transcribed: this reads the Python as the single source of truth and
writes the JavaScript. Re-run it after ANY change to the labels or answer key:

    python gen_js_constants.py

verify_form_sync.py already guards Python <-> XLSForm. This guards
Python -> JavaScript.
"""

import importlib.util
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "fetch_rdt_results.py")
OUT = os.path.join(HERE, "lib", "constants.mjs")


def load(path):
    spec = importlib.util.spec_from_file_location("rdt", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    if not os.path.exists(SRC):
        sys.exit("not found: %s" % SRC)
    m = load(SRC)

    # ANSWER_KEY maps q -> (letter, points); JS only needs the letter and points
    answer_key = {q: {"letter": v[0], "points": v[1]} for q, v in m.ANSWER_KEY.items()}

    payload = {
        "MAX_SCORE": m.MAX_SCORE,
        "PASS_THRESHOLD": m.PASS_THRESHOLD,
        "OPTION_LETTERS": list(m.OPTION_LETTERS),
        "ANSWER_KEY": answer_key,
        "QUESTION_LABELS": dict(m.QUESTION_LABELS),
        "OPTION_TEXTS": {k: list(v) for k, v in m.OPTION_TEXTS.items()},
        "POSITION_LABELS": dict(m.POSITION_LABELS),
        "TESTTYPE_LABELS": dict(m.TESTTYPE_LABELS),
        "PROVINCE_ORDER": list(m.PROVINCE_ORDER),
        "PROVINCE_LABELS": dict(m.PROVINCE_LABELS),
        "PROVINCE_EN": dict(m.PROVINCE_EN),
        "NGO_BUCKET_KH": m.NGO_BUCKET_KH,
        "NGO_BUCKET_EN": m.NGO_BUCKET_EN,
        "EXPECTED_BY_PROVINCE": dict(m.EXPECTED_BY_PROVINCE),
        "EXPECTED_BY_PROVINCE_POSITION": {k: dict(v) if v else v
                                          for k, v in m.EXPECTED_BY_PROVINCE_POSITION.items()},
    }

    body = ["// GENERATED FILE - DO NOT EDIT BY HAND.",
            "// Produced by gen_js_constants.py from fetch_rdt_results.py.",
            "// Re-run that script after changing any label, the answer key or the pass mark.",
            ""]
    for name, value in payload.items():
        body.append("export const %s = %s;" % (
            name, json.dumps(value, ensure_ascii=False, indent=2)))
        body.append("")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    io.open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(body))

    print("wrote %s" % os.path.relpath(OUT, HERE))
    print("  questions      : %d" % len(payload["QUESTION_LABELS"]))
    print("  option texts   : %d" % sum(len(v) for v in payload["OPTION_TEXTS"].values()))
    print("  provinces      : %d" % len(payload["PROVINCE_LABELS"]))
    print("  max score      : %s" % payload["MAX_SCORE"])
    print("  pass threshold : %s" % payload["PASS_THRESHOLD"])


if __name__ == "__main__":
    main()
