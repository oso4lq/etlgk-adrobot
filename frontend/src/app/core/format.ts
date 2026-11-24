import { AutocompleteOption } from '../shared/autocomplete/autocomplete';
import { OfferSummary } from './api-types';

// Created once: constructing Intl formatters is comparatively expensive and the options never change.
const dateTimeFormat = new Intl.DateTimeFormat('ru-RU', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

export function toOfferOption(offer: OfferSummary): AutocompleteOption {
  return { id: offer.id, label: `${offer.id} — ${offer.name}` };
}

export function formatDateTime(iso: string): string {
  return dateTimeFormat.format(new Date(iso));
}
