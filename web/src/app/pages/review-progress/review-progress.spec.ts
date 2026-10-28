import { AuthService } from '../../core/auth.service';
import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { of } from 'rxjs';
import { appConfig } from '../../app.config';
import { ReviewerApi } from '../../core/api.service';
import { ReviewProgressPage } from './review-progress';
const job:any={id:'job',command:{pull_number:142},status:'running',phase:'ai_review',message:'Batch 3 of 5',progress:64,created_at:new Date().toISOString(),started_at:new Date().toISOString(),completed_at:null,error:null,metrics:{},steps:[{key:'ai_review',label:'AI review',state:'active',updated_at:null}],events:[{id:'batch',phase:'ai_review',level:'info',title:'Reviewing batch',detail:'Four files',timestamp:new Date().toISOString(),batch_index:3,batch_total:5,files:['src/app.ts'],token_count:null}]};
describe('Current activity progress',()=>{
  beforeEach(()=>TestBed.configureTestingModule({imports:[ReviewProgressPage],providers:[...appConfig.providers, { provide: AuthService, useValue: { canReview:()=>true, canPublish:()=>true, canCancel:()=>true } },{provide:ActivatedRoute,useValue:{snapshot:{paramMap:convertToParamMap({jobId:'job'})}}},{provide:ReviewerApi,useValue:{getReview:()=>of(job)}}]}));
  it('shows completed batch progress and keeps files visible',fakeAsync(()=>{
    const fixture=TestBed.createComponent(ReviewProgressPage);tick(0);fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.activity-progress-bar').getAttribute('aria-valuenow')).toBe('40');
    expect(fixture.nativeElement.querySelector('.activity-files').textContent).toContain('src/app.ts');
    fixture.destroy();
  }));
  it('uses indeterminate progress when no batch percentage is available',fakeAsync(()=>{
    const fixture=TestBed.createComponent(ReviewProgressPage);tick(0);
    fixture.componentInstance.job.set({...job,events:[]});fixture.detectChanges();
    const bar=fixture.nativeElement.querySelector('.activity-progress-bar');
    expect(bar.classList.contains('indeterminate')).toBeTrue(); expect(bar.hasAttribute('aria-valuenow')).toBeFalse();fixture.destroy();
  }));
});
