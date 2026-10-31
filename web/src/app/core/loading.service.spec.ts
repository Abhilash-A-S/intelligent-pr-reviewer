import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import { HttpClient, HttpContext, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { BACKGROUND_REQUEST, LoadingService, loadingInterceptor } from './loading.service';

describe('Foreground loading', () => {
  let loading: LoadingService, http: HttpTestingController, client: HttpClient;
  beforeEach(() => {
    TestBed.configureTestingModule({providers:[provideHttpClient(withInterceptors([loadingInterceptor])),provideHttpClientTesting()]});
    loading=TestBed.inject(LoadingService); loading.navigating.set(false);
    client=TestBed.inject(HttpClient); http=TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());
  it('keeps the overlay until all concurrent calls finish', () => {
    client.get('/api/first').subscribe(); client.get('/api/second').subscribe();
    expect(loading.busy()).toBeTrue(); http.expectOne('/api/first').flush({});
    expect(loading.busy()).toBeTrue(); http.expectOne('/api/second').flush({});
    expect(loading.busy()).toBeFalse();
  });
  it('releases the overlay on errors and cancellation', () => {
    client.get('/api/failure').subscribe({error:()=>{}});
    http.expectOne('/api/failure').flush({}, {status:503,statusText:'Unavailable'});
    expect(loading.busy()).toBeFalse();
    const subscription=client.get('/api/cancelled').subscribe();
    const request=http.expectOne('/api/cancelled'); subscription.unsubscribe();
    expect(request.cancelled).toBeTrue(); expect(loading.busy()).toBeFalse();
  });
  it('does not block background polling or external requests', () => {
    client.get('/api/poll', {context:new HttpContext().set(BACKGROUND_REQUEST,true)}).subscribe();
    client.get('https://example.test/asset').subscribe(); expect(loading.busy()).toBeFalse();
    http.expectOne('/api/poll').flush({}); http.expectOne('https://example.test/asset').flush({});
  });
  it('releases a stalled request after its deadline', fakeAsync(() => {
    let failed=false; client.get('/api/stalled').subscribe({error:()=>failed=true});
    const request=http.expectOne('/api/stalled'); tick(90001);
    expect(failed).toBeTrue();expect(request.cancelled).toBeTrue();expect(loading.busy()).toBeFalse();
  }));
  it('keeps sign-in and navigation blocking after a request completes', () => {
    loading.redirecting.set(true);client.get('/api/config').subscribe();http.expectOne('/api/config').flush({});
    expect(loading.busy()).toBeTrue();loading.redirecting.set(false);expect(loading.busy()).toBeFalse();
  });
});
