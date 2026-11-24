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
  const date = new Date(iso);
  // Intl throws RangeError on an invalid date, which would blank the whole page.
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return dateTimeFormat.format(date);
}
