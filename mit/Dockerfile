FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend ./backend
COPY pine ./pine
COPY docs ./docs
RUN pip install --no-cache-dir .
ENV MIT_MODE=mock MIT_HOST=0.0.0.0 MIT_PORT=8000
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
