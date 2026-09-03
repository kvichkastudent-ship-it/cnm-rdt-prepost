# CNM Malaria RDT Pre/Post Test — Deployment

Two separate things get deployed, **in this order**:

1. **The form** to KoboToolbox, so people can take the test.
2. **The dashboard**, generated on your machine from the submissions Kobo collected.

---

## Files

| File | Role |
|---|---|
| `CNM_RDT_PrePostTest_KoboXLSForm_v5.xlsx` | **The form to deploy.** Current version. |
| `fetch_rdt_results.py` | Pulls submissions from Kobo, scores them, builds the dashboard. |
| `rdt_dashboard_template.html` | Layout the script injects data into. **Must sit in the same folder.** |
| `verify_form_sync.py` | Guard: fails if the form and the script disagree. |
| `CNM_RDT_Dashboard_SAMPLE.html` | Preview built from fake data. Not for circulation. |
| `..._v3.xlsx`, `..._v4.xlsx`, `..._KhmerFixed.xlsx` | **Superseded by v5.** Keep for reference; do not deploy. |

---

## Step 1 — Deploy the form to Kobo

Upload v5 as a **new version of the existing project**, not a new project — a new
project loses the collected submissions and changes the asset UID.

In Kobo: open the project → **Settings → Media / Replace form** (or
**Form → Replace form**) → upload `CNM_RDT_PrePostTest_KoboXLSForm_v5.xlsx` → **Deploy**.

Safe to redeploy over live data:

- Stored answers are the choice *names* (`a`/`b`/`c`/`d`), not the label text, so the
  Khmer corrections do not affect scoring or anything already collected.
- v5 only **adds** questions (`position_other`, `province_other`, `od_other`,
  `hc_other`, `org_name`) and **skips** ones that never applied — NGO/Partner staff
  are no longer asked for a province, and PMS are no longer asked for an OD.
  Submissions collected before the redeploy simply have those fields empty; the
  script reads a missing field as blank and carries on.

---

## Step 2 — One-time setup on the machine that builds the dashboard

```
pip install requests openpyxl
```

Get the two credentials:

- **API token** — Kobo → profile icon → **Account Settings → Security → API Key**
- **Asset UID** — from the form's URL: `.../#/forms/aXXXXXXXXXXXX/summary`

---

## Step 3 — Build the dashboard

Open PowerShell **in this folder** (the template path is relative — running from
elsewhere fails), then set the three variables. They last for that session only:

```
$env:KOBO_SERVER    = "https://eu.kobotoolbox.org"
$env:KOBO_API_TOKEN = "your_token_here"
$env:KOBO_ASSET_UID = "aXXXXXXXXXXXXXXXXXXXXXX"
```

Check the form and script still agree, then build:

```
python verify_form_sync.py CNM_RDT_PrePostTest_KoboXLSForm_v5.xlsx
python fetch_rdt_results.py
```

Output: `CNM_RDT_Dashboard.html` + `CNM_RDT_Results.csv`.
Re-run whenever you want refreshed numbers.

**Expected headcounts** live in `EXPECTED_BY_PROVINCE_POSITION` near the top of
`fetch_rdt_results.py` — one figure per province per level (PMS / ODMS / HC),
currently totalling 131. Province and overall totals are derived from it, so edit
that one table and nothing else. It drives the Expected/Missing columns in the
Submission Tracking table, the per-province PMS/OD/HC breakdown, and the
submission-rate line on the two count cards.

The API token never reaches the generated HTML — it stays in your shell session.

---

## Step 4 — Share the dashboard

`CNM_RDT_Dashboard.html` is a **single self-contained file**. Chart.js and its
datalabels plugin are embedded, so it works with no internet. The only external
request is Google Fonts for Kantumruy Pro, which falls back to a system font
offline.

- **Email / Box / SharePoint** — simplest. Box and SharePoint often *download*
  HTML rather than render it, so recipients may need to open the downloaded file.
- **A clickable link that renders in-browser** — drag the HTML onto
  <https://app.netlify.com/drop>. No signup, instant public URL.

### Decide this before sharing widely

The dashboard has an embedded **raw CSV download** containing every submission:
province, OD, health centre, position, all answers and the score. There are no
names, but in a small health centre those columns could narrow to an individual.
Fine for CNM staff; think twice before putting it behind a public link. The export
can be switched to aggregate-only if needed.

---

## Do not deploy

The **live auto-updating Vercel version** (`CNM_RDT_Live_Dashboard.zip`) from the
original handoff is far behind — none of the Khmer corrections, the colour work,
the added sections, the submission tracking, or the export buttons. Either retire
it in favour of re-running the script, or have `public/index.html` and
`api/data.js` brought up to date first.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| `Missing KOBO_API_TOKEN or KOBO_ASSET_UID` | Variables not set, or set in a different PowerShell session. |
| `FileNotFoundError: rdt_dashboard_template.html` | Running from the wrong folder. |
| `verify_form_sync.py` reports mismatches | The form and script have drifted — fix before building, or the dashboard will mislabel results. Mismatches against `_KhmerFixed.xlsx` are expected; it is superseded. |
| Khmer shows as boxes in Excel when opening the CSV | Open the CSV downloaded from the dashboard button (it carries a UTF-8 BOM) rather than converting by hand. |
| Charts blank when opened | Check the file was opened directly, not from inside a zip. |
