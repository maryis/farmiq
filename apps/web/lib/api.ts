export async function getDemoFarm() {
  const response = await fetch('/api/v1/demo', { cache: 'no-store' });
  if (!response.ok) throw new Error('Demo farm unavailable');
  return response.json() as Promise<{ farm_id: string; name: string }>;
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`, { cache: 'no-store' });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}
