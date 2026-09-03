#!/usr/bin/env python3
"""
fetch_rdt_results.py
====================
Pulls Pre/Post submissions from the CNM Malaria RDT ("FIRST RESPONSE") Knowledge
Test on KoboToolbox, scores them against ANSWER_KEY, and rebuilds a
self-contained HTML dashboard plus a flat CSV export.

IMPORTANT LIMITATION
---------------------
The form has no name/ID field, so a person's Pre-test cannot be matched to their
Post-test. Everything here therefore compares Pre vs Post at the AGGREGATE level
(group mean, per-question accuracy, per-position and per-province breakdowns).
"Avg Change" is the difference of two group means, NOT the average individual
improvement. Add a required staff-ID question to the form if per-person gain is
needed, and this script can be extended to pair submissions on it.

KEEP IN SYNC WITH THE XLSFORM
------------------------------
ANSWER_KEY, QUESTION_LABELS, OPTION_TEXTS and PROVINCE_LABELS below all duplicate
content that also lives in CNM_RDT_PrePostTest_KoboXLSForm*.xlsx. Run
    python verify_form_sync.py <the-xlsx>
after ANY edit to either side - it fails loudly on drift instead of letting the
dashboard silently mislabel results.

SETUP
-----
1. pip install requests            (openpyxl too, for verify_form_sync.py)

2. Kobo API token:
   KoboToolbox -> profile icon -> ACCOUNT SETTINGS -> Security -> API Key

3. Asset UID from the form URL, e.g.
   https://eu.kobotoolbox.org/#/forms/aXXXXXXXXXXXXXXXXXXXXXX/summary

4. Set environment variables.

   Windows PowerShell (per session):
       $env:KOBO_SERVER    = "https://eu.kobotoolbox.org"
       $env:KOBO_API_TOKEN = "your_token_here"
       $env:KOBO_ASSET_UID = "aRAkKsGrthphw4Nqd7egNY"

   macOS / Linux:
       export KOBO_SERVER="https://eu.kobotoolbox.org"
       export KOBO_API_TOKEN="your_token_here"
       export KOBO_ASSET_UID="aRAkKsGrthphw4Nqd7egNY"

   The token is a credential - do not commit it or paste it into the dashboard.
   It stays on the machine that runs this script; the generated HTML never
   contains it.

   NOTE: run this script from the folder that holds rdt_dashboard_template.html
   (the template path is relative).

5. Run against live submissions:
       python fetch_rdt_results.py
   -> CNM_RDT_Dashboard.html + CNM_RDT_Results.csv

   Or preview with generated sample data:
       python fetch_rdt_results.py --sample
   -> CNM_RDT_Dashboard_SAMPLE.html + CNM_RDT_Results_SAMPLE.csv
"""

import io
import os
import sys
import csv
import json
import argparse
import random
from datetime import datetime, timezone

import requests

# ---------------------------------------------------------------------------
KOBO_SERVER = os.environ.get("KOBO_SERVER", "https://kf.kobotoolbox.org")
API_TOKEN = os.environ.get("KOBO_API_TOKEN", "")
ASSET_UID = os.environ.get("KOBO_ASSET_UID", "aRAkKsGrthphw4Nqd7egNY")

OUTPUT_HTML = "CNM_RDT_Dashboard.html"
OUTPUT_CSV = "CNM_RDT_Results.csv"
# --sample writes to its own filenames so a preview can never overwrite a
# dashboard built from real submissions (main() swaps these in).
OUTPUT_HTML_SAMPLE = "CNM_RDT_Dashboard_SAMPLE.html" 
OUTPUT_CSV_SAMPLE = "CNM_RDT_Results_SAMPLE.csv"
TEMPLATE_HTML = "rdt_dashboard_template.html"

# ---------------------------------------------------------------------------
# Answer key -- must match CNM_RDT_PrePostTest_KoboXLSForm.xlsx exactly
# ---------------------------------------------------------------------------
ANSWER_KEY = {
    "q1": ("b", 1), "q2": ("a", 1), "q3": ("c", 1), "q4": ("b", 1),
    "q5": ("c", 1), "q6": ("c", 1), "q7": ("b", 1), "q8": ("b", 1),
    "q9": ("b", 1), "q10": ("a", 1), "q11": ("b", 1), "q12": ("b", 1),
    "q13": ("c", 1), "q14": ("a", 1), "q15": ("b", 1),
}
MAX_SCORE = sum(pts for _, pts in ANSWER_KEY.values())  # 15, rescaled to /100 in dashboard

