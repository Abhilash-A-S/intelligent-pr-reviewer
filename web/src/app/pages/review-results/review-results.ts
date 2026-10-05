import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { ReviewerApi } from '../../core/api.service';
import { ReviewFinding, ReviewJob, ReviewResult, Severity } from '../../core/models';
import { Icon } from '../../shared/icon';
import { SmartSelect, SmartSelectOption } from '../../shared/smart-select';

@Component({
  selector: 'app-review-results-page',
  imports: [DecimalPipe, FormsModule, RouterLink, Icon, SmartSelect],
  templateUrl: './review-results.html',
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

  readonly visibleFindings = computed(() => {
    const severity = this.severity();
    const source = this.source();
    const search = this.search().trim().toLowerCase();
    return (this.result()?.findings ?? []).filter((finding) => {
      const matchesSeverity = severity === 'all' || finding.severity === severity;
      const matchesSource = source === 'all' || finding.source === source;
      const haystack =
        `${finding.file_path} ${finding.rule_id} ${finding.issue ?? finding.message}`.toLowerCase();
      return matchesSeverity && matchesSource && (!search || haystack.includes(search));
    });
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
    if (severity === 'critical' || severity === 'high') return 'octagon-alert';
    if (severity === 'medium') return 'triangle-alert';
    if (severity === 'low') return 'circle-alert';
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
