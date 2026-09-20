FROM python:3.11-slim

WORKDIR /code

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency specifications
COPY requirements.txt pyproject.toml /code/

# Install python dependencies from PyPI and TestPyPI
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ "nba-prep-26040826>=0.4.0"

# Copy application, models, data, and tests
COPY ./app /code/app
COPY ./models /code/models
COPY ./data /code/data
COPY ./tests /code/tests

EXPOSE 8000

# Render provides $PORT dynamically; fallback to 8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
