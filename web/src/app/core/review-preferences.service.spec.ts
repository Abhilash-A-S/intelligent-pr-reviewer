import { TestBed } from '@angular/core/testing';

import { ReviewPreferencesService } from './review-preferences.service';

describe('ReviewPreferencesService', () => {
  beforeEach(() => {
    localStorage.clear();
    TestBed.resetTestingModule();
  });

  it('uses safe defaults', () => {
    const service = TestBed.inject(ReviewPreferencesService);

    expect(service.defaultDepth()).toBe('standard');
    expect(service.maxWorkers()).toBe(1);
  });

  it('persists review options used by new review requests', () => {
    const first = TestBed.inject(ReviewPreferencesService);
    first.defaultDepth.set('deep');
    first.maxWorkers.set(3);
    first.save();

    TestBed.resetTestingModule();
    const restored = TestBed.inject(ReviewPreferencesService);

    expect(restored.defaultDepth()).toBe('deep');
    expect(restored.maxWorkers()).toBe(3);
  });

  it('rejects unsafe or malformed stored values', () => {
    localStorage.setItem('ipr-review-defaults', '{"depth":"everything","maxWorkers":99}');
    const service = TestBed.inject(ReviewPreferencesService);

    expect(service.defaultDepth()).toBe('standard');
    expect(service.maxWorkers()).toBe(1);
  });
});
