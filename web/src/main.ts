import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { App } from './app/app';

bootstrapApplication(App, appConfig)
  .catch((err) => {
    console.error(err);
    const root = document.querySelector('app-root');
    if (root) root.innerHTML = '<div class="boot-loader"><div class="boot-error" role="alert">Unable to open your workspace.<br><a href="/login">Try again</a></div></div>';
  });
