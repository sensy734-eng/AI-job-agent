# 指标体系与评测方案

## 1. 产品指标

- 完成率：用户从输入简历/JD 到生成匹配报告的比例。
- 建议采纳率：简历改写建议被 accept 的比例。
- 面试准备使用率：生成报告后进入面试准备页的比例。
- 反馈率：用户对建议进行 accept/reject/revise 的比例。
- 多 JD 使用率：用户是否针对同一份简历比较多个岗位。
- 导出率：用户是否导出 Markdown 简历优化报告。

## 2. AI 质量指标

- 匹配档位准确率：系统输出的高/中/低匹配档位是否符合人工期望。
- 短板命中率：系统指出的 gap 是否对应 JD 真实要求。
- 建议证据覆盖率：改写建议是否绑定至少一个 evidence_id。
- 校验通过率：改写建议生成后校验为 `passed` 的比例。
- 幻觉风险数：建议中出现简历未提供经历、指标、技能或公司的风险数量。
- 面试反馈完整率：面试回答反馈是否包含得分、优点、改进点和重答提纲。

## 3. RAG 指标

- Evidence 可追溯率：证据必须包含 `source`、`text`、`score`、`retrieval_method`。
- 召回方式分布：统计 `keyword`、`hybrid-sqlite`、`vector-pgvector`、`hybrid-pgvector`、`fallback` 占比。
- Embedding fallback 次数：Embedding API 失败后回退到 hashing 的次数。
- Embedding 真实启用率：评测时是否成功使用真实 provider，而不是 fallback。
- Embedding 模型与维度：记录当前 `EMBEDDING_MODEL` 和 `EMBEDDING_DIMENSION`，便于对比不同模型。
- RAG backend：当前使用 `sqlite` 还是 `pgvector`。
- Chunk 更新稳定性：同一个 `owner_id/source` 重新 upsert 后不重复堆积。
- 检索延迟：向量召回 + 关键词召回 + rerank 的整体耗时。

## 4. 工程指标

- 报告生成延迟：P95 小于 20 秒。
- 接口成功率：核心 API 成功率大于 99%。
- 结构化输出失败率：小于 3%。
- 单次分析成本：统计 LLM token 和 embedding 调用成本。
- API 失败率：统计 LLM、Embedding、数据库连接的失败次数。
- 前端主流程可用性：输入材料、生成报告、查看证据、改写简历、模拟面试、导出材料可完成。

## 5. 评测集

- 当前评测样例位于 `backend/evaluation/fixtures.json`，覆盖 20 组脱敏简历/JD。
- 样例覆盖高匹配、中匹配、低匹配和跨方向误投。
- 样例覆盖 AI 应用开发、后端开发、算法实习、数据分析实习等方向。
- 每次修改 Prompt、评分权重、检索策略、校验策略后都应运行评测。
- 后续扩展到 30-50 组，并补充人工期望优势、期望短板、禁用虚构信息。

## 6. 评测输出

`python backend/evaluation/run_eval.py` 输出：

- `case_count`
- `band_accuracy`
- `gap_hit_rate`
- `suggestion_evidence_coverage`
- `hallucination_risk_count`
- `validation_pass_rate`
- `embedding_fallback_count`
- `embedding_provider`
- `embedding_model`
- `embedding_dimension`
- `embedding_real_enabled`
- `rag_backend`
- `average_latency_ms`
- `average_trace_steps`
- `cases`

v4 将 `hallucination_risk_count=13` 作为历史基线，后续每轮优化都应追踪该指标是否下降。

## 7. v4 质量门禁

- 改写建议必须绑定 evidence_id，建议证据覆盖率目标接近 100%。
- 校验失败或 LLM JSON 输出解析失败时，必须降级为规则模板或重新生成，不能让主流程报错。
- `/health` 不能返回 API Key、完整数据库 URL 或其他敏感配置。
- embedding 错误诊断只能返回脱敏后的状态码、模型或 provider 摘要，不能包含 key 或完整私有 endpoint。
- SQLite fallback 必须可用，保证无 PostgreSQL、无 Docker、无 Embedding API 时仍可演示。
- 切换 embedding provider 或维度后，必须运行 `POST /rag/reindex` 或重新生成报告，确保旧 chunk 不混用旧向量。
- pgvector 集成测试仅在 `PGVECTOR_TEST_DATABASE_URL` 存在时运行。
- Evidence 必须包含召回方式，前端侧栏能够展示来源、相似度和 retrieval method。
- 多 JD 对比、简历版本、Agent 链路、项目展示页在前端构建后可访问。

## 8. 本地验收命令

后端：

```bash
cd backend
python -m unittest discover -s tests -t .
python evaluation/run_eval.py
```

前端：

```bash
cd frontend
npx tsc --noEmit
npm run build
```

安全扫描重点：

- 文档、测试输出和前端 bundle 中不能出现真实 API Key。
- `.env` 不进入 git。
- `/health` 只展示脱敏后的运行状态。

## 9. 下一步评测计划

- 扩展样例集到 30-50 组，并建立高/中/低匹配分层。
- 增加人工期望字段：匹配档位、期望优势、期望短板、禁止虚构信息。
- 记录 Prompt、RAG、评分策略每次变更前后的指标对比。
- 将评测摘要沉淀到项目展示页和 README 截图中，作为面试讲解材料。
