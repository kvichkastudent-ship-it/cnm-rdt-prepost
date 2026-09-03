// Netlify Function. Kept alongside the Cloudflare one so the site can be
// published from either host - Netlify pauses deploys when a team runs out of
// free credits, and nothing about the dashboard should depend on that.
//
// All the work is in ../../lib/kobo.mjs, shared with functions/api/data.js.
// This file only knows how Netlify hands over environment variables
// (process.env) and how it routes a function to a URL (the config export).

import { buildResponse } from "../../lib/kobo.mjs";

export default () =>
  buildResponse(process.env, "Netlify (Site configuration -> Environment variables)");

export const config = { path: "/api/data" };
