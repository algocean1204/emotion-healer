# 빌드 후 nginx가 정적 파일만 서빙함.
FROM node:22-alpine AS build
WORKDIR /build
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npx tsc -b && npx vite build

FROM nginx:1.27-alpine
COPY --from=build /build/dist /usr/share/nginx/html
# nginx:alpine이 뜰 때 templates/*.template의 환경변수를 치환해 conf.d로 내림
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
# 백엔드는 호스트에서 실행. compose가 이 값을 덮어씀
ENV API_UPSTREAM=http://host.docker.internal:8000
EXPOSE 80
