import type { ReviewResult } from "../types/review";
import { reportDownloadUrl } from "../lib/api";

type ResultViewProps = {
  review: ReviewResult;
};

export function ResultView({ review }: ResultViewProps) {
  return (
    <section className="result-stack">
      <div className="panel highlight">
        <div className="score-band">
          <div>
            <p className="eyebrow">批改结果</p>
            <h2>{review.filename}</h2>
            <p className="muted">{review.summary}</p>
          </div>
          <div className="score-card">
            <span>总分</span>
            <strong>{review.total_score}</strong>
            <small>通过线 {review.pass_score}</small>
          </div>
        </div>
        <div className="result-meta">
          <span>题型：{review.standard.standard_name}</span>
          <span>类型：{review.standard.category === "knowledge_area" ? "十大知识域" : "八大绩效域"}</span>
          <span>通过判断：{label(review.pass_probability)}</span>
        </div>
        <a className="download-link" href={reportDownloadUrl(review.suggested_report_name)}>
          下载批注版改后 Word
        </a>
      </div>

      <div className="grid two-columns">
        <div className="panel">
          <h3>分项评分</h3>
          <ul className="metric-list">
            {review.dimensions.map((item) => (
              <li key={item.id}>
                <div className="metric-head">
                  <span>{item.name}</span>
                  <strong>
                    {item.score} / {item.max_score}
                  </strong>
                </div>
                <p>{item.summary}</p>
              </li>
            ))}
          </ul>
        </div>

        <div className="panel">
          <h3>题型评分卡</h3>
          <ul className="metric-list">
            {review.topic_scorecard.map((item, index) => (
              <li key={`${item.title}-${index}`} className={`scorecard-${item.status}`}>
                <div className="metric-head">
                  <span>{item.title}</span>
                  <strong>
                    {item.score} / {item.max_score}
                  </strong>
                </div>
                <p>{item.summary}</p>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="panel">
        <h3>主要问题</h3>
        <ul className="issue-list">
          {review.issues.length ? (
            review.issues.map((item, index) => (
              <li key={`${item.title}-${index}`} className={`severity-${item.severity}`}>
                <strong>{item.title}</strong>
                <p>{item.details}</p>
                <p>建议：{item.suggestion}</p>
              </li>
            ))
          ) : (
            <li>未检测到明显高风险问题。</li>
          )}
        </ul>
      </div>

      <div className="grid three-columns">
        <PriorityPanel title="必须补写" items={review.must_fix} emptyText="当前无必须补写项。" />
        <PriorityPanel title="建议补强" items={review.should_fix} emptyText="当前无建议补强项。" />
        <PriorityPanel title="可优化项" items={review.could_improve} emptyText="当前无可优化项。" />
      </div>

      <div className="panel">
        <h3>题型模板建议</h3>
        <div className="template-list">
          {review.revision_templates.map((item, index) => (
            <article key={`${item.title}-${index}`} className="template-card">
              <h4>{item.title}</h4>
              <p>用途：{item.purpose}</p>
              <p>适用场景：{item.when_to_use}</p>
              <p>补写结构：{item.outline.join("；")}</p>
              <p>示例写法：{item.sample}</p>
            </article>
          ))}
        </div>
      </div>

      <div className="panel">
        <h3>逐段建议</h3>
        <div className="paragraph-list">
          {review.paragraph_reviews.map((item) => (
            <article key={item.index} className="paragraph-card">
              <header>
                <strong>第 {item.index} 段</strong>
                <p>{item.excerpt}</p>
              </header>
              <p>优点：{item.strengths.length ? item.strengths.join("；") : "暂无明显亮点。"}</p>
              <p>问题：{item.issues.length ? item.issues.join("；") : "未发现明显问题。"}</p>
              <p>建议：{item.suggestions.length ? item.suggestions.join("；") : "保持当前写法，继续补充细节。"}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function label(value: ReviewResult["pass_probability"]): string {
  if (value === "high") {
    return "较高通过概率";
  }
  if (value === "medium") {
    return "接近通过，仍需修改";
  }
  return "当前通过风险高";
}

function PriorityPanel({
  title,
  items,
  emptyText
}: {
  title: string;
  items: ReviewResult["issues"];
  emptyText: string;
}) {
  return (
    <div className="panel">
      <h3>{title}</h3>
      <ul className="issue-list compact">
        {items.length ? (
          items.map((item, index) => (
            <li key={`${title}-${item.title}-${index}`} className={`severity-${item.severity}`}>
              <strong>{item.title}</strong>
              <p>{item.suggestion}</p>
            </li>
          ))
        ) : (
          <li>{emptyText}</li>
        )}
      </ul>
    </div>
  );
}
