FROM python:3.12-slim AS deps
COPY pyproject.toml .
RUN pip install uv && uv pip install --system .

FROM python:3.12-slim
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY src/ /app/src/
WORKDIR /app
EXPOSE 8420
ENTRYPOINT ["python", "-m", "src.server.main"]
