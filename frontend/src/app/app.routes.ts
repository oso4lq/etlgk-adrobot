import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'create', pathMatch: 'full' },
  {
    path: 'create',
    loadComponent: () => import('./creator/create-page').then((module) => module.CreatePage),
  },
  {
    path: 'editor',
    loadComponent: () => import('./editor/editor-page').then((module) => module.EditorPage),
  },
  {
    path: 'editor/:campaignId',
    loadComponent: () => import('./editor/editor-page').then((module) => module.EditorPage),
  },
];
