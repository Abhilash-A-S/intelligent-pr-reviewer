import { ChangeDetectionStrategy, Component, effect, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationCancel, NavigationEnd, NavigationError, NavigationSkipped, NavigationStart, Router, RouterOutlet } from '@angular/router';
import { NgxSpinnerComponent, NgxSpinnerService } from 'ngx-spinner';
import { LoadingService } from './core/loading.service';
import { ThemeService } from './core/theme.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, NgxSpinnerComponent],
  template: `
    <div [attr.inert]="loading.busy() ? '' : null" [attr.aria-busy]="loading.busy()">
      <router-outlet />
    </div>
    @if (loading.busy()) {
      <div class="request-backdrop" role="status" aria-label="Loading" aria-live="polite"></div>
    }
    <ngx-spinner name="foreground" size="medium" type="ball-clip-rotate-pulse"
      color="var(--accent)" bdColor="transparent" [zIndex]="10001"
      [fullScreen]="true" [disableAnimation]="true" aria-hidden="true" />
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App {
  readonly loading = inject(LoadingService);
  private readonly theme = inject(ThemeService);
  private readonly spinner = inject(NgxSpinnerService);

  constructor() {
    inject(Router).events.pipe(takeUntilDestroyed()).subscribe(event => {
      if (event instanceof NavigationStart) this.loading.navigating.set(true);
      else if (event instanceof NavigationEnd || event instanceof NavigationCancel ||
        event instanceof NavigationError || event instanceof NavigationSkipped) {
        this.loading.navigating.set(false);
      }
    });
    effect(() => {
      if (this.loading.busy()) void this.spinner.show('foreground');
      else void this.spinner.hide('foreground');
    });
  }
}
