/**
 * Turn Conduit — 한 턴 파이프라인의 분기 토폴로지를 시드 고정 입자 흐름으로 그린다.
 * 노드 = 어트랙터, 간선 = 입자 경로. 분기 색으로 path family 를 구분한다.
 * 동일 seed → 동일 프레임 시퀀스.
 */

const params = {
  seed: 260805,
  width: 1440,
  height: 1520,
  particles: 420,
  trail: 0.14,
  speed: 1.35,
  jitter: 0.55,
  // 경로 패밀리 (색 매핑)
  palette: {
    bg: [248, 249, 251],
    ink: [32, 36, 43],
    mute: [96, 104, 116],
    gate: [125, 94, 50], // 게이트·코드
    recall: [63, 92, 138], // 영구 원문 회상
    prepare: [38, 102, 139], // 되묻기
    identity: [162, 88, 31], // 정체성
    orient: [99, 73, 151], // 대화 방향
    persona: [138, 66, 113], // 페르소나
    empathy: [32, 116, 82], // 공감
    reason: [174, 77, 31], // 방법
    review: [150, 106, 20], // 검수
    after: [57, 100, 119], // 턴 후
  },
};

/** @type {GraphNode[]} */
let nodes = [];
/** @type {Edge[]} */
let edges = [];
/** @type {Particle[]} */
let particles = [];
let nodeById = {};
let reducedMotion = false;
let paused = false;
let t = 0;

class GraphNode {
  constructor(id, label, x, y, kind, layer) {
    this.id = id;
    this.label = label;
    this.x = x;
    this.y = y;
    this.kind = kind;
    this.layer = layer;
    this.pulse = random(TWO_PI);
    const longestLine = Math.max(...label.split("\n").map((line) => [...line].length));
    this.w = Math.min(264, Math.max(164, longestLine * 13 + 42));
    this.h = 30 + label.split("\n").length * 18;
  }
}

class Edge {
  constructor(from, to, family, branch) {
    this.from = from;
    this.to = to;
    this.family = family;
    this.branch = branch || "";
  }
}

class Particle {
  constructor() {
    this.reset(true);
  }

  reset(anywhere) {
    const edge = random(edges);
    this.edge = edge;
    this.u = anywhere ? random() : 0;
    this.speed = params.speed * (0.55 + random(0.9));
    this.size = 1.2 + random(2.2);
    this.life = 180 + random(220);
    this.age = 0;
    this.family = edge.family;
  }

  step() {
    this.age++;
    if (this.age > this.life) {
      this.reset(false);
      return;
    }
    const a = nodeById[this.edge.from];
    const b = nodeById[this.edge.to];
    // 간선을 따라가며 노이즈로 살짝 흔들림
    this.u += (this.speed * 0.008) / max(1, dist(a.x, a.y, b.x, b.y) / 120);
    if (this.u >= 1) {
      // 도착 노드에서 나가는 간선 중 하나로 전이
      const outs = edges.filter((e) => e.from === this.edge.to);
      if (outs.length === 0) {
        this.reset(false);
        return;
      }
      // 분기 가중: 같은 family 우선, 아니면 균등
      const same = outs.filter((e) => e.family === this.family);
      this.edge = random(same.length ? same : outs);
      this.family = this.edge.family;
      this.u = 0;
    }
  }

  draw() {
    const a = nodeById[this.edge.from];
    const b = nodeById[this.edge.to];
    const n1 = noise(this.u * 3 + this.age * 0.01, params.seed * 0.001);
    const n2 = noise(this.u * 3 + 40, this.age * 0.01);
    const x = lerp(a.x, b.x, this.u) + (n1 - 0.5) * 18 * params.jitter;
    const y = lerp(a.y, b.y, this.u) + (n2 - 0.5) * 14 * params.jitter;
    const c = params.palette[this.family] || params.palette.ink;
    const alpha = map(this.age, 0, this.life, 220, 30);
    noStroke();
    fill(c[0], c[1], c[2], alpha);
    circle(x, y, this.size);
  }
}

