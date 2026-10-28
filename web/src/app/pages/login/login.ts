import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { ActivatedRoute, Router } from '@angular/router';
import { ThemeService } from '../../core/theme.service';
import { AuthService } from '../../core/auth.service';
import { Icon } from '../../shared/icon';

@Component({selector:'app-login',imports:[Icon],templateUrl:'./login.html',styleUrl:'./login.scss',changeDetection:ChangeDetectionStrategy.OnPush})
export class LoginPage {
  readonly theme = inject(ThemeService);
  private readonly http = inject(HttpClient);
  readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  readonly loading = signal(true);
  readonly ready = signal(false);
  readonly provider = signal('Microsoft');
  readonly error = signal('');
  readonly starting = signal(false);
  constructor() {
    const query = this.route.snapshot.queryParamMap;
    if (query.has('error')) this.error.set('Sign-in could not be completed. Please try again or contact your administrator.');
    else if (query.get('reason') === 'session_expired') this.error.set('Your session has expired. Sign in again to continue.');
    this.http.get<{configured:boolean;provider_label:string}>('/api/auth/config').subscribe({next:config=>{
      this.ready.set(config.configured);this.provider.set(config.provider_label);this.loading.set(false);
      if (!config.configured) this.error.set('Company sign-in is not configured yet. Please contact your administrator.');
      else void this.auth.restore().then(ok=>{if(ok)void this.router.navigateByUrl('/');});
    },error:()=>{this.loading.set(false);this.error.set('Unable to reach the sign-in service. Please reload to try again.');}});
  }
  signIn(): void { if(this.ready()&&!this.starting()){this.starting.set(true);window.location.assign('/api/auth/login');} }
}
