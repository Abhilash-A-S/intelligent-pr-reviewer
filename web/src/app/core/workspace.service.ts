import { computed, inject, Injectable, signal } from '@angular/core';
import { finalize } from 'rxjs';

import { ReviewerApi } from './api.service';
import { DEMO_PULL_REQUESTS } from './demo-data';
import { ProviderId, PullRequestSummary } from './models';

@Injectable({ providedIn: 'root' })
export class WorkspaceService {
  private readonly api = inject(ReviewerApi);

  readonly provider = signal<ProviderId>('azure-devops');
  readonly organization = signal('noventra-ai-labs');
  readonly project = signal('pr-reviewer-lab');
  readonly repositoryName = signal('pr-reviewer-lab');
  readonly pullRequests = signal<PullRequestSummary[]>(DEMO_PULL_REQUESTS);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly previewData = signal(true);

  readonly repository = computed(() => {
    if (this.provider() === 'github') {
      return `${this.organization().trim()}/${this.repositoryName().trim()}`;
    }
    return [this.organization(), this.project(), this.repositoryName()]
      .map((value) => value.trim())
      .filter(Boolean)
      .join('/');
  });

  constructor() {
    this.restore();
  }

  refreshPullRequests(): void {
    const repository = this.repository();
    if (!repository) {
      this.error.set('Enter a valid repository before refreshing.');
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    this.persist();
    this.api
      .listPullRequests(this.provider(), repository)
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (response) => {
          this.pullRequests.set(response.items);
          this.previewData.set(false);
        },
        error: (error) => {
          const detail = error?.error?.detail ?? error?.message ?? 'Unable to load pull requests.';
          this.error.set(detail);
        },
      });
  }

  setProvider(provider: ProviderId): void {
    this.provider.set(provider);
    this.persist();
  }

  private persist(): void {
    try {
      localStorage.setItem(
        'ipr-workspace',
        JSON.stringify({
          provider: this.provider(),
          organization: this.organization(),
          project: this.project(),
          repositoryName: this.repositoryName(),
        }),
      );
    } catch {
      // Selection persistence is optional.
    }
  }

  private restore(): void {
    try {
      const raw = localStorage.getItem('ipr-workspace');
      if (!raw) return;
      const value = JSON.parse(raw) as Partial<{
        provider: ProviderId;
        organization: string;
        project: string;
        repositoryName: string;
      }>;
      if (value.provider === 'github' || value.provider === 'azure-devops') {
        this.provider.set(value.provider);
      }
      if (typeof value.organization === 'string') this.organization.set(value.organization);
      if (typeof value.project === 'string') this.project.set(value.project);
      if (typeof value.repositoryName === 'string') {
        this.repositoryName.set(value.repositoryName);
      }
    } catch {
      // Ignore corrupt local preferences and keep safe defaults.
    }
  }
}
