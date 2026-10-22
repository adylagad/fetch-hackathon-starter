# Runs the Hackkit Guide (agent/) as a background worker. Outbound internet only:
#   docker build -t hackkit-guide .
#   docker run -d --restart unless-stopped --env-file agent/.env hackkit-guide
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app

COPY . .
RUN uv sync --no-dev --all-packages --frozen

WORKDIR /app/agent
CMD ["uv", "run", "--no-dev", "python", "agent.py"]
