import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ProviderId, PullRequestSummary } from '../../core/models';
import { WorkspaceService } from '../../core/workspace.service';
import { Icon } from '../../shared/icon';
import { ProviderMark } from '../../shared/provider-mark';

@Component({
  selector: 'app-dashboard-page',
  imports: [FormsModule, RouterLink, Icon, ProviderMark],
  templateUrl: './dashboard.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardPage {
  readonly workspace = inject(WorkspaceService);
  readonly search = signal('');
  readonly statusFilter = signal<'all' | 'awaiting' | 'blocked' | 'passed'>('all');

  readonly filteredPullRequests = computed(() => {
    const term = this.search().trim().toLowerCase();
    const status = this.statusFilter();
    return this.workspace.pullRequests().filter((pullRequest) => {
      const reviewStatus = pullRequest.review_status ?? 'awaiting';
      const matchesStatus = status === 'all' || reviewStatus === status;
      const matchesSearch =
        !term ||
        pullRequest.title.toLowerCase().includes(term) ||
        pullRequest.author.toLowerCase().includes(term) ||
        pullRequest.head_branch.toLowerCase().includes(term) ||
        String(pullRequest.number).includes(term);
      return matchesStatus && matchesSearch;
    });
  });

  readonly metrics = computed(() => {
    const pullRequests = this.workspace.pullRequests();
    return {
      open: pullRequests.length,
      awaiting: pullRequests.filter((item) => (item.review_status ?? 'awaiting') === 'awaiting')
        .length,
      blocked: pullRequests.filter((item) => item.review_status === 'blocked').length,
      passed: pullRequests.filter((item) => item.review_status === 'passed').length,
    };
  });

  setProvider(provider: ProviderId): void {
    this.workspace.setProvider(provider);
  }

  initials(author: string): string {
    return author
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part.charAt(0))
      .join('')
      .toUpperCase();
  }

  statusLabel(item: PullRequestSummary): string {
    switch (item.review_status) {
      case 'blocked':
        return 'Blocked';
      case 'passed':
        return 'Passed';
      default:
        return 'Awaiting review';
    }
  }

  relativeTime(value?: string): string {
    if (!value) return '—';
    const timestamp = new Date(value).getTime();
    if (!Number.isFinite(timestamp)) return value;
    const seconds = Math.round((timestamp - Date.now()) / 1000);
    const ranges: ReadonlyArray<[number, Intl.RelativeTimeFormatUnit]> = [
      [60, 'second'],
      [60, 'minute'],
      [24, 'hour'],
      [7, 'day'],
      [4.345, 'week'],
      [12, 'month'],
      [Number.POSITIVE_INFINITY, 'year'],
    ];
    let amount = seconds;
    for (const [limit, unit] of ranges) {
      if (Math.abs(amount) < limit) {
        return new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(
          Math.round(amount),
          unit,
        );
      }
      amount /= limit;
    }
    return value;
  }
}
