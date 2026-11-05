# Parent-Check 代码与上线审查

审查日期：2026-10-30。对象：本地 main（46da369）和当前全部未提交改动。
本文件保留修复前的审查与复现记录。**R1–R19 已修复并推送至草稿 PR #1，CI 通过；尚未部署。**

最新实现与验证结果见 [BUGFIXES.md](BUGFIXES.md)。下文描述的是发现问题时的行为，
不代表修复后的当前行为。AWS 线上观察同样是修复部署前的快照；本次没有修改云端配置。

## 审查范围与评价

覆盖 Flask 路由、数据层、规则判断、URL 抓取、OCR、AI 图与工具、RAG、
日志/追踪、Next.js 页面及 API 类型、Docker/Compose、密钥导出与 systemd、
CI，以及可选 ECS Terraform 和研究/MCP 入口。静态审查和合成复现不能证明
生产环境不存在其他问题；未读取生产密钥或用户历史，也未进行线上攻击测试。

| 维度 | 评价 | 主要依据 |
|---|---|---|
| 安全 | 上线前需修复 | DNS 重绑定、错误信息进入模型、依赖告警、线上 SSH/metrics 暴露 |
| 正确性 | 需修复 | 原始 URL 风险丢失、AI 风险与摘要矛盾、前后端 advice 类型不一致 |
| 性能与可靠性 | 需修复 | 外部下载不设上限、同步单 worker、密钥刷新失败会令重启后的服务停机 |
| 可维护性 | 基础良好，覆盖有缺口 | 模块边界明确，但现有测试未覆盖上述跨模块行为 |

有效的基础包括：历史数据查询与写入按会话所有者过滤、CSRF、参数化 SQL、
模板转义、AI 风险只能上调、按服务分配密钥文件、生产 Cookie 配置和密钥缺失时拒绝启动。
这些优点不抵消以下问题。

## 需要修复的代码问题

### R1 · P1 · URL 校验没有约束实际连接的 IP

位置：fetch_url.py:97、fetch_url.py:164。

is_safe_url 先解析 DNS；requests.get 建立连接时会再次解析，且没有使用已验证的地址。
攻击者可让校验时返回公网 IP、连接时返回内网 IP。合成传输复现得到解析序列
`公网、公网、127.0.0.1`，抓取仍成功。它可绕过应用层 SSRF 检查；实际能访问哪些
内部服务取决于网络和防火墙。仅限制重定向不能解决此问题。

建议：将已验证 IP 固定到连接，并正确保留 HTTPS 的主机验证/SNI，或使用受控的
出站代理；配合阻止内网/metadata 的网络出站规则。增加 DNS 重绑定回归测试。

### R2 · P1 · 外部网页下载没有字节上限或整体时间预算

位置：fetch_url.py:164–183；Dockerfile:27。

requests.get 默认完整缓冲响应，随后才截取文本到 MAX_CHARS。超大页面、压缩膨胀
或持续缓慢发送数据的站点可消耗内存并占住当前唯一的同步 Gunicorn worker。
输入的 6MB 限制不限制下载内容；timeout=10 也不是整个下载的截止时间。

