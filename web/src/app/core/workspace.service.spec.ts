import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { WorkspaceService } from './workspace.service';

describe('WorkspaceService live data', () => {
  let http: HttpTestingController;
  let service: WorkspaceService;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    service = TestBed.inject(WorkspaceService);
  });

  afterEach(() => http.verify());

  it('starts empty instead of displaying fabricated pull requests', () => {
    expect(service.organization()).toBe('');
    expect(service.repositoryName()).toBe('');
    expect(service.pullRequests()).toEqual([]);
    expect(service.loaded()).toBeFalse();
  });

  it('requires a complete repository selection before requesting provider data', () => {
    service.refreshPullRequests();

    expect(service.error()).toContain('GitHub owner');
    http.expectNone((request) => request.url.startsWith('/api/'));
  });

  it('loads provider pull requests and derives review status from live jobs', () => {
    service.organization.set('acme');
    service.repositoryName.set('store');
    service.refreshPullRequests();

    http
      .expectOne(
        (request) =>
          request.url === '/api/pull-requests' &&
          request.params.get('repository') === 'acme/store',
      )
      .flush({
        provider: 'github',
        repository: 'acme/store',
        total: 1,
        items: [
          {
            number: 17,
            title: 'Use live review data',
            author: 'developer',
            base_branch: 'main',
            head_branch: 'feature/live-data',
            state: 'open',
            updated_at: '2026-10-04T05:00:00Z',
          },
        ],
      });
    http.expectOne('/api/reviews?limit=200').flush({
      total: 1,
      items: [
        {
          id: 'job-17',
          command: {
            provider: 'github',
            repository: 'acme/store',
            pull_number: 17,
            review_depth: 'standard',
            publish: false,
          },
          status: 'completed',
          created_at: '2026-10-04T05:05:00Z',
          result_summary: {
            title: 'Use live review data',
            author: 'developer',
            decision: 'pass',
            findings: 0,
            duration_seconds: 8.4,
            dry_run: true,
          },
        },
      ],
    });

    expect(service.pullRequests().length).toBe(1);
    expect(service.pullRequests()[0].review_status).toBe('passed');
    expect(service.loaded()).toBeTrue();
  });

  it('clears repository results when switching providers', () => {
    service.pullRequests.set([
      {
        number: 1,
        title: 'Loaded item',
        author: 'developer',
        base_branch: 'main',
        head_branch: 'feature',
        state: 'open',
      },
    ]);
    service.loaded.set(true);

    service.setProvider('azure-devops');

    expect(service.pullRequests()).toEqual([]);
    expect(service.loaded()).toBeFalse();
  });
});
