import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { appConfig } from '../../app.config';
import { ReviewerApi } from '../../core/api.service';
import { ReviewPreferencesService } from '../../core/review-preferences.service';
import { SettingsPage } from './settings';

describe('Settings draft preferences', () => {
  let preferences: ReviewPreferencesService;
  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [SettingsPage], providers: [
      ...appConfig.providers,
      { provide: ReviewerApi, useValue: { health: () => of({ providers: [], ollama: { ready: false } }) } },
    ] });
    preferences = TestBed.inject(ReviewPreferencesService);
    preferences.defaultDepth.set('standard');
    preferences.maxWorkers.set(2);
  });
  it('keeps editing local to the draft and discards back to saved preferences', () => {
    const page = TestBed.createComponent(SettingsPage).componentInstance;
    page.setDefaultDepth('deep');
    page.draftWorkers.set(6);
    expect(preferences.defaultDepth()).toBe('standard');
    expect(preferences.maxWorkers()).toBe(2);
    page.discard();
    expect(page.draftDepth()).toBe('standard');
    expect(page.draftWorkers()).toBe(2);
  });
  it('rejects invalid concurrency without changing the saved depth or workers', () => {
    const page = TestBed.createComponent(SettingsPage).componentInstance;
    spyOn(preferences, 'save');
    for (const workers of [0, 9, 1.5, NaN]) {
      page.setDefaultDepth('fast');
      page.draftWorkers.set(workers);
      page.save();
      expect(page.error()).toContain('between 1 and 8');
      expect(preferences.defaultDepth()).toBe('standard');
      expect(preferences.maxWorkers()).toBe(2);
    }
    expect(preferences.save).not.toHaveBeenCalled();
  });
  it('commits valid drafts and saves them explicitly', () => {
    const page = TestBed.createComponent(SettingsPage).componentInstance;
    spyOn(preferences, 'save');
    page.setDefaultDepth('deep');
    page.draftWorkers.set(4);
    page.save();
    expect(preferences.defaultDepth()).toBe('deep');
    expect(preferences.maxWorkers()).toBe(4);
    expect(preferences.save).toHaveBeenCalledTimes(1);
    expect(page.saved()).toBeTrue();
  });
});
