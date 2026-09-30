FROM python:3.12-slim
WORKDIR /app
COPY packages/contracts /app/packages/contracts
COPY apps/frontend/mock-api /app/apps/frontend/mock-api
RUN pip install --no-cache-dir -e /app/packages/contracts fastapi uvicorn
WORKDIR /app/apps/frontend/mock-api
EXPOSE 8090
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8090"]
