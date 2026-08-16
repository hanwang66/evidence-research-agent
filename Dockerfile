FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY evidence_research ./evidence_research

RUN pip install --no-cache-dir .

EXPOSE 3051

CMD ["uvicorn", "evidence_research.api:app", "--host", "0.0.0.0", "--port", "3051"]
