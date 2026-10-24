import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';
import {
  LucideAtom, LucideFlaskConical, LucideExternalLink,
  LucideFileText, LucideCopy, LucideDatabase, LucideLayoutDashboard, LucideCircleAlert, LucideX,
  LucideArrowRight,
  LucideBot,
  LucideChevronRight,
  LucideCode2,
  LucideFileCode2,
  LucideFileDiff,
  LucideGitBranch,
  LucideLockKeyhole,
  LucideMinus,
  LucideMoreHorizontal,
  LucidePlay,
  LucidePlus,
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
          LucideAtom, LucideFlaskConical, LucideExternalLink,
          LucideFileText, LucideCopy, LucideDatabase, LucideLayoutDashboard, LucideCircleAlert, LucideX,
          LucideArrowRight,
          LucideBot,
          LucideChevronRight,
          LucideCode2,
          LucideFileCode2,
          LucideFileDiff,
          LucideGitBranch,
          LucideLockKeyhole,
          LucideMinus,
          LucideMoreHorizontal,
          LucidePlay,
          LucidePlus,
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
            startReview: jasmine.createSpy('startReview').and.returnValue(of({ id: 'new-job' })),
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

  it('shows the four Figma file columns and all files on the Changed Files tab', () => {
    const fixture = TestBed.createComponent(PullRequestPage); fixture.detectChanges();
    const headers = [...fixture.nativeElement.querySelectorAll('thead th')].map((el: any) => el.textContent.trim());
    expect(headers).toEqual(['File', 'Status', '+ / -', 'Project']);
    expect(fixture.nativeElement.querySelector('.change-summary').textContent).toContain('Projects');
    fixture.componentInstance.activeTab.set('files'); fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('tbody tr').length).toBe(1);
  });
  it('sends the selected depth for a dry run and requires confirmation before publishing', () => {
    const fixture = TestBed.createComponent(PullRequestPage); fixture.detectChanges();
    spyOn(TestBed.inject(Router), 'navigate').and.resolveTo(true);
    const api = TestBed.inject(ReviewerApi);
    fixture.componentInstance.setDepth('deep');
    fixture.componentInstance.requestPublish(); fixture.detectChanges();
    expect(api.startReview).not.toHaveBeenCalled();
    expect(fixture.nativeElement.querySelector('[role="dialog"]')).toBeTruthy();
    fixture.componentInstance.closeConfirmation(); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="dialog"]')).toBeNull();
    fixture.componentInstance.startReview(false);
    expect(api.startReview).toHaveBeenCalledWith(jasmine.objectContaining({ review_depth: 'deep', publish: false, pull_number: 42 }));
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
  it('shows live line counts, real zeros, and avoids incomplete totals', () => {
    const fixture = TestBed.createComponent(PullRequestPage); fixture.detectChanges();
    const page = fixture.componentInstance;
    expect(page.additions()).toBe(6); expect(page.deletions()).toBe(2);
    expect(fixture.nativeElement.querySelector('.diff-stat').textContent).toContain('+6');
    page.files.set([{ file_path: 'empty.ts', status: 'added', language: null, changed_line_count: 0, additions: 0, deletions: 0 }]);
    fixture.detectChanges();
    expect(page.additions()).toBe(0); expect(page.deletions()).toBe(0);
    expect(fixture.nativeElement.querySelector('.diff-stat').textContent).toContain('+0');
    page.files.set([...page.files(), { file_path: 'binary.png', status: 'added', language: null, changed_line_count: 0, additions: null, deletions: null }]);
    expect(page.additions()).toBeNull(); expect(page.deletions()).toBeNull();
    page.files.set([]); expect(page.additions()).toBe(0); expect(page.deletions()).toBe(0);
  });

});
