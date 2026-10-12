export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// Fired when the server says nobody is signed in (accounts on, sign-in expired or signed out
// elsewhere): AuthGate shows the sign-in screen.
export const SIGNED_OUT = 'footsim:signed-out'

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (response.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event(SIGNED_OUT))
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    try {
      const data = (await response.json()) as { detail?: unknown }
      if (typeof data.detail === 'string') message = data.detail
    } catch {
      // keep the status text
    }
    throw new ApiError(response.status, message)
  }
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
  put: <T>(path: string, body: unknown) => request<T>('PUT', path, body),
  delete: <T>(path: string) => request<T>('DELETE', path),
}
