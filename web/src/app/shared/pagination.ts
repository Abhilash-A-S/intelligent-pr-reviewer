import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
@Component({
  selector: 'app-pagination',
  template: `@if (total() > 0) { <nav class="pagination" aria-label="Pagination">
    <button type="button" aria-label="Previous page" [disabled]="page() <= 1" (click)="pageChange.emit(page() - 1)">‹</button>
    @for (number of buttons(); track $index) {
      @if (number === 0) { <span aria-hidden="true">…</span> }
      @else { <button type="button" [attr.aria-label]="'Page ' + number" [attr.aria-current]="number === page() ? 'page' : null" [class.active]="number === page()" (click)="pageChange.emit(number)">{{ number }}</button> }
    }
    <button type="button" aria-label="Next page" [disabled]="page() >= pages()" (click)="pageChange.emit(page() + 1)">›</button>
  </nav> }`,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Pagination {
  readonly total = input.required<number>();
  readonly page = input.required<number>();
  readonly pageSize = input.required<number>();
  readonly pageChange = output<number>();
  readonly pages = computed(() => Math.max(1, Math.ceil(this.total() / this.pageSize())));
  readonly buttons = computed(() => {
    const last = this.pages(), current = this.page();
    if (last <= 7) return Array.from({length: last}, (_, i) => i + 1);
    const selected = [...new Set([1, last, current - 1, current, current + 1, ...(current < 5 ? [2, 3, 4, 5] : [])])].filter(n => n > 0 && n <= last).sort((a,b) => a-b);
    const result: number[] = [];
    for (const n of selected) { if (result.length && n - result[result.length-1] > 1) result.push(0); result.push(n); }
    return result;
  });
}
