import { computed, inject, Injectable, signal } from '@angular/core';
import { catchError, finalize, forkJoin, of } from 'rxjs';

import { ReviewerApi } from './api.service';
import { ProviderId, PullRequestSummary, ReviewJob } from './models';

@Injectable({ providedIn: 'root' })
export class WorkspaceService {
  private readonly api = inject(ReviewerApi);

  readonly provider = signal<ProviderId>('github');
  readonly organization = signal('');
  readonly project = signal('');
  readonly repositoryName = signal('');
  readonly pullRequests = signal<PullRequestSummary[]>([]);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly loaded = signal(false);

  readonly repository = computed(() => {
    if (this.provider() === 'github') {
      return `${this.organization().trim()}/${this.repositoryName().trim()}`;
    }
    return [this.organization(), this.project(), this.repositoryName()]
      .map((value) => value.trim())
      .filter(Boolean)
      .join('/');
  });

  readonly hasRepositorySelection = computed(() => {
    if (!this.organization().trim() || !this.repositoryName().trim()) return false;
    return this.provider() === 'github' || Boolean(this.project().trim());
  });

  constructor() {
    this.restore();
    if (this.hasRepositorySelection()) this.refreshPullRequests();
  }

  refreshPullRequests(): void {
    const repository = this.repository();
    if (!this.hasRepositorySelection()) {
      this.error.set(
        this.provider() === 'github'
          ? 'Enter the GitHub owner and repository.'
          : 'Enter the Azure DevOps organization, project, and repository.',
      );
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    this.persist();
    forkJoin({
      pullRequests: this.api.listPullRequests(this.provider(), repository),
      reviews: this.api
        .listReviews(200)
        .pipe(catchError(() => of({ items: [], total: 0 }))),
    })
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: ({ pullRequests, reviews }) => {
          this.pullRequests.set(
            pullRequests.items.map((item) => this.withReviewStatus(item, reviews.items)),
          );
          this.loaded.set(true);
        },
        error: (error) => {
          this.pullRequests.set([]);
          this.loaded.set(true);
          const detail = error?.error?.detail ?? error?.message ?? 'Unable to load pull requests.';
          this.error.set(detail);
        },
      });
  }

  setProvider(provider: ProviderId): void {
    if (provider === this.provider()) return;
    this.provider.set(provider);
    this.pullRequests.set([]);
    this.error.set(null);
    this.loaded.set(false);
    this.persist();
  }

  private withReviewStatus(
    pullRequest: PullRequestSummary,
    jobs: ReviewJob[],
  ): PullRequestSummary {
    const latest = jobs.find(
      (job) =>
        job.command.provider === this.provider() &&
        job.command.repository === this.repository() &&
        job.command.pull_number === pullRequest.number,
    );
    if (!latest) return { ...pullRequest, review_status: 'awaiting' };
    const decision = latest.result?.quality_gate.decision ?? latest.result_summary?.decision;
    const reviewStatus =
      latest.status !== 'completed'
        ? 'awaiting'
        : decision === 'pass'
          ? 'passed'
          : 'blocked';
    return {
      ...pullRequest,
      review_status: reviewStatus,
      updated_at: pullRequest.updated_at ?? latest.created_at,
    };
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
