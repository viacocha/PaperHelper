from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.models.schemas import CriterionScore, Issue, ParagraphReview, ReviewResult, StandardMatch
from app.services.parser import ParsedEssay, parse_docx
from app.services.standards import Standard, StandardLibrary, load_standard_library


@dataclass
class ReviewContext:
    parsed: ParsedEssay
    standard: Standard
    confidence: float
    filename: str
    essay_quality: float
    essay_signals: dict[str, int]


class EssayReviewer:
    def __init__(self, library: StandardLibrary | None = None) -> None:
        self.library = library or load_standard_library()

    def review(
        self,
        file_path: Path,
        preferred_standard_id: str | None = None,
        original_filename: str | None = None,
    ) -> ReviewResult:
        parsed = parse_docx(file_path)
        standard, confidence = self.library.find_best_match(parsed.text, preferred_standard_id)
        display_name = original_filename or file_path.name
        essay_signals, essay_quality = self._assess_essay_quality(parsed)
        context = ReviewContext(
            parsed=parsed,
            standard=standard,
            confidence=confidence,
            filename=display_name,
            essay_quality=essay_quality,
            essay_signals=essay_signals,
        )

        dimensions = self._score_dimensions(context)
        issues = self._collect_issues(context)
        paragraph_reviews = self._review_paragraphs(context)
        raw_total = sum(item.score for item in dimensions)
        total_score = round(self._apply_total_adjustments(raw_total, context, issues), 1)
        report_name = f"{Path(display_name).stem}+修改建议.docx"

        return ReviewResult(
            filename=display_name,
            standard=StandardMatch(
                standard_id=standard.id,
                standard_name=standard.name,
                category=standard.category,  # type: ignore[arg-type]
                confidence=round(confidence, 2),
            ),
            total_score=total_score,
            pass_score=self.library.pass_score,
            pass_probability=self._pass_probability(total_score),
            summary=self._build_summary(total_score, issues, context),
            dimensions=dimensions,
            issues=issues,
            paragraph_reviews=paragraph_reviews,
            suggested_report_name=report_name,
        )

    def _score_dimensions(self, context: ReviewContext) -> list[CriterionScore]:
        text = context.parsed.text
        paragraphs = context.parsed.paragraphs

        topic_fit_score = self._scaled_score(
            hits=self._keyword_hits(text, context.standard.question_points + context.standard.keywords),
            target=max(4, len(context.standard.question_points)),
            max_score=22.5,
        ) * context.essay_quality

        overview_score = self._scaled_score(
            hits=context.essay_signals["project_background"],
            target=6,
            max_score=10,
        ) * context.essay_quality
        role_score = self._scaled_score(
            hits=context.essay_signals["role_actions"],
            target=4,
            max_score=6,
        ) * context.essay_quality
        body_score = self._scaled_score(
            hits=self._keyword_hits(text, context.standard.required_processes),
            target=max(3, len(context.standard.required_processes) // 2),
            max_score=12,
        ) * context.essay_quality
        practice_score = self._scaled_score(
            hits=context.essay_signals["practice_signals"],
            target=6,
            max_score=8,
        ) * context.essay_quality
        artifact_score = self._scaled_score(
            hits=self._keyword_hits(text, context.standard.required_artifacts),
            target=max(1, len(context.standard.required_artifacts)),
            max_score=6,
        ) * context.essay_quality
        issue_loop_score = self._scaled_score(
            hits=context.essay_signals["closure_signals"],
            target=6,
            max_score=6,
        ) * context.essay_quality
        expression_score = self._scaled_score(
            hits=context.essay_signals["structure_signals"],
            target=4,
            max_score=4.5,
        )
        if len(paragraphs) < 8:
            expression_score = min(expression_score, 2.5)

        return [
            CriterionScore(id="topic_fit", name="切合题意", score=round(topic_fit_score, 1), max_score=22.5, summary="检查题目与子问覆盖情况。"),
            CriterionScore(id="project_overview", name="项目概要与角色", score=round(overview_score + role_score, 1), max_score=16, summary="检查项目背景、角色和管理者视角。"),
            CriterionScore(id="body_process", name="过程与要点展开", score=round(body_score, 1), max_score=12, summary="检查是否按过程或绩效要点展开。"),
            CriterionScore(id="practice_depth", name="实践深度", score=round(practice_score + artifact_score, 1), max_score=14, summary="检查工具文档与实践动作是否真实落地。"),
            CriterionScore(id="closure", name="问题闭环与总结", score=round(issue_loop_score, 1), max_score=6, summary="检查问题、措施、结果、心得闭环。"),
            CriterionScore(id="expression", name="表达与结构", score=round(expression_score, 1), max_score=4.5, summary="检查结构完整度和可读性。"),
        ]

    def _collect_issues(self, context: ReviewContext) -> list[Issue]:
        parsed = context.parsed
        text = parsed.text
        issues: list[Issue] = []
        min_words = self.library.shared["min_words"]
        max_words = self.library.shared["max_words"]

        if context.essay_quality < 0.55:
            issues.append(Issue(
                severity="high",
                title="文档更像讲义或资料，不像考试论文",
                details="系统检测到该文档缺少稳定的项目背景、第一人称管理动作和论文式结构，更接近讲义、提纲或资料整理稿。",
                suggestion="请上传按考试要求撰写的论文正文，至少包含项目概要、本人角色、主体过程、问题应对和结果总结。",
            ))

        if parsed.word_count < min_words:
            issues.append(Issue(
                severity="high",
                title="正文字数不足",
                details=f"当前字数约 {parsed.word_count}，低于建议下限 {min_words}，通过风险高。",
                suggestion="补充项目背景、核心管理过程、问题应对和项目结果，优先扩充主体段落。",
            ))
        elif parsed.word_count > max_words:
            issues.append(Issue(
                severity="medium",
                title="字数偏多",
                details=f"当前字数约 {parsed.word_count}，超过建议上限 {max_words}。",
                suggestion="压缩空泛概念和重复表述，保留项目动作、工具和结果。",
            ))

        if "项目经理" not in text:
            issues.append(Issue(
                severity="high",
                title="缺少项目经理角色定位",
                details="论文没有清晰说明本人担任项目经理及其职责。",
                suggestion="在项目概要中明确写出本人担任乙方项目经理，并说明负责启动、规划、执行、监控和收尾等工作。",
            ))

        missing_processes = [item for item in context.standard.required_processes if item not in text]
        if len(missing_processes) >= max(2, len(context.standard.required_processes) // 2):
            issues.append(Issue(
                severity="high",
                title="核心过程覆盖不足",
                details=f"当前题型要求的关键过程缺失较多，缺失项包括：{'、'.join(missing_processes[:6])}。",
                suggestion="主体部分按过程逐段展开，每段至少写概念、本人做法、工具文档和效果。",
            ))

        missing_artifacts = [item for item in context.standard.required_artifacts if item not in text]
        if missing_artifacts:
            issues.append(Issue(
                severity="medium",
                title="专属产物响应不足",
                details=f"当前题型应重点响应的产物未明显出现：{'、'.join(missing_artifacts)}。",
                suggestion="把题目要求的矩阵、登记册、WBS、核对单或指标写到对应过程段中，不要只在结尾单独提到。",
            ))

        if not any(token in text for token in ["问题", "风险", "困难", "偏差", "冲突"]):
            issues.append(Issue(
                severity="medium",
                title="缺少问题与应对场景",
                details="论文偏像顺叙说明，缺少项目管理中常见的问题、纠偏和改进。",
                suggestion="至少补充 1 到 2 个真实管理难点，并写清楚如何处理以及最终结果。",
            ))

        if not any(token in text for token in ["验收", "上线", "成效", "满意", "体会", "总结"]):
            issues.append(Issue(
                severity="medium",
                title="结尾成果与总结偏弱",
                details="未明显体现项目结果、验收情况和个人心得。",
                suggestion="结尾补充项目上线或验收结果、业务效果、用户反馈以及个人管理体会。",
            ))

        if len(parsed.paragraphs) < 6:
            issues.append(Issue(
                severity="low",
                title="段落结构偏少",
                details="正文段落数量较少，容易形成大段堆叠，影响阅卷体验。",
                suggestion="按项目概要、主论点、过程分论点、问题应对、总结等结构拆分段落。",
            ))

        if context.essay_signals["structure_signals"] < 2:
            issues.append(Issue(
                severity="medium",
                title="论文结构块不完整",
                details="当前文档没有明显体现项目概要、主体展开、问题应对和总结收尾等论文结构块。",
                suggestion="建议按“项目背景与角色-主论点概述-分论点过程-问题与应对-成果与总结”重组全文。",
            ))

        return issues

    def _review_paragraphs(self, context: ReviewContext) -> list[ParagraphReview]:
        reviews: list[ParagraphReview] = []
        for index, paragraph in enumerate(context.parsed.paragraphs[:12], start=1):
            strengths: list[str] = []
            issues: list[str] = []
            suggestions: list[str] = []

            if any(token in paragraph for token in ["项目", "金额", "工期", "模块", "验收"]):
                strengths.append("包含项目事实信息。")
            if any(token in paragraph for token in ["我组织", "我制定", "我协调", "我推动"]):
                strengths.append("体现了项目经理管理动作。")
            if any(token in paragraph for token in context.standard.required_artifacts + context.standard.required_processes):
                strengths.append("命中了当前题型的关键术语。")

            if not any(token in paragraph for token in ["我", "本人"]):
                issues.append("本段缺少第一人称管理者视角。")
                suggestions.append("补充“我组织/我制定/我协调/我推动”等管理动作。")
            if not any(token in paragraph for token in ["问题", "措施", "通过", "最终", "验收", "效果"]):
                issues.append("本段缺少问题-措施-结果闭环。")
                suggestions.append("增加遇到的问题、采取的措施及最终效果。")
            if len(paragraph) < 60:
                issues.append("本段内容偏短，信息密度不足。")
                suggestions.append("扩充本段中的项目事实、工具文档或结果。")

            reviews.append(ParagraphReview(
                index=index,
                excerpt=paragraph[:120],
                strengths=strengths,
                issues=issues,
                suggestions=suggestions,
            ))
        return reviews

    def _keyword_hits(self, text: str, tokens: list[str]) -> int:
        return sum(1 for token in tokens if token and token in text)

    def _scaled_score(self, hits: int, target: int, max_score: float) -> float:
        ratio = min(hits / max(1, target), 1.0)
        return ratio * max_score

    def _pass_probability(self, total_score: float) -> str:
        if total_score >= 52:
            return "high"
        if total_score >= self.library.pass_score:
            return "medium"
        return "low"

    def _build_summary(self, total_score: float, issues: list[Issue], context: ReviewContext) -> str:
        if context.essay_quality < 0.55:
            return f"当前上传内容未表现出稳定的考试论文形态，更像资料或讲义，建议先按 {context.standard.name} 论文模板重写后再批改。"
        if total_score >= 52:
            return f"这篇论文已具备较强通过基础，当前主要需要针对 {context.standard.name} 题型补足细节和专属产物。"
        if total_score >= self.library.pass_score:
            return f"这篇论文接近通过，但仍有明显风险，建议优先修正高风险问题后再进行二次批改。"
        high_issue_count = sum(1 for item in issues if item.severity == 'high')
        return f"这篇论文当前未达到稳定通过水平，存在 {high_issue_count} 个高风险问题，建议先重构结构和主体内容。"

    def _apply_total_adjustments(self, raw_total: float, context: ReviewContext, issues: list[Issue]) -> float:
        total = raw_total
        high_issue_count = sum(1 for item in issues if item.severity == "high")
        medium_issue_count = sum(1 for item in issues if item.severity == "medium")

        total -= high_issue_count * 3.5
        total -= medium_issue_count * 1.0

        if context.essay_quality < 0.55:
            total = min(total, 38)
        elif context.essay_quality < 0.7:
            total = min(total, 48)

        return max(0.0, min(75.0, total))

    def _assess_essay_quality(self, parsed: ParsedEssay) -> tuple[dict[str, int], float]:
        text = parsed.text
        project_background_tokens = [
            "项目背景", "发起单位", "建设周期", "工期", "合同金额", "总投资", "交付成果", "组织结构", "项目内容", "模块",
            "验收", "上线", "项目目标", "发起", "周期", "金额"
        ]
        role_action_tokens = [
            "项目经理", "我负责", "本人负责", "我组织", "我制定", "我协调", "我推动", "我跟踪", "我复盘"
        ]
        practice_tokens = [
            "WBS", "甘特图", "风险登记册", "需求跟踪矩阵", "核对单", "质量保证", "变更", "里程碑", "状态报告", "验收"
        ]
        closure_tokens = [
            "问题", "风险", "为此", "措施", "最终", "验收", "上线", "满意", "总结", "体会", "心得", "成效"
        ]
        structure_tokens = [
            "项目背景", "概要", "本文", "结合", "问题与应对", "总结", "体会", "结尾", "项目成功"
        ]
        anti_essay_tokens = [
            "讲义", "课件", "趋势判断", "考试范围", "写作方法", "评分逻辑", "授课", "考前串讲"
        ]

        signals = {
            "project_background": self._keyword_hits(text, project_background_tokens),
            "role_actions": self._keyword_hits(text, role_action_tokens),
            "practice_signals": self._keyword_hits(text, practice_tokens) + self._first_person_action_count(text),
            "closure_signals": self._keyword_hits(text, closure_tokens),
            "structure_signals": self._keyword_hits(text, structure_tokens),
            "anti_essay": self._keyword_hits(text, anti_essay_tokens),
        }

        score = 0.0
        score += min(signals["project_background"] / 6, 1.0) * 0.28
        score += min(signals["role_actions"] / 4, 1.0) * 0.26
        score += min(signals["practice_signals"] / 6, 1.0) * 0.18
        score += min(signals["closure_signals"] / 5, 1.0) * 0.16
        score += min(signals["structure_signals"] / 4, 1.0) * 0.12
        score -= min(signals["anti_essay"] / 4, 1.0) * 0.35

        if parsed.word_count < 1800:
            score -= 0.15
        if len(parsed.paragraphs) < 8:
            score -= 0.08

        return signals, max(0.15, min(score, 1.0))

    def _first_person_action_count(self, text: str) -> int:
        action_phrases = ["我组织", "我制定", "我协调", "我推动", "我跟踪", "我安排", "我主持", "我带领", "我分析", "我复盘"]
        return sum(text.count(token) for token in action_phrases)
