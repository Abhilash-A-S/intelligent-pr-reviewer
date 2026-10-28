import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  HostListener,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';

import { AuthService } from '../core/auth.service';
import { ReviewerApi } from '../core/api.service';
import { HealthResponse, ProviderStatus } from '../core/models';
import { ThemeService } from '../core/theme.service';
import { Icon } from '../shared/icon';
import { ProviderMark } from '../shared/provider-mark';
import { RevealSections } from '../shared/reveal-sections';

@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, RouterLink, Icon, ProviderMark, RevealSections],
  templateUrl: './app-shell.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AppShell {
  private readonly api = inject(ReviewerApi);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  readonly auth = inject(AuthService);
  readonly theme = inject(ThemeService);
  readonly sidebarCollapsed = signal(false);
  readonly mobileNavigationOpen = signal(false);
  readonly mobileHealthOpen = signal(false);
  readonly profileOpen = signal(false);
  readonly health = signal<HealthResponse | null>(null);
  readonly currentPath = signal(this.router.url.split('?')[0]);
  readonly pageScrolled = signal(false);

  readonly navigation = [
    { label: 'Dashboard', route: '/', icon: 'layout-dashboard', section: 'dashboard' },
    { label: 'Review History', route: '/history', icon: 'history', section: 'history' },
    { label: 'Settings', route: '/settings', icon: 'settings', section: 'settings' },
  ];

  constructor() {
    this.router.events
      .pipe(
        filter((event): event is NavigationEnd => event instanceof NavigationEnd),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((event) => {
        this.currentPath.set(event.urlAfterRedirects.split('?')[0]);
        this.closeMobileNavigation();
        this.mobileHealthOpen.set(false);
        this.profileOpen.set(false);
        window.scrollTo({ top: 0, behavior: 'instant' });
        this.pageScrolled.set(false);
      });
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

  providerDetail(id: 'github' | 'azure-devops'): string | null {
    return this.health()?.providers.find((provider) => provider.id === id)?.detail ?? null;
  }

  providerState(id: 'github' | 'azure-devops'): ProviderStatus['state'] | 'checking' {
    return this.health()?.providers.find((provider) => provider.id === id)?.state ?? 'checking';
  }

  closeMobileNavigation(): void {
    this.mobileNavigationOpen.set(false);
  }

  healthState(id: 'github' | 'azure-devops' | 'ollama'): string {
    if (id === 'ollama') {
      if (!this.health() || this.health()?.ollama.ready === null) return 'Checking';
      return this.health()?.ollama.ready ? 'Ready' : 'Offline';
    }
    const connected = this.providerConnected(id);
    if (connected === null) return 'Checking';
    return {
      connected: 'Connected',
      configured: 'Configured',
      'not-configured': 'Not configured',
      'authentication-failed': 'Auth failed',
      unavailable: 'Unavailable',
      checking: 'Checking',
    }[this.providerState(id)] ?? 'Unavailable';
  }

  healthHasIssue(): boolean {
    const health = this.health();
    return (
      !!health &&
      (['authentication-failed', 'unavailable'].includes(this.providerState('github')) ||
        ['authentication-failed', 'unavailable'].includes(this.providerState('azure-devops')) ||
        health.ollama.ready === false)
    );
  }

  isNavigationActive(section: string): boolean {
    const path = this.currentPath();
    if (section === 'dashboard') {
      return path === '/';
    }
    if (section === 'history') return path === '/history' || path.startsWith('/history/') || path.startsWith('/pull-requests/') || path.startsWith('/reviews/');
    return path === '/settings' || path.startsWith('/settings/');
  }

  @HostListener('window:scroll')
  onWindowScroll(): void {
    this.pageScrolled.set(window.scrollY > 48);
  }

  @HostListener('document:keydown.escape')
  closeOverlays(): void {
    this.closeMobileNavigation();
    this.mobileHealthOpen.set(false);
    this.profileOpen.set(false);
  }

  toggleMobileHealth(): void {
    this.mobileHealthOpen.update((open) => !open);
  }

  toggleMobileNavigation(): void {
    this.mobileNavigationOpen.update((open) => !open);
  }

  toggleSidebar(): void {
    this.sidebarCollapsed.update((collapsed) => !collapsed);
  }
}
