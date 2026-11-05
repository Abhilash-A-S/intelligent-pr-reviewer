import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { AuthService } from '../../core/auth.service';
import { ReviewerApi } from '../../core/api.service';
import { HealthResponse, ReviewDepth } from '../../core/models';
import { ReviewPreferencesService } from '../../core/review-preferences.service';
import { Icon } from '../../shared/icon';
import { ProviderMark } from '../../shared/provider-mark';

type SettingsTab = 'integrations' | 'review' | 'performance' | 'publishing';

@Component({
  selector: 'app-settings-page',
  imports: [FormsModule, Icon, ProviderMark],
  templateUrl: './settings.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SettingsPage {
  readonly auth = inject(AuthService);
  private readonly api = inject(ReviewerApi);
  readonly preferences = inject(ReviewPreferencesService);
  readonly activeTab = signal<SettingsTab>('integrations');
  readonly draftDepth = signal<ReviewDepth>(this.preferences.defaultDepth());
  readonly draftWorkers = signal(this.preferences.maxWorkers());
  readonly health = signal<HealthResponse | null>(null);
  readonly error = signal<string | null>(null);
  readonly checking = signal(false);
  readonly saved = signal(false);
  readonly depthOptions: ReadonlyArray<{ value: ReviewDepth; label: string; desc: string }> = [
    { value: 'fast', label: 'Quick', desc: 'Minimum LLM calls' },
    { value: 'standard', label: 'Standard', desc: 'Balanced and recommended' },
    { value: 'deep', label: 'Thorough', desc: 'Every eligible file' },
  ];

  constructor() {
    this.loadHealth();
  }

  loadHealth(): void {
    this.checking.set(true);
    this.error.set(null);
    this.api.health(true).subscribe({
      next: (response) => {
        this.health.set(response);
        this.checking.set(false);
      },
      error: (error) => {
        this.health.set(null);
        this.checking.set(false);
        this.error.set(error?.error?.detail ?? 'Runtime health could not be loaded.');
      },
    });
  }

  connected(provider: 'github' | 'azure-devops'): boolean {
    return this.health()?.providers.find((item) => item.id === provider)?.connected ?? false;
  }

  providerStatusLabel(provider: 'github' | 'azure-devops'): string {
    const status = this.health()?.providers.find((item) => item.id === provider);
    if (!status) return this.checking() ? 'Checking' : 'Unavailable';
    return {
      connected: 'Connected',
      configured: 'Configured',
      'not-configured': 'Not configured',
      'authentication-failed': 'Authentication failed',
      unavailable: 'Unavailable',
    }[status.state];
  }

  save(): void {
    const workers = Number(this.draftWorkers());
    if (!Number.isInteger(workers) || workers < 1 || workers > 8) {
      this.error.set('Parallel workers must be a whole number between 1 and 8.');
      return;
    }
    this.error.set(null);
    this.preferences.defaultDepth.set(this.draftDepth());
    this.preferences.maxWorkers.set(workers);
    this.preferences.save();
    this.saved.set(true);
    setTimeout(() => this.saved.set(false), 2200);
  }

  discard(): void {
    this.draftDepth.set(this.preferences.defaultDepth());
    this.draftWorkers.set(this.preferences.maxWorkers());
    this.saved.set(false);
    this.error.set(null);
  }

  selectTab(tab: SettingsTab): void {
    this.activeTab.set(tab);
    document.getElementById('settings-' + tab)?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' });
  }

  setDefaultDepth(value: ReviewDepth): void {
    this.draftDepth.set(value);
  }
}
