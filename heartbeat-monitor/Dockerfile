FROM python:3.11-slim
WORKDIR /app
COPY monitor.py /app/monitor.py
RUN pip install --no-cache-dir requests
ENV STATE_PATH=/data/state.json
CMD ["python", "-u", "/app/monitor.py"]
