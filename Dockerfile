FROM python:3.11-slim

WORKDIR /app

# 원격 접속을 위한 ssh 클라이언트 및 필수 유틸리티 설치
RUN apt-get update && apt-get install -y openssh-client curl iputils-ping && rm -rf /var/lib/apt/lists/*

# 패키지 우선 설치 (캐시 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 전체 소스 코드 복사
COPY . .

# Flask 포트 노출
EXPOSE 5050

# 파이썬 출력 버퍼링 방지 (로그 실시간 확인용)
ENV PYTHONUNBUFFERED=1

# 서버 실행
CMD ["python", "server.py"]
