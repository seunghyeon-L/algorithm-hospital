# syntax=docker/dockerfile:1
# 병원 수술 스케줄링 — Hugging Face Spaces 단일 Docker 배포.
# 1) Next.js를 정적 export로 빌드 → out/
# 2) FastAPI(Python)가 API를 제공하면서 out/을 같은 출처에서 서빙(7860)

# ===== Stage 1: Next.js 정적 export 빌드 =====
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
# 같은 출처(상대경로)로 API를 호출하도록 빈 base로 빌드
ENV NEXT_PUBLIC_API_BASE=""
RUN npm run build
# 결과물: /fe/out (정적 사이트)

# ===== Stage 2: Python 백엔드 + 정적 프론트 서빙 =====
FROM python:3.11-slim AS app
WORKDIR /app

# ortools / deap / numpy 는 PyPI manylinux 휠로 설치됨(소스 빌드 불필요).
# 만약 HF 빌드에서 휠을 못 찾아 소스 빌드가 필요하면 base를 python:3.11 로 교체할 것.
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# 백엔드 코드
COPY backend/ ./backend/
# 1단계에서 빌드된 정적 프론트
COPY --from=frontend /fe/out ./frontend_static
ENV FRONTEND_DIR=/app/frontend_static
ENV PYTHONUNBUFFERED=1

# Hugging Face Spaces 기본 포트
EXPOSE 7860
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "7860"]
