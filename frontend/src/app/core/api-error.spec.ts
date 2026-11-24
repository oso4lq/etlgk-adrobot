import { HttpErrorResponse } from '@angular/common/http';
import { toApiError } from './api-error';

describe('toApiError', () => {
  it('keeps code and message from an API error body', () => {
    const error = new HttpErrorResponse({
      status: 409,
      error: { code: 'stream_not_draft', message: 'Нечего публиковать…' },
    });
    expect(toApiError(error)).toEqual({
      code: 'stream_not_draft',
      message: 'Нечего публиковать…',
      status: 409,
    });
  });

  it('maps status 0 to backend unavailable', () => {
    const error = new HttpErrorResponse({ status: 0 });
    expect(toApiError(error)).toEqual({
      code: 'network_error',
      message: 'Бэкенд недоступен',
      status: 0,
    });
  });

  it('maps proxy error without JSON body to backend_unavailable', () => {
    for (const status of [502, 503, 504]) {
      const error = new HttpErrorResponse({ status, error: 'Bad Gateway' });
      expect(toApiError(error)).toEqual({
        code: 'backend_unavailable',
        message: `Бэкенд недоступен (HTTP ${status})`,
        status,
      });
    }
  });

  it('maps other bodies to unexpected_response', () => {
    const expected = {
      code: 'unexpected_response',
      message: 'Неожиданный ответ сервера (HTTP 500)',
      status: 500,
    };
    expect(toApiError(new HttpErrorResponse({ status: 500, error: 'oops' }))).toEqual(expected);
    expect(toApiError(new HttpErrorResponse({ status: 500, error: { code: 1 } }))).toEqual(expected);
  });

  it('maps non-HTTP errors to unexpected_error', () => {
    expect(toApiError(new Error('x'))).toEqual({
      code: 'unexpected_error',
      message: 'Непредвиденная ошибка',
      status: 0,
    });
  });
});
