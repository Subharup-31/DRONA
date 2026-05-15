FROM python:3.11-slim

WORKDIR /app

# Install deps first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# DRONA_LLM_BACKEND defaults to template — zero egress, judges need no API keys
ENV DRONA_LLM_BACKEND=template
ENV PYTHONPATH=/app

# Self-check is the default entrypoint
CMD ["python", "self_check.py"]
