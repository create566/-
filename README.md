# 智能监控平台

[![CI](https://github.com/create566/-/actions/workflows/ci.yml/badge.svg)](https://github.com/create566/-/actions)

基于 Plan-Execute-Replan Agent 的全自动智能监控系统，支持 Milvus 向量检索、RAG 知识增强、飞书告警。

## 核心能力

- **8 个检测器**：4 个本地（HTTP/CPU/内存/磁盘）+ 4 个远程（Prometheus/MySQL/Redis）
- **智能 Agent**：趋势分析、毛刺过滤、关联分析、根因诊断
- **专业知识库**：7 篇故障处理方案，Milvus 向量检索 + RAG 增强
- **管理端**：Web 界面注册系统、查看仪表盘、故障历史
- **飞书推送**：异常自动推送 Markdown 诊断报告

## 快速开始

### 方式一：Docker 部署（推荐）

```bash
# 1. 复制环境变量文件
cp .env.example .env
# 编辑 .env 填入你的 LLM API Key

# 2. 启动所有服务
docker-compose up -d

# 3. 索引知识库（首次运行）
docker exec smart-monitor-app python scripts/index_knowledge.py --drop

# 4. 打开管理端
open http://localhost:9900
```

### 方式二：本地开发

```bash
# 1. 安装依赖
pip install -e .

# 2. 配置 .env（参考 .env.example）

# 3. 启动
uvicorn app.main:app --port 9900

# 4. 打开管理端
浏览器访问 http://localhost:9900
```

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                    智能监控平台                           │
├─────────────────────────────────────────────────────────┤
│  Agent (LangGraph Plan-Execute-Replan)                  │
│  ├── Planner   → 制定检测计划                           │
│  ├── Executor  → 执行检测器                            │
│  └── Replanner → 根因分析 + 生成报告                    │
├─────────────────────────────────────────────────────────┤
│  检测器 (8种)                                           │
│  ├── 本地: HTTP / CPU / 内存 / 磁盘                     │
│  └── 远程: Prometheus / MySQL / Redis                  │
├─────────────────────────────────────────────────────────┤
│  知识库 (Milvus 向量检索)                               │
│  └── 7 篇专业知识文档 → RAG 增强诊断                     │
├─────────────────────────────────────────────────────────┤
│  告警通知                                               │
│  └── 飞书 Webhook + 机器人                              │
└─────────────────────────────────────────────────────────┘
```

## 注册本机监控示例

```bash
curl -X POST http://localhost:9900/api/systems \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "name": "本机监控",
    "system_type": "server",
    "endpoint": "localhost",
    "detectors": [
      {"name": "local_cpu", "thresholds": {"warning": 60, "critical": 80}},
      {"name": "local_memory", "thresholds": {"warning": 70, "critical": 85}},
      {"name": "local_disk", "thresholds": {"warning": 75, "critical": 90}}
    ],
    "check_interval_seconds": 30
  }'
```

## API 文档

启动后访问 http://localhost:9900/docs

## 环境变量说明

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_API_KEY` | LLM API Key | 必填 |
| `LLM_API_BASE` | LLM API 地址 | https://api.deepseek.com |
| `LLM_MODEL` | LLM 模型名 | deepseek-v4-flash |
| `LLM_PROVIDER` | LLM 提供商 | vllm / ollama / openai |
| `EMBEDDING_PROVIDER` | Embedding 提供商 | local (local/openai/azure) |
| `MILVUS_HOST` | Milvus 地址 | localhost |
| `DB_HOST` | MySQL 地址 | localhost |

## 目录结构

```
app/
├── agent/          # LangGraph Agent（planner/executor/replanner）
├── detectors/      # 检测器实现
├── knowledge/      # 知识库文档
├── tools/          # 飞书通知等工具
├── api/            # FastAPI 路由
├── dao/            # 数据存储层
└── main.py         # 应用入口

scripts/
└── index_knowledge.py  # 知识库索引脚本

configs/
└── prometheus.yml      # Prometheus 配置
```

## 开发

```bash
# 运行测试
pytest tests/ -v

# 索引知识库
python scripts/index_knowledge.py --preview  # 预览
python scripts/index_knowledge.py --drop      # 重建索引
```

## 云端服务依赖

- **LLM**: DeepSeek / OpenAI / Ollama / vLLM（OpenAI 兼容模式）
- **Embedding**: OpenAI text-embedding-3-small / 本地 Ollama（BGE）
- **向量数据库**: Milvus（Docker 部署）
- **数据库**: MySQL 8.0（Docker 部署）
- **缓存**: Redis 7（Docker 部署）
