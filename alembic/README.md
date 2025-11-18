# Alembic

This directory contains the Alembic migration environment for the Adaptive Lighting service.

## Quick start

1. Ensure the `DATABASE_URL` environment variable is set (or a `.env` file provides it).
2. Create a new revision:
   ```bash
   alembic revision --autogenerate -m "describe change"
   ```
3. Apply all pending migrations:
   ```bash
   alembic upgrade head
   ```
4. Roll back the most recent migration if needed:
   ```bash
   alembic downgrade -1
   ```

The environment script (`env.py`) loads the application settings, so the same configuration source (env vars, AWS Secrets Manager, etc.) powers both the API and migrations.
