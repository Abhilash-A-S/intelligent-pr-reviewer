import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ProviderId, PullRequestSummary } from '../../core/models';
import { WorkspaceService } from '../../core/workspace.service';
import { Icon } from '../../shared/icon';
import { ProviderMark } from '../../shared/provider-mark';
import { SmartSelect, SmartSelectOption } from '../../shared/smart-select';

@Component({
  selector: 'app-dashboard-page',
  imports: [FormsModule, RouterLink, Icon, ProviderMark, SmartSelect],
  templateUrl: './dashboard.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardPage {
  readonly workspace = inject(WorkspaceService);
  readonly search = signal('');
  readonly statusFilter = signal<'all' | 'awaiting' | 'blocked' | 'passed'>('all');

  readonly organizationOptions = computed<SmartSelectOption[]>(() =>
    this.workspace.organizations().map((organization) => ({
      value: organization.name,
      label: organization.display_name || organization.name,
      description:
        organization.description ||
        (organization.display_name !== organization.name ? organization.name : undefined),
      searchText: `${organization.id} ${organization.name}`,
    })),
  );

  readonly projectOptions = computed<SmartSelectOption[]>(() =>
    this.workspace.projects().map((project) => ({
      value: project.name,
      label: project.name,
      description: project.description ?? undefined,
      searchText: project.id,
    })),
  );

  readonly repositoryOptions = computed<SmartSelectOption[]>(() =>
    this.workspace.repositories().map((repository) => ({
      value: repository.name,
      label: repository.name,
      description:
        [repository.visibility, repository.default_branch?.replace(/^refs\/heads\//, '')]
          .filter(Boolean)
          .join(' · ') ||
        repository.description ||
        undefined,
      searchText: `${repository.id} ${repository.full_name ?? ''} ${repository.description ?? ''}`,
    })),
  );

  readonly statusOptions: SmartSelectOption[] = [
    { value: 'all', label: 'All statuses' },
    { value: 'awaiting', label: 'Awaiting review' },
    { value: 'blocked', label: 'Blocked' },
    { value: 'passed', label: 'Passed' },
  ];

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

  constructor() {
    this.workspace.ensureDiscoveryLoaded();
  }

  setProvider(provider: ProviderId): void {
    this.search.set('');
    this.statusFilter.set('all');
    this.workspace.setProvider(provider);
  }

  clearFilters(): void {
    this.search.set('');
    this.statusFilter.set('all');
  }

  setStatusFilter(value: string): void {
    if (['all', 'awaiting', 'blocked', 'passed'].includes(value)) {
      this.statusFilter.set(value as 'all' | 'awaiting' | 'blocked' | 'passed');
    }
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