QUESTION_LABELS = {
    "q1": "១. តើ Malaria RDT ត្រូវបានប្រើសម្រាប់គោលបំណងអ្វី?",
    "q2": "២. RDT First Response pLDH/HRP2 Combo អាចរកឃើញ marker សំខាន់ៗអ្វីខ្លះ?",
    "q3": "៣. HRP2 មានទំនាក់ទំនងជាចម្បងជាមួយមេរោគប្រភេទណា?",
    "q4": "៤. pLDH/PAN ក្នុង RDT មានសារៈសំខាន់អ្វី?",
    "q5": "៥. តើសំណាកអ្វីអាចប្រើសម្រាប់ RDT នេះ?",
    "q6": "៦. ប្រសិនបើ RDT អវិជ្ជមាន ប៉ុន្តែអ្នកជំងឺមានរោគសញ្ញា និងប្រវត្តិធ្វើដំណើរទៅតំបន់មានហានិភ័យខ្ពស់ តើគួរធ្វើដូចម្ដេច?",
    "q7": "៧. ហេតុអ្វីបានជាត្រូវប្រុងប្រយ័ត្នចំពោះ RDT អវិជ្ជមានក្នុងករណី parasite density ទាប?",
    "q8": "៨. តើលក្ខខណ្ឌសំខាន់បំផុតមួយក្នុងការរក្សាទុក RDT ដែលបង្ហាញលើប្រអប់នេះគឺអ្វី?",
    "q9": "៩. ប្រសិនបើ RDT បង្ហាញលទ្ធផល Positive តើបុគ្គលិកសុខាភិបាលគួរធ្វើអ្វីជំហានបន្ទាប់?",
    "q10": "១០. សម្រាប់អ្នកជំងឺដែលត្រូវបានបញ្ជាក់ថាមាន P. vivax តើការគ្រប់គ្រងតាមកម្មវិធីគ្រុនចាញ់កម្ពុជាគួរយកចិត្តទុកដាក់លើអ្វីបន្ថែម?",
    "q11": "១១. នៅពេលចុះត្រួតពិនិត្យ RDT នៅមូលដ្ឋានសុខាភិបាល តើចំណុចណាមួយដែលអ្នកត្រួតពិនិត្យត្រូវពិនិត្យជាមុន?",
    "q12": "១២. តើហេតុអ្វីបានជាត្រូវពិនិត្យ Lot Number និង Expiry Date របស់ RDT នៅពេល Field Supervision?",
    "q13": "១៣. ប្រសិនបើអ្នកត្រួតពិនិត្យឃើញថា RDT ត្រូវបានរក្សាទុកក្រៅលក្ខខណ្ឌដែលក្រុមហ៊ុនផលិតបានកំណត់ តើគួរធ្វើអ្វី?",
    "q14": "១៤. ក្នុងការត្រួតពិនិត្យគុណភាព RDT នៅវាល តើមួយណាជាចំណុចសំខាន់ក្នុងការសង្កេតការអនុវត្តរបស់បុគ្គលិក?",
    "q15": "១៥. ប្រសិនបើ Field Supervisor រកឃើញភាពខុសប្រក្រតី ឬលទ្ធផល RDT មិនស្របគ្នា តើសកម្មភាព QA សមស្របបំផុតគឺអ្វី?",
}

# Pass mark. Mirrors the XLSForm's result_label rule: total_100 >= 80, which with
# 15 equally-weighted questions means exactly 12 correct.
PASS_THRESHOLD = 80.0

POSITION_LABELS = {"pms": "PMS", "odms": "ODMS", "hc": "HC",
                   # NGO/partner staff sit outside the provincial structure, so the
                   # form skips province/OD/HC for them and asks org_name instead
                   "ngo": "NGO/Partner", "other": "Other"}

# Province choice names -> labels, taken verbatim from the XLSForm `choices` sheet.
# PROVINCE_ORDER is the roster order the training used, not alphabetical - the
# by-province chart follows it so the bars stay in a familiar sequence.
NGO_BUCKET_KH = "NGO / ដៃគូ"
NGO_BUCKET_EN = "NGO / Partner"

