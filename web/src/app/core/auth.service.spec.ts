import { TestBed } from '@angular/core/testing';
import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Router, provideRouter } from '@angular/router';
import { AuthService, authGuard, authInterceptor, SignedInUser } from './auth.service';
import { ReviewerApi } from './api.service';

const user: SignedInUser = {id:'issuer|alice',name:'Alice',csrf_token:'csrf',repositories:[{provider:'github',repository:'acme/store',role:'reviewer',can_review:true,can_publish:false,can_admin:false}]};
describe('Authentication and permissions',()=>{
  let auth:AuthService,http:HttpTestingController;
  beforeEach(()=>{
    TestBed.configureTestingModule({providers:[provideRouter([]),provideHttpClient(withInterceptors([authInterceptor])),provideHttpClientTesting()]});
    auth=TestBed.inject(AuthService);http=TestBed.inject(HttpTestingController);
  });
  afterEach(()=>http.verify());
  it('denies UI actions until signed in',()=>{expect(auth.canReview('github','acme/store')).toBeFalse();expect(auth.canPublish('github','acme/store')).toBeFalse();});
  it('restores the opaque cookie session without local token storage',async()=>{
    const promise=auth.restore();http.expectOne('/api/auth/me').flush(user);expect(await promise).toBeTrue();expect(auth.user()?.name).toBe('Alice');
  });
  it('shares concurrent session discovery without caching later permission checks',async()=>{
    const first=auth.restore(), second=auth.restore();
    http.expectOne('/api/auth/me').flush(user);expect(await first).toBeTrue();expect(await second).toBeTrue();
    const later=auth.restore();http.expectOne('/api/auth/me').flush({...user,repositories:[]});
    await later;expect(auth.canReview('github','acme/store')).toBeFalse();
  });
  it('keeps publisher permission separate and repository scoped',()=>{
    auth.user.set(user);expect(auth.canReview('github','ACME/Store')).toBeTrue();expect(auth.canPublish('github','acme/store')).toBeFalse();expect(auth.canReview('github','other/private')).toBeFalse();
  });
  it('allows cancel only for own jobs or repository admins',()=>{
    auth.user.set(user);expect(auth.canCancel({command:{provider:'github',repository:'acme/store',owner_id:'other'}})).toBeFalse();expect(auth.canCancel({command:{provider:'github',repository:'acme/store',owner_id:user.id}})).toBeTrue();
    auth.user.set({...user,repositories:[{...user.repositories[0],can_admin:true}]});expect(auth.canCancel({command:{provider:'github',repository:'acme/store',owner_id:'other'}})).toBeTrue();
  });
  it('adds the session CSRF value to state-changing API requests',()=>{
    auth.user.set(user);TestBed.inject(ReviewerApi).startReview({provider:'github',repository:'acme/store',pull_number:1,publish:false,review_depth:'standard'}).subscribe();
    const request=http.expectOne('/api/reviews');expect(request.request.headers.get('X-CSRF-Token')).toBe('csrf');request.flush({id:'job'});
  });
  it('does not send the CSRF value to external addresses',()=>{
    auth.user.set(user);const client=TestBed.inject(HttpClient);client.get('https://other.example/test').subscribe();const request=http.expectOne('https://other.example/test');expect(request.request.headers.has('X-CSRF-Token')).toBeFalse();request.flush({});
  });
  it('redirects to login on an expired session',()=>{
    auth.user.set(user);const nav=spyOn(TestBed.inject(Router),'navigate').and.resolveTo(true);TestBed.inject(ReviewerApi).listReviews().subscribe({error:()=>{}});http.expectOne(r=>r.url==='/api/reviews').flush({}, {status:401,statusText:'Unauthorized'});expect(auth.user()).toBeNull();expect(nav).toHaveBeenCalled();
  });
  it('keeps the session and explains a forbidden action',()=>{
    auth.user.set(user);TestBed.inject(ReviewerApi).cancelReview('job').subscribe({error:()=>{}});http.expectOne('/api/reviews/job').flush({}, {status:403,statusText:'Forbidden'});expect(auth.user()).not.toBeNull();expect(auth.message()).toContain('Access denied');
  });
  it('logs out at the backend before clearing local state',async()=>{
    auth.user.set(user);spyOn(TestBed.inject(Router),'navigateByUrl').and.resolveTo(true);const done=auth.logout();const r=http.expectOne('/api/auth/logout');expect(r.request.headers.get('X-CSRF-Token')).toBe('csrf');r.flush({signed_out:true});await done;expect(auth.user()).toBeNull();
  });
  it('route guard rejects unsigned visitors',async()=>{
    const done=TestBed.runInInjectionContext(()=>authGuard({} as any,{} as any)) as Promise<unknown>;
    http.expectOne('/api/auth/me').flush({}, {status:401,statusText:'Unauthorized'});expect(await done).toBeTruthy();expect(auth.user()).toBeNull();
  });
});

describe('Provider onboarding route protection',()=>{
  it('redirects an unconnected user before a protected page can instantiate',async()=>{
    TestBed.configureTestingModule({providers:[provideRouter([]),provideHttpClient(),provideHttpClientTesting()]});
    const auth=TestBed.inject(AuthService),http=TestBed.inject(HttpTestingController);
    const done=TestBed.runInInjectionContext(()=>authGuard({} as any,{url:'/history'} as any)) as Promise<any>;
    http.expectOne('/api/auth/me').flush({...user,access_mode:'provider',repositories:[]});
    expect((await done).toString()).toBe('/access');http.verify();
  });
  it('lets the access result render for users with no repositories',async()=>{
    TestBed.configureTestingModule({providers:[provideRouter([]),provideHttpClient(),provideHttpClientTesting()]});
    const http=TestBed.inject(HttpTestingController);
    const done=TestBed.runInInjectionContext(()=>authGuard({} as any,{url:'/access'} as any)) as Promise<any>;
    http.expectOne('/api/auth/me').flush({...user,access_mode:'provider',repositories:[]});
    expect(await done).toBeTrue();http.verify();
  });
});

describe('Selected provider session',()=>{
  it('hides the other provider even if a stale profile contains it',()=>{
    TestBed.configureTestingModule({providers:[provideRouter([]),provideHttpClient()]});
    const auth=TestBed.inject(AuthService);auth.user.set({...user,active_provider:'github',enabled_providers:['github','azure-devops']});
    expect(auth.providerEnabled('github')).toBeTrue();expect(auth.providerEnabled('azure-devops')).toBeFalse();
  });
  it('shows access results rather than a PAT form for an empty GitHub authorization',async()=>{
    TestBed.configureTestingModule({providers:[provideRouter([]),provideHttpClient(),provideHttpClientTesting()]});
    const http=TestBed.inject(HttpTestingController);
    const done=TestBed.runInInjectionContext(()=>authGuard({} as any,{url:'/'} as any)) as Promise<any>;
    http.expectOne('/api/auth/me').flush({...user,access_mode:'provider',active_provider:'github',repositories:[]});
    expect((await done).toString()).toBe('/access');http.verify();
  });
});
