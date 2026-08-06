#!/bin/bash
# bolt 준비 뒤 스키마 적용. 모든 제약이 IF NOT EXISTS라 반복 실행 가능.
set -u
password="${NEO4J_AUTH##*/}"

for _ in $(seq 1 60); do
  if cypher-shell -u neo4j -p "$password" "RETURN 1" > /dev/null 2>&1; then
    cypher-shell -u neo4j -p "$password" -f /schema/schema.cypher
    echo "온톨로지 스키마 적용 완료"
    exit 0
  fi
  sleep 2
done

echo "온톨로지 스키마 적용 실패: bolt가 120초 안에 안 열렸다" >&2
exit 1
