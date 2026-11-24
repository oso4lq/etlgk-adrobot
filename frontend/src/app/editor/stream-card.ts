import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import {
  Autocomplete,
  AutocompleteOption,
  AutocompleteSearch,
} from '../shared/autocomplete/autocomplete';
import { StreamView } from './editor-view';

// Pure presentation: shows the prepared StreamView and forwards user events upward.
@Component({
  selector: 'app-stream-card',
  imports: [Autocomplete],
  templateUrl: './stream-card.html',
  styleUrl: './stream-card.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class StreamCard {
  readonly stream = input.required<StreamView>();
  readonly searchOffers = input.required<AutocompleteSearch>();

  readonly offerSelected = output<AutocompleteOption | null>();
  readonly add = output<void>();
  readonly push = output<void>();
  // The name is fixed by the task contract; the card is not a native element that fires `cancel`.
  // eslint-disable-next-line @angular-eslint/no-output-native
  readonly cancel = output<void>();
  readonly remove = output<number>();
  readonly bringBack = output<number>();
  readonly pin = output<number>();
  readonly unpin = output<number>();
}
