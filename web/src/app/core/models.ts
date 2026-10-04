export type ProviderId = 'github' | 'azure-devops';
export type ReviewDepth = 'fast' | 'standard' | 'deep';
export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'suggestion';

export interface ProviderStatus {
  id: ProviderId;
  name: string;
  connected: boolean;
  repository_format: string;
}

export interface HealthResponse {
  status: string;
  version: string;
  providers: ProviderStatus[];
  ollama: {
    configured: boolean;
    ready: boolean | null;
    model: string;
    base_url: string;
  };
}

export interface PullRequestSummary {
  number: number;
  title: string;
  author: string;
  base_branch: string;
  head_branch: string;
  state: string;
  changed_files?: number | null;
  updated_at?: string;
  review_status?: 'awaiting' | 'blocked' | 'passed';
}

export interface PullRequestListResponse {
  provider: ProviderId;
  repository: string;
  items: PullRequestSummary[];
  total: number;
}

export interface PullRequestDetail extends PullRequestSummary {
  provider: ProviderId;
  repository: string;
  head_commit: string;
  description?: string;
}

export interface ChangedFileSummary {
  file_path: string;
  status: string;
  language: string | null;
  changed_line_count: number;
  additions?: number;
  deletions?: number;
}

export interface ChangedFileListResponse {
  items: ChangedFileSummary[];
  total: number;
}

export interface ReviewCreateRequest {
  provider: ProviderId;
  repository: string;
  pull_number: number;
  review_depth: ReviewDepth;
  publish: boolean;
  max_workers?: number;
}

export interface ReviewStep {
  key: string;
  label: string;
  state: 'pending' | 'active' | 'complete' | 'failed' | 'cancelled';
  message: string | null;
  updated_at: string | null;
}

export interface ReviewFinding {
  file_path: string;
  line_number: number;
  severity: Severity;
  rule_id: string;
  message: string;
  suggestion: string | null;
  source: string;
  category: string | null;
  issue: string | null;
  impact: string | null;
  evidence: string | null;
  confidence: string | null;
}

export interface QualityGate {
  decision: string;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  suggestion_count: number;
  total_findings?: number;
}

export interface ReviewDiagnostics {
  changed_files: number;
  ai_review_files: number;
  review_batches: number;
  skipped_files: number;
  context_only_files: number;
  semantic_skipped_files: number;
  review_depth: ReviewDepth;
  skipped_by_category: Record<string, number>;
  skipped_by_reason: Record<string, number>;
  review_files_by_project: Record<string, number>;
  planned_llm_calls: number;
  actual_llm_calls: number;
  llm_retries: number;
  failed_llm_parts: number;
  llm_prompt_tokens: number;
  llm_generated_tokens: number;
  raw_ai_findings: number;
  final_ai_findings: number;
  static_analysis_seconds: number;
  llm_review_seconds: number;
  total_review_seconds: number;
}

export interface ReviewResult {
  pull_request: PullRequestDetail;
  findings: ReviewFinding[];
  quality_gate: QualityGate;
  publishing: {
    published_comments: unknown[];
    skipped_duplicates: number;
    failed_comments: unknown[];
    summary_only_findings: number;
    grouped_findings: number;
    rate_limited: boolean;
  };
  summary_publishing: { action: string; comment: Record<string, unknown> } | null;
  dry_run: boolean;
  diagnostics: ReviewDiagnostics;
  summary_publishing_failure: string | null;
}

export interface ReviewJob {
  id: string;
  command: ReviewCreateRequest;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  phase: string;
  progress: number;
  message: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  result?: ReviewResult | null;
  result_summary?: {
    title: string | null;
    author: string | null;
    decision: string | null;
    findings: number;
    duration_seconds: number | null;
    dry_run: boolean;
  } | null;
  steps: ReviewStep[];
}

export interface ReviewListResponse {
  items: ReviewJob[];
  total: number;
}
