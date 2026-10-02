from __future__ import annotations

import difflib
import html
from pathlib import Path

from experiments.iteration7.runtime import read
from experiments.validation.style_feedback.evaluate import LABELS, ROOT


def escaped(value: object) -> str:
    return html.escape(str(value))


def changes(before: str, after: str) -> tuple[str, str]:
    left, right = [], []
    for op, i, j, x, y in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
        a, b = escaped(before[i:j]), escaped(after[x:y])
        left.append(a if op == "equal" else f"<mark>{a}</mark>" if a else "")
        right.append(b if op == "equal" else f"<mark>{b}</mark>" if b else "")
    return "".join(left), "".join(right)


def table(headers: list[str], rows: list[list]) -> str:
    return "<div class='table-wrap'><table><thead><tr>" + "".join(f"<th>{escaped(x)}</th>" for x in headers) + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{escaped(x)}</td>" for x in row) + "</tr>" for row in rows) + "</tbody></table></div>"


def main() -> None:
    human = read(ROOT / "human_summary.json")
    cards = read(ROOT / "close_reading/comparison_cards.json")["cards"]
    sections = ["<h1>从您的选择，看译文还差在哪里</h1>",
        "<p class='lead'>当前偏好最多的是「中文局部编辑＋英文核查」。值得继续打磨的，是动作组织和随口叙述的语气。</p>",
        "<p>现有局部编辑只修明确不地道的措辞，并要求自然句保持不变。这会放过「通顺，但不像作者」的表达。下一轮适合允许保留事实的局部重组，把风格偏好与错词修复分开记录。</p>",
        "<p>中间结果显示：「询问般望向」被中文编辑扩成「用询问的目光望向」；山上与盾牌两处的结构则继承自直接译写，编辑没有调整。另有漂浮描写被编辑简化后，又在英文核查中改回字面措辞。需要同时检查编辑的方向和核查对语义等价的判断。</p>",
        "<p>这是本次分析的固定快照。建议改写供诊断，还没有经过新的盲测。</p>",
        "<nav><a href='#preferences'>您的选择</a><a href='#ratings'>48 组机器对照</a><a href='#cards'>11 张局部对照</a><a href='http://127.0.0.1:8767/'>继续原来的评分</a></nav>",
        "<section id='preferences'><h2>您的选择</h2>",
        table(["方法", "单选次数"], [[LABELS[m], int(v)] for m, v in sorted(human["preference_credits"].items(), key=lambda x: -x[1])]),
        "<p>21 组选择了一个候选，1 组「都不理想」，1 组只有「AC差不多」的备注。备注未擅自转成票；未填写的组不计入。每本书等权查看，局部编辑仍暂时领先，但差距还不足以确立稳定胜出。</p>",
        table(["书", "直接", "正例", "纠错对照", "局部编辑", "都不理想"], [
            [title, *[int(b["credits"][m]) for m in LABELS], b["none"]] for title, b in human["by_book"].items()]),
        "<p>各书目前只有 3–4 组有效回答，不能据此确定适合某种题材的最佳方法。</p></section>",
        "<section id='ratings'><h2>48 组机器对照</h2>"]
    if (ROOT / "analysis.json").exists():
        analysis = read(ROOT / "analysis.json")
        sections.append(table(["方法", "评审一 / 5", "评审二 / 5", "合看 / 5"], [
            [LABELS[m], f"{analysis['by_reviewer']['sol']['scores'][m]['book_equal_mean']:.2f}",
             f"{analysis['by_reviewer']['terra']['scores'][m]['book_equal_mean']:.2f}",
             f"{analysis['all']['scores'][m]['book_equal_mean']:.2f}"] for m in LABELS]))
        sections.append("<p>评分看动作与分句、叙述语气、对白节奏、解释是否过度。评审看到匿名候选和中英文，未看到您的投票；规则要求排除术语与英文版本增删，但人工抽查仍发现执行不稳。六本书等权。分数是探索性的判断均值，不是风格还原百分比，也不是已验证的量表。</p>")
        sections.append("<p>机器排名只表示相对顺序，不代表某版已经值得采用。您在第 018 组选择了「都不理想」，这个判断不能被机器排出的第一名替代。抽查还发现评审有时把英文原有的强烈语气当成中文译文加重，因此当前分数不能直接用作自动选稿标准。</p>")
        agreement_rows = []
        for reviewer, label in (("sol", "评审一"), ("terra", "评审二")):
            a = analysis["by_reviewer"][reviewer]["human_agreement"]
            agreement_rows.append([label, a["n"], len(a["same_single_winner"]), len(a["human_choice_in_model_tied_top"]), len(a["human_choice_not_top"])])
        sections.append(table(["与您对照", "已单选组数", "唯一首选相同", "您的首选在并列第一中", "首选不同"], agreement_rows))
        pair_rows = []
        for reviewer, label in (("sol", "评审一"), ("terra", "评审二")):
            a = analysis["by_reviewer"][reviewer]["pairwise"]["direct_vs_edited"]
            pair_rows.append([label, a["a_closer"], a["tie"], a["b_closer"]])
        sections.append(table(["直接译写 vs 局部编辑", "直接译写更近", "并列", "局部编辑更近"], pair_rows))
        sections.append("<p><b>这轮结果：</b>直接译写与局部编辑基本处在同一档，两位评审均在 48 组中的 41 组判二者并列。机器没有稳定复现您的完整偏好，当前更适合用来发现需复查的片段。下一轮可把局部编辑作为改良起点，同时保留直接译写作对照。</p>")
        sections.append(f"<p>共 {analysis['unit_count']} 条局部比较说明；其中 {analysis['units_with_quote_or_coverage_problems']} 条有引用或覆盖问题，不能直接采入例库。自动检查只能验证引文来自哪里，论断仍需人工复核。两位评审的模型和候选顺序同时不同，不能把分歧单独归因于顺序。</p>")
    else:
        sections.append("<p>评审仍在运行；完成并复核后显示结果。</p>")
    sections.extend(["</section><section id='cards'><h2>11 张局部对照</h2>",
        "<p>一行四项：作者原文、直接译写、当前局部编辑、建议修改。<mark>黄色</mark>仅标出局部编辑与建议之间的文字变化，不代表错误计数。英文未展示。部分直接译写保留了更长的上下文。</p>",
        "<label for='book'>按书筛选：</label><select id='book'><option value=''>全部六本</option>" + "".join(f"<option>{escaped(b)}</option>" for b in dict.fromkeys(c["book"] for c in cards)) + "</select>"])
    for card in cards:
        proposed = card["suggested_English_faithful_revision"]
        before, after = changes(card["edited_quote"], proposed) if proposed else (escaped(card["edited_quote"]), "<em>版本差异尚不明确，不作为确定纠错。</em>")
        status = {"proposed_local_edit": "待验证的局部建议", "scene_specific_candidate": "针对本场景的可选改法", "positive_control_keep_existing": "已有合理改进，保留", "ambiguous_rejected_as_training_correction": "不收为确定纠错"}[card["status"]]
        texts = [escaped(card["author_quote"]), escaped(card["four_method_context"]["direct"]["quote"]), before, after]
        sections.append(f"<article id='{escaped(card['id'])}' data-book='{escaped(card['book'])}'><h3>{escaped(card['sample_id'].replace('balanced_', '第 '))} 组 · {escaped(card['book'])} · {escaped(card['category'])}</h3><p class='badge'>{status}</p><div class='comparison'>" + "".join(f"<div class='version'><h4>{label}</h4><p>{text}</p></div>" for label, text in zip(("作者原文", "直接译写", "当前局部编辑", "建议修改"), texts)) + f"</div><p><b>为什么：</b>{escaped(card['why'])}</p><p class='boundary'><b>内容边界：</b>{escaped(card['edition_boundary'])}</p></article>")
    sections.append("</section><footer>这些例子已经用于诊断与设计，后续验证应另抽新段落。可以学合并动作、保留随口语气、少解释已明白的意图；不能按字数越短越好，也不能把作者中文中的额外事实补回英文译文。</footer>")
    css = """body{margin:0;background:#f7f5ef;color:#202c30;font:16px/1.75 system-ui,-apple-system,sans-serif}main{max-width:1560px;margin:auto;padding:38px 32px}h1{font-size:30px;line-height:1.35}h2{font-size:23px;margin-top:0}h3{font-size:19px}h4{margin:0 0 12px;color:#506065;font:600 14px system-ui}p{margin:10px 0}.lead{font-size:20px}nav{display:flex;gap:24px;flex-wrap:wrap;padding:20px 0}a{color:#17675d}section{margin:28px 0;padding:26px;background:#fff;border:1px solid #dcded9;border-radius:12px}table{border-collapse:collapse;width:100%;max-width:950px}th,td{text-align:left;border-bottom:1px solid #dfe4df;padding:10px 14px}th{background:#edf3ef}.table-wrap{overflow-x:auto}.comparison{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0}.version{padding:18px;border:1px solid #dce3dd;margin-right:-1px;background:#fdfdfa}.version p{font:18px/1.9 ui-serif,'Songti SC',serif;white-space:pre-wrap;overflow-wrap:anywhere}article{margin:30px 0;border-top:1px solid #dce3dd;padding-top:12px}mark{background:#ffe9a6;color:inherit;border-radius:2px;padding:1px 0}.badge{display:inline-block;border-radius:20px;background:#eef3ef;padding:2px 12px;font-size:13px}.boundary{color:#515e61;font-size:14px}select{padding:8px;font-size:16px;border:1px solid #adbcb4;border-radius:6px}footer{color:#515e61;padding:12px 4px 50px}section{scroll-margin-top:12px}@media(max-width:900px){main{padding:20px 12px}section{padding:16px}.comparison{overflow-x:auto;grid-template-columns:repeat(4,260px)}}"""
    script = "document.getElementById('book').addEventListener('change', e => { document.querySelectorAll('article').forEach(a => a.hidden = !!e.target.value && a.dataset.book !== e.target.value); });"
    output = "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>译文风格诊断 · 48 组反馈与局部对照</title><style>" + css + "</style></head><body><main>" + "".join(sections) + "</main><script>" + script + "</script></body></html>"
    (ROOT / "review.html").write_text(output)
    (ROOT / "public").mkdir(exist_ok=True)
    (ROOT / "public/index.html").write_text(output)
    print(ROOT / "review.html")


if __name__ == "__main__":
    main()
