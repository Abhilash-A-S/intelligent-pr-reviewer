import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import {
  ChangedFileListResponse,
  DiscoveryResponse,
  HealthResponse,
  OrganizationSummary,
  ProjectSummary,
  ProviderId,
  PullRequestDetail,
  PullRequestListResponse,
  ReviewCreateRequest,
  ReviewJob,
  ReviewListResponse,
  RepositorySummary,
} from './models';

@Injectable({ providedIn: 'root' })
export class ReviewerApi {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = '/api';

  health(probeOllama = true, probeProviders = true): Observable<HealthResponse> {
    return this.http.get<HealthResponse>(`${this.baseUrl}/health`, {
      params: { probe_ollama: probeOllama, probe_providers: probeProviders },
    });
  }

  listOrganizations(
    provider: ProviderId,
    query = '',
  ): Observable<DiscoveryResponse<OrganizationSummary>> {
    let params = new HttpParams().set('provider', provider);
    if (query.trim()) params = params.set('query', query.trim());
    return this.http.get<DiscoveryResponse<OrganizationSummary>>(
      `${this.baseUrl}/repository-discovery/organizations`,
      { params },
    );
  }

  listProjects(
    provider: ProviderId,
    organization: string,
    query = '',
  ): Observable<DiscoveryResponse<ProjectSummary>> {
    let params = new HttpParams()
      .set('provider', provider)
      .set('organization', organization);
    if (query.trim()) params = params.set('query', query.trim());
    return this.http.get<DiscoveryResponse<ProjectSummary>>(
      `${this.baseUrl}/repository-discovery/projects`,
      { params },
    );
  }

  listRepositories(
    provider: ProviderId,
    organization: string,
    project?: string,
    query = '',
  ): Observable<DiscoveryResponse<RepositorySummary>> {
    let params = new HttpParams()
      .set('provider', provider)
      .set('organization', organization);
    if (project) params = params.set('project', project);
    if (query.trim()) params = params.set('query', query.trim());
    return this.http.get<DiscoveryResponse<RepositorySummary>>(
      `${this.baseUrl}/repository-discovery/repositories`,
      { params },
    );
  }

  listPullRequests(
    provider: ProviderId,
    repository: string,
    state: 'open' | 'closed' | 'all' = 'open',
  ): Observable<PullRequestListResponse> {
    const params = new HttpParams()
      .set('provider', provider)
      .set('repository', repository)
      .set('state', state);
    return this.http.get<PullRequestListResponse>(`${this.baseUrl}/pull-requests`, { params });
  }

  getPullRequest(
    provider: ProviderId,
    repository: string,
    pullNumber: number,
  ): Observable<PullRequestDetail> {
    return this.http.get<PullRequestDetail>(`${this.baseUrl}/pull-requests/${pullNumber}`, {
      params: { provider, repository },
    });
  }

  getChangedFiles(
    provider: ProviderId,
    repository: string,
    pullNumber: number,
  ): Observable<ChangedFileListResponse> {
    return this.http.get<ChangedFileListResponse>(
      `${this.baseUrl}/pull-requests/${pullNumber}/files`,
      { params: { provider, repository } },
    );
  }

  startReview(request: ReviewCreateRequest): Observable<ReviewJob> {
    return this.http.post<ReviewJob>(`${this.baseUrl}/reviews`, request);
  }

  getReview(jobId: string, includeResult = true): Observable<ReviewJob> {
    return this.http.get<ReviewJob>(`${this.baseUrl}/reviews/${jobId}`, {
      params: { include_result: includeResult },
    });
  }

  listReviews(limit = 50): Observable<ReviewListResponse> {
    return this.http.get<ReviewListResponse>(`${this.baseUrl}/reviews`, { params: { limit } });
  }

  cancelReview(jobId: string): Observable<{ id: string; status: string }> {
    return this.http.delete<{ id: string; status: string }>(`${this.baseUrl}/reviews/${jobId}`);
  }
}
