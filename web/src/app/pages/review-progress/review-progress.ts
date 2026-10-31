import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ViewEncapsulation,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { catchError, EMPTY, interval, switchMap, takeWhile, tap, timer } from 'rxjs';

import { AuthService } from '../../core/auth.service';
import { ReviewerApi } from '../../core/api.service';
import { PullRequestDetail, ReviewEvent, ReviewJob, ReviewStep } from '../../core/models';
import { Icon } from '../../shared/icon';
import { SmartSelect, SmartSelectOption } from '../../shared/smart-select';

@Component({
  selector: 'app-review-progress-page',
  imports: [RouterLink, Icon, SmartSelect],
  templateUrl: './review-progress.html',
  styleUrl: './review-progress.scss',
  encapsulation: ViewEncapsulation.None,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReviewProgressPage {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly auth = inject(AuthService);
  private readonly api = inject(ReviewerApi);
  private readonly destroyRef = inject(DestroyRef);
  private readonly clock = signal(Date.now());

  readonly jobId = this.route.snapshot.paramMap.get('jobId') ?? '';
  readonly job = signal<ReviewJob | null>(null);
  readonly pullRequest = signal<PullRequestDetail | null>(null);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly cancelling = signal(false);
  readonly cancelConfirmationOpen = signal(false);
  readonly logsExpanded = signal(false);
  readonly copyStatus = signal('');
  readonly diagnosticFilter = signal('all');
  readonly diagnosticOptions: SmartSelectOption[] = [
    { value: 'all', label: 'All logs' },
    { value: 'discovery', label: 'Repository' },
    { value: 'static_analysis', label: 'Static analysis' },
    { value: 'ai_review', label: 'AI review' },
    { value: 'validation', label: 'Validation' },
    { value: 'publishing', label: 'Publishing' },
  ];
  readonly activityRingCircumference = 56.55;

  readonly isActive = computed(() => {
    const status = this.job()?.status;
    return status === 'running' || status === 'queued';
  });

  readonly pageTitle = computed(() => {
    switch (this.job()?.status) {
      case 'completed':
        return 'Review completed';
      case 'failed':
        return 'Review failed';
      case 'cancelled':
        return 'Review cancelled';
      case 'queued':
        return 'Review queued';
      default:
        return 'Review in progress';
    }
  });

  readonly repositoryName = computed(() => {
    const repo = this.job()?.command?.repository ?? '';
    return repo.split('/').at(-1) ?? repo;
  });

  readonly skippedCount = computed(() => {
    const changed = Number(this.changedFileCount());
    const review = Number(this.reviewFileCount());
    if (Number.isFinite(changed) && Number.isFinite(review) && changed > review) {
      return changed - review;
    }
    return 0;
  });

  readonly activeBatchInfo = computed(() => {
    const event = [...(this.job()?.events ?? [])]
      .reverse()
      .find((e) => e.phase === 'ai_review' && e.batch_index && e.batch_total);
    if (event?.batch_index && event.batch_total) {
      return {
        current: event.batch_index,
        total: event.batch_total,
        fileCount: event.files?.length ?? 0,
      };
    }
    return null;
  });

  readonly activitySteps = computed(() => {
    const activityKeys = new Set([
      'discovery',
      'static_analysis',
      'ai_review',
      'validation',
      'publishing',
    ]);
    return (this.job()?.steps ?? []).filter((step) => activityKeys.has(step.key));
  });

  readonly diagnosticEvents = computed(() => {
    const selected = this.diagnosticFilter();
    const events = this.job()?.events ?? [];
    return selected === 'all' ? events : events.filter((event) => event.phase === selected);
  });

  readonly elapsedSeconds = computed(() => {
    const job = this.job();
    if (!job) return 0;
    const start = job.started_at ? new Date(job.started_at).getTime() : new Date(job.created_at).getTime();
    const end = job.completed_at
      ? new Date(job.completed_at).getTime()
      : this.clock();
    return Math.max(0, Math.floor((end - start) / 1000));
  });

  readonly elapsed = computed(() => {
    const seconds = this.elapsedSeconds();
    return `${Math.floor(seconds / 60)
      .toString()
      .padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`;
  });

  readonly estimatedRemaining = computed(() => {
    const progress = this.job()?.progress ?? 0;
    if (progress <= 0 || progress >= 100) return progress >= 100 ? '00:00' : '—';
    const seconds = Math.max(
      0,
      Math.round((this.elapsedSeconds() * (100 - progress)) / progress),
    );
    return `${Math.floor(seconds / 60)
      .toString()
      .padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`;
  });

  constructor() {
    interval(1000)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.clock.set(Date.now()));

    if (!this.jobId) {
      this.loading.set(false);
      this.error.set('No review job was specified.');
      return;
    }
    timer(0, 1500)
      .pipe(
        switchMap(() => this.api.getReview(this.jobId, true, !!this.job())),
        tap((job) => {
          this.job.set(job);
          this.loading.set(false);

          if (!this.pullRequest() && job.command?.pull_number && job.command?.repository && job.command?.provider) {
            this.api.getPullRequest(job.command.provider, job.command.repository, job.command.pull_number)
              .pipe(catchError(() => EMPTY))
              .subscribe((pr) => this.pullRequest.set(pr));
          }

          if (job.status === 'completed') {
            setTimeout(() => void this.router.navigate(['/reviews', this.jobId, 'results']), 650);
          }
        }),
        takeWhile(
          (job) => !['completed', 'failed', 'cancelled'].includes(job.status),
          true,
        ),
        catchError((error) => {
          this.loading.set(false);
          this.error.set(error?.error?.detail ?? 'Unable to retrieve review progress.');
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe();
  }

  requestCancel(): void {
    if (!this.job() || !this.auth.canCancel(this.job()!)) return;
    this.cancelConfirmationOpen.set(true);
  }

  confirmCancel(): void {
    this.cancelConfirmationOpen.set(false);
    this.cancel();
  }

  cancel(): void {
    if (!this.job() || !this.auth.canCancel(this.job()!)) return;
    this.cancelling.set(true);
    this.api.cancelReview(this.jobId).subscribe({
      next: () => {
        this.cancelling.set(false);
        void this.router.navigate(['/']);
      },
      error: (error) => {
        this.cancelling.set(false);
        this.error.set(error?.error?.detail ?? 'The running review could not be cancelled.');
      },
    });
  }

  async copyJobId(): Promise<void> {
    try {
      await navigator.clipboard.writeText(this.jobId);
      this.copyStatus.set('Copied!');
      setTimeout(() => this.copyStatus.set(''), 2000);
    } catch {
      this.copyStatus.set('Copy failed');
    }
  }

  statusLabel(status: string): string {
    if (status === 'completed') return 'Completed';
    if (status === 'failed') return 'Failed';
    if (status === 'cancelled') return 'Cancelled';
    return 'Running';
  }

  splitFilePath(file: string): { name: string; path: string } {
    const clean = file.includes(':') ? file.split(':').slice(1).join(':') : file;
    const normalized = clean.replaceAll('\\', '/');
    const parts = normalized.split('/');
    const name = parts.pop() ?? clean;
    const path = parts.length ? parts.join('/') + '/' : './';
    return { name, path };
  }

  stepIcon(state: string): string {
    if (state === 'complete') return 'check';
    if (state === 'failed') return 'x';
    if (state === 'active') return 'loader-circle';
    return 'circle-dot';
  }

  changedFileCount(): number | string {
    const job = this.job();
    return job?.metrics?.changed_files ?? job?.result?.diagnostics.changed_files ?? 'Waiting';
  }

  reviewFileCount(): number | string {
    const job = this.job();
    return job?.metrics?.review_files ?? job?.result?.diagnostics.ai_review_files ?? 'Waiting';
  }

  staticFindingCount(): number | string {
    const job = this.job();
    if (!job) return 'Waiting';
    if (job.metrics?.static_findings !== null && job.metrics?.static_findings !== undefined) {
      return job.metrics.static_findings;
    }
    const diagnostics = job.result?.diagnostics;
    if (diagnostics) {
      return Math.max(0, job.result!.findings.length - diagnostics.final_ai_findings);
    }
    const staticStep = job.steps.find((step) => step.key === 'static_analysis');
    const match = staticStep?.message?.match(/\d+/);
    return match ? Number(match[0]) : 'Waiting';
  }

  llmCallCount(): string {
    const job = this.job();
    const planned = job?.metrics?.planned_llm_calls ?? job?.result?.diagnostics.planned_llm_calls;
    const actual = job?.metrics?.actual_llm_calls ?? job?.result?.diagnostics.actual_llm_calls;
    if (planned === null || planned === undefined) return 'Waiting';
    return `${actual ?? 0} / ${planned}`;
  }

  diagnosticTime(event: ReviewEvent): string {
    const timestamp = event.timestamp;
    return timestamp
      ? new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      : 'Waiting';
  }

  setDiagnosticFilter(value: string): void {
    const allowed = new Set(this.diagnosticOptions.map((option) => option.value));
    if (allowed.has(value)) this.diagnosticFilter.set(value);
  }

  activityTitle(step: ReviewStep): string {
    const labels: Record<string, string> = {
      discovery: 'Repository analysis',
      static_analysis: 'Static analysis',
      ai_review: 'AI semantic review',
      validation: 'Validation and deduplication',
      publishing: 'Publishing review comments',
    };
    const event = this.latestPhaseEvent(step.key);
    if (step.key === 'ai_review' && event?.batch_index && event.batch_total) {
      return `${labels[step.key]} · Batch ${event.batch_index}/${event.batch_total}`;
    }
    return labels[step.key] ?? step.label;
  }

  activityMessage(step: ReviewStep): string {
    const event = this.latestPhaseEvent(step.key);
    if (event?.detail) return event.detail;
    if (step.state === 'complete') return 'Completed successfully';
    if (step.state === 'active') return step.message ?? this.job()?.message ?? 'In progress';
    if (step.state === 'failed') return 'Review stage failed';
    if (step.state === 'cancelled') return 'Cancelled';
    return 'Pending';
  }

  activityFiles(step: ReviewStep): string[] {
    return [...(this.job()?.events ?? [])].reverse().find(e => e.phase === step.key && e.files?.length)?.files ?? [];
  }

  readonly completedStageCount = computed(
    () => this.activitySteps().filter((step) => step.state === 'complete').length,
  );

  activityLabel(step: ReviewStep): string {
    const labels: Record<string, string> = {
      discovery: 'Repository analysis',
      static_analysis: 'Static analysis',
      ai_review: 'AI semantic review',
      validation: 'Validation and deduplication',
      publishing: 'Publishing review comments',
    };
    return labels[step.key] ?? step.label;
  }

  severityBreakdown(step: ReviewStep): { level: string; count: number }[] {
    if (step.key !== 'static_analysis') return [];
    const text = this.activityMessage(step);
    const order = ['critical', 'high', 'medium', 'low'];
    const found = new Map<string, number>();
    for (const match of text.matchAll(/\b(critical|high|medium|low)\b[\s:]*(\d+)/gi)) {
      found.set(match[1].toLowerCase(), Number(match[2]));
    }
    return order
      .filter((level) => (found.get(level) ?? 0) > 0)
      .map((level) => ({ level, count: found.get(level)! }));
  }

  findingTotal(step: ReviewStep): number {
    const match = this.activityMessage(step).match(/(\d+)\s+findings?/i);
    if (match) return Number(match[1]);
    return this.severityBreakdown(step).reduce((sum, item) => sum + item.count, 0);
  }

  activityProgress(step: ReviewStep): number {
    if (step.state === 'complete') return 100;
    if (step.state !== 'active') return 0;
    const event = [...(this.job()?.events ?? [])].reverse().find(e => e.phase === step.key && e.batch_index && e.batch_total);
    if (event?.batch_index && event.batch_total) {
      return Math.min(100, Math.max(0, ((event.batch_index - 1) / event.batch_total) * 100));
    }
    return 0;
  }

  activityHasProgress(step: ReviewStep): boolean {
    return (this.job()?.events ?? []).some(e => e.phase === step.key && e.batch_index && e.batch_total);
  }

  activityRingOffset(step: ReviewStep): number {
    return this.activityRingCircumference * (1 - this.activityProgress(step) / 100);
  }

  activityTime(step: ReviewStep): string {
    if (step.state === 'pending') return 'Pending';
    if (step.state === 'active') return 'In progress';
    if (step.state === 'failed') return 'Failed';
    if (step.state === 'cancelled') return 'Cancelled';
    return this.relativeTime(step.updated_at);
  }

  diagnosticIcon(event: ReviewEvent): string {
    if (event.level === 'error') return 'x';
    if (event.level === 'success' || event.phase === 'completed') return 'check';
    if (event.phase === 'validation' || event.phase === 'completed') return 'check';
    return 'info';
  }

  private latestPhaseEvent(phase: string): ReviewEvent | undefined {
    return [...(this.job()?.events ?? [])].reverse().find((event) => event.phase === phase);
  }

  private relativeTime(value: string | null): string {
    if (!value) return 'Done';
    const seconds = Math.max(0, Math.floor((this.clock() - new Date(value).getTime()) / 1000));
    if (seconds < 10) return 'Just now';
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    return minutes < 60 ? `${minutes}m ago` : `${Math.floor(minutes / 60)}h ago`;
  }
}
