import { Injectable, signal } from '@angular/core';

import { ReviewDepth } from './models';

const STORAGE_KEY = 'ipr-review-defaults';

interface StoredReviewPreferences {
  depth?: unknown;
  maxWorkers?: unknown;
}

@Injectable({ providedIn: 'root' })
export class ReviewPreferencesService {
  readonly defaultDepth = signal<ReviewDepth>('standard');
  readonly maxWorkers = signal(1);

  constructor() {
    this.restore();
  }

  save(): void {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          depth: this.defaultDepth(),
          maxWorkers: this.maxWorkers(),
        }),
      );
    } catch {
      // Browser persistence is optional; safe in-memory defaults remain active.
    }
  }

  private restore(): void {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const value = JSON.parse(raw) as StoredReviewPreferences;
      if (value.depth === 'fast' || value.depth === 'standard' || value.depth === 'deep') {
        this.defaultDepth.set(value.depth);
      }
      if (
        typeof value.maxWorkers === 'number' &&
        Number.isInteger(value.maxWorkers) &&
        value.maxWorkers >= 1 &&
        value.maxWorkers <= 8
      ) {
        this.maxWorkers.set(value.maxWorkers);
      }
    } catch {
      // Ignore malformed browser state and retain safe defaults.
    }
  }
}
