import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ReviewerApi } from '../../core/api.service';
import { ReviewJob } from '../../core/models';
import { Icon } from '../../shared/icon';
import { ProviderMark } from '../../shared/provider-mark';

interface HistoryRow {
  id: string;
  provider: 'github' | 'azure-devops';
  repository: string;
  pullNumber: number;
  title: string;
  author: string;
  decision: 'blocked' | 'changes' | 'passed' | 'running' | 'failed';
  findings: number;
  mode: 'Dry run' | 'Published';
  duration: string;
  created: string;
  createdAt: Date;
}

@Component({
  selector: 'app-history-page',
  imports: [FormsModule, RouterLink, Icon, ProviderMark],
  templateUrl: './history.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HistoryPage {
  private readonly api = inject(ReviewerApi);
  readonly rows = signal<HistoryRow[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly search = signal('');
  readonly provider = signal<'all' | 'github' | 'azure-devops'>('all');
  readonly decision = signal<'all' | HistoryRow['decision']>('all');

  readonly metrics = computed(() => {
    const rows = this.rows();
    const now = new Date();
    const completedThisMonth = rows.filter(
      (row) =>
        row.decision !== 'running' &&
        row.createdAt.getFullYear() === now.getFullYear() &&
        row.createdAt.getMonth() === now.getMonth(),
    ).length;
    return {
      total: rows.length,
      completed: completedThisMonth,
      blocked: rows.filter((row) => row.decision === 'blocked').length,
      published: rows.filter((row) => row.mode === 'Published').length,
    };
  });

  readonly filteredRows = computed(() => {
    const search = this.search().trim().toLowerCase();
    return this.rows().filter((row) => {
      const providerMatch = this.provider() === 'all' || row.provider === this.provider();
      const decisionMatch = this.decision() === 'all' || row.decision === this.decision();
      const searchable = `${row.title} ${row.repository} ${row.author} ${row.pullNumber}`.toLowerCase();
      return providerMatch && decisionMatch && (!search || searchable.includes(search));
    });
  });

  readonly trend = computed(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const days = Array.from({ length: 31 }, (_value, index) => {
      const date = new Date(today);
      date.setDate(today.getDate() - (30 - index));
      const matching = this.rows().filter((row) => this.sameDay(row.createdAt, date));
      return {
        date,
        passed: matching.filter((row) => row.decision === 'passed').length,
        blocked: matching.filter((row) => ['blocked', 'changes', 'failed'].includes(row.decision)).length,
      };
    });
    const maximum = Math.max(1, ...days.flatMap((day) => [day.passed, day.blocked]));
    return days.map((day) => ({
      ...day,
      passedHeight: (day.passed / maximum) * 100,
      blockedHeight: (day.blocked / maximum) * 100,
    }));
  });

  readonly historyRangeLabel = computed(() => {
    const trend = this.trend();
    if (!trend.length) return '—';
    const format = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    return `${format.format(trend[0].date)} – ${format.format(trend.at(-1)!.date)}`;
  });

  readonly trendLabels = computed(() => {
    const trend = this.trend();
    const format = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' });
    return [0, 6, 12, 18, 24, 30].map((index) => format.format(trend[index].date));
  });

  constructor() {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.listReviews(200).subscribe({
      next: (response) => {
        this.rows.set(response.items.map((job) => this.fromJob(job)));
        this.loading.set(false);
      },
      error: (error) => {
        this.rows.set([]);
        this.loading.set(false);
        this.error.set(error?.error?.detail ?? 'Review history could not be loaded.');
      },
    });
  }

  decisionLabel(decision: HistoryRow['decision']): string {
    return {
      blocked: 'Block merge',
      changes: 'Request changes',
      passed: 'Passed',
      running: 'Running',
      failed: 'Failed',
    }[decision];
  }

  initials(author: string): string {
    return author
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part.charAt(0))
      .join('')
      .toUpperCase();
  }

  exportHistory(): void {
    const rows = this.filteredRows();
    if (!rows.length) return;
    const exportRows = rows.map(({ createdAt: _createdAt, ...row }) => row);
    const blob = new Blob([JSON.stringify(exportRows, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'review-history.json';
    anchor.click();
    URL.revokeObjectURL(url);
  }

  private fromJob(job: ReviewJob): HistoryRow {
    const quality = job.result?.quality_gate;
    const summary = job.result_summary;
    const total = quality
      ? quality.critical_count + quality.high_count + quality.medium_count + quality.low_count + quality.suggestion_count
      : (summary?.findings ?? 0);
    const qualityDecision = String(quality?.decision ?? summary?.decision ?? '').toLowerCase();
    const decision: HistoryRow['decision'] =
      job.status === 'queued' || job.status === 'running'
        ? 'running'
        : job.status === 'failed' || job.status === 'cancelled'
          ? 'failed'
          : qualityDecision.includes('pass')
            ? 'passed'
            : qualityDecision.includes('block')
              ? 'blocked'
              : 'changes';
    const duration = job.result?.diagnostics.total_review_seconds ?? summary?.duration_seconds;
    const createdAt = new Date(job.created_at);
    return {
      id: job.id,
      provider: job.command.provider,
      repository: job.command.repository.split('/').at(-1) ?? job.command.repository,
      pullNumber: job.command.pull_number,
      title: job.result?.pull_request.title ?? summary?.title ?? `Pull request #${job.command.pull_number}`,
      author: job.result?.pull_request.author ?? summary?.author ?? 'Unavailable',
      decision,
      findings: total,
      mode: job.command.publish ? 'Published' : 'Dry run',
      duration: typeof duration === 'number' ? `${duration.toFixed(1)}s` : '—',
      created: Number.isNaN(createdAt.getTime())
        ? '—'
        : createdAt.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }),
      createdAt,
    };
  }

  private sameDay(first: Date, second: Date): boolean {
    return (
      first.getFullYear() === second.getFullYear() &&
      first.getMonth() === second.getMonth() &&
      first.getDate() === second.getDate()
    );
  }
}
