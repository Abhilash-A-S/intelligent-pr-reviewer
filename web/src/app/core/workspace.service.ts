import { computed, inject, Injectable, signal } from '@angular/core';
import { catchError, finalize, forkJoin, of } from 'rxjs';

import { ReviewerApi } from './api.service';
import {
  OrganizationSummary,
  ProjectSummary,
  ProviderId,
  PullRequestSummary,
  RepositorySummary,
  ReviewJob,
} from './models';

@Injectable({ providedIn: 'root' })
export class WorkspaceService {
  private readonly api = inject(ReviewerApi);

  readonly provider = signal<ProviderId>('github');
  readonly organization = signal('');
  readonly project = signal('');
  readonly repositoryName = signal('');
  readonly organizations = signal<OrganizationSummary[]>([]);
  readonly projects = signal<ProjectSummary[]>([]);
  readonly repositories = signal<RepositorySummary[]>([]);
  readonly organizationLoading = signal(false);
  readonly projectLoading = signal(false);
  readonly repositoryLoading = signal(false);
  readonly organizationError = signal<string | null>(null);
  readonly projectError = signal<string | null>(null);
  readonly repositoryError = signal<string | null>(null);
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

  readonly discoveryLoading = computed(
    () => this.organizationLoading() || this.projectLoading() || this.repositoryLoading(),
  );
  readonly discoveryError = computed(
    () => this.repositoryError() ?? this.projectError() ?? this.organizationError(),
  );

  private organizationRequestId = 0;
  private projectRequestId = 0;
  private repositoryRequestId = 0;

  constructor() {
    this.restore();
    if (this.hasRepositorySelection()) this.refreshPullRequests();
  }

  ensureDiscoveryLoaded(): void {
    if (!this.organizations().length && !this.organizationLoading()) {
      this.loadOrganizations();
      return;
    }
    this.loadSavedSelectionChildren();
  }

  loadOrganizations(): void {
    const provider = this.provider();
    const requestId = ++this.organizationRequestId;
    this.organizationLoading.set(true);
    this.organizationError.set(null);
    this.api.listOrganizations(provider).subscribe({
      next: (response) => {
        if (requestId !== this.organizationRequestId || provider !== this.provider()) return;
        this.organizations.set(response.items);
        this.organizationLoading.set(false);
        this.loadSavedSelectionChildren();
      },
      error: (error) => {
        if (requestId !== this.organizationRequestId || provider !== this.provider()) return;
        this.organizations.set([]);
        this.organizationLoading.set(false);
        this.organizationError.set(
          `${this.errorDetail(error, 'Provider accounts could not be discovered.')} You can enter the value manually.`,
        );
      },
    });
  }

  selectOrganization(organization: string): void {
    const value = organization.trim();
    if (value === this.organization()) return;
    this.projectRequestId += 1;
    this.repositoryRequestId += 1;
    this.projectLoading.set(false);
    this.repositoryLoading.set(false);
    this.organization.set(value);
    this.project.set('');
    this.repositoryName.set('');
    this.projects.set([]);
    this.repositories.set([]);
    this.clearPullRequests();
    this.organizationError.set(null);
    this.projectError.set(null);
    this.repositoryError.set(null);
    this.persist();
    if (!value) return;
    if (this.provider() === 'azure-devops') this.loadProjects(value);
    else this.loadRepositories(value);
  }

  loadProjects(organization = this.organization()): void {
    const provider = this.provider();
    const context = organization.trim();
    if (provider !== 'azure-devops' || !context) return;
    const requestId = ++this.projectRequestId;
    this.projectLoading.set(true);
    this.projectError.set(null);
    this.api.listProjects(provider, context).subscribe({
      next: (response) => {
        if (
          requestId !== this.projectRequestId ||
          provider !== this.provider() ||
          context !== this.organization()
        )
          return;
        this.projects.set(response.items);
        this.projectLoading.set(false);
        if (this.project()) this.loadRepositories(context, this.project());
      },
      error: (error) => {
        if (requestId !== this.projectRequestId || context !== this.organization()) return;
        this.projects.set([]);
        this.projectLoading.set(false);
        this.projectError.set(
          `${this.errorDetail(error, 'Azure projects could not be discovered.')} You can enter the project manually.`,
        );
      },
    });
  }

