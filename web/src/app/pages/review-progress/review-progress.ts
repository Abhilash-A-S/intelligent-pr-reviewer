import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { catchError, EMPTY, interval, switchMap, takeWhile, tap, timer } from 'rxjs';

import { ReviewerApi } from '../../core/api.service';
import { ReviewJob } from '../../core/models';
import { Icon } from '../../shared/icon';

@Component({
  selector: 'app-review-progress-page',
  imports: [RouterLink, Icon],
  templateUrl: './review-progress.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReviewProgressPage {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(ReviewerApi);
  private readonly destroyRef = inject(DestroyRef);
  private readonly clock = signal(Date.now());

  readonly jobId = this.route.snapshot.paramMap.get('jobId') ?? '';
  readonly job = signal<ReviewJob | null>(null);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly cancelling = signal(false);

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
        switchMap(() => this.api.getReview(this.jobId)),
        tap((job) => {
          this.job.set(job);
          this.loading.set(false);
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

  cancel(): void {
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

  stepIcon(state: string): string {
    if (state === 'complete') return 'check';
    if (state === 'failed') return 'x';
    if (state === 'active') return 'loader-circle';
    return 'circle-dot';
  }

  staticFindingCount(): number | string {
    const job = this.job();
    if (!job) return '—';
    const diagnostics = job.result?.diagnostics;
    if (diagnostics) {
      return Math.max(0, job.result!.findings.length - diagnostics.final_ai_findings);
    }
    const staticStep = job.steps.find((step) => step.key === 'static_analysis');
    const match = staticStep?.message?.match(/\d+/);
    return match ? Number(match[0]) : '—';
  }

  diagnosticTime(index: number): string {
    const job = this.job();
    if (!job) return '—';
    const step = job.steps[index];
    const timestamp = step?.updated_at ?? (index === 0 ? job.started_at : null);
    return timestamp
      ? new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      : '—';
  }

  statusMessage(state: string): string {
    if (state === 'complete') return 'Completed successfully';
    if (state === 'active') return 'In progress';
    if (state === 'failed') return 'Review stage failed';
    if (state === 'cancelled') return 'Cancelled';
    return 'Waiting';
  }
}
