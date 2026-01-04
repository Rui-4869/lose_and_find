# 校园失物招领智能推荐系统

基于 Flask + SQLAlchemy 构建的校园失物招领管理平台，内置规则型智能体与消息协作能力，支持多角色协同、精准匹配与一键部署。

## 功能亮点

- 失物 / 招领全链路管理：提交、编辑、浏览、删除与详情页处理均通过 Web 界面完成。
- 规则型智能体执行感知→决策→执行流程，支持针对单条记录手动触发并生成高/中/低匹配建议。
- 支持模糊关键词搜索（类别、地点、描述），默认列表展示最新全站记录，个人页聚合个人数据。
- 匹配结果提供“确认完成”保护机制、双向留言板与操作日志提示，方便物品归还协作。
- 图片上传、自动命名与静态目录存储，便于识别物品特征。
- 登录、注册、管理员授权等安全控制完善，首个账号自动成为管理员，可晋升其他账号。
- 提供 Docker 一键部署、PowerShell 脚本与 pytest 单元测试，降低运维成本并保障逻辑稳定。

## 系统架构概览

```text
浏览器 (Bootstrap + Jinja2 模板)
        ↓
Flask 路由层 (app.py：认证、表单、路由、会话)
        ↓
服务层 (services.match_service.MatchService：数据访问与业务规则)
        ↓
规则型智能体 (agent.rule_agent.RuleBasedAgent：评分与匹配策略)
        ↓
数据访问层 (SQLAlchemy ORM + SQLite / 可配置数据库)
```

- Flask 负责 HTTP 交互、用户认证、文件上传与 CLI 命令。
- MatchService 统一封装数据读取、匹配写入、权限校验与消息存储。
- RuleBasedAgent 依据预置规则对候选数据打分并调用服务层持久化。
- SQLAlchemy 模型定义实体关系，实现用户、记录、匹配、消息的级联管理。

## 模块说明

| 模块 | 关键文件 | 职责说明 |
| --- | --- | --- |
| Web 入口层 | app.py | 定义所有 Flask 路由、登录流程、表单校验、文件上传、CLI 命令与视图渲染。 |
| 服务层 | services/match_service.py | 封装匹配记录查询、增删改与权限校验，提供消息列表和状态维护。 |
| 智能体 | agent/rule_agent.py | 实现感知候选数据、匹配决策与动作执行的规则型智能体。 |
| 数据模型 | models/ | 定义 LostItem、FoundItem、MatchResult、Message、User 等 ORM 模型与关系。 |
| 配置 | config.py / database.py | 统一配置加载、数据库初始化、上传目录等全局常量。 |
| 前端展示 | templates/ | 提供基于 Bootstrap 的表单、表格、详情页与消息窗口。 |
| 辅助脚本 | scripts/ | 包含 docker-up.ps1 与 schema 升级脚本，方便部署与维护。 |
| 测试 | tests/test_agent.py | 覆盖匹配规则、权限控制、消息流转等关键逻辑。 |

## 数据模型

| 表名 | 关键字段 | 说明 |
| --- | --- | --- |
| users | username, password_hash, is_admin | 存储用户账号，支持管理员标记与 Flask-Login 集成。 |
| lost_items | category, location, occurred_at, user_id | 记录失物详情，与用户、匹配表双向关联。 |
| found_items | category, location, occurred_at, user_id | 记录招领详情，与用户、匹配表双向关联。 |
| match_results | score, level, reason, is_completed | 存储智能体输出，唯一约束保证一对一组合不重复。 |
| messages | match_id, sender_id, content | 支持匹配双方在平台内即时留言沟通。 |

## 业务流程

1. 用户注册或登录后提交失物/招领表单，可附带图片与联系方式；系统自动保存到 SQLite（或自定义数据库）。
2. 提交成功会触发 RuleBasedAgent，从相对集合中检索候选记录并执行匹配规则。
3. MatchService 将匹配结果写入 match_results 表并返回前端展示，结果包含得分、等级、理由与完成状态。
4. 用户可从主页或个人页查看推荐列表、确认完成、补充留言、重新触发匹配或删除记录。

## 智能体匹配决策策略

- **感知 (Perceive)**：读取候选失物或招领记录，结合当前提交的条目形成匹配组合。
- **决策 (Decide)**：采用权重化规则（类别 40%、地点 30%、时间 15%、描述相似度 15%），根据类别/地点一致性、时间间隔与关键字重合度给出打分与等级。
- **执行 (Act)**：通过 MatchService.upsert_match 写入结果，若记录被确认完成则保持历史结果不再覆盖。

### 优先级规则

1. **完美匹配（98 分 / 高匹配）**：类别、地点一致且时间差 ≤ 2 天。
2. **强匹配（90 分 / 高匹配）**：类别与地点一致，描述相似度 ≥ 50%。
3. **类别 + 描述匹配（80 分 / 中匹配）**：类别一致且描述相似度 ≥ 65% 或关键词重合 ≥ 3 个。
4. **类别 + 地点匹配（75 分 / 中匹配）**：类别、地点一致且时间差 ≤ 7 天。
5. **类别 + 时间匹配（70 分 / 中匹配）**：类别一致、时间差 ≤ 5 天且关键词重合 ≥ 1 个。
6. **描述 + 地点匹配（65 分 / 中匹配）**：描述相似度 ≥ 60%，地点一致。
7. **弱相关匹配（55 分 / 低匹配）**：类别一致且描述相似度 ≥ 40%，或描述相似度 ≥ 50% 且关键词重合 ≥ 2 个。
8. **地点 + 描述弱匹配（45 分 / 低匹配）**：地点一致、关键词重合 ≥ 2 个且描述相似度 ≥ 35%。

