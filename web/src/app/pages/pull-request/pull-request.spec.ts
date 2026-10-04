import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import {
  LucideArrowRight,
  LucideBot,
  LucideChevronRight,
  LucideCode2,
  LucideFileCode2,
  LucideFileDiff,
  LucideGitBranch,
  LucideLockKeyhole,
  LucideMoreHorizontal,
  LucidePlay,
  LucideRocket,
  LucideShieldCheck,
  LucideSparkles,
  LucideTestTube2,
  LucideWorkflow,
  provideLucideIcons,
} from '@lucide/angular';
import { of } from 'rxjs';

import { ReviewerApi } from '../../core/api.service';
import { PullRequestPage } from './pull-request';

describe('PullRequestPage context header', () => {
  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      imports: [PullRequestPage],
      providers: [
        provideRouter([]),
        provideLucideIcons(
          LucideArrowRight,
          LucideBot,
          LucideChevronRight,
          LucideCode2,
          LucideFileCode2,
          LucideFileDiff,
          LucideGitBranch,
          LucideLockKeyhole,
          LucideMoreHorizontal,
          LucidePlay,
          LucideRocket,
          LucideShieldCheck,
          LucideSparkles,
          LucideTestTube2,
          LucideWorkflow,
        ),
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: convertToParamMap({ pullNumber: '42' }),
              queryParamMap: convertToParamMap({
                provider: 'github',
                repository: 'acme/store',
              }),
            },
          },
        },
        {
          provide: ReviewerApi,
          useValue: {
            getPullRequest: () =>
              of({
                provider: 'github',
                repository: 'acme/store',
                number: 42,
                title: 'Keep review context visible',
                author: 'Developer',
                base_branch: 'main',
                head_branch: 'feature/sticky-context',
                head_commit: 'abcdef1234567890',
                state: 'open',
                commit_count: 2,
              }),
            getChangedFiles: () =>
              of({
                total: 1,
                items: [
                  {
                    file_path: 'src/app.ts',
                    status: 'modified',
                    language: 'typescript',
                    changed_line_count: 8,
                    additions: 6,
                    deletions: 2,
                  },
                ],
              }),
          },
        },
      ],
    });
  });

  it('keeps the complete pull-request identity in the sticky context header', () => {
    const fixture = TestBed.createComponent(PullRequestPage);
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    const header = element.querySelector<HTMLElement>(
      '[data-testid="pull-request-context-header"]',
    );

    expect(header).not.toBeNull();
    expect(header?.classList.contains('sticky-page-heading')).toBeTrue();
    expect(header?.textContent).toContain('Keep review context visible');
    expect(header?.textContent).toContain('acme/store');
    expect(header?.textContent).toContain('feature/sticky-context');
    expect(header?.textContent).toContain('1');
    expect(header?.textContent).toContain('changed files');
  });
});
