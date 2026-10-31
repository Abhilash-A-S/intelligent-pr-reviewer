import { HttpContextToken, HttpInterceptorFn } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { defer, finalize, timeout } from 'rxjs';

// Background polling must never repeatedly block a usable page.
export const BACKGROUND_REQUEST = new HttpContextToken<boolean>(() => false);

@Injectable({ providedIn: 'root' })
export class LoadingService {
  private readonly requests = signal(0);
  readonly navigating = signal(true);
  readonly redirecting = signal(false);
  readonly busy = computed(() => this.navigating() || this.redirecting() || this.requests() > 0);

  begin(): () => void {
    this.requests.update(count => count + 1);
    let finished = false;
    return () => {
      if (finished) return;
      finished = true;
      this.requests.update(count => Math.max(0, count - 1));
    };
  }
}

export const loadingInterceptor: HttpInterceptorFn = (request, next) => {
  const loading = inject(LoadingService);
  if (!request.url.startsWith('/api/') || request.context.get(BACKGROUND_REQUEST)) {
    return next(request);
  }
  return defer(() => {
    const finish = loading.begin();
    return next(request).pipe(timeout(90000), finalize(finish));
  });
};
