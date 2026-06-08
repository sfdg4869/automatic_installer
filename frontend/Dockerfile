FROM node:20-alpine

WORKDIR /app

# 패키지 설치
COPY package*.json ./
RUN npm install

# 프론트엔드 전체 소스 복사
COPY . .

# Vite 기본 포트
EXPOSE 5173

# 도커 환경에서는 항상 외부 접속을 허용해야 하므로 --host 0.0.0.0 추가
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
