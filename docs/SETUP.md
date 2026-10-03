# Local setup

This guide covers the disposable local development stack. It does not establish production readiness. The root `.env.example` documents Compose variables; `backend/.env.example`, `frontend/.env.example`, and `agent/.env.example` cover direct runs. Copy examples to local ignored environment files and replace placeholders. Never commit a populated environment file.

## Docker Compose

1. Install Docker Engine/Desktop with Compose v2.
2. Copy root `.env.example` to `.env`. Set unique local `POSTGRES_PASSWORD`, a random `ITOPS_JWT_SECRET` of at least 32 characters, and a strong `ITOPS_INITIAL_ADMIN_PASSWORD` for a new database. To create the fictional enterprise directory, set `ITOPS_ENTERPRISE_SEED_PASSWORD` to that same local-only password. Keep `ITOPS_AI_PROVIDER=disabled` unless you intentionally configure an external provider.
3. Run:

```sh
docker compose up --build -d
docker compose ps
docker compose logs api
```

The API startup runs `alembic upgrade head` followed by `python -m scripts.seed`; the enterprise directory seed is opt-in through the environment variable. The API waits for healthy PostgreSQL, and the frontend waits for the API. The SLA and monitoring workers run as separate Python polling processes. Open `http://localhost:5173`; API health endpoints are `http://localhost:8000/api/v1/health/live` and `/api/v1/health/ready`.

For a dedicated disposable demo database, run `docker compose exec api python -m scripts.demo_seed` after startup. The demo seed refuses production environments and expects the enterprise directory. Its simulated monitoring telemetry is not real infrastructure. Remove bootstrap password variables after first setup; existing identities are not reset by the idempotent seed.

`docker compose down` stops the stack while preserving named PostgreSQL and attachment volumes. `docker compose up -d` starts it again with persistent data. **Do not run `down -v` unless you have confirmed the exact disposable Compose project and intend to destroy its data.** See [the demo reset procedure](DEMO.md#safe-local-reset).

## Direct development

Use Python 3.12/3.13 and Node.js 24/npm 11. Start a PostgreSQL instance, configure `ITOPS_DATABASE_URL` and other backend settings from `backend/.env.example`, then:

```sh
cd backend
python -m venv .venv
python -m pip install -e ".[dev]"
alembic upgrade head
python -m scripts.seed
uvicorn app.main:app --reload
```

Activate the virtual environment before the install on your operating system. In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

Direct development requires you to supply compatible API/CORS origins. The containerized frontend uses a same-origin Nginx proxy; direct Vite development uses the `VITE_API_BASE_URL` value in `frontend/.env.example`.

## Verification

Run `docker compose ps` and check both health endpoints. Sign in through the UI using credentials you set locally. Run tests only against disposable databases; `ITOPS_TEST_DATABASE_URL` must never point at production. See [testing](TESTING.md), [security](SECURITY.md), and [deployment boundaries](DEPLOYMENT.md).
