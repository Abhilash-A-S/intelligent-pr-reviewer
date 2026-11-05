import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { ReviewerApi } from './api.service';

describe('ReviewerApi', () => {
  let api: ReviewerApi;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    api = TestBed.inject(ReviewerApi);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('omits an empty organization query parameter', () => {
    api.listOrganizations('azure-devops').subscribe();

    const request = http.expectOne(
      (candidate) =>
        candidate.url === '/api/repository-discovery/organizations' &&
        candidate.params.get('provider') === 'azure-devops',
    );
    expect(request.request.params.has('query')).toBeFalse();
    request.flush({ provider: 'azure-devops', items: [], total: 0 });
  });

  it('requests validated provider and Ollama health', () => {
    api.health(true).subscribe();

    const request = http.expectOne('/api/health?probe_ollama=true&probe_providers=true');
    request.flush({});
  });
});
