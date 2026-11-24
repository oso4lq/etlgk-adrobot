import { Component, effect, inject, input } from '@angular/core';
import { Router } from '@angular/router';
import { Autocomplete, AutocompleteOption } from '../shared/autocomplete/autocomplete';
import { EditorStore } from './editor-store';
import { StreamCard } from './stream-card';

@Component({
  selector: 'app-editor-page',
  imports: [Autocomplete, StreamCard],
  providers: [EditorStore],
  templateUrl: './editor-page.html',
  styleUrl: './editor-page.css',
})
export class EditorPage {
  readonly campaignId = input<string>();

  protected readonly store = inject(EditorStore);
  private readonly router = inject(Router);

  constructor() {
    effect(() => {
      const campaignId = this.campaignId();
      if (campaignId !== undefined) {
        this.store.open(campaignId);
      }
    });
  }

  protected campaignChosen(option: AutocompleteOption | null): void {
    if (option !== null) {
      void this.router.navigate(['/editor', option.id]);
    }
  }
}
