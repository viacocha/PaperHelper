from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.shared import Pt

from app.models.schemas import ReviewResult


def generate_report(review: ReviewResult, output_path: Path) -> Path:
    document = Document()
    _add_title(document, f"{review.filename} 批改报告")
    _add_heading(document, "一、批改总评")
    document.add_paragraph(f"总分：{review.total_score} / 75")
    document.add_paragraph(f"通过参考线：{review.pass_score}")
    document.add_paragraph(f"通过风险判断：{_label(review.pass_probability)}")
    document.add_paragraph(f"匹配题型：{review.standard.standard_name}（{review.standard.category}，置信度 {review.standard.confidence}）")
    document.add_paragraph(f"总体结论：{review.summary}")

    _add_heading(document, "二、分项评分")
    for dimension in review.dimensions:
        document.add_paragraph(
            f"{dimension.name}：{dimension.score} / {dimension.max_score}。{dimension.summary}",
            style="List Bullet",
        )

    _add_heading(document, "三、题型评分卡")
    for item in review.topic_scorecard:
        document.add_paragraph(
            f"[{item.status.upper()}] {item.title}：{item.score} / {item.max_score}。{item.summary}",
            style="List Bullet",
        )

    _add_heading(document, "四、主要问题与修改建议")
    if review.issues:
        for item in review.issues:
            paragraph = document.add_paragraph(style="List Bullet")
            paragraph.add_run(f"[{item.action_priority.upper()}/{item.severity.upper()}] {item.title}：").bold = True
            paragraph.add_run(item.details + " ")
            paragraph.add_run("建议：").bold = True
            paragraph.add_run(item.suggestion)
    else:
        document.add_paragraph("未检测到明显高风险问题，但仍建议结合题目子问逐项复核。")

    _add_heading(document, "五、修改优先级队列")
    _add_issue_group(document, "必须补写", review.must_fix)
    _add_issue_group(document, "建议补强", review.should_fix)
    _add_issue_group(document, "可优化项", review.could_improve)

    _add_heading(document, "六、题型模板建议")
    for item in review.revision_templates:
        document.add_paragraph(item.title).runs[0].bold = True
        document.add_paragraph("用途：" + item.purpose)
        document.add_paragraph("适用场景：" + item.when_to_use)
        document.add_paragraph("补写结构：" + "；".join(item.outline))
        document.add_paragraph("示例写法：" + item.sample)

    _add_heading(document, "七、逐段建议")
    for paragraph_review in review.paragraph_reviews:
        document.add_paragraph(f"第 {paragraph_review.index} 段：{paragraph_review.excerpt}", style="List Bullet")
        if paragraph_review.strengths:
            document.add_paragraph("优点：" + "；".join(paragraph_review.strengths))
        if paragraph_review.issues:
            document.add_paragraph("问题：" + "；".join(paragraph_review.issues))
        if paragraph_review.suggestions:
            document.add_paragraph("建议：" + "；".join(paragraph_review.suggestions))

    _add_heading(document, "八、修改顺序建议")
    priorities = [
        "先补齐题目要求的子问、专属产物和关键过程。",
        "再强化项目经理视角、问题应对和结果成效。",
        "最后压缩空泛理论，润色衔接与专业术语表达。",
    ]
    for item in priorities:
        document.add_paragraph(item, style="List Number")

    document.save(output_path)
    return output_path


def _add_title(document: Document, text: str) -> None:
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text)
    run.bold = True
    run.font.size = Pt(18)


def _add_heading(document: Document, text: str) -> None:
    document.add_paragraph().add_run(text).bold = True


def _add_issue_group(document: Document, title: str, items) -> None:
    document.add_paragraph(title).runs[0].bold = True
    if not items:
        document.add_paragraph("当前无对应问题。")
        return
    for item in items:
        document.add_paragraph(f"{item.title}：{item.suggestion}", style="List Bullet")


def _label(value: str) -> str:
    return {
        "high": "较高通过概率",
        "medium": "接近通过，仍需修改",
        "low": "当前通过风险高",
    }[value]
