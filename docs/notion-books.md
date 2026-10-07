# 爬取后的输出：EPUB、Notion 草稿与 TXT

新增书籍时，先根据用户要求确定输出目的地；未指定时询问。可选择本地 EPUB、
[Notion 草稿](https://app.notion.com/p/3deca693996b810c8774f3658c89a423)、
TXT 或任意组合。爬取一次后写入所选目的地；单独选择本地文件时不连接 Notion。
Notion 输出完成于草稿写入和回读验证；发布操作不属于上传流程。

## 安装共享依赖

先安装 `uv`、`mise` 和 GitHub CLI（`gh`）。`notion-books` 是必装依赖，
即使仅输出本地 EPUB，也需要能访问其私有 GitHub 仓库的账号。
依赖固定到版本标签，`uv.lock` 记录确切提交；无需相邻 checkout。

**当前开发状态：** 新链接/脚注 codec 需要 `notion-books` 0.5.0；本项目仍锁定
0.4.1，发布共享库和升级锁文件按本次约定留待后续。因此，当前新增 Notion 功能及
完整测试须使用下面的本地 0.5.0 覆盖；锁定安装成功或 CLI 帮助可用不代表这些功能
已可运行。发布后再按正式升级步骤验证锁定环境。

首次安装在本项目根目录依次运行：

```bash
gh auth login
gh auth setup-git
mise trust
mise install
mise exec -- uv sync --locked
mise exec -- uv run --locked book-notion --help
```

最后一条命令显示帮助即表示依赖安装和 CLI 加载成功，不会连接 Notion。
Git 报权限错误时，确认 `gh` 登录的账号拥有 `notion-books` 仓库访问权限，
再运行 `gh auth setup-git` 并重试同步。Go 编译器缺失时，运行 `mise install`，
并通过 `mise exec --` 执行同步。Go 核心在安装时编译进 Python 包；运行时无需 Go 或新增服务。

测试共享库的本地修改时，使用临时覆盖，不修改依赖配置或锁文件：

```bash
mise exec -- uv run --no-cache --with /absolute/path/to/notion-books python -m unittest discover -s tests -p 'test_*.py'
```

正式升级时选择已发布的不可变标签，同步修改本项目的版本号和 Git 标签，运行
`mise exec -- uv lock`。移除本地覆盖后，使用锁定版本运行本项目测试。

## 使用

```bash
uv run book-notion login
uv run book-notion upload --source generated/book_import/source.json
uv run book-notion verify --state generated/notion_cms_sources/HASH/import.json
uv run book-ingest "作品URL" --mode notion
uv run book-ingest "作品URL" --mode epub -o books/作者/书名.epub
uv run book-ingest "作品URL" --mode epub --mode notion --mode txt
```

`book-ingest --mode` 可重复指定 EPUB、Notion、TXT。未指定模式时，
`-o` 选择 EPUB，`--txt-output` 选择 TXT；都未指定时 CLI 报错。
训练导出另加 `--dataset-root research/datasets`，普通 TXT 不触发分类。
组合输出逐项执行，失败时核对已有文件及检查点，再恢复未完成的输出。
翻译流程使用同一个内容 JSON 和 EPUB writer。

正文、目录、作者关联和书籍属性通过独立 MCP 客户端读写。
OAuth 凭据保存在用户私有状态目录，可刷新。普通正文及外部链接只需 MCP；
含脚注或章节内部链接时，还需已登录 Notion 的 Arc 及可用的
`arc-cdp run browser-harness` 适配器，用于读取原生 block ID 并验证链接。
`book-notion logout` 删除本地 token，重新授权使用 `book-notion login`。

### 封面

封面有两条路径：现有登录浏览器上传，或可选的官方 File Upload API。
只有官方 API 路径需要进程环境里的 `NOTION_API_TOKEN`；正文 MCP 不需要它。
没有该 token 时，正文先完成，检查点旁生成 `cover-browser.json`，按
[固定浏览器流程](../.agents/skills/book-management/references/notion-cover.md)
复用已登录的 Arc，然后运行 `book-notion verify-cover --state ...`。
不需要为了导入一本书额外配置 API token。

PNG/JPEG 最大 10 MiB、2500 万像素。封面不可读取或回读字节不一致时保留
待处理状态，不重复创建正文。脚本不读取 `.env`，不保存 token 或签名下载 URL。
公开 URL 封面仍可用 `--cover-url` 经 MCP 附加。

本地 EPUB 嵌入封面图片及 cover metadata，供书库显示缩略图；
不生成 `cover.xhtml` 或 `cover.html`，也不加入封面阅读页。

## Notion 存储

目录 ID 配置在 `book_specs/notion/config.json`。新书使用作品库默认模板创建：

- 每本书拥有独立的「正文」数据库。`章节`是页面标题，`所属标题`是可选的上级目录标题。
- 读取未筛选、未分组、无属性排序的「正文」手动视图；「待发布」视图不决定目录。
- 上传按源目录建立行顺序，完成后核对实际手动顺序。相同上级标题只有连续出现时才归为一组。
- Notion 上传支持章节加一层上级标题；更深的目录在上传前报错，本地 EPUB 路径仍支持原目录树。
- 简介、尾声、后记和番外卷中的章节都是正文行。简介元数据与可阅读的简介章节分别保存。
- 独立番外存放于共享库，通过「涉及作品」关联书籍。书页的番外视图只筛选当前作品，并保留手动顺序。

作品属性写入 `作品`、`作者` relation、`书籍分类` multi-select、`系列` select、
`系列序号` number、`语言` select、`简介`、`来源` URL、`出版日期` date。
可由源提供多个作者；不会自行拆分笔名。上传器只补齐必要的 select 选项，保留已有值。
上传只写上述内容属性，保留目标库中的其他属性和按钮。

## 续传与冲突

检查点位于 `generated/notion_cms_sources/<来源摘要>/import.json`，按目标目录及来源标识隔离。
保存每次创建返回的 ID，回读正文和属性后标记已验证；上传完成后以 Notion 中的编辑为准。

```bash
uv run book-notion resume --state generated/notion_cms_sources/<来源摘要>/import.json
```

- 创建请求结果不确定：根据页面内容核对对应 ID，再修复检查点；不要盲目重建。
- 同名书已存在：核对书籍身份及原检查点，不覆盖已有书籍。
- 新爬取与检查点不同：比较本地来源和 Notion 编辑，确认合并后再继续。
- 疑似重复番外：上传前暂停，在检查点同目录生成 `extra-review.md`。按报告选择
  复用已有正文或新建，再续传；操作与判定范围见[共享番外](fanwai-notion.md)。
- 实际顺序不同：在对应手动视图整理为源目录顺序，再续传；不会添加数字排序列。
- `cover_pending` 表示封面附加结果不确定。运行 `book-notion verify-cover --state ...`
  核对当前原生图片字节后完成恢复；不要手工把 `cover_uploaded` 改成 true。

不同目标库之间不能复用导入检查点。

本地 EPUB/TXT 的内容准备、卷标签颜色、公开 URL 封面和
模板恢复可用 `book-notion recover-template --state ...`，然后 resume 原检查点。
`book-notion upload` 接收已审查的共享 source.json；无需每次编写上传脚本。
新建作者时，通过晋江作者检索查找唯一匹配的主页；找到后在同一次创建中
填写「晋江主页」URL，并回读验证。检索失败会中止创建，明确无匹配才留空。
已存在的作者直接复用；导入检查点保留新建作者的主页，供恢复和验证使用。
已上传内容在 Notion 中编辑；重新抓取本地版则选择 `--mode epub`。

## 排版约定

`src/content/` 负责内容相关的清理和格式识别；共享依赖 `notion-books` 负责
Notion schema、格式编解码和读写。`src/notion/cms.py` 与 `upload.py`
负责导入决策、身份匹配、检查点和流程；认证与封面 HTTP 客户端也留在本项目。
`src/workflows/ingest.py` 决定输出目的地；本地输出调用 `src/epub/writer.py`，不经 Notion。
模块边界见[架构说明](architecture.md)。

正文和番外使用同一组块和渲染规则。保持现有 CSS：正文行高 `1.7`、段间距 `0.3em`，
正文内 H3 为 `1.1em`。标题级别和对齐独立；居中用三列中间列存内容、两侧留空，
右对齐用最右列。粗斜体、下划线、删除线、段内换行、空段、引用和分隔线保持语义。
渲染只解释排版属性，不根据「全文完」或其他具体文字推断格式。

平铺编号条目保存为带字面量 `1. `、`2. ` 前缀的 paragraph。MCP 回读会省略
句点转义，共享 codec 按此约定保留编号、全文和段落边界；嵌套列表仍拒绝读取。
卷名、章内小标题及空段清理遵循[内容规则](normalization.md)，不在 writer 重做清洗。

本地替换先生成、验证候选 EPUB，再校验原文件哈希、备份和原子安装。
检查点、书籍内容和生成的 EPUB 不提交 Git。

## Live upload validation

The [crawler live test](../tests/LIVE_NOTION.md) runs a synthetic crawl result
through real Notion upload, readback and checkpoint resume. The test ends after
verifying the uploaded content and preserved page identities.

## 链接与脚注的往返约定

命名链接保留文字、样式和目标 URL。脚注采用明确配对格式：正文链接 `[1]`，
章末普通段落 `[1] 内容 ↩1`，其中 `↩1` 是返回正文的链接。多次引用的回链
使用 `↩1.1`、`↩1.2`。编号必须对应；共享 codec 不依赖导入 checkpoint 即可
恢复脚注、锚点和本地链接。原生 quote block 则恢复为 EPUB blockquote。

上传先写入并回读正文，再通过已登录 Arc 的 `arc-cdp run browser-harness`
读取实际 block ID、绑定双向链接，并再次检查全文和目标 ID。实现集中于
`src/notion/references.py`，无需 API token。浏览器只使用自己的任务页签。
未完成的绑定留在 checkpoint，不能当作完整上传。

同书章节及关联独立番外的首页链接写为 Notion 页面 URL，导出时根据本书内容目录
恢复为本地链接；内容身份不包含 Notion 页面 ID。
普通内部链接仅支持章节首页；任意段落锚点（包括同章）在写入前拒绝，不能降级为
章节首页。配对脚注及回链使用各自的段落目标，不受这个普通链接限制。
Notion 的富文本 codec 属于 `notion-books`；Bookshelf CMS 的 EPUB 渲染器消费
同一结构。Bookshelf CMS 需另外升级对应共享库及渲染器后才能发布新版脚注 EPUB；
本项目导入完成不代表 CMS 已升级或部署。更换存储格式须验证两个消费者。
