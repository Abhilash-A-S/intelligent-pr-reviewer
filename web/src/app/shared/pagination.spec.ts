import { TestBed } from '@angular/core/testing';
import { Pagination } from './pagination';
describe('Pagination', () => {
  it('selects pages and disables navigation at boundaries', () => {
    const fixture = TestBed.createComponent(Pagination);
    fixture.componentRef.setInput('total', 12); fixture.componentRef.setInput('pageSize', 4); fixture.componentRef.setInput('page', 1); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[aria-label="Previous page"]').disabled).toBeTrue();
    const changed = jasmine.createSpy(); fixture.componentInstance.pageChange.subscribe(changed);
    fixture.nativeElement.querySelector('[aria-label="Page 2"]').click(); expect(changed).toHaveBeenCalledWith(2);
    fixture.componentRef.setInput('page', 3); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[aria-label="Next page"]').disabled).toBeTrue();
  });
});
