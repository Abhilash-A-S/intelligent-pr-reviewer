import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { appConfig } from '../app.config';
import { ReviewerApi } from '../core/api.service';
import { AppShell } from './app-shell';

describe('AppShell PR navigation and health', () => {
  beforeEach(() => TestBed.configureTestingModule({ imports: [AppShell], providers: [
    ...appConfig.providers, provideRouter([]),
    { provide: ReviewerApi, useValue: { health: () => of({
      providers: [ { id: 'github', connected: true, state: 'connected' }, { id: 'azure-devops', connected: false, state: 'authentication-failed' } ],
      ollama: { ready: null },
    }) } },
  ] }));
  it('selects Review History, not Dashboard, for PR details', () => {
    const fixture = TestBed.createComponent(AppShell);
    fixture.componentInstance.currentPath.set('/pull-requests/1'); fixture.detectChanges();
    expect(fixture.componentInstance.isNavigationActive('history')).toBeTrue();
    expect(fixture.componentInstance.isNavigationActive('dashboard')).toBeFalse();
    expect(fixture.nativeElement.querySelector('.nav-item.active').textContent).toContain('Review History');
  });
  it('marks only verified connections for green pulsing', () => {
    const fixture = TestBed.createComponent(AppShell); fixture.detectChanges();
    const chips = fixture.nativeElement.querySelectorAll('.health-chip');
    expect(chips[0].classList.contains('is-connected')).toBeTrue();
    expect(chips[1].classList.contains('is-connected')).toBeFalse();
    expect(chips[1].classList.contains('is-offline')).toBeTrue();
    expect(chips[2].classList.contains('is-checking')).toBeTrue();
    expect(chips[2].classList.contains('is-connected')).toBeFalse();
  });
});
