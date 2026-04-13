import { useState } from "react";
import type { StandardOption } from "../types/review";

type GenerateFormProps = {
  standards: StandardOption[];
  loading: boolean;
  onSubmit: (projectBackground: string, standardId: string) => Promise<void>;
};

export function GenerateForm({ standards, loading, onSubmit }: GenerateFormProps) {
  const [projectBackground, setProjectBackground] = useState("");
  const [standardId, setStandardId] = useState("");
  const [error, setError] = useState("");

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!standardId) {
      setError("请选择要生成的论文题型。");
      return;
    }
    if (projectBackground.trim().length < 80) {
      setError("项目背景信息太少，请至少写清项目目标、周期、本人角色、模块和交付成果。");
      return;
    }

    setError("");
    await onSubmit(projectBackground, standardId);
  }

  return (
    <form className="panel" onSubmit={handleSubmit}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">Paper Draft</p>
          <h2>自动生成论文初稿</h2>
        </div>
        <p className="muted">输入项目背景和论文题型，生成一篇信息系统项目管理师论文初稿 Word。</p>
      </div>

      <label className="field">
        <span>论文题型</span>
        <select value={standardId} onChange={(event) => setStandardId(event.target.value)}>
          <option value="">请选择题型</option>
          {standards.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name} · {item.category === "knowledge_area" ? "十大知识域" : "八大绩效域"}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span>项目背景信息</span>
        <textarea
          className="textarea"
          value={projectBackground}
          onChange={(event) => setProjectBackground(event.target.value)}
          rows={8}
          placeholder="例如：2025年3月，我担任某市智慧政务平台建设项目的乙方项目经理，合同金额820万元，建设周期11个月，主要模块包括统一门户、在线审批、数据交换、统计分析等..."
        />
      </label>

      {error ? <div className="error">{error}</div> : null}

      <button className="primary-button" type="submit" disabled={loading}>
        {loading ? "生成中..." : "生成论文初稿"}
      </button>
    </form>
  );
}