  selectProject(project: string): void {
    const value = project.trim();
    if (value === this.project()) return;
    this.repositoryRequestId += 1;
    this.repositoryLoading.set(false);
    this.project.set(value);
    this.repositoryName.set('');
    this.repositories.set([]);
    this.clearPullRequests();
    this.projectError.set(null);
    this.repositoryError.set(null);
    this.persist();
    if (value && this.organization()) this.loadRepositories(this.organization(), value);
  }

  loadRepositories(
    organization = this.organization(),
    project = this.provider() === 'azure-devops' ? this.project() : undefined,
  ): void {
    const provider = this.provider();
    const owner = organization.trim();
    const projectName = project?.trim();
    if (!owner || (provider === 'azure-devops' && !projectName)) return;
    const requestId = ++this.repositoryRequestId;
    this.repositoryLoading.set(true);
    this.repositoryError.set(null);
    this.api.listRepositories(provider, owner, projectName).subscribe({
      next: (response) => {
        if (
          requestId !== this.repositoryRequestId ||
          provider !== this.provider() ||
          owner !== this.organization() ||
          (provider === 'azure-devops' && projectName !== this.project())
        )
          return;
        this.repositories.set(response.items);
        this.repositoryLoading.set(false);
      },
      error: (error) => {
        if (requestId !== this.repositoryRequestId || owner !== this.organization()) return;
        this.repositories.set([]);
        this.repositoryLoading.set(false);
        this.repositoryError.set(
          `${this.errorDetail(error, 'Repositories could not be discovered.')} You can enter the repository manually.`,
        );
      },
    });
  }

  selectRepository(repository: string): void {
    this.repositoryName.set(repository.trim());
    this.clearPullRequests();
    this.error.set(null);
    this.persist();
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
      reviews: this.api.listReviews(200).pipe(catchError(() => of({ items: [], total: 0 }))),
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
    this.organization.set('');
    this.project.set('');
    this.repositoryName.set('');
    this.organizations.set([]);
    this.projects.set([]);
    this.repositories.set([]);
    this.invalidateDiscoveryRequests();
    this.clearPullRequests();
    this.organizationError.set(null);
    this.projectError.set(null);
    this.repositoryError.set(null);
    this.persist();
    this.loadOrganizations();
  }

  private loadSavedSelectionChildren(): void {
    const organization = this.organization();
    if (!organization) return;
    if (this.provider() === 'azure-devops') {
      if (!this.projects().length && !this.projectLoading()) this.loadProjects(organization);
    } else if (!this.repositories().length && !this.repositoryLoading()) {
      this.loadRepositories(organization);
    }
  }

  private clearPullRequests(): void {
    this.pullRequests.set([]);
    this.error.set(null);
    this.loaded.set(false);
  }

  private invalidateDiscoveryRequests(): void {
    this.organizationRequestId += 1;
    this.projectRequestId += 1;
    this.repositoryRequestId += 1;
    this.organizationLoading.set(false);
    this.projectLoading.set(false);
    this.repositoryLoading.set(false);
  }

  private errorDetail(error: unknown, fallback: string): string {
    const candidate = error as {
      status?: number;
      error?: { detail?: string };
      message?: string;
    } | null;
    if (candidate?.status === 401) {
      return 'Provider authentication failed. Ask an administrator to verify the server credential.';
    }
    if (candidate?.status === 403) {
      return 'The provider denied discovery access. The credential may still support a manually entered repository.';
    }
    if (candidate?.status === 503) {
      return 'This provider is not configured on the review server.';
    }
    return candidate?.error?.detail ?? candidate?.message ?? fallback;
  }

  private withReviewStatus(pullRequest: PullRequestSummary, jobs: ReviewJob[]): PullRequestSummary {
    const latest = jobs.find(
      (job) =>
        job.command.provider === this.provider() &&
        job.command.repository === this.repository() &&
        job.command.pull_number === pullRequest.number,
    );
    if (!latest) return { ...pullRequest, review_status: 'awaiting' };
    const decision = latest.result?.quality_gate.decision ?? latest.result_summary?.decision;
    const reviewStatus =
      latest.status !== 'completed' ? 'awaiting' : decision === 'pass' ? 'passed' : 'blocked';
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
