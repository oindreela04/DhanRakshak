# DhanRakshak

## Every rupee deserves a second chance.

DhanRakshak is an AI Revenue Recovery Control Plane for the Razorpay AI Buildathon 2026 Revenue Recovery track. It detects revenue at risk, explains root causes, predicts bounded interventions, checks deterministic policies, verifies outcomes, and measures **incremental revenue recovered**.

This first increment is an honest foundation: the dashboard is a product surface, the API exposes health, the database schema is ready for the recovery lifecycle, and provider adapters are explicit skeletons. No fake payment execution or placeholder recovery API is exposed.

## Synthetic Benchmark Dataset

The generated files are a deterministic **Synthetic Benchmark Dataset**, created locally with seed `2026`. They are not Razorpay production data and contain no customer-identifying production information. The generator preserves customer-level behavior correlations, temporal event ordering, intervention/control labels, and time-based train/validation/test partitions.

Generate and validate the full benchmark:

```powershell
python scripts\generate_dataset.py --output-root data --clean
python scripts\validate_dataset.py --root data
```

For a fast smoke run, pass smaller `--customers`, `--transactions`, `--subscriptions`, `--invoices`, `--checkouts`, and `--recovery-events` values.

Seed the ORM-backed database in dependency order:

```powershell
python scripts\seed_database.py --root data --database-url $env:DATABASE_URL
```

The seed script uses batch inserts and can be limited during development with `--limit`.

## Technology stack

- Frontend: React, TypeScript, Vite, Framer Motion, Recharts, Lucide React
- Backend: Python 3.11+, FastAPI, Pydantic Settings, SQLAlchemy, Alembic, PostgreSQL
- ML/AI boundary: `ml/` for pandas, NumPy, scikit-learn, and XGBoost workflows; LLM use is reserved for reasoning, explanations, promise extraction, messages, and command-center responses
- Infrastructure: Docker Compose

## Architecture

Demo or Razorpay events enter through a future webhook gateway, are normalized and identity-resolved, then pass through recovery memory, risk, root-cause, probability, economics, and deterministic policy layers. A bounded recovery action is executed through an adapter, verified, measured for incrementality, written back to memory, and audited.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full system boundary and data flow.

Recovery DNA is available at `GET /api/v1/customers/{customer_id}/recovery-dna`. It is computed from stored, verified outcomes and persisted through `RecoveryMemoryService`; the frontend exposes a typed `getRecoveryDna()` client in `frontend/src/api.ts`.

## Local setup

Prerequisites: Node.js 20+, Python 3.11+, and Docker Desktop for PostgreSQL.

```powershell
cd DhanRakshak
Copy-Item .env.example .env
docker compose up -d db
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
pip install -e backend
```

Start the backend in one terminal:

```powershell
cd DhanRakshak
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "backend"
uvicorn app.main:app --app-dir backend --reload --port 8000
```

Start the frontend in another:

```powershell
cd DhanRakshak\frontend
npm install
npm run dev
```

Run tests and frontend checks:

```powershell
cd DhanRakshak
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "backend"
pytest backend\tests
cd frontend
npm run lint
npm run build
```

The API health check is available at `http://localhost:8000/health` and the frontend at the Vite URL printed by `npm run dev`.
