# TradingView screenshot capturer: headless Chromium on the VPS, logged into TradingView with
# Jake's session cookies, screenshots the agent's chart layout every CAPTURE_EVERY_S seconds
# and posts it to the paper agent's /screenshot endpoint (same as the Mac uploader).
FROM mcr.microsoft.com/playwright/python:v1.47.0-noble
WORKDIR /app
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data
RUN pip install --no-cache-dir playwright==1.47.0
COPY capture.py .
EXPOSE 8080
CMD ["python3", "capture.py"]
