import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
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
      <section class="smart-select-panel" [class.has-error]="!!error()">
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
    if (this.searchable()) {
      setTimeout(() =>
        this.element.nativeElement.querySelector<HTMLInputElement>('input')?.focus(),
      );
    }
  }

  close(): void {
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
