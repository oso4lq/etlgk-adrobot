import { Component, inject } from '@angular/core';
import { FormField } from '@angular/forms/signals';
import { RouterLink } from '@angular/router';
import { Autocomplete } from '../shared/autocomplete/autocomplete';
import { CreatorStore } from './creator-store';

@Component({
  selector: 'app-create-page',
  imports: [FormField, RouterLink, Autocomplete],
  providers: [CreatorStore],
  templateUrl: './create-page.html',
  styleUrl: './create-page.css',
})
export class CreatePage {
  protected readonly store = inject(CreatorStore);

  constructor() {
    this.store.load();
  }
}
