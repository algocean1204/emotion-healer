-- 사용자·로그인 토큰·영구 대화 원문을 담음. 작업 기억과 온톨로지는 각각 JSON 파일과 그래프 DB에 있음.
-- 컨테이너가 뜰 때마다 다시 돌아도 되도록 전부 IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS users (
    -- 세션 파일 이름과 그래프 DB 키로 그대로 쓰임. 그래서 형식을 코드가 검증함
    user_id       TEXT PRIMARY KEY,
    -- scrypt 결과. 원문 비밀번호는 어디에도 남기지 않음
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    token      TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

-- 로그아웃과 만료 정리에 사용하는 인덱스
CREATE INDEX IF NOT EXISTS auth_tokens_user ON auth_tokens (user_id);
CREATE INDEX IF NOT EXISTS auth_tokens_expiry ON auth_tokens (expires_at);

-- 사용자별 선호. 제품 공통 정책(healer_*.json)은 파일에 두고, 사람마다 다른 값만 여기.
-- payload 예: {"model":"gpt-5.6-luna","effort":"xhigh"}
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id    TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    payload    JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 화면과 과거 대화 검색이 읽는 원문. AI가 보는 작업 문맥은 별도 JSON에서 줄어들 수 있지만
-- 이 표의 문장은 가입 이후 순서와 시각 그대로 유지함.
CREATE TABLE IF NOT EXISTS chat_messages (
    id         BIGSERIAL PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('human', 'ai')),
    text       TEXT NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'chat',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_messages_user_id_id ON chat_messages (user_id, id DESC);
CREATE INDEX IF NOT EXISTS chat_messages_user_time ON chat_messages (user_id, created_at DESC);
