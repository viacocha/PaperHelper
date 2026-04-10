import { useState } from "react";
import type { StandardOption } from "../types/review";

type UploadFormProps = {
  standards: StandardOption[];
  loading: boolean;
  onSubmit: (file: File, standardId: string) => Promise<void>;
};

export function UploadForm({ standards, loading, onSubmit }: UploadFormProps) {
  const [file, setFile] = useState<File | null>(null);
  const [standardId, setStandardId] = useState<string>("");
  const [error, setError] = useState<string>("");

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("请先选择一份 .docx 论文。");
      return;
    }

    setError("");
    await onSubmit(file, standardId);
  }

  return (
    <form className="panel" onSubmit={handleSubmit}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">PaperHelper</p>
          <h1>自动论文批改</h1>
        </div>
        <p className="muted">
          按高项论文标准库检查结构、题意、过程、专属产物与通过风险。
        </p>
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

      <label className="field upload-box">
        <span>上传论文 Word</span>
        <input
          type="file"
          accept=".docx"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
        <small>{file ? `已选择：${file.name}` : "仅支持 .docx 文件"}</small>
      </label>

      {error ? <div className="error">{error}</div> : null}

      <button className="primary-button" type="submit" disabled={loading}>
        {loading ? "批改中..." : "开始批改"}
      </button>
    </form>
  );
}
