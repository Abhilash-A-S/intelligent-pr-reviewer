import { ChangeDetectionStrategy, Component, computed, inject, linkedSignal, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { AuthService } from '../../core/auth.service';
import { ReviewerApi } from '../../core/api.service';
import { ReviewJob } from '../../core/models';
import { Pagination } from '../../shared/pagination';
import { Icon } from '../../shared/icon';
import { ProviderMark } from '../../shared/provider-mark';
import { SmartSelect, SmartSelectOption } from '../../shared/smart-select';

interface HistoryRow {
  id: string;
  provider: 'github' | 'azure-devops';
  repository: string;
  repositoryKey: string;
  severity: { danger: number; warning: number; info: number } | null;
  pullNumber: number;
  title: string;
  author: string;
  decision: 'blocked' | 'changes' | 'passed' | 'running' | 'failed';
  findings: number;
  mode: 'Dry run' | 'Published' | 'Publishing' | 'Not published';
  duration: string;
  created: string;
  createdAt: Date;
}

@Component({
  selector: 'app-history-page',
  imports: [FormsModule, RouterLink, Icon, ProviderMark, SmartSelect, Pagination],
  templateUrl: './history.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HistoryPage {
  readonly auth = inject(AuthService);
  private readonly api = inject(ReviewerApi);
  readonly rows = signal<HistoryRow[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly search = signal('');
  readonly provider = signal<'all' | 'github' | 'azure-devops'>('all');
  readonly decision = signal<'all' | HistoryRow['decision']>('all');
  readonly repository = signal('all');
  readonly startDate = signal('');
  readonly endDate = signal('');
  readonly dateError = computed(() => this.startDate() && this.endDate() && this.startDate() > this.endDate() ? 'Start date must be before the end date.' : '');
  readonly repositoryOptions = computed<SmartSelectOption[]>(() => [
    {value: 'all', label: 'All repositories'},
    ...[...new Set(this.rows().filter(r => this.provider() === 'all' || r.provider === this.provider()).map(r => r.repositoryKey))].sort().map(value => ({value, label: value})),
  ]);
  readonly providerOptions = computed<SmartSelectOption[]>(() => [
    { value: 'all', label: 'All providers' },
    { value: 'github', label: 'GitHub' },
    { value: 'azure-devops', label: 'Azure DevOps' },
  ].filter(option => option.value === 'all' || this.auth.providerEnabled(option.value)));
  readonly decisionOptions: SmartSelectOption[] = [
    { value: 'all', label: 'All decisions' },
    { value: 'blocked', label: 'Block merge' },
    { value: 'changes', label: 'Request changes' },
    { value: 'passed', label: 'Passed' },
    { value: 'running', label: 'Running' },
    { value: 'failed', label: 'Failed' },
  ];

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
      const searchable =
        `${row.title} ${row.repository} ${row.author} ${row.pullNumber}`.toLowerCase();
      const repositoryMatch = this.repository() === 'all' || row.repositoryKey === this.repository();
      const day = this.localDate(row.createdAt);
      const dateMatch = (!this.startDate() || day >= this.startDate()) && (!this.endDate() || day <= this.endDate());
      return !this.dateError() && providerMatch && repositoryMatch && decisionMatch && dateMatch && (!search || searchable.includes(search));
    });
  });

  readonly pageSize = 5;
  readonly requestedPage = linkedSignal({source: this.filteredRows, computation: () => 1});
  readonly currentPage = computed(() => Math.min(this.requestedPage(), Math.max(1, Math.ceil(this.filteredRows().length / this.pageSize))));
  readonly pagedRows = computed(() => this.filteredRows().slice((this.currentPage()-1)*this.pageSize, this.currentPage()*this.pageSize));
  readonly firstItem = computed(() => this.filteredRows().length ? (this.currentPage()-1)*this.pageSize+1 : 0);
  readonly lastItem = computed(() => Math.min(this.currentPage()*this.pageSize, this.filteredRows().length));
  readonly trend = computed(() => {
    const end = this.endDate() ? new Date(this.endDate() + 'T00:00:00') : new Date(); end.setHours(0,0,0,0);
    const start = this.startDate() ? new Date(this.startDate() + 'T00:00:00') : new Date(end);
    if (!this.startDate()) start.setDate(end.getDate()-30);
    if (this.dateError()) return [];
    // Limit chart buckets to 31; longer ranges aggregate into consecutive date intervals.
    const totalDays = Math.round((Date.UTC(end.getFullYear(),end.getMonth(),end.getDate()) - Date.UTC(start.getFullYear(),start.getMonth(),start.getDate()))/86400000)+1;
    const bucketDays = Math.max(1, Math.ceil(totalDays/31));
    const bars = [];
    for (let offset=0; offset<totalDays; offset+=bucketDays) {
      const date = new Date(start); date.setDate(start.getDate()+offset);
      const next = new Date(date); next.setDate(date.getDate()+bucketDays);
      const matching = this.filteredRows().filter(r => r.createdAt >= date && r.createdAt < next);
      bars.push({date, passed: matching.filter(r => r.decision === 'passed').length, blocked: matching.filter(r => ['blocked','changes'].includes(r.decision)).length});
    }
    const maximum = Math.max(1, ...bars.map(b => b.passed+b.blocked));
    return bars.map(b => ({...b, passedHeight:b.passed/maximum*100, blockedHeight:b.blocked/maximum*100}));
  });
  readonly trendMaximum = computed(() => Math.max(1, ...this.trend().map(b=>b.passed+b.blocked)));
  readonly trendLabels = computed(() => this.trend().filter((_b,i,all)=>i%Math.max(1,Math.floor(all.length/6))===0 || i===all.length-1).map(b=>b.date.toLocaleDateString([], {month:'short',day:'numeric'})));
  readonly historyRangeLabel = computed(() => this.startDate() || this.endDate() ? `${this.startDate() || 'Any date'} – ${this.endDate() || 'Today'}` : 'All dates');
  private localDate(date: Date): string { return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`; }

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

  setProviderFilter(value: string): void {
    if (['all', 'github', 'azure-devops'].includes(value)) {
      this.provider.set(value as 'all' | 'github' | 'azure-devops');
      this.repository.set('all');
    }
  }

  setDecisionFilter(value: string): void {
    if (['all', 'blocked', 'changes', 'passed', 'running', 'failed'].includes(value)) {
      this.decision.set(value as 'all' | HistoryRow['decision']);
    }
  }

  decisionLabel(decision: HistoryRow['decision']): string {
    return {
      blocked: 'BLOCK',
      changes: 'Request changes',
      passed: 'PASS',
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
      ? quality.critical_count +
        quality.high_count +
        quality.medium_count +
        quality.low_count +
        quality.suggestion_count
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
      repository: job.command.repository.split('/').slice(-2).join('/'),
      repositoryKey: job.command.repository,
      severity: quality ? {danger: quality.critical_count + quality.high_count, warning: quality.medium_count, info: quality.low_count + quality.suggestion_count} : summary?.severity_counts ? {danger: (summary.severity_counts['critical'] ?? 0) + (summary.severity_counts['high'] ?? 0), warning: summary.severity_counts['medium'] ?? 0, info: (summary.severity_counts['low'] ?? 0) + (summary.severity_counts['suggestion'] ?? 0)} : null,
      pullNumber: job.command.pull_number,
      title:
        job.result?.pull_request.title ??
        summary?.title ??
        `Pull request #${job.command.pull_number}`,
      author: job.result?.pull_request.author ?? summary?.author ?? 'Unavailable',
      decision,
      findings: total,
      mode: (job.result?.dry_run ?? summary?.dry_run ?? !job.command.publish) ? 'Dry run' : job.status === 'completed' ? 'Published' : ['queued', 'running'].includes(job.status) ? 'Publishing' : 'Not published',
      duration: typeof duration === 'number' ? `${String(Math.floor(duration/60)).padStart(2,'0')}:${String(Math.floor(duration%60)).padStart(2,'0')}` : '—',
      created: Number.isNaN(createdAt.getTime())
        ? '—'
        : createdAt.toLocaleString([], {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          }),
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
