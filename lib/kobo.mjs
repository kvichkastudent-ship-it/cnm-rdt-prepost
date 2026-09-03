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
  // Pasted secrets very often carry a trailing newline or a stray space. That
  // makes the Authorization header malformed, and servers reject it with a
  // blank 400 rather than a useful message - so trim before it can happen.
  const host = server.trim().replace(/\/+$/, "");
  const headers = { Authorization: `Token ${token.trim()}` };
  let url = `${host}/api/v2/assets/${uid.trim()}/data.json?format=json&limit=${PAGE_SIZE}`;
  const all = [];
  // Kobo paginates with an absolute "next" URL; follow it until exhausted.
  while (url) {
    const res = await fetch(url, { headers });
    if (!res.ok) {
      const body = (await res.text()).trim();
      const hint = res.status === 401 ? " - token rejected; regenerate it in Kobo and set it again with `wrangler secret put KOBO_API_TOKEN`"
                 : res.status === 404 ? " - not found; check KOBO_ASSET_UID, and that KOBO_SERVER is the server you actually log in to"
                 : res.status === 400 ? " - bad request; the usual cause is KOBO_SERVER pointing at the wrong Kobo (eu vs kf), so the asset id means nothing there"
                 : "";
      // Name the host and echo whatever the server said. A blank 400 with no
      // context is the hardest kind of failure to act on.
      throw new Error(`Kobo returned ${res.status} ${res.statusText}${hint}.`
                    + ` Asked ${new URL(url).host} for asset ${uid.trim()}.`
                    + (body ? ` Server said: ${body.slice(0, 300)}` : " Server sent an empty body."));
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
    // Name the one that is actually missing. "Both must be set" sends you
    // looking at the one you already did set.
    const missing = [!token && "KOBO_API_TOKEN", !uid && "KOBO_ASSET_UID"].filter(Boolean);
    return json({
      error: "Not configured",
      missing,
      detail: `${missing.join(" and ")} ${missing.length > 1 ? "are" : "is"} not set. `
            + `Either run  npx wrangler secret put ${missing[0]}  from the project folder, `
            + `or add it in ${where}. A value set in the dashboard only reaches the site `
            + `on the next deploy; a secret set with wrangler applies immediately.`,
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
