import { ChangeDetectionStrategy, Component, DestroyRef, HostListener, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { LoadingService } from '../../core/loading.service';
import { HttpClient } from '@angular/common/http';
import { ActivatedRoute, Router } from '@angular/router';
import { ThemeService } from '../../core/theme.service';
import { AuthService } from '../../core/auth.service';
import { Icon } from '../../shared/icon';
import { ProviderMark } from '../../shared/provider-mark';

@Component({selector:'app-login',imports:[Icon,ProviderMark],templateUrl:'./login.html',styleUrl:'./login.scss',changeDetection:ChangeDetectionStrategy.OnPush})
export class LoginPage {
  readonly theme = inject(ThemeService);
  private readonly http = inject(HttpClient);
  readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  private readonly busy = inject(LoadingService);
  private redirectTimer?: ReturnType<typeof setTimeout>;
  readonly microsoftEnabled = signal(false);
  readonly githubEnabled = signal(false);
  readonly loading = signal(true);
  readonly microsoftReady = signal(false);
  readonly githubReady = signal(false);
  readonly error = signal('');
  readonly starting = signal<'microsoft'|'github'|null>(null);
  constructor() {
    this.destroyRef.onDestroy(() => this.clearRedirect());
    const query=this.route.snapshot.queryParamMap;
    if(query.has('error'))this.error.set('Sign-in could not be completed. Microsoft sign-in requires a company work or school account with Azure DevOps authorization. For GitHub, check your organization approval or SSO.');
    else if(query.get('reason')==='session_expired')this.error.set('Your session has expired. Sign in again to continue.');
    this.http.get<{configured:boolean;provider_label:string;microsoft_configured?:boolean;github_configured?:boolean;enabled_providers?:string[]}>('/api/auth/config').pipe(takeUntilDestroyed(this.destroyRef)).subscribe({next:config=>{
      this.microsoftEnabled.set(config.enabled_providers?.includes('azure-devops') ?? (config.microsoft_configured ?? config.configured));
      this.githubEnabled.set(config.enabled_providers?.includes('github') ?? config.github_configured ?? false);
      this.microsoftReady.set(config.microsoft_configured ?? config.configured);
      this.githubReady.set(config.github_configured ?? false);
      this.loading.set(false);
      if(!config.configured || (!this.microsoftEnabled() && !this.githubEnabled()))this.error.set('Application sign-in is not configured yet. Please contact your administrator.');
      // An explicit failure must remain visible instead of restoring the old session and looping.
      else if(!query.has('error'))void this.auth.restore().then(ok=>{if(ok)void this.router.navigateByUrl('/');});
    },error:()=>{this.loading.set(false);this.error.set('Unable to reach the sign-in service. Please reload to try again.');}});
  }
  @HostListener('window:pageshow')
  clearRedirect(): void {
    clearTimeout(this.redirectTimer);
    this.starting.set(null);
    this.busy.redirecting.set(false);
  }
  signIn(provider:'microsoft'|'github'):void {
    if(this.loading()||this.starting()||!(provider==='microsoft'?this.microsoftReady():this.githubReady()))return;
    this.starting.set(provider);
    this.busy.redirecting.set(true);
    this.redirectTimer = setTimeout(() => {
      this.clearRedirect();
      this.error.set('Sign-in is taking longer than expected. Please try again.');
    }, 30000);
    try { window.location.assign('/api/auth/login?provider='+provider); }
    catch { this.clearRedirect(); this.error.set('Unable to open the sign-in provider. Please try again.'); }
  }
}
