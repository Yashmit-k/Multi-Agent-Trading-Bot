FROM python:3.12-slim
WORKDIR /app
COPY packages/contracts /app/packages/contracts
COPY services/quant /app/services/quant
RUN pip install --no-cache-dir \
    -e /app/packages/contracts \
    -e /app/services/quant
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["uvicorn", "quant_agents.service:app", "--host", "0.0.0.0", "--port", "8080"]
