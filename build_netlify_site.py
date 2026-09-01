#!/usr/bin/env python3
"""
build_netlify_site.py
=====================
Generates netlify_public/index.html from rdt_dashboard_template.html.

WHY THIS EXISTS
---------------
The old handoff warned that the static dashboard and the live one had to be kept
in sync by hand, and that whenever the charts changed BOTH had to be edited. That
is how they drifted apart. So the live site is not a second copy: it is generated
from the same template the Python script uses.

The only difference between the two outputs is where the data comes from:

  static build   the payload is injected into the page at build time
  live build     the page fetches /api/data on load, and the Netlify function
                 does the scoring server-side with the Kobo token

Run this after ANY change to rdt_dashboard_template.html:

    python build_netlify_site.py
"""

import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "rdt_dashboard_template.html")
OUTDIR = os.path.join(HERE, "netlify_public")
OUT = os.path.join(OUTDIR, "index.html")

LOADER = """
// ---------------------------------------------------------------------------
// LIVE BUILD. The static build has its payload injected here at build time; this
// one asks the Netlify function, which holds the Kobo token server-side and does
// the scoring with the same logic. Reloading the page therefore shows current
// submissions.
// ---------------------------------------------------------------------------
let DASHBOARD_DATA = null;
let RAW_CSV = null;

function showStatus(kind, title, detail){
  let el = document.getElementById('live-status');
  if(!el){
    el = document.createElement('div');
    el.id = 'live-status';
    el.style.cssText = 'max-width:1320px;margin:0 auto 18px;padding:16px 20px;border-radius:12px;'
      + "font:500 14.5px/1.6 'Kantumruy Pro',sans-serif;";
    const host = document.querySelector('.wrap') || document.body;
    host.insertBefore(el, host.firstChild);
  }
  const good = kind === 'loading';
  el.style.background = good ? '#EAF1FB' : '#FCECEA';
  el.style.border = '1px solid ' + (good ? '#cfdff5' : '#F1C6C1');
  el.style.color = good ? '#1b5aa8' : '#B5342A';
  el.innerHTML = '<strong>' + title + '</strong>' + (detail ? '<br><span style="opacity:.85">' + detail + '</span>' : '');
}

function clearStatus(){
  const el = document.getElementById('live-status');
  if(el) el.remove();
}

async function loadLive(){
  showStatus('loading', 'កំពុងទាញយកទិន្នន័យ / Loading latest results\\u2026');
  try{
    const res = await fetch('/api/data', { cache: 'no-store' });
    const body = await res.json();
    if(!res.ok){
      showStatus('error', body.error || 'Could not load results',
                 body.detail || ('HTTP ' + res.status));
      return;
    }
    DASHBOARD_DATA = body.data;
    RAW_CSV = body.csv || null;
    clearStatus();
    init();
  }catch(err){
    showStatus('error', 'Could not reach the server',
               String(err && err.message ? err.message : err));
  }
}
"""


def main():
    if not os.path.exists(TEMPLATE):
        sys.exit("not found: %s" % TEMPLATE)
    html = io.open(TEMPLATE, encoding="utf-8", newline="").read()

    # The template declares its two payload constants between markers. Replace
    # that whole declaration block with the fetching loader.
    csv_start = html.index("const RAW_CSV = /*__CSV__*/")
    data_end = html.index("/*__END_DATA__*/") + len("/*__END_DATA__*/;")
    assert csv_start < data_end, "unexpected marker order in the template"

    html = html[:csv_start] + LOADER.strip() + html[data_end:]

    # Swap the bare init() for loadLive(), keeping it in the SAME position - the
    # very end of the script. init() touches `let` bindings declared further down
    # the file, so invoking it any earlier hits the temporal dead zone and throws
    # "Cannot access 'charts' before initialization".
    assert html.count("\ninit();\n") == 1, "expected exactly one bare init() call"
    html = html.replace("\ninit();\n", "\nloadLive();   // calls init() once /api/data responds\n", 1)

    for gone in ("/*__DATA__*/", "/*__END_DATA__*/", "/*__CSV__*/", "/*__END_CSV__*/"):
        assert gone not in html, "marker left behind: %s" % gone
    for needed in ("loadLive()", "function init()", "wirePngExport", "renderTracking"):
        assert needed in html, "lost during the rewrite: %s" % needed

    os.makedirs(OUTDIR, exist_ok=True)
    io.open(OUT, "w", encoding="utf-8", newline="").write(html)
    print("wrote %s  (%d chars)" % (os.path.relpath(OUT, HERE), len(html)))
    print("  data source : /api/data (Netlify function)")
    print("  charts      : identical to the static build, same template")


if __name__ == "__main__":
    main()
