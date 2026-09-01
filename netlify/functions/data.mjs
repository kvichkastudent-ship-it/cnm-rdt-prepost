// Netlify Function: fetches submissions from Kobo, scores them, returns the
// dashboard payload as JSON.
//
// The whole point of this file is that the Kobo API token stays here, on the
// server. The browser only ever talks to /api/data and never sees a credential.
// Putting the token in the page instead would let any visitor read - or delete -
// the project's submissions.

import { scoreSubmission, buildDashboardData } from "../lib/scoring.mjs";

const PAGE_SIZE = 2000;

function rowsToCsv(rows) {
  if (!rows.length) return "";
  const cols = Object.keys(rows[0]);
  const esc = v => {
    if (v === null || v === undefined) return "";
    const s = String(v);
    return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  const lines = [cols.join(",")];
  for (const r of rows) lines.push(cols.map(c => esc(r[c])).join(","));
  return lines.join("\r\n") + "\r\n";
}

async function fetchAllSubmissions(server, uid, token) {
  const headers = { Authorization: `Token ${token}` };
  let url = `${server.replace(/\/+$/, "")}/api/v2/assets/${uid}/data.json?limit=${PAGE_SIZE}`;
  const all = [];
  // Kobo paginates with an absolute "next" URL; follow it until exhausted.
  while (url) {
    const res = await fetch(url, { headers });
    if (!res.ok) {
      const body = await res.text();
      const hint = res.status === 401 ? " - token rejected; regenerate it in Kobo and update the KOBO_API_TOKEN environment variable"
                 : res.status === 404 ? " - not found; check KOBO_ASSET_UID, and that KOBO_SERVER is kf. or eu. (not kc.)"
                 : "";
      throw new Error(`Kobo returned ${res.status}${hint}. ${body.slice(0, 300)}`);
    }
    const page = await res.json();
    all.push(...(page.results || []));
    url = page.next || null;
    if (all.length > 100000) break;   // runaway guard
  }
  return all;
}

export default async (req) => {
  const started = Date.now();
  const server = process.env.KOBO_SERVER || "https://kf.kobotoolbox.org";
  const token = process.env.KOBO_API_TOKEN;
  const uid = process.env.KOBO_ASSET_UID;

  const json = (obj, status = 200, extra = {}) =>
    new Response(JSON.stringify(obj), {
      status,
      headers: {
        "content-type": "application/json; charset=utf-8",
        ...extra,
      },
    });

  if (!token || !uid) {
    return json({
      error: "Not configured",
      detail: "KOBO_API_TOKEN and KOBO_ASSET_UID must be set as environment variables in Netlify (Site settings -> Environment variables).",
    }, 500, { "cache-control": "no-store" });
  }

  try {
    const submissions = await fetchAllSubmissions(server, uid, token);
    const rows = submissions.map(scoreSubmission);
    const generatedAt = new Date().toISOString().replace("T", " ").slice(0, 16) + " UTC";
    const data = buildDashboardData(rows, generatedAt);

    return json({ data, csv: rowsToCsv(rows), fetched: submissions.length, ms: Date.now() - started }, 200, {
      // Cached at Netlify's edge for a minute: many people refreshing costs one
      // function invocation per minute rather than one each, which keeps this
      // comfortably inside the free tier.
      "cache-control": "public, max-age=30",
      "netlify-cdn-cache-control": "public, s-maxage=60, stale-while-revalidate=120",
    });
  } catch (err) {
    return json({ error: "Could not load results", detail: String(err.message || err) },
                502, { "cache-control": "no-store" });
  }
};

export const config = { path: "/api/data" };
