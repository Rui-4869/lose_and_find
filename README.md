# 校园失物招领智能推荐系统

基于 Flask + SQLAlchemy 实现的失物招领管理平台。系统内置规则型智能体，能够在用户提交失物或招领信息后自动完成匹配并给出推荐等级，满足课程《智能体系统设计与实现》报告中的主要功能与非功能要求。

## 功能亮点

- 失物 / 招领信息提交、浏览与管理。
- 支持一键删除失物/招领记录，自动级联清理历史推荐。
- 规则型智能体执行感知-决策-执行流程：
  - 感知：自动拉取数据库中可匹配的候选记录。
  - 决策：根据类别、地点、时间与描述相似度等规则计算匹配得分。
  - 执行：写入 `match_results` 表并在界面展示推荐等级与理由。
- 推荐表格支持“确认完成”操作，标记成功匹配并阻止后续自动覆盖。
- Bootstrap 前端界面，支持快速查看近期记录与推荐结果。
- Docker 一键部署，支持 `docker compose up` 启动。
- 单元测试验证智能体规则的正确性。

## 本地运行

1. 克隆仓库并进入目录。
2. 准备虚拟环境并安装依赖：
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
3. 初始化环境变量（可选）：
   ```powershell
   set FLASK_APP=app.py
   set FLASK_ENV=development
   # 如需自定义数据库路径：
   # set DATABASE_URL=sqlite:///data/lost_and_found.db
   ```
4. 创建 SQLite 目录（自定义路径时需要）：
   ```powershell
   mkdir data
   ```
5. 启动开发服务器：
   ```powershell
   flask run --debug
   ```
6. 打开浏览器访问 http://127.0.0.1:5000 并按以下流程体验：
   - 在“发布失物信息”表单中填写类别、地点、描述，提交后页面将高亮该失物记录。
   - 在“发布招领信息”表单中提交对应物品，智能体会自动执行匹配。
   - 匹配成功后，页面底部“智能体匹配推荐”表格显示等级、分数和理由。
   - 可在列表内点击“删除”快速移除记录，匹配表格支持“确认完成”以锁定成功结果。
7. 若此前已生成旧版本数据库，请删除 `data/lost_and_found.db` 以加载新增字段。

## Docker 部署

1. 首次部署推荐直接运行：
   ```powershell
   docker compose -p lost-and-found up --build
   ```
   - 如遇命令无法识别，可尝试 `docker-compose -p lost-and-found up --build`（旧版 Docker Desktop）。
   - 若提示找不到命令，请先安装并启动 Docker Desktop，并确保命令已加入系统 PATH。
2. 首次启动会自动创建挂载目录 `data/lost_and_found.db`，日志将显示 Gunicorn 监听地址。
3. 访问 http://127.0.0.1:5000 并按“本地运行”步骤中的业务流程体验系统。
4. 若需停止容器：
   ```powershell
   docker compose -p lost-and-found down
   ```

## 目录结构

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

## 运行测试

```bash
pytest
```

如需切换数据库或秘钥，可通过环境变量 `DATABASE_URL`、`SECRET_KEY` 覆盖默认配置。