PROVINCE_ORDER = ["prov_1", "prov_2", "prov_3", "prov_4", "prov_5", "prov_6"]
PROVINCE_LABELS = {
    "prov_1": "ស្ទឹងត្រែង",
    "prov_2": "ព្រះវិហារ",
    "prov_3": "សៀមរាប",
    "prov_4": "ឧត្តរមានជ័យ",
    "prov_5": "បន្ទាយមានជ័យ",
    "prov_6": "កំពង់ស្ពឺ",
    # the form's "other (specify)" choice; the typed text lands in
    # province_other in the CSV, while grouping stays under one "Other" bucket
    "other": "ផ្សេងទៀត",
}
# ---------------------------------------------------------------------------
# EXPECTED PARTICIPANTS PER PROVINCE - fill these in from the training roster.
#
# This is the denominator for submission tracking ("48 of 60 submitted, 12
# still missing"). The form itself cannot supply it: the cascade lists name 6
# provinces / 16 ODs / 109 health centres, but nothing records how many PEOPLE
# each was sending.
#
# Leave a province as None if you do not have its figure - it is then excluded
# from the totals rather than counted as zero. With ALL of them None the
# tracking simply switches off and the dashboard shows received counts only,
# exactly as before.
#
# NOTE: this counts submissions per province, not per person. Without a
# name/ID question on the form there is no way to say WHICH individuals are
# missing - only how many.
# Expected participants broken down by level, straight from the participant list
# (បញ្ជីអ្នកចូលរួម_CNM.docx): one person per row, 6 PMS + 16 ODMS + 109 HC = 131.
# The 109 health centres match the form's cascade list exactly.
#
#   PMS   Provincial Malaria Supervisor  (PHD level)
#   ODMS  Operational District Malaria Supervisor
#   HC    Health Centre staff
#
# Set a province to None to exclude it from tracking; set a level to 0 if that
# level sends nobody.
EXPECTED_BY_PROVINCE_POSITION = {
    "prov_1": {"PMS": 1, "ODMS": 1, "HC": 18},   # Stung Treng       20
    "prov_2": {"PMS": 1, "ODMS": 1, "HC": 18},   # Preah Vihear      20
    "prov_3": {"PMS": 1, "ODMS": 4, "HC": 32},   # Siem Reap         37
    "prov_4": {"PMS": 1, "ODMS": 2, "HC": 9},    # Oddar Meanchey    12
    "prov_5": {"PMS": 1, "ODMS": 4, "HC": 11},   # Banteay Meanchey  16
    "prov_6": {"PMS": 1, "ODMS": 4, "HC": 21},   # Kampong Speu      26
}

# Province totals are DERIVED, never typed twice - the level figures are the
# single source of truth, so the two can never drift apart.
EXPECTED_BY_PROVINCE = {
    code: (sum(levels.values()) if levels else None)
    for code, levels in EXPECTED_BY_PROVINCE_POSITION.items()
}

PROVINCE_EN = {
    "prov_1": "Stung Treng",
    "prov_2": "Preah Vihear",
    "prov_3": "Siem Reap",
    "prov_4": "Oddar Meanchey",
    "prov_5": "Banteay Meanchey",
    "prov_6": "Kampong Speu",
    "other": "Other",
}
TESTTYPE_LABELS = {"pre": "pre", "pos": "post"}  # Kobo choice names from test_type list