function buildTopology() {
  nodes = [];
  edges = [];
  const W = params.width;
  const H = params.height;

  // 세로 레이어 배치 — 질문 종료·공감·방법 경로를 분리한다.
  const L = {
    in: 120,
    recall: 215,
    recallWork: 315,
    gate: 415,
    decide: 530,
    prepare: 650,
    ask: 780,
    orient: 790,
    write: 930,
    review: 1050,
    reviewFinish: 1240,
    send: 1340,
    after: 1430,
  };

  const add = (id, label, x, y, kind, layer) => {
    const n = new GraphNode(id, label, x, y, kind, layer);
    nodes.push(n);
    nodeById[id] = n;
  };

  // 입력 · 게이트
  add("user", "사용자 말", W * 0.5, L.in, "io", "in");
  add("recall", "과거 대화 확인 게이트\n명시적 요청만 검색", W * 0.5, L.recall, "code", "recall");
  add("bridge", "확인 말 생성\n잠깐 위를 보는 생활어", W * 0.31, L.recallWork, "llm", "recall");
  add("search", "영구 원문 검색\n날짜·키워드 · LLM 없음", W * 0.69, L.recallWork, "code", "recall");
  add(
    "gate",
    "기억 주입 게이트\n프롬프트에 넣을 기억 선택",
    W * 0.5,
    L.gate,
    "code",
    "gate",
  );

  // prepare 분기 4갈래
  add(
    "decide",
    "되물을지 판정\n상황/감정/정체성/바로답",
    W * 0.5,
    L.decide,
    "llm",
    "prepare",
  );
  add(
    "situation",
    "상황 되묻기\n언제·어디서·무슨 일",
    W * 0.16,
    L.prepare,
    "llm",
    "prepare",
  );
  add(
    "identity",
    "정체성 되묻기\n호칭·하루·곁의 사람 등",
    W * 0.34,
    L.prepare,
    "llm",
    "prepare",
  );
  add(
    "analysis",
    "감정 되묻기\n감정 분석 후 한 줄 질문",
    W * 0.53,
    L.prepare,
    "llm",
    "prepare",
  );
  add(
    "analyze_skip",
    "감정만 갱신\n바로 답 경로",
    W * 0.8,
    L.prepare,
    "llm",
    "prepare",
  );
  add("end_ask", "추가 질문을 보내고\n이번 턴 종료", W * 0.18, L.ask, "end", "prepare");

  // 대화 방향 · 페르소나 (순차)
  add(
    "orient",
    "대화 방향 정리\n낮은 강도 조언은 방법만",
    W * 0.44,
    L.orient,
    "llm",
    "orient",
  );
  add(
    "persona",
    "태도 재사용/갱신\n4턴 임대·안전 사건 즉시",
    W * 0.69,
    L.orient,
    "llm",
    "orient",
  );

  // 답변 분기
  add("empathy_w", "공감 초안 작성", W * 0.31, L.write, "llm", "empathy");
  add("reason_w", "방법 초안 작성", W * 0.72, L.write, "llm", "reason");

  // 초안별 최종 다듬기 1회 + 코드 안전 검사
  add("finalize", "공감 답 한 번 다듬기\n문제 부분만 최소 수정", W * 0.31, L.review, "llm", "review");
  add("guard", "친구 말투·위기 안전 검사", W * 0.31, L.reviewFinish, "code", "review");
  add("finalize_r", "방법 답 한 번 다듬기\n문제 부분만 최소 수정", W * 0.69, L.review, "llm", "review");
  add("guard_r", "의도·진행 보고 안전 검사", W * 0.69, L.reviewFinish, "code", "review");

  add("end_ans", "사용자에게 응답 전송", W * 0.5, L.send, "io", "after");
  add("remember", "기억 만들기\n사실·정체성 슬롯", W * 0.36, L.after, "llm", "after");
  add("compress", "대화 압축\n길 때만", W * 0.64, L.after, "llm", "after");

  const E = (a, b, family, branch) => edges.push(new Edge(a, b, family, branch));

  // 메인 유입
  E("user", "recall", "recall", "매 턴");
  E("recall", "search", "recall", "확인 요청 · 동시");
  E("recall", "bridge", "recall", "확인 요청 · 동시");
  E("recall", "gate", "gate", "평소 대화");
  E("search", "gate", "recall", "원문 근거만 추가");
  E("bridge", "gate", "recall", "확인 말 결합");
  E("gate", "decide", "prepare", "배경 문장 실음");

  // prepare 분기 — 판단 기준을 라벨에
  E("decide", "situation", "prepare", "상황 확인");
  E("decide", "identity", "identity", "정체성 확인");
  E("decide", "analysis", "prepare", "감정 확인");
  E("decide", "analyze_skip", "prepare", "바로 답");
  E("situation", "end_ask", "prepare");
  E("identity", "end_ask", "identity");
  E("analysis", "end_ask", "prepare");
  E("analyze_skip", "orient", "orient");

  // orient → persona → 분기
  E("orient", "persona", "persona");
  E("persona", "empathy_w", "empathy", "공감 또는 둘 다");
  E("persona", "reason_w", "reason", "방법만");

  // empathy path + both
  E("empathy_w", "finalize", "empathy");
  E("finalize", "guard", "review", "LLM 1회");
  E("guard", "reason_w", "reason", "둘 다 + 연결 허용");
  E("guard", "end_ans", "empathy", "공감만이면 전송");

  // reason path
  E("reason_w", "finalize_r", "reason");
  E("finalize_r", "guard_r", "review", "LLM 1회");
  E("guard_r", "end_ans", "reason", "전송");

  // after turn
  E("end_ans", "remember", "after", "동시 시작 · 매 턴");
  E("end_ans", "compress", "after", "동시 시작 · 길 때만");
}

