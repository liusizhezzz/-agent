# 微光星球 Night Orbit · 手机高保真原型

高保真、移动优先的睡前行为支持产品原型。核心闭环围绕“荒芜星球上的一个人、一只动物、一株植物”展开：

产品研究参考 Sleep Ninja® 的分阶段训练和循证设计方法；当前眠舱 MVP 仅验证结束手机使用的行为闭环，不宣称治疗或临床有效。

- Onboarding：起床时间、睡前障碍、降刺激偏好
- 今晚首页：个性化着陆时间、行为指标
- 有限 Feed：4 步，没有无限滚动
- 物理 Anchor：去刷牙并回来确认
- 睡眠模式：今天结束了
- 次晨反馈：精神评分与难度
- Personal Continuity：基于真实反馈的下一晚调度建议
- 连续性回顾：最近 7 晚着陆次数、夺回时间与晨间反馈趋势
- 眠眠兔 IP：角色化提示、语音播放和低压力陪伴
- 训练中心：6 节认知行为启发式小练习与成长值解锁
- 四入口产品框架：今晚 / 训练 / 回顾 / 我的

## 设计交付

- 手机画布基准：390 × 844，桌面端居中展示，移动端铺满屏幕
- Figma 高保真文件：[眠舱 Sleep Landing · Mobile High Fidelity MVP](https://www.figma.com/design/h4AZwjbu6fRhvWyNIXY8QX)
- Figma 页面包含新版 Tonight 首页（node 6:2）、Training 训练中心（node 8:2）、Review 回顾页（node 9:2）、Product Framework（node 7:3）和 Foundations 色彩令牌页

## 启动

```bash
cd /Users/cls/sleep-landing-mvp
npm start
```

浏览器打开 http://localhost:4173。

开发模式：`npm run dev`

## 后端

使用 Node.js 原生 HTTP 服务和 Node 24 内置 SQLite，无需额外安装依赖。数据库文件会生成在 `data/sleep-landing.sqlite`。

- `GET /api/health` 服务健康检查
- `GET /api/dashboard` 用户画像、今晚计划、反馈和指标
- `POST /api/onboarding` 保存 onboarding 并生成今晚计划
- `PATCH /api/landings/:id` 更新着陆步骤和完成状态
- `POST /api/morning-feedback` 保存次晨反馈
- `POST /api/agent-message` 返回支持性语音 Agent 文案并记录事件
- `POST /api/events` 保存最小化产品行为事件

当前为单用户 Demo，未接入登录、支付、系统级 App 限制、健康设备、摄像头或诊断能力。四位 Agent 的画像由 `agent_profiles.json` 统一驱动，Prompt 由 `prompt_compiler.js` 编译，推荐由 `agent_matcher.js` 完成。

## Qwen Omni 语音适配

生产后端入口是 `backend_agent`（FastAPI + SQLite/Postgres 可替换存储），Node 服务仅保留给旧版 UI 兼容。生产启动：

```bash
python3 -m pip install -r backend_agent/requirements.txt
WUWANGWO_ENV_FILE=/path/to/forget-me-not-ad-screening/backend/.env.local \
python3 -m backend_agent
```

上线前运行真实 Qwen Omni 协议冒烟（只发送测试文本，不上传个人音频）：

```bash
WUWANGWO_ENV_FILE=/path/to/forget-me-not-ad-screening/backend/.env.local \
.venv/bin/python scripts/smoke_qwen.py
```

后端提供 `GET /healthz`、`GET/POST /api/agents*`、`POST /api/sessions`、`WS /api/sessions/:id/audio`、`POST /api/sessions/:id/end`、`GET /api/sessions/:id/memory`、`GET /api/memories` 与 `PATCH /api/memories/:id/retention`。Qwen adapter 会在服务端建立一对一 Realtime 连接，浏览器永远不会接触 API Key。

`qwen_service/server.py` 是项目内的 WebSocket 适配器，协议参考 WuWangWo 的 `fun-audiochat-realtime`，不会修改上游示例。先安装依赖并启动：

```bash
python3 -m pip install -r qwen_service/requirements.txt
export DASHSCOPE_API_KEY=...
export FUN_REALTIME_SPACE_ID=...
export FUN_REALTIME_MODEL=qwen-audio-3.0-realtime-plus
python3 qwen_service/server.py
```

密钥只从服务端环境读取；浏览器拿不到密钥。设置 `WUWANGWO_ENV_FILE` 可直接复用既有 WuWangWo 服务端 env；本机未设置时会读取既有 `backend/.env.local`（只在服务端进程内使用，不会提交或打印）。Space ID 是可选覆盖项，模型沿用既有 Omni 配置。