# Full answer-choice text for every question, in a/b/c/d order — used to build the
# per-question "which option did people pick" pie charts with a proper legend.
OPTION_TEXTS = {
    "q1": ["វាស់សម្ពាធឈាម", "រកឃើញអង់ទីហ្សែនរបស់មេរោគគ្រុនចាញ់ក្នុងឈាម", "វាស់ជាតិស្ករក្នុងឈាម", "រកឃើញជំងឺគ្រុនឈាម"],
    "q2": ["HRP2 និង pLDH", "Hb និង WBC", "Dengue NS1 និង IgM", "G6PD និង Hb"],
    "q3": ["P. vivax", "P. malariae", "P. falciparum", "P. ovale"],
    "q4": ["រកឃើញតែមេរោគ P. falciparum", "រកឃើញមេរោគគ្រុនចាញ់ជាច្រើនប្រភេទ", "វាស់កម្រិត G6PD", "វាស់កម្រិត Hb"],
    "q5": ["ទឹកនោម", "ទឹកមាត់", "ឈាមទាំងមូល (Whole blood)", "ទឹកខួរឆ្អឹងខ្នង"],
    "q6": ["បដិសេធជំងឺគ្រុនចាញ់ភ្លាមៗ", "មិនចាំបាច់ពិនិត្យបន្ថែម", "ពិចារណាពិនិត្យបញ្ជាក់បន្ថែម ដូចជា microscopy តាមការចង្អុលបង្ហាញ", "ចាប់ផ្ដើមថ្នាំគ្រុនចាញ់គ្រប់ករណី"],
    "q7": ["RDT អាចរកឃើញមេរោគគ្រប់កម្រិត", "RDT អាចមាន sensitivity ទាបនៅពេល parasite density ទាប", "RDT អាចបង្កើន parasite density", "RDT អាចកំណត់ species បានគ្រប់ករណី"],
    "q8": ["រក្សាទុកក្រោម -20°C", "រក្សាទុកតាមលក្ខខណ្ឌរបស់ក្រុមហ៊ុនផលិត និងមិនឱ្យលើស 40°C", "ដាក់ក្នុងទឹកកកជានិច្ច", "ដាក់ក្រោមពន្លឺថ្ងៃ"],
    "q9": ["មិនចាំបាច់កត់ត្រា", "បញ្ជាក់ និងគ្រប់គ្រងករណីតាម National Treatment Guidelines និងប្រព័ន្ធរាយការណ៍", "បោះចោលលទ្ធផល", "រង់ចាំឱ្យអ្នកជំងឺមានរោគសញ្ញាធ្ងន់"],
    "q10": ["G6PD testing និង Radical Cure តាម National Treatment Guidelines", "Dengue vaccination", "Blood pressure monitoring តែប៉ុណ្ណោះ", "មិនចាំបាច់ព្យាបាលបន្ថែមទេ"],
    "q11": ["ចំនួនអ្នកជំងឺក្នុងមួយថ្ងៃតែប៉ុណ្ណោះ", "លក្ខខណ្ឌរក្សាទុក RDT និងសីតុណ្ហភាព", "ចំនួនបុគ្គលិករដ្ឋបាល", "ចំនួនគ្រែអ្នកជំងឺ"],
    "q12": ["ដើម្បីដឹងថាប្រអប់មានពណ៌អ្វី", "ដើម្បីធានាថា RDT មានសុពលភាព និងអាច trace បាន ប្រសិនបើមានបញ្ហាគុណភាព", "ដើម្បីកំណត់ចំនួនអ្នកជំងឺ", "ដើម្បីកំណត់ប្រភេទថ្នាំព្យាបាល"],
    "q13": ["ប្រើប្រាស់បន្តដោយមិនចាំបាច់ពិនិត្យ", "បោះចោល RDT ទាំងអស់ភ្លាមៗ", "កត់ត្រាបញ្ហា ពិនិត្យផលប៉ះពាល់លើគុណភាព និងអនុវត្តតាម SOP/ការណែនាំ QA", "ដាក់នៅក្នុងទូទឹកកកភ្លាមៗ ហើយប្រើបន្ត"],
    "q14": ["អនុវត្តតាម SOP/IFU ត្រឹមត្រូវ រួមទាំងបរិមាណឈាម បរិមាណ buffer និងពេលអានលទ្ធផល", "អានលទ្ធផលនៅពេលណាក៏បាន", "ប្រើ RDT ដោយមិនចាំបាច់ពិនិត្យ expiry date", "ប្រើ buffer ពី kit ផ្សេងគ្នា"],
    "q15": ["មិនចាំបាច់កត់ត្រា ព្រោះជាកំហុសតូចតាច", "កត់ត្រា និងរាយការណ៍ បញ្ជាក់ Lot/Expiry និងស្ថានភាពរក្សាទុក ហើយចាត់វិធានការកែតម្រូវតាម QA system", "ប្ដូរលទ្ធផលឱ្យស្របតាម microscopy", "បន្តប្រើ RDT ដោយមិនធ្វើអ្វី"],
}
OPTION_LETTERS = ["a", "b", "c", "d"]