匹配在详情页由用户手动触发，匹配结果在“我的智能体匹配推荐”模块展示，并支持“确认完成”以锁定结果。

## 权限与安全控制

- 基于 Flask-Login 实现会话管理，未登录用户访问需要认证的路由将被重定向至登录页。
- 首次成功注册的账号自动赋予管理员身份，可查看全量记录并执行删除；普通用户仅能操作自己的数据。
- 提供 `flask promote-admin <用户名>` CLI，将普通账号升级为管理员。Docker 部署下通过 `docker compose exec web ...` 执行。
- 匹配留言仅限匹配双方访问和新增，接口会校验参与者身份。
- 图片上传限制文件类型与大小，统一存储到 `static/uploads` 目录并生成唯一文件名。

## 部署与运行

### 环境准备

- Python 3.11 及以上版本，确保已安装 pip。
- 推荐安装 Git 以便克隆仓库。
- 可选安装 Docker Desktop 以使用容器化部署。
- Windows 用户建议使用 PowerShell；macOS/Linux 使用终端。

### 本地开发流程

1. 克隆仓库并进入目录：
   ```powershell
   git clone <你的仓库地址> lost-and-found-agent
   cd lost-and-found-agent
   ```
2. 准备虚拟环境并安装依赖：
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
3. 配置环境变量（可选）：
   ```powershell
   set FLASK_APP=app.py
   set FLASK_ENV=development
   # set DATABASE_URL=sqlite:///data/lost_and_found.db
   ```
4. 当使用自定义 SQLite 路径时创建数据目录：
   ```powershell
   mkdir data
   ```
5. 启动调试服务器：
   ```powershell
   flask run --debug
   ```
6. 访问 http://127.0.0.1:5000 并体验业务流程：注册 → 发布记录 → 详情页触发智能体 → 查看推荐 → 留言或确认完成。
7. 若需重置数据库，删除 `data/lost_and_found.db`（或自定义路径）后重启应用。

### Docker 部署

1. 首次部署运行：
   ```powershell
   docker compose -p lost-and-found up --build
   ```
   - 旧版 Docker Desktop 可使用 `docker-compose -p lost-and-found up --build`。
   - 如提示命令不存在，请确认 Docker Desktop 已安装并在 PATH 中。
2. 首次启动将自动生成挂载目录 `data/lost_and_found.db` 并输出 Gunicorn 监听信息。
3. 访问 http://127.0.0.1:5000 即可体验与本地一致的流程。
4. 停止容器：
   ```powershell
   docker compose -p lost-and-found down
   ```

### 服务器部署建议

1. 同步代码后执行：
   ```bash
   docker compose -p lost-and-found up --build -d
   ```
2. `-d` 参数会在后台运行，Gunicorn 默认监听 0.0.0.0:5000。
3. 确保服务器开放 5000 端口，或使用 Nginx 反向代理至域名并配置 HTTPS。
4. 访问 `http://<服务器IP或域名>:5000`，即可多人协同使用。
5. 若需备份，定期导出 `data/lost_and_found.db` 或切换到云数据库获取更高并发与持久化能力。

## 测试与质量保障

- 项目提供 pytest 测试用例：
  ```bash
  pytest
  ```
- 测试覆盖智能体分级、级联删除、权限拦截、消息收发等关键逻辑。
- 建议在提交前执行测试，确保匹配策略与权限控制未被回归。

## 常见问题排查

1. **Internal Server Error**：
   - Docker 环境查看日志：`docker compose logs -f web`
   - 本地调试：`flask run --debug` 后刷新页面并观察终端 traceback。
2. **数据库缺少字段或结构变更**：
   - 删除旧版 SQLite 文件后重启：
     ```powershell
     Remove-Item .\data\lost_and_found.db
     flask run --debug
     ```
   - Docker 环境可直接删除挂载目录 `data`，再执行 `docker compose -p lost-and-found up --build`。
3. **依赖缺失**：运行 `pip install -r requirements.txt` 或重新构建 Docker 镜像。
4. **管理员权限管理**：通过 CLI 命令升级账号；若在容器内执行，使用 `docker compose exec web flask promote-admin <用户名>`。
5. **文件上传失败**：确认图片格式为 png/jpg/jpeg/gif/webp 且小于 5 MB，必要时检查 upload 目录写入权限。

## 目录结构速览

```
├── agent/                # 规则型智能体
├── models/               # 数据模型定义
├── services/             # 业务服务层
├── templates/            # 前端模板
├── tests/                # 单元测试
├── app.py                # Flask 入口
├── config.py             # 配置与常量
├── database.py           # SQLAlchemy 实例
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

如需切换数据库或秘钥，可通过环境变量 `DATABASE_URL`、`SECRET_KEY` 覆盖默认配置。
