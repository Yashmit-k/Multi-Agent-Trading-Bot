# Frontend

Next.js dashboard. Talks only to `/api/v1/*` and `/ws/v1/stream`.

```bash
cd apps/frontend
npm install
npm run gen:types
npm test
npm run dev
```

Mock API:

```bash
pip install -e packages/contracts fastapi uvicorn
cd apps/frontend/mock-api
uvicorn app:app --port 8090
```

`NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8090`

LIVE mode is displayed only. This UI never enables live trading.

Docker: build from the **repository root**.
