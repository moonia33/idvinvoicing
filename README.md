# IDV Apskaita

Apskaitos sistema individualią veiklą vykdantiems asmenims: sąskaitų išrašymas, mokėjimai, pajamų-išlaidų žurnalas, mokesčių skaičiavimas ir ataskaitos.

Specifikacija ir architektūros sprendimai: [.agent.md](.agent.md)

## Tech stack

- **Backend**: Python 3.13 · Django 5.2 · django-ninja (`/api/v1`, OpenAPI) · PostgreSQL 16 · django-q2 (foninės užduotys, ORM broker) · WeasyPrint (PDF) · openpyxl (Excel) · uv
- **Frontend**: SvelteKit 2 / Svelte 5 · TypeScript · Tailwind CSS v4 · shadcn-svelte · pnpm
- **Infra**: Docker Compose · Caddy reverse proxy · GitHub Actions

## Greitas startas (dev, Docker)

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build
```

- Frontend: http://localhost:5173 (Vite dev, `/api` proxy → backend)
- Backend API docs: http://localhost:8000/api/v1/docs
- Django admin: http://localhost:8000/admin

## Lokalus dev be Docker (frontend + DB docker, backend native)

```bash
docker compose -f docker-compose.dev.yml up db
cd backend && uv sync && uv run python manage.py migrate && uv run python manage.py runserver
cd frontend && pnpm install && pnpm dev
```

> Pastaba: WeasyPrint (PDF generavimas) Windows'e reikalauja GTK bibliotekų – importuojama lazily, tad likusi sistema veikia ir be jų; PDF generavimui naudokite Docker.

## Prod-like paleidimas

```bash
cp .env.example .env   # užpildyti POSTGRES_PASSWORD, DJANGO_SECRET_KEY
docker compose up --build -d
```

Viskas pasiekiama per http://localhost (Caddy: `/api`, `/admin`, `/static` → backend; visa kita → frontend).

Migracijos: `docker compose exec backend python manage.py migrate`
Supervartotojas: `docker compose exec backend python manage.py createsuperuser`

## Struktūra

```
backend/
  config/          Django settings, urls, ninja API
  apps/
    core/          bendri pagalbiniai įrankiai
    tenancy/       User, Tenant (veikla), narystės, seller profile
    invoicing/     klientai, sąskaitos, eilutės, mokėjimai, PDF, recurring
    ledger/        pajamų-išlaidų žurnalas, valiutų konversija PLN→EUR
    taxes/         mokesčių taisyklės (per metus), GPM/VSD/PSD variklis
    reports/       ataskaitos, Excel eksportas
    mailer/        per-tenant SMTP, laiškų eilė (outbox)
frontend/          SvelteKit app
deploy/caddy/      Caddyfile
```

## Testai ir kokybė

```bash
cd backend && uv run pytest && uv run ruff check . && uv run mypy .
cd frontend && pnpm run check && pnpm run lint && pnpm run test:unit -- --run && pnpm run build
```
