import { HttpClient, HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, firstValueFrom, throwError } from 'rxjs';

export interface RepositoryAccess { provider: string; repository: string; role: string; can_review: boolean; can_publish: boolean; can_admin: boolean; }
export interface SignedInUser { id: string; name: string; csrf_token: string; repositories: RepositoryAccess[]; }
@Injectable({providedIn:'root'})
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  readonly user = signal<SignedInUser | null>(null);
  readonly message = signal('');
  async restore(): Promise<boolean> {
    try { this.user.set(await firstValueFrom(this.http.get<SignedInUser>('/api/auth/me'))); return true; }
    catch { this.user.set(null); return false; }
  }
  access(provider: string, repository: string): RepositoryAccess | undefined {
    return this.user()?.repositories.find(r => r.provider === provider && r.repository.toLowerCase() === repository.toLowerCase());
  }
  canReview(provider: string, repository: string): boolean { return this.access(provider,repository)?.can_review ?? false; }
  canPublish(provider: string, repository: string): boolean { return this.access(provider,repository)?.can_publish ?? false; }
  canCancel(job: {command: {provider: string; repository: string; owner_id?: string | null}}): boolean {
    const access = this.access(job.command.provider,job.command.repository);
    return !!access && (access.can_admin || (access.can_review && job.command.owner_id === this.user()?.id));
  }
  expire(): void { this.user.set(null); void this.router.navigate(['/login'],{queryParams:{reason:'session_expired'}}); }
  async logout(): Promise<void> {
    try { await firstValueFrom(this.http.post('/api/auth/logout',{}, {headers:{'X-CSRF-Token':this.user()?.csrf_token ?? ''}})); }
    catch(error) { if (!(error instanceof HttpErrorResponse) || error.status !== 401) { this.message.set('Could not sign out. Please retry.'); return; } }
    this.user.set(null); this.message.set(''); void this.router.navigateByUrl('/login');
  }
}
export const authGuard: CanActivateFn = async () => {
  const auth = inject(AuthService), router = inject(Router);
  return await auth.restore() ? true : router.createUrlTree(['/login']);
};
export const authInterceptor: HttpInterceptorFn = (request,next) => {
  const auth = inject(AuthService);
  if (!request.url.startsWith('/api/')) return next(request);
  const unsafe = !['GET','HEAD','OPTIONS'].includes(request.method);
  const headers: Record<string,string> = unsafe && auth.user() ? {'X-CSRF-Token': auth.user()!.csrf_token} : {};
  return next(request.clone({setHeaders:headers})).pipe(catchError((error:HttpErrorResponse) => {
    if (error.status === 401 && !request.url.startsWith('/api/auth/')) auth.expire();
    if (error.status === 403) auth.message.set('Access denied. Your account is not permitted to perform this action.');
    return throwError(()=>error);
  }));
};
