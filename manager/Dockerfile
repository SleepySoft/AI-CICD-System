# Manager —— AISystem 管理服务（FastAPI）
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 TZ=Asia/Shanghai

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY tools.yaml ./tools.yaml

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
