// Cloudflare Workers entry point.
//
// Static files in public/ are served by the assets binding before this runs, so
// the only request that gets here is /api/data - the one that needs the Kobo
// token, which stays on the server and never reaches the page.
//
// The work itself is in lib/kobo.mjs, shared with the Netlify function and the
// Pages function, so no host can drift away from the others.

import { buildResponse } from "./lib/kobo.mjs";

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    if (pathname === "/api/data") {
      return buildResponse(env, "Cloudflare (Settings -> Variables and Secrets)");
    }
    return new Response("Not found", { status: 404 });
  },
};
