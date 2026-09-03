// Everything /api/data does, with no host-specific API in sight.
//
// This exists because the dashboard now runs on two hosts (Cloudflare Pages and
// Netlify) and the logic must not be written twice - a fix applied to one copy
// and not the other is exactly how the two would start disagreeing about the
// same submissions. The platform files are thin adapters: they read the three
// environment variables their own way and hand them to buildResponse().
//
// The Kobo API token stays on the server. The browser only ever talks to
// /api/data and never sees a credential; putting the token in the page would
// let any visitor read - or delete - the project's submissions.

import { scoreSubmission, buildDashboardData } from "./scoring.mjs";

const PAGE_SIZE = 2000;

export function rowsToCsv(rows) {
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

export async function fetchAllSubmissions(server, uid, token) {
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

/**
 * Build the /api/data response.
 *
 * @param {object} env  KOBO_SERVER, KOBO_API_TOKEN, KOBO_ASSET_UID
 * @param {string} where  host name, used only in the "not configured" message
 *                        so the reader is told where to go and set them
 * @returns {Response}
 */
export async function buildResponse(env, where = "your hosting provider") {
  const started = Date.now();
  const server = env.KOBO_SERVER || "https://kf.kobotoolbox.org";
  const token = env.KOBO_API_TOKEN;
  const uid = env.KOBO_ASSET_UID;

  const json = (obj, status = 200, extra = {}) =>
    new Response(JSON.stringify(obj), {
      status,
      headers: { "content-type": "application/json; charset=utf-8", ...extra },
    });

  if (!token || !uid) {
    return json({
      error: "Not configured",
      detail: `KOBO_API_TOKEN and KOBO_ASSET_UID must be set as environment variables in ${where}.`,
    }, 500, { "cache-control": "no-store" });
  }

  try {
    const submissions = await fetchAllSubmissions(server, uid, token);
    const rows = submissions.map(scoreSubmission);
    const generatedAt = new Date().toISOString().replace("T", " ").slice(0, 16) + " UTC";
    const data = buildDashboardData(rows, generatedAt);

    return json({ data, csv: rowsToCsv(rows), fetched: submissions.length, ms: Date.now() - started }, 200, {
      // Cached at the edge for a minute: a room full of people refreshing costs
      // one upstream fetch per minute rather than one each, which keeps this
      // comfortably inside the free tier on either host.
      "cache-control": "public, max-age=30, s-maxage=60, stale-while-revalidate=120",
      "netlify-cdn-cache-control": "public, s-maxage=60, stale-while-revalidate=120",
    });
  } catch (err) {
    return json({ error: "Could not load results", detail: String(err.message || err) },
                502, { "cache-control": "no-store" });
  }
}
