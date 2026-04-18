from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZIP_DEFLATED, ZipFile

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from lxml import etree

from app.models.schemas import CompareResult, ReviewResult

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
COMMENTS_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
COMMENTS_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"


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


def generate_annotated_report(source_path: Path, review: ReviewResult, output_path: Path) -> Path:
    document = Document(source_path)
    _remove_existing_comment_markers(document)
    non_empty_paragraphs = [paragraph for paragraph in document.paragraphs if paragraph.text.strip()]
    comment_texts: list[str] = []

    title_paragraph = non_empty_paragraphs[0] if non_empty_paragraphs else document.add_paragraph(review.filename)
    _add_word_comment_marker(title_paragraph, 0)
    comment_texts.append(_overall_comment_text(review))

    for paragraph_review in review.paragraph_reviews:
        paragraph_index = paragraph_review.index - 1
        if paragraph_index >= len(non_empty_paragraphs):
            continue
        comment_text = _paragraph_comment_text(paragraph_review)
        if not comment_text:
            continue
        _add_word_comment_marker(non_empty_paragraphs[paragraph_index], len(comment_texts))
        comment_texts.append(comment_text)

    with NamedTemporaryFile(suffix=".docx", delete=False) as temp_file:
        temp_path = Path(temp_file.name)
    document.save(temp_path)

    _patch_comments_part(temp_path, output_path, comment_texts)
    temp_path.unlink(missing_ok=True)
    return output_path


def generate_compare_report(comparison: CompareResult, output_path: Path) -> Path:
    document = Document()
    _add_title(document, f"{comparison.revised.filename} 二次批改对比报告")

    _add_heading(document, "一、对比总评")
    document.add_paragraph(f"修改前总分：{comparison.original.total_score} / 75")
    document.add_paragraph(f"修改后总分：{comparison.revised.total_score} / 75")
    document.add_paragraph(f"分数变化：{comparison.score_delta:+.1f}")
    document.add_paragraph("通过风险变化：" + ("已变化" if comparison.pass_probability_changed else "未变化"))
    document.add_paragraph("总体结论：" + comparison.summary)

    _add_heading(document, "二、已修复问题")
    _add_issue_group(document, "已修复", comparison.fixed_issues)

    _add_heading(document, "三、仍未解决问题")
    _add_issue_group(document, "仍未解决", comparison.remaining_issues)

    _add_heading(document, "四、新增问题")
    _add_issue_group(document, "新增", comparison.new_issues)

    _add_heading(document, "五、下一轮修改建议")
    if comparison.remaining_issues:
        document.add_paragraph("优先处理仍未解决的问题，尤其是必须补写项和题目专属产物缺失。")
    if comparison.new_issues:
        document.add_paragraph("检查新增问题是否由压缩、改写或结构调整导致，避免修复旧问题时引入新缺陷。")
    if not comparison.remaining_issues and not comparison.new_issues:
        document.add_paragraph("当前未发现旧问题残留或新增问题，可进入表达润色和考场默写训练阶段。")

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


def _add_word_comment_marker(paragraph, comment_id: int) -> str:  # type: ignore[no-untyped-def]
    if not paragraph.runs:
        paragraph.add_run(" ")

    start = OxmlElement("w:commentRangeStart")
    start.set(qn("w:id"), str(comment_id))
    paragraph._p.insert(0, start)

    end = OxmlElement("w:commentRangeEnd")
    end.set(qn("w:id"), str(comment_id))
    paragraph._p.append(end)

    reference_run = OxmlElement("w:r")
    reference = OxmlElement("w:commentReference")
    reference.set(qn("w:id"), str(comment_id))
    reference_run.append(reference)
    paragraph._p.append(reference_run)
    return str(comment_id)


def _remove_existing_comment_markers(document: Document) -> None:
    comment_tags = {
        qn("w:commentRangeStart"),
        qn("w:commentRangeEnd"),
        qn("w:commentReference"),
    }
    for element in list(document.element.iter()):
        if element.tag not in comment_tags:
            continue
        parent = element.getparent()
        if parent is not None:
            parent.remove(element)


