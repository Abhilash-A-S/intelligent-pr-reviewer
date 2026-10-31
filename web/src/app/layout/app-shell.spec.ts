import { AuthService } from '../core/auth.service';
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
  it('shows only the access screen and header controls without assigned repositories', () => {
    const auth = TestBed.inject(AuthService);
    auth.user.set({ id: 'https://issuer.example/v2.0|account', name: 'Test User', csrf_token: 'test', repositories: [] });
    const fixture = TestBed.createComponent(AppShell);
    fixture.componentInstance.currentPath.set('/history');
    fixture.detectChanges();
    const element: HTMLElement = fixture.nativeElement;
    expect(element.querySelector('router-outlet')).not.toBeNull();
    expect(element.querySelector('.sidebar')).toBeNull();
    expect(element.querySelector('.mobile-menu-button')).toBeNull();
    expect(element.querySelector('.health-chip')).toBeNull();
    expect(element.querySelector('.theme-toggle')).not.toBeNull();
    fixture.componentInstance.profileOpen.set(true); fixture.detectChanges();
    expect(element.querySelector('.popover-nav')?.textContent).toContain('Sign out');
    expect(element.querySelector('.popover-nav a')).toBeNull();
    auth.user.update(user => ({ ...user!, repositories: [{ provider: 'github', repository: 'owner/repo', role: 'viewer', can_review: false, can_publish: false, can_admin: false }] }));
    fixture.detectChanges();
    expect(element.querySelector('.repository-access-message')).toBeNull();
    expect(element.querySelector('.sidebar')).not.toBeNull();
    expect(element.querySelector('router-outlet')).not.toBeNull();
  });

  it('does not expose the retired connection page in provider navigation', () => {
    TestBed.inject(AuthService).user.set({id:'issuer|alice',name:'Alice',csrf_token:'test',access_mode:'provider',repositories:[{provider:'github',repository:'acme/store',role:'reviewer',can_review:true,can_publish:false,can_admin:false}]});
    const fixture=TestBed.createComponent(AppShell);fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('a[href="/connections"]')).toBeNull();
  });

});