# ---------------------------------------------------------------------------
def fetch_submissions():
    if not API_TOKEN or not ASSET_UID:
        sys.exit(
            "Missing KOBO_API_TOKEN or KOBO_ASSET_UID.\n"
            "Set them as environment variables (see SETUP notes in this file's header)."
        )
    url = f"{KOBO_SERVER}/api/v2/assets/{ASSET_UID}/data.json"
    headers = {"Authorization": f"Token {API_TOKEN}"}
    all_results = []
    params = {"format": "json", "limit": 2000}
    while url:
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        payload = resp.json()
        all_results.extend(payload.get("results", []))
        url = payload.get("next")
        params = {}
    return all_results


def get_field(submission, field):
    if field in submission:
        return submission[field]
    for key, value in submission.items():
        if key.endswith("/" + field):
            return value
    return None


def score_submission(sub):
    row = {
        "test_type": TESTTYPE_LABELS.get(get_field(sub, "test_type"), get_field(sub, "test_type")),
        "position": POSITION_LABELS.get(get_field(sub, "position"), get_field(sub, "position") or "Unknown"),
        # NGO/partner staff are never asked for a province, so they would otherwise
        # land in a bucket called "Unknown" - which reads like missing data rather
        # than a group that legitimately has no province. Give them their own.
        "province": (NGO_BUCKET_KH if get_field(sub, "position") == "ngo" and not get_field(sub, "province")
                     else PROVINCE_LABELS.get(get_field(sub, "province"),
                                              get_field(sub, "province") or "Unknown")),
        "province_en": (NGO_BUCKET_EN if get_field(sub, "position") == "ngo" and not get_field(sub, "province")
                        else PROVINCE_EN.get(get_field(sub, "province"), "")),
        "od": get_field(sub, "od"),
        "hc": get_field(sub, "hc"),
        "date": get_field(sub, "test_date"),
        # free text captured when "other (specify)" was chosen
        "position_other": get_field(sub, "position_other"),
        "org_name": get_field(sub, "org_name"),
        "province_other": get_field(sub, "province_other"),
        "od_other": get_field(sub, "od_other"),
        "hc_other": get_field(sub, "hc_other"),
    }
    total = 0
    for q, (correct_letter, pts) in ANSWER_KEY.items():
        ans = get_field(sub, q)
        is_correct = int(ans == correct_letter)
        row[q] = is_correct
        row[f"{q}_raw"] = ans  # actual chosen letter, for option-distribution pies
        row[f"{q}_pts_earned"] = pts if is_correct else 0
        total += row[f"{q}_pts_earned"]
    row["total_score"] = total
    row["total_pct"] = round(total / MAX_SCORE * 100, 1)
    return row


