import { ChangeDetectionStrategy, Component, ViewEncapsulation, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { ReviewerApi } from '../../core/api.service';
import { ReviewFinding, ReviewJob, ReviewResult, Severity } from '../../core/models';
import { Icon } from '../../shared/icon';
import { SmartSelect, SmartSelectOption } from '../../shared/smart-select';

@Component({
  selector: 'app-review-results-page',
  imports: [FormsModule, RouterLink, Icon, SmartSelect],
  templateUrl: './review-results.html',
  styleUrl: './review-results.scss',
  encapsulation: ViewEncapsulation.None,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReviewResultsPage {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(ReviewerApi);

  readonly jobId = this.route.snapshot.paramMap.get('jobId') ?? '';
  readonly job = signal<ReviewJob | null>(null);
  readonly result = signal<ReviewResult | null>(null);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly severity = signal<'all' | Severity>('all');
  readonly source = signal<'all' | 'static' | 'llm' | 'framework'>('all');
  readonly search = signal('');
  readonly project = signal('all');
  readonly rule = signal('all');
  readonly expanded = signal<Set<string>>(new Set());
  readonly rejectedOpen = signal(false);
  readonly copyStatus = signal('');
  readonly severities: Severity[] = ['critical', 'high', 'medium', 'low'];
  readonly ruleOptions = computed(() => [{ value: 'all', label: 'All rules' },
    ...[...new Set((this.result()?.findings ?? []).map(f => f.rule_id))].sort().map(value => ({ value, label: value }))]);
  readonly projectOptions = computed(() => [{ value: 'all', label: 'All projects' },
    ...[...new Set((this.result()?.findings ?? []).map(f => this.findingProject(f)))].sort().map(value => ({ value, label: value }))]);

  findingProject(finding: ReviewFinding): string {
    const path = finding.file_path.replaceAll('\\', '/');
    const projects = Object.keys(this.result()?.diagnostics.review_files_by_project ?? {});
    return projects.filter(p => p !== '.' && (path === p || path.startsWith(p + '/')))
      .sort((a, b) => b.length - a.length)[0] ?? (path.includes('/') ? path.split('/')[0] : 'Root');
  }
  findingKey(finding: ReviewFinding): string {
    return `${finding.file_path}:${finding.line_number}:${finding.rule_id}`;
  }
  isExpanded(finding: ReviewFinding): boolean { return this.expanded().has(this.findingKey(finding)); }
  toggleFinding(finding: ReviewFinding): void {
    const key = this.findingKey(finding);
    this.expanded.update(current => { const next = new Set(current); next.has(key) ? next.delete(key) : next.add(key); return next; });
  }
  filename(path: string): string { return path.replaceAll('\\', '/').split('/').pop() ?? path; }
  severityCount(severity: Severity): number { return this.result()?.quality_gate[`${severity}_count`] ?? 0; }
  durationLabel(): string {
    const seconds = Math.max(0, Math.round(this.result()?.diagnostics.total_review_seconds ?? 0));
    return `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`;
  }
  evidenceLines(finding: ReviewFinding): { number: number | null; text: string }[] {
    return (finding.evidence ?? '').split('\n').map((text, index) => {
      const match = text.match(/^\s*(\d+)\s+(.*)$/);
      return match ? { number: Number(match[1]), text: match[2] } : { number: index === 0 ? finding.line_number : null, text };
    });
  }
  async copyJobId(): Promise<void> {
    const id = this.job()?.id;
    if (!id) return;
    try { await navigator.clipboard.writeText(id); this.copyStatus.set('Job ID copied'); }
    catch { this.copyStatus.set('Unable to copy job ID: ' + id); }
  }

  async copyEvidence(finding: ReviewFinding): Promise<void> {
    try { await navigator.clipboard.writeText(finding.evidence ?? ''); this.copyStatus.set('Evidence copied'); }
    catch { this.copyStatus.set('Unable to copy. Select the evidence text to copy it.'); }
  }

  readonly publishConfirmationOpen = signal(false);
  readonly publishing = signal(false);
  readonly severityOptions: SmartSelectOption[] = [
    { value: 'all', label: 'All severities' },
    { value: 'critical', label: 'Critical' },
    { value: 'high', label: 'High' },
    { value: 'medium', label: 'Medium' },
    { value: 'low', label: 'Low' },
    { value: 'suggestion', label: 'Suggestion' },
  ];
  readonly sourceOptions: SmartSelectOption[] = [
    { value: 'all', label: 'All sources' },
    { value: 'static', label: 'Static' },
    { value: 'framework', label: 'Framework' },
    { value: 'llm', label: 'AI semantic' },
  ];

  readonly prTitle = computed(
    () => this.result()?.pull_request?.title ?? this.job()?.result_summary?.title ?? '',
  );

  readonly repositoryName = computed(() => {
    const repo = this.result()?.pull_request?.repository ?? '';
    return repo.split('/').filter(Boolean).at(-1) ?? '';
  });

  readonly staticFindingCount = computed(() =>
    Math.max(0, this.totalFindings() - (this.result()?.diagnostics.final_ai_findings ?? 0)),
  );

  readonly hasActiveFilters = computed(
    () =>
      this.severity() !== 'all' ||
      this.source() !== 'all' ||
      this.project() !== 'all' ||
      this.rule() !== 'all' ||
      !!this.search().trim(),
  );

  decisionTone(): 'block' | 'pass' | 'warn' {
    const decision = this.result()?.quality_gate.decision;
    if (decision === 'block') return 'block';
    if (decision === 'pass') return 'pass';
    return 'warn';
  }

  decisionText(): string {
    const tone = this.decisionTone();
    if (tone === 'block') return 'Merge blocked';
    if (tone === 'pass') return 'Ready to merge';
    return 'Needs attention';
  }

  toggleSeverityFilter(level: Severity): void {
    this.severity.set(this.severity() === level ? 'all' : level);
  }

  clearFilters(): void {
    this.severity.set('all');
    this.source.set('all');
    this.project.set('all');
    this.rule.set('all');
    this.search.set('');
  }

  readonly visibleFindings = computed(() => {
    const severity = this.severity();
    const source = this.source();
    const search = this.search().trim().toLowerCase();
    return (this.result()?.findings ?? []).filter((finding) => {
      const matchesSeverity = severity === 'all' || finding.severity === severity;
      const matchesSource = source === 'all' || finding.source === source;
      const haystack =
        `${finding.file_path} ${finding.rule_id} ${finding.issue ?? finding.message}`.toLowerCase();
      return matchesSeverity && matchesSource && (this.project() === 'all' || this.findingProject(finding) === this.project()) && (this.rule() === 'all' || finding.rule_id === this.rule()) && (!search || haystack.includes(search));
    }).sort((a, b) => ['critical', 'high', 'medium', 'low', 'suggestion'].indexOf(a.severity) - ['critical', 'high', 'medium', 'low', 'suggestion'].indexOf(b.severity));
  });

  readonly totalFindings = computed(() => {
    const quality = this.result()?.quality_gate;
    if (!quality) return 0;
    return (
      quality.critical_count +
      quality.high_count +
      quality.medium_count +
      quality.low_count +
      quality.suggestion_count
    );
  });

  readonly rejectedAiFindings = computed(() =>
    Math.max(
      0,
      (this.result()?.diagnostics.raw_ai_findings ?? 0) -
        (this.result()?.diagnostics.final_ai_findings ?? 0),
    ),
  );

  constructor() {
    if (!this.jobId) {
      this.loading.set(false);
      this.error.set('No review job was specified.');
      return;
    }
    this.api.getReview(this.jobId).subscribe({
      next: (job) => {
        this.job.set(job);
        if (job.result) {
          this.result.set(job.result);
          const first = this.visibleFindings()[0];
          if (first) this.expanded.set(new Set([this.findingKey(first)]));
        } else if (job.status === 'queued' || job.status === 'running') {
          void this.router.navigate(['/reviews', job.id, 'progress']);
        } else {
          this.error.set(job.error ?? 'This review completed without a result payload.');
        }
        this.loading.set(false);
      },
      error: (error) => {
        this.loading.set(false);
        this.error.set(error?.error?.detail ?? 'Unable to load the review result.');
      },
    });
  }

  gateDescription(): string {
    const quality = this.result()?.quality_gate;
    if (!quality) return '';
    if (quality.decision === 'pass') return 'No reportable issues were found. This PR passed the quality gate.';
    if (quality.decision === 'block') {
      const count = quality.critical_count || quality.high_count;
      const level = quality.critical_count ? 'critical' : 'high';
      return `${count} ${level} issue${count === 1 ? '' : 's'} must be resolved before this PR can be merged.`;
    }
    return 'Review the findings and merge recommendation before merging this PR.';
  }

  decisionLabel(): string {
    return (this.result()?.quality_gate.decision ?? 'unknown').replaceAll('_', ' ').toUpperCase();
  }

  completedLabel(): string {
    const timestamp = this.job()?.completed_at;
    if (!timestamp) return '—';
    return new Date(timestamp).toLocaleString([], {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  severityIcon(severity: Severity): string {
    if (severity === 'critical') return 'circle-alert';
    if (severity === 'high') return 'circle-arrow-up';
    if (severity === 'medium') return 'triangle-alert';
    if (severity === 'low') return 'info';
    return 'sparkles';
  }

  findingIssue(finding: ReviewFinding): string {
    return finding.issue ?? finding.message;
  }

  setSeverity(value: string): void {
    if (['all', 'critical', 'high', 'medium', 'low', 'suggestion'].includes(value)) {
      this.severity.set(value as 'all' | Severity);
    }
  }

  setSource(value: string): void {
    if (['all', 'static', 'llm', 'framework'].includes(value)) {
      this.source.set(value as 'all' | 'static' | 'llm' | 'framework');
    }
  }

  downloadJson(): void {
    const result = this.result();
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `review-${result.pull_request.number}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  publish(): void {
    const current = this.result();
    if (!current) {
      this.error.set('The review result is unavailable.');
      return;
    }
    this.publishConfirmationOpen.set(false);
    this.publishing.set(true);
    this.api
      .startReview({
        provider: current.pull_request.provider,
        repository: current.pull_request.repository,
        pull_number: current.pull_request.number,
        review_depth: current.diagnostics.review_depth,
        publish: true,
      })
      .subscribe({
        next: (job) => void this.router.navigate(['/reviews', job.id, 'progress']),
        error: (error) => {
          this.publishing.set(false);
          this.error.set(error?.error?.detail ?? 'The publish review could not be started.');
        },
      });
  }
}
