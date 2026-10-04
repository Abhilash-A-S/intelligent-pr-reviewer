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
  decision: 'blocked' | 'changes' | 'passed' | 'running';
  findings: number;
  mode: 'Dry run' | 'Published';
  duration: string;
  created: string;
}

const PREVIEW_HISTORY: HistoryRow[] = [
  { id: 'RVW-7F3A91', provider: 'azure-devops', repository: 'pr-reviewer-lab', pullNumber: 48, title: 'Improve checkout validation', author: 'Maya Patel', decision: 'blocked', findings: 56, mode: 'Dry run', duration: '24.2s', created: 'Today, 10:42' },
  { id: 'RVW-62B110', provider: 'github', repository: 'commerce-web', pullNumber: 147, title: 'Harden payment webhook verification', author: 'Daniel Kim', decision: 'changes', findings: 12, mode: 'Published', duration: '18.8s', created: 'Today, 09:15' },
  { id: 'RVW-4C10EE', provider: 'azure-devops', repository: 'catalog-api', pullNumber: 46, title: 'Add product search result caching', author: 'Amelia Stone', decision: 'passed', findings: 0, mode: 'Published', duration: '11.4s', created: 'Yesterday, 17:38' },
  { id: 'RVW-1A8CF2', provider: 'github', repository: 'platform-services', pullNumber: 312, title: 'Refactor order repository pagination', author: 'Noah Williams', decision: 'changes', findings: 7, mode: 'Dry run', duration: '31.0s', created: 'Yesterday, 14:06' },
  { id: 'RVW-90DBA4', provider: 'azure-devops', repository: 'pr-reviewer-lab', pullNumber: 44, title: 'Update CI deployment protections', author: 'Olivia Martin', decision: 'passed', findings: 2, mode: 'Published', duration: '9.7s', created: 'Sep 30, 16:21' },
];

@Component({
  selector: 'app-history-page',
  imports: [FormsModule, RouterLink, Icon, ProviderMark],
  templateUrl: './history.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HistoryPage {
  private readonly api = inject(ReviewerApi);
  readonly rows = signal<HistoryRow[]>(PREVIEW_HISTORY);
  readonly previewData = signal(true);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly search = signal('');
  readonly provider = signal<'all' | 'github' | 'azure-devops'>('all');
  readonly decision = signal<'all' | 'blocked' | 'changes' | 'passed' | 'running'>('all');
  readonly trendBars = [
    { passed: 24, blocked: 10 }, { passed: 31, blocked: 18 }, { passed: 29, blocked: 12 },
    { passed: 42, blocked: 25 }, { passed: 58, blocked: 30 }, { passed: 37, blocked: 20 },
    { passed: 49, blocked: 27 }, { passed: 61, blocked: 35 }, { passed: 45, blocked: 24 },
    { passed: 56, blocked: 31 }, { passed: 39, blocked: 19 }, { passed: 67, blocked: 38 },
    { passed: 48, blocked: 22 }, { passed: 60, blocked: 28 }, { passed: 72, blocked: 41 },
    { passed: 52, blocked: 25 }, { passed: 64, blocked: 34 }, { passed: 47, blocked: 21 },
    { passed: 69, blocked: 37 }, { passed: 55, blocked: 24 }, { passed: 76, blocked: 43 },
    { passed: 58, blocked: 29 }, { passed: 66, blocked: 33 }, { passed: 49, blocked: 20 },
    { passed: 79, blocked: 46 }, { passed: 62, blocked: 27 }, { passed: 71, blocked: 35 },
    { passed: 54, blocked: 23 }, { passed: 74, blocked: 39 }, { passed: 65, blocked: 31 },
    { passed: 77, blocked: 42 },
  ] as const;

  readonly metrics = computed(() => {
    if (this.previewData()) {
      return { total: 128, completed: 34, blocked: 21, published: 107, blockedRate: '16.4' };
    }
    const rows = this.rows();
    const blocked = rows.filter((row) => row.decision === 'blocked').length;
    return {
      total: rows.length,
      completed: rows.filter((row) => row.decision !== 'running').length,
      blocked,
      published: rows.filter((row) => row.mode === 'Published').length,
      blockedRate: rows.length ? ((blocked / rows.length) * 100).toFixed(1) : '0.0',
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

  constructor() {
    this.api.listReviews().subscribe({
      next: (response) => {
        if (response.items.length) {
          this.rows.set(response.items.map((job) => this.fromJob(job)));
          this.previewData.set(false);
        }
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  decisionLabel(decision: HistoryRow['decision']): string {
    return { blocked: 'Block merge', changes: 'Request changes', passed: 'Passed', running: 'Running' }[
      decision
    ];
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
    const blob = new Blob([JSON.stringify(this.filteredRows(), null, 2)], {
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
    const qualityDecision = quality?.decision ?? summary?.decision;
    const decision: HistoryRow['decision'] =
      job.status !== 'completed'
        ? 'running'
        : qualityDecision === 'block'
          ? 'blocked'
          : qualityDecision === 'pass'
            ? 'passed'
            : 'changes';
    const duration = job.result?.diagnostics.total_review_seconds ?? summary?.duration_seconds;
    return {
      id: job.id,
      provider: job.command.provider,
      repository: job.command.repository.split('/').at(-1) ?? job.command.repository,
      pullNumber: job.command.pull_number,
      title: job.result?.pull_request.title ?? summary?.title ?? `Pull request #${job.command.pull_number}`,
      author: job.result?.pull_request.author ?? summary?.author ?? 'Unknown author',
      decision,
      findings: total,
      mode: job.command.publish ? 'Published' : 'Dry run',
      duration: typeof duration === 'number' ? `${duration.toFixed(1)}s` : '—',
      created: new Date(job.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }),
    };
  }
}
