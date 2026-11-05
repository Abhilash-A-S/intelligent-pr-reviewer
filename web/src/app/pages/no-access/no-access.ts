import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { AuthService } from '../../core/auth.service';
@Component({selector:'app-no-access',template:`<section class="card access-message">
@if(auth.user()?.active_provider){
<h2>No accessible repositories</h2><p>Your {{auth.user()?.active_provider === 'github' ? 'GitHub' : 'Azure DevOps'}} account has not returned any repositories you can review.</p>
@if(auth.user()?.access_error){<p role="alert">{{auth.user()?.access_error}}</p>}
<p>Check your provider permissions and any required organization approval. Reauthorize if your connection has expired.</p>
<div class="access-actions"><button class="button secondary" type="button" (click)="retry()">Retry</button><a class="button primary" [href]="auth.user()?.active_provider === 'github' ? '/api/auth/login?provider=github' : '/api/auth/login?provider=microsoft'">Sign in again</a></div>
}@else{
<h2>No repositories assigned</h2><p>You are signed in, but your administrator has not assigned repository access.</p><p>Account ID: <code>{{auth.user()?.id}}</code></p><button class="button secondary" type="button" (click)="copy()">Copy Account ID</button><p role="status">{{status()}}</p>
}</section>`,styles:`.access-message{width:min(720px,calc(100% - 32px));margin:clamp(24px,8vh,80px) auto;padding:clamp(20px,4vw,36px)}h2{margin-top:0}p{line-height:1.6}code{overflow-wrap:anywhere;user-select:all}.access-actions{display:flex;flex-wrap:wrap;gap:12px}`,changeDetection:ChangeDetectionStrategy.OnPush})
export class NoAccessPage {
 readonly auth=inject(AuthService);readonly status=signal('');
 retry(){window.location.reload();}
 async copy(){try{await navigator.clipboard.writeText(this.auth.user()?.id ?? '');this.status.set('Account ID copied.')}catch{this.status.set('Could not copy. Please select and copy the Account ID above.')}}
}
