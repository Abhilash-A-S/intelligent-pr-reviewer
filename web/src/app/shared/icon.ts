import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { LucideDynamicIcon } from '@lucide/angular';

@Component({
  selector: 'app-icon',
  imports: [LucideDynamicIcon],
  template: '<svg [lucideIcon]="name()" [attr.aria-hidden]="decorative()"></svg>',
  host: { class: 'app-icon' },
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Icon {
  readonly name = input.required<string>();
  readonly decorative = input(true);
}