# ---------------------------------------------------------------------------
def build_dashboard_data(rows):
    pre_rows = [r for r in rows if r["test_type"] == "pre"]
    post_rows = [r for r in rows if r["test_type"] == "post"]

    def avg(vals):
        return round(sum(vals) / len(vals), 1) if vals else 0

    pre_scores = [r["total_pct"] for r in pre_rows]
    post_scores = [r["total_pct"] for r in post_rows]

    avg_pre = avg(pre_scores)
    avg_post = avg(post_scores)
    avg_improve = round(avg_post - avg_pre, 1)

    pass_pre = round(sum(1 for r in pre_rows if r["total_pct"] >= PASS_THRESHOLD) / len(pre_rows) * 100, 1) if pre_rows else 0
    pass_post = round(sum(1 for r in post_rows if r["total_pct"] >= PASS_THRESHOLD) / len(post_rows) * 100, 1) if post_rows else 0

    by_question = []
    for q in ANSWER_KEY:
        pre_n = len(pre_rows)
        post_n = len(post_rows)
        pre_correct = sum(r[q] for r in pre_rows)
        post_correct = sum(r[q] for r in post_rows)
        pre_acc = round(pre_correct / pre_n * 100, 1) if pre_n else 0
        post_acc = round(post_correct / post_n * 100, 1) if post_n else 0

        options = []
        for letter in OPTION_LETTERS:
            pre_count = sum(1 for r in pre_rows if r.get(f"{q}_raw") == letter)
            post_count = sum(1 for r in post_rows if r.get(f"{q}_raw") == letter)
            options.append({
                "letter": letter.upper(),
                "text": OPTION_TEXTS[q][OPTION_LETTERS.index(letter)],
                "is_correct": letter == ANSWER_KEY[q][0],
                "pre_count": pre_count,
                "post_count": post_count,
                "pre_pct": round(pre_count / pre_n * 100, 1) if pre_n else 0,
                "post_pct": round(post_count / post_n * 100, 1) if post_n else 0,
            })

        by_question.append({
            "question": QUESTION_LABELS[q],
            "question_number": q.upper(),
            "pre_pct": pre_acc,
            "post_pct": post_acc,
            "improvement": round(post_acc - pre_acc, 1),
            "pre_n": pre_n,
            "post_n": post_n,
            "pre_correct": pre_correct,
            "post_correct": post_correct,
            "correct_letter": ANSWER_KEY[q][0].upper(),
            "options": options,
        })

    # Roster order (province level, then OD, then health centre, then partners)
    # rather than alphabetical, so the groups read in the same order as the
    # chart title and the per-province breakdown. NGO/Partner is listed even
    # with nothing received yet, so the group is visibly tracked rather than
    # silently absent; the chart draws no bar for an empty group.
    always = ["PMS", "ODMS", "HC", POSITION_LABELS["ngo"]]
    seen = set(r["position"] for r in rows)
    by_position = []
    for pos in always + sorted(seen - set(always)):
        pre_p = [r for r in pre_rows if r["position"] == pos]
        post_p = [r for r in post_rows if r["position"] == pos]
        by_position.append({
            "position": pos,
            "n_pre": len(pre_p),
            "n_post": len(post_p),
            "pre_pct": avg([r["total_pct"] for r in pre_p]),
            "post_pct": avg([r["total_pct"] for r in post_p]),
            "pass_pre_pct": round(sum(1 for r in pre_p if r["total_pct"] >= PASS_THRESHOLD) / len(pre_p) * 100, 1) if pre_p else 0,
            "pass_post_pct": round(sum(1 for r in post_p if r["total_pct"] >= PASS_THRESHOLD) / len(post_p) * 100, 1) if post_p else 0,
        })

    # pass/fail counts (donut charts)
    pass_fail = {
        "pre": {"pass": sum(1 for r in pre_rows if r["total_pct"] >= PASS_THRESHOLD),
                "fail": sum(1 for r in pre_rows if r["total_pct"] < PASS_THRESHOLD)},
        "post": {"pass": sum(1 for r in post_rows if r["total_pct"] >= PASS_THRESHOLD),
                 "fail": sum(1 for r in post_rows if r["total_pct"] < PASS_THRESHOLD)},
    }

    # ---- points-based stats + per-score histogram (Pre vs Post Distribution) ----
    def point_stats(rs):
        pts = [r["total_score"] for r in rs]
        return {
            "n": len(rs),
            "avg_points": round(sum(pts) / len(pts), 1) if pts else 0,
            "avg_pct": avg([r["total_pct"] for r in rs]),
            "min_points": min(pts) if pts else 0,
            "max_points": max(pts) if pts else 0,
        }

    points = {"max_score": MAX_SCORE, "pre": point_stats(pre_rows), "post": point_stats(post_rows)}

    # one bar per achievable raw score, 0..MAX_SCORE, so gaps are visible as gaps
    score_histogram = [
        {"score": s,
         "pre_n": sum(1 for r in pre_rows if r["total_score"] == s),
         "post_n": sum(1 for r in post_rows if r["total_score"] == s)}
        for s in range(MAX_SCORE + 1)
    ]

    # ---- average score by province (Results by Province) ----
    present = {r["province"] for r in rows if r.get("province")}
    # A province with NO submissions yet must still be listed - that is exactly
    # the row worth seeing (nothing received, everyone still missing). So take
    # any province on the roster as well as any that turns up in the data.
    on_roster = {PROVINCE_LABELS[c] for c, v in EXPECTED_BY_PROVINCE_POSITION.items() if v}
    ordered = [PROVINCE_LABELS[c] for c in PROVINCE_ORDER
               if PROVINCE_LABELS[c] in present or PROVINCE_LABELS[c] in on_roster]
    ordered += sorted(p for p in present if p not in ordered
                      and p != NGO_BUCKET_KH)                  # anything off-roster
    # NGO/partner staff have no province at all, so they get their own row at
    # the bottom rather than being filed under a province they never chose.
    # Listed even when nothing has come in, for the same reason as the provinces.
    ordered.append(NGO_BUCKET_KH)
    # expected counts keyed by the Khmer label, so they line up with the rows below
    expected_by_label = {PROVINCE_LABELS[c]: n
                         for c, n in EXPECTED_BY_PROVINCE.items() if n is not None}

    # province label -> code, so the per-level config can be looked up by label
    label_to_code = {PROVINCE_LABELS[c]: c for c in PROVINCE_LABELS}

    def levels_for(prov_label, pre_p, post_p):
        """PMS / ODMS / HC detail for one province: expected vs received."""
        cfg = EXPECTED_BY_PROVINCE_POSITION.get(label_to_code.get(prov_label)) or {}
        out = []
        # roster order first (PHD level, then OD, then health centre), and any
        # position that turned up in the data but is not on the roster after it
        extra = sorted({r["position"] for r in pre_p + post_p} - set(cfg))
        for pos in list(cfg.keys()) + extra:
            exp = cfg.get(pos)
            n_pre = sum(1 for r in pre_p if r["position"] == pos)
            n_post = sum(1 for r in post_p if r["position"] == pos)
            if exp is None and not n_pre and not n_post:
                continue
            out.append({
                "position": pos,
                "expected": exp,
                "n_pre": n_pre,
                "n_post": n_post,
                "missing_pre": None if exp is None else max(0, exp - n_pre),
                "missing_post": None if exp is None else max(0, exp - n_post),
            })
        return out

    by_province = []
    for prov in ordered:
        pre_p = [r for r in pre_rows if r.get("province") == prov]
        post_p = [r for r in post_rows if r.get("province") == prov]
        by_province.append({
            "province": prov,
            # by code, not by scanning rows - a province with no submissions still has a name
            "province_en": (NGO_BUCKET_EN if prov == NGO_BUCKET_KH else
                            PROVINCE_EN.get(label_to_code.get(prov), "")
                            or next((r.get("province_en", "") for r in rows if r.get("province") == prov), "")),
            "n_pre": len(pre_p),
            "n_post": len(post_p),
            "pre_pct": avg([r["total_pct"] for r in pre_p]),
            "post_pct": avg([r["total_pct"] for r in post_p]),
            # None when this province has no roster figure configured
            "expected": expected_by_label.get(prov),
            # clamped at 0: a province can over-deliver if extra staff attended
            "missing_pre": (max(0, expected_by_label[prov] - len(pre_p))
                            if prov in expected_by_label else None),
            "missing_post": (max(0, expected_by_label[prov] - len(post_p))
                             if prov in expected_by_label else None),
            # PMS / ODMS / HC breakdown, shown when a province row is expanded
            # NGO/partner is a single group, not a province with PMS/OD/HC
            # underneath it, so it has nothing to expand into.
            "levels": [] if prov == NGO_BUCKET_KH else levels_for(prov, pre_p, post_p),
        })

    # roll-up, over the provinces that actually have a figure
    exp_total = sum(expected_by_label.values()) if expected_by_label else None
    tracking = None
    if exp_total:
        covered = [r for r in by_province if r["expected"] is not None]
        sub_pre = sum(r["n_pre"] for r in covered)
        sub_post = sum(r["n_post"] for r in covered)
        tracking = {
            "expected_total": exp_total,
            "provinces_configured": len(expected_by_label),
            "provinces_total": len(PROVINCE_ORDER),   # "other" is a choice, not a province
            "pre": {"submitted": sub_pre, "missing": max(0, exp_total - sub_pre),
                    "rate_pct": round(sub_pre / exp_total * 100, 1)},
            "post": {"submitted": sub_post, "missing": max(0, exp_total - sub_post),
                     "rate_pct": round(sub_post / exp_total * 100, 1)},
        }

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "kpis": {
            "n_pre": len(pre_rows),
            "n_post": len(post_rows),
            "avg_pre_pct": avg_pre,
            "avg_post_pct": avg_post,
            "avg_improvement_pct": avg_improve,
            "pass_pre_pct": pass_pre,
            "pass_post_pct": pass_post,
        },
        "by_question": by_question,
        "by_position": by_position,
        "pass_fail": pass_fail,
        "pass_threshold": PASS_THRESHOLD,
        "tracking": tracking,
        "points": points,
        "score_histogram": score_histogram,
        "by_province": by_province,

    }


