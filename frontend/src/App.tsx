import { useEffect, useState } from "react";
import { CompareForm } from "./components/CompareForm";
import { CompareView } from "./components/CompareView";
import { GeneratedPaperView } from "./components/GeneratedPaperView";
import { GenerateForm } from "./components/GenerateForm";
import { ResultView } from "./components/ResultView";
import { UploadForm } from "./components/UploadForm";
import { compareEssays, fetchStandards, generatePaper, reviewEssay } from "./lib/api";
import type { CompareResult, GeneratedPaper, ReviewResult, StandardOption } from "./types/review";

export default function App() {
  const [standards, setStandards] = useState<StandardOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const [error, setError] = useState("");
  const [review, setReview] = useState<ReviewResult | null>(null);
  const [comparison, setComparison] = useState<CompareResult | null>(null);
  const [generatedPaper, setGeneratedPaper] = useState<GeneratedPaper | null>(null);

  useEffect(() => {
    fetchStandards()
      .then(setStandards)
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setInitializing(false));
  }, []);

  async function handleSubmit(file: File, standardId: string) {
    try {
      setLoading(true);
      setError("");
      const result = await reviewEssay(file, standardId);
      setReview(result);
      setComparison(null);
      setGeneratedPaper(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "批改失败。");
    } finally {
      setLoading(false);
    }
  }

  async function handleCompare(originalFile: File, revisedFile: File, standardId: string) {
    try {
      setLoading(true);
      setError("");
      const result = await compareEssays(originalFile, revisedFile, standardId);
      setComparison(result);
      setReview(null);
      setGeneratedPaper(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "对比失败。");
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerate(projectBackground: string, standardId: string) {
    try {
      setLoading(true);
      setError("");
      const result = await generatePaper(projectBackground, standardId);
      setGeneratedPaper(result);
      setReview(null);
      setComparison(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "生成失败。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <section className="hero">
        <div>
          <p className="eyebrow">PaperHelper</p>
          <h1>软考高项论文自动批改工具</h1>
          <p className="hero-copy">
            围绕十大知识域、八大绩效域和历年高频子题，检查论文是否具备通过结构，并生成建议版 Word。
          </p>
        </div>
      </section>

      {error ? <div className="banner error">{error}</div> : null}
      {initializing ? (
        <div className="panel">正在加载标准库...</div>
      ) : (
        <>
          <GenerateForm standards={standards} loading={loading} onSubmit={handleGenerate} />
          <UploadForm standards={standards} loading={loading} onSubmit={handleSubmit} />
          <CompareForm standards={standards} loading={loading} onSubmit={handleCompare} />
        </>
      )}

      {generatedPaper ? <GeneratedPaperView paper={generatedPaper} /> : null}
      {review ? <ResultView review={review} /> : null}
      {comparison ? <CompareView comparison={comparison} /> : null}
    </main>
  );
}
