import type { CompareResult, Issue } from "../types/review";
import { reportDownloadUrl } from "../lib/api";

type CompareViewProps = {
  comparison: CompareResult;
};

export function CompareView({ comparison }: CompareViewProps) {
  return (
    <section className="result-stack">
      <div className="panel highlight">
        <div className="score-band">
          <div>
            <p className="eyebrow">对比结果</p>
            <h2>{comparison.summary}</h2>
            <p className="muted">
              修改前 {comparison.original.total_score} 分，修改后 {comparison.revised.total_score} 分。
              {comparison.pass_probability_changed ? "通过风险等级已变化。" : "通过风险等级未变化。"}
            </p>
          </div>
          <div className="score-card">
            <span>分数变化</span>
            <strong>{comparison.score_delta > 0 ? `+${comparison.score_delta}` : comparison.score_delta}</strong>
            <small>目标通过线 {comparison.revised.pass_score}</small>
          </div>
        </div>
        <a className="download-link" href={reportDownloadUrl(comparison.compare_report_name)}>
          下载二次对比 Word
        </a>
      </div>

      <div className="grid three-columns">
        <IssueColumn title="已修复问题" items={comparison.fixed_issues} emptyText="暂未检测到已修复问题。" />
        <IssueColumn title="仍未解决" items={comparison.remaining_issues} emptyText="没有旧问题残留。" />
        <IssueColumn title="新增问题" items={comparison.new_issues} emptyText="没有新增问题。" />
      </div>
    </section>
  );
}

function IssueColumn({ title, items, emptyText }: { title: string; items: Issue[]; emptyText: string }) {
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
