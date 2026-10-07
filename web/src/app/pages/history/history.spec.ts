import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { appConfig } from '../../app.config';
import { ReviewerApi } from '../../core/api.service';
import { HistoryPage } from './history';
const jobs = Array.from({length:12}, (_,i) => ({id:`job-${i}`, status:'completed', command:{provider:i%2?'github':'azure-devops',repository:i%2?'acme/web':'contoso/project/api',pull_number:i+1,publish:false}, created_at:'2026-10-05T10:00:00Z', result_summary:{title:`Review ${i}`,author:'Abhilash',decision:i%3?'pass':'block', findings:6,duration_seconds:143,severity_counts:{critical:1,high:2,medium:1,low:2,suggestion:0}}, steps:[],events:[],metrics:{}}));
describe('History filtering and pagination', () => {
  beforeEach(() => TestBed.configureTestingModule({imports:[HistoryPage],providers:[...appConfig.providers,{provide:ReviewerApi,useValue:{listReviews:()=>of({items:jobs,total:jobs.length})}}]}));
  it('paginates five rows and resets the selected page after filters change', () => {
    const fixture=TestBed.createComponent(HistoryPage),page=fixture.componentInstance;fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('tbody tr').length).toBe(5);
    page.requestedPage.set(3); expect(page.pagedRows().length).toBe(2);
    page.setProviderFilter('github'); expect(page.currentPage()).toBe(1); expect(page.filteredRows().length).toBe(6);
    page.repository.set('contoso/project/api'); expect(page.filteredRows().length).toBe(0);
    page.setProviderFilter('all'); page.startDate.set('2026-10-06'); expect(page.filteredRows().length).toBe(0);
    page.startDate.set('2026-10-05'); page.endDate.set('2026-10-05'); expect(page.filteredRows().length).toBe(12);
    page.endDate.set('2026-10-04'); expect(page.dateError()).toBeTruthy(); expect(page.filteredRows().length).toBe(0);
  });
  it('uses backend severity counts and stacks actual decisions without visible zero bars', () => {
    const fixture=TestBed.createComponent(HistoryPage),page=fixture.componentInstance;
    page.startDate.set('2026-10-05');page.endDate.set('2026-10-05');fixture.detectChanges();
    expect(page.rows()[0].severity).toEqual({danger:3,warning:1,info:2});
    expect(page.rows()[0].duration).toBe('02:23'); expect(page.trend()[0].passed).toBe(8); expect(page.trend()[0].blocked).toBe(4);
    expect(page.trend()[0].passedHeight+page.trend()[0].blockedHeight).toBeCloseTo(100);
  });
});
