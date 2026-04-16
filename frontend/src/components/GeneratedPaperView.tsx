import { reportDownloadUrl } from "../lib/api";
import type { GeneratedPaper } from "../types/review";

type GeneratedPaperViewProps = {
  paper: GeneratedPaper;
};

export function GeneratedPaperView({ paper }: GeneratedPaperViewProps) {
  return (
    <section className="result-stack">
      <div className="panel highlight">
        <div className="score-band">
          <div>
            <p className="eyebrow">生成结果</p>
            <h2>{paper.title}</h2>
            <p className="muted">
              题型：{paper.standard.standard_name} · 约 {paper.word_count} 字 · 最低要求 {paper.minimum_word_count} 字
            </p>
          </div>
          <a className="download-link" href={reportDownloadUrl(paper.generated_report_name)}>
            下载论文初稿 Word
          </a>
        </div>
      </div>

      <div className="panel">
        <h3>初稿预览</h3>
        <div className="generated-paper">
          {paper.paragraphs.map((paragraph, index) => (
            <p key={index}>{paragraph}</p>
          ))}
        </div>
      </div>
    </section>
  );
}