function setup() {
  const c = createCanvas(params.width, params.height);
  c.parent("canvas-host");
  pixelDensity(Math.min(2, displayDensity()));
  randomSeed(params.seed);
  noiseSeed(params.seed);
  reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  buildTopology();
  particles = [];
  for (let i = 0; i < params.particles; i++) particles.push(new Particle());
  if (reducedMotion) {
    // 한 프레임만 그려 정적 그래프
    drawFrame(true);
    noLoop();
  }
  wireControls();
}

function draw() {
  if (paused) return;
  drawFrame(false);
  t++;
}

function drawFrame(staticMode) {
  // 잔상
  noStroke();
  fill(params.palette.bg[0], params.palette.bg[1], params.palette.bg[2], staticMode ? 255 : params.trail * 255);
  rect(0, 0, width, height);

  // 배경 장력 필드 (토폴로지 위에 얇은 flow)
  if (!staticMode) drawField();

  // 간선
  for (const e of edges) drawEdge(e);

  // 입자
  if (!staticMode) {
    for (const p of particles) {
      p.step();
      p.draw();
    }
  } else {
    // 정적: 간선 위에 고정 점 샘플
    for (const e of edges) {
      const a = nodeById[e.from];
      const b = nodeById[e.to];
      const c = params.palette[e.family] || params.palette.ink;
      for (let i = 1; i < 6; i++) {
        const u = i / 6;
        fill(c[0], c[1], c[2], 160);
        noStroke();
        circle(lerp(a.x, b.x, u), lerp(a.y, b.y, u), 2.5);
      }
    }
  }

  // 노드
  for (const n of nodes) drawNode(n, staticMode);

  // 헤더
  drawChrome();
}

function drawField() {
  stroke(180, 186, 196, 45);
  strokeWeight(0.6);
  const step = 48;
  for (let x = 20; x < width; x += step) {
    for (let y = 20; y < height; y += step) {
      const a = noise(x * 0.004, y * 0.004, t * 0.003) * TWO_PI * 2;
      line(x, y, x + cos(a) * 10, y + sin(a) * 10);
    }
  }
}

function drawEdge(e) {
  const a = nodeById[e.from];
  const b = nodeById[e.to];
  const c = params.palette[e.family] || params.palette.mute;
  const start = cardPort(a, b);
  const end = cardPort(b, a);
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const length = max(1, sqrt(dx * dx + dy * dy));
  const normalX = -dy / length;
  const normalY = dx / length;
  const bend = e.from === "guard" && e.to === "reason_w" ? -108 : 0;
  const c1 = {
    x: start.x + dx * 0.34 + normalX * bend,
    y: start.y + dy * 0.34 + normalY * bend,
  };
  const c2 = {
    x: start.x + dx * 0.66 + normalX * bend,
    y: start.y + dy * 0.66 + normalY * bend,
  };
  stroke(c[0], c[1], c[2], 70);
  strokeWeight(1.2);
  noFill();
  bezier(start.x, start.y, c1.x, c1.y, c2.x, c2.y, end.x, end.y);
  if (e.branch && shouldDrawBranchLabel(e)) {
    const labelX = bezierPoint(start.x, c1.x, c2.x, end.x, 0.5);
    const labelY = bezierPoint(start.y, c1.y, c2.y, end.y, 0.5);
    textSize(10);
    const labelWidth = textWidth(e.branch) + 18;
    noStroke();
    fill(params.palette.bg[0], params.palette.bg[1], params.palette.bg[2], 235);
    rect(labelX - labelWidth / 2, labelY - 10, labelWidth, 20, 10);
    fill(c[0], c[1], c[2], 220);
    textAlign(CENTER, CENTER);
    text(e.branch, labelX, labelY);
  }
}

function cardPort(node, target) {
  const dx = target.x - node.x;
  const dy = target.y - node.y;
  const scale = 1 / max(1, abs(dx) / (node.w / 2 + 3), abs(dy) / (node.h / 2 + 3));
  return { x: node.x + dx * scale, y: node.y + dy * scale };
}

function shouldDrawBranchLabel(e) {
  return new Set([
    "decide:situation",
    "recall:search",
    "recall:gate",
    "search:gate",
    "decide:identity",
    "decide:analysis",
    "decide:analyze_skip",
    "persona:empathy_w",
    "persona:reason_w",
    "finalize:guard",
    "finalize_r:guard_r",
    "guard:reason_w",
    "guard:end_ans",
    "guard_r:end_ans",
  ]).has(`${e.from}:${e.to}`);
}

