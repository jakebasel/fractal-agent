# Build from the repo root:  docker build -f wingman/Dockerfile .
# Coolify: Base Directory "/", Dockerfile Location "/wingman/Dockerfile", port 8080, volume at /data
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 DATA_DIR=/data
COPY wingman/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY wingman ./wingman
EXPOSE 8080
CMD ["uvicorn", "wingman.main:app", "--host", "0.0.0.0", "--port", "8080"]
