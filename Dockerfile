FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 DATA_DIR=/data
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY rules ./rules
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
