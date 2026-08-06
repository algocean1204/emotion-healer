// 온톨로지 그래프 스키마. 멱등이라 컨테이너가 뜰 때마다 다시 돌려도 됨.
//
// 트리플을 관계 대신 (:Statement) 노드로 표현함. 관계로 두면 세 가지가 막힘.
// 관계를 관계로 가리킬 수 없어 개정 체인을 가변 길이로 못 타고,
// 술어를 관계 타입으로 쓰면 타입이 무한히 늘며, 관계에는 유니크 제약 설정 불가.

// id만 보던 옛 제약. MERGE가 다른 스레드의 같은 id에 결합함
DROP CONSTRAINT statement_id IF EXISTS;
DROP INDEX statement_thread IF EXISTS;

// 정체성은 (스레드, id). 스레드가 앞에 있어 조회 인덱스 역할도 겸함
CREATE CONSTRAINT statement_key IF NOT EXISTS
FOR (s:Statement) REQUIRE (s.thread_id, s.id) IS UNIQUE;

// 없으면 동시 MERGE가 같은 인물을 두 개 만듦
CREATE CONSTRAINT entity_key IF NOT EXISTS
FOR (e:Entity) REQUIRE (e.thread_id, e.name) IS UNIQUE;

// 정체성 슬롯 조회. 복합 인덱스로 스레드 단위 스캔을 줄임
CREATE INDEX statement_slot IF NOT EXISTS
FOR (s:Statement) ON (s.thread_id, s.slot);
