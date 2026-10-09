# 用晋江校对已有版本

`book-proofread` 以已有版本为准，利用已登录晋江账号能读取的章节补空行、
核验疑似坏字、补齐缺失作话。Notion 作品页、EPUB 和共享 `source.json` 都可作为原书。
版本不同、匹配含糊或锁章时保留原书并记录原因。

## 使用

```bash
uv run book-proofread plan --notion '<作品页 URL>' --jinjiang '<晋江 URL 或 novelid>' \
  --run-dir generated/proofread/BOOK_DATE
uv run book-proofread review --run-dir generated/proofread/BOOK_DATE
uv run book-proofread apply --run-dir generated/proofread/BOOK_DATE
```

Notion 正文需要进程环境中的 `NOTION_API_TOKEN`，目录使用项目已有 MCP 登录。
如凭据放在本地 `.env`，可显式使用 `uv run --env-file .env ...` 提供环境；命令本身不读取该文件。
晋江通过 `arc-cdp run browser-harness` 使用现有 Arc 登录，不自动订阅或购买。
登录失效、购买页、锁章和加载失败分别报告；之前失败的章节在续跑时重新尝试。
需要登录时在浏览器完成登录，再运行同一命令。

`--jinjiang` 省略时使用原书的来源属性；来源不是晋江时需指定已确认的参考作品。
本地输入用 `--input original.epub` 或 `--input source.json` 代替 `--notion`。
本地结果是 run 目录的 `candidate.json`，源 EPUB 不会被覆盖；需要 EPUB/TXT 时再选对应输出。

`plan` 只读远端并生成候选。`review` 仅在有疑似坏字、作话图片说明或部分作话缺失候选时调用
只读 Codex CLI，也可由当前 Codex 会话按同一格式填写决策。`apply` 执行已确认范围内的
排版修改与高置信度、证据齐全的正文修复，并回读核验。

## 比对原则

- **空行**：全书及关联番外按内容索引定位，利用分隔位置两侧的唯一上下文。
  短段落借用相邻段落补足上下文。只增加缺失空行，保留原有额外留白、分割线和版本增补。
  空行落在原书同一段内部、重复文本或其他结构中时列入待审，不自动拆段。
- **空格**：原书出现汉字间断词空格，且唯一对应的参考段落能确认没有该空格时修复。
  不用晋江的标点和随机空格覆盖原书排版。
- **坏字**：先找原书的乱码、替代字符、缺字标记、转义残留，再找参考候选。
  普通版本差异不自动当作错字。Codex 只能提交短小、唯一的替换，替换文字及两侧上下文
  必须出现在可读参考里。找不到、多个匹配或版本差距大时保留原文。
- **字体混淆**：晋江的私用区字符可作为排版匹配中的未知字，不作为修复正文的证据。
- **疑似问题线索**：`plan --flagged findings.json` 可接收
  `[{"member":"chapter-0003","index":5,"reason":"这个词疑似错误"}]`；索引从 0 开始，
  member 和段落来自 `original/source.json`。这样可核验正常汉字组成的疑似错词。

## 作者有话说

读取 `#note_str` 的原始作话内容，避开依赖滚动加载的展示层。
根据章节结尾文字定位真实 Notion 页面，已有、部分已有、目标不明分别记录，避免重复添加。
保留现有作话的版本差异；部分缺失时，Codex 可在已有作话中选择插入位置，
只补参考里明确存在且原书尚未包含的整行。脚本限制来源行、顺序及目标位置，
不能用此决策改写或删除已有文字。位置或意义不可靠时保留待审。

缺失作话用原生分割线、独立的 `作者有话说：` 和纯文本段落补在对应章末；
原书已有的作话也检查分隔：标题前缺少分割线时补一条，已有分割线（包括隔着空行）不重复添加。
这项检查不依赖作话是否需要补文字，保留现有标题和段落结构。
新增和已有作话的可见文字都使用[共享规范化规则](normalization.md)，包括 `10月` → `10 月`、
`IPHONE` → `iPhone` 等；保留链接、样式和块身份。已有作话只提交有差异的文字补丁。
遇到分割线、结束标记或附加版本标题时停止作话范围，避免处理后面的另一版正文。
遵循之前确认的作话规则：

- 只保留有效文字；图片和网站的霸王票、营养液组件不导入。
- 超链接保留有效文字标签，不附加网址；单独的“点我”等空入口略过。
- 依赖已移除/失效图片的说明先交 Codex 判断，只有确认无独立文字价值的整句才删除。
  一句混有重要内容、无法安全整句删除时保留待审。
- 清理后没有有效文字，不添加作话标题或分割线。

这是晋江补全作话的专用规则，不删除现有正文里的图片说明、链接或普通感谢文字。

## 报告与恢复

一个 run 绑定原书快照、参考内容和校对规则。主要文件：

| 文件 | 内容 |
| --- | --- |
| `original/source.json`、`original/evidence.json` | 原书正文、Notion 页面与原块身份 |
| `reference/source.json`、`reference/evidence.json` | 参考正文、访问结果、作话及原始 HTML |
| `plan.json`、`report.json` | 每处匹配证据、待审位置与汇总 |
| `decisions.json`、`note-decisions.json`、`completion-decisions.json` | 与本次 plan 指纹绑定的正文、作话清理、部分补全决策 |
| `candidate.json`、`result.json` | 候选版本与实际执行核验结果 |

同一目录用于续跑；新的独立校对用新目录，重新读取当前 Notion 内容。
Notion 恢复请求和写入日志另存于 `state/notion/proofread/<work>/<fingerprint>/`。
每次写入前持久化请求，响应身份校验后保存进度，按小批及整页回读。
响应丢失时重新观察远端，识别已成功的那一步后继续，不重复插入。
发现正文、章节身份、标题或目录变化时停下，保留日志供检查。

最终验收包括原有块身份与内容、新增空行/作话、章节标题和正文/番外手动顺序。
`result.json` 的成功表示已执行的修改回读通过，未匹配位置仍需按 `plan.json` 说明保留或另行处理。
命令不会发布到 Bookshelf，也不会修改 Notion 的发布属性。

## 实现边界

晋江浏览器采集在 `crawler/providers/jjwxc/reference.py`；匹配与决策约束在
`content/proofread.py`，作话纯文本准备在 `content/author_notes.py`；
`workflows/proofread.py` 组织阶段，`notion/proofread.py` 负责现有页面的精确增量编辑和回读。
共享 `notion-books` 解码及验证正文；增量适配器只插入空段/纯文本作话或修改现有文本对象，
保留原生样式、链接及未修改块 ID。嵌套结构和复杂富文本替换使用已有完整稿件更新流程。
