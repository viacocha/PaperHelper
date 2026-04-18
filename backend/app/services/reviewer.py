from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.models.schemas import CriterionScore, Issue, ParagraphReview, RevisionTemplate, ReviewResult, StandardMatch, TopicScorecardItem
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
        topic_scorecard = self._build_topic_scorecard(context)
        issues = self._collect_issues(context)
        must_fix, should_fix, could_improve = self._group_issues(issues)
        revision_templates = self._build_revision_templates(context, must_fix, should_fix)
        paragraph_reviews = self._review_paragraphs(context)
        raw_total = sum(item.score for item in dimensions)
        total_score = round(self._apply_total_adjustments(raw_total, context, issues), 1)
        original_stem = Path(display_name).stem
        if original_stem.endswith(("（改后）", "(改后)")):
            report_name = f"{original_stem}.docx"
        else:
            report_name = f"{original_stem}（改后）.docx"

        return ReviewResult(
            filename=display_name,
            standard=StandardMatch(
                standard_id=standard.id,
                standard_name=standard.name,
                category=standard.category,  # type: ignore[arg-type]
                confidence=round(confidence, 2),
            ),
            word_count=parsed.word_count,
            minimum_word_count=self.library.shared["min_words"],
            total_score=total_score,
            pass_score=self.library.pass_score,
            pass_probability=self._pass_probability(total_score),
            summary=self._build_summary(total_score, issues, context),
            dimensions=dimensions,
            topic_scorecard=topic_scorecard,
            issues=issues,
            must_fix=must_fix,
            should_fix=should_fix,
            could_improve=could_improve,
            revision_templates=revision_templates,
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

    def _build_topic_scorecard(self, context: ReviewContext) -> list[TopicScorecardItem]:
        builders = {
            "scope_management": self._scope_scorecard,
            "schedule_management": self._schedule_scorecard,
            "cost_management": self._cost_scorecard,
            "quality_management": self._quality_scorecard,
            "risk_management": self._risk_scorecard,
            "stakeholder_management": self._stakeholder_scorecard,
            "contract_management": self._contract_scorecard,
            "planning_performance_domain": self._planning_scorecard,
            "work_performance_domain": self._work_pd_scorecard,
            "delivery_performance_domain": self._delivery_scorecard,
            "uncertainty_performance_domain": self._uncertainty_scorecard,
            "measurement_performance_domain": self._measurement_scorecard,
        }
        builder = builders.get(context.standard.id)
        return builder(context) if builder else self._generic_scorecard(context)

    def _collect_issues(self, context: ReviewContext) -> list[Issue]:
        parsed = context.parsed
        text = parsed.text
        issues: list[Issue] = []
        min_words = self.library.shared["min_words"]
        max_words = self.library.shared["max_words"]

        if context.essay_quality < 0.55:
            issues.append(Issue(
                severity="high",
                action_priority="must",
                title="文档更像讲义或资料，不像考试论文",
                details="系统检测到该文档缺少稳定的项目背景、第一人称管理动作和论文式结构，更接近讲义、提纲或资料整理稿。",
                suggestion="请上传按考试要求撰写的论文正文，至少包含项目概要、本人角色、主体过程、问题应对和结果总结。",
            ))

        if parsed.word_count < min_words:
            issues.append(Issue(
                severity="high",
                action_priority="must",
                title="正文字数不足",
                details=f"当前字数约 {parsed.word_count}，低于建议下限 {min_words}，通过风险高。",
                suggestion="补充项目背景、核心管理过程、问题应对和项目结果，优先扩充主体段落。",
            ))
        elif parsed.word_count > max_words:
            issues.append(Issue(
                severity="medium",
                action_priority="should",
                title="字数偏多",
                details=f"当前字数约 {parsed.word_count}，超过建议上限 {max_words}。",
                suggestion="压缩空泛概念和重复表述，保留项目动作、工具和结果。",
            ))

        if "项目经理" not in text:
            issues.append(Issue(
                severity="high",
                action_priority="must",
                title="缺少项目经理角色定位",
                details="论文没有清晰说明本人担任项目经理及其职责。",
                suggestion="在项目概要中明确写出本人担任乙方项目经理，并说明负责启动、规划、执行、监控和收尾等工作。",
            ))

        missing_processes = [item for item in context.standard.required_processes if item not in text]
        if len(missing_processes) >= max(2, len(context.standard.required_processes) // 2):
            issues.append(Issue(
                severity="high",
                action_priority="must",
                title="核心过程覆盖不足",
                details=f"当前题型要求的关键过程缺失较多，缺失项包括：{'、'.join(missing_processes[:6])}。",
                suggestion="主体部分按过程逐段展开，每段至少写概念、本人做法、工具文档和效果。",
            ))

        missing_artifacts = [item for item in context.standard.required_artifacts if item not in text]
        if missing_artifacts:
            issues.append(Issue(
                severity="medium",
                action_priority="must",
                title="专属产物响应不足",
                details=f"当前题型应重点响应的产物未明显出现：{'、'.join(missing_artifacts)}。",
                suggestion="把题目要求的矩阵、登记册、WBS、核对单或指标写到对应过程段中，不要只在结尾单独提到。",
            ))

        if not any(token in text for token in ["问题", "风险", "困难", "偏差", "冲突"]):
            issues.append(Issue(
                severity="medium",
                action_priority="should",
                title="缺少问题与应对场景",
                details="论文偏像顺叙说明，缺少项目管理中常见的问题、纠偏和改进。",
                suggestion="至少补充 1 到 2 个真实管理难点，并写清楚如何处理以及最终结果。",
            ))

        if not any(token in text for token in ["验收", "上线", "成效", "满意", "体会", "总结"]):
            issues.append(Issue(
                severity="medium",
                action_priority="should",
                title="结尾成果与总结偏弱",
                details="未明显体现项目结果、验收情况和个人心得。",
                suggestion="结尾补充项目上线或验收结果、业务效果、用户反馈以及个人管理体会。",
            ))

        if len(parsed.paragraphs) < 6:
            issues.append(Issue(
                severity="low",
                action_priority="could",
                title="段落结构偏少",
                details="正文段落数量较少，容易形成大段堆叠，影响阅卷体验。",
                suggestion="按项目概要、主论点、过程分论点、问题应对、总结等结构拆分段落。",
            ))

        if context.essay_signals["structure_signals"] < 2:
            issues.append(Issue(
                severity="medium",
                action_priority="must",
                title="论文结构块不完整",
                details="当前文档没有明显体现项目概要、主体展开、问题应对和总结收尾等论文结构块。",
                suggestion="建议按“项目背景与角色-主论点概述-分论点过程-问题与应对-成果与总结”重组全文。",
            ))

        issues.extend(self._topic_specific_issues(context))
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
                if not any(token in paragraph for token in ["例如", "具体", "数据", "指标", "发现", "纠正", "优化", "对比", "结果"]):
                    issues.append("本段提到了过程或工具，但缺少具体使用场景和数据佐证。")
                    suggestions.append("补充工具如何制定、如何使用、发现了什么问题、如何纠正以及产生的效果。")

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

    def _group_issues(self, issues: list[Issue]) -> tuple[list[Issue], list[Issue], list[Issue]]:
        must_fix = [item for item in issues if item.action_priority == "must"]
        should_fix = [item for item in issues if item.action_priority == "should"]
        could_improve = [item for item in issues if item.action_priority == "could"]
        return must_fix, should_fix, could_improve

    def _topic_specific_issues(self, context: ReviewContext) -> list[Issue]:
        issue_builders = {
            "scope_management": self._scope_issues,
            "schedule_management": self._schedule_issues,
            "cost_management": self._cost_issues,
            "quality_management": self._quality_issues,
            "risk_management": self._risk_issues,
            "stakeholder_management": self._stakeholder_issues,
            "contract_management": self._contract_issues,
            "delivery_performance_domain": self._delivery_issues,
            "uncertainty_performance_domain": self._uncertainty_issues,
            "measurement_performance_domain": self._measurement_issues,
            "planning_performance_domain": self._planning_issues,
            "work_performance_domain": self._work_pd_issues,
        }
        builder = issue_builders.get(context.standard.id)
        return builder(context) if builder else []

    def _build_revision_templates(
        self,
        context: ReviewContext,
        must_fix: list[Issue],
        should_fix: list[Issue],
    ) -> list[RevisionTemplate]:
        builders = {
            "scope_management": self._scope_templates,
            "risk_management": self._risk_templates,
            "quality_management": self._quality_templates,
            "schedule_management": self._schedule_templates,
            "delivery_performance_domain": self._delivery_templates,
            "uncertainty_performance_domain": self._uncertainty_templates,
        }
        base_templates = self._generic_templates(context)
        topic_templates = builders.get(context.standard.id, lambda _context: [])(context)

        limit = 4 if must_fix else 3
        templates = base_templates + topic_templates
        return templates[:limit]

    def _generic_templates(self, context: ReviewContext) -> list[RevisionTemplate]:
        return [
            RevisionTemplate(
                title="项目背景与角色补写模板",
                purpose="补齐论文开头最核心的项目真实性和管理者视角。",
                when_to_use="缺少项目背景、本人职责、项目规模或验收结果时使用。",
                outline=[
                    "项目发起背景、建设目标、合同金额或总投资",
                    "建设周期、主要模块、组织结构、交付成果",
                    "本人担任乙方项目经理，负责启动、规划、执行、监控和收尾",
                    "用一句话引出本文将围绕当前题型展开"
                ],
                sample="我于2025年3月担任某市智慧监管平台建设项目的乙方项目经理，项目合同金额820万元，建设周期11个月，采用强矩阵组织结构，交付内容包括统一门户、业务办理、数据交换和统计分析等模块。我负责项目启动、范围规划、进度控制、质量协调和验收交付。下面结合该项目，论述我在当前题型中的具体管理实践。"
            ),
            RevisionTemplate(
                title="问题-措施-结果段落模板",
                purpose="把空泛理论段改成阅卷老师更容易给分的实战段。",
                when_to_use="某一段只有概念，没有问题、动作和结果时使用。",
                outline=[
                    "先交代项目中出现的具体问题或风险",
                    "再写本人采取的管理措施和使用的工具文档",
                    "补充执行频率、责任人、会议或评审机制",
                    "结尾写最终效果、验收结果或偏差收敛情况"
                ],
                sample="在项目实施过程中，由于甲方多个业务部门口径不一致，需求反复变化，导致交付边界一度不清。为此，我组织召开了专题需求澄清会，并结合需求跟踪矩阵逐项确认需求来源、责任人和验收标准。同时我要求团队每周更新问题清单，双周进行一次范围评审。经过以上措施，需求变更率明显下降，后续验收工作也更加顺畅。"
            )
        ]

    def _generic_scorecard(self, context: ReviewContext) -> list[TopicScorecardItem]:
        text = context.parsed.text
        return [
            self._make_scorecard_item("项目背景与角色", self._keyword_hits(text, ["项目经理", "项目背景", "工期", "交付成果", "负责"]), 4, 5, "检查项目真实性和本人职责。"),
            self._make_scorecard_item("核心过程展开", self._keyword_hits(text, context.standard.required_processes), max(2, len(context.standard.required_processes) // 2), 5, "检查题型核心过程是否被展开。"),
            self._make_scorecard_item("专属产物响应", self._keyword_hits(text, context.standard.required_artifacts), max(1, len(context.standard.required_artifacts)), 5, "检查矩阵、计划、登记册等产物。"),
            self._make_scorecard_item("问题与结果闭环", self._keyword_hits(text, ["问题", "风险", "措施", "最终", "验收", "体会"]), 4, 5, "检查是否写出问题、措施和结果。"),
        ]

    def _scope_scorecard(self, context: ReviewContext) -> list[TopicScorecardItem]:
        text = context.parsed.text
        return [
            self._make_scorecard_item("范围过程覆盖", self._keyword_hits(text, context.standard.required_processes), 4, 5, "规划范围、收集需求、定义范围、创建WBS等过程是否完整。"),
            self._make_scorecard_item("需求跟踪矩阵", text.count("需求跟踪矩阵"), 1, 5, "是否写出矩阵及关键字段或示例需求。"),
            self._make_scorecard_item("WBS 分解", text.count("WBS"), 1, 5, "是否写出与项目一致的 WBS 分解。"),
            self._make_scorecard_item("确认与控制范围", self._keyword_hits(text, ["确认范围", "控制范围", "验收", "范围变更"]), 3, 5, "是否写出确认范围和范围控制。"),
        ]

    def _schedule_scorecard(self, context: ReviewContext) -> list[TopicScorecardItem]:
        text = context.parsed.text
        return [
            self._make_scorecard_item("进度过程覆盖", self._keyword_hits(text, context.standard.required_processes), 4, 5, "是否覆盖定义活动、排序、估算、制定计划和控制进度。"),
            self._make_scorecard_item("进度计划/甘特图", self._keyword_hits(text, ["甘特图", "进度计划", "里程碑"]), 2, 5, "是否体现主要进度计划产物。"),
            self._make_scorecard_item("延期处理", self._keyword_hits(text, ["延期", "延迟", "赶工", "快速跟进", "关键路径"]), 2, 5, "是否回应进度偏差和纠偏方式。"),
            self._make_scorecard_item("结果与偏差收敛", self._keyword_hits(text, ["按期", "里程碑", "追赶", "偏差", "验收"]), 2, 5, "是否写出调整后的效果。"),
        ]

    def _cost_scorecard(self, context: ReviewContext) -> list[TopicScorecardItem]:
        text = context.parsed.text
        return [
            self._make_scorecard_item("成本过程覆盖", self._keyword_hits(text, context.standard.required_processes), 3, 5, "是否覆盖估算、预算和控制成本。"),
            self._make_scorecard_item("预算形成", self._keyword_hits(text, ["预算", "成本基准", "估算", "汇总"]), 3, 5, "是否写清预算形成过程。"),
            self._make_scorecard_item("成本控制方法", self._keyword_hits(text, ["挣值", "S曲线", "偏差分析", "趋势分析", "成本控制"]), 2, 5, "是否写明成本监控与纠偏工具。"),
            self._make_scorecard_item("成本结果", self._keyword_hits(text, ["预算范围内", "偏差收敛", "节约", "控制在"]), 2, 5, "是否体现最终成本效果。"),
        ]

    def _quality_scorecard(self, context: ReviewContext) -> list[TopicScorecardItem]:
        text = context.parsed.text
        return [
            self._make_scorecard_item("质量过程覆盖", self._keyword_hits(text, context.standard.required_processes), 3, 5, "是否覆盖规划质量、质量保证和质量控制。"),
            self._make_scorecard_item("质量保证", self._keyword_hits(text, ["质量保证", "QA", "评审", "过程审计"]), 3, 5, "是否写出质量保证动作。"),
            self._make_scorecard_item("质量核对单/标准", self._keyword_hits(text, ["核对单", "质量标准", "准入标准"]), 2, 5, "是否给出核对单或质量准入要求。"),
            self._make_scorecard_item("质量结果", self._keyword_hits(text, ["缺陷", "一次性通过", "验收", "返工"]), 2, 5, "是否体现质量改进结果。"),
        ]

    def _risk_scorecard(self, context: ReviewContext) -> list[TopicScorecardItem]:
        text = context.parsed.text
        return [
            self._make_scorecard_item("风险过程覆盖", self._keyword_hits(text, context.standard.required_processes), 4, 5, "是否覆盖识别、分析、应对和监督风险。"),
            self._make_scorecard_item("风险登记册", self._keyword_hits(text, ["风险登记册", "风险编号", "概率", "影响", "责任人"]), 3, 5, "是否写出登记册字段或样例。"),
            self._make_scorecard_item("定性/定量分析", self._keyword_hits(text, ["定性", "定量", "概率影响矩阵", "建模", "模拟"]), 2, 5, "是否体现分析深度。"),
            self._make_scorecard_item("风险应对与跟踪", self._keyword_hits(text, ["应对", "储备", "B计划", "监督风险", "双周风险会议"]), 3, 5, "是否写出应对和跟踪机制。"),
        ]

    def _stakeholder_scorecard(self, context: ReviewContext) -> list[TopicScorecardItem]:
        text = context.parsed.text
        return [
            self._make_scorecard_item("干系人过程覆盖", self._keyword_hits(text, context.standard.required_processes), 3, 5, "是否覆盖识别、规划参与、管理参与和监督参与。"),
            self._make_scorecard_item("权力/利益方格", self._keyword_hits(text, ["权力", "利益方格", "参与度评估矩阵"]), 2, 5, "是否写出分类分析和策略。"),
            self._make_scorecard_item("联系与区别", self._keyword_hits(text, ["沟通管理", "需求管理", "区别", "联系"]), 2, 5, "是否回应与沟通/需求管理的区别。"),
            self._make_scorecard_item("干系人成效", self._keyword_hits(text, ["满意度", "参与", "支持", "冲突处理"]), 2, 5, "是否体现管理效果。"),
        ]

    def _contract_scorecard(self, context: ReviewContext) -> list[TopicScorecardItem]:
        text = context.parsed.text
        return [
            self._make_scorecard_item("合同过程覆盖", self._keyword_hits(text, context.standard.required_processes), 3, 5, "是否覆盖签订、履行、变更、档案和索赔。"),
            self._make_scorecard_item("索赔流程", self._keyword_hits(text, ["索赔", "监理", "审批", "书面提出"]), 2, 5, "是否写出索赔或变更流程。"),
            self._make_scorecard_item("主要条款", self._keyword_hits(text, ["付款", "违约", "验收条款", "范围条款", "工期"]), 3, 5, "是否列出核心合同条款。"),
            self._make_scorecard_item("合同执行结果", self._keyword_hits(text, ["履约", "按合同", "验收", "违约控制"]), 2, 5, "是否体现合同执行效果。"),
        ]

    def _planning_scorecard(self, context: ReviewContext) -> list[TopicScorecardItem]:
        text = context.parsed.text
        return [
            self._make_scorecard_item("项目管理计划主线", self._keyword_hits(text, ["项目管理计划", "子计划", "基准"]), 3, 5, "是否围绕项目管理计划展开。"),
            self._make_scorecard_item("规划关键抓手", self._keyword_hits(text, ["估算", "滚动式规划", "变更控制", "采购规划", "沟通规划"]), 3, 5, "是否写出规划抓手。"),
            self._make_scorecard_item("规划适应变化", self._keyword_hits(text, ["调整", "变化", "基准更新", "变更"]), 2, 5, "是否体现动态规划。"),
            self._make_scorecard_item("规划结果", self._keyword_hits(text, ["协调一致", "按计划推进", "差异收敛"]), 2, 5, "是否体现规划效果。"),
        ]

    def _work_pd_scorecard(self, context: ReviewContext) -> list[TopicScorecardItem]:
        text = context.parsed.text
        return [
            self._make_scorecard_item("执行监控机制", self._keyword_hits(text, ["状态报告", "过程审计", "变更日志", "采购审计"]), 3, 5, "是否写出执行中的监控抓手。"),
            self._make_scorecard_item("沟通/资源/采购管理", self._keyword_hits(text, ["沟通", "资源利用率", "采购", "实物资源"]), 3, 5, "是否覆盖工作绩效域关键要点。"),
            self._make_scorecard_item("变更与新工作处理", self._keyword_hits(text, ["变更", "新工作", "评估", "范围增加"]), 2, 5, "是否写出变更评估和处理。"),
            self._make_scorecard_item("持续改进", self._keyword_hits(text, ["经验教训", "持续改进", "知识管理", "复盘"]), 2, 5, "是否体现学习与改进。"),
        ]

    def _delivery_scorecard(self, context: ReviewContext) -> list[TopicScorecardItem]:
        text = context.parsed.text
        return [
            self._make_scorecard_item("业务价值与目标一致", self._keyword_hits(text, ["业务目标", "价值", "收益", "战略"]), 3, 5, "是否写出交付与业务目标一致。"),
            self._make_scorecard_item("可交付物与验收", self._keyword_hits(text, ["交付物", "验收", "质量标准", "需求理解"]), 3, 5, "是否写出交付物和验收机制。"),
            self._make_scorecard_item("绩效域协同", self._keyword_hits(text, ["协同", "规划绩效域", "工作绩效域", "干系人"]), 2, 5, "是否写出与其他绩效域协同。"),
            self._make_scorecard_item("测量指标与满意度", self._keyword_hits(text, ["测量指标", "满意度", "收益兑现", "缺陷"]), 2, 5, "是否写出测量指标和最终效果。"),
        ]

    def _uncertainty_scorecard(self, context: ReviewContext) -> list[TopicScorecardItem]:
        text = context.parsed.text
        return [
            self._make_scorecard_item("风险/模糊性/复杂性", self._keyword_hits(text, ["风险", "模糊性", "复杂性"]), 3, 5, "是否覆盖三类不确定性来源。"),
            self._make_scorecard_item("分析与排序", self._keyword_hits(text, ["分析", "排序", "概率", "影响", "优先级"]), 3, 5, "是否体现识别后的分析排序。"),
            self._make_scorecard_item("应对与储备", self._keyword_hits(text, ["储备", "应对", "机会", "威胁", "B计划"]), 3, 5, "是否写出储备和应对策略。"),
            self._make_scorecard_item("与其他绩效域关系", self._keyword_hits(text, ["其他绩效域", "干系人绩效域", "规划绩效域", "度量绩效域"]), 2, 5, "是否说明相互作用。"),
        ]

    def _measurement_scorecard(self, context: ReviewContext) -> list[TopicScorecardItem]:
        text = context.parsed.text
        return [
            self._make_scorecard_item("指标体系", self._keyword_hits(text, ["指标", "KPI", "阈值", "预警"]), 3, 5, "是否建立有效指标体系。"),
            self._make_scorecard_item("展示与诊断", self._keyword_hits(text, ["状态报告", "趋势分析", "偏差分析", "图表"]), 2, 5, "是否写出展示和诊断方式。"),
            self._make_scorecard_item("基于度量采取行动", self._keyword_hits(text, ["纠偏", "行动", "决策", "调整"]), 2, 5, "是否体现数据驱动决策。"),
            self._make_scorecard_item("持续改进", self._keyword_hits(text, ["持续改进", "优化指标", "复盘"]), 2, 5, "是否体现度量闭环。"),
        ]

    def _make_scorecard_item(self, title: str, hits: int, target: int, max_score: float, summary: str) -> TopicScorecardItem:
        ratio = min(hits / max(1, target), 1.0)
        score = round(ratio * max_score, 1)
        if ratio >= 0.8:
            status = "good"
        elif ratio >= 0.4:
            status = "warning"
        else:
            status = "missing"
        return TopicScorecardItem(title=title, score=score, max_score=max_score, status=status, summary=summary)

    def _scope_templates(self, context: ReviewContext) -> list[RevisionTemplate]:
        return [
            RevisionTemplate(
                title="需求跟踪矩阵补写模板",
                purpose="补齐范围题最关键的专属产物。",
                when_to_use="缺少需求跟踪矩阵或只提到名称没有具体字段时使用。",
                outline=[
                    "说明需求跟踪矩阵建立在收集需求和定义范围阶段",
                    "列出字段：需求编号、需求描述、来源、责任人、优先级、验收标准、对应交付物",
                    "至少举 2 个核心需求作为示例",
                    "补一句矩阵如何支持后续确认范围和控制范围"
                ],
                sample="在收集需求阶段，我组织团队建立了需求跟踪矩阵，字段包括需求编号、需求描述、提出部门、责任人、优先级、验收标准及对应交付物。例如 R-01 为统一登录需求，对应门户模块，由需求分析师负责跟踪，验收标准为单点登录成功率达到100%。通过该矩阵，我们在确认范围和后续验收时能够快速定位每项需求的落实情况。"
            ),
            RevisionTemplate(
                title="WBS 分解补写模板",
                purpose="补齐范围题对子问中 WBS 的响应。",
                when_to_use="缺少 WBS、分解层级不清或与项目内容不一致时使用。",
                outline=[
                    "先说明分解原则：面向可交付成果、逐层细化、责任清晰",
                    "按项目/阶段/模块/工作包逐层分解",
                    "说明至少分到可管理工作包层",
                    "补一句 WBS 如何支持进度、成本和责任落实"
                ],
                sample="在创建WBS时，我遵循面向可交付成果、逐层分解和责任清晰的原则，将项目分解为项目管理、需求分析、系统设计、开发实现、测试验证、部署培训六大层级，再继续分解到门户模块、审批模块、报表模块等工作包。通过WBS，团队明确了边界和责任，也为后续进度编排和成本估算提供了基础。"
            )
        ]

    def _risk_templates(self, context: ReviewContext) -> list[RevisionTemplate]:
        return [
            RevisionTemplate(
                title="风险登记册补写模板",
                purpose="补齐风险题最关键的产物和管理闭环。",
                when_to_use="缺少风险登记册字段或没有体现动态更新过程时使用。",
                outline=[
                    "说明在识别风险后建立风险登记册",
                    "列出字段：风险编号、描述、原因、概率、影响、责任人、应对措施、状态",
                    "举 1 到 2 个实际风险案例",
                    "补一句登记册如何在双周会议中持续更新"
                ],
                sample="在识别风险后，我建立了风险登记册，字段包括风险编号、风险描述、触发原因、概率、影响程度、风险责任人、应对措施和当前状态。例如 R-03 为第三方接口延期风险，概率评估为中，影响为高，由实施负责人负责跟踪，应对措施为提前联调并准备模拟接口。此后我要求团队在双周风险会议上持续更新登记册状态，确保风险处于可控范围。"
            ),
            RevisionTemplate(
                title="定性定量分析补写模板",
                purpose="提高风险题的深度得分。",
                when_to_use="正文只写识别和应对，没有分析过程时使用。",
                outline=[
                    "先写概率影响矩阵进行定性分析",
                    "再补一个定量分析或储备测算例子",
                    "说明分析结果如何影响优先级和应对方式",
                    "最后写应急储备或 B 计划"
                ],
                sample="在完成初步识别后，我先采用概率-影响矩阵对风险进行定性排序，将接口延期和核心成员流失列为高优先级风险。对于接口延期风险，我进一步结合历史数据测算可能造成的工期影响，并预留了两周进度储备。根据分析结果，我决定提前安排联调窗口，并准备模拟接口作为B计划，从而降低该风险对总工期的冲击。"
            )
        ]

    def _quality_templates(self, context: ReviewContext) -> list[RevisionTemplate]:
        return [
            RevisionTemplate(
                title="质量保证补写模板",
                purpose="补齐质量题中最容易失分的质量保证部分。",
                when_to_use="正文主要写测试和质量控制，缺少 QA、评审和过程保证时使用。",
                outline=[
                    "说明 QA 介入时点和职责",
                    "写需求评审、设计评审、代码走查、过程审计等动作",
                    "写质量核对单或准入标准",
                    "最后写缺陷下降、返工减少或一次验收通过"
                ],
                sample="在质量保证阶段，我安排QA全过程介入，分别在需求、设计、开发和测试阶段组织正式评审，并依据质量核对单检查文档完整性、评审记录、缺陷关闭情况和发布准入条件。针对关键模块，我还安排了代码走查和过程审计。通过这些措施，项目后期重大缺陷数量明显下降，最终一次性通过用户验收。"
            )
        ]

    def _schedule_templates(self, context: ReviewContext) -> list[RevisionTemplate]:
        return [
            RevisionTemplate(
                title="进度延迟处理补写模板",
                purpose="补齐进度题对子问“延期处理”的直接回应。",
                when_to_use="正文有进度计划但没有偏差处理场景时使用。",
                outline=[
                    "先交代进度偏差出现的原因",
                    "写关键路径分析或里程碑预警",
                    "写赶工、快速跟进、资源调整或范围协商",
                    "结尾写偏差如何被收敛"
                ],
                sample="项目中期由于接口联调迟迟未完成，里程碑节点出现延迟。为此，我首先重新审查关键路径，确认受影响任务范围，并安排开发与测试并行推进，对关键模块采用赶工方式增加人手。同时与甲方协商将低优先级需求延后处理。经过调整后，项目在后续两周内逐步追回了进度偏差。"
            )
        ]

    def _delivery_templates(self, context: ReviewContext) -> list[RevisionTemplate]:
        return [
            RevisionTemplate(
                title="交付价值与协同补写模板",
                purpose="补齐交付绩效域的业务价值和协同目标。",
                when_to_use="正文只写交付物，没有写业务目标、满意度和与其他绩效域协同时使用。",
                outline=[
                    "先写交付物如何支撑业务目标",
                    "再写与规划、工作、干系人、不确定性等绩效域协同",
                    "补充验收、满意度或收益兑现指标",
                    "结尾写价值实现效果"
                ],
                sample="在交付绩效域管理中，我始终以业务目标为牵引，确保统一门户、审批流程和统计分析等交付物能够真正支撑客户提升办事效率。为此，我在规划绩效域中明确验收标准，在工作绩效域中跟踪执行状态，在干系人绩效域中持续收集用户反馈，并在不确定性绩效域中提前应对交付风险。最终系统顺利上线，关键功能全部通过验收，用户满意度达到预期。"
            )
        ]

    def _uncertainty_templates(self, context: ReviewContext) -> list[RevisionTemplate]:
        return [
            RevisionTemplate(
                title="不确定性与其他绩效域关系补写模板",
                purpose="补齐不确定性绩效域的综合分析深度。",
                when_to_use="正文只写风险处理，没有写模糊性、复杂性以及与其他绩效域联动时使用。",
                outline=[
                    "区分风险、模糊性、复杂性",
                    "分别说明对规划、干系人、交付和度量的影响",
                    "写识别、分析、储备和备选方案",
                    "结尾写如何降低交付负面影响"
                ],
                sample="在本项目中，不确定性既包括接口延期等可识别风险，也包括需求口径不一致带来的模糊性，以及多系统集成带来的复杂性。针对这些因素，我一方面在规划绩效域中预留进度储备，另一方面通过干系人沟通机制及时澄清需求，并在度量绩效域中设置预警指标，动态监控不确定性变化。通过多绩效域协同，我将不确定性对交付的影响控制在可接受范围内。"
            )
        ]

    def _scope_issues(self, context: ReviewContext) -> list[Issue]:
        text = context.parsed.text
        issues: list[Issue] = []
        if "需求跟踪矩阵" not in text:
            issues.append(Issue(
                severity="high",
                action_priority="must",
                title="范围题缺少需求跟踪矩阵",
                details="范围管理题通常要求写出核心范围对应的需求跟踪矩阵，当前正文未明显体现。",
                suggestion="在收集需求或定义范围部分补充需求跟踪矩阵字段，并至少举 2 个核心需求的跟踪示例。",
            ))
        if "WBS" not in text:
            issues.append(Issue(
                severity="high",
                action_priority="must",
                title="范围题缺少 WBS 响应",
                details="范围管理题常要求给出与项目一致的 WBS，当前未明显出现。",
                suggestion="在创建 WBS 段写出分解原则、层级和主要可交付成果，必要时补充树状结构说明。",
            ))
        if not any(token in text for token in ["确认范围", "控制范围"]):
            issues.append(Issue(
                severity="medium",
                action_priority="should",
                title="范围题后段过程展开不足",
                details="正文更偏前期需求和范围定义，确认范围、控制范围的叙述不够。",
                suggestion="补充验收、范围变更、范围蔓延控制和干系人确认的做法。",
            ))
        return issues

    def _schedule_issues(self, context: ReviewContext) -> list[Issue]:
        text = context.parsed.text
        issues: list[Issue] = []
        if "甘特图" not in text and "进度计划" not in text:
            issues.append(Issue(
                severity="high",
                action_priority="must",
                title="进度题缺少进度计划产物",
                details="进度管理题通常要求体现甘特图或对应进度计划，当前未明确响应。",
                suggestion="补充主要阶段、里程碑、持续时间和前后依赖关系，并说明进度计划如何形成。",
            ))
        if not any(token in text for token in ["延期", "延迟", "赶工", "快速跟进", "关键路径"]):
            issues.append(Issue(
                severity="medium",
                action_priority="must",
                title="进度题缺少延期处理",
                details="正文没有明显回应进度偏差或延期时的处理办法。",
                suggestion="补充进度延迟场景，并写出赶工、快速跟进、资源调整或范围协商等纠偏措施。",
            ))
        return issues

    def _cost_issues(self, context: ReviewContext) -> list[Issue]:
        text = context.parsed.text
        issues: list[Issue] = []
        if not any(token in text for token in ["预算形成", "预算", "成本基准", "资金"]):
            issues.append(Issue(
                severity="high",
                action_priority="must",
                title="成本题缺少预算形成过程",
                details="成本管理题的核心之一是预算形成和成本基准，当前表达不足。",
                suggestion="补充成本估算、汇总形成预算、管理储备和成本基准确定过程。",
            ))
        if not any(token in text for token in ["挣值", "偏差", "S曲线", "成本控制"]):
            issues.append(Issue(
                severity="medium",
                action_priority="should",
                title="成本题控制手段偏弱",
                details="正文缺少成本监控和偏差分析的具体方法。",
                suggestion="补充挣值分析、成本偏差、趋势分析或 S 曲线等控制手段，并说明如何纠偏。",
            ))
        return issues

    def _quality_issues(self, context: ReviewContext) -> list[Issue]:
        text = context.parsed.text
        issues: list[Issue] = []
        if "质量保证" not in text:
            issues.append(Issue(
                severity="high",
                action_priority="must",
                title="质量题缺少质量保证展开",
                details="质量管理题通常会重点考查质量保证，当前正文未明显展开。",
                suggestion="单独写质量保证段，说明评审、过程审计、QA 介入、制度落实等动作。",
            ))
        if "核对单" not in text:
            issues.append(Issue(
                severity="medium",
                action_priority="must",
                title="质量题缺少质量核对单",
                details="当前没有明显体现质量核对单或检查项。",
                suggestion="补充质量核对单的关键字段或重点检查项，如需求评审、测试覆盖、缺陷关闭、发布准入等。",
            ))
        return issues

    def _risk_issues(self, context: ReviewContext) -> list[Issue]:
        text = context.parsed.text
        issues: list[Issue] = []
        if "风险登记册" not in text:
            issues.append(Issue(
                severity="high",
                action_priority="must",
                title="风险题缺少风险登记册",
                details="风险管理题一般要求写出风险登记册及其逐步完善过程，当前未明显体现。",
                suggestion="补充风险登记册字段，如风险描述、原因、概率、影响、责任人、应对措施和状态。",
            ))
        if not any(token in text for token in ["定性", "概率", "影响矩阵"]):
            issues.append(Issue(
                severity="medium",
                action_priority="must",
                title="风险题缺少定性分析",
                details="正文未明显体现对风险进行概率-影响判断或排序。",
                suggestion="补充定性分析方法，如概率影响矩阵、紧迫性标识或优先级排序。",
            ))
        if not any(token in text for token in ["定量", "建模", "模拟", "储备"]):
            issues.append(Issue(
                severity="medium",
                action_priority="should",
                title="风险题缺少定量或储备思路",
                details="风险题深度部分通常需要写定量分析、储备或多方案应对，当前偏弱。",
                suggestion="补充定量分析、进度/成本储备、B 计划或关键风险量化例子。",
            ))
        return issues

    def _stakeholder_issues(self, context: ReviewContext) -> list[Issue]:
        text = context.parsed.text
        issues: list[Issue] = []
        if not any(token in text for token in ["权力/利益方格", "权力", "利益方格"]):
            issues.append(Issue(
                severity="high",
                action_priority="must",
                title="干系人题缺少权力/利益分析",
                details="干系人管理题高频要求对干系人按权力/利益进行分类分析，当前未明显体现。",
                suggestion="列出关键干系人，按权力/利益方格分类，并给出差异化管理策略。",
            ))
        if not any(token in text for token in ["沟通管理", "需求管理", "区别", "联系"]):
            issues.append(Issue(
                severity="medium",
                action_priority="must",
                title="干系人题对子问响应不足",
                details="正文没有明显回应干系人管理与沟通管理、需求管理的联系和区别。",
                suggestion="单独补一段比较三者关系，说明对象、目标和管理重点的差异。",
            ))
        return issues

    def _contract_issues(self, context: ReviewContext) -> list[Issue]:
        text = context.parsed.text
        issues: list[Issue] = []
        if not any(token in text for token in ["索赔流程", "索赔", "监理"]):
            issues.append(Issue(
                severity="high",
                action_priority="must",
                title="合同题缺少索赔流程",
                details="合同管理题常要求在有监理参与情况下描述索赔流程，当前未明确响应。",
                suggestion="补充变更提出、监理审查、审批、通知和实施等索赔或变更流程。",
            ))
        if not any(token in text for token in ["合同条款", "付款", "违约", "验收条款"]):
            issues.append(Issue(
                severity="medium",
                action_priority="must",
                title="合同题主要条款内容不足",
                details="正文未明显体现合同主要条款结构。",
                suggestion="补充范围、工期、质量、付款、验收、违约责任和变更条款等主要内容。",
            ))
        return issues

    def _delivery_issues(self, context: ReviewContext) -> list[Issue]:
        text = context.parsed.text
        issues: list[Issue] = []
        if not any(token in text for token in ["业务目标", "价值", "收益兑现", "收益"]):
            issues.append(Issue(
                severity="high",
                action_priority="must",
                title="交付绩效域缺少业务价值表达",
                details="交付绩效域重点是成果和业务目标一致，当前价值表达不足。",
                suggestion="补充项目交付物如何支撑业务目标、预期收益和最终实现效果。",
            ))
        if not any(token in text for token in ["协同", "其他绩效域", "过程组"]):
            issues.append(Issue(
                severity="medium",
                action_priority="must",
                title="交付绩效域缺少协同关系",
                details="正文未明显回应交付绩效域与其他绩效域或过程组的协同。",
                suggestion="补充启动、规划、执行、监控、收尾各阶段与干系人、规划、工作、不确定性等绩效域的协同目标。",
            ))
        if not any(token in text for token in ["测量指标", "指标", "满意度", "验收标准"]):
            issues.append(Issue(
                severity="medium",
                action_priority="must",
                title="交付绩效域缺少测量指标",
                details="题目往往要求给出交付绩效域测量指标，当前未充分体现。",
                suggestion="补充需求稳定性、验收通过率、缺陷数、满意度、收益实现率等指标。",
            ))
        return issues

    def _uncertainty_issues(self, context: ReviewContext) -> list[Issue]:
        text = context.parsed.text
        issues: list[Issue] = []
        if not any(token in text for token in ["模糊性", "复杂性", "风险"]):
            issues.append(Issue(
                severity="high",
                action_priority="must",
                title="不确定性绩效域要素覆盖不足",
                details="正文没有完整体现风险、模糊性和复杂性这几个不确定性来源。",
                suggestion="明确区分风险、模糊性、复杂性，并分别写识别和应对方式。",
            ))
        if not any(token in text for token in ["其他7个绩效域", "相关关系", "干系人绩效域", "团队绩效域"]):
            issues.append(Issue(
                severity="medium",
                action_priority="must",
                title="不确定性绩效域缺少与其他绩效域关系",
                details="题目常要求描述与其他绩效域的相互作用，当前未明显响应。",
                suggestion="补充不确定性与干系人、团队、规划、工作、交付、度量等绩效域的关系。",
            ))
        if not any(token in text for token in ["储备", "机会", "威胁", "B计划"]):
            issues.append(Issue(
                severity="medium",
                action_priority="should",
                title="不确定性应对策略偏弱",
                details="正文缺少储备、机会利用或备选方案等高级应对策略。",
                suggestion="补充管理储备、应急储备、机会利用和备选方案设计。",
            ))
        return issues

    def _measurement_issues(self, context: ReviewContext) -> list[Issue]:
        text = context.parsed.text
        issues: list[Issue] = []
        if not any(token in text for token in ["度量指标", "KPI", "指标"]):
            issues.append(Issue(
                severity="high",
                action_priority="must",
                title="度量绩效域缺少指标体系",
                details="度量绩效域核心是建立有效指标，当前未形成清晰指标体系。",
                suggestion="列出计划值、实际值、阈值、预警值和展示方式，说明如何服务决策。",
            ))
        if not any(token in text for token in ["预测", "预警", "偏差分析", "趋势分析"]):
            issues.append(Issue(
                severity="medium",
                action_priority="must",
                title="度量绩效域缺少诊断与预警",
                details="正文未明显体现基于度量结果进行诊断和行动。",
                suggestion="补充偏差分析、趋势分析、预警阈值和基于数据的纠偏动作。",
            ))
        return issues

    def _planning_issues(self, context: ReviewContext) -> list[Issue]:
        text = context.parsed.text
        issues: list[Issue] = []
        if "项目管理计划" not in text:
            issues.append(Issue(
                severity="high",
                action_priority="must",
                title="规划绩效域缺少项目管理计划主线",
                details="规划绩效域应围绕项目管理计划及其子计划展开，当前主线不清楚。",
                suggestion="按范围、进度、成本、资源、沟通、采购、变更和度量等规划内容组织正文。",
            ))
        if not any(token in text for token in ["基准", "估算", "滚动式规划", "变更控制"]):
            issues.append(Issue(
                severity="medium",
                action_priority="must",
                title="规划绩效域关键抓手不足",
                details="正文缺少基准、估算、规划调整和变更控制等规划抓手。",
                suggestion="补充基准建立、估算方法、滚动式规划和变更控制机制。",
            ))
        return issues

    def _work_pd_issues(self, context: ReviewContext) -> list[Issue]:
        text = context.parsed.text
        issues: list[Issue] = []
        if not any(token in text for token in ["状态报告", "过程审计", "资源利用率", "变更日志"]):
            issues.append(Issue(
                severity="high",
                action_priority="must",
                title="工作绩效域缺少执行监控抓手",
                details="工作绩效域重点是执行中的过程、资源、采购、沟通和变更控制，当前缺少监控抓手。",
                suggestion="补充状态报告、过程审计、资源利用率、采购审计、变更日志等执行监控机制。",
            ))
        if not any(token in text for token in ["持续改进", "经验教训", "知识管理", "学习"]):
            issues.append(Issue(
                severity="medium",
                action_priority="should",
                title="工作绩效域缺少持续改进",
                details="正文未明显体现学习、复盘和持续改进。",
                suggestion="补充经验教训沉淀、复盘机制和流程优化动作。",
            ))
        return issues
