import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  DestroyRef,
  HostListener,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';

import { Icon } from './icon';

export interface SmartSelectOption {
  value: string;
  label: string;
  description?: string;
  searchText?: string;
}

let smartSelectSequence = 0;

@Component({
  selector: 'app-smart-select',
  imports: [Icon],
  host: { class: 'smart-select-host' },
  template: `
    <button
      class="smart-select-trigger"
      type="button"
      role="combobox"
      aria-haspopup="listbox"
      [attr.aria-label]="ariaLabel()"
      [attr.aria-expanded]="open()"
      [attr.aria-controls]="listboxId"
      [attr.aria-activedescendant]="open() ? activeOptionId() : null"
      [disabled]="disabled()"
      (click)="toggle()"
      (keydown)="onTriggerKeydown($event)"
    >
      @if (icon()) {
        <app-icon [name]="icon()" />
      }
      <span class="smart-select-value" [class.placeholder]="!value()">
        <strong>{{ selectedLabel() }}</strong>
        @if (selectedDescription()) {
          <small>{{ selectedDescription() }}</small>
        }
      </span>
      @if (loading()) {
        <app-icon class="smart-select-spinner" name="loader-circle" />
      } @else {
        <app-icon class="smart-select-chevron" name="chevron-down" />
      }
    </button>

    @if (open()) {
      <section class="smart-select-panel" popover="manual" [class.has-error]="!!error()"
        [style.left.px]="panelLeft()" [style.top.px]="panelTop()" [style.bottom.px]="panelBottom()"
        [style.width.px]="panelWidth()" [style.max-height.px]="panelMaxHeight()">
        @if (searchable()) {
          <label class="smart-select-search">
            <app-icon name="search" />
            <input
              type="search"
              [attr.aria-label]="'Search ' + ariaLabel()"
              [placeholder]="searchPlaceholder()"
              [value]="query()"
              (input)="updateQuery($event)"
              (keydown)="onSearchKeydown($event)"
              autocomplete="off"
            />
          </label>
        }

        <div class="smart-select-options" [id]="listboxId" role="listbox">
          @if (loading()) {
            <div class="smart-select-state">
              <app-icon name="loader-circle" class="smart-select-spinner" />Loading options…
            </div>
          } @else {
            @for (option of filteredOptions(); track option.value; let index = $index) {
              <button
                type="button"
                class="smart-select-option"
                role="option"
                [id]="optionId(index)"
                [class.active]="activeIndex() === index"
                [class.selected]="value() === option.value"
                [attr.aria-selected]="value() === option.value"
                (mouseenter)="activeIndex.set(index)"
                (click)="select(option.value)"
              >
                <span
                  ><strong>{{ option.label }}</strong>
                  @if (option.description) {
                    <small>{{ option.description }}</small>
                  }
                </span>
                @if (value() === option.value) {
                  <app-icon name="check" />
                }
              </button>
            }

            @if (showCustomOption()) {
              <button
                type="button"
                class="smart-select-option custom-entry"
                role="option"
                [id]="optionId(filteredOptions().length)"
                [class.active]="activeIndex() === filteredOptions().length"
                [attr.aria-selected]="false"
                (mouseenter)="activeIndex.set(filteredOptions().length)"
                (click)="select(query().trim())"
              >
                <span
                  ><strong>Use “{{ query().trim() }}”</strong
                  ><small>Enter this value manually</small></span
                >
                <app-icon name="arrow-right" />
              </button>
            }

            @if (!filteredOptions().length && !showCustomOption()) {
              <div class="smart-select-state"><app-icon name="search" />{{ emptyLabel() }}</div>
            }
          }
        </div>

        @if (error()) {
          <div class="smart-select-error"><app-icon name="circle-alert" />{{ error() }}</div>
        }
      </section>
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SmartSelect {
  private readonly element: ElementRef<HTMLElement> = inject(ElementRef);

  readonly panelLeft = signal(0);
  readonly panelTop = signal<number | null>(0);
  readonly panelBottom = signal<number | null>(null);
  readonly panelWidth = signal(250);
  readonly panelMaxHeight = signal(350);
  private readonly destroyRef = inject(DestroyRef);
  private openingTimer?: ReturnType<typeof setTimeout>;

  constructor() {
    const reposition = () => { if (this.open()) this.positionPanel(); };
    window.addEventListener('scroll', reposition, true);
    window.addEventListener('resize', reposition);
    this.destroyRef.onDestroy(() => {
      clearTimeout(this.openingTimer);
      window.removeEventListener('scroll', reposition, true);
      window.removeEventListener('resize', reposition);
    });
  }

  private panel(): HTMLElement | null {
    return this.element.nativeElement.querySelector<HTMLElement>('.smart-select-panel');
  }

  positionPanel(): void {
    const trigger = this.element.nativeElement.querySelector('.smart-select-trigger');
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const margin = 8, gap = 7;
    const width = Math.min(Math.max(rect.width, 250), window.innerWidth - margin * 2);
    const below = Math.max(0, window.innerHeight - rect.bottom - gap - margin);
    const above = Math.max(0, rect.top - gap - margin);
    const upward = below < 200 && above > below;
    this.panelLeft.set(Math.max(margin, Math.min(rect.left, window.innerWidth - width - margin)));
    this.panelWidth.set(width);
    this.panelTop.set(upward ? null : Math.max(margin, rect.bottom + gap));
    this.panelBottom.set(upward ? window.innerHeight - rect.top + gap : null);
    this.panelMaxHeight.set(Math.min(350, upward ? above : below));
  }

  readonly options = input<readonly SmartSelectOption[]>([]);
  readonly value = input('');
  readonly placeholder = input('Select an option');
  readonly ariaLabel = input('Select an option');
  readonly icon = input('');
  readonly searchable = input(false);
  readonly searchPlaceholder = input('Search options…');
  readonly loading = input(false);
  readonly disabled = input(false);
  readonly allowCustomValue = input(false);
  readonly emptyLabel = input('No options found');
  readonly error = input<string | null>(null);
  readonly valueChange = output<string>();

  readonly open = signal(false);
  readonly query = signal('');
  readonly activeIndex = signal(0);
  readonly listboxId = `smart-select-${++smartSelectSequence}`;

  readonly filteredOptions = computed(() => {
    const term = this.query().trim().toLocaleLowerCase();
    if (!term) return this.options();
    return this.options().filter((option) =>
      `${option.label} ${option.description ?? ''} ${option.searchText ?? ''}`
        .toLocaleLowerCase()
        .includes(term),
    );
  });

  readonly selectedOption = computed(() =>
    this.options().find((option) => option.value === this.value()),
  );
  readonly selectedLabel = computed(
    () => this.selectedOption()?.label ?? (this.value() || this.placeholder()),
  );
  readonly selectedDescription = computed(() => this.selectedOption()?.description ?? '');
  readonly showCustomOption = computed(() => {
    const candidate = this.query().trim();
    return (
      this.allowCustomValue() &&
      !!candidate &&
      !this.options().some(
        (option) =>
          option.value.toLocaleLowerCase() === candidate.toLocaleLowerCase() ||
          option.label.toLocaleLowerCase() === candidate.toLocaleLowerCase(),
      )
    );
  });
  readonly activeOptionId = computed(() => {
    const count = this.filteredOptions().length + (this.showCustomOption() ? 1 : 0);
    return count ? this.optionId(Math.min(this.activeIndex(), count - 1)) : null;
  });

  toggle(): void {
    if (this.disabled()) return;
    this.open() ? this.close() : this.openPanel();
  }

  openPanel(): void {
    if (this.disabled()) return;
    this.open.set(true);
    this.query.set('');
    this.activeIndex.set(
      Math.max(
        0,
        this.options().findIndex((option) => option.value === this.value()),
      ),
    );
    this.positionPanel();
    clearTimeout(this.openingTimer);
    this.openingTimer = setTimeout(() => {
      if (!this.open()) return;
      const panel = this.panel();
      if (panel && typeof panel.showPopover === 'function') panel.showPopover();
      this.positionPanel();
      if (this.searchable()) panel?.querySelector<HTMLInputElement>('input')?.focus();
    });
  }

  close(): void {
    clearTimeout(this.openingTimer);
    const panel = this.panel();
    if (panel?.matches(':popover-open')) panel.hidePopover();
    this.open.set(false);
    this.query.set('');
  }

  select(value: string): void {
    this.valueChange.emit(value);
    this.close();
    this.element.nativeElement.querySelector<HTMLButtonElement>('.smart-select-trigger')?.focus();
  }

  updateQuery(event: Event): void {
    this.query.set((event.target as HTMLInputElement).value);
    this.activeIndex.set(0);
  }

  onTriggerKeydown(event: KeyboardEvent): void {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!this.open()) this.openPanel();
      else this.moveActive(event.key === 'ArrowDown' ? 1 : -1);
    } else if ((event.key === 'Enter' || event.key === ' ') && !this.open()) {
      event.preventDefault();
      this.openPanel();
    } else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      this.selectActive();
    } else if (event.key === 'Escape') {
      this.close();
    }
  }

  onSearchKeydown(event: KeyboardEvent): void {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      this.moveActive(event.key === 'ArrowDown' ? 1 : -1);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      this.selectActive();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      this.close();
      this.element.nativeElement.querySelector<HTMLButtonElement>('.smart-select-trigger')?.focus();
    }
  }

  optionId(index: number): string {
    return `${this.listboxId}-option-${index}`;
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (!this.open()) return;
    this.close();
    this.element.nativeElement.querySelector<HTMLButtonElement>('.smart-select-trigger')?.focus();
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    if (this.open() && !this.element.nativeElement.contains(event.target as Node)) this.close();
  }

  private moveActive(offset: number): void {
    const count = this.filteredOptions().length + (this.showCustomOption() ? 1 : 0);
    if (!count) return;
    this.activeIndex.update((index) => (index + offset + count) % count);
  }

  private selectActive(): void {
    const options = this.filteredOptions();
    const active = this.activeIndex();
    if (active < options.length) this.select(options[active].value);
    else if (this.showCustomOption()) this.select(this.query().trim());
  }
}
