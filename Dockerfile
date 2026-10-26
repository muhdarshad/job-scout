FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt ./
COPY scraper/vendor/JobSpy ./scraper/vendor/JobSpy
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY scraper ./scraper
COPY --from=frontend /build/dist/client ./dist/client
RUN useradd --uid 10001 --create-home scout && chown -R scout:scout /app
USER scout
EXPOSE 8000
CMD ["uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8000"]
