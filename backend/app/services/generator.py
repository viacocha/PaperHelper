from __future__ import annotations

from pathlib import Path

from docx import Document

from app.models.schemas import GeneratedPaper, StandardMatch
from app.services.standards import Standard, StandardLibrary


def generate_paper(
    project_background: str,
    standard_id: str,
    library: StandardLibrary,
    output_dir: Path,
) -> tuple[GeneratedPaper, Path]:
    standard = _find_standard(standard_id, library)
    title = f"论信息系统项目的{standard.name}"
    if standard.category == "performance_domain":
        title = f"论信息系统项目{standard.name}"

    paragraphs = _build_paragraphs(project_background.strip(), standard)
    content = "\n\n".join(paragraphs)
    report_name = f"{standard.name}+论文初稿.docx"
    output_path = output_dir / report_name
    _write_docx(title, paragraphs, output_path)

    return (
        GeneratedPaper(
            title=title,
            standard=StandardMatch(
                standard_id=standard.id,
                standard_name=standard.name,
                category=standard.category,  # type: ignore[arg-type]
                confidence=1.0,
            ),
            content=content,
            paragraphs=paragraphs,
            generated_report_name=report_name,
        ),
        output_path,
    )


def _find_standard(standard_id: str, library: StandardLibrary) -> Standard:
    for standard in library.all():
        if standard.id == standard_id:
            return standard
    raise ValueError("请选择有效的论文题型。")


def _build_paragraphs(project_background: str, standard: Standard) -> list[str]:
    process_text = "、".join(standard.required_processes[:6])
    artifact_text = "、".join(standard.required_artifacts) or "相关管理计划和项目文件"
    question_text = "、".join(standard.question_points)

    paragraphs = [
        f"【题目】{_title_for(standard)}",
        (
            f"{project_background}。在该项目中，我担任乙方项目经理，全面负责项目启动、规划、执行、监控和收尾工作。"
            f"结合项目特点，我认为{standard.name}是保障项目目标实现的重要管理内容。本文将结合该项目实践，围绕{question_text}展开论述。"
        ),
        (
            f"{standard.name}不是单纯的理论概念，而是需要在真实项目场景中持续落地的管理活动。"
            f"在本项目中，我将其与项目目标、交付成果、干系人诉求和项目约束条件结合起来，重点从{process_text}等方面开展管理，"
            f"并通过{artifact_text}等工具和文档进行跟踪、控制和复盘。"
        ),
    ]

    for index, process in enumerate(standard.required_processes[:4], start=1):
        paragraphs.append(
            f"首先，在{process}过程中，我结合项目背景和客户诉求，组织项目团队识别本过程的关键输入、约束条件和预期输出。"
            f"针对项目中可能出现的沟通不充分、责任边界不清或执行偏差等问题，我通过专题会议、评审机制和项目文件跟踪的方式进行管理。"
            f"在具体执行中，我要求团队将管理动作落实到责任人、时间节点和可检查成果上，确保{process}不是停留在文档层面，而是能够支撑项目后续交付。"
        )
        if index == 2:
            paragraphs.append(
                f"其次，为提升{standard.name}的实践深度，我重点使用了{artifact_text}等工具。"
                f"例如，我会将关键事项分解为可跟踪条目，明确来源、责任人、处理状态和验收标准，并在例会中持续更新。"
                f"这样既能让团队及时发现偏差，也便于在项目监控过程中形成闭环。"
            )

    paragraphs.extend([
        (
            f"在项目执行过程中，{standard.name}也遇到了一些管理难点。"
            f"例如，部分干系人对交付边界、实施节奏或验收标准的理解不一致，导致团队一度出现返工和沟通成本上升。"
            f"为此，我组织相关干系人召开专题协调会，重新确认关键事项，并通过问题清单和变更记录持续跟踪处理结果。"
            f"经过以上措施，项目管理过程逐步回到可控状态。"
        ),
        (
            f"在监控阶段，我坚持以数据和事实为依据，对{standard.name}相关事项进行持续检查。"
            f"对已经完成的工作，我组织团队进行阶段性复盘；对仍存在偏差的事项，我及时协调资源、调整计划并向关键干系人同步。"
            f"通过这种方式，项目团队能够及时识别问题、快速采取措施，并保证最终交付成果符合客户要求。"
        ),
        (
            f"最终，在项目团队和各方干系人的共同努力下，项目按计划完成主要建设任务并顺利通过验收。"
            f"通过本项目实践，我进一步认识到，{standard.name}的关键不在于机械背诵流程，而在于结合项目场景，将理论方法转化为具体管理动作。"
            f"今后在类似信息系统项目中，我将继续坚持理论联系实际，重视过程控制、问题闭环和经验复盘，不断提升项目管理水平。"
        ),
    ])
    return paragraphs


def _title_for(standard: Standard) -> str:
    if standard.category == "performance_domain":
        return f"论信息系统项目{standard.name}"
    return f"论信息系统项目的{standard.name}"


def _write_docx(title: str, paragraphs: list[str], output_path: Path) -> None:
    document = Document()
    document.add_heading(title, level=1)
    for paragraph in paragraphs[1:]:
        document.add_paragraph(paragraph)
    document.save(output_path)
