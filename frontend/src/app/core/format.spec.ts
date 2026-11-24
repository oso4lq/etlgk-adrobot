import { formatDateTime, toOfferOption } from './format';

describe('format', () => {
  it('labels an offer as id and name', () => {
    expect(toOfferOption({ id: 18813, name: 'Test offer' })).toEqual({
      id: 18813,
      label: '18813 — Test offer',
    });
  });

  it('formats a date in local time without depending on the machine time zone', () => {
    const iso = '2026-11-24T10:05:00+00:00';
    const expected = new Intl.DateTimeFormat('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(new Date(iso));

    expect(formatDateTime(iso)).toBe(expected);
  });
});
