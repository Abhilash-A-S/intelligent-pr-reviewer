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
    if (this.workspace.previewData()) {
      return { open: 12, awaiting: 3, blocked: 2, passed: 7 };
    }
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
}
