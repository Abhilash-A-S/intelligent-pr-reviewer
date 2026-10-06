import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { ReviewerApi } from '../../core/api.service';
import { ReviewFinding, ReviewJob } from '../../core/models';
import { appConfig } from '../../app.config';
import { ReviewResultsPage } from './review-results';

const finding = (severity: ReviewFinding['severity'], rule: string, file: string, source = 'static'): ReviewFinding => ({
  severity, rule_id: rule, file_path: file, line_number: 10, source,
  message: 'Issue', issue: 'Issue', impact: 'Impact', evidence: 'const value = 1;',
  suggestion: 'Fix it', category: 'Security', confidence: 'high',
});
describe('ReviewResultsPage', () => {
  beforeEach(() => {
    const job = { id: 'test', status: 'completed', result: {
      findings: [finding('medium', 'empty-catch', 'client/a.ts'), finding('critical', 'secret', 'server/a.ts'), finding('low', 'timeout', 'server/b.ts', 'llm')],
      pull_request: { number: 142 },
      quality_gate: { decision: 'block', critical_count: 1, high_count: 0, medium_count: 1, low_count: 1, suggestion_count: 0 },
      diagnostics: { total_review_seconds: 143, raw_ai_findings: 3, final_ai_findings: 1, review_files_by_project: { client: 1, server: 2 } },
      publishing: { published_comments: [], failed_comments: [], skipped_duplicates: 0 }, dry_run: true,
    }} as unknown as ReviewJob;
    TestBed.configureTestingModule({ imports: [ReviewResultsPage], providers: [
      ...appConfig.providers, provideRouter([]), { provide: ActivatedRoute, useValue: { snapshot: { paramMap: new Map([['jobId', 'test']]) } } },
      { provide: ReviewerApi, useValue: { getReview: () => of(job) } },
    ] });
  });
  it('sorts by severity and initially expands the most severe finding', () => {
    const page = TestBed.createComponent(ReviewResultsPage).componentInstance;
    expect(page.visibleFindings()[0].severity).toBe('critical');
    expect(page.isExpanded(page.visibleFindings()[0])).toBeTrue();
    page.toggleFinding(page.visibleFindings()[0]);
    expect(page.isExpanded(page.visibleFindings()[0])).toBeFalse();
  });
  it('combines severity, source, project, rule, and search filters', () => {
    const page = TestBed.createComponent(ReviewResultsPage).componentInstance;
    page.setSeverity('low'); page.setSource('llm'); page.project.set('server'); page.rule.set('timeout'); page.search.set('b.ts');
    expect(page.visibleFindings().length).toBe(1);
    page.project.set('client'); expect(page.visibleFindings().length).toBe(0);
  });
  it('renders four labelled filters, evidence and accurate gate/publishing counts', () => {
    const fixture = TestBed.createComponent(ReviewResultsPage); fixture.detectChanges();
    const element: HTMLElement = fixture.nativeElement;
    expect(element.querySelectorAll('[role="combobox"]').length).toBe(4);
    expect(element.querySelector('.finding-expanded')?.textContent).toContain('const value = 1;');
    expect(element.querySelector('.publishing-stats')?.textContent).toContain('0 failures');
    expect(fixture.componentInstance.durationLabel()).toBe('02:23');
    expect(fixture.componentInstance.rejectedAiFindings()).toBe(2);
  });
  it('does not open publishing until the explicit button is clicked', () => {
    const fixture = TestBed.createComponent(ReviewResultsPage); fixture.detectChanges();
    expect(fixture.componentInstance.publishConfirmationOpen()).toBeFalse();
    (fixture.nativeElement.querySelector('.publishing-card .primary') as HTMLButtonElement).click();
    fixture.detectChanges(); expect(fixture.nativeElement.querySelector('[role="dialog"]')).toBeTruthy();
  });
});
