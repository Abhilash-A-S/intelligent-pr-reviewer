import { ChangeDetectionStrategy, Component, HostListener, ViewEncapsulation, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';

import { ReviewerApi } from '../../core/api.service';
import {
  ChangedFileSummary,
  ProviderId,
  PullRequestDetail,
  ReviewDepth,
} from '../../core/models';
import { ReviewPreferencesService } from '../../core/review-preferences.service';
import { Icon } from '../../shared/icon';
import { ProviderMark } from '../../shared/provider-mark';

@Component({
  selector: 'app-pull-request-page',
  imports: [RouterLink, Icon, ProviderMark],
  templateUrl: './pull-request.html',
  styleUrl: './pull-request.scss',
  encapsulation: ViewEncapsulation.None,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PullRequestPage {
  readonly Math = Math;
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(ReviewerApi);
  private readonly preferences = inject(ReviewPreferencesService);

  readonly provider = signal<ProviderId>('azure-devops');
  readonly repository = signal('');
  readonly pullRequest = signal<PullRequestDetail | null>(null);
  readonly files = signal<ChangedFileSummary[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly activeTab = signal<'overview' | 'files' | 'commits'>('overview');
  readonly depth = signal<ReviewDepth>(this.preferences.defaultDepth());
  readonly publishConfirmationOpen = signal(false);
  readonly submitting = signal(false);

  readonly copyStatus = signal('');
  readonly repositoryName = computed(() => this.repository().split('/').at(-1) ?? this.repository());
  readonly projectCount = computed(() => new Set(this.files().map(file => this.fileProject(file))).size);
  fileProject(file: ChangedFileSummary): string {
    const path = file.file_path.replaceAll('\\', '/');
    const match = path.match(/^(?:apps|packages|projects|services)\/([^/]+)\//);
    return match?.[1] ?? this.repositoryName();
  }
  fileType(file: ChangedFileSummary): string {
    if (/(^|\/)(tests?|__tests__)\/|\.(test|spec)\./i.test(file.file_path)) return 'test';
    const ext = file.file_path.split('.').pop()?.toLowerCase();
    if (ext === 'tsx' || ext === 'jsx') return 'react';
    if (ext === 'ts') return 'ts';
    if (ext === 'js' || ext === 'mjs' || ext === 'cjs') return 'js';
    return 'file';
  }
  async copyCommit(): Promise<void> {
    try { await navigator.clipboard.writeText(this.pullRequest()?.head_commit ?? ''); this.copyStatus.set('Commit copied'); }
    catch { this.copyStatus.set('Unable to copy the commit.'); }
  }
  @HostListener('document:keydown.escape') closeConfirmation(): void { this.publishConfirmationOpen.set(false); }

  readonly additions = computed(() => this.sumKnownDiffValues('additions'));
  readonly deletions = computed(() => this.sumKnownDiffValues('deletions'));
  readonly languageSummary = computed(() => {
    const languages = [...new Set(this.files().map((file) => file.language).filter(Boolean))];
    return languages.length ? languages.join(', ') : 'Resolved during review';
  });

  constructor() {
    const pullNumber = Number(this.route.snapshot.paramMap.get('pullNumber'));
    const provider = this.route.snapshot.queryParamMap.get('provider');
    const repository = this.route.snapshot.queryParamMap.get('repository');
    if (provider === 'github' || provider === 'azure-devops') this.provider.set(provider);
    if (repository) this.repository.set(repository);
    if (!Number.isFinite(pullNumber) || pullNumber <= 0 || !repository) {
      this.loading.set(false);
      this.error.set('Open a pull request from the dashboard so its provider and repository are known.');
      return;
    }
    this.load(pullNumber);
  }

  load(pullNumber: number): void {
    this.loading.set(true);
    this.error.set(null);
    forkJoin({
      pullRequest: this.api.getPullRequest(this.provider(), this.repository(), pullNumber),
      files: this.api.getChangedFiles(this.provider(), this.repository(), pullNumber),
    }).subscribe({
      next: ({ pullRequest, files }) => {
        this.pullRequest.set(pullRequest);
        this.files.set(files.items);
        this.loading.set(false);
      },
      error: (error) => {
        this.loading.set(false);
        this.error.set(
          error?.error?.detail ??
            'Live pull request metadata could not be loaded.',
        );
      },
    });
  }

  requestPublish(): void {
    this.publishConfirmationOpen.set(true);
  }

  setDepth(value: ReviewDepth): void {
    this.depth.set(value);
  }

  startReview(publish: boolean): void {
    const pullRequest = this.pullRequest();
    if (!pullRequest) {
      this.error.set('Pull request metadata must load before a review can start.');
      return;
    }
    this.publishConfirmationOpen.set(false);
    this.submitting.set(true);
    this.error.set(null);
    this.api
      .startReview({
        provider: this.provider(),
        repository: this.repository(),
        pull_number: pullRequest.number,
        review_depth: this.depth(),
        publish,
        max_workers: this.preferences.maxWorkers(),
      })
      .subscribe({
        next: (job) => {
          void this.router.navigate(['/reviews', job.id, 'progress']);
        },
        error: (error) => {
          this.submitting.set(false);
          this.error.set(error?.error?.detail ?? 'The review could not be started.');
        },
      });
  }

  statusClass(status: string): string {
    return `file-status ${status.toLowerCase()}`;
  }

  authorInitials(author: string): string {
    return author
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part.charAt(0))
      .join('')
      .toUpperCase();
  }

  private sumKnownDiffValues(key: 'additions' | 'deletions'): number | null {
    const values = this.files().map((file) => file[key]);
    if (values.some(value => typeof value !== 'number' || !Number.isFinite(value))) return null;
    return values.reduce<number>((total, value) => total + (value ?? 0), 0);
  }
}
