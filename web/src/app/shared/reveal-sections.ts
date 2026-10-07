import { AfterViewInit, Directive, ElementRef, OnDestroy, inject } from '@angular/core';

/** Reveal each section once; review polling never replays existing animations. */
@Directive({ selector: '[appRevealSections]' })
export class RevealSections implements AfterViewInit, OnDestroy {
  private readonly element = inject(ElementRef<HTMLElement>);
  private intersection?: IntersectionObserver;
  private mutations?: MutationObserver;
  private readonly tracked = new Set<Element>();

  ngAfterViewInit(): void {
    if (typeof IntersectionObserver === 'undefined' || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    this.intersection = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add('section-revealed');
          this.intersection?.unobserve(entry.target);
        }
      }
    }, { threshold: 0.05 });
    const observe = () => {
      // Angular replaces routed content and asynchronously inserts loaded cards.
      for (const el of this.element.nativeElement.querySelectorAll('.page > .card, .page > .metric-grid, .settings-panel, .progress-detail-grid > .card')) {
        if (!this.tracked.has(el)) {
          this.tracked.add(el);
          el.classList.add('section-reveal');
          this.intersection?.observe(el);
        }
      }
      for (const el of this.tracked) {
        if (!el.isConnected) {
          this.intersection?.unobserve(el);
          this.tracked.delete(el);
        }
      }
    };
    this.mutations = new MutationObserver(observe);
    this.mutations.observe(this.element.nativeElement, { childList: true, subtree: true });
    observe();
  }

  ngOnDestroy(): void {
    this.intersection?.disconnect();
    this.mutations?.disconnect();
    this.tracked.clear();
  }
}
