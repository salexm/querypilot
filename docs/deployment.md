# Deploying QueryPilot

QueryPilot's public demo runs on free tiers:

| Part | Service | Notes |
|---|---|---|
| Frontend | Render static site | Production Vite build |
| Backend | Render free web service | Built from `backend/Dockerfile` |
| Database | Neon free plan | Data is about 156 MB of the 0.5 GB limit |

The free API sleeps after about 15 minutes without traffic, so the first question after a quiet spell can take up to a minute. Neon also sleeps when idle.

Secrets stay in Render's environment variables and your ignored `.env.neon` file. They never go in the repo.

## 1. Protect your API credits

1. In the [Anthropic Console](https://console.anthropic.com), add credit and set a monthly spend limit.
2. Create a new API key for the demo.

The spend limit is the hard stop. The app's own limits reset when the free API sleeps.

## 2. Create the database

1. Create a project at [neon.com](https://neon.com).
2. Open its connection details, and copy the direct host, not the one containing `-pooler`.
3. Copy `db/seed/neon.env.example` to `.env.neon` at the repo root, and fill it in. Use a long, random password for the read-only role.

If you use the Neon CLI, `neon init` and `neon deploy` link the project through `neon.ts` and add an owner `DATABASE_URL` to `.env`. Use that login only to load data, and never give it to the API.

Don't create the read-only role in the Neon console. Console-created roles get broad rights, including writes. The seed creates it with SQL instead.

## 3. Load the data

From the repo root, with Docker running:

```bash
docker build -t querypilot-seed db/seed
docker run --rm --env-file .env.neon -v "${PWD}/db/seed/data:/app/data" querypilot-seed
```

The output should end with `Read-only role querypilot_readonly is ready.`

## 4. Create the services

1. In the [Render dashboard](https://dashboard.render.com), choose **New**, then **Blueprint**, and connect this repository.
2. Render reads `render.yaml` and asks for each secret. Enter the Neon host, database name, read-only user and password, and the Anthropic key.
3. For `CORS_ORIGINS` and `VITE_API_BASE_URL`, enter placeholders for now, because the URLs don't exist yet.
4. Deploy, then copy both service URLs.
5. On `querypilot-api`, set `CORS_ORIGINS` to the `querypilot-web` URL.
6. On `querypilot-web`, set `VITE_API_BASE_URL` to the `querypilot-api` URL, then redeploy it. Vite builds this value into the frontend.

Use full URLs, such as `https://querypilot-web.onrender.com`, with no trailing slash.

## 5. Check the deployment

Replace `API_URL` with your API address:

```bash
curl https://API_URL/health
curl https://API_URL/health/ready
```

Both should return `{"status":"ok"}`. Then open the web app and ask a question.

### Check that the rate limit can't be bypassed

Send 7 requests, each with a different forged address. The last two must return 429:

```bash
for i in 1 2 3 4 5 6 7; do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST https://API_URL/query \
    -H "Content-Type: application/json" \
    -H "X-Forwarded-For: 10.0.0.$i" -H "CF-Connecting-IP: 10.0.0.$i" \
    -d '{"question":"How many orders are there?"}'
done
```

If every request gets through, `CLIENT_IP_HEADER` doesn't match the header your host sets. Don't use `X-Forwarded-For` for this: on Render it holds client-supplied values and proxy addresses that change between requests.

## Costs and limits

| Setting | Value | Why |
|---|---|---|
| `LLM_MODEL` | `claude-haiku-5-5` | Far cheaper than Opus, and 99.2% on the benchmark |
| `RATE_LIMIT_PER_MINUTE` | 5 | Stops one visitor spending the budget |
| `DAILY_QUERY_LIMIT` | 200 | Caps the whole site, whoever is asking |

Each question can make up to 3 LLM calls because of self-correction.
