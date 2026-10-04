import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

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
  private readonly api = inject(ReviewerApi);
  readonly preferences = inject(ReviewPreferencesService);
  readonly activeTab = signal<SettingsTab>('integrations');
  readonly health = signal<HealthResponse | null>(null);
  readonly checking = signal(false);
  readonly saved = signal(false);
  readonly depthOptions: ReadonlyArray<{ value: ReviewDepth; label: string; desc: string }> = [
    { value: 'fast', label: 'Fast', desc: 'Minimum LLM calls' },
    { value: 'standard', label: 'Standard', desc: 'Balanced and recommended' },
    { value: 'deep', label: 'Deep', desc: 'Every eligible file' },
  ];

  constructor() {
    this.loadHealth();
  }

  loadHealth(): void {
    this.checking.set(true);
    this.api.health(true).subscribe({
      next: (response) => {
        this.health.set(response);
        this.checking.set(false);
      },
      error: () => {
        this.health.set(null);
        this.checking.set(false);
      },
    });
  }

  connected(provider: 'github' | 'azure-devops'): boolean {
    return this.health()?.providers.find((item) => item.id === provider)?.connected ?? false;
  }

  save(): void {
    this.preferences.save();
    this.saved.set(true);
    setTimeout(() => this.saved.set(false), 2200);
  }

  setDefaultDepth(value: ReviewDepth): void {
    this.preferences.defaultDepth.set(value);
  }
}
