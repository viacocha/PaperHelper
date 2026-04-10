export type StandardOption = {
  id: string;
  name: string;
  category: string;
};

export type CriterionScore = {
  id: string;
  name: string;
  score: number;
  max_score: number;
  summary: string;
};

export type Issue = {
  severity: "high" | "medium" | "low";
  title: string;
  details: string;
  suggestion: string;
  paragraph_index?: number | null;
};

export type ParagraphReview = {
  index: number;
  excerpt: string;
  strengths: string[];
  issues: string[];
  suggestions: string[];
};

export type ReviewResult = {
  filename: string;
  standard: {
    standard_id: string;
    standard_name: string;
    category: string;
    confidence: number;
  };
  total_score: number;
  pass_score: number;
  pass_probability: "high" | "medium" | "low";
  summary: string;
  dimensions: CriterionScore[];
  issues: Issue[];
  paragraph_reviews: ParagraphReview[];
  suggested_report_name: string;
};