建议：流式读取、限制解压后字节数、检查内容类型、使用整体截止时间，所有跳转共享
预算，并在超限/超时后立即关闭响应。详见 [Requests 的 timeout 定义](https://docs.python-requests.org/en/latest/user/quickstart/#timeouts)。

### R3 · P1 · 抓取正文后丢弃原始链接的确定性风险

位置：app.py:271、app.py:465。

两条文本路由均用抓取的正文覆盖 content，随后只对正文运行规则。复现：提交已在
SAMPLE_BLOCKLIST 中的 `http://hmrc-refund.net`，让抓取返回无害正文，最终返回 `ok`。
恶意站点可以给抓取器展示不同内容，原始域名的危险信号不应因此消失。

建议：保留并检测原始 URL、重定向目标与正文，合并证据并取最高风险；增加真实路由测试。

### R4 · P1 · AI 上调风险后，摘要、分类和历史内容未同步

位置：app.py:313、app.py:410；helpers.py:142–143。

当前只更新 risk，category/reasons 保持规则结果。复现中 AI 返回 HIGH，API 输出
`risk=danger, category=none`，同时 summary 显示“I didn't find obvious warning signs”，
普通 advice 为空。HTML 历史只保存这套过时分类和规则理由，无法保留 AI 升级的解释。

建议：从最终风险和证据统一构建页面/API/历史视图，避免高危标签与低风险摘要并存；
对两种语言、HTML/API 和历史回看增加测试。

### R5 · P1 · 新 systemd 模板的重启流程会先停服务再取 Secret

位置：ops/parent-check.service.example:15–17；DEPLOY.md 的更新流程。

这是上一轮新增方案中的问题。systemctl restart 会先执行 ExecStop（Compose stop），
再执行 ExecStartPre。若 IAM、网络或 Secret 校验失败，原服务已经停止，无法达到
文档声称的“失败时保留运行中的旧服务”。up -d 也没有确认 web 的业务就绪状态。

建议：将部署/轮换与显式停机分离，在停止旧服务前完成密钥获取及校验，再切换并检查
就绪状态，失败时恢复旧服务。需要真实 Linux/Compose 验收。
参见 [systemd 的 restart 顺序](https://www.freedesktop.org/software/systemd/man/255/systemd.service.html)。

### R6 · P1 · 工具异常文本未经脱敏发送回 LLM

位置：ai/tools.py:176–178；ai/agent_graph.py:263；mcp_server.py:100 附近。

run_tools_parallel 将 str(e) 作为工具输出，tools_node 再将其加入下一次模型请求。
用异常消息中的合成凭证标记复现，标记完整出现在工具响应。数据库异常可能包含 SQL、
参数及内部连接信息。日志格式器的密钥替换不覆盖发往模型的这条数据流。
graph 的 exc_info=True 与“只记录错误类型”的注释也不一致。

建议：对外只返回固定错误码和关联 ID；日志只记允许的元数据。MCP 同样不要回传原始异常。

### R7 · P1（部署 Next.js 前）· 固定依赖处于已公告受影响版本范围

位置：frontend/package.json:13、frontend/package-lock.json。

实际安装 next=15.5.26、sharp=0.35.4。npm audit 返回 5 个受影响包条目：
1 Critical、3 High、1 Moderate；包含 next、sharp 和构建工具依赖。
厂商公告将 Next.js <=15.5.27 列入受影响范围，并提供 15.5.28 修复。
图像优化/SVG 风险具有 Linux 与运行时条件；本项目未使用 Server Actions，
不能把公告里的所有攻击条件都当作已满足，也不能据此宣称线上已被攻破。

建议：升级到该维护分支的修复版本并更新 lockfile，再审计、构建和验证；确认 sharp
也达到公告要求。当前 EC2 Compose 运行的是 Flask，Next.js 的风险需按其实际部署位置评估。
来源：[Next.js 官方安全公告](https://github.com/vercel/next.js/security/advisories/GHSA-2464-fhr4-w9xw)、
[Server Actions 公告及适用条件](https://github.com/vercel/next.js/security/advisories/GHSA-p3m5-59mp-jv5r)。

### R8 · P2 · 图片检查只相信 MIME 和长度

位置：ocr.py:32–44。

`b'not an image'` 配上 image/png 会被直接送给 OCR provider；合成 provider 返回文本后
extract_text 报成功。当前未检查真实格式、像素尺寸、解码有效性或解压膨胀。
这不等于服务端已经能执行上传内容，但可以使无效内容到达外部服务并消耗额度。

建议：先解码并校验允许的图片格式、像素/字节上限，必要时重新编码，再调用 OCR。

### R9 · P2 · Redis 短暂失败后永久切换为本进程限流

位置：ratelimit.py:70–77。

异常时将 self._redis 置 None，没有重试/恢复路径。合成复现中 Redis 恢复后 limiter
仍为 memory，完全没有再次访问 Redis。多实例/多 worker 的全局限流因此失效，
进程重启也会清空回退配额。当前单 worker 降低了倍增风险，但未消除恢复与重启问题。

建议：加入受控重连、健康状态和告警；给付费 AI 调用设计独立于进程生命周期的总预算。

### R10 · P2 · API 的 advice 类型与前端定义不一致

位置：frontend/lib/types.ts:22、frontend/components/ResultCard.tsx:52–57。

Flask 实际返回 string[]，前端声明 string，并放进单个 p 中渲染。构建不会验证远程
JSON 的运行时类型，多条建议会连在一起，空数组仍会显示空建议区块。

建议：统一 API schema，按数组逐项渲染，并补一条真实返回数据驱动的前端测试。

### R11 · P2 · URL 编码后的数据库密码导致 Alembic 配置失败

位置：migrations/env.py:19–25。

导出器正确将密码中的 @ 等字符编码成 %xx，但 Alembic 的 ConfigParser 会把百分号
当作插值语法。以 `p@ssword` 的重复字符串生成合成 DB URL，set_main_option 直接抛
ValueError；因此应用可以连接的密码并不一定能用于迁移命令。

建议：传入 Alembic 配置前将字面百分号转义为双百分号，或避免经 ConfigParser 传递 URL，
并增加包含 @、%、斜杠等字符的迁移配置测试。

### R12 · P2 · 全新安装会拉取不兼容的 MCP 2.x

位置：requirements.txt:27、mcp_server.py:19。

在全新 Python 3.12 环境按 requirements.txt 安装得到 mcp 2.3.0，
`import mcp_server` 因 `mcp.server.fastmcp` 不存在而失败。版本约束没有限制
主版本，测试又未覆盖这个入口。Flask 测试通过不能证明 MCP 服务能启动。

建议：将依赖约束到经过测试的兼容版本，或按新 SDK 迁移接口，并给 MCP 入口加入
无外部凭证的启动/工具契约测试。此问题影响 MCP 入口，不等于 Flask 网站无法启动。

## 补充业务逻辑复查

以下问题来自对输入、规则、AI 工具和历史回看的补充检查；使用合成数据复现，未调用真实 LLM。

### R13 · P1 · 黑名单域名加默认端口后不再命中

位置：blocklist.py:58–63、blocklist.py:81。

_host 使用字符串切割，不是真正的 URL hostname 解析。`https://hmrc-refund.net/info`
得到黑名单分数 3；同一个地址写为 `https://hmrc-refund.net:443/info` 得到 0。
完整规则结果从 danger 降为 caution，剩下的提醒只来自 hmrc 关键词。子域名也未匹配
根域名黑名单。此问题与 R3 的正文覆盖是两个独立缺口，混合文本里的链接同样受影响。

建议：使用标准 URL 解析提取规范 hostname，剔除端口/userinfo，明确根域名与子域名匹配规则；
避免简单后缀匹配误伤无关域名。

### R14 · P2 · 接受 5000 字，但两道 AI 都静默只看前 800 字

位置：app.py:65、ai/agent.py:189/196、ai/verifier.py:96/104。

以 850 个填充字符加尾部证据标记构建消息，分析员和复核员的提示词中都没有尾部标记。
规则会处理较长内容，但 AI 特有的语义检测覆盖不到后面的内容；独立复核也重复了这个盲区。

建议：让 AI 覆盖业务承诺的输入长度，或按段分析并合并风险；若必须截断，需要明确告知
用户实际检查范围，不应将其当作完整内容的二次核查。

### R15 · P2 · 电话号码规则把语言当作地区

位置：ai/tools.py:89–100、ai/tools.py:127–152。

REGION=uk 时，同一条英国热线文本在 lang=en 能找到号码，在 lang=zh 却报告没有号码；
切换界面语言不应改变实际所在地区或号码体系。regions.py 已区分地区与语言，工具没有沿用。

建议：根据独立 region 参数选择号码规则，lang 只负责输出翻译；覆盖“英国地区、中文界面”的测试。

### R16 · P2 · 普通大陆手机号的正则写错

位置：ai/tools.py:134。

`^\+?86?1...` 中 8 是必需的，只有 6 可选。复现中 `13800138000` 被标为未知号码，
`+8613800138000` 却能识别为大陆手机号。

建议：将国家码作为完整可选分组，而不是只让数字 6 可选；测试有无国家码及非法长度。

### R17 · P2 · 同名并行工具调用会丢掉超时结果

位置：ai/tools.py:192–195。

超时逻辑按工具名称判断完成，而非按单次调用判断。让两个 query_knowledge_base 调用
一快一慢，复现结果是发出 2 次调用、只收到 1 个响应，并且没有 timeout 响应。
后续模型收到的 functionResponse 与请求不完整对应。

建议：按调用索引/唯一 ID 跟踪每一次调用，保证每个请求都有成功或错误响应。

### R18 · P2 · 英文组合规则把 wireless 当作 wire 汇款信号

位置：semantic.py:61–62、semantic.py:76。

semantic.hits 在去掉空格的字符串上做子串匹配。复现：
`Hi mum, I urgently need my wireless headphones.` 命中 wire、hi mum、urgent，结果为 danger；
将 wireless 换成 corded 后，语义升级分数由 3 变为 0，结果为 caution。
这是错误分词造成的额外风险升级，不只是“宁可保守”的阈值选择。

建议：英文信号按单词/短语边界匹配，中文继续使用适当的归一化匹配；加入相近无害词测试。

### R19 · P2 · 新装依赖后数据库追踪没有实际启用

位置：requirements.txt:12、observability.py 中的 SQLAlchemyInstrumentor 初始化。

全新环境安装得到 SQLAlchemy 2.1.6，而安装的 SQLAlchemy instrumentation 声明仅支持
`>=1.0.0,<2.1.0`。启动日志明确报“不进行 instrument”，随后却仍输出 otel=True 的配置成功信息。
网站测试通过，但数据库追踪缺失。

建议：约束经过联合测试的依赖版本，并验证实际产生 DB span，不能只检查能否 import 或启动。

### 对已有 R4 的历史记录补充验证

已用 HTML 路由复现：首次结果包含合成 AI 原因，进入同一用户的历史详情后原因消失；
数据库保存 risk=danger、category=none、reasons 为空。修复 R4 时必须同时处理展示与持久化，
仅修改风险标签或 API 摘要无法修复历史回看。

### 需要明确的设计取舍

- “AI 只能上调风险”是有意的安全策略，不是实现 bug；它也意味着 AI 无法纠正规则误报。
- 仅凭 .cn 等域名后缀就直接判 danger 是过强的启发式规则。合成规则测试中合法政府域名
  也得到 danger；后缀适合充当辅助信号，是否据此升级应通过误报评估决定。
- Next.js 的 stateless API 不保存历史、HTML 页面保存会话历史，是当前产品行为差异；
  需要在用户界面说明，而不是默认宣称两个前端拥有相同功能。

## 线上只读核查

| 项目 | 本次观察 | 需要的处理 |
|---|---|---|
| EC2 | 实例运行中，无 IAM instance profile；IMDSv2 required，hop limit=2 | 部署前配置目标角色及 Secret 权限，并验证 metadata 隔离 |
| 安全组 | 22 和 443 对 0.0.0.0/0 开放 | 先限制 SSH 到管理 IP；SSM 验证成功后再关闭 SSH |
| 公网 /metrics | **200，Prometheus 格式，约 811KB** | 修正/重新加载实际入口配置，公网应返回 404/403；仓库 Caddyfile 规则未在该线上路径生效 |
| /about 与 /history | 200，未观察到新增 nosniff、HSTS、no-store 头 | 确认实际部署版本、构建并重新创建服务 |
| main 的既有 CI | 46da369 对应运行成功 | 不能替代当前未提交改动的 CI；新 security workflow 尚未运行 |

本次没有读取 metrics 的内容到报告，没有访问他人的历史数据，没有发起线上 LLM 调用。
未验证实例内实际容器端口、挂载、磁盘加密、备份或当前 Secret 配置。

## 验证记录与边界

- 原开发环境：ruff 通过；pytest 125 passed / 1 skipped；分类评估 61 条中 59 条正确，
  诈骗召回 31/31，既有质量门禁通过。
- 另外建立了隔离的全新 Python 3.12 环境，安装 requirements.txt 和 requirements-dev.txt
  全部依赖（含 OpenTelemetry、Prometheus）；ruff 与 pytest 再次通过，仍为 125 passed /
  1 skipped。该验证使用 SQLite，不是实际 Postgres/Redis/Docker 集成验证。
- 图片实测评估因没有配置 OCR 凭证而跳过；不能将其表述为通过真实 OCR 测试。
- 补用 WSL Linux 执行密钥快照的 0700/0444 权限、原子切换与旧快照保留断言，全部通过；
  这不是 Docker 挂载或真实 AWS 角色验证。
- npm ci 后 Next.js 生产构建和类型检查通过；npm audit 存在上述告警。未运行自动修复。
- 当前机器没有可用 Docker，因此未运行生产 Compose 集成检查。
- 未执行完整 Python 依赖 CVE 审计；本报告的依赖告警统计来自 npm，不能推广为整个系统的漏洞总数。

## 建议发布次序

1. 修复 R1–R7；为复现问题添加跨模块回归测试，准备完整依赖下的测试结果。
2. 跑新 security workflow，使用合成密钥验证 Compose 的挂载、网络、只读文件系统和就绪检查。
3. 备份当前 Postgres；保留现有 Compose project 名称和数据卷。先完成 IAM/Secret 引导，
   迁入现有数据库密码并协调必要的密码轮换。**不要直接用新配置盲目 up --build。**
4. 更新现有 EC2 的代码、镜像与 Caddy 配置，重建需要更新的容器，进行 HTTPS、metrics、
   会话隔离和密钥读取验收；不要删库或创建新的空数据卷。
5. 若 Next.js 单独托管，另外更新那一处前端部署；仅更新 Flask 容器不会更新 Next.js。
6. 部署 GitHub Actions 工作流是提交/推送代码的事情，无需重建 AWS 服务器。

可选 Terraform ECS 当前明确是 HTTP 演示栈，不能用它替代上述生产迁移。
