import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import {
  LucideBuilding2,
  LucideChevronDown,
  LucideClock3,
  LucideDatabase,
  LucideGitBranch,
  LucideGitPullRequest,
  LucideListFilter,
  LucideOctagonAlert,
  LucideRefreshCw,
  LucideSearch,
  LucideShieldCheck,
  provideLucideIcons,
} from '@lucide/angular';

import { DashboardPage } from './dashboard';

describe('DashboardPage metrics', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      imports: [DashboardPage],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideLucideIcons(
          LucideBuilding2,
          LucideChevronDown,
          LucideClock3,
          LucideDatabase,
          LucideGitBranch,
          LucideGitPullRequest,
          LucideListFilter,
          LucideOctagonAlert,
          LucideRefreshCw,
          LucideSearch,
          LucideShieldCheck,
        ),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('renders compact status metrics from live pull-request state without helper copy', () => {
    const fixture = TestBed.createComponent(DashboardPage);
    const page = fixture.componentInstance;

    http
      .expectOne(
        (request) =>
          request.url === '/api/repository-discovery/organizations' &&
          request.params.get('provider') === 'github',
      )
      .flush({ provider: 'github', items: [], total: 0 });

    page.workspace.pullRequests.set([
      {
        number: 1,
        title: 'Awaiting review',
        author: 'A',
        base_branch: 'main',
        head_branch: 'feature/a',
        state: 'open',
      },
      {
        number: 2,
        title: 'Blocked review',
        author: 'B',
        base_branch: 'main',
        head_branch: 'feature/b',
        state: 'open',
        review_status: 'blocked',
      },
      {
        number: 3,
        title: 'Passing review',
        author: 'C',
        base_branch: 'main',
        head_branch: 'feature/c',
        state: 'open',
        review_status: 'passed',
      },
    ]);
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    const cards = Array.from(
      element.querySelectorAll<HTMLElement>('.dashboard-metrics .metric-card'),
    );
    const values = cards.map((card) => card.querySelector('strong')?.textContent?.trim());
    const labels = cards.map((card) => card.querySelector('small')?.textContent?.trim());

    expect(cards.length).toBe(4);
    expect(values).toEqual(['3', '1', '1', '1']);
    expect(labels).toEqual(['Open PRs', 'Awaiting review', 'Blocked', 'Passed']);
    expect(element.querySelector('.dashboard-metrics em')).toBeNull();
  });
});
