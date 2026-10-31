import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { appConfig } from '../../app.config';
import { LoginPage } from './login';

describe('Provider sign-in choices',()=>{
  let http:HttpTestingController;
  beforeEach(()=>{TestBed.configureTestingModule({imports:[LoginPage],providers:[...appConfig.providers,provideRouter([]),provideHttpClient(),provideHttpClientTesting()]});http=TestBed.inject(HttpTestingController)});
  afterEach(()=>http.verify());
  for(const [microsoft,github] of [[true,true],[true,false],[false,true],[false,false]]){
    it(`shows only enabled providers with readiness ${microsoft}/${github}`,()=>{
      const fixture=TestBed.createComponent(LoginPage);fixture.detectChanges();
      http.expectOne('/api/auth/config').flush({configured:microsoft||github,provider_label:'Microsoft',microsoft_configured:microsoft,github_configured:github,enabled_providers:[...(microsoft?['azure-devops']:[]),...(github?['github']:[])]});
      if(microsoft||github)http.expectOne('/api/auth/me').flush({},{status:401,statusText:'Unauthorized'});
      fixture.detectChanges();
      const ms=fixture.nativeElement.querySelector('.microsoft-login') as HTMLButtonElement,gh=fixture.nativeElement.querySelector('.github-login') as HTMLButtonElement;
      expect(!!ms).toBe(microsoft);expect(!!gh).toBe(github);
      if(ms){expect(ms.textContent).toContain('Sign in with Microsoft');expect(ms.disabled).toBeFalse();}
      if(gh){expect(gh.textContent).toContain('Sign in with GitHub');expect(gh.disabled).toBeFalse();}
      expect(fixture.nativeElement.querySelector('select')).toBeNull();
    });
  }
  it('does not start an unconfigured provider login',()=>{
    const fixture=TestBed.createComponent(LoginPage);
    http.expectOne('/api/auth/config').flush({configured:false,provider_label:'Microsoft',microsoft_configured:false,github_configured:false});
    fixture.componentInstance.signIn('github');expect(fixture.componentInstance.starting()).toBeNull();
  });
});

describe('Enabled provider configuration', () => {
  it('shows an enabled but unconfigured provider as unavailable', () => {
    TestBed.configureTestingModule({imports:[LoginPage],providers:[...appConfig.providers,provideRouter([]),provideHttpClient(),provideHttpClientTesting()]});
    const http=TestBed.inject(HttpTestingController), fixture=TestBed.createComponent(LoginPage);
    http.expectOne('/api/auth/config').flush({configured:false,enabled_providers:['github'],github_configured:false,microsoft_configured:true});
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.microsoft-login')).toBeNull();
    expect(fixture.nativeElement.querySelector('.github-login').disabled).toBeTrue();
    expect(fixture.nativeElement.textContent).toContain('contact your administrator');
    http.verify();
  });
});
