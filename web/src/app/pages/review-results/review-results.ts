import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { ReviewerApi } from '../../core/api.service';
import { DEMO_JOB, DEMO_RESULT } from '../../core/demo-data';
import { ReviewFinding, ReviewJob, ReviewResult, Severity } from '../../core/models';
import { Icon } from '../../shared/icon';

@Component({
  selector: 'app-review-results-page',
  imports: [DecimalPipe, FormsModule, RouterLink, Icon],
  templateUrl: './review-results.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReviewResultsPage {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(ReviewerApi);

  readonly jobId = this.route.snapshot.paramMap.get('jobId') ?? 'demo';
  readonly job = signal<ReviewJob>({ ...DEMO_JOB, id: this.jobId, status: 'completed', result: DEMO_RESULT });
  readonly result = signal<ReviewResult>(DEMO_RESULT);
  readonly loading = signal(this.jobId !== 'demo');
  readonly error = signal<string | null>(null);
  readonly severity = signal<'all' | Severity>('all');
  readonly source = signal<'all' | 'static' | 'llm' | 'framework'>('all');
  readonly search = signal('');
  readonly publishConfirmationOpen = signal(false);
  readonly publishing = signal(false);

  readonly visibleFindings = computed(() => {
    const severity = this.severity();
    const source = this.source();
    const search = this.search().trim().toLowerCase();
    return this.result().findings.filter((finding) => {
      const matchesSeverity = severity === 'all' || finding.severity === severity;
      const matchesSource = source === 'all' || finding.source === source;
      const haystack = `${finding.file_path} ${finding.rule_id} ${finding.issue ?? finding.message}`.toLowerCase();
      return matchesSeverity && matchesSource && (!search || haystack.includes(search));
    });
  });

  readonly totalFindings = computed(() => {
    const quality = this.result().quality_gate;
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
      this.result().diagnostics.raw_ai_findings - this.result().diagnostics.final_ai_findings,
    ),
  );

  constructor() {
    if (this.jobId !== 'demo') {
      this.api.getReview(this.jobId).subscribe({
        next: (job) => {
          this.job.set(job);
          if (job.result) this.result.set(job.result);
          this.loading.set(false);
        },
        error: (error) => {
          this.loading.set(false);
          this.error.set(error?.error?.detail ?? 'Unable to load the review result.');
        },
      });
    }
  }

  decisionLabel(): string {
    return this.result().quality_gate.decision.replaceAll('_', ' ').toUpperCase();
  }

  completedLabel(): string {
    const timestamp = this.job().completed_at;
    if (!timestamp) return 'just now';
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

  downloadJson(): void {
    const blob = new Blob([JSON.stringify(this.result(), null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `review-${this.result().pull_request.number}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  publish(): void {
    const current = this.result();
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