function drawNode(n, staticMode) {
  const c =
    n.kind === "code"
      ? params.palette.gate
      : n.kind === "end"
        ? params.palette.mute
        : n.kind === "io"
          ? params.palette.ink
          : params.palette[n.layer] || params.palette.ink;
  const pulse = staticMode ? 1 : 0.85 + 0.15 * sin(t * 0.04 + n.pulse);
  const left = n.x - n.w / 2;
  const top = n.y - n.h / 2;
  const corner = n.kind === "io" ? n.h / 2 : n.kind === "code" ? 7 : 14;
  noStroke();
  fill(c[0], c[1], c[2], 18 * pulse);
  rect(left - 5, top - 5, n.w + 10, n.h + 10, corner + 4);
  stroke(c[0], c[1], c[2], 210);
  strokeWeight(1.2);
  fill(params.palette.bg[0], params.palette.bg[1], params.palette.bg[2], 242);
  rect(left, top, n.w, n.h, corner);
  noStroke();
  fill(c[0], c[1], c[2], 230);
  rect(left + 10, top + 10, 5, n.h - 20, 3);
  fill(params.palette.ink[0], params.palette.ink[1], params.palette.ink[2], 210);
  textAlign(CENTER, CENTER);
  textSize(12);
  textLeading(16);
  text(n.label, left + 22, top + 8, n.w - 32, n.h - 16);
}

function drawChrome() {
  noStroke();
  fill(params.palette.ink[0], params.palette.ink[1], params.palette.ink[2], 230);
  textAlign(LEFT, TOP);
  textSize(18);
  text("일반 대화 한 턴 — 내 친구 민수 (스트롱 민수)", 28, 18);
  fill(params.palette.mute[0], params.palette.mute[1], params.palette.mute[2], 220);
  textSize(12);
  text(
    `시드 ${params.seed}  ·  대화 방향 orient  ·  입자 ${params.particles}개  ·  실제 코드 기준`,
    28,
    42,
  );

  // 범례
  const legend = [
    ["recall", "원문 회상"],
    ["gate", "기억 주입"],
    ["prepare", "되묻기"],
    ["identity", "정체성"],
    ["orient", "대화 방향"],
    ["persona", "태도"],
    ["empathy", "공감 답"],
    ["reason", "방법 답"],
    ["review", "한 번 다듬기"],
    ["after", "응답 뒤"],
  ];
  const legendX = width - 470;
  textSize(11);
  for (const [index, [key, label]] of legend.entries()) {
    const c = params.palette[key];
    const x = legendX + (index % 3) * 150;
    const y = 24 + floor(index / 3) * 20;
    fill(c[0], c[1], c[2]);
    circle(x, y, 8);
    fill(params.palette.mute[0], params.palette.mute[1], params.palette.mute[2]);
    textAlign(LEFT, CENTER);
    text(label, x + 10, y);
  }
}

function wireControls() {
  const seedEl = document.getElementById("seed");
  const pauseBtn = document.getElementById("pause");
  const resetBtn = document.getElementById("reset");
  const exportBtn = document.getElementById("export");
  if (seedEl) {
    seedEl.value = String(params.seed);
    seedEl.addEventListener("change", () => {
      params.seed = int(seedEl.value) || 0;
      reseed();
    });
  }
  if (pauseBtn) {
    pauseBtn.addEventListener("click", () => {
      paused = !paused;
      pauseBtn.textContent = paused ? "재생" : "일시정지";
      pauseBtn.setAttribute("aria-pressed", paused ? "true" : "false");
    });
  }
  if (resetBtn) resetBtn.addEventListener("click", reseed);
  if (exportBtn) {
    exportBtn.addEventListener("click", () => {
      saveCanvas(`turn-conduit-${params.seed}`, "png");
    });
  }
}

function reseed() {
  randomSeed(params.seed);
  noiseSeed(params.seed);
  buildTopology();
  particles = [];
  for (let i = 0; i < params.particles; i++) particles.push(new Particle());
  t = 0;
  background(params.palette.bg);
  if (reducedMotion) {
    drawFrame(true);
    noLoop();
  } else {
    loop();
  }
}

function keyPressed() {
  if (key === " ") {
    paused = !paused;
    const pauseBtn = document.getElementById("pause");
    if (pauseBtn) {
      pauseBtn.textContent = paused ? "재생" : "일시정지";
      pauseBtn.setAttribute("aria-pressed", paused ? "true" : "false");
    }
    return false;
  }
  if (key === "r" || key === "R") reseed();
  if (key === "s" || key === "S") saveCanvas(`turn-conduit-${params.seed}`, "png");
}
