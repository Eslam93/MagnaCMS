# Backend — FastAPI service

Python 3.12, FastAPI, async SQLAlchemy 2.0, Pydantic v2, Alembic. Tooling: uv, Ruff, mypy, pytest + pytest-asyncio.

Application code lands here as the service comes together. See the top-level [`README.md`](../README.md) for the stack overview and [`ARCHITECTURE.md`](../ARCHITECTURE.md) for the load-bearing decisions.

## Layout (target)

```
backend/
├── app/
│   ├── main.py
│   ├── api/v1/routers/        # auth, content, images, improver, brand_voices, usage, exports
│   ├── core/                  # config, security, logging, exceptions
│   ├── db/                    # session, base, models
│   ├── repositories/          # data access
│   ├── services/              # business logic
│   ├── providers/             # ILLMProvider / IImageProvider + OpenAI impls + mock + Bedrock alt
│   ├── prompts/               # one module per content type
│   ├── schemas/               # Pydantic request/response models
│   └── middleware/            # request id, rate limit, logging
├── alembic/                   # migrations
├── tests/                     # unit, integration
├── Dockerfile
└── pyproject.toml
```
