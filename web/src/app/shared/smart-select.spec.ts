import { TestBed } from '@angular/core/testing';
import {
  LucideArrowRight,
  LucideCheck,
  LucideChevronDown,
  LucideCircleAlert,
  LucideLoaderCircle,
  LucideSearch,
  provideLucideIcons,
} from '@lucide/angular';

import { SmartSelect } from './smart-select';

describe('SmartSelect', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SmartSelect],
      providers: [
        provideLucideIcons(
          LucideArrowRight,
          LucideCheck,
          LucideChevronDown,
          LucideCircleAlert,
          LucideLoaderCircle,
          LucideSearch,
        ),
      ],
    }).compileComponents();
  });

  it('filters and selects an API-backed option', () => {
    const fixture = TestBed.createComponent(SmartSelect);
    fixture.componentRef.setInput('searchable', true);
    fixture.componentRef.setInput('options', [
      { value: 'api', label: 'API service', description: 'Backend' },
      { value: 'shop', label: 'Shop web', description: 'Frontend' },
    ]);
    const selected: string[] = [];
    fixture.componentInstance.valueChange.subscribe((value) => selected.push(value));
    fixture.detectChanges();

    fixture.nativeElement.querySelector('.smart-select-trigger').click();
    fixture.detectChanges();
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    input.value = 'shop';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    const options = fixture.nativeElement.querySelectorAll('.smart-select-option');

    expect(options.length).toBe(1);
    expect(options[0].textContent).toContain('Shop web');
    options[0].click();
    expect(selected).toEqual(['shop']);
    expect(fixture.componentInstance.open()).toBeFalse();
  });

  it('supports a manual value when provider discovery returns no match', () => {
    const fixture = TestBed.createComponent(SmartSelect);
    fixture.componentRef.setInput('searchable', true);
    fixture.componentRef.setInput('allowCustomValue', true);
    fixture.componentRef.setInput('options', []);
    const selected: string[] = [];
    fixture.componentInstance.valueChange.subscribe((value) => selected.push(value));
    fixture.detectChanges();

    fixture.nativeElement.querySelector('.smart-select-trigger').click();
    fixture.detectChanges();
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    input.value = 'manual-repository';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    (fixture.nativeElement.querySelector('.custom-entry') as HTMLButtonElement).click();

    expect(selected).toEqual(['manual-repository']);
  });

  it('supports keyboard navigation and selection', () => {
    const fixture = TestBed.createComponent(SmartSelect);
    fixture.componentRef.setInput('options', [
      { value: 'all', label: 'All statuses' },
      { value: 'passed', label: 'Passed' },
    ]);
    const selected: string[] = [];
    fixture.componentInstance.valueChange.subscribe((value) => selected.push(value));
    fixture.detectChanges();
    const trigger = fixture.nativeElement.querySelector(
      '.smart-select-trigger',
    ) as HTMLButtonElement;

    trigger.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    trigger.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    trigger.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    fixture.detectChanges();

    expect(selected).toEqual(['passed']);
  });

  it('closes with Escape and an outside click', () => {
    const fixture = TestBed.createComponent(SmartSelect);
    fixture.detectChanges();
    const trigger = fixture.nativeElement.querySelector(
      '.smart-select-trigger',
    ) as HTMLButtonElement;

    trigger.click();
    fixture.detectChanges();
    expect(fixture.componentInstance.open()).toBeTrue();
    trigger.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(fixture.componentInstance.open()).toBeFalse();

    trigger.click();
    document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    expect(fixture.componentInstance.open()).toBeFalse();
  });

  it('renders loading, empty, and provider-error states', () => {
    const fixture = TestBed.createComponent(SmartSelect);
    fixture.componentRef.setInput('loading', true);
    fixture.componentRef.setInput('error', 'Provider discovery failed.');
    fixture.detectChanges();

    fixture.nativeElement.querySelector('.smart-select-trigger').click();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.smart-select-state').textContent).toContain(
      'Loading options',
    );
    expect(fixture.nativeElement.querySelector('.smart-select-error').textContent).toContain(
      'Provider discovery failed',
    );

    fixture.componentRef.setInput('loading', false);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.smart-select-state').textContent).toContain(
      'No options found',
    );
  });
});
