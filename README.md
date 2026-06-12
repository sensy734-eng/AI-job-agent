# AI 求职助手 Agent

一个面向 AI 实习投递场景的求职助手原型：基于个人简历和岗位 JD，完成岗位匹配、简历优化、面试准备，并展示可解释 RAG、Agent Trace、质量评测和本地 Embedding 接入能力。

![工作台截图](docs/assets/workbench.png)

## 项目亮点

- 端到端求职链路：简历/JD 输入 -> 匹配评分 -> 证据检索 -> 简历改写 -> 面试练习 -> 反馈迭代。
- 可解释 Agent：记录 `InputGuard -> ResumeParser -> JDParser -> RAGRetriever -> MatchScorer -> ResumeRewriter -> InterviewCoach -> ReportAssembler` 的节点状态、耗时和输出摘要。
- RAG 证据闭环：统一 `rag_chunks` 存储简历、JD、题库和反馈片段，证据包含来源、分数和召回方式。
- 本地 Embedding：默认使用 `BAAI/bge-small-zh-v1.5`，无模型或加载失败时自动回退 hashing，保证演示稳定。
- 质量评测：内置 20 组脱敏简历/JD 样例，输出档位准确率、短板命中率、证据覆盖率、幻觉风险和耗时。
- 产品化前端：支持三步输入、投递建议、证据联动、多 JD 对比、简历版本、Agent 链路和项目展示页。

## 技术栈

- 前端：Next.js + TypeScript + Tailwind CSS
- 后端：FastAPI + Pydantic + SQLAlchemy
- LLM：OpenAI-compatible Chat Completions Provider + Offline fallback
- Embedding：sentence-transformers 本地模型 / OpenAI-compatible Embedding / hashing fallback
- RAG 存储：SQLite JSON embedding fallback；可选 PostgreSQL + pgvector
- 评测：Python unittest + 脱敏样例集

## 系统架构

```mermaid
flowchart LR
    U["用户"] --> FE["Next.js Web"]
    FE --> API["FastAPI API"]
    API --> Agent["Agent Runner"]
    Agent --> Parse["Resume/JD Parser"]
    Agent --> RAG["Repository-backed RAG"]
    Agent --> Score["Match Scorer"]
    Agent --> Rewrite["Resume Rewriter + Validator"]
    Agent --> Coach["Interview Coach"]
    RAG --> Chunks["rag_chunks"]
    Chunks --> SQLite["SQLite fallback"]
    Chunks --> PG["PostgreSQL + pgvector"]
    RAG --> Emb["Local Embedding / Fallback"]
    Agent --> Trace["Agent Trace"]
```

## 功能截图

| 匹配报告 | 简历优化 |
| --- | --- |
| ![匹配报告](docs/assets/match-report.png) | ![简历优化](docs/assets/resume-rewrite.png) |

| Agent 链路 | 项目展示 |
| --- | --- |
| ![Agent 链路](docs/assets/agent-trace.png) | ![项目展示](docs/assets/showcase.png) |

## 快速启动

### 1. 后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

`.env` 中可配置 OpenAI-compatible LLM：

```env
LLM_PROVIDER=openai
OPENAI_BASE_URL=https://your-chat-endpoint/v1
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=gpt-4.1-mini
```

没有 API Key 时，系统会使用离线规则兜底，仍可跑通主流程。

### 2. 本地 Embedding

模型文件不随仓库上传。需要真实本地语义检索时运行：

```bash
cd backend
pip install -r requirements-local-embedding.txt
python download_local_embedding.py
```

如果 HuggingFace 访问慢，可使用镜像：

```bash
set HF_ENDPOINT=https://hf-mirror.com
python download_local_embedding.py
```

推荐配置：

```env
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=backend/models/bge-small-zh-v1.5
EMBEDDING_DEVICE=cpu
EMBEDDING_DIMENSION=512
EMBEDDING_FALLBACK=offline-hashing
```

模型下载或配置变更后执行：

```bash
curl -X POST http://localhost:8000/embeddings/warmup
curl -X POST http://localhost:8000/rag/reindex
```

### 3. 前端

```bash
cd frontend
npm install
npm run dev
```

默认访问：`http://localhost:3000`。

如需指定后端：

```bash
set NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
npm run dev
```

## 核心 API

- `GET /health`：服务、LLM、RAG、Embedding 状态。
- `POST /matches`：生成单个 JD 匹配报告。
- `POST /matches/batch`：同一份简历对比多个 JD。
- `POST /resume-versions`：基于采纳建议生成简历版本。
- `GET /resume-versions/{resume_id}`：查看版本历史。
- `POST /interviews/{session_id}/answer`：面试回答反馈。
- `POST /embeddings/warmup`：预热本地 Embedding。
- `POST /rag/reindex`：重建 RAG chunk 向量。
- `GET /evaluation/summary`：评测摘要。

## 评测结果

当前脱敏样例集包含 20 组简历/JD：

| 指标 | 当前结果 |
| --- | --- |
| 匹配档位准确率 | 0.75 |
| 短板命中率 | 0.447 |
| 建议证据覆盖率 | 1.0 |
| 校验通过率 | 0.558 |
| 明显幻觉风险数 | 13 |
| 本地 Embedding | `BAAI/bge-small-zh-v1.5` |
| 向量维度 | 512 |

运行评测：

```bash
cd backend
python evaluation/run_eval.py
```

## 测试

后端：

```bash
cd backend
python -m unittest discover -s tests -t .
```

前端：

```bash
cd frontend
npx tsc --noEmit
npm run build
```

## pgvector 可选配置

默认使用 SQLite，便于本地演示。需要正式向量检索时可启动 PostgreSQL + pgvector：

```bash
docker compose -f docker-compose.pgvector.yml up -d
```

`.env` 示例：

```env
VECTOR_BACKEND=pgvector
DATABASE_URL=postgresql+psycopg://job_agent:job_agent@localhost:5432/job_agent
EMBEDDING_DIMENSION=512
```

## 项目结构

```text
.
├── backend
│   ├── app
│   ├── evaluation
│   ├── tests
│   ├── download_local_embedding.py
│   └── requirements-local-embedding.txt
├── docs
│   ├── PRD.md
│   ├── architecture.md
│   ├── metrics.md
│   └── assets
├── frontend
│   ├── app
│   ├── components
│   └── lib
└── docker-compose.pgvector.yml
```

## 简历项目描述

可写入简历：

> 设计并实现 AI 求职助手 Agent，基于简历与岗位 JD 完成岗位匹配、RAG 证据检索、结构化简历改写和模拟面试反馈。后端使用 FastAPI + Pydantic + SQLAlchemy，前端使用 Next.js + TypeScript；接入 OpenAI-compatible LLM，并支持本地 BGE Embedding、SQLite/pgvector 检索、Agent Trace 和 20 组脱敏样例评测，形成可解释、可回退、可评测的 AI 应用闭环。

## 安全说明

- `.env`、数据库、模型文件和缓存目录不会提交到 Git。
- README、测试输出和前端代码不应包含真实 API Key。
- 如果 API Key 曾出现在聊天、截图或日志中，请在服务商后台轮换新 Key。

## License

MIT License
