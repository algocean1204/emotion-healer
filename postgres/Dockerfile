# 사용자 관리 DB. 공식 이미지의 초기화 훅에 스키마만 얹음.
FROM postgres:17-alpine

# docker-entrypoint-initdb.d 는 빈 데이터 디렉터리에서 한 번만 실행.
# 스키마가 전부 IF NOT EXISTS 라 다시 돌아도 안전함
COPY schema.sql /docker-entrypoint-initdb.d/10-schema.sql
