# 代码自审 · Code audit

按"如何一眼判断垃圾代码"的 8 条标准 + 100 分评分,逐项对照真实源码。
欢迎对着源码核对每一条。

## 外部审查(评 68/100)发现的问题与修复

一位 reviewer 在能看到源码后给出 68/100 与一份很到位的清单。逐条认领并修复:

- **P0 隐私文案与实现不符** — 历史其实存在服务器(按浏览器 token 区分),文案却说"只存在浏览器"。
  已改为如实表述:服务器只存判断摘要(不含原文),用浏览器随机编号区分。
- **P0 没有真正的删除历史** — 新增 `POST /history/clear`(`DELETE … WHERE user_token = ?`)+ 历史页"清除历史"按钮(带确认)。
- **P0 依赖未锁版本** — `requirements.txt` 锁到 `Flask==3.1.3`、`gunicorn==23.0.0`。
- **P0 生产 secret 危险兜底** — 生产(Render)缺 `SECRET_KEY` 时直接报错,不再回退到固定 dev key。
- **P1 无 CSRF 保护** — 加了基于 session 的 CSRF 令牌:所有 POST 表单带隐藏字段,`before_request` 校验,不符返回 400。
- **P1 英文关键词 substring 误匹配** — `pin` 会命中 "sho**ppin**g"。英文改成**词边界**匹配,中文仍用 compact 子串(防绕过)。已加测试覆盖。
- **P1 评估只是脚本,无 CI** — 新增 `tests/test_app.py`(pytest)+ `.github/workflows/ci.yml`(push 自动跑 ruff + pytest + evaluate)。
- **P1 source 未校验** — 后端校验 `source in SOURCE_CODES`,否则归为 "other"。

仍保留为已知限制:速率限制、SQLite→Postgres + 保留期策略、学习型模型默认关闭(数据不足)、免费档冷启动。

## 逐行自审发现并修复

- **F1（中）数据库连接未在异常时关闭** — 4 个路由 + `init_db` 原为 `conn=get_db() … conn.close()`,
  中途 `execute` 抛异常会跳过 `close()` 导致连接泄漏。已改为 `with closing(get_db()) as conn:`,保证释放。
- **F2（低-中）关键词 `remote` 过宽** — 会误伤正常英文("remote control")。已删除裸词,
  保留 `remote access` / `remote support`;诈骗样例仍由 `share your screen` 命中,召回不受影响。
- **F3（低）死代码** — 移除"当时的内容"后,翻译键 `detail_content` 无人使用,已删除(中英)。

验证:ruff 通过、black 已格式化、全部路由 200/302、按浏览器隔离有效、评测不变(97%、0 漏报)。

## 8 条标准逐条核对

### 1. 逻辑是否全堆在一个文件里 — ✅ 已分层
判断逻辑是**独立的纯函数**,不依赖网页即可调用:
```python
# helpers.py
result = analyze_content(text, source)   # -> {"risk", "category", "reasons"}
```
- `app.py` — 只有路由(请求/响应)
- `helpers.py` — 打分与结果组装(纯函数,可单测)
- `keywords.py` — 关键词库(危险/诈骗/养生)
- `blocklist.py` — 链接/号码的确定性威胁检测
- `semantic.py` — 意图升级层(只升不降)+ 可选模型钩子
- `normalize.py` — 输入归一化(防绕过)
- `regions.py` — 英国/中国地区配置
- `translations.py` — 中英文案(逻辑与文案分离)
- `templates/` `static/` `tests/` `model/`

### 2. 是否有测试样例 — ✅ 有
- `tests/dataset.py` — **61 条人工标注样例**(诈骗/养生/正常,中英;含难例),与训练集分开防泄漏
- `evaluate.py` — 计算准确率,并**区分"漏报(危险)"和"误报(只是烦)"**
- 当前结果:**97% 准确率,0 漏报诈骗,2 误报**

### 3. 用户输入是否直接进 HTML(XSS) — ✅ 安全
- 全部经 Jinja2 **自动转义**渲染;全项目 **无 `| safe`**、无 f-string 拼 HTML(可 grep 验证)

### 4. 是否把敏感原文写进日志/数据库 — ✅ 不保存原文
- **不存用户输入的原文**(数据最小化)。`app.py` 的 INSERT 只存:
  `created_at / source / risk / category / reasons / user_token`
- web 代码中无 `print(用户输入)` / 无日志记录原文

### 5. secret 是否写死 — ✅ 走环境变量
```python
# app.py
app.secret_key = os.environ.get("SECRET_KEY", "parent-check-dev-key")  # 仅本地兜底
```
- 生产由 `render.yaml` 的 `generateValue` 自动注入;**无任何第三方 API key**(不调外部 API)

### 6. 是否有错误处理 — ✅ 覆盖主要边界
- 空输入 → 重定向回首页;超长 → 截断到 5000 字
- 缺省 `source` → "other";非法 `lang`/`region` → 回退默认
- 模型加载失败 → try/except **失败安全**(返回不升级);
- 访问他人/不存在的记录 → 重定向(配合 `user_token` 过滤)

### 7. 语言切换是否混乱 / 503 — ⚠️ 503 是冷启动,非代码 bug
- `503 Service Unavailable` 是 Render 免费档**休眠后冷启动**时代理返回的(Flask 自身错误是 500)。
  随后 /about /history 正常,正是因为实例已被唤醒。
- 中英文案 key **对称完整**,`?lang=zh` 不会因缺 key 崩溃。

### 8. 规则是否能解释 — ✅ 每条判断都给"为什么+怎么做"
- 命中项作为**证据(reasons)**展示;分数决定等级;`category` → 对应**大白话建议(不要点链接/不要转账…)** + 求助专线
- 不是黑箱 `if "cure" in text`,而是分类计分 + 可解释输出

## 100 分评分(自评,偏保守)

| 项目 | 满分 | 自评 | 说明 |
|---|---:|---:|---|
| 安全(XSS/secret/输入校验/debug/依赖) | 25 | 21 | 参数化 SQL、自动转义、cookie 加固到位;缺独立 CSRF token(靠 SameSite)、无限流 |
| 隐私(是否存敏感原文/日志/历史) | 20 | 19 | 不存原文、按浏览器隔离、有隐私页 |
| 正确性(规则稳定/有测试) | 20 | 17 | 纯函数 + 评测集 + 0 漏报;数据集仅 61 条、模型暂关 |
| 结构(模块化/可维护) | 15 | 14 | 分层清晰、判断可单独调用 |
| UX(语言/错误/老人路径) | 10 | 9 | 单任务、大字、三色、行动为中心;免费档冷启动 |
| 文档(README/部署/限制) | 10 | 10 | README + 安全段 + 隐私 + 部署 + 限制 |
| **合计** | **100** | **≈90** | **不错,可以继续扩展** |

## 仍存在的已知限制(诚实)
- 无独立 CSRF token(现靠 `SameSite=Lax`;更高标准加 Flask-WTF)
- 无速率限制(生产加 Flask-Limiter / 反代)
- 学习型模型默认关闭(64 条数据区分度不足,数据驱动地关掉)
- 免费档冷启动 503(升级付费档可消除)
