# 온톨로지 그래프 DB. 공식 이미지에 스키마 적용 단계만 얹음.
# 5.26 LTS 사용. 최신 라인은 CalVer로 갈렸고 이 규모에서 따라갈 이유가 없음.
FROM neo4j:5.26-community

COPY schema.cypher /schema/schema.cypher
COPY apply-schema.sh /schema/apply-schema.sh
RUN chmod +x /schema/apply-schema.sh

# 공식 이미지에는 초기화 훅이 없음. 서버 기동 뒤 별도 접속으로 스키마 적용
CMD ["/bin/bash", "-c", "/schema/apply-schema.sh & exec /startup/docker-entrypoint.sh neo4j"]