def _overall_comment_text(review: ReviewResult) -> str:
    pass_text = {
        "high": "当前具备较高通过概率",
        "medium": "接近通过，但仍需按批注修改",
        "low": "当前通过风险高，建议大改后再提交",
    }[review.pass_probability]
    must_fix = "；".join(item.title for item in review.must_fix[:4]) or "暂无必须补写项"
    should_fix = "；".join(item.title for item in review.should_fix[:4]) or "暂无重点补强项"
    return (
        f"总评：{pass_text}。预计得分：{review.total_score}/75，通过参考线：{review.pass_score}。"
        f"匹配题型：{review.standard.standard_name}。总体结论：{review.summary}"
        f"必须优先修改：{must_fix}。建议继续补强：{should_fix}。"
        "修改时请优先补齐题目要求的过程、工具或文件，并把工具使用过程写到具体项目场景中。"
    )


def _paragraph_comment_text(paragraph_review) -> str:  # type: ignore[no-untyped-def]
    parts: list[str] = []
    if paragraph_review.issues:
        parts.append("问题：" + "；".join(paragraph_review.issues))
    if paragraph_review.suggestions:
        parts.append("建议：" + "；".join(paragraph_review.suggestions))
    if not parts:
        return ""
    if paragraph_review.strengths:
        parts.append("优点：" + "；".join(paragraph_review.strengths))
    return "本段批注：" + " ".join(parts)


def _patch_comments_part(temp_path: Path, output_path: Path, comment_texts: list[str]) -> None:
    with ZipFile(temp_path, "r") as source:
        entries = {item.filename: source.read(item.filename) for item in source.infolist()}

    entries["word/comments.xml"] = _build_comments_xml(comment_texts)
    entries["word/_rels/document.xml.rels"] = _ensure_comments_relationship(
        entries.get("word/_rels/document.xml.rels", _empty_relationships_xml())
    )
    entries["[Content_Types].xml"] = _ensure_comments_content_type(entries["[Content_Types].xml"])

    with ZipFile(output_path, "w", ZIP_DEFLATED) as target:
        for name, data in entries.items():
            target.writestr(name, data)


def _build_comments_xml(comment_texts: list[str]) -> bytes:
    root = etree.Element(f"{{{WORD_NS}}}comments", nsmap={"w": WORD_NS})
    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for index, text in enumerate(comment_texts):
        comment = etree.SubElement(root, f"{{{WORD_NS}}}comment")
        comment.set(f"{{{WORD_NS}}}id", str(index))
        comment.set(f"{{{WORD_NS}}}author", "PaperHelper")
        comment.set(f"{{{WORD_NS}}}initials", "PH")
        comment.set(f"{{{WORD_NS}}}date", timestamp)
        paragraph = etree.SubElement(comment, f"{{{WORD_NS}}}p")
        run = etree.SubElement(paragraph, f"{{{WORD_NS}}}r")
        text_node = etree.SubElement(run, f"{{{WORD_NS}}}t")
        text_node.text = text
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")


def _ensure_comments_relationship(raw_xml: bytes) -> bytes:
    root = etree.fromstring(raw_xml)
    for relationship in root:
        if relationship.get("Type") == COMMENTS_REL_TYPE:
            return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")

    existing_ids = {relationship.get("Id") for relationship in root}
    next_index = 1
    while f"rId{next_index}" in existing_ids:
        next_index += 1
    relationship = etree.SubElement(root, f"{{{RELS_NS}}}Relationship")
    relationship.set("Id", f"rId{next_index}")
    relationship.set("Type", COMMENTS_REL_TYPE)
    relationship.set("Target", "comments.xml")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")


def _ensure_comments_content_type(raw_xml: bytes) -> bytes:
    root = etree.fromstring(raw_xml)
    for override in root:
        if override.get("PartName") == "/word/comments.xml":
            return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")

    override = etree.SubElement(root, f"{{{CONTENT_TYPES_NS}}}Override")
    override.set("PartName", "/word/comments.xml")
    override.set("ContentType", COMMENTS_CONTENT_TYPE)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")


def _empty_relationships_xml() -> bytes:
    root = etree.Element(f"{{{RELS_NS}}}Relationships", nsmap={None: RELS_NS})
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")
