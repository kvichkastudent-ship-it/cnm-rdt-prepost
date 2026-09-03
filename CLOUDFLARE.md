# Publishing the live dashboard on Cloudflare

The live dashboard is a static page plus one small server function. The page is
`public/index.html`; the function answers `/api/data` by fetching Kobo, scoring
the submissions and returning JSON.

Cloudflare offers two ways in, and the dashboard supports both. **Workers** is
what the current "Create an app" screen gives you, and the one to use.

**Why the function exists:** the Kobo API token must never be in the page. Anyone
who opens the dashboard can read its source, and that token can read *and delete*
every submission in the project. The function keeps it on the server.

Cloudflare's free plan has no monthly deploy credit to run out of, which is why
this exists alongside `netlify.toml` — the same site deploys to either host from
the same repository.

---

## One-time setup (Workers)

### 1. Create the app

1. Sign up (free) at <https://dash.cloudflare.com>.
2. **Compute (Workers) → Create → Import a repository**.
3. Authorise GitHub, choose **`kvichkastudent-ship-it/cnm-rdt-prepost`**.

### 2. Settings on the "Set up your application" screen

| Field | Value |
|---|---|
| Project name | `cnm-rdt-prepost` |
| Build command | **leave empty** |
| Deploy command | `npx wrangler deploy` (the default) |

There is no build step, and there is no "output directory" field to fill in.
Both live in `wrangler.toml` in the repository:

```toml
name = "cnm-rdt-prepost"
main = "worker.js"          # answers /api/data
[assets]
directory = "./public"      # the dashboard page
```

Assets win whenever a path matches a file, so `/api/data` is the only request
that ever reaches the Worker. `public/index.html` is generated locally by
`build_site.py` and committed, so Cloudflare has nothing to build.

**Protect with Cloudflare Access** on that screen is worth considering — see
*Before sharing the link* below.

### 3. Environment variables

**Settings → Variables and Secrets → Add**, three of them:

| Name | Value | Type |
|---|---|---|
| `KOBO_API_TOKEN` | your Kobo API token | **Secret** |
| `KOBO_SERVER` | `https://eu.kobotoolbox.org` | Text |
| `KOBO_ASSET_UID` | `aRAkKsGrthphw4Nqd7egNY` | Text |

Choose **Secret** for the token so it is hidden after saving.

Check `KOBO_SERVER` against your own browser: use `eu.kobotoolbox.org` if that is
what your Kobo address bar says, `kf.kobotoolbox.org` if it says that instead. A
token issued by one server returns nothing on the other, and it fails quietly —
the dashboard just looks empty.

Add these under **Production**. If you also want preview deployments to work,
add them under Preview as well.

### 4. Deploy

**Deploy.** The site appears at
`https://cnm-rdt-prepost.<your-subdomain>.workers.dev`.

Environment variables only take effect on a *new* deploy. If you add them after
the first deploy, redeploy from **Deployments**.

---

## Day to day

- **Refreshing the numbers:** reload the page. The function re-reads Kobo each
  time, cached at the edge for 60 seconds so a room full of people refreshing
  costs one upstream fetch per minute rather than one each.
- **Publishing a change:** push to `main`. Cloudflare deploys automatically.
  After editing `rdt_dashboard_template.html`, run `python build_site.py` first —
  the committed `public/index.html` is what actually gets served.
- **Rolling back:** **Deployments → …  → Rollback to this deployment**.

---

## Before sharing the link

The URL is **public to anyone who has it** — unlisted, not private.
The dashboard's Raw CSV button exports every submission: province, OD, health
centre, position, every answer and the score. There are no names, but in a small
health centre those columns could narrow to one person.

Fine to share inside CNM. Think before posting it anywhere wider. If you need it
genuinely restricted, turn on **Protect with Cloudflare Access** (offered when
you create the app, or later in the project's settings). It puts a sign-in in
front of the whole site, so only the email addresses you list can open it.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| Page loads, sections empty, red banner | `/api/data` failed. Open `https://<site>/api/data` directly — it prints the reason. |
| `Not configured` | The three variables are missing, or were added after the last deploy. Add them, then retry the deployment. |
| `Kobo returned 401` | Token rejected. Regenerate it in Kobo (Account Settings → Security) and update `KOBO_API_TOKEN`. |
| `Kobo returned 404` | Wrong `KOBO_ASSET_UID`, or `KOBO_SERVER` pointing at the wrong Kobo server. |
| Old layout after a push | `public/index.html` was not rebuilt. Run `python build_site.py`, commit, push. |
| `wrangler.toml not found` | The deploy ran against a commit from before it existed. Push first, then redeploy. |
| Charts fine, numbers stale by under a minute | The 60-second edge cache. Expected. |

---

## The Pages route (alternative)

If you use **Workers & Pages → Pages → Connect to Git** instead, Cloudflare
ignores `wrangler.toml` and wants the settings in its own form:

| Setting | Value |
|---|---|
| Production branch | `main` |
| Framework preset | None |
| Build command | leave empty |
| Build output directory | `public` |

Pages finds `functions/` in the repository root on its own, and the folder path
becomes the URL: `functions/api/data.js` → `/api/data`. Environment variables
work the same way. Do **not** point the output directory at the repository root;
that would publish the XLSForm and the scoring script.
