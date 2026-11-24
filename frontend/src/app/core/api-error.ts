import { HttpErrorResponse } from '@angular/common/http';

export interface ApiError {
  code: string;
  message: string;
  status: number;
}

// Statuses the dev proxy or a gateway returns when the backend itself is not answering.
const GATEWAY_STATUSES = [502, 503, 504];

function isApiErrorBody(body: unknown): body is { code: string; message: string } {
  if (typeof body !== 'object' || body === null) {
    return false;
  }
  const candidate = body as { code?: unknown; message?: unknown };
  return typeof candidate.code === 'string' && typeof candidate.message === 'string';
}

export function toApiError(error: unknown): ApiError {
  if (!(error instanceof HttpErrorResponse)) {
    return { code: 'unexpected_error', message: 'Непредвиденная ошибка', status: 0 };
  }
  if (error.status === 0) {
    return { code: 'network_error', message: 'Бэкенд недоступен', status: 0 };
  }
  if (isApiErrorBody(error.error)) {
    return { code: error.error.code, message: error.error.message, status: error.status };
  }
  // A gateway answer has no JSON body from our API, so it is told apart by status only.
  if (GATEWAY_STATUSES.includes(error.status)) {
    return {
      code: 'backend_unavailable',
      message: `Бэкенд недоступен (HTTP ${error.status})`,
      status: error.status,
    };
  }
  return {
    code: 'unexpected_response',
    message: `Неожиданный ответ сервера (HTTP ${error.status})`,
    status: error.status,
  };
}
