import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { ProviderId } from '../core/models';

@Component({
  selector: 'app-provider-mark',
  template: `
    @if (provider() === 'github') {
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path
          fill="currentColor"
          d="M12 .7a11.5 11.5 0 0 0-3.64 22.41c.58.1.79-.25.79-.56v-2.23c-3.22.7-3.9-1.37-3.9-1.37-.52-1.34-1.29-1.7-1.29-1.7-1.05-.72.08-.71.08-.71 1.17.08 1.78 1.2 1.78 1.2 1.04 1.78 2.72 1.27 3.38.97.1-.75.4-1.27.74-1.56-2.57-.29-5.28-1.29-5.28-5.68 0-1.26.45-2.29 1.19-3.09-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.16 1.18a10.98 10.98 0 0 1 5.76 0c2.2-1.49 3.16-1.18 3.16-1.18.63 1.59.23 2.76.11 3.05.74.8 1.19 1.83 1.19 3.09 0 4.4-2.72 5.38-5.3 5.67.42.36.79 1.07.79 2.16v3.2c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .7Z"
        />
      </svg>
    } @else if (provider() === 'ollama') {
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M7 8 6 3c-.2-1 1.1-1.6 1.8-.8L10 6h4l2.2-3.8c.7-.8 2-.2 1.8.8l-1 5c2 1.3 3 3.6 3 6v3l1 5M7 8c-2 1.3-3 3.6-3 6v3l-1 5M7 8c3-2 7-2 10 0" />
        <path d="M9 12h.01M15 12h.01M10 16c1.3 1 2.7 1 4 0M12 15v2" />
      </svg>
    } @else {
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path fill="#0089d6" d="m13.5 2-6 5.2L2 20.5h5.3L13.5 2Z" />
        <path fill="#0078d4" d="m15 5 7 16H9l8.1-1.5-4.7-5.5L15 5Z" />
      </svg>
    }
  `,
  host: { class: 'provider-mark' },
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProviderMark {
  readonly provider = input.required<ProviderId | 'ollama'>();
}
