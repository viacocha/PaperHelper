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
  action_priority: "must" | "should" | "could";
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

export type RevisionTemplate = {
  title: string;
  purpose: string;
  when_to_use: string;
  outline: string[];
  sample: string;
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
  must_fix: Issue[];
  should_fix: Issue[];
  could_improve: Issue[];
  revision_templates: RevisionTemplate[];
  paragraph_reviews: ParagraphReview[];
  suggested_report_name: string;
};
