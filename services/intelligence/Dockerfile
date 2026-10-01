FROM python:3.12-slim
WORKDIR /app
COPY packages/contracts /app/packages/contracts
COPY services/intelligence /app/services/intelligence
RUN pip install --no-cache-dir \
    -e /app/packages/contracts \
    -e /app/services/intelligence
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["uvicorn", "intelligence_agents.service:app", "--host", "0.0.0.0", "--port", "8080"]
