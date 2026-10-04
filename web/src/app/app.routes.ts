import { Routes } from '@angular/router';

import { AppShell } from './layout/app-shell';

export const routes: Routes = [
  {
    path: '',
    component: AppShell,
    children: [
      {
        path: '',
        title: 'Dashboard · Intelligent PR Reviewer',
        loadComponent: () =>
          import('./pages/dashboard/dashboard').then((module) => module.DashboardPage),
      },
      {
        path: 'pull-requests/:pullNumber',
        title: 'Pull Request · Intelligent PR Reviewer',
        loadComponent: () =>
          import('./pages/pull-request/pull-request').then((module) => module.PullRequestPage),
      },
      {
        path: 'reviews/:jobId/progress',
        title: 'Review Progress · Intelligent PR Reviewer',
        loadComponent: () =>
          import('./pages/review-progress/review-progress').then(
            (module) => module.ReviewProgressPage,
          ),
      },
      {
        path: 'reviews/:jobId/results',
        title: 'Review Results · Intelligent PR Reviewer',
        loadComponent: () =>
          import('./pages/review-results/review-results').then(
            (module) => module.ReviewResultsPage,
          ),
      },
      {
        path: 'history',
        title: 'Review History · Intelligent PR Reviewer',
        loadComponent: () =>
          import('./pages/history/history').then((module) => module.HistoryPage),
      },
      {
        path: 'settings',
        title: 'Settings · Intelligent PR Reviewer',
        loadComponent: () =>
          import('./pages/settings/settings').then((module) => module.SettingsPage),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