# ---------------------------------------------------------------------------
def generate_sample_rows():
    random.seed(7)
    positions = ["PMS", "ODMS", "HC"]
    weak_qs = {"q7", "q8"}  # baked-in "doesn't improve much" for the demo
    other_letters = {q: [l for l in OPTION_LETTERS if l != ANSWER_KEY[q][0]] for q in ANSWER_KEY}
    rows = []
    for i in range(60):
        pos = random.choice(positions)
        # Province is assigned by index, NOT random.choice, so all six are covered
        # evenly and the RNG stream is untouched - every other sample figure stays
        # byte-identical to previous runs.
        prov_code = PROVINCE_ORDER[i % len(PROVINCE_ORDER)]
        for test_type in ["pre", "post"]:
            is_post = test_type == "post"
            row = {
                "test_type": test_type,
                "position": pos,
                "province": PROVINCE_LABELS[prov_code],
                "province_en": PROVINCE_EN[prov_code],
                "od": None, "hc": None, "date": "2026-09-03",
                "position_other": None, "org_name": None, "province_other": None,
                "od_other": None, "hc_other": None,
            }
            total = 0
            for q, (correct, pts) in ANSWER_KEY.items():
                if q in weak_qs:
                    p_correct = 0.35 if not is_post else 0.5
                else:
                    p_correct = 0.5 if not is_post else 0.88
                is_correct = random.random() < p_correct
                chosen = correct if is_correct else random.choice(other_letters[q])
                row[q] = 1 if is_correct else 0
                row[f"{q}_raw"] = chosen
                row[f"{q}_pts_earned"] = pts if is_correct else 0
                total += row[f"{q}_pts_earned"]
            row["total_score"] = total
            row["total_pct"] = round(total / MAX_SCORE * 100, 1)
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
def rows_to_csv(rows):
    """The per-submission export, as a single CSV string.

    Used twice: written to OUTPUT_CSV, and embedded in the dashboard so the
    download button works from the HTML file on its own - no sidecar .csv to
    keep together when the dashboard gets emailed or copied to a USB stick.
    """
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def build_html(dashboard_data, rows):
    with open(TEMPLATE_HTML, "r", encoding="utf-8") as f:
        template = f.read()

    payload = json.dumps(dashboard_data, ensure_ascii=False)
    start = template.index("/*__DATA__*/") + len("/*__DATA__*/")
    end = template.index("/*__END_DATA__*/")
    new_html = template[:start] + payload + template[end:]

    # same marker trick for the raw CSV
    csv_text = json.dumps(rows_to_csv(rows), ensure_ascii=False)
    start = new_html.index("/*__CSV__*/") + len("/*__CSV__*/")
    end = new_html.index("/*__END_CSV__*/")
    new_html = new_html[:start] + csv_text + new_html[end:]

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(new_html)


def write_csv(rows):
    if not rows:
        return
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        f.write(rows_to_csv(rows))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()

    if args.sample:
        print("Generating dashboard from SAMPLE data (no Kobo API call)...")
        global OUTPUT_HTML, OUTPUT_CSV
        OUTPUT_HTML, OUTPUT_CSV = OUTPUT_HTML_SAMPLE, OUTPUT_CSV_SAMPLE
        rows = generate_sample_rows()
    else:
        print(f"Fetching submissions from {KOBO_SERVER} (asset {ASSET_UID})...")
        submissions = fetch_submissions()
        print(f"Retrieved {len(submissions)} submissions.")
        rows = [score_submission(s) for s in submissions]

    write_csv(rows)
    dashboard_data = build_dashboard_data(rows)
    build_html(dashboard_data, rows)

    print(f"Wrote {OUTPUT_CSV} ({len(rows)} rows)")
    print(f"Wrote {OUTPUT_HTML}")
    print(f"Pre submissions: {dashboard_data['kpis']['n_pre']}, Post submissions: {dashboard_data['kpis']['n_post']}")


if __name__ == "__main__":
    main()
