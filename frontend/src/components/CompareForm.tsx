import { useState } from "react";
import type { StandardOption } from "../types/review";

type CompareFormProps = {
  standards: StandardOption[];
  loading: boolean;
  onSubmit: (originalFile: File, revisedFile: File, standardId: string) => Promise<void>;
};

export function CompareForm({ standards, loading, onSubmit }: CompareFormProps) {
  const [originalFile, setOriginalFile] = useState<File | null>(null);
  const [revisedFile, setRevisedFile] = useState<File | null>(null);
  const [standardId, setStandardId] = useState("");
  const [error, setError] = useState("");

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!originalFile || !revisedFile) {
      setError("请同时选择修改前和修改后的 .docx 文件。");
      return;
    }

    setError("");
    await onSubmit(originalFile, revisedFile, standardId);
  }

  return (
    <form className="panel" onSubmit={handleSubmit}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">Second Pass</p>
          <h2>二次批改对比</h2>
        </div>
        <p className="muted">上传修改前后两份论文，查看分数变化、已修复问题和仍未解决的问题。</p>
      </div>

      <label className="field">
        <span>论文题型</span>
        <select value={standardId} onChange={(event) => setStandardId(event.target.value)}>
          <option value="">自动识别</option>
          {standards.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name} · {item.category === "knowledge_area" ? "十大知识域" : "八大绩效域"}
            </option>
          ))}
        </select>
      </label>

      <div className="grid two-columns">
        <label className="field upload-box">
          <span>修改前论文</span>
          <input type="file" accept=".docx" onChange={(event) => setOriginalFile(event.target.files?.[0] ?? null)} />
          <small>{originalFile ? originalFile.name : "选择原始版本 .docx"}</small>
        </label>
        <label className="field upload-box">
          <span>修改后论文</span>
          <input type="file" accept=".docx" onChange={(event) => setRevisedFile(event.target.files?.[0] ?? null)} />
          <small>{revisedFile ? revisedFile.name : "选择修改版本 .docx"}</small>
        </label>
      </div>

      {error ? <div className="error">{error}</div> : null}

      <button className="primary-button" type="submit" disabled={loading}>
        {loading ? "对比中..." : "开始对比"}
      </button>
    </form>
  );
}
