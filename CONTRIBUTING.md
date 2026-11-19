# Contributing

## Local setup

1. In `backend/`, copy `.env.example` to `.env` and fill in the keys you actually use. Never commit the real `.env`.
2. Backend: from `backend/`, install `requirements-dev.txt` and run `python -m pytest tests/ -v`.
3. Frontend: from `frontend/`, run `npm install` then `npm run dev`.

## Pull requests

Keep changes small and focused. Match the existing commit style (`feat:`, `fix:`, `test:`, `docs:`). Include tests when you change backend behaviour.
