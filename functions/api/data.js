// Cloudflare Pages Function. Its path in this folder IS its URL: functions/api/
// data.js serves /api/data, which is what the dashboard page fetches on load.
//
// All the work is in ../../lib/kobo.mjs, shared with the Netlify function, so
// the two hosts can never drift apart. This file only knows how Cloudflare
// hands over environment variables: context.env, not process.env (Workers has
// no process global).
//
// Set KOBO_API_TOKEN, KOBO_SERVER and KOBO_ASSET_UID under
// Workers & Pages -> your project -> Settings -> Variables and Secrets.
// Mark the token as a Secret so it stays hidden after saving.

import { buildResponse } from "../../lib/kobo.mjs";

export const onRequestGet = ({ env, request }) =>
  buildResponse(env, "Cloudflare (Settings -> Variables and Secrets)", request?.url);
