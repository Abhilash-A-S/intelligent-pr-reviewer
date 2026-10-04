import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { ReviewerApi } from '../core/api.service';
import { HealthResponse } from '../core/models';
import { ThemeService } from '../core/theme.service';
import { Icon } from '../shared/icon';
import { ProviderMark } from '../shared/provider-mark';

@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, Icon, ProviderMark],
  templateUrl: './app-shell.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AppShell {
  private readonly api = inject(ReviewerApi);
  readonly theme = inject(ThemeService);
  readonly sidebarCollapsed = signal(false);
  readonly mobileNavigationOpen = signal(false);
  readonly health = signal<HealthResponse | null>(null);

  readonly navigation = [
    { label: 'Dashboard', route: '/', icon: 'layout-dashboard', exact: true },
    { label: 'Review History', route: '/history', icon: 'history', exact: false },
    { label: 'Settings', route: '/settings', icon: 'settings', exact: false },
  ];

  constructor() {
    this.api.health(true).subscribe({
      next: (health) => this.health.set(health),
      error: () => this.health.set(null),
    });
  }

  providerConnected(id: string): boolean | null {
    const current = this.health();
    if (!current) return null;
    return current.providers.find((provider) => provider.id === id)?.connected ?? false;
  }

  closeMobileNavigation(): void {
    this.mobileNavigationOpen.set(false);
  }

  toggleMobileNavigation(): void {
    this.mobileNavigationOpen.update((open) => !open);
  }

  toggleSidebar(): void {
    this.sidebarCollapsed.update((collapsed) => !collapsed);
  }
}
